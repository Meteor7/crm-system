"""Plan, apply and verify the move from free-text regions to the shared region options.

- Customer ``custom_crm_region`` and Opportunity ``sub_region`` are migrated together.
- A spelling of a preset becomes the preset ("华东", "East" -> "East China"). Any other English
  value becomes a custom region, reusing an existing option that differs only in case, spacing
  or punctuation.
- Anything else, such as a Chinese city name, is not guessed: ``apply_migration`` stops and lists
  it until a person maps it. Mappings live in site_config under ``crm_region_migration_overrides``,
  keyed by the value as stored today, e.g. ``{"上海": "East China", "Korea": "Overseas"}``.
- The option list keeps the presets and the custom regions still in use; unused ones are dropped.
- ``dry_run`` and ``verify`` do not write to the database. They write CSV reports under
  ``sites/<site>/private/crm-region-migration/``.
- The ``normalize_crm_regions`` patch applies the same plan and turns the field into a Select.
- Undoing the migration means restoring the pre-upgrade backup.

Run on a restored copy first::

    bench --site <site> execute rayher_crm.setup.region_migration.dry_run
    bench --site <site> migrate
    bench --site <site> execute rayher_crm.setup.region_migration.verify

The Review region filter stays off until verify passes and Sales have confirmed the report::

    bench --site <site> set-config -p crm_cockpit_region_migration_verified True

``-p`` reads the value as a Python literal, so it is ``True``; a lowercase ``true`` fails. To take the flag back out,
``bench --site <site> set-config crm_cockpit_region_migration_verified None`` (without ``-p``) removes the key.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frappe

from rayher_crm.services.regions import (
    REGION_PRESETS,
    collapse_region,
    is_english_region,
    matching_region,
    options_text,
    preset_region,
    region_key,
    region_options,
)


OVERRIDES_KEY = "crm_region_migration_overrides"
CUSTOMER = "Customer"
OPPORTUNITY = "CRM Opportunity"
REPORT_COLUMNS = ("doctype", "name", "title", "owner", "from", "to", "rule", "warnings")


@dataclass(frozen=True)
class RegionRow:
    doctype: str
    name: str
    title: str
    owner: str
    value: str


@dataclass
class ValuePlan:
    value: str
    target: str
    rule: str
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.value != self.target


def load_overrides() -> dict[str, str]:
    raw = frappe.conf.get(OVERRIDES_KEY) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{OVERRIDES_KEY} must be an object keyed by the stored region.")
    overrides: dict[str, str] = {}
    for value, target in raw.items():
        target_text = collapse_region(target)
        if not target_text:
            raise ValueError(f"{OVERRIDES_KEY}[{value}] needs a target region.")
        if not preset_region(target_text) and not is_english_region(target_text):
            raise ValueError(f"{OVERRIDES_KEY}[{value}] {target_text!r} must be a preset or an English name.")
        overrides[str(value)] = target_text
    return overrides


def plan_values(
    counts: Counter[str], existing_options: Any, overrides: dict[str, str],
) -> tuple[dict[str, ValuePlan], list[str]]:
    """Map every stored spelling to its target; returns the plans and the resulting option list.

    Overrides and presets are settled first. The more common of two near-duplicate custom
    spellings becomes the option. An existing custom option survives only while a stored value
    still uses it, and a value that is neither a preset nor English is left ``unmapped``.
    """

    options = list(REGION_PRESETS)
    existing = [option for option in region_options(existing_options) if option not in REGION_PRESETS]
    plans: dict[str, ValuePlan] = {}
    ordered = sorted(counts, key=lambda value: (-counts[value], value))

    def keep(target: str) -> str:
        if target and target not in options:
            options.append(target)
        return target

    for value in ordered:
        text = collapse_region(value)
        override = overrides.get(value, overrides.get(text))
        if override is not None:
            plans[value] = ValuePlan(value, keep(matching_region(override, [*options, *existing]) or override), "override")
        elif not text:
            plans[value] = ValuePlan(value, "", "empty")
        elif preset_region(text):
            plans[value] = ValuePlan(value, preset_region(text), "preset")
    for value in ordered:
        if value in plans:
            continue
        text = collapse_region(value)
        match = matching_region(text, [*options, *existing])
        if match:
            plans[value] = ValuePlan(value, keep(match), "existing_option")
        elif is_english_region(text):
            plans[value] = ValuePlan(value, keep(text), "custom")
        else:
            # A city name or other non-English value is not guessed; a person maps it with an override.
            plans[value] = ValuePlan(value, text, "unmapped", ["not_english"])
    return plans, options


def collect_rows() -> list[RegionRow]:
    customers = frappe.db.sql(
        "SELECT `name`, `customer_name` AS `title`, `custom_crm_owner` AS `owner`, `custom_crm_region` AS `value` "
        "FROM `tabCustomer` ORDER BY `name`",
        as_dict=True,
    )
    opportunities = frappe.db.sql(
        "SELECT `name`, `title`, `opportunity_owner` AS `owner`, `sub_region` AS `value` "
        "FROM `tabCRM Opportunity` ORDER BY `name`",
        as_dict=True,
    )
    return [
        RegionRow(doctype, row.name, row.title or "", row.owner or "", row.value or "")
        for doctype, rows in ((CUSTOMER, customers), (OPPORTUNITY, opportunities))
        for row in rows
    ]


def _region_field() -> dict[str, Any]:
    field_row = frappe.db.get_value(
        "Custom Field", {"dt": CUSTOMER, "fieldname": "custom_crm_region"}, ["name", "fieldtype", "options"], as_dict=True,
    )
    if not field_row:
        raise ValueError("Customer.custom_crm_region is not installed.")
    return field_row


def build_plans() -> tuple[list[RegionRow], dict[str, ValuePlan], list[str], list[str]]:
    overrides = load_overrides()
    rows = collect_rows()
    plans, options = plan_values(Counter(row.value for row in rows), _region_field().options, overrides)
    unused_overrides = sorted(set(overrides) - set(plans) - {collapse_region(value) for value in plans})
    return rows, plans, options, unused_overrides


def _report_path(kind: str) -> Path:
    directory = Path(frappe.get_site_path("private", "crm-region-migration")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{kind}-{frappe.utils.now_datetime():%Y%m%d-%H%M%S}.csv"


def write_plan_report(kind: str, rows: list[RegionRow], plans: dict[str, ValuePlan], unused_overrides: list[str]) -> str:
    path = _report_path(kind)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        for row in rows:
            plan = plans[row.value]
            if plan.changed or plan.warnings:
                writer.writerow([
                    row.doctype, row.name, row.title, row.owner, row.value, plan.target, plan.rule, " ".join(plan.warnings),
                ])
        for value in unused_overrides:
            writer.writerow(["", "", "", "", value, "", "override", "override_not_applied"])
    return str(path)


def _summary(rows: list[RegionRow], plans: dict[str, ValuePlan], options: list[str], report: str, unused_overrides: list[str]) -> dict[str, Any]:
    usage: dict[str, Counter[str]] = {value: Counter() for value in plans}
    for row in rows:
        usage[row.value][row.doctype] += 1
    values = [
        {
            "from": plan.value,
            "to": plan.target,
            "rule": plan.rule,
            "customers": usage[plan.value][CUSTOMER],
            "opportunities": usage[plan.value][OPPORTUNITY],
            "warnings": plan.warnings,
        }
        for plan in sorted(plans.values(), key=lambda item: (item.target, item.value))
        if plan.value
    ]
    return {
        "customers": sum(1 for row in rows if row.doctype == CUSTOMER),
        "opportunities": sum(1 for row in rows if row.doctype == OPPORTUNITY),
        "changes": sum(1 for row in rows if plans[row.value].changed),
        "values": values,
        "options": options,
        "customRegions": [option for option in options if option not in REGION_PRESETS],
        "unmapped": sorted({plan.value for plan in plans.values() if plan.rule == "unmapped"}),
        "unusedOverrides": unused_overrides,
        "report": report,
    }


def dry_run() -> dict[str, Any]:
    """Plan the migration without touching the database; returns the value mapping and the report path."""

    rows, plans, options, unused_overrides = build_plans()
    return _summary(rows, plans, options, write_plan_report("dry-run", rows, plans, unused_overrides), unused_overrides)


def apply_migration() -> dict[str, Any]:
    """Store every region in its normalized spelling and turn the field into a Select; reruns change nothing.

    Stops before writing anything while a stored value is unmapped.
    """

    rows, plans, options, unused_overrides = build_plans()
    unmapped = Counter(row.value for row in rows if plans[row.value].rule == "unmapped")
    if unmapped:
        listed = ", ".join(f"{value} ({count})" for value, count in sorted(unmapped.items()))
        raise RuntimeError(
            f"Regions need a person to decide: {listed}. Map each to a preset or an English region "
            f"in site_config {OVERRIDES_KEY}, then run the migration again."
        )
    region_field = _region_field()
    target_options = options_text(options)
    if region_field.fieldtype != "Select" or (region_field.options or "") != target_options:
        frappe.db.set_value(
            "Custom Field", region_field.name, {"fieldtype": "Select", "options": target_options}, update_modified=False,
        )
        frappe.clear_cache(doctype=CUSTOMER)
    # Normalizing a spelling is not a user edit, so modified stays as it was.
    for row in rows:
        plan = plans[row.value]
        if not plan.changed:
            continue
        fieldname = "custom_crm_region" if row.doctype == CUSTOMER else "sub_region"
        frappe.db.set_value(row.doctype, row.name, fieldname, plan.target, update_modified=False)
    report = write_plan_report("applied", rows, plans, unused_overrides) if any(plan.changed for plan in plans.values()) else ""
    return _summary(rows, plans, options, report, unused_overrides)


def verify() -> dict[str, Any]:
    """Check the field and every stored region against the shared options; read-only apart from the report."""

    findings: list[tuple[str, str, str, str, str]] = []
    region_field = _region_field()
    options = [line.strip() for line in (region_field.options or "").splitlines() if line.strip()]
    if region_field.fieldtype != "Select":
        findings.append(("Custom Field", region_field.name, "error", "field_not_select", region_field.fieldtype))
    for preset in REGION_PRESETS:
        if preset not in options:
            findings.append(("Custom Field", region_field.name, "error", "preset_missing", preset))
    seen: dict[str, str] = {}
    for option in options:
        if preset_region(option) and option not in REGION_PRESETS:
            findings.append(("Custom Field", region_field.name, "error", "preset_spelling_option", option))
        key = region_key(option)
        if key in seen:
            findings.append(("Custom Field", region_field.name, "error", "duplicate_option", f"{seen[key]} / {option}"))
        seen.setdefault(key, option)
        if option not in REGION_PRESETS and not is_english_region(option):
            findings.append(("Custom Field", region_field.name, "error", "custom_region_not_english", option))
    for row in collect_rows():
        if not row.value:
            if row.doctype == CUSTOMER:
                findings.append((row.doctype, row.name, "warning", "region_empty", row.title))
            continue
        if row.value not in options:
            findings.append((row.doctype, row.name, "error", "region_not_in_options", row.value))

    path = _report_path("verify")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("doctype", "name", "severity", "check", "detail"))
        writer.writerows(findings)
    errors = sum(1 for finding in findings if finding[2] == "error")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": len(findings) - errors,
        "options": options,
        "findings": [
            {"doctype": doctype, "name": name, "severity": severity, "check": check, "detail": detail}
            for doctype, name, severity, check, detail in findings
        ],
        "report": str(path),
    }
