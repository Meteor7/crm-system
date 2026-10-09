"""Engineer-uploaded Demo Test Reports with atomic versioning and notifications."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from typing import Any

import frappe
from frappe.utils import now_datetime
from rayher_crm.services.private_file_lifecycle import discard_rolled_back_blob
from rayher_crm.services.private_file_lifecycle import save_private_file as save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability
from rayher_crm.services.demo_artifacts import (
    CUSTOMER_REPORT,
    TEST_REPORT,
    _part,
    _serialize,
    insert_service_artifact,
)
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
from rayher_crm.services.notifications import notify_if_reachable


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


REPORT_MARKER = re.compile(r"^\[(?:External|Internal|Customer)\]\s+", re.IGNORECASE)


def _marked_file_name(file_name: str, label: str) -> str:
    return f"[{label}] {REPORT_MARKER.sub('', file_name).strip()}"


def _notification(recipient: str, evaluation, request, version: int) -> None:
    notify_if_reachable(
        recipient=recipient,
        category="Evaluation",
        title="Test Report uploaded",
        message=f"{evaluation.name} Test Report v{version} is available in Article.",
        route=f"/demo-workflow/{request.name}?tab=information",
        source_doctype="CRM Evaluation",
        source_name=evaluation.name,
    )


def _remove_orphaned_files(generated: list[tuple[str, str, str]]) -> None:
    """Delete the files an aborted upload wrote, but never a file another record still owns.

    Frappe de-duplicates uploads by content hash: saving bytes that already exist on
    disk creates a new File row that points at the *existing* file_url instead of
    writing a second copy. After the savepoint rollback removed this upload's File
    row, a file_url that some other File row still references belongs to that earlier
    upload and must stay on disk -- including an upload committed by another session
    after this request opened its snapshot, which is why the decision belongs to
    ``private_file_lifecycle`` and its current-read reference check rather than to a
    plain ``frappe.db.exists`` on this connection.
    """
    for path, file_url, content_hash in generated:
        discard_rolled_back_blob(path, file_url, content_hash)


def _assert_expected_round(evaluation, expected_round: Any) -> None:
    """A retest opens a new round, and a report picked in an older window belongs to that round.

    The upload carries the round the uploader saw, so a window left open across a retest is
    refused instead of filing last round's report as evidence for the new one.
    """

    current = int(evaluation.test_round or 1)
    if expected_round in (None, ""):
        raise CrmApiException(
            "VALIDATION_ERROR", "expectedRound is required.", field_errors={"expectedRound": "Required"},
        )
    try:
        expected = int(expected_round)
    except (TypeError, ValueError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "expectedRound must be a whole number.") from exc
    if expected != current:
        raise CrmApiException(
            "CONFLICT",
            f"The Demo Test is on round {current} now; reload it before uploading this report.",
        )


def release_demo_test_report(
    evaluation_id: str,
    internal_file: Mapping[str, Any],
    external_file: Mapping[str, Any],
    *,
    scanner: MalwareScanner | None = None,
    failure_injector: Callable[[str], None] | None = None,
    expected_round: Any = None,
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
    generated_files: list[tuple[str, str, str]] = []
    frappe.db.savepoint(savepoint)
    try:
        evaluation = _lock_evaluation(evaluation_id)
        if not frappe.has_permission("CRM Evaluation", "read", doc=evaluation, user=frappe.session.user):
            raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
        if evaluation.status != "Testing":
            raise CrmApiException("INVALID_REPORT_STAGE", "Test Report upload requires Testing status.")
        _assert_expected_round(evaluation, expected_round)
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
            generated_files.append((file_doc.get_full_path(), file_doc.file_url, file_doc.content_hash))
            artifact = insert_service_artifact({
                "demo_request": request.name,
                "evaluation": evaluation.name,
                "account": request.account,
                "artifact_type": TEST_REPORT,
                "private_file": file_doc.name,
                "file_name": file_name,
                "mime_type": actual_mime,
                "size_bytes": len(content),
                "artifact_version": version,
                "test_round": int(evaluation.test_round or 1),
                "visibility": visibility,
                "content_hash": hashlib.sha256(content).hexdigest(),
                "created_by_user": frappe.session.user,
                "created_at": now_datetime(),
            })
            frappe.db.set_value(
                "File", file_doc.name,
                # File's native owner shortcut must not bypass download_demo_artifact:
                # the uploader keeps the URL after losing the role or the scope. The
                # real author is recorded on the artifact's own `created_by_user`.
                {
                    "attached_to_doctype": "CRM Demo Artifact", "attached_to_name": artifact.name,
                    "attached_to_field": None, "owner": "Administrator",
                },
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
        _remove_orphaned_files(generated_files)
        raise
    for artifact in artifacts.values():
        artifact.reload()
    return {
        "internalReportArtifact": _serialize(artifacts["Internal"]),
        "externalReportArtifact": _serialize(artifacts["External"]),
        "version": version,
    }


def _next_customer_report_version(evaluation) -> int:
    rows = frappe.db.sql(
        "SELECT `artifact_version` FROM `tabCRM Demo Artifact` "
        "WHERE `evaluation` = %s AND `artifact_type` = %s "
        "ORDER BY `artifact_version` DESC LIMIT 1 FOR UPDATE",
        (evaluation.name, CUSTOMER_REPORT),
    )
    return int(rows[0][0] if rows else 0) + 1


def upload_customer_report(
    evaluation_id: str,
    file: Mapping[str, Any],
    *,
    scanner: MalwareScanner | None = None,
    expected_round: Any = None,
) -> dict[str, Any]:
    """Store the customer-supplied report for the current test round.

    Customer Reports are append-only like Test Reports: a retest opens a new round
    rather than replacing what an earlier round produced.
    """
    assert_capability("evaluation:customer_review")
    _require_evaluation(evaluation_id)
    file_name, claimed_mime, content = _part(file)
    actual_mime = validate_and_scan(file_name, claimed_mime, content, scanner)
    marked_name = _marked_file_name(file_name, "Customer")
    savepoint = f"crm_customer_report_{frappe.generate_hash(length=8)}"
    generated_files: list[tuple[str, str, str]] = []
    frappe.db.savepoint(savepoint)
    try:
        evaluation = _lock_evaluation(evaluation_id)
        if not frappe.has_permission("CRM Evaluation", "read", doc=evaluation, user=frappe.session.user):
            raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
        if evaluation.status != "Customer Review":
            raise CrmApiException(
                "INVALID_REPORT_STAGE", "Customer Report upload requires Customer Review status.",
            )
        _assert_expected_round(evaluation, expected_round)
        request = _request_for_evaluation(evaluation)
        version = _next_customer_report_version(evaluation)
        test_round = int(evaluation.test_round or 1)
        storage_name = (
            f"tipray-{frappe.generate_hash(length=20)}.bin"
            if content.startswith(TIPRAY_HEADER)
            else marked_name
        )
        file_doc = save_file(storage_name, content, "CRM Evaluation", evaluation.name, is_private=1)
        generated_files.append((file_doc.get_full_path(), file_doc.file_url, file_doc.content_hash))
        artifact = insert_service_artifact({
            "demo_request": request.name,
            "evaluation": evaluation.name,
            "account": request.account,
            "artifact_type": CUSTOMER_REPORT,
            "private_file": file_doc.name,
            "file_name": marked_name,
            "mime_type": actual_mime,
            "size_bytes": len(content),
            "artifact_version": version,
            "test_round": test_round,
            "visibility": "Customer Review",
            "content_hash": hashlib.sha256(content).hexdigest(),
            "created_by_user": frappe.session.user,
            "created_at": now_datetime(),
        })
        frappe.db.set_value(
            "File", file_doc.name,
            # Same as the Test Report path: the uploader must not keep native access
            # to the blob through File's owner shortcut.
            {
                "attached_to_doctype": "CRM Demo Artifact", "attached_to_name": artifact.name,
                "attached_to_field": None, "owner": "Administrator",
            },
            update_modified=False,
        )
        evaluation.customer_report_artifact_id = artifact.name
        evaluation.save(ignore_permissions=True)
        summary = f"Uploaded Customer Report v{version} for round {test_round}"
        append_evaluation_history(
            evaluation, "Report", summary, str(version - 1) if version > 1 else "", str(version),
        )
        _update_request_tracking(evaluation, summary)
        recipients = {request.sales_owner, evaluation.evaluation_owner} - {frappe.session.user}
        for recipient in sorted(recipients):
            notify_if_reachable(
                recipient=recipient,
                category="Evaluation",
                title="Customer Report uploaded",
                message=f"{evaluation.name} Customer Report v{version} (round {test_round}) is available in Article.",
                route=f"/demo-workflow/{request.name}?tab=information",
                source_doctype="CRM Evaluation",
                source_name=evaluation.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        _remove_orphaned_files(generated_files)
        raise
    artifact.reload()
    return {"artifact": _serialize(artifact), "round": test_round, "version": version}


__all__ = ["MAX_FILE_BYTES", "release_demo_test_report", "upload_customer_report"]
