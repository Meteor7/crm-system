from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import inspect
import json
import re
from threading import Barrier, Event
from unittest.mock import patch

import frappe
from frappe.client import get as client_get
from frappe.client import get_list as client_get_list
from frappe.client import insert as client_insert
from frappe.client import set_value as client_set_value
from frappe.permissions import (
    add_permission,
    add_user_permission,
    remove_user_permission,
    update_permission_property,
)
from frappe.share import add as add_share
from frappe.tests.utils import FrappeTestCase

from rayher_crm.permissions.scope import (
    CONDITION_DOCTYPES,
    MUTATING_PERMISSIONS,
    OPPORTUNITY_CHILD_DOCTYPES,
    SCOPED_DOCTYPES,
    SCOPED_CHILD_RELATIONSHIPS,
    _CUSTOMER_CONVERTED_LEAD_QUERY,
    _CUSTOMER_LINKED_PARENTS_QUERY,
    _OWNED_LEADS_QUERY,
    _parent_scope_condition,
    _lock_customer_groups,
    _lock_docshare_target,
    _lock_user_crm_roles,
    _locked_linked_customer_names,
    address_query,
    conditions_for_doctype,
    has_address_permission,
    has_crm_permission,
    install_crm_doc_permissions,
    revoke_contact_shares_entering_crm,
    revoke_customer_address_shares_entering_crm,
    revoke_lead_shares_entering_crm,
)
from rayher_crm.api import search as crm_search
from rayher_crm.api.search import _has_rayher_permission_query
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
        return self._grant_address_role(
            user, role, {"read", "write", "create", "delete", "share"},
        )

    def _grant_address_role(
        self, user: str, role: str, permissions: set[str], *, if_owner: bool = False,
    ) -> str:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        add_permission("Address", role, 0, "read")
        for permission_type in ("select", "read", "write", "create", "delete", "share"):
            update_permission_property(
                "Address", role, 0, permission_type,
                int(permission_type in permissions), validate=False,
            )
        update_permission_property("Address", role, 0, "if_owner", int(if_owner), validate=False)
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
        *, submitted: bool = True,
    ) -> str:
        name = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": customer, "primary_contact": contact,
            "opportunity": opportunity, "sales_owner": sales_owner, "created_by_user": sales_owner,
            "title": "Scope Demo Request", "objective": "Validate row scope",
            "requested_equipment": "Inspection", "sample_type": "Wafer", "sample_quantity": 1,
            "target_date": "2026-12-31", "customer_expected_date": "2026-12-31",
            "priority": "Medium", "acceptance_criteria": "Scope is enforced",
            "status": "Engineer Review" if submitted else "Draft",
            "engineer_owner": engineer_owner, "form_data": {},
        }).insert(ignore_permissions=True).name
        if submitted:
            # Submitted once: its Engineer reads it from then on.
            frappe.get_doc({
                "doctype": "CRM Demo Request History", "demo_request": name, "at": frappe.utils.now_datetime(),
                "actor": sales_owner, "from_status": "Draft", "to_status": "Engineer Review", "comment": "Submitted",
            }).insert(ignore_permissions=True)
        return name

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

    def _native_child_rows(
        self,
        doctype: str,
        parent_doctype: str,
        user: str,
        names: list[str],
        sensitive_field: str,
    ) -> dict[str, dict]:
        frappe.set_user(user)
        rows = client_get_list(
            doctype,
            parent=parent_doctype,
            fields=["name", "parent", sensitive_field],
            filters={"name": ["in", names]},
            limit_page_length=100,
        )
        return {row["name"]: row for row in rows}

    def _insert_child(self, values: dict) -> str | int:
        row = frappe.get_doc(values)
        if row.meta.autoname != "autoincrement":
            row.name = frappe.generate_hash(length=10)
        row.db_insert()
        return row.name

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

    def _whitelisted_call(self, cmd: str, **params):
        """Dispatch like POST /api/method/<cmd>: override map, whitelist and type checks."""
        from frappe.handler import execute_cmd
        from frappe.utils import set_request

        previous_form = getattr(frappe.local, "form_dict", frappe._dict())
        previous_request = getattr(frappe.local, "request", None)
        set_request(method="POST", path=f"/api/method/{cmd}")
        frappe.local.form_dict = frappe._dict(params, cmd=cmd)
        try:
            return execute_cmd(cmd)
        finally:
            frappe.local.form_dict = previous_form
            if previous_request is None:
                del frappe.local.request
            else:
                frappe.local.request = previous_request

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

    def test_direct_child_table_lists_follow_the_parent_native_scope(self):
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Customer",
            self.foreign_customer,
            "custom_crm_visibility",
            "Private",
            update_modified=False,
        )
        customer_children = {}
        for label, customer in (("owned", self.owned_customer), ("foreign", self.foreign_customer)):
            for doctype, parentfield in (
                ("Allowed To Transact With", "companies"),
                ("Customer Credit Limit", "credit_limits"),
                ("Party Account", "accounts"),
                ("Sales Team", "sales_team"),
                ("Portal User", "portal_users"),
            ):
                customer_children[(doctype, label)] = self._insert_child({
                    "doctype": doctype,
                    "parent": customer,
                    "parenttype": "Customer",
                    "parentfield": parentfield,
                })

        contact_children = {}
        for label, contact in (("owned", self.owned_contact), ("foreign", self.foreign_contact)):
            contact_children[("Contact Email", label)] = self._insert_child({
                "doctype": "Contact Email", "parent": contact, "parenttype": "Contact",
                "parentfield": "email_ids", "email_id": f"{label}@scope.example.invalid",
            })
            contact_children[("Contact Phone", label)] = self._insert_child({
                "doctype": "Contact Phone", "parent": contact, "parenttype": "Contact",
                "parentfield": "phone_nos", "phone": f"+86-21-{label}",
            })
            contact_children[("Dynamic Link", label)] = frappe.db.get_value(
                "Dynamic Link",
                {"parent": contact, "parenttype": "Contact", "parentfield": "links"},
                "name",
            )

        lead_children = {}
        for label, lead in (("owned", self.owned_lead), ("foreign", self.foreign_lead)):
            lead_children[("CRM Note", label)] = self._insert_child({
                "doctype": "CRM Note", "parent": lead, "parenttype": "Lead",
                "parentfield": "notes", "note": f"{label} scoped lead note",
            })

        quotation_children = {}
        for label, account, owner in (
            ("owned", self.owned_customer, self.sales),
            ("foreign", self.foreign_customer, self.other_sales),
        ):
            quotation = frappe.get_doc({
                "doctype": "CRM Quotation", "ref_no": f"CHILD-{label}",
                "quotation_type": "Device", "account": account,
                "quotation_owner": owner, "status": "Draft",
            }).insert(ignore_permissions=True)
            version = frappe.get_doc({
                "doctype": "CRM Quotation Version", "quotation": quotation.name,
                "version_no": 1, "quotation_type": "Device", "status": "Draft",
                "approval_status": "Not Submitted", "ref_no": quotation.ref_no,
                "account": account, "quotation_owner": owner, "quote_date": "2026-12-01",
                "validity_months": 1, "valid_until": "2026-12-31", "currency": "CNY",
                "discount_type": "None", "incoterm": "FOB",
                "items": [{
                    "line_key": f"line-{label}", "line_type": "Device",
                    "item_name": f"{label} scoped quotation item", "pricing_mode": "Charged",
                    "quantity": 1, "unit_price": 100, "line_amount": 100,
                }],
                "payment_terms": [{
                    "percentage": 100, "trigger_condition": "Acceptance",
                    "description": f"{label} scoped payment term",
                }],
            }).insert(ignore_permissions=True)
            quotation_children[("CRM Quotation Item", label)] = version.items[0].name
            quotation_children[("CRM Quotation Payment Term", label)] = version.payment_terms[0].name

        cases = (
            ("Allowed To Transact With", "Customer", "parentfield", customer_children),
            ("Customer Credit Limit", "Customer", "parentfield", customer_children),
            ("Party Account", "Customer", "parentfield", customer_children),
            ("Sales Team", "Customer", "parentfield", customer_children),
            ("Portal User", "Customer", "parentfield", customer_children),
            ("Contact Email", "Contact", "email_id", contact_children),
            ("Contact Phone", "Contact", "phone", contact_children),
            ("Dynamic Link", "Contact", "link_name", contact_children),
            ("CRM Note", "Lead", "note", lead_children),
            ("CRM Quotation Item", "CRM Quotation Version", "item_name", quotation_children),
            (
                "CRM Quotation Payment Term", "CRM Quotation Version", "description",
                quotation_children,
            ),
        )
        for doctype, parent_doctype, field, children in cases:
            owned = children[(doctype, "owned")]
            foreign = children[(doctype, "foreign")]
            with self.subTest(doctype=doctype, user="sales"):
                self.assertEqual(
                    set(self._native_child_rows(
                        doctype, parent_doctype, self.sales, [owned, foreign], field,
                    )),
                    {owned},
                )
            with self.subTest(doctype=doctype, user="manager"):
                self.assertEqual(
                    set(self._native_child_rows(
                        doctype, parent_doctype, self.manager, [owned, foreign], field,
                    )),
                    {owned, foreign},
                )

        malformed = self._insert_child({
            "doctype": "Contact Email",
            "parent": self.owned_contact,
            "parenttype": "Contact",
            "parentfield": "phone_nos",
            "email_id": "wrong-parentfield@scope.example.invalid",
        })
        self.assertEqual(
            self._native_child_rows(
                "Contact Email", "Contact", self.sales, [malformed], "email_id",
            ),
            {},
        )

    def test_event_and_communication_children_follow_real_parent_visibility(self):
        cases = (
            ("Event", "Event Participants", "event_participants", "reference_docname", self.owned_customer),
            ("Event", "Event Notifications", "notifications", "type", "Notification"),
            ("Communication", "Communication Link", "timeline_links", "link_name", self.owned_customer),
        )
        for parent_type, child_type, parent_field, reference_field, value in cases:
            children = []
            for owner in (self.sales, self.other_sales):
                frappe.set_user("Administrator")
                # Store ordinary parent fixtures without sending event invitations
                # or communications. The list below runs the real native scopes.
                parent = frappe.get_doc({
                    "doctype": parent_type, "subject": "Scope parent fixture",
                    "owner": owner, "event_type": "Private",
                    "starts_on": "2026-12-01 10:00:00",
                    "communication_type": "Communication", "communication_medium": "Other",
                })
                parent.name = frappe.generate_hash(length=12)
                parent.db_insert()
                # db_insert initializes owner to the current Administrator when
                # creation is absent; set the intended fixture owner explicitly.
                frappe.db.set_value(parent_type, parent.name, "owner", owner, update_modified=False)
                children.append(self._insert_child({
                    "doctype": child_type, "parent": parent.name,
                    "parenttype": parent_type, "parentfield": parent_field,
                    "reference_doctype": "Customer", "link_doctype": "Customer",
                    reference_field: value,
                }))
            with self.subTest(parent=parent_type):
                self.assertEqual(
                    set(self._native_child_rows(
                        child_type, parent_type, self.sales, children, reference_field,
                    )),
                    {children[0]},
                )
                self.assertEqual(
                    set(self._native_child_rows(
                        child_type, parent_type, "Administrator", children, reference_field,
                    )),
                    set(children),
                )

    def test_reserved_customer_group_rejects_rename_and_merge(self):
        frappe.set_user("Administrator")
        group = frappe.get_doc({
            "doctype": "Customer Group",
            "customer_group_name": f"Scope ERP Group {frappe.generate_hash(length=8)}",
            "parent_customer_group": "All Customer Groups",
        }).insert(ignore_permissions=True)
        for old, new, merge in (
            ("CRM Customers", f"Renamed {group.name}", False),
            ("CRM Customers", group.name, True),
            (group.name, "CRM Customers", True),
            (group.name, "crm customers", True),
        ):
            with self.subTest(old=old, new=new, merge=merge):
                with self.assertRaisesRegex(frappe.PermissionError, "reserved"):
                    frappe.rename_doc(
                        "Customer Group", old, new, merge=merge, force=True,
                        show_alert=False, rebuild_search=False,
                    )
        self.assertEqual(
            frappe.db.get_value("Customer", self.owned_customer, "customer_group"),
            "CRM Customers",
        )
        renamed = f"Renamed {group.name}"
        self.assertEqual(frappe.rename_doc(
            "Customer Group", group.name, renamed, force=True,
            show_alert=False, rebuild_search=False,
        ), renamed)

    def test_reserved_customer_group_uses_canonical_database_identity(self):
        from rayher_crm.permissions.scope import protect_crm_customer_group_name

        reserved = frappe.get_doc("Customer Group", "CRM Customers")
        # The database may resolve a differently spelled input to the same
        # canonical row under its collation; the supplied text is not identity.
        with patch.object(frappe.db, "exists", return_value=reserved.name):
            with self.assertRaisesRegex(frappe.PermissionError, "reserved"):
                protect_crm_customer_group_name(
                    reserved, None, "CRM Cústomers", "Other Group", False,
                )
        self.assertTrue(frappe.db.exists("Customer Group", reserved.name))

    def test_native_standard_merge_rejects_cross_crm_boundary_without_changes(self):
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=8)
        erp_user = self._create_user(f"crm-merge-erp-{suffix}@example.invalid", "Sales User")
        erp_customer = self._create_customer(f"Merge ERP Account {suffix}", erp_user)
        frappe.db.set_value("Customer", erp_customer, "customer_group", "All Customer Groups")
        erp_contact_doc = frappe.get_doc({
            "doctype": "Contact", "first_name": f"Merge ERP Contact {suffix}",
            "links": [{"link_doctype": "Customer", "link_name": erp_customer}],
        }).insert(ignore_permissions=True)
        erp_address_doc = frappe.get_doc({
            "doctype": "Address", "address_title": f"Merge ERP Address {suffix}",
            "address_type": "Other", "address_line1": "Outside CRM",
            "city": "Shanghai", "country": "China",
            "links": [{"link_doctype": "Customer", "link_name": erp_customer}],
        }).insert(ignore_permissions=True)
        erp_lead_doc = frappe.get_doc({
            "doctype": "Lead", "first_name": f"Merge ERP Lead {suffix}",
            "company_name": f"Merge ERP Company {suffix}", "status": "Lead",
            "lead_owner": erp_user, "custom_crm_converted_account": erp_customer,
        }).insert(ignore_permissions=True)
        pairs = (
            ("Customer", erp_customer, self.owned_customer),
            ("Contact", erp_contact_doc.name, self.owned_contact),
            ("Address", erp_address_doc.name, self.owned_site),
            ("Lead", erp_lead_doc.name, self.owned_lead),
        )
        for doctype, erp_name, crm_name in pairs:
            for source, target in ((erp_name, crm_name), (crm_name, erp_name)):
                with self.subTest(doctype=doctype, source=source):
                    with self.assertRaisesRegex(frappe.PermissionError, "CRM boundary"):
                        frappe.rename_doc(
                            doctype, source, target, merge=True, force=True,
                            show_alert=False, rebuild_search=False,
                        )
                    self.assertTrue(frappe.db.exists(doctype, erp_name))
                    self.assertTrue(frappe.db.exists(doctype, crm_name))
        self.assertEqual(
            frappe.db.get_value("Customer", erp_customer, "customer_group"),
            "All Customer Groups",
        )
        self.assertEqual(
            frappe.db.get_value("Dynamic Link", erp_contact_doc.links[0].name, "link_name"),
            erp_customer,
        )
        self.assertEqual(
            frappe.db.get_value("Dynamic Link", erp_address_doc.links[0].name, "link_name"),
            erp_customer,
        )
        self.assertEqual(
            frappe.db.get_value("Lead", erp_lead_doc.name, "lead_owner"), erp_user,
        )

    def test_native_erp_customer_merge_remains_available(self):
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=8)
        source = self._create_customer(f"Merge ERP Source {suffix}", "Administrator")
        target = self._create_customer(f"Merge ERP Target {suffix}", "Administrator")
        for name in (source, target):
            frappe.db.set_value("Customer", name, "customer_group", "All Customer Groups")
        self.assertEqual(
            frappe.rename_doc(
                "Customer", source, target, merge=True, force=True,
                show_alert=False, rebuild_search=False,
            ),
            target,
        )
        self.assertFalse(frappe.db.exists("Customer", source))
        self.assertTrue(frappe.db.exists("Customer", target))

    def test_user_merge_reconciles_surviving_crm_identity_shares(self):
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=8)
        source = self._create_user(f"crm-merge-source-{suffix}@example.invalid", "Employee")
        recipient = self._create_user(f"crm-merge-recipient-{suffix}@example.invalid", "Employee")
        customer = self._create_customer(f"Merge ERP Customer {suffix}", "Administrator")
        frappe.db.set_value("Customer", customer, "customer_group", "All Customer Groups")
        lead = self._create_lead(f"Merge ERP Lead {suffix}", source, "")
        transferred_share = add_share("Customer", customer, user=source, read=1).name
        lead_share = add_share("Lead", lead, user=recipient, read=1).name
        retained_share = add_share("Customer", customer, user=recipient, read=1).name

        frappe.rename_doc(
            "User", source, self.sales, merge=True, force=True,
            show_alert=False, rebuild_search=False,
        )

        self.assertEqual(frappe.db.get_value("Lead", lead, "lead_owner"), self.sales)
        self.assertFalse(frappe.db.exists("DocShare", transferred_share))
        self.assertFalse(frappe.db.exists("DocShare", lead_share))
        self.assertTrue(frappe.db.exists("DocShare", retained_share))
        self.assertTrue(frappe.db.exists("User", self.sales))

    def test_share_only_parent_limits_a_shared_child_table_to_that_parent(self):
        frappe.set_user("Administrator")
        role = "CRM Scope Shared Supplier Reader"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        user = self._create_user("crm-scope-shared-supplier@example.invalid", role)
        supplier_names = [f"SCOPE-SUP-{frappe.generate_hash(length=10)}" for _ in range(2)]
        for supplier in supplier_names:
            frappe.db.sql(
                "INSERT INTO `tabSupplier` "
                "(`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`) "
                "VALUES (%s, NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0)",
                (supplier,),
            )
        children = [
            self._insert_child({
                "doctype": "Allowed To Transact With",
                "parent": supplier,
                "parenttype": "Supplier",
                "parentfield": "companies",
            })
            for supplier in supplier_names
        ]
        self._insert_legacy_share("Supplier", supplier_names[0], user)
        frappe.clear_cache(user=user)

        self.assertEqual(
            set(self._native_child_rows(
                "Allowed To Transact With",
                "Supplier",
                user,
                children,
                "parentfield",
            )),
            {children[0]},
        )

    def test_business_child_scope_requires_parent_read(self):
        with (
            patch("rayher_crm.permissions.scope.frappe.has_permission", return_value=False),
            patch("rayher_crm.permissions.scope.DatabaseQuery.build_match_conditions") as build,
        ):
            self.assertEqual(
                _parent_scope_condition(
                    "CRM Opportunity Stakeholder", "CRM Opportunity", "opportunity", self.sales,
                ),
                "1=0",
            )
            build.assert_not_called()

    def test_business_child_scope_keeps_native_and_service_restrictions(self):
        def build(query):
            self.assertEqual(query.reference_doctype, "CRM Opportunity")
            self.assertEqual(query.get_permission_query_conditions(), "")
            query.conditions.append("native_share_scope")
            return "native_match_scope"

        with (
            patch("rayher_crm.permissions.scope.frappe.has_permission", return_value=True),
            patch("rayher_crm.permissions.scope.DatabaseQuery.build_match_conditions", build),
            patch("rayher_crm.permissions.scope.conditions_for_doctype", return_value="service_scope"),
        ):
            condition = _parent_scope_condition(
                "CRM Opportunity Stakeholder", "CRM Opportunity", "opportunity", self.sales,
            )
        self.assertIn("(native_share_scope) AND (native_match_scope) AND (service_scope)", condition)
        self.assertIn("`tabCRM Opportunity`.`name` = `tabCRM Opportunity Stakeholder`.`opportunity`", condition)

    def test_business_child_scope_escapes_only_native_percent_for_bound_sql(self):
        def build(query):
            query.conditions.append("`tabCRM Opportunity`.`name` LIKE 'share%'")
            return "`tabCRM Opportunity`.`account` = '100% Customer'"

        with (
            patch("rayher_crm.permissions.scope.frappe.has_permission", return_value=True),
            patch("rayher_crm.permissions.scope.DatabaseQuery.build_match_conditions", build),
            patch(
                "rayher_crm.permissions.scope.conditions_for_doctype",
                return_value="`tabCRM Opportunity`.`title` LIKE 'service%%'",
            ),
        ):
            unbound = _parent_scope_condition(
                "CRM Opportunity Action", "CRM Opportunity", "opportunity", self.manager,
            )
            bound = _parent_scope_condition(
                "CRM Opportunity Action", "CRM Opportunity", "opportunity", self.manager,
                for_bound_query=True,
            )
        self.assertIn("LIKE 'share%'", unbound)
        self.assertIn("= '100% Customer'", unbound)
        self.assertIn("LIKE 'share%%'", bound)
        self.assertIn("= '100%% Customer'", bound)
        self.assertIn("LIKE 'service%%'", bound)
        self.assertNotIn("LIKE 'service%%%%'", bound)

    def test_business_child_scope_handles_native_permission_denial(self):
        with (
            patch("rayher_crm.permissions.scope.frappe.has_permission", return_value=True),
            patch(
                "rayher_crm.permissions.scope.DatabaseQuery.build_match_conditions",
                side_effect=frappe.PermissionError,
            ),
        ):
            self.assertEqual(
                _parent_scope_condition(
                    "CRM Opportunity Stakeholder", "CRM Opportunity", "opportunity", self.sales,
                ),
                "1=0",
            )

    def test_user_permission_cannot_replace_missing_parent_read_permission(self):
        frappe.set_user("Administrator")
        role = "CRM Scope Customer Child Reader"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        add_permission("Customer", role, 0, "read")
        user = self._create_user("crm-scope-no-supplier-read@example.invalid", role)
        supplier_names = [f"SCOPE-NO-READ-SUP-{frappe.generate_hash(length=10)}" for _ in range(2)]
        for supplier in supplier_names:
            frappe.db.sql(
                "INSERT INTO `tabSupplier` "
                "(`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`) "
                "VALUES (%s, NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0)",
                (supplier,),
            )
        children = [
            self._insert_child({
                "doctype": "Allowed To Transact With",
                "parent": supplier,
                "parenttype": "Supplier",
                "parentfield": "companies",
            })
            for supplier in supplier_names
        ]
        add_user_permission("Supplier", supplier_names[0], user, ignore_permissions=True)
        frappe.clear_cache(user=user)

        self.assertFalse(frappe.has_permission(
            "Supplier", "read", user=user,
        ))
        self.assertEqual(
            self._native_child_rows(
                "Allowed To Transact With", "Customer", user, children, "parentfield",
            ),
            {},
        )

    def test_parent_applicable_user_permission_filters_child_table_rows(self):
        frappe.set_user("Administrator")
        role = "CRM Scope Customer Supplier Reader"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        for doctype in ("Customer", "Supplier"):
            add_permission(doctype, role, 0, "read")
        user = self._create_user("crm-scope-supplier-user-permission@example.invalid", role)
        supplier_names = [f"SCOPE-LIMITED-SUP-{frappe.generate_hash(length=10)}" for _ in range(2)]
        for supplier in supplier_names:
            frappe.db.sql(
                "INSERT INTO `tabSupplier` "
                "(`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`) "
                "VALUES (%s, NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0)",
                (supplier,),
            )
        children = [
            self._insert_child({
                "doctype": "Allowed To Transact With",
                "parent": supplier,
                "parenttype": "Supplier",
                "parentfield": "companies",
            })
            for supplier in supplier_names
        ]
        add_user_permission(
            "Supplier", supplier_names[0], user,
            ignore_permissions=True, applicable_for="Supplier",
        )
        frappe.clear_cache(user=user)

        frappe.set_user(user)
        self.assertEqual(
            set(frappe.get_list(
                "Supplier", filters={"name": ["in", supplier_names]}, pluck="name",
            )),
            {supplier_names[0]},
        )
        self.assertEqual(
            set(self._native_child_rows(
                "Allowed To Transact With", "Customer", user, children, "parentfield",
            )),
            {children[0]},
        )

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
        self.assertIn("`tabCRM Demo Request History`", conditions_for_doctype("CRM Demo Request", self.engineer))
        # A draft names its Engineer but has not been submitted to them: Sales read it, the Engineer does not.
        draft = self._create_demo_request(
            self.owned_customer, self.owned_contact, self.owned_opportunity, self.sales, self.engineer,
            submitted=False,
        )
        self.assertIn(draft, self._visible_names("CRM Demo Request", self.sales))
        self.assertNotIn(draft, self._visible_names("CRM Demo Request", self.engineer))
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

    def test_link_search_cannot_disable_crm_row_scope(self):
        frappe.set_user("Administrator")
        owned = self._create_parent_scoped_rows(
            opportunity=self.owned_opportunity,
            contact=self.owned_contact,
            demo_request=self.owned_demo_request,
            evaluation=self.owned_evaluation,
            installed_tool=self.owned_tool,
            actor=self.sales,
            marker="owned search detail",
        )
        foreign = self._create_parent_scoped_rows(
            opportunity=self.foreign_opportunity,
            contact=self.foreign_contact,
            demo_request=self.foreign_demo_request,
            evaluation=self.foreign_evaluation,
            installed_tool=self.foreign_tool,
            actor=self.other_sales,
            marker="foreign search detail",
        )
        cases = (
            (self.sales, "CRM Opportunity Stakeholder"),
            (self.engineer, "CRM Opportunity History"),
        )
        for user, doctype in cases:
            owned_name, fieldname, _ = owned[doctype]
            foreign_name, _, foreign_value = foreign[doctype]
            filters = json.dumps({"name": ["in", [owned_name, foreign_name]]})
            frappe.set_user(user)
            # No custom query: Frappe's own search turns the flag into
            # get_list(ignore_permissions=True) unless the override drops it.
            with self.subTest(user=user, doctype=doctype, endpoint="widget"):
                rows = self._whitelisted_call(
                    "frappe.desk.search.search_widget",
                    doctype=doctype, txt="", filters=filters,
                    filter_fields=json.dumps([fieldname]), as_dict="1",
                    page_length="100", ignore_user_permissions="1",
                )
                self.assertEqual({row["name"] for row in rows}, {owned_name})
                self.assertNotIn(foreign_value, {row.get(fieldname) for row in rows})
            with self.subTest(user=user, doctype=doctype, endpoint="link"):
                rows = self._whitelisted_call(
                    "frappe.desk.search.search_link",
                    doctype=doctype, txt="", filters=filters,
                    page_length="100", ignore_user_permissions="1",
                )
                self.assertEqual({row["value"] for row in rows}, {owned_name})

    def test_whitelisted_link_search_cannot_list_child_rows_outside_the_parent_scope(self):
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Customer", self.foreign_customer, "custom_crm_visibility", "Private",
            update_modified=False,
        )
        foreign_quotation = frappe.get_doc({
            "doctype": "CRM Quotation", "ref_no": "SEARCH-foreign",
            "quotation_type": "Device", "account": self.foreign_customer,
            "quotation_owner": self.other_sales, "status": "Draft",
        }).insert(ignore_permissions=True)
        foreign_version = frappe.get_doc({
            "doctype": "CRM Quotation Version", "quotation": foreign_quotation.name,
            "version_no": 1, "quotation_type": "Device", "status": "Draft",
            "approval_status": "Not Submitted", "ref_no": foreign_quotation.ref_no,
            "account": self.foreign_customer, "quotation_owner": self.other_sales,
            "quote_date": "2026-12-01", "validity_months": 1, "valid_until": "2026-12-31",
            "currency": "CNY", "discount_type": "None", "incoterm": "FOB",
            "items": [{
                "line_key": "line-search-foreign", "line_type": "Device",
                "item_name": "foreign searched quotation item", "pricing_mode": "Charged",
                "quantity": 1, "unit_price": 987654, "line_amount": 987654,
            }],
            "payment_terms": [{
                "percentage": 100, "trigger_condition": "Acceptance",
                "description": "foreign searched payment term",
            }],
        }).insert(ignore_permissions=True)
        foreign_contact_link = frappe.db.get_value(
            "Dynamic Link",
            {"parent": self.foreign_contact, "parenttype": "Contact", "parentfield": "links"},
            "name",
        )
        foreign_site_link = frappe.db.get_value(
            "Dynamic Link",
            {"parent": self.foreign_site, "parenttype": "Address", "parentfield": "links"},
            "name",
        )
        # Search must also reject child rows with a missing parent, even when
        # every signed-in user holds read on the parent DocType.
        communication_link = self._insert_child({
            "doctype": "Communication Link", "parenttype": "Communication",
            "parent": f"SCOPE-COMM-{frappe.generate_hash(length=8)}",
            "parentfield": "timeline_links", "link_doctype": "Customer",
            "link_name": self.foreign_customer, "link_title": "Scope Foreign Customer",
        })
        event_participant = self._insert_child({
            "doctype": "Event Participants", "parenttype": "Event",
            "parent": f"SCOPE-EVENT-{frappe.generate_hash(length=8)}",
            "parentfield": "event_participants", "reference_doctype": "Customer",
            "reference_docname": self.foreign_customer,
        })
        cases = (
            (
                "CRM Quotation Item", "CRM Quotation Version", foreign_version.items[0].name,
                ["item_name", "unit_price"], "foreign searched quotation item",
            ),
            (
                "Dynamic Link", "Contact", foreign_contact_link,
                ["link_name", "link_title"], self.foreign_customer,
            ),
            (
                "Dynamic Link", "Address", foreign_site_link,
                ["link_name", "link_title"], self.foreign_customer,
            ),
            (
                "Communication Link", "Communication", communication_link,
                ["link_name", "link_title"], self.foreign_customer,
            ),
            (
                "Event Participants", "Event", event_participant,
                ["reference_docname"], self.foreign_customer,
            ),
        )
        frappe.set_user(self.sales)
        for doctype, reference_doctype, hidden, fields, marker in cases:
            for cmd in ("frappe.desk.search.search_widget", "frappe.desk.search.search_link"):
                with self.subTest(doctype=doctype, reference=reference_doctype, cmd=cmd):
                    params = {
                        "doctype": doctype, "txt": "", "reference_doctype": reference_doctype,
                        "filters": json.dumps({"name": ["in", [hidden]]}),
                        "page_length": "100", "ignore_user_permissions": "1",
                    }
                    if cmd.endswith("search_widget"):
                        params.update(filter_fields=json.dumps(fields), as_dict="1")
                    try:
                        result = json.dumps(self._whitelisted_call(cmd, **params), default=str)
                    except frappe.PermissionError:
                        # A child table has no parent context here, so the scoped
                        # list refuses it outright; that discloses nothing.
                        result = "[]"
                    self.assertNotIn(str(hidden), result)
                    self.assertNotIn(marker, result)

    def test_link_search_keeps_frappe_flag_and_query_where_no_crm_scope_applies(self):
        frappe.set_user("Administrator")
        erp_role = "CRM Scope Search ERP User"
        if not frappe.db.exists("Role", erp_role):
            frappe.get_doc({"doctype": "Role", "role_name": erp_role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        erp_user = self._create_user("crm-scope-search-erp@example.invalid", erp_role)
        self._grant_address_role(erp_user, "CRM Scope Search ERP Address Reader", {"read"})
        custom_query = "erpnext.controllers.queries.lead_query"
        cases = (
            # A CRM row predicate restricts the caller: drop the flag and the query.
            (self.sales, "Lead", False),
            (self.sales, "Address", False),
            (erp_user, "Customer", False),
            # Child tables are authorised through the parent DocType alone.
            (self.manager, "Dynamic Link", False),
            ("Administrator", "Event Participants", False),
            # No CRM predicate restricts the caller: Frappe's semantics stay intact.
            ("Administrator", "Lead", True),
            (self.manager, "Customer", True),
            (erp_user, "Address", True),
            (self.sales, "Item", True),
        )
        for user, doctype, keeps_frappe_semantics in cases:
            with self.subTest(user=user, doctype=doctype):
                frappe.set_user(user)
                with patch.object(crm_search, "frappe_search_widget", return_value=[]) as search:
                    self._whitelisted_call(
                        "frappe.desk.search.search_widget",
                        doctype=doctype, txt="", query=custom_query,
                        ignore_user_permissions="1",
                    )
                self.assertEqual(search.call_count, 1)
                query = search.call_args.args[2]
                flag = search.call_args.kwargs["ignore_user_permissions"]
                if keeps_frappe_semantics:
                    self.assertEqual(query, custom_query)
                    self.assertTrue(flag)
                else:
                    self.assertIsNone(query)
                    self.assertFalse(flag)

    def test_link_search_preserves_unscoped_child_query_with_permissions_enabled(self):
        custom_query = (
            "erpnext.assets.doctype.asset_maintenance_log.asset_maintenance_log."
            "get_maintenance_tasks"
        )
        for user in ("Administrator", self.manager):
            with self.subTest(user=user):
                frappe.set_user(user)
                with patch.object(crm_search, "frappe_search_widget", return_value=[]) as search:
                    self._whitelisted_call(
                        "frappe.desk.search.search_widget",
                        doctype="Asset Maintenance Task", txt="", query=custom_query,
                        ignore_user_permissions="1",
                    )
                self.assertEqual(search.call_args.args[2], custom_query)
                self.assertFalse(search.call_args.kwargs["ignore_user_permissions"])

    def test_erp_asset_maintenance_task_link_uses_its_parent_query(self):
        frappe.set_user("Administrator")
        erp_user = self._create_user("crm-scope-maintenance@example.invalid", "Quality Manager")
        maintenance = f"CRM-SCOPE-MAINTENANCE-{frappe.generate_hash(length=8)}"
        task = "Inspect calibration"
        # A child fixture is sufficient for ERPNext's parent-filter query;
        # creating an Asset would introduce unrelated accounting side effects.
        self._insert_child({
            "doctype": "Asset Maintenance Task", "parent": maintenance,
            "parenttype": "Asset Maintenance", "parentfield": "asset_maintenance_tasks",
            "maintenance_task": task,
        })
        for user in ("Administrator", erp_user):
            frappe.set_user(user)
            for endpoint in ("search_widget", "search_link"):
                with self.subTest(user=user, endpoint=endpoint):
                    rows = self._whitelisted_call(
                        f"frappe.desk.search.{endpoint}",
                        doctype="Asset Maintenance Task", txt="",
                        query=(
                            "erpnext.assets.doctype.asset_maintenance_log."
                            "asset_maintenance_log.get_maintenance_tasks"
                        ),
                        filters=json.dumps({"asset_maintenance": maintenance}),
                        reference_doctype="Asset Maintenance Log",
                    )
                    values = [row["value"] if endpoint == "search_link" else row[0] for row in rows]
                    self.assertEqual(values, [task])

    def test_stock_address_search_keeps_custom_query_with_native_permissions(self):
        frappe.set_user("Administrator")
        stock_user = self._create_user("crm-scope-stock-search@example.invalid", "Stock User")
        frappe.set_user(stock_user)
        self.assertEqual(address_query(stock_user), "")
        custom_query = "erpnext.controllers.queries.get_warehouse_address"
        for endpoint in ("search_widget", "search_link"):
            with self.subTest(endpoint=endpoint), \
                patch.object(crm_search, "frappe_search_widget", return_value=[]) as search:
                self._whitelisted_call(
                    f"frappe.desk.search.{endpoint}", doctype="Address", txt="",
                    query=custom_query, ignore_user_permissions="1",
                    reference_doctype="Stock Entry",
                )
                self.assertEqual(search.call_args.args[2], custom_query)
                self.assertFalse(search.call_args.kwargs["ignore_user_permissions"])

    def test_stock_warehouse_address_search_uses_its_native_query(self):
        frappe.set_user("Administrator")
        stock_user = self._create_user("crm-scope-stock-address@example.invalid", "Stock User")
        warehouse = f"CRM-SCOPE-WAREHOUSE-{frappe.generate_hash(length=8)}"
        address = frappe.get_doc({
            "doctype": "Address", "address_title": warehouse, "address_type": "Shipping",
            "address_line1": "1 Warehouse Road", "city": "Shanghai", "country": "China",
        }).insert(ignore_permissions=True)
        self.assertEqual(address.owner, "Administrator")
        # The warehouse query reads only Address and its Dynamic Link rows;
        # keep the fixture independent of unrelated stock/accounting setup.
        self._insert_child({
            "doctype": "Dynamic Link", "parent": address.name,
            "parenttype": "Address", "parentfield": "links",
            "link_doctype": "Warehouse", "link_name": warehouse,
        })
        for mixed_role in (False, True):
            frappe.set_user("Administrator")
            if mixed_role:
                frappe.get_doc("User", stock_user).add_roles("CRM Sales")
                frappe.clear_cache(user=stock_user)
            frappe.set_user(stock_user)
            for endpoint in ("search_widget", "search_link"):
                with self.subTest(mixed_role=mixed_role, endpoint=endpoint):
                    rows = self._whitelisted_call(
                        f"frappe.desk.search.{endpoint}", doctype="Address", txt="",
                        query="erpnext.controllers.queries.get_warehouse_address",
                        filters=json.dumps({"warehouse": warehouse}),
                        reference_doctype="Stock Entry",
                    )
                    values = [row["value"] if endpoint == "search_link" else row[0] for row in rows]
                    self.assertEqual(values, [address.name])
            if mixed_role:
                # The warehouse selection exception ends with the Link query.
                self.assertNotIn(address.name, self._visible_names("Address", stock_user))
                with self.assertRaises(frappe.PermissionError):
                    client_get("Address", address.name)

    def test_manager_link_search_retains_native_customer_user_permissions(self):
        frappe.set_user("Administrator")
        add_user_permission(
            "Customer", self.owned_customer, self.manager, ignore_permissions=True,
        )
        frappe.clear_cache(user=self.manager)
        try:
            for doctype, owned_name, foreign_name in (
                ("Customer", self.owned_customer, self.foreign_customer),
                ("CRM Opportunity", self.owned_opportunity, self.foreign_opportunity),
            ):
                frappe.set_user(self.manager)
                filters = json.dumps({"name": ["in", [owned_name, foreign_name]]})
                with self.subTest(doctype=doctype, endpoint="widget"):
                    rows = self._whitelisted_call(
                        "frappe.desk.search.search_widget", doctype=doctype, txt="",
                        filters=filters, as_dict="1", page_length="100",
                        ignore_user_permissions="1",
                    )
                    self.assertEqual({row["name"] for row in rows}, {owned_name})
                with self.subTest(doctype=doctype, endpoint="link"):
                    rows = self._whitelisted_call(
                        "frappe.desk.search.search_link", doctype=doctype, txt="",
                        filters=filters, page_length="100", ignore_user_permissions="1",
                    )
                    self.assertEqual({row["value"] for row in rows}, {owned_name})
        finally:
            frappe.set_user("Administrator")
            remove_user_permission(
                "Customer", self.owned_customer, self.manager, ignore_permissions=True,
            )
            frappe.clear_cache(user=self.manager)

    def test_doc_event_hooks_only_use_events_frappe_raises(self):
        # A doc event Frappe never raises reads like a guard but runs nothing (#68).
        # Frappe 15 has no before_delete: native deletion is guarded by the
        # has_permission("delete") check delete_doc performs.
        import frappe.model.delete_doc
        import frappe.model.document
        import frappe.model.rename_doc
        from rayher_crm.hooks import doc_events

        raised = set()
        for module in (frappe.model.document, frappe.model.delete_doc, frappe.model.rename_doc):
            raised.update(re.findall(r"run_method\(\s*[\"'](\w+)[\"']", inspect.getsource(module)))
        self.assertTrue({"before_save", "validate", "on_trash"}.issubset(raised), raised)
        for doctype, events in doc_events.items():
            for event in events:
                with self.subTest(doctype=doctype, event=event):
                    self.assertIn(event, raised)

    def test_search_override_registry_covers_every_scoped_query_hook(self):
        from rayher_crm.hooks import override_whitelisted_methods, permission_query_conditions

        self.assertTrue(set(CONDITION_DOCTYPES).issubset(permission_query_conditions))
        self.assertEqual(
            {
                doctype
                for doctype, handler in permission_query_conditions.items()
                if handler == "rayher_crm.permissions.scope.scoped_child_query"
            },
            set(SCOPED_CHILD_RELATIONSHIPS),
        )
        frappe.set_user("Administrator")
        for child_doctype, expected_relationships in SCOPED_CHILD_RELATIONSHIPS.items():
            rows = frappe.get_all(
                "DocField",
                filters={
                    "fieldtype": ["in", ["Table", "Table MultiSelect"]],
                    "options": child_doctype,
                },
                fields=["parent", "fieldname"],
            ) + frappe.get_all(
                "Custom Field",
                filters={
                    "fieldtype": ["in", ["Table", "Table MultiSelect"]],
                    "options": child_doctype,
                },
                fields=["dt as parent", "fieldname"],
            )
            self.assertEqual(
                {(row.parent, row.fieldname) for row in rows},
                set(expected_relationships),
                child_doctype,
            )
        for doctype, handler in permission_query_conditions.items():
            if handler.startswith("rayher_crm."):
                self.assertTrue(_has_rayher_permission_query(doctype), doctype)
        self.assertEqual(
            override_whitelisted_methods,
            {
                "frappe.desk.search.search_link": "rayher_crm.api.search.search_link",
                "frappe.desk.search.search_widget": "rayher_crm.api.search.search_widget",
            },
        )
        for core_method, override in override_whitelisted_methods.items():
            self.assertEqual(frappe.override_whitelisted_method(core_method), override)

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

    def test_parent_scoped_rows_inherit_customer_user_permissions(self):
        frappe.set_user("Administrator")

        def insert_raw(values: dict) -> str:
            document = frappe.get_doc(values)
            document.name = frappe.generate_hash(length=10)
            document.db_insert()
            return document.name

        owned = self._create_parent_scoped_rows(
            opportunity=self.owned_opportunity,
            contact=self.owned_contact,
            demo_request=self.owned_demo_request,
            evaluation=self.owned_evaluation,
            installed_tool=self.owned_tool,
            actor=self.manager,
            marker="user permission owned detail",
        )
        foreign = self._create_parent_scoped_rows(
            opportunity=self.foreign_opportunity,
            contact=self.foreign_contact,
            demo_request=self.foreign_demo_request,
            evaluation=self.foreign_evaluation,
            installed_tool=self.foreign_tool,
            actor=self.manager,
            marker="user permission foreign detail",
        )
        special_children: dict[str, tuple[str, str, str]] = {}
        for label, account, opportunity in (
            ("owned", self.owned_customer, self.owned_opportunity),
            ("foreign", self.foreign_customer, self.foreign_opportunity),
        ):
            marker = f"user permission {label} indirect detail"
            visit = insert_raw({
                "doctype": "CRM Visit", "account": account, "visit_owner": self.manager,
                "subject": marker, "visit_date": "2026-12-01", "visit_type": "On-site",
                "status": "Minutes Submitted", "objective": "Permission inheritance",
                "created_by_user": self.manager,
            })
            meeting = insert_raw({
                "doctype": "CRM Visit Meeting Record", "visit": visit, "summary": marker,
                "parse_status": "Parsed", "manually_corrected": 0,
            })
            quotation = insert_raw({
                "doctype": "CRM Quotation", "ref_no": f"UP-{label}",
                "quotation_type": "Device", "account": account,
                "quotation_owner": self.manager, "status": "Draft",
            })
            quotation_version = insert_raw({
                "doctype": "CRM Quotation Version", "quotation": quotation, "version_no": 1,
                "quotation_type": "Device", "status": "Draft", "approval_status": "Pending",
                "ref_no": f"UP-{label}", "account": account, "quotation_owner": self.manager,
                "quote_date": "2026-12-01", "validity_months": 1,
                "valid_until": "2026-12-31", "currency": "CNY",
                "discount_type": "None", "incoterm": "FOB",
            })
            approval = insert_raw({
                "doctype": "CRM Quotation Approval", "quotation": quotation,
                "quotation_version": quotation_version, "attempt_no": 1,
                "status": "Pending", "submitted_by": self.manager,
                "submitted_at": frappe.utils.now_datetime(), "decision_comment": marker,
            })
            rfq = insert_raw({
                "doctype": "CRM RFQ", "opportunity": opportunity, "account": account,
                "sales_owner": self.manager, "engineer_owner": self.engineer,
                "status": "Engineer Review",
            })
            rfq_version = insert_raw({
                "doctype": "CRM RFQ Version", "rfq": rfq, "version_no": 1,
                "status": "Engineer Review", "original_file": f"up-original-{label}",
                "file_name": f"{label}.pdf", "mime_type": "application/pdf", "size_bytes": 1,
                "content_hash": f"hash-{label}", "preview_file": f"up-preview-{label}",
                "preview_file_name": f"{label}-preview.pdf", "preview_mime_type": "application/pdf",
                "preview_content_hash": f"preview-hash-{label}", "uploaded_by": self.manager,
                "uploaded_at": frappe.utils.now_datetime(), "engineer_comment": marker,
            })
            special_children[f"CRM Visit Meeting Record:{label}"] = (meeting, "summary", marker)
            special_children[f"CRM Quotation Approval:{label}"] = (
                approval, "decision_comment", marker,
            )
            special_children[f"CRM RFQ Version:{label}"] = (
                rfq_version, "engineer_comment", marker,
            )
        add_user_permission(
            "Customer", self.owned_customer, self.manager, ignore_permissions=True,
        )
        frappe.clear_cache(user=self.manager)
        try:
            self.assertIn(
                self.owned_opportunity,
                self._visible_names("CRM Opportunity", self.manager),
            )
            self.assertNotIn(
                self.foreign_opportunity,
                self._visible_names("CRM Opportunity", self.manager),
            )
            address_rows = self._native_rows(
                "Address", self.manager, [self.owned_site, self.foreign_site], "address_line1",
            )
            self.assertEqual(set(address_rows), {self.owned_site})
            self.assertEqual(
                client_get("Address", self.owned_site)["address_line1"],
                address_rows[self.owned_site]["address_line1"],
            )
            with self.assertRaises(frappe.PermissionError):
                client_get("Address", self.foreign_site)
            for doctype, (owned_name, field, owned_value) in owned.items():
                foreign_name = foreign[doctype][0]
                rows = self._native_rows(
                    doctype, self.manager, [owned_name, foreign_name], field,
                )
                self.assertEqual(set(rows), {owned_name}, doctype)
                self.assertEqual(rows[owned_name][field], owned_value, doctype)
                self.assertEqual(client_get(doctype, owned_name)[field], owned_value, doctype)
                with self.assertRaises(frappe.PermissionError, msg=doctype):
                    client_get(doctype, foreign_name)
            for doctype in (
                "CRM Visit Meeting Record", "CRM Quotation Approval", "CRM RFQ Version",
            ):
                owned_name, field, owned_value = special_children[f"{doctype}:owned"]
                foreign_name = special_children[f"{doctype}:foreign"][0]
                rows = self._native_rows(
                    doctype, self.manager, [owned_name, foreign_name], field,
                )
                self.assertEqual(set(rows), {owned_name}, doctype)
                self.assertEqual(rows[owned_name][field], owned_value, doctype)
                self.assertEqual(client_get(doctype, owned_name)[field], owned_value, doctype)
                with self.assertRaises(frappe.PermissionError, msg=doctype):
                    client_get(doctype, foreign_name)
        finally:
            frappe.set_user("Administrator")
            remove_user_permission(
                "Customer", self.owned_customer, self.manager, ignore_permissions=True,
            )
            frappe.clear_cache(user=self.manager)

    def test_address_inherits_address_specific_customer_user_permissions(self):
        frappe.set_user("Administrator")
        add_user_permission(
            "Customer", self.owned_customer, self.manager,
            ignore_permissions=True, applicable_for="Address",
        )
        frappe.clear_cache(user=self.manager)
        try:
            rows = self._native_rows(
                "Address", self.manager, [self.owned_site, self.foreign_site], "address_line1",
            )
            self.assertEqual(set(rows), {self.owned_site})
            self.assertEqual(
                client_get("Address", self.owned_site)["address_line1"],
                rows[self.owned_site]["address_line1"],
            )
            with self.assertRaises(frappe.PermissionError):
                client_get("Address", self.foreign_site)
        finally:
            frappe.set_user("Administrator")
            remove_user_permission(
                "Customer", self.owned_customer, self.manager, ignore_permissions=True,
            )
            frappe.clear_cache(user=self.manager)

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
        # The Demo Request itself: a share of someone else's request used to open it, draft or not.
        foreign["CRM Demo Request"] = (self.foreign_demo_request, "title", "Scope Demo Request")
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
        self.assertEqual(address_query("Administrator"), "")
        self.assertEqual(
            set(self._native_rows("Address", "Administrator", names, "city")),
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

    def test_address_detail_supports_percent_in_customer_user_permission(self):
        frappe.set_user("Administrator")
        customer = self._create_customer("Scope 100% Customer", self.sales)
        site = create_site(customer, self._site_input("Percent Customer Site"))["id"]
        add_user_permission(
            "Customer", customer, self.sales,
            ignore_permissions=True, applicable_for="Address",
        )
        frappe.clear_cache(user=self.sales)
        try:
            self.assertEqual(
                set(self._native_rows("Address", self.sales, [site, self.owned_site], "city")),
                {site},
            )
            self.assertEqual(client_get("Address", site)["name"], site)
            self.assertFalse(has_address_permission(
                frappe.get_doc("Address", self.owned_site),
                user=self.sales, permission_type="read",
            ))
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", customer, self.sales, ignore_permissions=True)
            frappe.clear_cache(user=self.sales)

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
        self.assertIn("`tabCustomer`.`customer_group` = 'CRM Customers'", sales_condition)
        self.assertIn("`tabCustomer`.`custom_crm_owner`", sales_condition)
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

    def test_mixed_address_roles_preserve_erp_read_and_if_owner_constraints(self):
        frappe.set_user("Administrator")
        foreign_erp_address = frappe.get_doc({
            "doctype": "Address", "address_title": "Mixed role foreign ERP Address",
            "address_type": "Other", "address_line1": "Foreign ERP", "city": "Shanghai",
            "country": "China",
        }).insert(ignore_permissions=True).name

        create_only = self._create_user("crm-scope-create-only@example.invalid", "CRM Sales")
        self._grant_address_role(
            create_only, "CRM Scope ERP Address Create Only", {"create", "share"},
        )
        self.assertNotIn(foreign_erp_address, self._visible_names("Address", create_only))
        frappe.set_user(create_only)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", foreign_erp_address)

        frappe.set_user("Administrator")
        owner_reader = self._create_user("crm-scope-owner-reader@example.invalid", "CRM Sales")
        self._grant_address_role(
            owner_reader, "CRM Scope ERP Address Owner Reader", {"read"}, if_owner=True,
        )
        owned_erp_address = frappe.get_doc({
            "doctype": "Address", "address_title": "Mixed role owned ERP Address",
            "address_type": "Other", "address_line1": "Owned ERP", "city": "Suzhou",
            "country": "China",
        }).insert(ignore_permissions=True).name
        frappe.db.set_value("Address", owned_erp_address, "owner", owner_reader, update_modified=False)
        self.assertEqual(
            set(self._native_rows(
                "Address", owner_reader, [owned_erp_address, foreign_erp_address], "city",
            )),
            {owned_erp_address},
        )
        self.assertEqual(client_get("Address", owned_erp_address)["city"], "Suzhou")
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", foreign_erp_address)

        # Field-level DocPerm rows do not grant row-level Address access. A level
        # 1 non-owner read must not widen the level 0 if-owner ERP grant.
        frappe.set_user("Administrator")
        role = "CRM Scope ERP Address Owner Reader"
        add_permission("Address", role, 1, "read")
        update_permission_property("Address", role, 1, "read", 1, validate=False)
        update_permission_property("Address", role, 1, "if_owner", 0, validate=False)
        frappe.clear_cache(doctype="Address")
        frappe.clear_cache(user=owner_reader)
        self.assertEqual(
            set(self._native_rows(
                "Address", owner_reader, [owned_erp_address, foreign_erp_address], "city",
            )),
            {owned_erp_address},
        )

    def test_mixed_address_select_grant_only_expands_name_search(self):
        frappe.set_user("Administrator")
        address = frappe.get_doc({
            "doctype": "Address", "address_title": "Selectable ERP Address",
            "address_type": "Other", "address_line1": "ERP Selection Fixture",
            "city": "Shanghai", "country": "China",
        }).insert(ignore_permissions=True)
        user = self._create_user("crm-scope-address-select@example.invalid", "CRM Sales")
        self._grant_address_role(user, "CRM Scope Address Selection", {"select"})
        frappe.set_user(user)
        for endpoint in ("search_widget", "search_link"):
            with self.subTest(endpoint=endpoint):
                options = {"as_dict": "1"} if endpoint == "search_widget" else {}
                rows = self._whitelisted_call(
                    f"frappe.desk.search.{endpoint}", doctype="Address", txt="",
                    filters=json.dumps({"name": address.name}), **options,
                )
                if endpoint == "search_widget":
                    self.assertEqual([dict(row) for row in rows], [{"name": address.name}])
                else:
                    self.assertEqual([row["value"] for row in rows], [address.name])
                # The selection context ends with the query and never changes
                # the ordinary Address list or document-read permission.
                self.assertNotIn(address.name, self._visible_names("Address", user))
                with self.assertRaises(frappe.PermissionError):
                    client_get("Address", address.name)

    def test_mixed_address_owner_grant_keeps_ordinary_read_shares(self):
        frappe.set_user("Administrator")
        user = self._create_user("crm-scope-address-shared@example.invalid", "CRM Sales")
        self._grant_address_role(user, "CRM Scope Address Shared Owner Reader", {"read"}, if_owner=True)
        addresses = []
        for label in ("User shared", "Everyone shared", "Unshared"):
            addresses.append(frappe.get_doc({
                "doctype": "Address", "address_title": f"ERP {label}",
                "address_type": "Other", "address_line1": label,
                "city": "Shanghai", "country": "China",
            }).insert(ignore_permissions=True).name)
        add_share("Address", addresses[0], user=user, read=1)
        add_share("Address", addresses[1], everyone=1, read=1)
        self.assertEqual(
            set(self._native_rows("Address", user, addresses, "city")), set(addresses[:2]),
        )
        for name in addresses[:2]:
            frappe.set_user(user)
            self.assertEqual(client_get("Address", name)["city"], "Shanghai")
        frappe.set_user(user)
        rows = self._whitelisted_call(
            "frappe.desk.search.search_link", doctype="Address", txt="",
            filters=json.dumps({"name": ["in", addresses]}),
        )
        self.assertEqual({row["value"] for row in rows}, set(addresses[:2]))

    def test_address_with_a_dangling_customer_link_stays_inside_the_crm_boundary(self):
        frappe.set_user("Administrator")
        gone_customer = self._create_customer("Scope Deleted Customer", self.sales)
        orphan = frappe.get_doc({
            "doctype": "Address", "address_title": "Scope Orphan Address", "address_type": "Other",
            "address_line1": "Left behind", "city": "Shanghai", "country": "China",
            "links": [{"link_doctype": "Customer", "link_name": gone_customer}],
        }).insert(ignore_permissions=True).name
        # Frappe normally removes these links; a failed migration or direct SQL can leave one.
        frappe.db.delete("Customer", {"name": gone_customer})
        self.assertTrue(frappe.db.exists("Dynamic Link", {"parent": orphan, "link_name": gone_customer}))
        dual_role = self._create_user("crm-scope-orphan-erp@example.invalid", "CRM Sales")
        self._grant_explicit_address_role(dual_role)

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

        legacy_share = self._insert_legacy_share("Address", orphan, dual_role)
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", legacy_share))
        self.assertIn(orphan, set(frappe.get_list("Address", pluck="name")))

    def test_native_link_search_cannot_skip_the_crm_row_scope(self):
        for method in ("search_link", "search_widget"):
            overrides = frappe.get_hooks("override_whitelisted_methods")[f"frappe.desk.search.{method}"]
            self.assertEqual(overrides[-1], f"rayher_crm.api.search.{method}")

        hidden = self.foreign_booking
        frappe.set_user(self.sales)
        self.assertNotIn(hidden, self._visible_names("CRM Booking", self.sales))
        for ignore in ("0", "1"):
            with self.subTest(ignore=ignore):
                for method in ("search_link", "search_widget"):
                    self.assertNotIn(hidden, str(self._whitelisted_call(
                        f"frappe.desk.search.{method}",
                        doctype="CRM Booking", txt=hidden, searchfield="name",
                        ignore_user_permissions=ignore,
                    )))
        frappe.set_user(self.other_sales)
        for method in ("search_link", "search_widget"):
            self.assertIn(hidden, str(self._whitelisted_call(
                f"frappe.desk.search.{method}",
                doctype="CRM Booking", txt=hidden, searchfield="name",
                ignore_user_permissions="1",
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
        promoted_contact = self._create_contact(
            "ERP Contact Promoted To CRM", promoted_customer, erp_user,
        )
        promoted_lead = self._create_lead(
            "ERP Lead Promoted To CRM", erp_user, promoted_customer,
        )
        promoted_share = self._insert_legacy_share("Address", promoted_address.name, erp_user)
        for doctype, name in (
            ("Customer", promoted_customer),
            ("Contact", promoted_contact),
            ("Lead", promoted_lead),
        ):
            add_share(doctype, name, user=erp_user, read=1, write=1)
        frappe.set_user(erp_user)
        self.assertEqual(client_get("Address", promoted_address.name)["city"], "Shanghai")
        for doctype, name in (
            ("Customer", promoted_customer),
            ("Contact", promoted_contact),
            ("Lead", promoted_lead),
        ):
            self.assertEqual(client_get(doctype, name)["name"], name)
        frappe.set_user("Administrator")
        customer_doc = frappe.get_doc("Customer", promoted_customer)
        customer_doc.customer_group = "CRM Customers"
        customer_doc.save(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("DocShare", promoted_share))
        for doctype, name in (
            ("Customer", promoted_customer),
            ("Contact", promoted_contact),
            ("Lead", promoted_lead),
        ):
            self.assertFalse(frappe.db.exists("DocShare", {
                "share_doctype": doctype, "share_name": name, "user": erp_user,
            }))
        with self.assertRaises(frappe.PermissionError):
            add_share("Address", promoted_address.name, user=erp_user, read=1)
        frappe.set_user(erp_user)
        with self.assertRaises(frappe.PermissionError):
            client_get("Address", promoted_address.name)
        for doctype, name in (
            ("Customer", promoted_customer),
            ("Contact", promoted_contact),
            ("Lead", promoted_lead),
        ):
            with self.assertRaises(frappe.PermissionError):
                client_get(doctype, name)
            try:
                visible = self._visible_names(doctype, erp_user)
            except frappe.PermissionError:
                visible = set()
            self.assertNotIn(name, visible)
        with self.assertRaises(frappe.PermissionError):
            client_set_value("Customer", promoted_customer, "custom_crm_city", "SHARE-BYPASS")

    def test_contact_lead_and_recipient_transitions_revoke_erp_shares(self):
        frappe.set_user("Administrator")
        role = "CRM Scope ERP Transition Recipient"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        recipient = self._create_user("crm-scope-role-transition@example.invalid", role)
        erp_customer = self._create_customer(
            f"Scope transition ERP {frappe.generate_hash(length=8)}", recipient,
        )
        frappe.db.set_value("Customer", erp_customer, "customer_group", None, update_modified=False)
        contact = self._create_contact("Scope transition contact", erp_customer, recipient)
        lead = self._create_lead("Scope transition lead", recipient, erp_customer)

        add_share("Contact", contact, user=recipient, read=1, write=1)
        add_share("Lead", lead, user=recipient, read=1, write=1)
        contact_doc = frappe.get_doc("Contact", contact)
        contact_doc.append("links", {
            "link_doctype": "Customer", "link_name": self.owned_customer,
        })
        contact_doc.save(ignore_permissions=True)
        lead_doc = frappe.get_doc("Lead", lead)
        lead_doc.custom_crm_converted_account = self.owned_customer
        lead_doc.save(ignore_permissions=True)
        for doctype, name in (("Contact", contact), ("Lead", lead)):
            self.assertFalse(frappe.db.exists("DocShare", {
                "share_doctype": doctype, "share_name": name, "user": recipient,
            }))
            with self.assertRaises(frappe.PermissionError):
                add_share(doctype, name, user=recipient, read=1)

        role_customer = self._create_customer(
            f"Scope recipient role ERP {frappe.generate_hash(length=8)}", recipient,
        )
        frappe.db.set_value("Customer", role_customer, "customer_group", None, update_modified=False)
        role_contact = self._create_contact("Scope recipient role contact", role_customer, recipient)
        role_lead = self._create_lead("Scope recipient role lead", recipient, role_customer)
        for doctype, name in (
            ("Customer", role_customer), ("Contact", role_contact), ("Lead", role_lead),
        ):
            add_share(doctype, name, user=recipient, read=1, write=1)
        frappe.get_doc("User", recipient).add_roles("CRM Sales")
        for doctype, name in (
            ("Customer", role_customer), ("Contact", role_contact), ("Lead", role_lead),
        ):
            self.assertFalse(frappe.db.exists("DocShare", {
                "share_doctype": doctype, "share_name": name, "user": recipient,
            }))

    def test_scoped_parents_reject_new_shares_and_install_removes_legacy_shares(self):
        frappe.set_user("Administrator")
        target = frappe.get_doc({
            "doctype": "CRM Cockpit Target",
            "name": f"scope-target-{frappe.generate_hash(length=8)}",
            "sales_owner": self.sales, "metric": "visits", "period": "month",
            "anchor": "2026-09-01", "target_value": "1", "changed_by": "Administrator",
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):
            add_share(
                "CRM Opportunity", self.foreign_opportunity,
                user=self.sales, read=1, write=1,
            )
        with self.assertRaises(frappe.PermissionError):
            add_share("CRM Cockpit Target", target.name, user=self.sales, read=1, write=1)
        with self.assertRaises(frappe.PermissionError):
            add_share(
                "Customer", self.foreign_customer,
                user=self.sales, read=1, write=1,
            )

        crm_opportunity_share = self._insert_legacy_share(
            "CRM Opportunity", self.owned_opportunity, self.other_sales, write=1, submit=1,
        )
        crm_customer_share = self._insert_legacy_share(
            "Customer", self.owned_customer, self.other_sales, write=1, submit=1,
        )
        crm_unscoped_custom_share = self._insert_legacy_share(
            "CRM Cockpit Target", target.name, self.other_sales, write=1,
        )
        erp_customer = self._create_customer(
            f"Scope ordinary ERP share {frappe.generate_hash(length=10)}", self.other_sales,
        )
        frappe.db.set_value("Customer", erp_customer, "customer_group", None, update_modified=False)
        erp_role = "CRM Scope Ordinary ERP Share User"
        if not frappe.db.exists("Role", erp_role):
            frappe.get_doc({"doctype": "Role", "role_name": erp_role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        erp_user = self._create_user("crm-scope-ordinary-share@example.invalid", erp_role)
        erp_share = self._insert_legacy_share(
            "Customer", erp_customer, erp_user, write=1, submit=1,
        )

        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", crm_opportunity_share))
        self.assertFalse(frappe.db.exists("DocShare", crm_customer_share))
        self.assertFalse(frappe.db.exists("DocShare", crm_unscoped_custom_share))
        self.assertEqual(
            frappe.db.get_value("DocShare", erp_share, ["read", "write", "submit"], as_dict=True),
            {"read": 1, "write": 1, "submit": 1},
        )

        # An ordinary ERP Customer remains shareable to a non-CRM ERP identity.
        add_share("Customer", erp_customer, user=erp_user, read=1)
        self.assertTrue(frappe.db.exists("DocShare", {
            "share_doctype": "Customer", "share_name": erp_customer, "user": erp_user,
        }))

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

    def _create_erp_address_writer(self) -> str:
        role = "CRM Scope Concurrent ERP Address Writer"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        add_permission("Address", role, 0, "read")
        for permission_type in ("read", "write", "delete"):
            update_permission_property(
                "Address", role, 0, permission_type, 1, validate=False,
            )
        user = "crm-scope-concurrent-address-writer@example.invalid"
        if not frappe.db.exists("User", user):
            frappe.get_doc({
                "doctype": "User", "email": user, "first_name": "Concurrent Address Writer",
                "enabled": 1, "send_welcome_email": 0,
                "roles": [{"role": "CRM Sales"}, {"role": role}],
            }).insert(ignore_permissions=True)
        else:
            frappe.get_doc("User", user).add_roles("CRM Sales", role)
        frappe.clear_cache(doctype="Address")
        frappe.clear_cache(user=user)
        return user

    def _create_erp_share_recipient(self) -> str:
        role = "CRM Scope Concurrent ERP Share Recipient"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True,
            )
        user = "crm-scope-concurrent-share-recipient@example.invalid"
        if not frappe.db.exists("User", user):
            frappe.get_doc({
                "doctype": "User", "email": user, "first_name": "Concurrent Share Recipient",
                "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
            }).insert(ignore_permissions=True)
        return user

    def _create_linked_erp_address(self, customer: str, suffix: str) -> str:
        return frappe.get_doc({
            "doctype": "Address", "address_title": f"Scope Concurrent Native {suffix}",
            "address_type": "Other", "address_line1": "Before promotion", "city": "Shanghai",
            "country": "China", "links": [{"link_doctype": "Customer", "link_name": customer}],
        }).insert(ignore_permissions=True).name

    def _create_linked_erp_record(self, kind: str, customer: str, owner: str, suffix: str) -> str:
        if kind == "Address":
            return self._create_linked_erp_address(customer, suffix)
        if kind == "Contact":
            return frappe.get_doc({
                "doctype": "Contact", "first_name": f"Concurrent Held Contact {suffix}",
                "links": [{"link_doctype": "Customer", "link_name": customer}],
            }).insert(ignore_permissions=True).name
        return frappe.get_doc({
            "doctype": "Lead", "first_name": f"Concurrent Held Lead {suffix}",
            "company_name": f"Concurrent Held Lead {suffix}", "status": "Lead",
            "lead_owner": owner, "custom_crm_converted_account": customer,
        }).insert(ignore_permissions=True).name

    def _insert_erp_share(self, doctype: str, name: str, user: str) -> str:
        share = frappe.get_doc({
            "doctype": "DocShare", "user": user, "share_doctype": doctype,
            "share_name": name, "read": 1, "write": 1,
        })
        share.name = frappe.generate_hash(length=10)
        share.db_insert()
        return share.name

    def _delete_linked_erp_record(self, kind: str, name: str) -> None:
        frappe.db.delete("DocShare", {"share_doctype": kind, "share_name": name})
        if kind in {"Address", "Contact"}:
            frappe.db.delete("Dynamic Link", {"parent": name, "parenttype": kind})
        frappe.db.delete(kind, {"name": name})

    def test_boundary_transition_lookups_lock_only_related_rows(self):
        # NOWAIT fails a transition on any row its locking read touches, so every
        # lookup must reach the related rows through an index instead of a scan.
        for query, values, table in (
            (_CUSTOMER_CONVERTED_LEAD_QUERY, ("scope-missing-customer",), "tabLead"),
            (_CUSTOMER_LINKED_PARENTS_QUERY, ("Address", "scope-missing-customer"), "tabDynamic Link"),
            (_CUSTOMER_LINKED_PARENTS_QUERY, ("Contact", "scope-missing-customer"), "tabDynamic Link"),
            (_OWNED_LEADS_QUERY, ("scope-missing@example.invalid",), "tabLead"),
        ):
            with self.subTest(table=table, values=values):
                self.assertIn("NOWAIT", query)
                plan = frappe.db.sql("EXPLAIN " + query, values, as_dict=True)
                steps = [row for row in plan if row.table == table]
                self.assertTrue(steps, plan)
                self.assertTrue(all(row.key for row in steps), plan)
                self.assertFalse({"ALL", "index"}.intersection(row.type for row in steps), plan)

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

    def test_customer_promotion_blocks_stale_native_address_write_and_delete(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        writer = self._create_erp_address_writer()
        records = []
        for action in ("write", "delete"):
            customer = self._create_erp_customer(f"{suffix}-{action}")
            address = self._create_linked_erp_address(customer, f"{suffix}-{action}")
            records.append((customer, address))
        primary = frappe.local.db
        primary.commit()

        try:
            for action, (customer, address) in zip(("write", "delete"), records, strict=True):
                with self.secondary_connection():
                    frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    frappe.set_user(writer)
                    self.assertIsNone(frappe.db.get_value("Customer", customer, "customer_group"))
                    address_doc = frappe.get_doc("Address", address)

                    with self.primary_connection():
                        frappe.set_user("Administrator")
                        frappe.db.set_value(
                            "Customer", customer, "customer_group", "CRM Customers",
                            update_modified=False,
                        )
                        frappe.db.commit()

                    frappe.set_user(writer)
                    with self.assertRaises(frappe.PermissionError):
                        if action == "write":
                            address_doc.address_line1 = "Native write after promotion"
                            address_doc.save()
                        else:
                            address_doc.delete()
                    frappe.db.rollback()

                with self.primary_connection():
                    self.assertTrue(frappe.db.exists("Address", address))
                    self.assertEqual(
                        frappe.db.get_value("Address", address, "address_line1"),
                        "Before promotion",
                    )
        finally:
            frappe.local.db = primary
            primary.rollback()
            frappe.set_user("Administrator")
            for customer, address in records:
                frappe.db.delete("Dynamic Link", {"parent": address, "parenttype": "Address"})
                frappe.db.delete("Address", {"name": address})
                frappe.db.delete("Customer", {"name": customer})
            primary.commit()

    def test_address_mutation_checks_current_links_after_loading_the_document(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        writer = self._create_erp_address_writer()
        customer = self._create_erp_customer(suffix)
        crm_customer = self._create_erp_customer(f"{suffix}-crm")
        frappe.db.set_value(
            "Customer", crm_customer, "customer_group", "CRM Customers", update_modified=False,
        )
        address = self._create_linked_erp_address(customer, suffix)
        primary = frappe.local.db
        primary.commit()
        try:
            with self.secondary_connection():
                frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                frappe.set_user(writer)
                address_doc = frappe.get_doc("Address", address)
                self.assertEqual(address_doc.links[0].link_name, customer)
                with self.primary_connection():
                    frappe.set_user("Administrator")
                    frappe.db.set_value(
                        "Dynamic Link",
                        {"parent": address, "parenttype": "Address", "parentfield": "links"},
                        "link_name", crm_customer, update_modified=False,
                    )
                    frappe.db.commit()
                frappe.set_user(writer)
                # The loaded document keeps its ERP link; mutation permission
                # must use the current stored CRM association as well.
                for permission_type in ("write", "delete"):
                    self.assertFalse(has_address_permission(
                        address_doc, user=writer, permission_type=permission_type,
                    ))
                frappe.db.rollback()
            with self.primary_connection():
                self.assertTrue(frappe.db.exists("Address", address))
        finally:
            frappe.local.db = primary
            primary.rollback()
            frappe.set_user("Administrator")
            self._delete_linked_erp_record("Address", address)
            frappe.db.delete("Customer", {"name": customer})
            frappe.db.delete("Customer", {"name": crm_customer})
            primary.commit()

    def test_customer_promotion_and_share_creation_cannot_leave_a_share(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        customer = self._create_erp_customer(frappe.generate_hash(length=10))
        recipient = self._create_erp_share_recipient()
        site = frappe.local.site
        frappe.db.commit()
        plan = frappe.db.sql(
            "EXPLAIN " + _CUSTOMER_CONVERTED_LEAD_QUERY, (customer,), as_dict=True,
        )
        lead_steps = [row for row in plan if row.table == "tabLead"]
        self.assertTrue(lead_steps)
        self.assertEqual(
            {row.key for row in lead_steps}, {"custom_crm_converted_account_index"},
        )
        self.assertFalse({"ALL", "index"}.intersection(row.type for row in lead_steps))
        gate = Barrier(2)

        def share_customer() -> str:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                gate.wait(timeout=10)
                add_share("Customer", customer, user=recipient, read=1, write=1)
                frappe.db.commit()
                return "created"
            except frappe.PermissionError:
                frappe.db.rollback()
                return "blocked"
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                frappe.destroy()

        def promote_customer() -> None:
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
                share_future = executor.submit(share_customer)
                promote_future = executor.submit(promote_customer)
                self.assertIn(share_future.result(timeout=30), {"created", "blocked"})
                promote_future.result(timeout=30)
            self.assertEqual(
                frappe.db.get_value("Customer", customer, "customer_group"), "CRM Customers",
            )
            self.assertFalse(frappe.db.exists("DocShare", {
                "share_doctype": "Customer", "share_name": customer, "user": recipient,
            }))
        finally:
            frappe.db.rollback()
            frappe.db.delete("DocShare", {"share_doctype": "Customer", "share_name": customer})
            frappe.db.delete("Customer", {"name": customer})
            frappe.db.commit()

    def test_customer_promotion_retries_instead_of_waiting_for_a_contact_save(self):
        # Frappe locks a Contact and its links before the Contact hook waits for the
        # Customer. The promotion must neither wait for that Contact (deadlock) nor
        # commit without it: it aborts, the save goes on, and a retry revokes the share.
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        customer = self._create_erp_customer(suffix)
        recipient = self._create_erp_share_recipient()
        contact = frappe.get_doc({
            "doctype": "Contact", "first_name": f"Concurrent Contact {suffix}",
            "links": [{"link_doctype": "Customer", "link_name": customer}],
        }).insert(ignore_permissions=True).name
        share = frappe.get_doc({
            "doctype": "DocShare", "user": recipient, "share_doctype": "Contact",
            "share_name": contact, "read": 1, "write": 1,
        })
        share.name = frappe.generate_hash(length=10)
        share.db_insert()
        site = frappe.local.site
        frappe.db.commit()
        contact_locked = Event()
        customer_locked = Event()

        def save_contact_boundary() -> None:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                contact_doc = frappe.get_doc("Contact", contact)
                frappe.db.sql(
                    "SELECT `name` FROM `tabContact` WHERE `name` = %s FOR UPDATE", (contact,),
                )
                frappe.db.sql(
                    "SELECT `name` FROM `tabDynamic Link` "
                    "WHERE `parent` = %s AND `parenttype` = 'Contact' FOR UPDATE",
                    (contact,),
                )
                contact_locked.set()
                self.assertTrue(customer_locked.wait(timeout=10))
                revoke_contact_shares_entering_crm(contact_doc)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                frappe.destroy()

        def promote_customer_boundary() -> str:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                self.assertTrue(contact_locked.wait(timeout=10))
                frappe.db.sql(
                    "SELECT `name` FROM `tabCustomer` WHERE `name` = %s FOR UPDATE", (customer,),
                )
                customer_doc = frappe.get_doc("Customer", customer)
                customer_doc.customer_group = "CRM Customers"
                customer_locked.set()
                try:
                    revoke_customer_address_shares_entering_crm(customer_doc)
                except frappe.PermissionError:
                    frappe.db.rollback()
                    return "retry"
                frappe.db.sql(
                    "UPDATE `tabCustomer` SET `customer_group` = 'CRM Customers' "
                    "WHERE `name` = %s",
                    (customer,),
                )
                frappe.db.commit()
                return "promoted"
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                customer_locked.set()
                frappe.destroy()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                save_future = executor.submit(save_contact_boundary)
                promote_future = executor.submit(promote_customer_boundary)
                self.assertEqual(promote_future.result(timeout=30), "retry")
                save_future.result(timeout=30)
            self.assertIsNone(frappe.db.get_value("Customer", customer, "customer_group"))
            self.assertTrue(frappe.db.exists("DocShare", share.name))

            customer_doc = frappe.get_doc("Customer", customer)
            customer_doc.customer_group = "CRM Customers"
            customer_doc.save(ignore_permissions=True)
            frappe.db.commit()
            self.assertFalse(frappe.db.exists("DocShare", share.name))
        finally:
            frappe.db.rollback()
            frappe.db.delete("DocShare", {"share_doctype": "Contact", "share_name": contact})
            frappe.db.delete("Dynamic Link", {"parent": contact, "parenttype": "Contact"})
            frappe.db.delete("Contact", {"name": contact})
            frappe.db.delete("Customer", {"name": customer})
            frappe.db.commit()

    def test_contact_boundary_save_rejects_share_after_cleanup_before_commit(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        erp_customer = self._create_erp_customer(f"{suffix}-erp")
        crm_customer = self._create_erp_customer(f"{suffix}-crm")
        frappe.db.set_value(
            "Customer", crm_customer, "customer_group", "CRM Customers", update_modified=False,
        )
        recipient = self._create_erp_share_recipient()
        contact = frappe.get_doc({
            "doctype": "Contact", "first_name": f"Boundary Contact {suffix}",
            "links": [{"link_doctype": "Customer", "link_name": erp_customer}],
        }).insert(ignore_permissions=True).name
        site = frappe.local.site
        frappe.db.commit()
        cleanup_finished = Event()
        share_attempt_finished = Event()

        def save_contact_boundary() -> None:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                contact_doc = frappe.get_doc("Contact", contact)
                contact_doc.append(
                    "links", {"link_doctype": "Customer", "link_name": crm_customer},
                )
                contact_doc.save(ignore_permissions=True)
                cleanup_finished.set()
                self.assertTrue(share_attempt_finished.wait(timeout=10))
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                frappe.destroy()

        def share_contact_after_cleanup() -> str:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                self.assertTrue(cleanup_finished.wait(timeout=10))
                add_share("Contact", contact, user=recipient, read=1, write=1)
                frappe.db.commit()
                return "created"
            except frappe.PermissionError:
                frappe.db.rollback()
                return "blocked"
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                share_attempt_finished.set()
                frappe.destroy()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                save_future = executor.submit(save_contact_boundary)
                share_future = executor.submit(share_contact_after_cleanup)
                self.assertEqual(share_future.result(timeout=30), "blocked")
                save_future.result(timeout=30)
            self.assertTrue(frappe.db.exists("Dynamic Link", {
                "parent": contact, "parenttype": "Contact", "parentfield": "links",
                "link_doctype": "Customer", "link_name": crm_customer,
            }))
            self.assertFalse(frappe.db.exists("DocShare", {
                "share_doctype": "Contact", "share_name": contact, "user": recipient,
            }))
        finally:
            frappe.db.rollback()
            frappe.db.delete("DocShare", {"share_doctype": "Contact", "share_name": contact})
            frappe.db.delete("Dynamic Link", {"parent": contact, "parenttype": "Contact"})
            frappe.db.delete("Contact", {"name": contact})
            frappe.db.delete("Customer", {"name": ("in", (erp_customer, crm_customer))})
            frappe.db.commit()

    def test_user_role_transition_retries_instead_of_waiting_for_a_lead_save(self):
        # A Lead save holds the Lead row while its hook waits for the owner's User row.
        # The role transition holding that User row must abort instead of waiting
        # (deadlock) or skipping the Lead; a retry then revokes the Lead's ERP shares.
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        role = f"CRM Scope Concurrent Lead {suffix}"
        frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
            ignore_permissions=True,
        )
        owner = f"crm-scope-concurrent-lead-{suffix}@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": owner, "first_name": "Concurrent Lead Owner",
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True)
        recipient = self._create_erp_share_recipient()
        customer = self._create_erp_customer(suffix)
        lead = frappe.get_doc({
            "doctype": "Lead", "first_name": f"Concurrent Lead {suffix}",
            "company_name": f"Concurrent Lead {suffix}", "status": "Lead",
            "lead_owner": owner, "custom_crm_converted_account": customer,
        }).insert(ignore_permissions=True).name
        share = frappe.get_doc({
            "doctype": "DocShare", "user": owner, "share_doctype": "Lead",
            "share_name": lead, "read": 1, "write": 1,
        })
        share.name = frappe.generate_hash(length=10)
        share.db_insert()
        recipient_share = self._insert_erp_share("Lead", lead, recipient)
        site = frappe.local.site
        frappe.db.commit()
        lead_locked = Event()
        user_locked = Event()

        def save_lead_boundary() -> None:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                lead_doc = frappe.get_doc("Lead", lead)
                frappe.db.sql(
                    "SELECT `name` FROM `tabLead` WHERE `name` = %s FOR UPDATE", (lead,),
                )
                lead_locked.set()
                self.assertTrue(user_locked.wait(timeout=10))
                revoke_lead_shares_entering_crm(lead_doc)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                frappe.destroy()

        def add_crm_role_boundary() -> str:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                self.assertTrue(lead_locked.wait(timeout=10))
                frappe.db.sql(
                    "SELECT `name` FROM `tabUser` WHERE `name` = %s FOR UPDATE", (owner,),
                )
                user_locked.set()
                try:
                    frappe.get_doc("User", owner).add_roles("CRM Sales")
                except frappe.PermissionError:
                    frappe.db.rollback()
                    return "retry"
                frappe.db.commit()
                return "granted"
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                user_locked.set()
                frappe.destroy()

        crm_sales_role = {"parent": owner, "parenttype": "User", "role": "CRM Sales"}
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                save_future = executor.submit(save_lead_boundary)
                role_future = executor.submit(add_crm_role_boundary)
                self.assertEqual(role_future.result(timeout=30), "retry")
                save_future.result(timeout=30)
            self.assertFalse(frappe.db.exists("Has Role", crm_sales_role))
            self.assertTrue(frappe.db.exists("DocShare", share.name))
            self.assertTrue(frappe.db.exists("DocShare", recipient_share))

            frappe.get_doc("User", owner).add_roles("CRM Sales")
            frappe.db.commit()
            self.assertTrue(frappe.db.exists("Has Role", crm_sales_role))
            self.assertFalse(frappe.db.exists("DocShare", share.name))
            self.assertFalse(frappe.db.exists("DocShare", recipient_share))
        finally:
            frappe.db.rollback()
            frappe.db.delete("DocShare", {"share_doctype": "Lead", "share_name": lead})
            frappe.db.delete("Lead", {"name": lead})
            frappe.db.delete("Customer", {"name": customer})
            frappe.db.delete("Has Role", {"parent": owner, "parenttype": "User"})
            frappe.db.delete("User", {"name": owner})
            frappe.db.delete("Role", {"name": role})
            frappe.db.commit()

    def test_customer_promotion_aborts_while_a_share_check_holds_a_linked_record(self):
        # A share check locks its target and the target's Customer links, then waits
        # for the Customer the promotion holds. Once the promotion commits it rejects
        # the new share and rolls back, removing no older share. A promotion that
        # skipped the held record would therefore leave that ERP share honoured on
        # a CRM record; it must abort instead, and a retry must revoke the share.
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        recipient = self._create_erp_share_recipient()
        site = frappe.local.site
        frappe.db.commit()
        for kind in ("Address", "Contact", "Lead"):
            with self.subTest(kind=kind):
                suffix = frappe.generate_hash(length=10)
                customer = self._create_erp_customer(f"{suffix}-held")
                record = self._create_linked_erp_record(kind, customer, recipient, suffix)
                share = self._insert_erp_share(kind, record, recipient)
                frappe.db.commit()
                customer_locked = Event()
                record_locked = Event()

                def hold_record_like_a_share_check() -> None:
                    frappe.init(site=site)
                    frappe.connect()
                    try:
                        frappe.set_user("Administrator")
                        self.assertTrue(customer_locked.wait(timeout=10))
                        target = _lock_docshare_target(kind, record)
                        if kind == "Lead":
                            customer_names = (target.custom_crm_converted_account,)
                        else:
                            customer_names = _locked_linked_customer_names(kind, record)
                        record_locked.set()
                        _lock_customer_groups(customer_names)
                    finally:
                        record_locked.set()
                        frappe.db.rollback()
                        frappe.destroy()

                def promote() -> str:
                    frappe.init(site=site)
                    frappe.connect()
                    try:
                        frappe.set_user("Administrator")
                        customer_doc = frappe.get_doc("Customer", customer)
                        frappe.db.sql(
                            "SELECT `name` FROM `tabCustomer` WHERE `name` = %s FOR UPDATE",
                            (customer,),
                        )
                        customer_locked.set()
                        self.assertTrue(record_locked.wait(timeout=10))
                        customer_doc.customer_group = "CRM Customers"
                        customer_doc.save(ignore_permissions=True)
                        frappe.db.commit()
                        return "promoted"
                    except frappe.PermissionError:
                        frappe.db.rollback()
                        return "retry"
                    except Exception:
                        frappe.db.rollback()
                        raise
                    finally:
                        customer_locked.set()
                        frappe.destroy()

                try:
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        holder = executor.submit(hold_record_like_a_share_check)
                        promotion = executor.submit(promote)
                        outcome = promotion.result(timeout=30)
                        holder.result(timeout=30)
                    promoted = (
                        frappe.db.get_value("Customer", customer, "customer_group")
                        == "CRM Customers"
                    )
                    self.assertFalse(
                        promoted and frappe.db.exists("DocShare", share),
                        f"a CRM Customer's {kind} kept its ERP share",
                    )
                    self.assertEqual(outcome, "retry")

                    customer_doc = frappe.get_doc("Customer", customer)
                    customer_doc.customer_group = "CRM Customers"
                    customer_doc.save(ignore_permissions=True)
                    frappe.db.commit()
                    self.assertFalse(frappe.db.exists("DocShare", share))
                finally:
                    frappe.db.rollback()
                    self._delete_linked_erp_record(kind, record)
                    frappe.db.delete("Customer", {"name": customer})
                    frappe.db.commit()

    def test_user_role_transition_aborts_while_a_share_check_holds_an_owned_lead(self):
        # The same race for a Lead whose owner is gaining a CRM role: the share check
        # holds the Lead and waits for the owner's User row, then rejects and rolls back.
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        role = f"CRM Scope Held Lead {suffix}"
        frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
            ignore_permissions=True,
        )
        owner = f"crm-scope-held-lead-{suffix}@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": owner, "first_name": "Held Lead Owner",
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True)
        recipient = self._create_erp_share_recipient()
        lead = frappe.get_doc({
            "doctype": "Lead", "first_name": f"Held Lead {suffix}",
            "company_name": f"Held Lead {suffix}", "status": "Lead", "lead_owner": owner,
        }).insert(ignore_permissions=True).name
        share = self._insert_erp_share("Lead", lead, recipient)
        site = frappe.local.site
        frappe.db.commit()
        user_locked = Event()
        lead_locked = Event()

        def hold_lead_like_a_share_check() -> None:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                self.assertTrue(user_locked.wait(timeout=10))
                target = _lock_docshare_target("Lead", lead)
                lead_locked.set()
                _lock_user_crm_roles((recipient, target.lead_owner))
            finally:
                lead_locked.set()
                frappe.db.rollback()
                frappe.destroy()

        def grant_crm_role() -> str:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                user = frappe.get_doc("User", owner)
                frappe.db.sql(
                    "SELECT `name` FROM `tabUser` WHERE `name` = %s FOR UPDATE", (owner,),
                )
                user_locked.set()
                self.assertTrue(lead_locked.wait(timeout=10))
                user.add_roles("CRM Sales")
                frappe.db.commit()
                return "granted"
            except frappe.PermissionError:
                frappe.db.rollback()
                return "retry"
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                user_locked.set()
                frappe.destroy()

        crm_sales_role = {"parent": owner, "parenttype": "User", "role": "CRM Sales"}
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                holder = executor.submit(hold_lead_like_a_share_check)
                transition = executor.submit(grant_crm_role)
                outcome = transition.result(timeout=30)
                holder.result(timeout=30)
            self.assertFalse(
                frappe.db.exists("Has Role", crm_sales_role) and frappe.db.exists("DocShare", share),
                "a CRM owner's Lead kept its ERP share",
            )
            self.assertEqual(outcome, "retry")

            frappe.get_doc("User", owner).add_roles("CRM Sales")
            frappe.db.commit()
            self.assertFalse(frappe.db.exists("DocShare", share))
        finally:
            frappe.db.rollback()
            frappe.db.delete("DocShare", {"share_doctype": "Lead", "share_name": lead})
            frappe.db.delete("Lead", {"name": lead})
            frappe.db.delete("Has Role", {"parent": owner, "parenttype": "User"})
            frappe.db.delete("User", {"name": owner})
            frappe.db.delete("Role", {"name": role})
            frappe.db.commit()

    def test_saving_an_existing_crm_user_ignores_locks_on_their_leads(self):
        # Only a real CRM entry revokes the shares on a user's Leads (NOWAIT). A
        # later save of that user, e.g. a password reset, must not fail because
        # one of their Leads is being edited at the same moment.
        self.assertTrue(frappe.local.site.endswith(".test"))
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=10)
        owner = f"crm-scope-existing-crm-{suffix}@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": owner, "first_name": "Existing CRM Owner",
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "CRM Sales"}],
        }).insert(ignore_permissions=True)
        lead = frappe.get_doc({
            "doctype": "Lead", "first_name": f"Existing CRM Lead {suffix}",
            "company_name": f"Existing CRM Lead {suffix}", "status": "Lead", "lead_owner": owner,
        }).insert(ignore_permissions=True).name
        primary = frappe.local.db
        primary.commit()
        try:
            with self.secondary_connection():
                frappe.db.sql("SELECT `name` FROM `tabLead` WHERE `name` = %s FOR UPDATE", (lead,))
                try:
                    with self.primary_connection():
                        user = frappe.get_doc("User", owner)
                        user.last_name = "Saved While Lead Locked"
                        user.save(ignore_permissions=True)
                        frappe.db.commit()
                finally:
                    # Release the Lead before any cleanup touches it.
                    frappe.db.rollback()
            self.assertEqual(
                frappe.db.get_value("User", owner, "last_name"), "Saved While Lead Locked",
            )
        finally:
            frappe.local.db = primary
            primary.rollback()
            frappe.db.delete("Lead", {"name": lead})
            frappe.db.delete("Has Role", {"parent": owner, "parenttype": "User"})
            frappe.db.delete("User", {"name": owner})
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
