"""Preserve every legacy flag without inventing severity, author or history."""
import json
import frappe
from rayher_crm.services.blue_sheet_rules import red_flags


def execute():
    for row in frappe.get_all("CRM Opportunity", fields=["name"], limit_page_length=0):
        doc = frappe.get_doc("CRM Opportunity", row.name, for_update=True)
        if doc.get("red_flag_records") in (None, ""):
            frappe.db.set_value("CRM Opportunity", doc.name, "red_flag_records",
                json.dumps(red_flags(doc.name, None, doc.red_flags), ensure_ascii=False), update_modified=False)
