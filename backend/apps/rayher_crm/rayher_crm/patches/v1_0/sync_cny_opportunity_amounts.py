"""Bring every CNY Opportunity in line with the rule that its CNY amount is its amount (#87).

Between the stage-1 optional amount (#120) and that rule, a CNY Opportunity could be saved with an
amount and no CNY amount; the amount gate from Demo done reads the CNY amount, so those are filled by
the same rules and with the same history row as the first backfill. Before the rule the CNY amount
could also be typed apart from the amount; a row that holds a different one takes the amount, with a
history row from the old value to the new.
"""

from __future__ import annotations

import frappe

from rayher_crm.setup.opportunity_cny_backfill import apply, sync_divergent


def execute() -> None:
    if not frappe.db.has_column("CRM Opportunity", "amount_cny"):
        return
    apply()
    sync_divergent()
