"""Authenticated entry point for the packaged CRM single-page application."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

import frappe


CRM_ASSET_ENTRY = "/assets/rayher_crm/crm/index.html"


def _versioned_asset_entry() -> str:
    index_path = Path(frappe.get_app_path("rayher_crm", "public", "crm", "index.html"))
    build_token = sha256(index_path.read_bytes()).hexdigest()[:12]
    return f"{CRM_ASSET_ENTRY}?v={build_token}#/dashboard"


def get_context(context):
    context.no_cache = 1
    context.no_sitemap = 1
    if frappe.session.user == "Guest":
        target = f"/login?redirect-to={quote('/crm', safe='')}"
    else:
        target = _versioned_asset_entry()
    frappe.local.flags.redirect_location = target
    raise frappe.Redirect
