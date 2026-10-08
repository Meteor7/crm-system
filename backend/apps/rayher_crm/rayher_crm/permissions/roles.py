"""Server-owned CRM roles and capability resolution."""

from __future__ import annotations

from collections.abc import Iterable

import frappe

CRM_MANAGER_ROLE = "CRM Manager"
CRM_SALES_ROLE = "CRM Sales"
CRM_ENGINEER_ROLE = "CRM Engineer"

CRM_ROLE_TO_PROFILE = {
    CRM_MANAGER_ROLE: "Manager",
    CRM_SALES_ROLE: "Sales",
    CRM_ENGINEER_ROLE: "Engineer",
}

ALL_CAPABILITIES = (
    "event:view",
    "event:write",
    "cockpit:view",
    "dashboard:view",
    "account:view",
    "account:write",
    "stakeholder:view",
    "stakeholder:write",
    "requirement:view",
    "deal:view",
    "deal:write",
    "deal:rollback",
    "deal:internal_validation_approve",
    "contact:view",
    "contact:write",
    "contact:merge",
    "contact:delete",
    "visit:view",
    "visit:create",
    "visit:write",
    "visit:review",
    "demo_request:view",
    "demo_request:create",
    "demo_request:engineering_review",
    "demo_request:manager_approve",
    "evaluation:view",
    "evaluation:write",
    "installed_tool:write",
    "service:view",
    "contract:view",
    "quotation:view",
    "quotation:write",
    "quotation:submit",
    "quotation:approve",
    "quotation:publish",
    "rfq:view",
    "rfq:create",
    "rfq:engineer_comment",
    "rfq:manager_approve",
)

ROLE_CAPABILITIES = {
    "Manager": ALL_CAPABILITIES,
    "Sales": (
        "event:view",
        "event:write",
        "dashboard:view",
        "account:view",
        "account:write",
        "stakeholder:view",
        "stakeholder:write",
        "contact:view",
        "contact:write",
        "requirement:view",
        "deal:view",
        "deal:write",
        "visit:view",
        "visit:create",
        "visit:write",
        "demo_request:view",
        "demo_request:create",
        "evaluation:view",
        "service:view",
        "contract:view",
        "quotation:view",
        "quotation:write",
        "quotation:submit",
        "rfq:view",
        "rfq:create",
    ),
    "Engineer": (
        "dashboard:view",
        "account:view",
        "requirement:view",
        "deal:view",
        "demo_request:view",
        "demo_request:engineering_review",
        "evaluation:view",
        "evaluation:write",
        "service:view",
        "installed_tool:write",
        "rfq:view",
        "rfq:engineer_comment",
    ),
}

ROLE_TEAMS = {
    "Manager": "Management",
    "Sales": "Sales",
    "Engineer": "Engineering",
}


def install_roles() -> None:
    """Create the three CRM roles if missing; never create users or credentials."""

    for role_name in CRM_ROLE_TO_PROFILE:
        if frappe.db.exists("Role", role_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
            }
        ).insert(ignore_permissions=True)


def _assigned_crm_roles(user_id: str) -> set[str]:
    return set(frappe.get_roles(user_id)).intersection(CRM_ROLE_TO_PROFILE)


def resolve_crm_role(user_id: str | None = None) -> str:
    """Resolve one server role to the public CRM role, failing closed on ambiguity."""

    resolved_user_id = user_id or getattr(frappe.session, "user", None)
    if not resolved_user_id or resolved_user_id == "Guest":
        raise frappe.PermissionError("CRM authentication is required.")
    if resolved_user_id == "Administrator":
        return "Manager"

    assigned_roles = _assigned_crm_roles(resolved_user_id)
    if len(assigned_roles) != 1:
        raise frappe.PermissionError("User must have exactly one CRM role.")
    return CRM_ROLE_TO_PROFILE[next(iter(assigned_roles))]


def capabilities_for_role(role: str) -> tuple[str, ...]:
    try:
        return ROLE_CAPABILITIES[role]
    except KeyError as exc:
        raise frappe.PermissionError("Unknown CRM role.") from exc


def capabilities_for_user(user_id: str | None = None) -> tuple[str, ...]:
    return capabilities_for_role(resolve_crm_role(user_id))


def assert_capability(capability: str, user_id: str | None = None) -> None:
    if capability not in capabilities_for_user(user_id):
        raise frappe.PermissionError(f"CRM capability required: {capability}")


def has_any_crm_role(roles: Iterable[str]) -> bool:
    return bool(set(roles).intersection(CRM_ROLE_TO_PROFILE))
