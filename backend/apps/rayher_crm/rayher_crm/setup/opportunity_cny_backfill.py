"""Give Opportunities priced in CNY their CNY amount, and list the ones Sales still have to fill in.

- Sales enter ``amount_cny`` on every Opportunity; 0 means nobody has entered it yet.
- When the field goes live, an Opportunity priced in CNY takes its ``amount``. Opportunities in any
  other currency stay empty until Sales fill them in, which any edit of the Opportunity now requires.
- Every filled Opportunity gets a ``CRM Opportunity History`` row (``field = amount_cny``, from empty)
  written by the user running the migration, so the value has the same trail as a Sales edit.
- ``dry_run`` and ``list_missing`` do not write to the database. They write CSV reports under
  ``sites/<site>/private/crm-cny-backfill/``.
- The ``backfill_opportunity_cny_amount`` patch runs ``apply``; reruns change nothing.

Run on a restored copy first::

    bench --site <site> execute rayher_crm.setup.opportunity_cny_backfill.dry_run
    bench --site <site> migrate
    bench --site <site> execute rayher_crm.setup.opportunity_cny_backfill.list_missing
"""

from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import frappe


OPPORTUNITY = "CRM Opportunity"
FILLABLE = "`currency` = 'CNY' AND COALESCE(`amount_cny`, 0) = 0 AND `amount` > 0"
MISSING = "COALESCE(`amount_cny`, 0) = 0"
REPORT_COLUMNS = ("opportunity", "title", "owner", "stage", "currency", "amount", "amount_cny")


def _rows(where: str) -> list[dict[str, Any]]:
    return frappe.db.sql(
        "SELECT `name`, `title`, `opportunity_owner` AS `owner`, `stage`, `currency`, "
        "CAST(`amount` AS CHAR) AS `amount`, CAST(`amount_cny` AS CHAR) AS `amount_cny` "
        f"FROM `tab{OPPORTUNITY}` WHERE {where} ORDER BY `opportunity_owner`, `name`",
        as_dict=True,
    )


def _money(value: Any) -> str:
    amount = Decimal(str(value or 0))
    return format(amount, ".2f") if amount else ""


def _report(kind: str, rows: list[dict[str, Any]]) -> str:
    directory = Path(frappe.get_site_path("private", "crm-cny-backfill")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{kind}-{frappe.utils.now_datetime():%Y%m%d-%H%M%S}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        for row in rows:
            writer.writerow([
                row.name, row.title or "", row.owner or "", row.stage or "", row.currency or "",
                _money(row.amount), _money(row.amount_cny),
            ])
    return str(path)


def _summary(rows: list[dict[str, Any]], report: str) -> dict[str, Any]:
    return {
        "count": len(rows),
        "byCurrency": dict(sorted(Counter(row.currency or "" for row in rows).items())),
        "report": report,
    }


def dry_run() -> dict[str, Any]:
    """What apply would fill and what Sales would still have to fill in; changes nothing."""

    fill = _rows(FILLABLE)
    filled = {row.name for row in fill}
    left = [row for row in _rows(MISSING) if row.name not in filled]
    return {
        "fill": _summary(fill, _report("dry-run-fill", fill)),
        "stillMissing": _summary(left, _report("dry-run-still-missing", left)),
    }


def apply() -> dict[str, Any]:
    """Copy the amount of every CNY Opportunity that has no CNY amount yet, with a history row each."""

    fill = _rows(FILLABLE)
    at = frappe.utils.now_datetime()
    for row in fill:
        # A backfill is not a user edit, so modified stays as it was.
        frappe.db.sql(
            f"UPDATE `tab{OPPORTUNITY}` SET `amount_cny` = `amount` WHERE `name` = %s AND {FILLABLE}",
            (row.name,),
        )
        frappe.get_doc({
            "doctype": "CRM Opportunity History",
            "opportunity": row.name,
            "actor": frappe.session.user,
            "at": at,
            "field": "amount_cny",
            "from_value": "",
            "to_value": _money(row.amount),
        }).insert(ignore_permissions=True)
    left = _rows(MISSING)
    return {
        "filled": _summary(fill, _report("applied", fill) if fill else ""),
        "stillMissing": _summary(left, _report("still-missing", left) if left else ""),
    }


def list_missing() -> dict[str, Any]:
    """Every Opportunity Sales still have to give a CNY amount; changes nothing apart from the report."""

    rows = _rows(MISSING)
    return {
        **_summary(rows, _report("missing", rows)),
        "opportunities": [
            {
                "name": row.name, "title": row.title or "", "owner": row.owner or "", "stage": row.stage or "",
                "currency": row.currency or "", "amount": _money(row.amount),
            }
            for row in rows
        ],
    }
