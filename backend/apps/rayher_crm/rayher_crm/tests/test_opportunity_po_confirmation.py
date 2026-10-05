from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import (
    create_booking,
    get_booking,
    list_bookings,
    set_booking_actual_po_date,
    update_booking,
)
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
        self.po_date = str(frappe.utils.add_days(frappe.utils.today(), -3))

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
            "probabilityLevel": "pipeline",
            "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Opportunity",
            "owner": self.sales, "amount": "880000.00", "intentScore": 70, "poDate": "2026-12-31",
            "toolType": "Inspection", "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "originalAmount": "880000.00", "amountCny": "880000.00", "qualificationConfirmed": True,
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

    def _po(self, contact: dict, **overrides) -> dict:
        return {"booking": self._booking(contact, **overrides), "actualPoDate": self.po_date}

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
            confirm_po(quoted["id"], self._po(contact), "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        for payload in (self._po(contact, quantity=0), {}):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as invalid:
                confirm_po(quoted["id"], payload, quoted["modified"])
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as manager_owner:
            confirm_po(quoted["id"], self._po(contact, owner=""), quoted["modified"])
        self.assertEqual(manager_owner.exception.code, "VALIDATION_ERROR")

        frappe.set_user(self.sales)
        frappe.db.set_value("CRM Opportunity", quoted["id"], "probability_level", "", update_modified=False)
        with self.assertRaises(CrmApiException) as no_level:
            confirm_po(quoted["id"], self._po(contact), quoted["modified"])
        self.assertEqual(no_level.exception.field_errors, {"probabilityLevel": "Required"})
        frappe.db.set_value("CRM Opportunity", quoted["id"], "probability_level", "committed", update_modified=False)
        self.assertEqual(
            (get_strategy_opportunity(quoted["id"])["stage"], self._booking_count(quoted["id"])), ("quotation_sent", 0),
        )

        received = confirm_po(quoted["id"], self._po(contact), quoted["modified"])
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
            confirm_po(quoted["id"], self._po(contact), received["modified"])
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
            quoted["id"], self._po(contact, amount="860000.00"), after_cancel["modified"],
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
            "actualPoDate": self.po_date,
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
        # The cancellation moved the Opportunity version, so the rollback needs the current one.
        quoted_again = rollback_opportunity_stage(
            quoted["id"], "quotation_sent", "Stop production", get_strategy_opportunity(quoted["id"])["modified"],
        )
        self.assertEqual((quoted_again["stage"], quoted_again["liveBooking"]), ("quotation_sent", None))

        frappe.set_user(self.sales)
        direct = confirm_po(quoted["id"], self._po(contact), quoted_again["modified"])
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
        for payload in (
            {"booking": prefilled, "actualPoDate": self.po_date},
            {"booking": prefilled, "expectedBookingModified": " ", "actualPoDate": self.po_date},
        ):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as missing:
                confirm_po(quoted["id"], payload, current["modified"])
            self.assertEqual(missing.exception.code, "VALIDATION_ERROR")
        update_booking(pending_id, {"note": "Ship to the new fab, dock 3"}, get_booking(pending_id)["modified"])
        with self.assertRaises(CrmApiException) as stale:
            confirm_po(quoted["id"], {
                "booking": prefilled, "expectedBookingModified": current["liveBooking"]["modified"],
                "actualPoDate": self.po_date,
            }, current["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        self.assertEqual(get_booking(pending_id)["note"], "Ship to the new fab, dock 3")

        current = get_strategy_opportunity(quoted["id"])
        prefilled["note"] = current["liveBooking"]["note"]
        received = confirm_po(quoted["id"], {
            "booking": prefilled, "expectedBookingModified": current["liveBooking"]["modified"],
            "actualPoDate": self.po_date,
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
        # A new Booking owner needs Account access, while the original owner must
        # retain Opportunity access so this test exercises its redacted summary.
        account = frappe.db.get_value("CRM Booking", pending_id, "account")
        frappe.db.set_value("Customer", account, "custom_crm_visibility", "Public")
        reassigned = update_booking(pending_id, {"owner": self.other_sales}, get_booking(pending_id)["modified"])
        frappe.set_user(self.other_sales)
        self.assertEqual(get_booking(pending_id)["owner"], self.other_sales)

        # A Sales user only reads Bookings assigned to them, so the Opportunity owner now gets a summary
        # without details and must not be able to confirm the approval draft over the other user's Booking.
        frappe.set_user(self.sales)
        hidden = get_strategy_opportunity(quoted["id"])
        self.assertEqual(hidden["liveBooking"], {"id": pending_id, "status": "Pending"})
        with self.assertRaises(CrmApiException) as denied:
            confirm_po(quoted["id"], {
                "booking": self._booking(contact), "expectedBookingModified": reassigned["modified"],
                "actualPoDate": self.po_date,
            }, hidden["modified"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        self.assertEqual(
            frappe.db.get_value("CRM Booking", pending_id, ["status", "booking_owner"], as_dict=True),
            {"status": "Pending", "booking_owner": self.other_sales},
        )

        frappe.set_user(self.manager)
        received = confirm_po(quoted["id"], {
            "booking": self._booking(contact, owner=self.other_sales), "expectedBookingModified": reassigned["modified"],
            "actualPoDate": self.po_date,
        }, hidden["modified"])
        self.assertEqual(
            (received["stage"], received["liveBooking"]["status"], received["liveBooking"]["owner"]),
            ("po_received", "Confirmed", self.other_sales),
        )

    def test_confirmation_notification_storage_failure_rolls_back(self):
        _, contact, quoted = self._quoted("PoNoticeRollback")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        frappe.set_user(self.manager)
        account = frappe.db.get_value("CRM Booking", pending_id, "account")
        frappe.db.set_value("Customer", account, "custom_crm_visibility", "Public")
        reassigned = update_booking(
            pending_id, {"owner": self.other_sales}, approved["liveBooking"]["modified"],
        )
        opportunity = get_strategy_opportunity(quoted["id"])
        with patch(
            "rayher_crm.services.notifications.create_notification",
            side_effect=RuntimeError("notification storage failed"),
        ), self.assertRaisesRegex(RuntimeError, "notification storage failed"):
            confirm_po(quoted["id"], {
                "booking": self._booking(contact, owner=self.other_sales),
                "expectedBookingModified": reassigned["modified"],
                "actualPoDate": self.po_date,
            }, opportunity["modified"])
        self.assertEqual(
            frappe.db.get_value("CRM Booking", pending_id, "status"),
            "Pending",
        )
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", quoted["id"], "stage"),
            "internal_validation",
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
            "actualPoDate": self.po_date,
        }, approved["modified"])
        booking_id = received["liveBooking"]["id"]
        update_booking(booking_id, {"status": "Cancelled"}, get_booking(booking_id)["modified"])
        switched = update_strategy_opportunity(
            quoted["id"], {"saleType": "Service"}, get_strategy_opportunity(quoted["id"])["modified"],
        )
        self.assertEqual((switched["stage"], switched["liveBooking"]), ("po_received", None))
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as back:
            rollback_opportunity_stage(quoted["id"], "internal_validation", "PO withdrawn", switched["modified"])
        self.assertEqual(back.exception.code, "INVALID_TRANSITION")
        quoted_again = rollback_opportunity_stage(quoted["id"], "quotation_sent", "PO withdrawn", switched["modified"])
        self.assertEqual((quoted_again["stage"], quoted_again["saleType"]), ("quotation_sent", "Service"))

    def test_a_change_to_the_opportunity_booking_moves_the_opportunity_version(self):
        # The live Booking is part of the Opportunity's state, so editing, reassigning or cancelling it
        # moves the Opportunity version: an action prepared on the older view answers VERSION_CONFLICT
        # even when it carries no Booking version at all.
        _, contact, quoted = self._quoted("PoVersion")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        stale_form = self._po(contact)

        frappe.set_user(self.sales)
        edited = update_booking(pending_id, {"note": "Dock 3"}, get_booking(pending_id)["modified"])
        after_edit = get_strategy_opportunity(quoted["id"])
        self.assertNotEqual(after_edit["modified"], approved["modified"])
        self.assertEqual(after_edit["liveBooking"]["modified"], edited["modified"])
        for payload in (stale_form, {**stale_form, "expectedBookingModified": approved["liveBooking"]["modified"]}):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as stale:
                confirm_po(quoted["id"], payload, approved["modified"])
            self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        frappe.set_user(self.manager)
        account = frappe.db.get_value("CRM Booking", pending_id, "account")
        frappe.db.set_value("Customer", account, "custom_crm_visibility", "Public")
        reassigned = update_booking(pending_id, {"owner": self.other_sales}, edited["modified"])
        after_reassign = get_strategy_opportunity(quoted["id"])
        self.assertNotEqual(after_reassign["modified"], after_edit["modified"])

        update_booking(pending_id, {"status": "Cancelled"}, reassigned["modified"])
        after_cancel = get_strategy_opportunity(quoted["id"])
        self.assertNotEqual(after_cancel["modified"], after_reassign["modified"])
        self.assertIsNone(after_cancel["liveBooking"])
        with self.assertRaises(CrmApiException) as rollback:
            rollback_opportunity_stage(quoted["id"], "quotation_sent", "Stop production", after_reassign["modified"])
        self.assertEqual(rollback.exception.code, "VERSION_CONFLICT")
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as confirm:
            confirm_po(quoted["id"], stale_form, after_reassign["modified"])
        self.assertEqual(confirm.exception.code, "VERSION_CONFLICT")
        self.assertEqual(self._booking_count(quoted["id"]), 1)

        # A refreshed client carries on: the current version creates the replacement Booking.
        received = confirm_po(quoted["id"], stale_form, after_cancel["modified"])
        self.assertEqual((received["stage"], self._booking_count(quoted["id"])), ("po_received", 2))

    def test_cancelled_validation_booking_is_replaced_and_completed_booking_blocks_rollback(self):
        _, contact, quoted = self._quoted("PoReplaced")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        old_input = {
            "booking": self._booking(contact),
            "expectedBookingModified": approved["liveBooking"]["modified"],
            "actualPoDate": self.po_date,
        }
        update_booking(pending_id, {"status": "Cancelled"}, get_booking(pending_id)["modified"])

        frappe.set_user(self.sales)
        current = get_strategy_opportunity(quoted["id"])
        # Cancelling the Booking moved the Opportunity version, so a form prepared on the old view is
        # refused whether or not it carries the Pending Booking's version.
        self.assertNotEqual(current["modified"], approved["modified"])
        self.assertIsNone(current["liveBooking"])
        for payload in (old_input, self._po(contact)):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as cancelled:
                confirm_po(quoted["id"], payload, approved["modified"])
            self.assertEqual(cancelled.exception.code, "VERSION_CONFLICT")
        unchanged = get_strategy_opportunity(quoted["id"])
        self.assertEqual((unchanged["stage"], unchanged["modified"]), ("internal_validation", current["modified"]))
        self.assertEqual(unchanged["stageHistory"], current["stageHistory"])
        self.assertEqual(self._booking_count(quoted["id"]), 1)
        self.assertEqual(get_booking(pending_id)["status"], "Cancelled")

        # A refreshed form has no Pending Booking version and may explicitly create a replacement.
        received = confirm_po(quoted["id"], self._po(contact), unchanged["modified"])
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

    def test_po_confirmation_records_the_actual_po_date_on_the_booking(self):
        _, contact, quoted = self._quoted("PoActualDate")
        tomorrow = str(frappe.utils.add_days(frappe.utils.today(), 1))
        for actual_po_date, error in ((None, "Required"), (tomorrow, "Cannot be in the future")):
            payload = {"booking": self._booking(contact)}
            if actual_po_date:
                payload["actualPoDate"] = actual_po_date
            with self.subTest(actual_po_date=actual_po_date), self.assertRaises(CrmApiException) as invalid:
                confirm_po(quoted["id"], payload, quoted["modified"])
            self.assertEqual(invalid.exception.field_errors, {"actualPoDate": error})
        self.assertEqual(self._booking_count(quoted["id"]), 0)

        received = confirm_po(quoted["id"], self._po(contact), quoted["modified"])
        self.assertEqual(received["liveBooking"]["actualPoDate"], self.po_date)
        # The stage history keeps the system time; the date on the PO lives on the Booking.
        self.assertEqual(
            (received["stageHistory"][0]["event"], received["stageHistory"][0]["reachedAtBasis"]),
            ("po_confirmed", "recorded"),
        )
        booking = get_booking(received["liveBooking"]["id"])
        self.assertEqual(
            (booking["actualPoDate"], booking["actualPoDateSource"], booking["actualPoDateNote"], booking["bookingDate"]),
            (self.po_date, "po_confirmation", "", frappe.utils.today()),
        )

        noted = update_booking(booking["id"], {"note": "PO rev B"}, booking["modified"])
        self.assertEqual(noted["actualPoDate"], self.po_date)
        with self.assertRaises(CrmApiException) as changed:
            update_booking(booking["id"], {"actualPoDate": "2026-01-02"}, noted["modified"])
        self.assertEqual(changed.exception.field_errors, {"actualPoDate": "Manager correction only"})
        cancelled = update_booking(booking["id"], {"status": "Cancelled"}, noted["modified"])
        self.assertEqual((cancelled["status"], cancelled["actualPoDate"]), ("Cancelled", self.po_date))

        after_cancel = get_strategy_opportunity(quoted["id"])
        with self.assertRaises(CrmApiException) as undated_replacement:
            confirm_po(quoted["id"], {"booking": self._booking(contact)}, after_cancel["modified"])
        self.assertEqual(undated_replacement.exception.field_errors, {"actualPoDate": "Required"})
        replaced = confirm_po(quoted["id"], self._po(contact), after_cancel["modified"])
        replacement = get_booking(replaced["liveBooking"]["id"])
        self.assertEqual((replacement["actualPoDate"], replacement["actualPoDateSource"]), (self.po_date, "po_confirmation"))

    def test_internal_validation_booking_gets_its_po_date_only_when_the_po_is_confirmed(self):
        _, contact, quoted = self._quoted("PoDateValidated")
        approved = self._approved_validation(quoted, contact)
        pending_id = approved["liveBooking"]["id"]
        self.assertEqual(get_booking(pending_id)["actualPoDate"], "")

        frappe.set_user(self.sales)
        pending = get_booking(pending_id)
        payload = self._po(contact)
        payload["expectedBookingModified"] = pending["modified"]
        received = confirm_po(quoted["id"], payload, approved["modified"])
        self.assertEqual(
            (received["liveBooking"]["id"], get_booking(pending_id)["actualPoDateSource"]), (pending_id, "po_confirmation"),
        )

        frappe.set_user(self.manager)
        back = rollback_opportunity_stage(
            quoted["id"], "internal_validation", "Customer withdrew the PO", received["modified"],
        )
        pending = get_booking(pending_id)
        self.assertEqual((pending["status"], pending["actualPoDate"], pending["actualPoDateSource"]), ("Pending", "", ""))
        self.assertEqual(
            [(row["from"], row["to"]) for row in back["history"] if row["field"] == "bookingPoDate"],
            [(self.po_date, "")],
        )
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as undated:
            confirm_po(quoted["id"], {"booking": self._booking(contact)}, back["modified"])
        self.assertEqual(undated.exception.field_errors, {"actualPoDate": "Required"})

    def test_only_a_manager_fills_in_or_corrects_the_actual_po_date(self):
        account, contact, quoted = self._quoted("PoBackfill")
        received = confirm_po(quoted["id"], self._po(contact), quoted["modified"])
        booking_id = received["liveBooking"]["id"]
        # An order confirmed before the actual PO date existed.
        frappe.db.set_value(
            "CRM Booking", booking_id, {"actual_po_date": None, "actual_po_date_source": None}, update_modified=False,
        )
        booking = get_booking(booking_id)
        missing = list_bookings({"actualPoDateMissing": "1", "pageSize": 100})[0]
        self.assertIn(booking_id, {row["id"] for row in missing})
        with self.assertRaises(CrmApiException) as sales_denied:
            set_booking_actual_po_date(booking_id, {"actualPoDate": "2025-12-30"}, booking["modified"])
        self.assertEqual(sales_denied.exception.code, "PERMISSION_DENIED")

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as stale:
            set_booking_actual_po_date(booking_id, {"actualPoDate": "2025-12-30"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        filled = set_booking_actual_po_date(booking_id, {"actualPoDate": "2025-12-30"}, booking["modified"])
        self.assertEqual(
            (filled["actualPoDate"], filled["actualPoDateSource"], filled["actualPoDateNote"], filled["bookingDate"]),
            ("2025-12-30", "backfill", "", booking["bookingDate"]),
        )
        for payload, field_errors in (
            ({"actualPoDate": "2025-12-30", "reason": "Same date"}, {"actualPoDate": "Unchanged"}),
            ({"actualPoDate": "2026-01-02"}, {"reason": "Required"}),
            ({"actualPoDate": "", "reason": "Clear it"}, {"actualPoDate": "Required"}),
        ):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as invalid:
                set_booking_actual_po_date(booking_id, payload, filled["modified"])
            self.assertEqual(invalid.exception.field_errors, field_errors)
        corrected = set_booking_actual_po_date(
            booking_id, {"actualPoDate": "2026-01-02", "reason": "The PO scan is dated 2 January"}, filled["modified"],
        )
        self.assertEqual(
            (corrected["actualPoDate"], corrected["actualPoDateNote"]), ("2026-01-02", "The PO scan is dated 2 January"),
        )
        self.assertEqual(
            [(row["from"], row["to"]) for row in get_strategy_opportunity(quoted["id"])["history"] if row["field"] == "bookingPoDate"],
            [("2025-12-30", "2026-01-02"), ("", "2025-12-30")],
        )

        # A converted order stays open to the correction; a Pending one has no PO yet.
        frappe.db.set_value("CRM Booking", booking_id, "status", "Completed", update_modified=False)
        completed = set_booking_actual_po_date(
            booking_id, {"actualPoDate": "2026-01-03", "reason": "The customer reissued the PO"}, corrected["modified"],
        )
        self.assertEqual((completed["status"], completed["actualPoDate"]), ("Completed", "2026-01-03"))
        pending_upsell = create_booking({
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Spare parts",
            "quantity": 1, "ddl": "2027-03-31", "amount": "1000.00", "currency": "CNY", "status": "Pending",
            "owner": self.sales, "source": "Upsell",
        })
        with self.assertRaises(CrmApiException) as pending:
            set_booking_actual_po_date(pending_upsell["id"], {"actualPoDate": "2026-01-03"}, pending_upsell["modified"])
        self.assertEqual(pending.exception.code, "INVALID_TRANSITION")

    def test_upsell_booking_takes_its_first_actual_po_date_on_entry(self):
        account, contact, _ = self._quoted("PoUpsell")
        base = {
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Spare parts",
            "quantity": 1, "ddl": "2027-03-31", "amount": "1000.00", "currency": "CNY", "status": "Confirmed",
            "owner": self.sales, "source": "Upsell",
        }
        with self.assertRaises(CrmApiException) as future:
            create_booking({**base, "actualPoDate": str(frappe.utils.add_days(frappe.utils.today(), 1))})
        self.assertEqual(future.exception.field_errors, {"actualPoDate": "Cannot be in the future"})
        dated = create_booking({**base, "actualPoDate": self.po_date})
        self.assertEqual((dated["actualPoDate"], dated["actualPoDateSource"]), (self.po_date, "booking_entry"))

        undated = create_booking(base)
        self.assertEqual((undated["actualPoDate"], undated["actualPoDateSource"]), ("", ""))
        filled = update_booking(undated["id"], {"actualPoDate": self.po_date}, undated["modified"])
        self.assertEqual((filled["actualPoDate"], filled["actualPoDateSource"]), (self.po_date, "booking_entry"))
        for value in ("2026-01-02", ""):
            with self.subTest(value=value), self.assertRaises(CrmApiException) as locked:
                update_booking(filled["id"], {"actualPoDate": value}, filled["modified"])
            self.assertEqual(locked.exception.field_errors, {"actualPoDate": "Manager correction only"})
