import frappe


def execute():
    if frappe.db.table_exists("CRM Demo Request"):
        frappe.db.sql(
            "UPDATE `tabCRM Demo Request` SET `request_mode` = 'Opportunity' "
            "WHERE COALESCE(`request_mode`, '') = ''"
        )
    if frappe.db.table_exists("CRM Evaluation"):
        frappe.db.sql(
            "UPDATE `tabCRM Evaluation` SET `internal_report_artifact_id` = `report_artifact_id` "
            "WHERE COALESCE(`internal_report_artifact_id`, '') = '' "
            "AND COALESCE(`report_artifact_id`, '') != ''"
        )
        if frappe.db.table_exists("CRM Demo Artifact"):
            frappe.db.sql(
                "UPDATE `tabCRM Demo Artifact` artifact "
                "INNER JOIN `tabCRM Evaluation` evaluation "
                "ON evaluation.`internal_report_artifact_id` = artifact.`name` "
                "SET artifact.`visibility` = 'Internal' "
                "WHERE COALESCE(evaluation.`external_report_artifact_id`, '') = ''"
            )
