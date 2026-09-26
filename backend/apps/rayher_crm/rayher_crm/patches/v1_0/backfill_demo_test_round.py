"""Give every pre-existing Evaluation, Demo Artifact and Test Run a test round of 1.

Retests are numbered from the round they reopen, so records created before
rounds existed have to read as round 1 rather than 0/NULL.
"""

import frappe


def execute():
    if frappe.db.table_exists("CRM Evaluation"):
        frappe.db.sql(
            "UPDATE `tabCRM Evaluation` SET `test_round` = 1 "
            "WHERE COALESCE(`test_round`, 0) < 1"
        )
    if frappe.db.table_exists("CRM Demo Artifact"):
        frappe.db.sql(
            "UPDATE `tabCRM Demo Artifact` SET `test_round` = 1 "
            "WHERE COALESCE(`test_round`, 0) < 1"
        )
    if frappe.db.table_exists("CRM Test Run"):
        frappe.db.sql(
            "UPDATE `tabCRM Test Run` SET `test_round` = 1 "
            "WHERE COALESCE(`test_round`, 0) < 1"
        )
