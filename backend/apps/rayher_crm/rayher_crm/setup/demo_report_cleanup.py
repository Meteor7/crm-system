"""Retire legacy generated external Demo Test Reports after schema migration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import frappe


LEGACY_REPORT_TYPE = "External Demo Test Report PDF"
TEST_REPORT_TYPE = "Test Report"
LEGACY_FILE_NAME = re.compile(r"^external-demo-report-CRM-EVAL-\d{5}-v\d+\.pdf$")


def _latest_test_report(evaluation_id: str) -> dict[str, Any] | None:
    rows = frappe.get_all(
        "CRM Demo Artifact",
        filters={
            "evaluation": evaluation_id,
            "artifact_type": TEST_REPORT_TYPE,
            "visibility": "Internal",
        },
        fields=["name", "artifact_version"],
        order_by="artifact_version desc, creation desc, name desc",
        limit=1,
        ignore_permissions=True,
    )
    return rows[0] if rows else None


def _repair_evaluation(evaluation_id: str) -> bool:
    if not frappe.db.exists("CRM Evaluation", evaluation_id):
        return False
    evaluation = frappe.get_doc("CRM Evaluation", evaluation_id)
    latest = _latest_test_report(evaluation_id)
    values = {
        "report_artifact_id": latest.name if latest else None,
        "report_version": int(latest.artifact_version) if latest else 0,
        "report_status": "Ready" if latest else "Not Ready",
    }
    if all(evaluation.get(field) == value for field, value in values.items()):
        return False
    frappe.db.set_value("CRM Evaluation", evaluation_id, values, update_modified=False)
    return True


def _remove_orphaned_legacy_files() -> int:
    root = Path(frappe.get_site_path("private", "files")).resolve()
    deleted = 0
    for candidate in root.iterdir():
        if not LEGACY_FILE_NAME.fullmatch(candidate.name) or candidate.is_symlink():
            continue
        target = candidate.resolve()
        if target.parent != root or not target.is_file():
            continue
        target.unlink()
        deleted += 1
    return deleted


def cleanup_external_demo_reports() -> dict[str, int]:
    """Delete every legacy generated report and repair only its report projection."""
    legacy_rows = frappe.get_all(
        "CRM Demo Artifact",
        filters={"artifact_type": LEGACY_REPORT_TYPE},
        fields=["name", "evaluation", "private_file"],
        order_by="name asc",
        ignore_permissions=True,
    )
    affected_evaluations = {row.evaluation for row in legacy_rows if row.evaluation}

    # Recover safely from an earlier interrupted cleanup that removed metadata first.
    pointed = frappe.db.sql(
        "SELECT `name`, `report_artifact_id` FROM `tabCRM Evaluation` "
        "WHERE COALESCE(`report_artifact_id`, '') != ''",
        as_dict=True,
    )
    for row in pointed:
        artifact_type = frappe.db.get_value("CRM Demo Artifact", row.report_artifact_id, "artifact_type")
        if artifact_type in {None, LEGACY_REPORT_TYPE}:
            affected_evaluations.add(row.name)

    files_deleted = 0
    for row in legacy_rows:
        # Artifacts are immutable through normal application flows; migration owns this exact legacy type.
        frappe.db.delete("CRM Demo Artifact", {"name": row.name})
        if row.private_file and frappe.db.exists("File", row.private_file):
            frappe.delete_doc("File", row.private_file, ignore_permissions=True, force=True)
            files_deleted += 1

    evaluations_repaired = sum(
        1 for evaluation_id in sorted(affected_evaluations) if _repair_evaluation(evaluation_id)
    )
    physical_files_deleted = _remove_orphaned_legacy_files()
    return {
        "artifactsDeleted": len(legacy_rows),
        "filesDeleted": files_deleted,
        "evaluationsRepaired": evaluations_repaired,
        "physicalFilesDeleted": physical_files_deleted,
    }


__all__ = ["cleanup_external_demo_reports"]
