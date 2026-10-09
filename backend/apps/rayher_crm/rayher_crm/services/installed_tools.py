"""Installed Tool services and atomic Booking conversion."""

from __future__ import annotations

import json
from datetime import date
from collections.abc import Callable
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype, has_crm_permission
from rayher_crm.services.bookings import (
    _lock_source_opportunity,
    _require_booking,
    assert_booking_not_archived,
    assert_booking_not_archived_now,
    serialize_booking,
    touch_source_opportunity,
)
from rayher_crm.services.common import normalize_pagination, required_text, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.notifications import create_notification
from rayher_crm.services.sites import _require_site, _site_account, can_read_site_data, sites_of_account


def _engineer_owner(value: Any) -> str:
    owner = value.strip() if isinstance(value, str) else ""
    if not owner or not frappe.db.exists("User", {"name": owner, "enabled": 1}):
        raise CrmApiException("INVALID_OWNER", "Engineer owner must be an active CRM Engineer.")
    try:
        role = resolve_crm_role(owner)
    except frappe.PermissionError as exc:
        raise CrmApiException("INVALID_OWNER", "Engineer owner must be an active CRM Engineer.") from exc
    if role != "Engineer":
        raise CrmApiException("INVALID_OWNER", "Engineer owner must be an active CRM Engineer.")
    return owner


def _unique_serial(value: Any, tool_id: str | None = None) -> str:
    serial = required_text({"serial": value}, "serial")
    rows = frappe.db.sql(
        """SELECT `name` FROM `tabCRM Installed Tool`
        WHERE LOWER(`serial`) = LOWER(%s) AND (%s IS NULL OR `name` != %s) LIMIT 1""",
        (serial, tool_id, tool_id),
    )
    if rows:
        raise CrmApiException("INSTALLED_TOOL_SERIAL_EXISTS", "Serial Number already exists.")
    return serial


def _fallback(value: Any) -> str:
    return str(value or "").strip() or "待确认"


def _optional_date(value: Any, field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise CrmApiException("VALIDATION_ERROR", f"{field} must be an ISO date.") from exc

def _decode_json(value: Any) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


LIFECYCLE_STAGES = ("FAT", "Shipment", "Installation", "SAT", "Warranty")
LIFECYCLE_STATUS_AFTER_COMPLETION = {
    "FAT": "Shipment",
    "Shipment": "Installation",
    "Installation": "Installation Complete",
    "SAT": "Production",
}
COMPLETENESS_FIELDS = (
    "serial", "model", "site", "location", "engineer_owner", "software", "firmware",
    "operating_system", "configuration", "sales_order_reference", "contract_reference",
    "ownership_type", "warranty_start", "warranty_end", "service_contract", "pm_cycle", "last_service",
)


def _calculate_completeness(doc, milestones: list[dict[str, Any]] | None = None) -> int:
    lifecycle = milestones if milestones is not None else _decode_json(doc.milestones)
    filled = sum(bool(str(getattr(doc, field, "") or "").strip()) for field in COMPLETENESS_FIELDS)
    completed = sum(row.get("state") == "Done" for row in lifecycle)
    return round((filled + completed) * 100 / (len(COMPLETENESS_FIELDS) + len(LIFECYCLE_STAGES)))


def _required_date(payload: dict[str, Any], field: str) -> str:
    value = required_text(payload, field)
    parsed = _optional_date(value, field)
    if not parsed:
        raise CrmApiException("VALIDATION_ERROR", f"{field} is required.")
    return parsed


def _evidence_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise CrmApiException("VALIDATION_ERROR", "evidence must be an array of non-empty strings.")
    return [item.strip() for item in value]


def _is_lifecycle_completed(doc) -> bool:
    if doc.lifecycle_stage != "Warranty":
        return False
    if frappe.db.exists(
        "CRM Installed Tool Lifecycle History",
        {"installed_tool": doc.name, "from_stage": "Warranty", "to_stage": "Completed"},
    ):
        return True
    milestones = _decode_json(doc.milestones)
    return bool(milestones and all(row.get("state") == "Done" for row in milestones))


def _completed_milestones(doc, completed_at: str) -> list[dict[str, str]]:
    current_stage = doc.lifecycle_stage
    current_index = LIFECYCLE_STAGES.index(current_stage)
    existing = {row.get("label"): row for row in _decode_json(doc.milestones)}
    final = current_stage == "Warranty"
    result: list[dict[str, str]] = []
    for index, stage in enumerate(LIFECYCLE_STAGES):
        previous_date = str(existing.get(stage, {}).get("date") or "")
        if index < current_index:
            result.append({"label": stage, "date": previous_date, "state": "Done"})
        elif index == current_index:
            result.append({"label": stage, "date": completed_at, "state": "Done"})
        elif index == current_index + 1 and not final:
            result.append({"label": stage, "date": "", "state": "Current"})
        else:
            result.append({"label": stage, "date": "", "state": "Waiting"})
    return result

def serialize_installed_tool(doc) -> dict[str, Any]:
    can_read_site = can_read_site_data(doc.account)
    return {
        "id": doc.name,
        "accountId": doc.account,
        "siteId": doc.site if can_read_site else "",
        "serial": doc.serial,
        "model": doc.model,
        "account": frappe.db.get_value("Customer", doc.account, "customer_name") or doc.account,
        "site": (frappe.db.get_value("Address", doc.site, "address_title") or doc.site) if can_read_site else "",
        "location": doc.location if can_read_site else "",
        "status": doc.status,
        "lifecycleStage": doc.lifecycle_stage,
        "software": doc.software,
        "firmware": doc.firmware,
        "warrantyEnd": str(doc.warranty_end or ""),
        "completeness": int(doc.completeness or 0),
        "sourceBookingId": doc.source_booking,
        "sourceOpportunityId": doc.source_opportunity or "",
        "salesOwner": doc.sales_owner,
        "engineerOwner": doc.engineer_owner,
        "salesOrder": doc.sales_order_reference or "",
        "contract": doc.contract_reference or "",
        "warrantyStart": str(doc.warranty_start or ""),
        "serviceContract": doc.service_contract or "",
        "pmCycle": doc.pm_cycle or "",
        "lastService": str(doc.last_service or ""),
        "operatingSystem": doc.operating_system or "",
        "configuration": doc.configuration or "",
        "ownershipType": doc.ownership_type,
        "milestones": _decode_json(doc.milestones),
        "documents": _decode_json(doc.documents),
        "modified": to_iso_timestamp(doc.modified),
    }


def _history_rows(doctype: str, installed_tool: str, fields: list[str]) -> list:
    return frappe.get_all(
        doctype,
        filters={"installed_tool": installed_tool},
        fields=["name", *fields],
        order_by="at desc, creation desc",
    )


def _serialize_lifecycle_history(row) -> dict[str, Any]:
    return {
        "id": row.name,
        "at": to_iso_timestamp(row.at),
        "actor": row.actor,
        "fromStage": row.from_stage,
        "toStage": row.to_stage,
        "completedAt": str(row.completed_at or ""),
        "result": row.result,
        "openIssues": row.open_issues,
        "customerSignoff": row.customer_signoff,
        "comment": row.comment,
        "evidence": _decode_json(row.evidence),
    }


def _serialize_version_history(row) -> dict[str, Any]:
    return {
        "id": row.name,
        "at": to_iso_timestamp(row.at),
        "actor": row.actor,
        "changeDate": str(row.change_date or ""),
        "changeType": row.change_type,
        "fromValue": row.from_value or "",
        "toValue": row.to_value,
        "reason": row.reason,
        "comment": row.comment or "",
    }


def _serialize_service_history(row) -> dict[str, Any]:
    return {
        "id": row.name,
        "at": to_iso_timestamp(row.at),
        "actor": row.actor,
        "serviceDate": str(row.service_date or ""),
        "serviceType": row.service_type,
        "result": row.result,
        "openIssues": row.open_issues,
        "nextAction": row.next_action or "",
        "actionOwner": row.action_owner or "",
        "due": str(row.due or ""),
        "comment": row.comment or "",
        "warrantyStart": str(row.warranty_start or ""),
        "warrantyEnd": str(row.warranty_end or ""),
        "serviceContract": row.service_contract or "",
        "pmCycle": row.pm_cycle or "",
    }


def _can_operate_installed_tool(doc) -> bool:
    role = resolve_crm_role()
    return role == "Manager" or (role == "Engineer" and doc.engineer_owner == frappe.session.user)


def _assert_installed_tool_operator(doc) -> str:
    role = resolve_crm_role()
    if role == "Manager" or (role == "Engineer" and doc.engineer_owner == frappe.session.user):
        return role
    raise CrmApiException(
        "INSTALLED_TOOL_OPERATION_DENIED",
        "Only CRM Manager or the assigned Engineer may operate this Installed Tool.",
    )


def get_installed_tool(name: str) -> dict[str, Any]:
    assert_capability("service:view")
    doc = _require_installed_tool(name)
    lifecycle = [
        _serialize_lifecycle_history(row)
        for row in _history_rows(
            "CRM Installed Tool Lifecycle History",
            doc.name,
            ["at", "actor", "from_stage", "to_stage", "completed_at", "result", "open_issues", "customer_signoff", "comment", "evidence"],
        )
    ]
    versions = [
        _serialize_version_history(row)
        for row in _history_rows(
            "CRM Installed Tool Version History",
            doc.name,
            ["at", "actor", "change_date", "change_type", "from_value", "to_value", "reason", "comment"],
        )
    ]
    services = [
        _serialize_service_history(row)
        for row in _history_rows(
            "CRM Installed Tool Service History",
            doc.name,
            ["at", "actor", "service_date", "service_type", "result", "open_issues", "next_action", "action_owner", "due", "comment", "warranty_start", "warranty_end", "service_contract", "pm_cycle"],
        )
    ]
    result = serialize_installed_tool(doc)
    result.update({
        "lifecycleHistory": lifecycle,
        "versionHistory": versions,
        "serviceHistory": services,
        "lifecycleCompleted": any(row["toStage"] == "Completed" for row in lifecycle)
        or bool(result["milestones"] and all(row.get("state") == "Done" for row in result["milestones"])),
        "canOperate": _can_operate_installed_tool(doc),
        "canReassign": resolve_crm_role() == "Manager",
        # The Sites of the Account, for the editor of the Tool: id, name and city, what the choice is made by. An
        # Engineer reads the Tool and its Site, but not the Account 360 (it carries the Account's Visits, which an
        # Engineer may not read), so the editor cannot ask it for the Sites; the Sites' kind, process and status
        # stay with the Account.
        "sites": [
            {"id": site["id"], "name": site["name"], "city": site["city"]}
            for site in (sites_of_account(doc.account) if can_read_site_data(doc.account) else [])
        ],
    })
    return result

def _require_installed_tool(name: str):
    if not frappe.db.exists("CRM Installed Tool", name):
        raise CrmApiException("INSTALLED_TOOL_NOT_FOUND", "Installed Tool was not found.")
    doc = frappe.get_doc("CRM Installed Tool", name)
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        code = "INSTALLED_TOOL_SCOPE_DENIED" if resolve_crm_role() == "Engineer" else "SCOPE_DENIED"
        raise CrmApiException(code, "The Installed Tool is outside the current user scope.")
    return doc


def list_installed_tools(query: dict[str, Any] | None = None):
    assert_capability("service:view")
    where_parts = [f"({conditions_for_doctype('CRM Installed Tool')})"]
    values: list[Any] = []
    where = where_parts[0]
    if query is None:
        rows = frappe.db.sql(
            f"SELECT `name` FROM `tabCRM Installed Tool` WHERE {where} ORDER BY `modified` DESC, `name` DESC",
            as_dict=True,
        )
        return [serialize_installed_tool(frappe.get_doc("CRM Installed Tool", row.name)) for row in rows]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        where_parts.append("(`name` LIKE %s OR `serial` LIKE %s OR `model` LIKE %s)")
        values.extend([pattern, pattern, pattern])
    for input_name, column in (("accountId", "account"), ("status", "status"), ("owner", "engineer_owner")):
        value = str(query.get(input_name) or "").strip()
        if value and value != "All":
            where_parts.append(f"`{column}` = %s")
            values.append(value)
    where = " AND ".join(where_parts)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Installed Tool` WHERE {where}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Installed Tool` WHERE {where} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]), as_dict=True,
    )
    return [serialize_installed_tool(frappe.get_doc("CRM Installed Tool", row.name)) for row in rows], total, page, page_size


def convert_booking_to_installed_tool(
    booking_id: str,
    payload: dict[str, Any],
    expected_modified: Any,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    assert_capability("deal:write")
    current = _require_booking(booking_id)
    assert_booking_not_archived(current)
    if current.installed_tool or current.status == "Completed":
        raise CrmApiException("BOOKING_ALREADY_CONVERTED", "Booking was already converted.")
    if current.status != "Confirmed":
        raise CrmApiException("BOOKING_NOT_CONFIRMED", "Only Confirmed Booking can be converted.")

    _lock_source_opportunity(current)
    booking = lock_document("CRM Booking", booking_id, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Booking", "read", doc=booking, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Booking is outside the current user scope.")
    assert_booking_not_archived_now(booking.name)
    if booking.installed_tool or booking.status == "Completed":
        raise CrmApiException("BOOKING_ALREADY_CONVERTED", "Booking was already converted.")
    if booking.status != "Confirmed":
        raise CrmApiException("BOOKING_NOT_CONFIRMED", "Only Confirmed Booking can be converted.")

    if (booking.booking_type or "Equipment") != "Equipment":
        raise CrmApiException("BOOKING_TYPE_INVALID", "Service Booking cannot be converted to Installed Tool.")
    site_id = required_text(payload, "siteId")
    _require_site(site_id, booking.account)
    engineer = _engineer_owner(payload.get("engineerOwner"))
    model = required_text(payload, "model")
    savepoint = f"crm_booking_convert_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        milestones = [
            {"label": "FAT", "date": "", "state": "Current"},
            {"label": "Shipment", "date": "", "state": "Waiting"},
            {"label": "Installation", "date": "", "state": "Waiting"},
            {"label": "SAT", "date": "", "state": "Waiting"},
            {"label": "Warranty", "date": "", "state": "Waiting"},
        ]
        tool = frappe.get_doc({
            "doctype": "CRM Installed Tool",
            "account": booking.account,
            "site": site_id,
            "serial": f"CRM-SN-TMP-{frappe.generate_hash(length=10)}",
            "model": model,
            "location": _fallback(payload.get("location")),
            "status": "Delivery Preparation",
            "lifecycle_stage": "FAT",
            "software": _fallback(payload.get("software")),
            "firmware": _fallback(payload.get("firmware")),
            "warranty_end": None,
            "completeness": 0,
            "source_booking": booking.name,
            "source_opportunity": booking.source_opportunity,
            "sales_owner": booking.booking_owner,
            "engineer_owner": engineer,
            "sales_order_reference": _fallback(payload.get("salesOrder")),
            "contract_reference": _fallback(payload.get("contract")),
            "warranty_start": None,
            "service_contract": "",
            "pm_cycle": "",
            "last_service": None,
            "operating_system": "",
            "configuration": _fallback(payload.get("configuration")),
            "ownership_type": "Customer Owned",
            "milestones": json.dumps(milestones, ensure_ascii=False),
            "documents": "[]",
        })
        tool.completeness = _calculate_completeness(tool)
        tool.insert(ignore_permissions=True)
        tool.serial = f"CRM-SN-{tool.name.rsplit(chr(45), 1)[-1]}"
        tool.save(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_tool_insert")

        booking.status = "Completed"
        booking.installed_tool = tool.name
        booking.installed_tool_converted_at = frappe.utils.now_datetime()
        booking.save(ignore_permissions=True)
        touch_source_opportunity(booking)
        if booking.source_opportunity:
            frappe.get_doc({
                "doctype": "CRM Opportunity History", "opportunity": booking.source_opportunity,
                "actor": frappe.session.user, "at": frappe.utils.now_datetime(), "field": "bookingConverted",
                "from_value": booking.name, "to_value": tool.name,
            }).insert(ignore_permissions=True)
        if engineer != frappe.session.user:
            create_notification(
                recipient=engineer, category="InstalledTool",
                title="Installed Tool assigned",
                message=f"{tool.serial} was created from Booking {booking.name}.",
                route=f"/installed-tools?surface=detail&tool={tool.name}",
                source_doctype="CRM Installed Tool", source_name=tool.name,
            )
        if failure_injector:
            failure_injector("after_booking_update")
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("CONFLICT", "Installed Tool serial already exists.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise

    booking.reload()
    tool.reload()
    return {"booking": serialize_booking(booking), "installedTool": serialize_installed_tool(tool)}


def transition_installed_tool(
    name: str,
    payload: dict[str, Any],
    expected_modified: Any,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    assert_capability("installed_tool:write")
    current = _require_installed_tool(name)
    _assert_installed_tool_operator(current)
    completed_at = _required_date(payload, "completedAt")
    if date.fromisoformat(completed_at) > date.fromisoformat(frappe.utils.nowdate()):
        raise CrmApiException("VALIDATION_ERROR", "completedAt must not be in the future.")
    result = required_text(payload, "result")
    open_issues = required_text(payload, "openIssues")
    customer_signoff = required_text(payload, "customerSignoff")
    comment = required_text(payload, "comment")
    evidence = _evidence_list(payload.get("evidence"))

    doc = lock_document("CRM Installed Tool", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("INSTALLED_TOOL_SCOPE_DENIED", "The Installed Tool is outside the current user scope.")
    _assert_installed_tool_operator(doc)
    if doc.lifecycle_stage not in LIFECYCLE_STAGES or _is_lifecycle_completed(doc):
        raise CrmApiException("INVALID_TRANSITION", "The Installed Tool lifecycle cannot be advanced.")
    completed_dates = [
        str(row.get("date") or "") for row in _decode_json(doc.milestones)
        if row.get("state") == "Done" and row.get("date")
    ]
    if completed_dates and date.fromisoformat(completed_at) < max(date.fromisoformat(value) for value in completed_dates):
        raise CrmApiException("VALIDATION_ERROR", "completedAt must not be before an earlier lifecycle stage.")

    current_index = LIFECYCLE_STAGES.index(doc.lifecycle_stage)
    to_stage = LIFECYCLE_STAGES[current_index + 1] if current_index + 1 < len(LIFECYCLE_STAGES) else "Completed"
    milestones = _completed_milestones(doc, completed_at)
    savepoint = f"crm_installed_tool_transition_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        frappe.get_doc({
            "doctype": "CRM Installed Tool Lifecycle History",
            "installed_tool": doc.name,
            "at": frappe.utils.now_datetime(),
            "actor": frappe.session.user,
            "from_stage": doc.lifecycle_stage,
            "to_stage": to_stage,
            "completed_at": completed_at,
            "result": result,
            "open_issues": open_issues,
            "customer_signoff": customer_signoff,
            "comment": comment,
            "evidence": json.dumps(evidence, ensure_ascii=False),
        }).insert(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_history_insert")

        if to_stage != "Completed":
            doc.lifecycle_stage = to_stage
        doc.status = LIFECYCLE_STATUS_AFTER_COMPLETION.get(doc.lifecycle_stage if to_stage == "Completed" else LIFECYCLE_STAGES[current_index], doc.status)
        doc.milestones = json.dumps(milestones, ensure_ascii=False)
        doc.completeness = _calculate_completeness(doc, milestones)
        doc.save(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_tool_update")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise

    return get_installed_tool(doc.name)

VERSION_FIELD_MAP = {
    "Software": "software",
    "Firmware": "firmware",
    "Operating System": "operating_system",
    "Configuration": "configuration",
}
SERVICE_TYPES = {
    "Warranty Activation",
    "Preventive Maintenance",
    "Corrective Service",
    "Remote Support",
    "Installation Support",
    "Contract Change",
}


def _locked_operable_tool(name: str, expected_modified: Any):
    assert_capability("installed_tool:write")
    current = _require_installed_tool(name)
    _assert_installed_tool_operator(current)
    doc = lock_document("CRM Installed Tool", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("INSTALLED_TOOL_SCOPE_DENIED", "The Installed Tool is outside the current user scope.")
    _assert_installed_tool_operator(doc)
    return doc


def add_installed_tool_version_record(
    name: str,
    payload: dict[str, Any],
    expected_modified: Any,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    change_date = _required_date(payload, "changeDate")
    change_type = required_text(payload, "changeType")
    if change_type not in VERSION_FIELD_MAP:
        raise CrmApiException("VALIDATION_ERROR", "changeType is invalid.")
    to_value = required_text(payload, "toValue")
    reason = required_text(payload, "reason")
    comment = str(payload.get("comment") or "").strip()
    doc = _locked_operable_tool(name, expected_modified)
    fieldname = VERSION_FIELD_MAP[change_type]
    from_value = str(getattr(doc, fieldname, "") or "")
    if from_value == to_value:
        raise CrmApiException("VALIDATION_ERROR", "Version or configuration value did not change.")

    savepoint = f"crm_installed_tool_version_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        frappe.get_doc({
            "doctype": "CRM Installed Tool Version History",
            "installed_tool": doc.name,
            "at": frappe.utils.now_datetime(),
            "actor": frappe.session.user,
            "change_date": change_date,
            "change_type": change_type,
            "from_value": from_value,
            "to_value": to_value,
            "reason": reason,
            "comment": comment,
        }).insert(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_history_insert")
        setattr(doc, fieldname, to_value)
        doc.completeness = _calculate_completeness(doc)
        doc.save(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_tool_update")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return get_installed_tool(doc.name)


def _active_user(value: Any, field: str) -> str:
    user = str(value or "").strip()
    if not user or not frappe.db.exists("User", {"name": user, "enabled": 1}):
        raise CrmApiException("VALIDATION_ERROR", f"{field} must be an active user.")
    return user


def add_installed_tool_service_record(
    name: str,
    payload: dict[str, Any],
    expected_modified: Any,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    service_date = _required_date(payload, "serviceDate")
    service_type = required_text(payload, "serviceType")
    if service_type not in SERVICE_TYPES:
        raise CrmApiException("VALIDATION_ERROR", "serviceType is invalid.")
    result = required_text(payload, "result")
    open_issues = required_text(payload, "openIssues")
    next_action = str(payload.get("nextAction") or "").strip()
    comment = str(payload.get("comment") or "").strip()
    if next_action:
        requested_action_owner = payload.get("actionOwner")
        due = _required_date(payload, "due")
    else:
        requested_action_owner = ""
        due = None

    warranty_start = _optional_date(payload.get("warrantyStart"), "warrantyStart") if "warrantyStart" in payload else None
    warranty_end = _optional_date(payload.get("warrantyEnd"), "warrantyEnd") if "warrantyEnd" in payload else None
    service_contract = str(payload.get("serviceContract") or "").strip() if "serviceContract" in payload else None
    pm_cycle = str(payload.get("pmCycle") or "").strip() if "pmCycle" in payload else None
    doc = _locked_operable_tool(name, expected_modified)
    action_owner = _active_user(requested_action_owner, "actionOwner") if next_action else ""
    if action_owner and not frappe.has_permission(
        "CRM Installed Tool", "read", doc=doc, user=action_owner,
    ):
        raise CrmApiException(
            "INVALID_OWNER", "Action owner must have access to this Installed Tool.",
        )
    resulting_start = warranty_start if "warrantyStart" in payload else doc.warranty_start
    resulting_end = warranty_end if "warrantyEnd" in payload else doc.warranty_end
    if resulting_start and resulting_end and date.fromisoformat(str(resulting_start)) > date.fromisoformat(str(resulting_end)):
        raise CrmApiException("VALIDATION_ERROR", "warrantyEnd must not be before warrantyStart.")

    savepoint = f"crm_installed_tool_service_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        history = frappe.get_doc({
            "doctype": "CRM Installed Tool Service History",
            "installed_tool": doc.name,
            "at": frappe.utils.now_datetime(),
            "actor": frappe.session.user,
            "service_date": service_date,
            "service_type": service_type,
            "result": result,
            "open_issues": open_issues,
            "next_action": next_action,
            "action_owner": action_owner,
            "due": due,
            "comment": comment,
            "warranty_start": warranty_start,
            "warranty_end": warranty_end,
            "service_contract": service_contract or "",
            "pm_cycle": pm_cycle or "",
        }).insert(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_history_insert")
        if not doc.last_service or date.fromisoformat(service_date) > date.fromisoformat(str(doc.last_service)):
            doc.last_service = service_date
        if "warrantyStart" in payload:
            doc.warranty_start = warranty_start
        if "warrantyEnd" in payload:
            doc.warranty_end = warranty_end
        if "serviceContract" in payload:
            doc.service_contract = service_contract or ""
        if "pmCycle" in payload:
            doc.pm_cycle = pm_cycle or ""
        doc.completeness = _calculate_completeness(doc)
        doc.save(ignore_permissions=True)
        if action_owner and action_owner != frappe.session.user:
            create_notification(
                recipient=action_owner, category="InstalledTool",
                title="Installed Tool service action assigned",
                message=f"{doc.serial}: {next_action} is due {due}.",
                route=f"/installed-tools?surface=detail&tool={doc.name}",
                source_doctype="CRM Installed Tool Service History", source_name=history.name,
            )
        if failure_injector:
            failure_injector("after_tool_update")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return get_installed_tool(doc.name)

def _validated_update(doc, payload: dict[str, Any]) -> dict[str, Any]:
    site_id = required_text(payload, "siteId")
    if not frappe.db.exists("Address", site_id) or _site_account(site_id) != doc.account:
        raise CrmApiException("SITE_ACCOUNT_MISMATCH", "The Site belongs to another Account.")
    engineer = _engineer_owner(payload.get("engineerOwner"))
    role = resolve_crm_role()
    if role == "Engineer" and engineer != doc.engineer_owner:
        raise CrmApiException("INSTALLED_TOOL_REASSIGN_DENIED", "Engineer cannot reassign Installed Tool ownership.")
    warranty_start = _optional_date(payload.get("warrantyStart"), "warrantyStart")
    warranty_end = _optional_date(payload.get("warrantyEnd"), "warrantyEnd")
    if warranty_start and warranty_end and date.fromisoformat(warranty_start) > date.fromisoformat(warranty_end):
        raise CrmApiException("VALIDATION_ERROR", "warrantyEnd must not be before warrantyStart.")
    return {
        "site": site_id,
        "serial": doc.serial,
        "model": required_text(payload, "model"),
        "location": required_text(payload, "location"),
        "engineer_owner": engineer,
        "operating_system": str(payload.get("operatingSystem") or "").strip(),
        "warranty_start": warranty_start,
        "warranty_end": warranty_end,
        "service_contract": str(payload.get("serviceContract") or "").strip(),
        "pm_cycle": str(payload.get("pmCycle") or "").strip(),
        "ownership_type": required_text(payload, "ownershipType"),
        "sales_order_reference": str(payload.get("salesOrder") or "").strip(),
        "contract_reference": str(payload.get("contract") or "").strip(),
    }


def update_installed_tool(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("installed_tool:write")
    current = _require_installed_tool(name)
    _assert_installed_tool_operator(current)
    doc = lock_document("CRM Installed Tool", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("INSTALLED_TOOL_SCOPE_DENIED", "The Installed Tool is outside the current user scope.")
    _assert_installed_tool_operator(doc)
    previous_engineer = doc.engineer_owner
    values = _validated_update(doc, payload)
    for fieldname, value in values.items():
        setattr(doc, fieldname, value)
    doc.completeness = _calculate_completeness(doc)
    savepoint = f"crm_installed_tool_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.save(ignore_permissions=True)
        if previous_engineer != doc.engineer_owner:
            frappe.get_doc({
                "doctype": "CRM Installed Tool Version History",
                "installed_tool": doc.name, "at": frappe.utils.now_datetime(),
                "actor": frappe.session.user, "change_date": frappe.utils.today(),
                "change_type": "Engineer Assignment", "from_value": previous_engineer,
                "to_value": doc.engineer_owner, "reason": "Manager reassignment",
                "comment": "Installed Tool owner changed",
            }).insert(ignore_permissions=True)
            if doc.engineer_owner != frappe.session.user:
                create_notification(
                    recipient=doc.engineer_owner, category="InstalledTool",
                    title="Installed Tool assigned",
                    message=f"You are now responsible for {doc.serial}.",
                    route=f"/installed-tools?surface=detail&tool={doc.name}",
                    source_doctype="CRM Installed Tool", source_name=doc.name,
                )
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("CONFLICT", "Installed Tool serial already exists.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_installed_tool(doc)
