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
OPPORTUNITY_STAKEHOLDER_INDEX = "idx_crm_opportunity_stakeholder_active"
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


# The single-column indexes the reads of one parent's rows go through: the Account's archive reads its Opportunities
# and Bookings under their locks (accounts._account_index_hint), which then lock those rows and not the table; a
# submission for approval numbers its approval from its Quotation's approvals, read without a lock
# (quotations._next_attempt_no).
LOOKUP_INDEXES = (("CRM Opportunity", "account"), ("CRM Booking", "account"), ("CRM Quotation Approval", "quotation"))


def install_lookup_indexes() -> None:
    """The DocTypes declare these indexes (`search_index`) and Frappe's schema sync makes them, but the sync looks for
    an index on a column by the table's name alone, in every database of the server, and counts one the column leads:
    on a server with another site's table, or with such an index, it makes none. Made here only when the column has
    no single-column index, under the name the sync gives one it adds, so never a second one."""

    for doctype, column in LOOKUP_INDEXES:
        if frappe.db.table_exists(doctype) and not frappe.db.get_column_index(f"tab{doctype}", column, unique=False):
            frappe.db.add_index(doctype, [column], f"{column}_index")


def install_stage5f_indexes() -> None:
    install_notification_indexes()
    install_lookup_indexes()
    if frappe.db.table_exists("CRM Cockpit Target"):
        frappe.db.add_index("CRM Cockpit Target", ["period", "anchor"], "idx_crm_target_period")
        frappe.db.add_index("CRM Cockpit Target", ["period", "sales_owner", "metric", "anchor"], "idx_crm_target_defaults")
    if frappe.db.table_exists("CRM Plan Commitment"):
        frappe.db.add_index("CRM Plan Commitment", ["period", "anchor"], "idx_crm_commitment_period")
        # Non-unique: historical duplicates remain visible for reconciliation.
        frappe.db.add_index("CRM Plan Commitment", ["sales_owner", "metric", "period", "anchor"], "idx_crm_commitment_owner")
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
    if frappe.db.table_exists("CRM Opportunity Stakeholder"):
        frappe.db.add_index("CRM Opportunity Stakeholder", ["opportunity", "archived", "name"], OPPORTUNITY_STAKEHOLDER_INDEX)
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
    # Review and Warnings read every handling's revisions, per handling.
    if frappe.db.table_exists("CRM Warning Handling Revision"):
        frappe.db.add_index(
            "CRM Warning Handling Revision", ["handling", "recorded_at"], WARNING_HANDLING_REVISION_INDEX,
        )
    if frappe.db.table_exists("CRM Evaluation") and frappe.db.has_column("CRM Evaluation", "demo_resource"):
        frappe.db.add_index("CRM Evaluation", ["demo_resource", "name"], "crm_demo_resource_schedule")
        frappe.db.add_index("CRM Evaluation", ["status", "demo_resource", "name"], "crm_active_demo_resource_schedule")
    if frappe.db.table_exists("CRM Demo Unavailability"):
        frappe.db.add_index("CRM Demo Unavailability", ["resource", "status"], "crm_demo_resource_availability")
    if frappe.db.table_exists("CRM Demo Resource Impact"):
        frappe.db.add_index("CRM Demo Resource Impact", ["evaluation", "detected_at"], "crm_demo_resource_history")
