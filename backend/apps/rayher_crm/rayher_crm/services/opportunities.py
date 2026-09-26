"""Lightweight CRM Opportunity strategy services."""

from __future__ import annotations

import json
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype, has_crm_permission
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
from rayher_crm.services.sites import _require_site, can_read_site_data
from rayher_crm.services.contacts import _contact_account
from rayher_crm.services.money import MoneyValidationError, as_decimal, decimal_string
from rayher_crm.services.notifications import create_notification


OPPORTUNITY_STAGES = ("需求发现", "Wafer Demo确认", "预算审批", "设备规格确认", "报价", "采购流程", "Won", "Lost")
DEMO_EVENT_TRANSITIONS = {
    "request_created": ("需求发现", "Wafer Demo确认"),
    "request_approved": ("Wafer Demo确认", "Wafer Demo确认"),
    "evaluation_accepted": ("Wafer Demo确认", "预算审批"),
}
COMMERCIAL_EVENT_TRANSITIONS = {
    "rfq_approved": ("设备规格确认", "报价"),
    "quotation_published": ("报价", "采购流程"),
}
MANUAL_STAGE_TRANSITIONS = {
    ("预算审批", "设备规格确认"),
    ("采购流程", "Won"),
}
STAGE_PROBABILITIES = {
    "需求发现": 15, "Wafer Demo确认": 55, "预算审批": 70, "设备规格确认": 75,
    "报价": 80, "采购流程": 90, "Won": 100, "Lost": 0,
}
FORECASTS = {"Pipeline", "Best Case", "Commit", "Closed"}
SALE_TYPES = {"New Equipment", "Repeat Order", "Service"}
LIST_FIELDS = ("payment_milestones", "strengths", "red_flags", "information_needed")


def delete_strategy_opportunity(name: str) -> dict[str, str]:
    return delete_manager_scoped_document("CRM Opportunity", name, "deal:write", "OPPORTUNITY_NOT_FOUND")
STAKEHOLDER_ROLES = (
    "Decision Maker", "Economic Buyer", "Technical Buyer", "User Buyer", "Coach",
    "Procurement", "Influencer", "Champion", "Technical Champion", "Primary Contact",
)
STAKEHOLDER_INFLUENCES = ("High", "Medium", "Low")
STAKEHOLDER_STANCES = ("Support", "Neutral", "Against")
ACTION_STATUSES = ("Open", "Done")


def _positive_money(value: Any, fieldname: str):
    try:
        parsed = as_decimal(value)
    except MoneyValidationError as exc:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be positive with at most two decimal places.") from exc
    if not parsed:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be positive with at most two decimal places.")
    return parsed


def _percentage(value: Any, fieldname: str) -> int:
    if isinstance(value, bool):
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be an integer from 0 to 100.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be an integer from 0 to 100.") from exc
    if str(value).strip() != str(parsed) or not 0 <= parsed <= 100:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be an integer from 0 to 100.")
    return parsed


def _calculate_opportunity_probability(stage: str, score: int) -> int:
    if stage == "Won":
        return 100
    if stage == "Lost":
        return 0
    return max(0, min(100, (STAGE_PROBABILITIES[stage] * 6 + score * 4 + 5) // 10))


def _string_list(value: Any, fieldname: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be an array of non-empty strings.")
    return [item.strip() for item in value]


def _decode_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _validate_opportunity(payload: dict[str, Any]) -> dict[str, Any]:
    account_id = required_text(payload, "accountId")
    site_id = required_text(payload, "siteId")
    _require_account(account_id)
    _require_site(site_id, account_id)

    currency = required_text(payload, "currency").upper()
    if not frappe.db.exists("Currency", currency):
        raise CrmApiException("VALIDATION_ERROR", "currency is invalid.", field_errors={"currency": "Invalid value"})
    po_date = optional_date(payload.get("poDate"), "poDate")
    if not po_date:
        raise CrmApiException("VALIDATION_ERROR", "poDate is required.", field_errors={"poDate": "Required"})

    amount = _positive_money(payload.get("amount"), "amount")
    original_amount = _positive_money(payload.get("originalAmount", amount), "originalAmount")
    stage = validate_choice(payload.get("stage"), "stage", OPPORTUNITY_STAGES)
    score = _percentage(payload.get("intentScore", 20), "intentScore")
    if "probability" in payload:
        _percentage(payload.get("probability"), "probability")
    return {
        "account": account_id,
        "site": site_id,
        "title": required_text(payload, "title"),
        "opportunity_owner": resolve_write_owner(payload.get("owner")),
        "stage": stage,
        "forecast": validate_choice(payload.get("forecast"), "forecast", FORECASTS),
        "amount": amount,
        "probability": _calculate_opportunity_probability(stage, score),
        "score": score,
        "po_date": po_date,
        "tool_type": required_text(payload, "toolType"),
        "sale_type": validate_choice(payload.get("saleType"), "saleType", SALE_TYPES),
        "sub_region": required_text(payload, "subRegion"),
        "currency": currency,
        "original_amount": original_amount,
        "shipment_date": optional_date(payload.get("shipmentDate"), "shipmentDate"),
        "fat_date": optional_date(payload.get("fatDate"), "fatDate"),
        "payment_milestones": _string_list(payload.get("paymentMilestones"), "paymentMilestones"),
        "competition": str(payload.get("competition") or "").strip(),
        "win_reason": str(payload.get("winReason") or "").strip(),
        "lost_reason": str(payload.get("lostReason") or "").strip(),
        "strengths": _string_list(payload.get("strengths"), "strengths"),
        "red_flags": _string_list(payload.get("redFlags"), "redFlags"),
        "information_needed": _string_list(payload.get("informationNeeded"), "informationNeeded"),
    }


def _history_for_opportunity(opportunity_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CRM Opportunity History",
        filters={"opportunity": opportunity_id},
        fields=["actor", "at", "field", "from_value", "to_value"],
        order_by="at desc, creation desc",
    )
    return [
        {
            "at": to_iso_timestamp(row.at),
            "actor": row.actor,
            "field": row.field,
            "from": row.from_value or "",
            "to": row.to_value or "",
        }
        for row in rows
    ]


def _stakeholders_for_opportunity(opportunity_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CRM Opportunity Stakeholder",
        filters={"opportunity": opportunity_id, "archived": 0},
        fields=["name", "contact", "role", "influence", "stance", "coverage", "is_coach", "win_result", "opportunity_notes"],
        order_by="creation asc",
    )
    result = []
    for row in rows:
        contact = frappe.db.get_value("Contact", row.contact, ["first_name", "last_name", "designation"], as_dict=True)
        display_name = " ".join(part for part in ((contact.first_name if contact else ""), (contact.last_name if contact else "")) if part).strip()
        result.append({
            "id": row.name,
            "contactId": row.contact,
            "name": display_name or row.contact,
            "title": contact.designation if contact else "",
            "role": row.role,
            "influence": row.influence,
            "stance": row.stance,
            "coverage": row.coverage,
            "isCoach": bool(row.is_coach),
            "winResult": row.win_result or "",
            "opportunityNotes": row.opportunity_notes or "",
        })
    return result


def _actions_for_opportunity(opportunity_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CRM Opportunity Action",
        filters={"opportunity": opportunity_id, "archived": 0},
        fields=["name", "title", "action_owner", "due", "status", "remark"],
        order_by="creation asc",
    )
    return [{
        "id": row.name,
        "title": row.title,
        "owner": row.action_owner,
        "due": str(row.due or ""),
        "status": row.status,
        "remark": row.remark or "",
    } for row in rows]


def serialize_opportunity(doc) -> dict[str, Any]:
    role = resolve_crm_role()
    can_read_site = can_read_site_data(doc.account)
    exact_amounts = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR) AS `amount`, CAST(`original_amount` AS CHAR) AS `original_amount` "
        "FROM `tabCRM Opportunity` WHERE `name` = %s",
        (doc.name,), as_dict=True,
    )
    exact = exact_amounts[0] if exact_amounts else None
    result = {
        "id": doc.name,
        "accountId": doc.account,
        "siteId": doc.site if can_read_site else "",
        "siteRestricted": not can_read_site,
        "title": doc.title,
        "account": frappe.db.get_value("Customer", doc.account, "customer_name") or doc.account,
        "site": (frappe.db.get_value("Address", doc.site, "address_title") or doc.site) if can_read_site else "",
        "owner": doc.opportunity_owner,
        "stage": doc.stage,
        "forecast": doc.forecast,
        "amount": decimal_string(exact.amount if exact else doc.amount or 0),
        "probability": int(doc.probability or 0),
        "poDate": str(doc.po_date or ""),
        "updated": to_iso_timestamp(doc.modified),
        "modified": to_iso_timestamp(doc.modified),
        "score": int(doc.score or 0),
        "toolType": doc.tool_type,
        "saleType": doc.sale_type,
        "subRegion": doc.sub_region,
        "currency": doc.currency,
        "originalAmount": decimal_string(exact.original_amount if exact else doc.original_amount or 0),
        "shipmentDate": str(doc.shipment_date or ""),
        "fatDate": str(doc.fat_date or ""),
        "paymentMilestones": _decode_list(doc.payment_milestones),
        "competition": doc.competition or "",
        "winReason": doc.win_reason or "",
        "lostReason": doc.lost_reason or "",
        "history": _history_for_opportunity(doc.name),
        "strengths": _decode_list(doc.strengths),
        "redFlags": _decode_list(doc.red_flags),
        "informationNeeded": _decode_list(doc.information_needed),
        # Engineers can work the opportunity but do not have contact/stakeholder access.
        "stakeholders": _stakeholders_for_opportunity(doc.name) if role in {"Manager", "Sales"} else [],
        "actions": _actions_for_opportunity(doc.name),
    }
    if doc.source_lead:
        result["sourceLeadId"] = doc.source_lead
    return result


def _require_opportunity(name: str):
    if not frappe.db.exists("CRM Opportunity", name):
        raise CrmApiException("OPPORTUNITY_NOT_FOUND", "Opportunity was not found.")
    doc = frappe.get_doc("CRM Opportunity", name)
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")
    return doc


def list_strategy_opportunities(query: dict[str, Any] | None = None):
    assert_capability("deal:view")
    where_parts = [f"({conditions_for_doctype('CRM Opportunity')})"]
    values: list[Any] = []
    where = where_parts[0]
    if query is None:
        rows = frappe.db.sql(
            f"SELECT `name` FROM `tabCRM Opportunity` WHERE {where} ORDER BY `modified` DESC, `name` DESC",
            as_dict=True,
        )
        return [serialize_opportunity(frappe.get_doc("CRM Opportunity", row.name)) for row in rows]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        if resolve_crm_role() == "Sales":
            where_parts.append(
                "(`name` LIKE %s OR `title` LIKE %s OR `account` LIKE %s OR "
                "(`site` LIKE %s AND EXISTS ("
                "SELECT 1 FROM `tabCustomer` AS `crm_site_search_customer` "
                "WHERE `crm_site_search_customer`.`name` = `tabCRM Opportunity`.`account` "
                "AND `crm_site_search_customer`.`custom_crm_owner` = %s)))"
            )
            values.extend([pattern, pattern, pattern, pattern, frappe.session.user])
        else:
            where_parts.append("(`name` LIKE %s OR `title` LIKE %s OR `account` LIKE %s OR `site` LIKE %s)")
            values.extend([pattern, pattern, pattern, pattern])
    for input_name, column in (("status", "stage"), ("forecast", "forecast"), ("owner", "opportunity_owner"), ("accountId", "account")):
        value = str(query.get(input_name) or "").strip()
        if value and value != "All":
            where_parts.append(f"`{column}` = %s")
            values.append(value)
    contact_id = str(query.get("contactId") or "").strip()
    if contact_id:
        where_parts.append("EXISTS (SELECT 1 FROM `tabCRM Opportunity Stakeholder` stakeholder WHERE stakeholder.`opportunity` = `tabCRM Opportunity`.`name` AND stakeholder.`contact` = %s AND stakeholder.`archived` = 0)")
        values.append(contact_id)
    opportunity_id = str(query.get("opportunityId") or "").strip()
    if opportunity_id:
        where_parts.append("`name` = %s")
        values.append(opportunity_id)
    where = " AND ".join(where_parts)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Opportunity` WHERE {where}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Opportunity` WHERE {where} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]), as_dict=True,
    )
    return [serialize_opportunity(frappe.get_doc("CRM Opportunity", row.name)) for row in rows], total, page, page_size


def get_strategy_opportunity(name: str) -> dict[str, Any]:
    assert_capability("deal:view")
    return serialize_opportunity(_require_opportunity(name))


def opportunities_for_account(account_id: str) -> list[dict[str, Any]]:
    _require_account(account_id)
    return [item for item in list_strategy_opportunities() if item["accountId"] == account_id]


def create_strategy_opportunity(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:write")
    ensure_server_generated_id(payload)
    values = _validate_opportunity(payload)
    if values["stage"] != OPPORTUNITY_STAGES[0]:
        raise CrmApiException("INVALID_TRANSITION", f"New Opportunity must start at {OPPORTUNITY_STAGES[0]}.")
    for fieldname in LIST_FIELDS:
        values[fieldname] = json.dumps(values[fieldname], ensure_ascii=False)
    doc = frappe.get_doc({"doctype": "CRM Opportunity", **values}).insert(ignore_permissions=True)
    return serialize_opportunity(doc)


def _current_input(doc) -> dict[str, Any]:
    exact_amount = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR), CAST(`original_amount` AS CHAR) "
        "FROM `tabCRM Opportunity` WHERE `name` = %s",
        (doc.name,),
    )[0]
    return {
        "accountId": doc.account,
        "siteId": doc.site,
        "title": doc.title,
        "owner": doc.opportunity_owner,
        "stage": doc.stage,
        "forecast": doc.forecast,
        "amount": exact_amount[0],
        "probability": doc.probability,
        "intentScore": doc.score,
        "poDate": str(doc.po_date or ""),
        "toolType": doc.tool_type,
        "saleType": doc.sale_type,
        "subRegion": doc.sub_region,
        "currency": doc.currency,
        "originalAmount": exact_amount[1],
        "shipmentDate": str(doc.shipment_date or ""),
        "fatDate": str(doc.fat_date or ""),
        "paymentMilestones": _decode_list(doc.payment_milestones),
        "competition": doc.competition or "",
        "winReason": doc.win_reason or "",
        "lostReason": doc.lost_reason or "",
        "strengths": _decode_list(doc.strengths),
        "redFlags": _decode_list(doc.red_flags),
        "informationNeeded": _decode_list(doc.information_needed),
    }


def _history_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def update_strategy_opportunity(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    _require_opportunity(name)
    doc = lock_document("CRM Opportunity", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")

    merged = _current_input(doc)
    merged.update(payload)
    values = _validate_opportunity(merged)
    next_stage = values["stage"]
    if next_stage == "Lost" and not values["lost_reason"]:
        raise CrmApiException("VALIDATION_ERROR", "Lost Reason is required when closing an Opportunity as Lost.", field_errors={"lostReason": "Required"})
    if next_stage != doc.stage:
        if doc.stage in {"Won", "Lost"}:
            raise CrmApiException("INVALID_TRANSITION", "A closed Opportunity stage cannot be changed.")
        if next_stage != "Lost" and (doc.stage, next_stage) not in MANUAL_STAGE_TRANSITIONS:
            raise CrmApiException("INVALID_TRANSITION", f"Opportunity cannot move from {doc.stage} to {next_stage}.")

    changes: list[tuple[str, Any, Any]] = []
    for fieldname, value in values.items():
        current = _decode_list(getattr(doc, fieldname)) if fieldname in LIST_FIELDS else getattr(doc, fieldname)
        stored = json.dumps(value, ensure_ascii=False) if fieldname in LIST_FIELDS else value
        changed = current != value if fieldname in LIST_FIELDS else str(current or "") != str(value or "")
        if changed:
            changes.append((fieldname, current, value))
            setattr(doc, fieldname, stored)

    doc.save(ignore_permissions=True)
    for fieldname, before, after in changes:
        frappe.get_doc(
            {
                "doctype": "CRM Opportunity History",
                "opportunity": doc.name,
                "actor": frappe.session.user,
                "at": frappe.utils.now_datetime(),
                "field": fieldname,
                "from_value": _history_value(before),
                "to_value": _history_value(after),
            }
        ).insert(ignore_permissions=True)
    doc.reload()
    return serialize_opportunity(doc)


def _append_history(opportunity_id: str, fieldname: str, before: Any, after: Any) -> None:
    frappe.get_doc({
        "doctype": "CRM Opportunity History",
        "opportunity": opportunity_id,
        "actor": frappe.session.user,
        "at": frappe.utils.now_datetime(),
        "field": fieldname,
        "from_value": _history_value(before),
        "to_value": _history_value(after),
    }).insert(ignore_permissions=True)


def rollback_opportunity_stage(
    name: str,
    target_stage: Any,
    reason: Any,
    expected_modified: Any,
) -> dict[str, Any]:
    assert_capability("deal:rollback")
    target = validate_choice(target_stage, "targetStage", OPPORTUNITY_STAGES)
    rollback_reason = required_text({"reason": reason}, "reason")
    _require_opportunity(name)
    doc = lock_document("CRM Opportunity", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")
    if target in {"Won", "Lost"} or OPPORTUNITY_STAGES.index(target) >= OPPORTUNITY_STAGES.index(doc.stage):
        raise CrmApiException(
            "INVALID_TRANSITION",
            "Rollback target must be an earlier actionable stage.",
        )
    if target == "需求发现" and frappe.db.exists(
        "CRM Demo Request",
        {"opportunity": doc.name, "status": ["not in", ["Cancelled", "Converted"]]},
    ):
        raise CrmApiException(
            "CONFLICT",
            "Cancel the active Demo Request before rolling the Opportunity back to 需求发现.",
        )

    savepoint = f"crm_opportunity_rollback_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        previous_stage = doc.stage
        previous_probability = int(doc.probability or 0)
        doc.stage = target
        doc.probability = _calculate_opportunity_probability(target, int(doc.score or 0))
        doc.save(ignore_permissions=True)
        if (
            OPPORTUNITY_STAGES.index(previous_stage) >= OPPORTUNITY_STAGES.index("报价")
            and OPPORTUNITY_STAGES.index(target) <= OPPORTUNITY_STAGES.index("设备规格确认")
        ):
            from rayher_crm.services.rfqs import reopen_approved_rfq_for_stage_rollback

            reopen_approved_rfq_for_stage_rollback(doc.name, rollback_reason)
        _append_history(doc.name, "stageRollback", previous_stage, f"{target} | {rollback_reason}")
        if int(doc.probability or 0) != previous_probability:
            _append_history(doc.name, "probability", previous_probability, int(doc.probability or 0))
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_opportunity(doc)


def _advance_opportunity_for_event(
    opportunity_id: str,
    event: str,
    transitions: dict[str, tuple[str, str]],
) -> None:
    rows = frappe.db.sql(
        "SELECT `name` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE",
        (opportunity_id,),
    )
    if not rows:
        raise CrmApiException("OPPORTUNITY_NOT_FOUND", "Opportunity was not found.")
    doc = frappe.get_doc("CRM Opportunity", opportunity_id)
    expected_stage, target_stage = transitions[event]
    if doc.stage == "Lost":
        raise CrmApiException("INVALID_TRANSITION", "A Lost Opportunity cannot be advanced by workflow completion.")
    if doc.stage == target_stage:
        return
    current_index = OPPORTUNITY_STAGES.index(doc.stage)
    target_index = OPPORTUNITY_STAGES.index(target_stage)
    if current_index > target_index:
        return
    if doc.stage != expected_stage:
        raise CrmApiException(
            "CONFLICT",
            f"Opportunity must be in {expected_stage} before workflow completion can move it to {target_stage}.",
        )

    before_probability = int(doc.probability or 0)
    doc.stage = target_stage
    doc.probability = _calculate_opportunity_probability(target_stage, int(doc.score or 0))
    doc.save(ignore_permissions=True)
    _append_history(doc.name, "stage", expected_stage, target_stage)
    if int(doc.probability or 0) != before_probability:
        _append_history(doc.name, "probability", before_probability, int(doc.probability or 0))


def advance_opportunity_for_demo_event(opportunity_id: str, event: str) -> None:
    """Advance one server-owned Demo gate without exposing a target stage to clients."""

    if event not in DEMO_EVENT_TRANSITIONS:
        raise ValueError(f"Unknown Demo opportunity event: {event}")
    _advance_opportunity_for_event(opportunity_id, event, DEMO_EVENT_TRANSITIONS)


def advance_opportunity_for_commercial_event(opportunity_id: str, event: str) -> None:
    """Advance an RFQ or quotation gate only after its server workflow completes."""

    if event not in COMMERCIAL_EVENT_TRANSITIONS:
        raise ValueError(f"Unknown commercial opportunity event: {event}")
    _advance_opportunity_for_event(opportunity_id, event, COMMERCIAL_EVENT_TRANSITIONS)


def _lock_relation(doctype: str, name: str, opportunity_id: str, missing_code: str):
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tab{doctype}` WHERE `name` = %s AND `opportunity` = %s FOR UPDATE",
        (name, opportunity_id),
        as_dict=True,
    )
    if not rows:
        raise CrmApiException(missing_code, f"{doctype.removeprefix('CRM Opportunity ')} was not found.")
    doc = frappe.get_doc(doctype, name)
    if doc.archived:
        raise CrmApiException(missing_code, f"{doctype.removeprefix('CRM Opportunity ')} was not found.")
    return doc


def _validate_stakeholder(opportunity, payload: dict[str, Any], stakeholder_id: str | None = None) -> dict[str, Any]:
    contact_id = required_text(payload, "contactId")
    if not frappe.db.exists("Contact", contact_id):
        raise CrmApiException("CONTACT_NOT_FOUND", "Contact was not found.")
    contact = frappe.get_doc("Contact", contact_id)
    if _contact_account(contact_id) != opportunity.account:
        raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "The contact belongs to another account.")
    if contact.custom_crm_status != "Active":
        raise CrmApiException("CONTACT_INACTIVE", "The contact must be active.")
    duplicate_filters = {"opportunity": opportunity.name, "contact": contact_id, "archived": 0}
    duplicate = frappe.db.get_value("CRM Opportunity Stakeholder", duplicate_filters, "name")
    if duplicate and duplicate != stakeholder_id:
        raise CrmApiException("DUPLICATE_OPPORTUNITY_CONTACT", "The contact is already a live stakeholder.")
    return {
        "contact": contact_id,
        "role": validate_choice(payload.get("role"), "role", STAKEHOLDER_ROLES),
        "influence": validate_choice(payload.get("influence"), "influence", STAKEHOLDER_INFLUENCES),
        "stance": validate_choice(payload.get("stance"), "stance", STAKEHOLDER_STANCES),
        "coverage": required_text(payload, "coverage"),
        "is_coach": 1 if payload.get("isCoach") else 0,
        "win_result": str(payload.get("winResult") or "").strip(),
        "opportunity_notes": str(payload.get("opportunityNotes") or "").strip(),
    }


def _serialize_stakeholder(doc) -> dict[str, Any]:
    return next(item for item in _stakeholders_for_opportunity(doc.opportunity) if item["id"] == doc.name)


def create_opportunity_stakeholder(opportunity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("stakeholder:write")
    ensure_server_generated_id(payload)
    opportunity = _require_opportunity(opportunity_id)
    values = _validate_stakeholder(opportunity, payload)
    doc = frappe.get_doc({
        "doctype": "CRM Opportunity Stakeholder", "opportunity": opportunity_id, **values,
    }).insert(ignore_permissions=True)
    _append_history(opportunity_id, "stakeholderCreated", "", doc.name)
    return _serialize_stakeholder(doc)


def update_opportunity_stakeholder(opportunity_id: str, stakeholder_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("stakeholder:write")
    opportunity = _require_opportunity(opportunity_id)
    doc = _lock_relation("CRM Opportunity Stakeholder", stakeholder_id, opportunity_id, "STAKEHOLDER_NOT_FOUND")
    values = _validate_stakeholder(opportunity, payload, stakeholder_id)
    for fieldname, value in values.items():
        setattr(doc, fieldname, value)
    doc.save(ignore_permissions=True)
    _append_history(opportunity_id, "stakeholderUpdated", stakeholder_id, stakeholder_id)
    return _serialize_stakeholder(doc)


def delete_opportunity_stakeholder(opportunity_id: str, stakeholder_id: str) -> dict[str, str]:
    assert_capability("stakeholder:write")
    _require_opportunity(opportunity_id)
    doc = _lock_relation("CRM Opportunity Stakeholder", stakeholder_id, opportunity_id, "STAKEHOLDER_NOT_FOUND")
    doc.archived = 1
    doc.save(ignore_permissions=True)
    _append_history(opportunity_id, "stakeholderDeleted", "", stakeholder_id)
    return {"id": stakeholder_id}


def _action_remark(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > 10000:
        raise CrmApiException("VALIDATION_ERROR", "Remark must be text of at most 10000 characters.")
    return value.strip()


def _validate_action(payload: dict[str, Any], opportunity) -> dict[str, Any]:
    due = optional_date(payload.get("due"), "due")
    if not due:
        raise CrmApiException("VALIDATION_ERROR", "due is required.", field_errors={"due": "Required"})
    action_owner = resolve_write_owner(payload.get("owner"))
    if not has_crm_permission(opportunity, user=action_owner, permission_type="read"):
        raise CrmApiException(
            "INVALID_OWNER", "Action owner must have access to this Opportunity.",
        )
    return {
        "title": required_text(payload, "title"),
        "action_owner": action_owner,
        "due": due,
        "status": validate_choice(payload.get("status"), "status", ACTION_STATUSES),
        "remark": _action_remark(payload.get("remark")),
    }


def _serialize_action(doc) -> dict[str, Any]:
    return {
        "id": doc.name, "title": doc.title, "owner": doc.action_owner,
        "due": str(doc.due or ""), "status": doc.status, "remark": doc.remark or "",
    }


def create_opportunity_action(opportunity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:write")
    ensure_server_generated_id(payload)
    opportunity = _require_opportunity(opportunity_id)
    savepoint = f"crm_opportunity_action_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc = frappe.get_doc({
            "doctype": "CRM Opportunity Action", "opportunity": opportunity_id,
            **_validate_action(payload, opportunity),
        }).insert(ignore_permissions=True)
        serialized = _serialize_action(doc)
        _append_history(opportunity_id, "actionCreated", "", serialized)
        if doc.action_owner != frappe.session.user:
            create_notification(
                recipient=doc.action_owner, category="Action",
                title="Opportunity action assigned",
                message=f"{doc.title} is due {doc.due}.",
                route=f"/opportunities/{opportunity_id}",
                source_doctype="CRM Opportunity Action", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return _serialize_action(doc)


def update_opportunity_action(opportunity_id: str, action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:write")
    opportunity = _require_opportunity(opportunity_id)
    doc = _lock_relation("CRM Opportunity Action", action_id, opportunity_id, "ACTION_NOT_FOUND")
    before = _serialize_action(doc)
    payload = {"remark": doc.remark or "", **payload}
    savepoint = f"crm_opportunity_action_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        for fieldname, value in _validate_action(payload, opportunity).items():
            setattr(doc, fieldname, value)
        doc.save(ignore_permissions=True)
        after = _serialize_action(doc)
        _append_history(opportunity_id, "actionUpdated", before, after)
        if doc.action_owner != frappe.session.user:
            create_notification(
                recipient=doc.action_owner, category="Action",
                title="Opportunity action updated",
                message=f"{doc.title} is due {doc.due} and is {doc.status}.",
                route=f"/opportunities/{opportunity_id}",
                source_doctype="CRM Opportunity Action", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return _serialize_action(doc)


def delete_opportunity_action(opportunity_id: str, action_id: str) -> dict[str, str]:
    assert_capability("deal:write")
    _require_opportunity(opportunity_id)
    doc = _lock_relation("CRM Opportunity Action", action_id, opportunity_id, "ACTION_NOT_FOUND")
    doc.archived = 1
    doc.save(ignore_permissions=True)
    _append_history(opportunity_id, "actionDeleted", "", action_id)
    return {"id": action_id}
