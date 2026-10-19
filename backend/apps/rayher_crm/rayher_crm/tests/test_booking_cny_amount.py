from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import archive_booking, create_booking, get_booking, set_booking_amount_cny, update_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import (
    confirm_po,
    create_strategy_opportunity,
    get_strategy_opportunity,
    request_internal_validation,
    review_internal_validation,
)
from rayher_crm.services.sites import create_site
from rayher_crm.setup import booking_cny_amount
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestBookingCnyAmount(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-bcny-sales@example.invalid", "CRM Sales")
        self.manager = self._user("crm-bcny-manager@example.invalid", "CRM Manager")
        self.reviewer = self._user("crm-bcny-reviewer@example.invalid", "CRM Manager")
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

    def _quoted(self, suffix: str, currency: str = "USD"):
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"BCNY {suffix}", "shortName": suffix[:8], "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "East China", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000001",
            "email": f"bcny-{suffix.lower().replace(' ', '-')}@example.invalid", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        amount = "120000.00" if currency != "CNY" else "880000.00"
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline", "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Opportunity",
            "owner": self.sales, "amount": amount, "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": currency, "originalAmount": amount,
            "amountCny": "852000.00", "qualificationConfirmed": True,
        })
        return account, contact, advance_opportunity_fixture(opportunity, "quotation_sent")

    def _draft(self, contact: dict, currency: str = "USD", **overrides) -> dict:
        draft = {
            "primaryContactId": contact["id"], "equipment": "Inspection 3000", "quantity": 1, "ddl": "2027-03-31",
            "amount": "120000.00" if currency != "CNY" else "880000.00", "currency": currency, "owner": self.sales, "note": "",
        }
        draft.update(overrides)
        return draft

    def _upsell(self, account: dict, contact: dict, **overrides) -> dict:
        payload = {
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Upgrade kit", "quantity": 1,
            "ddl": "2027-01-31", "amount": "50000.00", "currency": "USD", "status": "Confirmed", "source": "Upsell",
            "owner": self.sales, "note": "",
        }
        payload.update(overrides)
        return payload

    def test_a_foreign_currency_po_needs_its_cny_amount(self):
        _, contact, opportunity = self._quoted("Foreign PO")
        frappe.set_user(self.sales)

        with self.assertRaises(CrmApiException) as missing:
            confirm_po(opportunity["id"], {"booking": self._draft(contact), "actualPoDate": self.po_date}, opportunity["modified"])
        self.assertEqual(missing.exception.field_errors, {"amountCny": "Required"})
        with self.assertRaises(CrmApiException) as invalid:
            confirm_po(opportunity["id"], {
                "booking": self._draft(contact, amountCny="0"), "actualPoDate": self.po_date,
            }, opportunity["modified"])
        self.assertEqual(invalid.exception.field_errors, {"amountCny": "Invalid amount"})

        confirmed = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, amountCny="852000.5"), "actualPoDate": self.po_date,
        }, opportunity["modified"])

        booking = get_booking(confirmed["liveBooking"]["id"])
        self.assertEqual((booking["currency"], booking["amount"], booking["amountCny"]), ("USD", "120000.00", "852000.50"))
        self.assertEqual(confirmed["liveBooking"]["amountCny"], "852000.50")

    def test_a_cny_booking_uses_its_amount_and_stores_nothing_extra(self):
        _, contact, opportunity = self._quoted("Native PO", currency="CNY")
        frappe.set_user(self.sales)

        confirmed = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, currency="CNY", amountCny="1.00"), "actualPoDate": self.po_date,
        }, opportunity["modified"])

        booking = get_booking(confirmed["liveBooking"]["id"])
        self.assertEqual((booking["amount"], booking["amountCny"]), ("880000.00", "880000.00"))
        self.assertEqual(frappe.db.get_value("CRM Booking", booking["id"], "amount_cny"), 0)

    def test_an_internal_validation_may_leave_the_cny_amount_for_the_po(self):
        _, contact, opportunity = self._quoted("Validation")
        frappe.set_user(self.sales)
        requested = request_internal_validation(opportunity["id"], {
            "reason": "Long lead time", "expectedPoDate": "2026-11-30", "booking": self._draft(contact),
        }, opportunity["modified"])
        frappe.set_user(self.reviewer)
        approved = review_internal_validation(opportunity["id"], {
            "validationId": requested["internalValidation"]["id"], "decision": "approved",
        }, requested["modified"])
        self.assertEqual(approved["liveBooking"]["status"], "Pending")
        self.assertEqual(approved["liveBooking"]["amountCny"], "")

        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as missing:
            confirm_po(opportunity["id"], {"booking": self._draft(contact), "actualPoDate": self.po_date}, approved["modified"])
        self.assertEqual(missing.exception.field_errors, {"amountCny": "Required"})
        confirmed = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, amountCny="851000"), "actualPoDate": self.po_date,
            "expectedBookingModified": get_booking(approved["liveBooking"]["id"])["modified"],
        }, approved["modified"])

        self.assertEqual((confirmed["liveBooking"]["status"], confirmed["liveBooking"]["amountCny"]), ("Confirmed", "851000.00"))

    def test_an_upsell_needs_its_cny_amount_once_confirmed_and_cancelling_is_never_blocked(self):
        account, contact, _ = self._quoted("Upsell")
        frappe.set_user(self.sales)

        with self.assertRaises(CrmApiException) as missing:
            create_booking(self._upsell(account, contact))
        self.assertEqual(missing.exception.field_errors, {"amountCny": "Required"})
        pending = create_booking(self._upsell(account, contact, status="Pending"))
        self.assertEqual(pending["amountCny"], "")
        with self.assertRaises(CrmApiException) as confirming:
            update_booking(pending["id"], {"status": "Confirmed"}, pending["modified"])
        self.assertEqual(confirming.exception.field_errors, {"amountCny": "Required"})

        confirmed = update_booking(pending["id"], {"status": "Confirmed", "amountCny": "355000"}, pending["modified"])
        self.assertEqual(confirmed["amountCny"], "355000.00")

        # An order confirmed before the field existed can still be cancelled.
        frappe.db.set_value("CRM Booking", confirmed["id"], "amount_cny", 0, update_modified=False)
        cancelled = update_booking(confirmed["id"], {"status": "Cancelled"}, confirmed["modified"])
        self.assertEqual((cancelled["status"], cancelled["amountCny"]), ("Cancelled", ""))

    def test_a_manager_fills_in_or_corrects_the_cny_amount(self):
        _, contact, opportunity = self._quoted("Manager")
        frappe.set_user(self.sales)
        confirmed = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, amountCny="852000"), "actualPoDate": self.po_date,
        }, opportunity["modified"])
        booking_id = confirmed["liveBooking"]["id"]
        # An order confirmed before the field existed.
        frappe.db.set_value("CRM Booking", booking_id, "amount_cny", 0, update_modified=False)
        booking = get_booking(booking_id)
        self.assertEqual(booking["amountCny"], "")

        with self.assertRaises(CrmApiException) as denied:
            set_booking_amount_cny(booking_id, {"amountCny": "850000"}, booking["modified"])
        self.assertEqual(denied.exception.code, "PERMISSION_DENIED")

        frappe.set_user(self.manager)
        filled = set_booking_amount_cny(booking_id, {"amountCny": "850000"}, booking["modified"])
        self.assertEqual((filled["amountCny"], filled["amountCnyNote"]), ("850000.00", ""))
        with self.assertRaises(CrmApiException) as no_reason:
            set_booking_amount_cny(booking_id, {"amountCny": "860000"}, filled["modified"])
        self.assertEqual(no_reason.exception.field_errors, {"reason": "Required"})
        with self.assertRaises(CrmApiException) as unchanged:
            set_booking_amount_cny(booking_id, {"amountCny": "850000.00", "reason": "Same"}, filled["modified"])
        self.assertEqual(unchanged.exception.field_errors, {"amountCny": "Unchanged"})
        corrected = set_booking_amount_cny(booking_id, {"amountCny": "860000", "reason": "Rate on the PO"}, filled["modified"])
        self.assertEqual((corrected["amountCny"], corrected["amountCnyNote"]), ("860000.00", "Rate on the PO"))

        history = frappe.get_all(
            "CRM Opportunity History", filters={"opportunity": opportunity["id"], "field": "bookingAmountCny"},
            fields=["from_value", "to_value"], order_by="creation asc",
        )
        self.assertEqual([(row.from_value or "", row.to_value) for row in history], [("", "850000.00"), ("850000.00", "860000.00")])

    def test_an_ordinary_edit_cannot_change_a_recorded_cny_amount(self):
        account, contact, opportunity = self._quoted("Edit Guard")
        frappe.set_user(self.sales)
        confirmed = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, amountCny="852000"), "actualPoDate": self.po_date,
        }, opportunity["modified"])
        booking = get_booking(confirmed["liveBooking"]["id"])

        with self.assertRaises(CrmApiException) as changed:
            update_booking(booking["id"], {"amountCny": "1.00"}, booking["modified"])
        self.assertEqual(changed.exception.field_errors, {"amountCny": "Manager correction only"})
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as manager_edit:
            update_booking(booking["id"], {"amountCny": "1.00"}, booking["modified"])
        self.assertEqual(manager_edit.exception.field_errors, {"amountCny": "Manager correction only"})
        self.assertEqual(get_booking(booking["id"])["amountCny"], "852000.00")

        # The same amount, as the editor sends it back, lets the other fields change.
        frappe.set_user(self.sales)
        edited = update_booking(booking["id"], {"amountCny": "852000", "note": "Ships in March"}, booking["modified"])
        self.assertEqual((edited["amountCny"], edited["note"]), ("852000.00", "Ships in March"))
        # An empty amount keeps the recorded one instead of wiping it.
        edited = update_booking(booking["id"], {"amountCny": "", "note": "Ships in April"}, edited["modified"])
        self.assertEqual((edited["amountCny"], edited["note"]), ("852000.00", "Ships in April"))

        # A Pending Booking is not an order yet, so its CNY amount stays editable.
        pending = create_booking(self._upsell(account, contact, status="Pending", amountCny="300000"))
        repriced = update_booking(pending["id"], {"amountCny": "310000"}, pending["modified"])
        self.assertEqual(repriced["amountCny"], "310000.00")

        # A confirmed order keeps its original currency and recorded CNY amount. Those fields
        # cannot be rewritten together through the ordinary editor.
        frappe.set_user(self.manager)
        corrected = set_booking_amount_cny(booking["id"], {"amountCny": "860000", "reason": "Rate on the PO"}, edited["modified"])
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as currency_change:
            update_booking(booking["id"], {"currency": "CNY", "amount": "860000"}, corrected["modified"])
        self.assertEqual(currency_change.exception.field_errors, {"currency": "Confirmed order currency is fixed"})
        unchanged = get_booking(booking["id"])
        self.assertEqual(
            (unchanged["currency"], unchanged["amount"], unchanged["amountCny"], unchanged["amountCnyNote"]),
            ("USD", "120000.00", "860000.00", "Rate on the PO"),
        )

    def test_replacing_a_cancelled_order_keeps_the_trail_of_its_amount_and_po_date(self):
        _, contact, opportunity = self._quoted("Replace")
        frappe.set_user(self.sales)
        confirmed = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, amountCny="852000"), "actualPoDate": self.po_date,
        }, opportunity["modified"])
        first = get_booking(confirmed["liveBooking"]["id"])
        update_booking(first["id"], {"status": "Cancelled"}, first["modified"])
        new_po_date = str(frappe.utils.add_days(frappe.utils.today(), -1))

        replacement = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, amountCny="700000"), "actualPoDate": new_po_date,
        }, get_strategy_opportunity(opportunity["id"])["modified"])

        self.assertEqual(replacement["liveBooking"]["amountCny"], "700000.00")
        history = frappe.get_all(
            "CRM Opportunity History",
            filters={"opportunity": opportunity["id"], "field": ["in", ["bookingAmountCny", "bookingPoDate"]]},
            fields=["field", "from_value", "to_value"], order_by="field asc",
        )
        self.assertEqual(
            [(row.field, row.from_value, row.to_value) for row in history],
            [("bookingAmountCny", "852000.00", "700000.00"), ("bookingPoDate", self.po_date, new_po_date)],
        )

    def test_a_correction_reason_goes_when_a_later_edit_changes_the_amount(self):
        account, contact, _ = self._quoted("Stale Note")
        frappe.set_user(self.sales)
        order = create_booking(self._upsell(account, contact, amountCny="355000"))
        frappe.set_user(self.manager)
        corrected = set_booking_amount_cny(order["id"], {"amountCny": "356000", "reason": "Rate on the PO"}, order["modified"])

        frappe.set_user(self.sales)
        kept = update_booking(order["id"], {"note": "Ships in March"}, corrected["modified"])
        self.assertEqual(kept["amountCnyNote"], "Rate on the PO")
        pending = update_booking(order["id"], {"status": "Pending"}, kept["modified"])
        repriced = update_booking(order["id"], {"amountCny": "300000"}, pending["modified"])
        self.assertEqual((repriced["amountCny"], repriced["amountCnyNote"]), ("300000.00", ""))

    def test_currency_changes_cannot_bypass_a_recorded_cny_amount(self):
        account, contact, _ = self._quoted("Currency Guard")
        frappe.set_user(self.sales)
        order = create_booking(self._upsell(account, contact, amountCny="355000"))
        frappe.set_user(self.manager)
        corrected = set_booking_amount_cny(
            order["id"], {"amountCny": "356000", "reason": "PO exchange rate"}, order["modified"],
        )
        for user in (self.sales, self.manager):
            frappe.set_user(user)
            for currency in ("CNY", "EUR"):
                with self.subTest(user=user, currency=currency):
                    with self.assertRaises(CrmApiException) as denied:
                        update_booking(order["id"], {"currency": currency}, corrected["modified"])
                    self.assertEqual(denied.exception.field_errors, {"currency": "Confirmed order currency is fixed"})
                    unchanged = get_booking(order["id"])
                    self.assertEqual(
                        (unchanged["currency"], unchanged["amountCny"], unchanged["amountCnyNote"], unchanged["modified"]),
                        ("USD", "356000.00", "PO exchange rate", corrected["modified"]),
                    )
        frappe.set_user(self.sales)
        edited = update_booking(order["id"], {"note": "Contact customer before delivery"}, corrected["modified"])
        self.assertEqual((edited["amountCny"], edited["amountCnyNote"]), ("356000.00", "PO exchange rate"))
        pending = create_booking(self._upsell(account, contact, status="Pending"))
        repriced = update_booking(pending["id"], {"currency": "CNY", "amount": "300000"}, pending["modified"])
        self.assertEqual((repriced["currency"], repriced["amountCny"]), ("CNY", "300000.00"))

    def test_the_manager_endpoint_only_takes_confirmed_foreign_orders(self):
        account, contact, opportunity = self._quoted("Endpoint", currency="CNY")
        frappe.set_user(self.sales)
        cny = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, currency="CNY"), "actualPoDate": self.po_date,
        }, opportunity["modified"])
        pending = create_booking(self._upsell(account, contact, status="Pending"))

        frappe.set_user(self.manager)
        cny_booking = get_booking(cny["liveBooking"]["id"])
        with self.assertRaises(CrmApiException) as native:
            set_booking_amount_cny(cny_booking["id"], {"amountCny": "1000"}, cny_booking["modified"])
        self.assertEqual(native.exception.field_errors, {"amountCny": "CNY Booking"})
        with self.assertRaises(CrmApiException) as not_confirmed:
            set_booking_amount_cny(pending["id"], {"amountCny": "1000"}, pending["modified"])
        # BOOKING_STATUS_INVALID is reported as INVALID_TRANSITION.
        self.assertEqual(not_confirmed.exception.code, "INVALID_TRANSITION")

    def test_list_missing_names_confirmed_foreign_orders_without_a_cny_amount(self):
        account, contact, opportunity = self._quoted("Missing")
        frappe.set_user(self.sales)
        confirmed = confirm_po(opportunity["id"], {
            "booking": self._draft(contact, amountCny="852000"), "actualPoDate": self.po_date,
        }, opportunity["modified"])
        filled = create_booking(self._upsell(account, contact, amountCny="355000"))
        # A foreign order without its CNY amount, archived by a Manager: no longer anyone's to fill in.
        shelved = create_booking(self._upsell(account, contact, equipment="Shelved kit", amountCny="355000"))
        frappe.db.set_value("CRM Booking", confirmed["liveBooking"]["id"], "amount_cny", 0, update_modified=False)
        frappe.db.set_value("CRM Booking", shelved["id"], "amount_cny", 0, update_modified=False)

        frappe.set_user("Administrator")
        archive_booking(shelved["id"])
        missing = booking_cny_amount.list_missing()

        names = {row["name"] for row in missing["bookings"]}
        self.assertIn(confirmed["liveBooking"]["id"], names)
        self.assertNotIn(filled["id"], names)
        self.assertNotIn(shelved["id"], names)
        self.assertEqual(
            next(row for row in missing["bookings"] if row["name"] == confirmed["liveBooking"]["id"])["currency"], "USD",
        )
