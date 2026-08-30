"""Legacy Stakeholder compatibility backed only by standard Contact."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.permissions.roles import assert_capability
from rayher_crm.services.contacts import (
    _require_contact, create_contact, list_contacts, serialize_contact, update_contact,
)


def _contact_input(payload: dict[str, Any], current=None) -> dict[str, Any]:
    return {
        "accountId": payload.get("accountId"), "siteId": getattr(current, "custom_crm_site", None),
        "name": payload.get("name"), "title": payload.get("title"), "department": payload.get("department"),
        "phone": (getattr(current, "phone", "") or "") if current else "",
        "email": payload.get("email") or "", "relationship": payload.get("relationship"),
        "owner": getattr(current, "custom_crm_owner", None) or frappe.session.user,
        "status": getattr(current, "custom_crm_status", None) or "Active",
        "reportsToContactId": payload.get("reportsTo") or None,
        "role": payload.get("role"), "influence": payload.get("influence"),
    }


def list_stakeholders(query: dict[str, Any]) -> tuple[list[dict], int, int, int]:
    assert_capability("stakeholder:view")
    mapped = dict(query)
    if "status" in mapped and "contactStatus" not in mapped:
        mapped["contactStatus"] = mapped.pop("status")
    return list_contacts(mapped)


def create_stakeholder(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("stakeholder:write")
    return create_contact(_contact_input(payload))


def update_stakeholder(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("stakeholder:write")
    current = _require_contact(name)
    return update_contact(name, _contact_input(payload, current), expected_modified)
