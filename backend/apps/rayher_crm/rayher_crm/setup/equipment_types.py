"""Keep the equipment type options in step with the stored Opportunities; read-only report.

Stored ``CRM Opportunity.tool_type`` values that differ only in case, accents, spacing or punctuation
are one type. ``sync`` registers each type once: a preset is never registered, an existing custom
type keeps its spelling, and a new type takes its most common stored spelling. No Opportunity is
rewritten. ``report`` lists every stored value with hints for a person (for example a value that
contains a preset name, like ``Kibo 4895C``)::

    bench --site <site> execute rayher_crm.setup.equipment_types.report

``sync`` runs on every migrate (``sync_after_migrate``) and drops custom types no Opportunity uses
any more, the same way unused custom regions are dropped.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import frappe

from rayher_crm.services.equipment import EQUIPMENT_PRESETS, EQUIPMENT_TYPE, equipment_key, lock_catalog


def stored_values() -> Counter[str]:
    # Counted in Python: the column's collation would fold "Nansi" and "nansi" into one group.
    rows = frappe.db.sql("SELECT `tool_type` FROM `tabCRM Opportunity`")
    return Counter(text for text in (str(row[0] or "").strip() for row in rows) if text)


def sync_after_migrate() -> dict[str, list[str]]:
    """The after_migrate entry point.

    Migrate can run while the old web workers still serve saves. Committing first starts a new
    transaction, so the reads in ``sync``, taken after the catalog lock, see every save that
    committed before it; later saves of custom types wait for the lock.
    """

    frappe.db.commit()
    return sync()


def sync() -> dict[str, list[str]]:
    # Saves that use a custom type hold this lock until they commit, so none of them adds or
    # starts using a type between the reads below. Opportunity rows are not locked: a save holds
    # its row while it waits for this lock, and locking rows here too could deadlock.
    lock_catalog()
    counts = stored_values()
    # One entry per type, holding its most common stored spelling; most common type first.
    stored: dict[str, str] = {}
    for value in sorted(counts, key=lambda value: (-counts[value], value)):
        stored.setdefault(equipment_key(value), value)
    existing = frappe.db.sql(
        f"SELECT `name`, `equipment_name` FROM `tab{EQUIPMENT_TYPE}` ORDER BY `creation`, `name` FOR UPDATE",
        as_dict=True,
    )
    kept = {equipment_key(preset) for preset in EQUIPMENT_PRESETS}
    unused = []
    for row in existing:
        key = equipment_key(row.equipment_name)
        # A preset spelling, a second spelling of a kept type, or a type nobody uses any more.
        if key in kept or key not in stored:
            unused.append(row)
        else:
            kept.add(key)
    # Remove before adding: equipment_name is unique, and the collation ignores case.
    if unused:
        frappe.db.delete(EQUIPMENT_TYPE, {"name": ["in", [row.name for row in unused]]})
    added = []
    for key, value in stored.items():
        # The unique index also folds a few characters the key keeps apart ("〇" and "0"); the
        # spelling already registered stands for both, as it does when an Opportunity is saved.
        if key in kept or frappe.db.sql(f"SELECT 1 FROM `tab{EQUIPMENT_TYPE}` WHERE `equipment_name` = %s", (value,)):
            continue
        frappe.get_doc({"doctype": EQUIPMENT_TYPE, "equipment_name": value}).insert(ignore_permissions=True)
        added.append(value)
    return {"added": added, "removed": sorted(row.equipment_name for row in unused)}


def report() -> dict[str, Any]:
    """Every stored equipment value with its count and hints for a person reviewing the catalog."""

    counts = stored_values()
    preset_keys = {equipment_key(preset): preset for preset in EQUIPMENT_PRESETS}
    by_key: dict[str, list[str]] = {}
    for value in counts:
        by_key.setdefault(equipment_key(value), []).append(value)
    values = []
    for value in sorted(counts, key=lambda item: (-counts[item], item)):
        key = equipment_key(value)
        hints = []
        if value not in EQUIPMENT_PRESETS and key in preset_keys:
            hints.append(f"spelling_of_preset:{preset_keys[key]}")
        hints += [f"contains_preset:{preset}" for preset_key, preset in preset_keys.items()
                  if preset_key != key and preset_key in key]
        hints += [f"same_as:{other}" for other in by_key[key] if other != value]
        values.append({"value": value, "opportunities": counts[value],
                       "kind": "preset" if value in EQUIPMENT_PRESETS else "custom", "hints": hints})
    return {
        "presets": list(EQUIPMENT_PRESETS),
        "opportunities": sum(counts.values()),
        "values": values,
        "needsReview": [item["value"] for item in values if item["hints"]],
    }
