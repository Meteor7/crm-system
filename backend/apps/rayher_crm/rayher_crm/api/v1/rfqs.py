"""Whitelisted RFQ workflow and private-file endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import rfqs
from rayher_crm.services.common import as_payload


def _upload_part() -> dict[str, Any]:
    uploads = frappe.request.files.getlist("file")
    if len(uploads) != 1:
        raise CrmApiException("VALIDATION_ERROR", "Exactly one RFQ file is required.")
    upload = uploads[0]
    content = upload.stream.read(rfqs.MAX_FILE_BYTES + 1)
    if len(content) > rfqs.MAX_FILE_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "File exceeds the 100 MiB limit.")
    return {"file_name": upload.filename, "mime_type": upload.mimetype, "content": content}


def _set_file_response(item: dict[str, Any], disposition: str) -> None:
    frappe.local.response.filename = item["file_name"]
    frappe.local.response.filecontent = item["content"]
    frappe.local.response.type = "download"
    frappe.local.response.content_type = item["mime_type"]
    frappe.local.response.display_content_as = disposition
    frappe.local.response.private_file_delivery = True


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_rfqs(**query) -> dict:
    items, total, page, page_size = rfqs.list_rfqs(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_rfq(id: str) -> dict:
    return success_response(rfqs.get_rfq(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_rfq(opportunityId: str, engineerId: str, note: str = "") -> dict:
    return success_response(rfqs.create_rfq(
        {"opportunityId": opportunityId, "engineerId": engineerId, "note": note}, _upload_part(),
    ))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def revise_rfq(id: str, expectedModified: str) -> dict:
    return success_response(rfqs.revise_rfq(id, _upload_part(), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def submit_engineer_comment(id: str, input: Any, expectedModified: str) -> dict:
    payload = as_payload(input)
    return success_response(rfqs.submit_engineer_comment(id, payload.get("comment"), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_rfq(id: str, input: Any, expectedModified: str) -> dict:
    payload = as_payload(input)
    return success_response(rfqs.review_rfq(id, payload.get("decision"), payload.get("comment"), expectedModified))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def preview_rfq_file(id: str, versionId: str | None = None):
    _set_file_response(rfqs.preview_rfq_file(id, versionId), "inline")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_rfq_file(id: str, versionId: str | None = None):
    _set_file_response(rfqs.download_rfq_file(id, versionId), "attachment")
