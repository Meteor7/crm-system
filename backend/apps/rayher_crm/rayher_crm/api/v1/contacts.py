"""Whitelisted Contact endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import contacts
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_contacts(**query) -> dict:
    items, total, page, page_size = contacts.list_contacts(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_contact(id: str) -> dict:
    return success_response(contacts.get_contact(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_contact(input: Any) -> dict:
    return success_response(contacts.create_contact(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_contact(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(contacts.update_contact(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def merge_contacts(input: Any) -> dict:
    payload = as_payload(input)
    return success_response(contacts.merge_contacts(payload.get("survivorId"), payload.get("duplicateId")))


@frappe.whitelist(methods=["POST", "DELETE"])
@api_endpoint
def delete_contact(id: str) -> dict:
    return success_response(contacts.delete_contact(id))
