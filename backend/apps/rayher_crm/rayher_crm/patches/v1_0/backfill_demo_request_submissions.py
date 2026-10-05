"""Record the submission of every Demo Request that is past Draft and has no history entry for it.

An Engineer reads a Demo Request from its submission for Engineer Review on (`permissions.scope`). A request
written in at a later status, by the staging generator or by hand, has no such entry, and its Engineer would
stop reading it; this adds the entry, dated at the request's creation. Idempotent: a request that has the
entry is left alone, and so is a draft.
"""

from __future__ import annotations

import frappe

SUBMITTED_STATUSES = ("Engineer Review", "Engineer Returned", "Manager Approval", "Manager Rejected", "Converted")


def execute() -> None:
    if not frappe.db.table_exists("CRM Demo Request History"):
        return
    rows = frappe.db.sql(
        """SELECT `request`.`name`, `request`.`sales_owner`, `request`.`creation`
        FROM `tabCRM Demo Request` AS `request`
        WHERE `request`.`status` IN %(statuses)s
          AND NOT EXISTS (
            SELECT 1 FROM `tabCRM Demo Request History` AS `history`
            WHERE `history`.`demo_request` = `request`.`name` AND `history`.`to_status` = 'Engineer Review'
          )""",
        {"statuses": SUBMITTED_STATUSES},
        as_dict=True,
    )
    for row in rows:
        frappe.get_doc({
            "doctype": "CRM Demo Request History", "demo_request": row.name, "at": row.creation,
            "actor": row.sales_owner or "Administrator", "from_status": "Draft", "to_status": "Engineer Review",
            "comment": "Submission recorded by backfill_demo_request_submissions",
        }).insert(ignore_permissions=True)
    frappe.logger("rayher_crm").info(f"backfill_demo_request_submissions: {len(rows)} entries added")
