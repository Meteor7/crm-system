import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.permissions.roles import (
    CRM_ENGINEER_ROLE,
    CRM_MANAGER_ROLE,
    CRM_SALES_ROLE,
    ROLE_CAPABILITIES,
    install_roles,
    resolve_crm_role,
)


class TestCrmRoles(FrappeTestCase):
    def _create_user(self, email: str, roles: tuple[str, ...] = ()) -> str:
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "CRM",
                "last_name": "Test User",
                "enabled": 1,
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
        if roles:
            user.add_roles(*roles)
        return user.name

    def test_capability_matrix_is_server_owned_and_role_specific(self):
        self.assertNotIn("system:configure", ROLE_CAPABILITIES["Manager"])
        self.assertNotIn("account_report:export", ROLE_CAPABILITIES["Manager"])
        self.assertNotIn("dashboard:management", ROLE_CAPABILITIES["Manager"])
        self.assertIn("account:write", ROLE_CAPABILITIES["Sales"])
        self.assertNotIn("account:write", ROLE_CAPABILITIES["Engineer"])
        self.assertIn("evaluation:write", ROLE_CAPABILITIES["Engineer"])
        self.assertNotIn("visit:view", ROLE_CAPABILITIES["Engineer"])
        self.assertIn("deal:rollback", ROLE_CAPABILITIES["Manager"])
        self.assertNotIn("deal:rollback", ROLE_CAPABILITIES["Sales"])
        self.assertNotIn("deal:rollback", ROLE_CAPABILITIES["Engineer"])
        self.assertIn("deal:internal_validation_approve", ROLE_CAPABILITIES["Manager"])
        self.assertNotIn("deal:internal_validation_approve", ROLE_CAPABILITIES["Sales"])
        self.assertNotIn("deal:internal_validation_approve", ROLE_CAPABILITIES["Engineer"])
        self.assertIn("quotation:submit", ROLE_CAPABILITIES["Sales"])
        self.assertNotIn("quotation:publish", ROLE_CAPABILITIES["Sales"])
        self.assertNotIn("quotation:approve", ROLE_CAPABILITIES["Sales"])
        self.assertIn("quotation:approve", ROLE_CAPABILITIES["Manager"])

    def test_role_installation_is_idempotent(self):
        install_roles()
        install_roles()

        for role in (CRM_MANAGER_ROLE, CRM_SALES_ROLE, CRM_ENGINEER_ROLE):
            self.assertTrue(frappe.db.exists("Role", role))

    def test_administrator_is_manager(self):
        self.assertEqual(resolve_crm_role("Administrator"), "Manager")

    def test_normal_user_maps_from_single_server_role(self):
        user = self._create_user("crm-sales-role-test@example.invalid", (CRM_SALES_ROLE,))

        self.assertEqual(resolve_crm_role(user), "Sales")

    def test_user_without_crm_role_is_denied(self):
        user = self._create_user("crm-no-role-test@example.invalid")

        with self.assertRaises(frappe.PermissionError):
            resolve_crm_role(user)

    def test_conflicting_crm_roles_are_denied(self):
        user = self._create_user(
            "crm-conflicting-role-test@example.invalid",
            (CRM_SALES_ROLE, CRM_ENGINEER_ROLE),
        )

        with self.assertRaises(frappe.PermissionError):
            resolve_crm_role(user)
