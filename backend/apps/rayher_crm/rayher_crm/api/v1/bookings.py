"""Whitelisted Booking endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import bookings
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_bookings(**query) -> dict:
    items, total, page, page_size = bookings.list_bookings(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_booking(id: str) -> dict:
    return success_response(bookings.get_booking(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_booking(input: Any) -> dict:
    return success_response(bookings.create_booking(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_booking(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(bookings.update_booking(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_booking(id: str) -> dict:
    return success_response(bookings.delete_booking(id))
@frappe.whitelist(methods=["POST"])
@api_endpoint
def complete_service_booking(id: str, expectedModified: str | None = None) -> dict:
    return success_response(bookings.complete_service_booking(id, expectedModified))
