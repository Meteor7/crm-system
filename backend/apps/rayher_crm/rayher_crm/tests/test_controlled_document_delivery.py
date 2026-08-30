from __future__ import annotations

import io
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.controlled_documents import PPTX_MIME, render_controlled_document
from rayher_crm.services.document_access import create_request, decide_request, version_id
from rayher_crm.setup.controlled_documents import ACONCA_DOCUMENT_ID
from rayher_crm.tests._controlled_document_fixtures import install_test_controlled_documents


class TestControlledDocumentDelivery(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        install_test_controlled_documents()
        self.sales = "crm-controlled-sales@example.invalid"
        if not frappe.db.exists("User", self.sales):
            frappe.get_doc({
                "doctype": "User",
                "email": self.sales,
                "first_name": "Controlled Sales",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": "CRM Sales"}],
            }).insert(ignore_permissions=True)
        self.manager = "crm-controlled-manager@example.invalid"
        if not frappe.db.exists("User", self.manager):
            frappe.get_doc({
                "doctype": "User", "email": self.manager, "first_name": "Controlled Manager",
                "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "CRM Manager"}],
            }).insert(ignore_permissions=True)
        self.document = frappe.get_doc("CRM Controlled Document", ACONCA_DOCUMENT_ID)
        self.original_private_file = self.document.private_file
        self.original_preview_file = self.document.preview_file
        self.approval = frappe.get_doc({
            "doctype": "CRM Document Access Request",
            "controlled_document": self.document.name,
            "version_id": version_id(self.document),
            "requester": self.sales,
            "reason": "Customer technical review",
            "status": "Approved",
            "delivery_mode": "Watermarked",
            "decided_by": "Administrator",
        }).insert(ignore_permissions=True)
        frappe.set_user(self.sales)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "CRM Controlled Document",
            ACONCA_DOCUMENT_ID,
            {"private_file": self.original_private_file, "preview_file": self.original_preview_file},
            update_modified=False,
        )
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_preview_and_watermarked_download_cover_every_page_and_create_audits(self):
        source = frappe.get_doc("File", self.original_preview_file).get_content()
        if isinstance(source, str):
            source = source.encode()

        frappe.local.flags.commit = False
        preview = render_controlled_document(ACONCA_DOCUMENT_ID, "preview")
        self.assertTrue(frappe.local.flags.commit)
        frappe.local.flags.commit = False
        download = render_controlled_document(ACONCA_DOCUMENT_ID, "download")
        self.assertTrue(frappe.local.flags.commit)

        self.assertEqual(preview["mime_type"], "application/pdf")
        self.assertTrue(preview["file_name"].endswith("-Controlled.pdf"))
        self.assertNotEqual(preview["content"], bytes(source))
        self.assertNotEqual(preview["access_id"], download["access_id"])

        pages = PdfReader(io.BytesIO(preview["content"])).pages
        self.assertEqual(len(pages), 19)
        for page in pages:
            text = page.extract_text() or ""
            self.assertIn("CONTROLLED COPY", text)
            self.assertIn(ACONCA_DOCUMENT_ID, text)
            self.assertIn(preview["access_id"], text)
            self.assertIn(self.sales, text)

        for action, item in (("Preview", preview), ("Download", download)):
            self.assertEqual(
                frappe.db.count("CRM File Access Audit", {
                    "entity_type": "Controlled Document",
                    "entity_id": ACONCA_DOCUMENT_ID,
                    "actor": self.sales,
                    "action": action,
                    "outcome": "Allowed",
                    "access_id": item["access_id"],
                }),
                1,
            )

    def test_access_request_notifications_are_actionable_and_decision_is_atomic(self):
        requested = create_request(version_id(self.document), "Customer acceptance review")
        manager_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Document Access Request", "source_name": requested["id"],
                     "recipient_user": self.manager},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (manager_notice.category, manager_notice.route),
            ("Document", "/document-center?workspace=approvals"),
        )

        frappe.set_user(self.manager)
        with patch(
            "rayher_crm.services.document_access.create_notification",
            side_effect=RuntimeError("injected access notification failure"),
        ), self.assertRaisesRegex(RuntimeError, "injected access notification failure"):
            decide_request(requested["id"], "approve-watermarked")
        self.assertEqual(
            frappe.db.get_value("CRM Document Access Request", requested["id"], "status"),
            "Pending",
        )

        approved = decide_request(requested["id"], "approve-watermarked")
        self.assertEqual((approved["status"], approved["deliveryMode"]), ("Approved", "Watermarked"))
        requester_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Document Access Request", "source_name": requested["id"],
                     "recipient_user": self.sales},
            fields=["category", "route", "title"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (requester_notice.category, requester_notice.route, requester_notice.title),
            ("Document", "/document-center", "Controlled document access approved"),
        )
        frappe.set_user(self.sales)
        result = render_controlled_document(ACONCA_DOCUMENT_ID, "preview")
        self.assertEqual(result["mime_type"], "application/pdf")

    def test_original_approval_downloads_verified_pptx(self):
        self.approval.db_set("delivery_mode", "Original")
        result = render_controlled_document(ACONCA_DOCUMENT_ID, "download")
        self.assertEqual(result["mime_type"], PPTX_MIME)
        self.assertEqual(result["file_name"], self.document.file_name)
        self.assertTrue(result["content"].startswith(b"PK"))

    def test_manager_preview_returns_verified_clean_pdf_without_watermarking(self):
        frappe.set_user("Administrator")
        source = frappe.get_doc("File", self.original_preview_file).get_content()
        if isinstance(source, str):
            source = source.encode()

        result = render_controlled_document(ACONCA_DOCUMENT_ID, "preview")

        self.assertEqual(result["mime_type"], "application/pdf")
        self.assertEqual(result["content"], bytes(source))
        self.assertNotIn("Controlled", result["file_name"])
        self.assertEqual(
            frappe.db.count("CRM File Access Audit", {
                "entity_type": "Controlled Document",
                "entity_id": ACONCA_DOCUMENT_ID,
                "actor": "Administrator",
                "action": "Preview",
                "outcome": "Allowed",
                "access_id": result["access_id"],
            }),
            1,
        )

    def test_manager_download_returns_verified_original_without_access_request(self):
        frappe.set_user("Administrator")
        source = frappe.get_doc("File", self.original_private_file).get_content()
        if isinstance(source, str):
            source = source.encode()

        result = render_controlled_document(ACONCA_DOCUMENT_ID, "download")

        self.assertEqual(result["mime_type"], PPTX_MIME)
        self.assertEqual(result["file_name"], self.document.file_name)
        self.assertEqual(result["content"], bytes(source))

    def test_guest_is_denied_and_audited_without_rendering_source_bytes(self):
        frappe.set_user("Guest")
        frappe.local.flags.commit = False
        with self.assertRaises(frappe.PermissionError):
            render_controlled_document(ACONCA_DOCUMENT_ID, "preview")
        self.assertTrue(frappe.local.flags.commit)
        self.assertEqual(
            frappe.db.count("CRM File Access Audit", {
                "entity_type": "Controlled Document",
                "entity_id": ACONCA_DOCUMENT_ID,
                "actor": "Guest",
                "action": "Preview",
                "outcome": "Denied",
            }),
            1,
        )

    def test_invalid_preview_file_association_fails_closed_and_is_audited(self):
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "CRM Controlled Document",
            ACONCA_DOCUMENT_ID,
            "preview_file",
            None,
            update_modified=False,
        )
        with self.assertRaises(CrmApiException) as raised:
            render_controlled_document(ACONCA_DOCUMENT_ID, "preview")
        self.assertEqual(raised.exception.code, "NOT_FOUND")
        self.assertNotIn("private", raised.exception.public_message.lower())
