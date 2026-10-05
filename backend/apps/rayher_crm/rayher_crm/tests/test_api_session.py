from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request

from rayher_crm.security.api_session import require_session_for_crm_api


BOOTSTRAP = "rayher_crm.api.v1.bootstrap.get_bootstrap"
HEALTH = "rayher_crm.api.v1.health.get_health"


class TestApiSession(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        self.original_request = getattr(frappe.local, "request", None)
        self.original_form_dict = frappe.local.form_dict
        self.original_disable_traceback = frappe.local.flags.disable_traceback

    def tearDown(self):
        frappe.local.request = self.original_request
        frappe.local.form_dict = self.original_form_dict
        frappe.local.flags.disable_traceback = self.original_disable_traceback
        frappe.set_user(self.original_user)
        super().tearDown()

    def _request(self, user: str, path: str, method: str = "GET", command: str | None = None) -> None:
        frappe.set_user(user)
        set_request(method=method, path=path)
        frappe.local.form_dict = frappe._dict({"cmd": command} if command else {})
        require_session_for_crm_api()

    def test_hook_is_registered_and_answers_401(self):
        self.assertIn(
            "rayher_crm.security.api_session.require_session_for_crm_api",
            frappe.get_hooks("auth_hooks"),
        )
        self.assertEqual(frappe.AuthenticationError.http_status_code, 401)

    def test_guest_call_to_the_crm_api_is_unauthenticated(self):
        calls = (
            ("GET", f"/api/method/{BOOTSTRAP}", None),
            ("POST", "/api/method/rayher_crm.api.v1.accounts.create_account", None),
            ("GET", f"/api/v1/method/{BOOTSTRAP}", None),
            ("GET", f"/api/v2/method/{BOOTSTRAP}", None),
            ("GET", "/api/method/rayher_crm.api.v1.accounts.no_such_method", None),
            # Frappe's v1 route takes the first path segment as the method and ignores the rest.
            ("GET", f"/api/method/{BOOTSTRAP}/anything", None),
            ("GET", f"/api/v1/method/{BOOTSTRAP}/anything/else", None),
            ("POST", "/", BOOTSTRAP),
            # Frappe runs `cmd` before it looks at the path, so `cmd` decides.
            ("GET", f"/api/method/{HEALTH}", BOOTSTRAP),
        )
        for method, path, command in calls:
            with self.subTest(method=method, path=path, command=command):
                frappe.local.flags.disable_traceback = False
                with self.assertRaises(frappe.AuthenticationError):
                    self._request("Guest", path, method, command)
                self.assertTrue(frappe.local.flags.disable_traceback)

    def test_guest_keeps_the_health_check_and_everything_outside_the_crm_api(self):
        for path in (
            f"/api/method/{HEALTH}",
            "/api/method/login",
            "/api/method/frappe.ping",
            "/api/resource/User",
            "/crm",
            "/login",
        ):
            with self.subTest(path=path):
                self._request("Guest", path)
        self._request("Guest", f"/api/method/{BOOTSTRAP}", command="frappe.ping")
        self._request("Guest", f"/api/method/{HEALTH}/anything")
        # Two segments under v2 name a DocType method, which is Frappe's to refuse.
        self._request("Guest", f"/api/v2/method/Customer/{BOOTSTRAP}")
        self._request("Guest", "/", "POST", HEALTH)

    def test_preflight_and_signed_in_calls_pass(self):
        self._request("Guest", f"/api/method/{BOOTSTRAP}", "OPTIONS")
        self._request("Administrator", f"/api/method/{BOOTSTRAP}")
        self._request("Administrator", "/", "POST", BOOTSTRAP)
