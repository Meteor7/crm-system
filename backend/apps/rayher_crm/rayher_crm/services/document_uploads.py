"""Secure controlled-document upload staging and Manager publication."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

import frappe
from frappe.utils import add_years, now_datetime, today
from rayher_crm.services.private_file_lifecycle import save_private_file as save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import as_payload, optional_date, required_text, validate_choice
from rayher_crm.services.file_security import MAX_FILE_BYTES, PDF_MIME, TIPRAY_HEADER, MalwareScanner, validate_and_scan
from rayher_crm.services.notifications import active_crm_users, create_notification


def _metadata(value: Any) -> dict[str, str]:
    payload = as_payload(value)
    return {
        "title": required_text(payload, "title"),
        "category": validate_choice(payload.get("category"), "category", {"Technical", "Commercial"}),
        "document_type": required_text(payload, "documentType"),
        "access_mode": validate_choice(payload.get("accessMode"), "accessMode", {"Direct", "Request"}),
        "confidentiality": validate_choice(payload.get("confidentiality"), "confidentiality", {"Internal", "Confidential", "Restricted"}),
        "product": str(payload.get("product") or "General").strip() or "General",
        "version": str(payload.get("version") or "1.0").strip() or "1.0",
        "revision": str(payload.get("revision") or "R1").strip() or "R1",
        "review_date": optional_date(payload.get("reviewDate"), "reviewDate") or str(add_years(today(), 1)),
        "applicable_tool": str(payload.get("applicableTool") or "").strip(),
    }


def _part(part: Mapping[str, Any]) -> tuple[str, str, bytes]:
    name, mime, content = part.get("file_name"), part.get("mime_type"), part.get("content")
    if not isinstance(name, str) or not isinstance(mime, str) or not isinstance(content, bytes):
        raise CrmApiException("VALIDATION_ERROR", "Upload requires file_name, mime_type and byte content.")
    return name, mime, content


def _serialize(doc) -> dict[str, Any]:
    submitter_name = frappe.db.get_value("User", doc.submitted_by, "full_name") or doc.submitted_by
    try:
        submitter_role = resolve_crm_role(doc.submitted_by)
    except frappe.PermissionError:
        submitter_role = ""
    return {
        "id": doc.name, "title": doc.title, "category": doc.category,
        "documentType": doc.document_type, "accessMode": doc.access_mode,
        "confidentiality": doc.confidentiality, "product": doc.product,
        "version": doc.version, "revision": doc.revision, "reviewDate": str(doc.review_date or ""),
        "applicableTool": doc.applicable_tool or "", "fileName": doc.file_name,
        "mimeType": doc.mime_type, "size": int(doc.size_bytes or 0), "status": doc.status,
        "submittedBy": doc.submitted_by, "submittedByName": submitter_name,
        "submittedByRole": submitter_role, "submittedAt": str(doc.creation or ""),
        "decidedBy": doc.decided_by or "", "decidedAt": str(doc.decided_at or ""),
        "decisionReason": doc.decision_reason or "", "publishedDocumentId": doc.published_document or "",
    }


def _audit(entity_id: str, action: str, outcome: str, reason: str = "") -> None:
    frappe.get_doc({
        "doctype": "CRM File Access Audit", "entity_type": "Controlled Document",
        "entity_id": entity_id, "actor": frappe.session.user, "action": action,
        "outcome": outcome, "reason": reason[:140], "at": now_datetime(),
        "request_id": str(getattr(frappe.local, "request_id", "") or "")[:140],
    }).insert(ignore_permissions=True)


def _document_id(request_name: str) -> str:
    suffix = re.search(r"(\d+)$", request_name)
    if not suffix:
        raise CrmApiException("INTERNAL_ERROR", "Upload request has no publication sequence.")
    return f"DOC-UPL-{int(suffix.group(1)):05d}"


def _publish(request) -> None:
    if not request.private_file or not frappe.db.exists("File", request.private_file):
        raise CrmApiException("NOT_FOUND", "The staged upload file is unavailable.")
    document_id = _document_id(request.name)
    if frappe.db.exists("CRM Controlled Document", document_id):
        raise CrmApiException("CONFLICT", "This upload request has already been published.")
    stored_file_name = str(frappe.db.get_value("File", request.private_file, "file_name") or "")
    is_pdf = request.mime_type == PDF_MIME and not stored_file_name.endswith(".bin")
    document = frappe.get_doc({
        "doctype": "CRM Controlled Document", "document_id": document_id,
        "title": request.title, "category": request.category, "document_type": request.document_type,
        "product": request.product, "version": request.version, "revision": request.revision,
        "status": "Released", "confidentiality": request.confidentiality,
        "access_mode": request.access_mode, "review_date": request.review_date,
        "document_owner": request.submitted_by, "private_file": request.private_file,
        "file_name": request.file_name, "mime_type": request.mime_type,
        "size_bytes": request.size_bytes, "content_hash": request.content_hash,
        "preview_file": request.private_file if is_pdf else None,
        "preview_file_name": request.file_name if is_pdf else "",
        "preview_content_hash": request.content_hash if is_pdf else "",
        "applicable_tool": request.applicable_tool or "",
    }).insert(ignore_permissions=True)
    frappe.db.set_value("File", request.private_file, {
        "attached_to_doctype": "CRM Controlled Document", "attached_to_name": document.name,
        "attached_to_field": None, "owner": "Administrator",
    }, update_modified=False)
    request.status = "Published"
    request.published_document = document.name
    request.decided_by = frappe.session.user
    request.decided_at = now_datetime()
    request.save(ignore_permissions=True)
    _audit(document.name, "Publish", "Allowed", request.name)


def submit_upload(input_value: Any, part: Mapping[str, Any], scanner: MalwareScanner | None = None) -> dict[str, Any]:
    assert_capability("account:view")
    values = _metadata(input_value)
    file_name, claimed_mime, content = _part(part)
    if len(content) > MAX_FILE_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "File exceeds the 100 MiB limit.")
    mime_type = validate_and_scan(file_name, claimed_mime, content, scanner)
    submitted_by = str(frappe.session.user)
    savepoint = f"crm_document_submit_{frappe.generate_hash(length=8)}"
    staged_file = None
    frappe.db.savepoint(savepoint)
    try:
        request = frappe.get_doc({
            "doctype": "CRM Document Upload Request", **values, "status": "Pending",
            "file_name": file_name, "mime_type": mime_type, "size_bytes": len(content),
            "content_hash": hashlib.sha256(content).hexdigest(), "submitted_by": submitted_by,
        }).insert(ignore_permissions=True)
        storage_name = (
            f"tipray-{frappe.generate_hash(length=20)}.bin"
            if content.startswith(TIPRAY_HEADER)
            else file_name
        )
        file_doc = save_file(storage_name, content, request.doctype, request.name, is_private=1)
        staged_file = file_doc.name
        request.db_set("private_file", staged_file, update_modified=False)
        request.reload()
        if resolve_crm_role(submitted_by) == "Manager":
            _publish(request)
        else:
            for manager in active_crm_users("Manager"):
                create_notification(
                    recipient=manager, category="Document",
                    title="Controlled document upload requires approval",
                    message=f"{request.title}: {request.file_name}",
                    route="/document-center?workspace=approvals",
                    source_doctype="CRM Document Upload Request", source_name=request.name,
                )
        return _serialize(request)
    except Exception:
        try:
            if staged_file and frappe.db.exists("File", staged_file):
                frappe.delete_doc("File", staged_file, ignore_permissions=True, force=True)
        finally:
            frappe.db.rollback(save_point=savepoint)
        raise


def list_upload_requests() -> list[dict[str, Any]]:
    if resolve_crm_role() != "Manager":
        raise frappe.PermissionError("Manager approval is required.")
    names = frappe.get_all(
        "CRM Document Upload Request", filters={"status": "Pending"}, pluck="name",
        order_by="creation desc",
    )
    return [_serialize(frappe.get_doc("CRM Document Upload Request", name)) for name in names]


def decide_upload_request(request_id: Any, input_value: Any) -> dict[str, Any]:
    if resolve_crm_role() != "Manager":
        raise frappe.PermissionError("Manager approval is required.")
    name = required_text({"requestId": request_id}, "requestId")
    payload = as_payload(input_value)
    decision = validate_choice(payload.get("decision"), "decision", {"approve", "reject"})
    savepoint = f"crm_document_upload_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        locked = frappe.db.sql(
            "SELECT `name` FROM `tabCRM Document Upload Request` WHERE `name` = %s FOR UPDATE",
            (name,),
        )
        if not locked:
            raise CrmApiException("NOT_FOUND", "The document upload request was not found.")
        request = frappe.get_doc("CRM Document Upload Request", name)
        if request.status != "Pending":
            raise CrmApiException("CONFLICT", "This document upload request has already been decided.")
        if decision == "approve":
            request.category = validate_choice(payload.get("category"), "category", {"Technical", "Commercial"})
            request.confidentiality = validate_choice(payload.get("confidentiality"), "confidentiality", {"Internal", "Confidential", "Restricted"})
            request.access_mode = validate_choice(payload.get("accessMode"), "accessMode", {"Direct", "Request"})
            _publish(request)
        else:
            reason = required_text(payload, "reason")
            private_file = request.private_file
            request.status = "Rejected"
            request.decision_reason = reason
            request.decided_by = frappe.session.user
            request.decided_at = now_datetime()
            request.private_file = None
            request.save(ignore_permissions=True)
            _audit(request.name, "Reject", "Allowed", reason)
            if request.submitted_by != frappe.session.user:
                create_notification(
                    recipient=request.submitted_by, category="Document",
                    title="Controlled document upload rejected",
                    message=request.decision_reason,
                    route="/document-center",
                    source_doctype="CRM Document Upload Request", source_name=request.name,
                )
            if private_file and frappe.db.exists("File", private_file):
                frappe.delete_doc("File", private_file, ignore_permissions=True, force=True)
        if decision == "approve" and request.submitted_by != frappe.session.user:
            create_notification(
                recipient=request.submitted_by, category="Document",
                title="Controlled document upload published",
                message=f"{request.title} is now Published.",
                route="/document-center",
                source_doctype="CRM Document Upload Request", source_name=request.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return _serialize(request)
