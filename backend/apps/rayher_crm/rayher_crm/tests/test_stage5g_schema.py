from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.concurrency import LOCKABLE_DOCTYPES


class TestStage5GSchema(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")

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

    def test_visit_schema_uses_lightweight_crm_links_and_server_fields(self):
        meta = frappe.get_meta("CRM Visit")
        fields = {field.fieldname: field for field in meta.fields}
        expected = {
            "account": ("Link", "Customer"),
            "primary_contact": ("Link", "Contact"),
            "opportunity": ("Link", "CRM Opportunity"),
            "visit_owner": ("Link", "User"),
            "subject": ("Data", None),
            "visit_date": ("Date", None),
            "visit_type": ("Select", None),
            "status": ("Select", None),
            "objective": ("Small Text", None),
            "outcome": ("Small Text", None),
            "next_action": ("Data", None),
            "action_owner": ("Link", "User"),
            "due": ("Date", None),
            "action_done": ("Check", None),
            "created_by_user": ("Link", "User"),
        }
        for fieldname, (fieldtype, options) in expected.items():
            self.assertIn(fieldname, fields)
            self.assertEqual(fields[fieldname].fieldtype, fieldtype)
            if options:
                self.assertEqual(fields[fieldname].options, options)
        self.assertTrue(meta.autoname.startswith("format:CRM-VIS-"))
        self.assertNotIn("Project", {field.options for field in meta.fields})
        self.assertNotIn("Task", {field.options for field in meta.fields})
        self.assertIn("CRM Visit", LOCKABLE_DOCTYPES)

    def test_visit_permissions_and_query_scope_are_role_specific(self):
        manager = self._user("crm-stage5g-manager@example.invalid", "CRM Manager")
        sales = self._user("crm-stage5g-sales@example.invalid", "CRM Sales")
        engineer = self._user("crm-stage5g-engineer@example.invalid", "CRM Engineer")
        roles = {row.role: row for row in frappe.get_meta("CRM Visit").permissions}
        self.assertTrue(roles["CRM Manager"].read and roles["CRM Manager"].write)
        self.assertTrue(roles["CRM Sales"].read and roles["CRM Sales"].write)
        self.assertFalse(bool(roles["CRM Engineer"].read))
        self.assertFalse(bool(roles["CRM Engineer"].write))
        self.assertEqual(conditions_for_doctype("CRM Visit", manager), "1=1")
        self.assertIn("visit_owner", conditions_for_doctype("CRM Visit", sales))
        self.assertEqual(conditions_for_doctype("CRM Visit", engineer), "1=0")
        self.assertEqual(conditions_for_doctype("CRM Visit", "Guest"), "1=0")

    def test_contact_has_legacy_stakeholder_compatibility_fields(self):
        meta = frappe.get_meta("Contact")
        role = meta.get_field("custom_crm_buying_role")
        influence = meta.get_field("custom_crm_influence")
        self.assertIsNotNone(role)
        self.assertEqual(role.fieldtype, "Select")
        self.assertIn("Decision Maker", role.options)
        self.assertIsNotNone(influence)
        self.assertEqual(influence.options, "High\nMedium\nLow")
