"""Derive Installed Tool lifecycle state and create minimal legacy audit history."""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import getdate

from rayher_crm.patches.v1_0.prepare_installed_tool_date_fields import normalize_legacy_date


LIFECYCLE_STAGES = ("FAT", "Shipment", "Installation", "SAT", "Warranty")
STATUS_STAGE_MAP = {
    "delivery preparation": "FAT",
    "fat": "FAT",
    "shipment": "Shipment",
    "shipped": "Shipment",
    "in transit": "Shipment",
    "installation": "Installation",
    "installing": "Installation",
    "installation complete": "SAT",
    "sat": "SAT",
    "production": "Warranty",
    "installed": "Warranty",
    "running": "Warranty",
}
LEGACY_COMMENT = "Legacy milestone migration"


def _decode_milestones(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        decoded = value
    else:
        try:
            decoded = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            decoded = []
    return [row for row in decoded if isinstance(row, dict)] if isinstance(decoded, list) else []


def build_lifecycle_state(value: Any, status: Any = None) -> tuple[str, list[dict[str, str]]]:
    existing = {
        str(row.get("label") or "").strip(): row
        for row in _decode_milestones(value)
        if str(row.get("label") or "").strip() in LIFECYCLE_STAGES
    }
    all_done = all(existing.get(stage, {}).get("state") == "Done" for stage in LIFECYCLE_STAGES)
    current_stage = next(
        (stage for stage in LIFECYCLE_STAGES if existing.get(stage, {}).get("state") == "Current"),
        None,
    )
    if not current_stage:
        current_stage = STATUS_STAGE_MAP.get(str(status or "").strip().lower(), "FAT")
    if all_done:
        current_stage = "Warranty"

    current_index = LIFECYCLE_STAGES.index(current_stage)
    milestones: list[dict[str, str]] = []
    for index, stage in enumerate(LIFECYCLE_STAGES):
        source = existing.get(stage, {})
        if all_done or index < current_index:
            state = "Done"
            milestone_date = normalize_legacy_date(source.get("date")) or ""
        elif index == current_index:
            state = "Current"
            milestone_date = ""
        else:
            state = "Waiting"
            milestone_date = ""
        milestones.append({"label": stage, "date": milestone_date, "state": state})
    return current_stage, milestones


def _migrate_done_history(row, legacy: list[dict[str, Any]], current_stage: str) -> None:
    current_index = LIFECYCLE_STAGES.index(current_stage)
    all_done = all(
        any(item.get("label") == stage and item.get("state") == "Done" for item in legacy)
        for stage in LIFECYCLE_STAGES
    )
    by_stage = {str(item.get("label") or "").strip(): item for item in legacy}
    for index, stage in enumerate(LIFECYCLE_STAGES):
        source = by_stage.get(stage, {})
        if source.get("state") != "Done" or (not all_done and index >= current_index):
            continue
        to_stage = LIFECYCLE_STAGES[index + 1] if index + 1 < len(LIFECYCLE_STAGES) else "Completed"
        if frappe.db.exists(
            "CRM Installed Tool Lifecycle History",
            {"installed_tool": row.name, "to_stage": to_stage, "comment": LEGACY_COMMENT},
        ):
            continue
        completed_at = normalize_legacy_date(source.get("date")) or str(getdate(row.modified))
        frappe.get_doc({
            "doctype": "CRM Installed Tool Lifecycle History",
            "installed_tool": row.name,
            "at": row.modified,
            "actor": row.modified_by or "Administrator",
            "from_stage": stage,
            "to_stage": to_stage,
            "completed_at": completed_at,
            "result": LEGACY_COMMENT,
            "open_issues": "Unknown",
            "customer_signoff": "Unknown",
            "comment": LEGACY_COMMENT,
            "evidence": "[]",
        }).insert(ignore_permissions=True)


def execute() -> None:
    if not frappe.db.table_exists("CRM Installed Tool"):
        return
    columns = set(frappe.db.get_table_columns("CRM Installed Tool"))
    if not {"lifecycle_stage", "milestones", "status"}.issubset(columns):
        return
    rows = frappe.db.sql(
        "SELECT `name`, `status`, `lifecycle_stage`, `milestones`, `modified`, `modified_by` FROM `tabCRM Installed Tool`",
        as_dict=True,
    )
    for row in rows:
        legacy = _decode_milestones(row.milestones)
        stage, milestones = build_lifecycle_state(legacy, row.status)
        _migrate_done_history(row, legacy, stage)
        encoded = json.dumps(milestones, ensure_ascii=False, separators=(",", ":"))
        if row.lifecycle_stage == stage and (row.milestones or "") == encoded:
            continue
        frappe.db.sql(
            "UPDATE `tabCRM Installed Tool` SET `lifecycle_stage`=%s, `milestones`=%s WHERE `name`=%s",
            (stage, encoded, row.name),
        )