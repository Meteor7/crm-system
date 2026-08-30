"""Whitelisted Installed Tool endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import installed_tools
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_installed_tools(**query) -> dict:
    items, total, page, page_size = installed_tools.list_installed_tools(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_installed_tool(id: str) -> dict:
    return success_response(installed_tools.get_installed_tool(id))

@frappe.whitelist(methods=["POST"])
@api_endpoint
def convert_booking_to_installed_tool(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(
        installed_tools.convert_booking_to_installed_tool(id, as_payload(input), expectedModified)
    )


@frappe.whitelist(methods=["POST"])
@api_endpoint
def transition_installed_tool(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(
        installed_tools.transition_installed_tool(id, as_payload(input), expectedModified)
    )

@frappe.whitelist(methods=["POST"])
@api_endpoint
def add_installed_tool_version_record(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(
        installed_tools.add_installed_tool_version_record(id, as_payload(input), expectedModified)
    )


@frappe.whitelist(methods=["POST"])
@api_endpoint
def add_installed_tool_service_record(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(
        installed_tools.add_installed_tool_service_record(id, as_payload(input), expectedModified)
    )

@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_installed_tool(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(installed_tools.update_installed_tool(id, as_payload(input), expectedModified))
