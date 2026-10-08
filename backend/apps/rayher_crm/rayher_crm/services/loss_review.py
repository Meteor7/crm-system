"""Post-mortem reviews linked to immutable marked_lost stage events.

A review row is created the moment an Opportunity is marked lost and is never deleted
when the deal reopens, so the Manager post-mortem survives the cleared lost_* fields
on the Opportunity. The Sales-entered reason stays the reason; the Manager only records
the conclusion and flips the status.
"""

from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import to_iso_timestamp, validate_choice
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.review_breakdowns import LOSS_CATEGORIES

LOSS_REVIEW = "CRM Opportunity Loss Review"
LOSS_REVIEW_REVISION = "CRM Opportunity Loss Review Revision"
REVIEW_STATUSES = ("Pending", "Reviewed")
REVIEW_FIELDS = [
    "name", "opportunity", "stage_event", "lost_at", "lost_at_stage", "lost_by", "lost_reason",
    "review_status", "review_category", "review_note", "reviewed_by", "reviewed_at", "reopened_at", "modified",
]


def _text(value, field: str, message: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > 4000:
        raise CrmApiException("VALIDATION_ERROR", message, field_errors={field: "Enter 1-4000 characters"})
    return text


def _append_revision(doc, kind: str, *, actor: str | None = None, at=None, reason: str = "") -> None:
    frappe.get_doc({
        "doctype": LOSS_REVIEW_REVISION, "loss_review": doc.name, "opportunity": doc.opportunity,
        "kind": kind, "review_status": doc.review_status, "review_category": doc.review_category or "", "review_note": doc.review_note or "", "reason": reason,
        "actor": actor or frappe.session.user, "recorded_at": at or frappe.utils.now_datetime(),
    }).insert(ignore_permissions=True)


def create_loss_review(opportunity, event):
    """Called inside the transaction that appends the marked_lost stage event."""
    doc = frappe.get_doc({
        "doctype": LOSS_REVIEW, "opportunity": opportunity.name, "stage_event": event.name,
        "lost_at": event.reached_at or event.recorded_at, "lost_at_stage": event.from_stage,
        "lost_by": event.actor, "lost_reason": event.reason or "", "review_status": "Pending",
    }).insert(ignore_permissions=True)
    _append_revision(doc, "Created")
    return doc


def mark_reopened(opportunity_id: str, at) -> None:
    """Reopening keeps the review; it only records when the deal came back."""
    for name in frappe.get_all(
        LOSS_REVIEW, filters={"opportunity": opportunity_id, "reopened_at": ["is", "not set"]}, pluck="name",
    ):
        # Locking read: a concurrent post-mortem save must not turn the reopen into a timestamp error.
        doc = frappe.get_doc(LOSS_REVIEW, name, for_update=True)
        doc.reopened_at = at
        doc.save(ignore_permissions=True)
        _append_revision(doc, "Reopened")


def _dto(row, history) -> dict:
    return {
        "id": row.name, "opportunityId": row.opportunity, "stageEventId": row.stage_event,
        "lostAt": to_iso_timestamp(row.lost_at) if row.lost_at else "",
        "lostAtStage": row.lost_at_stage or "", "lostBy": row.lost_by or "", "lostReason": row.lost_reason or "",
        "status": "reviewed" if row.review_status == "Reviewed" else "pending",
        "reviewCategory": row.review_category or "", "reviewNote": row.review_note or "", "reviewedBy": row.reviewed_by or None,
        "reviewedAt": to_iso_timestamp(row.reviewed_at) if row.reviewed_at else None,
        "reopenedAt": to_iso_timestamp(row.reopened_at) if row.reopened_at else None,
        "modified": to_iso_timestamp(row.modified), "history": history,
    }


def reviews_for_opportunities(opportunity_ids: list[str]) -> dict[str, list[dict]]:
    """The caller must authorize every parent first; at most two queries per page."""
    if not opportunity_ids:
        return {}
    filters = {"opportunity": ["in", list(opportunity_ids)]}
    rows = frappe.get_all(LOSS_REVIEW, filters=filters, fields=REVIEW_FIELDS, order_by="lost_at desc, creation desc")
    if not rows:
        return {}
    histories: dict[str, list[dict]] = {}
    for row in frappe.get_all(
        LOSS_REVIEW_REVISION, filters=filters,
        fields=["name", "loss_review", "kind", "review_status", "review_category", "review_note", "reason", "actor", "recorded_at"],
        order_by="recorded_at desc, creation desc, name desc",
    ):
        histories.setdefault(row.loss_review, []).append({
            "id": row.name, "kind": row.kind, "status": "reviewed" if row.review_status == "Reviewed" else "pending",
            "category": row.review_category or "", "note": row.review_note or "", "reason": row.reason or "", "actor": row.actor, "at": to_iso_timestamp(row.recorded_at),
        })
    result: dict[str, list[dict]] = {}
    for row in rows:
        result.setdefault(row.opportunity, []).append(_dto(row, histories.get(row.name, [])))
    return result


def reviews_for_opportunity(opportunity_id: str) -> list[dict]:
    return reviews_for_opportunities([opportunity_id]).get(opportunity_id, [])


def review_loss(opportunity_id: str, review_id: str, payload: dict, expected_modified) -> dict:
    """Manager-only: record the post-mortem conclusion and mark the loss reviewed (or revert it)."""
    from rayher_crm.services.opportunities import _require_opportunity

    assert_capability("deal:write")
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Only a Manager can confirm a lost-deal post-mortem.")
    # The Opportunity first, the order the delete and every other writer under it lock in; the review row next.
    _require_opportunity(opportunity_id, for_update=True)
    status = validate_choice(payload.get("status"), "status", set(REVIEW_STATUSES))
    # Marking done needs the conclusion. Reverting needs its own reason (FR-K9-02) and keeps the
    # conclusion, so a revert can never pass off the old conclusion as its reason or replace it.
    if status == "Reviewed":
        note = _text(payload.get("reviewNote"), "reviewNote", "A post-mortem conclusion of 1-4000 characters is required.")
        reason = ""
    else:
        reason = _text(payload.get("revertReason"), "revertReason", "A reason of 1-4000 characters is required to revert a post-mortem.")
    doc = lock_document(LOSS_REVIEW, review_id, expected_modified, "NOT_FOUND")
    if doc.opportunity != opportunity_id:
        raise CrmApiException("NOT_FOUND", "The loss review was not found.")
    category = doc.review_category or ""
    if status == "Reviewed" and "reviewCategory" in payload:
        category = "" if payload.get("reviewCategory") == "" else validate_choice(payload.get("reviewCategory"), "reviewCategory", set(LOSS_CATEGORIES))
    if status == "Reviewed" and doc.review_status != "Reviewed" and not category:
        raise CrmApiException("VALIDATION_ERROR", "Choose a confirmed loss category before completing the post-mortem.",
                              field_errors={"reviewCategory": "Choose a confirmed loss category"})
    if status == "Pending":
        if doc.review_status != "Reviewed":
            raise CrmApiException("INVALID_TRANSITION", "Only a reviewed loss can be reverted to pending.")
        note = doc.review_note or ""
        kind = "ReviewReverted"
    elif doc.review_status == "Reviewed" and (doc.review_note or "") == note and (doc.review_category or "") == category:
        return _current(doc)
    else:
        kind = "Reviewed" if doc.review_status != "Reviewed" else "ReviewUpdated"
    savepoint = f"crm_loss_review_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.review_category = category
        doc.review_note = note
        doc.review_status = status
        if status == "Reviewed":
            # The latest Manager to confirm the conclusion is the reviewer shown; every edit stays in the revisions.
            doc.reviewed_by = frappe.session.user
            doc.reviewed_at = frappe.utils.now_datetime()
        else:
            doc.reviewed_by = None
            doc.reviewed_at = None
        doc.save(ignore_permissions=True)
        _append_revision(doc, kind, reason=reason)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return _current(doc)


def _current(doc) -> dict:
    return next(r for r in reviews_for_opportunity(doc.opportunity) if r["id"] == doc.name)


def backfill_loss_reviews() -> dict[str, int]:
    """Give every historical marked_lost event a pending review; safe to run repeatedly."""
    events = frappe.get_all(
        "CRM Opportunity Stage History", filters={"event": "marked_lost"},
        fields=["name", "opportunity", "from_stage", "reason", "actor", "recorded_at", "reached_at"],
        order_by="recorded_at asc, creation asc",
    )
    if not events:
        return {"created": 0, "existing": 0, "skipped": 0}
    existing = set(frappe.get_all(LOSS_REVIEW, filters={"stage_event": ["in", [e.name for e in events]]}, pluck="stage_event"))
    opportunity_ids = {e.opportunity for e in events}
    live = set(frappe.get_all("CRM Opportunity", filters={"name": ["in", list(opportunity_ids)]}, pluck="name"))
    reopenings: dict[str, list] = {}
    for row in frappe.get_all(
        "CRM Opportunity Stage History", filters={"event": "reopened", "opportunity": ["in", list(opportunity_ids)]},
        fields=["opportunity", "recorded_at", "actor"], order_by="recorded_at asc",
    ):
        reopenings.setdefault(row.opportunity, []).append(row)
    created = skipped = 0
    for event in events:
        if event.name in existing:
            continue
        if event.opportunity not in live:
            skipped += 1
            continue
        reopening = next((r for r in reopenings.get(event.opportunity, []) if r.recorded_at > event.recorded_at), None)
        reopened_at = reopening.recorded_at if reopening else None
        doc = frappe.get_doc({
            "doctype": LOSS_REVIEW, "opportunity": event.opportunity, "stage_event": event.name,
            "lost_at": event.reached_at or event.recorded_at, "lost_at_stage": event.from_stage,
            "lost_by": event.actor, "lost_reason": event.reason or "", "review_status": "Pending",
            "reopened_at": reopened_at,
        }).insert(ignore_permissions=True)
        _append_revision(doc, "Created", actor=event.actor, at=event.recorded_at)
        if reopening:
            _append_revision(doc, "Reopened", actor=reopening.actor, at=reopening.recorded_at)
        created += 1
    return {"created": created, "existing": len(existing), "skipped": skipped}
