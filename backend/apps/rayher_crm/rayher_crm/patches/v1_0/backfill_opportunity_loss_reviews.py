"""Create a pending post-mortem review for every historical marked_lost event.

Old free-text reasons are kept as the reason but are never treated as reviewed. The
backfill is idempotent (one review per stage event); rehearse it on a data copy first.
"""

from __future__ import annotations

import frappe

from rayher_crm.services.loss_review import backfill_loss_reviews


def execute() -> None:
    if not frappe.db.table_exists("CRM Opportunity Loss Review"):
        return
    report = backfill_loss_reviews()
    frappe.logger("rayher_crm").info(f"backfill_opportunity_loss_reviews: {report}")
