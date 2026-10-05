"""Persistent, recipient-scoped CRM notification events."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.permissions.notification_scope import SOURCE_DOCTYPES, can_read_source
from rayher_crm.services.common import normalize_pagination, to_iso_timestamp


CATEGORIES = {
    "Account", "Contact", "Requirement", "Lead", "Opportunity", "Action",
    "Visit", "Booking", "Demo", "Evaluation", "InstalledTool", "Quotation",
    "RFQ", "Document",
}


def active_crm_users(role: str) -> list[str]:
    role_name = {
        "Manager": "CRM Manager",
        "Sales": "CRM Sales",
        "Engineer": "CRM Engineer",
    }.get(role)
    if not role_name:
        raise CrmApiException("VALIDATION_ERROR", "CRM notification role is invalid.")
    users = frappe.get_all(
        "Has Role",
        filters={"role": role_name, "parenttype": "User"},
        pluck="parent",
    )
    active: list[str] = []
    for user in sorted(set(users)):
        if not frappe.db.get_value("User", user, "enabled"):
            continue
        try:
            if resolve_crm_role(user) == role:
                active.append(user)
        except frappe.PermissionError:
            continue
    return active


def _authenticated_user() -> str:
    user = getattr(frappe.session, "user", None)
    resolve_crm_role(user)
    return user


def _boolean(value: Any, fieldname: str) -> bool:
    if value in (None, "", False, 0, "0", "false", "False"):
        return False
    if value in (True, 1, "1", "true", "True"):
        return True
    raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a boolean.")


def _text(value: Any, fieldname: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} is required.")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} is too long.")
    return normalized


def _serialize(row: Any) -> dict[str, Any]:
    as_dict = getattr(row, "as_dict", None)
    value = frappe._dict(as_dict() if callable(as_dict) else row)
    read_at = to_iso_timestamp(value.read_at) if value.read_at else None
    return {
        "id": value.name,
        "category": value.category,
        "title": value.title,
        "message": value.message,
        "route": value.route,
        "recipientId": value.recipient_user,
        "actorId": value.actor,
        "createdAt": to_iso_timestamp(value.created_at),
        "readAt": read_at,
        "read": bool(read_at),
    }


def _validate_source(source_doctype, source_name) -> None:
    if source_doctype not in SOURCE_DOCTYPES or not isinstance(source_name, str) or not source_name:
        raise CrmApiException("VALIDATION_ERROR", "A supported notification source is required.")
    if not frappe.db.exists(source_doctype, source_name):
        raise CrmApiException("VALIDATION_ERROR", "Notification source record was not found.")


# The route is stored in a Data field.
ROUTE_MAX_LENGTH = 140


def record_route(list_route: str, record_id: str) -> str:
    """Route of a record's own page, or of its list when the ID makes that route too long to store.

    An Account or Contact ID is built from names and can be as long as the route field itself. A
    notice follows an action that is otherwise valid; refusing the action because the link to the
    record cannot be stored would be worse than a link to the list the record is in.
    """

    route = f"{list_route}/{record_id}"
    return route if len(route) <= ROUTE_MAX_LENGTH else list_route


def create_notification(
    *,
    recipient: str,
    category: str,
    title: str,
    message: str,
    route: str,
    source_doctype: str | None = None,
    source_name: str | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Create an event from server-owned actor/time and an approved server recipient."""

    actor = _authenticated_user()
    if not isinstance(recipient, str) or not frappe.db.get_value("User", recipient, "enabled"):
        raise CrmApiException("INVALID_OWNER", "Notification recipient must be an active User.")
    resolve_crm_role(recipient)
    if category not in CATEGORIES:
        raise CrmApiException("VALIDATION_ERROR", "Notification category is invalid.")
    normalized_route = _text(route, "route", ROUTE_MAX_LENGTH)
    if not normalized_route.startswith("/") or normalized_route.startswith("//"):
        raise CrmApiException("VALIDATION_ERROR", "Notification route must be an internal path.")
    _validate_source(source_doctype, source_name)
    if not can_read_source(source_doctype, source_name, recipient):
        raise CrmApiException("SCOPE_DENIED", "Notification recipient cannot read its source.")

    event = frappe.get_doc({
        "doctype": "CRM Notification Event",
        "actor": actor,
        "category": category,
        "recipient_user": recipient,
        "title": _text(title, "title", 140),
        "message": _text(message, "message", 1000),
        "route": normalized_route,
        "created_at": now_datetime(),
        "source_doctype": source_doctype,
        "source_name": source_name,
        "dedupe_key": dedupe_key,
    }).insert(ignore_permissions=True)
    return _serialize(event)


def notify_if_reachable(*, recipient: str | None, **fields: Any) -> dict[str, Any] | None:
    """Send an informational notice, skipping a recipient who can no longer receive it.

    A notice follows a business action that has already happened. When its
    recipient has left (disabled) or lost their CRM role, raising here would fail
    that action -- or, where the caller has no savepoint, report an error while the
    action commits anyway. `create_notification` stays strict for callers that
    choose a recipient on purpose.
    """
    # Malformed or unsupported source metadata is a caller bug: reject it before any recipient is
    # skipped, so a disabled user can never hide it from the tests and the logs.
    _validate_source(fields.get("source_doctype"), fields.get("source_name"))
    if not isinstance(recipient, str) or not recipient or not frappe.db.get_value("User", recipient, "enabled"):
        return None
    try:
        resolve_crm_role(recipient)
    except frappe.PermissionError:
        return None
    if not can_read_source(fields["source_doctype"], fields["source_name"], recipient):
        return None
    return create_notification(recipient=recipient, **fields)


def list_notifications(
    page: Any = None,
    page_size: Any = None,
    unread_only: Any = None,
) -> dict[str, Any]:
    user = _authenticated_user()
    normalized_page, normalized_size, offset = normalize_pagination(page, page_size)
    unread = _boolean(unread_only, "unreadOnly")
    where = [
        f"({conditions_for_doctype('CRM Notification Event', user, for_bound_query=True)})",
        "`recipient_user` = %s",
    ]
    values: list[Any] = [user]
    if unread:
        where.append("`read_at` IS NULL")
    clause = " AND ".join(where)
    total = int(frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabCRM Notification Event` WHERE {clause}", values,
    )[0][0])
    rows = frappe.db.sql(
        "SELECT `name`, `category`, `title`, `message`, `route`, `recipient_user`, "
        "`actor`, `created_at`, `read_at` FROM `tabCRM Notification Event` "
        f"WHERE {clause} ORDER BY `created_at` DESC, `name` DESC LIMIT %s OFFSET %s",
        [*values, normalized_size, offset], as_dict=True,
    )
    return {
        "items": [_serialize(row) for row in rows],
        "page": normalized_page,
        "pageSize": normalized_size,
        "total": total,
    }


def _recipient_row(notification_id: str, user: str):
    rows = frappe.db.sql(
        "SELECT `name`, `category`, `title`, `message`, `route`, `recipient_user`, "
        "`actor`, `created_at`, `read_at` FROM `tabCRM Notification Event` "
        "WHERE `name` = %s AND `recipient_user` = %s AND ("
        f"{conditions_for_doctype('CRM Notification Event', user, for_bound_query=True)}) FOR UPDATE",
        (notification_id, user), as_dict=True,
    )
    if not rows:
        raise CrmApiException("NOTIFICATION_NOT_FOUND", "The notification was not found.")
    return rows[0]


def mark_notification_read(notification_id: str) -> dict[str, Any]:
    user = _authenticated_user()
    if not isinstance(notification_id, str) or not notification_id.strip():
        raise CrmApiException("VALIDATION_ERROR", "id is required.")
    row = _recipient_row(notification_id.strip(), user)
    if not row.read_at:
        frappe.db.set_value(
            "CRM Notification Event", row.name, "read_at", now_datetime(), update_modified=False,
        )
        row = _recipient_row(row.name, user)
    return _serialize(row)


def mark_all_notifications_read() -> dict[str, Any]:
    user = _authenticated_user()
    read_at = now_datetime()
    frappe.db.sql(
        "UPDATE `tabCRM Notification Event` SET `read_at` = %s "
        "WHERE `recipient_user` = %s AND `read_at` IS NULL AND ("
        f"{conditions_for_doctype('CRM Notification Event', user, for_bound_query=True)})",
        (read_at, user),
    )
    updated = int(frappe.db.sql("SELECT ROW_COUNT()")[0][0])
    return {"updated": updated, "readAt": to_iso_timestamp(read_at)}


__all__ = [
    "active_crm_users", "create_notification", "notify_if_reachable", "list_notifications",
    "mark_notification_read", "mark_all_notifications_read",
]
