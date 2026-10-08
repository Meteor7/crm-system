import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import territory_admin


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_catalogue():
    return success_response(territory_admin.catalogue())


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_territory(input=None, name=None, expectedModified=None):
    return success_response(territory_admin.save_territory(input, name, expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_assignment(input=None, name=None, expectedModified=None):
    return success_response(territory_admin.save_assignment(input, name, expectedModified))
