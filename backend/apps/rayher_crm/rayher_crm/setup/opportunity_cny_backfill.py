"""Give Opportunities priced in CNY their CNY amount, and list the ones Sales still have to fill in.

- Sales enter ``amount_cny`` on every Opportunity; 0 means nobody has entered it yet.
- When the field goes live, an Opportunity priced in CNY takes its ``amount``. Opportunities in any
  other currency stay empty until Sales fill them in, which any edit of the Opportunity now requires.
- Every filled Opportunity gets a ``CRM Opportunity History`` row (``field = amount_cny``, from empty)
  written by the user running the migration, so the value has the same trail as a Sales edit.
- ``dry_run`` and ``list_missing`` do not write to the database. They write CSV reports under
  ``sites/<site>/private/crm-cny-backfill/``.
- The ``backfill_opportunity_cny_amount`` patch runs ``apply``; reruns change nothing.
- The ``sync_cny_opportunity_amounts`` patch then runs ``sync_divergent``: a CNY Opportunity holding a CNY
  amount different from its amount takes its amount. That overwrites a value someone typed, so ``dry_run``
  lists those Opportunities under ``sync`` with the old and the new value; review them before migrating.

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
# A CNY Opportunity has one amount (#87); before that rule its CNY amount could be typed apart from it,
# also beside an amount left unknown.
DIVERGENT = (
    "`currency` = 'CNY' AND COALESCE(`amount_cny`, 0) > 0 "
    "AND COALESCE(`amount_cny`, 0) <> COALESCE(`amount`, 0)"
)
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
    """What the migration would fill, what it would overwrite, and what Sales would still have to fill in; changes nothing."""

    fill = _rows(FILLABLE)
    filled = {row.name for row in fill}
    sync = _rows(DIVERGENT)
    # Missing after the migration: what is missing now and not filled, and what the sync empties because
    # the Opportunity has no amount to take (listed with the empty CNY amount it will have).
    emptied = [frappe._dict(row, amount_cny=0) for row in sync if not Decimal(str(row.amount or 0))]
    left = sorted(
        [*(row for row in _rows(MISSING) if row.name not in filled), *emptied],
        key=lambda row: (row.owner or "", row.name),
    )
    return {
        "fill": _summary(fill, _report("dry-run-fill", fill)),
        "stillMissing": _summary(left, _report("dry-run-still-missing", left)),
        # CNY amounts typed apart from the amount, which sync_divergent replaces: the one change that loses a value.
        "sync": {
            **_summary(sync, _report("dry-run-sync", sync)),
            "opportunities": [
                {
                    "name": row.name, "title": row.title or "", "owner": row.owner or "", "stage": row.stage or "",
                    "amountCny": _money(row.amount_cny), "becomes": _money(row.amount),
                }
                for row in sync
            ],
        },
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


def sync_divergent() -> dict[str, Any]:
    """Set the CNY amount of every CNY Opportunity that holds a different one to its amount, with a history row each.

    An unknown amount makes the CNY amount unknown too: the next edit would do the same without a trace.
    """

    rows = _rows(DIVERGENT)
    at = frappe.utils.now_datetime()
    for row in rows:
        # Like the backfill, not a user edit: modified stays as it was.
        frappe.db.sql(
            f"UPDATE `tab{OPPORTUNITY}` SET `amount_cny` = COALESCE(`amount`, 0) WHERE `name` = %s AND {DIVERGENT}",
            (row.name,),
        )
        frappe.get_doc({
            "doctype": "CRM Opportunity History",
            "opportunity": row.name,
            "actor": frappe.session.user,
            "at": at,
            "field": "amount_cny",
            "from_value": _money(row.amount_cny),
            "to_value": _money(row.amount),
        }).insert(ignore_permissions=True)
    return {"synced": _summary(rows, _report("synced", rows) if rows else "")}


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
