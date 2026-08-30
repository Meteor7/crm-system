from __future__ import annotations

import io
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfWriter

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.document_uploads import decide_upload_request, list_upload_requests, submit_upload
from rayher_crm.services.file_security import TIPRAY_HEADER


class CleanScanner:
    def scan(self, content: bytes) -> bool:
        return True


def pdf_part(name: str = "manual.pdf") -> dict:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(output)
    return {"file_name": name, "mime_type": "application/pdf", "content": output.getvalue()}


def metadata(**overrides) -> dict:
    values = {
        "title": "Engineer equipment manual", "category": "Technical",
        "documentType": "Equipment Manual", "accessMode": "Request",
        "confidentiality": "Confidential",
    }
    values.update(overrides)
    return values


class TestDocumentUploads(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self._user("crm-doc-upload-manager@example.invalid", "CRM Manager")
        self.sales = self._user("crm-doc-upload-sales@example.invalid", "CRM Sales")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
            user.enabled = 1
            if role not in {row.role for row in user.roles}:
                user.append("roles", {"role": role})
                user.save(ignore_permissions=True)
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def test_sales_upload_stays_pending_until_manager_publishes_it(self):
        frappe.set_user(self.sales)
        submitted = submit_upload(metadata(), pdf_part(), scanner=CleanScanner())
        self.assertEqual(submitted["status"], "Pending")
        self.assertFalse(submitted["publishedDocumentId"])
        manager_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Document Upload Request", "source_name": submitted["id"],
                     "recipient_user": self.manager},
            fields=["category", "route"],
        )[0]
        self.assertEqual((manager_notice.category, manager_notice.route), ("Document", "/document-center?workspace=approvals"))

        frappe.set_user(self.manager)
        self.assertIn(submitted["id"], [item["id"] for item in list_upload_requests()])
        approved = decide_upload_request(submitted["id"], {
            "decision": "approve", "category": "Commercial",
            "confidentiality": "Restricted", "accessMode": "Direct",
        })
        self.assertEqual(approved["status"], "Published")
        submitter_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Document Upload Request", "source_name": submitted["id"],
                     "recipient_user": self.sales},
            fields=["category", "route", "title"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (submitter_notice.category, submitter_notice.route, submitter_notice.title),
            ("Document", "/document-center", "Controlled document upload published"),
        )
        document = frappe.get_doc("CRM Controlled Document", approved["publishedDocumentId"])
        self.assertRegex(document.document_id, r"^DOC-UPL-\d{5}$")
        self.assertEqual((document.category, document.access_mode, document.mime_type), ("Commercial", "Direct", "application/pdf"))

    def test_manager_upload_publishes_immediately(self):
        frappe.set_user(self.manager)
        submitted = submit_upload(metadata(), pdf_part("contract.pdf"), scanner=CleanScanner())
        self.assertEqual(submitted["status"], "Published")
        self.assertTrue(frappe.db.exists("CRM Controlled Document", submitted["publishedDocumentId"]))

    def test_submit_failure_rolls_back_request_file_and_published_document(self):
        frappe.set_user(self.manager)
        before_requests = frappe.db.count("CRM Document Upload Request")
        before_files = set(frappe.get_all("File", pluck="name"))
        before_documents = set(frappe.get_all("CRM Controlled Document", pluck="name"))

        with patch("rayher_crm.services.document_uploads._publish", side_effect=RuntimeError("publish failed")):
            with self.assertRaises(RuntimeError):
                submit_upload(metadata(title="Atomic upload"), pdf_part("atomic.pdf"), scanner=CleanScanner())

        self.assertEqual(frappe.db.count("CRM Document Upload Request"), before_requests)
        self.assertEqual(set(frappe.get_all("File", pluck="name")), before_files)
        self.assertEqual(set(frappe.get_all("CRM Controlled Document", pluck="name")), before_documents)

        with patch("rayher_crm.services.document_uploads.save_file", side_effect=RuntimeError("storage failed")):
            with self.assertRaises(RuntimeError):
                submit_upload(metadata(title="Storage failure"), pdf_part("storage.pdf"), scanner=CleanScanner())
        self.assertEqual(frappe.db.count("CRM Document Upload Request"), before_requests)
    def test_tipray_pdf_is_stored_as_private_binary_without_preview(self):
        frappe.set_user(self.manager)
        content = TIPRAY_HEADER + bytes(range(256))
        submitted = submit_upload(metadata(), {
            "file_name": "protected-manual.pdf", "mime_type": "application/pdf", "content": content,
        }, scanner=CleanScanner())
        document = frappe.get_doc("CRM Controlled Document", submitted["publishedDocumentId"])
        stored_file = frappe.get_doc("File", document.private_file)
        self.assertEqual(document.file_name, "protected-manual.pdf")
        self.assertFalse(document.preview_file)
        self.assertTrue(stored_file.file_name.endswith(".bin"))
        self.assertEqual(stored_file.get_content(), content)

    def test_rejection_requires_reason_and_removes_the_private_file(self):
        frappe.set_user(self.sales)
        submitted = submit_upload(metadata(), pdf_part(), scanner=CleanScanner())
        private_file = frappe.db.get_value("CRM Document Upload Request", submitted["id"], "private_file")
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException):
            decide_upload_request(submitted["id"], {"decision": "reject", "reason": ""})
        rejected = decide_upload_request(submitted["id"], {"decision": "reject", "reason": "Duplicate manual"})
        self.assertEqual((rejected["status"], rejected["decisionReason"]), ("Rejected", "Duplicate manual"))
        self.assertFalse(frappe.db.exists("File", private_file))

    def test_rejection_audit_failure_preserves_pending_request_and_file_content(self):
        frappe.set_user(self.sales)
        submitted = submit_upload(metadata(title="Audit rollback"), pdf_part("audit.pdf"), scanner=CleanScanner())
        private_file = frappe.db.get_value("CRM Document Upload Request", submitted["id"], "private_file")
        original_content = frappe.get_doc("File", private_file).get_content()

        frappe.set_user(self.manager)
        with patch("rayher_crm.services.document_uploads._audit", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                decide_upload_request(submitted["id"], {"decision": "reject", "reason": "Duplicate"})

        request = frappe.get_doc("CRM Document Upload Request", submitted["id"])
        self.assertEqual(request.status, "Pending")
        self.assertEqual(request.private_file, private_file)
        self.assertEqual(frappe.get_doc("File", private_file).get_content(), original_content)
