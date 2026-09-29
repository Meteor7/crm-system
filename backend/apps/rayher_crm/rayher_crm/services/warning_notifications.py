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
        except (frappe.PermissionError, CrmApiException, frappe.UniqueValidationError, frappe.DuplicateEntryError):
            continue
    return created


def send_warning_notifications() -> int:
    """Scheduled daily (hooks.py). Returns how many notices were created."""
    now = frappe.utils.now_datetime()
    details = warning_details(now)
    days = {field: value for field, (value, _source) in thresholds().items()}
    since = now.date() - timedelta(days=NOTICE_DAYS)
    fresh = lambda kind, rows: [r for r in rows if (began(kind, r, days, now.date()) or date.min) >= since]
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
    for row in fresh("stage6_no_po", details["stage6_no_po"]):
        handling = row.get("handling") or {}
        event = handling.get("sourceEvent") or BEFORE_HISTORY
        created += _notify(readers(managers, "CRM Opportunity", row["id"]),
                           key=f"stage6_no_po:{row['id']}:{event}:{handling.get('followUpOn') or ''}", category="Opportunity",
                           title="预警：第 6 阶段超期无 PO",
                           message=f"{row['title']}（{row['customer']}）已在第 6 阶段 {row['daysInStage']} 天{'以上' if row.get('daysAtLeast') else ''}，仍未收到 PO。",
                           route=f"/opportunities/{quote(row['id'], safe='')}",
                           # The entry event, not the Opportunity: an inbox item must not block deleting it.
                           source_doctype="CRM Opportunity Stage History" if event != BEFORE_HISTORY else None,
                           source_name=event if event != BEFORE_HISTORY else None)
    return created
