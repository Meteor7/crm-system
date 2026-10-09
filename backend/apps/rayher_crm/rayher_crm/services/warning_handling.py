"""Next steps and actions a Manager records on Warnings rows that have no business record of their own.

Overdue actions and expiring quotations clear only through their own records (done, rescheduled,
replaced, decided), so they take a next step and never a clearing action. A deal waiting in internal
validation (S6) without a PO also takes a recorded action with a follow-up day: it leaves the count
until that day and comes back if it is still waiting then. A next step never clears anything.
"""
from __future__ import annotations

from datetime import date, timedelta
from rayher_crm.services.action_statuses import open_action
from rayher_crm.services.close_date_slips import current_slip

import frappe
from rayher_crm.setup.indexes import OPPORTUNITY_FIELD_HISTORY_INDEX

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.services.accounts import account_archived
from rayher_crm.services.common import as_payload, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.cockpit_metrics import (
    BEFORE_HISTORY, HANDLING_TYPES, covered, handling_key, handling_state, last_entry,
    stage_entered, stage6_stay, stamp,
)
from rayher_crm.services.opportunity_stages import INTERNAL_VALIDATION, OPEN_STAGES

HANDLING = "CRM Warning Handling"
REVISION = "CRM Warning Handling Revision"
FIELDS = ["name", "warning_type", "source_id", "source_event", "opportunity", "next_step", "plan_updated_by",
          "plan_updated_at", "action_taken", "acted_by", "acted_at", "follow_up_on", "modified"]
TEXT_LIMIT = 2000


def _iso(value):
    return to_iso_timestamp(value) if value else None


REVISION_FIELDS = ["name", "creation", "handling", "kind", "next_step", "action_taken", "follow_up_on", "actor", "recorded_at"]


def _serialize(row, history) -> dict:
    return {"warningType": row["warning_type"], "sourceId": row["source_id"], "sourceEvent": row["source_event"],
            "id": row["name"], "modified": _iso(row["modified"]),
            "nextStep": row.get("next_step") or None, "planBy": row.get("plan_updated_by") or None, "planAt": _iso(row.get("plan_updated_at")),
            "actionTaken": row.get("action_taken") or None, "actedBy": row.get("acted_by") or None, "actedAt": _iso(row.get("acted_at")),
            "followUpOn": str(row["follow_up_on"]) if row.get("follow_up_on") else None, "history": history}


def handling_records(rows, revisions) -> dict[str, dict]:
    """Saved handling keyed like the Warnings rows (cockpit_metrics.handling_key), each with its history newest first."""
    histories: dict[str, list[dict]] = {}
    for row in sorted(revisions, key=lambda r: (str(r["recorded_at"]), str(r.get("creation") or ""), r["name"]), reverse=True):
        histories.setdefault(row["handling"], []).append({
            "kind": row["kind"], "nextStep": row.get("next_step") or None, "actionTaken": row.get("action_taken") or None,
            "followUpOn": str(row["follow_up_on"]) if row.get("follow_up_on") else None, "actor": row["actor"], "at": _iso(row["recorded_at"])})
    return {row["name"]: _serialize(row, histories.get(row["name"], [])) for row in rows}


def _current(name: str) -> dict:
    row = frappe.db.get_value(HANDLING, name, FIELDS, as_dict=True)
    revisions = frappe.get_all(REVISION, filters={"handling": name}, fields=REVISION_FIELDS, limit_page_length=0)
    record = handling_records([row], revisions)[name]
    return {**record, "state": handling_state(record, frappe.utils.now_datetime().date().isoformat())}


def _require_manager():
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Warnings handling is available to CRM Managers only.")


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > TEXT_LIMIT:
        raise CrmApiException("VALIDATION_ERROR", f"{field} must be 1–{TEXT_LIMIT} characters.",
                              field_errors={field: f"Enter 1–{TEXT_LIMIT} characters"})
    return value.strip()


def _current_stage6_history(opportunity_id: str):
    # A locking read: the current history, not the request's snapshot (the Opportunity row is already locked).
    return frappe.db.sql("SELECT `name`, `creation`, `to_stage`, `reached_at`, `recorded_at`, `source`, `reached_at_basis` "
                         "FROM `tabCRM Opportunity Stage History` WHERE `opportunity` = %s FOR UPDATE", (opportunity_id,), as_dict=True)


def current_stage6_event(opportunity_id: str) -> str:
    row = last_entry(_current_stage6_history(opportunity_id), INTERNAL_VALIDATION, stamp(frappe.utils.now_datetime()))
    return (row or {}).get("name") or BEFORE_HISTORY


def _gone():
    return CrmApiException("INVALID_TRANSITION", "This warning has changed or cleared. Reload the page.")


def _require_current_stage6_warning(opportunity_id: str) -> None:
    """Only a currently due warning can be suppressed by a recorded action.

    A historical row may still take a next-step plan for the current entry, but
    must not hide a future warning after re-entry or a threshold increase.
    """
    from rayher_crm.services.cockpit_settings import thresholds
    now = stamp(frappe.utils.now_datetime())
    threshold = thresholds(for_update=True)["stage6_no_po_days"][0]
    history = _current_stage6_history(opportunity_id)
    entered, at_least = stage_entered(history, INTERNAL_VALIDATION, now)
    coverage = frappe.conf.get("crm_cockpit_history_complete_from") or {}
    if not isinstance(coverage, dict):
        coverage = {}
    history_start = stamp(coverage["stage"]) if covered(coverage, "stage", now) else None
    created = frappe.db.get_value("CRM Opportunity", opportunity_id, "creation", for_update=True)
    days, _ = stage6_stay(entered, at_least, stamp(created), history_start, now, threshold)
    if days is None or days < threshold:
        raise _gone()


def _source(payload) -> tuple[str, str, str, str | None]:
    """The warning named by the request, checked against current state; returns its opportunity too.

    A rescheduled action, a new quotation version or a new entry into S6 is a new warning, so a page
    showing the old one is told to reload rather than writing to the wrong record.
    """
    kind = payload.get("warningType")
    if kind not in HANDLING_TYPES:
        raise CrmApiException("VALIDATION_ERROR", "Unknown warning type.")
    source_id, event = payload.get("sourceId"), payload.get("sourceEvent")
    if not all(isinstance(v, str) and v.strip() and len(v) <= 140 for v in (source_id, event)):
        raise CrmApiException("VALIDATION_ERROR", "sourceId and sourceEvent are required.")
    # Locking reads see the current rows (not this request's snapshot) and serialize saves on one warning.
    # Opportunity before action, the order the Opportunity service locks them in.
    today = frappe.utils.now_datetime().date()

    def stage(opportunity, lock=True):
        # An archived Opportunity (a Manager's archive, in place of a delete) has no current warning: its
        # stage reads as none, and the page showing the old warning is told to reload.
        row = frappe.db.get_value("CRM Opportunity", opportunity, ["stage", "archived"], as_dict=True, for_update=lock) if opportunity else None
        return row.stage if row and not row.archived else None

    if kind == "overdue":
        parent = frappe.db.get_value("CRM Opportunity Action", source_id, "opportunity")
        current_stage = stage(parent)
        row = frappe.db.get_value("CRM Opportunity Action", source_id, ["opportunity", "due", "status", "archived"], as_dict=True, for_update=True)
        if (not row or row.opportunity != parent or not open_action(row) or not row.due or str(row.due)[:10] != event
                or str(row.due)[:10] >= today.isoformat() or current_stage not in OPEN_STAGES):
            raise _gone()
        return kind, source_id, event, row.opportunity
    if kind == "quotation_expiry":
        row = frappe.db.get_value("CRM Quotation", source_id, ["opportunity", "current_published_version", "account"], as_dict=True, for_update=True)
        version = frappe.db.get_value("CRM Quotation Version", event, ["quotation", "status", "valid_until"], as_dict=True) if row else None
        # The quotation of a closed deal, or of an archived one (its stage reads as none), is no warning; nor is one of
        # an archived Account (a Manager's archive, in place of a delete), out of the warnings with it: its `account`,
        # the customer it was addressed to, which the warnings list it by. The Account's flag is read under a shared
        # lock on its row, then the stage under the Opportunity's lock, after the Quotation's: the order the
        # Quotation's writers take them in.
        archived = bool(row and row.account and account_archived(row.account, shared_lock=True))
        parent_stage = stage(row.opportunity) if row and row.opportunity and not archived else ""
        if (not row or archived or row.current_published_version != event or not version or version.quotation != source_id
                or version.status != "Published" or not version.valid_until or str(version.valid_until)[:10] < today.isoformat()
                or parent_stage is None or parent_stage in {"po_received", "lost"}):
            raise _gone()
        return kind, source_id, event, row.opportunity or None
    if kind == "close_date_slip":
        if stage(source_id) not in OPEN_STAGES:
            raise _gone()
        current_date = frappe.db.get_value("CRM Opportunity", source_id, "po_date", for_update=True)
        history = frappe.db.sql(
            "SELECT name, creation, at, field, from_value, to_value FROM `tabCRM Opportunity History` "
            f"FORCE INDEX (`{OPPORTUNITY_FIELD_HISTORY_INDEX}`) "
            "WHERE opportunity=%s AND field='po_date' FOR UPDATE", (source_id,), as_dict=True,
        )
        slip = current_slip(history, current_date, stamp(frappe.utils.now_datetime()))
        if not slip or slip["name"] != event:
            raise _gone()
        return kind, source_id, event, source_id
    if stage(source_id) != INTERNAL_VALIDATION or current_stage6_event(source_id) != event:
        raise _gone()
    return kind, source_id, event, source_id


def _save(source, expected_modified, kind: str, values: dict, unchanged) -> dict:
    warning_type, source_id, event, opportunity = source
    name = handling_key(warning_type, source_id, event)
    # No lock on this read: a locking read of a row that is not there yet takes a gap lock, and two
    # first saves of different warnings would deadlock on their inserts. Saves of one warning are already
    # serialized by the parent row lock in _source; if this request's REPEATABLE READ snapshot predates a
    # concurrent first save, the duplicate insert below is answered as VERSION_CONFLICT.
    exists = frappe.db.get_value(HANDLING, name, "name")
    if exists:
        doc = frappe.get_doc(HANDLING, name, for_update=True)
        if unchanged(doc):
            # A retry of a save that already landed returns the record instead of a conflict.
            return _current(name)
        if not expected_modified:
            raise CrmApiException("VERSION_CONFLICT", "Someone else already saved this warning. Reload before editing.")
        doc = lock_document(HANDLING, name, expected_modified, "NOT_FOUND")
    else:
        if expected_modified:
            raise CrmApiException("VERSION_CONFLICT", "This warning's handling is no longer there. Reload before editing.")
        doc = frappe.get_doc({"doctype": HANDLING, "name": name, "warning_type": warning_type,
                              "source_id": source_id, "source_event": event, "opportunity": opportunity})
    doc.update(values)
    savepoint = f"crm_warning_handling_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        if exists:
            doc.save(ignore_permissions=True)
        else:
            doc.insert(ignore_permissions=True)
        frappe.get_doc({"doctype": REVISION, "handling": name, "warning_type": warning_type, "kind": kind,
                        "next_step": values.get("next_step"), "action_taken": values.get("action_taken"),
                        "follow_up_on": values.get("follow_up_on"), "actor": frappe.session.user,
                        "recorded_at": frappe.utils.now_datetime()}).insert(ignore_permissions=True)
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("VERSION_CONFLICT", "Someone else saved this warning at the same time. Reload.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return _current(name)


def save_plan(payload, expected_modified=None) -> dict:
    """The next step: shown on the row and kept in the history, never clears the warning."""
    _require_manager()
    payload = as_payload(payload)
    source = _source(payload)
    step = _text(payload.get("nextStep"), "nextStep")
    return _save(source, expected_modified, "PlanUpdated",
                 {"next_step": step, "plan_updated_by": frappe.session.user, "plan_updated_at": frappe.utils.now_datetime()},
                 lambda doc: (doc.next_step or "") == step)


def record_action(payload, expected_modified=None) -> dict:
    """What was done about a deal waiting in S6 without a PO, and the day to look at it again."""
    _require_manager()
    payload = as_payload(payload)
    if payload.get("warningType") not in {"stage6_no_po", "close_date_slip"}:
        raise CrmApiException("INVALID_TRANSITION", "Only stage 6 and postponed PO warnings take a recorded action; the others clear through their own records.")
    source = _source(payload)
    if source[0] == "stage6_no_po":
        _require_current_stage6_warning(source[1])
    action = _text(payload.get("actionTaken"), "actionTaken")
    today = frappe.utils.now_datetime().date()
    try:
        follow_up = date.fromisoformat(str(payload.get("followUpOn") or ""))
    except ValueError:
        follow_up = None
    if not follow_up or not today < follow_up <= today + timedelta(days=365):
        raise CrmApiException("VALIDATION_ERROR", "Pick a follow-up day after today, at most a year ahead.",
                              field_errors={"followUpOn": "Pick a day after today, at most a year ahead"})
    return _save(source, expected_modified, "ActionRecorded",
                 {"action_taken": action, "follow_up_on": follow_up, "acted_by": frappe.session.user,
                  "acted_at": frappe.utils.now_datetime()},
                 lambda doc: (doc.action_taken or "") == action and str(doc.follow_up_on or "") == follow_up.isoformat())
