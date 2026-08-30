from __future__ import annotations

import frappe
from frappe.auth import CookieManager
from frappe.tests.utils import FrappeTestCase
from werkzeug.wrappers import Response

from rayher_crm.api.v1.controlled_documents import (
    apply_delivery_headers,
    preview_document,
)
from rayher_crm.security.session_cookie import enforce_browser_session_cookie
from rayher_crm.setup.controlled_documents import ACONCA_DOCUMENT_ID
from rayher_crm.tests._controlled_document_fixtures import install_test_controlled_documents


class TestDeliveryIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        install_test_controlled_documents()

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_real_cookie_manager_flushes_sid_without_persistence(self):
        manager = CookieManager()
        manager.set_cookie("sid", "opaque-test-value", max_age=612000, httponly=True, samesite="Lax")
        frappe.local.cookie_manager = manager

        enforce_browser_session_cookie()
        response = Response()
        manager.flush_cookies(response)
        header = response.headers.get("Set-Cookie", "")

        self.assertIn("sid=", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        self.assertNotIn("Max-Age", header)
        self.assertNotIn("Expires", header)

    def test_preview_endpoint_sets_inline_pdf_and_no_store_headers(self):
        preview_document(ACONCA_DOCUMENT_ID)

        self.assertEqual(frappe.local.response.type, "download")
        self.assertEqual(frappe.local.response.content_type, "application/pdf")
        self.assertEqual(frappe.local.response.display_content_as, "inline")
        self.assertFalse(frappe.local.response.filename.endswith("-Controlled.pdf"))
        self.assertTrue(frappe.local.response.filecontent.startswith(b"%PDF-"))

        response = Response()
        apply_delivery_headers(response)
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_private_file_downloads_also_receive_no_store_headers(self):
        frappe.local.response.controlled_document_delivery = False
        frappe.local.response.private_file_delivery = True

        response = Response()
        apply_delivery_headers(response)

        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_hooks_register_cookie_and_controlled_document_guards(self):
        hooks = frappe.get_hooks("after_request")
        self.assertIn("rayher_crm.security.session_cookie.enforce_browser_session_cookie", hooks)
        self.assertIn("rayher_crm.api.v1.controlled_documents.apply_delivery_headers", hooks)
