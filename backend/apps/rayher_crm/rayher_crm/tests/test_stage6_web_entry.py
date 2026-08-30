"""Stage 6 contract tests for the packaged CRM web entry."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.www.crm import CRM_ASSET_ENTRY, get_context


class TestStage6WebEntry(FrappeTestCase):
    def test_authenticated_session_redirects_to_packaged_hash_router(self):
        original_user = frappe.session.user
        try:
            frappe.set_user("Administrator")
            with self.assertRaises(frappe.Redirect):
                get_context(SimpleNamespace())
            index_path = Path(frappe.get_app_path("rayher_crm", "public", "crm", "index.html"))
            build_token = sha256(index_path.read_bytes()).hexdigest()[:12]
            self.assertEqual(
                frappe.local.flags.redirect_location,
                f"{CRM_ASSET_ENTRY}?v={build_token}#/dashboard",
            )
            self.assertEqual(CRM_ASSET_ENTRY, "/assets/rayher_crm/crm/index.html")
        finally:
            frappe.set_user(original_user)

    def test_guest_session_redirects_to_login_without_exposing_app_state(self):
        original_user = frappe.session.user
        try:
            frappe.set_user("Guest")
            context = SimpleNamespace()
            with self.assertRaises(frappe.Redirect):
                get_context(context)
            self.assertEqual(frappe.local.flags.redirect_location, "/login?redirect-to=%2Fcrm")
            self.assertEqual(context.no_cache, 1)
            self.assertEqual(context.no_sitemap, 1)
        finally:
            frappe.set_user(original_user)
