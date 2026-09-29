"""Give every Opportunity priced in CNY its CNY amount.

The rules and the reports live in rayher_crm.setup.opportunity_cny_backfill; run its dry_run on a
restored copy first. Opportunities in other currencies stay empty and are listed by list_missing.
"""

from __future__ import annotations

import frappe

from rayher_crm.setup.opportunity_cny_backfill import apply


def execute() -> None:
    if not frappe.db.has_column("CRM Opportunity", "amount_cny"):
        return
    apply()
