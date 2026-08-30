"""Multipart controlled-document upload and Manager approval endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import document_uploads
from rayher_crm.services.common import paginate_items


@frappe.whitelist(methods=["POST"])
@api_endpoint
def submit_upload(
    title: str, category: str, documentType: str, accessMode: str, confidentiality: str,
    product: str = "", version: str = "", revision: str = "", reviewDate: str = "",
    applicableTool: str = "",
) -> dict:
    uploads = frappe.request.files.getlist("file")
    if len(uploads) != 1:
        raise CrmApiException("VALIDATION_ERROR", "Exactly one file is required.")
    upload = uploads[0]
    content = upload.stream.read(document_uploads.MAX_FILE_BYTES + 1)
    if len(content) > document_uploads.MAX_FILE_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "File exceeds the 100 MiB limit.")
    metadata = {
        "title": title, "category": category, "documentType": documentType,
        "accessMode": accessMode, "confidentiality": confidentiality,
        "product": product, "version": version, "revision": revision,
        "reviewDate": reviewDate, "applicableTool": applicableTool,
    }
    part = {"file_name": upload.filename, "mime_type": upload.mimetype, "content": content}
    return success_response(document_uploads.submit_upload(metadata, part))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_upload_requests(**query) -> dict:
    items, total, page, page_size = paginate_items(document_uploads.list_upload_requests(), query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def decide_upload_request(requestId: str, input: Any) -> dict:
    return success_response(document_uploads.decide_upload_request(requestId, input))
