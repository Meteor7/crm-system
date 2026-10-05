from __future__ import annotations

import frappe
from frappe.permissions import add_user_permission, remove_user_permission
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.notification_scope import SOURCE_DOCTYPES, source_condition
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.notifications import (
    create_notification,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    notify_if_reachable,
)
from rayher_crm.setup.indexes import (
    NOTIFICATION_RECIPIENT_CREATED_INDEX,
    NOTIFICATION_RECIPIENT_UNREAD_CREATED_INDEX,
    NOTIFICATION_SOURCE_INDEX,
    install_notification_indexes,
)


class TestNotificationApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-notification-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-notification-other@example.invalid", "CRM Sales")
        self.manager = self._user("crm-notification-manager@example.invalid", "CRM Manager")
        from rayher_crm.services.accounts import create_account
        self.accounts = {}
        for user in (self.sales, self.other_sales, self.manager):
            frappe.set_user(user)
            account = create_account({
                "name": f"Inbox scope {frappe.generate_hash(length=8)}", "shortName": "Inbox",
                "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": "East", "owner": user,
            })
            self.accounts[user] = account["id"]
        frappe.set_user("Administrator")
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
            source_doctype="Customer", source_name=self.accounts[recipient],
        )

    def test_source_scope_requires_native_read_before_matching(self):
        with (
            patch("rayher_crm.permissions.notification_scope.frappe.has_permission", return_value=False),
            patch("rayher_crm.permissions.notification_scope.DatabaseQuery.build_match_conditions") as build,
        ):
            self.assertEqual(source_condition("Customer", self.sales), "1=0")
            build.assert_not_called()

    def test_source_scope_preserves_all_native_and_service_conditions(self):
        def build(query):
            self.assertEqual(query.reference_doctype, "Customer")
            self.assertEqual(query.get_permission_query_conditions(), "")
            query.conditions.append("native_share_scope")
            return "native_match_scope"

        with (
            patch("rayher_crm.permissions.notification_scope.frappe.has_permission", return_value=True),
            patch("rayher_crm.permissions.notification_scope.DatabaseQuery.build_match_conditions", build),
            patch("rayher_crm.permissions.scope.conditions_for_doctype", return_value="service_scope"),
        ):
            self.assertEqual(
                source_condition("Customer", self.sales),
                "(native_share_scope) AND (native_match_scope) AND (service_scope)",
            )

    def test_source_scope_keeps_literal_percents_in_bound_and_unbound_sql(self):
        def build(query):
            query.conditions.append("`tabCustomer`.`name` LIKE 'share%'")
            return "`tabCustomer`.`name` = '100% Customer'"

        with (
            patch("rayher_crm.permissions.notification_scope.frappe.has_permission", return_value=True),
            patch("rayher_crm.permissions.notification_scope.DatabaseQuery.build_match_conditions", build),
            patch(
                "rayher_crm.permissions.scope.conditions_for_doctype",
                return_value=(
                    "`tabCustomer`.`owner` = 'service%%user' AND "
                    "`tabCustomer`.`customer_name` = 'two%%%%signs'"
                ),
            ) as service_scope,
        ):
            unbound = source_condition("Customer", self.sales)
            bound = source_condition("Customer", self.sales, for_bound_query=True)
        self.assertIn("LIKE 'share%'", unbound)
        self.assertIn("= '100% Customer'", unbound)
        self.assertIn("= 'service%user'", unbound)
        self.assertIn("= 'two%%signs'", unbound)
        self.assertIn("LIKE 'share%%'", bound)
        self.assertIn("= '100%% Customer'", bound)
        self.assertIn("= 'service%%user'", bound)
        self.assertIn("= 'two%%%%signs'", bound)
        self.assertEqual(service_scope.call_count, 2)
        self.assertTrue(all(call.kwargs["for_bound_query"] for call in service_scope.call_args_list))
        rendered = ("SELECT name FROM `tabCustomer` WHERE name=%s AND (" + bound + ")") % "'source'"
        self.assertIn("= '100% Customer'", rendered)
        self.assertIn("= 'service%user'", rendered)
        self.assertIn("= 'two%%signs'", rendered)

    def test_bound_notification_scope_propagates_to_child_sources(self):
        from rayher_crm.permissions.notification_scope import notification_condition

        with (
            patch("rayher_crm.permissions.notification_scope.SOURCE_DOCTYPES", ("CRM Opportunity Action",)),
            patch("rayher_crm.permissions.notification_scope.source_condition", return_value="1=1") as source,
        ):
            notification_condition(self.sales, for_bound_query=True)
        source.assert_called_once_with("CRM Opportunity Action", self.sales, for_bound_query=True)

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

    def test_disabled_and_role_revoked_recipient_loses_history_and_receives_no_new_notice(self):
        from frappe.client import get, get_list

        for reason in ("disabled", "role_removed"):
            with self.subTest(reason=reason):
                frappe.set_user(self.manager)
                event = self._event(self.sales, f"Before {reason}")
                frappe.set_user("Administrator")
                user = frappe.get_doc("User", self.sales)
                enabled, roles = user.enabled, [row.role for row in user.roles]
                if reason == "disabled":
                    user.enabled = 0
                else:
                    user.set("roles", [{"role": role} for role in roles if not role.startswith("CRM ")])
                user.save(ignore_permissions=True)
                frappe.clear_cache(user=self.sales)
                try:
                    frappe.set_user(self.manager)
                    before = frappe.db.count("CRM Notification Event", {"recipient_user": self.sales})
                    self.assertIsNone(notify_if_reachable(
                        recipient=self.sales, category="Account", title="After revocation",
                        message="Hidden", route="/accounts", source_doctype="Customer",
                        source_name=self.accounts[self.sales],
                    ))
                    self.assertEqual(frappe.db.count("CRM Notification Event", {"recipient_user": self.sales}), before)
                    frappe.set_user(self.sales)
                    if reason == "disabled":
                        self.assertEqual(list_notifications(page_size=1)["total"], 0)
                        self.assertEqual(list_notifications(unread_only=True)["items"], [])
                        self.assertEqual(mark_all_notifications_read()["updated"], 0)
                        with self.assertRaises(CrmApiException):
                            mark_notification_read(event["id"])
                    else:
                        for operation in (list_notifications, mark_all_notifications_read,
                                          lambda: mark_notification_read(event["id"])):
                            with self.assertRaises(frappe.PermissionError):
                                operation()
                    if reason == "disabled":
                        self.assertEqual(get_list("CRM Notification Event", filters={"name": event["id"]}), [])
                    else:
                        with self.assertRaises(frappe.PermissionError):
                            get_list("CRM Notification Event", filters={"name": event["id"]})
                    with self.assertRaises(frappe.PermissionError):
                        get("CRM Notification Event", event["id"])
                    self.assertIsNone(frappe.db.get_value("CRM Notification Event", event["id"], "read_at"))
                finally:
                    frappe.set_user("Administrator")
                    user.reload()
                    user.enabled = enabled
                    user.set("roles", [{"role": role} for role in roles])
                    user.save(ignore_permissions=True)
                    frappe.clear_cache(user=self.sales)

    def test_source_transfer_revokes_list_total_detail_and_all_read_mutations(self):
        from frappe.client import get, get_list
        frappe.set_user(self.manager)
        event = self._event(self.sales, "Before transfer")
        frappe.set_user(self.sales)
        self.assertEqual(list_notifications()["total"], 1)
        self.assertEqual(get("CRM Notification Event", event["id"])["name"], event["id"])
        frappe.db.set_value("Customer", self.accounts[self.sales], {"custom_crm_owner": self.other_sales, "custom_crm_visibility": "Private"})
        self.assertEqual(list_notifications()["total"], 0)
        self.assertEqual(list_notifications()["items"], [])
        self.assertEqual(get_list("CRM Notification Event", filters={"name": event["id"]}), [])
        with self.assertRaises(frappe.PermissionError):
            get("CRM Notification Event", event["id"])
        with self.assertRaises(CrmApiException) as denied:
            mark_notification_read(event["id"])
        self.assertEqual(denied.exception.code, "NOT_FOUND")
        self.assertEqual(mark_all_notifications_read()["updated"], 0)
        self.assertIsNone(frappe.db.get_value("CRM Notification Event", event["id"], "read_at"))

    def test_missing_unknown_and_deleted_sources_do_not_leave_readable_copies(self):
        frappe.set_user(self.manager)
        event = self._event(self.sales, "Legacy source")
        for values in (
            {"source_doctype": None, "source_name": None},
            {"source_doctype": "User", "source_name": self.sales},
            {"source_doctype": "Customer", "source_name": "missing-customer"},
        ):
            frappe.db.set_value("CRM Notification Event", event["id"], values)
            frappe.set_user(self.sales)
            self.assertEqual(list_notifications()["total"], 0)
            with self.assertRaises(CrmApiException):
                mark_notification_read(event["id"])
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as invalid:
            create_notification(recipient=self.sales, category="Account", title="No source", message="Invalid", route="/accounts")
        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")

    def test_informational_out_of_scope_skip_does_not_swallow_database_errors(self):
        frappe.set_user(self.manager)
        fields = dict(category="Account", title="Assigned", message="Account changed", route="/accounts",
            source_doctype="Customer", source_name=self.accounts[self.sales])
        frappe.db.set_value("Customer", self.accounts[self.sales], "custom_crm_visibility", "Private")
        self.assertIsNone(notify_if_reachable(recipient=self.other_sales, **fields))
        with self.assertRaises(CrmApiException) as denied:
            create_notification(recipient=self.other_sales, **fields)
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        with patch("rayher_crm.services.notifications.create_notification", side_effect=RuntimeError("DB write failed")):
            with self.assertRaises(RuntimeError):
                notify_if_reachable(recipient=self.sales, **fields)

    def test_public_account_contact_assignment_uses_service_scope_for_notification(self):
        account = self.accounts[self.other_sales]
        frappe.db.set_value("Customer", account, "custom_crm_visibility", "Public")
        frappe.set_user(self.manager)

        contact = create_contact({
            "accountId": account,
            "name": "Public account assignee",
            "title": "Director",
            "department": "Engineering",
            "relationship": "Developing",
            "owner": self.sales,
            "status": "Active",
        })

        self.assertEqual(contact["owner"], self.sales)
        self.assertTrue(frappe.db.exists("CRM Notification Event", {
            "recipient_user": self.sales,
            "source_doctype": "Contact",
            "source_name": contact["id"],
            "title": "Contact assigned",
        }))

    def test_source_condition_fails_closed_when_permission_matching_drifts(self):
        with patch(
            "rayher_crm.permissions.notification_scope.DatabaseQuery.build_match_conditions",
            side_effect=frappe.PermissionError,
        ):
            self.assertEqual(source_condition("Customer", self.sales), "1=0")

    def test_source_scope_uses_target_user_permissions_and_applicable_for(self):
        from frappe.client import get, get_list

        allowed = self.accounts[self.manager]
        denied = self.accounts[self.other_sales]
        frappe.set_user(self.manager)
        allowed_event = create_notification(
            recipient=self.manager, category="Account", title="Allowed account",
            message="Allowed", route="/accounts", source_doctype="Customer", source_name=allowed,
        )
        denied_event = create_notification(
            recipient=self.manager, category="Account", title="Denied account",
            message="Denied", route="/accounts", source_doctype="Customer", source_name=denied,
        )

        frappe.set_user("Administrator")
        add_user_permission("Customer", allowed, self.manager, ignore_permissions=True)
        frappe.clear_cache(user=self.manager)
        try:
            frappe.set_user(self.manager)
            self.assertEqual(
                {row["name"] for row in get_list(
                    "Customer", filters={"name": ["in", [allowed, denied]]}, fields=["name"], limit_page_length=20,
                )},
                {allowed},
            )
            self.assertEqual(
                {item["id"] for item in list_notifications(page_size=20)["items"]},
                {allowed_event["id"]},
            )
            with self.assertRaises(frappe.PermissionError):
                get("CRM Notification Event", denied_event["id"])
            with self.assertRaises(CrmApiException) as out_of_scope:
                create_notification(
                    recipient=self.manager, category="Account", title="Blocked",
                    message="Blocked", route="/accounts", source_doctype="Customer", source_name=denied,
                )
            self.assertEqual(out_of_scope.exception.code, "SCOPE_DENIED")

            frappe.set_user("Administrator")
            remove_user_permission("Customer", allowed, self.manager, ignore_permissions=True)
            add_user_permission(
                "Customer", allowed, self.manager,
                ignore_permissions=True, applicable_for="Address",
            )
            frappe.clear_cache(user=self.manager)
            frappe.set_user(self.manager)
            self.assertEqual(
                {row["name"] for row in get_list(
                    "Customer", filters={"name": ["in", [allowed, denied]]}, fields=["name"], limit_page_length=20,
                )},
                {allowed, denied},
            )
            self.assertEqual(
                {item["id"] for item in list_notifications(page_size=20)["items"]},
                {allowed_event["id"], denied_event["id"]},
            )
            self.assertEqual(
                create_notification(
                    recipient=self.manager, category="Account", title="Address-only permission",
                    message="Visible", route="/accounts", source_doctype="Customer", source_name=denied,
                )["recipientId"],
                self.manager,
            )
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", allowed, self.manager, ignore_permissions=True)
            frappe.clear_cache(user=self.manager)

    def test_notification_indexes_and_query_plans_are_selective(self):
        from rayher_crm.permissions.scope import conditions_for_doctype

        install_notification_indexes()
        install_notification_indexes()
        rows = frappe.db.sql(
            """SELECT `INDEX_NAME`, `COLUMN_NAME`, `SEQ_IN_INDEX`
               FROM information_schema.STATISTICS
               WHERE `TABLE_SCHEMA` = DATABASE()
                 AND `TABLE_NAME` = 'tabCRM Notification Event'
               ORDER BY `INDEX_NAME`, `SEQ_IN_INDEX`""",
            as_dict=True,
        )
        columns: dict[str, list[str]] = {}
        for row in rows:
            columns.setdefault(row.INDEX_NAME, []).append(row.COLUMN_NAME)
        self.assertEqual(
            columns[NOTIFICATION_RECIPIENT_CREATED_INDEX],
            ["recipient_user", "created_at", "name"],
        )
        self.assertEqual(
            columns[NOTIFICATION_RECIPIENT_UNREAD_CREATED_INDEX],
            ["recipient_user", "read_at", "created_at", "name"],
        )
        self.assertEqual(
            columns[NOTIFICATION_SOURCE_INDEX],
            ["source_doctype", "source_name"],
        )

        condition = conditions_for_doctype("CRM Notification Event", self.manager)
        queries = (
            f"SELECT COUNT(*) FROM `tabCRM Notification Event` WHERE ({condition}) AND `recipient_user`=%s",
            f"SELECT COUNT(*) FROM `tabCRM Notification Event` WHERE ({condition}) AND `recipient_user`=%s AND `read_at` IS NULL",
            "SELECT `name` FROM `tabCRM Notification Event` "
            f"WHERE ({condition}) AND `recipient_user`=%s "
            "ORDER BY `created_at` DESC, `name` DESC LIMIT 20",
        )
        source_tables = {f"tab{doctype}" for doctype in SOURCE_DOCTYPES}
        for query in queries:
            plan = frappe.db.sql("EXPLAIN " + query, (self.manager,), as_dict=True)
            event = next(row for row in plan if row.table == "tabCRM Notification Event")
            self.assertNotIn(event.type, {"ALL", "index"}, plan)
            self.assertIn(
                event.key,
                {NOTIFICATION_RECIPIENT_CREATED_INDEX, NOTIFICATION_RECIPIENT_UNREAD_CREATED_INDEX},
                plan,
            )
            self.assertFalse(any(row.select_type == "MATERIALIZED" for row in plan), plan)
            self.assertFalse(
                any(row.table in source_tables and row.type in {"ALL", "index"} for row in plan),
                plan,
            )

    def test_old_notification_share_is_removed_and_new_shares_cannot_bypass_scope(self):
        from rayher_crm.permissions.scope import install_crm_doc_permissions
        event = self._event(self.sales, "No durable share")
        share = frappe.get_doc({"doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "CRM Notification Event", "share_name": event["id"], "user": self.other_sales, "read": 1})
        share.db_insert()
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", share.name))
        replacement = frappe.get_doc({"doctype": "DocShare", "share_doctype": "CRM Notification Event",
            "share_name": event["id"], "user": self.other_sales, "read": 1})
        replacement.flags.ignore_share_permission = True
        with self.assertRaises(frappe.PermissionError):
            replacement.insert(ignore_permissions=True)
