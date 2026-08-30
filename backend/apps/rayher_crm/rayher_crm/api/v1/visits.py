"""Whitelisted CRM Visit endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import visit_meetings, visits
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_visits(**query) -> dict:
    items, total, page, page_size = visits.list_visits(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_visit(id: str) -> dict:
    return success_response(visits.get_visit(id))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_visit_detail(id: str) -> dict:
    return success_response(visits.get_visit_detail(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_visit(input: Any) -> dict:
    return success_response(visits.create_visit(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_visit(id: str, command: Any, expectedModified: str | None = None) -> dict:
    return success_response(visits.update_visit(id, as_payload(command), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def submit_visit_record(visitId: str) -> dict:
    uploads = frappe.request.files.getlist("file")
    if len(uploads) != 1:
        raise CrmApiException("VALIDATION_ERROR", "Exactly one visit record file is required.")
    upload = uploads[0]
    content = upload.stream.read(visit_meetings.MAX_FILE_BYTES + 1)
    if len(content) > visit_meetings.MAX_FILE_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "File exceeds the 100 MiB limit.")
    visit_meetings.upload(visitId, upload.filename or "", upload.mimetype or "", content)
    return success_response(visits.get_visit_detail(visitId))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_visit(id: str, expectedModified: str | None = None) -> dict:
    return success_response(visits.review_visit(id, expectedModified))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_meeting_record(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(visit_meetings.update_record(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_attachment(fileId: str):
    item = visit_meetings.download(fileId)
    frappe.local.response.filename = item["file_name"]
    frappe.local.response.filecontent = item["content"]
    frappe.local.response.type = "download"
    frappe.local.response.content_type = item["mime_type"]
    frappe.local.response.private_file_delivery = True
