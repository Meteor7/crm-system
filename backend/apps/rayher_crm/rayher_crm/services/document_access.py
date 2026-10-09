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


def serialize_request(document, *, with_document: bool = False, audit: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The request; with `with_document`, the document's own confidentiality, status and download audit as well,
    for the approval detail of a document the Released library no longer lists. The audit is read here for one
    request; a caller serializing many passes the audit it read for all of their documents at once."""
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
        # The version and revision the request names, as the document had them when it was made; a request older
        # than the fields takes the document's while it still names the document's current version.
        "version": document.document_version or (controlled.version if document.version_id == version_id(controlled) else ""),
        "revision": document.document_revision or (controlled.revision if document.version_id == version_id(controlled) else ""),
        "reason": document.reason,
        "status": document.status,
        "deliveryMode": document.delivery_mode or "",
        "submittedAt": str(document.creation or ""),
        "decidedBy": document.decided_by or "",
        "decidedAt": str(document.decided_at or ""),
        "decisionNote": document.decision_note or "",
        **(_document_of_request(controlled, audit) if with_document else {}),
    }


def _document_of_request(controlled, audit: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from rayher_crm.services.read_only_views import _download_audit

    user = str(frappe.session.user)
    return {
        "documentConfidentiality": controlled.confidentiality or "",
        "documentStatus": controlled.status or "",
        "documentAudit": _download_audit(controlled, user, resolve_crm_role(user)) if audit is None else audit,
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
            "document_version": document.version,
            "document_revision": document.revision,
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
    from rayher_crm.services.read_only_views import _download_audits

    # The audit of every document the queue names is read once, not once per request.
    requests = [frappe.get_doc("CRM Document Access Request", name) for name in names]
    documents: dict[str, Any] = {}
    for request in requests:
        if request.controlled_document not in documents:
            documents[request.controlled_document] = frappe.get_doc("CRM Controlled Document", request.controlled_document)
    user = str(frappe.session.user)
    audits = _download_audits(list(documents.values()), user, resolve_crm_role(user))
    return [
        serialize_request(request, with_document=True, audit=audits.get(documents[request.controlled_document].document_id, []))
        for request in requests
    ]


MAX_DECISION_NOTE = 1000


# A notice's message is held to this (`notifications.py`): the note is told as far as it fits, the request keeps it all.
NOTICE_MESSAGE_LIMIT = 1000


def decide_request(request_id: Any, decision: Any, note: Any = None) -> dict[str, Any]:
    if resolve_crm_role() != "Manager":
        raise frappe.PermissionError("Manager approval is required.")
    request_name = required_text({"requestId": request_id}, "requestId")
    decision_name = required_text({"decision": decision}, "decision")
    if decision_name not in APPROVAL_DECISIONS:
        raise CrmApiException("VALIDATION_ERROR", "Unknown controlled-document decision.")
    # The applicant is told what to add: a request for more information carries a note; a rejection may. An approval
    # carries none, and one sent with it is refused rather than dropped unseen.
    if note is not None and not isinstance(note, str):
        raise CrmApiException("VALIDATION_ERROR", "The note must be text.", field_errors={"note": "Must be text"})
    note_text = (note or "").strip()
    if note_text and decision_name not in {"more-info", "reject"}:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "An approval carries no note: clear it, or reject the request or ask for more information.",
            field_errors={"note": "Not with an approval"},
        )
    if decision_name == "more-info" and not note_text:
        raise CrmApiException(
            "VALIDATION_ERROR", "Say what the applicant should add.", field_errors={"note": "Required"},
        )
    if len(note_text) > MAX_DECISION_NOTE:
        raise CrmApiException("VALIDATION_ERROR", f"The note may hold at most {MAX_DECISION_NOTE} characters.")
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
        if decision_name == "approve-watermarked":
            # The approval must still have a PDF source, even when the client loaded an older library.
            # A locking read checks the current committed document and keeps its source stable until approval.
            sources = frappe.db.sql(
                "SELECT `preview_file` FROM `tabCRM Controlled Document` WHERE `name` = %s FOR UPDATE",
                (document.controlled_document,), as_dict=True,
            )
            if not sources or not sources[0].preview_file:
                raise CrmApiException(
                    "VALIDATION_ERROR", "This document has no PDF preview. Approve the original file instead.",
                )
        status, delivery_mode = APPROVAL_DECISIONS[decision_name]
        document.status = status
        document.delivery_mode = delivery_mode
        document.decided_by = frappe.session.user
        document.decided_at = now_datetime()
        document.decision_note = note_text
        document.save(ignore_permissions=True)
        if document.requester != frappe.session.user:
            head = f"{document.version_id}: your access request is now {status}."
            room = NOTICE_MESSAGE_LIMIT - len(head) - 1
            told = note_text if len(note_text) <= room else note_text[: room - 1].rstrip() + "…"
            notify_if_reachable(
                recipient=document.requester, category="Document",
                title=f"Controlled document access {status.lower()}",
                message=head + (f" {told}" if told else ""),
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
