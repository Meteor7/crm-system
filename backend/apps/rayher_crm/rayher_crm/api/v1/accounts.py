"""Whitelisted Account endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import accounts
from rayher_crm.services import sites
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_accounts(**query) -> dict:
    items, total, page, page_size = accounts.list_accounts(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_account_segments() -> dict:
    return success_response(accounts.list_account_segments())


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_account_cities() -> dict:
    return success_response(accounts.list_account_cities())


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_account(input: Any) -> dict:
    return success_response(accounts.create_account(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_account(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(accounts.update_account(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_account(id: str) -> dict:
    return success_response(accounts.delete_account(id))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_account_360(id: str) -> dict:
    return success_response(accounts.get_account_360(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_account_site(accountId: str, input: Any) -> dict:
    return success_response(sites.create_site(accountId, as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_account_site(accountId: str, siteId: str, input: Any) -> dict:
    return success_response(sites.update_site(accountId, siteId, as_payload(input)))


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_account_site(accountId: str, siteId: str) -> dict:
    return success_response(sites.delete_site(accountId, siteId))
