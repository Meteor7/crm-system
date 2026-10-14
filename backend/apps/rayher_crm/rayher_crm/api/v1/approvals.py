"""Authenticated pending approval projection and per-user view receipts."""

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import approvals


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_pending_approvals() -> dict:
    return success_response({"items": approvals.list_pending_approvals()})


@frappe.whitelist(methods=["POST"])
@api_endpoint
def mark_approval_viewed(id: str) -> dict:
    return success_response(approvals.mark_approval_viewed(id))
