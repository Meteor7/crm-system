"""Lightweight CRM Opportunity strategy services."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import OPPORTUNITY_CHILD_DOCTYPES, conditions_for_doctype, has_crm_permission
from rayher_crm.services.accounts import _require_account
from rayher_crm.services.common import (
    delete_manager_scoped_document,
    ensure_server_generated_id,
    normalize_expected_modified,
    normalize_pagination,
    optional_date,
    required_text,
    resolve_write_owner,
    to_iso_timestamp,
    validate_choice,
)
from rayher_crm.services.bookings import validate_actual_po_date
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.sites import _require_site, can_read_site_data
from rayher_crm.services.contacts import _contact_account
from rayher_crm.services.equipment import normalize_equipment, register_equipment
from rayher_crm.services.money import (
    MoneyValidationError,
    as_decimal,
    optional_money_text,
    required_positive_money,
)
from rayher_crm.services.notifications import active_crm_users, create_notification, notify_if_reachable
from rayher_crm.services.opportunity_bookings import (
    booking_amount,
    booking_amount_cny,
    confirm_pending_booking,
    create_opportunity_booking,
    live_booking,
    replaced_booking,
    validate_booking_draft,
)
from rayher_crm.services.opportunity_stages import (
    AUTOMATIC_STAGE_EVENTS,
    CLOSED_STAGES,
    CUSTOMER_BUDGET_APPROVED,
    DEMO_DONE,
    INTERNAL_VALIDATION,
    LOST,
    MILESTONE_STAGES,
    OPEN_STAGES,
    OPPORTUNITY_STAGES,
    PO_CONFIRMABLE_STAGES,
    PO_RECEIVED,
    PROBABILITY_LEVEL_CHOICES,
    QUALIFIED_OPPORTUNITY,
    QUOTATION_SENT,
    probability_level_rank,
    stage_index,
)
from rayher_crm.services.regions import resolve_region
from rayher_crm.services.probability_recovery import create_recovery, notify_downgrade, plan_text, plans_for_opportunity, plans_for_opportunities
from rayher_crm.services.loss_review import create_loss_review, mark_reopened, reviews_for_opportunities, reviews_for_opportunity


SALE_TYPES = {"New Equipment", "Repeat Order", "Service"}
LIST_FIELDS = ("payment_milestones", "strengths", "red_flags", "information_needed")
# Compared as decimals, so an amount saved again unchanged is not recorded as an edit.
MONEY_FIELDS = ("amount", "original_amount", "amount_cny")
# An Opportunity carries a value from Demo done on (#22); before that its amount may be unknown.
AMOUNT_REQUIRED = "Required from Demo done"
AMOUNT_REQUIRED_MESSAGE = "The amount and the amount in CNY are required from Demo done."
# Stage history note of a Demo done that waited for the amount until the owner saved it.
PENDING_AMOUNT_REASON = "Demo done pending amount"


def delete_strategy_opportunity(name: str) -> dict[str, str]:
    savepoint = f"crm_opportunity_delete_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        # Lock the Opportunity first, the order the Opportunity's own writers take it in (stage moves,
        # stakeholders, actions, post-mortems, recovery plans, overdue and S6 warning handling): a write
        # racing this delete lands before it and is removed with the rest, or finds the Opportunity gone.
        # Rows written under a Quotation or a Booking (quotation warnings, booking history) lock that record
        # instead; while it links to the Opportunity, frappe.delete_doc below refuses the delete anyway.
        frappe.db.get_value("CRM Opportunity", name, "name", for_update=True)
        # History and internal validation rows link to the Opportunity; remove them first or
        # the link check in frappe.delete_doc reports the Opportunity as still referenced.
        # The field history, stakeholders and actions belong to this Opportunity alone (the
        # relation APIs only archive their rows), so they go with it too.
        for doctype in (
            *OPPORTUNITY_CHILD_DOCTYPES,
            "CRM Opportunity History",
            "CRM Opportunity Stakeholder",
            "CRM Opportunity Action",
        ):
            frappe.db.delete(doctype, {"opportunity": name})
        # The notice of a Demo done waiting for the amount names the Opportunity itself. A notification
        # cannot be deleted as a document and its link would refuse the delete below, so it is removed here.
        frappe.db.delete("CRM Notification Event", {"source_doctype": "CRM Opportunity", "source_name": name})
        # Warnings handling names the Opportunity in a Data field, so it never blocks the delete; it goes too.
        # A locking read: the current rows, not this request's snapshot.
        handlings = [row[0] for row in frappe.db.sql(
            "SELECT `name` FROM `tabCRM Warning Handling` WHERE `opportunity` = %s FOR UPDATE", (name,))]
        if handlings:
            frappe.db.delete("CRM Warning Handling Revision", {"handling": ["in", handlings]})
            frappe.db.delete("CRM Warning Handling", {"name": ["in", handlings]})
        return delete_manager_scoped_document("CRM Opportunity", name, "deal:write", "OPPORTUNITY_NOT_FOUND")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


STAKEHOLDER_ROLES = (
    "Decision Maker", "Economic Buyer", "Technical Buyer", "User Buyer", "Coach",
    "Procurement", "Influencer", "Champion", "Technical Champion", "Primary Contact",
)
STAKEHOLDER_INFLUENCES = ("High", "Medium", "Low")
STAKEHOLDER_STANCES = ("Support", "Neutral", "Against")
# Blank is "not recorded yet", which every stakeholder from before the field starts as.
STAKEHOLDER_RESPONSE_MODES = ("", "Growth", "Trouble", "Even Keel", "Overconfident")
# A Small Text column holds far more than anyone writes; the limit keeps an overlong value a field error.
# Keep it in step with MAX_OBJECTIVE_LENGTH and oppEditor.objectiveTooLong in the front end, and with generated-error-messages.ts.
MAX_SINGLE_SALES_OBJECTIVE = 2000
ACTION_STATUSES = ("Open", "Done")


def _positive_money(value: Any, fieldname: str):
    # The same field hint as required_positive_money, so the form marks the amount and not only a message.
    message = f"{fieldname} must be positive with at most two decimal places."
    try:
        parsed = as_decimal(value)
    except MoneyValidationError as exc:
        raise CrmApiException("VALIDATION_ERROR", message, field_errors={fieldname: "Invalid amount"}) from exc
    if not parsed:
        raise CrmApiException("VALIDATION_ERROR", message, field_errors={fieldname: "Invalid amount"})
    return parsed


def _optional_positive_money(value: Any, fieldname: str, invalid=_positive_money) -> Decimal:
    """Like _positive_money, but blank or zero means "not entered yet"; stored as 0.00.

    Only a qualified (S1) Opportunity may leave its amounts unknown. `value` arrives blank from a
    fresh payload (None or ""), as a Decimal computed earlier in this call (the originalAmount
    fallback), or as the "0.00" that `_current_input()` reads back on every edit of an Opportunity
    that has no amount yet. Anything that is not an exact amount with at most two decimal places
    still fails, with the error `invalid` raises for it.
    """
    if value is None or str(value).strip() == "":
        return Decimal("0.00")
    try:
        return as_decimal(value)
    except MoneyValidationError:
        return invalid(value, fieldname)


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


def _tool_type(payload: dict[str, Any], current: str | None) -> str:
    submitted = payload.get("toolType")
    # Saving without touching the type keeps its stored spelling, including one from before the catalog.
    if current and isinstance(submitted, str) and submitted.strip() == current.strip():
        return current
    return normalize_equipment(submitted, "toolType")


def _single_sales_objective(value: Any, stored: str | None = None) -> str:
    text = str(value or "").strip()
    # A value that is already stored stays valid: Frappe's HTML cleaning of Small Text can lengthen it past the
    # limit, and an unrelated edit must not fail because of it. Only a changed value is held to the limit.
    if len(text) > MAX_SINGLE_SALES_OBJECTIVE and (stored is None or text != stored.strip()):
        raise CrmApiException(
            "VALIDATION_ERROR", "singleSalesObjective is too long.",
            field_errors={"singleSalesObjective": f"Maximum length is {MAX_SINGLE_SALES_OBJECTIVE}"},
        )
    return text


def cny_amount_for(currency: str, amount: Decimal, amount_cny: Decimal) -> Decimal:
    """A CNY Opportunity has one amount (#87): its CNY amount is that amount, whatever was sent with it."""

    return amount if currency == "CNY" else amount_cny


# API field and column of each amount an Opportunity needs from Demo done on; every edit past S1 requires all three.
GATED_AMOUNTS = (("amount", "amount"), ("originalAmount", "original_amount"), ("amountCny", "amount_cny"))


def _missing_amounts(doc) -> list[str]:
    return [field for field, column in GATED_AMOUNTS if frappe.utils.flt(doc.get(column)) <= 0]


def _has_amounts(doc) -> bool:
    return not _missing_amounts(doc)


def _assert_amounts_for_stage(doc, stage: str) -> None:
    """Every way forward into Demo done or a later milestone needs the amount and the CNY amount."""

    if stage not in MILESTONE_STAGES or stage_index(stage) < stage_index(DEMO_DONE):
        return
    missing = _missing_amounts(doc)
    if missing:
        raise CrmApiException(
            "VALIDATION_ERROR", AMOUNT_REQUIRED_MESSAGE, field_errors={field: AMOUNT_REQUIRED for field in missing},
        )


def _validate_opportunity(
    payload: dict[str, Any], current_tool_type: str | None = None, stored_objective: str | None = None,
    *, require_amount: bool = True,
) -> dict[str, Any]:
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

    if require_amount:
        amount = _positive_money(payload.get("amount"), "amount")
        original_amount = _positive_money(payload.get("originalAmount", amount), "originalAmount")
    else:
        amount = _optional_positive_money(payload.get("amount"), "amount")
        original_amount = _optional_positive_money(payload.get("originalAmount", amount), "originalAmount")
        # An amount entered without an original amount is its own original, as when the key is left out:
        # otherwise the Opportunity would pass S1 and then fail every edit on the missing original amount.
        if amount and not original_amount:
            original_amount = amount
    if require_amount and currency != "CNY":
        entered_cny = required_positive_money(payload.get("amountCny"), "amountCny")
    else:
        # Still checked as money when it is sent, also for a CNY Opportunity that will not store it.
        entered_cny = _optional_positive_money(payload.get("amountCny"), "amountCny", required_positive_money)
    amount_cny = cny_amount_for(currency, amount, entered_cny)
    stage = validate_choice(payload.get("stage"), "stage", OPPORTUNITY_STAGES)
    score = _percentage(payload.get("intentScore", 20), "intentScore")
    return {
        "account": account_id,
        "site": site_id,
        "title": required_text(payload, "title"),
        "opportunity_owner": resolve_write_owner(payload.get("owner")),
        "stage": stage,
        "probability_level": validate_choice(
            payload.get("probabilityLevel") or "", "probabilityLevel", PROBABILITY_LEVEL_CHOICES,
        ),
        "amount": amount,
        "score": score,
        "po_date": po_date,
        "tool_type": _tool_type(payload, current_tool_type),
        "sale_type": validate_choice(payload.get("saleType"), "saleType", SALE_TYPES),
        "sub_region": resolve_region(payload.get("subRegion"), "subRegion"),
        "currency": currency,
        "original_amount": original_amount,
        "amount_cny": amount_cny,
        "shipment_date": optional_date(payload.get("shipmentDate"), "shipmentDate"),
        "fat_date": optional_date(payload.get("fatDate"), "fatDate"),
        "payment_milestones": _string_list(payload.get("paymentMilestones"), "paymentMilestones"),
        "competition": str(payload.get("competition") or "").strip(),
        "single_sales_objective": _single_sales_objective(payload.get("singleSalesObjective"), stored_objective),
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


def _probability_history_for_opportunity(opportunity_id: str, recoveries=None) -> list[dict[str, Any]]:
    if recoveries is None:
        recoveries = plans_for_opportunity(opportunity_id)
    rows = frappe.get_all(
        "CRM Opportunity Probability History",
        filters={"opportunity": opportunity_id},
        fields=["name", "actor", "changed_at", "from_level", "to_level", "reason"],
        order_by="changed_at desc, creation desc",
    )
    return [
        {
            "id": row.name,
            "from": row.from_level or "",
            "to": row.to_level or "",
            "reason": row.reason or "",
            "actor": row.actor,
            "at": to_iso_timestamp(row.changed_at),
            "recovery": recoveries.get(row.name),
        }
        for row in rows
    ]


def _stage_history_for_opportunity(opportunity_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CRM Opportunity Stage History",
        filters={"opportunity": opportunity_id},
        fields=[
            "name", "from_stage", "to_stage", "source", "event", "reference_doctype", "reference_name",
            "reason", "actor", "recorded_at", "reached_at", "reached_at_basis",
        ],
        order_by="recorded_at desc, creation desc",
    )
    return [
        {
            "id": row.name,
            "from": row.from_stage or "",
            "to": row.to_stage,
            "source": row.source,
            "event": row.event,
            "referenceDoctype": row.reference_doctype or "",
            "referenceName": row.reference_name or "",
            "reason": row.reason or "",
            "actor": row.actor,
            "recordedAt": to_iso_timestamp(row.recorded_at),
            "reachedAt": to_iso_timestamp(row.reached_at) if row.reached_at else "",
            "reachedAtBasis": row.reached_at_basis,
        }
        for row in rows
    ]


def _latest_internal_validation(opportunity_id: str) -> dict[str, Any] | None:
    rows = frappe.get_all(
        "CRM Opportunity Internal Validation",
        filters={"opportunity": opportunity_id},
        fields=[
            "name", "attempt_no", "status", "reason", "expected_po_date", "booking_draft", "requested_by",
            "requested_at", "decided_by", "decided_at", "decision_comment", "booking", "cancelled_by",
            "cancelled_at", "cancel_reason",
        ],
        order_by="attempt_no desc",
        limit=1,
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "id": row.name,
        "attemptNo": int(row.attempt_no or 0),
        "status": row.status,
        "reason": row.reason or "",
        "expectedPoDate": str(row.expected_po_date or ""),
        "booking": _decode_object(row.booking_draft),
        "requestedBy": row.requested_by,
        "requestedAt": to_iso_timestamp(row.requested_at),
        "decidedBy": row.decided_by or "",
        "decidedAt": to_iso_timestamp(row.decided_at) if row.decided_at else "",
        "decisionComment": row.decision_comment or "",
        "bookingId": row.booking or "",
        "cancelledBy": row.cancelled_by or "",
        "cancelledAt": to_iso_timestamp(row.cancelled_at) if row.cancelled_at else "",
        "cancelReason": row.cancel_reason or "",
    }


def _live_booking_summary(opportunity_id: str) -> dict[str, Any] | None:
    booking = live_booking(opportunity_id)
    if not booking:
        return None
    summary: dict[str, Any] = {"id": booking.name, "status": booking.status}
    # The Booking can belong to another Sales user; its details stay within Booking scope. The PO
    # confirmation form is prefilled from this summary, so it carries every field Sales can edit on
    # the Pending Booking; otherwise confirming would write the approval draft back over the edits.
    if has_crm_permission(booking, user=frappe.session.user, permission_type="read"):
        summary.update({
            "primaryContactId": booking.primary_contact,
            "equipment": booking.equipment,
            "quantity": int(booking.quantity or 0),
            "ddl": str(booking.ddl or ""),
            "amount": booking_amount(booking.name),
            "currency": booking.currency,
            "owner": booking.booking_owner,
            "note": booking.note or "",
            "modified": to_iso_timestamp(booking.modified),
            "amountCny": booking_amount_cny(booking.name),
            "actualPoDate": str(booking.actual_po_date or ""),
        })
    return summary


def _stakeholders_for_opportunity(opportunity_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CRM Opportunity Stakeholder",
        filters={"opportunity": opportunity_id, "archived": 0},
        fields=["name", "contact", "role", "influence", "stance", "response_mode", "coverage", "is_coach", "win_result", "opportunity_notes"],
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
            "responseMode": row.response_mode or "",
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


def serialize_opportunity(doc, recoveries=None, loss_reviews=None) -> dict[str, Any]:
    role = resolve_crm_role()
    can_read_site = can_read_site_data(doc.account)
    exact_amounts = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR) AS `amount`, CAST(`original_amount` AS CHAR) AS `original_amount`, "
        "CAST(`amount_cny` AS CHAR) AS `amount_cny` "
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
        "pendingStageAdvance": doc.pending_stage_advance or "",
        "stageChangedAt": to_iso_timestamp(doc.stage_changed_at) if doc.stage_changed_at else "",
        "budgetApprovedOn": str(doc.budget_approved_on or ""),
        "lostAtStage": doc.lost_at_stage or "",
        "lostAt": to_iso_timestamp(doc.lost_at) if doc.lost_at else "",
        "lostBy": doc.lost_by or "",
        "probabilityLevel": doc.probability_level or "",
        # 0 is an amount nobody has entered yet (allowed at S1): "" like amountCny, never a 0.
        "amount": optional_money_text(exact.amount if exact else doc.amount or 0),
        "poDate": str(doc.po_date or ""),
        "updated": to_iso_timestamp(doc.modified),
        "modified": to_iso_timestamp(doc.modified),
        "score": int(doc.score or 0),
        "toolType": doc.tool_type,
        "saleType": doc.sale_type,
        "subRegion": doc.sub_region,
        "currency": doc.currency,
        "originalAmount": optional_money_text(exact.original_amount if exact else doc.original_amount or 0),
        "amountCny": optional_money_text(exact.amount_cny if exact else "0"),
        "shipmentDate": str(doc.shipment_date or ""),
        "fatDate": str(doc.fat_date or ""),
        "paymentMilestones": _decode_list(doc.payment_milestones),
        "competition": doc.competition or "",
        "singleSalesObjective": doc.single_sales_objective or "",
        "winReason": doc.win_reason or "",
        "lostReason": doc.lost_reason or "",
        "lossReviews": reviews_for_opportunity(doc.name) if loss_reviews is None else loss_reviews.get(doc.name, []),
        "history": _history_for_opportunity(doc.name),
        "probabilityHistory": _probability_history_for_opportunity(doc.name, recoveries),
        "stageHistory": _stage_history_for_opportunity(doc.name),
        "internalValidation": _latest_internal_validation(doc.name),
        "liveBooking": _live_booking_summary(doc.name),
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


def _require_opportunity(name: str, for_update: bool = False):
    # A writer of rows the Opportunity delete removes (stakeholders, actions, history, post-mortems) locks
    # the Opportunity first, the order the delete takes it in, and checks it under the lock: a write racing
    # the delete lands before it and is removed with the rest, or finds the Opportunity gone.
    exists = (frappe.db.get_value("CRM Opportunity", name, "name", for_update=True) if for_update
              else frappe.db.exists("CRM Opportunity", name))
    if not exists:
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
        recoveries = plans_for_opportunities([row.name for row in rows])
        reviews = reviews_for_opportunities([row.name for row in rows])
        return [serialize_opportunity(frappe.get_doc("CRM Opportunity", row.name), recoveries, reviews) for row in rows]
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
    for input_name, column in (("status", "stage"), ("owner", "opportunity_owner"), ("accountId", "account")):
        value = str(query.get(input_name) or "").strip()
        if value and value != "All":
            where_parts.append(f"`{column}` = %s")
            values.append(value)
    probability_level = str(query.get("probabilityLevel") or "").strip()
    if probability_level == "pending":
        where_parts.append("COALESCE(`probability_level`, '') = ''")
    elif probability_level and probability_level != "All":
        where_parts.append("`probability_level` = %s")
        values.append(probability_level)
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
    recoveries = plans_for_opportunities([row.name for row in rows])
    reviews = reviews_for_opportunities([row.name for row in rows])
    return [serialize_opportunity(frappe.get_doc("CRM Opportunity", row.name), recoveries, reviews) for row in rows], total, page, page_size


def get_strategy_opportunity(name: str) -> dict[str, Any]:
    assert_capability("deal:view")
    return serialize_opportunity(_require_opportunity(name))


def opportunities_for_account(account_id: str) -> list[dict[str, Any]]:
    _require_account(account_id)
    return [item for item in list_strategy_opportunities() if item["accountId"] == account_id]


def create_strategy_opportunity(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:write")
    ensure_server_generated_id(payload)
    assert_qualification_confirmed(payload)
    # Every new Opportunity starts at S1 (checked just below), where the amounts may still be unknown.
    values = _validate_opportunity(
        {**payload, "stage": payload.get("stage") or QUALIFIED_OPPORTUNITY}, require_amount=False,
    )
    if values["stage"] != QUALIFIED_OPPORTUNITY:
        raise CrmApiException("INVALID_TRANSITION", f"New Opportunity must start at {QUALIFIED_OPPORTUNITY}.")
    assert_initial_probability_level(values["probability_level"])
    for fieldname in LIST_FIELDS:
        values[fieldname] = json.dumps(values[fieldname], ensure_ascii=False)
    savepoint = f"crm_opportunity_create_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc = insert_qualified_opportunity(values, event="created")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_opportunity(doc)


def _current_input(doc) -> dict[str, Any]:
    exact_amount = frappe.db.sql(
        "SELECT CAST(`amount` AS CHAR), CAST(`original_amount` AS CHAR), CAST(`amount_cny` AS CHAR) "
        "FROM `tabCRM Opportunity` WHERE `name` = %s",
        (doc.name,),
    )[0]
    return {
        "accountId": doc.account,
        "siteId": doc.site,
        "title": doc.title,
        "owner": doc.opportunity_owner,
        "stage": doc.stage,
        "probabilityLevel": doc.probability_level or "",
        "amount": exact_amount[0],
        "intentScore": doc.score,
        "poDate": str(doc.po_date or ""),
        "toolType": doc.tool_type,
        "saleType": doc.sale_type,
        "subRegion": doc.sub_region,
        "currency": doc.currency,
        "originalAmount": exact_amount[1],
        # Empty until Sales enters it, so any edit of such an Opportunity asks for it first.
        "amountCny": optional_money_text(exact_amount[2]),
        "shipmentDate": str(doc.shipment_date or ""),
        "fatDate": str(doc.fat_date or ""),
        "paymentMilestones": _decode_list(doc.payment_milestones),
        "competition": doc.competition or "",
        "singleSalesObjective": doc.single_sales_objective or "",
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

    current_input = _current_input(doc)
    stored_money = {
        "amount": as_decimal(current_input["amount"]),
        "original_amount": as_decimal(current_input["originalAmount"]),
        "amount_cny": as_decimal(current_input["amountCny"] or 0),
    }
    # Leaving CNY: the stored CNY amount was the amount mirrored, not a conversion Sales entered, so it
    # does not carry over into another currency as a 1:1 rate. The caller sends one or it is asked for.
    new_currency = str(payload.get("currency") or doc.currency or "").strip().upper()
    if doc.currency == "CNY" and new_currency != "CNY" and "amountCny" not in payload:
        current_input["amountCny"] = ""
    # The stage never changes here, so the stored one decides: past S1 every edit needs all three amounts.
    # A deal lost at S1 never got past it, so it may still leave them blank.
    reached = doc.lost_at_stage if doc.stage == LOST and doc.lost_at_stage else doc.stage
    values = _validate_opportunity(
        {**current_input, **payload}, current_tool_type=doc.tool_type,
        stored_objective=doc.single_sales_objective or "",
        require_amount=(reached != QUALIFIED_OPPORTUNITY),
    )
    if values["stage"] != doc.stage:
        raise CrmApiException(
            "INVALID_TRANSITION", "Opportunity stages change only through their workflow actions.",
        )
    if doc.stage == LOST and not values["lost_reason"]:
        raise CrmApiException(
            "VALIDATION_ERROR", "Lost Reason is required for a lost Opportunity.",
            field_errors={"lostReason": "Required"},
        )

    previous_level = doc.probability_level or ""
    recovery_plan = None
    probability_reason = str(payload.get("probabilityReason") or "").strip()
    if values["probability_level"] != previous_level:
        _assert_probability_level_owner(doc.opportunity_owner)
        if doc.stage in CLOSED_STAGES:
            raise CrmApiException(
                "INVALID_TRANSITION",
                "The probability level is frozen once the PO is received or the Opportunity is lost.",
            )
        # Empty is only where an Opportunity from before the levels starts; once set, a level stays set.
        if not values["probability_level"]:
            raise CrmApiException(
                "VALIDATION_ERROR", "probabilityLevel cannot be cleared once it is set.",
                field_errors={"probabilityLevel": "Required"},
            )
        # Managers act on a downgrade, so the owner has to say why in the same save.
        lowered = probability_level_rank(values["probability_level"]) < probability_level_rank(previous_level)
        if lowered and not probability_reason:
            raise CrmApiException(
                "VALIDATION_ERROR", "A reason is required to lower the probability level.",
                field_errors={"probabilityReason": "Required"},
            )
        if lowered:
            recovery_plan = plan_text(payload.get("probabilityActionPlan"), "probabilityActionPlan")
    if values["account"] != doc.account or values["sale_type"] != doc.sale_type:
        if live_booking(doc.name):
            raise CrmApiException(
                "CONFLICT", "Account and sale type cannot change while the Opportunity has a live Booking.",
            )
        if doc.stage == INTERNAL_VALIDATION:
            # The approval that brought the Opportunity here was given for this account's equipment
            # deal; with its Booking cancelled the stage still stands until a Manager rolls it back,
            # and a Service Opportunity must never sit at internal validation.
            raise CrmApiException(
                "CONFLICT", "Account and sale type cannot change while the Opportunity is at internal validation.",
            )

    savepoint = f"crm_opportunity_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        if values["tool_type"] != doc.tool_type:
            values["tool_type"] = register_equipment(values["tool_type"])
        changes: list[tuple[str, Any, Any]] = []
        for fieldname, value in values.items():
            if fieldname in MONEY_FIELDS:
                if stored_money[fieldname] != value:
                    setattr(doc, fieldname, value)
                    # A first amount is recorded as filled in from empty, not changed from 0; one taken
                    # out again at S1 goes back to empty.
                    changes.append((fieldname, optional_money_text(stored_money[fieldname]), optional_money_text(value)))
                continue
            current = _decode_list(getattr(doc, fieldname)) if fieldname in LIST_FIELDS else getattr(doc, fieldname)
            stored = json.dumps(value, ensure_ascii=False) if fieldname in LIST_FIELDS else value
            changed = current != value if fieldname in LIST_FIELDS else str(current or "") != str(value or "")
            if changed:
                setattr(doc, fieldname, stored)
                # Probability level changes are audited in their own table.
                if fieldname != "probability_level":
                    changes.append((fieldname, current, value))

        doc.save(ignore_permissions=True)
        for fieldname, before, after in changes:
            _append_history(doc.name, fieldname, before, after)
        if values["probability_level"] != previous_level:
            event = _append_probability_history(
                doc.name, previous_level, values["probability_level"], probability_reason,
            )
            if recovery_plan is not None:
                create_recovery(event, recovery_plan)
                notify_downgrade(doc, event)
        # Under the row lock taken above, so a double submit or a concurrent save applies it once.
        _apply_pending_stage_advance(doc)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
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


def _append_probability_history(opportunity_id: str, before: str, after: str, reason: str = ""):
    return frappe.get_doc({
        "doctype": "CRM Opportunity Probability History",
        "opportunity": opportunity_id,
        "from_level": before,
        "to_level": after,
        "reason": reason,
        "actor": frappe.session.user,
        "changed_at": frappe.utils.now_datetime(),
    }).insert(ignore_permissions=True)


def _assert_probability_level_owner(owner: str) -> None:
    if owner != frappe.session.user:
        raise CrmApiException(
            "PERMISSION_DENIED", "Only the Opportunity owner can set the probability level.",
        )


def assert_initial_probability_level(level: str, fieldname: str = "probabilityLevel") -> None:
    """Every new Opportunity starts with a level.

    Whoever opens it sets the first one, which covers a Manager opening an Opportunity for a
    salesperson. Every change after that belongs to the owner.
    """

    if not level:
        raise CrmApiException(
            "VALIDATION_ERROR", f"{fieldname} is required.", field_errors={fieldname: "Required"},
        )


def assert_qualification_confirmed(payload: dict[str, Any]) -> None:
    """Creating an Opportunity requires Sales to confirm the customer need and budget owner."""

    if payload.get("qualificationConfirmed") is not True:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "Confirm the customer need and the budget owner before creating the Opportunity.",
            field_errors={"qualificationConfirmed": "Required"},
        )


def insert_qualified_opportunity(
    values: dict[str, Any],
    *,
    event: str,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
):
    """Insert an Opportunity at its first milestone and record how it got there."""

    now = frappe.utils.now_datetime()
    # Inside the caller's savepoint, so a failed insert does not leave a new custom type behind.
    values = {**values, "tool_type": register_equipment(values["tool_type"])}
    doc = frappe.get_doc({
        "doctype": "CRM Opportunity", **values, "stage": QUALIFIED_OPPORTUNITY, "stage_changed_at": now,
    }).insert(ignore_permissions=True)
    append_stage_history(
        doc.name, "", QUALIFIED_OPPORTUNITY, source="creation", event=event, at=now,
        reference_doctype=reference_doctype, reference_name=reference_name,
    )
    if doc.probability_level:
        _append_probability_history(doc.name, "", doc.probability_level)
    return doc


def append_stage_history(
    opportunity_id: str,
    from_stage: str,
    to_stage: str,
    *,
    source: str,
    event: str,
    at: Any,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
    reason: str = "",
    reached_at: Any = None,
    reached_at_basis: str = "recorded",
):
    return frappe.get_doc({
        "doctype": "CRM Opportunity Stage History",
        "opportunity": opportunity_id,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "source": source,
        "event": event,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "reason": reason,
        "actor": frappe.session.user,
        "recorded_at": at,
        "reached_at": at if reached_at is None else reached_at,
        "reached_at_basis": reached_at_basis,
    }).insert(ignore_permissions=True)


def _move_stage(
    doc,
    to_stage: str,
    *,
    source: str,
    event: str,
    at: Any = None,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
    reason: str = "",
    reached_at: Any = None,
    reached_at_basis: str = "recorded",
):
    """Change the stage and append its history row in the same transaction; returns the history row."""

    # A rollback returns to a stage already reached; every other move into Demo done or later is gated.
    if source != "rollback":
        _assert_amounts_for_stage(doc, to_stage)
    recorded_at = at or frappe.utils.now_datetime()
    from_stage = doc.stage
    doc.stage = to_stage
    # Follows the business time of the arrival, e.g. the budget approval date Sales declared.
    doc.stage_changed_at = recorded_at if reached_at is None else reached_at
    # A forward move spends a Demo done that was waiting for the amount. A loss and the reopening after
    # it do not: the Demo still stands, so the amounts still move the reopened Opportunity to Demo done.
    pending = doc.pending_stage_advance if to_stage != LOST and source != "rollback" else ""
    if pending:
        doc.pending_stage_advance = ""
    doc.save(ignore_permissions=True)
    if pending:
        _append_history(doc.name, "pendingStageAdvance", _pending_stage_advance_value(doc.name), "")
    return append_stage_history(
        doc.name, from_stage, to_stage, source=source, event=event, at=recorded_at,
        reference_doctype=reference_doctype, reference_name=reference_name, reason=reason,
        reached_at=reached_at, reached_at_basis=reached_at_basis,
    )


def _pending_stage_advance_value(opportunity_id: str) -> str:
    """The value the Opportunity's current waiting advance was recorded with: JSON text, or ''."""

    rows = frappe.get_all(
        "CRM Opportunity History", filters={"opportunity": opportunity_id, "field": "pendingStageAdvance"},
        fields=["to_value"], order_by="at desc, creation desc", limit=1,
    )
    return (rows[0].to_value or "") if rows else ""


def _hold_stage_advance(doc, target_stage: str, *, reference_doctype: str, reference_name: str) -> None:
    """Keep the Opportunity at its stage until the owner saves the amount; the workflow step stands.

    Recorded once: a second Demo event while it waits changes nothing and notifies nobody again.
    """

    if doc.pending_stage_advance == target_stage:
        return
    doc.pending_stage_advance = target_stage
    # Saving moves modified, so an editor opened before sees the change and reloads.
    doc.save(ignore_permissions=True)
    _append_history(doc.name, "pendingStageAdvance", "", {
        "stage": target_stage, "referenceDoctype": reference_doctype, "referenceName": reference_name,
    })
    # Sourced from the Opportunity (delete_strategy_opportunity removes the notice) and skipped for an owner who left.
    notify_if_reachable(
        recipient=doc.opportunity_owner, category="Opportunity", title="Enter the amount to reach Demo done",
        message=(
            f"{doc.title}: the Demo reached customer review. Enter the amount and the amount in CNY "
            "to move the Opportunity to Demo done."
        )[:1000],
        route=f"/opportunities/{doc.name}", source_doctype="CRM Opportunity", source_name=doc.name,
    )


def _apply_pending_stage_advance(doc) -> None:
    """Move an Opportunity whose Demo done waited for the amount, in the save that enters the amount."""

    if doc.pending_stage_advance != DEMO_DONE or doc.stage != QUALIFIED_OPPORTUNITY or not _has_amounts(doc):
        return
    held = _decode_object(_pending_stage_advance_value(doc.name))
    # Reached now: the Opportunity could not be at Demo done before it had an amount.
    _move_stage(
        doc, DEMO_DONE, source="event", event="demo_customer_review",
        reference_doctype=held.get("referenceDoctype") or None, reference_name=held.get("referenceName") or None,
        reason=PENDING_AMOUNT_REASON,
    )


def _lock_opportunity_for_action(name: str, expected_modified: Any):
    _require_opportunity(name)
    doc = lock_document("CRM Opportunity", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")
    return doc


def _require_stage(doc, stages: tuple[str, ...], action: str) -> None:
    if doc.stage not in stages:
        raise CrmApiException("INVALID_TRANSITION", f"{action} is not available at {doc.stage}.")


def _require_probability_level(doc) -> None:
    if not doc.probability_level:
        raise CrmApiException(
            "VALIDATION_ERROR", "Set the probability level before this step.",
            field_errors={"probabilityLevel": "Required"},
        )


def _decode_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _notify_opportunity_users(
    recipients: set[str], doc, *, title: str, message: str, source_doctype: str, source_name: str,
) -> None:
    for recipient in sorted(recipients - {frappe.session.user, None, ""}):
        # A disabled user or one without exactly one CRM role must not abort the business action.
        if not frappe.db.get_value("User", recipient, "enabled"):
            continue
        try:
            resolve_crm_role(recipient)
        except frappe.PermissionError:
            continue
        create_notification(
            recipient=recipient, category="Opportunity", title=title, message=message[:1000],
            route=f"/opportunities/{doc.name}", source_doctype=source_doctype, source_name=source_name,
        )


def _lock_internal_validations(opportunity_id: str) -> None:
    frappe.db.sql(
        "SELECT `name` FROM `tabCRM Opportunity Internal Validation` WHERE `opportunity` = %s FOR UPDATE",
        (opportunity_id,),
    )


def _cancel_pending_internal_validation(opportunity_id: str, reason: str) -> None:
    name = frappe.db.get_value(
        "CRM Opportunity Internal Validation", {"opportunity": opportunity_id, "status": "pending"}, "name",
    )
    if not name:
        return
    validation = frappe.get_doc("CRM Opportunity Internal Validation", name)
    validation.status = "cancelled"
    validation.cancelled_by = frappe.session.user
    validation.cancelled_at = frappe.utils.now_datetime()
    validation.cancel_reason = reason
    validation.save(ignore_permissions=True)
    _append_history(opportunity_id, "internalValidationCancelled", name, reason)


def confirm_budget_approved(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    doc = _lock_opportunity_for_action(name, expected_modified)
    _require_stage(doc, (DEMO_DONE,), "Budget approval")
    approved_on = optional_date(payload.get("approvedOn"), "approvedOn")
    if not approved_on:
        raise CrmApiException("VALIDATION_ERROR", "approvedOn is required.", field_errors={"approvedOn": "Required"})
    if approved_on > frappe.utils.today():
        raise CrmApiException(
            "VALIDATION_ERROR", "approvedOn cannot be in the future.",
            field_errors={"approvedOn": "Cannot be in the future"},
        )
    _require_probability_level(doc)

    savepoint = f"crm_opportunity_budget_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.budget_approved_on = approved_on
        _move_stage(
            doc, CUSTOMER_BUDGET_APPROVED, source="manual", event="budget_confirmed",
            reached_at=frappe.utils.get_datetime(approved_on), reached_at_basis="declared",
        )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_opportunity(doc)


def request_internal_validation(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    doc = _lock_opportunity_for_action(name, expected_modified)
    _require_stage(doc, (QUOTATION_SENT,), "Internal validation")
    # Asked here, not only at approval: Managers should not be sent a request they cannot approve.
    _assert_amounts_for_stage(doc, INTERNAL_VALIDATION)
    if doc.sale_type == "Service":
        raise CrmApiException(
            "INVALID_TRANSITION", "Internal validation is only available for equipment Opportunities.",
        )
    _require_probability_level(doc)
    reason = required_text(payload, "reason")
    expected_po_date = optional_date(payload.get("expectedPoDate"), "expectedPoDate")
    if not expected_po_date:
        raise CrmApiException(
            "VALIDATION_ERROR", "expectedPoDate is required.", field_errors={"expectedPoDate": "Required"},
        )
    booking = validate_booking_draft(doc, payload.get("booking"))
    _lock_internal_validations(doc.name)
    if frappe.db.exists("CRM Opportunity Internal Validation", {"opportunity": doc.name, "status": "pending"}):
        raise CrmApiException("CONFLICT", "The Opportunity already has a pending internal validation.")
    reviewers = {user for user in active_crm_users("Manager") if user != frappe.session.user}
    if not reviewers:
        raise CrmApiException("CONFLICT", "No other active Manager can review this internal validation.")

    savepoint = f"crm_opportunity_validation_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        validation = frappe.get_doc({
            "doctype": "CRM Opportunity Internal Validation",
            "opportunity": doc.name,
            "attempt_no": frappe.db.count("CRM Opportunity Internal Validation", {"opportunity": doc.name}) + 1,
            "status": "pending",
            "reason": reason,
            "expected_po_date": expected_po_date,
            "booking_draft": json.dumps(booking, ensure_ascii=False),
            "requested_by": frappe.session.user,
            "requested_at": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True)
        # The stage does not change; saving still moves modified so stale clients see the request.
        doc.save(ignore_permissions=True)
        _append_history(doc.name, "internalValidationRequested", "", validation.name)
        _notify_opportunity_users(
            reviewers, doc, title="Internal validation requested", message=f"{doc.title}: {reason}",
            source_doctype="CRM Opportunity Internal Validation", source_name=validation.name,
        )
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("CONFLICT", "The Opportunity already has a pending internal validation.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_opportunity(doc)


def review_internal_validation(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:internal_validation_approve")
    doc = _lock_opportunity_for_action(name, expected_modified)
    validation_id = required_text(payload, "validationId")
    decision = validate_choice(payload.get("decision"), "decision", {"approved", "rejected"})
    comment = str(payload.get("comment") or "").strip()
    if decision == "rejected" and not comment:
        raise CrmApiException(
            "VALIDATION_ERROR", "A comment is required to reject an internal validation.",
            field_errors={"comment": "Required"},
        )
    _lock_internal_validations(doc.name)
    if frappe.db.get_value("CRM Opportunity Internal Validation", validation_id, "opportunity") != doc.name:
        raise CrmApiException("INTERNAL_VALIDATION_NOT_FOUND", "Internal validation was not found.")
    validation = frappe.get_doc("CRM Opportunity Internal Validation", validation_id)
    if validation.status != "pending":
        raise CrmApiException("INVALID_TRANSITION", "The internal validation was already decided or cancelled.")
    if validation.requested_by == frappe.session.user:
        raise CrmApiException("PERMISSION_DENIED", "Managers cannot review their own internal validation.")
    _require_stage(doc, (QUOTATION_SENT,), "Internal validation review")
    booking_values = None
    if decision == "approved":
        if doc.sale_type == "Service":
            raise CrmApiException(
                "INVALID_TRANSITION", "Internal validation is only available for equipment Opportunities.",
            )
        # The request may be days old: its contact, owner and currency must still be valid now.
        booking_values = validate_booking_draft(doc, _decode_object(validation.booking_draft))
        if live_booking(doc.name, for_update=True):
            raise CrmApiException("CONFLICT", "The Opportunity already has a live Booking.")

    savepoint = f"crm_opportunity_validation_review_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        validation.status = decision
        validation.decided_by = frappe.session.user
        validation.decided_at = frappe.utils.now_datetime()
        validation.decision_comment = comment
        booking = create_opportunity_booking(doc, booking_values, "Pending") if booking_values else None
        if booking:
            validation.booking = booking.name
        validation.save(ignore_permissions=True)
        if booking:
            _move_stage(
                doc, INTERNAL_VALIDATION, source="approval", event="internal_validation_approved",
                reference_doctype="CRM Opportunity Internal Validation", reference_name=validation.name,
            )
        else:
            doc.save(ignore_permissions=True)
        _append_history(
            doc.name, f"internalValidation{decision.title()}", validation.name, booking.name if booking else comment,
        )
        _notify_opportunity_users(
            {validation.requested_by, doc.opportunity_owner}, doc,
            title=f"Internal validation {decision}",
            message=f"{doc.title}: {comment}" if comment else f"{doc.title}: internal validation {decision}.",
            source_doctype="CRM Opportunity Internal Validation", source_name=validation.name,
        )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_opportunity(doc)


def confirm_po(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    doc = _lock_opportunity_for_action(name, expected_modified)
    # At po_received the only thing left is to replace a Booking that was cancelled by hand.
    replacing = doc.stage == PO_RECEIVED
    if not replacing:
        _require_stage(doc, PO_CONFIRMABLE_STAGES, "PO confirmation")
        _require_probability_level(doc)
    # The CNY amount of a foreign-currency order is known once the PO is.
    booking_values = validate_booking_draft(doc, payload.get("booking"), require_amount_cny=True)
    # The date on the customer's PO, as opposed to the expected `po_date` on the Opportunity.
    actual_po_date = validate_actual_po_date(payload.get("actualPoDate"), required=True)
    _lock_internal_validations(doc.name)
    booking = live_booking(doc.name, for_update=True)
    if booking and (doc.stage != INTERNAL_VALIDATION or booking.status != "Pending"):
        raise CrmApiException("CONFLICT", "The Opportunity already has a live Booking.")
    # A form prefilled from a Pending Booking that is gone now was prepared on an older view. The
    # Opportunity version check above normally catches that already (cancelling the Booking moves
    # the Opportunity's modified); this keeps the refusal explicit for a client that sent the token.
    if not booking and payload.get("expectedBookingModified") is not None:
        raise CrmApiException("VERSION_CONFLICT", "The Pending Booking was cancelled. Reload before confirming the PO.")
    if booking:
        # The PO details replace those of the Pending Booking, so the caller must see its current
        # details (a Sales user cannot read a Booking assigned to another Sales user) and the Booking
        # must still be the version the form was prefilled from. Booking edits also move the
        # Opportunity's modified, so this is a second check behind the Opportunity version.
        if not has_crm_permission(booking, user=frappe.session.user, permission_type="read"):
            raise CrmApiException("SCOPE_DENIED", "The Pending Booking is outside the current user scope.")
        expected_booking_modified = payload.get("expectedBookingModified")
        if not isinstance(expected_booking_modified, str) or not expected_booking_modified.strip():
            raise CrmApiException(
                "VALIDATION_ERROR", "expectedBookingModified is required.",
                field_errors={"expectedBookingModified": "Required"},
            )
        if to_iso_timestamp(booking.modified) != normalize_expected_modified(expected_booking_modified):
            raise CrmApiException("VERSION_CONFLICT", "The Pending Booking was changed by another request.")
    replaced = replaced_booking(doc.name) if replacing else None

    savepoint = f"crm_opportunity_po_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        if doc.stage == QUOTATION_SENT:
            _cancel_pending_internal_validation(doc.name, "PO received before the internal validation was decided.")
        if booking:
            confirm_pending_booking(booking, booking_values, actual_po_date=actual_po_date)
        else:
            booking = create_opportunity_booking(doc, booking_values, "Confirmed", actual_po_date=actual_po_date)
        if replacing:
            doc.save(ignore_permissions=True)
            # A replacement may carry another amount or PO date than the cancelled order; keep the trail.
            if replaced:
                for fieldname, before, after in (
                    ("bookingAmountCny", booking_amount_cny(replaced.name), booking_amount_cny(booking.name)),
                    ("bookingPoDate", str(replaced.actual_po_date or ""), str(booking.actual_po_date or "")),
                ):
                    if before != after:
                        _append_history(doc.name, fieldname, before, after)
            _append_history(doc.name, "bookingReplaced", "", booking.name)
        else:
            _move_stage(
                doc, PO_RECEIVED, source="manual", event="po_confirmed",
                reference_doctype="CRM Booking", reference_name=booking.name,
            )
            _append_history(doc.name, "poConfirmed", "", booking.name)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_opportunity(doc)


def mark_opportunity_lost(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    doc = _lock_opportunity_for_action(name, expected_modified)
    _require_stage(doc, OPEN_STAGES, "Marking the Opportunity lost")
    lost_reason = required_text(payload, "lostReason")
    _lock_internal_validations(doc.name)
    if live_booking(doc.name, for_update=True):
        raise CrmApiException("CONFLICT", "Cancel the Booking before marking the Opportunity lost.")

    now = frappe.utils.now_datetime()
    savepoint = f"crm_opportunity_lost_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        _cancel_pending_internal_validation(doc.name, "Opportunity marked lost.")
        doc.lost_reason = lost_reason
        doc.lost_at_stage = doc.stage
        doc.lost_at = now
        doc.lost_by = frappe.session.user
        event = _move_stage(doc, LOST, source="lost", event="marked_lost", at=now, reason=lost_reason)
        # The post-mortem lives on the immutable event, so reopening the deal cannot erase it.
        create_loss_review(doc, event)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_opportunity(doc)


def rollback_opportunity_stage(
    name: str,
    target_stage: Any,
    reason: Any,
    expected_modified: Any,
) -> dict[str, Any]:
    assert_capability("deal:rollback")
    target = validate_choice(target_stage, "targetStage", set(MILESTONE_STAGES))
    rollback_reason = required_text({"reason": reason}, "reason")
    _require_opportunity(name)
    # Locks are taken RFQ -> Opportunity -> internal validation -> Booking. review_rfq locks the
    # RFQ before the Opportunity too, so a rollback cannot deadlock against an RFQ approval.
    rfq = frappe.db.sql(
        "SELECT `status` FROM `tabCRM RFQ` WHERE `opportunity` = %s FOR UPDATE", (name,), as_dict=True,
    )
    doc = lock_document("CRM Opportunity", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")
    reopening = doc.stage == LOST
    if reopening:
        # Without a recorded loss stage, reopening stops below internal validation, which would
        # claim a Manager approval nobody can vouch for.
        ceiling = doc.lost_at_stage or QUOTATION_SENT
        if stage_index(target) > stage_index(ceiling):
            raise CrmApiException(
                "INVALID_TRANSITION", f"A lost Opportunity can only reopen at or below {ceiling}.",
            )
    elif stage_index(target) >= stage_index(doc.stage):
        raise CrmApiException("INVALID_TRANSITION", "Rollback target must be an earlier stage.")
    _lock_internal_validations(doc.name)
    booking = live_booking(doc.name, for_update=True)
    if booking and booking.status == "Completed":
        raise CrmApiException("CONFLICT", "A completed Booking blocks stage rollback.")
    if target == INTERNAL_VALIDATION:
        approved = frappe.get_all(
            "CRM Opportunity Internal Validation",
            filters={"opportunity": doc.name, "status": "approved"},
            pluck="booking", order_by="attempt_no desc", limit=1,
        )
        latest_booking = frappe.get_all(
            "CRM Booking", filters={"source_opportunity": doc.name},
            pluck="name", order_by="creation desc", limit=1,
        )
        # Only the Booking the approval created may carry the Opportunity back to internal
        # validation; a PO confirmed straight from quotation_sent never had that approval.
        if not approved or not latest_booking or latest_booking[0] != approved[0]:
            raise CrmApiException(
                "INVALID_TRANSITION",
                "internal_validation requires the Booking created by an approved internal validation.",
            )
        # The approval was given for this account's equipment deal. Once its Booking is cancelled the
        # account and sale type can change at po_received or lost, so the Opportunity may only come
        # back under that approval while both still match it.
        if doc.sale_type == "Service":
            raise CrmApiException(
                "INVALID_TRANSITION", "Internal validation is only available for equipment Opportunities.",
            )
        if frappe.db.get_value("CRM Booking", approved[0], "account") != doc.account:
            raise CrmApiException(
                "INVALID_TRANSITION", "The approved internal validation was given for another account.",
            )
    elif booking:
        raise CrmApiException("CONFLICT", "Cancel the Booking before rolling the Opportunity back.")

    savepoint = f"crm_opportunity_rollback_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        if doc.stage == QUOTATION_SENT:
            _cancel_pending_internal_validation(doc.name, f"Opportunity rolled back to {target}.")
        if booking and booking.status == "Confirmed":
            # Production carries on under the internal validation, but the PO is no longer confirmed,
            # so its date goes too; confirming the PO again asks for it.
            previous_po_date = str(booking.actual_po_date or "")
            booking.status = "Pending"
            booking.actual_po_date = None
            booking.actual_po_date_source = None
            booking.actual_po_date_note = None
            booking.save(ignore_permissions=True)
            if previous_po_date:
                _append_history(doc.name, "bookingPoDate", previous_po_date, "")
        if stage_index(target) <= stage_index(CUSTOMER_BUDGET_APPROVED) and rfq and rfq[0].status == "Approved":
            from rayher_crm.services.rfqs import reopen_approved_rfq_for_stage_rollback

            reopen_approved_rfq_for_stage_rollback(doc.name, rollback_reason)
        if stage_index(target) < stage_index(CUSTOMER_BUDGET_APPROVED):
            doc.budget_approved_on = None
        if reopening:
            doc.lost_reason = ""
            doc.lost_at_stage = None
            doc.lost_at = None
            doc.lost_by = None
        event = _move_stage(
            doc, target, source="rollback", event="reopened" if reopening else "rollback", reason=rollback_reason,
        )
        if reopening:
            mark_reopened(doc.name, event.recorded_at)
            # A Demo done that was waiting when the deal was lost applies as soon as the amounts are there.
            _apply_pending_stage_advance(doc)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_opportunity(doc)


def advance_opportunity_for_event(
    opportunity_id: str,
    event: str,
    *,
    reference_doctype: str,
    reference_name: str,
) -> None:
    """Move an Opportunity to the milestone a server workflow has just reached."""

    if event not in AUTOMATIC_STAGE_EVENTS:
        raise ValueError(f"Unknown opportunity stage event: {event}")
    required_stage, target_stage = AUTOMATIC_STAGE_EVENTS[event]
    rows = frappe.db.sql(
        "SELECT `name` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE",
        (opportunity_id,),
    )
    if not rows:
        raise CrmApiException("OPPORTUNITY_NOT_FOUND", "Opportunity was not found.")
    # A locking read: the committed row, not this transaction's older snapshot, since the owner may
    # have saved the amount (and moved the stage) while this workflow step waited for the lock.
    doc = frappe.get_doc("CRM Opportunity", opportunity_id, for_update=True)
    if doc.stage == LOST:
        if event == "demo_customer_review":
            # Customer feedback on a lost deal is still recorded; it does not reopen the deal.
            return
        raise CrmApiException("INVALID_TRANSITION", "A lost Opportunity cannot be advanced by workflow completion.")
    if stage_index(doc.stage) >= stage_index(target_stage):
        return
    if doc.stage != required_stage:
        raise CrmApiException(
            "CONFLICT",
            f"Opportunity must be at {required_stage} before workflow completion can move it to {target_stage}.",
        )
    if target_stage == DEMO_DONE and not _has_amounts(doc):
        # The Demo result must never be lost for a missing amount, nor may the deal skip the gate:
        # the advance waits for the owner to save the amount (see _apply_pending_stage_advance).
        _hold_stage_advance(doc, target_stage, reference_doctype=reference_doctype, reference_name=reference_name)
        return
    _move_stage(
        doc, target_stage, source="event", event=event,
        reference_doctype=reference_doctype, reference_name=reference_name,
    )


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


def _validate_stakeholder(
    opportunity, payload: dict[str, Any], stakeholder_id: str | None = None, *, stored_response_mode: str = "",
) -> dict[str, Any]:
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
    # A null mode means "not set"; any other non-choice value (false, 0, [], {}) is rejected. An update that
    # leaves the key out keeps the stored mode, as a page from before the field does not send it.
    response_mode = payload["responseMode"] if "responseMode" in payload else stored_response_mode
    return {
        "contact": contact_id,
        "role": validate_choice(payload.get("role"), "role", STAKEHOLDER_ROLES),
        "influence": validate_choice(payload.get("influence"), "influence", STAKEHOLDER_INFLUENCES),
        "stance": validate_choice(payload.get("stance"), "stance", STAKEHOLDER_STANCES),
        "response_mode": validate_choice(
            "" if response_mode is None else response_mode, "responseMode", STAKEHOLDER_RESPONSE_MODES,
        ),
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
    opportunity = _require_opportunity(opportunity_id, for_update=True)
    values = _validate_stakeholder(opportunity, payload)
    doc = frappe.get_doc({
        "doctype": "CRM Opportunity Stakeholder", "opportunity": opportunity_id, **values,
    }).insert(ignore_permissions=True)
    _append_history(opportunity_id, "stakeholderCreated", "", doc.name)
    return _serialize_stakeholder(doc)


def update_opportunity_stakeholder(opportunity_id: str, stakeholder_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("stakeholder:write")
    opportunity = _require_opportunity(opportunity_id, for_update=True)
    doc = _lock_relation("CRM Opportunity Stakeholder", stakeholder_id, opportunity_id, "STAKEHOLDER_NOT_FOUND")
    values = _validate_stakeholder(
        opportunity, payload, stakeholder_id, stored_response_mode=doc.response_mode or "",
    )
    for fieldname, value in values.items():
        setattr(doc, fieldname, value)
    doc.save(ignore_permissions=True)
    _append_history(opportunity_id, "stakeholderUpdated", stakeholder_id, stakeholder_id)
    return _serialize_stakeholder(doc)


def delete_opportunity_stakeholder(opportunity_id: str, stakeholder_id: str) -> dict[str, str]:
    assert_capability("stakeholder:write")
    _require_opportunity(opportunity_id, for_update=True)
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
    opportunity = _require_opportunity(opportunity_id, for_update=True)
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
    opportunity = _require_opportunity(opportunity_id, for_update=True)
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
    _require_opportunity(opportunity_id, for_update=True)
    doc = _lock_relation("CRM Opportunity Action", action_id, opportunity_id, "ACTION_NOT_FOUND")
    doc.archived = 1
    doc.save(ignore_permissions=True)
    _append_history(opportunity_id, "actionDeleted", "", action_id)
    return {"id": action_id}
