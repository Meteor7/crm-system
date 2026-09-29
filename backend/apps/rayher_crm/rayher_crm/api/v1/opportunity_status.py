"""Status endpoints: scope-checked notes and multipart private attachments."""
import frappe

from rayher_crm.api.v1.contact_files import _read_uploads
from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import opportunity_status
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_records(opportunityId: str):
    return success_response(opportunity_status.list_records(opportunityId))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_record(opportunityId: str, input):
    files = frappe.request.files.getlist("files")
    return success_response(opportunity_status.save_record(opportunityId, as_payload(input), _read_uploads(files) if files else []))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_file(opportunityId: str, recordId: str, fileId: str):
    item = opportunity_status.download_file(opportunityId, recordId, fileId)
    frappe.local.response.filename = item["file_name"]
    frappe.local.response.filecontent = item["content"]
    frappe.local.response.type = "download"
    frappe.local.response.content_type = item["mime_type"]
    frappe.local.response.private_file_delivery = True
