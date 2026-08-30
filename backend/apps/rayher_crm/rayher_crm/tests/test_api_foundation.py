from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.bootstrap import get_bootstrap
from rayher_crm.api.v1.health import get_health
from rayher_crm.api.v1.responses import success_response


SENSITIVE_KEY_PARTS = ("password", "secret", "token", "cookie", "session", "database")


def _all_keys(value):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key).lower()
            yield from _all_keys(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            yield from _all_keys(child)


class TestApiFoundation(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _create_user_without_crm_role(self) -> str:
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": "crm-api-no-role-test@example.invalid",
                "first_name": "No Role",
                "enabled": 1,
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True).name

    def test_success_response_has_stable_envelope_and_unique_request_ids(self):
        first = success_response({"value": 1})
        second = success_response({"value": 2}, warnings=("careful",))

        self.assertEqual(first["data"], {"value": 1})
        self.assertEqual(first["warnings"], [])
        self.assertEqual(second["warnings"], ["careful"])
        self.assertNotEqual(first["meta"]["requestId"], second["meta"]["requestId"])
        self.assertRegex(first["meta"]["requestId"], r"^req_[0-9a-f]{24}$")
        self.assertRegex(first["meta"]["generatedAt"], r"^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$")

    def test_health_is_guest_safe_and_redacts_sensitive_state(self):
        frappe.set_user("Guest")

        response = get_health()

        self.assertEqual(response["data"]["status"], "ok")
        self.assertEqual(response["data"]["app"], "rayher_crm")
        self.assertRegex(response["data"]["version"], r"^\d+\.\d+\.\d+$")
        for key in _all_keys(response):
            self.assertFalse(any(part in key for part in SENSITIVE_KEY_PARTS), key)

    def test_administrator_bootstrap_uses_server_identity_and_manager_capabilities(self):
        response = get_bootstrap()

        self.assertEqual(response["data"]["user"]["id"], "Administrator")
        self.assertEqual(response["data"]["user"]["role"], "Manager")
        self.assertEqual(response["data"]["user"]["team"], "Management")
        self.assertIn("account:write", response["data"]["capabilities"])
        self.assertNotIn("system:configure", response["data"]["capabilities"])
        self.assertEqual(response["data"]["version"], response["data"]["appVersion"])
        self.assertEqual(response["data"]["csrfToken"], frappe.session.data.csrf_token)
        self.assertTrue(response["data"]["csrfToken"])
        self.assertNotIn("roles", response["data"]["user"])

    def test_bootstrap_denies_authenticated_user_without_one_crm_role(self):
        user_id = self._create_user_without_crm_role()
        frappe.set_user(user_id)

        response = get_bootstrap()

        self.assertEqual(frappe.local.response["http_status_code"], 403)
        self.assertEqual(response["error"]["code"], "PERMISSION_DENIED")

    def test_bootstrap_personnel_contains_only_enabled_system_users_with_one_crm_role(self):
        sales = frappe.get_doc({
            "doctype": "User",
            "email": "crm-bootstrap-sales@example.invalid",
            "first_name": "Bootstrap Sales",
            "bio": "销售经理",
            "enabled": 1,
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
        sales.add_roles("CRM Sales")
        multiple = frappe.get_doc({
            "doctype": "User",
            "email": "crm-bootstrap-multiple@example.invalid",
            "first_name": "Bootstrap Multiple",
            "enabled": 1,
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
        multiple.add_roles("CRM Sales", "CRM Engineer")

        response = get_bootstrap()
        personnel = {row["id"]: row for row in response["data"]["personnel"]}

        self.assertEqual(personnel[sales.name]["role"], "Sales")
        self.assertEqual(personnel[sales.name]["team"], "销售经理")
        self.assertNotIn(multiple.name, personnel)
