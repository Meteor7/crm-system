"""Authorized raw endpoints for watermarked controlled documents."""

from __future__ import annotations

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
