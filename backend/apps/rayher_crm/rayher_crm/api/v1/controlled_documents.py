"""Authorized raw endpoints for watermarked controlled documents."""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.services.controlled_documents import render_controlled_document


def _set_file_response(item: dict, disposition: str) -> None:
    frappe.local.response.filename = item["file_name"]
    frappe.local.response.filecontent = item["content"]
    frappe.local.response.type = "download"
    frappe.local.response.content_type = item["mime_type"]
    frappe.local.response.display_content_as = disposition
    frappe.local.response.controlled_document_delivery = True


@frappe.whitelist(methods=["GET"])
@api_endpoint
def preview_document(documentId: str):
    _set_file_response(render_controlled_document(documentId, "preview"), "inline")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_document(documentId: str):
    _set_file_response(render_controlled_document(documentId, "download"), "attachment")


_FALLBACK_UNSAFE = '"%/' + chr(92)


def _ascii_fallback(file_name: str) -> str:
    # NFKD keeps the base letter of an accented one (é -> e). Anything else
    # outside printable ASCII becomes `_`, and so do quotes, slashes (NFKD turns
    # a fullwidth one into `/`), backslashes and `%`: RFC 6266 appendix D, a
    # client may percent-decode the plain parameter.
    decomposed = "".join(
        ch for ch in unicodedata.normalize("NFKD", file_name) if not unicodedata.combining(ch)
    )
    return "".join(ch if 32 <= ord(ch) < 127 and ch not in _FALLBACK_UNSAFE else "_" for ch in decomposed)


def _content_disposition(disposition: str, file_name: str) -> str:
    # Frappe's own header carries the name as raw bytes, which the browser's fetch
    # reads back one Latin-1 character per byte: a name outside ASCII arrived
    # garbled. RFC 6266: an ASCII fallback for every client, plus the RFC 5987
    # `filename*` form whenever the fallback had to change the name.
    fallback = _ascii_fallback(file_name)
    header = f'{disposition}; filename="{fallback}"'
    if fallback != file_name:
        header += f"; filename*=UTF-8''{quote(file_name, safe='')}"
    return header


def apply_delivery_headers(response, request=None) -> None:
    del request
    if not (
        getattr(frappe.local.response, "controlled_document_delivery", False)
        or getattr(frappe.local.response, "private_file_delivery", False)
    ):
        return
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    file_name = getattr(frappe.local.response, "filename", None)
    if file_name:
        response.headers["Content-Disposition"] = _content_disposition(
            getattr(frappe.local.response, "display_content_as", None) or "attachment", str(file_name),
        )
