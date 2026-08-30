from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.account import change_password


class TestAccountApi(FrappeTestCase):
    def test_change_password_logs_out_other_sessions(self):
        user_id = frappe.session.user

        with patch("rayher_crm.api.v1.account.resolve_crm_role"), patch(
            "rayher_crm.api.v1.account.check_password"
        ), patch("rayher_crm.api.v1.account.update_password") as update_password:
            result = change_password.__wrapped__("Current123", "Replacement456")

        update_password.assert_called_once_with(
            user_id,
            "Replacement456",
            logout_all_sessions=True,
        )
        self.assertEqual(result["data"], {"updated": True})
