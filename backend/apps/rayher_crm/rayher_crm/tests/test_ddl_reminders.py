from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from rayher_crm.services import ddl_reminders
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import archive_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.ddl_reminders import send_ddl_reminders
from rayher_crm.services.sites import create_site


class TestDdlReminders(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-ddl-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-ddl-engineer@example.invalid", "CRM Engineer")
        self.manager = self._user("crm-ddl-manager@example.invalid", "CRM Manager")

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
            "doctype": "User",
            "email": email,
            "first_name": email.split("@", 1)[0],
            "enabled": 1,
            "send_welcome_email": 0,
            "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def test_booking_reminders_broadcast_at_15_and_7_days_without_duplicates(self):
        frappe.set_user(self.sales)
        account = create_account({
            "name": "DDL Reminder Account",
            "shortName": "DDL Reminder",
            "segment": "Frontend",
            "tier": "A",
            "city": "Shanghai",
            "region": "East China",
            "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": "DDL Reminder Site",
            "city": "Shanghai",
            "type": "Fab",
            "process": "Frontend",
            "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"],
            "siteId": site["id"],
            "name": "DDL Reminder Contact",
            "title": "Director",
            "department": "Engineering",
            "relationship": "Developing",
            "owner": self.sales,
            "status": "Active",
        })
        booking = frappe.get_doc({
            "doctype": "CRM Booking",
            "account": account["id"],
            "primary_contact": contact["id"],
            "booking_type": "Equipment",
            "equipment": "Inspection Tool",
            "quantity": 1,
            "ddl": add_days(today(), 15),
            "amount": "1000.00",
            "currency": "CNY",
            "status": "Confirmed",
            "booking_date": today(),
            "booking_owner": self.sales,
            "source": "Upsell",
        }).insert(ignore_permissions=True)

        frappe.set_user("Administrator")
        send_ddl_reminders()
        recipients = set(frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Booking", "source_name": booking.name, "title": ["like", "%15 天"]},
            pluck="recipient_user",
        ))
        self.assertTrue({self.sales, self.manager}.issubset(recipients))
        first_count = frappe.db.count("CRM Notification Event", {"source_name": booking.name})
        send_ddl_reminders()
        self.assertEqual(frappe.db.count("CRM Notification Event", {"source_name": booking.name}), first_count)

        # An archived Booking (a Manager's archive, in place of a delete) has no deadline to remind of.
        archived = frappe.copy_doc(booking)
        archived.equipment = "Archived Inspection Tool"
        archived.insert(ignore_permissions=True)
        archive_booking(archived.name)
        send_ddl_reminders()
        self.assertEqual(frappe.db.count("CRM Notification Event", {"source_name": archived.name}), 0)

        frappe.db.set_value("CRM Booking", booking.name, "ddl", add_days(today(), 7))
        send_ddl_reminders()
        seven_day_recipients = set(frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": booking.name, "title": ["like", "%7 天"]},
            pluck="recipient_user",
        ))
        self.assertTrue({self.sales, self.manager}.issubset(seven_day_recipients))

    def _booking_for_scope_test(self, suffix):
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"DDL Scope {suffix}", "shortName": f"DDL {suffix}", "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East China", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"DDL Site {suffix}", "city": "Shanghai", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"DDL Contact {suffix}",
            "title": "Director", "department": "Engineering", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        return frappe.get_doc({
            "doctype": "CRM Booking", "account": account["id"], "primary_contact": contact["id"],
            "booking_type": "Equipment", "equipment": "Inspection Tool", "quantity": 1,
            "ddl": add_days(today(), 15), "amount": "1000.00", "currency": "CNY",
            "status": "Confirmed", "booking_date": today(), "booking_owner": self.sales, "source": "Upsell",
        }).insert(ignore_permissions=True)

    def test_transferred_account_skips_stale_owner_without_stopping_other_reminders(self):
        valid = self._booking_for_scope_test("valid")
        stale = self._booking_for_scope_test("transferred")
        frappe.set_user("Administrator")
        new_owner = self._user("crm-ddl-new-owner@example.invalid", "CRM Sales")
        frappe.db.set_value("Customer", stale.account, {
            "custom_crm_owner": new_owner, "custom_crm_visibility": "Private",
        })
        send_ddl_reminders()
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM Booking", "source_name": stale.name, "recipient_user": self.sales,
        }))
        for booking, recipient in ((stale, self.manager), (valid, self.sales)):
            self.assertTrue(frappe.db.exists("CRM Notification Event", {
                "source_doctype": "CRM Booking", "source_name": booking.name, "recipient_user": recipient,
            }))
        with patch("rayher_crm.services.notifications.create_notification", side_effect=RuntimeError("database unavailable")):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                send_ddl_reminders()

    def test_demo_and_test_run_deadlines_reach_all_assigned_people(self):
        request = frappe.get_doc({
            "doctype": "CRM Demo Request",
            "request_mode": "Self Test",
            "sales_owner": self.sales,
            "created_by_user": self.sales,
            "title": "DDL Demo Request",
            "objective": "Verify reminder delivery",
            "requested_equipment": "Inspection Tool",
            "sample_type": "Wafer",
            "sample_quantity": 1,
            "target_date": add_days(today(), 20),
            "customer_expected_date": add_days(today(), 15),
            "priority": "Medium",
            "acceptance_criteria": "Reminder reaches every owner",
            "status": "Engineer Review",
            "engineer_owner": self.engineer,
            "form_data": "{}",
        }).insert(ignore_permissions=True)
        # Submitted, as a request in Engineer Review has been: its Engineer reads it and hears of its deadline.
        frappe.get_doc({
            "doctype": "CRM Demo Request History", "demo_request": request.name, "at": frappe.utils.now_datetime(),
            "actor": self.sales, "from_status": "Draft", "to_status": "Engineer Review", "comment": "Submitted",
        }).insert(ignore_permissions=True)
        evaluation = frappe.get_doc({
            "doctype": "CRM Evaluation",
            "demo_request": request.name,
            "title": "DDL Evaluation",
            "status": "Scheduled",
            "evaluation_owner": self.engineer,
            "planned_end": add_days(today(), 10),
            "test_run_deadline": add_days(today(), 7),
            "wafer_preparation_status": "Pending",
            "test_preparation_status": "Pending",
            "acceptance": "Pending",
            "report_status": "Not Ready",
        }).insert(ignore_permissions=True)

        # A draft naming the Engineer is Sales' own until they submit it: its deadline reaches Sales, not the Engineer.
        draft = frappe.get_doc({
            "doctype": "CRM Demo Request", "request_mode": "Self Test", "sales_owner": self.sales,
            "created_by_user": self.sales, "title": "DDL Demo Request Draft", "objective": "Verify reminder delivery",
            "requested_equipment": "Inspection Tool", "sample_type": "Wafer", "sample_quantity": 1,
            "target_date": add_days(today(), 20), "customer_expected_date": add_days(today(), 15),
            "priority": "Medium", "acceptance_criteria": "Reminder reaches the owner", "status": "Draft",
            "engineer_owner": self.engineer, "form_data": "{}",
        }).insert(ignore_permissions=True)

        # The Engineer is among the people of every record's deadline here, as an RFQ of the Opportunity would
        # make them: the draft still keeps its deadline from them.
        related = ddl_reminders._related_users

        def with_engineer(**kwargs):
            return related(**kwargs) | {self.engineer}

        frappe.set_user("Administrator")
        with patch.object(ddl_reminders, "_related_users", side_effect=with_engineer):
            send_ddl_reminders()
        draft_recipients = set(frappe.get_all(
            "CRM Notification Event", filters={"source_name": draft.name}, pluck="recipient_user",
        ))
        self.assertIn(self.sales, draft_recipients)
        self.assertNotIn(self.engineer, draft_recipients)
        expected = {self.sales, self.engineer, self.manager}
        request_recipients = set(frappe.get_all(
            "CRM Notification Event", filters={"source_name": request.name}, pluck="recipient_user",
        ))
        evaluation_recipients = set(frappe.get_all(
            "CRM Notification Event", filters={"source_name": evaluation.name}, pluck="recipient_user",
        ))
        self.assertTrue(expected.issubset(request_recipients))
        self.assertTrue(expected.issubset(evaluation_recipients))

        before = {
            request.name: frappe.db.count("CRM Notification Event", {"source_name": request.name}),
            evaluation.name: frappe.db.count("CRM Notification Event", {"source_name": evaluation.name}),
        }
        send_ddl_reminders()
        self.assertEqual(frappe.db.count("CRM Notification Event", {"source_name": request.name}), before[request.name])
        self.assertEqual(frappe.db.count("CRM Notification Event", {"source_name": evaluation.name}), before[evaluation.name])
