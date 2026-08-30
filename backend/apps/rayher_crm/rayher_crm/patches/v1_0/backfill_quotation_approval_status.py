import frappe


def execute():
    if not frappe.db.table_exists("CRM Quotation Version"):
        return
    frappe.db.sql(
        """UPDATE `tabCRM Quotation Version`
           SET approval_status = CASE
             WHEN status = 'Draft' THEN 'Not Submitted'
             ELSE 'Not Required'
           END
           WHERE current_approval IS NULL"""
    )
