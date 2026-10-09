"""List the confirmed foreign-currency Bookings that still need their amount in CNY.

A CNY Booking's amount is already in CNY. A Booking in another currency carries ``amount_cny``,
entered when its PO is confirmed; older ones are filled in by editing the Booking, or by a
Manager once it is Completed. Nothing is backfilled automatically: there is no exchange rate
to trust.

    bench --site <site> execute rayher_crm.setup.booking_cny_amount.list_missing
"""

from __future__ import annotations

import csv
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

import frappe


MISSING = (
    "UPPER(COALESCE(`currency`, 'CNY')) != 'CNY' AND COALESCE(`amount_cny`, 0) = 0 "
    "AND `status` IN ('Confirmed', 'Completed') AND `archived` = 0"
)
REPORT_COLUMNS = ("booking", "account", "owner", "status", "source", "opportunity", "currency", "amount", "actual_po_date")


def _money(value: Any) -> str:
    return format(Decimal(str(value or 0)), ".2f")


def list_missing() -> dict[str, Any]:
    """Every confirmed or completed foreign-currency Booking without a CNY amount; writes a CSV report."""

    rows = frappe.db.sql(
        "SELECT `name`, `account`, `booking_owner` AS `owner`, `status`, `source`, `source_opportunity` AS `opportunity`, "
        "`currency`, CAST(`amount` AS CHAR) AS `amount`, `actual_po_date` "
        f"FROM `tabCRM Booking` WHERE {MISSING} ORDER BY `booking_owner`, `name`",
        as_dict=True,
    )
    directory = Path(frappe.get_site_path("private", "crm-cny-backfill")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"bookings-missing-{frappe.utils.now_datetime():%Y%m%d-%H%M%S}.csv"
    bookings = [
        {
            "name": row.name, "account": row.account or "", "owner": row.owner or "", "status": row.status or "",
            "source": row.source or "", "opportunity": row.opportunity or "", "currency": row.currency or "",
            "amount": _money(row.amount), "actualPoDate": str(row.actual_po_date or ""),
        }
        for row in rows
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        for item in bookings:
            writer.writerow([
                item["name"], item["account"], item["owner"], item["status"], item["source"], item["opportunity"],
                item["currency"], item["amount"], item["actualPoDate"],
            ])
    return {
        "count": len(bookings),
        "byCurrency": dict(sorted(Counter(item["currency"] for item in bookings).items())),
        "report": str(path),
        "bookings": bookings,
    }
