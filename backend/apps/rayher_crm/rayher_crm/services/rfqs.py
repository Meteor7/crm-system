"""RFQ workflow, private-file delivery, and Opportunity approval gate."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import frappe
from frappe.utils import now_datetime
from rayher_crm.services.private_file_lifecycle import save_private_file as save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.permissions.scope import has_crm_permission
from rayher_crm.services.common import normalize_pagination, paginate_items, required_text, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.file_security import (
    DOCX_MIME,
    JPEG_MIME,
    MAX_FILE_BYTES,
    PDF_MIME,
    PNG_MIME,
    PPTX_MIME,
    TIPRAY_HEADER,
    XLSX_MIME,
    MalwareScanner,
    validate_and_scan,
)
from rayher_crm.services.notifications import active_crm_users, create_notification, notify_if_reachable
from rayher_crm.services.opportunity_stages import CUSTOMER_BUDGET_APPROVED
from rayher_crm.services.sites import can_read_site_data

ALLOWED_MIME_TYPES = {PDF_MIME, PNG_MIME, JPEG_MIME, DOCX_MIME, XLSX_MIME, PPTX_MIME}
OFFICE_MIME_TYPES = {DOCX_MIME, XLSX_MIME, PPTX_MIME}
STATUSES = {"Engineer Review", "Manager Approval", "Sales Revision", "Approved"}
CONVERSION_TIMEOUT_SECONDS = 90
TIPRAY_PREVIEW_ERROR = (
    "TipRay-protected RFQ files cannot be previewed online. Download the original file to view it."
)


def _notify(recipients: set[str], master, title: str, message: str, *, informational: bool = False) -> None:
    notify = notify_if_reachable if informational else create_notification
    for recipient in sorted(recipients - {frappe.session.user, None, ""}):
        notify(
            recipient=recipient,
            category="RFQ",
            title=title,
            message=message,
            route=f"/rfqs/{master.name}",
            source_doctype="CRM RFQ",
            source_name=master.name,
        )


def reopen_approved_rfq_for_stage_rollback(opportunity_id: str, reason: str) -> None:
    """Reopen an approved RFQ when its Opportunity rolls back across the RFQ gate."""

    rows = frappe.db.sql(
        "SELECT `name`, `status`, `current_version` FROM `tabCRM RFQ` WHERE `opportunity` = %s FOR UPDATE",
        (opportunity_id,),
        as_dict=True,
    )
    if not rows or rows[0].status != "Approved":
        return
    master = frappe.get_doc("CRM RFQ", rows[0].name)
    if not master.current_version:
        raise CrmApiException("CONFLICT", "Approved RFQ has no current version.")
    version = frappe.get_doc("CRM RFQ Version", master.current_version)
    if version.status != "Approved":
        raise CrmApiException("CONFLICT", "Approved RFQ version state is inconsistent.")

    decided_at = now_datetime()
    version.status = "Returned"
    version.manager_decision = "Returned"
    version.manager_comment = reason
    version.manager_decided_by = frappe.session.user
    version.manager_decided_at = decided_at
    version.save(ignore_permissions=True)
    master.status = "Sales Revision"
    master.approved_by = None
    master.approved_at = None
    master.save(ignore_permissions=True)
    _notify(
        {master.sales_owner, master.engineer_owner},
        master,
        "RFQ revision required after stage rollback",
        f"{master.name}: Opportunity stage was rolled back. Upload a revised RFQ and repeat technical approval.",
        informational=True,
    )


def _active_engineer(user_id: Any) -> str:
    normalized = required_text({"engineerId": user_id}, "engineerId")
    if not frappe.db.exists("User", {"name": normalized, "enabled": 1}):
        raise CrmApiException("VALIDATION_ERROR", "Engineer is not an active user.")
    try:
        if resolve_crm_role(normalized) != "Engineer":
            raise CrmApiException("VALIDATION_ERROR", "Assigned user must be a CRM Engineer.")
    except frappe.PermissionError as exc:
        raise CrmApiException("VALIDATION_ERROR", "Assigned user must be a CRM Engineer.") from exc
    return normalized


def _require_rfq_uploader() -> None:
    if resolve_crm_role() not in {"Sales", "Manager"}:
        raise frappe.PermissionError("CRM Sales or Manager role is required.")


def _require_manager() -> None:
    if resolve_crm_role() != "Manager":
        raise frappe.PermissionError("CRM Manager role is required.")


def _require_rfq(name: Any):
    normalized = required_text({"id": name}, "id")
    if not frappe.db.exists("CRM RFQ", normalized):
        raise CrmApiException("NOT_FOUND", "RFQ was not found.")
    doc = frappe.get_doc("CRM RFQ", normalized)
    if not frappe.has_permission("CRM RFQ", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "RFQ is outside the current user scope.")
    return doc


def _display_name(user_id: str) -> str:
    return frappe.db.get_value("User", user_id, "full_name") or user_id


def _opportunity_summary(opportunity_id: str) -> dict[str, Any]:
    opportunity = frappe.get_doc("CRM Opportunity", opportunity_id)
    can_read_site = can_read_site_data(opportunity.account)
    return {
        "id": opportunity.name,
        "title": opportunity.title,
        "accountId": opportunity.account,
        "account": frappe.db.get_value("Customer", opportunity.account, "customer_name") or opportunity.account,
        "siteId": opportunity.site if can_read_site else "",
        "site": (frappe.db.get_value("Address", opportunity.site, "address_title") or opportunity.site) if can_read_site else "",
        "stage": opportunity.stage,
        "owner": opportunity.opportunity_owner,
        "toolType": opportunity.tool_type,
        "poDate": str(opportunity.po_date or ""),
    }


def _serialize_version(version) -> dict[str, Any]:
    return {
        "id": version.name,
        "version": int(version.version_no or 0),
        "status": version.status,
        "fileName": version.file_name,
        "mimeType": version.mime_type,
        "size": int(version.size_bytes or 0),
        "uploadedBy": version.uploaded_by,
        "uploadedByName": _display_name(version.uploaded_by),
        "uploadedAt": to_iso_timestamp(version.uploaded_at),
        "engineerComment": version.engineer_comment or "",
        "engineerCommentedBy": version.engineer_commented_by or "",
        "engineerCommentedByName": _display_name(version.engineer_commented_by) if version.engineer_commented_by else "",
        "engineerCommentedAt": to_iso_timestamp(version.engineer_commented_at) if version.engineer_commented_at else "",
        "managerDecision": version.manager_decision or "",
        "managerComment": version.manager_comment or "",
        "managerDecidedBy": version.manager_decided_by or "",
        "managerDecidedByName": _display_name(version.manager_decided_by) if version.manager_decided_by else "",
        "managerDecidedAt": to_iso_timestamp(version.manager_decided_at) if version.manager_decided_at else "",
    }


def _versions(doc) -> list[Any]:
    names = frappe.get_all(
        "CRM RFQ Version", filters={"rfq": doc.name}, pluck="name",
        order_by="version_no desc", limit_page_length=200,
    )
    return [frappe.get_doc("CRM RFQ Version", name) for name in names]


def _serialize_summary(doc) -> dict[str, Any]:
    opportunity = _opportunity_summary(doc.opportunity)
    version = frappe.get_doc("CRM RFQ Version", doc.current_version) if doc.current_version else None
    return {
        "id": doc.name,
        "opportunity": opportunity,
        "salesOwner": doc.sales_owner,
        "salesOwnerName": _display_name(doc.sales_owner),
        "engineerOwner": doc.engineer_owner,
        "engineerOwnerName": _display_name(doc.engineer_owner),
        "status": doc.status,
        "currentVersionId": doc.current_version or "",
        "latestVersion": int(doc.latest_version_no or 0),
        "fileName": version.file_name if version else "",
        "note": doc.note or "",
        "approvedBy": doc.approved_by or "",
        "approvedAt": to_iso_timestamp(doc.approved_at) if doc.approved_at else "",
        "modified": to_iso_timestamp(doc.modified),
    }


def _serialize_detail(doc) -> dict[str, Any]:
    result = _serialize_summary(doc)
    versions = _versions(doc)
    result["versions"] = [_serialize_version(version) for version in versions]
    result["currentVersion"] = next(
        (item for item in result["versions"] if item["id"] == doc.current_version), None,
    )
    return result


def list_rfqs(query: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    role = resolve_crm_role()
    filters: dict[str, Any] = {}
    if role == "Sales":
        filters["sales_owner"] = frappe.session.user
    elif role == "Engineer":
        filters["engineer_owner"] = frappe.session.user
    status = str(query.get("status") or "").strip()
    if status and status != "All":
        if status not in STATUSES:
            raise CrmApiException("VALIDATION_ERROR", "Unknown RFQ status.")
        filters["status"] = status
    opportunity_id = str(query.get("opportunityId") or "").strip()
    if opportunity_id:
        filters["opportunity"] = opportunity_id
    names = frappe.get_list("CRM RFQ", filters=filters, pluck="name", order_by="modified desc", limit_page_length=1000)
    rows = [_serialize_summary(frappe.get_doc("CRM RFQ", name)) for name in names]
    search = str(query.get("search") or "").strip().lower()
    owner = str(query.get("owner") or "").strip()
    if search:
        rows = [row for row in rows if search in " ".join((
            row["id"], row["opportunity"]["id"], row["opportunity"]["title"],
            row["opportunity"]["account"], row["opportunity"]["site"], row["fileName"],
        )).lower()]
    if owner and owner != "All":
        rows = [row for row in rows if owner in {row["salesOwner"], row["engineerOwner"]}]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    return rows[offset:offset + page_size], len(rows), page, page_size


def get_rfq(name: Any) -> dict[str, Any]:
    return _serialize_detail(_require_rfq(name))


def _file_part(part: Mapping[str, Any], scanner: MalwareScanner | None = None) -> tuple[str, str, bytes]:
    file_name, claimed_mime, content = part.get("file_name"), part.get("mime_type"), part.get("content")
    if not isinstance(file_name, str) or not isinstance(claimed_mime, str) or not isinstance(content, bytes):
        raise CrmApiException("VALIDATION_ERROR", "RFQ upload requires one valid file.")
    mime_type = validate_and_scan(file_name, claimed_mime, content, scanner)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise CrmApiException("VALIDATION_ERROR", "RFQ file type is not supported.")
    return file_name, mime_type, content


def _office_preview(file_name: str, content: bytes) -> tuple[str, str, bytes]:
    if content.startswith(TIPRAY_HEADER):
        raise CrmApiException("VALIDATION_ERROR", "Encrypted Office files must be decrypted before RFQ upload.")
    with tempfile.TemporaryDirectory(prefix="crm-rfq-") as directory:
        root = Path(directory)
        source = root / file_name
        source.write_bytes(content)
        profile = root / "profile"
        try:
            result = subprocess.run(
                [
                    "soffice", "--headless", "--nologo", "--nodefault", "--nolockcheck", "--norestore",
                    f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "pdf", "--outdir", str(root), str(source),
                ],
                check=False, capture_output=True, timeout=CONVERSION_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CrmApiException("INTERNAL_ERROR", "RFQ Office preview conversion is unavailable.", retryable=True) from exc
        target = root / f"{source.stem}.pdf"
        if result.returncode != 0 or not target.exists():
            raise CrmApiException("VALIDATION_ERROR", "RFQ Office file could not be converted to PDF.")
        preview = target.read_bytes()
        if not preview.startswith(b"%PDF-") or len(preview) > MAX_FILE_BYTES:
            raise CrmApiException("VALIDATION_ERROR", "RFQ Office preview output is invalid.")
        return target.name, PDF_MIME, preview


def _preview(file_name: str, mime_type: str, content: bytes) -> tuple[str, str, bytes] | None:
    if content.startswith(TIPRAY_HEADER):
        return None
    if mime_type in OFFICE_MIME_TYPES:
        return _office_preview(file_name, content)
    return file_name, mime_type, content


def _attach(file_id: str, version_id: str, fieldname: str) -> None:
    frappe.db.set_value("File", file_id, {
        "attached_to_doctype": "CRM RFQ Version",
        "attached_to_name": version_id,
        "attached_to_field": fieldname,
    }, update_modified=False)


def _create_version(master, part: Mapping[str, Any], scanner: MalwareScanner | None = None):
    file_name, mime_type, content = _file_part(part, scanner)
    preview_result = _preview(file_name, mime_type, content)
    storage_name = (
        f"tipray-{frappe.generate_hash(length=20)}.bin"
        if content.startswith(TIPRAY_HEADER)
        else file_name
    )
    original = save_file(storage_name, content, "CRM RFQ", master.name, is_private=1)
    if preview_result is None:
        preview_name, preview_mime, preview_content, preview = file_name, mime_type, content, original
    else:
        preview_name, preview_mime, preview_content = preview_result
        preview = original if preview_content == content and preview_mime == mime_type else save_file(
            preview_name, preview_content, "CRM RFQ", master.name, is_private=1,
        )
    number = int(master.latest_version_no or 0) + 1
    version = frappe.get_doc({
        "doctype": "CRM RFQ Version", "rfq": master.name, "version_no": number,
        "status": "Engineer Review", "original_file": original.name,
        "file_name": file_name, "mime_type": mime_type, "size_bytes": len(content),
        "content_hash": hashlib.sha256(content).hexdigest(), "preview_file": preview.name,
        "preview_file_name": preview_name, "preview_mime_type": preview_mime,
        "preview_content_hash": hashlib.sha256(preview_content).hexdigest(),
        "uploaded_by": frappe.session.user, "uploaded_at": now_datetime(),
    }).insert(ignore_permissions=True)
    _attach(original.name, version.name, "original_file")
    if preview.name != original.name:
        _attach(preview.name, version.name, "preview_file")
    master.current_version = version.name
    master.latest_version_no = number
    master.status = "Engineer Review"
    master.approved_by = None
    master.approved_at = None
    master.save(ignore_permissions=True)
    return version


def create_rfq(payload: Mapping[str, Any], part: Mapping[str, Any], scanner: MalwareScanner | None = None) -> dict[str, Any]:
    _require_rfq_uploader()
    opportunity_id = required_text(payload, "opportunityId")
    if not frappe.db.exists("CRM Opportunity", opportunity_id):
        raise CrmApiException("NOT_FOUND", "Opportunity was not found.")
    opportunity = frappe.get_doc("CRM Opportunity", opportunity_id)
    if not has_crm_permission(opportunity, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "Opportunity is outside the current user scope.")
    if opportunity.stage != CUSTOMER_BUDGET_APPROVED:
        raise CrmApiException(
            "INVALID_TRANSITION", "RFQ can only be created when the Opportunity is at customer_budget_approved.",
        )
    engineer = _active_engineer(payload.get("engineerId"))
    savepoint = f"crm_rfq_create_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        if frappe.db.exists("CRM RFQ", {"opportunity": opportunity_id}):
            raise CrmApiException("CONFLICT", "This Opportunity already has an RFQ.")
        master = frappe.get_doc({
            "doctype": "CRM RFQ", "opportunity": opportunity.name, "account": opportunity.account,
            "sales_owner": opportunity.opportunity_owner, "engineer_owner": engineer,
            "status": "Engineer Review", "latest_version_no": 0,
            "note": str(payload.get("note") or "").strip(),
        }).insert(ignore_permissions=True)
        _create_version(master, part, scanner)
        _notify(
            {engineer}, master, "RFQ requires Engineer review",
            f"{opportunity.title}: a new RFQ is ready for your technical comment.",
        )
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("CONFLICT", "This Opportunity already has an RFQ.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    master.reload()
    return _serialize_detail(master)


def revise_rfq(name: Any, part: Mapping[str, Any], expected_modified: Any, scanner: MalwareScanner | None = None) -> dict[str, Any]:
    _require_rfq_uploader()
    current = _require_rfq(name)
    master = lock_document("CRM RFQ", current.name, expected_modified, "NOT_FOUND")
    if resolve_crm_role() == "Sales" and master.sales_owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the RFQ Sales owner or a Manager can upload a revision.")
    if master.status != "Sales Revision":
        raise CrmApiException("INVALID_TRANSITION", "Only a returned RFQ can be revised.")
    savepoint = f"crm_rfq_revise_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        _create_version(master, part, scanner)
        _notify(
            {master.engineer_owner}, master, "RFQ revision requires Engineer review",
            f"{master.name}: Sales uploaded a revised RFQ version.", informational=True,
        )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    master.reload()
    return _serialize_detail(master)


def submit_engineer_comment(name: Any, comment: Any, expected_modified: Any) -> dict[str, Any]:
    if resolve_crm_role() != "Engineer":
        raise frappe.PermissionError("CRM Engineer role is required.")
    current = _require_rfq(name)
    master = lock_document("CRM RFQ", current.name, expected_modified, "NOT_FOUND")
    if master.engineer_owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the assigned Engineer can comment on this RFQ.")
    if master.status != "Engineer Review":
        raise CrmApiException("INVALID_TRANSITION", "RFQ is not waiting for Engineer Comment.")
    body = required_text({"comment": comment}, "comment")
    version = frappe.get_doc("CRM RFQ Version", master.current_version)
    version.status = "Manager Approval"
    version.engineer_comment = body
    version.engineer_commented_by = frappe.session.user
    version.engineer_commented_at = now_datetime()
    version.save(ignore_permissions=True)
    master.status = "Manager Approval"
    master.save(ignore_permissions=True)
    _notify(
        set(active_crm_users("Manager")), master, "RFQ requires Manager approval",
        f"{master.name}: Engineer review is complete.",
        informational=True,
    )
    master.reload()
    return _serialize_detail(master)


def review_rfq(name: Any, decision: Any, comment: Any, expected_modified: Any) -> dict[str, Any]:
    _require_manager()
    current = _require_rfq(name)
    master = lock_document("CRM RFQ", current.name, expected_modified, "NOT_FOUND")
    if master.status != "Manager Approval":
        raise CrmApiException("INVALID_TRANSITION", "RFQ is not waiting for Manager approval.")
    normalized = str(decision or "").strip()
    if normalized not in {"Approved", "Returned"}:
        raise CrmApiException("VALIDATION_ERROR", "Manager decision must be Approved or Returned.")
    manager_comment = str(comment or "").strip()
    if normalized == "Returned" and not manager_comment:
        raise CrmApiException("VALIDATION_ERROR", "A return reason is required.")
    if normalized == "Approved":
        opportunity_rows = frappe.db.sql(
            "SELECT name FROM `tabCRM Opportunity` WHERE name = %s FOR UPDATE",
            (master.opportunity,),
        )
        if not opportunity_rows:
            raise CrmApiException("NOT_FOUND", "Opportunity was not found.")
    savepoint = f"crm_rfq_review_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        version = frappe.get_doc("CRM RFQ Version", master.current_version)
        version.status = "Approved" if normalized == "Approved" else "Returned"
        version.manager_decision = normalized
        version.manager_comment = manager_comment
        version.manager_decided_by = frappe.session.user
        version.manager_decided_at = now_datetime()
        version.save(ignore_permissions=True)
        master.status = "Approved" if normalized == "Approved" else "Sales Revision"
        master.approved_by = frappe.session.user if normalized == "Approved" else None
        master.approved_at = now_datetime() if normalized == "Approved" else None
        master.save(ignore_permissions=True)
        if normalized == "Approved":
            from rayher_crm.services.opportunities import advance_opportunity_for_event

            advance_opportunity_for_event(
                master.opportunity, "rfq_approved", reference_doctype="CRM RFQ", reference_name=master.name,
            )
        _notify(
            {master.sales_owner, master.engineer_owner}, master,
            f"RFQ {normalized}",
            manager_comment or f"{master.name} was {normalized.lower()} by Manager.",
            informational=True,
        )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    master.reload()
    return _serialize_detail(master)


def _version_for_delivery(master, version_id: Any):
    name = str(version_id or master.current_version or "").strip()
    if not name or not frappe.db.exists("CRM RFQ Version", {"name": name, "rfq": master.name}):
        raise CrmApiException("NOT_FOUND", "RFQ version was not found.")
    return frappe.get_doc("CRM RFQ Version", name)


def _verified_file(version, fieldname: str, hash_field: str) -> bytes:
    file_id = getattr(version, fieldname)
    if not file_id or not frappe.db.exists("File", file_id):
        raise CrmApiException("NOT_FOUND", "RFQ file is unavailable.")
    file_doc = frappe.get_doc("File", file_id)
    from rayher_crm.services.managed_file_access import authorize_restricted_file_read
    authorize_restricted_file_read(file_doc)
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    if hashlib.sha256(content).hexdigest() != getattr(version, hash_field):
        raise CrmApiException("CONFLICT", "RFQ file integrity validation failed.")
    return content


def _audit(master, version, action: str) -> None:
    frappe.get_doc({
        "doctype": "CRM File Access Audit", "entity_type": "RFQ", "entity_id": master.name,
        "account": master.account,
        "actor": frappe.session.user, "action": action, "outcome": "Allowed",
        "reason": version.name, "at": now_datetime(),
        "request_id": str(getattr(frappe.local, "request_id", "") or "")[:140],
    }).insert(ignore_permissions=True)


def preview_rfq_file(name: Any, version_id: Any = None) -> dict[str, Any]:
    master = _require_rfq(name)
    version = _version_for_delivery(master, version_id)
    content = _verified_file(version, "preview_file", "preview_content_hash")
    if content.startswith(TIPRAY_HEADER):
        raise CrmApiException("VALIDATION_ERROR", TIPRAY_PREVIEW_ERROR)
    _audit(master, version, "Preview")
    return {"file_name": version.preview_file_name, "mime_type": version.preview_mime_type, "content": content}


def download_rfq_file(name: Any, version_id: Any = None) -> dict[str, Any]:
    master = _require_rfq(name)
    if resolve_crm_role() == "Engineer":
        raise frappe.PermissionError("Engineers may preview RFQ files but cannot download originals.")
    version = _version_for_delivery(master, version_id)
    content = _verified_file(version, "original_file", "content_hash")
    _audit(master, version, "Download")
    return {"file_name": version.file_name, "mime_type": version.mime_type, "content": content}
