"""Idempotent database indexes that Frappe DocType JSON cannot express."""

from __future__ import annotations

import frappe

from rayher_crm.patches.v1_0.add_file_content_hash_index import (
    ensure_index as ensure_file_content_hash_index,
)

ARTIFACT_INDEX = "unique_evaluation_artifact_version"
QUOTATION_VERSION_INDEX = "uq_crm_quotation_version_number"
PROBABILITY_HISTORY_INDEX = "idx_crm_opportunity_probability_history"
STAGE_HISTORY_INDEX = "idx_crm_opportunity_stage_history"
STAGE_REACHED_INDEX = "idx_crm_opportunity_stage_reached"
LOSS_REVIEW_INDEX = "idx_crm_opportunity_loss_review"
LOSS_REVIEW_REVISION_INDEX = "idx_crm_opportunity_loss_review_revision"
WARNING_HANDLING_REVISION_INDEX = "idx_crm_warning_handling_revision"
OPPORTUNITY_FIELD_HISTORY_INDEX = "idx_crm_opportunity_field_history"
LEAD_CONVERTED_ACCOUNT_INDEX = "custom_crm_converted_account_index"
NOTIFICATION_RECIPIENT_CREATED_INDEX = "idx_crm_notification_recipient_created"
NOTIFICATION_RECIPIENT_UNREAD_CREATED_INDEX = "idx_crm_notification_recipient_unread_created"
NOTIFICATION_SOURCE_INDEX = "idx_crm_notification_source"


def install_notification_indexes() -> None:
    if not frappe.db.table_exists("CRM Notification Event"):
        return
    frappe.db.add_index(
        "CRM Notification Event",
        ["recipient_user", "created_at", "name"],
        NOTIFICATION_RECIPIENT_CREATED_INDEX,
    )
    frappe.db.add_index(
        "CRM Notification Event",
        ["recipient_user", "read_at", "created_at", "name"],
        NOTIFICATION_RECIPIENT_UNREAD_CREATED_INDEX,
    )
    frappe.db.add_index(
        "CRM Notification Event",
        ["source_doctype", "source_name"],
        NOTIFICATION_SOURCE_INDEX,
    )

DEMO_REQUEST_SUBMISSION_INDEX = "idx_crm_demo_request_history_submission"


def install_stage5f_indexes() -> None:
    install_notification_indexes()
    if frappe.db.table_exists("File") and frappe.db.has_column("File", "content_hash"):
        ensure_file_content_hash_index()
    if frappe.db.table_exists("Lead") and frappe.db.has_column(
        "Lead", "custom_crm_converted_account",
    ):
        frappe.db.add_index(
            "Lead", ["custom_crm_converted_account"], LEAD_CONVERTED_ACCOUNT_INDEX,
        )
    if frappe.db.table_exists("CRM Demo Artifact"):
        rows = frappe.db.sql(
            """SELECT GROUP_CONCAT(`COLUMN_NAME` ORDER BY `SEQ_IN_INDEX`) AS columns
               FROM information_schema.STATISTICS
               WHERE `TABLE_SCHEMA` = DATABASE() AND `TABLE_NAME` = 'tabCRM Demo Artifact'
                 AND `INDEX_NAME` = %s
               GROUP BY `INDEX_NAME`""",
            (ARTIFACT_INDEX,),
        )
        expected = "evaluation,artifact_type,artifact_version,visibility"
        current = str(rows[0][0]) if rows else ""
        if current and current != expected:
            frappe.db.sql_ddl(
                f"ALTER TABLE `tabCRM Demo Artifact` "
                f"DROP INDEX `{ARTIFACT_INDEX}`, ADD UNIQUE `{ARTIFACT_INDEX}` "
                "(`evaluation`, `artifact_type`, `artifact_version`, `visibility`)"
            )
        elif not current:
            frappe.db.add_unique(
                "CRM Demo Artifact",
                ["evaluation", "artifact_type", "artifact_version", "visibility"],
                ARTIFACT_INDEX,
            )
    if frappe.db.table_exists("CRM Quotation Version"):
        frappe.db.add_unique(
            "CRM Quotation Version", ["quotation", "version_no"], QUOTATION_VERSION_INDEX,
        )
    if frappe.db.table_exists("CRM Opportunity Probability History"):
        frappe.db.add_index(
            "CRM Opportunity Probability History", ["opportunity", "changed_at"], PROBABILITY_HISTORY_INDEX,
        )
    if frappe.db.table_exists("CRM Opportunity History"):
        # Slip handling locks this opportunity's PO-date history, not other deals.
        frappe.db.add_index("CRM Opportunity History", ["opportunity", "field"], OPPORTUNITY_FIELD_HISTORY_INDEX)
    if frappe.db.table_exists("CRM Opportunity Stage History"):
        frappe.db.add_index(
            "CRM Opportunity Stage History", ["opportunity", "recorded_at"], STAGE_HISTORY_INDEX,
        )
        # The cockpit counts arrivals at a stage within a period.
        frappe.db.add_index(
            "CRM Opportunity Stage History", ["to_stage", "reached_at"], STAGE_REACHED_INDEX,
        )
    # Opportunity detail and list pages read post-mortems per Opportunity.
    if frappe.db.table_exists("CRM Opportunity Loss Review"):
        frappe.db.add_index("CRM Opportunity Loss Review", ["opportunity", "lost_at"], LOSS_REVIEW_INDEX)
    if frappe.db.table_exists("CRM Opportunity Loss Review Revision"):
        frappe.db.add_index(
            "CRM Opportunity Loss Review Revision", ["opportunity", "recorded_at"], LOSS_REVIEW_REVISION_INDEX,
        )
    # An Engineer reads a Demo Request from its submission on: their every read asks the history for it.
    if frappe.db.table_exists("CRM Demo Request History"):
        frappe.db.add_index("CRM Demo Request History", ["demo_request", "to_status"], DEMO_REQUEST_SUBMISSION_INDEX)
    # Review and Warnings read every handling's revisions; the Opportunity delete removes them per handling.
    if frappe.db.table_exists("CRM Warning Handling Revision"):
        frappe.db.add_index(
            "CRM Warning Handling Revision", ["handling", "recorded_at"], WARNING_HANDLING_REVISION_INDEX,
        )
