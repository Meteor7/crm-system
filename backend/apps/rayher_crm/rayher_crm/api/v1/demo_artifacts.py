"""Multipart Demo Artifact metadata and authorized raw-download endpoints."""

from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import demo_artifacts


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_artifacts(demoRequestId: str, **query) -> dict:
    items, total, page, page_size = demo_artifacts.list_demo_artifacts(demoRequestId, query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_artifact(
    demoRequestId: str, type: str, visibility: str, evaluationId: str | None = None,
) -> dict:
    upload = frappe.request.files.get("file")
    if upload is None:
        request_files = frappe.request.files.getlist("files")
        upload = request_files[0] if len(request_files) == 1 else None
    if upload is None:
        from rayher_crm.api.v1.errors import CrmApiException
        raise CrmApiException("VALIDATION_ERROR", "Exactly one artifact file is required.")
    part = {
        "file_name": upload.filename,
        "mime_type": upload.mimetype,
        "content": upload.stream.read(demo_artifacts.MAX_FILE_BYTES + 1),
    }
    payload = {
        "demoRequestId": demoRequestId, "evaluationId": evaluationId,
        "type": type, "visibility": visibility,
    }
    return success_response(demo_artifacts.save_demo_artifact(payload, part))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_artifact(artifactId: str):
    item = demo_artifacts.download_demo_artifact(artifactId)
    frappe.local.response.filename = item["file_name"]
    frappe.local.response.filecontent = item["content"]
    frappe.local.response.type = "download"
    frappe.local.response.content_type = item["mime_type"]
    frappe.local.response.private_file_delivery = True
