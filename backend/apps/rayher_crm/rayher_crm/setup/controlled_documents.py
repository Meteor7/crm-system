"""Manage optional controlled-document cleanup without bundling demo content."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import frappe
from frappe.utils.file_manager import save_file


LEGACY_MUSHI_DOCUMENT_ID = "DOC-MUSHI-OVERVIEW"
ACONCA_DOCUMENT_ID = "DOC-ACONCA-FSBS-EDGE"
NANSI_DOCUMENT_ID = "DOC-NANSI-0610"

# Production does not bundle default controlled documents. Documents are uploaded through
# Document Center and stored as private Frappe File records.
APPROVED_DOCUMENTS: tuple[dict[str, Any], ...] = ()


def _asset_path(file_name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "controlled_documents" / file_name


def _verified_asset(file_name: str, expected_hash: str) -> bytes:
    path = _asset_path(file_name)
    if not path.is_file():
        raise RuntimeError(f"Approved controlled-document asset is missing: {file_name}")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise RuntimeError(f"Approved controlled-document asset failed integrity check: {file_name}")
    return content


def _attach_private_file(document, field_name: str, file_name: str, content: bytes) -> None:
    existing_name = document.get(field_name)
    if existing_name and frappe.db.exists("File", existing_name):
        existing = frappe.get_doc("File", existing_name)
        existing_content = existing.get_content()
        if isinstance(existing_content, str):
            existing_content = existing_content.encode()
        if (
            bool(existing.is_private)
            and existing.attached_to_doctype == document.doctype
            and existing.attached_to_name == document.name
            and hashlib.sha256(bytes(existing_content)).digest() == hashlib.sha256(content).digest()
        ):
            return
        frappe.delete_doc("File", existing.name, ignore_permissions=True, force=True)

    file_doc = save_file(file_name, content, document.doctype, document.name, is_private=1)
    document.db_set(field_name, file_doc.name, update_modified=False)


def _retire_legacy_mushi() -> None:
    if not frappe.db.exists("CRM Controlled Document", LEGACY_MUSHI_DOCUMENT_ID):
        return
    document = frappe.get_doc("CRM Controlled Document", LEGACY_MUSHI_DOCUMENT_ID)
    attached_files = [document.get("private_file"), document.get("preview_file")]
    frappe.delete_doc("CRM Controlled Document", document.name, ignore_permissions=True, force=True)
    for file_name in attached_files:
        if file_name and frappe.db.exists("File", file_name):
            frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)


def install_approved_controlled_documents() -> None:
    """Keep legacy demo content retired; production documents are managed via uploads."""

    for spec in APPROVED_DOCUMENTS:
        source = _verified_asset(spec["file_name"], spec["content_hash"])
        preview = _verified_asset(spec["preview_file_name"], spec["preview_content_hash"])
        values = {
            "title": spec["title"],
            "category": "Technical",
            "document_type": "Product Technical Presentation",
            "product": spec["product"],
            "version": spec["version"],
            "revision": spec["revision"],
            "status": "Released",
            "confidentiality": "Restricted",
            "access_mode": "Request",
            "review_date": "2027-06-10",
            "document_owner": "Product Engineering",
            "file_name": spec["file_name"],
            "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "size_bytes": len(source),
            "content_hash": spec["content_hash"],
            "preview_file_name": spec["preview_file_name"],
            "preview_content_hash": spec["preview_content_hash"],
            "applicable_tool": spec["applicable_tool"],
        }
        if frappe.db.exists("CRM Controlled Document", spec["document_id"]):
            document = frappe.get_doc("CRM Controlled Document", spec["document_id"])
            document.update(values)
            document.save(ignore_permissions=True)
        else:
            document = frappe.get_doc({
                "doctype": "CRM Controlled Document",
                "document_id": spec["document_id"],
                **values,
            }).insert(ignore_permissions=True)
        _attach_private_file(document, "private_file", spec["file_name"], source)
        _attach_private_file(document, "preview_file", spec["preview_file_name"], preview)

    _retire_legacy_mushi()
