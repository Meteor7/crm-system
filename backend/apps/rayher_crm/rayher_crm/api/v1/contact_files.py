"""Multipart Contact File metadata and authorized raw-download endpoints."""

from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import contact_files


def _read_uploads(request_files) -> list[dict]:
    if not request_files or len(request_files) > contact_files.MAX_FILES_PER_REQUEST:
        raise CrmApiException("VALIDATION_ERROR", "Upload must contain between 1 and 10 files.")

    uploads = []
    total_bytes = 0
    for item in request_files:
        remaining_bytes = contact_files.MAX_REQUEST_BYTES - total_bytes
        read_limit = min(contact_files.MAX_FILE_BYTES + 1, remaining_bytes + 1)
        content = item.stream.read(read_limit)
        if len(content) > contact_files.MAX_FILE_BYTES:
            raise CrmApiException("VALIDATION_ERROR", "A file exceeds the 100 MiB file limit.")
        total_bytes += len(content)
        if total_bytes > contact_files.MAX_REQUEST_BYTES:
            raise CrmApiException("VALIDATION_ERROR", "Upload exceeds the 100 MiB request limit.")
        uploads.append({"file_name": item.filename, "mime_type": item.mimetype, "content": content})
    return uploads


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_files(contactId: str, **query) -> dict:
    items, total, page, page_size = contact_files.list_contact_files(contactId, query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def upload_files(contactId: str) -> dict:
    request_files = frappe.request.files.getlist("files")
    uploads = _read_uploads(request_files)
    return success_response(contact_files.upload_contact_files(contactId, uploads))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_file(fileId: str):
    item = contact_files.download_contact_file(fileId)
    frappe.local.response.filename = item["file_name"]
    frappe.local.response.filecontent = item["content"]
    frappe.local.response.type = "download"
    frappe.local.response.content_type = item["mime_type"]
    frappe.local.response.private_file_delivery = True


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_file(fileId: str) -> dict:
    return success_response(contact_files.delete_contact_file(fileId))
