"""Versioned recovery plans linked to immutable probability-change events."""

from __future__ import annotations

import frappe
from hashlib import sha256
from urllib.parse import quote

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.opportunity_stages import probability_level_rank
from rayher_crm.services.notifications import active_crm_users, notify_if_reachable
from rayher_crm.permissions.scope import has_crm_permission


def plan_text(value, field="plan") -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 4000:
        raise CrmApiException(
            "VALIDATION_ERROR", "A recovery plan of 1–4000 characters is required.",
            field_errors={field: "Enter 1–4000 characters"},
        )
    return value.strip()


def is_downgrade(event) -> bool:
    return bool(event.from_level) and probability_level_rank(event.to_level) < probability_level_rank(event.from_level)


def _append_revision(doc, kind: str):
    return frappe.get_doc({
        "doctype": "CRM Probability Recovery Revision", "recovery": doc.name,
        "opportunity": doc.opportunity, "kind": kind, "plan": doc.plan,
        "actor": frappe.session.user, "recorded_at": frappe.utils.now_datetime(),
        "action_taken": doc.action_taken if kind == "ActionRecorded" else None,
    }).insert(ignore_permissions=True)


def create_recovery(event, plan: str):
    """Called inside the transaction that appends the downgrade event."""
    if not is_downgrade(event):
        raise CrmApiException("INVALID_TRANSITION", "Only a downgrade can have a recovery plan.")
    doc = frappe.get_doc({
        "doctype": "CRM Probability Recovery", "opportunity": event.opportunity,
        "probability_change": event.name, "plan": plan_text(plan),
    }).insert(ignore_permissions=True)
    _append_revision(doc, "Created")
    return doc


def plans_for_opportunity(opportunity_id: str) -> dict:
    return plans_for_opportunities([opportunity_id])


def plans_for_opportunities(opportunity_ids: list[str]) -> dict:
    """The caller must authorize every parent first; at most two queries per page."""
    if not opportunity_ids:
        return {}
    filters = {"opportunity": ["in", opportunity_ids]}
    rows = frappe.get_all(
        "CRM Probability Recovery", filters=filters,
        fields=["name", "probability_change", "plan", "modified", "action_taken", "acted_by", "acted_at"],
    )
    if not rows:
        return {}
    histories = {}
    for row in frappe.get_all(
        "CRM Probability Recovery Revision", filters=filters,
        fields=["name", "recovery", "kind", "plan", "actor", "recorded_at", "action_taken"],
        order_by="recorded_at desc, creation desc, name desc",
    ):
        histories.setdefault(row.recovery, []).append({
            "id": row.name, "kind": row.kind, "plan": row.plan,
            "actor": row.actor, "at": to_iso_timestamp(row.recorded_at),
            "actionTaken": row.action_taken or None,
        })
    return {row.probability_change: {
        "id": row.name, "plan": row.plan, "modified": to_iso_timestamp(row.modified),
        "history": histories.get(row.name, []),
        "state": "handled" if row.acted_at else "pending", "actionTaken": row.action_taken or None,
        "actedBy": row.acted_by or None, "actedAt": to_iso_timestamp(row.acted_at) if row.acted_at else None,
    } for row in rows}


def _lock_context(opportunity_id: str, event_id: str, expected_modified):
    # Lock order is always parent then recovery, matching the original downgrade.
    from rayher_crm.services.opportunities import _lock_opportunity_for_action

    assert_capability("deal:write")
    opportunity = _lock_opportunity_for_action(opportunity_id, expected_modified)
    if resolve_crm_role() != "Manager" and opportunity.opportunity_owner != frappe.session.user:
        raise CrmApiException("PERMISSION_DENIED", "Only the Opportunity owner or a Manager can maintain recovery plans.")
    event = frappe.db.get_value(
        "CRM Opportunity Probability History", {"name": event_id, "opportunity": opportunity_id},
        ["name", "opportunity", "from_level", "to_level"], as_dict=True,
    )
    if not event:
        raise CrmApiException("NOT_FOUND", "The probability change was not found.")
    if not is_downgrade(event):
        raise CrmApiException("INVALID_TRANSITION", "Only a downgrade can have a recovery plan.")
    return opportunity, event


def save_plan(opportunity_id: str, event_id: str, payload: dict, expected_modified) -> dict:
    opportunity, event = _lock_context(opportunity_id, event_id, expected_modified)
    plan = plan_text(payload.get("plan"))
    # A competing legacy creation does not change the parent version. Use a current
    # read after the parent lock; the request may already have a REPEATABLE READ snapshot.
    name = frappe.db.get_value("CRM Probability Recovery", {"probability_change": event_id}, "name", for_update=True)
    # A legacy event has no plan. The client must explicitly submit null to create
    # one, so a racing creation cannot silently overwrite the first author's plan.
    expected_recovery = payload.get("recoveryModified", "missing")
    if not name and expected_recovery is not None:
        raise CrmApiException("VERSION_CONFLICT", "Reload the probability change before creating its plan.")
    if name and not expected_recovery:
        raise CrmApiException("VERSION_CONFLICT", "A recovery plan was already created. Reload before editing.")
    doc = lock_document("CRM Probability Recovery", name, expected_recovery, "NOT_FOUND") if name else None
    savepoint = f"crm_recovery_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        revision = None
        if doc is None:
            doc = create_recovery(event, plan)
        elif doc.plan != plan:
            doc.plan = plan
            doc.save(ignore_permissions=True)
            revision = _append_revision(doc, "PlanUpdated").name
        if revision and resolve_crm_role() == "Manager" and opportunity.opportunity_owner != frappe.session.user:
            notify_if_reachable(
                recipient=opportunity.opportunity_owner, category="Opportunity",
                title="Recovery plan updated by Manager",
                message=f"{opportunity.title}: {plan}"[:1000],
                route=f"/opportunities/{quote(opportunity.name, safe='')}?probabilityEvent={quote(event.name, safe='')}",
                source_doctype="CRM Probability Recovery Revision", source_name=revision,
                dedupe_key=sha256(f"recovery-plan:{revision}:{opportunity.opportunity_owner}".encode()).hexdigest(),
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return plans_for_opportunity(opportunity_id)[event_id]


def record_action(opportunity_id: str, event_id: str, payload: dict, expected_modified) -> dict:
    opportunity, _ = _lock_context(opportunity_id, event_id, expected_modified)
    if opportunity.opportunity_owner != frappe.session.user:
        raise CrmApiException("PERMISSION_DENIED", "Only the current Opportunity owner can record the action taken.")
    action = plan_text(payload.get("actionTaken"), "actionTaken")
    name = frappe.db.get_value("CRM Probability Recovery", {"probability_change": event_id}, "name", for_update=True)
    if not name:
        raise CrmApiException("INVALID_TRANSITION", "Record a recovery plan before recording the action taken.")
    doc = lock_document("CRM Probability Recovery", name, payload.get("recoveryModified"), "NOT_FOUND")
    if doc.acted_at:
        raise CrmApiException("INVALID_TRANSITION", "An action was already recorded for this downgrade.")
    savepoint = f"crm_recovery_action_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.action_taken = action
        doc.acted_by = frappe.session.user
        doc.acted_at = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)
        _append_revision(doc, "ActionRecorded")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return plans_for_opportunity(opportunity_id)[event_id]


def notify_downgrade(opportunity, event) -> None:
    """Persist one in-app event per authorized Manager inside the downgrade transaction."""
    for recipient in active_crm_users("Manager"):
        if not has_crm_permission(opportunity, user=recipient, permission_type="read"):
            continue
        notify_if_reachable(
            recipient=recipient, category="Opportunity", title="Opportunity probability downgraded",
            message=f"{opportunity.title}: {event.from_level} → {event.to_level}. {event.reason or ''}"[:1000],
            route=f"/opportunities/{quote(opportunity.name, safe='')}?probabilityEvent={quote(event.name, safe='')}",
            # Like existing Action/Internal Validation notices, reference the source
            # event so an otherwise-deletable parent is not blocked by an inbox item.
            source_doctype="CRM Opportunity Probability History", source_name=event.name,
            dedupe_key=sha256(f"probability-downgrade:{event.name}:{recipient}".encode()).hexdigest(),
        )
