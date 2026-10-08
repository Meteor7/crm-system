import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import quotation_planning


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_planning(quotationId=None):
    return success_response(quotation_planning.get_planning(quotationId))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_schedule(quotationId=None, input=None, expectedModified=None):
    return success_response(quotation_planning.save_schedule(quotationId, input, expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_follow_up(quotationId=None, input=None, id=None, expectedModified=None):
    return success_response(quotation_planning.save_follow_up(quotationId, input, id, expectedModified))
