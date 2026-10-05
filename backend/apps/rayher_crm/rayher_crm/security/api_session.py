"""A caller of the CRM API who is not signed in is unauthenticated, not forbidden."""

from __future__ import annotations

import re

import frappe


CRM_API_PREFIX = "rayher_crm.api.v1."
# /api/method/<name> and /api/v1/method/<name>: Frappe runs the first segment and ignores the rest.
_V1_METHOD_PATH = re.compile(r"^/api/(?:v1/)?method/(?P<method>[^/]+)(?:/.*)?$")
# /api/v2/method/<name>. With two segments the path names a DocType method, not a CRM API method.
_V2_METHOD_PATH = re.compile(r"^/api/v2/method/(?P<method>[^/]+)/?$")


def _requested_method(request) -> str:
    """The method Frappe is about to run: `cmd` when the request carries one, else the one in the path."""

    command = frappe.form_dict.get("cmd") if frappe.form_dict else None
    if command:
        return command if isinstance(command, str) else ""
    path = getattr(request, "path", "") or ""
    matched = _V1_METHOD_PATH.match(path) or _V2_METHOD_PATH.match(path)
    return matched.group("method") if matched else ""


def _allows_guests(method: str) -> bool:
    try:
        return frappe.get_attr(method) in frappe.guest_methods
    except Exception:
        return False


def require_session_for_crm_api() -> None:
    """auth_hooks entry: answer a Guest call to the CRM API with 401.

    Frappe refuses a Guest call to a method that is not whitelisted for guests with its own 403,
    before the CRM error envelope applies. The browser cannot tell that 403 from "signed in, but not
    permitted", so an expired session read as a permission error and never led back to the login page.

    Frappe runs auth_hooks after it has resolved the session cookie, API key or OAuth token, so the
    session user is final here.
    """

    request = getattr(frappe.local, "request", None)
    if request is None or request.method == "OPTIONS":
        return
    if getattr(frappe.session, "user", None) not in (None, "", "Guest"):
        return
    method = _requested_method(request)
    if not method.startswith(CRM_API_PREFIX) or _allows_guests(method):
        return
    # Nothing about the server belongs in the answer to a caller who is not signed in.
    frappe.local.flags.disable_traceback = True
    raise frappe.AuthenticationError("Authentication is required.")
