"""Plan, apply and verify the move from the legacy Opportunity stages to the seven milestones.

Legacy stages named the work in progress; the new stages are milestones already reached.

- ``plan_opportunity`` is a pure function over one Opportunity's evidence snapshot.
- ``dry_run`` and ``verify`` do not write to the database. They write CSV reports under
  ``sites/<site>/private/crm-stage-migration/``.
- The ``migrate_opportunity_seven_stages`` patch applies the same plans.
- Sales corrections live in site_config under ``crm_stage_migration_overrides``, e.g.
  ``{"CRM-OPP-00012": {"stage": "demo_done", "note": "客户已看过 Demo"}}``; a lost
  Opportunity may also carry ``lostAtStage``.
- Undoing the migration means restoring the pre-upgrade backup.

Run on a restored copy first::

    bench --site <site> execute rayher_crm.setup.opportunity_stage_migration.dry_run
    bench --site <site> migrate
    bench --site <site> execute rayher_crm.setup.opportunity_stage_migration.verify
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import frappe

from rayher_crm.services.opportunity_stages import (
    CUSTOMER_BUDGET_APPROVED,
    DEMO_DONE,
    INTERNAL_VALIDATION,
    LOST,
    MILESTONE_STAGES,
    OPEN_STAGES,
    OPPORTUNITY_STAGES,
    PO_RECEIVED,
    QUALIFIED_OPPORTUNITY,
    QUOTATION_SENT,
    RFQ_VALIDATED,
    stage_index,
)

LEGACY_ALIASES = {
    "技术确认": "Wafer Demo确认",
    "Demo验证": "Wafer Demo确认",
    "Demo 验证": "Wafer Demo确认",
    "商务谈判": "报价",
    "Closed Won": "Won",
    "Closed Lost": "Lost",
}
LEGACY_STAGES = ("需求发现", "Wafer Demo确认", "预算审批", "设备规格确认", "报价", "采购流程", "Won", "Lost")
LEGACY_DEMO_STAGE = "Wafer Demo确认"
LEGACY_STAGE_MAP = {
    "需求发现": QUALIFIED_OPPORTUNITY,
    "预算审批": DEMO_DONE,
    "设备规格确认": CUSTOMER_BUDGET_APPROVED,
    "报价": RFQ_VALIDATED,
    "采购流程": QUOTATION_SENT,
    "Won": PO_RECEIVED,
    "Lost": LOST,
}
# Entering one of these legacy stages happened exactly when its milestone was reached.
EXACT_ARRIVAL_STAGES = {"需求发现", "设备规格确认", "报价", "采购流程", "Won", "Lost"}
MILESTONE_EVENTS = {
    QUALIFIED_OPPORTUNITY: "created",
    DEMO_DONE: "demo_customer_review",
    CUSTOMER_BUDGET_APPROVED: "budget_confirmed",
    RFQ_VALIDATED: "rfq_approved",
    QUOTATION_SENT: "quotation_published",
    PO_RECEIVED: "po_confirmed",
}
OVERRIDES_KEY = "crm_stage_migration_overrides"
MIGRATION_ACTOR = "Administrator"
REPORT_COLUMNS = (
    "opportunity", "title", "owner", "legacy_stage", "new_stage", "lost_at_stage",
    "stage_changed_at", "arrival_basis", "evidence", "override_note", "warnings",
)


@dataclass
class Evidence:
    at: datetime | None
    basis: str
    note: str
    reference_doctype: str = ""
    reference_name: str = ""


@dataclass
class Snapshot:
    """Everything the planner may use about one Opportunity still on a legacy stage."""

    name: str
    stage: str
    created_at: datetime
    title: str = ""
    owner: str = ""
    source_lead: str = ""
    has_customer_review: bool = False
    customer_review: Evidence | None = None
    budget_confirmed: Evidence | None = None
    rfq_approved: Evidence | None = None
    rfq_created: Evidence | None = None
    quotation_published: Evidence | None = None
    won: Evidence | None = None
    lost: Evidence | None = None
    lost_by: str = ""
    lost_from_stage: str = ""
    first_booking: Evidence | None = None
    has_live_booking: bool = False
    stage_arrival: Evidence | None = None


@dataclass
class HistoryRow:
    to_stage: str
    event: str
    reached_at: datetime | None
    basis: str
    reason: str
    reference_doctype: str = ""
    reference_name: str = ""


@dataclass
class Plan:
    name: str
    legacy_stage: str
    stage: str
    lost_at_stage: str = ""
    lost_at: datetime | None = None
    lost_by: str = ""
    stage_changed_at: datetime | None = None
    rows: list[HistoryRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    override_note: str = ""


def normalize_legacy_stage(value: str | None) -> str:
    stripped = (value or "").strip()
    return LEGACY_ALIASES.get(stripped, stripped)


def map_legacy_stage(legacy: str, has_customer_review: bool) -> str:
    if legacy == LEGACY_DEMO_STAGE:
        return DEMO_DONE if has_customer_review else QUALIFIED_OPPORTUNITY
    return LEGACY_STAGE_MAP[legacy]


def _reviewed_by(snapshot: Snapshot, moment: datetime | None) -> bool:
    """Whether the customer had reviewed the Demo by ``moment``.

    A review recorded after the deal was lost says nothing about the stage it was lost at.
    Evidence without a timestamp keeps the plain flag.
    """
    if not snapshot.has_customer_review:
        return False
    if moment is None or not snapshot.customer_review or not snapshot.customer_review.at:
        return True
    return snapshot.customer_review.at <= moment


def validate_override(name: str, raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"{OVERRIDES_KEY}[{name}] must be an object.")
    stage = str(raw.get("stage") or "").strip()
    lost_at_stage = str(raw.get("lostAtStage") or "").strip()
    if stage and stage not in OPPORTUNITY_STAGES:
        raise ValueError(f"{OVERRIDES_KEY}[{name}].stage {stage!r} is not a stage.")
    if INTERNAL_VALIDATION in {stage, lost_at_stage}:
        raise ValueError(
            f"{OVERRIDES_KEY}[{name}]: internal_validation needs an approved request and cannot be migrated to.",
        )
    if lost_at_stage and lost_at_stage not in OPEN_STAGES:
        raise ValueError(f"{OVERRIDES_KEY}[{name}].lostAtStage {lost_at_stage!r} must come before po_received.")
    return {"stage": stage, "lostAtStage": lost_at_stage, "note": str(raw.get("note") or "").strip()}


def _milestone_evidence(snapshot: Snapshot, stage: str) -> Evidence | None:
    if stage == QUALIFIED_OPPORTUNITY:
        if snapshot.source_lead:
            return Evidence(
                snapshot.created_at, "evidence", f"由线索 {snapshot.source_lead} 转化", "Lead", snapshot.source_lead,
            )
        return Evidence(snapshot.created_at, "evidence", "商机创建")
    if stage == DEMO_DONE:
        return snapshot.customer_review
    if stage == CUSTOMER_BUDGET_APPROVED:
        return snapshot.budget_confirmed or snapshot.rfq_created
    if stage == RFQ_VALIDATED:
        return snapshot.rfq_approved
    if stage == QUOTATION_SENT:
        return snapshot.quotation_published
    if stage == PO_RECEIVED:
        return snapshot.won or snapshot.first_booking
    return None


def _current_arrival(snapshot: Snapshot, legacy: str, stage: str, overridden: bool) -> Evidence | None:
    if stage == LOST:
        return snapshot.lost
    if not overridden and legacy in EXACT_ARRIVAL_STAGES and snapshot.stage_arrival:
        return snapshot.stage_arrival
    evidence = _milestone_evidence(snapshot, stage)
    if evidence and evidence.at:
        return evidence
    if not overridden and legacy == "预算审批" and snapshot.stage_arrival:
        # The Demo had been accepted by then, so the customer reviewed it no later than this.
        return Evidence(snapshot.stage_arrival.at, "upper_bound", "进入 预算审批 的时间（客户评审不晚于此）")
    return None


def plan_opportunity(snapshot: Snapshot, override: dict[str, str] | None = None) -> Plan:
    legacy = normalize_legacy_stage(snapshot.stage)
    if legacy not in LEGACY_STAGES:
        raise ValueError(f"{snapshot.name}: {snapshot.stage!r} is not a legacy stage.")
    mapped = map_legacy_stage(legacy, snapshot.has_customer_review)
    plan = Plan(name=snapshot.name, legacy_stage=snapshot.stage, stage=mapped)
    if legacy == LEGACY_DEMO_STAGE:
        plan.warnings.append("demo_stage_reviewed" if snapshot.has_customer_review else "demo_stage_not_reviewed")
    if mapped == LOST:
        plan.lost_at = snapshot.lost.at if snapshot.lost else None
        plan.lost_by = snapshot.lost_by
        lost_from = normalize_legacy_stage(snapshot.lost_from_stage)
        if lost_from in LEGACY_STAGES and lost_from not in {"Won", "Lost"}:
            plan.lost_at_stage = map_legacy_stage(lost_from, _reviewed_by(snapshot, plan.lost_at))

    overridden = bool(override and (override["stage"] or override["lostAtStage"]))
    if override:
        plan.override_note = override["note"]
        if override["stage"] and override["stage"] != mapped:
            plan.stage = override["stage"]
            if plan.stage == LOST:
                plan.lost_at_stage = mapped if mapped in OPEN_STAGES else ""
            else:
                plan.lost_at_stage, plan.lost_at, plan.lost_by = "", None, ""
        if plan.stage == LOST and override["lostAtStage"]:
            plan.lost_at_stage = override["lostAtStage"]
        plan.warnings.append("override")
    if plan.stage == LOST and not plan.lost_at_stage:
        plan.warnings.append("lost_at_stage_unknown")
    if plan.stage != PO_RECEIVED and snapshot.has_live_booking:
        plan.warnings.append("live_booking_before_po_received")

    # Evidence rows for milestones already passed, then one migration row for the current stage.
    if plan.stage == LOST:
        passed = MILESTONE_STAGES[:stage_index(plan.lost_at_stage) + 1] if plan.lost_at_stage else MILESTONE_STAGES[:1]
    else:
        passed = MILESTONE_STAGES[:stage_index(plan.stage)]
    for stage in passed:
        evidence = _milestone_evidence(snapshot, stage)
        if stage == INTERNAL_VALIDATION or not evidence or not evidence.at:
            continue
        event = "lead_converted" if stage == QUALIFIED_OPPORTUNITY and snapshot.source_lead else MILESTONE_EVENTS[stage]
        plan.rows.append(HistoryRow(
            to_stage=stage, event=event, reached_at=evidence.at, basis=evidence.basis,
            reason=f"迁移凭证：{evidence.note}",
            reference_doctype=evidence.reference_doctype, reference_name=evidence.reference_name,
        ))

    arrival = _current_arrival(snapshot, legacy, plan.stage, overridden)
    has_time = bool(arrival and arrival.at)
    reasons = [f"旧阶段 {snapshot.stage}"]
    if has_time:
        reasons.append(arrival.note)
    else:
        plan.warnings.append("arrival_time_unknown")
    if override:
        reasons.append(f"销售修正：{plan.override_note}" if plan.override_note else "销售修正")
    plan.rows.append(HistoryRow(
        to_stage=plan.stage, event="migration",
        reached_at=arrival.at if has_time else None,
        basis=arrival.basis if has_time else "unknown",
        reason="；".join(reasons),
        reference_doctype=arrival.reference_doctype if has_time else "",
        reference_name=arrival.reference_name if has_time else "",
    ))
    plan.stage_changed_at = plan.rows[-1].reached_at
    if plan.stage_changed_at and any(row.reached_at > plan.stage_changed_at for row in plan.rows[:-1]):
        plan.warnings.append("evidence_after_current_stage")
    return plan


def _in_clause(values: list[str]) -> str:
    return ", ".join(["%s"] * len(values))


def _legacy_values() -> list[str]:
    return sorted({*LEGACY_STAGES, *LEGACY_ALIASES})


def collect_snapshots() -> list[Snapshot]:
    legacy_values = _legacy_values()
    opportunities = frappe.db.sql(
        "SELECT `name`, `title`, `opportunity_owner`, `stage`, `creation`, `source_lead` "
        # BINARY: the default collation ignores case, so the new `lost` would match legacy `Lost`.
        f"FROM `tabCRM Opportunity` WHERE BINARY `stage` IN ({_in_clause(legacy_values)}) ORDER BY `name`",
        legacy_values, as_dict=True,
    )
    if not opportunities:
        return []
    snapshots = {
        row.name: Snapshot(
            name=row.name, stage=row.stage, created_at=row.creation, title=row.title or "",
            owner=row.opportunity_owner or "", source_lead=row.source_lead or "",
        )
        for row in opportunities
    }
    names = list(snapshots)
    _collect_customer_review(snapshots, names)
    _collect_opportunity_history(snapshots, names)
    _collect_rfqs(snapshots, names)
    _collect_quotations(snapshots, names)
    _collect_bookings(snapshots, names)
    return list(snapshots.values())


def _collect_customer_review(snapshots: dict[str, Snapshot], names: list[str]) -> None:
    placeholders = _in_clause(names)
    for row in frappe.db.sql(
        f"""SELECT `request`.`opportunity`, `evaluation`.`status`, `evaluation`.`test_round`
        FROM `tabCRM Evaluation` AS `evaluation`
        JOIN `tabCRM Demo Request` AS `request` ON `request`.`name` = `evaluation`.`demo_request`
        WHERE `request`.`opportunity` IN ({placeholders})""",
        names, as_dict=True,
    ):
        if row.status in {"Customer Review", "Accepted"} or int(row.test_round or 1) > 1:
            snapshots[row.opportunity].has_customer_review = True
    for row in frappe.db.sql(
        f"""SELECT `request`.`opportunity`, `history`.`evaluation`, `history`.`at`
        FROM `tabCRM Evaluation History` AS `history`
        JOIN `tabCRM Evaluation` AS `evaluation` ON `evaluation`.`name` = `history`.`evaluation`
        JOIN `tabCRM Demo Request` AS `request` ON `request`.`name` = `evaluation`.`demo_request`
        WHERE `history`.`event_type` = 'Status' AND `history`.`to_value` = 'Customer Review'
          AND `request`.`opportunity` IN ({placeholders})
        ORDER BY `history`.`at`, `history`.`creation`""",
        names, as_dict=True,
    ):
        snapshot = snapshots[row.opportunity]
        snapshot.has_customer_review = True
        if not snapshot.customer_review:
            snapshot.customer_review = Evidence(
                row.at, "evidence", f"Evaluation {row.evaluation} 进入客户评审", "CRM Evaluation", row.evaluation,
            )
    for row in frappe.db.sql(
        f"""SELECT `request`.`opportunity`, `review`.`evaluation`, `review`.`at`
        FROM `tabCRM Evaluation Customer Review` AS `review`
        JOIN `tabCRM Evaluation` AS `evaluation` ON `evaluation`.`name` = `review`.`evaluation`
        JOIN `tabCRM Demo Request` AS `request` ON `request`.`name` = `evaluation`.`demo_request`
        WHERE `request`.`opportunity` IN ({placeholders})
        ORDER BY `review`.`at`, `review`.`creation`""",
        names, as_dict=True,
    ):
        snapshot = snapshots[row.opportunity]
        snapshot.has_customer_review = True
        if not snapshot.customer_review:
            # The comment is written when the customer review ends, so the review began no later.
            snapshot.customer_review = Evidence(
                row.at, "upper_bound", f"Evaluation {row.evaluation} 的客户意见（进入客户评审不晚于此）",
                "CRM Evaluation", row.evaluation,
            )


def _collect_opportunity_history(snapshots: dict[str, Snapshot], names: list[str]) -> None:
    for row in frappe.db.sql(
        f"""SELECT `opportunity`, `field`, `from_value`, `to_value`, `actor`, `at`
        FROM `tabCRM Opportunity History`
        WHERE `opportunity` IN ({_in_clause(names)}) AND `field` IN ('stage', 'stageRollback')
        ORDER BY `at`, `creation`""",
        names, as_dict=True,
    ):
        snapshot = snapshots[row.opportunity]
        raw_target = str(row.to_value or "")
        if row.field == "stageRollback":
            # Rollback rows store "<target> | <reason>".
            raw_target = raw_target.split(" | ", 1)[0]
        target = normalize_legacy_stage(raw_target)
        # Rows are oldest first, so the last match is the latest arrival.
        if target == normalize_legacy_stage(snapshot.stage):
            snapshot.stage_arrival = Evidence(row.at, "evidence", f"旧历史中进入 {target} 的时间")
        if row.field != "stage":
            continue
        if target == "设备规格确认":
            snapshot.budget_confirmed = Evidence(row.at, "evidence", "旧历史中手动推进到 设备规格确认")
        elif target == "Won":
            snapshot.won = Evidence(row.at, "evidence", "旧历史中标记 Won")
        elif target == "Lost":
            snapshot.lost = Evidence(row.at, "evidence", "旧历史中标记 Lost")
            snapshot.lost_by = row.actor or ""
            snapshot.lost_from_stage = row.from_value or ""


def _collect_rfqs(snapshots: dict[str, Snapshot], names: list[str]) -> None:
    for row in frappe.db.sql(
        "SELECT `opportunity`, `name`, `status`, `approved_at`, `creation` FROM `tabCRM RFQ` "
        f"WHERE `opportunity` IN ({_in_clause(names)})",
        names, as_dict=True,
    ):
        snapshot = snapshots[row.opportunity]
        snapshot.rfq_created = Evidence(
            row.creation, "upper_bound", f"RFQ {row.name} 创建（预算批准不晚于此）", "CRM RFQ", row.name,
        )
        if row.status == "Approved" and row.approved_at:
            snapshot.rfq_approved = Evidence(row.approved_at, "evidence", f"RFQ {row.name} 经理批准", "CRM RFQ", row.name)


def _collect_quotations(snapshots: dict[str, Snapshot], names: list[str]) -> None:
    opportunity = "COALESCE(NULLIF(`version`.`opportunity`, ''), `quotation`.`opportunity`)"
    for row in frappe.db.sql(
        f"""SELECT {opportunity} AS `opportunity`, `version`.`name`, `version`.`published_at`
        FROM `tabCRM Quotation Version` AS `version`
        JOIN `tabCRM Quotation` AS `quotation` ON `quotation`.`name` = `version`.`quotation`
        WHERE `version`.`published_at` IS NOT NULL AND {opportunity} IN ({_in_clause(names)})
        ORDER BY `version`.`published_at`, `version`.`creation`""",
        names, as_dict=True,
    ):
        snapshot = snapshots[row.opportunity]
        if not snapshot.quotation_published:
            snapshot.quotation_published = Evidence(
                row.published_at, "evidence", f"报价版本 {row.name} 首次发布", "CRM Quotation Version", row.name,
            )


def _collect_bookings(snapshots: dict[str, Snapshot], names: list[str]) -> None:
    for row in frappe.db.sql(
        "SELECT `source_opportunity`, `name`, `status`, `creation` FROM `tabCRM Booking` "
        f"WHERE `source_opportunity` IN ({_in_clause(names)}) ORDER BY `creation`",
        names, as_dict=True,
    ):
        snapshot = snapshots[row.source_opportunity]
        if row.status != "Cancelled":
            snapshot.has_live_booking = True
        if not snapshot.first_booking:
            snapshot.first_booking = Evidence(
                row.creation, "upper_bound", f"Booking {row.name} 创建（收到 PO 不晚于此）", "CRM Booking", row.name,
            )


def load_overrides() -> dict[str, dict[str, str]]:
    raw = frappe.conf.get(OVERRIDES_KEY) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{OVERRIDES_KEY} must be an object keyed by Opportunity ID.")
    return {name: validate_override(name, value) for name, value in raw.items()}


def build_plans() -> tuple[list[Plan], list[Snapshot], list[str]]:
    overrides = load_overrides()
    snapshots = collect_snapshots()
    plans = [plan_opportunity(snapshot, overrides.get(snapshot.name)) for snapshot in snapshots]
    unused_overrides = sorted(set(overrides) - {plan.name for plan in plans})
    return plans, snapshots, unused_overrides


def apply_plans(plans: list[Plan]) -> None:
    recorded_at = frappe.utils.now_datetime()
    for plan in plans:
        for row in plan.rows:
            frappe.get_doc({
                "doctype": "CRM Opportunity Stage History",
                "opportunity": plan.name,
                "from_stage": "",
                "to_stage": row.to_stage,
                "source": "migration",
                "event": row.event,
                "reference_doctype": row.reference_doctype,
                "reference_name": row.reference_name,
                "reason": row.reason,
                "actor": MIGRATION_ACTOR,
                "recorded_at": recorded_at,
                "reached_at": row.reached_at,
                "reached_at_basis": row.basis,
            }).insert(ignore_permissions=True)
        is_lost = plan.stage == LOST
        lost_by = plan.lost_by if is_lost and plan.lost_by and frappe.db.exists("User", plan.lost_by) else None
        # Migration is not a user edit, so modified stays as it was.
        frappe.db.set_value("CRM Opportunity", plan.name, {
            "stage": plan.stage,
            "legacy_stage": plan.legacy_stage,
            "stage_changed_at": plan.stage_changed_at,
            "lost_at_stage": plan.lost_at_stage if is_lost and plan.lost_at_stage else None,
            "lost_at": plan.lost_at if is_lost else None,
            "lost_by": lost_by,
        }, update_modified=False)


def _format_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _report_path(kind: str) -> Path:
    directory = Path(frappe.get_site_path("private", "crm-stage-migration")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{kind}-{frappe.utils.now_datetime():%Y%m%d-%H%M%S}.csv"


def write_plan_report(kind: str, plans: list[Plan], snapshots: list[Snapshot], unused_overrides: list[str]) -> str:
    path = _report_path(kind)
    by_name = {snapshot.name: snapshot for snapshot in snapshots}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        for plan in plans:
            snapshot = by_name[plan.name]
            writer.writerow([
                plan.name, snapshot.title, snapshot.owner, plan.legacy_stage, plan.stage, plan.lost_at_stage,
                _format_time(plan.stage_changed_at), plan.rows[-1].basis,
                "; ".join(f"{row.to_stage}@{_format_time(row.reached_at)}({row.basis})" for row in plan.rows[:-1]),
                plan.override_note, " ".join(plan.warnings),
            ])
        for name in unused_overrides:
            writer.writerow([name, "", "", "", "", "", "", "", "", "", "override_not_applied"])
    return str(path)


def _summary(plans: list[Plan], report: str, unused_overrides: list[str]) -> dict[str, Any]:
    stages: dict[str, int] = {}
    for plan in plans:
        stages[plan.stage] = stages.get(plan.stage, 0) + 1
    return {
        "opportunities": len(plans),
        "stages": stages,
        "withWarnings": sum(1 for plan in plans if plan.warnings),
        "unusedOverrides": unused_overrides,
        "report": report,
    }


def dry_run() -> dict[str, Any]:
    """Plan the migration without touching the database; returns a summary and the report path."""

    plans, snapshots, unused_overrides = build_plans()
    return _summary(plans, write_plan_report("dry-run", plans, snapshots, unused_overrides), unused_overrides)


def apply_migration() -> dict[str, Any]:
    """Migrate every Opportunity still on a legacy stage; rerunning finds nothing left to do."""

    plans, snapshots, unused_overrides = build_plans()
    if not plans:
        return _summary(plans, "", unused_overrides)
    apply_plans(plans)
    return _summary(plans, write_plan_report("applied", plans, snapshots, unused_overrides), unused_overrides)


def verify() -> dict[str, Any]:
    """Check migrated Opportunities against their migration rows; read-only apart from the report."""

    findings: list[tuple[str, str, str, str]] = []
    legacy_values = _legacy_values()
    for row in frappe.db.sql(
        f"SELECT `name`, `stage` FROM `tabCRM Opportunity` WHERE BINARY `stage` IN ({_in_clause(legacy_values)})",
        legacy_values, as_dict=True,
    ):
        findings.append((row.name, "error", "legacy_stage_remaining", row.stage))
    for opportunity in frappe.db.sql(
        "SELECT `name`, `stage`, `legacy_stage`, `stage_changed_at`, `lost_at_stage` FROM `tabCRM Opportunity` "
        "WHERE COALESCE(`legacy_stage`, '') != '' ORDER BY `name`",
        as_dict=True,
    ):
        rows = frappe.get_all(
            "CRM Opportunity Stage History",
            filters={"opportunity": opportunity.name},
            fields=["event", "to_stage", "reached_at"],
            order_by="recorded_at asc, creation asc",
        )
        migration_indexes = [index for index, row in enumerate(rows) if row.event == "migration"]
        if len(migration_indexes) != 1:
            findings.append((opportunity.name, "error", "migration_row_count", str(len(migration_indexes))))
            continue
        migration_row = rows[migration_indexes[0]]
        # Stage changes after the migration legitimately move the Opportunity on.
        if migration_indexes[0] == len(rows) - 1:
            if migration_row.to_stage != opportunity.stage:
                findings.append((
                    opportunity.name, "error", "stage_mismatch", f"{migration_row.to_stage} != {opportunity.stage}",
                ))
            if migration_row.reached_at != opportunity.stage_changed_at:
                findings.append((
                    opportunity.name, "error", "stage_changed_at_mismatch",
                    f"{_format_time(migration_row.reached_at)} != {_format_time(opportunity.stage_changed_at)}",
                ))
        if opportunity.stage == LOST and not opportunity.lost_at_stage:
            findings.append((opportunity.name, "warning", "lost_at_stage_unknown", ""))

    path = _report_path("verify")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("opportunity", "severity", "check", "detail"))
        writer.writerows(findings)
    errors = sum(1 for finding in findings if finding[1] == "error")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": len(findings) - errors,
        "findings": [
            {"opportunity": name, "severity": severity, "check": check, "detail": detail}
            for name, severity, check, detail in findings
        ],
        "report": str(path),
    }
