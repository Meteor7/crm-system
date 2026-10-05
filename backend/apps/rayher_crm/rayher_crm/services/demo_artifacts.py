"""Private Demo Request artifacts with server-owned versions and download audit."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import frappe
from frappe.utils import now_datetime
from rayher_crm.services.private_file_lifecycle import save_private_file as save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.rayher_crm.doctype.crm_demo_artifact.crm_demo_artifact import SERVICE_OWNED_ARTIFACT_FLAG
from rayher_crm.services.common import normalize_pagination, to_iso_timestamp
from rayher_crm.services.demo_requests import _require_demo_request
from rayher_crm.services.file_security import DOCX_MIME, MAX_FILE_BYTES, MalwareScanner, validate_and_scan


REQUEST_DOCX = "Demo Request DOCX"
TEST_REPORT = "Test Report"
CUSTOMER_REPORT = "Customer Report"


def insert_service_artifact(values: Mapping[str, Any]):
    """Create a CRM Demo Artifact on behalf of an upload service.

    Only the upload services may create artifacts: they scan the file, check the
    workflow stage and allocate the version first. The controller rejects any
    insert without this in-memory flag, so neither the standard resource API nor
    the Desk form can post a forged report row.
    """
    artifact = frappe.get_doc({"doctype": "CRM Demo Artifact", **values})
    artifact.flags[SERVICE_OWNED_ARTIFACT_FLAG] = True
    return artifact.insert(ignore_permissions=True)


def _serialize(doc) -> dict[str, Any]:
    result = {
        "id": doc.name,
        "demoRequestId": doc.demo_request,
        "type": doc.artifact_type,
        "fileName": doc.file_name,
        "mimeType": doc.mime_type,
        "version": int(doc.artifact_version),
        "createdBy": doc.created_by_user,
        "createdAt": to_iso_timestamp(doc.created_at),
        "visibility": doc.visibility,
    }
    if doc.evaluation:
        result["evaluationId"] = doc.evaluation
    if doc.artifact_type in (TEST_REPORT, CUSTOMER_REPORT):
        # Only reports belong to a test round; the Demo Request form predates testing.
        result["round"] = int(doc.test_round or 1)
    return result


def _part(upload: Mapping[str, Any]) -> tuple[str, str, bytes]:
    file_name = upload.get("file_name")
    mime_type = upload.get("mime_type")
    content = upload.get("content")
    if not isinstance(file_name, str) or not isinstance(mime_type, str) or not isinstance(content, bytes):
        raise CrmApiException("VALIDATION_ERROR", "Artifact upload requires file_name, mime_type and byte content.")
    return file_name, mime_type, content


def _audit(
    entity_id: str,
    account: str | None,
    outcome: str,
    reason: str = "",
    access_id: str | None = None,
) -> None:
    frappe.get_doc({
        "doctype": "CRM File Access Audit",
        "entity_type": "Demo Artifact",
        "entity_id": entity_id,
        "account": account,
        "actor": frappe.session.user,
        "action": "Download",
        "outcome": outcome,
        "reason": reason[:140],
        "at": now_datetime(),
        "request_id": str(getattr(frappe.local, "request_id", "") or "")[:140],
        "access_id": access_id,
    }).insert(ignore_permissions=True)
    frappe.local.flags.commit = True


def _lock_request(request_id: str):
    rows = frappe.db.sql(
        "SELECT `name` FROM `tabCRM Demo Request` WHERE `name` = %s FOR UPDATE",
        (request_id,),
    )
    if not rows:
        raise CrmApiException("DEMO_REQUEST_NOT_FOUND", "Demo Request was not found.")
    return frappe.get_doc("CRM Demo Request", request_id)


def _lock_evaluation(evaluation_id: str):
    rows = frappe.db.sql(
        "SELECT `name` FROM `tabCRM Evaluation` WHERE `name` = %s FOR UPDATE",
        (evaluation_id,),
    )
    if not rows:
        raise CrmApiException("EVALUATION_NOT_FOUND", "Evaluation was not found.")
    return frappe.get_doc("CRM Evaluation", evaluation_id)


def _next_version(request_id: str, evaluation_id: str | None) -> int:
    # Serialize allocation on the parent request, including self-test rows
    # whose nullable evaluation field cannot provide a unique-index lock.
    frappe.db.sql(
        "SELECT `name` FROM `tabCRM Demo Request` WHERE `name` = %s FOR UPDATE",
        (request_id,),
    )
    if evaluation_id:
        rows = frappe.db.sql(
            "SELECT `artifact_version` FROM `tabCRM Demo Artifact` "
            "WHERE `demo_request` = %s AND `evaluation` = %s AND `artifact_type` = %s "
            "ORDER BY `artifact_version` DESC LIMIT 1 FOR UPDATE",
            (request_id, evaluation_id, REQUEST_DOCX),
        )
    else:
        rows = frappe.db.sql(
            "SELECT `artifact_version` FROM `tabCRM Demo Artifact` "
            "WHERE `demo_request` = %s AND `evaluation` IS NULL AND `artifact_type` = %s "
            "ORDER BY `artifact_version` DESC LIMIT 1 FOR UPDATE",
            (request_id, REQUEST_DOCX),
        )
    return int(rows[0][0] if rows else 0) + 1


def save_demo_artifact(
    payload: Mapping[str, Any], upload: Mapping[str, Any], scanner: MalwareScanner | None = None,
) -> dict[str, Any]:
    assert_capability("demo_request:create")
    if payload.get("type") != REQUEST_DOCX:
        raise CrmApiException("VALIDATION_ERROR", "Artifact type is invalid.")
    if payload.get("visibility") != "Internal":
        raise CrmApiException("VALIDATION_ERROR", "Demo Request DOCX visibility must be Internal.")
    request_id = payload.get("demoRequestId")
    if not isinstance(request_id, str) or not request_id.strip():
        raise CrmApiException("VALIDATION_ERROR", "demoRequestId is required.")
    request_id = request_id.strip()
    _require_demo_request(request_id)

    evaluation_id = payload.get("evaluationId")
    if evaluation_id is not None:
        if not isinstance(evaluation_id, str) or not evaluation_id.strip():
            raise CrmApiException("VALIDATION_ERROR", "evaluationId must be a stable string id.")
        evaluation_id = evaluation_id.strip()
        if not frappe.db.exists("CRM Evaluation", evaluation_id):
            raise CrmApiException("EVALUATION_NOT_FOUND", "Evaluation was not found.")
        if frappe.db.get_value("CRM Evaluation", evaluation_id, "demo_request") != request_id:
            raise CrmApiException("LINK_MISMATCH", "Artifact Request and Evaluation do not match.")

    file_name, claimed_mime, content = _part(upload)
    actual_mime = validate_and_scan(file_name, claimed_mime, content, scanner)
    if actual_mime != DOCX_MIME:
        raise CrmApiException("VALIDATION_ERROR", "Demo Request artifact must be a DOCX file.")

    savepoint = f"crm_demo_artifact_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        request = _lock_request(request_id)
        if not frappe.has_permission("CRM Demo Request", "read", doc=request, user=frappe.session.user):
            raise CrmApiException("SCOPE_DENIED", "The Demo Request is outside the current user scope.")
        if evaluation_id:
            evaluation = _lock_evaluation(evaluation_id)
            if evaluation.demo_request != request.name or evaluation.account != request.account:
                raise CrmApiException("LINK_MISMATCH", "Artifact Request and Evaluation do not match.")
        version = _next_version(request.name, evaluation_id)
        file_doc = save_file(file_name.strip(), content, "CRM Demo Request", request.name, is_private=1)
        meta = insert_service_artifact({
            "demo_request": request.name,
            "evaluation": evaluation_id,
            "account": request.account,
            "artifact_type": REQUEST_DOCX,
            "private_file": file_doc.name,
            "file_name": file_name.strip(),
            "mime_type": actual_mime,
            "size_bytes": len(content),
            "artifact_version": version,
            "visibility": "Internal",
            "content_hash": hashlib.sha256(content).hexdigest(),
            "created_by_user": frappe.session.user,
            "created_at": now_datetime(),
        })
        frappe.db.set_value(
            "File", file_doc.name,
            # File's native owner shortcut must not bypass the scoped download endpoint:
            # the uploader keeps the URL after losing the role or the scope. The real
            # author is recorded on the artifact's own `created_by_user`.
            {
                "attached_to_doctype": "CRM Demo Artifact", "attached_to_name": meta.name,
                "attached_to_field": None, "owner": "Administrator",
            },
            update_modified=False,
        )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    meta.reload()
    return _serialize(meta)


def list_demo_artifacts(demo_request_id: str, query: Mapping[str, Any] | None = None):
    assert_capability("demo_request:view")
    _require_demo_request(demo_request_id)
    where = f"`demo_request` = %s AND ({conditions_for_doctype('CRM Demo Artifact')})"
    values: tuple[Any, ...] = (demo_request_id,)
    if query is None:
        rows = frappe.db.sql(
            f"SELECT `name` FROM `tabCRM Demo Artifact` WHERE {where} ORDER BY `artifact_version` ASC, `name` ASC",
            values, as_dict=True,
        )
        return [_serialize(frappe.get_doc("CRM Demo Artifact", row.name)) for row in rows]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Demo Artifact` WHERE {where}", values)[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Demo Artifact` WHERE {where} ORDER BY `artifact_version` ASC, `name` ASC LIMIT %s OFFSET %s",
        (*values, page_size, offset), as_dict=True,
    )
    return [_serialize(frappe.get_doc("CRM Demo Artifact", row.name)) for row in rows], total, page, page_size


def _file_belongs_to_artifact(file_doc, meta) -> bool:
    """Serve only a private file attached to this artifact or to its own Demo.

    The upload services attach each file to its artifact. A file still attached to
    the artifact's Evaluation or Demo Request is accepted for rows created before
    re-attachment, but a file owned by any other record is never served, even if
    an artifact row points at it.
    """
    if not file_doc.is_private:
        return False
    owners = {("CRM Demo Artifact", meta.name)}
    if meta.evaluation:
        owners.add(("CRM Evaluation", meta.evaluation))
    if meta.demo_request:
        owners.add(("CRM Demo Request", meta.demo_request))
    return (file_doc.attached_to_doctype, file_doc.attached_to_name) in owners


def download_demo_artifact(artifact_id: str) -> dict[str, Any]:
    access_id = f"RPTDL-{frappe.generate_hash(length=20).upper()}"
    if not frappe.db.exists("CRM Demo Artifact", artifact_id):
        _audit(artifact_id, None, "Denied", "not found")
        raise CrmApiException("DEMO_ARTIFACT_NOT_FOUND", "Demo Artifact was not found.")
    meta = frappe.get_doc("CRM Demo Artifact", artifact_id)
    try:
        assert_capability("demo_request:view")
    except frappe.PermissionError:
        try:
            assert_capability("evaluation:view")
        except frappe.PermissionError as exc:
            _audit(artifact_id, meta.account, "Denied", "capability denied")
            raise exc
    submitted = bool(frappe.db.exists(
        "CRM Demo Request History",
        {"demo_request": meta.demo_request, "to_status": "Engineer Review"},
    ))
    if resolve_crm_role() != "Sales" and not submitted:
        _audit(artifact_id, meta.account, "Denied", "request not submitted")
        raise CrmApiException("PERMISSION_DENIED", "The Demo Artifact is not visible before submission.")
    if not frappe.has_permission("CRM Demo Artifact", "read", doc=meta, user=frappe.session.user):
        _audit(artifact_id, meta.account, "Denied", "scope denied")
        raise CrmApiException("SCOPE_DENIED", "The Demo Artifact is outside the current user scope.")
    file_doc = frappe.get_doc("File", meta.private_file) if frappe.db.exists("File", meta.private_file) else None
    if file_doc is None or not _file_belongs_to_artifact(file_doc, meta):
        _audit(artifact_id, meta.account, "Denied", "file not owned by artifact")
        raise CrmApiException("PERMISSION_DENIED", "The Demo Artifact file does not belong to this record.")
    from rayher_crm.services.managed_file_access import authorize_restricted_file_read
    authorize_restricted_file_read(file_doc)
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    content = bytes(content)
    _audit(artifact_id, meta.account, "Allowed", access_id=access_id)
    return {"content": content, "file_name": meta.file_name, "mime_type": meta.mime_type}


__all__ = [
    "MAX_FILE_BYTES", "download_demo_artifact", "insert_service_artifact", "list_demo_artifacts",
    "save_demo_artifact",
]
