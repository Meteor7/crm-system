from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import create_booking, get_booking, update_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import (
    confirm_po,
    create_strategy_opportunity,
    get_strategy_opportunity,
    mark_opportunity_lost,
    request_internal_validation,
    review_internal_validation,
    rollback_opportunity_stage,
    update_strategy_opportunity,
)
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestOpportunityPoConfirmation(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-po-sales@example.invalid", "CRM Sales")
        self.manager = self._user("crm-po-manager@example.invalid", "CRM Manager")
        self.reviewer = self._user("crm-po-reviewer@example.invalid", "CRM Manager")
        self.other_sales = self._user("crm-po-other-sales@example.invalid", "CRM Sales")

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

    def _quoted(self, suffix: str):
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"PO {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"po-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Opportunity",
            "owner": self.sales, "amount": "880000.00", "intentScore": 70, "poDate": "2026-12-31",
            "toolType": "Inspection", "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "originalAmount": "880000.00", "qualificationConfirmed": True,
        })
        return account, contact, advance_opportunity_fixture(opportunity, "quotation_sent")

    def _booking(self, contact: dict, **overrides) -> dict:
        draft = {
            "primaryContactId": contact["id"], "equipment": "Inspection 3000", "quantity": 1,
            "ddl": "2027-03-31", "amount": "880000.00", "currency": "CNY", "owner": self.sales,
            "note": "PO 4500012345",
        }
        draft.update(overrides)
        return draft

    def _approved_validation(self, opportunity: dict, contact: dict) -> dict:
        frappe.set_user(self.sales)
        requested = request_internal_validation(opportunity["id"], {
            "reason": "Long lead time", "expectedPoDate": "2026-11-30", "booking": self._booking(contact),
        }, opportunity["modified"])
        frappe.set_user(self.reviewer)
        return review_internal_validation(opportunity["id"], {
            "validationId": requested["internalValidation"]["id"], "decision": "approved",
        }, requested["modified"])

    def _booking_count(self, opportunity_id: str) -> int:
        return frappe.db.count("CRM Booking", {"source_opportunity": opportunity_id})

    def test_po_from_quotation_sent_creates_a_confirmed_booking(self):
        account, contact, quoted = self._quoted("PoDirect")
        with self.assertRaises(CrmApiException) as stale:
            confirm_po(quoted["id"], {"booking": self._booking(contact)}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        for payload in ({"booking": self._booking(contact, quantity=0)}, {}):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as invalid:
                confirm_po(quoted["id"], payload, quoted["modified"])
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as manager_owner:
            confirm_po(quoted["id"], {"booking": self._booking(contact, owner="")}, quoted["modified"])
        self.assertEqual(manager_owner.exception.code, "VALIDATION_ERROR")

        frappe.set_user(self.sales)
        frappe.db.set_value("CRM Opportunity", quoted["id"], "probability_level", "", update_modified=False)
        with self.assertRaises(CrmApiException) as no_level:
            confirm_po(quoted["id"], {"booking": self._booking(contact)}, quoted["modified"])
        self.assertEqual(no_level.exception.field_errors, {"probabilityLevel": "Required"})
        frappe.db.set_value("CRM Opportunity", quoted["id"], "probability_level", "committed", update_modified=False)
        self.assertEqual(
            (get_strategy_opportunity(quoted["id"])["stage"], self._booking_count(quoted["id"])), ("quotation_sent", 0),
        )

        received = confirm_po(quoted["id"], {"booking": self._booking(contact)}, quoted["modified"])
        booking_id = received["liveBooking"]["id"]
        self.assertEqual(received["stage"], "po_received")
        self.assertEqual(
            {key: received["liveBooking"][key] for key in ("status", "amount", "currency", "owner", "quantity")},
            {"status": "Confirmed", "amount": "880000.00", "currency": "CNY", "owner": self.sales, "quantity": 1},
        )
        latest = received["stageHistory"][0]
        self.assertEqual(
            (latest["from"], latest["to"], latest["source"], latest["event"], latest["referenceDoctype"], latest["referenceName"]),
            ("quotation_sent", "po_received", "manual", "po_confirmed", "CRM Booking", booking_id),
        )
        self.assertIn("poConfirmed", {row["field"] for row in received["history"]})
        booking = get_booking(booking_id)
        self.assertEqual(
            (booking["source"], booking["sourceOpportunityId"], booking["bookingType"], booking["accountId"], booking["note"]),
            ("Opportunity", quoted["id"], "Equipment", account["id"], "PO 4500012345"),
        )

        with self.assertRaises(CrmApiException) as twice:
            confirm_po(quoted["id"], {"booking": self._booking(contact)}, received["modified"])
        self.assertEqual(twice.exception.code, "CONFLICT")
        with self.assertRaises(CrmApiException) as lost_after_po:
            mark_opportunity_lost(quoted["id"], {"lostReason": "Too late"}, received["modified"])
        self.assertEqual(lost_after_po.exception.code, "INVALID_TRANSITION")
        with self.assertRaises(CrmApiException) as level_frozen:
            update_strategy_opportunity(quoted["id"], {"probabilityLevel": "upside"}, received["modified"])
        self.assertEqual(level_frozen.exception.code, "INVALID_TRANSITION")
        with self.assertRaises(CrmApiException) as sale_type_locked:
            update_strategy_opportunity(quoted["id"], {"saleType": "Repeat Order"}, received["modified"])
        self.assertEqual(sale_type_locked.exception.code, "CONFLICT")
        renamed = update_strategy_opportunity(quoted["id"], {"title": "Direct PO"}, received["modified"])
        self.assertEqual(renamed["title"], "Direct PO")

        with self.assertRaises(CrmApiException) as manual_opportunity_booking:
            create_booking({
                "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Inspection 3000",
                "quantity": 1, "ddl": "2027-03-31", "amount": "1.00", "currency": "CNY", "status": "Confirmed",
                "owner": self.sales, "source": "Opportunity", "sourceOpportunityId": quoted["id"],
            })
        self.assertEqual(manual_opportunity_booking.exception.code, "INVALID_TRANSITION")
        upsell = create_booking({
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Spare parts",
            "quantity": 1, "ddl": "2027-03-31", "amount": "1000.00", "currency": "CNY", "status": "Confirmed",
            "owner": self.sales, "source": "Upsell",
        })
        with self.assertRaises(CrmApiException) as relabelled:
            update_booking(
                upsell["id"], {"source": "Opportunity", "sourceOpportunityId": quoted["id"]}, upsell["modified"],
            )
        self.assertEqual(relabelled.exception.code, "INVALID_TRANSITION")
        for payload in ({"status": "Pending"}, {"sourceOpportunityId": ""}, {"source": "Upsell"}, {"bookingType": "Service"}):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as locked:
                update_booking(booking_id, payload, booking["modified"])
            self.assertEqual(locked.exception.code, "INVALID_TRANSITION")
        noted = update_booking(booking_id, {"note": "PO 4500012345 rev A"}, booking["modified"])
        cancelled = update_booking(booking_id, {"status": "Cancelled"}, noted["modified"])
        self.assertEqual(cancelled["status"], "Cancelled")
        with self.assertRaises(CrmApiException) as restored:
            update_booking(booking_id, {"status": "Confirmed"}, cancelled["modified"])
        self.assertEqual(restored.exception.code, "INVALID_TRANSITION")

        after_cancel = get_strategy_opportunity(quoted["id"])
        self.assertIsNone(after_cancel["liveBooking"])
        replaced = confirm_po(
            quoted["id"], {"booking": self._booking(contact, amount="860000.00")}, after_cancel["modified"],
        )
        self.assertEqual((replaced["stage"], replaced["stageHistory"]), ("po_received", after_cancel["stageHistory"]))
        self.assertNotEqual(replaced["liveBooking"]["id"], booking_id)
        self.assertEqual(
            (replaced["liveBooking"]["status"], replaced["liveBooking"]["amount"]), ("Confirmed", "860000.00"),
        )
        self.assertIn("bookingReplaced", {row["field"] for row in replaced["history"]})
        self.assertEqual(self._booking_count(quoted["id"]), 2)

    def test_po_after_internal_validation_confirms_the_same_booking(self):
        _, contact, quoted = self._quoted("PoValidated")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        self.assertEqual((approved["stage"], approved["liveBooking"]["status"]), ("internal_validation", "Pending"))

        frappe.set_user(self.sales)
        received = confirm_po(quoted["id"], {
            "booking": self._booking(contact, amount="900000.00", note="PO arrived"),
            "expectedBookingModified": approved["liveBooking"]["modified"],
        }, approved["modified"])
        self.assertEqual(
            (received["stage"], received["liveBooking"]["id"], received["liveBooking"]["status"], received["liveBooking"]["amount"]),
            ("po_received", pending_id, "Confirmed", "900000.00"),
        )
        self.assertEqual(received["stageHistory"][0]["from"], "internal_validation")
        self.assertEqual(self._booking_count(quoted["id"]), 1)

        frappe.set_user(self.manager)
        back_to_validation = rollback_opportunity_stage(
            quoted["id"], "internal_validation", "Customer withdrew the PO", received["modified"],
        )
        self.assertEqual(
            (back_to_validation["stage"], back_to_validation["liveBooking"]["id"], back_to_validation["liveBooking"]["status"]),
            ("internal_validation", pending_id, "Pending"),
        )
        with self.assertRaises(CrmApiException) as booking_still_live:
            rollback_opportunity_stage(quoted["id"], "quotation_sent", "Stop production", back_to_validation["modified"])
        self.assertEqual(booking_still_live.exception.code, "CONFLICT")

        update_booking(pending_id, {"status": "Cancelled"}, get_booking(pending_id)["modified"])
        quoted_again = rollback_opportunity_stage(
            quoted["id"], "quotation_sent", "Stop production", back_to_validation["modified"],
        )
        self.assertEqual((quoted_again["stage"], quoted_again["liveBooking"]), ("quotation_sent", None))

        frappe.set_user(self.sales)
        direct = confirm_po(quoted["id"], {"booking": self._booking(contact)}, quoted_again["modified"])
        self.assertNotEqual(direct["liveBooking"]["id"], pending_id)
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as not_from_validation:
            rollback_opportunity_stage(quoted["id"], "internal_validation", "Restore production", direct["modified"])
        self.assertEqual(not_from_validation.exception.code, "INVALID_TRANSITION")

    def test_pending_booking_edits_reach_the_po_confirmation_summary(self):
        account, contact, quoted = self._quoted("PoEdited")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        self.assertEqual(
            (approved["liveBooking"]["primaryContactId"], approved["liveBooking"]["note"]),
            (contact["id"], "PO 4500012345"),
        )

        frappe.set_user(self.sales)
        buyer = create_contact({
            "accountId": account["id"], "siteId": contact["siteId"], "name": "PoEdited Buyer",
            "title": "Buyer", "department": "Procurement", "phone": "13800000002",
            "email": "po-poedited-buyer@example.invalid", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        update_booking(
            pending_id, {"primaryContactId": buyer["id"], "note": "Ship to the new fab"}, get_booking(pending_id)["modified"],
        )
        # The PO confirmation form is prefilled from the live Booking summary, so the edited contact and
        # note must be in it; the approval draft still holds the original values.
        current = get_strategy_opportunity(quoted["id"])
        self.assertEqual(
            (current["liveBooking"]["primaryContactId"], current["liveBooking"]["note"]),
            (buyer["id"], "Ship to the new fab"),
        )
        self.assertEqual(current["internalValidation"]["booking"]["primaryContactId"], contact["id"])

        prefilled = {
            key: current["liveBooking"][key]
            for key in ("primaryContactId", "equipment", "quantity", "ddl", "amount", "currency", "owner", "note")
        }

        # The confirmation carries the Booking version the form was prefilled from, so an edit made in the
        # meantime (another tab, another user) is not written over.
        for payload in ({"booking": prefilled}, {"booking": prefilled, "expectedBookingModified": " "}):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as missing:
                confirm_po(quoted["id"], payload, current["modified"])
            self.assertEqual(missing.exception.code, "VALIDATION_ERROR")
        update_booking(pending_id, {"note": "Ship to the new fab, dock 3"}, get_booking(pending_id)["modified"])
        with self.assertRaises(CrmApiException) as stale:
            confirm_po(quoted["id"], {
                "booking": prefilled, "expectedBookingModified": current["liveBooking"]["modified"],
            }, current["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        self.assertEqual(get_booking(pending_id)["note"], "Ship to the new fab, dock 3")

        current = get_strategy_opportunity(quoted["id"])
        prefilled["note"] = current["liveBooking"]["note"]
        received = confirm_po(quoted["id"], {
            "booking": prefilled, "expectedBookingModified": current["liveBooking"]["modified"],
        }, current["modified"])
        booking = get_booking(pending_id)
        self.assertEqual(
            (received["stage"], booking["status"], booking["primaryContactId"], booking["note"]),
            ("po_received", "Confirmed", buyer["id"], "Ship to the new fab, dock 3"),
        )

    def test_po_confirmation_needs_the_pending_booking_in_scope(self):
        _, contact, quoted = self._quoted("PoHidden")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        frappe.set_user(self.manager)
        reassigned = update_booking(pending_id, {"owner": self.other_sales}, get_booking(pending_id)["modified"])

        # A Sales user only reads Bookings assigned to them, so the Opportunity owner now gets a summary
        # without details and must not be able to confirm the approval draft over the other user's Booking.
        frappe.set_user(self.sales)
        hidden = get_strategy_opportunity(quoted["id"])
        self.assertEqual(hidden["liveBooking"], {"id": pending_id, "status": "Pending"})
        with self.assertRaises(CrmApiException) as denied:
            confirm_po(quoted["id"], {
                "booking": self._booking(contact), "expectedBookingModified": reassigned["modified"],
            }, hidden["modified"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        self.assertEqual(
            frappe.db.get_value("CRM Booking", pending_id, ["status", "booking_owner"], as_dict=True),
            {"status": "Pending", "booking_owner": self.other_sales},
        )

        frappe.set_user(self.manager)
        received = confirm_po(quoted["id"], {
            "booking": self._booking(contact, owner=self.other_sales), "expectedBookingModified": reassigned["modified"],
        }, hidden["modified"])
        self.assertEqual(
            (received["stage"], received["liveBooking"]["status"], received["liveBooking"]["owner"]),
            ("po_received", "Confirmed", self.other_sales),
        )

    def test_internal_validation_keeps_the_sale_type_after_its_booking_is_cancelled(self):
        _, contact, quoted = self._quoted("PoKept")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as live:
            update_strategy_opportunity(quoted["id"], {"saleType": "Service"}, approved["modified"])
        self.assertEqual(live.exception.code, "CONFLICT")

        update_booking(pending_id, {"status": "Cancelled"}, get_booking(pending_id)["modified"])
        # The approval was given for an equipment deal and the stage stands until a Manager rolls it
        # back, so the sale type stays put even though no Booking is live any more.
        current = get_strategy_opportunity(quoted["id"])
        self.assertEqual((current["stage"], current["liveBooking"]), ("internal_validation", None))
        with self.assertRaises(CrmApiException) as kept:
            update_strategy_opportunity(quoted["id"], {"saleType": "Service"}, current["modified"])
        self.assertEqual(kept.exception.code, "CONFLICT")
        self.assertEqual(frappe.db.get_value("CRM Opportunity", quoted["id"], "sale_type"), "New Equipment")

        frappe.set_user(self.manager)
        rolled = rollback_opportunity_stage(
            quoted["id"], "quotation_sent", "Switching to a service deal", current["modified"],
        )
        frappe.set_user(self.sales)
        switched = update_strategy_opportunity(quoted["id"], {"saleType": "Service"}, rolled["modified"])
        self.assertEqual((switched["stage"], switched["saleType"]), ("quotation_sent", "Service"))

    def test_rollback_to_internal_validation_needs_the_approved_equipment_deal(self):
        # Once the approval's Booking is cancelled the sale type can change at lost or at po_received;
        # neither path may carry a Service Opportunity back under the equipment approval.
        _, contact, quoted = self._quoted("PoReopen")
        approved = self._approved_validation(quoted, contact)
        frappe.set_user(self.sales)
        update_booking(approved["liveBooking"]["id"], {"status": "Cancelled"}, get_booking(approved["liveBooking"]["id"])["modified"])
        lost = mark_opportunity_lost(quoted["id"], {"lostReason": "Budget cut"}, get_strategy_opportunity(quoted["id"])["modified"])
        self.assertEqual(lost["lostAtStage"], "internal_validation")
        switched = update_strategy_opportunity(quoted["id"], {"saleType": "Service"}, lost["modified"])
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as reopen:
            rollback_opportunity_stage(quoted["id"], "internal_validation", "Customer is back", switched["modified"])
        self.assertEqual(reopen.exception.code, "INVALID_TRANSITION")
        reopened = rollback_opportunity_stage(quoted["id"], "quotation_sent", "Customer is back", switched["modified"])
        self.assertEqual((reopened["stage"], reopened["saleType"]), ("quotation_sent", "Service"))

        _, contact, quoted = self._quoted("PoRollback")
        approved = self._approved_validation(quoted, contact)
        frappe.set_user(self.sales)
        received = confirm_po(quoted["id"], {
            "booking": self._booking(contact), "expectedBookingModified": approved["liveBooking"]["modified"],
        }, approved["modified"])
        booking_id = received["liveBooking"]["id"]
        update_booking(booking_id, {"status": "Cancelled"}, get_booking(booking_id)["modified"])
        switched = update_strategy_opportunity(quoted["id"], {"saleType": "Service"}, received["modified"])
        self.assertEqual((switched["stage"], switched["liveBooking"]), ("po_received", None))
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as back:
            rollback_opportunity_stage(quoted["id"], "internal_validation", "PO withdrawn", switched["modified"])
        self.assertEqual(back.exception.code, "INVALID_TRANSITION")
        quoted_again = rollback_opportunity_stage(quoted["id"], "quotation_sent", "PO withdrawn", switched["modified"])
        self.assertEqual((quoted_again["stage"], quoted_again["saleType"]), ("quotation_sent", "Service"))

    def test_cancelled_validation_booking_is_replaced_and_completed_booking_blocks_rollback(self):
        _, contact, quoted = self._quoted("PoReplaced")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        old_input = {
            "booking": self._booking(contact),
            "expectedBookingModified": approved["liveBooking"]["modified"],
        }
        update_booking(pending_id, {"status": "Cancelled"}, get_booking(pending_id)["modified"])

        frappe.set_user(self.sales)
        current = get_strategy_opportunity(quoted["id"])
        self.assertEqual((current["modified"], current["liveBooking"]), (approved["modified"], None))
        # The old form was confirming this Pending Booking, not creating its replacement.
        with self.assertRaises(CrmApiException) as cancelled:
            confirm_po(quoted["id"], old_input, approved["modified"])
        self.assertEqual(cancelled.exception.code, "VERSION_CONFLICT")
        unchanged = get_strategy_opportunity(quoted["id"])
        self.assertEqual((unchanged["stage"], unchanged["modified"]), ("internal_validation", current["modified"]))
        self.assertEqual(unchanged["stageHistory"], current["stageHistory"])
        self.assertEqual(self._booking_count(quoted["id"]), 1)
        self.assertEqual(get_booking(pending_id)["status"], "Cancelled")

        # A refreshed form has no Pending Booking version and may explicitly create a replacement.
        received = confirm_po(quoted["id"], {"booking": self._booking(contact)}, unchanged["modified"])
        self.assertEqual(received["stage"], "po_received")
        self.assertEqual((received["liveBooking"]["status"], self._booking_count(quoted["id"])), ("Confirmed", 2))
        self.assertNotEqual(received["liveBooking"]["id"], pending_id)
        self.assertEqual(frappe.db.get_value("CRM Booking", pending_id, "status"), "Cancelled")

        frappe.db.set_value("CRM Booking", received["liveBooking"]["id"], "status", "Completed", update_modified=False)
        frappe.set_user(self.manager)
        for target in ("internal_validation", "quotation_sent"):
            with self.subTest(target=target), self.assertRaises(CrmApiException) as completed:
                rollback_opportunity_stage(quoted["id"], target, "Already installed", received["modified"])
            self.assertEqual(completed.exception.code, "CONFLICT")
