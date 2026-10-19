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
from rayher_crm.services.accounts import ARCHIVED_ACCOUNT_EDIT, archive_account, create_account, unarchive_account, update_account
from rayher_crm.services import contact_files as contact_file_service
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


def pdf(
    name: str = "spec.pdf",
    content: bytes | None = None,
    claimed: str = "application/pdf",
    marker: str | None = None,
) -> dict:
    if content is None:
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        if marker:
            writer.add_metadata({"/CRMTestMarker": marker})
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
        self.other_sales = self._user("crm-contact-file-other-sales@example.invalid", "CRM Sales")
        self.manager = self._user("crm-contact-file-manager@example.invalid", "CRM Manager")
        self.unassigned_engineer = self._user("crm-contact-file-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.sales)
        self.account = create_account(self._account_input("Contact File Account"))
        self.contact = create_contact(self._contact_input(self.account["id"], "File Contact"))

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

    def _account_input(self, name: str) -> dict:
        # Every test of the class makes this Account again in the one transaction: the same name, confirmed.
        return {"name": name, "shortName": name[:8], "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": "East", "owner": frappe.session.user, "confirmDuplicate": True}

    def _contact_input(self, account_id: str, name: str) -> dict:
        return {"accountId": account_id, "name": name, "title": "Director", "department": "Engineering", "phone": "13800000001", "email": f"{name.replace(' ', '.').lower()}@example.invalid", "relationship": "Developing", "owner": frappe.session.user, "status": "Active"}

    def test_the_files_of_an_archived_accounts_contact_take_no_upload_and_no_removal(self):
        suffix = frappe.generate_hash(length=8)
        account = create_account(self._account_input("Contact File Archived " + suffix))
        contact = create_contact(self._contact_input(account["id"], "ArchivedFiles" + suffix))
        kept = upload_contact_files(contact["id"], [pdf(marker="kept-" + suffix)], scanner=Scanner())[0]
        frappe.set_user(self.manager)
        archive_account(account["id"])

        frappe.set_user(self.sales)
        for call in (
            lambda: upload_contact_files(contact["id"], [pdf(marker="late-" + suffix)], scanner=Scanner()),
            lambda: delete_contact_file(kept["id"]),
        ):
            with self.assertRaises(CrmApiException) as refused:
                call()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_ACCOUNT_EDIT))
        self.assertEqual(frappe.db.get_value("CRM Contact File", kept["id"], "deleted"), 0)
        self.assertEqual([row["id"] for row in list_contact_files(contact["id"])], [kept["id"]])
        self.assertTrue(download_contact_file(kept["id"])["content"])

        frappe.set_user(self.manager)
        unarchive_account(account["id"])
        frappe.set_user(self.sales)
        self.assertEqual(delete_contact_file(kept["id"]), {"id": kept["id"]})

    def test_a_contact_moved_to_another_account_meanwhile_takes_no_file_change(self):
        """The Contact's Account is read again as committed under that Account's row: one moved to another Account
        while its files were scanned (or before a removal took the row) is refused as changed, nothing written."""

        suffix = frappe.generate_hash(length=8)
        account = create_account(self._account_input("Contact File Moved " + suffix))
        contact = create_contact(self._contact_input(account["id"], "MovedFiles" + suffix))
        kept = upload_contact_files(contact["id"], [pdf(marker="kept-" + suffix)], scanner=Scanner())[0]
        before = frappe.db.count("CRM Contact File", {"contact": contact["id"]})
        with patch.object(contact_file_service, "_current_contact_accounts", return_value={"Another Account " + suffix}):
            for call in (
                lambda: upload_contact_files(contact["id"], [pdf(marker="moved-" + suffix)], scanner=Scanner()),
                lambda: delete_contact_file(kept["id"]),
            ):
                with self.assertRaises(CrmApiException) as changed:
                    call()
                self.assertEqual(changed.exception.code, "VERSION_CONFLICT")
        self.assertEqual(frappe.db.count("CRM Contact File", {"contact": contact["id"]}), before)
        self.assertEqual(frappe.db.get_value("CRM Contact File", kept["id"], "deleted"), 0)
        # Still under its Account: both go through.
        self.assertEqual(len(upload_contact_files(contact["id"], [pdf(marker="stays-" + suffix)], scanner=Scanner())), 1)
        self.assertEqual(delete_contact_file(kept["id"]), {"id": kept["id"]})

    def test_an_upload_takes_its_files_content_locks_before_the_accounts_row(self):
        suffix = frappe.generate_hash(length=8)
        account = create_account(self._account_input("Contact File Order " + suffix))
        contact = create_contact(self._contact_input(account["id"], "OrderFiles" + suffix))
        real_sql = frappe.db.sql
        order: list[str] = []

        def watch(query, *args, **kwargs):
            text = " ".join(str(query).split())
            if "GET_LOCK" in text:
                order.append("content")
            elif "`tabCustomer`" in text and ("FOR UPDATE" in text or "LOCK IN SHARE MODE" in text):
                order.append("account")
            return real_sql(query, *args, **kwargs)

        # A Status save takes its files' content locks before the Account's row: an upload does too, so neither waits
        # for the other's while holding its own (private_file_lifecycle's rule).
        with patch.object(frappe.db, "sql", side_effect=watch):
            upload_contact_files(contact["id"], [pdf(marker="order-" + suffix)], scanner=Scanner())
        self.assertIn("content", order)
        self.assertIn("account", order)
        self.assertLess(order.index("content"), order.index("account"))

    def test_contact_file_reads_follow_customer_user_permission_on_metadata(self):
        from frappe.permissions import add_user_permission, remove_user_permission

        suffix = frappe.generate_hash(length=8)
        other_account = create_account(self._account_input("Contact UP " + suffix))
        other_contact = create_contact(self._contact_input(other_account["id"], "ContactUP" + suffix))
        cases = []
        for contact, allowed in ((self.contact, True), (other_contact, False)):
            part = pdf(marker="contact-up-" + str(allowed) + suffix)
            item = upload_contact_files(contact["id"], [part], scanner=Scanner())[0]
            metadata = frappe.get_doc("CRM Contact File", item["id"])
            cases.append((metadata, frappe.get_doc("File", metadata.private_file), part["content"], allowed))

        frappe.set_user("Administrator")
        add_user_permission(
            "Customer", self.account["id"], self.sales,
            ignore_permissions=True, applicable_for="CRM Contact File",
        )
        frappe.clear_cache(user=self.sales)
        frappe.set_user(self.sales)
        try:
            for metadata, file_doc, expected, allowed in cases:
                with self.subTest(allowed=allowed):
                    self.assertEqual(metadata.has_permission("read"), allowed)
                    self._assert_native_file_access(file_doc, allowed)
                    self.assertEqual(bool(file_doc.is_downloadable()), allowed)
                    if allowed:
                        content = file_doc.get_content()
                        self.assertEqual(content.encode() if isinstance(content, str) else bytes(content), expected)
                        self.assertEqual(download_contact_file(metadata.name)["content"], expected)
                    else:
                        with self.assertRaises(frappe.PermissionError):
                            file_doc.get_content()
                        with self.assertRaises(CrmApiException) as denied:
                            download_contact_file(metadata.name)
                        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", self.account["id"], self.sales, ignore_permissions=True)
            frappe.clear_cache(user=self.sales)
            frappe.set_user(self.sales)

    def test_contact_file_native_detail_accepts_percent_in_user_permission_value(self):
        from frappe.permissions import add_user_permission, remove_user_permission

        suffix = frappe.generate_hash(length=8)
        account = create_account(self._account_input("Contact 100% Pure " + suffix))
        self.assertIn("%", account["id"])
        contact = create_contact(self._contact_input(account["id"], "PercentContact" + suffix))
        part = pdf(marker="percent-user-permission-" + suffix)
        item = upload_contact_files(contact["id"], [part], scanner=Scanner())[0]
        metadata = frappe.get_doc("CRM Contact File", item["id"])
        file_doc = frappe.get_doc("File", metadata.private_file)

        frappe.set_user("Administrator")
        add_user_permission(
            "Customer", account["id"], self.sales,
            ignore_permissions=True, applicable_for="CRM Contact File",
        )
        frappe.clear_cache(user=self.sales)
        frappe.set_user(self.sales)
        try:
            self._assert_native_file_access(file_doc, True)
            self.assertEqual(download_contact_file(metadata.name)["content"], part["content"])
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", account["id"], self.sales, ignore_permissions=True)
            frappe.clear_cache(user=self.sales)
            frappe.set_user(self.sales)

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
            self.assertEqual(file_doc.owner, "Administrator")
            self.assertEqual((file_doc.attached_to_doctype, file_doc.attached_to_name), ("CRM Contact File", meta.name))
            self.assertEqual(meta.uploaded_by, self.sales)
            self.assertTrue(meta.content_hash)

    def test_equal_contact_and_restricted_uploads_keep_independent_delivery_paths(self):
        from rayher_crm.services.managed_file_access import authorize_restricted_file_read
        from rayher_crm.services.private_file_lifecycle import save_private_file

        contact_first_part = pdf(marker="contact-first-boundary")
        contact_first = upload_contact_files(
            self.contact["id"], [contact_first_part], scanner=Scanner(),
        )[0]
        contact_first_meta = frappe.get_doc("CRM Contact File", contact_first["id"])
        contact_first_file = frappe.get_doc("File", contact_first_meta.private_file)
        restricted_second = save_private_file(
            "restricted-second.pdf", contact_first_part["content"],
            "CRM Quotation Version", "missing-version-contact-first",
        )
        self.assertEqual(contact_first_file.content_hash, restricted_second.content_hash)
        self.assertNotEqual(contact_first_file.file_url, restricted_second.file_url)
        self.assertEqual(
            download_contact_file(contact_first_meta.name)["content"],
            contact_first_part["content"],
        )
        restricted_second = frappe.get_doc("File", restricted_second.name)
        authorize_restricted_file_read(restricted_second)
        self.assertEqual(bytes(restricted_second.get_content()), contact_first_part["content"])

        restricted_first_part = pdf(marker="restricted-first-boundary")
        restricted_first = save_private_file(
            "restricted-first.pdf", restricted_first_part["content"],
            "CRM Quotation Version", "missing-version-restricted-first",
        )
        contact_second = upload_contact_files(
            self.contact["id"], [restricted_first_part], scanner=Scanner(),
        )[0]
        contact_second_meta = frappe.get_doc("CRM Contact File", contact_second["id"])
        contact_second_file = frappe.get_doc("File", contact_second_meta.private_file)
        self.assertEqual(restricted_first.content_hash, contact_second_file.content_hash)
        self.assertNotEqual(restricted_first.file_url, contact_second_file.file_url)
        self.assertEqual(
            download_contact_file(contact_second_meta.name)["content"],
            restricted_first_part["content"],
        )
        restricted_first = frappe.get_doc("File", restricted_first.name)
        authorize_restricted_file_read(restricted_first)
        self.assertEqual(bytes(restricted_first.get_content()), restricted_first_part["content"])

    def _assert_native_file_access(self, file_doc, allowed):
        from frappe.client import get, get_list
        from frappe.core.doctype.file.file import has_permission as native_file_permission
        file_doc.reload()
        self.assertEqual(bool(native_file_permission(file_doc, "read")), allowed)
        names = [row["name"] for row in get_list("File", filters={"name": file_doc.name}, fields=["name"])]
        self.assertEqual(names, [file_doc.name] if allowed else [])
        if allowed:
            self.assertEqual(get("File", file_doc.name)["name"], file_doc.name)
        else:
            with self.assertRaises(frappe.PermissionError):
                get("File", file_doc.name)

    def test_contact_file_native_access_tracks_transfer_and_soft_delete(self):
        from frappe.core.doctype.file.utils import find_file_by_url

        item = upload_contact_files(
            self.contact["id"],
            [pdf(marker=frappe.generate_hash(length=16))],
            scanner=Scanner(),
        )[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        file_doc = frappe.get_doc("File", meta.private_file)
        self._assert_native_file_access(file_doc, True)
        self.assertEqual(find_file_by_url(file_doc.file_url).name, file_doc.name)
        self.assertEqual(find_file_by_url(file_doc.file_url, name=file_doc.name).name, file_doc.name)
        frappe.set_user("Administrator")
        successor = self._user("crm-contact-file-successor@example.invalid", "CRM Sales")
        manager = self._user("crm-contact-file-manager@example.invalid", "CRM Manager")
        frappe.db.set_value("Customer", self.account["id"], "custom_crm_owner", successor)
        frappe.set_user(self.sales)
        self._assert_native_file_access(file_doc, False)
        self.assertIsNone(find_file_by_url(file_doc.file_url))
        self.assertIsNone(find_file_by_url(file_doc.file_url, name=file_doc.name))
        with self.assertRaises(CrmApiException):
            download_contact_file(meta.name)
        frappe.set_user(successor)
        self._assert_native_file_access(file_doc, True)
        self.assertTrue(download_contact_file(meta.name)["content"])
        delete_contact_file(meta.name)
        self._assert_native_file_access(file_doc, False)
        frappe.set_user(manager)
        self._assert_native_file_access(file_doc, False)
        self.assertEqual(frappe.db.get_value("CRM Contact File", meta.name, "uploaded_by"), self.sales)

    def test_invalid_contact_parent_and_removed_role_revoke_native_file(self):
        item = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        file_doc = frappe.get_doc("File", meta.private_file)
        self._assert_native_file_access(file_doc, True)
        frappe.db.set_value("CRM Contact File", meta.name, "contact", "missing-contact")
        self._assert_native_file_access(file_doc, False)
        frappe.db.set_value("CRM Contact File", meta.name, "contact", self.contact["id"])
        self._assert_native_file_access(file_doc, True)
        frappe.db.delete("Has Role", {
            "parent": self.sales, "parenttype": "User", "parentfield": "roles", "role": "CRM Sales",
        })
        frappe.clear_cache(user=self.sales)
        frappe.set_user(self.sales)
        self._assert_native_file_access(file_doc, False)

    def test_assigned_engineer_cannot_read_contact_file(self):
        item = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        file_doc = frappe.get_doc("File", meta.private_file)
        frappe.set_user("Administrator")
        frappe.get_doc({
            "doctype": "CRM Account Engineer Assignment",
            "customer": self.account["id"],
            "engineer": self.unassigned_engineer,
            "enabled": 1,
        }).insert(ignore_permissions=True)
        frappe.set_user(self.unassigned_engineer)
        self._assert_native_file_access(file_doc, False)

    def test_contact_file_shares_and_reference_only_alias_are_rejected(self):
        item = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        file_doc = frappe.get_doc("File", meta.private_file)
        for doctype, name in (("File", file_doc.name), ("CRM Contact File", meta.name)):
            frappe.set_user("Administrator")
            share = frappe.get_doc({"doctype": "DocShare", "share_doctype": doctype, "share_name": name,
                "user": self.unassigned_engineer, "read": 1})
            share.flags.ignore_share_permission = True
            with self.assertRaises(frappe.PermissionError):
                share.insert(ignore_permissions=True)
        frappe.set_user(self.sales)
        copied = frappe.get_doc({"doctype": "File", "file_name": "copied.pdf", "file_url": file_doc.file_url,
            "is_private": 1})
        copied.flags.ignore_permissions = True
        with self.assertRaises(frappe.PermissionError):
            copied.insert(ignore_permissions=True)
        forged = frappe.get_doc({"doctype": "File", "file_name": "forged-copy.pdf", "file_url": file_doc.file_url,
            "is_private": 1, "content": "unrelated bytes"})
        forged.flags.copy_from_existing_file = True
        with self.assertRaises(frappe.PermissionError):
            forged.insert(ignore_permissions=True)

    def test_revoked_user_cannot_copy_managed_bytes_through_local_path_aliases(self):
        from frappe.client import insert
        from rayher_crm.services.managed_file_access import canonical_local_reference
        from rayher_crm.services.private_file_lifecycle import save_private_file

        item = upload_contact_files(
            self.contact["id"], [pdf(marker=frappe.generate_hash(length=16))], scanner=Scanner(),
        )[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        managed = frappe.get_doc("File", meta.private_file)
        canonical_url = managed.file_url
        directory, stored_name = canonical_url.rsplit("/", 1)

        frappe.set_user("Administrator")
        successor = self._user("crm-reference-copy-successor@example.invalid", "CRM Sales")
        frappe.db.set_value("Customer", self.account["id"], "custom_crm_owner", successor)
        frappe.set_user(self.sales)
        before = set(frappe.get_all("File", pluck="name"))
        payloads = (
            {"file_name": stored_name, "file_url": "", "is_private": 1},
            {"file_name": "dot-copy.pdf", "file_url": f"{directory}/./{stored_name}", "is_private": 1},
            {"file_name": "dotdot-copy.pdf", "file_url": f"{directory}/../files/{stored_name}", "is_private": 1},
            {"file_name": "absolute-copy.pdf", "file_url": f"{frappe.utils.get_url()}{directory}/%2E/{stored_name}", "is_private": 1},
        )
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(frappe.PermissionError):
                insert({"doctype": "File", **payload})
        self.assertEqual(set(frappe.get_all("File", pluck="name")), before)

        ordinary = insert({
            "doctype": "File", "file_name": "ordinary-native-upload.txt",
            "content": "ordinary caller supplied bytes", "is_private": 1,
        })
        self.assertTrue(frappe.db.exists("File", ordinary["name"]))
        ordinary_content = frappe.get_doc("File", ordinary["name"]).get_content()
        ordinary_content = ordinary_content.encode() if isinstance(ordinary_content, str) else ordinary_content
        self.assertEqual(ordinary_content, b"ordinary caller supplied bytes")
        service_file = save_private_file(
            "trusted-service-upload.bin", b"\x00\xfftrusted service bytes", None, None,
        )
        self.assertEqual(service_file.get_content(), b"\x00\xfftrusted service bytes")
        self.assertEqual(
            canonical_local_reference(file_url="https://files.example.invalid/manual.pdf", is_private=1),
            None,
        )

    def test_existing_file_cannot_rebind_to_contact_url_with_fake_content(self):
        from frappe.client import set_value

        item = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        managed = frappe.get_doc("File", meta.private_file)
        ordinary = frappe.get_doc({
            "doctype": "File", "file_name": "ordinary.txt", "content": "ordinary bytes", "is_private": 1,
        }).insert(ignore_permissions=True)
        original_url = ordinary.file_url
        with self.assertRaises(frappe.PermissionError):
            set_value("File", ordinary.name, {"file_url": managed.file_url, "content": "fake replacement"})
        ordinary.reload()
        self.assertEqual(ordinary.file_url, original_url)

    def test_independent_ordinary_blob_can_be_published_but_not_spoofed(self):
        from frappe.client import set_value

        part = pdf()
        item = upload_contact_files(self.contact["id"], [part], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        managed = frappe.get_doc("File", meta.private_file)
        ordinary = frappe.get_doc({
            "doctype": "File", "file_name": "ordinary-same-content.pdf",
            "content": part["content"], "is_private": 1,
        }).insert(ignore_permissions=True)
        self.assertEqual(ordinary.content_hash, managed.content_hash)
        self.assertNotEqual(ordinary.file_url, managed.file_url)
        set_value("File", ordinary.name, {"is_private": 0})

        forged = frappe.get_doc({
            "doctype": "File", "file_name": "ordinary-other-content.txt",
            "content": "unrelated bytes", "is_private": 1,
        }).insert(ignore_permissions=True)
        forged_url, forged_hash = forged.file_url, forged.content_hash
        with self.assertRaises(frappe.PermissionError):
            set_value("File", forged.name, {"content_hash": managed.content_hash, "is_private": 0})

        managed.reload()
        ordinary.reload()
        forged.reload()
        self.assertEqual(managed.is_private, 1)
        self.assertTrue(managed.file_url.startswith("/private/files/"))
        self.assertEqual(ordinary.is_private, 0)
        self.assertTrue(ordinary.file_url.startswith("/files/"))
        self.assertNotEqual(ordinary.file_url, managed.file_url)
        self.assertEqual((forged.is_private, forged.file_url, forged.content_hash), (1, forged_url, forged_hash))

    def test_contact_file_migration_is_targeted_idempotent_and_clears_legacy_shares(self):
        from rayher_crm.patches.v1_0.protect_contact_files import execute
        from rayher_crm.services.private_file_lifecycle import save_private_file
        item = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        file_doc = frappe.get_doc("File", meta.private_file)
        unrelated = save_private_file("unrelated.txt", b"Different unrelated content", None, None)
        frappe.db.set_value("File", file_doc.name, {"owner": self.sales, "attached_to_doctype": "Contact", "attached_to_name": self.contact["id"]})
        # Deliberately create pre-migration data without today's guard.
        share = frappe.get_doc({"doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "File", "share_name": file_doc.name, "user": self.unassigned_engineer, "read": 1})
        share.db_insert()
        execute()
        execute()
        self.assertEqual(frappe.db.get_value("File", file_doc.name, "owner"), "Administrator")
        self.assertEqual(frappe.db.get_value("File", unrelated.name, "owner"), self.sales)
        self.assertFalse(frappe.db.exists("DocShare", share.name))
        self._assert_native_file_access(file_doc, True)

    def test_equal_contact_blobs_remain_readable_only_through_live_metadata(self):
        part = pdf()
        first, second = upload_contact_files(self.contact["id"], [part, {**part, "file_name": "second.pdf"}], scanner=Scanner())
        first_meta = frappe.get_doc("CRM Contact File", first["id"])
        second_meta = frappe.get_doc("CRM Contact File", second["id"])
        first_file = frappe.get_doc("File", first_meta.private_file)
        second_file = frappe.get_doc("File", second_meta.private_file)
        self.assertEqual(first_file.content_hash, second_file.content_hash)
        self.assertNotEqual(first_file.file_url, second_file.file_url)
        delete_contact_file(first_meta.name)
        self._assert_native_file_access(first_file, False)
        self._assert_native_file_access(second_file, True)
        self.assertEqual(download_contact_file(second_meta.name)["content"], part["content"])

    def test_migration_rejects_historical_crm_alias_with_an_independent_owner(self):
        from rayher_crm.patches.v1_0.protect_contact_files import execute, inventory
        item = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        file_doc = frappe.get_doc("File", meta.private_file)
        for target in ("CRM Opportunity", "CRM Demo Request"):
            # Emulate a pre-guard row. A CRM target alone never proves it was
            # created by a scanned service or has a safe technical owner.
            alias = frappe.get_doc({"doctype": "File", "name": frappe.generate_hash(length=10),
                "file_name": "legacy-alias.pdf", "file_url": file_doc.file_url,
                "content_hash": file_doc.content_hash, "is_private": 1, "owner": self.sales,
                "attached_to_doctype": target, "attached_to_name": "legacy-parent"})
            alias.db_insert()
            try:
                self.assertIn({"file": alias.name, "reason": "shared-url-outside-contact-metadata"}, inventory()["problems"])
                with self.assertRaises(RuntimeError):
                    execute()
                self.assertEqual(frappe.db.get_value("File", alias.name, "owner"), self.sales)
            finally:
                frappe.db.delete("File", {"name": alias.name})

    def test_contact_migration_and_runtime_reject_canonical_alias_variants(self):
        from frappe.client import get
        from frappe.core.api.file import zip_files
        from rayher_crm.patches.v1_0.protect_contact_files import execute, inventory

        item = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())[0]
        meta = frappe.get_doc("CRM Contact File", item["id"])
        source = frappe.get_doc("File", meta.private_file)
        directory, stored_name = source.file_url.rsplit("/", 1)
        variants = {
            "dot": (f"{directory}/./{stored_name}", "legacy-dot.pdf"),
            "dotdot": (f"{directory}/nested/../{stored_name}", "legacy-dotdot.pdf"),
            "absolute": (f"{frappe.utils.get_url()}{source.file_url}", "legacy-absolute.pdf"),
            "backslash": (source.file_url.replace("/", "\\"), "legacy-backslash.pdf"),
            "encoded-separator": (source.file_url.replace("/", "%2F"), "legacy-encoded.pdf"),
            "bare-private-name": ("", stored_name),
        }
        share = frappe.get_doc({
            "doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "File", "share_name": source.name,
            "user": self.unassigned_engineer, "read": 1,
        })
        share.db_insert()

        for label, (file_url, file_name) in variants.items():
            alias = frappe.get_doc({
                "doctype": "File", "name": frappe.generate_hash(length=10),
                "file_name": file_name, "file_url": file_url,
                "content_hash": source.content_hash, "is_private": 1, "owner": self.sales,
            })
            alias.db_insert()
            alias = frappe.get_doc("File", alias.name)
            try:
                with self.subTest(alias=label):
                    self.assertIn(
                        {"file": alias.name, "reason": "shared-url-outside-contact-metadata"},
                        inventory()["problems"],
                    )
                    self.assertFalse(alias.is_downloadable())
                    with self.assertRaises(frappe.PermissionError):
                        get("File", alias.name)
                    with self.assertRaises(frappe.PermissionError):
                        alias.get_content()
                    frappe.response.pop("filecontent", None)
                    with self.assertRaises(frappe.PermissionError):
                        zip_files(frappe.as_json([alias.name]))
                    self.assertNotIn("filecontent", frappe.response)
                    with self.assertRaises(RuntimeError):
                        execute()
                    self.assertTrue(frappe.db.exists("DocShare", share.name))
            finally:
                frappe.db.delete("File", {"name": alias.name})
        frappe.db.delete("DocShare", {"name": share.name})

    def test_manager_uploads_to_a_contact_of_an_account_owned_by_sales(self):
        frappe.set_user(self.manager)
        uploaded = upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())

        self.assertEqual(len(uploaded), 1)
        self.assertEqual(frappe.db.get_value("CRM Contact File", uploaded[0]["id"], "uploaded_by"), self.manager)

    def test_sales_who_does_not_own_the_account_cannot_upload(self):
        public_input = self._account_input("Contact File Account")
        public_input["visibility"] = "Public"
        update_account(self.account["id"], public_input, self.account["modified"])

        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException) as raised:
            upload_contact_files(self.contact["id"], [pdf()], scanner=Scanner())

        self.assertEqual(raised.exception.code, "SCOPE_DENIED")
        self.assertEqual(raised.exception.public_message, "Only the Account owner or a Manager may upload files.")
        self.assertEqual(frappe.db.count("CRM Contact File", {"contact": self.contact["id"]}), 0)

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


class TestContactAccountsAsCommitted(FrappeTestCase):
    def test_a_contacts_accounts_are_read_as_committed_by_now(self):
        contact = "zz-contact-moved-" + frappe.generate_hash(length=8)
        link = "zz-link-" + frappe.generate_hash(length=8)
        connection = None
        try:
            frappe.db.commit()
            # This request's snapshot, taken before another request commits the Contact under its new Account.
            frappe.db.sql("SELECT COUNT(*) FROM `tabDynamic Link`")
            connection = frappe.db._get_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO `tabContact` (name, first_name, creation, modified) VALUES (%s, 'Moved', NOW(6), NOW(6))",
                    (contact,),
                )
                cursor.execute(
                    "INSERT INTO `tabDynamic Link` (name, parent, parenttype, parentfield, link_doctype, link_name, creation, modified)"
                    " VALUES (%s, %s, 'Contact', 'links', 'Customer', 'Moved Account', NOW(6), NOW(6))",
                    (link, contact),
                )
            connection.commit()
            self.assertIsNone(frappe.db.get_value("Dynamic Link", {"parent": contact}, "link_name"))
            self.assertEqual(contact_file_service._current_contact_accounts(contact), {"Moved Account"})
        finally:
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM `tabDynamic Link` WHERE `name` = %s", (link,))
                    cursor.execute("DELETE FROM `tabContact` WHERE `name` = %s", (contact,))
                connection.commit()
                connection.close()
            frappe.db.rollback()
