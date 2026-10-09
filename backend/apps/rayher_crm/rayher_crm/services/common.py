"""Validation, pagination, and wire-format helpers shared by CRM services."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from frappe.utils import get_datetime

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
MAX_PAGE_SIZE = 200
# What a list shows of the archive: the active records (the default), the archived ones, or both.
ARCHIVE_STATES = ("active", "archived", "all")


def archive_state(query: Mapping[str, Any]) -> str:
    """The archive filter of a list query: `archiveState`, "active" when absent."""

    state = str(query.get("archiveState") or "active")
    if state not in ARCHIVE_STATES:
        raise CrmApiException(
            "VALIDATION_ERROR", "archiveState must be active, archived or all.", field_errors={"archiveState": "Invalid value"},
        )
    return state


def _positive_integer(value: Any, default: int, fieldname: str) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:  # OverflowError: JSON 1e999 parses as inf
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a positive integer.") from exc
    if str(value).strip() != str(parsed) or parsed < 1:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a positive integer.")
    return parsed


def normalize_pagination(page: Any, page_size: Any) -> tuple[int, int, int]:
    normalized_page = _positive_integer(page, 1, "page")
    normalized_size = min(_positive_integer(page_size, 20, "pageSize"), MAX_PAGE_SIZE)
    return normalized_page, normalized_size, (normalized_page - 1) * normalized_size


def paginate_items(items: list[Any], query: Mapping[str, Any]) -> tuple[list[Any], int, int, int]:
    """Apply the canonical 1..200 pagination contract to an already scoped list."""

    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    return items[offset:offset + page_size], len(items), page, page_size


def read_all_pages(read_page, base_query: Mapping[str, Any] | None = None) -> list[Any]:
    query = dict(base_query or {})
    first, total, _page, _page_size = read_page({**query, "page": 1, "pageSize": MAX_PAGE_SIZE})
    items = list(first)
    page_count = (int(total) + MAX_PAGE_SIZE - 1) // MAX_PAGE_SIZE
    for page in range(2, page_count + 1):
        page_items, _total, _page, _page_size = read_page({**query, "page": page, "pageSize": MAX_PAGE_SIZE})
        items.extend(page_items)
    return items


def ensure_server_generated_id(payload: Mapping[str, Any]) -> None:
    if "id" in payload:
        raise CrmApiException("VALIDATION_ERROR", "Create requests must not provide an id.")


def as_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        import frappe

        value = frappe.parse_json(value)
    if not isinstance(value, Mapping):
        raise CrmApiException("VALIDATION_ERROR", "A JSON object is required.")
    return dict(value)


def required_text(payload: Mapping[str, Any], fieldname: str) -> str:
    value = payload.get(fieldname)
    if not isinstance(value, str) or not value.strip():
        raise CrmApiException(
            "VALIDATION_ERROR",
            f"{fieldname} is required.",
            field_errors={fieldname: "Required"},
        )
    return value.strip()


def validate_choice(value: Any, fieldname: str, choices: set[str]) -> str:
    if value not in choices:
        raise CrmApiException(
            "VALIDATION_ERROR",
            f"{fieldname} is invalid.",
            field_errors={fieldname: "Invalid value"},
        )
    return value


def optional_date(value: Any, fieldname: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must use YYYY-MM-DD.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a real YYYY-MM-DD date.") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must use YYYY-MM-DD.")
    return value


def resolve_write_owner(requested_owner: Any, *, shared_sales: bool = False) -> str:
    import frappe

    user_id = getattr(frappe.session, "user", None)
    role = resolve_crm_role(user_id)
    requested = requested_owner.strip() if isinstance(requested_owner, str) else ""
    if role == "Sales" and not shared_sales:
        if requested and requested != user_id:
            # The client tells this refusal from a record out of reach by this sentence (src/api/request-state.ts):
            # change the two together.
            raise CrmApiException("SCOPE_DENIED", "Sales users can only assign records to themselves.")
        return user_id
    if role not in {"Manager", "Sales"}:
        raise frappe.PermissionError("CRM write ownership requires Manager or Sales.")

    target = requested or user_id
    try:
        if not frappe.db.get_value("User", target, "enabled"):
            raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM Manager or Sales user.")
        target_role = resolve_crm_role(target)
    except frappe.PermissionError as exc:
        raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM Manager or Sales user.") from exc
    if target_role not in {"Manager", "Sales"}:
        raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM Manager or Sales user.")
    return target


def to_iso_timestamp(value: str | datetime) -> str:
    parsed = get_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TIMEZONE)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_expected_modified(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CrmApiException("VALIDATION_ERROR", "expectedModified is required.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise CrmApiException("VALIDATION_ERROR", "expectedModified must be an ISO timestamp.") from exc
    if parsed.tzinfo is None:
        raise CrmApiException("VALIDATION_ERROR", "expectedModified must include a timezone.")
    try:
        return to_iso_timestamp(parsed)
    except OverflowError as exc:  # e.g. 9999-12-31T23:59:59-14:00 has no UTC equivalent
        raise CrmApiException("VALIDATION_ERROR", "expectedModified must be an ISO timestamp.") from exc


def require_manager_scoped_document(
    doctype: str,
    name: str,
    capability: str,
    not_found_code: str,
    *,
    for_update: bool = False,
):
    """The record a Manager-only action (an archive or a restore) is about: the capability, the Manager role, the
    record and the caller's read scope are checked in that order. With for_update the record is read with its row
    locked (`SELECT … FOR UPDATE`, a locking read: the row as committed, not this transaction's snapshot), so the
    action decides on the current record and no other write lands on it before the action commits."""

    import frappe

    assert_capability(capability)
    if resolve_crm_role() != "Manager":
        raise frappe.PermissionError("CRM Manager role is required.")
    if for_update:
        try:
            doc = frappe.get_doc(doctype, name, for_update=True)
        except frappe.DoesNotExistError as exc:
            frappe.clear_last_message()
            raise CrmApiException(not_found_code, f"{doctype} was not found.") from exc
    else:
        if not frappe.db.exists(doctype, name):
            raise CrmApiException(not_found_code, f"{doctype} was not found.")
        doc = frappe.get_doc(doctype, name)
    if not frappe.has_permission(doctype, "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", f"{doctype} is outside the current user scope.")
    return doc
