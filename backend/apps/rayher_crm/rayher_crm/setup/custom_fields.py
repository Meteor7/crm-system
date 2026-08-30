"""Idempotent schema extensions for the first CRM business slice."""

from __future__ import annotations

from copy import deepcopy

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CRM_CUSTOM_FIELDS = {
    "Customer": [
        {"fieldname": "custom_crm_owner", "label": "CRM Owner", "fieldtype": "Link", "options": "User", "insert_after": "customer_name"},
        {"fieldname": "custom_crm_short_name", "label": "CRM Short Name", "fieldtype": "Data", "insert_after": "custom_crm_owner"},
        {"fieldname": "custom_crm_segment", "label": "CRM Segment", "fieldtype": "Select", "options": "Frontend\nAdvanced Packaging", "insert_after": "custom_crm_short_name"},
        {"fieldname": "custom_crm_tier", "label": "CRM Tier", "fieldtype": "Select", "options": "S\nA\nB", "insert_after": "custom_crm_segment"},
        {"fieldname": "custom_crm_city", "label": "CRM City", "fieldtype": "Data", "insert_after": "custom_crm_tier"},
        {"fieldname": "custom_crm_region", "label": "CRM Region", "fieldtype": "Data", "insert_after": "custom_crm_city"},
        {"fieldname": "custom_crm_visibility", "label": "CRM Visibility", "fieldtype": "Select", "options": "Private\nPublic", "default": "Private", "insert_after": "custom_crm_region"},
    ],
    "Contact": [
        {"fieldname": "custom_crm_owner", "label": "CRM Owner", "fieldtype": "Link", "options": "User", "insert_after": "first_name"},
        {"fieldname": "custom_crm_site", "label": "CRM Site", "fieldtype": "Link", "options": "Address", "insert_after": "custom_crm_owner"},
        {"fieldname": "custom_crm_reports_to", "label": "CRM Reports To", "fieldtype": "Link", "options": "Contact", "insert_after": "custom_crm_site"},
        {"fieldname": "custom_crm_relationship", "label": "CRM Relationship", "fieldtype": "Select", "options": "Strong\nDeveloping\nWeak", "insert_after": "custom_crm_reports_to"},
        {"fieldname": "custom_crm_status", "label": "CRM Status", "fieldtype": "Select", "options": "Active\nLeft Company\nArchived", "insert_after": "custom_crm_relationship"},
        {"fieldname": "custom_crm_data_quality", "label": "CRM Data Quality", "fieldtype": "Select", "options": "Complete\nNeeds Review", "insert_after": "custom_crm_status"},
        {"fieldname": "custom_crm_merged_into", "label": "CRM Merged Into", "fieldtype": "Link", "options": "Contact", "insert_after": "custom_crm_data_quality"},
        {"fieldname": "custom_crm_buying_role", "label": "CRM Buying Role", "fieldtype": "Select", "options": "Decision Maker\nEconomic Buyer\nChampion\nTechnical Champion\nTechnical Evaluator\nProcurement\nInfluencer\nBlocker\nUser", "insert_after": "custom_crm_merged_into"},
        {"fieldname": "custom_crm_influence", "label": "CRM Influence", "fieldtype": "Select", "options": "High\nMedium\nLow", "insert_after": "custom_crm_buying_role"},
    ],
    "Address": [
        {"fieldname": "custom_crm_owner", "label": "CRM Owner", "fieldtype": "Link", "options": "User", "insert_after": "address_title"},
        {"fieldname": "custom_crm_site_type", "label": "CRM Site Type", "fieldtype": "Data", "insert_after": "custom_crm_owner"},
        {"fieldname": "custom_crm_process", "label": "CRM Process", "fieldtype": "Data", "insert_after": "custom_crm_site_type"},
        {"fieldname": "custom_crm_status", "label": "CRM Status", "fieldtype": "Select", "options": "量产\n建设中\n规划中", "insert_after": "custom_crm_process"},
    ],
    "Lead": [
        {"fieldname": "custom_crm_source", "label": "CRM Source", "fieldtype": "Select", "options": "Website\nTrade Show\nPartner Referral\nOutbound\nCustomer Referral\nOther", "insert_after": "source"},
        {"fieldname": "custom_crm_status", "label": "CRM Status", "fieldtype": "Select", "options": "New\nWorking\nQualified\nNurturing\nDisqualified\nConverted", "insert_after": "status"},
        {"fieldname": "custom_crm_interest", "label": "CRM Interest", "fieldtype": "Small Text", "insert_after": "custom_crm_status"},
        {"fieldname": "custom_crm_first_contact_note", "label": "CRM First Contact Note", "fieldtype": "Small Text", "insert_after": "custom_crm_interest"},
        {"fieldname": "custom_crm_next_action", "label": "CRM Next Action", "fieldtype": "Data", "insert_after": "custom_crm_first_contact_note"},
        {"fieldname": "custom_crm_next_action_due", "label": "CRM Next Action Due", "fieldtype": "Date", "insert_after": "custom_crm_next_action"},
        {"fieldname": "custom_crm_converted_account", "label": "CRM Converted Account", "fieldtype": "Link", "options": "Customer", "insert_after": "custom_crm_next_action_due", "read_only": 1},
        {"fieldname": "custom_crm_converted_contact", "label": "CRM Converted Contact", "fieldtype": "Link", "options": "Contact", "insert_after": "custom_crm_converted_account", "read_only": 1},
        {"fieldname": "custom_crm_converted_opportunity", "label": "CRM Converted Opportunity", "fieldtype": "Link", "options": "CRM Opportunity", "insert_after": "custom_crm_converted_contact", "read_only": 1},
        {"fieldname": "custom_crm_converted_at", "label": "CRM Converted At", "fieldtype": "Datetime", "insert_after": "custom_crm_converted_opportunity", "read_only": 1},
        {"fieldname": "custom_crm_reused_account", "label": "CRM Reused Account", "fieldtype": "Check", "insert_after": "custom_crm_converted_at", "read_only": 1},
        {"fieldname": "custom_crm_reused_contact", "label": "CRM Reused Contact", "fieldtype": "Check", "insert_after": "custom_crm_reused_account", "read_only": 1},
    ],
}

LEGACY_STANDARD_OPPORTUNITY_FIELD = "Opportunity-custom_crm_tool_type"
ACCOUNT_SEGMENT_FIELD = "Customer-custom_crm_segment"


def _custom_fields_for_install() -> dict:
    fields = deepcopy(CRM_CUSTOM_FIELDS)
    existing_options = frappe.db.get_value("Custom Field", ACCOUNT_SEGMENT_FIELD, "options")
    if not existing_options:
        return fields
    segment_field = next(
        field for field in fields["Customer"] if field["fieldname"] == "custom_crm_segment"
    )
    options: list[str] = []
    for value in f"{segment_field['options']}\n{existing_options}".splitlines():
        normalized = value.strip()
        if normalized and normalized not in options:
            options.append(normalized)
    segment_field["options"] = "\n".join(options)
    return fields


def _install_reference_roots() -> None:
    """Create only the ERPNext tree roots required to validate CRM Customers."""

    if not frappe.db.exists("Customer Group", "All Customer Groups"):
        frappe.get_doc(
            {
                "doctype": "Customer Group",
                "customer_group_name": "All Customer Groups",
                "is_group": 1,
            }
        ).insert(ignore_permissions=True)

    if not frappe.db.exists("Customer Group", "CRM Customers"):
        frappe.get_doc(
            {
                "doctype": "Customer Group",
                "customer_group_name": "CRM Customers",
                "parent_customer_group": "All Customer Groups",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)

    if not frappe.db.exists("Territory", "All Territories"):
        frappe.get_doc(
            {
                "doctype": "Territory",
                "territory_name": "All Territories",
                "is_group": 1,
            }
        ).insert(ignore_permissions=True)

    if not frappe.db.exists("Territory", "CRM Territory"):
        frappe.get_doc(
            {
                "doctype": "Territory",
                "territory_name": "CRM Territory",
                "parent_territory": "All Territories",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)


def _install_assignment_unique_constraint() -> None:
    frappe.db.add_unique(
        "CRM Account Engineer Assignment",
        ["customer", "engineer"],
        constraint_name="uniq_crm_account_engineer",
    )


def _disable_erpnext_lead_auto_contact() -> None:
    """CRM creates Contacts explicitly; ERPNext Lead must not create parallel rows."""

    frappe.db.set_single_value("CRM Settings", "auto_creation_of_contact", 0)


def install_crm_schema() -> None:
    """Install Stage 5B fields and constraints without inserting business data."""

    _install_reference_roots()
    _disable_erpnext_lead_auto_contact()
    if frappe.db.exists("Custom Field", LEGACY_STANDARD_OPPORTUNITY_FIELD):
        frappe.delete_doc(
            "Custom Field",
            LEGACY_STANDARD_OPPORTUNITY_FIELD,
            ignore_permissions=True,
            force=True,
        )
    create_custom_fields(_custom_fields_for_install(), update=True)
    _install_assignment_unique_constraint()
