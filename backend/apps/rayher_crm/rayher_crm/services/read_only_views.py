"""Read-only CRM views plus controlled-document request projections."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import normalize_pagination
from rayher_crm.services.document_access import create_request, latest_request, serialize_request, version_id


def _require_crm_identity() -> None:
    user = getattr(frappe.session, "user", None)
    if not user or user == "Guest":
        raise frappe.PermissionError("A CRM identity is required.")
    resolve_crm_role(user)


def _empty_page(query: dict[str, Any]) -> tuple[list[dict], int, int, int]:
    _require_crm_identity()
    page, page_size, _offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    return [], 0, page, page_size


def list_requirements(query: dict[str, Any]) -> tuple[list[dict], int, int, int]:
    assert_capability("requirement:view")
    return _empty_page(query)


def list_contracts(query: dict[str, Any]) -> tuple[list[dict], int, int, int]:
    assert_capability("contract:view")
    return _empty_page(query)


AUDIT_ENTRIES = 50


def _download_audits(documents: list, user: str, role: str) -> dict[str, list[dict[str, Any]]]:
    """The downloads of each document the user may see, by document id: every one for a Manager, their own for
    anyone else (who downloaded what is for the Manager to see); the fifty most recent of each. The purpose shown is
    that of the access request, when the download was by an approved request; a download without a request (the
    own download of a Manager, or a document open to direct access) says so. The version is the one the audit row
    recorded at the download; a row older than that record shows that of its request, and none without one. One
    read of the audit, one of the requests and one of the users, whatever the number of documents."""

    ids = [document.document_id for document in documents]
    entries: dict[str, list[dict[str, Any]]] = {document_id: [] for document_id in ids}
    if not ids:
        return entries
    # The fifty most recent rows of each document, taken in the database (a window over the document), so
    # that the read does not grow with the lifetime of the audit.
    actor_clause = "" if role == "Manager" else " AND `actor` = %(actor)s"
    kept = frappe.db.sql(
        "SELECT `name`, `entity_id`, `actor`, `at`, `reason`, `version_id` FROM ("
        "SELECT `name`, `entity_id`, `actor`, `at`, `reason`, `version_id`, "
        "ROW_NUMBER() OVER (PARTITION BY `entity_id` ORDER BY `at` DESC, `name` DESC) AS `recency` "
        "FROM `tabCRM File Access Audit` "
        "WHERE `entity_type` = 'Controlled Document' AND `entity_id` IN %(ids)s "
        f"AND `action` = 'Download' AND `outcome` = 'Allowed'{actor_clause}) AS `recent` "
        "WHERE `recency` <= %(limit)s ORDER BY `at` DESC, `name` DESC",
        {"ids": tuple(ids), "actor": user, "limit": AUDIT_ENTRIES}, as_dict=True,
    )
    parsed = [(row, _audit_marker(row)) for row in kept]
    request_names = sorted({marker for _row, marker in parsed if marker and marker not in {"MANAGER-PREVIEW", "DIRECT-ACCESS"}})
    requests = {
        request.name: request
        for request in frappe.get_all("CRM Document Access Request", filters={"name": ["in", request_names]}, fields=["name", "reason", "version_id"])
    } if request_names else {}
    actors = sorted({str(row.actor) for row in kept})
    full_names = {
        account.name: account.full_name for account in frappe.get_all("User", filters={"name": ["in", actors]}, fields=["name", "full_name"])
    } if actors else {}
    for row, marker in parsed:
        note = str(row.reason or "").strip()
        noted_version = str(row.version_id or "")
        request = requests.get(marker) if marker and marker not in {"MANAGER-PREVIEW", "DIRECT-ACCESS"} else None
        if request:
            reason, version = str(request.reason or ""), noted_version or str(request.version_id or "")
        elif marker == "DIRECT-ACCESS":
            reason, version = "Direct access (no request needed)", noted_version
        elif marker:
            reason, version = "Download without a request", noted_version
        else:
            reason, version = note, noted_version
        entries[str(row.entity_id)].append({
            "id": row.name,
            "employee": full_names.get(str(row.actor)) or row.actor,
            "at": str(row.at or ""),
            "reason": reason,
            "version": version,
        })
    return entries


def _audit_marker(row) -> str:
    """What the note of an audit row names after "Original" or "Watermarked": the access request, or "MANAGER-PREVIEW"
    (a download of the Manager without a request; in rows older than the distinction, any download without one) or
    "DIRECT-ACCESS"; empty for a note of another shape."""

    parts = str(row.reason or "").strip().split(" ")
    return parts[1] if len(parts) > 1 and parts[0] in {"Original", "Watermarked"} else ""


def _download_audit(document, user: str, role: str) -> list[dict[str, Any]]:
    """The downloads of one document the user may see (see _download_audits)."""

    return _download_audits([document], user, role).get(document.document_id, [])


def list_controlled_documents() -> list[dict[str, Any]]:
    assert_capability("account:view")
    user = str(frappe.session.user)
    role = resolve_crm_role(user)
    items: list[dict[str, Any]] = []
    names = frappe.get_all(
        "CRM Controlled Document",
        filters={"status": "Released"},
        pluck="name",
        order_by="product asc, modified desc",
    )
    documents = [frappe.get_doc("CRM Controlled Document", name) for name in names]
    audits = _download_audits(documents, user, role)
    for document in documents:
        request = latest_request(document.name, user)
        approved = bool(request and request.version_id == version_id(document) and request.status == "Approved")
        direct = document.access_mode == "Direct"
        has_preview = bool(document.preview_file)
        items.append({
            "id": document.document_id,
            "versionId": version_id(document),
            "title": document.title,
            "category": document.category,
            "type": document.document_type,
            "product": document.product,
            "version": document.version,
            "revision": document.revision,
            "status": document.status,
            "confidentiality": document.confidentiality,
            "access": document.access_mode,
            "reviewDate": str(document.review_date or ""),
            "owner": document.document_owner,
            "fileName": document.file_name,
            "mimeType": document.mime_type or "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "size": int(document.size_bytes or 0),
            "hasPreview": has_preview,
            "canPreview": has_preview and (direct or role == "Manager" or approved),
            "canDownload": direct or role == "Manager" or approved,
            "deliveryMode": "Original" if direct or role == "Manager" else request.delivery_mode if approved else "",
            "accessRequest": serialize_request(request) if request else None,
            "versions": [{
                "version": document.version,
                "revision": document.revision,
                "status": document.status,
                "releasedAt": str(document.creation or ""),
                "checksum": document.content_hash,
            }],
            "audit": audits.get(document.document_id, []),
            "applicableTool": document.applicable_tool or "",
        })
    return items


def request_controlled_document_access(version_id_value: Any, reason: Any) -> dict[str, Any]:
    return create_request(version_id_value, reason)
