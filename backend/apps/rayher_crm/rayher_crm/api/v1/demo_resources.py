"""Service-owned resource catalogue and Evaluation arrangements."""
from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import demo_resources as service


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_demo_resources():
    return success_response(service.get_catalogue())


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_demo_unavailability(resourceId: str):
    return success_response(service.get_unavailability(resourceId))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_demo_resource(input: Any, id: str | None = None, expectedModified: str | None = None):
    return success_response(service.save_resource(input, id, expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_demo_unavailability(resourceId: str, input: Any, id: str | None = None, expectedModified: str | None = None):
    return success_response(service.save_unavailability(resourceId, input, id, expectedModified))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_demo_resource_schedule(evaluationId: str):
    return success_response(service.get_schedule(evaluationId))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_demo_resource_schedule(evaluationId: str, input: Any, expectedModified: str):
    return success_response(service.save_schedule(evaluationId, input, expectedModified))
