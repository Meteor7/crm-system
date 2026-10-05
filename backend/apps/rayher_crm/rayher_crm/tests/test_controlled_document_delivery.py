from __future__ import annotations

import io
import hashlib
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
        self.engineer = "crm-controlled-engineer@example.invalid"
        if not frappe.db.exists("User", self.engineer):
            frappe.get_doc({
                "doctype": "User", "email": self.engineer, "first_name": "Controlled Engineer",
                "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "CRM Engineer"}],
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

    def _source_content(self, file_name: str) -> bytes:
        current_user = frappe.session.user
        frappe.set_user("Administrator")
        try:
            content = frappe.get_doc("File", file_name).get_content()
            return content.encode() if isinstance(content, str) else bytes(content)
        finally:
            frappe.set_user(current_user)

    def test_preview_and_watermarked_download_cover_every_page_and_create_audits(self):
        source = self._source_content(self.original_preview_file)

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

    def test_equal_controlled_and_restricted_uploads_keep_independent_delivery_paths(self):
        from rayher_crm.services.managed_file_access import (
            authorize_controlled_file_read,
            authorize_restricted_file_read,
        )
        from rayher_crm.services.private_file_lifecycle import save_private_file

        controlled_first = frappe.get_doc("File", self.original_private_file)
        controlled_first_content = self._source_content(controlled_first.name)
        restricted_second = save_private_file(
            "restricted-after-controlled.bin", controlled_first_content,
            "CRM RFQ Version", "missing-version-controlled-first",
        )
        self.assertEqual(controlled_first.content_hash, restricted_second.content_hash)
        self.assertNotEqual(controlled_first.file_url, restricted_second.file_url)
        # Exercise the real controlled delivery after the equal restricted upload.
        self.assertTrue(render_controlled_document(ACONCA_DOCUMENT_ID, "download")["content"])
        restricted_second = frappe.get_doc("File", restricted_second.name)
        authorize_restricted_file_read(restricted_second)
        restricted_second_content = restricted_second.get_content()
        if isinstance(restricted_second_content, str):
            restricted_second_content = restricted_second_content.encode()
        self.assertEqual(bytes(restricted_second_content), controlled_first_content)

        pdf_buffer = io.BytesIO()
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_metadata({"/CRMTestMarker": "restricted-first-controlled-boundary"})
        writer.write(pdf_buffer)
        restricted_first_content = pdf_buffer.getvalue()
        restricted_first = save_private_file(
            "restricted-before-controlled.pdf", restricted_first_content,
            "CRM Quotation Version", "missing-version-controlled-second",
        )
        document_id = "DOC-BOUNDARY-" + frappe.generate_hash(length=8)
        digest = hashlib.sha256(restricted_first_content).hexdigest()
        temporary_document = frappe.get_doc({
            "doctype": "CRM Controlled Document", "document_id": document_id,
            "title": "Boundary isolation", "category": "Technical",
            "document_type": "Test PDF", "product": "Test", "version": "1",
            "revision": "A", "status": "Released", "confidentiality": "Internal",
            "access_mode": "Direct", "review_date": "2027-09-28",
            "document_owner": "Product Engineering", "file_name": "controlled-second.pdf",
            "mime_type": "application/pdf", "size_bytes": len(restricted_first_content),
            "content_hash": digest, "preview_file_name": "controlled-second.pdf",
            "preview_content_hash": digest,
        }).insert(ignore_permissions=True)
        controlled_second = save_private_file(
            "controlled-second.pdf", restricted_first_content,
            temporary_document.doctype, temporary_document.name,
        )
        frappe.db.set_value("CRM Controlled Document", temporary_document.name, {
            "private_file": controlled_second.name,
            "preview_file": controlled_second.name,
        }, update_modified=False)
        self.assertEqual(restricted_first.content_hash, controlled_second.content_hash)
        self.assertNotEqual(restricted_first.file_url, controlled_second.file_url)
        controlled_second = frappe.get_doc("File", controlled_second.name)
        authorize_controlled_file_read(controlled_second)
        controlled_second_content = controlled_second.get_content()
        if isinstance(controlled_second_content, str):
            controlled_second_content = controlled_second_content.encode()
        self.assertEqual(bytes(controlled_second_content), restricted_first_content)
        self.assertTrue(render_controlled_document(document_id, "download")["content"])
        restricted_first = frappe.get_doc("File", restricted_first.name)
        authorize_restricted_file_read(restricted_first)
        generic_content = restricted_first.get_content()
        if isinstance(generic_content, str):
            generic_content = generic_content.encode()
        self.assertEqual(bytes(generic_content), restricted_first_content)

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
        source = self._source_content(self.original_preview_file)
        frappe.get_doc({
            "doctype": "CRM Document Access Request",
            "controlled_document": self.document.name,
            "version_id": version_id(self.document),
            "requester": self.manager,
            "reason": "Manager clean preview",
            "status": "Approved",
            "delivery_mode": "Watermarked",
            "decided_by": "Administrator",
        }).insert(ignore_permissions=True)
        frappe.set_user(self.manager)

        result = render_controlled_document(ACONCA_DOCUMENT_ID, "preview")

        self.assertEqual(result["mime_type"], "application/pdf")
        self.assertEqual(result["content"], bytes(source))
        self.assertNotIn("Controlled", result["file_name"])
        self.assertEqual(
            frappe.db.count("CRM File Access Audit", {
                "entity_type": "Controlled Document",
                "entity_id": ACONCA_DOCUMENT_ID,
                "actor": self.manager,
                "action": "Preview",
                "outcome": "Allowed",
                "access_id": result["access_id"],
            }),
            1,
        )

    def test_manager_download_returns_verified_original_without_access_request(self):
        frappe.set_user("Administrator")
        source = self._source_content(self.original_private_file)

        result = render_controlled_document(ACONCA_DOCUMENT_ID, "download")

        self.assertEqual(result["mime_type"], PPTX_MIME)
        self.assertEqual(result["file_name"], self.document.file_name)
        self.assertEqual(result["content"], bytes(source))

    def test_direct_delivery_still_returns_original_and_audits(self):
        source = self._source_content(self.original_private_file)
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "CRM Controlled Document", self.document.name, "access_mode", "Direct", update_modified=False,
        )
        frappe.set_user(self.engineer)

        result = render_controlled_document(ACONCA_DOCUMENT_ID, "download")

        self.assertEqual(result["content"], source)
        self.assertEqual(
            frappe.db.count("CRM File Access Audit", {
                "entity_type": "Controlled Document", "entity_id": self.document.name,
                "actor": self.engineer, "action": "Download", "outcome": "Allowed",
                "access_id": result["access_id"],
            }),
            1,
        )

    def _assert_native_source_denied(self, file_name: str, *, list_fails_closed: bool = False) -> None:
        from frappe.client import get, get_list
        from frappe.core.doctype.file.utils import find_file_by_url

        file_doc = frappe.get_doc("File", file_name)
        self.assertFalse(file_doc.is_downloadable())
        if list_fails_closed:
            with self.assertRaises(frappe.PermissionError):
                get_list("File", filters={"name": file_name}, fields=["name", "file_url"])
        else:
            self.assertEqual(
                get_list("File", filters={"name": file_name}, fields=["name", "file_url"]),
                [],
            )
        with self.assertRaises(frappe.PermissionError):
            get("File", file_name)
        self.assertIsNone(find_file_by_url(file_doc.file_url))
        self.assertIsNone(find_file_by_url(file_doc.file_url, name=file_name))
        with self.assertRaises(frappe.PermissionError):
            file_doc.get_content()

    def test_native_file_paths_deny_all_crm_roles_but_allow_administrator(self):
        from frappe.client import get, get_list
        from frappe.core.doctype.file.utils import find_file_by_url

        for user in (self.sales, self.manager, self.engineer):
            frappe.set_user(user)
            for file_name in (self.original_private_file, self.original_preview_file):
                with self.subTest(user=user, file=file_name):
                    self._assert_native_source_denied(file_name)

        frappe.set_user("Administrator")
        for file_name in (self.original_private_file, self.original_preview_file):
            file_doc = frappe.get_doc("File", file_name)
            self.assertEqual(get("File", file_name)["name"], file_name)
            self.assertEqual(get_list("File", filters={"name": file_name}, fields=["name"])[0]["name"], file_name)
            self.assertEqual(find_file_by_url(file_doc.file_url).name, file_name)
            self.assertTrue(file_doc.get_content())

    def test_native_file_list_does_not_run_release_inventory(self):
        from frappe.client import get_list

        with patch(
            "rayher_crm.patches.v1_0.protect_controlled_document_files.canonical_local_file_inventory",
            side_effect=AssertionError("release inventory ran in a request"),
        ):
            names = {
                row["name"]
                for row in get_list("File", fields=["name"], limit_page_length=20)
            }
        self.assertFalse(
            {self.original_private_file, self.original_preview_file}.intersection(names),
        )

    def test_runtime_file_guards_use_targeted_file_indexes(self):
        from rayher_crm.services.managed_file_access import (
            _CONTROLLED_DIRECT_FILE_QUERY,
            _MANAGED_FILE_CANDIDATE_QUERY,
            _PROTECTED_BLOB_HASH_QUERY,
            _PROTECTED_BLOB_URL_QUERY,
            _protected_blob,
        )

        source = frappe.get_doc("File", self.original_private_file)
        candidate_plan = frappe.db.sql(
            "EXPLAIN " + _MANAGED_FILE_CANDIDATE_QUERY,
            (source.name, source.file_url, source.file_url),
            as_dict=True,
        )
        file_steps = [row for row in candidate_plan if row.table == "tabFile"]
        self.assertEqual({row.key for row in file_steps}, {"PRIMARY", "file_url_index"})
        self.assertNotIn("ALL", {row.type for row in file_steps})

        direct_plan = frappe.db.sql("EXPLAIN " + _CONTROLLED_DIRECT_FILE_QUERY, as_dict=True)
        self.assertEqual(direct_plan[0].key, "attached_to_doctype_attached_to_name_index")
        self.assertNotEqual(direct_plan[0].type, "ALL")

        protected_plans = (
            frappe.db.sql(
                "EXPLAIN " + _PROTECTED_BLOB_URL_QUERY,
                (source.file_url, source.file_url), as_dict=True,
            ),
            frappe.db.sql(
                "EXPLAIN " + _PROTECTED_BLOB_HASH_QUERY,
                (source.content_hash, source.content_hash), as_dict=True,
            ),
        )
        for plan, expected_key in zip(
            protected_plans, ("file_url_index", "content_hash_index"), strict=True,
        ):
            file_steps = [row for row in plan if row.table == "tabFile"]
            self.assertTrue(file_steps)
            self.assertEqual({row.key for row in file_steps}, {expected_key})
            self.assertNotIn("ALL", {row.type for row in file_steps})

        self.assertTrue(_protected_blob(
            url=source.file_url, content_hash=source.content_hash,
        ))
        self.assertFalse(_protected_blob(
            url=f"/private/files/{frappe.generate_hash(length=10)}-ordinary.bin",
            content_hash=frappe.generate_hash(length=40),
        ))

    def test_same_url_alias_and_new_docshares_cannot_bypass_native_boundary(self):
        source = frappe.get_doc("File", self.original_private_file)
        alias = frappe.get_doc({
            "doctype": "File", "name": frappe.generate_hash(length=10),
            "file_name": "historical-controlled-alias.pptx", "file_url": source.file_url,
            "content_hash": source.content_hash, "is_private": 1, "owner": self.sales,
        })
        alias.db_insert()

        for user in (self.sales, self.manager, self.engineer):
            frappe.set_user(user)
            with self.subTest(user=user):
                self._assert_native_source_denied(alias.name, list_fails_closed=True)

        frappe.set_user("Administrator")
        for doctype, name in (
            ("CRM Controlled Document", self.document.name),
            ("File", self.original_private_file),
            ("File", alias.name),
        ):
            share = frappe.get_doc({
                "doctype": "DocShare", "share_doctype": doctype, "share_name": name,
                "user": self.sales, "read": 1,
            })
            share.flags.ignore_share_permission = True
            with self.subTest(doctype=doctype, name=name), self.assertRaises(frappe.PermissionError):
                share.insert(ignore_permissions=True)

    def test_same_hash_with_independent_path_does_not_block_native_file_list(self):
        from frappe.client import get_list

        source = frappe.get_doc("File", self.original_private_file)
        ordinary = frappe.get_doc({
            "doctype": "File", "name": frappe.generate_hash(length=10),
            "file_name": "independent-erp-copy.pptx",
            "file_url": f"/private/files/{frappe.generate_hash(length=10)}-independent.pptx",
            "content_hash": source.content_hash, "is_private": 1, "owner": self.sales,
        })
        ordinary.db_insert()

        frappe.set_user(self.sales)
        self.assertEqual(
            get_list("File", filters={"name": ordinary.name}, fields=["name"]),
            [{"name": ordinary.name}],
        )

    def test_controlled_migration_and_runtime_reject_canonical_alias_variants(self):
        from frappe.client import get, get_list
        from rayher_crm.patches.v1_0.protect_controlled_document_files import execute, inventory

        source = frappe.get_doc("File", self.original_private_file)
        directory, stored_name = source.file_url.rsplit("/", 1)
        variants = {
            "dot": (f"{directory}/./{stored_name}", "legacy-dot.pptx"),
            "dotdot": (f"{directory}/nested/../{stored_name}", "legacy-dotdot.pptx"),
            "absolute": (f"{frappe.utils.get_url()}{source.file_url}", "legacy-absolute.pptx"),
            "backslash": (source.file_url.replace("/", "\\"), "legacy-backslash.pptx"),
            "encoded-separator": (source.file_url.replace("/", "%2F"), "legacy-encoded.pptx"),
            "bare-private-name": ("", stored_name),
        }
        share = frappe.get_doc({
            "doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "File", "share_name": source.name,
            "user": self.sales, "read": 1,
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
                        {"reason": "shared-url-outside-controlled-document", "file": alias.name},
                        inventory()["problems"],
                    )
                    self.assertFalse(alias.is_downloadable())
                    with self.assertRaises(frappe.PermissionError):
                        get("File", alias.name)
                    with self.assertRaises(frappe.PermissionError):
                        get_list("File", filters={"name": alias.name}, fields=["name"])
                    with self.assertRaises(frappe.PermissionError):
                        alias.get_content()
                    with self.assertRaises(RuntimeError):
                        execute()
                    self.assertTrue(frappe.db.exists("DocShare", share.name))
            finally:
                frappe.db.delete("File", {"name": alias.name})
        frappe.db.delete("DocShare", {"name": share.name})

    def test_controlled_file_migration_is_idempotent_and_clears_legacy_shares(self):
        from rayher_crm.patches.v1_0.protect_controlled_document_files import execute, inventory

        frappe.set_user("Administrator")
        self.assertEqual(inventory()["problems"], [])
        shares = []
        for doctype, name in (
            ("CRM Controlled Document", self.document.name),
            ("File", self.original_private_file),
            ("File", self.original_preview_file),
        ):
            share = frappe.get_doc({
                "doctype": "DocShare", "name": frappe.generate_hash(length=10),
                "share_doctype": doctype, "share_name": name, "user": self.sales, "read": 1,
            })
            share.db_insert()
            shares.append(share.name)

        execute()
        execute()

        self.assertFalse(frappe.get_all("DocShare", filters={"name": ["in", shares]}, pluck="name"))
        self.assertEqual(
            set(frappe.get_all(
                "File", filters={"name": ["in", [self.original_private_file, self.original_preview_file]]},
                pluck="owner",
            )),
            {"Administrator"},
        )

    def test_controlled_file_migration_fails_before_cleanup_on_alias_or_bad_parent(self):
        from rayher_crm.patches.v1_0.protect_controlled_document_files import execute, inventory

        frappe.set_user("Administrator")
        source = frappe.get_doc("File", self.original_private_file)
        alias = frappe.get_doc({
            "doctype": "File", "name": frappe.generate_hash(length=10),
            "file_name": "legacy-controlled-alias.pptx", "file_url": source.file_url,
            "content_hash": source.content_hash, "is_private": 1, "owner": self.sales,
        })
        alias.db_insert()
        share = frappe.get_doc({
            "doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "File", "share_name": self.original_private_file,
            "user": self.sales, "read": 1,
        })
        share.db_insert()
        self.assertIn(
            {"reason": "shared-url-outside-controlled-document", "file": alias.name},
            inventory()["problems"],
        )
        with self.assertRaises(RuntimeError):
            execute()
        self.assertTrue(frappe.db.exists("DocShare", share.name))

        frappe.db.delete("File", {"name": alias.name})
        frappe.db.set_value(
            "File", self.original_private_file, "attached_to_name", "missing-controlled-parent",
            update_modified=False,
        )
        self.assertIn(
            {
                "reason": "unexpected-controlled-file-association",
                "document": self.document.name,
                "file": self.original_private_file,
            },
            inventory()["problems"],
        )
        frappe.set_user(self.sales)
        self._assert_native_source_denied(self.original_private_file, list_fails_closed=True)
        frappe.set_user("Administrator")
        with self.assertRaises(RuntimeError):
            execute()
        self.assertTrue(frappe.db.exists("DocShare", share.name))

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
