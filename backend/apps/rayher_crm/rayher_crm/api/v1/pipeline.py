"""Whitelisted Pipeline projection endpoint."""

from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services.pipeline import list_pipeline as project_pipeline


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_pipeline(**query) -> dict:
    return success_response(project_pipeline(query))
