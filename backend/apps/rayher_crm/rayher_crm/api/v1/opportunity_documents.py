import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services.common import as_payload
from rayher_crm.services import opportunity_documents


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_documents(opportunityId: str):
    return success_response(opportunity_documents.get_documents(opportunityId))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_links(opportunityId: str, input, expectedModified=None):
    return success_response(opportunity_documents.save_links(opportunityId, as_payload(input), expectedModified))
