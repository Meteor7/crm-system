from __future__ import annotations

import frappe


def execute() -> None:
    if frappe.db.table_exists("CRM Quotation"):
        frappe.db.sql(
            "UPDATE `tabCRM Quotation` SET `quotation_type` = 'Device' "
            "WHERE COALESCE(`quotation_type`, '') = ''"
        )
    if frappe.db.table_exists("CRM Quotation Version"):
        frappe.db.sql(
            "UPDATE `tabCRM Quotation Version` SET `quotation_type` = 'Device' "
            "WHERE COALESCE(`quotation_type`, '') = ''"
        )
