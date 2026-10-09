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
    data: dict = {"items": items}
    # Asked for by the Booking page: read in the same request as the page, so both describe the same moment.
    if str(query.get("summary") or "").strip().lower() in {"1", "true"}:
        data["summary"] = bookings.booking_summary(query)
    return success_response(data, page=page, pageSize=page_size, total=total)


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


@frappe.whitelist(methods=["POST"])
@api_endpoint
def archive_booking(id: str) -> dict:
    return success_response(bookings.archive_booking(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def unarchive_booking(id: str) -> dict:
    return success_response(bookings.unarchive_booking(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def set_actual_po_date(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(bookings.set_booking_actual_po_date(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def set_amount_cny(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(bookings.set_booking_amount_cny(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def complete_service_booking(id: str, expectedModified: str | None = None) -> dict:
    return success_response(bookings.complete_service_booking(id, expectedModified))
