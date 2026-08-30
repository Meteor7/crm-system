"""Whitelisted endpoints for external-ingest CRM read models."""

from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import read_only_views
from rayher_crm.services.common import paginate_items
from rayher_crm.services.document_access import decide_request, list_requests


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_requirements(**query) -> dict:
    items, total, page, page_size = read_only_views.list_requirements(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_contracts(**query) -> dict:
    items, total, page, page_size = read_only_views.list_contracts(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_controlled_documents(**query) -> dict:
    items, total, page, page_size = paginate_items(read_only_views.list_controlled_documents(), query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def request_controlled_document_access(versionId: str, reason: str) -> dict:
    return success_response(read_only_views.request_controlled_document_access(versionId, reason))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_controlled_document_requests(**query) -> dict:
    items, total, page, page_size = paginate_items(list_requests(), query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def decide_controlled_document_request(requestId: str, decision: str) -> dict:
    return success_response(decide_request(requestId, decision))
