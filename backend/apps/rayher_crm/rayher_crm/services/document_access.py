"""Persistent approval workflow for controlled-document delivery."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import required_text
from rayher_crm.services.notifications import active_crm_users, notify_if_reachable


APPROVAL_DECISIONS = {
    "approve-watermarked": ("Approved", "Watermarked"),
    "approve-original": ("Approved", "Original"),
    "reject": ("Rejected", ""),
    "more-info": ("More Info Required", ""),
}


def version_id(document) -> str:
    return f"{document.document_id}-{document.version}-{document.revision}"


def _document_for_version(value: str):
    for name in frappe.get_all("CRM Controlled Document", pluck="name"):
        document = frappe.get_doc("CRM Controlled Document", name)
        if version_id(document) == value:
            return document
    raise CrmApiException("NOT_FOUND", "The controlled-document version is unavailable.")


def latest_request(document_id: str, requester: str | None = None):
    filters: dict[str, Any] = {"controlled_document": document_id}
    if requester:
        filters["requester"] = requester
    names = frappe.get_all(
        "CRM Document Access Request",
        filters=filters,
        pluck="name",
        order_by="creation desc",
        limit_page_length=1,
    )
    return frappe.get_doc("CRM Document Access Request", names[0]) if names else None


def serialize_request(document) -> dict[str, Any]:
    requester_name = frappe.db.get_value("User", document.requester, "full_name") or document.requester
    try:
        requester_role = resolve_crm_role(document.requester)
    except frappe.PermissionError:
        requester_role = ""
    controlled = frappe.get_doc("CRM Controlled Document", document.controlled_document)
    return {
        "id": document.name,
        "requester": document.requester,
        "requesterName": requester_name,
        "requesterRole": requester_role,
        "documentId": document.controlled_document,
        "documentTitle": controlled.title,
        "versionId": document.version_id,
        "reason": document.reason,
        "status": document.status,
        "deliveryMode": document.delivery_mode or "",
        "submittedAt": str(document.creation or ""),
        "decidedBy": document.decided_by or "",
        "decidedAt": str(document.decided_at or ""),
    }


def create_request(version_id_value: Any, reason: Any) -> dict[str, Any]:
    assert_capability("account:view")
    requested_version = required_text({"versionId": version_id_value}, "versionId")
    request_reason = required_text({"reason": reason}, "reason")
    document = _document_for_version(requested_version)
    # Serialize the Pending check for this document before inserting. Without
    # the parent-row lock, concurrent clicks can create duplicate requests.
    locked = frappe.db.sql(
        "SELECT `name` FROM `tabCRM Controlled Document` WHERE `name` = %s FOR UPDATE",
        (document.name,),
    )
    if not locked:
        raise CrmApiException("NOT_FOUND", "The controlled-document version is unavailable.")
    document = frappe.get_doc("CRM Controlled Document", document.name)
    if document.status != "Released" or document.access_mode != "Request":
        raise CrmApiException("PERMISSION_DENIED", "This document does not accept access requests.")
    requester = str(frappe.session.user)
    existing = latest_request(document.name, requester)
    if existing and existing.version_id == requested_version and existing.status == "Pending":
        return serialize_request(existing)
    savepoint = f"crm_document_access_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        created = frappe.get_doc({
            "doctype": "CRM Document Access Request",
            "controlled_document": document.name,
            "version_id": requested_version,
            "requester": requester,
            "reason": request_reason,
            "status": "Pending",
        }).insert(ignore_permissions=True)
        for manager in active_crm_users("Manager"):
            if manager == requester:
                continue
            notify_if_reachable(
                recipient=manager, category="Document",
                title="Controlled document access requires approval",
                message=f"{document.title}: {request_reason}",
                route="/document-center?workspace=approvals",
                source_doctype="CRM Document Access Request", source_name=created.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_request(created)


def list_requests() -> list[dict[str, Any]]:
    if resolve_crm_role() != "Manager":
        raise frappe.PermissionError("Manager approval is required.")
    names = frappe.get_all(
        "CRM Document Access Request",
        filters={"status": "Pending"},
        pluck="name",
        order_by="creation desc",
    )
    return [serialize_request(frappe.get_doc("CRM Document Access Request", name)) for name in names]


def decide_request(request_id: Any, decision: Any) -> dict[str, Any]:
    if resolve_crm_role() != "Manager":
        raise frappe.PermissionError("Manager approval is required.")
    request_name = required_text({"requestId": request_id}, "requestId")
    decision_name = required_text({"decision": decision}, "decision")
    if decision_name not in APPROVAL_DECISIONS:
        raise CrmApiException("VALIDATION_ERROR", "Unknown controlled-document decision.")
    savepoint = f"crm_document_access_decision_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        locked = frappe.db.sql(
            "SELECT `name` FROM `tabCRM Document Access Request` WHERE `name` = %s FOR UPDATE",
            (request_name,),
        )
        if not locked:
            raise CrmApiException("NOT_FOUND", "The controlled-document request was not found.")
        document = frappe.get_doc("CRM Document Access Request", request_name)
        if document.status != "Pending":
            raise CrmApiException("CONFLICT", "This controlled-document request has already been decided.")
        status, delivery_mode = APPROVAL_DECISIONS[decision_name]
        document.status = status
        document.delivery_mode = delivery_mode
        document.decided_by = frappe.session.user
        document.decided_at = now_datetime()
        document.save(ignore_permissions=True)
        if document.requester != frappe.session.user:
            notify_if_reachable(
                recipient=document.requester, category="Document",
                title=f"Controlled document access {status.lower()}",
                message=f"{document.version_id}: your access request is now {status}.",
                route="/document-center",
                source_doctype="CRM Document Access Request", source_name=document.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_request(document)


def authorized_request(document, action: str):
    role = resolve_crm_role()
    if role == "Manager":
        return None, "Original"
    request = latest_request(document.name, str(frappe.session.user))
    if (
        not request
        or request.version_id != version_id(document)
        or request.status != "Approved"
        or request.delivery_mode not in {"Watermarked", "Original"}
    ):
        raise CrmApiException("PERMISSION_DENIED", "Approved document access is required.")
    return request, request.delivery_mode
