"""Authenticated account-management endpoints for QIHENG Demo CRM."""

from __future__ import annotations

import frappe
from frappe.utils.password import check_password, update_password

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.permissions.roles import resolve_crm_role


def _validate_new_password(current_password: str, new_password: str) -> None:
    field_errors: dict[str, str] = {}

    if not isinstance(current_password, str) or not current_password:
        field_errors["currentPassword"] = "Current password is required."

    if not isinstance(new_password, str) or not new_password:
        field_errors["newPassword"] = "New password is required."
    elif len(new_password) < 8:
        field_errors["newPassword"] = "New password must contain at least 8 characters."
    elif not any(character.isascii() and character.isalpha() for character in new_password):
        field_errors["newPassword"] = "New password must contain a letter."
    elif not any(character.isascii() and character.isdigit() for character in new_password):
        field_errors["newPassword"] = "New password must contain a number."
    elif current_password == new_password:
        field_errors["newPassword"] = "New password must be different from the current password."

    if field_errors:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "Please correct the password fields.",
            field_errors=field_errors,
        )


@frappe.whitelist(methods=["POST"])
@api_endpoint
def change_password(currentPassword=None, newPassword=None) -> dict:
    """Change the authenticated CRM user's password without exposing credentials."""

    user_id = getattr(frappe.session, "user", None)
    resolve_crm_role(user_id)
    _validate_new_password(currentPassword, newPassword)

    try:
        check_password(user_id, currentPassword)
    except frappe.AuthenticationError as exc:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "The current password is incorrect.",
            field_errors={"currentPassword": "The current password is incorrect."},
        ) from exc

    update_password(user_id, newPassword, logout_all_sessions=True)
    return success_response({"updated": True})
