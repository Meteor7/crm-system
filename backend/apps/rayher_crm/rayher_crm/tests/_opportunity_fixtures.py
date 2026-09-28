from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.services.opportunities import (
    advance_opportunity_for_event,
    confirm_budget_approved,
    confirm_po,
    get_strategy_opportunity,
    update_strategy_opportunity,
)
from rayher_crm.services.opportunity_stages import (
    CUSTOMER_BUDGET_APPROVED,
    DEMO_DONE,
    INTERNAL_VALIDATION,
    MILESTONE_STAGES,
    PO_RECEIVED,
    QUOTATION_SENT,
    RFQ_VALIDATED,
    stage_index,
)


_AUTOMATIC_EVENT_BY_STAGE = {
    DEMO_DONE: ("demo_customer_review", "CRM Evaluation"),
    RFQ_VALIDATED: ("rfq_approved", "CRM RFQ"),
    QUOTATION_SENT: ("quotation_published", "CRM Quotation Version"),
}


def advance_opportunity_fixture(
    opportunity: dict[str, Any],
    target_stage: str,
    changes: dict[str, Any] | None = None,
    *,
    booking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advance downstream test data through the same server-owned gates as production.

    Internal validation is optional, so the helper goes from quotation_sent straight to
    po_received; internal validation tests call its services directly. Reaching
    po_received needs the Booking fields of the PO confirmation.
    """

    if target_stage == INTERNAL_VALIDATION:
        raise ValueError("Call the internal validation services to reach internal_validation.")
    current = opportunity
    if stage_index(target_stage) < stage_index(current["stage"]):
        raise ValueError("Fixture helper only advances Opportunity stages.")

    for next_stage in MILESTONE_STAGES[stage_index(current["stage"]) + 1:stage_index(target_stage) + 1]:
        automatic = _AUTOMATIC_EVENT_BY_STAGE.get(next_stage)
        if automatic:
            event, reference_doctype = automatic
            advance_opportunity_for_event(
                current["id"], event, reference_doctype=reference_doctype, reference_name="fixture",
            )
            current = get_strategy_opportunity(current["id"])
        elif next_stage == CUSTOMER_BUDGET_APPROVED:
            current = _with_probability_level(current)
            current = confirm_budget_approved(
                current["id"], {"approvedOn": frappe.utils.today()}, current["modified"],
            )
        elif next_stage == PO_RECEIVED:
            if booking is None:
                raise ValueError("Reaching po_received needs the Booking fields of the PO confirmation.")
            current = confirm_po(current["id"], {"booking": booking}, current["modified"])

    if changes:
        current = update_strategy_opportunity(current["id"], changes, current["modified"])
    return current


def _with_probability_level(current: dict[str, Any]) -> dict[str, Any]:
    if current["probabilityLevel"]:
        return current
    # Test data only: the owner-only rule has its own tests in test_opportunity_api.
    frappe.db.set_value(
        "CRM Opportunity", current["id"], "probability_level", "pipeline", update_modified=False,
    )
    return get_strategy_opportunity(current["id"])


def advance_opportunity_fixture_by_id(
    opportunity_id: str,
    target_stage: str,
    changes: dict[str, Any] | None = None,
    booking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bench entry point for acceptance setup; unavailable outside dedicated test sites."""

    from rayher_crm.tests.safety import assert_dedicated_test_site

    assert_dedicated_test_site(frappe.conf.get("crm_test_site"), frappe.local.site)
    return advance_opportunity_fixture(
        get_strategy_opportunity(opportunity_id), target_stage, changes, booking=booking,
    )


def cleanup_installed_tool_trace_fixture(installed_tool_id: str) -> None:
    """Remove trace records owned by one acceptance Tool on a dedicated test site."""

    from rayher_crm.tests.safety import assert_dedicated_test_site

    assert_dedicated_test_site(frappe.conf.get("crm_test_site"), frappe.local.site)
    source_names = {installed_tool_id}
    history_doctypes = (
        "CRM Installed Tool Lifecycle History",
        "CRM Installed Tool Version History",
        "CRM Installed Tool Service History",
    )
    for doctype in history_doctypes:
        source_names.update(frappe.get_all(
            doctype, filters={"installed_tool": installed_tool_id}, pluck="name",
        ))
    if source_names:
        frappe.db.delete("CRM Notification Event", {"source_name": ["in", sorted(source_names)]})
    for doctype in history_doctypes:
        frappe.db.delete(doctype, {"installed_tool": installed_tool_id})
