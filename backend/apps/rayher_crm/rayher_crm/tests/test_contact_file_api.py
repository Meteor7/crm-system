from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfWriter

from rayher_crm.api.v1.contact_files import _read_uploads
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contact_files import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_REQUEST,
    MAX_REQUEST_BYTES,
    delete_contact_file,
    download_contact_file,
    list_contact_files,
    upload_contact_files,
)
from rayher_crm.services.contacts import create_contact


class Scanner:
    def __init__(self, clean: bool = True):
        self.clean = clean
        self.seen: list[bytes] = []

    def scan(self, content: bytes) -> bool:
        self.seen.append(content)
        return self.clean


def pdf(name: str = "spec.pdf", content: bytes | None = None, claimed: str = "application/pdf") -> dict:
    if content is None:
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(output)
        content = output.getvalue()
    return {"file_name": name, "mime_type": claimed, "content": content}


def docx(name: str = "request.docx") -> dict:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document><body>CRM</body></document>")
    return {"file_name": name, "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "content": output.getvalue()}


class TestContactFileApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-contact-file-sales@example.invalid", "CRM Sales")
        self.unassigned_engineer = self._user("crm-contact-file-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.sales)
        self.account = create_account(self._account_input("Contact File Account"))
        self.contact = create_contact(self._contact_input(self.account["id"], "File Contact"))

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _account_input(self, name: str) -> dict:
        return {"name": name, "shortName": name[:8], "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": "East", "owner": frappe.session.user}

    def _contact_input(self, account_id: str, name: str) -> dict:
        return {"accountId": account_id, "name": name, "title": "Director", "department": "Engineering", "phone": "13800000002", "email": f"{name.replace(' ', '.').lower()}@example.invalid", "relationship": "Developing", "owner": frappe.session.user, "status": "Active"}

    def test_limits_are_frozen_and_valid_pdf_docx_are_private(self):
        self.assertEqual((MAX_FILE_BYTES, MAX_FILES_PER_REQUEST, MAX_REQUEST_BYTES), (100 * 1024 * 1024, 10, 100 * 1024 * 1024))
        scanner = Scanner()
        pdf_part = pdf()
        uploaded = upload_contact_files(self.contact["id"], [pdf_part, docx()], scanner=scanner)

        self.assertEqual(len(uploaded), 2)
        self.assertEqual(len(scanner.seen), 2)
        self.assertEqual({item["mimeType"] for item in uploaded}, {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"})
        for item in uploaded:
            meta = frappe.get_doc("CRM Contact File", item["id"])
            file_doc = frappe.get_doc("File", meta.private_file)
            self.assertTrue(file_doc.is_private)
            self.assertEqual((file_doc.attached_to_doctype, file_doc.attached_to_name), ("CRM Contact File", meta.name))
            self.assertEqual(meta.uploaded_by, self.sales)
            self.assertTrue(meta.content_hash)

    def test_spoofed_oversized_too_many_and_malicious_files_are_rejected(self):
        with self.assertRaises(CrmApiException) as spoofed:
            upload_contact_files(self.contact["id"], [pdf(content=b"MZ-not-a-pdf")], scanner=Scanner())
        self.assertEqual(spoofed.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as oversized:
            upload_contact_files(self.contact["id"], [pdf(content=b"%PDF-" + b"x" * MAX_FILE_BYTES)], scanner=Scanner())
        self.assertEqual(oversized.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as too_many:
            upload_contact_files(self.contact["id"], [pdf(f"f-{index}.pdf") for index in range(MAX_FILES_PER_REQUEST + 1)], scanner=Scanner())
        self.assertEqual(too_many.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as infected:
            upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner(clean=False))
        self.assertEqual(infected.exception.code, "VALIDATION_ERROR")
        self.assertEqual(frappe.db.count("CRM Contact File", {"contact": self.contact["id"]}), 0)

    def test_file_names_with_response_header_control_characters_are_rejected(self):
        with self.assertRaises(CrmApiException) as raised:
            upload_contact_files(
                self.contact["id"],
                [pdf("report\r\nX-Injected-Header: yes.pdf")],
                scanner=Scanner(),
            )

        self.assertEqual(raised.exception.code, "VALIDATION_ERROR")
        self.assertEqual(frappe.db.count("CRM Contact File", {"contact": self.contact["id"]}), 0)

    def test_http_reader_stops_at_total_limit_before_materializing_all_files(self):
        streams = [io.BytesIO(b"x" * 10), io.BytesIO(b"y" * 10), io.BytesIO(b"z" * 10), io.BytesIO(b"w")]
        request_files = [
            SimpleNamespace(filename=f"file-{index}.pdf", mimetype="application/pdf", stream=stream)
            for index, stream in enumerate(streams)
        ]
        with patch("rayher_crm.services.contact_files.MAX_FILE_BYTES", 10), patch(
            "rayher_crm.services.contact_files.MAX_REQUEST_BYTES", 25,
        ):
            with self.assertRaises(CrmApiException) as raised:
                _read_uploads(request_files)
        self.assertEqual(raised.exception.code, "VALIDATION_ERROR")
        self.assertEqual(streams[2].tell(), 6)
        self.assertEqual(streams[3].tell(), 0)

    def test_batch_write_rolls_back_first_file_when_second_save_fails(self):
        from rayher_crm.services import contact_files as contact_file_service

        original_save_file = contact_file_service.save_file
        calls = 0

        def fail_second_save(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second file failed")
            return original_save_file(*args, **kwargs)

        with patch.object(contact_file_service, "save_file", side_effect=fail_second_save):
            with self.assertRaises(RuntimeError):
                upload_contact_files(
                    self.contact["id"], [pdf("first.pdf"), pdf("second.pdf")], scanner=Scanner(),
                )
        self.assertEqual(frappe.db.count("CRM Contact File", {"contact": self.contact["id"]}), 0)
    def test_scope_download_audit_and_soft_delete(self):
        pdf_part = pdf()
        uploaded = upload_contact_files(self.contact["id"], [pdf_part], scanner=Scanner())[0]
        listed = list_contact_files(self.contact["id"])
        self.assertEqual([item["id"] for item in listed], [uploaded["id"]])

        frappe.local.flags.commit = False
        result = download_contact_file(uploaded["id"])
        self.assertEqual(result["content"], pdf_part["content"])
        self.assertEqual(result["mime_type"], "application/pdf")
        self.assertTrue(frappe.local.flags.commit)
        self.assertEqual(frappe.db.count("CRM File Access Audit", {"entity_id": uploaded["id"], "outcome": "Allowed"}), 1)

        frappe.set_user(self.unassigned_engineer)
        with self.assertRaises(frappe.PermissionError):
            download_contact_file(uploaded["id"])
        self.assertEqual(frappe.db.count("CRM File Access Audit", {"entity_id": uploaded["id"], "actor": self.unassigned_engineer, "outcome": "Denied"}), 1)

        frappe.set_user(self.sales)
        self.assertEqual(delete_contact_file(uploaded["id"]), {"id": uploaded["id"]})
        self.assertEqual(list_contact_files(self.contact["id"]), [])
        self.assertTrue(frappe.db.get_value("CRM Contact File", uploaded["id"], "deleted"))
        deleted_meta = frappe.get_doc("CRM Contact File", uploaded["id"])
        self.assertFalse(frappe.has_permission("CRM Contact File", "read", doc=deleted_meta, user=self.sales))
        with self.assertRaises(CrmApiException) as deleted:
            download_contact_file(uploaded["id"])
        self.assertEqual(deleted.exception.code, "NOT_FOUND")
