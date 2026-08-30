from __future__ import annotations

import frappe

from rayher_crm.services.opportunities import (
    STAGE_PROBABILITIES,
    _calculate_opportunity_probability,
)


def execute():
    rows = frappe.get_all(
        "CRM Opportunity",
        fields=["name", "stage", "score", "probability"],
    )
    for row in rows:
        if row.stage not in STAGE_PROBABILITIES:
            continue
        probability = _calculate_opportunity_probability(row.stage, int(row.score or 0))
        if int(row.probability or 0) != probability:
            frappe.db.set_value(
                "CRM Opportunity", row.name, "probability", probability, update_modified=False,
            )
