"""Daily Warnings notices: each warning once, on the first day it is found.

Managers hear about every warning (the Warnings page is theirs). The owner of an overdue action and the
owner of an expiring quotation also hear about their own. A warning is one instance (cockpit_metrics
handling_key): a new due date, quotation version or entry into S6 is a new warning and notifies again,
and so does an S6 deal still waiting after its follow-up day. A handled S6 deal is not in the list, so it
stays quiet. Downgrades keep their notice at the moment of the change (probability_recovery.notify_downgrade).

Only warnings that began in the last NOTICE_DAYS days are announced (a missed run or two is still caught).
A warning begins the first day it meets its condition, which is the first day it can be listed.
Older ones are on the Warnings page already: announcing them would flood every inbox the first time the job
runs, or after a staging wipe clears the notices.
"""
from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from types import SimpleNamespace
from urllib.parse import quote

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.permissions.scope import has_crm_permission
from rayher_crm.services import cockpit
from rayher_crm.services.cockpit_metrics import BEFORE_HISTORY, build_review, stamp
from rayher_crm.services.cockpit_settings import thresholds
from rayher_crm.services.notifications import active_crm_users, create_notification


NOTICE_DAYS = 3
# create_notification refuses a recipient who is not an active CRM user (INVALID_OWNER) or who can no
# longer read the source (SCOPE_DENIED): both are normal skips for a batch.
RECIPIENT_UNREACHABLE_CODES = frozenset({"INVALID_OWNER", "SCOPE_DENIED"})


def warning_details(now) -> dict:
    """Every current warning company-wide: this week's Warnings page with no filters."""
    customers, people, _ = cockpit.options()
    data = cockpit.load_data(customers, people)
    coverage = frappe.conf.get("crm_cockpit_history_complete_from") or {}
    if not isinstance(coverage, dict):
        coverage = {}
    limits = thresholds()
    query = {"period": "week", "anchor": now.date().isoformat(), "sales": "", "market": "", "region": "", "equipment": ""}
    return build_review(data, query, now, coverage, limits["quote_expiry_days"][0], limits["stage6_no_po_days"][0])["_details"]


def began(kind: str, row: dict, thresholds_days: dict, today: date) -> date | None:
    """The first day a warning met its condition, so the first day it could be listed."""
    day = lambda value: stamp(value).date() if value else None
    if kind == "lost":
        return day(row.get("at"))
    if kind == "overdue":
        return date.fromisoformat(row["due"]) + timedelta(days=1)
    if kind == "quotation_expiry":
        entered_window = date.fromisoformat(row["validUntil"]) - timedelta(days=thresholds_days["quote_expiry_days"])
        return max(filter(None, (day(row.get("publishedAt")), entered_window)))
    if kind == "close_date_slip":
        handling = row.get("handling") or {}
        return max(filter(None, (day(row.get("at")), day(handling.get("followUpOn")) if handling.get("actedAt") else None)))
    # The first day the stay reached the threshold: the entry plus the threshold, or for a stay known only as
    # a minimum (an entry before the complete history) the first day that minimum did, when it was first listed.
    reached = today - timedelta(days=row["daysInStage"] - thresholds_days["stage6_no_po_days"])
    handling = row.get("handling") or {}
    if handling.get("actedAt") and handling.get("followUpOn"):
        # Back after its follow-up day, or on the day it reaches a threshold raised since, whichever is later.
        return max(date.fromisoformat(handling["followUpOn"]), reached)
    return reached


def _can_read(user: str, doctype: str, name: str | None) -> bool:
    return bool(name) and has_crm_permission(SimpleNamespace(doctype=doctype, name=name), user=user, permission_type="read")


def _notify(recipients, *, key: str, category: str, title: str, message: str, route: str,
            source_doctype: str | None, source_name: str | None) -> int:
    created = 0
    for recipient in sorted({r for r in recipients if r}):
        dedupe_key = sha256(f"warning:{key}:{recipient}".encode()).hexdigest()
        if frappe.db.exists("CRM Notification Event", {"dedupe_key": dedupe_key}):
            continue
        # A disabled user or one without exactly one CRM role is skipped, never fatal to the others.
        if not frappe.db.get_value("User", recipient, "enabled"):
            continue
        try:
            resolve_crm_role(recipient)
            create_notification(recipient=recipient, category=category, title=title, message=message[:1000], route=route,
                                source_doctype=source_doctype, source_name=source_name, dedupe_key=dedupe_key)
            created += 1
        except (frappe.PermissionError, frappe.UniqueValidationError, frappe.DuplicateEntryError):
            continue
        except CrmApiException as exc:
            if exc.code in RECIPIENT_UNREACHABLE_CODES:
                continue
            # Bad source metadata (a warning row whose source is gone, an unsupported source type) is a
            # defect, not a reachability problem: keep it visible instead of reporting a clean run, and
            # keep the other recipients and warnings of today's batch.
            frappe.log_error(
                title="Warning notification skipped: invalid source",
                message=f"{exc.code}: {exc}\nrecipient={recipient} source={source_doctype}/{source_name} key={key}",
            )
    return created


def _lock_current_opportunities(names) -> set[str]:
    """Lock every legacy notice parent before this transaction takes a series lock."""

    opportunity_ids = tuple(sorted({name for name in names if name}))
    return {name for name in opportunity_ids if _lock_current_opportunity(name)}


def _lock_current_opportunity(name: str) -> bool:
    """Serialize a legacy parent-sourced notice with the Opportunity's archive (and a deletion from the Desk):
    a locking read, so a parent archived after warning_details' snapshot gets no notice."""

    rows = frappe.db.sql(
        "SELECT `archived` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE",
        (name,),
    )
    return bool(rows) and not rows[0][0]


def send_warning_notifications() -> int:
    """Scheduled daily (hooks.py). Returns how many notices were created."""
    now = frappe.utils.now_datetime()
    details = warning_details(now)
    days = {field: value for field, (value, _source) in thresholds().items()}
    since = now.date() - timedelta(days=NOTICE_DAYS)
    fresh = lambda kind, rows: [r for r in rows if (began(kind, r, days, now.date()) or date.min) >= since]
    stage6_rows = fresh("stage6_no_po", details["stage6_no_po"])
    slip_rows = fresh("close_date_slip", details.get("close_date_slip", []))
    # Lock every relevant parent before any notification can take the naming-series
    # lock. Current reads exclude parents deleted after warning_details' RR snapshot.
    before_history_ids = _lock_current_opportunities([
        *[row["id"] for row in stage6_rows
          if ((row.get("handling") or {}).get("sourceEvent") or BEFORE_HISTORY) == BEFORE_HISTORY],
        *[row["id"] for row in slip_rows],
    ])
    managers = active_crm_users("Manager")
    created = 0

    def readers(users, doctype, name):
        return {u for u in users if _can_read(u, doctype, name)}

    for row in fresh("lost", details["lost"]):
        if not row.get("reviewPending"):
            continue
        created += _notify(readers(managers, "CRM Opportunity", row["id"]), key=f"lost:{row['eventId']}", category="Opportunity",
                           title="预警：丢单待复盘", message=f"{row['title']}（{row['customer']}）已丢单，请完成复盘。",
                           route=f"/opportunities/{quote(row['id'], safe='')}",
                           source_doctype="CRM Opportunity Stage History", source_name=row["eventId"])
    for row in fresh("overdue", details["overdue"]):
        created += _notify(readers({*managers, row.get("actionOwner")}, "CRM Opportunity", row["id"]),
                           key=f"overdue:{row['actionId']}:{row['due']}", category="Action",
                           title="预警：行动逾期", message=f"{row['title']}（{row['customer']}）的行动「{row['actionTitle']}」原定 {row['due']} 完成，已逾期。",
                           route=f"/opportunities/{quote(row['id'], safe='')}",
                           source_doctype="CRM Opportunity Action", source_name=row["actionId"])
    for row in fresh("quotation_expiry", details["quotation_expiry"]):
        created += _notify(readers({*managers, row.get("owner")}, "CRM Quotation", row["id"]),
                           key=f"quotation_expiry:{row['id']}:{row['quotationVersionId']}", category="Quotation",
                           title="预警：报价即将到期", message=f"报价 {row['title']}（{row['customer']}）V{row.get('quotationVersionNo')} 将于 {row['validUntil']} 到期，还剩 {row['daysToExpiry']} 天。",
                           route=f"/quotations/{quote(row['id'], safe='')}",
                           source_doctype="CRM Quotation Version", source_name=row["quotationVersionId"])
    for row in stage6_rows:
        handling = row.get("handling") or {}
        event = handling.get("sourceEvent") or BEFORE_HISTORY
        # All before-history parents were locked in sorted order before any notice
        # insert took the shared naming-series lock. This matches Opportunity writers'
        # parent -> notification order and still serializes with deletion.
        if event == BEFORE_HISTORY and row["id"] not in before_history_ids:
            continue
        created += _notify(readers(managers, "CRM Opportunity", row["id"]),
                           key=f"stage6_no_po:{row['id']}:{event}:{handling.get('followUpOn') or ''}", category="Opportunity",
                           title="预警：第 6 阶段超期无 PO",
                           message=f"{row['title']}（{row['customer']}）已在第 6 阶段 {row['daysInStage']} 天{'以上' if row.get('daysAtLeast') else ''}，仍未收到 PO。",
                           route=f"/opportunities/{quote(row['id'], safe='')}",
                           # Legacy entries have no trusted history row. Anchor
                           # their notice to the current parent, never an unscoped copy.
                           source_doctype="CRM Opportunity Stage History" if event != BEFORE_HISTORY else "CRM Opportunity",
                           source_name=event if event != BEFORE_HISTORY else row["id"])
    for row in slip_rows:
        if row["id"] not in before_history_ids:
            continue
        handling = row.get("handling") or {}
        created += _notify(readers({*managers, row.get("owner")}, "CRM Opportunity", row["id"]),
                           key=f"close_date_slip:{row['eventId']}:{handling.get('followUpOn') or ''}", category="Opportunity",
                           title="预警：预计 PO 日期跨季度推迟",
                           message=f"{row['title']}（{row['customer']}）预计 PO 日期由 {row['previousPoDate']} 推迟至 {row['postponedPoDate']}，请跟进并记录行动。",
                           route=f"/opportunities/{quote(row['id'], safe='')}",
                           source_doctype="CRM Opportunity History", source_name=row["eventId"])
    return created
