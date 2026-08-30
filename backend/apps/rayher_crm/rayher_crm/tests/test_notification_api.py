from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.notifications import (
    create_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)


class TestNotificationApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-notification-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-notification-other@example.invalid", "CRM Sales")
        self.manager = self._user("crm-notification-manager@example.invalid", "CRM Manager")
        frappe.db.delete(
            "CRM Notification Event",
            {"recipient_user": ["in", [self.sales, self.other_sales, self.manager]]},
        )

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

    def _event(self, recipient: str, title: str):
        return create_notification(
            recipient=recipient,
            category="Demo",
            title=title,
            message=f"{title} message",
            route="/demo-workflow/CRM-DEMO-TEST?tab=information",
        )

    def test_recipient_only_list_and_manager_is_not_wildcard(self):
        frappe.set_user(self.manager)
        self._event(self.sales, "Sales only")
        self._event(self.manager, "Manager only")

        frappe.set_user(self.sales)
        sales_page = list_notifications(page=1, page_size=20)
        self.assertEqual([item["title"] for item in sales_page["items"]], ["Sales only"])
        self.assertEqual(sales_page["items"][0]["recipientId"], self.sales)

        frappe.set_user(self.manager)
        manager_page = list_notifications(page=1, page_size=20)
        self.assertEqual([item["title"] for item in manager_page["items"]], ["Manager only"])

    def test_server_actor_time_and_recipient_only_read_mutation(self):
        frappe.set_user(self.manager)
        event = self._event(self.sales, "Server fields")
        stored = frappe.get_doc("CRM Notification Event", event["id"])
        self.assertEqual(stored.actor, self.manager)
        self.assertTrue(stored.created_at)

        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException) as denied:
            mark_notification_read(event["id"])
        self.assertEqual(denied.exception.code, "NOT_FOUND")

        frappe.set_user(self.sales)
        marked = mark_notification_read(event["id"])
        self.assertTrue(marked["read"])
        self.assertTrue(marked["readAt"].endswith("Z"))
        self.assertEqual(mark_notification_read(event["id"])["readAt"], marked["readAt"])

    def test_unread_filter_pagination_and_mark_all_are_recipient_scoped(self):
        frappe.set_user(self.manager)
        first = self._event(self.sales, "First")
        self._event(self.sales, "Second")
        self._event(self.other_sales, "Other recipient")

        frappe.set_user(self.sales)
        mark_notification_read(first["id"])
        unread = list_notifications(page=1, page_size=1, unread_only=True)
        self.assertEqual(unread["total"], 1)
        self.assertEqual(len(unread["items"]), 1)
        result = mark_all_notifications_read()
        self.assertEqual(result["updated"], 1)
        self.assertTrue(result["readAt"].endswith("Z"))
        self.assertEqual(list_notifications(unread_only=True)["total"], 0)

        frappe.set_user(self.other_sales)
        other = list_notifications(unread_only=True)
        self.assertEqual(other["total"], 1)
        self.assertEqual(other["items"][0]["title"], "Other recipient")
