"""Lightweight CRM Booking services."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.accounts import (
    ARCHIVED_ACCOUNT_EDIT,
    ARCHIVED_ACCOUNT_LINK,
    ARCHIVED_ACCOUNT_REOPEN,
    _require_account,
    account_archived,
    lock_accounts,
    require_active_account,
)
from rayher_crm.services.common import (
    archive_state,
    ensure_server_generated_id,
    normalize_pagination,
    optional_date,
    require_manager_scoped_document,
    required_text,
    resolve_write_owner,
    to_iso_timestamp,
    validate_choice,
)
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.notifications import create_notification
from rayher_crm.services.contacts import _contact_account, _require_contact
from rayher_crm.services.money import (
    MoneyValidationError,
    as_decimal,
    decimal_string,
    optional_money_text,
    required_positive_money,
)
from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_LINK, assert_opportunity_not_archived


BOOKING_STATUSES = {"Confirmed", "Pending", "Completed", "Cancelled"}
BOOKING_SOURCES = {"Opportunity", "Upsell"}
BOOKING_TYPES = {"Equipment", "Service"}
# Where the date on the customer's PO came from: entered when the PO was confirmed, typed on an
# Upsell Booking, or filled in or corrected later by a Manager.
ACTUAL_PO_DATE_SOURCES = ("po_confirmation", "booking_entry", "backfill")


def validate_actual_po_date(value: Any, *, required: bool) -> str | None:
    """The date on the customer's PO: a real calendar date that is not in the future.

    It is not the Opportunity's `po_date`, which is only the expected PO date.
    """

    actual_po_date = optional_date(value, "actualPoDate")
    if not actual_po_date:
        if required:
            raise CrmApiException(
                "VALIDATION_ERROR", "actualPoDate is required.", field_errors={"actualPoDate": "Required"},
            )
        return None
    if actual_po_date > frappe.utils.today():
        raise CrmApiException(
            "VALIDATION_ERROR", "actualPoDate cannot be in the future.",
            field_errors={"actualPoDate": "Cannot be in the future"},
        )
    return actual_po_date


def validate_booking_amount_cny(currency: str, value: Any, *, required: bool) -> Decimal:
    """The amount in CNY of a Booking in another currency; 0 means nobody has entered it.

    A CNY Booking's amount is already in CNY, so nothing is stored for it and any value sent
    is ignored. For another currency it is required once the order is confirmed.
    """

    if currency == "CNY":
        return Decimal("0")
    if value is None or str(value).strip() == "":
        if required:
            raise CrmApiException("VALIDATION_ERROR", "amountCny is required.", field_errors={"amountCny": "Required"})
        return Decimal("0")
    return required_positive_money(value, "amountCny")


def cny_amount_text(currency: Any, amount: Any, amount_cny: Any) -> str:
    """The order's amount in CNY: its amount for a CNY Booking, otherwise the entered CNY amount or ""."""

    if str(currency or "CNY").upper() == "CNY":
        return decimal_string(amount or 0)
    return optional_money_text(amount_cny)


ARCHIVED_BOOKING_EDIT = "An archived Booking cannot be changed; a Manager can restore it from the archive."
OPPORTUNITY_BOOKING_ARCHIVE = "An Opportunity Booking cannot be archived; cancel it instead."
COMPLETED_BOOKING_ARCHIVE = "A completed Booking is the record of a delivered order and cannot be archived."


def assert_booking_not_archived(doc) -> None:
    """A Booking archived (by a Manager, in place of a delete) takes no change until it is restored. Run on the
    record as first read (this transaction's snapshot), before its payload and its version are looked at, so the
    refusal names the archive whatever the client sent and whichever version it holds."""

    if doc.archived:
        raise CrmApiException("INVALID_TRANSITION", ARCHIVED_BOOKING_EDIT)


def assert_booking_not_archived_now(name: str) -> None:
    """The same, as committed now: a locking read of the flag, run after the Booking's row is held. Defence in
    depth: an archive committed after the first read moved the version, which the lock refuses already, so this
    is reached only by a caller whose version is current and whose first read was stale (a test shows the
    case); it reads the flag itself rather than relying on the version."""

    if frappe.db.get_value("CRM Booking", name, "archived", for_update=True):
        raise CrmApiException("INVALID_TRANSITION", ARCHIVED_BOOKING_EDIT)


def _set_archived(doc, archived: bool) -> None:
    """Write the three archive columns of the Booking, read under its row lock, and nothing else (no full save
    for a flag flip, and so no Version row). `modified` moves with it, so an edit, a correction, a completion
    or a conversion prepared on the record before is refused rather than written over the archive: by the
    archive check each runs on its first read, or, when the archive lands between that read and its lock, by
    its version check (`lock_document`). The archive and the restore each leave a comment on the Booking (who,
    when), which outlives the restore."""

    frappe.db.set_value("CRM Booking", doc.name, {
        "archived": 1 if archived else 0,
        "archived_at": frappe.utils.now_datetime() if archived else None,
        "archived_by": frappe.session.user if archived else None,
    })
    frappe.get_doc({
        "doctype": "Comment", "comment_type": "Info", "reference_doctype": "CRM Booking", "reference_name": doc.name,
        "content": "Archived" if archived else "Restored from the archive",
    }).insert(ignore_permissions=True)
    doc.reload()


def archive_booking(name: str) -> dict[str, Any]:
    """Archive an Upsell Booking, a Manager's action (the delete it replaces was one): the Booking leaves the list,
    the pipeline, the figures and the reminders, keeps all it holds, and is brought back by unarchive_booking.
    An Opportunity Booking is the PO record behind its Opportunity (the live booking, rollback and loss rules rely
    on it) and is only ever cancelled; a completed Booking (a service delivered, an order converted to an Installed
    Tool, which names it) is the record of a delivered order and stays (the delete refused the first, and most
    completed ones: those an Installed Tool or a notice names). Archiving a Booking archived already changes nothing."""

    doc = require_manager_scoped_document("CRM Booking", name, "deal:write", "BOOKING_NOT_FOUND", for_update=True)
    if doc.source == "Opportunity":
        raise CrmApiException("BOOKING_SOURCE_INVALID", OPPORTUNITY_BOOKING_ARCHIVE)
    if doc.installed_tool or doc.status == "Completed":
        raise CrmApiException("INVALID_TRANSITION", COMPLETED_BOOKING_ARCHIVE)
    if not doc.archived:
        _set_archived(doc, True)
    return serialize_booking(doc)


def unarchive_booking(name: str) -> dict[str, Any]:
    """Bring an archived Booking back: every field as it was, its version moved on. A Booking not archived is left
    as it is."""

    # The Account's row first (a shared lock), then the Booking's: a Booking is not restored under an archived
    # Account, which would put an order in progress under it. The Account's lock is taken whatever the snapshot says
    # of the Booking (one archived since is seen under its own lock below); the Account of an archived Booking does
    # not change (it takes no edit).
    current = require_manager_scoped_document("CRM Booking", name, "deal:write", "BOOKING_NOT_FOUND")
    account_is_archived = account_archived(current.account, shared_lock=True)
    doc = require_manager_scoped_document("CRM Booking", name, "deal:write", "BOOKING_NOT_FOUND", for_update=True)
    if doc.account != current.account:
        raise CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
    if doc.archived:
        if account_is_archived:
            raise CrmApiException("INVALID_TRANSITION", ARCHIVED_ACCOUNT_REOPEN)
        _set_archived(doc, False)
    return serialize_booking(doc)


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
    _require_contact(contact_id)
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
        raise CrmApiException("BOOKING_SOURCE_REQUIRED", "Opportunity Booking requires a source Opportunity.")
    source = frappe.db.get_value("CRM Opportunity", source_opportunity, ["account", "archived"], as_dict=True)
    if not source or source.account != account_id:
        raise CrmApiException("BOOKING_SOURCE_INVALID", "Source Opportunity must belong to the Account.")
    assert_opportunity_not_archived(source.archived, ARCHIVED_OPPORTUNITY_LINK)
    duplicate = frappe.db.sql(
        """SELECT `name` FROM `tabCRM Booking`
        WHERE `source_opportunity` = %s AND `status` != 'Cancelled' AND (%s IS NULL OR `name` != %s)
        LIMIT 1""",
        (source_opportunity, booking_id, booking_id),
    )
    if duplicate:
        raise CrmApiException("BOOKING_ALREADY_EXISTS", "The Opportunity already has a live Booking.")
    return source_opportunity


def _validate_booking(payload: dict[str, Any], booking_id: str | None = None) -> dict[str, Any]:
    account_id = required_text(payload, "accountId")
    # No Booking is created under an archived Account (the flag read under a shared lock on the Account's row,
    # before any other lock of the request). An edit reads the flag before its locks too, and decides in
    # update_booking (no move under an archived Account, no order put back in progress under one).
    if booking_id is None:
        require_active_account(account_id)
    else:
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
        "amount_cny": validate_booking_amount_cny(currency, payload.get("amountCny"), required=status == "Confirmed"),
        "status": status,
        "booking_owner": _booking_owner(payload.get("owner")),
        "source": source,
        "booking_type": booking_type,
        "source_opportunity": source_opportunity,
        "live_source_opportunity": source_opportunity if source_opportunity and status != "Cancelled" else None,
        "note": str(payload.get("note") or "").strip(),
    }


def serialize_booking(doc) -> dict[str, Any]:
    contact = frappe.db.get_value("Contact", doc.primary_contact, ["first_name", "last_name"], as_dict=True)
    contact_name = " ".join(part for part in ((contact.first_name if contact else ""), (contact.last_name if contact else "")) if part).strip()
    exact_amount = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR) AS `amount`, CAST(`amount_cny` AS CHAR) AS `amount_cny` FROM `tabCRM Booking` WHERE `name` = %s",
        (doc.name,), as_dict=True,
    )
    amount = exact_amount[0].amount if exact_amount else doc.amount or 0
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
        "amount": decimal_string(amount),
        "currency": doc.currency,
        "amountCny": cny_amount_text(doc.currency, amount, exact_amount[0].amount_cny if exact_amount else 0),
        "amountCnyNote": doc.amount_cny_note or "",
        "status": doc.status,
        "bookingDate": str(doc.booking_date or ""),
        "actualPoDate": str(doc.actual_po_date or ""),
        "actualPoDateSource": doc.actual_po_date_source or "",
        "actualPoDateNote": doc.actual_po_date_note or "",
        "owner": doc.booking_owner,
        "source": doc.source,
        "bookingType": doc.booking_type or "Equipment",
        "sourceOpportunityId": doc.source_opportunity or "",
        "note": doc.note or "",
        "modified": to_iso_timestamp(doc.modified),
        "archived": bool(doc.archived),
    }
    if doc.archived:
        result["archivedAt"] = to_iso_timestamp(doc.archived_at) if doc.archived_at else ""
        result["archivedBy"] = doc.archived_by or ""
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


def _lock_source_opportunity(booking) -> None:
    """Take the source Opportunity's row lock before the Booking's.

    The Opportunity services lock the Opportunity first and its Booking second; taking the same
    order here keeps a Booking change and an Opportunity action from deadlocking on each other.
    """

    if booking.source == "Opportunity" and booking.source_opportunity:
        rows = frappe.db.sql(
            "SELECT `archived` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE",
            (booking.source_opportunity,),
        )
        # As committed now: the Booking of an archived Opportunity (its order) is part of what was archived
        # and takes no change until the Opportunity is restored.
        if rows:
            assert_opportunity_not_archived(rows[0][0])


def touch_source_opportunity(booking) -> None:
    """Move the source Opportunity's version after one of its Bookings changed.

    The live Booking is part of the Opportunity's state: the Opportunity page shows it and PO
    confirmation, rollback and marking lost decide on it. Editing, reassigning, cancelling,
    completing or converting the Booking therefore has to invalidate the version a client holds,
    so an action prepared on the older view answers VERSION_CONFLICT instead of acting on a
    Booking that changed underneath it, whether or not the action carries a Booking version.
    """

    if booking.source != "Opportunity" or not booking.source_opportunity:
        return
    frappe.db.sql(
        "UPDATE `tabCRM Opportunity` SET `modified` = %s, `modified_by` = %s WHERE `name` = %s",
        (frappe.utils.now(), frappe.session.user, booking.source_opportunity),
    )
    frappe.clear_document_cache("CRM Opportunity", booking.source_opportunity)


def _list_filters(query: dict[str, Any]) -> tuple[str, list[Any]]:
    """WHERE clause and values of the Booking list: the caller's scope and the query's filters."""

    where_parts = [f"({conditions_for_doctype('CRM Booking')})"]
    values: list[Any] = []
    state = archive_state(query)
    if state != "all":
        where_parts.append("`archived` = %s")
        values.append(1 if state == "archived" else 0)
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
    if str(query.get("actualPoDateMissing") or "").strip().lower() in {"1", "true"}:
        # Orders whose PO is confirmed but whose PO date was never recorded, for a Manager to fill in.
        where_parts.append("`actual_po_date` IS NULL AND `status` IN ('Confirmed', 'Completed')")
    date_from = str(query.get("dateFrom") or "").strip()
    date_to = str(query.get("dateTo") or "").strip()
    if date_from:
        where_parts.append("`ddl` >= %s")
        values.append(date_from)
    if date_to:
        where_parts.append("`ddl` <= %s")
        values.append(date_to)
    return " AND ".join(where_parts), values


def list_bookings(query: dict[str, Any] | None = None):
    assert_capability("deal:view")
    if query is None:
        # Every Booking in scope but the archived ones, as a list query without archiveState gives it.
        where = f"({conditions_for_doctype('CRM Booking')}) AND `archived` = 0"
        rows = frappe.db.sql(
            f"SELECT `name` FROM `tabCRM Booking` WHERE {where} ORDER BY `modified` DESC, `name` DESC",
            as_dict=True,
        )
        return [serialize_booking(frappe.get_doc("CRM Booking", row.name)) for row in rows]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    where, values = _list_filters(query)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Booking` WHERE {where}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Booking` WHERE {where} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]), as_dict=True,
    )
    return [serialize_booking(frappe.get_doc("CRM Booking", row.name)) for row in rows], total, page, page_size


def booking_summary(query: dict[str, Any]) -> dict[str, Any]:
    """Count, pending count and Confirmed totals of every Booking the list query matches, whatever page is shown.

    The cards of the Booking page show these. They are computed here, in one statement, so that they describe
    one moment: a browser that adds up pages fetched one after the other can count a record twice or miss it
    when something changes in between. The totals are per currency, over the Confirmed Bookings.
    """

    assert_capability("deal:view")
    where, values = _list_filters(query)
    rows = frappe.db.sql(
        "SELECT `status`, UPPER(TRIM(COALESCE(`currency`, ''))) AS `currency`, COUNT(*) AS `count`, "
        "CAST(SUM(COALESCE(`amount`, 0)) AS CHAR) AS `amount` "
        f"FROM `tabCRM Booking` WHERE {where} GROUP BY `status`, UPPER(TRIM(COALESCE(`currency`, '')))",
        tuple(values), as_dict=True,
    )
    confirmed = [row for row in rows if row.status == "Confirmed"]
    return {
        "count": sum(int(row["count"]) for row in rows),
        "pendingCount": sum(int(row["count"]) for row in rows if row.status == "Pending"),
        "confirmed": {
            "count": sum(int(row["count"]) for row in confirmed),
            "totals": sorted(
                ({"currency": row.currency, "amount": format(Decimal(row.amount).quantize(Decimal("0.01")), ".2f")} for row in confirmed),
                key=lambda total: total["currency"],
            ),
        },
    }


def get_booking(name: str) -> dict[str, Any]:
    assert_capability("deal:view")
    return serialize_booking(_require_booking(name))


def create_booking(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:write")
    ensure_server_generated_id(payload)
    if str(payload.get("source") or "").strip() == "Opportunity":
        raise CrmApiException(
            "BOOKING_SOURCE_INVALID",
            "Opportunity Bookings are created by confirming the PO or approving an internal validation.",
        )
    values = _validate_booking(payload)
    actual_po_date = validate_actual_po_date(payload.get("actualPoDate"), required=False)
    if actual_po_date:
        values.update({"actual_po_date": actual_po_date, "actual_po_date_source": "booking_entry"})
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
        raise CrmApiException("CONFLICT", "The Opportunity already has a live Booking.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_booking(doc)


def _current_input(doc) -> dict[str, Any]:
    exact_amount, exact_amount_cny = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR), CAST(`amount_cny` AS CHAR) FROM `tabCRM Booking` WHERE `name` = %s",
        (doc.name,),
    )[0]
    return {
        "accountId": doc.account, "primaryContactId": doc.primary_contact,
        "equipment": doc.equipment, "quantity": doc.quantity, "ddl": str(doc.ddl or ""),
        "amount": exact_amount, "currency": doc.currency or "CNY", "status": doc.status, "owner": doc.booking_owner,
        "source": doc.source, "bookingType": doc.booking_type or "Equipment", "sourceOpportunityId": doc.source_opportunity or "", "note": doc.note or "",
        "actualPoDate": str(doc.actual_po_date or ""),
        # Empty until someone enters it, so a confirmed foreign-currency order asks for it on any edit.
        "amountCny": optional_money_text(exact_amount_cny),
    }


def _assert_opportunity_booking_edit(doc, merged: dict[str, Any]) -> None:
    """An Opportunity Booking follows its Opportunity: only its details and a manual cancel change."""

    fixed = {
        "accountId": doc.account,
        "source": doc.source,
        "sourceOpportunityId": doc.source_opportunity or "",
        "bookingType": doc.booking_type or "Equipment",
    }
    if any(str(merged.get(key) or "") != value for key, value in fixed.items()):
        raise CrmApiException(
            "BOOKING_SOURCE_INVALID",
            "Account, source, Opportunity and type of an Opportunity Booking cannot change.",
        )
    status = merged.get("status")
    if status != doc.status and (status != "Cancelled" or doc.status == "Cancelled"):
        raise CrmApiException("BOOKING_STATUS_INVALID", "An Opportunity Booking can only be changed to Cancelled.")


def _edited_actual_po_date(doc, requested: Any) -> str | None:
    """An ordinary edit may only give an Upsell Booking its first actual PO date.

    The date of a confirmed Opportunity PO, and any date already recorded, changes only through
    a Manager's correction. Returns the date to set, or None when nothing changes.
    """

    current = str(doc.actual_po_date or "")
    if str(requested or "") == current:
        return None
    if doc.source == "Opportunity" or current:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "The actual PO date changes only through a Manager's correction.",
            field_errors={"actualPoDate": "Manager correction only"},
        )
    return validate_actual_po_date(requested, required=True)


def _assert_amount_cny_edit(doc, recorded: str, merged: dict[str, Any]) -> None:
    """An ordinary edit may only give a foreign-currency order its first CNY amount.

    Once recorded it changes only through a Manager's correction, which keeps the reason and
    the Opportunity history; an edit that leaves it empty keeps the recorded amount. A Pending
    Booking is not an order yet, so its amount stays editable.
    """

    if doc.status == "Pending":
        return
    currency = str(merged.get("currency") or "CNY").strip().upper()
    if currency != str(doc.currency or "CNY").strip().upper():
        # Switching to CNY clears the separately recorded amount. Switching back would then
        # look like its first entry and bypass the Manager correction and its reason.
        raise CrmApiException(
            "VALIDATION_ERROR", "The currency of a confirmed order cannot change through an ordinary edit.",
            field_errors={"currency": "Confirmed order currency is fixed"},
        )
    if currency == "CNY":
        return
    if not recorded:
        return
    requested = merged.get("amountCny")
    if requested is None or str(requested).strip() == "":
        merged["amountCny"] = recorded
    elif required_positive_money(requested, "amountCny") != as_decimal(recorded):
        raise CrmApiException(
            "VALIDATION_ERROR",
            "The CNY amount changes only through a Manager's correction.",
            field_errors={"amountCny": "Manager correction only"},
        )


def update_booking(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    current = _require_booking(name)
    assert_booking_not_archived(current)
    if current.installed_tool or current.status == "Completed":
        raise CrmApiException("BOOKING_LOCKED", "Converted Booking cannot be edited.")
    # The Accounts the edit touches, the Booking's own and the one it would move to (that one in the caller's read
    # scope first: an id guessed answers as one that does not exist, archived or not): their flags read under shared
    # locks on their rows, in name order, before the Opportunity's and the Booking's (the order the Account's
    # archive takes them in).
    target_account = str(payload.get("accountId") or "").strip() or current.account
    if target_account != current.account:
        target_account = _require_account(target_account).name
    archived_accounts = lock_accounts((current.account, target_account))
    _lock_source_opportunity(current)
    doc = lock_document("CRM Booking", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Booking", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    assert_booking_not_archived_now(doc.name)
    if doc.installed_tool or doc.status == "Completed":
        raise CrmApiException("BOOKING_LOCKED", "Converted Booking cannot be edited.")
    if doc.account != current.account:
        # Moved by another request since the Accounts were locked (its version moved too).
        raise CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
    merged = _current_input(doc)
    recorded_amount_cny = merged["amountCny"]
    merged.update(payload)
    if str(merged.get("source") or "").strip() != doc.source:
        # Opportunity Bookings only come from PO confirmation or internal validation, so an
        # Upsell Booking cannot be relabelled as one later.
        raise CrmApiException("BOOKING_SOURCE_INVALID", "A Booking's source cannot change.")
    if doc.source == "Opportunity":
        _assert_opportunity_booking_edit(doc, merged)
    if target_account != doc.account and archived_accounts.get(doc.account):
        # Nothing moves out of an archived Account: its orders stay where they were archived with it (moved out, a
        # cancelled one could be put back in progress under another Account).
        raise CrmApiException("INVALID_TRANSITION", ARCHIVED_ACCOUNT_EDIT)
    if archived_accounts.get(target_account):
        # No Booking is moved under an archived Account, and none under one is put back in progress (the archive
        # is refused while one is): a cancelled order under it stays cancelled; its other details may be corrected.
        if target_account != doc.account:
            raise CrmApiException("INVALID_TRANSITION", ARCHIVED_ACCOUNT_LINK)
        if str(merged.get("status") or "") in {"Confirmed", "Pending"}:
            raise CrmApiException("INVALID_TRANSITION", ARCHIVED_ACCOUNT_REOPEN)
    actual_po_date = _edited_actual_po_date(doc, merged.get("actualPoDate"))
    _assert_amount_cny_edit(doc, recorded_amount_cny, merged)
    previous_owner = doc.booking_owner
    savepoint = f"crm_booking_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    for fieldname, value in _validate_booking(merged, name).items():
        setattr(doc, fieldname, value)
    if actual_po_date:
        doc.actual_po_date = actual_po_date
        doc.actual_po_date_source = "booking_entry"
    if doc.amount_cny != as_decimal(recorded_amount_cny or 0):
        # A correction's reason describes the amount it came with, so it goes when that amount does.
        doc.amount_cny_note = None
    try:
        doc.save(ignore_permissions=True)
        touch_source_opportunity(doc)
        if previous_owner != doc.booking_owner and doc.booking_owner != frappe.session.user:
            create_notification(
                recipient=doc.booking_owner, category="Booking", title="Booking reassigned",
                message=f"You are now responsible for {doc.equipment}.",
                route=f"/booking/{doc.name}", source_doctype="CRM Booking", source_name=doc.name,
            )
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("CONFLICT", "The Opportunity already has a live Booking.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_booking(doc)


def set_booking_actual_po_date(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    """A Manager fills in or corrects the date on a confirmed order's PO; a correction needs a reason."""

    assert_capability("deal:write")
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Only a Manager can fill in or correct the actual PO date.")
    current = _require_booking(name)
    assert_booking_not_archived(current)
    _lock_source_opportunity(current)
    doc = lock_document("CRM Booking", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Booking", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    assert_booking_not_archived_now(doc.name)
    # Completed orders count too: converting to an Installed Tool locks every other edit.
    if doc.status not in ("Confirmed", "Completed"):
        raise CrmApiException(
            "BOOKING_STATUS_INVALID", "Only a Confirmed or Completed Booking has an actual PO date.",
        )
    actual_po_date = validate_actual_po_date(payload.get("actualPoDate"), required=True)
    previous = str(doc.actual_po_date or "")
    if actual_po_date == previous:
        raise CrmApiException(
            "VALIDATION_ERROR", "actualPoDate is unchanged.", field_errors={"actualPoDate": "Unchanged"},
        )
    reason = str(payload.get("reason") or "").strip()
    if previous and not reason:
        raise CrmApiException(
            "VALIDATION_ERROR", "A reason is required to correct the actual PO date.",
            field_errors={"reason": "Required"},
        )
    savepoint = f"crm_booking_po_date_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.actual_po_date = actual_po_date
        doc.actual_po_date_source = "backfill"
        doc.actual_po_date_note = reason or None
        doc.save(ignore_permissions=True)
        touch_source_opportunity(doc)
        if doc.source_opportunity:
            # Written inline: services.opportunities imports this module, not the other way round.
            frappe.get_doc({
                "doctype": "CRM Opportunity History", "opportunity": doc.source_opportunity,
                "actor": frappe.session.user, "at": frappe.utils.now_datetime(), "field": "bookingPoDate",
                "from_value": previous, "to_value": actual_po_date,
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_booking(doc)


def set_booking_amount_cny(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    """A Manager fills in or corrects the CNY amount of a confirmed foreign-currency order.

    Completed orders are locked against ordinary edits, so this is how theirs gets filled in;
    a correction needs a reason.
    """

    assert_capability("deal:write")
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Only a Manager can fill in or correct the CNY amount.")
    current = _require_booking(name)
    assert_booking_not_archived(current)
    _lock_source_opportunity(current)
    doc = lock_document("CRM Booking", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Booking", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    assert_booking_not_archived_now(doc.name)
    if doc.status not in ("Confirmed", "Completed"):
        raise CrmApiException(
            "BOOKING_STATUS_INVALID", "Only a Confirmed or Completed Booking has a CNY amount to record.",
        )
    if (doc.currency or "CNY").upper() == "CNY":
        raise CrmApiException(
            "VALIDATION_ERROR", "A CNY Booking uses its amount.", field_errors={"amountCny": "CNY Booking"},
        )
    amount_cny = required_positive_money(payload.get("amountCny"), "amountCny")
    previous = as_decimal(
        frappe.db.sql("SELECT CAST(`amount_cny` AS CHAR) FROM `tabCRM Booking` WHERE `name` = %s", (name,))[0][0] or 0
    )
    if amount_cny == previous:
        raise CrmApiException("VALIDATION_ERROR", "amountCny is unchanged.", field_errors={"amountCny": "Unchanged"})
    reason = str(payload.get("reason") or "").strip()
    if previous and not reason:
        raise CrmApiException(
            "VALIDATION_ERROR", "A reason is required to correct the CNY amount.", field_errors={"reason": "Required"},
        )
    savepoint = f"crm_booking_amount_cny_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.amount_cny = amount_cny
        doc.amount_cny_note = reason or None
        doc.save(ignore_permissions=True)
        touch_source_opportunity(doc)
        if doc.source_opportunity:
            # Written inline: services.opportunities imports this module, not the other way round.
            frappe.get_doc({
                "doctype": "CRM Opportunity History", "opportunity": doc.source_opportunity,
                "actor": frappe.session.user, "at": frappe.utils.now_datetime(), "field": "bookingAmountCny",
                "from_value": optional_money_text(previous), "to_value": decimal_string(amount_cny),
            }).insert(ignore_permissions=True)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_booking(doc)


def complete_service_booking(name: str, expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    current = _require_booking(name)
    assert_booking_not_archived(current)
    if (current.booking_type or "Equipment") != "Service":
        raise CrmApiException("BOOKING_TYPE_INVALID", "Only Service Booking can be completed as a service.")
    if current.installed_tool or current.status == "Completed":
        raise CrmApiException("BOOKING_ALREADY_COMPLETED", "Booking was already completed.")
    if current.status != "Confirmed":
        raise CrmApiException("BOOKING_NOT_CONFIRMED", "Only Confirmed Service Booking can be completed.")

    _lock_source_opportunity(current)
    doc = lock_document("CRM Booking", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Booking", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    assert_booking_not_archived_now(doc.name)
    if (doc.booking_type or "Equipment") != "Service":
        raise CrmApiException("BOOKING_TYPE_INVALID", "Only Service Booking can be completed as a service.")
    if doc.installed_tool or doc.status == "Completed":
        raise CrmApiException("BOOKING_ALREADY_COMPLETED", "Booking was already completed.")
    if doc.status != "Confirmed":
        raise CrmApiException("BOOKING_NOT_CONFIRMED", "Only Confirmed Service Booking can be completed.")
    doc.status = "Completed"
    doc.save(ignore_permissions=True)
    touch_source_opportunity(doc)
    doc.reload()
    return serialize_booking(doc)
