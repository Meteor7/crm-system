"""Keep Frappe's sid in the current browser session only."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def make_sid_cookie_session_only(cookie_manager: Any) -> None:
    cookies = getattr(cookie_manager, "cookies", None)
    if not isinstance(cookies, MutableMapping):
        return

    options = cookies.get("sid")
    if not isinstance(options, MutableMapping):
        return

    options["max_age"] = None
    options["expires"] = None


def enforce_browser_session_cookie(response: Any = None, request: Any = None) -> None:
    del response, request

    import frappe

    try:
        cookie_manager = getattr(frappe.local, "cookie_manager", None)
    except (AttributeError, RuntimeError):
        return
    make_sid_cookie_session_only(cookie_manager)
