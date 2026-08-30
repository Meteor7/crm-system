"""Clear legacy placeholder text before Installed Tool fields become SQL Date columns."""

from __future__ import annotations

from datetime import date
from typing import Any

import frappe


DATE_FIELDS = ("warranty_start", "warranty_end", "last_service")


def normalize_legacy_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def execute() -> None:
    if not frappe.db.table_exists("CRM Installed Tool"):
        return
    columns = set(frappe.db.get_table_columns("CRM Installed Tool"))
    fields = [field for field in DATE_FIELDS if field in columns]
    if not fields:
        return
    selected = ", ".join(f"`{field}`" for field in fields)
    rows = frappe.db.sql(
        f"SELECT `name`, {selected} FROM `tabCRM Installed Tool`",
        as_dict=True,
    )
    for row in rows:
        for field in fields:
            normalized = normalize_legacy_date(row.get(field))
            current = str(row.get(field) or "").strip() or None
            if current == normalized:
                continue
            frappe.db.sql(
                f"UPDATE `tabCRM Installed Tool` SET `{field}`=%s WHERE `name`=%s",
                (normalized, row.name),
            )