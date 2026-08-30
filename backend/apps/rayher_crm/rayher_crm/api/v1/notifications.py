"""Recipient-scoped persistent notification endpoints."""

from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import notifications


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_notifications(page=None, pageSize=None, unreadOnly=None) -> dict:
    result = notifications.list_notifications(page, pageSize, unreadOnly)
    return success_response(
        result["items"], page=result["page"], pageSize=result["pageSize"], total=result["total"],
    )


@frappe.whitelist(methods=["POST"])
@api_endpoint
def mark_notification_read(id: str) -> dict:
    return success_response(notifications.mark_notification_read(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def mark_all_notifications_read() -> dict:
    return success_response(notifications.mark_all_notifications_read())
