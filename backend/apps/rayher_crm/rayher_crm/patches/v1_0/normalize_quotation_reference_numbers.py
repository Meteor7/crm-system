"""Normalize every Quotation reference from its initial quotation date."""
from __future__ import annotations
from collections import defaultdict
from typing import Any
import frappe
from frappe.utils import getdate

def plan_reference_updates(rows: list[dict[str, Any]]) -> dict[str, str]:
    counters: dict[str, int] = defaultdict(int)
    planned: dict[str, str] = {}
    ordered = sorted(rows, key=lambda row: (str(getdate(row.get("initial_date") or row.get("creation"))), str(row.get("creation") or ""), str(row["name"])))
    for row in ordered:
        date_key = getdate(row.get("initial_date") or row.get("creation")).strftime("%Y%m%d")
        counters[date_key] += 1
        planned[str(row["name"])] = f"PK{date_key}-A{counters[date_key]}"
    return planned

def execute() -> None:
    if not frappe.db.table_exists("CRM Quotation") or not frappe.db.table_exists("CRM Quotation Version"):
        return
    rows = frappe.db.sql(
        """SELECT q.name, q.ref_no, q.creation, COALESCE(MIN(v.quote_date), DATE(q.creation)) AS initial_date
           FROM `tabCRM Quotation` q LEFT JOIN `tabCRM Quotation Version` v ON v.quotation = q.name
           GROUP BY q.name, q.ref_no, q.creation ORDER BY initial_date, q.creation, q.name""",
        as_dict=True,
    )
    desired = plan_reference_updates(rows)
    current = {str(row.name): str(row.ref_no or "") for row in rows}
    changed = [name for name, ref_no in desired.items() if current.get(name) != ref_no]
    if not changed:
        return
    for name in changed:
        temporary = f"MIG-{name}"
        frappe.db.sql("UPDATE `tabCRM Quotation` SET ref_no=%s WHERE name=%s", (temporary, name))
        frappe.db.sql("UPDATE `tabCRM Quotation Version` SET ref_no=%s WHERE quotation=%s", (temporary, name))
    for name in changed:
        ref_no = desired[name]
        frappe.db.sql("UPDATE `tabCRM Quotation` SET ref_no=%s WHERE name=%s", (ref_no, name))
        frappe.db.sql("UPDATE `tabCRM Quotation Version` SET ref_no=%s WHERE quotation=%s", (ref_no, name))
    from rayher_crm.services.quotations import _release_pdf, render_quotation_pdf
    for name in changed:
        master = frappe.get_doc("CRM Quotation", name)
        version_names = frappe.get_all("CRM Quotation Version", filters={"quotation": name, "pdf_file": ["is", "set"], "status": ["!=", "Draft"]}, pluck="name")
        for version_name in version_names:
            version = frappe.get_doc("CRM Quotation Version", version_name)
            version.pdf_file = _release_pdf(master, version, render_quotation_pdf(master, version))
            version.save(ignore_permissions=True)