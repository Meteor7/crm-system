from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import frappe
from frappe.model.delete_doc import get_dynamic_linked_docs, get_linked_docs
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services import bookings as booking_service

from rayher_crm.api.v1.bookings import list_bookings as list_bookings_endpoint
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.bookings import (
    ARCHIVED_BOOKING_EDIT,
    COMPLETED_BOOKING_ARCHIVE,
    OPPORTUNITY_BOOKING_ARCHIVE,
    archive_booking,
    booking_summary,
    complete_service_booking,
    create_booking,
    get_booking,
    list_bookings,
    set_booking_actual_po_date,
    set_booking_amount_cny,
    unarchive_booking,
    update_booking,
)
from rayher_crm.services.contacts import create_contact, get_contact
from rayher_crm.services.dashboard import get_dashboard
from rayher_crm.services.installed_tools import convert_booking_to_installed_tool
from rayher_crm.services.opportunities import confirm_po, create_strategy_opportunity, get_strategy_opportunity
from rayher_crm.services.pipeline import list_pipeline
from rayher_crm.services.opportunity_stages import PO_RECEIVED, QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestBookingApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-booking-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-booking-other@example.invalid", "CRM Sales")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
            user.enabled = 1
            if role not in {row.role for row in user.roles}:
                user.append("roles", {"role": role})
                user.save(ignore_permissions=True)
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _records(self, owner: str, suffix: str, stage: str = PO_RECEIVED, sale_type: str = "New Equipment"):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Booking {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": owner,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"booking-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": owner, "status": "Active",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Opportunity",
            "owner": owner, "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline",
            "amount": 200000, "intentScore": 80, "qualificationConfirmed": True,
            "poDate": "2026-12-31", "toolType": "Inspection", "saleType": sale_type,
            "subRegion": "华东", "currency": "CNY", "originalAmount": 200000, "amountCny": 200000,
        })
        # Opportunity Bookings are only created by the PO confirmation that reaches po_received.
        booking = self._booking_draft(contact, owner) if stage == PO_RECEIVED else None
        opportunity = advance_opportunity_fixture(opportunity, stage, booking=booking)
        return account, site, contact, opportunity

    def _booking_draft(self, contact: dict, owner: str, **overrides):
        draft = {
            "primaryContactId": contact["id"], "equipment": "Inspection 3000", "quantity": 2,
            "ddl": "2027-01-31", "amount": "200000.00", "currency": "CNY", "owner": owner,
            "note": "Priority delivery",
        }
        draft.update(overrides)
        return draft

    def _input(self, account: dict, contact: dict, opportunity: dict | None, owner: str, **overrides):
        payload = {
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Inspection 3000",
            "quantity": 2, "ddl": "2027-01-31", "amount": "200000.00", "currency": "CNY", "status": "Confirmed",
            "owner": owner, "source": "Opportunity" if opportunity else "Upsell",
            "sourceOpportunityId": opportunity["id"] if opportunity else "", "note": "Priority delivery",
        }
        payload.update(overrides)
        return payload

    def test_summary_counts_and_totals_every_booking_the_query_matches(self):
        account, _, contact, _ = self._records(self.sales, "Summary")
        # The PO confirmation left one Confirmed CNY Booking; two Upsell Bookings join it.
        create_booking(self._input(account, contact, None, self.sales, status="Pending", amount="100.00"))
        create_booking(self._input(
            account, contact, None, self.sales, currency="USD", amount="20000.00", amountCny="140000.00",
        ))

        summary = booking_summary({"accountId": account["id"], "page": 1, "pageSize": 1})
        self.assertEqual((summary["count"], summary["pendingCount"], summary["confirmed"]["count"]), (3, 1, 2))
        self.assertEqual(
            summary["confirmed"]["totals"],
            [{"currency": "CNY", "amount": "200000.00"}, {"currency": "USD", "amount": "20000.00"}],
        )
        # The filters of the list apply; the page does not.
        pending = booking_summary({"accountId": account["id"], "status": "Pending"})
        self.assertEqual((pending["count"], pending["pendingCount"], pending["confirmed"]), (1, 1, {"count": 0, "totals": []}))
        # The endpoint returns it with the page, in the same request, only when asked; the browser sends "true".
        # Its count is the list's total, whatever page is asked for.
        for asked in ("true", "1"):
            with_summary = list_bookings_endpoint(accountId=account["id"], page=1, pageSize=1, summary=asked)
            self.assertEqual(with_summary["data"]["summary"], summary)
            self.assertEqual((len(with_summary["data"]["items"]), with_summary["meta"]["total"]), (1, summary["count"]))
        self.assertEqual(
            list_bookings_endpoint(accountId=account["id"], page=2, pageSize=1, summary="true")["data"]["summary"], summary,
        )
        for not_asked in ({}, {"summary": "false"}, {"summary": "0"}, {"summary": ""}):
            answer = list_bookings_endpoint(accountId=account["id"], page=1, pageSize=1, **not_asked)
            self.assertNotIn("summary", answer["data"])
        # The caller's scope applies: another Sales user sees none of them.
        frappe.set_user(self.other_sales)
        self.assertEqual(booking_summary({"accountId": account["id"]})["count"], 0)

    def test_create_list_get_update_and_cas(self):
        account, _, _, opportunity = self._records(self.sales, "Core")
        created = get_booking(opportunity["liveBooking"]["id"])
        self.assertRegex(created["id"], r"^CRM-BKG-\d{5}$")
        self.assertEqual(
            (created["status"], created["source"], created["sourceOpportunityId"], created["bookingType"]),
            ("Confirmed", "Opportunity", opportunity["id"], "Equipment"),
        )
        self.assertEqual(created["accountName"], account["name"])
        self.assertEqual(created["customerContact"], "Core Contact")
        self.assertEqual(created["title"], "Inspection 3000 · 2 台")
        self.assertRegex(created["modified"], r"Z$")
        before_modified = frappe.db.get_value("CRM Booking", created["id"], "modified")
        self.assertEqual(get_booking(created["id"])["id"], created["id"])
        self.assertIn(created["id"], {item["id"] for item in list_bookings()})
        page, total, page_number, page_size = list_bookings({"page": 1, "pageSize": 1})
        self.assertEqual((len(page), total, page_number, page_size), (1, 1, 1, 1))
        self.assertEqual(frappe.db.get_value("CRM Booking", created["id"], "modified"), before_modified)

        with self.assertRaises(CrmApiException) as stale:
            update_booking(created["id"], {"note": "stale"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        updated = update_booking(created["id"], {"quantity": 3, "note": "Await delivery slot"}, created["modified"])
        self.assertEqual(
            (updated["status"], updated["quantity"], updated["note"]), ("Confirmed", 3, "Await delivery slot"),
        )

    def test_source_contact_status_and_duplicate_rules(self):
        account, _, contact, won = self._records(self.sales, "Rules")
        open_account, _, _, open_opportunity = self._records(self.sales, "Open", stage=QUALIFIED_OPPORTUNITY)
        cases = [
            # Opportunity Bookings come only from the PO confirmation, whatever the Opportunity stage.
            (self._input(account, contact, None, self.sales, source="Opportunity", sourceOpportunityId=""), "INVALID_TRANSITION"),
            (self._input(account, contact, open_opportunity, self.sales), "INVALID_TRANSITION"),
            (self._input(account, contact, won, self.sales), "INVALID_TRANSITION"),
            (self._input(account, contact, None, self.sales, status="Completed"), "INVALID_TRANSITION"),
            (self._input(account, contact, None, self.sales, quantity=0), "VALIDATION_ERROR"),
            (self._input(account, contact, None, self.sales, amount=-1), "VALIDATION_ERROR"),
            (self._input(account, contact, None, self.sales, ddl="2026-02-30"), "VALIDATION_ERROR"),
        ]
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaises(CrmApiException) as error:
                create_booking(payload)
            self.assertEqual(error.exception.code, code)
        self.assertFalse(frappe.db.exists("CRM Booking", {"source_opportunity": open_opportunity["id"]}))

        first = get_booking(won["liveBooking"]["id"])
        self.assertEqual(
            frappe.db.get_value("CRM Booking", first["id"], "live_source_opportunity"),
            won["id"],
        )
        unique_indexes = frappe.db.sql(
            "SHOW INDEX FROM `tabCRM Booking` WHERE Column_name = 'live_source_opportunity' AND Non_unique = 0",
            as_dict=True,
        )
        self.assertTrue(unique_indexes)
        with self.assertRaises(CrmApiException) as duplicate:
            confirm_po(won["id"], {
                "booking": self._booking_draft(contact, self.sales), "actualPoDate": frappe.utils.today(),
            }, won["modified"])
        self.assertEqual(duplicate.exception.code, "CONFLICT")

        # An Opportunity Booking follows its Opportunity: details may change, the status only to Cancelled.
        for changes in (
            {"accountId": open_account["id"]},
            {"source": "Upsell", "sourceOpportunityId": ""},
            {"sourceOpportunityId": open_opportunity["id"]},
            {"bookingType": "Service"},
            {"status": "Pending"},
            {"status": "Completed"},
        ):
            with self.subTest(changes=changes), self.assertRaises(CrmApiException) as fixed:
                update_booking(first["id"], changes, first["modified"])
            self.assertEqual(fixed.exception.code, "INVALID_TRANSITION")

        cancelled = update_booking(first["id"], {"status": "Cancelled"}, first["modified"])
        self.assertEqual(cancelled["status"], "Cancelled")
        self.assertIsNone(frappe.db.get_value("CRM Booking", first["id"], "live_source_opportunity"))
        with self.assertRaises(CrmApiException) as restored:
            update_booking(first["id"], {"status": "Confirmed"}, cancelled["modified"])
        self.assertEqual(restored.exception.code, "INVALID_TRANSITION")
        # Cancelling the Booking moved the Opportunity version; the replacement needs the current one.
        replacement = confirm_po(
            won["id"], {
                "booking": self._booking_draft(contact, self.sales),
                "actualPoDate": frappe.utils.today(),
            }, get_strategy_opportunity(won["id"])["modified"],
        )
        self.assertEqual(replacement["stage"], PO_RECEIVED)
        self.assertNotEqual(replacement["liveBooking"]["id"], first["id"])

    def test_owner_account_contact_scope_and_locked_booking(self):
        account, _, contact, won = self._records(self.sales, "Owned")
        foreign_account, _, foreign_contact, _ = self._records(self.other_sales, "Foreign", stage=QUALIFIED_OPPORTUNITY)
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as forged:
            create_booking(self._input(account, contact, None, self.other_sales))
        self.assertEqual(forged.exception.code, "SCOPE_DENIED")
        # A Contact of someone else's Private Account answers as one that does not exist.
        with self.assertRaises(CrmApiException) as mismatch:
            create_booking(self._input(account, foreign_contact, None, self.sales))
        self.assertEqual(
            (mismatch.exception.code, mismatch.exception.public_message),
            ("NOT_FOUND", "Contact was not found, or you have no access to it."),
        )

        created = get_booking(won["liveBooking"]["id"])
        frappe.set_user(self.other_sales)
        self.assertNotIn(created["id"], {item["id"] for item in list_bookings()})
        with self.assertRaises(CrmApiException) as denied:
            get_booking(created["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

        frappe.set_user("Administrator")
        frappe.db.set_value("CRM Booking", created["id"], {"status": "Completed", "installed_tool": "CRM-TOOL-LOCKED"})
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as locked:
            update_booking(created["id"], {"note": "cannot edit"}, created["modified"])
        self.assertEqual(locked.exception.code, "CONFLICT")
        self.assertTrue(foreign_account["id"])

    def test_only_a_manager_archives_an_upsell_booking_and_the_archive_is_reversible(self):
        account, _, contact, opportunity = self._records(self.other_sales, "Archive")
        po_booking = get_booking(opportunity["liveBooking"]["id"])
        frappe.set_user(self.other_sales)
        # Three amounts apart, so the dashboard's sum tells which of them it counts.
        upsell = create_booking(self._input(account, contact, None, self.other_sales, amount="150000.00"))
        service = create_booking(self._input(account, contact, None, self.other_sales, amount="30000.00", bookingType="Service", equipment="Service plan"))

        frappe.set_user(self.sales)
        for booking_id in (upsell["id"], po_booking["id"]):
            with self.assertRaises(frappe.PermissionError):
                archive_booking(booking_id)
            self.assertEqual(frappe.db.get_value("CRM Booking", booking_id, "archived"), 0)

        frappe.set_user("Administrator")
        # The dashboard reads the Booking list itself (#215), the Account's confirmed orders summed per currency.
        def dashboard_booking() -> Decimal:
            rows = get_dashboard({"range": "quarter"})["topAccounts"]
            return sum((Decimal(row["booking"]) for row in rows if row["accountId"] == account["id"] and row["currency"] == "CNY"), Decimal("0"))
        before = dashboard_booking()
        self.assertEqual(before, sum((Decimal(item["amount"]) for item in (po_booking, upsell, service)), Decimal("0")))

        # And the Contact 360, which reads the list by the Contact.
        def on_contact() -> set[str]:
            return {item["id"] for item in get_contact(contact["id"])["bookings"]} & {upsell["id"], service["id"]}

        self.assertEqual(on_contact(), {upsell["id"], service["id"]})
        # The PO record behind a po_received Opportunity is only ever cancelled, never archived.
        with self.assertRaises(CrmApiException) as protected:
            archive_booking(po_booking["id"])
        # BOOKING_SOURCE_INVALID is published as the INVALID_TRANSITION contract code.
        self.assertEqual((protected.exception.code, protected.exception.public_message), ("INVALID_TRANSITION", OPPORTUNITY_BOOKING_ARCHIVE))
        self.assertEqual(frappe.db.get_value("CRM Booking", po_booking["id"], "archived"), 0)
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["liveBooking"]["id"], po_booking["id"])
        with self.assertRaises(CrmApiException) as missing:
            archive_booking("CRM-BKG-NOBODY")
        self.assertEqual(missing.exception.code, "NOT_FOUND")

        # The archive writes its columns alone: no save of the Booking (the test runner writes no Version row for
        # any save, so a Version count would show nothing; a save is refused here outright). The comment is inserted.
        with patch.object(Document, "save", side_effect=AssertionError("the archive saves no document")):
            archived = archive_booking(upsell["id"])
        self.assertTrue(archived["archived"])
        self.assertEqual(archived["archivedBy"], "Administrator")
        self.assertRegex(archived["archivedAt"], r"Z$")
        self.assertEqual(archived["status"], "Confirmed")
        self.assertTrue(frappe.db.exists("CRM Booking", upsell["id"]))
        # The archive moved the Booking's version: a page opened before holds an older one.
        self.assertNotEqual(archived["modified"], upsell["modified"])
        comments = {"reference_doctype": "CRM Booking", "reference_name": upsell["id"], "comment_type": "Info"}
        self.assertEqual(frappe.get_all("Comment", filters=comments, pluck="content"), ["Archived"])
        # Archived again, nothing changes.
        self.assertEqual(archive_booking(upsell["id"])["archivedAt"], archived["archivedAt"])
        archive_booking(service["id"])

        # Out of the list, its summary, the pipeline, the Account 360 and the dashboard unless the archive is asked for.
        def listed(query: dict) -> set[str]:
            return {item["id"] for item in list_bookings({**query, "accountId": account["id"], "pageSize": 200})[0]}
        self.assertEqual(listed({}), {po_booking["id"]})
        self.assertEqual(listed({"archiveState": "active"}), {po_booking["id"]})
        self.assertEqual(listed({"archiveState": "archived"}), {upsell["id"], service["id"]})
        self.assertEqual(listed({"archiveState": "all"}), {po_booking["id"], upsell["id"], service["id"]})
        with self.assertRaises(CrmApiException) as invalid:
            list_bookings({"archiveState": "deleted"})
        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        self.assertEqual(booking_summary({"accountId": account["id"]})["count"], 1)
        self.assertEqual(booking_summary({"accountId": account["id"], "archiveState": "archived"})["count"], 2)
        self.assertEqual({item["id"] for item in list_pipeline({"accountId": account["id"]})["bookings"]}, {po_booking["id"]})
        self.assertEqual({item["id"] for item in get_account_360(account["id"])["bookings"]}, {po_booking["id"]})
        self.assertEqual(dashboard_booking(), Decimal(po_booking["amount"]))
        self.assertEqual(on_contact(), set())

        # Its owner still reads it, is refused every change, and does not restore it.
        frappe.set_user(self.other_sales)
        self.assertTrue(get_booking(upsell["id"])["archived"])
        self.assertEqual(listed({"archiveState": "archived"}), {upsell["id"], service["id"]})
        # Refused for the archive whichever version the edit carries: the current one or the older one from before.
        for version in (archived["modified"], upsell["modified"]):
            with self.assertRaises(CrmApiException) as edit:
                update_booking(upsell["id"], {"note": "Changed while archived"}, version)
            self.assertEqual((edit.exception.code, edit.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_BOOKING_EDIT))
        with self.assertRaises(CrmApiException) as completion:
            complete_service_booking(service["id"], get_booking(service["id"])["modified"])
        self.assertEqual((completion.exception.code, completion.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_BOOKING_EDIT))
        self.assertEqual(frappe.db.get_value("CRM Booking", service["id"], "status"), "Confirmed")
        with self.assertRaises(frappe.PermissionError):
            unarchive_booking(upsell["id"])

        frappe.set_user("Administrator")
        with patch.object(Document, "save", side_effect=AssertionError("the restore saves no document")):
            restored = unarchive_booking(upsell["id"])
        self.assertFalse(restored["archived"])
        self.assertNotIn("archivedAt", restored)
        self.assertNotIn("archivedBy", restored)
        self.assertEqual(
            frappe.db.get_value("CRM Booking", upsell["id"], ["archived", "archived_at", "archived_by"]), (0, None, None),
        )
        self.assertEqual(listed({}), {po_booking["id"], upsell["id"]})
        self.assertEqual(dashboard_booking(), before - Decimal(service["amount"]))
        self.assertEqual(on_contact(), {upsell["id"]})
        self.assertEqual(frappe.get_all("Comment", filters=comments, pluck="content", order_by="creation asc"), ["Archived", "Restored from the archive"])
        self.assertEqual(unarchive_booking(upsell["id"])["modified"], restored["modified"])
        # Back as it was, the Booking is edited again.
        frappe.set_user(self.other_sales)
        self.assertEqual(update_booking(upsell["id"], {"note": "Changed while archived"}, restored["modified"])["note"], "Changed while archived")

    def test_the_check_under_the_lock_catches_a_stale_first_read_whose_version_is_current(self):
        """The re-check under the Booking's lock is reached only by a request whose first read predates the archive
        while the version it sends is the archive's: staged here by handing the edit the snapshot from before."""

        account, _, contact, _ = self._records(self.other_sales, "StaleRead")
        upsell = create_booking(self._input(account, contact, None, self.other_sales))
        frappe.set_user("Administrator")
        archived = archive_booking(upsell["id"])

        before = frappe.get_doc("CRM Booking", upsell["id"])
        before.archived = 0
        with patch.object(booking_service, "_require_booking", return_value=before):
            # The owner's edit, and a Manager's correction of the PO date, each with the current version.
            for user, call in (
                (self.other_sales, lambda: update_booking(upsell["id"], {"note": "Late edit"}, archived["modified"])),
                ("Administrator", lambda: set_booking_actual_po_date(upsell["id"], {"actualPoDate": "2026-10-01", "reason": "Late"}, archived["modified"])),
            ):
                frappe.set_user(user)
                with self.assertRaises(CrmApiException) as refused:
                    call()
                self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_BOOKING_EDIT))
        self.assertEqual(frappe.db.get_value("CRM Booking", upsell["id"], "note"), "Priority delivery")
        self.assertNotEqual(str(frappe.db.get_value("CRM Booking", upsell["id"], "actual_po_date") or ""), "2026-10-01")

    def test_an_archived_order_takes_no_correction_and_no_conversion_and_a_completed_one_is_not_archived(self):
        account, site, contact, _ = self._records(self.other_sales, "ArchiveOrder")
        frappe.set_user("Administrator")
        engineer = self._user("crm-booking-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.other_sales)
        # A confirmed equipment order in USD: every Manager correction and the conversion apply to it.
        order = create_booking(self._input(account, contact, None, self.other_sales, currency="USD", amount="20000.00", amountCny="140000.00"))
        frappe.set_user("Administrator")
        archived = archive_booking(order["id"])
        self.assertTrue(archived["archived"])

        def refused(call) -> None:
            with self.assertRaises(CrmApiException) as refusal:
                call()
            self.assertEqual((refusal.exception.code, refusal.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_BOOKING_EDIT))

        refused(lambda: set_booking_actual_po_date(order["id"], {"actualPoDate": frappe.utils.today()}, archived["modified"]))
        refused(lambda: set_booking_amount_cny(order["id"], {"amountCny": "150000.00", "reason": "Rate"}, archived["modified"]))
        refused(lambda: convert_booking_to_installed_tool(order["id"], {
            "siteId": site["id"], "engineerOwner": engineer, "serial": f"ARCHIVED-{frappe.generate_hash(length=6)}",
            "model": "Model X", "location": "Fab 1", "salesOrder": "SO-REF", "contract": "CT-REF",
            "software": "1.0", "firmware": "2.0", "configuration": "Standard",
        }, archived["modified"]))
        row = frappe.db.get_value("CRM Booking", order["id"], ["status", "actual_po_date", "installed_tool"], as_dict=True)
        self.assertEqual((row.status, row.actual_po_date, row.installed_tool), ("Confirmed", None, None))
        self.assertEqual(frappe.db.sql("SELECT CAST(`amount_cny` AS CHAR) FROM `tabCRM Booking` WHERE `name` = %s", (order["id"],))[0][0], "140000.00")
        self.assertEqual(frappe.db.count("CRM Installed Tool", {"source_booking": order["id"]}), 0)

        # A completed Booking is the record of a delivered order: it is not archived (the delete would have taken this
        # one, which no Installed Tool or notice names; the archive refuses it all the same).
        frappe.set_user(self.other_sales)
        service = create_booking(self._input(account, contact, None, self.other_sales, bookingType="Service", equipment="Service plan"))
        completed = complete_service_booking(service["id"], service["modified"])
        self.assertEqual(completed["status"], "Completed")
        self.assertEqual(frappe.db.count("CRM Installed Tool", {"source_booking": service["id"]}), 0)
        self.assertEqual(frappe.db.count("CRM Notification Event", {
            "source_doctype": "CRM Booking", "source_name": service["id"],
        }), 0)
        named = frappe.get_doc("CRM Booking", service["id"])
        self.assertEqual(get_linked_docs(named) + get_dynamic_linked_docs(named), [])
        frappe.set_user("Administrator")
        with self.assertRaises(CrmApiException) as kept:
            archive_booking(service["id"])
        self.assertEqual((kept.exception.code, kept.exception.public_message), ("INVALID_TRANSITION", COMPLETED_BOOKING_ARCHIVE))
        self.assertEqual(frappe.db.get_value("CRM Booking", service["id"], "archived"), 0)

    def test_assignment_notification_failure_rolls_back_create_and_reassignment(self):
        account, _, contact, _ = self._records(self.sales, "NotifyRollback", stage=QUALIFIED_OPPORTUNITY)
        payload = self._input(account, contact, None, self.other_sales)
        frappe.set_user("Administrator")

        before = frappe.db.count("CRM Booking")
        with patch(
            "rayher_crm.services.bookings.create_notification",
            side_effect=RuntimeError("injected booking notification failure"),
        ), self.assertRaisesRegex(RuntimeError, "injected booking notification failure"):
            create_booking(payload)
        self.assertEqual(frappe.db.count("CRM Booking"), before)

        created = create_booking(self._input(account, contact, None, self.sales))
        try:
            assigned = frappe.get_all(
                "CRM Notification Event",
                filters={"source_doctype": "CRM Booking", "source_name": created["id"],
                         "recipient_user": self.sales, "title": "Booking assigned"},
                fields=["category", "route"], order_by="creation desc", limit=1,
            )[0]
            self.assertEqual(
                (assigned.category, assigned.route),
                ("Booking", f"/booking/{created['id']}"),
            )
            frappe.set_user(self.sales)
            self.assertEqual(get_booking(created["id"])["id"], created["id"])
            frappe.set_user("Administrator")
            with patch(
                "rayher_crm.services.bookings.create_notification",
                side_effect=RuntimeError("injected booking notification failure"),
            ), self.assertRaisesRegex(RuntimeError, "injected booking notification failure"):
                update_booking(created["id"], {"owner": self.other_sales}, created["modified"])
            self.assertEqual(
                frappe.db.get_value("CRM Booking", created["id"], "booking_owner"),
                self.sales,
            )
        finally:
            frappe.delete_doc("CRM Booking", created["id"], force=True, ignore_permissions=True)
    def test_service_booking_completes_without_installed_tool(self):
        account, _, contact, opportunity = self._records(self.sales, "Service")
        service = create_booking(self._input(
            account, contact, None, self.sales, bookingType="Service", status="Confirmed"
        ))
        self.assertEqual(service["bookingType"], "Service")
        completed = complete_service_booking(service["id"], service["modified"])
        self.assertEqual(completed["status"], "Completed")
        self.assertNotIn("installedToolId", completed)

        equipment = get_booking(opportunity["liveBooking"]["id"])
        with self.assertRaises(CrmApiException) as invalid_type:
            complete_service_booking(equipment["id"], equipment["modified"])
        self.assertEqual(invalid_type.exception.code, "INVALID_TRANSITION")

        # Completing the Service Booking of a Service Opportunity moves the Opportunity version.
        _, _, _, service_deal = self._records(self.sales, "ServiceDeal", sale_type="Service")
        service_booking = get_booking(service_deal["liveBooking"]["id"])
        self.assertEqual(service_booking["bookingType"], "Service")
        completed_deal = complete_service_booking(service_booking["id"], service_booking["modified"])
        self.assertEqual(completed_deal["status"], "Completed")
        self.assertNotEqual(get_strategy_opportunity(service_deal["id"])["modified"], service_deal["modified"])
