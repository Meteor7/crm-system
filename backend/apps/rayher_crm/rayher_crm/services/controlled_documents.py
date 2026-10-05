"""Approved delivery of watermarked PDF previews or original PPTX files."""

from __future__ import annotations

import hashlib
import html
import io
import re
import uuid
from typing import Any, Literal

import frappe
from frappe.utils import now_datetime
from frappe.utils.pdf import get_pdf
from pypdf import PdfReader, PdfWriter

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.document_access import authorized_request


PDF_MIME = "application/pdf"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MAX_CONTROLLED_FILE_BYTES = 100 * 1024 * 1024
_FILE_STEM = re.compile(r"[^A-Za-z0-9._-]+")


def _action_name(action: Literal["preview", "download"]) -> str:
    if action == "preview":
        return "Preview"
    if action == "download":
        return "Download"
    raise CrmApiException("VALIDATION_ERROR", "Unknown controlled-document action.")


def _access_id() -> str:
    return f"DL-{uuid.uuid4().hex[:20].upper()}"


def _audit(document_id: str, action: str, outcome: str, access_id: str, reason: str = "") -> None:
    actor = str(getattr(frappe.session, "user", "") or "Guest")
    frappe.get_doc({
        "doctype": "CRM File Access Audit",
        "entity_type": "Controlled Document",
        "entity_id": str(document_id or "unknown")[:140],
        "actor": actor,
        "action": action,
        "outcome": outcome,
        "reason": reason[:140],
        "at": now_datetime(),
        "access_id": access_id,
        "request_id": str(getattr(frappe.local, "request_id", "") or "")[:140],
    }).insert(ignore_permissions=True)
    frappe.local.flags.commit = True


def _denied(document_id: str, action: str, access_id: str, reason: str, error: Exception) -> None:
    _audit(document_id, action, "Denied", access_id, reason)
    raise error


def _authorized_document(document_id: str, action: str, access_id: str):
    try:
        assert_capability("account:view")
    except frappe.PermissionError as error:
        _denied(document_id, action, access_id, "permission denied", error)

    if not frappe.db.exists("CRM Controlled Document", document_id):
        _denied(
            document_id,
            action,
            access_id,
            "document not found",
            CrmApiException("NOT_FOUND", "The controlled document is unavailable."),
        )
    document = frappe.get_doc("CRM Controlled Document", document_id)
    if document.status != "Released":
        _denied(
            document_id,
            action,
            access_id,
            "document not released for approved access",
            CrmApiException("PERMISSION_DENIED", "The controlled document is not available for approved access."),
        )
    if document.access_mode == "Direct":
        request, delivery_mode = None, "Original"
    else:
        try:
            request, delivery_mode = authorized_request(document, action)
        except Exception as error:
            _denied(document_id, action, access_id, "approved access required", error)
    return document, request, delivery_mode


def _verified_file(
    document,
    field_name: str,
    hash_field: str,
    expected_prefix: bytes | None,
    action: str,
    access_id: str,
) -> bytes:
    linked_file = document.get(field_name)
    if not linked_file or not frappe.db.exists("File", linked_file):
        _denied(
            document.document_id,
            action,
            access_id,
            "file unavailable",
            CrmApiException("NOT_FOUND", "The controlled document is unavailable."),
        )
    file_doc = frappe.get_doc("File", linked_file)
    association_ok = (
        bool(file_doc.is_private)
        and file_doc.attached_to_doctype == "CRM Controlled Document"
        and file_doc.attached_to_name == document.name
    )
    if not association_ok:
        _denied(
            document.document_id,
            action,
            access_id,
            "file association invalid",
            CrmApiException("NOT_FOUND", "The controlled document is unavailable."),
        )
    from rayher_crm.services.managed_file_access import authorize_controlled_file_read
    authorize_controlled_file_read(file_doc)
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    content = bytes(content)
    valid = (
        0 < len(content) <= MAX_CONTROLLED_FILE_BYTES
        and (expected_prefix is None or content.startswith(expected_prefix))
        and hashlib.sha256(content).hexdigest() == document.get(hash_field)
    )
    if not valid:
        _denied(
            document.document_id,
            action,
            access_id,
            "file integrity invalid",
            CrmApiException("NOT_FOUND", "The controlled document is unavailable."),
        )
    return content


def _watermark_html(text: str, width_mm: float, height_mm: float) -> str:
    escaped = html.escape(text)
    width_units = width_mm * 10
    height_units = height_mm * 10
    marks = "".join(
        f"<text x='{x:.1f}' y='{y:.1f}' transform='rotate(-32 {x:.1f} {y:.1f})'>{escaped}</text>"
        for x, y in (
            (-width_units * 0.08, height_units * 0.16),
            (width_units * 0.02, height_units * 0.36),
            (-width_units * 0.08, height_units * 0.56),
            (width_units * 0.02, height_units * 0.76),
            (-width_units * 0.08, height_units * 0.96),
        )
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
@page{{size:{width_mm:.3f}mm {height_mm:.3f}mm;margin:0}}
html,body{{width:{width_mm:.3f}mm;height:{height_mm:.3f}mm;margin:0;padding:0;overflow:hidden}}
.trace{{position:absolute;left:5mm;right:5mm;bottom:3mm;color:#657b80;font-family:'Noto Sans CJK SC','Noto Sans CJK TC','Noto Sans CJK JP',Arial,sans-serif;
font-size:6px;opacity:.60;white-space:nowrap}}
</style></head><body>
<svg xmlns='http://www.w3.org/2000/svg' width='{width_mm:.3f}mm' height='{height_mm:.3f}mm'
 viewBox='0 0 {width_units:.1f} {height_units:.1f}'>
<g fill='#8fa4a9' fill-opacity='.30' font-family='Noto Sans CJK SC, Noto Sans CJK TC, Noto Sans CJK JP, Arial, sans-serif' font-size='25' font-weight='600'>{marks}</g>
</svg><div class='trace'>{escaped}</div></body></html>"""


def _render_watermarked_pdf(source: bytes, watermark_text: str) -> bytes:
    reader = PdfReader(io.BytesIO(source), strict=True)
    if not reader.pages:
        raise ValueError("PDF has no pages")
    writer = PdfWriter()
    overlays: dict[tuple[int, int], Any] = {}
    for page in reader.pages:
        width_pt = float(page.mediabox.width)
        height_pt = float(page.mediabox.height)
        size_key = (round(width_pt), round(height_pt))
        overlay_page = overlays.get(size_key)
        if overlay_page is None:
            width_mm = width_pt * 25.4 / 72
            height_mm = height_pt * 25.4 / 72
            overlay_bytes = get_pdf(
                _watermark_html(watermark_text, width_mm, height_mm),
                options={
                    "page-width": f"{width_mm:.3f}mm",
                    "page-height": f"{height_mm:.3f}mm",
                    "margin-top": "0mm",
                    "margin-right": "0mm",
                    "margin-bottom": "0mm",
                    "margin-left": "0mm",
                    "encoding": "UTF-8",
                    "disable-smart-shrinking": "",
                },
            )
            overlay_page = PdfReader(io.BytesIO(overlay_bytes), strict=True).pages[0]
            overlays[size_key] = overlay_page
        page.merge_page(overlay_page, over=True)
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def render_controlled_document(
    document_id: str,
    action: Literal["preview", "download"],
) -> dict[str, Any]:
    action_name = _action_name(action)
    access_id = _access_id()
    document, approval_request, delivery_mode = _authorized_document(str(document_id or ""), action_name, access_id)
    approval_id = approval_request.name if approval_request else "MANAGER-PREVIEW"

    if action_name == "Preview" and resolve_crm_role() == "Manager":
        content = _verified_file(document, "preview_file", "preview_content_hash", b"%PDF-", action_name, access_id)
        _audit(document.document_id, action_name, "Allowed", access_id, "Clean manager preview")
        return {
            "content": content,
            "file_name": document.preview_file_name or f"{document.document_id}-Preview.pdf",
            "mime_type": PDF_MIME,
            "access_id": access_id,
        }

    if action_name == "Download" and delivery_mode == "Original":
        content = _verified_file(document, "private_file", "content_hash", None, action_name, access_id)
        _audit(document.document_id, action_name, "Allowed", access_id, f"Original {approval_id}")
        return {
            "content": content,
            "file_name": document.file_name,
            "mime_type": document.mime_type or PPTX_MIME,
            "access_id": access_id,
        }

    source = _verified_file(document, "preview_file", "preview_content_hash", b"%PDF-", action_name, access_id)
    user_id = str(frappe.session.user)
    full_name = str(frappe.db.get_value("User", user_id, "full_name") or user_id)
    generated_at = now_datetime().strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    watermark = " | ".join((full_name, user_id, document.document_id, generated_at, access_id, "CONTROLLED COPY"))
    try:
        content = _render_watermarked_pdf(source, watermark)
    except Exception as error:
        frappe.log_error(title="Controlled document watermark generation failed")
        _denied(
            document.document_id,
            action_name,
            access_id,
            "watermark generation failed",
            CrmApiException("INTERNAL_ERROR", "The controlled document could not be generated.", retryable=True),
        )
        raise error  # pragma: no cover
    stem = _FILE_STEM.sub("-", str(document.preview_file_name or document.document_id).rsplit(".", 1)[0]).strip("-._")
    file_name = f"{stem or 'Controlled-Document'}-Controlled.pdf"
    _audit(document.document_id, action_name, "Allowed", access_id, f"Watermarked {approval_id}")
    return {
        "content": content,
        "file_name": file_name,
        "mime_type": PDF_MIME,
        "access_id": access_id,
    }
