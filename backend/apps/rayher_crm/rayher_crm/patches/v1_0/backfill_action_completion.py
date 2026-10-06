"""Recover known completions; legacy visits/classifications intentionally stay unknown."""
import frappe

from rayher_crm.services.activities import audited_action_completion


def execute():
    actions = frappe.get_all(
        "CRM Opportunity Action", filters={"status": "Done", "completed_at": ["is", "not set"]},
        fields=["name", "opportunity", "status"],
    )
    by_opportunity = {}
    for action in actions:
        by_opportunity.setdefault(action.opportunity, []).append(action)
    for opportunity, rows in by_opportunity.items():
        histories = frappe.get_all(
            "CRM Opportunity History", filters={"opportunity": opportunity, "field": ["in", ["actionCreated", "actionUpdated"]]},
            fields=["name", "creation", "at", "field", "from_value", "to_value"],
        )
        for action in rows:
            completed = audited_action_completion(action, histories)
            if completed:
                frappe.db.set_value("CRM Opportunity Action", action.name, "completed_at", completed, update_modified=False)
