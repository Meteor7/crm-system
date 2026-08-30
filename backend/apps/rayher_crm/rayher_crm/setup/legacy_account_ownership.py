"""Idempotent ownership and visibility backfill for legacy CRM Customers."""

from __future__ import annotations

import frappe


LEGACY_ACCOUNT_OWNER = "person043@staff.example.invalid"


def backfill_legacy_account_ownership() -> None:
    """Keep legacy CRM Customers usable after the CRM fields are added."""

    if not frappe.db.table_exists("Customer"):
        return
    if not frappe.db.exists("User", {"name": LEGACY_ACCOUNT_OWNER, "enabled": 1}):
        frappe.logger("rayher_crm").warning(
            "Skipping legacy Customer ownership backfill until active User %s exists.",
            LEGACY_ACCOUNT_OWNER,
        )
        return

    frappe.db.sql(
        """UPDATE `tabCustomer`
           SET `custom_crm_owner` = %s
           WHERE `customer_group` = 'CRM Customers'
             AND COALESCE(`custom_crm_owner`, '') = ''""",
        (LEGACY_ACCOUNT_OWNER,),
    )
    frappe.db.sql(
        """UPDATE `tabCustomer`
           SET `custom_crm_visibility` = 'Private'
           WHERE `customer_group` = 'CRM Customers'
             AND COALESCE(`custom_crm_visibility`, '') = ''"""
    )
