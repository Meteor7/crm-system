from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.has_column("CRM Booking", "live_source_opportunity"):
        return
    duplicates = frappe.db.sql(
        """SELECT `source_opportunity`, COUNT(*) AS `count`
        FROM `tabCRM Booking`
        WHERE `source_opportunity` IS NOT NULL AND `source_opportunity` != '' AND `status` != 'Cancelled'
        GROUP BY `source_opportunity` HAVING COUNT(*) > 1""",
        as_dict=True,
    )
    if duplicates:
        sources = ", ".join(row.source_opportunity for row in duplicates)
        raise RuntimeError(f"Resolve duplicate live Bookings before migration: {sources}")
    frappe.db.sql(
        """UPDATE `tabCRM Booking`
        SET `live_source_opportunity` = CASE
          WHEN `status` != 'Cancelled' AND `source_opportunity` IS NOT NULL AND `source_opportunity` != ''
          THEN `source_opportunity` ELSE NULL END"""
    )
