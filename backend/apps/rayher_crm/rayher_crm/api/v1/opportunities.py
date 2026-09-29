"""Whitelisted Opportunity strategy endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import equipment, opportunities
from rayher_crm.services import loss_review, probability_recovery
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_equipment_types(**query) -> dict:
    return success_response(equipment.list_equipment_type_options())


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_strategy_opportunities(**query) -> dict:
    items, total, page, page_size = opportunities.list_strategy_opportunities(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_strategy_opportunity(id: str) -> dict:
    return success_response(opportunities.get_strategy_opportunity(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_strategy_opportunity(input: Any) -> dict:
    return success_response(opportunities.create_strategy_opportunity(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_strategy_opportunity(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(opportunities.update_strategy_opportunity(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def save_probability_recovery(id: str, eventId: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(probability_recovery.save_plan(id, eventId, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def record_probability_recovery_action(id: str, eventId: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(probability_recovery.record_action(id, eventId, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def rollback_opportunity_stage(id: str, input: Any, expectedModified: str | None = None) -> dict:
    payload = as_payload(input)
    return success_response(opportunities.rollback_opportunity_stage(
        id,
        payload.get("targetStage"),
        payload.get("reason"),
        expectedModified,
    ))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def confirm_budget_approved(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(opportunities.confirm_budget_approved(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def request_internal_validation(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(opportunities.request_internal_validation(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_internal_validation(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(opportunities.review_internal_validation(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def confirm_po(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(opportunities.confirm_po(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def mark_opportunity_lost(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(opportunities.mark_opportunity_lost(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_opportunity_loss(id: str, reviewId: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(loss_review.review_loss(id, reviewId, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_strategy_opportunity(id: str) -> dict:
    return success_response(opportunities.delete_strategy_opportunity(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_opportunity_stakeholder(opportunityId: str, input: Any) -> dict:
    return success_response(opportunities.create_opportunity_stakeholder(opportunityId, as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_opportunity_stakeholder(opportunityId: str, stakeholderId: str, input: Any) -> dict:
    return success_response(opportunities.update_opportunity_stakeholder(opportunityId, stakeholderId, as_payload(input)))


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_opportunity_stakeholder(opportunityId: str, stakeholderId: str) -> dict:
    return success_response(opportunities.delete_opportunity_stakeholder(opportunityId, stakeholderId))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_opportunity_action(opportunityId: str, input: Any) -> dict:
    return success_response(opportunities.create_opportunity_action(opportunityId, as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_opportunity_action(opportunityId: str, actionId: str, input: Any) -> dict:
    return success_response(opportunities.update_opportunity_action(opportunityId, actionId, as_payload(input)))


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_opportunity_action(opportunityId: str, actionId: str) -> dict:
    return success_response(opportunities.delete_opportunity_action(opportunityId, actionId))
