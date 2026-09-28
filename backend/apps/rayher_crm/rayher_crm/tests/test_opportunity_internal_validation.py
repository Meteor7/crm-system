from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import get_booking, update_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.installed_tools import convert_booking_to_installed_tool
from rayher_crm.services.opportunities import (
    confirm_po,
    create_strategy_opportunity,
    get_strategy_opportunity,
    mark_opportunity_lost,
    request_internal_validation,
    review_internal_validation,
    rollback_opportunity_stage,
)
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestOpportunityInternalValidation(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-validation-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-validation-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-validation-engineer@example.invalid", "CRM Engineer")
        self.manager = self._user("crm-validation-manager@example.invalid", "CRM Manager")
        self.reviewer = self._user("crm-validation-reviewer@example.invalid", "CRM Manager")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _records(self, suffix: str, sale_type: str = "New Equipment"):
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"Validation {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"validation-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Opportunity",
            "owner": self.sales, "amount": "880000.00", "intentScore": 70, "poDate": "2026-12-31",
            "toolType": "Inspection", "saleType": sale_type, "subRegion": "华东", "currency": "CNY",
            "originalAmount": "880000.00", "qualificationConfirmed": True,
        })
        return site, contact, opportunity

    def _quoted(self, suffix: str, sale_type: str = "New Equipment"):
        site, contact, opportunity = self._records(suffix, sale_type)
        return site, contact, advance_opportunity_fixture(opportunity, "quotation_sent")

    def _request(self, contact: dict) -> dict:
        return {
            "reason": "Long lead time", "expectedPoDate": "2026-11-30",
            "booking": {
                "primaryContactId": contact["id"], "equipment": "Inspection 3000", "quantity": 1,
                "ddl": "2027-03-31", "amount": "880000", "currency": "cny", "owner": self.sales,
                "note": "Start production before the PO",
            },
        }

    def _notified(self, recipient: str, validation_id: str, title: str) -> bool:
        return bool(frappe.db.exists("CRM Notification Event", {
            "recipient_user": recipient, "source_doctype": "CRM Opportunity Internal Validation",
            "source_name": validation_id, "title": title,
        }))

    def test_request_checks_stage_type_level_input_and_reviewers(self):
        _, contact, opportunity = self._records("IvGate")
        request = self._request(contact)
        rfq_validated = advance_opportunity_fixture(opportunity, "rfq_validated")
        with self.assertRaises(CrmApiException) as early:
            request_internal_validation(opportunity["id"], request, rfq_validated["modified"])
        self.assertEqual(early.exception.code, "INVALID_TRANSITION")

        quoted = advance_opportunity_fixture(rfq_validated, "quotation_sent")
        cases = [
            ({**request, "reason": " "}, "VALIDATION_ERROR"),
            ({**request, "expectedPoDate": ""}, "VALIDATION_ERROR"),
            ({key: value for key, value in request.items() if key != "booking"}, "VALIDATION_ERROR"),
            ({**request, "booking": {**request["booking"], "quantity": 0}}, "VALIDATION_ERROR"),
            ({**request, "booking": {**request["booking"], "owner": self.other_sales}}, "SCOPE_DENIED"),
        ]
        for payload, code in cases:
            with self.subTest(code=code, payload=payload), self.assertRaises(CrmApiException) as invalid:
                request_internal_validation(opportunity["id"], payload, quoted["modified"])
            self.assertEqual(invalid.exception.code, code)

        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            request_internal_validation(opportunity["id"], request, quoted["modified"])

        frappe.set_user(self.sales)
        with patch("rayher_crm.services.opportunities.active_crm_users", return_value=[]):
            with self.assertRaises(CrmApiException) as nobody:
                request_internal_validation(opportunity["id"], request, quoted["modified"])
        self.assertEqual(nobody.exception.code, "CONFLICT")

        requested = request_internal_validation(opportunity["id"], request, quoted["modified"])
        validation = requested["internalValidation"]
        self.assertEqual(
            (requested["stage"], validation["status"], validation["attemptNo"], validation["requestedBy"],
             validation["reason"], validation["expectedPoDate"]),
            ("quotation_sent", "pending", 1, self.sales, "Long lead time", "2026-11-30"),
        )
        self.assertEqual(
            (validation["booking"]["amount"], validation["booking"]["currency"], validation["booking"]["owner"]),
            ("880000.00", "CNY", self.sales),
        )
        self.assertIsNone(requested["liveBooking"])
        self.assertNotEqual(requested["modified"], quoted["modified"])
        self.assertIn("internalValidationRequested", {row["field"] for row in requested["history"]})
        self.assertTrue(self._notified(self.reviewer, validation["id"], "Internal validation requested"))
        self.assertFalse(self._notified(self.sales, validation["id"], "Internal validation requested"))

        with self.assertRaises(CrmApiException) as duplicate:
            request_internal_validation(opportunity["id"], request, requested["modified"])
        self.assertEqual(duplicate.exception.code, "CONFLICT")

        _, service_contact, service = self._quoted("IvService", sale_type="Service")
        with self.assertRaises(CrmApiException) as service_request:
            request_internal_validation(service["id"], self._request(service_contact), service["modified"])
        self.assertEqual(service_request.exception.code, "INVALID_TRANSITION")

    def test_managers_cannot_review_their_own_request_and_rejection_needs_a_comment(self):
        _, contact, quoted = self._quoted("IvReview")
        frappe.set_user(self.manager)
        requested = request_internal_validation(quoted["id"], self._request(contact), quoted["modified"])
        validation_id = requested["internalValidation"]["id"]
        with self.assertRaises(CrmApiException) as own:
            review_internal_validation(
                quoted["id"], {"validationId": validation_id, "decision": "approved"}, requested["modified"],
            )
        self.assertEqual(own.exception.code, "PERMISSION_DENIED")
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            review_internal_validation(
                quoted["id"], {"validationId": validation_id, "decision": "approved"}, requested["modified"],
            )

        frappe.set_user(self.reviewer)
        for payload, code in (
            ({"validationId": validation_id, "decision": "rejected", "comment": " "}, "VALIDATION_ERROR"),
            ({"validationId": validation_id, "decision": "maybe"}, "VALIDATION_ERROR"),
            ({"validationId": "CRM-VAL-99999", "decision": "approved"}, "NOT_FOUND"),
        ):
            with self.subTest(code=code, payload=payload), self.assertRaises(CrmApiException) as invalid:
                review_internal_validation(quoted["id"], payload, requested["modified"])
            self.assertEqual(invalid.exception.code, code)

        rejected = review_internal_validation(quoted["id"], {
            "validationId": validation_id, "decision": "rejected", "comment": "Wait for the PO",
        }, requested["modified"])
        decision = rejected["internalValidation"]
        self.assertEqual(
            (rejected["stage"], decision["status"], decision["decidedBy"], decision["decisionComment"], rejected["liveBooking"]),
            ("quotation_sent", "rejected", self.reviewer, "Wait for the PO", None),
        )
        self.assertTrue(self._notified(self.manager, validation_id, "Internal validation rejected"))
        self.assertTrue(self._notified(self.sales, validation_id, "Internal validation rejected"))
        with self.assertRaises(CrmApiException) as decided:
            review_internal_validation(
                quoted["id"], {"validationId": validation_id, "decision": "approved"}, rejected["modified"],
            )
        self.assertEqual(decided.exception.code, "INVALID_TRANSITION")

        frappe.set_user(self.sales)
        again = request_internal_validation(quoted["id"], self._request(contact), rejected["modified"])
        self.assertEqual((again["internalValidation"]["attemptNo"], again["internalValidation"]["status"]), (2, "pending"))

    def test_approval_creates_a_pending_booking_that_cannot_be_installed(self):
        site, contact, quoted = self._quoted("IvApprove")
        requested = request_internal_validation(quoted["id"], self._request(contact), quoted["modified"])
        frappe.set_user(self.reviewer)
        approved = review_internal_validation(quoted["id"], {
            "validationId": requested["internalValidation"]["id"], "decision": "approved", "comment": "Go ahead",
        }, requested["modified"])
        validation = approved["internalValidation"]
        booking_id = approved["liveBooking"]["id"]
        self.assertEqual(
            (approved["stage"], validation["status"], validation["bookingId"], approved["liveBooking"]["status"]),
            ("internal_validation", "approved", booking_id, "Pending"),
        )
        latest = approved["stageHistory"][0]
        self.assertEqual(
            (latest["from"], latest["to"], latest["source"], latest["event"],
             latest["referenceDoctype"], latest["referenceName"], latest["actor"]),
            ("quotation_sent", "internal_validation", "approval", "internal_validation_approved",
             "CRM Opportunity Internal Validation", validation["id"], self.reviewer),
        )
        self.assertTrue(self._notified(self.sales, validation["id"], "Internal validation approved"))
        booking = frappe.get_doc("CRM Booking", booking_id)
        self.assertEqual(
            (booking.source, booking.source_opportunity, booking.live_source_opportunity, booking.booking_type,
             booking.booking_owner, booking.status),
            ("Opportunity", quoted["id"], quoted["id"], "Equipment", self.sales, "Pending"),
        )
        with self.assertRaises(CrmApiException) as not_confirmed:
            convert_booking_to_installed_tool(
                booking_id, {"siteId": site["id"], "engineerOwner": self.engineer, "model": "Inspection 3000"},
                get_booking(booking_id)["modified"],
            )
        self.assertEqual(not_confirmed.exception.code, "INVALID_TRANSITION")

        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as booking_live:
            mark_opportunity_lost(quoted["id"], {"lostReason": "Customer cancelled"}, approved["modified"])
        self.assertEqual(booking_live.exception.code, "CONFLICT")
        update_booking(booking_id, {"status": "Cancelled"}, get_booking(booking_id)["modified"])
        lost = mark_opportunity_lost(quoted["id"], {"lostReason": "Customer cancelled"}, approved["modified"])
        self.assertEqual((lost["stage"], lost["lostAtStage"]), ("lost", "internal_validation"))

        frappe.set_user(self.manager)
        reopened = rollback_opportunity_stage(quoted["id"], "internal_validation", "Customer is back", lost["modified"])
        self.assertEqual((reopened["stage"], reopened["liveBooking"]), ("internal_validation", None))

    def test_leaving_quotation_sent_cancels_a_pending_request(self):
        _, contact, quoted = self._quoted("IvCancel")
        requested = request_internal_validation(quoted["id"], self._request(contact), quoted["modified"])
        frappe.set_user(self.manager)
        rolled_back = rollback_opportunity_stage(
            quoted["id"], "rfq_validated", "Quotation to be revised", requested["modified"],
        )
        cancelled = rolled_back["internalValidation"]
        self.assertEqual(
            (cancelled["status"], cancelled["cancelledBy"], cancelled["cancelReason"]),
            ("cancelled", self.manager, "Opportunity rolled back to rfq_validated."),
        )

        frappe.set_user(self.sales)
        requoted = advance_opportunity_fixture(rolled_back, "quotation_sent")
        second = request_internal_validation(quoted["id"], self._request(contact), requoted["modified"])
        lost = mark_opportunity_lost(quoted["id"], {"lostReason": "Budget cut"}, second["modified"])
        self.assertEqual((lost["internalValidation"]["attemptNo"], lost["internalValidation"]["status"]), (2, "cancelled"))

        _, other_contact, other = self._quoted("IvCancelByPo")
        pending = request_internal_validation(other["id"], self._request(other_contact), other["modified"])
        received = confirm_po(other["id"], {"booking": self._request(other_contact)["booking"]}, pending["modified"])
        self.assertEqual((received["stage"], received["internalValidation"]["status"]), ("po_received", "cancelled"))

    def test_approval_revalidates_the_booking_draft(self):
        _, contact, quoted = self._quoted("IvStale")
        requested = request_internal_validation(quoted["id"], self._request(contact), quoted["modified"])
        frappe.db.set_value("Contact", contact["id"], "custom_crm_status", "Archived", update_modified=False)

        frappe.set_user(self.reviewer)
        with self.assertRaises(CrmApiException) as stale:
            review_internal_validation(quoted["id"], {
                "validationId": requested["internalValidation"]["id"], "decision": "approved",
            }, requested["modified"])
        self.assertEqual(stale.exception.code, "VALIDATION_ERROR")
        current = get_strategy_opportunity(quoted["id"])
        self.assertEqual(
            (current["stage"], current["internalValidation"]["status"], current["liveBooking"]),
            ("quotation_sent", "pending", None),
        )
