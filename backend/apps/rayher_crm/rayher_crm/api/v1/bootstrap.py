"""Authenticated CRM identity and capability bootstrap."""

from __future__ import annotations

import frappe
from frappe.sessions import get_csrf_token

from rayher_crm import __version__
from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.permissions.roles import (
    CRM_ROLE_TO_PROFILE,
    ROLE_TEAMS,
    capabilities_for_role,
    resolve_crm_role,
)


def _display_name(user_id: str) -> str:
    user = frappe.get_doc("User", user_id)
    name_parts = (user.first_name, user.middle_name, user.last_name)
    return " ".join(part.strip() for part in name_parts if part and part.strip()) or user_id


def _initials(display_name: str) -> str:
    words = [word for word in display_name.split() if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return f"{words[0][0]}{words[-1][0]}".upper()


def _personnel_directory() -> list[dict]:
    personnel = []
    users = frappe.get_all(
        "User",
        filters={"enabled": 1, "user_type": "System User"},
        fields=["name", "first_name", "middle_name", "last_name", "bio"],
        order_by="first_name asc, name asc",
    )
    for user in users:
        if user.name == "Administrator":
            continue
        assigned_roles = set(frappe.get_roles(user.name)).intersection(CRM_ROLE_TO_PROFILE)
        if len(assigned_roles) != 1:
            continue
        role = CRM_ROLE_TO_PROFILE[next(iter(assigned_roles))]
        name_parts = (user.first_name, user.middle_name, user.last_name)
        display_name = " ".join(part.strip() for part in name_parts if part and part.strip()) or user.name
        personnel.append({
            "id": user.name,
            "availableForAssignment": True,
            "name": display_name,
            "initials": _initials(display_name),
            "role": role,
            "team": user.bio.strip() if user.bio and user.bio.strip() else ROLE_TEAMS[role],
            "teamOwners": [],
            "assignedAccountIds": [],
        })
    return personnel


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_bootstrap() -> dict:
    user_id = getattr(frappe.session, "user", None)
    role = resolve_crm_role(user_id)
    display_name = _display_name(user_id)

    return success_response(
        {
            "user": {
                "id": user_id,
                "name": display_name,
                "initials": _initials(display_name),
                "role": role,
                "team": ROLE_TEAMS[role],
            },
            "capabilities": list(capabilities_for_role(role)),
            "personnel": _personnel_directory(),
            "version": __version__,
            "appVersion": __version__,
            "csrfToken": get_csrf_token(),
        }
    )
