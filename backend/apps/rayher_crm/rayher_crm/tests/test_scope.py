from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import frappe
from frappe.client import get as client_get
from frappe.client import get_list as client_get_list
from frappe.client import insert as client_insert
from frappe.client import set_value as client_set_value
from frappe.permissions import add_permission, update_permission_property
from frappe.share import add as add_share
from frappe.tests.utils import FrappeTestCase

from rayher_crm.permissions.scope import (
    MUTATING_PERMISSIONS,
    OPPORTUNITY_CHILD_DOCTYPES,
    SCOPED_DOCTYPES,
    _lock_customer_groups,
    address_query,
    conditions_for_doctype,
    has_address_permission,
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

    def _grant_explicit_address_role(self, user: str) -> str:
        role = "CRM Scope ERP Address User"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        add_permission("Address", role, 0, "read")
        for permission_type in ("read", "write", "create", "delete", "share"):
            update_permission_property(
                "Address", role, 0, permission_type, 1, validate=False,
            )
        frappe.get_doc("User", user).add_roles(role)
        frappe.clear_cache(doctype="Address")
        frappe.clear_cache(user=user)
        return role

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

    def _native_rows(
        self,
        doctype: str,
        user: str,
        names: list[str],
        sensitive_field: str,
    ) -> dict[str, dict]:
        frappe.set_user(user)
        rows = client_get_list(
            doctype,
            fields=["name", sensitive_field],
            filters={"name": ["in", names]},
            limit_page_length=100,
        )
        return {row["name"]: row for row in rows}

    def _insert_legacy_share(
        self,
        doctype: str,
        name: str,
        user: str,
        *,
        read: int = 1,
        write: int = 0,
        submit: int = 0,
    ) -> str:
        row = frappe.get_doc({
            "doctype": "DocShare", "user": user, "share_doctype": doctype,
            "share_name": name, "read": read, "write": write, "submit": submit,
        })
        row.name = frappe.generate_hash(length=10)
        row.db_insert()
        return row.name

    def _create_parent_scoped_rows(
        self,
        *,
        opportunity: str,
        contact: str,
        demo_request: str,
        evaluation: str,
        installed_tool: str,
        actor: str,
        marker: str,
    ) -> dict[str, tuple[str, str, str]]:
        now = frappe.utils.now_datetime()
        rows = {
            "CRM Opportunity Stakeholder": ({
                "doctype": "CRM Opportunity Stakeholder", "opportunity": opportunity, "contact": contact,
                "role": "Decision Maker", "influence": "High", "stance": "Support", "coverage": "Direct",
                "opportunity_notes": marker,
            }, "opportunity_notes"),
            "CRM Opportunity Action": ({
                "doctype": "CRM Opportunity Action", "opportunity": opportunity,
                "title": marker, "action_owner": actor, "due": "2026-12-31", "status": "Open",
            }, "title"),
            "CRM Opportunity History": ({
                "doctype": "CRM Opportunity History", "opportunity": opportunity,
                "actor": actor, "at": now, "field": "amount", "from_value": "1000", "to_value": marker,
            }, "to_value"),
            "CRM Demo Comment": ({
                "doctype": "CRM Demo Comment", "demo_request": demo_request, "author": actor,
                "role": "Sales", "body": marker, "at": now,
            }, "body"),
            "CRM Demo Request History": ({
                "doctype": "CRM Demo Request History", "demo_request": demo_request, "at": now,
                "actor": actor, "from_status": "", "to_status": "Draft", "comment": marker,
            }, "comment"),
            "CRM Evaluation History": ({
                "doctype": "CRM Evaluation History", "evaluation": evaluation, "demo_request": demo_request,
                "actor": actor, "at": now, "event_type": "Created", "summary": marker,
            }, "summary"),
            "CRM Evaluation Customer Review": ({
                "doctype": "CRM Evaluation Customer Review", "evaluation": evaluation,
                "demo_request": demo_request, "test_round": 1, "comment": marker,
                "author": actor, "at": now,
            }, "comment"),
            "CRM Test Run": ({
                "doctype": "CRM Test Run", "evaluation": evaluation, "run_date": "2026-12-01",
                "test_round": 1, "lot": marker, "wafers": 1, "status": "Planned", "summary": marker,
            }, "summary"),
            "CRM Installed Tool Lifecycle History": ({
                "doctype": "CRM Installed Tool Lifecycle History", "installed_tool": installed_tool,
                "at": now, "actor": actor, "from_stage": "FAT", "to_stage": "Shipment",
                "completed_at": "2026-12-01", "result": "Passed", "open_issues": "None",
                "customer_signoff": "Signed", "comment": marker,
            }, "comment"),
            "CRM Installed Tool Service History": ({
                "doctype": "CRM Installed Tool Service History", "installed_tool": installed_tool,
                "at": now, "actor": actor, "service_date": "2026-12-01",
                "service_type": "Installation Support", "result": "Completed", "open_issues": "None",
                "comment": marker,
            }, "comment"),
            "CRM Installed Tool Version History": ({
                "doctype": "CRM Installed Tool Version History", "installed_tool": installed_tool,
                "at": now, "actor": actor, "change_date": "2026-12-01", "change_type": "Software",
                "from_value": "1.0", "to_value": "1.1", "reason": marker,
            }, "reason"),
        }
        result = {}
        for doctype, (payload, sensitive_field) in rows.items():
            document = frappe.get_doc(payload).insert(ignore_permissions=True)
            result[doctype] = (document.name, sensitive_field, marker)
        return result

    def _create_controlled_document(self) -> str:
        suffix = frappe.generate_hash(length=10)
        return frappe.get_doc({
            "doctype": "CRM Controlled Document", "document_id": f"SCOPE-{suffix}",
            "title": "Scope document", "category": "Technical", "document_type": "Manual",
            "product": "Inspection", "version": "1", "revision": "A", "status": "Released",
            "confidentiality": "Internal", "access_mode": "Request", "review_date": "2027-12-31",
            "document_owner": "CRM", "file_name": "scope.pdf", "content_hash": suffix,
        }).insert(ignore_permissions=True).name

    def _create_access_request(self, document: str, requester: str, reason: str) -> str:
        return frappe.get_doc({
            "doctype": "CRM Document Access Request", "controlled_document": document,
            "version_id": f"{document}-1-A", "requester": requester, "reason": reason, "status": "Pending",
        }).insert(ignore_permissions=True).name

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

    def test_parent_scoped_business_rows_use_native_list_and_get_permissions(self):
        frappe.set_user("Administrator")
        owned = self._create_parent_scoped_rows(
            opportunity=self.owned_opportunity,
            contact=self.owned_contact,
            demo_request=self.owned_demo_request,
            evaluation=self.owned_evaluation,
            installed_tool=self.owned_tool,
            actor=self.sales,
            marker="owned sensitive detail",
        )
        foreign = self._create_parent_scoped_rows(
            opportunity=self.foreign_opportunity,
            contact=self.foreign_contact,
            demo_request=self.foreign_demo_request,
            evaluation=self.foreign_evaluation,
            installed_tool=self.foreign_tool,
            actor=self.other_sales,
            marker="foreign sensitive detail",
        )

        # Stakeholders follow Opportunity reads but are deliberately not added to the
        # physical-delete tuple used by delete_strategy_opportunity.
        self.assertNotIn("CRM Opportunity Stakeholder", OPPORTUNITY_CHILD_DOCTYPES)
        for doctype, (owned_name, field, owned_value) in owned.items():
            foreign_name, _, foreign_value = foreign[doctype]
            names = [owned_name, foreign_name]
            manager_rows = self._native_rows(doctype, self.manager, names, field)
            self.assertEqual(manager_rows[owned_name][field], owned_value, doctype)
            self.assertEqual(manager_rows[foreign_name][field], foreign_value, doctype)
            expected_users = (self.sales,) if doctype == "CRM Opportunity Stakeholder" else (self.sales, self.engineer)
            for user in expected_users:
                rows = self._native_rows(doctype, user, names, field)
                self.assertEqual(set(rows), {owned_name}, f"{doctype} {user}")
                self.assertEqual(client_get(doctype, owned_name)[field], owned_value, doctype)
                with self.assertRaises(frappe.PermissionError, msg=f"{doctype} {user}"):
                    client_get(doctype, foreign_name)
            if doctype == "CRM Opportunity Stakeholder":
                with self.assertRaises(frappe.PermissionError):
                    self._native_rows(doctype, self.engineer, names, field)
                frappe.set_user(self.engineer)
                with self.assertRaises(frappe.PermissionError):
                    client_get(doctype, owned_name)

    def test_parent_scope_reacts_to_visibility_owner_and_engineer_changes(self):
        frappe.set_user("Administrator")
        foreign = self._create_parent_scoped_rows(
            opportunity=self.foreign_opportunity,
            contact=self.foreign_contact,
            demo_request=self.foreign_demo_request,
            evaluation=self.foreign_evaluation,
            installed_tool=self.foreign_tool,
            actor=self.other_sales,
            marker="moving sensitive detail",
        )
        names_by_doctype = {doctype: [row[0]] for doctype, row in foreign.items()}
        fields_by_doctype = {doctype: row[1] for doctype, row in foreign.items()}
        frappe.db.set_value(
            "CRM Opportunity", self.foreign_opportunity, "opportunity_owner", self.sales, update_modified=False,
        )
        frappe.db.set_value(
            "CRM Demo Request", self.foreign_demo_request, "sales_owner", self.sales, update_modified=False,
        )
        frappe.db.set_value(
            "CRM Installed Tool", self.foreign_tool, "sales_owner", self.sales, update_modified=False,
        )

        # A Public Account plus object ownership grants service scope to Sales.
        for doctype, names in names_by_doctype.items():
            self.assertEqual(
                set(self._native_rows(doctype, self.sales, names, fields_by_doctype[doctype])),
                set(names),
                doctype,
            )

        # Public -> Private is effective immediately for the same old row IDs.
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Customer", self.foreign_customer, "custom_crm_visibility", "Private", update_modified=False,
        )
        for doctype, names in names_by_doctype.items():
            self.assertEqual(self._native_rows(doctype, self.sales, names, fields_by_doctype[doctype]), {}, doctype)
            frappe.set_user(self.sales)
            with self.assertRaises(frappe.PermissionError, msg=doctype):
                client_get(doctype, names[0])

        # Restoring Public access does not survive transfer of the object owner.
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Customer", self.foreign_customer, "custom_crm_visibility", "Public", update_modified=False,
        )
        frappe.db.set_value(
            "CRM Opportunity", self.foreign_opportunity, "opportunity_owner", self.other_sales, update_modified=False,
        )
        frappe.db.set_value(
            "CRM Demo Request", self.foreign_demo_request, "sales_owner", self.other_sales, update_modified=False,
        )
        frappe.db.set_value(
            "CRM Installed Tool", self.foreign_tool, "sales_owner", self.other_sales, update_modified=False,
        )
        for doctype, names in names_by_doctype.items():
            self.assertEqual(self._native_rows(doctype, self.sales, names, fields_by_doctype[doctype]), {}, doctype)

        # Engineer access follows the specific parent rule: Opportunity uses Account
        # assignment; Demo, Evaluation and Installed Tool use their direct assignee.
        frappe.set_user("Administrator")
        owned = self._create_parent_scoped_rows(
            opportunity=self.owned_opportunity,
            contact=self.owned_contact,
            demo_request=self.owned_demo_request,
            evaluation=self.owned_evaluation,
            installed_tool=self.owned_tool,
            actor=self.engineer,
            marker="engineer sensitive detail",
        )
        for doctype, (name, field, _) in owned.items():
            if doctype == "CRM Opportunity Stakeholder":
                with self.assertRaises(frappe.PermissionError):
                    self._native_rows(doctype, self.engineer, [name], field)
                continue
            self.assertIn(name, self._native_rows(doctype, self.engineer, [name], field), doctype)

        frappe.set_user("Administrator")
        frappe.db.set_value(
            "CRM Account Engineer Assignment",
            {"customer": self.owned_customer, "engineer": self.engineer},
            "enabled",
            0,
            update_modified=False,
        )
        stakeholder = owned["CRM Opportunity Stakeholder"]
        with self.assertRaises(frappe.PermissionError):
            self._native_rows("CRM Opportunity Stakeholder", self.engineer, [stakeholder[0]], stakeholder[1])
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "CRM Demo Request", self.owned_demo_request, "engineer_owner", self.other_engineer, update_modified=False,
        )
        frappe.db.set_value(
            "CRM Evaluation", self.owned_evaluation, "evaluation_owner", self.other_engineer, update_modified=False,
        )
        frappe.db.set_value(
            "CRM Installed Tool", self.owned_tool, "engineer_owner", self.other_engineer, update_modified=False,
        )
        for doctype, (name, field, _) in owned.items():
            if doctype == "CRM Opportunity Stakeholder":
                with self.assertRaises(frappe.PermissionError):
                    self._native_rows(doctype, self.engineer, [name], field)
            else:
                self.assertEqual(self._native_rows(doctype, self.engineer, [name], field), {}, doctype)

    def test_parent_scope_survives_legacy_read_shares_and_blocks_new_shares(self):
        frappe.set_user("Administrator")
        foreign = self._create_parent_scoped_rows(
            opportunity=self.foreign_opportunity,
            contact=self.foreign_contact,
            demo_request=self.foreign_demo_request,
            evaluation=self.foreign_evaluation,
            installed_tool=self.foreign_tool,
            actor=self.other_sales,
            marker="legacy shared sensitive detail",
        )
        status_attachment = frappe.get_doc({
            "doctype": "CRM Status Attachment",
            "status": f"scope-status-{frappe.generate_hash(length=10)}",
            "opportunity": self.foreign_opportunity,
            "private_file": f"scope-file-{frappe.generate_hash(length=10)}",
            "file_name": "legacy-secret.txt",
            "mime_type": "text/plain",
            "size_bytes": 20,
            "content_hash": frappe.generate_hash(length=32),
            "uploaded_by": self.other_sales,
            "uploaded_at": frappe.utils.now_datetime(),
            "deleted": 0,
        }).insert(ignore_permissions=True, ignore_links=True)
        foreign["CRM Status Attachment"] = (
            status_attachment.name, "file_name", "legacy-secret.txt",
        )
        legacy_shares = {
            doctype: self._insert_legacy_share(doctype, row[0], self.sales)
            for doctype, row in foreign.items()
        }

        # Frappe detail permissions fall back to DocShare after the controller denies
        # the row, reproducing why merely clearing write/submit is insufficient.
        frappe.set_user(self.sales)
        for doctype, (name, field, value) in foreign.items():
            self.assertEqual(client_get(doctype, name)[field], value, doctype)

        frappe.set_user("Administrator")
        install_crm_doc_permissions()
        install_crm_doc_permissions()  # cleanup is deliberately idempotent
        for doctype, (name, field, _) in foreign.items():
            self.assertFalse(frappe.db.exists("DocShare", legacy_shares[doctype]), doctype)
            if doctype == "CRM Status Attachment":
                with self.assertRaises(frappe.PermissionError):
                    self._native_rows(doctype, self.sales, [name], field)
            else:
                self.assertEqual(self._native_rows(doctype, self.sales, [name], field), {}, doctype)
            frappe.set_user(self.sales)
            with self.assertRaises(frappe.PermissionError, msg=doctype):
                client_get(doctype, name)

            # Administrator normally bypasses DocPerm, so this exercises the
            # DocShare event guard rather than only the CRM role permission rows.
            frappe.set_user("Administrator")
            with self.assertRaises(frappe.PermissionError, msg=doctype):
                add_share(doctype, name, user=self.sales, read=1)

    def test_assignment_and_document_request_native_reads_keep_their_own_rules(self):
        frappe.set_user("Administrator")
        owned_assignment = frappe.db.get_value(
            "CRM Account Engineer Assignment",
            {"customer": self.owned_customer, "engineer": self.engineer},
            "name",
        )
        foreign_assignment = frappe.get_doc({
            "doctype": "CRM Account Engineer Assignment", "customer": self.foreign_customer,
            "engineer": self.other_engineer, "enabled": 1,
        }).insert(ignore_permissions=True).name
        assignment_names = [owned_assignment, foreign_assignment]
        self.assertEqual(
            set(self._native_rows(
                "CRM Account Engineer Assignment", self.manager, assignment_names, "engineer",
            )),
            set(assignment_names),
        )
        engineer_rows = self._native_rows(
            "CRM Account Engineer Assignment", self.engineer, assignment_names, "engineer",
        )
        self.assertEqual(set(engineer_rows), {owned_assignment})
        with self.assertRaises(frappe.PermissionError):
            client_get("CRM Account Engineer Assignment", foreign_assignment)
        self.assertFalse(frappe.has_permission(
            "CRM Account Engineer Assignment", "share", doc=owned_assignment, user=self.manager,
        ))

        frappe.set_user("Administrator")
        assignment_share = self._insert_legacy_share(
            "CRM Account Engineer Assignment", foreign_assignment, self.sales,
        )
        frappe.set_user(self.sales)
        self.assertEqual(
            client_get("CRM Account Engineer Assignment", foreign_assignment)["engineer"],
            self.other_engineer,
        )
        frappe.set_user("Administrator")
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", assignment_share))
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            client_get("CRM Account Engineer Assignment", foreign_assignment)
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            add_share("CRM Account Engineer Assignment", foreign_assignment, user=self.sales, read=1)

        frappe.set_user(self.manager)
        client_set_value("CRM Account Engineer Assignment", owned_assignment, "enabled", 0)
        self.assertEqual(
            self._native_rows(
                "CRM Account Engineer Assignment", self.engineer, [owned_assignment], "engineer",
            ),
            {},
        )
        with self.assertRaises(frappe.PermissionError):
            client_get("CRM Account Engineer Assignment", owned_assignment)

        frappe.set_user("Administrator")
        document = self._create_controlled_document()
        requests = {
            self.sales: self._create_access_request(document, self.sales, "sales private reason"),
            self.other_sales: self._create_access_request(document, self.other_sales, "other private reason"),
            self.engineer: self._create_access_request(document, self.engineer, "engineer private reason"),
        }
        request_names = list(requests.values())
        self.assertEqual(
            set(self._native_rows("CRM Document Access Request", self.manager, request_names, "reason")),
            set(request_names),
        )
        for user in (self.sales, self.engineer):
            rows = self._native_rows("CRM Document Access Request", user, request_names, "reason")
            self.assertEqual(set(rows), {requests[user]}, user)
            for other_name in set(request_names) - {requests[user]}:
                with self.assertRaises(frappe.PermissionError):
                    client_get("CRM Document Access Request", other_name)

        frappe.set_user("Administrator")
        request_share = self._insert_legacy_share(
            "CRM Document Access Request", requests[self.engineer], self.sales,
        )
        frappe.set_user(self.sales)
        self.assertEqual(
            client_get("CRM Document Access Request", requests[self.engineer])["reason"],
            "engineer private reason",
        )
        frappe.set_user("Administrator")
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", request_share))
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            client_get("CRM Document Access Request", requests[self.engineer])
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            add_share("CRM Document Access Request", requests[self.engineer], user=self.sales, read=1)

    def test_address_native_access_is_crm_scoped_without_changing_erp_roles(self):
        frappe.set_user("Administrator")
        unrelated_address = frappe.get_doc({
            "doctype": "Address", "address_title": "Non CRM ERP address", "address_type": "Other",
            "address_line1": "Outside CRM", "city": "Shanghai", "country": "China",
        }).insert(ignore_permissions=True).name
        names = [self.owned_site, self.foreign_site, unrelated_address]
        # Frappe's superuser shortcut covers single documents only; Administrator's list, count
        # and link search still run the Address hook and must keep the non-CRM Address too.
        frappe.set_user("Administrator")
        self.assertEqual(address_query("Administrator"), "")
        self.assertEqual(
            set(frappe.get_list("Address", filters={"name": ["in", names]}, pluck="name")),
            set(names),
        )
        self.assertEqual(
            set(self._native_rows("Address", self.manager, names, "city")),
            {self.owned_site, self.foreign_site},
        )
        self.assertEqual(set(self._native_rows("Address", self.sales, names, "city")), {self.owned_site})
        self.assertEqual(set(self._native_rows("Address", self.engineer, names, "city")), {self.owned_site})
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", self.foreign_site)

        # A legacy share overrides the failed CRM controller detail check. Query
        # hooks still filter the list. Installation removes only CRM-site shares.
        non_crm = self._create_user("crm-scope-erp-user@example.invalid", "Sales User")
        crm_address_share = self._insert_legacy_share("Address", self.foreign_site, self.sales)
        erp_address_share = self._insert_legacy_share("Address", unrelated_address, non_crm)
        self.assertEqual(self._native_rows("Address", self.sales, [self.foreign_site], "city"), {})
        self.assertEqual(client_get("Address", self.foreign_site)["city"], "Shanghai")

        frappe.set_user("Administrator")
        install_crm_doc_permissions()
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", crm_address_share))
        self.assertTrue(frappe.db.exists("DocShare", erp_address_share))
        self.assertEqual(self._native_rows("Address", self.sales, [self.foreign_site], "city"), {})
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", self.foreign_site)
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            add_share("Address", self.foreign_site, user=self.sales, read=1)

        # The same DocShare hook leaves ordinary ERP Address sharing intact, and
        # the Address permission hook returns no decision for a non-CRM identity.
        add_share("Address", unrelated_address, user=non_crm, read=1)
        frappe.set_user(non_crm)
        self.assertEqual(client_get("Address", unrelated_address)["city"], "Shanghai")

        # Reproduce the ERPNext All/if_owner route while both users legitimately
        # read the CRM site. Ownership must not reopen native writes or creates.
        for user in (self.sales, self.engineer):
            frappe.set_user("Administrator")
            frappe.db.set_value("Address", self.owned_site, "owner", user, update_modified=False)
            frappe.set_user(user)
            with self.assertRaises(frappe.PermissionError):
                client_set_value("Address", self.owned_site, "city", "Changed outside the site service")
            with self.assertRaises(frappe.PermissionError):
                client_insert({
                    "doctype": "Address", "address_title": "Uncontrolled CRM site", "address_type": "Other",
                    "address_line1": "Outside service", "city": "Shanghai", "country": "China",
                    "links": [{"link_doctype": "Customer", "link_name": self.owned_customer}],
                })

        frappe.set_user("Administrator")
        frappe.db.set_value(
            "CRM Account Engineer Assignment",
            {"customer": self.owned_customer, "engineer": self.engineer},
            "enabled",
            0,
            update_modified=False,
        )
        self.assertEqual(self._native_rows("Address", self.engineer, [self.owned_site], "city"), {})

        self.assertEqual(address_query(non_crm), "")
        self.assertIsNone(
            has_address_permission(
                frappe.get_doc("Address", self.owned_site), user=non_crm, permission_type="read",
            )
        )

    def test_address_crm_boundary_handles_erp_roles_ambiguous_roles_and_multiple_links(self):
        frappe.set_user("Administrator")
        erp_customer = self._create_customer("Scope ERP Customer", self.sales)
        frappe.db.set_value("Customer", erp_customer, "customer_group", None, update_modified=False)
        erp_address = frappe.get_doc({
            "doctype": "Address", "address_title": "Scope ERP Customer Address",
            "address_type": "Other", "address_line1": "Outside CRM", "city": "Shanghai",
            "country": "China", "links": [{"link_doctype": "Customer", "link_name": erp_customer}],
        }).insert(ignore_permissions=True).name
        multi_link_address = frappe.get_doc({
            "doctype": "Address", "address_title": "Mixed Customer Address",
            "address_type": "Other", "address_line1": "Boundary", "city": "Shanghai",
            "country": "China", "links": [
                {"link_doctype": "Customer", "link_name": self.foreign_customer},
                {"link_doctype": "Customer", "link_name": erp_customer},
            ],
        }).insert(ignore_permissions=True).name

        # A missing/non-CRM group is not a CRM Manager wildcard. On a mixed-link
        # Address, the CRM group and Sales ownership must match the same Customer.
        self.assertNotIn(erp_address, self._visible_names("Address", self.manager))
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", erp_address)
        frappe.set_user("Administrator")
        add_share("Address", erp_address, user=self.manager, read=1)
        frappe.set_user(self.manager)
        self.assertEqual(client_get("Address", erp_address)["city"], "Shanghai")
        self.assertNotIn(multi_link_address, self._visible_names("Address", self.sales))
        sales_condition = conditions_for_doctype("Address", self.sales)
        self.assertIn("`crm_customer`.`customer_group` = 'CRM Customers'", sales_condition)
        self.assertIn("`crm_customer`.`custom_crm_owner`", sales_condition)
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", multi_link_address)

        frappe.set_user("Administrator")
        dual_role = self._create_user("crm-scope-dual-erp@example.invalid", "CRM Sales")
        self._grant_explicit_address_role(dual_role)
        self.assertEqual(
            set(self._native_rows("Address", dual_role, [erp_address, self.foreign_site], "city")),
            {erp_address},
        )
        self.assertEqual(client_get("Address", erp_address)["city"], "Shanghai")
        client_set_value("Address", erp_address, "city", "Suzhou")
        self.assertEqual(client_get("Address", erp_address)["city"], "Suzhou")
        created_erp_address = client_insert({
            "doctype": "Address", "address_title": "Dual Role ERP Address",
            "address_type": "Other", "address_line1": "Native ERP", "city": "Suzhou",
            "country": "China",
        })
        self.assertTrue(frappe.db.exists("Address", created_erp_address["name"]))
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", self.foreign_site)

        frappe.set_user("Administrator")
        ambiguous = self._create_user("crm-scope-ambiguous-erp@example.invalid", "CRM Sales")
        frappe.get_doc("User", ambiguous).add_roles("CRM Engineer")
        self._grant_explicit_address_role(ambiguous)
        self.assertEqual(
            set(self._native_rows("Address", ambiguous, [erp_address, self.owned_site], "city")),
            {erp_address},
        )
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", self.owned_site)

        # Classification also sees proposed links before Dynamic Link rows exist.
        draft_crm_address = frappe.get_doc({
            "doctype": "Address", "address_title": "Draft CRM Site", "address_type": "Other",
            "address_line1": "Draft", "city": "Shanghai", "country": "China",
            "links": [{"link_doctype": "Customer", "link_name": self.owned_customer}],
        })
        self.assertFalse(has_address_permission(
            draft_crm_address, user=dual_role, permission_type="create",
        ))

    def test_address_with_a_dangling_customer_link_stays_inside_the_crm_boundary(self):
        frappe.set_user("Administrator")
        gone_customer = self._create_customer("Scope Deleted Customer", self.sales)
        orphan = frappe.get_doc({
            "doctype": "Address", "address_title": "Scope Orphan Address", "address_type": "Other",
            "address_line1": "Left behind", "city": "Shanghai", "country": "China",
            "links": [{"link_doctype": "Customer", "link_name": gone_customer}],
        }).insert(ignore_permissions=True).name
        # Frappe removes a Customer's links when it deletes the record; a failed migration or
        # direct SQL is what leaves one behind.
        frappe.db.delete("Customer", {"name": gone_customer})
        self.assertTrue(frappe.db.exists("Dynamic Link", {"parent": orphan, "link_name": gone_customer}))
        dual_role = self._create_user("crm-scope-orphan-erp@example.invalid", "CRM Sales")
        self._grant_explicit_address_role(dual_role)

        # A CRM identity that also holds an ERP Address role may not use that role on an Address
        # whose CRM membership cannot be checked: list, detail and sharing all fail closed.
        self.assertEqual(self._native_rows("Address", dual_role, [orphan], "city"), {})
        self.assertNotIn(orphan, self._visible_names("Address", dual_role))
        frappe.set_user(dual_role)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", orphan)
        self.assertFalse(has_address_permission(
            frappe.get_doc("Address", orphan), user=dual_role, permission_type="read",
        ))
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            add_share("Address", orphan, user=self.manager, read=1)

        # A share that already existed is dropped by installation, like one on a CRM site.
        legacy_share = self._insert_legacy_share("Address", orphan, dual_role)
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", legacy_share))
        # Administrator still reaches it.
        self.assertIn(orphan, set(frappe.get_list("Address", pluck="name")))

    def test_link_search_cannot_skip_the_crm_row_scope(self):
        from rayher_crm.permissions import search as crm_search

        # CRM Booking has no standard query, so search_widget takes the get_list branch that
        # turns ignore_user_permissions=1 into ignore_permissions=True for a caller with read.
        for method in ("search_link", "search_widget"):
            overrides = frappe.get_hooks("override_whitelisted_methods")[f"frappe.desk.search.{method}"]
            self.assertEqual(overrides[-1], f"rayher_crm.permissions.search.{method}")

        hidden = self.foreign_booking
        frappe.set_user(self.sales)
        self.assertNotIn(hidden, self._visible_names("CRM Booking", self.sales))
        for ignore in (0, 1, "1"):
            with self.subTest(ignore=ignore):
                link = crm_search.search_link(
                    "CRM Booking", hidden, searchfield="name", ignore_user_permissions=ignore,
                )
                widget = crm_search.search_widget(
                    "CRM Booking", hidden, searchfield="name", ignore_user_permissions=ignore,
                )
                self.assertNotIn(hidden, str(link))
                self.assertNotIn(hidden, str(widget))
        # The owner still finds the record, so the empty result above comes from the scope.
        frappe.set_user(self.other_sales)
        self.assertIn(hidden, str(crm_search.search_link(
            "CRM Booking", hidden, searchfield="name", ignore_user_permissions=1,
        )))
        self.assertIn(hidden, str(crm_search.search_widget(
            "CRM Booking", hidden, searchfield="name", ignore_user_permissions=1,
        )))

    def test_address_and_customer_crm_transitions_revoke_erp_shares(self):
        frappe.set_user("Administrator")
        share_only_role = "CRM Scope ERP Share Recipient"
        if not frappe.db.exists("Role", share_only_role):
            frappe.get_doc({
                "doctype": "Role", "role_name": share_only_role, "desk_access": 1,
            }).insert(ignore_permissions=True)
        erp_user = self._create_user(
            "crm-scope-transition-erp@example.invalid", share_only_role,
        )

        reparent_customer = self._create_customer("Scope Reparent ERP Customer", self.sales)
        frappe.db.set_value("Customer", reparent_customer, "customer_group", None, update_modified=False)
        reparent_address = frappe.get_doc({
            "doctype": "Address", "address_title": "ERP Address Reparented To CRM",
            "address_type": "Other", "address_line1": "Reparent", "city": "Shanghai",
            "country": "China",
            "links": [{"link_doctype": "Customer", "link_name": reparent_customer}],
        }).insert(ignore_permissions=True)
        reparent_share = self._insert_legacy_share("Address", reparent_address.name, erp_user)
        frappe.set_user(erp_user)
        self.assertEqual(client_get("Address", reparent_address.name)["city"], "Shanghai")
        frappe.set_user("Administrator")
        reparent_address.append(
            "links", {"link_doctype": "Customer", "link_name": self.owned_customer},
        )
        reparent_address.save(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("DocShare", reparent_share))
        with self.assertRaises(frappe.PermissionError):
            add_share("Address", reparent_address.name, user=erp_user, read=1)
        frappe.set_user(erp_user)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", reparent_address.name)

        frappe.set_user("Administrator")
        promoted_customer = self._create_customer("Scope Promoted ERP Customer", self.sales)
        frappe.db.set_value("Customer", promoted_customer, "customer_group", None, update_modified=False)
        promoted_address = frappe.get_doc({
            "doctype": "Address", "address_title": "ERP Address Promoted To CRM",
            "address_type": "Other", "address_line1": "Promoted", "city": "Shanghai",
            "country": "China",
            "links": [{"link_doctype": "Customer", "link_name": promoted_customer}],
        }).insert(ignore_permissions=True)
        promoted_share = self._insert_legacy_share("Address", promoted_address.name, erp_user)
        frappe.set_user(erp_user)
        self.assertEqual(client_get("Address", promoted_address.name)["city"], "Shanghai")
        frappe.set_user("Administrator")
        customer_doc = frappe.get_doc("Customer", promoted_customer)
        customer_doc.customer_group = "CRM Customers"
        customer_doc.save(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("DocShare", promoted_share))
        with self.assertRaises(frappe.PermissionError):
            add_share("Address", promoted_address.name, user=erp_user, read=1)
        frappe.set_user(erp_user)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", promoted_address.name)

    def test_install_clears_only_legacy_crm_write_shares(self):
        frappe.set_user("Administrator")
        crm_share = self._insert_legacy_share(
            "CRM Opportunity", self.owned_opportunity, self.other_sales, write=1, submit=1,
        )
        erp_share = self._insert_legacy_share(
            "Customer", self.owned_customer, self.other_sales, write=1, submit=1,
        )
        install_crm_doc_permissions()
        self.assertEqual(
            frappe.db.get_value("DocShare", crm_share, ["read", "write", "submit"], as_dict=True),
            {"read": 1, "write": 0, "submit": 0},
        )
        self.assertEqual(
            frappe.db.get_value("DocShare", erp_share, ["read", "write", "submit"], as_dict=True),
            {"read": 1, "write": 1, "submit": 1},
        )

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
            "CRM Opportunity Stakeholder",
            "CRM Booking",
            "CRM Installed Tool",
            "CRM Installed Tool Lifecycle History",
            "CRM Installed Tool Service History",
            "CRM Installed Tool Version History",
            "CRM Demo Request",
            "CRM Demo Comment",
            "CRM Demo Request History",
            "CRM Evaluation",
            "CRM Evaluation Customer Review",
            "CRM Evaluation History",
            "CRM Test Run",
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


class TestAddressTransitionConcurrency(FrappeTestCase):
    def _create_erp_customer(self, suffix: str) -> str:
        customer = frappe.get_doc({
            "doctype": "Customer", "customer_name": f"Scope Concurrent ERP {suffix}",
            "customer_type": "Company", "customer_group": "CRM Customers",
            "territory": "CRM Territory", "custom_crm_owner": "Administrator",
        }).insert(ignore_permissions=True)
        frappe.db.set_value("Customer", customer.name, "customer_group", None, update_modified=False)
        return customer.name

    def test_customer_group_lock_is_a_current_read_after_repeatable_read_snapshot(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        customer = self._create_erp_customer(frappe.generate_hash(length=10))
        primary = frappe.local.db
        primary.commit()
        try:
            with self.secondary_connection():
                frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                self.assertIsNone(frappe.db.get_value("Customer", customer, "customer_group"))
                with self.primary_connection():
                    frappe.db.set_value(
                        "Customer", customer, "customer_group", "CRM Customers", update_modified=False,
                    )
                    frappe.db.commit()
                self.assertIsNone(frappe.db.get_value("Customer", customer, "customer_group"))
                self.assertEqual(_lock_customer_groups((customer,)), {customer: "CRM Customers"})
                frappe.db.rollback()
        finally:
            frappe.local.db = primary
            primary.rollback()
            frappe.db.delete("Customer", {"name": customer})
            primary.commit()

    def test_reparent_and_customer_promotion_cannot_leave_a_legacy_share(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        customer = self._create_erp_customer(suffix)
        address = frappe.get_doc({
            "doctype": "Address", "address_title": f"Scope Concurrent Address {suffix}",
            "address_type": "Other", "address_line1": "Concurrent", "city": "Shanghai",
            "country": "China",
        }).insert(ignore_permissions=True)
        share = frappe.get_doc({
            "doctype": "DocShare", "user": "Administrator", "share_doctype": "Address",
            "share_name": address.name, "read": 1,
        })
        share.name = frappe.generate_hash(length=10)
        share.db_insert()
        site = frappe.local.site
        address_name = address.name
        share_name = share.name
        frappe.db.commit()
        gate = Barrier(2)

        def reparent() -> None:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                address_doc = frappe.get_doc("Address", address_name)
                gate.wait(timeout=10)
                address_doc.append("links", {"link_doctype": "Customer", "link_name": customer})
                address_doc.save(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                frappe.destroy()

        def promote() -> None:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                customer_doc = frappe.get_doc("Customer", customer)
                gate.wait(timeout=10)
                customer_doc.customer_group = "CRM Customers"
                customer_doc.save(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                frappe.destroy()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(reparent), executor.submit(promote)]
                for future in futures:
                    future.result(timeout=30)
            self.assertEqual(
                frappe.db.get_value("Customer", customer, "customer_group"), "CRM Customers",
            )
            self.assertTrue(frappe.db.exists("Dynamic Link", {
                "parent": address_name, "parenttype": "Address", "parentfield": "links",
                "link_doctype": "Customer", "link_name": customer,
            }))
            self.assertFalse(frappe.db.exists("DocShare", share_name))
        finally:
            frappe.db.rollback()
            frappe.db.delete("DocShare", {"share_doctype": "Address", "share_name": address_name})
            frappe.db.delete("Dynamic Link", {"parent": address_name, "parenttype": "Address"})
            frappe.db.delete("Address", {"name": address_name})
            frappe.db.delete("Customer", {"name": customer})
            frappe.db.commit()
