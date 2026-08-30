from __future__ import annotations

from typing import Any
from rayher_crm.services.opportunities import (
    OPPORTUNITY_STAGES,
    advance_opportunity_for_commercial_event,
    advance_opportunity_for_demo_event,
    get_strategy_opportunity,
    update_strategy_opportunity,
)


_AUTO_EVENT_BY_STAGE = {
    "Wafer Demo确认": "request_created",
    "预算审批": "evaluation_accepted",
}
_COMMERCIAL_EVENT_BY_STAGE = {
    "报价": "rfq_approved",
    "采购流程": "quotation_published",
}


def advance_opportunity_fixture(
    opportunity: dict[str, Any],
    target_stage: str,
    changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advance downstream test data through the same server-owned gates as production."""

    current = opportunity
    current_index = OPPORTUNITY_STAGES.index(current["stage"])
    target_index = OPPORTUNITY_STAGES.index(target_stage)
    if target_index < current_index:
        raise ValueError("Fixture helper only advances Opportunity stages.")

    applied_changes = False
    for next_stage in OPPORTUNITY_STAGES[current_index + 1:target_index + 1]:
        event = _AUTO_EVENT_BY_STAGE.get(next_stage)
        if event:
            advance_opportunity_for_demo_event(current["id"], event)
            current = get_strategy_opportunity(current["id"])
            continue
        commercial_event = _COMMERCIAL_EVENT_BY_STAGE.get(next_stage)
        if commercial_event:
            advance_opportunity_for_commercial_event(current["id"], commercial_event)
            current = get_strategy_opportunity(current["id"])
            continue
        payload: dict[str, Any] = {"stage": next_stage}
        if next_stage == target_stage and changes:
            payload.update(changes)
            applied_changes = True
        current = update_strategy_opportunity(current["id"], payload, current["modified"])

    if changes and not applied_changes:
        current = update_strategy_opportunity(current["id"], changes, current["modified"])
    return current


def advance_opportunity_fixture_by_id(
    opportunity_id: str,
    target_stage: str,
    changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bench entry point for acceptance setup; unavailable outside dedicated test sites."""

    import frappe

    from rayher_crm.tests.safety import assert_dedicated_test_site

    assert_dedicated_test_site(frappe.conf.get("crm_test_site"), frappe.local.site)
    return advance_opportunity_fixture(
        get_strategy_opportunity(opportunity_id), target_stage, changes,
    )


def cleanup_installed_tool_trace_fixture(installed_tool_id: str) -> None:
    """Remove trace records owned by one acceptance Tool on a dedicated test site."""

    import frappe

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
