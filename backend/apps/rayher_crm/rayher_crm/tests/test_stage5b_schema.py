from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.setup.custom_fields import CRM_CUSTOM_FIELDS, install_crm_schema
from rayher_crm.patches.v1_0.remove_stage5b_schema_test_residue import execute as remove_test_residue


EXPECTED_FIELDS = {
    "File": {
        "custom_crm_service_upload": ("Check", None),
    },
    "Customer": {
        "custom_crm_owner": ("Link", "User"),
        "custom_crm_short_name": ("Data", None),
        "custom_crm_segment": ("Select", "Frontend\nAdvanced Packaging"),
        "custom_crm_tier": ("Select", "S\nA\nB"),
        "custom_crm_customer_kind": ("Select", "\nProspect\nExisting"),
        "custom_crm_city": ("Data", None),
        "custom_crm_region": ("Select", "\nEast China\nSouth China\nWest China\nNorth China\nCentral China"),
        "custom_crm_visibility": ("Select", "Private\nPublic"),
    },
    "Contact": {
        "custom_crm_owner": ("Link", "User"),
        "custom_crm_site": ("Link", "Address"),
        "custom_crm_reports_to": ("Link", "Contact"),
        "custom_crm_relationship": ("Select", "Strong\nDeveloping\nWeak"),
        "custom_crm_status": ("Select", "Active\nLeft Company\nArchived"),
        "custom_crm_data_quality": ("Select", "Complete\nNeeds Review"),
        "custom_crm_merged_into": ("Link", "Contact"),
        "custom_crm_buying_role": (
            "Select",
            "Decision Maker\nEconomic Buyer\nChampion\nTechnical Champion\nTechnical Evaluator\nProcurement\nInfluencer\nBlocker\nUser",
        ),
        "custom_crm_influence": ("Select", "High\nMedium\nLow"),
    },
    "Address": {
        "custom_crm_owner": ("Link", "User"),
        "custom_crm_site_type": ("Data", None),
        "custom_crm_process": ("Data", None),
        "custom_crm_status": ("Select", "量产\n建设中\n规划中"),
    },
    "Lead": {
        "custom_crm_source": (
            "Select",
            "Website\nTrade Show\nPartner Referral\nOutbound\nCustomer Referral\nOther",
        ),
        "custom_crm_status": (
            "Select",
            "New\nWorking\nQualified\nNurturing\nDisqualified\nConverted",
        ),
        "custom_crm_interest": ("Small Text", None),
        "custom_crm_first_contact_note": ("Small Text", None),
        "custom_crm_next_action": ("Data", None),
        "custom_crm_next_action_due": ("Date", None),
        "custom_crm_activities": ("JSON", None),
        "custom_crm_converted_account": ("Link", "Customer"),
        "custom_crm_converted_contact": ("Link", "Contact"),
        "custom_crm_converted_opportunity": ("Link", "CRM Opportunity"),
        "custom_crm_converted_at": ("Datetime", None),
        "custom_crm_reused_account": ("Check", None),
        "custom_crm_reused_contact": ("Check", None),
    },
}


class TestStage5BSchema(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_standard_erpnext_master_doctypes_are_present(self):
        for doctype in ("Customer", "Contact", "Address", "Lead"):
            self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

    def test_crm_opportunity_is_lightweight_and_has_no_erp_company_dependency(self):
        meta = frappe.get_meta("CRM Opportunity")
        expected = {
            "account": ("Link", "Customer", 1),
            "site": ("Link", "Address", 1),
            "source_lead": ("Link", "Lead", 0),
            "title": ("Data", None, 1),
            # A qualified (S1) Opportunity may leave its amounts unknown; the service enforces them after S1.
            "amount": ("Currency", "currency", 0),
            "currency": ("Link", "Currency", 1),
            "po_date": ("Date", None, 1),
            "opportunity_owner": ("Link", "User", 1),
            "tool_type": ("Data", None, 1),
            "stage": (
                "Select",
                "qualified_opportunity\ndemo_done\ncustomer_budget_approved\nrfq_validated\nquotation_sent\ninternal_validation\npo_received\nlost",
                1,
            ),
            "stage_changed_at": ("Datetime", None, 0),
            "budget_approved_on": ("Date", None, 0),
            "probability_level": ("Select", "\nlow_probability\npipeline\nupside\ncommitted", 0),
            "forecast": ("Select", "Pipeline\nBest Case\nCommit\nClosed", 1),
            "probability": ("Int", None, 0),
            "score": ("Int", None, 1),
            "sale_type": ("Select", "New Equipment\nRepeat Order\nService", 1),
            "sub_region": ("Data", None, 1),
            "original_amount": ("Currency", "currency", 0),
            "shipment_date": ("Date", None, 0),
            "fat_date": ("Date", None, 0),
            "payment_milestones": ("JSON", None, 0),
            "competition": ("Small Text", None, 0),
            "win_reason": ("Small Text", None, 0),
            "lost_reason": ("Small Text", None, 0),
            "lost_at_stage": (
                "Select",
                "\nqualified_opportunity\ndemo_done\ncustomer_budget_approved\nrfq_validated\nquotation_sent\ninternal_validation",
                0,
            ),
            "lost_at": ("Datetime", None, 0),
            "lost_by": ("Link", "User", 0),
            "strengths": ("JSON", None, 0),
            "red_flags": ("JSON", None, 0),
            "information_needed": ("JSON", None, 0),
            "legacy_stage": ("Data", None, 0),
        }
        actual = {
            fieldname: (meta.get_field(fieldname).fieldtype, meta.get_field(fieldname).options or None, meta.get_field(fieldname).reqd)
            for fieldname in expected
        }
        self.assertEqual(actual, expected)
        self.assertEqual(meta.get_field("stage").default, "qualified_opportunity")
        self.assertTrue(meta.get_field("legacy_stage").hidden)
        self.assertIsNone(meta.get_field("company"))
        self.assertIsNone(meta.get_field("status"))
        self.assertEqual(meta.autoname, "format:CRM-OPP-{#####}")
        self.assertFalse(frappe.db.exists("Custom Field", "Opportunity-custom_crm_tool_type"))

    def test_opportunity_relation_doctypes_are_server_named_and_append_safe(self):
        stakeholder = frappe.get_meta("CRM Opportunity Stakeholder")
        action = frappe.get_meta("CRM Opportunity Action")
        history = frappe.get_meta("CRM Opportunity History")

        self.assertEqual(stakeholder.autoname, "hash")
        self.assertEqual((stakeholder.get_field("opportunity").fieldtype, stakeholder.get_field("opportunity").options), ("Link", "CRM Opportunity"))
        self.assertEqual((stakeholder.get_field("contact").fieldtype, stakeholder.get_field("contact").options), ("Link", "Contact"))
        self.assertEqual(stakeholder.get_field("archived").fieldtype, "Check")

        self.assertEqual(action.autoname, "hash")
        self.assertEqual((action.get_field("opportunity").fieldtype, action.get_field("opportunity").options), ("Link", "CRM Opportunity"))
        self.assertEqual((action.get_field("action_owner").fieldtype, action.get_field("action_owner").options), ("Link", "User"))
        self.assertEqual(action.get_field("archived").fieldtype, "Check")

        self.assertEqual(history.autoname, "hash")
        self.assertEqual((history.get_field("opportunity").fieldtype, history.get_field("opportunity").options), ("Link", "CRM Opportunity"))
        for fieldname, fieldtype in {"actor": "Link", "at": "Datetime", "field": "Data", "from_value": "Long Text", "to_value": "Long Text"}.items():
            self.assertEqual(history.get_field(fieldname).fieldtype, fieldtype)
        self.assertEqual(history.get_field("actor").options, "User")
        permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in history.permissions}
        self.assertIn(("CRM Manager", 1, 0, 0, 0), permissions)

        probability_history = frappe.get_meta("CRM Opportunity Probability History")
        self.assertEqual(probability_history.autoname, "hash")
        opportunity_link = probability_history.get_field("opportunity")
        self.assertEqual((opportunity_link.fieldtype, opportunity_link.options), ("Link", "CRM Opportunity"))
        for fieldname in ("from_level", "to_level"):
            field = probability_history.get_field(fieldname)
            self.assertEqual((field.fieldtype, field.options), ("Select", "\nlow_probability\npipeline\nupside\ncommitted"))
        self.assertEqual(probability_history.get_field("changed_at").fieldtype, "Datetime")
        permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in probability_history.permissions}
        self.assertIn(("CRM Sales", 1, 0, 0, 0), permissions)

        stage_history = frappe.get_meta("CRM Opportunity Stage History")
        internal_validation = frappe.get_meta("CRM Opportunity Internal Validation")
        self.assertEqual(stage_history.autoname, "hash")
        self.assertEqual(internal_validation.autoname, "format:CRM-VAL-{#####}")
        self.assertEqual(
            stage_history.get_field("to_stage").options,
            "qualified_opportunity\ndemo_done\ncustomer_budget_approved\nrfq_validated\nquotation_sent\ninternal_validation\npo_received\nlost",
        )
        self.assertEqual(internal_validation.get_field("status").options, "pending\napproved\nrejected\ncancelled")
        # At most one pending request per Opportunity, whichever code path writes the row.
        self.assertTrue(internal_validation.get_field("live_opportunity").unique)
        for meta in (stage_history, internal_validation):
            opportunity_link = meta.get_field("opportunity")
            self.assertEqual((opportunity_link.fieldtype, opportunity_link.options), ("Link", "CRM Opportunity"))
            permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in meta.permissions}
            for role in ("CRM Manager", "CRM Sales", "CRM Engineer"):
                self.assertIn((role, 1, 0, 0, 0), permissions, meta.name)

    def test_booking_and_installed_tool_are_lightweight_crm_doctypes(self):
        booking = frappe.get_meta("CRM Booking")
        installed_tool = frappe.get_meta("CRM Installed Tool")
        booking_fields = {
            "account": ("Link", "Customer", 1),
            "primary_contact": ("Link", "Contact", 1),
            "equipment": ("Data", None, 1),
            "quantity": ("Int", None, 1),
            "ddl": ("Date", None, 1),
            "amount": ("Currency", "currency", 1),
            "currency": ("Link", "Currency", 1),
            "status": ("Select", "Confirmed\nPending\nCompleted\nCancelled", 1),
            "booking_date": ("Date", None, 1),
            "booking_owner": ("Link", "User", 1),
            "source": ("Select", "Opportunity\nUpsell", 1),
            "source_opportunity": ("Link", "CRM Opportunity", 0),
            "installed_tool": ("Link", "CRM Installed Tool", 0),
            "installed_tool_converted_at": ("Datetime", None, 0),
            "note": ("Small Text", None, 0),
        }
        tool_fields = {
            "account": ("Link", "Customer", 1), "site": ("Link", "Address", 1),
            "serial": ("Data", None, 1), "model": ("Data", None, 1),
            "location": ("Data", None, 1), "status": ("Data", None, 1),
            "lifecycle_stage": ("Select", "FAT\nShipment\nInstallation\nSAT\nWarranty", 1),
            "software": ("Data", None, 1), "firmware": ("Data", None, 1),
            "warranty_end": ("Date", None, 0), "completeness": ("Int", None, 1),
            "source_booking": ("Link", "CRM Booking", 1),
            "source_opportunity": ("Link", "CRM Opportunity", 0),
            "sales_owner": ("Link", "User", 1), "engineer_owner": ("Link", "User", 1),
            "sales_order_reference": ("Data", None, 0), "contract_reference": ("Data", None, 0),
            "warranty_start": ("Date", None, 0), "service_contract": ("Data", None, 0),
            "pm_cycle": ("Data", None, 0), "last_service": ("Date", None, 0),
            "operating_system": ("Data", None, 0), "configuration": ("Small Text", None, 0),
            "ownership_type": ("Data", None, 1), "milestones": ("JSON", None, 0),
            "documents": ("JSON", None, 0),
        }
        for meta, expected in ((booking, booking_fields), (installed_tool, tool_fields)):
            actual = {
                fieldname: (meta.get_field(fieldname).fieldtype, meta.get_field(fieldname).options or None, meta.get_field(fieldname).reqd)
                for fieldname in expected
            }
            self.assertEqual(actual, expected)
            for forbidden in ("company", "asset", "sales_order", "delivery_note", "item_code"):
                self.assertIsNone(meta.get_field(forbidden))

        self.assertEqual(booking.autoname, "format:CRM-BKG-{#####}")
        self.assertEqual(installed_tool.autoname, "format:CRM-TOOL-{#####}")
        self.assertTrue(installed_tool.get_field("serial").unique)
        self.assertTrue(installed_tool.get_field("source_booking").unique)
        booking_permissions = {(row.role, row.read, row.write, row.create) for row in booking.permissions}
        tool_permissions = {(row.role, row.read, row.write, row.create) for row in installed_tool.permissions}
        # Bookings and Installed Tools change through the api/v1 services, so the standard
        # document API only reads them.
        read_only = {("CRM Manager", 1, 0, 0), ("CRM Sales", 1, 0, 0), ("CRM Engineer", 1, 0, 0)}
        self.assertEqual(booking_permissions, read_only)
        self.assertEqual(tool_permissions, read_only)

    def test_installed_tool_audit_doctypes_are_server_named_and_append_only(self):
        expected_fields = {
            "CRM Installed Tool Lifecycle History": {
                "installed_tool": ("Link", "CRM Installed Tool", 1),
                "at": ("Datetime", None, 1),
                "actor": ("Link", "User", 1),
                "from_stage": ("Data", None, 1),
                "to_stage": ("Data", None, 1),
                "completed_at": ("Date", None, 1),
                "result": ("Small Text", None, 1),
                "open_issues": ("Small Text", None, 1),
                "customer_signoff": ("Small Text", None, 1),
                "comment": ("Small Text", None, 1),
                "evidence": ("JSON", None, 0),
            },
            "CRM Installed Tool Version History": {
                "installed_tool": ("Link", "CRM Installed Tool", 1),
                "at": ("Datetime", None, 1),
                "actor": ("Link", "User", 1),
                "change_date": ("Date", None, 1),
                "change_type": (
                    "Select",
                    "Software\nFirmware\nOperating System\nConfiguration\nEngineer Assignment",
                    1,
                ),
                "from_value": ("Small Text", None, 0),
                "to_value": ("Small Text", None, 1),
                "reason": ("Small Text", None, 1),
                "comment": ("Small Text", None, 0),
            },
            "CRM Installed Tool Service History": {
                "installed_tool": ("Link", "CRM Installed Tool", 1),
                "at": ("Datetime", None, 1),
                "actor": ("Link", "User", 1),
                "service_date": ("Date", None, 1),
                "service_type": ("Select", "Warranty Activation\nPreventive Maintenance\nCorrective Service\nRemote Support\nInstallation Support\nContract Change", 1),
                "result": ("Small Text", None, 1),
                "open_issues": ("Small Text", None, 1),
                "next_action": ("Small Text", None, 0),
                "action_owner": ("Link", "User", 0),
                "due": ("Date", None, 0),
                "comment": ("Small Text", None, 0),
                "warranty_start": ("Date", None, 0),
                "warranty_end": ("Date", None, 0),
                "service_contract": ("Data", None, 0),
                "pm_cycle": ("Data", None, 0),
            },
        }

        for doctype, fields in expected_fields.items():
            meta = frappe.get_meta(doctype)
            self.assertEqual(meta.autoname, "hash")
            actual = {
                fieldname: (meta.get_field(fieldname).fieldtype, meta.get_field(fieldname).options or None, meta.get_field(fieldname).reqd)
                for fieldname in fields
            }
            self.assertEqual(actual, fields)
            permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in meta.permissions}
            self.assertIn(("CRM Manager", 1, 0, 0, 0), permissions)
            self.assertIn(("CRM Sales", 1, 0, 0, 0), permissions)
            self.assertIn(("CRM Engineer", 1, 0, 0, 0), permissions)
    def test_demo_evaluation_doctypes_are_server_named_and_have_no_erp_project_dependency(self):
        request = frappe.get_meta("CRM Demo Request")
        history = frappe.get_meta("CRM Demo Request History")
        comment = frappe.get_meta("CRM Demo Comment")
        evaluation = frappe.get_meta("CRM Evaluation")
        test_run = frappe.get_meta("CRM Test Run")

        self.assertEqual(request.autoname, "format:CRM-DR-{#####}")
        self.assertEqual(evaluation.autoname, "format:CRM-EVAL-{#####}")
        self.assertEqual(test_run.autoname, "format:CRM-RUN-{#####}")
        self.assertEqual(history.autoname, "hash")
        self.assertEqual(comment.autoname, "hash")
        self.assertEqual(request.get_field("account").options, "Customer")
        self.assertEqual(request.get_field("primary_contact").options, "Contact")
        self.assertEqual(request.get_field("opportunity").options, "CRM Opportunity")
        self.assertEqual(request.get_field("sales_owner").options, "User")
        self.assertEqual(request.get_field("engineer_owner").options, "User")
        self.assertEqual(
            request.get_field("status").options,
            "Draft\nEngineer Review\nEngineer Returned\nManager Approval\nManager Rejected\nConverted\nCancelled",
        )
        self.assertEqual(request.get_field("priority").options, "Critical\nHigh\nMedium\nLow")
        self.assertEqual(request.get_field("form_data").fieldtype, "JSON")
        self.assertEqual(request.get_field("tracking").fieldtype, "JSON")
        self.assertEqual(history.get_field("demo_request").options, "CRM Demo Request")
        self.assertEqual(history.get_field("actor").options, "User")
        history_permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in history.permissions}
        self.assertIn(("CRM Manager", 1, 0, 0, 0), history_permissions)
        self.assertEqual(comment.get_field("author").options, "User")
        self.assertEqual(comment.get_field("mentioned_person").options, "User")
        self.assertEqual(comment.get_field("mentioned_people").fieldtype, "JSON")

        self.assertEqual(evaluation.get_field("demo_request").options, "CRM Demo Request")
        self.assertTrue(evaluation.get_field("demo_request").unique)
        self.assertEqual(
            evaluation.get_field("status").options,
            "Requested\nScope Confirmed\nSample Received\nScheduled\nTesting\nAnalysis\nInternal Review\nCustomer Review\nAccepted\nRejected",
        )
        self.assertEqual(test_run.get_field("evaluation").options, "CRM Evaluation")
        self.assertEqual(test_run.get_field("status").options, "Planned\nCompleted\nCancelled")
        for meta in (request, evaluation, test_run):
            for forbidden in ("company", "project", "task", "quality_inspection", "warehouse"):
                self.assertIsNone(meta.get_field(forbidden))

    def test_custom_field_contract_matches_the_frozen_minimum(self):
        actual = {
            doctype: {
                field["fieldname"]: (field["fieldtype"], field.get("options"))
                for field in fields
            }
            for doctype, fields in CRM_CUSTOM_FIELDS.items()
        }
        self.assertEqual(actual, EXPECTED_FIELDS)

    def test_schema_install_is_idempotent_and_fields_have_exact_types(self):
        customer_count_before = frappe.db.count("Customer")
        frappe.db.set_single_value("CRM Settings", "auto_creation_of_contact", 1)
        install_crm_schema()
        install_crm_schema()
        frappe.clear_cache()

        for doctype, fields in EXPECTED_FIELDS.items():
            meta = frappe.get_meta(doctype)
            for fieldname, (fieldtype, options) in fields.items():
                field = meta.get_field(fieldname)
                self.assertIsNotNone(field, f"{doctype}.{fieldname}")
                self.assertEqual(field.fieldtype, fieldtype)
                self.assertEqual(field.options or None, options)

        self.assertTrue(frappe.db.exists("Customer Group", "All Customer Groups"))
        self.assertTrue(frappe.db.exists("Customer Group", "CRM Customers"))
        self.assertTrue(frappe.db.exists("Territory", "All Territories"))
        self.assertTrue(frappe.db.exists("Territory", "CRM Territory"))
        self.assertEqual(frappe.db.count("Customer"), customer_count_before)

    def test_schema_reinstall_preserves_sales_registered_account_segments(self):
        field_name = "Customer-custom_crm_segment"
        original_options = frappe.db.get_value("Custom Field", field_name, "options")
        custom_segment = "Power Semiconductor"
        try:
            frappe.db.set_value(
                "Custom Field",
                field_name,
                "options",
                f"{original_options}\n{custom_segment}",
                update_modified=False,
            )
            frappe.clear_cache(doctype="Customer")

            install_crm_schema()

            options = frappe.db.get_value("Custom Field", field_name, "options").splitlines()
            self.assertEqual(options.count(custom_segment), 1)
        finally:
            frappe.db.set_value(
                "Custom Field",
                field_name,
                "options",
                original_options,
                update_modified=False,
            )
            frappe.clear_cache(doctype="Customer")
        self.assertFalse(frappe.db.get_single_value("CRM Settings", "auto_creation_of_contact"))

    def test_assignment_doctype_has_exact_links_and_role_permissions(self):
        meta = frappe.get_meta("CRM Account Engineer Assignment")

        self.assertEqual(meta.autoname, "hash")
        self.assertEqual((meta.get_field("customer").fieldtype, meta.get_field("customer").options), ("Link", "Customer"))
        self.assertEqual((meta.get_field("engineer").fieldtype, meta.get_field("engineer").options), ("Link", "User"))
        permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in meta.permissions}
        self.assertIn(("CRM Manager", 1, 1, 1, 1), permissions)
        self.assertIn(("CRM Engineer", 1, 0, 0, 0), permissions)

    def test_assignment_pair_is_unique(self):
        customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "Stage 5B Schema Customer",
                "customer_type": "Company",
                "customer_group": "CRM Customers",
                "territory": "CRM Territory",
            }
        ).insert(ignore_permissions=True)
        engineer = frappe.get_doc(
            {
                "doctype": "User",
                "email": "crm-stage5b-schema-engineer@example.invalid",
                "first_name": "Schema Engineer",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": "CRM Engineer"}],
            }
        ).insert(ignore_permissions=True)

        assignment = {
            "doctype": "CRM Account Engineer Assignment",
            "customer": customer.name,
            "engineer": engineer.name,
            "enabled": 1,
        }
        frappe.get_doc(assignment).insert(ignore_permissions=True)
        with self.assertRaises(frappe.UniqueValidationError):
            frappe.get_doc(assignment).insert(ignore_permissions=True)

    def test_reserved_stage5b_schema_residue_cleanup_is_exact(self):
        reserved_customer = "Stage 5B Schema Customer"
        reserved_engineer = "crm-stage5b-schema-engineer@example.invalid"
        preserved_customer = "Stage 5B Schema Customer - Preserve"

        remove_test_residue()
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": reserved_customer,
                "customer_type": "Company",
                "customer_group": "CRM Customers",
                "territory": "CRM Territory",
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": preserved_customer,
                "customer_type": "Company",
                "customer_group": "CRM Customers",
                "territory": "CRM Territory",
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "User",
                "email": reserved_engineer,
                "first_name": "Schema Engineer",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": "CRM Engineer"}],
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "CRM Account Engineer Assignment",
                "customer": reserved_customer,
                "engineer": reserved_engineer,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        remove_test_residue()

        self.assertFalse(frappe.db.exists("CRM Account Engineer Assignment", {"customer": reserved_customer}))
        self.assertFalse(frappe.db.exists("Customer", reserved_customer))
        self.assertFalse(frappe.db.exists("User", reserved_engineer))
        self.assertTrue(frappe.db.exists("Customer", preserved_customer))
