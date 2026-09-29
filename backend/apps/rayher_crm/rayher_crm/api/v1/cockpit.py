"""Custom business endpoints for the Manager Review cockpit and the Opportunities board."""
import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import cockpit, cockpit_settings, opportunity_board, warning_handling


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_review(**query):
    return success_response(cockpit.get_review(query))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_details(**query):
    return success_response(cockpit.get_details(query))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_warnings(**query):
    return success_response(cockpit.get_warnings(query))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_plan(**query):
    return success_response(cockpit.get_plan(query))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_plan_details(**query):
    return success_response(cockpit.get_plan_details(query))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_target(input, expectedModified=None):
    return success_response(cockpit.save_target(input, expectedModified))


# Warnings handling: a next step on any overdue / quotation / S6 row; a recorded action on S6 rows only.
@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_warning_plan(input=None, expectedModified=None):
    return success_response(warning_handling.save_plan(input, expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def record_warning_action(input=None, expectedModified=None):
    return success_response(warning_handling.record_action(input, expectedModified))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_cockpit_settings(**query):
    return success_response(cockpit_settings.get_settings())


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_cockpit_settings(input=None, expectedModified=None):
    return success_response(cockpit_settings.save_settings(input, expectedModified))


# Opportunities board: every CRM role with deal:view, within its own Opportunity row scope.
@frappe.whitelist(methods=["POST"])
@api_endpoint
def query_opportunities(input=None):
    data, total, page, page_size = opportunity_board.query_opportunities(input)
    return success_response(data, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_opportunity_filters(**query):
    return success_response(opportunity_board.get_opportunity_filters())


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_opportunity_queries(**query):
    return success_response(opportunity_board.list_opportunity_queries())


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_opportunity_query(input=None, id=None, expectedModified=None):
    return success_response(opportunity_board.save_opportunity_query(id, input, expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def delete_opportunity_query(id=None, expectedModified=None):
    return success_response(opportunity_board.delete_opportunity_query(id, expectedModified))
