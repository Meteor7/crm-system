import re
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import quotation_planning as service
from rayher_crm.tests.test_quotation_api import TestQuotationApi


class TestQuotationPlanning(FrappeTestCase):
    _user = TestQuotationApi._user
    _opportunity = TestQuotationApi._opportunity
    _ready_quotation = TestQuotationApi._ready_quotation
    _publish = TestQuotationApi._publish

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("quote-plan-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("quote-plan-other@example.invalid", "CRM Sales")
        self.manager = self._user("quote-plan-manager@example.invalid", "CRM Manager")

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_schedule_uses_master_cas_and_publishing_closes_scheduling(self):
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        first = service.get_planning(quote_id)
        plan = service.save_schedule(quote_id, {"plannedSendDate": "2026-10-12"}, first["modified"])
        self.assertEqual(plan["plannedSendDate"], "2026-10-12")
        with self.assertRaises(CrmApiException) as stale:
            service.save_schedule(quote_id, {"plannedSendDate": None}, first["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        published = self._publish(quote_id, saved["version"]["modified"])
        current = service.get_planning(quote_id)
        self.assertIsNone(current["plannedSendDate"])
        with self.assertRaises(CrmApiException) as locked:
            service.save_schedule(quote_id, {"plannedSendDate": "2026-10-13"}, current["modified"])
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")
        cleared = service.save_schedule(quote_id, {"plannedSendDate": None}, current["modified"])
        self.assertIsNone(cleared["plannedSendDate"])
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", published["version"]["id"], "status"), "Published")
        from rayher_crm.services import quotations
        revision = quotations.create_version(quote_id)
        current = service.get_planning(quote_id)
        self.assertIsNone(current["plannedSendDate"])
        service.save_schedule(quote_id, {"plannedSendDate": "2026-10-20"}, current["modified"])
        quotations.discard_draft(quote_id, revision["version"]["modified"])
        self.assertIsNone(service.get_planning(quote_id)["plannedSendDate"])

    def test_follow_up_completion_snapshot_survives_note_edits_and_clears_on_reopen(self):
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        published = self._publish(quote_id, saved["version"]["modified"])
        first = service.get_planning(quote_id)
        payload = {"title": "Confirm customer response", "due": "2026-10-12", "status": "Open", "note": ""}
        result = service.save_follow_up(quote_id, payload, expected_modified=first["modified"])
        followup_id = result["followUps"][0]["id"]
        with patch("frappe.utils.now_datetime", return_value=datetime(2026, 10, 5, 15)):
            done = service.save_follow_up(quote_id, {**payload, "status": "Done"}, followup_id, result["modified"])
        completed = done["followUps"][0]["completedAt"]
        self.assertEqual(done["followUps"][0]["completedVersion"], published["version"]["id"])
        self.assertEqual(frappe.db.get_value("CRM Quotation Follow Up", followup_id, "completed_owner"), self.sales)
        changed = service.save_follow_up(quote_id, {**payload, "status": "Done", "note": "Additional context"}, followup_id, done["modified"])
        self.assertEqual(changed["followUps"][0]["completedAt"], completed)
        with self.assertRaises(CrmApiException) as stale:
            service.save_follow_up(quote_id, payload, followup_id, done["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        reopened = service.save_follow_up(quote_id, payload, followup_id, changed["modified"])
        self.assertIsNone(reopened["followUps"][0]["completedAt"])
        self.assertIsNone(reopened["followUps"][0]["completedVersion"])
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": "CRM Quotation", "docname": quote_id}))

    def test_scope_and_open_quote_checks_apply_to_child_followups(self):
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        first = service.get_planning(quote_id)
        payload = {"title": "Follow up", "due": "2026-10-12", "status": "Open", "note": ""}
        with self.assertRaises(CrmApiException) as unopened:
            service.save_follow_up(quote_id, payload, expected_modified=first["modified"])
        self.assertEqual(unopened.exception.code, "INVALID_TRANSITION")
        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException):
            service.get_planning(quote_id)
        with self.assertRaises(CrmApiException):
            service.save_schedule(quote_id, {"plannedSendDate": "2026-10-12"}, first["modified"])
        self.assertFalse(frappe.get_all("CRM Quotation Follow Up", filters={"parent": quote_id}, pluck="name"))

    def test_an_archived_opportunitys_quotation_takes_no_send_plan_and_no_follow_up_and_leaves_plan(self):
        from rayher_crm.services import cockpit
        from rayher_crm.services.opportunities import archive_strategy_opportunity, unarchive_strategy_opportunity
        from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_EDIT
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        opportunity_id = saved["quotation"]["opportunityId"]
        scheduled = service.save_schedule(quote_id, {"plannedSendDate": "2030-10-14"}, service.get_planning(quote_id)["modified"])

        def planned() -> set[str]:
            frappe.set_user(self.manager)
            try:
                details = cockpit.get_plan_details({"period": "week", "anchor": "2030-10-14", "metric": "quotes", "sales": self.sales, "pageSize": 100})
            finally:
                frappe.set_user(self.sales)
            return {row.get("quotationId") for row in details["items"]}

        self.assertIn(quote_id, planned())
        frappe.set_user(self.manager)
        archive_strategy_opportunity(opportunity_id)
        frappe.set_user(self.sales)
        self.assertNotIn(quote_id, planned())
        modified = frappe.db.get_value("CRM Quotation", quote_id, "modified")
        follow_up = {"title": "Chase the customer", "due": "2030-10-15", "status": "Open", "note": ""}
        real_sql = frappe.db.sql
        statements: list[str] = []

        def watch(query, *args, **kwargs):
            statements.append(str(query))
            return real_sql(query, *args, **kwargs)

        for attempt in (
            lambda: service.save_schedule(quote_id, {"plannedSendDate": None}, scheduled["modified"]),
            lambda: service.save_follow_up(quote_id, follow_up, expected_modified=scheduled["modified"]),
        ):
            statements.clear()
            with self.assertRaises(CrmApiException) as refused, patch.object(frappe.db, "sql", side_effect=watch):
                attempt()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_EDIT))
            # The flag is read under the Opportunity's row lock, as committed, by each attempt: every statement on the
            # Opportunity's table that reads the archive's columns or the whole row, as these paths write them, is a
            # locking one without a subquery (which would read the snapshot's, without a lock), one of them FOR UPDATE
            # (a read served from the cache is not seen).
            reads = [text.upper() for text in statements if re.search(r"`tabCRM Opportunity`", text, re.I)
                     and re.search(r"\barchived(?:_at|_by)?\b|(?:SELECT|,)\s*(?:`[^`]+`\.|\w+\.)?\*", text, re.I)]
            self.assertTrue(any("FOR UPDATE" in text for text in reads), statements)
            self.assertTrue(all(("FOR UPDATE" in text or "LOCK IN SHARE MODE" in text) and text.count("SELECT") == 1
                                for text in reads), reads)
        self.assertEqual(
            frappe.db.get_value("CRM Quotation", quote_id, ["planned_send_date", "modified"]),
            (frappe.utils.getdate("2030-10-14"), modified),
        )
        self.assertFalse(frappe.get_all("CRM Quotation Follow Up", filters={"parent": quote_id}, pluck="name"))

        frappe.set_user(self.manager)
        unarchive_strategy_opportunity(opportunity_id)
        frappe.set_user(self.sales)
        self.assertIn(quote_id, planned())
        self.assertIsNone(service.save_schedule(quote_id, {"plannedSendDate": None}, scheduled["modified"])["plannedSendDate"])

    def test_an_archived_accounts_quotation_takes_no_send_plan_and_no_follow_up_until_the_restore(self):
        from rayher_crm.services import quotations
        from rayher_crm.services.accounts import ARCHIVED_ACCOUNT_EDIT, archive_account, unarchive_account
        from rayher_crm.services.opportunities import archive_strategy_opportunity
        opportunity = self._opportunity()
        created = quotations.create_quotation({"accountId": opportunity["accountId"], "quotationType": "Service"})
        quote_id = created["quotation"]["id"]
        plan = service.get_planning(quote_id)
        frappe.set_user(self.manager)
        archive_strategy_opportunity(opportunity["id"])
        archive_account(opportunity["accountId"])
        frappe.set_user(self.sales)
        modified = frappe.db.get_value("CRM Quotation", quote_id, "modified")
        follow_up = {"title": "Service response", "due": "2030-10-01", "status": "Done", "note": ""}
        for attempt in (
            lambda: service.save_schedule(quote_id, {"plannedSendDate": "2030-10-14"}, plan["modified"]),
            lambda: service.save_follow_up(quote_id, follow_up, expected_modified=plan["modified"]),
        ):
            with self.assertRaises(CrmApiException) as refused:
                attempt()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_ACCOUNT_EDIT))
        self.assertEqual(frappe.db.get_value("CRM Quotation", quote_id, ["planned_send_date", "modified"]), (None, modified))
        self.assertFalse(frappe.get_all("CRM Quotation Follow Up", filters={"parent": quote_id}, pluck="name"))
        frappe.set_user(self.manager)
        unarchive_account(opportunity["accountId"])
        frappe.set_user(self.sales)
        self.assertEqual(service.save_schedule(quote_id, {"plannedSendDate": "2030-10-14"}, plan["modified"])["plannedSendDate"], "2030-10-14")

    def test_a_quotations_plan_answers_to_its_deals_account_now(self):
        from rayher_crm.services.accounts import ARCHIVED_ACCOUNT_EDIT, archive_account, create_account
        from rayher_crm.services.opportunities import get_strategy_opportunity, mark_opportunity_lost, update_strategy_opportunity
        from rayher_crm.services.sites import create_site
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        deal_id = saved["quotation"]["opportunityId"]
        first = frappe.db.get_value("CRM Opportunity", deal_id, "account")
        suffix = frappe.generate_hash(length=6)
        frappe.set_user(self.sales)
        second = create_account({"name": f"Plan Move To {suffix}", "shortName": f"PM{suffix}", "segment": "Frontend",
                                 "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        second_site = create_site(second["id"], {"name": f"Plan Move To {suffix} Site", "city": "上海", "type": "Fab",
                                                 "process": "Frontend", "status": "量产"})
        deal = update_strategy_opportunity(deal_id, {"accountId": second["id"], "siteId": second_site["id"]},
                                           get_strategy_opportunity(deal_id)["modified"])
        # The Account it was addressed to archived: it answers to its deal's now, and plans on.
        frappe.set_user(self.manager)
        archive_account(first)
        frappe.set_user(self.sales)
        plan = service.save_schedule(quote_id, {"plannedSendDate": "2030-10-14"}, service.get_planning(quote_id)["modified"])
        self.assertEqual(plan["plannedSendDate"], "2030-10-14")
        # Its deal's Account archived (the deal closed first): frozen with it.
        mark_opportunity_lost(deal_id, {"lostReason": "Moved on"}, deal["modified"])
        frappe.set_user(self.manager)
        archive_account(second["id"])
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as refused:
            service.save_schedule(quote_id, {"plannedSendDate": None}, plan["modified"])
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_ACCOUNT_EDIT))
        self.assertEqual(str(frappe.db.get_value("CRM Quotation", quote_id, "planned_send_date")), "2030-10-14")

    def test_a_plan_whose_deal_moved_since_the_first_read_is_refused_as_changed(self):
        from rayher_crm.services.accounts import create_account
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        plan = service.get_planning(quote_id)
        suffix = frappe.generate_hash(length=6)
        frappe.set_user(self.sales)
        elsewhere = create_account({"name": f"Plan Elsewhere {suffix}", "shortName": f"PE{suffix}", "segment": "Frontend",
                                    "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        modified = frappe.db.get_value("CRM Quotation", quote_id, "modified")
        # A first read that has the deal under an Account it has left since: refused as changed under the deal's lock,
        # once the scope is checked, nothing written.
        with patch.object(service, "_quotation_account", return_value=elsewhere["id"]):
            with self.assertRaises(CrmApiException) as changed:
                service.save_schedule(quote_id, {"plannedSendDate": "2030-10-14"}, plan["modified"])
        # The deal's own refusal (the version sent is current: its check has a sentence of its own).
        self.assertEqual(
            (changed.exception.code, changed.exception.public_message), ("VERSION_CONFLICT", "The record was changed by another request."),
        )
        self.assertEqual(frappe.db.get_value("CRM Quotation", quote_id, ["planned_send_date", "modified"]), (None, modified))
        # A Sales user out of its scope is told so first, whatever moved meanwhile (the snapshot's own check of the
        # Quotation passed over, as when the scope changed after it).
        frappe.set_user(self.other_sales)
        with (
            patch.object(service, "_quotation_account", return_value=elsewhere["id"]),
            patch.object(service, "_require_quotation") as passed_over,
            self.assertRaises(CrmApiException) as denied,
        ):
            service.save_schedule(quote_id, {"plannedSendDate": "2030-10-14"}, plan["modified"])
        passed_over.assert_called_once_with(quote_id)
        self.assertEqual(
            (denied.exception.code, denied.exception.public_message), ("SCOPE_DENIED", "Quotation is outside the current user scope."),
        )

    def test_the_plan_takes_the_quotation_then_its_accounts_shared_then_its_deal(self):
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        modified = service.get_planning(quote_id)["modified"]
        real_sql = frappe.db.sql
        locks: list[tuple[str, str]] = []

        def watch(query, *args, **kwargs):
            text = str(query)
            mode = "exclusive" if "FOR UPDATE" in text else "shared" if "LOCK IN SHARE MODE" in text else None
            # Every table the statement reads takes its lock: a join's rows, each of them.
            for table in re.findall(r"(?:FROM|JOIN)\s+`(tab[^`]+)`", text) if mode else ():
                locks.append((table, mode))
            return real_sql(query, *args, **kwargs)

        with patch.object(frappe.db, "sql", side_effect=watch):
            service.locked(quote_id, modified)
        # The order of every Quotation writer: the Quotation's row, its Accounts' (shared, by one statement), its
        # Opportunity's; no Account's row is taken exclusively.
        first = list(dict.fromkeys(locks))
        self.assertEqual(first[:3], [("tabCRM Quotation", "exclusive"), ("tabCustomer", "shared"), ("tabCRM Opportunity", "exclusive")], locks)
        self.assertNotIn(("tabCustomer", "exclusive"), locks)

    def test_account_only_service_quote_can_complete_and_cancel_followups(self):
        from rayher_crm.services import quotations
        opportunity = self._opportunity()
        created = quotations.create_quotation({"accountId": opportunity["accountId"], "quotationType": "Service"})
        quote_id = created["quotation"]["id"]
        payload = {key: created["version"][key] for key in (
            "quoteDate", "validityMonths", "items", "discountType", "discountValue", "deliveryMonths", "warrantyMonths",
        )}
        payload.update(primaryContactId=self.quotation_contact["id"], addressId=self.quotation_site["id"])
        saved = quotations.save_draft(quote_id, payload, created["version"]["modified"])
        self._publish(quote_id, saved["version"]["modified"])
        plan = service.get_planning(quote_id)
        followup = {"title": "Service response", "due": "2030-10-01", "status": "Done", "note": "Confirmed"}
        done = service.save_follow_up(quote_id, followup, expected_modified=plan["modified"])
        row = done["followUps"][0]
        self.assertTrue(row["completedAt"])
        self.assertFalse(frappe.db.get_value("CRM Quotation", quote_id, "opportunity"))
        cancelled = service.save_follow_up(quote_id, {**followup, "status": "Cancelled"}, row["id"], done["modified"])
        self.assertIsNone(cancelled["followUps"][0]["completedAt"])
