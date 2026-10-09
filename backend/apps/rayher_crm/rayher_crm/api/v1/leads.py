"""Whitelisted Lead endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import leads
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_leads(**query) -> dict:
    items, total, page, page_size = leads.list_leads(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_lead(id: str) -> dict:
    return success_response(leads.get_lead(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_lead(input: Any) -> dict:
    return success_response(leads.create_lead(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_lead(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(leads.update_lead(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def archive_lead(id: str) -> dict:
    return success_response(leads.archive_lead(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def unarchive_lead(id: str) -> dict:
    return success_response(leads.unarchive_lead(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def convert_lead(id: str, input: Any) -> dict:
    return success_response(leads.convert_lead(id, as_payload(input)))
