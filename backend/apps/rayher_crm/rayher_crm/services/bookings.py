"""Lightweight CRM Booking services."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.accounts import _require_account
from rayher_crm.services.common import (
    delete_manager_scoped_document,
    ensure_server_generated_id,
    normalize_pagination,
    optional_date,
    required_text,
    resolve_write_owner,
    to_iso_timestamp,
    validate_choice,
)
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.notifications import create_notification
from rayher_crm.services.contacts import _contact_account
from rayher_crm.services.money import MoneyValidationError, as_decimal, decimal_string


BOOKING_STATUSES = {"Confirmed", "Pending", "Completed", "Cancelled"}
BOOKING_SOURCES = {"Opportunity", "Upsell"}
BOOKING_TYPES = {"Equipment", "Service"}


def delete_booking(name: str) -> dict[str, str]:
    return delete_manager_scoped_document("CRM Booking", name, "deal:write", "BOOKING_NOT_FOUND")


def _nonnegative_money(value: Any):
    try:
        return as_decimal(value)
    except MoneyValidationError as exc:
        raise CrmApiException("VALIDATION_ERROR", "amount must be non-negative with at most two decimal places.") from exc


def _positive_quantity(value: Any) -> int:
    if isinstance(value, bool):
        raise CrmApiException("VALIDATION_ERROR", "quantity must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "quantity must be a positive integer.") from exc
    if str(value).strip() != str(parsed) or parsed < 1:
        raise CrmApiException("VALIDATION_ERROR", "quantity must be a positive integer.")
    return parsed


def _booking_owner(value: Any) -> str:
    owner = resolve_write_owner(value)
    if resolve_crm_role(owner) != "Sales":
        raise CrmApiException("INVALID_OWNER", "Booking owner must be an active CRM Sales user.")
    return owner


def _validate_contact(contact_id: str, account_id: str) -> None:
    if not frappe.db.exists("Contact", contact_id):
        raise CrmApiException("CONTACT_NOT_FOUND", "Contact was not found.")
    if _contact_account(contact_id) != account_id:
        raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "The contact belongs to another account.")
    if frappe.db.get_value("Contact", contact_id, "custom_crm_status") != "Active":
        raise CrmApiException("CONTACT_INACTIVE", "The contact must be active.")


def _validate_source(account_id: str, source: str, source_opportunity: str, booking_id: str | None = None) -> str | None:
    if source == "Upsell":
        if source_opportunity:
            raise CrmApiException("BOOKING_SOURCE_INVALID", "Upsell Booking must not reference an Opportunity.")
        return None
    if not source_opportunity:
        raise CrmApiException("BOOKING_SOURCE_REQUIRED", "Opportunity Booking requires a Won Opportunity.")
    opportunity = frappe.db.get_value(
        "CRM Opportunity", source_opportunity, ["account", "stage"], as_dict=True
    )
    if not opportunity or opportunity.account != account_id or opportunity.stage != "Won":
        raise CrmApiException("BOOKING_SOURCE_INVALID", "Source Opportunity must be Won and belong to the Account.")
    duplicate = frappe.db.sql(
        """SELECT `name` FROM `tabCRM Booking`
        WHERE `source_opportunity` = %s AND `status` != 'Cancelled' AND (%s IS NULL OR `name` != %s)
        LIMIT 1""",
        (source_opportunity, booking_id, booking_id),
    )
    if duplicate:
        raise CrmApiException("BOOKING_ALREADY_EXISTS", "The Won Opportunity already has a live Booking.")
    return source_opportunity


def _validate_booking(payload: dict[str, Any], booking_id: str | None = None) -> dict[str, Any]:
    account_id = required_text(payload, "accountId")
    _require_account(account_id)
    contact_id = required_text(payload, "primaryContactId")
    _validate_contact(contact_id, account_id)
    status = validate_choice(payload.get("status"), "status", BOOKING_STATUSES)
    if status == "Completed":
        raise CrmApiException("BOOKING_STATUS_INVALID", "Completed is only set by Installed Tool conversion.")
    source = validate_choice(payload.get("source"), "source", BOOKING_SOURCES)
    source_opportunity = _validate_source(
        account_id, source, str(payload.get("sourceOpportunityId") or "").strip(), booking_id
    )
    if source == "Opportunity":
        sale_type = frappe.db.get_value("CRM Opportunity", source_opportunity, "sale_type")
        booking_type = "Service" if sale_type == "Service" else "Equipment"
    else:
        booking_type = validate_choice(payload.get("bookingType") or "Equipment", "bookingType", BOOKING_TYPES)
    ddl = optional_date(payload.get("ddl"), "ddl")
    if not ddl:
        raise CrmApiException("VALIDATION_ERROR", "ddl is required.", field_errors={"ddl": "Required"})
    currency = required_text(payload, "currency").upper()
    if not frappe.db.exists("Currency", currency):
        raise CrmApiException("VALIDATION_ERROR", "currency is invalid.", field_errors={"currency": "Invalid value"})
    return {
        "account": account_id,
        "primary_contact": contact_id,
        "equipment": required_text(payload, "equipment"),
        "quantity": _positive_quantity(payload.get("quantity")),
        "ddl": ddl,
        "amount": _nonnegative_money(payload.get("amount")),
        "currency": currency,
        "status": status,
        "booking_owner": _booking_owner(payload.get("owner")),
        "source": source,
        "booking_type": booking_type,
        "source_opportunity": source_opportunity,
        "live_source_opportunity": source_opportunity if source_opportunity and status != "Cancelled" else None,
        "note": str(payload.get("note") or "").strip(),
    }


def _lock_booking_source(payload: dict[str, Any]) -> None:
    if str(payload.get("source") or "").strip() != "Opportunity":
        return
    source_opportunity = str(payload.get("sourceOpportunityId") or "").strip()
    if source_opportunity:
        frappe.db.sql("SELECT `name` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE", source_opportunity)


def serialize_booking(doc) -> dict[str, Any]:
    contact = frappe.db.get_value("Contact", doc.primary_contact, ["first_name", "last_name"], as_dict=True)
    contact_name = " ".join(part for part in ((contact.first_name if contact else ""), (contact.last_name if contact else "")) if part).strip()
    exact_amount = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR) AS `amount` FROM `tabCRM Booking` WHERE `name` = %s",
        (doc.name,), as_dict=True,
    )
    result = {
        "id": doc.name,
        "accountId": doc.account,
        "accountName": frappe.db.get_value("Customer", doc.account, "customer_name") or doc.account,
        "title": f"{doc.equipment} · {int(doc.quantity or 0)} 台",
        "primaryContactId": doc.primary_contact,
        "customerContact": contact_name or doc.primary_contact,
        "equipment": doc.equipment,
        "quantity": int(doc.quantity or 0),
        "ddl": str(doc.ddl or ""),
        "amount": decimal_string(exact_amount[0].amount if exact_amount else doc.amount or 0),
        "currency": doc.currency,
        "status": doc.status,
        "bookingDate": str(doc.booking_date or ""),
        "owner": doc.booking_owner,
        "source": doc.source,
        "bookingType": doc.booking_type or "Equipment",
        "sourceOpportunityId": doc.source_opportunity or "",
        "note": doc.note or "",
        "modified": to_iso_timestamp(doc.modified),
    }
    if doc.installed_tool:
        result["installedToolId"] = doc.installed_tool
    if doc.installed_tool_converted_at:
        result["installedToolConvertedAt"] = to_iso_timestamp(doc.installed_tool_converted_at)
    return result


def _require_booking(name: str):
    if not frappe.db.exists("CRM Booking", name):
        raise CrmApiException("BOOKING_NOT_FOUND", "Booking was not found.")
    doc = frappe.get_doc("CRM Booking", name)
    if not frappe.has_permission("CRM Booking", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    return doc


def list_bookings(query: dict[str, Any] | None = None):
    assert_capability("deal:view")
    where_parts = [f"({conditions_for_doctype('CRM Booking')})"]
    values: list[Any] = []
    if query is None:
        where = where_parts[0]
        rows = frappe.db.sql(
            f"SELECT `name` FROM `tabCRM Booking` WHERE {where} ORDER BY `modified` DESC, `name` DESC",
            as_dict=True,
        )
        return [serialize_booking(frappe.get_doc("CRM Booking", row.name)) for row in rows]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        where_parts.append("(`name` LIKE %s OR `equipment` LIKE %s OR `account` LIKE %s)")
        values.extend([pattern, pattern, pattern])
    for input_name, column in (
        ("accountId", "account"), ("contactId", "primary_contact"),
        ("status", "status"), ("owner", "booking_owner"), ("source", "source"),
    ):
        value = str(query.get(input_name) or "").strip()
        if value and value != "All":
            where_parts.append(f"`{column}` = %s")
            values.append(value)
    date_from = str(query.get("dateFrom") or "").strip()
    date_to = str(query.get("dateTo") or "").strip()
    if date_from:
        where_parts.append("`ddl` >= %s")
        values.append(date_from)
    if date_to:
        where_parts.append("`ddl` <= %s")
        values.append(date_to)
    where = " AND ".join(where_parts)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Booking` WHERE {where}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Booking` WHERE {where} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]), as_dict=True,
    )
    return [serialize_booking(frappe.get_doc("CRM Booking", row.name)) for row in rows], total, page, page_size


def get_booking(name: str) -> dict[str, Any]:
    assert_capability("deal:view")
    return serialize_booking(_require_booking(name))


def create_booking(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:write")
    ensure_server_generated_id(payload)
    _lock_booking_source(payload)
    values = _validate_booking(payload)
    savepoint = f"crm_booking_create_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc = frappe.get_doc({
            "doctype": "CRM Booking", "booking_date": frappe.utils.today(), **values,
        }).insert(ignore_permissions=True)
        if doc.booking_owner != frappe.session.user:
            create_notification(
                recipient=doc.booking_owner, category="Booking", title="Booking assigned",
                message=f"You are now responsible for {doc.equipment}.",
                route=f"/booking/{doc.name}", source_doctype="CRM Booking", source_name=doc.name,
            )
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("CONFLICT", "The Won Opportunity already has a live Booking.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_booking(doc)


def _current_input(doc) -> dict[str, Any]:
    exact_amount = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR) FROM `tabCRM Booking` WHERE `name` = %s",
        (doc.name,),
    )[0][0]
    return {
        "accountId": doc.account, "primaryContactId": doc.primary_contact,
        "equipment": doc.equipment, "quantity": doc.quantity, "ddl": str(doc.ddl or ""),
        "amount": exact_amount, "currency": doc.currency or "CNY", "status": doc.status, "owner": doc.booking_owner,
        "source": doc.source, "bookingType": doc.booking_type or "Equipment", "sourceOpportunityId": doc.source_opportunity or "", "note": doc.note or "",
    }


def update_booking(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    current = _require_booking(name)
    if current.installed_tool or current.status == "Completed":
        raise CrmApiException("BOOKING_LOCKED", "Converted Booking cannot be edited.")
    doc = lock_document("CRM Booking", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Booking", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    if doc.installed_tool or doc.status == "Completed":
        raise CrmApiException("BOOKING_LOCKED", "Converted Booking cannot be edited.")
    merged = _current_input(doc)
    merged.update(payload)
    previous_owner = doc.booking_owner
    savepoint = f"crm_booking_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    for fieldname, value in _validate_booking(merged, name).items():
        setattr(doc, fieldname, value)
    try:
        doc.save(ignore_permissions=True)
        if previous_owner != doc.booking_owner and doc.booking_owner != frappe.session.user:
            create_notification(
                recipient=doc.booking_owner, category="Booking", title="Booking reassigned",
                message=f"You are now responsible for {doc.equipment}.",
                route=f"/booking/{doc.name}", source_doctype="CRM Booking", source_name=doc.name,
            )
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("CONFLICT", "The Won Opportunity already has a live Booking.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_booking(doc)
def complete_service_booking(name: str, expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    current = _require_booking(name)
    if (current.booking_type or "Equipment") != "Service":
        raise CrmApiException("BOOKING_TYPE_INVALID", "Only Service Booking can be completed as a service.")
    if current.installed_tool or current.status == "Completed":
        raise CrmApiException("BOOKING_ALREADY_COMPLETED", "Booking was already completed.")
    if current.status != "Confirmed":
        raise CrmApiException("BOOKING_NOT_CONFIRMED", "Only Confirmed Service Booking can be completed.")

    doc = lock_document("CRM Booking", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Booking", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    if (doc.booking_type or "Equipment") != "Service":
        raise CrmApiException("BOOKING_TYPE_INVALID", "Only Service Booking can be completed as a service.")
    if doc.installed_tool or doc.status == "Completed":
        raise CrmApiException("BOOKING_ALREADY_COMPLETED", "Booking was already completed.")
    if doc.status != "Confirmed":
        raise CrmApiException("BOOKING_NOT_CONFIRMED", "Only Confirmed Service Booking can be completed.")
    doc.status = "Completed"
    doc.save(ignore_permissions=True)
    doc.reload()
    return serialize_booking(doc)
