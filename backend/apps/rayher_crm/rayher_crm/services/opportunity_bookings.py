"""Bookings that come from an Opportunity: PO confirmation and approved internal validation."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.bookings import _booking_owner, _nonnegative_money, _positive_quantity, _validate_contact
from rayher_crm.services.common import optional_date, required_text
from rayher_crm.services.money import as_decimal, decimal_string
from rayher_crm.services.notifications import create_notification


def booking_type_for(opportunity) -> str:
    return "Service" if opportunity.sale_type == "Service" else "Equipment"


def validate_booking_draft(opportunity, draft: Any) -> dict[str, Any]:
    """Validate the Booking fields Sales enters for an Opportunity.

    Account, source, source Opportunity and type always follow the Opportunity, so the
    draft only carries the fields Sales fills in.
    """

    if not isinstance(draft, dict):
        raise CrmApiException("VALIDATION_ERROR", "booking is required.", field_errors={"booking": "Required"})
    contact_id = required_text(draft, "primaryContactId")
    _validate_contact(contact_id, opportunity.account)
    ddl = optional_date(draft.get("ddl"), "ddl")
    if not ddl:
        raise CrmApiException("VALIDATION_ERROR", "ddl is required.", field_errors={"ddl": "Required"})
    currency = required_text(draft, "currency").upper()
    if not frappe.db.exists("Currency", currency):
        raise CrmApiException("VALIDATION_ERROR", "currency is invalid.", field_errors={"currency": "Invalid value"})
    return {
        "primaryContactId": contact_id,
        "equipment": required_text(draft, "equipment"),
        "quantity": _positive_quantity(draft.get("quantity")),
        "ddl": ddl,
        "amount": decimal_string(_nonnegative_money(draft.get("amount"))),
        "currency": currency,
        "owner": _booking_owner(draft.get("owner")),
        "note": str(draft.get("note") or "").strip(),
    }


def live_booking(opportunity_id: str, *, for_update: bool = False):
    """The Opportunity's Booking that is not Cancelled: Pending, Confirmed or Completed."""

    lock = " FOR UPDATE" if for_update else ""
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Booking` WHERE `live_source_opportunity` = %s{lock}",
        (opportunity_id,),
    )
    return frappe.get_doc("CRM Booking", rows[0][0]) if rows else None


def booking_amount(booking_id: str) -> str:
    rows = frappe.db.sql("SELECT CAST(`amount` AS CHAR) FROM `tabCRM Booking` WHERE `name` = %s", (booking_id,))
    return decimal_string(rows[0][0] if rows else 0)


def _apply_draft(booking, values: dict[str, Any]) -> None:
    booking.primary_contact = values["primaryContactId"]
    booking.equipment = values["equipment"]
    booking.quantity = values["quantity"]
    booking.ddl = values["ddl"]
    booking.amount = as_decimal(values["amount"])
    booking.currency = values["currency"]
    booking.booking_owner = values["owner"]
    booking.note = values["note"]


def create_opportunity_booking(opportunity, values: dict[str, Any], status: str):
    booking = frappe.get_doc({
        "doctype": "CRM Booking",
        "booking_date": frappe.utils.today(),
        "account": opportunity.account,
        "status": status,
        "source": "Opportunity",
        "booking_type": booking_type_for(opportunity),
        "source_opportunity": opportunity.name,
        "live_source_opportunity": opportunity.name,
    })
    _apply_draft(booking, values)
    try:
        booking.insert(ignore_permissions=True)
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        raise CrmApiException("CONFLICT", "The Opportunity already has a live Booking.") from exc
    _notify_owner(booking, "Booking assigned", f"You are now responsible for {booking.equipment}.")
    return booking


def confirm_pending_booking(booking, values: dict[str, Any]):
    """Confirm the Pending Booking an approved internal validation created, using the PO's details."""

    _apply_draft(booking, values)
    booking.status = "Confirmed"
    booking.save(ignore_permissions=True)
    _notify_owner(booking, "Booking confirmed", f"{booking.equipment} is confirmed.")
    return booking


def _notify_owner(booking, title: str, message: str) -> None:
    if booking.booking_owner == frappe.session.user:
        return
    create_notification(
        recipient=booking.booking_owner, category="Booking", title=title, message=message,
        route=f"/booking/{booking.name}", source_doctype="CRM Booking", source_name=booking.name,
    )
