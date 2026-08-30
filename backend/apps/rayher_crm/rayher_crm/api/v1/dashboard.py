"""Whitelisted Dashboard aggregation endpoint."""

from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services.dashboard import get_dashboard as aggregate_dashboard


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_dashboard(**query) -> dict:
    return success_response(aggregate_dashboard(query))
