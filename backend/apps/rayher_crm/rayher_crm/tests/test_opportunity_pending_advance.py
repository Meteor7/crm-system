"""A Demo done that waits for the amount, with the Demo review and the amount save in separate requests (#22).

Each request is its own transaction, so these tests commit their data where a second connection or thread
has to see it, and remove it again afterwards. Administrator acts as a CRM Manager and owns the Opportunity,
so no user has to be committed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import (
    advance_opportunity_for_event,
    create_strategy_opportunity,
    get_strategy_opportunity,
    update_strategy_opportunity,
)
from rayher_crm.services.sites import create_site


AMOUNTS = {"amount": "480000", "originalAmount": "480000", "amountCny": "480000"}


class TestPendingDemoDoneAcrossRequests(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=8)
        self.evaluation = f"CRM-EVAL-PENDING-{token}"
        account = create_account({
            "name": f"Pending Advance {token}", "shortName": f"Pending{token}", "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": "Administrator",
        })
        site = create_site(account["id"], {
            "name": f"Pending {token} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        self.account, self.site = account["id"], site["id"]
        self.opportunity = create_strategy_opportunity({
            "accountId": self.account, "siteId": self.site, "title": f"Pending advance {token}",
            "owner": "Administrator", "amount": "", "originalAmount": "", "amountCny": "", "intentScore": 35,
            "poDate": "2026-12-31", "toolType": "Inspection", "saleType": "New Equipment", "subRegion": "华东",
            "currency": "CNY", "qualificationConfirmed": True, "probabilityLevel": "pipeline",
        })
        frappe.db.commit()
        self.addCleanup(self._remove_committed_rows)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _remove_committed_rows(self):
        frappe.local.db = self._primary_connection
        frappe.db.rollback()
        name = self.opportunity["id"]
        for doctype in (
            "CRM Opportunity Stage History", "CRM Opportunity Probability History", "CRM Opportunity History",
        ):
            frappe.db.delete(doctype, {"opportunity": name})
        frappe.db.delete("CRM Notification Event", {"source_doctype": "CRM Opportunity", "source_name": name})
        frappe.db.delete("Version", {"ref_doctype": "CRM Opportunity", "docname": name})
        frappe.db.delete("CRM Opportunity", {"name": name})
        frappe.db.delete("Dynamic Link", {"parenttype": "Address", "parent": self.site})
        frappe.db.delete("Address", {"name": self.site})
        frappe.db.delete("Customer", {"name": self.account})
        frappe.db.commit()

    def _demo_review(self):
        advance_opportunity_for_event(
            self.opportunity["id"], "demo_customer_review",
            reference_doctype="CRM Evaluation", reference_name=self.evaluation,
        )

    def _demo_moves(self, opportunity: dict) -> list[tuple[str, str]]:
        return [
            (row["reason"], row["referenceName"])
            for row in opportunity["stageHistory"] if row["event"] == "demo_customer_review"
        ]

    def _notices(self) -> int:
        return frappe.db.count(
            "CRM Notification Event", {"source_doctype": "CRM Opportunity", "source_name": self.opportunity["id"]},
        )

    def test_a_demo_review_sees_an_amount_saved_after_its_request_began(self):
        name = self.opportunity["id"]
        with self.secondary_connection():
            # The Demo review's request has already read the Opportunity, without an amount, when the
            # owner's save commits; it must not act on that older snapshot.
            self.assertEqual(frappe.db.get_value("CRM Opportunity", name, "amount_cny"), 0)
            with self.primary_connection():
                priced = update_strategy_opportunity(name, AMOUNTS, self.opportunity["modified"])
                self.assertEqual((priced["stage"], priced["pendingStageAdvance"]), ("qualified_opportunity", ""))
                frappe.db.commit()
            self._demo_review()
            frappe.db.commit()

        current = get_strategy_opportunity(name)
        self.assertEqual(
            (current["stage"], current["pendingStageAdvance"], current["amountCny"]), ("demo_done", "", "480000.00"),
        )
        # Moved by the Demo review itself: nothing waited, nobody was asked for the amount.
        self.assertEqual(self._demo_moves(current), [("", self.evaluation)])
        self.assertEqual(self._notices(), 0)

    def test_two_saves_of_the_amount_at_once_apply_the_waiting_demo_done_once(self):
        name = self.opportunity["id"]
        self._demo_review()
        frappe.db.commit()
        waiting = get_strategy_opportunity(name)
        self.assertEqual((waiting["stage"], waiting["pendingStageAdvance"]), ("qualified_opportunity", "demo_done"))
        # A form opened before the Demo review is refused, so the owner reloads and sees what waits.
        with self.assertRaises(CrmApiException) as stale:
            update_strategy_opportunity(name, AMOUNTS, self.opportunity["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        frappe.db.rollback()

        site = frappe.local.site
        gate = Barrier(2)

        def save() -> str:
            # Two tabs, or a double click: the same form submitted twice at the same moment.
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                gate.wait(timeout=10)
                try:
                    update_strategy_opportunity(name, AMOUNTS, waiting["modified"])
                except CrmApiException as exc:
                    frappe.db.rollback()
                    return exc.code
                frappe.db.commit()
                return "saved"
            finally:
                frappe.destroy()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(save), executor.submit(save)]
            outcomes = sorted(future.result(timeout=60) for future in futures)
        self.assertEqual(outcomes, ["VERSION_CONFLICT", "saved"])

        frappe.db.rollback()
        current = get_strategy_opportunity(name)
        self.assertEqual((current["stage"], current["pendingStageAdvance"]), ("demo_done", ""))
        self.assertEqual(self._demo_moves(current), [("Demo done pending amount", self.evaluation)])
        self.assertEqual(self._notices(), 1)
