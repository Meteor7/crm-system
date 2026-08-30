"""Lightweight CRM Visit persistence and workflow services."""

from __future__ import annotations

from collections.abc import Callable
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
from rayher_crm.services.contacts import _contact_account
from rayher_crm.services.notifications import create_notification


VISIT_TYPES = {"On-site", "Video", "Phone"}
VISIT_STATUS_ORDER = ["Planned", "Visited", "Minutes Submitted", "Manager Reviewed"]


def delete_visit(name: str) -> dict[str, str]:
    return delete_manager_scoped_document("CRM Visit", name, "visit:write", "VISIT_NOT_FOUND")


def _visit_owner(value: Any) -> str:
    owner = resolve_write_owner(value)
    if resolve_crm_role(owner) != "Sales":
        raise CrmApiException("INVALID_OWNER", "Visit owner must be an active CRM Sales user.")
    return owner


def _action_owner(value: Any, *, required: bool = False) -> str:
    owner = str(value or "").strip()
    if not owner:
        if required:
            raise CrmApiException("INVALID_TRANSITION", "Minutes require an action owner.")
        return ""
    if not frappe.db.get_value("User", owner, "enabled"):
        raise CrmApiException("INVALID_OWNER", "Action owner must be an active CRM user.")
    try:
        role = resolve_crm_role(owner)
    except frappe.PermissionError as exc:
        raise CrmApiException("INVALID_OWNER", "Action owner must be an active CRM Sales user.") from exc
    if role != "Sales":
        raise CrmApiException("INVALID_OWNER", "Action owner must be an active CRM Sales user with Visit access.")
    return owner


def _required_date(value: Any, fieldname: str) -> str:
    normalized = optional_date(value, fieldname)
    if not normalized:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} is required.", field_errors={fieldname: "Required"})
    return normalized


def _validate_contact(contact_id: Any, account_id: str) -> str:
    normalized = str(contact_id or "").strip()
    if not normalized:
        return ""
    if not frappe.db.exists("Contact", normalized):
        raise CrmApiException("CONTACT_NOT_FOUND", "Contact was not found.")
    if _contact_account(normalized) != account_id:
        raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "The contact belongs to another account.")
    if frappe.db.get_value("Contact", normalized, "custom_crm_status") != "Active":
        raise CrmApiException("CONTACT_INACTIVE", "The contact must be active.")
    return normalized


def _validate_opportunity(opportunity_id: Any, account_id: str) -> str:
    normalized = str(opportunity_id or "").strip()
    if not normalized:
        return ""
    opportunity_account = frappe.db.get_value("CRM Opportunity", normalized, "account")
    if not opportunity_account:
        raise CrmApiException("NOT_FOUND", "Opportunity was not found.")
    if opportunity_account != account_id:
        raise CrmApiException("CONFLICT", "The Opportunity belongs to another account.")
    return normalized


def serialize_visit(doc) -> dict[str, Any]:
    account = frappe.db.get_value(
        "Customer", doc.account, ["customer_name", "custom_crm_segment"], as_dict=True,
    )
    result = {
        "id": doc.name,
        "accountId": doc.account,
        "accountName": account.customer_name if account else doc.account,
        "segment": account.custom_crm_segment if account else "",
        "subject": doc.subject,
        "date": str(doc.visit_date or ""),
        "type": doc.visit_type,
        "status": doc.status,
        "owner": doc.visit_owner,
        "objective": doc.objective,
        "outcome": doc.outcome or "",
        "nextAction": doc.next_action or "",
        "actionOwner": doc.action_owner or "",
        "due": str(doc.due or ""),
        "actionDone": bool(doc.action_done),
        "modified": to_iso_timestamp(doc.modified),
    }
    if doc.primary_contact:
        result["primaryContactId"] = doc.primary_contact
    if doc.opportunity:
        result["opportunityId"] = doc.opportunity
    return result


def _require_visit(name: str):
    if not frappe.db.exists("CRM Visit", name):
        raise CrmApiException("VISIT_NOT_FOUND", "Visit was not found.")
    doc = frappe.get_doc("CRM Visit", name)
    if not frappe.has_permission("CRM Visit", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Visit is outside the current user scope.")
    return doc


def list_visits(query: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    assert_capability("visit:view")
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    where = [f"({conditions_for_doctype('CRM Visit')})"]
    values: list[Any] = []
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        where.append("(`subject` LIKE %s OR `objective` LIKE %s OR `account` LIKE %s)")
        values.extend([pattern, pattern, pattern])
    mappings = {
        "accountId": "account", "contactId": "primary_contact", "status": "status", "owner": "visit_owner",
    }
    for input_name, column in mappings.items():
        value = str(query.get(input_name) or "").strip()
        if value and value != "All":
            where.append(f"`{column}` = %s")
            values.append(value)
    date_from = optional_date(query.get("dateFrom"), "dateFrom")
    date_to = optional_date(query.get("dateTo"), "dateTo")
    if date_from:
        where.append("`visit_date` >= %s")
        values.append(date_from)
    if date_to:
        where.append("`visit_date` <= %s")
        values.append(date_to)
    if date_from and date_to and date_from > date_to:
        raise CrmApiException("VALIDATION_ERROR", "dateFrom must not be later than dateTo.")
    where_sql = " AND ".join(where)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Visit` WHERE {where_sql}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Visit` WHERE {where_sql} "
        "ORDER BY `visit_date` ASC, `modified` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]), as_dict=True,
    )
    return [serialize_visit(frappe.get_doc("CRM Visit", row.name)) for row in rows], total, page, page_size


def get_visit(name: str) -> dict[str, Any]:
    assert_capability("visit:view")
    return serialize_visit(_require_visit(name))


def get_visit_detail(name: str) -> dict[str, Any]:
    assert_capability("visit:view")
    doc = _require_visit(name)
    result = serialize_visit(doc)
    if doc.primary_contact:
        from rayher_crm.services.contacts import serialize_contact
        result["primaryContact"] = serialize_contact(frappe.get_doc("Contact", doc.primary_contact))
    from rayher_crm.services import visit_meetings
    result["meetingRecord"] = visit_meetings.get_record(name)
    result["attachments"] = visit_meetings.list_attachments(name)
    return result


def create_visit(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("visit:create")
    ensure_server_generated_id(payload)
    account_id = required_text(payload, "accountId")
    _require_account(account_id)
    doc = frappe.get_doc({
        "doctype": "CRM Visit",
        "account": account_id,
        "primary_contact": _validate_contact(payload.get("primaryContactId"), account_id),
        "opportunity": _validate_opportunity(payload.get("opportunityId"), account_id),
        "visit_owner": _visit_owner(payload.get("owner")),
        "subject": required_text(payload, "subject"),
        "visit_date": _required_date(payload.get("date"), "date"),
        "visit_type": validate_choice(payload.get("type"), "type", VISIT_TYPES),
        "status": "Planned",
        "objective": required_text(payload, "objective"),
        "created_by_user": frappe.session.user,
    }).insert(ignore_permissions=True)
    return serialize_visit(doc)


def _apply_edit(doc, command: dict[str, Any]) -> None:
    if doc.status == "Manager Reviewed":
        raise CrmApiException("INVALID_TRANSITION", "Manager-reviewed Visit cannot be edited.")
    if "subject" in command:
        doc.subject = required_text(command, "subject")
    if "date" in command:
        doc.visit_date = _required_date(command.get("date"), "date")
    if "visitType" in command:
        doc.visit_type = validate_choice(command.get("visitType"), "visitType", VISIT_TYPES)
    if "owner" in command:
        doc.visit_owner = _visit_owner(command.get("owner"))
    if "objective" in command:
        doc.objective = required_text(command, "objective")
    if "outcome" in command:
        doc.outcome = str(command.get("outcome") or "").strip()
    if "nextAction" in command:
        doc.next_action = str(command.get("nextAction") or "").strip()
    if "actionOwner" in command:
        doc.action_owner = _action_owner(command.get("actionOwner"))
    if "due" in command:
        doc.due = optional_date(command.get("due"), "due")


def _apply_advance(doc, command: dict[str, Any]) -> None:
    target = validate_choice(command.get("status"), "status", set(VISIT_STATUS_ORDER))
    current_index = VISIT_STATUS_ORDER.index(doc.status)
    if VISIT_STATUS_ORDER.index(target) != current_index + 1:
        raise CrmApiException("INVALID_TRANSITION", f"Visit cannot advance from {doc.status} to {target}.")
    if "outcome" in command:
        doc.outcome = str(command.get("outcome") or "").strip()
    if "nextAction" in command:
        doc.next_action = str(command.get("nextAction") or "").strip()
    if "actionOwner" in command:
        doc.action_owner = _action_owner(command.get("actionOwner"))
    if "due" in command:
        doc.due = optional_date(command.get("due"), "due")
    if target == "Visited" and not doc.outcome:
        raise CrmApiException("INVALID_TRANSITION", "Visited requires an outcome.")
    if target == "Minutes Submitted":
        from rayher_crm.services import visit_meetings
        record = visit_meetings.get_record(doc.name)
        required = ("purpose", "attendees", "agenda", "summary", "conclusion", "followup")
        if not record or not all(str(record.get(field) or "").strip() for field in required):
            raise CrmApiException("INVALID_TRANSITION", "Meeting record must be complete before submitting minutes.")
    doc.status = target


def _notify_update(doc, command_type: str, command: dict[str, Any]) -> bool:
    if command_type in {"advance", "edit"} and doc.action_owner and doc.next_action and ({"actionOwner", "nextAction"} & command.keys()):
        create_notification(
            recipient=doc.action_owner, category="Visit", title="Visit action assigned",
            message=f"{doc.subject}: {doc.next_action}", route=f"/visits?focus={doc.name}",
            source_doctype="CRM Visit", source_name=doc.name,
        )
        return True
    if command_type == "advance" and doc.status == "Manager Reviewed":
        create_notification(
            recipient=doc.visit_owner, category="Visit", title="Visit minutes reviewed",
            message=f"{doc.subject} was reviewed by the CRM Manager.", route=f"/visits?focus={doc.name}",
            source_doctype="CRM Visit", source_name=doc.name,
        )
        return True
    return False


def update_visit(
    name: str,
    command: dict[str, Any],
    expected_modified: Any,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    command_type = str(command.get("type") or "").strip()
    if command_type == "advance" and command.get("status") == "Manager Reviewed":
        assert_capability("visit:review")
    else:
        assert_capability("visit:write")
    _require_visit(name)
    doc = lock_document("CRM Visit", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Visit", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Visit is outside the current user scope.")

    if command_type == "edit":
        _apply_edit(doc, command)
    elif command_type == "advance":
        _apply_advance(doc, command)
    elif command_type == "complete_action":
        if not doc.next_action:
            raise CrmApiException("INVALID_TRANSITION", "The Visit has no next action to complete.")
        doc.action_done = 1
    else:
        raise CrmApiException("VALIDATION_ERROR", "Visit command type is invalid.")

    savepoint = f"crm_visit_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.save(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_visit_update")
        notified = _notify_update(doc, command_type, command)
        if notified and failure_injector:
            failure_injector("after_notification_insert")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_visit(doc)


def review_visit(name: str, expected_modified: Any = None) -> dict[str, Any]:
    assert_capability("visit:review")
    _require_visit(name)
    doc = lock_document("CRM Visit", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Visit", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Visit is outside the current user scope.")
    if doc.status != "Minutes Submitted":
        raise CrmApiException("INVALID_TRANSITION", "Only a submitted Visit record can be reviewed.")

    from rayher_crm.services import visit_meetings
    record = visit_meetings.get_record(doc.name)
    required = ("purpose", "attendees", "agenda", "summary", "conclusion", "followup")
    if not record or not all(str(record.get(field) or "").strip() for field in required):
        raise CrmApiException("INVALID_TRANSITION", "Complete the Visit record before Manager review.")

    doc.status = "Manager Reviewed"
    doc.save(ignore_permissions=True)
    _notify_update(doc, "advance")
    doc.reload()
    return serialize_visit(doc)


def visits_for_account(account_id: str) -> list[dict[str, Any]]:
    items, _total, _page, _page_size = list_visits({"accountId": account_id, "pageSize": 200})
    return items
