"""Enforce the physical DECIMAL(20,2) contract after Frappe schema sync."""

from __future__ import annotations

from decimal import Decimal

import frappe


MONEY_COLUMNS = (
    ("tabCRM Booking", "amount"),
    ("tabCRM Opportunity", "amount"),
    ("tabCRM Opportunity", "original_amount"),
)
MAX_MONEY = Decimal("999999999999999999.99")


def enforce_money_column_contract() -> None:
    """Fail before narrowing invalid legacy values, then enforce DECIMAL(20,2)."""

    for table, column in MONEY_COLUMNS:
        invalid = frappe.db.sql(
            f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` <> ROUND(`{column}`, 2) OR ABS(`{column}`) > %s",
            (str(MAX_MONEY),),
        )[0][0]
        if invalid:
            raise RuntimeError(f"{table}.{column} contains values outside DECIMAL(20,2).")
        column_contract = frappe.db.sql(
            """
            SELECT LOWER(COLUMN_TYPE), IS_NULLABLE, COLUMN_DEFAULT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
            """,
            (table, column),
        )
        if column_contract == [("decimal(20,2)", "NO", "0.00")]:
            continue
        frappe.db.sql_ddl(
            f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` DECIMAL(20,2) NOT NULL DEFAULT 0.00"
        )


__all__ = ["MONEY_COLUMNS", "enforce_money_column_contract"]
