"""Whitelisted CRM Quotation endpoints."""
from __future__ import annotations
from typing import Any
import frappe
from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import quotations
from rayher_crm.services.common import as_payload

@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_quotations(**query) -> dict:
    items, total, page, page_size = quotations.list_quotations(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)

@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_catalog() -> dict:
    return success_response(quotations.list_catalog())

@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_quotation(id: str, versionId: str | None = None) -> dict:
    return success_response(quotations.get_quotation(id, versionId))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_quotation(input: Any) -> dict:
    return success_response(quotations.create_quotation(as_payload(input)))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def link_opportunity(id: str, opportunityId: str, expectedModified: str) -> dict:
    return success_response(quotations.link_quotation_opportunity(id, opportunityId, expectedModified))

@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def save_draft(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(quotations.save_draft(id, as_payload(input), expectedModified))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_version(id: str) -> dict:
    return success_response(quotations.create_version(id))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def discard_draft(id: str, expectedModified: str | None = None) -> dict:
    return success_response(quotations.discard_draft(id, expectedModified))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def publish_version(id: str, expectedModified: str | None = None) -> dict:
    return success_response(quotations.publish_version(id, expectedModified))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def submit_for_approval(id: str, expectedModified: str | None = None) -> dict:
    return success_response(quotations.submit_for_approval(id, expectedModified))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_approval(id: str, decision: str, comment: str = "", expectedModified: str | None = None) -> dict:
    return success_response(quotations.review_approval(id, decision, comment, expectedModified))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def record_decision(id: str, decision: str, feedbackDate: str, feedbackNote: str, expectedModified: str | None = None) -> dict:
    return success_response(quotations.record_decision(id, decision, feedbackDate, feedbackNote, expectedModified))

@frappe.whitelist(methods=["GET"])
@api_endpoint
def preview_pdf(id: str, versionId: str | None = None):
    filename, content = quotations.get_preview_pdf(id, versionId)
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.private_file_delivery = True

@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_pdf(id: str, versionId: str | None = None):
    filename, content = quotations.get_pdf_file(id, versionId)
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.private_file_delivery = True
