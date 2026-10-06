"""Daily 15-day and 7-day reminders for active CRM deadlines."""

from __future__ import annotations

from collections.abc import Iterable
import hashlib
from typing import Any

import frappe
from rayher_crm.services.action_statuses import OPEN_ACTION_STATUSES
from frappe.utils import getdate, today

from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.services.notifications import active_crm_users, notify_if_reachable


REMINDER_DAYS = {15, 7}


def _active_recipients(candidates: Iterable[Any]) -> set[str]:
    recipients: set[str] = set()
    for candidate in candidates:
        user = str(candidate or "").strip()
        if not user or not frappe.db.get_value("User", user, "enabled"):
            continue
        try:
            resolve_crm_role(user)
        except frappe.PermissionError:
            continue
        recipients.add(user)
    return recipients


def _related_users(
    *,
    account_id: str | None,
    opportunity_id: str | None,
    explicit: Iterable[Any],
    managers: Iterable[str],
) -> set[str]:
    candidates = set(explicit) | set(managers)
    if account_id:
        candidates.add(frappe.db.get_value("Customer", account_id, "custom_crm_owner"))
    if opportunity_id:
        candidates.add(frappe.db.get_value("CRM Opportunity", opportunity_id, "opportunity_owner"))
        candidates.update(frappe.get_all(
            "CRM Opportunity Action",
            filters={"opportunity": opportunity_id, "status": ["in", list(OPEN_ACTION_STATUSES)], "archived": 0},
            pluck="action_owner",
        ))
        for row in frappe.get_all(
            "CRM RFQ", filters={"opportunity": opportunity_id}, fields=["sales_owner", "engineer_owner"],
        ):
            candidates.update((row.sales_owner, row.engineer_owner))
        candidates.update(frappe.get_all(
            "CRM Quotation", filters={"opportunity": opportunity_id}, pluck="quotation_owner",
        ))
    return _active_recipients(candidates)


def _send_source_reminder(
    *,
    source_doctype: str,
    source_name: str,
    category: str,
    label: str,
    deadline: Any,
    route: str,
    recipients: set[str],
) -> int:
    if not deadline:
        return 0
    days = (getdate(deadline) - getdate(today())).days
    if days not in REMINDER_DAYS:
        return 0
    deadline_text = str(getdate(deadline))
    title = f"{label} DDL 提醒 · 剩余 {days} 天"
    message = f"{source_name} 的 {label} DDL 为 {deadline_text}，距离截止还有 {days} 天，请及时跟进。"
    created = 0
    for recipient in sorted(recipients):
        dedupe_key = hashlib.sha256("|".join((recipient, source_doctype, source_name, title, message)).encode("utf-8")).hexdigest()
        try:
            notification = notify_if_reachable(
                recipient=recipient,
                category=category,
                title=title,
                message=message,
                route=route,
                source_doctype=source_doctype,
                source_name=source_name,
                dedupe_key=dedupe_key,
            )
            if notification is not None:
                created += 1
        except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
            continue
    return created


def send_ddl_reminders() -> int:
    """Broadcast each active deadline once at 15 days and once at 7 days."""

    managers = active_crm_users("Manager")
    created = 0

    for booking in frappe.get_all(
        "CRM Booking",
        filters={"status": ["not in", ["Cancelled", "Completed"]]},
        fields=["name", "ddl", "booking_owner", "account", "source_opportunity"],
    ):
        recipients = _related_users(
            account_id=booking.account,
            opportunity_id=booking.source_opportunity,
            explicit=[booking.booking_owner],
            managers=managers,
        )
        created += _send_source_reminder(
            source_doctype="CRM Booking",
            source_name=booking.name,
            category="Booking",
            label="Booking",
            deadline=booking.ddl,
            route="/booking",
            recipients=recipients,
        )

    for request in frappe.get_all(
        "CRM Demo Request",
        filters={"status": ["not in", ["Converted", "Cancelled"]]},
        fields=["name", "status", "customer_expected_date", "sales_owner", "engineer_owner", "account", "opportunity"],
    ):
        recipients = _related_users(
            account_id=request.account,
            opportunity_id=request.opportunity,
            explicit=[request.sales_owner, request.engineer_owner],
            managers=managers,
        )
        # A draft is Sales' own until they submit it: its Engineer neither reads it nor hears of its deadline,
        # whatever else of the Opportunity (an RFQ, say) names them.
        if request.status == "Draft":
            recipients.discard(request.engineer_owner)
        created += _send_source_reminder(
            source_doctype="CRM Demo Request",
            source_name=request.name,
            category="Demo",
            label="Demo 客户期望",
            deadline=request.customer_expected_date,
            route=f"/demo-workflow/{request.name}?tab=information",
            recipients=recipients,
        )

    for evaluation in frappe.get_all(
        "CRM Evaluation",
        filters={"status": ["not in", ["Accepted", "Rejected"]]},
        fields=["name", "test_run_deadline", "evaluation_owner", "account", "demo_request"],
    ):
        request = frappe.get_doc("CRM Demo Request", evaluation.demo_request)
        recipients = _related_users(
            account_id=evaluation.account or request.account,
            opportunity_id=request.opportunity,
            explicit=[evaluation.evaluation_owner, request.sales_owner, request.engineer_owner],
            managers=managers,
        )
        created += _send_source_reminder(
            source_doctype="CRM Evaluation",
            source_name=evaluation.name,
            category="Evaluation",
            label="Test Run",
            deadline=evaluation.test_run_deadline,
            route=f"/demo-workflow/{request.name}?tab=test",
            recipients=recipients,
        )

    return created


__all__ = ["send_ddl_reminders"]
