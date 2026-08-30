"""Whitelisted legacy Stakeholder compatibility endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import stakeholders
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_stakeholders(**query) -> dict:
    items, total, page, page_size = stakeholders.list_stakeholders(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_stakeholder(input: Any) -> dict:
    return success_response(stakeholders.create_stakeholder(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_stakeholder(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(stakeholders.update_stakeholder(id, as_payload(input), expectedModified))
