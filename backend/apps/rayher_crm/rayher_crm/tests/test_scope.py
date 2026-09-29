from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.permissions.scope import (
    MUTATING_PERMISSIONS,
    SCOPED_DOCTYPES,
    conditions_for_doctype,
    has_crm_permission,
    install_crm_doc_permissions,
)
from rayher_crm.services.sites import create_site


class TestCrmScope(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        install_crm_doc_permissions()
        frappe.clear_cache()

        self.manager = self._create_user("crm-scope-manager@example.invalid", "CRM Manager")
        self.sales = self._create_user("crm-scope-sales@example.invalid", "CRM Sales")
        self.other_sales = self._create_user("crm-scope-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._create_user("crm-scope-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._create_user("crm-scope-other-engineer@example.invalid", "CRM Engineer")

        self.owned_customer = self._create_customer("Scope Owned Customer", self.sales)
        self.foreign_customer = self._create_customer("Scope Foreign Customer", self.other_sales)
        frappe.db.set_value(
            "Customer", self.foreign_customer, "custom_crm_visibility", "Public", update_modified=False,
        )
        frappe.get_doc(
            {
                "doctype": "CRM Account Engineer Assignment",
                "customer": self.owned_customer,
                "engineer": self.engineer,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        self.owned_contact = self._create_contact("Owned Contact", self.owned_customer, self.sales)
        self.foreign_contact = self._create_contact("Foreign Contact", self.foreign_customer, self.other_sales)
        self.owned_lead = self._create_lead("Owned Lead", self.sales, self.owned_customer)
        self.foreign_lead = self._create_lead("Foreign Lead", self.other_sales, self.foreign_customer)
        self.owned_site = create_site(self.owned_customer, self._site_input("Owned Scope Site"))["id"]
        self.foreign_site = create_site(self.foreign_customer, self._site_input("Foreign Scope Site"))["id"]
        self.owned_opportunity = self._create_opportunity(
            "Owned Opportunity", self.owned_customer, self.owned_site, self.owned_lead, self.sales
        )
        self.foreign_opportunity = self._create_opportunity(
            "Foreign Opportunity", self.foreign_customer, self.foreign_site, self.foreign_lead, self.other_sales
        )
        self.owned_booking = self._create_booking(
            self.owned_customer, self.owned_contact, self.owned_opportunity, self.sales
        )
        self.foreign_booking = self._create_booking(
            self.foreign_customer, self.foreign_contact, self.foreign_opportunity, self.other_sales
        )
        self.owned_tool = self._create_installed_tool(
            self.owned_customer, self.owned_site, self.owned_booking, self.owned_opportunity,
            self.sales, self.engineer, f"SCOPE-OWNED-{frappe.generate_hash(length=10)}",
        )
        self.foreign_tool = self._create_installed_tool(
            self.foreign_customer, self.foreign_site, self.foreign_booking, self.foreign_opportunity,
            self.other_sales, self.other_engineer, f"SCOPE-FOREIGN-{frappe.generate_hash(length=10)}",
        )
        self.owned_demo_request = self._create_demo_request(
            self.owned_customer, self.owned_contact, self.owned_opportunity, self.sales, self.engineer,
        )
        self.foreign_demo_request = self._create_demo_request(
            self.foreign_customer, self.foreign_contact, self.foreign_opportunity,
            self.other_sales, self.other_engineer,
        )
        self.owned_evaluation = self._create_evaluation(
            self.owned_customer, self.owned_demo_request, self.engineer,
        )
        self.foreign_evaluation = self._create_evaluation(
            self.foreign_customer, self.foreign_demo_request, self.other_engineer,
        )

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _create_user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@", 1)[0],
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True).name

    def _create_customer(self, customer_name: str, owner: str) -> str:
        return frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": customer_name,
                "customer_type": "Company",
                "customer_group": "CRM Customers",
                "territory": "CRM Territory",
                "custom_crm_owner": owner,
            }
        ).insert(ignore_permissions=True).name

    def _create_contact(self, first_name: str, customer: str, owner: str) -> str:
        contact = frappe.get_doc(
            {
                "doctype": "Contact",
                "first_name": first_name,
                "custom_crm_owner": owner,
                "custom_crm_relationship": "Developing",
                "custom_crm_status": "Active",
                "custom_crm_data_quality": "Needs Review",
            }
        )
        contact.append("links", {"link_doctype": "Customer", "link_name": customer})
        return contact.insert(ignore_permissions=True).name

    def _create_lead(self, first_name: str, owner: str, customer: str) -> str:
        return frappe.get_doc(
            {
                "doctype": "Lead",
                "first_name": first_name,
                "company_name": f"{first_name} Company",
                "status": "Lead",
                "lead_owner": owner,
                "custom_crm_source": "Website",
                "custom_crm_status": "New",
                "custom_crm_converted_account": customer,
            }
        ).insert(ignore_permissions=True).name

    def _site_input(self, name: str) -> dict:
        return {"name": name, "city": "Shanghai", "type": "Fab", "process": "Frontend", "status": "量产"}

    def _create_opportunity(self, title: str, customer: str, site: str, lead: str, owner: str) -> str:
        return frappe.get_doc(
            {
                "doctype": "CRM Opportunity",
                "account": customer,
                "site": site,
                "source_lead": lead,
                "title": title,
                "amount": 1000,
                "original_amount": 1000,
                "currency": "CNY",
                "po_date": "2026-12-31",
                "opportunity_owner": owner,
                "tool_type": "Inspection",
                "stage": "qualified_opportunity",
                "forecast": "Pipeline",
                "probability": 20,
                "score": 20,
                "sale_type": "New Equipment",
                "sub_region": "East China",
            }
        ).insert(ignore_permissions=True).name

    def _create_booking(self, customer: str, contact: str, opportunity: str, owner: str) -> str:
        return frappe.get_doc({
            "doctype": "CRM Booking", "account": customer, "primary_contact": contact,
            "equipment": "Inspection", "quantity": 1, "ddl": "2026-12-31", "amount": 1000,
            "currency": "CNY", "status": "Confirmed", "booking_date": "2026-08-04",
            "booking_owner": owner, "source": "Opportunity", "source_opportunity": opportunity,
        }).insert(ignore_permissions=True).name

    def _create_installed_tool(
        self, customer: str, site: str, booking: str, opportunity: str,
        sales_owner: str, engineer_owner: str, serial: str,
    ) -> str:
        tool = frappe.get_doc({
            "doctype": "CRM Installed Tool", "account": customer, "site": site,
            "serial": serial, "model": "Model X", "location": "Fab", "status": "Delivery Preparation",
            "software": "Pending", "firmware": "Pending", "warranty_end": "2027-12-31", "completeness": 55,
            "source_booking": booking, "source_opportunity": opportunity, "sales_owner": sales_owner,
            "engineer_owner": engineer_owner, "ownership_type": "Customer Owned",
        }).insert(ignore_permissions=True)
        frappe.db.set_value("CRM Booking", booking, "installed_tool", tool.name, update_modified=False)
        return tool.name

    def _create_demo_request(
        self, customer: str, contact: str, opportunity: str, sales_owner: str, engineer_owner: str,
    ) -> str:
        return frappe.get_doc({
            "doctype": "CRM Demo Request", "account": customer, "primary_contact": contact,
            "opportunity": opportunity, "sales_owner": sales_owner, "created_by_user": sales_owner,
            "title": "Scope Demo Request", "objective": "Validate row scope",
            "requested_equipment": "Inspection", "sample_type": "Wafer", "sample_quantity": 1,
            "target_date": "2026-12-31", "customer_expected_date": "2026-12-31",
            "priority": "Medium", "acceptance_criteria": "Scope is enforced", "status": "Draft",
            "engineer_owner": engineer_owner, "form_data": {},
        }).insert(ignore_permissions=True).name

    def _create_evaluation(self, customer: str, demo_request: str, owner: str) -> str:
        return frappe.get_doc({
            "doctype": "CRM Evaluation", "account": customer, "demo_request": demo_request,
            "title": "Scope Evaluation", "status": "Requested", "evaluation_owner": owner,
            "planned_end": "2026-12-31", "acceptance": "Pending", "report_status": "Not Ready",
        }).insert(ignore_permissions=True).name

    def _visible_names(self, doctype: str, user: str) -> set[str]:
        frappe.set_user(user)
        return set(frappe.get_list(doctype, pluck="name"))

    def test_manager_and_sales_see_owned_and_public_customers(self):
        manager_names = self._visible_names("Customer", self.manager)
        self.assertIn(self.owned_customer, manager_names)
        self.assertIn(self.foreign_customer, manager_names)

        sales_names = self._visible_names("Customer", self.sales)
        self.assertIn(self.owned_customer, sales_names)
        self.assertIn(self.foreign_customer, sales_names)
        self.assertIn("custom_crm_visibility", conditions_for_doctype("Customer", self.sales))

    def test_engineer_assignment_controls_customer_contact_and_converted_lead_lists(self):
        self.assertIn(self.owned_customer, self._visible_names("Customer", self.engineer))
        self.assertNotIn(self.foreign_customer, self._visible_names("Customer", self.engineer))
        self.assertIn(self.owned_contact, self._visible_names("Contact", self.engineer))
        self.assertNotIn(self.foreign_contact, self._visible_names("Contact", self.engineer))
        self.assertIn(self.owned_lead, self._visible_names("Lead", self.engineer))
        self.assertNotIn(self.foreign_lead, self._visible_names("Lead", self.engineer))
        self.assertIn(self.owned_opportunity, self._visible_names("CRM Opportunity", self.engineer))
        self.assertNotIn(self.foreign_opportunity, self._visible_names("CRM Opportunity", self.engineer))

    def test_public_contact_service_scope_survives_raw_site_data_guard(self):
        reassigned_contact = self._create_contact(
            "Reassigned Foreign Contact", self.foreign_customer, self.sales,
        )

        frappe.set_user(self.sales)
        doc = frappe.get_doc("Contact", reassigned_contact)
        self.assertTrue(has_crm_permission(doc, user=self.sales, permission_type="read"))
        self.assertNotIn(reassigned_contact, self._visible_names("Contact", self.sales))
        self.assertFalse(frappe.has_permission("Contact", "read", doc=doc, user=self.sales))

    def test_standard_list_and_detail_permissions_use_the_same_raw_scope(self):
        for doctype, owned_name, foreign_name, shared in (
            ("Customer", self.owned_customer, self.foreign_customer, True),
            ("Contact", self.owned_contact, self.foreign_contact, False),
            ("Lead", self.owned_lead, self.foreign_lead, False),
            ("CRM Opportunity", self.owned_opportunity, self.foreign_opportunity, False),
            ("CRM Booking", self.owned_booking, self.foreign_booking, False),
            ("CRM Installed Tool", self.owned_tool, self.foreign_tool, False),
        ):
            visible = self._visible_names(doctype, self.sales)
            self.assertIn(owned_name, visible)
            self.assertEqual(foreign_name in visible, shared)
            self.assertTrue(frappe.has_permission(doctype, "read", doc=owned_name, user=self.sales))
            self.assertEqual(frappe.has_permission(doctype, "read", doc=foreign_name, user=self.sales), shared)

    def test_guest_is_denied_while_sales_customer_scope_stays_shared(self):
        self.assertEqual(conditions_for_doctype("Customer", "Guest"), "1=0")
        self.assertIn(self.foreign_customer, self._visible_names("Customer", self.sales))

        foreign = frappe.get_doc("Customer", self.foreign_customer)
        foreign.custom_crm_owner = self.sales
        self.assertTrue(frappe.has_permission("Customer", "read", doc=foreign, user=self.sales))

    def test_private_parent_cannot_be_bypassed_by_sales_child_ownership(self):
        frappe.set_user("Administrator")
        private_customer = self._create_customer("Scope Private Parent", self.other_sales)
        frappe.db.set_value(
            "Customer", private_customer, "custom_crm_visibility", "Private", update_modified=False,
        )
        private_contact = self._create_contact("Private Parent Contact", private_customer, self.other_sales)
        private_lead = self._create_lead("Private Parent Lead", self.sales, private_customer)
        private_site = create_site(private_customer, self._site_input("Private Parent Site"))["id"]
        private_opportunity = self._create_opportunity(
            "Private Parent Opportunity", private_customer, private_site, private_lead, self.sales,
        )
        private_booking = self._create_booking(
            private_customer, private_contact, private_opportunity, self.sales,
        )
        private_tool = self._create_installed_tool(
            private_customer,
            private_site,
            private_booking,
            private_opportunity,
            self.sales,
            self.other_engineer,
            f"SCOPE-PRIVATE-{frappe.generate_hash(length=10)}",
        )
        private_demo = self._create_demo_request(
            private_customer,
            private_contact,
            private_opportunity,
            self.sales,
            self.other_engineer,
        )
        private_evaluation = self._create_evaluation(
            private_customer, private_demo, self.other_engineer,
        )

        private_records = (
            ("Contact", private_contact),
            ("Lead", private_lead),
            ("CRM Opportunity", private_opportunity),
            ("CRM Booking", private_booking),
            ("CRM Installed Tool", private_tool),
            ("CRM Demo Request", private_demo),
            ("CRM Evaluation", private_evaluation),
        )
        for doctype, name in private_records:
            self.assertNotIn(name, self._visible_names(doctype, self.sales), doctype)
            self.assertFalse(frappe.has_permission(doctype, "read", doc=name, user=self.sales), doctype)

        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Customer", private_customer, "custom_crm_visibility", "Public", update_modified=False,
        )
        raw_site_bearing_doctypes = {"Contact", "CRM Opportunity", "CRM Installed Tool"}
        for doctype, name in private_records:
            doc = frappe.get_doc(doctype, name)
            self.assertTrue(
                has_crm_permission(doc, user=self.sales, permission_type="read"),
                f"{doctype} custom service scope",
            )
            raw_visible = doctype not in raw_site_bearing_doctypes
            self.assertEqual(name in self._visible_names(doctype, self.sales), raw_visible, doctype)
            self.assertEqual(
                frappe.has_permission(doctype, "read", doc=doc, user=self.sales),
                raw_visible,
                doctype,
            )

    def test_opportunity_scope_condition_is_sql_backed_for_all_roles(self):
        self.assertEqual(conditions_for_doctype("CRM Opportunity", self.manager), "1=1")
        self.assertIn(
            "`tabCRM Opportunity`.`opportunity_owner`",
            conditions_for_doctype("CRM Opportunity", self.sales),
        )
        self.assertIn(
            "CRM Account Engineer Assignment",
            conditions_for_doctype("CRM Opportunity", self.engineer),
        )
        self.assertIn("custom_crm_visibility", conditions_for_doctype("CRM Opportunity", self.sales))

    def test_booking_and_installed_tool_scope_is_sql_backed_for_all_roles(self):
        self.assertEqual(conditions_for_doctype("CRM Booking", self.manager), "1=1")
        self.assertIn("`tabCRM Booking`.`booking_owner`", conditions_for_doctype("CRM Booking", self.sales))
        self.assertIn("custom_crm_visibility", conditions_for_doctype("CRM Booking", self.sales))
        self.assertIn("CRM Account Engineer Assignment", conditions_for_doctype("CRM Booking", self.engineer))
        self.assertIn(self.owned_booking, self._visible_names("CRM Booking", self.engineer))
        self.assertNotIn(self.foreign_booking, self._visible_names("CRM Booking", self.engineer))

        self.assertEqual(conditions_for_doctype("CRM Installed Tool", self.manager), "1=1")
        self.assertIn("`tabCRM Installed Tool`.`sales_owner`", conditions_for_doctype("CRM Installed Tool", self.sales))
        self.assertIn("custom_crm_visibility", conditions_for_doctype("CRM Installed Tool", self.sales))
        self.assertNotIn("custom_crm_visibility", conditions_for_doctype("CRM Contact File", self.sales))
        self.assertIn("`tabCRM Installed Tool`.`engineer_owner`", conditions_for_doctype("CRM Installed Tool", self.engineer))
        self.assertIn(self.owned_tool, self._visible_names("CRM Installed Tool", self.engineer))
        self.assertNotIn(self.foreign_tool, self._visible_names("CRM Installed Tool", self.engineer))

    def test_demo_request_scope_is_owner_backed_for_sales_and_engineer(self):
        self.assertEqual(conditions_for_doctype("CRM Demo Request", self.manager), "1=1")
        self.assertIn("`tabCRM Demo Request`.`sales_owner`", conditions_for_doctype("CRM Demo Request", self.sales))
        self.assertIn("custom_crm_visibility", conditions_for_doctype("CRM Demo Request", self.sales))
        self.assertIn(
            "`tabCRM Demo Request`.`engineer_owner`",
            conditions_for_doctype("CRM Demo Request", self.engineer),
        )
        self.assertIn(self.owned_demo_request, self._visible_names("CRM Demo Request", self.sales))
        self.assertNotIn(self.foreign_demo_request, self._visible_names("CRM Demo Request", self.sales))
        self.assertIn(self.owned_demo_request, self._visible_names("CRM Demo Request", self.engineer))
        self.assertNotIn(self.foreign_demo_request, self._visible_names("CRM Demo Request", self.engineer))

    def test_evaluation_scope_inherits_sales_request_and_uses_engineer_owner(self):
        self.assertEqual(conditions_for_doctype("CRM Evaluation", self.manager), "1=1")
        self.assertIn("`crm_demo_request`.`sales_owner`", conditions_for_doctype("CRM Evaluation", self.sales))
        self.assertIn("custom_crm_visibility", conditions_for_doctype("CRM Evaluation", self.sales))
        self.assertIn("`tabCRM Evaluation`.`evaluation_owner`", conditions_for_doctype("CRM Evaluation", self.engineer))
        self.assertIn(self.owned_evaluation, self._visible_names("CRM Evaluation", self.sales))
        self.assertNotIn(self.foreign_evaluation, self._visible_names("CRM Evaluation", self.sales))
        self.assertIn(self.owned_evaluation, self._visible_names("CRM Evaluation", self.engineer))
        self.assertNotIn(self.foreign_evaluation, self._visible_names("CRM Evaluation", self.engineer))

        self.assertTrue(frappe.has_permission(
            "CRM Evaluation", "read", doc=self.owned_evaluation, user=self.engineer,
        ))
        self.assertFalse(frappe.has_permission(
            "CRM Evaluation", "read", doc=self.foreign_evaluation, user=self.engineer,
        ))

    def _create_customer_review(self, evaluation: str, demo_request: str, comment: str) -> str:
        return frappe.get_doc({
            "doctype": "CRM Evaluation Customer Review", "evaluation": evaluation,
            "demo_request": demo_request, "test_round": 1, "comment": comment,
            "author": self.sales, "at": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True).name

    def test_customer_review_scope_follows_the_parent_evaluation(self):
        owned_review = self._create_customer_review(
            self.owned_evaluation, self.owned_demo_request, "owned comment",
        )
        foreign_review = self._create_customer_review(
            self.foreign_evaluation, self.foreign_demo_request, "foreign comment",
        )
        doctype = "CRM Evaluation Customer Review"

        self.assertIn("`tabCRM Evaluation Customer Review`.`evaluation`", conditions_for_doctype(doctype, self.sales))
        self.assertIn("`crm_demo_request`.`sales_owner`", conditions_for_doctype(doctype, self.sales))
        self.assertIn("`tabCRM Evaluation`.`evaluation_owner`", conditions_for_doctype(doctype, self.engineer))

        manager_names = self._visible_names(doctype, self.manager)
        self.assertIn(owned_review, manager_names)
        self.assertIn(foreign_review, manager_names)
        for user in (self.sales, self.engineer):
            names = self._visible_names(doctype, user)
            self.assertIn(owned_review, names, user)
            self.assertNotIn(foreign_review, names, user)
            self.assertTrue(frappe.has_permission(doctype, "read", doc=owned_review, user=user))
            self.assertFalse(frappe.has_permission(doctype, "read", doc=foreign_review, user=user))
            # Record-keeping rows are never written by hand through the standard API.
            self.assertFalse(frappe.has_permission(doctype, "write", doc=owned_review, user=user))
            self.assertFalse(frappe.has_permission(doctype, "delete", doc=owned_review, user=user))

    def test_probability_history_scope_follows_the_parent_opportunity(self):
        doctype = "CRM Opportunity Probability History"
        rows = {
            key: frappe.get_doc({
                "doctype": doctype, "opportunity": opportunity, "from_level": "", "to_level": "pipeline",
                "actor": self.sales, "changed_at": frappe.utils.now_datetime(),
            }).insert(ignore_permissions=True).name
            for key, opportunity in (("owned", self.owned_opportunity), ("foreign", self.foreign_opportunity))
        }

        self.assertIn(f"`tab{doctype}`.`opportunity`", conditions_for_doctype(doctype, self.sales))
        manager_names = self._visible_names(doctype, self.manager)
        self.assertIn(rows["owned"], manager_names)
        self.assertIn(rows["foreign"], manager_names)
        for user in (self.sales, self.engineer):
            names = self._visible_names(doctype, user)
            self.assertIn(rows["owned"], names, user)
            self.assertNotIn(rows["foreign"], names, user)
            self.assertTrue(frappe.has_permission(doctype, "read", doc=rows["owned"], user=user))
            self.assertFalse(frappe.has_permission(doctype, "read", doc=rows["foreign"], user=user))
            # Audit rows are written only by the Opportunity service.
            self.assertFalse(frappe.has_permission(doctype, "write", doc=rows["owned"], user=user))

    def test_stage_history_scope_follows_the_parent_opportunity(self):
        doctype = "CRM Opportunity Stage History"
        now = frappe.utils.now_datetime()
        rows = {
            key: frappe.get_doc({
                "doctype": doctype, "opportunity": opportunity, "from_stage": "",
                "to_stage": "qualified_opportunity", "source": "creation", "event": "created",
                "actor": self.sales, "recorded_at": now, "reached_at": now, "reached_at_basis": "recorded",
            }).insert(ignore_permissions=True).name
            for key, opportunity in (("owned", self.owned_opportunity), ("foreign", self.foreign_opportunity))
        }

        self.assertIn(f"`tab{doctype}`.`opportunity`", conditions_for_doctype(doctype, self.sales))
        manager_names = self._visible_names(doctype, self.manager)
        self.assertIn(rows["owned"], manager_names)
        self.assertIn(rows["foreign"], manager_names)
        for user in (self.sales, self.engineer):
            names = self._visible_names(doctype, user)
            self.assertIn(rows["owned"], names, user)
            self.assertNotIn(rows["foreign"], names, user)
            self.assertTrue(frappe.has_permission(doctype, "read", doc=rows["owned"], user=user))
            self.assertFalse(frappe.has_permission(doctype, "read", doc=rows["foreign"], user=user))
            # Stage changes are appended only by the Opportunity service.
            self.assertFalse(frappe.has_permission(doctype, "write", doc=rows["owned"], user=user))
            self.assertFalse(frappe.has_permission(doctype, "delete", doc=rows["owned"], user=user))

    def test_internal_validation_scope_follows_the_parent_opportunity(self):
        doctype = "CRM Opportunity Internal Validation"
        # A pending request claims its Opportunity through a unique field, so each row needs its own.
        rows = {
            key: frappe.get_doc({
                "doctype": doctype, "opportunity": opportunity, "attempt_no": 1, "status": "pending",
                "reason": "Start production before the PO arrives", "expected_po_date": "2026-12-31",
                "booking_draft": "{}", "requested_by": self.sales, "requested_at": frappe.utils.now_datetime(),
            }).insert(ignore_permissions=True).name
            for key, opportunity in (("owned", self.owned_opportunity), ("foreign", self.foreign_opportunity))
        }

        self.assertIn(f"`tab{doctype}`.`opportunity`", conditions_for_doctype(doctype, self.sales))
        manager_names = self._visible_names(doctype, self.manager)
        self.assertIn(rows["owned"], manager_names)
        self.assertIn(rows["foreign"], manager_names)
        for user in (self.sales, self.engineer):
            names = self._visible_names(doctype, user)
            self.assertIn(rows["owned"], names, user)
            self.assertNotIn(rows["foreign"], names, user)
            self.assertTrue(frappe.has_permission(doctype, "read", doc=rows["owned"], user=user))
            self.assertFalse(frappe.has_permission(doctype, "read", doc=rows["foreign"], user=user))
            # Requests change only through the Opportunity review workflow.
            self.assertFalse(frappe.has_permission(doctype, "write", doc=rows["owned"], user=user))

    def _action_and_field_history(self, opportunity: str, owner: str) -> dict[str, str]:
        return {
            "CRM Opportunity Action": frappe.get_doc({
                "doctype": "CRM Opportunity Action", "opportunity": opportunity, "title": "Send the revised quote",
                "action_owner": owner, "due": "2026-12-31", "status": "Open",
            }).insert(ignore_permissions=True).name,
            "CRM Opportunity History": frappe.get_doc({
                "doctype": "CRM Opportunity History", "opportunity": opportunity, "actor": owner,
                "at": frappe.utils.now_datetime(), "field": "amount", "from_value": "1000", "to_value": "2500",
            }).insert(ignore_permissions=True).name,
        }

    def test_action_and_field_history_scope_follows_the_parent_opportunity(self):
        """The standard document API stops at the Opportunity scope; field history carries amounts."""

        owned = self._action_and_field_history(self.owned_opportunity, self.sales)
        foreign = self._action_and_field_history(self.foreign_opportunity, self.other_sales)

        for doctype in ("CRM Opportunity Action", "CRM Opportunity History"):
            self.assertIn(f"`tab{doctype}`.`opportunity`", conditions_for_doctype(doctype, self.sales))
            manager_names = self._visible_names(doctype, self.manager)
            self.assertIn(owned[doctype], manager_names)
            self.assertIn(foreign[doctype], manager_names)
            for user in (self.sales, self.engineer):
                names = self._visible_names(doctype, user)
                self.assertIn(owned[doctype], names, user)
                self.assertNotIn(foreign[doctype], names, user)
                # Rows other tests left on the site count too: each listed row sits on an
                # Opportunity the user can open.
                reachable = set(frappe.db.sql_list(
                    "SELECT `name` FROM `tabCRM Opportunity` "
                    f"WHERE {conditions_for_doctype('CRM Opportunity', user)}"
                ))
                listed = set(frappe.get_list(doctype, pluck="opportunity", limit_page_length=0))
                self.assertLessEqual(listed, reachable, f"{doctype} {user}")
                self.assertTrue(frappe.has_permission(doctype, "read", doc=owned[doctype], user=user))
                self.assertFalse(frappe.has_permission(doctype, "read", doc=foreign[doctype], user=user))
                # Both are written only by the Opportunity service.
                self.assertFalse(frappe.has_permission(doctype, "write", doc=owned[doctype], user=user))
                self.assertFalse(frappe.has_permission(doctype, "delete", doc=owned[doctype], user=user))

    def test_opportunity_and_review_services_still_read_actions_and_field_history(self):
        """They read with get_all, so the standard-API scope leaves what they return unchanged."""

        from rayher_crm.services import cockpit
        from rayher_crm.services.opportunities import get_strategy_opportunity

        owned = self._action_and_field_history(self.owned_opportunity, self.sales)
        foreign = self._action_and_field_history(self.foreign_opportunity, self.other_sales)

        # Engineers work the Opportunity, so its detail gives them the actions as well.
        for user in (self.sales, self.engineer):
            frappe.set_user(user)
            detail = get_strategy_opportunity(self.owned_opportunity)
            self.assertIn(owned["CRM Opportunity Action"], {row["id"] for row in detail["actions"]}, user)
            self.assertIn(
                ("amount", "1000", "2500"),
                {(row["field"], row["from"], row["to"]) for row in detail["history"]},
                user,
            )

        frappe.set_user(self.manager)
        customers, people, _filters = cockpit.options()
        review = cockpit.load_data(customers, people)
        plan = cockpit.load_plan_data(customers, people)
        for rows in (owned, foreign):
            self.assertIn(rows["CRM Opportunity Action"], {row["name"] for row in review["actions"]})
            self.assertIn(rows["CRM Opportunity History"], {row["name"] for row in review["history"]})
            self.assertIn(rows["CRM Opportunity Action"], {row["name"] for row in plan["actions"]})

    def test_all_sales_child_scopes_include_the_private_parent_guard(self):
        for doctype in (
            "Lead",
            "CRM Opportunity",
            "CRM Opportunity Probability History",
            "CRM Opportunity Stage History",
            "CRM Opportunity Internal Validation",
            "CRM Opportunity Action",
            "CRM Opportunity History",
            "CRM Booking",
            "CRM Installed Tool",
            "CRM Demo Request",
            "CRM Evaluation",
            "CRM Evaluation Customer Review",
            "CRM Demo Artifact",
            "CRM Visit",
            "CRM Quotation",
            "CRM Quotation Version",
            "CRM Quotation Approval",
            "CRM RFQ",
            "CRM RFQ Version",
        ):
            condition = conditions_for_doctype(doctype, self.sales)
            self.assertIn("tabCustomer", condition, doctype)
            self.assertIn("custom_crm_visibility", condition, doctype)

    def test_standard_doctypes_have_explicit_crm_role_permissions(self):
        for doctype in (
            "Customer", "Contact", "Lead", "CRM Opportunity", "CRM Booking", "CRM Installed Tool",
            "CRM Demo Request", "CRM Evaluation",
        ):
            roles = {row.role for row in frappe.get_meta(doctype).permissions}
            self.assertTrue({"CRM Manager", "CRM Sales", "CRM Engineer"}.issubset(roles), doctype)

    def test_no_crm_role_writes_through_the_standard_document_api(self):
        """Business rules and history live in the api/v1 services, so the generic API only reads."""

        for doctype in SCOPED_DOCTYPES:
            for user in (self.manager, self.sales, self.engineer):
                for permission in sorted(MUTATING_PERMISSIONS):
                    self.assertFalse(
                        frappe.has_permission(doctype, permission, user=user),
                        f"{doctype} {permission} for {user}",
                    )

    def test_standard_document_api_cannot_change_an_opportunity(self):
        """The review case: /api/resource and frappe.client skip the owner rule and the history."""

        from frappe.client import set_value

        before = frappe.db.get_value(
            "CRM Opportunity", self.owned_opportunity, ["stage", "probability_level", "title"],
        )
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.PermissionError):
            set_value("CRM Opportunity", self.owned_opportunity, "probability_level", "committed")

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            set_value("CRM Opportunity", self.owned_opportunity, "stage", "po_received")
        with self.assertRaises(frappe.PermissionError):
            document = frappe.get_doc("CRM Opportunity", self.owned_opportunity)
            document.title = "Renamed outside the services"
            document.save()

        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value(
                "CRM Opportunity", self.owned_opportunity, ["stage", "probability_level", "title"],
            ),
            before,
        )
        self.assertEqual(frappe.db.count("CRM Opportunity Probability History", {
            "opportunity": self.owned_opportunity,
        }), 0)
