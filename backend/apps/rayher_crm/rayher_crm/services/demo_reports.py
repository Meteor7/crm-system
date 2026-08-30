"""Engineer-uploaded Demo Test Reports with atomic versioning and notifications."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability
from rayher_crm.services.demo_artifacts import TEST_REPORT, _part, _serialize
from rayher_crm.services.evaluations import (
    _lock_evaluation,
    _require_evaluation,
    _update_request_tracking,
    append_evaluation_history,
)
from rayher_crm.services.file_security import (
    MAX_FILE_BYTES,
    TIPRAY_HEADER,
    MalwareScanner,
    validate_and_scan,
)
from rayher_crm.services.notifications import create_notification


def _request_for_evaluation(evaluation):
    if not evaluation.demo_request or not frappe.db.exists("CRM Demo Request", evaluation.demo_request):
        raise CrmApiException("DEMO_REQUEST_NOT_FOUND", "The source Demo Request was not found.")
    request = frappe.get_doc("CRM Demo Request", evaluation.demo_request)
    if request.account != evaluation.account:
        raise CrmApiException("LINK_MISMATCH", "Evaluation and Demo Request accounts do not match.")
    return request


def _next_report_version(evaluation) -> int:
    rows = frappe.db.sql(
        "SELECT `artifact_version` FROM `tabCRM Demo Artifact` "
        "WHERE `evaluation` = %s AND `artifact_type` = %s "
        "ORDER BY `artifact_version` DESC LIMIT 1 FOR UPDATE",
        (evaluation.name, TEST_REPORT),
    )
    return max(int(evaluation.report_version or 0), int(rows[0][0] if rows else 0)) + 1


REPORT_MARKER = re.compile(r"^\[(?:External|Internal)\]\s+", re.IGNORECASE)


def _marked_file_name(file_name: str, label: str) -> str:
    return f"[{label}] {REPORT_MARKER.sub('', file_name).strip()}"


def _notification(recipient: str, evaluation, request, version: int) -> None:
    create_notification(
        recipient=recipient,
        category="Evaluation",
        title="Test Report uploaded",
        message=f"{evaluation.name} Test Report v{version} is available in Article.",
        route=f"/demo-workflow/{request.name}?tab=information",
        source_doctype="CRM Evaluation",
        source_name=evaluation.name,
    )


def _remove_generated_file(path: str | None) -> None:
    if not path:
        return
    root = Path(frappe.get_site_path("private", "files")).resolve()
    target = Path(path).resolve()
    if root not in target.parents or not target.is_file():
        return
    target.unlink()


def release_demo_test_report(
    evaluation_id: str,
    internal_file: Mapping[str, Any],
    external_file: Mapping[str, Any],
    *,
    scanner: MalwareScanner | None = None,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    assert_capability("evaluation:write")
    _require_evaluation(evaluation_id)
    uploads = {
        "Internal": (*_part(internal_file), "Internal"),
        "External": (*_part(external_file), "Customer Review"),
    }
    validated: dict[str, tuple[str, str, bytes, str]] = {}
    for label, (file_name, claimed_mime, content, visibility) in uploads.items():
        actual_mime = validate_and_scan(file_name, claimed_mime, content, scanner)
        validated[label] = (_marked_file_name(file_name, label), actual_mime, content, visibility)
    savepoint = f"crm_report_upload_{frappe.generate_hash(length=8)}"
    generated_paths: list[str] = []
    frappe.db.savepoint(savepoint)
    try:
        evaluation = _lock_evaluation(evaluation_id)
        if not frappe.has_permission("CRM Evaluation", "read", doc=evaluation, user=frappe.session.user):
            raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
        if evaluation.status != "Testing":
            raise CrmApiException("INVALID_REPORT_STAGE", "Test Report upload requires Testing status.")
        request = _request_for_evaluation(evaluation)
        version = _next_report_version(evaluation)
        artifacts = {}
        for label, (file_name, actual_mime, content, visibility) in validated.items():
            storage_name = (
                f"tipray-{frappe.generate_hash(length=20)}.bin"
                if content.startswith(TIPRAY_HEADER)
                else file_name
            )
            file_doc = save_file(storage_name, content, "CRM Evaluation", evaluation.name, is_private=1)
            generated_paths.append(file_doc.get_full_path())
            artifact = frappe.get_doc({
                "doctype": "CRM Demo Artifact",
                "demo_request": request.name,
                "evaluation": evaluation.name,
                "account": request.account,
                "artifact_type": TEST_REPORT,
                "private_file": file_doc.name,
                "file_name": file_name,
                "mime_type": actual_mime,
                "size_bytes": len(content),
                "artifact_version": version,
                "visibility": visibility,
                "content_hash": hashlib.sha256(content).hexdigest(),
                "created_by_user": frappe.session.user,
                "created_at": now_datetime(),
            }).insert(ignore_permissions=True)
            frappe.db.set_value(
                "File", file_doc.name,
                {"attached_to_doctype": "CRM Demo Artifact", "attached_to_name": artifact.name, "attached_to_field": None},
                update_modified=False,
            )
            artifacts[label] = artifact
        if failure_injector:
            failure_injector("after_artifact_insert")
        evaluation.report_status = "Ready"
        evaluation.report_artifact_id = artifacts["Internal"].name
        evaluation.internal_report_artifact_id = artifacts["Internal"].name
        evaluation.external_report_artifact_id = artifacts["External"].name
        evaluation.report_version = version
        evaluation.save(ignore_permissions=True)
        append_evaluation_history(
            evaluation, "Report", f"Uploaded Test Report v{version}",
            str(version - 1) if version > 1 else "", str(version),
        )
        _update_request_tracking(evaluation, f"Uploaded Test Report v{version}")
        if failure_injector:
            failure_injector("after_evaluation_update")
        recipients = {request.sales_owner, evaluation.evaluation_owner} - {frappe.session.user}
        for recipient in sorted(recipients):
            _notification(recipient, evaluation, request, version)
        if failure_injector:
            failure_injector("after_notification_insert")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        for generated_path in generated_paths:
            _remove_generated_file(generated_path)
        raise
    for artifact in artifacts.values():
        artifact.reload()
    return {
        "internalReportArtifact": _serialize(artifacts["Internal"]),
        "externalReportArtifact": _serialize(artifacts["External"]),
        "version": version,
    }


__all__ = ["MAX_FILE_BYTES", "release_demo_test_report"]
