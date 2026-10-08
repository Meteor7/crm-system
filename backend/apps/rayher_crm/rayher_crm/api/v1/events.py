import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import events


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_events(page=None, pageSize=None, search=None):
    rows, total, page, size = events.list_events({"page": page, "pageSize": pageSize, "search": search})
    return success_response({"items": rows}, total=total, page=page, pageSize=size)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_event(id=None):
    return success_response(events.get_event(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_event(input=None, id=None, expectedModified=None):
    return success_response(events.save_event(input, id, expectedModified))
