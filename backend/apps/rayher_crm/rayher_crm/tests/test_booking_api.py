from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import complete_service_booking, create_booking, delete_booking, get_booking, list_bookings, update_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import confirm_po, create_strategy_opportunity, get_strategy_opportunity
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
        with self.assertRaises(CrmApiException) as mismatch:
            create_booking(self._input(account, foreign_contact, None, self.sales))
        self.assertEqual(mismatch.exception.code, "CONFLICT")

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

    def test_only_manager_can_delete_booking(self):
        account, _, contact, opportunity = self._records(self.other_sales, "Delete")
        po_booking = get_booking(opportunity["liveBooking"]["id"])
        frappe.set_user(self.other_sales)
        upsell = create_booking(self._input(account, contact, None, self.other_sales))

        frappe.set_user(self.sales)
        for booking_id in (upsell["id"], po_booking["id"]):
            with self.assertRaises(frappe.PermissionError):
                delete_booking(booking_id)
            self.assertTrue(frappe.db.exists("CRM Booking", booking_id))

        frappe.set_user("Administrator")
        # The PO record behind a po_received Opportunity can only be cancelled, never deleted.
        with self.assertRaises(CrmApiException) as protected:
            delete_booking(po_booking["id"])
        # BOOKING_SOURCE_INVALID is published as the INVALID_TRANSITION contract code.
        self.assertEqual(protected.exception.code, "INVALID_TRANSITION")
        self.assertTrue(frappe.db.exists("CRM Booking", po_booking["id"]))
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["liveBooking"]["id"], po_booking["id"])

        self.assertEqual(delete_booking(upsell["id"]), {"id": upsell["id"], "status": "Deleted"})
        self.assertFalse(frappe.db.exists("CRM Booking", upsell["id"]))

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
