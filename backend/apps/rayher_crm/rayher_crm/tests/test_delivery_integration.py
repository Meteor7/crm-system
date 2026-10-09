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

    def test_download_names_outside_ascii_also_get_the_utf8_filename_form(self):
        from frappe.utils.response import build_response

        cases = (
            ("attachment", "报价单 2026.pdf",
             "attachment; filename=\"___ 2026.pdf\"; filename*=UTF-8''%E6%8A%A5%E4%BB%B7%E5%8D%95%202026.pdf"),
            ("inline", "quote \"final\".pdf", 'inline; filename="quote _final_.pdf"; filename*=UTF-8\'\'quote%20%22final%22.pdf'),
            ("attachment", "quote.pdf", 'attachment; filename="quote.pdf"'),
            ("attachment", "Résumé.pdf", """attachment; filename="Resume.pdf"; filename*=UTF-8''R%C3%A9sum%C3%A9.pdf"""),
            # A plain parameter holding %20 may be percent-decoded by some clients.
            ("attachment", "report%20final.pdf",
             """attachment; filename="report_20final.pdf"; filename*=UTF-8''report%2520final.pdf"""),
            ("attachment", "a／b.pdf", """attachment; filename="a_b.pdf"; filename*=UTF-8''a%EF%BC%8Fb.pdf"""),
        )
        for disposition, file_name, expected in cases:
            with self.subTest(file_name=file_name):
                frappe.local.response.update({
                    "type": "download", "filename": file_name, "filecontent": b"%PDF-",
                    "content_type": "application/pdf", "display_content_as": disposition,
                    "private_file_delivery": True,
                })
                try:
                    # The Response Frappe itself builds for a download, then the after_request hook.
                    response = build_response("download")
                    apply_delivery_headers(response)
                finally:
                    for key in ("type", "filename", "filecontent", "content_type", "display_content_as", "private_file_delivery"):
                        frappe.local.response.pop(key, None)
                self.assertEqual(response.headers.getlist("Content-Disposition"), [expected])
                self.assertEqual(response.headers["Cache-Control"], "no-store, private")

    def test_download_without_a_delivery_flag_keeps_frappes_own_headers(self):
        from frappe.utils.response import build_response

        # frappe.local.response outlives a test; another one may have left a flag set.
        for key in ("private_file_delivery", "controlled_document_delivery"):
            frappe.local.response.pop(key, None)
        frappe.local.response.update({
            "type": "download", "filename": "报价单.pdf", "filecontent": b"%PDF-",
            "content_type": "application/pdf", "display_content_as": "attachment",
        })
        try:
            response = build_response("download")
            before = response.headers.getlist("Content-Disposition")
            apply_delivery_headers(response)
        finally:
            for key in ("type", "filename", "filecontent", "content_type", "display_content_as"):
                frappe.local.response.pop(key, None)
        self.assertEqual(response.headers.getlist("Content-Disposition"), before)
        self.assertNotIn("Cache-Control", response.headers)

    def test_controlled_document_flag_alone_also_gets_the_utf8_filename_form(self):
        from frappe.utils.response import build_response

        # Alone: a private-file flag left by another test would pass this on its own.
        frappe.local.response.pop("private_file_delivery", None)
        frappe.local.response.update({
            "type": "download", "filename": "受控文件.pdf", "filecontent": b"%PDF-",
            "content_type": "application/pdf", "display_content_as": "inline",
            "controlled_document_delivery": True,
        })
        try:
            response = build_response("download")
            apply_delivery_headers(response)
        finally:
            for key in ("type", "filename", "filecontent", "content_type", "display_content_as",
                        "controlled_document_delivery"):
                frappe.local.response.pop(key, None)
        self.assertEqual(
            response.headers.getlist("Content-Disposition"),
            ["""inline; filename="____.pdf"; filename*=UTF-8''%E5%8F%97%E6%8E%A7%E6%96%87%E4%BB%B6.pdf"""],
        )
