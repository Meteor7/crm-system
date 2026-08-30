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
    for name in names:
        document = frappe.get_doc("CRM Controlled Document", name)
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
            "audit": [],
            "applicableTool": document.applicable_tool or "",
        })
    return items


def request_controlled_document_access(version_id_value: Any, reason: Any) -> dict[str, Any]:
    return create_request(version_id_value, reason)
