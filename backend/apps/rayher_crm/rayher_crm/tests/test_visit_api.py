from __future__ import annotations

import io
import zipfile
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.opportunity_stages import QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site
from rayher_crm.services.visit_meetings import update_record as update_meeting_record
from rayher_crm.services.visit_meetings import upload as upload_meeting_file
from rayher_crm.services.visits import create_visit, delete_visit, get_visit, list_visits, review_visit, update_visit

class TestVisitApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self._user("crm-visit-manager@example.invalid", "CRM Manager")
        self.sales = self._user("crm-visit-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-visit-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-visit-engineer@example.invalid", "CRM Engineer")

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

    def _records(self, owner: str, suffix: str):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Visit {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East", "owner": owner,
        })
        contact = create_contact({
            "accountId": account["id"], "name": f"{suffix} Contact", "title": "Director",
            "department": "Engineering", "phone": "13800000002",
            "email": f"visit-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": owner, "status": "Active",
        })
        return account, contact

    def _meeting_record(self, visit_id: str):
        return frappe.get_doc({
            "doctype": "CRM Visit Meeting Record", "visit": visit_id,
            "purpose": "Discuss project", "attendees": "Customer A\nSales A",
            "agenda": "Introduce solution", "summary": "Requirements confirmed",
            "conclusion": "Proceed", "followup": "Send proposal",
            "parse_status": "Parsed", "parse_message": "Test record", "manually_corrected": 1,
        }).insert(ignore_permissions=True)

    def _input(self, account: dict, contact: dict | None, owner: str, **overrides):
        payload = {
            "accountId": account["id"], "primaryContactId": contact["id"] if contact else "",
            "subject": "Fab review", "date": "2026-08-20", "type": "On-site",
            "owner": owner, "objective": "Confirm evaluation criteria",
        }
        payload.update(overrides)
        return payload

    def _assert_native_visit_file_access(self, file_id: str, allowed: bool):
        from frappe.client import get, get_list

        file_doc = frappe.get_doc("File", file_id)
        self.assertEqual(bool(file_doc.is_downloadable()), allowed)
        names = [row["name"] for row in get_list("File", filters={"name": file_id}, fields=["name"])]
        self.assertEqual(names, [file_id] if allowed else [])
        if allowed:
            self.assertEqual(get("File", file_id)["name"], file_id)
        else:
            with self.assertRaises(frappe.PermissionError):
                get("File", file_id)

    def _native_zip_entries(self, file_id: str) -> dict[str, bytes]:
        from frappe.core.api.file import zip_files

        # Frappe's test runner does not guarantee a request response object for
        # direct service calls. Give the native download endpoint a fresh one so
        # this helper cannot depend on a previous test having bound it.
        frappe.local.response = frappe._dict()
        frappe.response.pop("filecontent", None)
        zip_files(frappe.as_json([file_id]))
        payload = frappe.response["filecontent"]
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    def test_visit_file_reads_follow_customer_user_permission_on_parent(self):
        from frappe.permissions import add_user_permission, remove_user_permission
        from rayher_crm.services.visit_meetings import download
        from rayher_crm.tests.test_contact_file_api import Scanner

        suffix = frappe.generate_hash(length=8)
        cases = []
        for label, allowed in (("Allowed", True), ("Excluded", False)):
            account, contact = self._records(self.sales, "VisitUP" + label + suffix)
            visit = create_visit(self._input(account, contact, self.sales))
            expected = ("visit-parent-up-" + label + suffix).encode()
            upload_meeting_file(visit["id"], label + ".txt", "text/plain", expected, scanner=Scanner())
            file_doc = frappe.get_doc("File", {"attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"]})
            cases.append((account, visit, file_doc.name, expected, allowed))

        permitted_account = cases[0][0]["id"]
        frappe.set_user("Administrator")
        add_user_permission(
            "Customer", permitted_account, self.sales,
            ignore_permissions=True, applicable_for="CRM Visit",
        )
        frappe.clear_cache(user=self.sales)
        frappe.set_user(self.sales)
        try:
            for account, visit, file_id, expected, allowed in cases:
                with self.subTest(allowed=allowed):
                    self.assertEqual(frappe.get_doc("CRM Visit", visit["id"]).has_permission("read"), allowed)
                    self._assert_native_visit_file_access(file_id, allowed)
                    file_doc = frappe.get_doc("File", file_id)
                    if allowed:
                        content = file_doc.get_content()
                        self.assertEqual(content.encode() if isinstance(content, str) else bytes(content), expected)
                        self.assertEqual(download(file_id)["content"], expected)
                    else:
                        with self.assertRaises(frappe.PermissionError):
                            file_doc.get_content()
                        with self.assertRaises(CrmApiException) as denied:
                            download(file_id)
                        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", permitted_account, self.sales, ignore_permissions=True)
            frappe.clear_cache(user=self.sales)
            frappe.set_user(self.sales)

    def test_visit_attachment_delivery_preserves_current_action_owner_access(self):
        from rayher_crm.services.visit_meetings import download
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "FileActionOwner" + frappe.generate_hash(length=8))
        frappe.db.set_value("Customer", account["id"], "custom_crm_visibility", "Public")
        visit = create_visit(self._input(account, contact, self.sales))
        expected = b"ordinary action-owner meeting evidence"
        upload_meeting_file(visit["id"], "action-owner.txt", "text/plain", expected, scanner=Scanner())
        file_doc = frappe.get_doc("File", {"attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"]})
        visit = get_visit(visit["id"])
        update_visit(
            visit["id"], {"type": "edit", "nextAction": "Bring samples", "actionOwner": self.other_sales},
            visit["modified"],
        )
        frappe.set_user(self.other_sales)
        self.assertEqual(get_visit(visit["id"])["id"], visit["id"])
        self._assert_native_visit_file_access(file_doc.name, True)
        content = frappe.get_doc("File", file_doc.name).get_content()
        self.assertEqual(content.encode() if isinstance(content, str) else bytes(content), expected)
        self.assertEqual(download(file_doc.name)["content"], expected)

    def test_native_visit_attachment_insert_and_reparenting_are_rejected(self):
        from frappe.client import attach_file
        account, contact = self._records(self.sales, "NativeIngress")
        visit = create_visit(self._input(account, contact, self.sales, actionOwner=self.other_sales))
        for user in (self.sales, self.other_sales, self.engineer, self.manager):
            frappe.set_user(user)
            for private in (0, 1):
                forged = frappe.get_doc({"doctype": "File", "file_name": "unscanned.txt", "content": "unscanned",
                    "is_private": private, "attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"]})
                forged.flags.ignore_permissions = True
                forged.flags.crm_upload_token = True
                with self.assertRaises(frappe.PermissionError):
                    forged.insert(ignore_permissions=True)
            with self.assertRaises(frappe.PermissionError):
                attach_file("unscanned.txt", "unscanned", "CRM Visit", visit["id"], is_private=1)
        frappe.set_user(self.sales)
        ordinary = frappe.get_doc({"doctype": "File", "file_name": "ordinary.txt", "content": "ordinary", "is_private": 1}).insert(ignore_permissions=True)
        ordinary.attached_to_doctype, ordinary.attached_to_name = "CRM Visit", visit["id"]
        with self.assertRaises(frappe.PermissionError):
            ordinary.save(ignore_permissions=True)

    def test_visit_sources_require_provenance_and_legacy_rescan(self):
        from rayher_crm.services.managed_file_access import reconcile_visit_files
        from rayher_crm.services.visit_meetings import list_attachments, download
        from rayher_crm.tests.test_contact_file_api import Scanner
        account, contact = self._records(self.sales, "Provenance")
        visit = create_visit(self._input(account, contact, self.sales))
        scanner = Scanner()
        upload_meeting_file(visit["id"], "notes.txt", "text/plain", b"Meeting notes", scanner=scanner)
        file_id = list_attachments(visit["id"])[0]["id"]
        self.assertEqual(len(scanner.seen), 1)
        self.assertEqual(download(file_id)["content"], b"Meeting notes")
        self.assertEqual(frappe.db.get_value("File", file_id, "owner"), self.sales)
        self._assert_native_visit_file_access(file_id, True)
        self.assertIn(b"Meeting notes", self._native_zip_entries(file_id).values())
        frappe.set_user(self.other_sales)
        self._assert_native_visit_file_access(file_id, False)
        frappe.set_user(self.sales)
        # Legacy files are retained but cannot appear as verified source files.
        frappe.db.set_value("File", file_id, "custom_crm_service_upload", 0)
        self.assertEqual(list_attachments(visit["id"]), [])
        self._assert_native_visit_file_access(file_id, False)
        fake_token_file = frappe.get_doc("File", file_id)
        fake_token_file.flags.crm_upload_token = True
        with self.assertRaises(frappe.PermissionError):
            fake_token_file.get_content()
        with self.assertRaises(frappe.PermissionError):
            self._native_zip_entries(file_id)
        self.assertNotIn("filecontent", frappe.response)
        with self.assertRaises(CrmApiException):
            download(file_id)
        frappe.set_user("Administrator")
        self.assertIn(file_id, [row["file"] for row in reconcile_visit_files()])
        scanner = Scanner()
        reconcile_visit_files(apply=True, scanner=scanner)
        self.assertIn(b"Meeting notes", scanner.seen)
        frappe.set_user(self.sales)
        self.assertEqual(list_attachments(visit["id"])[0]["id"], file_id)
        self._assert_native_visit_file_access(file_id, True)

        frappe.db.set_value("Customer", account["id"], "custom_crm_owner", self.other_sales)
        frappe.db.set_value("CRM Visit", visit["id"], "visit_owner", self.other_sales)
        self._assert_native_visit_file_access(file_id, False)
        with self.assertRaises(frappe.PermissionError):
            self._native_zip_entries(file_id)
        self.assertNotIn("filecontent", frappe.response)
        frappe.set_user(self.other_sales)
        self._assert_native_visit_file_access(file_id, True)
        self.assertIn(b"Meeting notes", self._native_zip_entries(file_id).values())

    def test_equal_visit_and_restricted_uploads_keep_independent_delivery_paths(self):
        from rayher_crm.services.managed_file_access import authorize_restricted_file_read
        from rayher_crm.services.private_file_lifecycle import save_private_file
        from rayher_crm.services.visit_meetings import download, list_attachments
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "BoundaryDedup")
        visit = create_visit(self._input(account, contact, self.sales))

        visit_first = b"Visit first shared payload"
        upload_meeting_file(
            visit["id"], "visit-first.txt", "text/plain", visit_first, scanner=Scanner(),
        )
        visit_file_id = list_attachments(visit["id"])[0]["id"]
        visit_file = frappe.get_doc("File", visit_file_id)
        restricted_second = save_private_file(
            "restricted-second.txt", visit_first,
            "CRM RFQ Version", "missing-version-visit-first",
        )
        self.assertEqual(visit_file.content_hash, restricted_second.content_hash)
        self.assertNotEqual(visit_file.file_url, restricted_second.file_url)
        self.assertEqual(download(visit_file_id)["content"], visit_first)
        restricted_second = frappe.get_doc("File", restricted_second.name)
        authorize_restricted_file_read(restricted_second)
        restricted_second_content = restricted_second.get_content()
        if isinstance(restricted_second_content, str):
            restricted_second_content = restricted_second_content.encode()
        self.assertEqual(bytes(restricted_second_content), visit_first)

        restricted_first_content = b"Restricted first shared payload"
        restricted_first = save_private_file(
            "restricted-first.txt", restricted_first_content,
            "CRM RFQ Version", "missing-version-restricted-first",
        )
        upload_meeting_file(
            visit["id"], "visit-second.txt", "text/plain",
            restricted_first_content, scanner=Scanner(),
        )
        visit_second_id = next(
            item["id"] for item in list_attachments(visit["id"])
            if item["fileName"] == "visit-second.txt"
        )
        visit_second = frappe.get_doc("File", visit_second_id)
        self.assertEqual(restricted_first.content_hash, visit_second.content_hash)
        self.assertNotEqual(restricted_first.file_url, visit_second.file_url)
        self.assertEqual(download(visit_second_id)["content"], restricted_first_content)
        restricted_first = frappe.get_doc("File", restricted_first.name)
        authorize_restricted_file_read(restricted_first)
        restricted_file_content = restricted_first.get_content()
        if isinstance(restricted_file_content, str):
            restricted_file_content = restricted_file_content.encode()
        self.assertEqual(bytes(restricted_file_content), restricted_first_content)

        visit_second_path = visit_second.get_full_path()
        restricted_first_path = restricted_first.get_full_path()
        frappe.set_user("Administrator")
        frappe.delete_doc("File", restricted_first.name, ignore_permissions=True, force=True)
        self.assertFalse(Path(restricted_first_path).exists())
        self.assertTrue(Path(visit_second_path).exists())

    def test_equal_visit_uploads_preserve_the_user_file_name(self):
        from rayher_crm.services.visit_meetings import download, list_attachments
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "EqualVisitNames")
        visit = create_visit(self._input(account, contact, self.sales))
        content = b"Two visit uploads with one logical name"
        for _ in range(2):
            upload_meeting_file(
                visit["id"], "customer-minutes.txt", "text/plain", content,
                scanner=Scanner(),
            )
        items = [
            item for item in list_attachments(visit["id"])
            if item["fileName"] == "customer-minutes.txt"
        ]
        self.assertEqual(len(items), 2)
        files = [frappe.get_doc("File", item["id"]) for item in items]
        self.assertEqual({file.file_name for file in files}, {"customer-minutes.txt"})
        self.assertEqual(len({file.file_url for file in files}), 2)
        for item in items:
            self.assertEqual(download(item["id"])["content"], content)

    def test_visit_rescan_records_rejections_continues_and_propagates_outages(self):
        from rayher_crm.services.managed_file_access import reconcile_visit_files
        from rayher_crm.services.visit_meetings import list_attachments
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "Rescan")
        visit = create_visit(self._input(account, contact, self.sales))
        clean = Scanner()
        upload_meeting_file(visit["id"], "first.txt", "text/plain", b"First legacy notes", scanner=clean)
        upload_meeting_file(visit["id"], "second.txt", "text/plain", b"Second legacy notes", scanner=clean)
        file_ids = frappe.get_all("File", filters={"attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"]}, pluck="name")
        self.assertEqual(len(file_ids), 2)
        frappe.db.set_value("File", {"name": ["in", file_ids]}, "custom_crm_service_upload", 0,
            update_modified=False)
        self.assertEqual(list_attachments(visit["id"]), [])

        frappe.set_user("Administrator")
        rejected_scanner = Scanner(clean=False)
        results = reconcile_visit_files(apply=True, scanner=rejected_scanner)
        by_file = {row["file"]: row for row in results}
        self.assertEqual({by_file[file_id]["status"] for file_id in file_ids}, {"rejected"})
        self.assertEqual({by_file[file_id]["code"] for file_id in file_ids}, {"VALIDATION_ERROR"})
        self.assertTrue({b"First legacy notes", b"Second legacy notes"}.issubset(set(rejected_scanner.seen)))
        self.assertEqual(set(frappe.get_all("File", filters={"name": ["in", file_ids],
            "custom_crm_service_upload": 0}, pluck="name")), set(file_ids))

        class UnavailableScanner:
            def scan(self, _content):
                raise OSError("scanner unavailable")

        with self.assertRaises(CrmApiException) as outage:
            reconcile_visit_files(apply=True, scanner=UnavailableScanner())
        self.assertEqual((outage.exception.code, outage.exception.retryable), ("INTERNAL_ERROR", True))

    def test_visit_file_migration_fails_closed_and_clears_legacy_shares(self):
        from rayher_crm.patches.v1_0.protect_visit_files import execute, inventory
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "VisitMigration")
        visit = create_visit(self._input(account, contact, self.sales))
        upload_meeting_file(visit["id"], "legacy.txt", "text/plain", b"Legacy meeting notes", scanner=Scanner())
        file_id = frappe.db.get_value("File", {"attached_to_doctype": "CRM Visit",
            "attached_to_name": visit["id"]}, "name")
        original_url = frappe.db.get_value("File", file_id, "file_url")

        frappe.set_user("Administrator")
        frappe.db.set_value("File", file_id, {"is_private": 0, "file_url": "/files/legacy.txt"},
            update_modified=False)
        self.assertEqual(inventory()["problems"], [{"file": file_id, "reason": "nonprivate-or-remote-visit-file"}])
        with self.assertRaises(RuntimeError):
            execute()

        frappe.db.set_value("File", file_id, {"is_private": 1,
            "file_url": "https://example.invalid/legacy.txt"}, update_modified=False)
        self.assertEqual(inventory()["problems"], [{"file": file_id, "reason": "nonprivate-or-remote-visit-file"}])
        with self.assertRaises(RuntimeError):
            execute()

        frappe.db.set_value("File", file_id, {"is_private": 1, "file_url": original_url},
            update_modified=False)
        share = frappe.get_doc({
            "doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "File", "share_name": file_id, "user": self.other_sales, "read": 1,
        })
        share.db_insert()
        execute()
        self.assertFalse(frappe.db.exists("DocShare", share.name))

    def test_visit_file_migration_and_runtime_reject_canonical_alias(self):
        from frappe.client import get
        from rayher_crm.patches.v1_0.protect_visit_files import execute, inventory
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "VisitAlias")
        visit = create_visit(self._input(account, contact, self.sales))
        upload_meeting_file(visit["id"], "alias.txt", "text/plain", b"Visit alias bytes", scanner=Scanner())
        source = frappe.get_doc("File", {
            "attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"],
        })
        directory, stored_name = source.file_url.rsplit("/", 1)
        alias = frappe.get_doc({
            "doctype": "File", "name": frappe.generate_hash(length=10),
            "file_name": "historical-visit-alias.txt",
            "file_url": f"{directory}/./{stored_name}",
            "content_hash": source.content_hash, "is_private": 1, "owner": self.sales,
        })
        alias.db_insert()
        alias = frappe.get_doc("File", alias.name)
        share = frappe.get_doc({
            "doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "File", "share_name": source.name,
            "user": self.other_sales, "read": 1,
        })
        share.db_insert()
        try:
            self.assertIn(
                {"file": alias.name, "reason": "shared-url-outside-visit-file"},
                inventory()["problems"],
            )
            with self.assertRaises(frappe.PermissionError):
                alias.get_content()
            with self.assertRaises(frappe.PermissionError):
                get("File", alias.name)
            with self.assertRaises(frappe.PermissionError):
                self._native_zip_entries(alias.name)
            frappe.set_user("Administrator")
            with self.assertRaises(RuntimeError):
                execute()
            self.assertTrue(frappe.db.exists("DocShare", share.name))
        finally:
            frappe.db.delete("DocShare", {"name": share.name})
            frappe.db.delete("File", {"name": alias.name})

    def test_folder_flag_cannot_switch_off_visit_file_guards(self):
        from frappe.client import set_value
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "FolderFlag")
        visit = create_visit(self._input(account, contact, self.sales))
        upload_meeting_file(visit["id"], "folder-flag.txt", "text/plain", b"Folder flag minutes", scanner=Scanner())
        file_id = frappe.db.get_value("File", {"attached_to_doctype": "CRM Visit",
            "attached_to_name": visit["id"]}, "name")
        self.assertEqual(frappe.db.get_value("File", file_id, "owner"), self.sales)
        path = Path(frappe.get_doc("File", file_id).get_full_path())
        try:
            # The uploader remains the technical owner after losing the Visit.
            frappe.db.set_value("Customer", account["id"], "custom_crm_owner", self.other_sales)
            frappe.db.set_value("CRM Visit", visit["id"], "visit_owner", self.other_sales)
            self._assert_native_visit_file_access(file_id, False)
            with self.assertRaises(frappe.PermissionError):
                set_value("File", file_id, "is_folder", 1)
            self.assertEqual(frappe.db.get_value("File", file_id, "is_folder"), 0)

            frappe.set_user("Administrator")
            stored = frappe.get_doc("File", file_id)
            stored.is_folder = 1
            with self.assertRaises(frappe.PermissionError):
                stored.save()

            # A folder flag that already reached the row must not switch the
            # classification off either: detail, list, private URL and delete stay closed.
            frappe.db.set_value("File", file_id, "is_folder", 1, update_modified=False)
            frappe.set_user(self.sales)
            self._assert_native_visit_file_access(file_id, False)
            with self.assertRaises(frappe.PermissionError):
                frappe.delete_doc("File", file_id)
            self.assertTrue(path.exists())
        finally:
            # Migration inventories read the whole table in this shared transaction.
            frappe.db.delete("File", {"name": file_id})

    def test_folder_alias_of_a_visit_file_is_inventoried_and_denied(self):
        from frappe.client import get
        from frappe.core.doctype.file.utils import find_file_by_url
        from rayher_crm.patches.v1_0.protect_visit_files import inventory
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "FolderAlias")
        visit = create_visit(self._input(account, contact, self.sales))
        upload_meeting_file(visit["id"], "folder-alias.txt", "text/plain", b"Folder alias minutes", scanner=Scanner())
        source = frappe.get_doc("File", {"attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"]})
        frappe.set_user("Administrator")
        # File.validate skips folders, so an older folder row can carry any URL.
        alias = frappe.get_doc({
            "doctype": "File", "name": frappe.generate_hash(length=10),
            "file_name": "legacy-folder-alias", "file_url": source.file_url,
            "is_private": 1, "is_folder": 1, "owner": self.other_sales,
        })
        alias.db_insert()
        try:
            self.assertIn(
                {"file": alias.name, "reason": "shared-url-outside-visit-file"},
                inventory()["problems"],
            )
            frappe.set_user(self.other_sales)
            self.assertFalse(frappe.get_doc("File", alias.name).is_downloadable())
            with self.assertRaises(frappe.PermissionError):
                get("File", alias.name)
            self.assertIsNone(find_file_by_url(source.file_url))
        finally:
            frappe.db.delete("File", {"name": alias.name})

    def _run_file_method(self, file_name: str, method: str):
        """Call a File method through the whitelisted desk endpoint."""
        from frappe.handler import run_doc_method
        from frappe.utils import set_request

        had_request = hasattr(frappe.local, "request")
        previous_request = getattr(frappe.local, "request", None)
        set_request(method="POST", path="/api/method/run_doc_method")
        frappe.local.response = frappe._dict(docs=[])
        try:
            return run_doc_method(method=method, dt="File", dn=file_name)
        finally:
            if had_request:
                frappe.local.request = previous_request
            else:
                del frappe.local.request

    def test_optimizing_a_visit_image_never_writes_under_its_logical_name(self):
        from PIL import Image
        from rayher_crm.tests.test_contact_file_api import Scanner

        def uncompressed_png(color) -> bytes:
            output = io.BytesIO()
            Image.new("RGB", (400, 400), color).save(output, format="PNG", compress_level=0)
            return output.getvalue()

        logical_name = f"visit-photo-{frappe.generate_hash(length=10)}.png"
        visit_image = uncompressed_png((20, 120, 200))
        account, contact = self._records(self.sales, "Optimize")
        visit = create_visit(self._input(account, contact, self.sales))
        upload_meeting_file(visit["id"], logical_name, "image/png", visit_image, scanner=Scanner())
        visit_file = frappe.get_doc("File", {"attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"]})
        self.assertEqual(visit_file.file_name, logical_name)
        visit_path = Path(visit_file.get_full_path())

        # An unrelated private file stored under the Visit file's logical name.
        frappe.set_user("Administrator")
        unrelated_content = b"Unrelated private bytes " + frappe.generate_hash(length=10).encode()
        unrelated = frappe.get_doc({
            "doctype": "File", "file_name": logical_name, "content": unrelated_content, "is_private": 1,
        }).insert(ignore_permissions=True)
        self.assertEqual(unrelated.file_url, f"/private/files/{logical_name}")
        unrelated_path = Path(unrelated.get_full_path())

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            self._run_file_method(visit_file.name, "optimize_file")
        self.assertEqual(unrelated_path.read_bytes(), unrelated_content)
        self.assertEqual(visit_path.read_bytes(), visit_image)

        # Ordinary images keep Frappe's whitelisted optimisation.
        ordinary_image = uncompressed_png((200, 40, 40))
        ordinary = frappe.get_doc({
            "doctype": "File", "file_name": f"ordinary-photo-{frappe.generate_hash(length=10)}.png",
            "content": ordinary_image, "is_private": 1,
        }).insert()
        self._run_file_method(ordinary.name, "optimize_file")
        ordinary.reload()
        self.assertLess(len(Path(ordinary.get_full_path()).read_bytes()), len(ordinary_image))

    def test_visit_file_migration_reports_orphans_before_touching_shares(self):
        from rayher_crm.patches.v1_0.protect_visit_files import execute, inventory
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "VisitOrphan")
        visit = create_visit(self._input(account, contact, self.sales))
        upload_meeting_file(visit["id"], "orphan.txt", "text/plain", b"Orphan meeting notes", scanner=Scanner())
        file_id = frappe.db.get_value("File", {"attached_to_doctype": "CRM Visit",
            "attached_to_name": visit["id"]}, "name")
        frappe.set_user("Administrator")
        share = frappe.get_doc({
            "doctype": "DocShare", "name": frappe.generate_hash(length=10),
            "share_doctype": "File", "share_name": file_id, "user": self.other_sales, "read": 1,
        })
        share.db_insert()
        try:
            # A raw delete leaves the private, canonical File without its Visit.
            frappe.db.delete("CRM Visit", {"name": visit["id"]})
            self.assertIn({"file": file_id, "reason": "missing-visit-parent"}, inventory()["problems"])
            with self.assertRaises(RuntimeError):
                execute()
            self.assertTrue(frappe.db.exists("DocShare", share.name))
        finally:
            frappe.db.delete("DocShare", {"name": share.name})
            frappe.db.delete("File", {"name": file_id})

    def test_visit_rescan_reports_missing_blobs_and_uploaders(self):
        from rayher_crm.services.managed_file_access import reconcile_visit_files
        from rayher_crm.tests.test_contact_file_api import Scanner

        account, contact = self._records(self.sales, "RescanMissing")
        visit = create_visit(self._input(account, contact, self.sales))
        upload_meeting_file(visit["id"], "kept.txt", "text/plain", b"Kept legacy notes", scanner=Scanner())
        upload_meeting_file(visit["id"], "lost.txt", "text/plain", b"Lost legacy notes", scanner=Scanner())
        files = {row.file_name: row.name for row in frappe.get_all("File", filters={
            "attached_to_doctype": "CRM Visit", "attached_to_name": visit["id"],
        }, fields=["name", "file_name"])}
        self.assertEqual(set(files), {"kept.txt", "lost.txt"})
        frappe.db.set_value("File", {"name": ["in", list(files.values())]}, "custom_crm_service_upload", 0,
            update_modified=False)
        frappe.set_user("Administrator")
        Path(frappe.get_doc("File", files["lost.txt"]).get_full_path()).unlink()
        try:
            inventory = {row["file"]: row for row in reconcile_visit_files()}
            for file_id in files.values():
                self.assertEqual(
                    (inventory[file_id]["uploader"], inventory[file_id]["visit_owner"]),
                    (self.sales, self.sales),
                )
            results = {row["file"]: row for row in reconcile_visit_files(apply=True, scanner=Scanner())}
            self.assertEqual(results[files["lost.txt"]]["status"], "missing-blob")
            self.assertEqual(results[files["kept.txt"]]["status"], "verified")
            self.assertEqual(frappe.db.get_value("File", files["lost.txt"], "custom_crm_service_upload"), 0)
        finally:
            # Other rescans in this shared transaction read every unverified Visit File.
            frappe.db.delete("File", {"name": ["in", list(files.values())]})

    def test_create_list_filters_scope_and_cas(self):
        account, contact = self._records(self.sales, "Core")
        foreign_account, foreign_contact = self._records(self.other_sales, "Foreign")
        foreign_visit = create_visit(self._input(foreign_account, foreign_contact, self.other_sales))
        frappe.set_user(self.sales)

        with self.assertRaises(CrmApiException) as forged:
            create_visit(self._input(account, contact, self.other_sales))
        self.assertEqual(forged.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as mismatch:
            create_visit(self._input(account, foreign_contact, self.sales))
        self.assertEqual(mismatch.exception.code, "CONFLICT")

        site = create_site(account["id"], {
            "name": "Core Fab", "city": "Shanghai", "type": "Fab",
            "process": "CIS", "status": "量产",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account["id"], "siteId": site["id"], "title": "CIS defect inspection",
            "owner": self.sales, "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": "4860000",
            "probability": 20, "intentScore": 35, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East", "currency": "CNY",
            "originalAmount": "4860000", "amountCny": "4860000", "paymentMilestones": [], "strengths": [],
            "redFlags": [], "informationNeeded": [], "qualificationConfirmed": True,
        })
        created = create_visit(self._input(account, contact, self.sales, opportunityId=opportunity["id"]))
        self.assertRegex(created["id"], r"^CRM-VIS-\d{5}$")
        self.assertEqual(created["accountName"], account["name"])
        self.assertEqual(created["owner"], self.sales)
        self.assertEqual(created["status"], "Planned")
        self.assertEqual(created["opportunityId"], opportunity["id"])
        self.assertEqual(frappe.db.get_value("CRM Visit", created["id"], "opportunity"), opportunity["id"])
        self.assertRegex(created["modified"], r"Z$")
        self.assertEqual(frappe.db.get_value("CRM Visit", created["id"], "created_by_user"), self.sales)
        self.assertEqual(get_visit(created["id"])["id"], created["id"])
        with self.assertRaises(CrmApiException) as outside_scope:
            get_visit(foreign_visit["id"])
        self.assertEqual(outside_scope.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as missing:
            get_visit("CRM-VIS-NOT-FOUND")
        self.assertEqual(missing.exception.code, "NOT_FOUND")

        items, total, page, page_size = list_visits({
            "search": "Fab", "accountId": account["id"], "contactId": contact["id"],
            "status": "Planned", "owner": self.sales, "dateFrom": "2026-08-01",
            "dateTo": "2026-08-31", "page": "1", "pageSize": "10",
        })
        self.assertEqual([item["id"] for item in items], [created["id"]])
        self.assertEqual((total, page, page_size), (1, 1, 10))

        with self.assertRaises(CrmApiException) as stale:
            update_visit(created["id"], {"type": "edit", "subject": "Stale"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        updated = update_visit(created["id"], {"type": "edit", "subject": "Updated fab review"}, created["modified"])
        self.assertEqual(updated["subject"], "Updated fab review")

        frappe.set_user(self.other_sales)
        self.assertNotIn(created["id"], {item["id"] for item in list_visits({})[0]})
        self.assertTrue(foreign_account["id"])

    def test_state_machine_requires_complete_meeting_record_and_locks_after_review(self):
        account, contact = self._records(self.sales, "Flow")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))

        with self.assertRaises(CrmApiException) as no_outcome:
            update_visit(visit["id"], {"type": "advance", "status": "Visited"}, visit["modified"])
        self.assertEqual(no_outcome.exception.code, "INVALID_TRANSITION")
        visited = update_visit(visit["id"], {
            "type": "advance", "status": "Visited", "outcome": "Criteria confirmed",
        }, visit["modified"])
        with self.assertRaises(CrmApiException) as no_minutes:
            update_visit(visit["id"], {"type": "advance", "status": "Minutes Submitted"}, visited["modified"])
        self.assertEqual(no_minutes.exception.code, "INVALID_TRANSITION")
        self._meeting_record(visit["id"])
        minutes = update_visit(visit["id"], {"type": "advance", "status": "Minutes Submitted"}, visited["modified"])
        assigned = update_visit(visit["id"], {
            "type": "edit", "nextAction": "Prepare plan", "actionOwner": self.sales, "due": "2026-08-25",
        }, minutes["modified"])
        notification = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Visit", "source_name": visit["id"], "title": "Visit action assigned"},
            fields=["recipient_user", "route"],
        )
        self.assertEqual(len(notification), 1)
        self.assertEqual(notification[0].recipient_user, self.sales)
        self.assertEqual(notification[0].route, f"/visits?focus={visit['id']}")

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            update_visit(visit["id"], {"type": "advance", "status": "Manager Reviewed"}, assigned["modified"])
        frappe.set_user(self.manager)
        reviewed = update_visit(visit["id"], {"type": "advance", "status": "Manager Reviewed"}, assigned["modified"])
        with self.assertRaises(CrmApiException) as locked:
            update_visit(visit["id"], {"type": "edit", "subject": "Too late"}, reviewed["modified"])
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")

    def test_review_endpoint_and_owner_reassignment_notify_the_owner(self):
        account, contact = self._records(self.sales, "Review")
        frappe.db.set_value("Customer", account["id"], "custom_crm_visibility", "Public")
        visit = create_visit(self._input(account, contact, self.sales))
        frappe.set_user(self.manager)
        # Reassigning the owner through the edit command tells the new owner.
        reassigned = update_visit(visit["id"], {"type": "edit", "owner": self.other_sales}, visit["modified"])
        self.assertEqual(reassigned["owner"], self.other_sales)
        assigned_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Visit", "source_name": visit["id"], "title": "Visit assigned"},
            fields=["recipient_user"],
        )
        self.assertEqual([row.recipient_user for row in assigned_notice], [self.other_sales])
        # An edit that keeps the owner stays silent.
        renamed = update_visit(visit["id"], {"type": "edit", "subject": "Fab review (moved)", "date": "2026-08-27"}, reassigned["modified"])
        self.assertEqual(frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Visit", "source_name": visit["id"]}), 1)

        visited = update_visit(visit["id"], {"type": "advance", "status": "Visited", "outcome": "Criteria confirmed"}, renamed["modified"])
        self._meeting_record(visit["id"])
        minutes = update_visit(visit["id"], {"type": "advance", "status": "Minutes Submitted"}, visited["modified"])
        # review_visit is the endpoint the frontend calls; it must complete and notify the owner.
        reviewed = review_visit(visit["id"], minutes["modified"])
        self.assertEqual(reviewed["status"], "Manager Reviewed")
        reviewed_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Visit", "source_name": visit["id"], "title": "Visit minutes reviewed"},
            fields=["recipient_user"],
        )
        self.assertEqual([row.recipient_user for row in reviewed_notice], [self.other_sales])
        with self.assertRaises(CrmApiException) as locked:
            update_visit(visit["id"], {"type": "edit", "date": "2026-09-01"}, reviewed["modified"])
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")

    def test_existing_meeting_record_requires_current_modified_token(self):
        account, contact = self._records(self.sales, "MeetingCAS")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        payload = {
            "meetingStart": "2026-08-20T10:00", "meetingEnd": "2026-08-20T11:00",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": "Proceed", "followup": "Send plan",
        }

        created = update_meeting_record(visit["id"], payload)
        self.assertTrue(created["modified"])
        # A complete record submits the new visit for Manager review straight away.
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Minutes Submitted")
        submitted = update_meeting_record(
            visit["id"], {**payload, "summary": "Submitted"}, created["modified"],
        )
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Minutes Submitted")

        with self.assertRaises(CrmApiException) as missing:
            update_meeting_record(visit["id"], {**payload, "summary": "Missing token"})
        self.assertEqual(missing.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as stale:
            update_meeting_record(visit["id"], {**payload, "summary": "Stale"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        updated = update_meeting_record(visit["id"], {**payload, "summary": "Current"}, submitted["modified"])
        self.assertEqual(updated["summary"], "Current")

    def test_saving_a_complete_record_submits_the_visit_for_manager_review(self):
        account, contact = self._records(self.sales, "AutoSubmit")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        self.assertEqual(visit["status"], "Planned")
        payload = {
            "meetingStart": "", "meetingEnd": "",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": "", "followup": "Send plan",
        }

        # A record still missing a required field keeps the visit waiting to be visited.
        draft = update_meeting_record(visit["id"], payload)
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Planned")

        reminders = {"source_doctype": "CRM Visit", "source_name": visit["id"], "title": "Visit awaiting review"}
        # An incomplete record is not submitted, so no Manager is reminded yet.
        self.assertEqual(frappe.db.count("CRM Notification Event", reminders), 0)

        # Completing it submits the visit for Manager review and reminds the Managers.
        completed = update_meeting_record(visit["id"], {**payload, "conclusion": "Proceed"}, draft["modified"])
        submitted = get_visit(visit["id"])
        self.assertEqual(submitted["status"], "Minutes Submitted")
        recipients = frappe.get_all("CRM Notification Event", filters=reminders, pluck="recipient_user")
        self.assertIn(self.manager, recipients)
        self.assertNotIn(self.sales, recipients)
        self.assertEqual(
            frappe.db.get_value("CRM Notification Event", {**reminders, "recipient_user": self.manager}, "route"),
            f"/visits?focus={visit['id']}",
        )

        # Saving the record again while it waits for review does not remind anyone twice.
        update_meeting_record(visit["id"], {**payload, "conclusion": "Proceed, revised"}, completed["modified"])
        self.assertEqual(frappe.db.count("CRM Notification Event", {**reminders, "recipient_user": self.manager}), 1)

        # Submitting skips Visited, which is where an outcome used to become
        # mandatory, and the edit form has no outcome field -- so the record's own
        # conclusion and follow-up fill them instead of leaving the visit list's
        # outcome column permanently empty.
        self.assertEqual(submitted["outcome"], "Proceed")
        self.assertEqual(submitted["nextAction"], "Send plan")

        # The Manager review completes the visit.
        frappe.set_user(self.manager)
        reviewed = review_visit(visit["id"], get_visit(visit["id"])["modified"])
        self.assertEqual(reviewed["status"], "Manager Reviewed")
        self.assertEqual(reviewed["outcome"], "Proceed")

    def test_auto_submit_keeps_an_outcome_the_user_already_entered(self):
        account, contact = self._records(self.sales, "KeepOutcome")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        visited = update_visit(
            visit["id"],
            {"type": "advance", "status": "Visited", "outcome": "Agreed on site", "nextAction": "Quote"},
            visit["modified"],
        )
        self.assertEqual(visited["outcome"], "Agreed on site")
        update_meeting_record(visit["id"], {
            "meetingStart": "", "meetingEnd": "",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": "Proceed", "followup": "Send plan",
        })
        submitted = get_visit(visit["id"])
        self.assertEqual(submitted["status"], "Minutes Submitted")
        self.assertEqual(submitted["outcome"], "Agreed on site")
        self.assertEqual(submitted["nextAction"], "Quote")

    def test_patch_submits_planned_visits_whose_record_was_already_complete(self):
        from rayher_crm.patches.v1_0.submit_planned_visits_with_complete_records import execute

        account, contact = self._records(self.sales, "PatchSubmit")
        frappe.set_user(self.sales)
        complete = create_visit(self._input(account, contact, self.sales))
        incomplete = create_visit(self._input(account, contact, self.sales, subject="Incomplete record"))
        frappe.set_user("Administrator")
        # Records saved before the auto-submit rule existed, while the visits were still Planned.
        self._meeting_record(complete["id"])
        frappe.get_doc({
            "doctype": "CRM Visit Meeting Record", "visit": incomplete["id"], "purpose": "Discuss project",
            "parse_status": "NeedsManualReview", "parse_message": "Partial record", "manually_corrected": 0,
        }).insert(ignore_permissions=True)

        execute()

        self.assertEqual(frappe.db.get_value("CRM Visit", complete["id"], "status"), "Minutes Submitted")
        self.assertEqual(frappe.db.get_value("CRM Visit", incomplete["id"], "status"), "Planned")
        # The backlog gets the same outcome treatment as the live path, and the
        # move is attributable rather than anonymous.
        migrated = frappe.db.get_value(
            "CRM Visit", complete["id"], ["outcome", "next_action", "modified_by"], as_dict=True
        )
        record = frappe.db.get_value(
            "CRM Visit Meeting Record", {"visit": complete["id"]}, ["conclusion", "followup"], as_dict=True
        )
        self.assertEqual(migrated.outcome, record.conclusion)
        self.assertEqual(migrated.next_action, record.followup)
        self.assertEqual(migrated.modified_by, "Administrator")
        # Nothing touched the visit whose record is incomplete.
        self.assertFalse(frappe.db.get_value("CRM Visit", incomplete["id"], "outcome"))
        # Migrated visits reach the queue with the same reminder the live path sends.
        reminders = {
            "source_doctype": "CRM Visit", "source_name": complete["id"],
            "title": "Visit awaiting review", "recipient_user": self.manager,
        }
        self.assertEqual(frappe.db.count("CRM Notification Event", reminders), 1)
        self.assertEqual(
            frappe.db.count("CRM Notification Event", {**reminders, "source_name": incomplete["id"]}), 0
        )

    def test_long_followup_submits_with_a_next_action_that_fits(self):
        account, contact = self._records(self.sales, "LongFollowup")
        frappe.set_user(self.sales)
        multi_line = create_visit(self._input(account, contact, self.sales))
        single_line = create_visit(self._input(account, contact, self.sales, subject="One long line"))
        record = {
            "meetingStart": "", "meetingEnd": "",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": "Proceed",
        }
        # Real follow-ups run to several lines, far past CRM Visit.next_action,
        # which is a 140-character Data field. Saving such a record used to fail.
        followup = "\n".join(f"{index}. 跟进事项：整理客户反馈并发送第{index}版方案" for index in range(1, 9))
        self.assertGreater(len(followup), 140)
        update_meeting_record(multi_line["id"], {**record, "followup": followup})
        update_meeting_record(single_line["id"], {**record, "followup": "跟进" * 90})

        submitted = get_visit(multi_line["id"])
        self.assertEqual(submitted["status"], "Minutes Submitted")
        # The first line is the next action; the record keeps the whole follow-up.
        self.assertEqual(submitted["nextAction"], "1. 跟进事项：整理客户反馈并发送第1版方案")
        self.assertEqual(
            frappe.db.get_value("CRM Visit Meeting Record", {"visit": multi_line["id"]}, "followup"), followup,
        )
        submitted = get_visit(single_line["id"])
        self.assertEqual(submitted["status"], "Minutes Submitted")
        self.assertEqual(submitted["nextAction"], ("跟进" * 90)[:140])

    def test_long_conclusion_submits_with_an_outcome_that_fits(self):
        account, contact = self._records(self.sales, "LongConclusion")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        # 72,000 bytes: more than CRM Visit.outcome (Small Text, 65,535 bytes) holds,
        # so copying it whole made the whole record save fail.
        conclusion = "结论" * 12000
        update_meeting_record(visit["id"], {
            "meetingStart": "", "meetingEnd": "",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": conclusion, "followup": "Send plan",
        })

        submitted = get_visit(visit["id"])
        self.assertEqual(submitted["status"], "Minutes Submitted")
        self.assertEqual(submitted["outcome"], conclusion[:4000])
        # The record keeps the whole conclusion.
        self.assertEqual(
            frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit["id"]}, "conclusion"), conclusion,
        )

    def test_patch_fills_a_next_action_that_fits_and_replaces_a_blank_outcome(self):
        from rayher_crm.patches.v1_0.submit_planned_visits_with_complete_records import execute

        account, contact = self._records(self.sales, "PatchLong")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        frappe.set_user("Administrator")
        record = self._meeting_record(visit["id"])
        # MariaDB runs in STRICT_TRANS_TABLES mode, so copying this follow-up into the
        # 140-character next_action column raised "Data too long" and stopped migrate.
        frappe.db.set_value("CRM Visit Meeting Record", record.name, "followup", "\n\t\n" + "跟进" * 90 + "\nSecond line")
        # A newline is blank to the live path's strip(); the migration must agree.
        frappe.db.set_value("CRM Visit", visit["id"], "outcome", "\n")

        execute()

        migrated = frappe.db.get_value("CRM Visit", visit["id"], ["status", "outcome", "next_action"], as_dict=True)
        self.assertEqual(migrated.status, "Minutes Submitted")
        self.assertEqual(migrated.outcome, "Proceed")
        self.assertEqual(migrated.next_action, ("跟进" * 90)[:140])

    def test_patch_ignores_a_record_whose_fields_hold_only_whitespace(self):
        from rayher_crm.patches.v1_0.submit_planned_visits_with_complete_records import execute

        account, contact = self._records(self.sales, "PatchWhitespace")
        frappe.set_user(self.sales)
        blank = create_visit(self._input(account, contact, self.sales, subject="Whitespace record"))
        frappe.set_user("Administrator")
        # Tabs and newlines survive MariaDB's bare TRIM() but not Python's strip(),
        # so this row would be submitted here and then refused by review_visit.
        frappe.get_doc({
            "doctype": "CRM Visit Meeting Record", "visit": blank["id"],
            "purpose": "\t", "attendees": "\n", "agenda": "\r\n", "summary": " \t ",
            "conclusion": "\n\n", "followup": "\t\n",
            "parse_status": "Parsed", "parse_message": "Blank record", "manually_corrected": 1,
        }).insert(ignore_permissions=True)

        execute()

        self.assertEqual(frappe.db.get_value("CRM Visit", blank["id"], "status"), "Planned")

    def test_patch_follows_the_live_rules_and_survives_a_row_it_cannot_write(self):
        from unittest.mock import patch

        from rayher_crm.patches.v1_0.submit_planned_visits_with_complete_records import execute

        account, contact = self._records(self.sales, "PatchRules")
        frappe.set_user(self.sales)
        blank = create_visit(self._input(account, contact, self.sales, subject="Form-feed record"))
        oversized = create_visit(self._input(account, contact, self.sales, subject="Oversized conclusion"))
        broken = create_visit(self._input(account, contact, self.sales, subject="Write fails"))
        regular = create_visit(self._input(account, contact, self.sales, subject="Regular record"))
        frappe.set_user("Administrator")
        # A form feed is blank to Python's strip() -- the rule review_visit applies -- but
        # passes the SQL filter, so only the patch's Python re-check keeps this row out.
        # NBSP and ideographic spaces would not exercise it: under the columns'
        # utf8mb4_unicode_ci collation they already compare equal to ''.
        frappe.get_doc({
            "doctype": "CRM Visit Meeting Record", "visit": blank["id"],
            **{field: "\x0c" for field in ("purpose", "attendees", "agenda", "summary", "conclusion", "followup")},
            "parse_status": "Parsed", "parse_message": "Form-feed record", "manually_corrected": 1,
        }).insert(ignore_permissions=True)
        # A conclusion longer than the outcome column (Small Text, 65,535 bytes) can hold
        # is cut the way the live path cuts it.
        record = self._meeting_record(oversized["id"])
        frappe.db.set_value("CRM Visit Meeting Record", record.name, "conclusion", "x" * 70000)
        self._meeting_record(broken["id"])
        self._meeting_record(regular["id"])
        set_value = frappe.db.set_value

        def failing_set_value(doctype, name, *args, **kwargs):
            result = set_value(doctype, name, *args, **kwargs)
            if doctype == "CRM Visit" and name == broken["id"]:
                # Fail after the row is written, so only the savepoint can undo it.
                raise RuntimeError("injected: this visit row cannot be written")
            return result

        with patch.object(frappe.db, "set_value", side_effect=failing_set_value):
            execute()

        self.assertEqual(frappe.db.get_value("CRM Visit", blank["id"], "status"), "Planned")
        migrated = frappe.db.get_value("CRM Visit", oversized["id"], ["status", "outcome"], as_dict=True)
        self.assertEqual((migrated.status, migrated.outcome), ("Minutes Submitted", "x" * 4000))
        # A row that cannot be written is rolled back to where it was instead of
        # stopping migrate, and the Error Log names it.
        self.assertEqual(frappe.db.get_value("CRM Visit", broken["id"], "status"), "Planned")
        self.assertTrue(frappe.db.exists(
            "Error Log", {"method": f"Visit {broken['id']} was not submitted for Manager review"},
        ))
        self.assertEqual(frappe.db.get_value("CRM Visit", regular["id"], "status"), "Minutes Submitted")
        reminders = {"source_doctype": "CRM Visit", "title": "Visit awaiting review", "recipient_user": self.manager}
        for visit, expected in ((blank, 0), (broken, 0), (oversized, 1), (regular, 1)):
            self.assertEqual(
                frappe.db.count("CRM Notification Event", {**reminders, "source_name": visit["id"]}), expected,
            )

    def test_notification_is_in_same_savepoint_as_visit_update(self):
        account, contact = self._records(self.sales, "Atomic")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        visited = update_visit(visit["id"], {
            "type": "advance", "status": "Visited", "outcome": "Done",
        }, visit["modified"])
        self._meeting_record(visit["id"])
        minutes = update_visit(visit["id"], {"type": "advance", "status": "Minutes Submitted"}, visited["modified"])
        before = frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Visit", "source_name": visit["id"]})

        def fail_after_notification(stage: str) -> None:
            if stage == "after_notification_insert":
                raise RuntimeError("injected visit notification failure")

        frappe.set_user(self.manager)
        with self.assertRaisesRegex(RuntimeError, "injected visit notification failure"):
            update_visit(visit["id"], {"type": "advance", "status": "Manager Reviewed"}, minutes["modified"], failure_injector=fail_after_notification)
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Minutes Submitted")
        self.assertEqual(
            frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Visit", "source_name": visit["id"]}),
            before,
        )

    def _submitted_visit(self, suffix: str) -> dict:
        account, contact = self._records(self.sales, suffix)
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        update_meeting_record(visit["id"], {
            "meetingStart": "", "meetingEnd": "",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": "Proceed", "followup": "Send plan",
        })
        return get_visit(visit["id"])

    def test_review_completes_when_the_visit_owner_has_left(self):
        visit = self._submitted_visit("OwnerLeft")
        frappe.set_user("Administrator")
        frappe.db.set_value("User", self.sales, "enabled", 0)
        try:
            frappe.set_user(self.manager)
            reviewed = review_visit(visit["id"], visit["modified"])
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("User", self.sales, "enabled", 1)
        # The review is the business action; a notice nobody can receive must not
        # fail it -- and must never leave it committed behind an error either.
        self.assertEqual(reviewed["status"], "Manager Reviewed")
        self.assertEqual(frappe.db.count("CRM Notification Event", {
            "source_doctype": "CRM Visit", "source_name": visit["id"], "title": "Visit minutes reviewed",
        }), 0)

    def test_review_rolls_back_when_its_notice_fails(self):
        from unittest.mock import patch

        visit = self._submitted_visit("ReviewAtomic")
        frappe.set_user(self.manager)
        with patch(
            "rayher_crm.services.visits._notify_update", side_effect=RuntimeError("injected review notice failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected review notice failure"):
                review_visit(visit["id"], visit["modified"])
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Minutes Submitted")

    def test_only_the_visit_owner_or_a_manager_changes_the_visit(self):
        account, contact = self._records(self.sales, "ActionOwner")
        # A Public account lets the action owner reach a colleague's visit.
        frappe.db.set_value("Customer", account["id"], "custom_crm_visibility", "Public")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        visit = update_visit(
            visit["id"], {"type": "edit", "nextAction": "Bring samples", "actionOwner": self.other_sales},
            visit["modified"],
        )

        frappe.set_user(self.other_sales)
        seen = get_visit(visit["id"])
        # Keeping the owner used to fail on every save, and naming themselves took
        # the visit away from its owner. Neither is theirs to do.
        for owner in (self.sales, self.other_sales):
            with self.assertRaises(CrmApiException) as denied:
                update_visit(visit["id"], {"type": "edit", "subject": "Taken over", "owner": owner}, seen["modified"])
            self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        # Advancing it is not theirs either; only completing their own action is.
        with self.assertRaises(CrmApiException) as advanced:
            update_visit(
                visit["id"], {"type": "advance", "status": "Visited", "outcome": "Taken over"}, seen["modified"],
            )
        self.assertEqual(advanced.exception.code, "SCOPE_DENIED")
        self.assertEqual(
            frappe.db.get_value("CRM Visit", visit["id"], ["visit_owner", "subject", "status"]),
            (self.sales, "Fab review", "Planned"),
        )
        # Nor is its meeting record, which would submit the visit for review once complete.
        with self.assertRaises(CrmApiException) as record_denied:
            update_meeting_record(visit["id"], {
                "meetingStart": "", "meetingEnd": "",
                "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
                "summary": "Summary", "conclusion": "Proceed", "followup": "Send plan",
            })
        self.assertEqual(record_denied.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as upload_denied:
            upload_meeting_file(visit["id"], "minutes.txt", "text/plain", b"Purpose: Review\n")
        self.assertEqual(upload_denied.exception.code, "SCOPE_DENIED")
        self.assertFalse(frappe.db.exists("CRM Visit Meeting Record", {"visit": visit["id"]}))
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Planned")
        # The action they were given is still theirs to complete.
        done = update_visit(visit["id"], {"type": "complete_action"}, seen["modified"])
        self.assertTrue(done["actionDone"])

        frappe.set_user(self.sales)
        edited = update_visit(visit["id"], {"type": "edit", "subject": "Fab review (moved)"}, done["modified"])
        frappe.set_user(self.manager)
        edited = update_visit(visit["id"], {"type": "edit", "subject": "Fab review (confirmed)"}, edited["modified"])
        self.assertEqual(edited["subject"], "Fab review (confirmed)")

    def test_meeting_records_are_written_only_through_the_visit_service(self):
        visit = self._submitted_visit("RecordApi")
        name = frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit["id"]}, "name")
        # The standard document API (REST, Desk) skips the service's owner, scope and
        # review checks, so nobody may write a record through it -- not the owner, a
        # colleague who only holds the action, or a Manager.
        for user in (self.sales, self.other_sales, self.manager):
            frappe.set_user(user)
            record = frappe.get_doc("CRM Visit Meeting Record", name)
            record.summary = "tampered through the document API"
            with self.assertRaises(frappe.PermissionError):
                record.save()
        frappe.set_user(self.other_sales)
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({
                "doctype": "CRM Visit Meeting Record", "visit": visit["id"], "purpose": "Forged",
            }).insert()
        self.assertEqual(frappe.db.get_value("CRM Visit Meeting Record", name, "summary"), "Summary")
        # Nor may anyone delete it there, which would leave the visit without minutes.
        from frappe.client import delete as client_delete

        frappe.set_user(self.manager)
        with self.assertRaises(frappe.PermissionError):
            client_delete("CRM Visit Meeting Record", name)
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("CRM Visit Meeting Record", name)
        self.assertTrue(frappe.db.exists("CRM Visit Meeting Record", name))
        # The service path still works for the owner.
        from rayher_crm.services.visit_meetings import get_record as get_meeting_record

        frappe.set_user(self.sales)
        saved = update_meeting_record(visit["id"], {
            "meetingStart": "", "meetingEnd": "",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary, revised", "conclusion": "Proceed", "followup": "Send plan",
        }, get_meeting_record(visit["id"])["modified"])
        self.assertEqual(saved["summary"], "Summary, revised")

    def test_visits_are_changed_only_through_the_visit_service(self):
        from frappe.client import set_value as client_set_value

        account, contact = self._records(self.sales, "VisitApi")
        # A Public account lets the action owner reach a colleague's visit.
        frappe.db.set_value("Customer", account["id"], "custom_crm_visibility", "Public")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        visit = update_visit(
            visit["id"], {"type": "edit", "nextAction": "Bring samples", "actionOwner": self.other_sales},
            visit["modified"],
        )
        # The standard document API skips the service's owner and workflow checks:
        # the action owner could take the visit over or mark it reviewed there, and
        # upload_file attaches files only where the user may write. Sales write
        # visits through the service alone, the owner included.
        for user, field, value in (
            (self.other_sales, "visit_owner", self.other_sales),
            (self.other_sales, "status", "Manager Reviewed"),
            (self.sales, "status", "Manager Reviewed"),
        ):
            frappe.set_user(user)
            self.assertFalse(frappe.has_permission(
                "CRM Visit", "write", doc=frappe.get_doc("CRM Visit", visit["id"]), user=user,
            ))
            with self.assertRaises(frappe.PermissionError):
                client_set_value("CRM Visit", visit["id"], field, value)
        self.assertEqual(
            frappe.db.get_value("CRM Visit", visit["id"], ["visit_owner", "status"]), (self.sales, "Planned"),
        )
        # The service still lets the owner change it.
        frappe.set_user(self.sales)
        moved = update_visit(visit["id"], {"type": "edit", "subject": "Fab review (moved)"}, visit["modified"])
        self.assertEqual(moved["subject"], "Fab review (moved)")

    def test_meeting_records_are_readable_only_within_visit_scope(self):
        from frappe.client import get as client_get

        account, contact = self._records(self.sales, "RecordScope")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        update_meeting_record(visit["id"], {
            "meetingStart": "", "meetingEnd": "",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": "Customer will drop vendor X", "followup": "Send plan",
        })
        name = frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit["id"]}, "name")
        record_filter = {"visit": visit["id"]}

        # The record carries the minutes, so it is read exactly where its visit is:
        # never by an Engineer, and by Sales only for a visit in their scope. The
        # standard document API (REST list and get) must apply the same rule.
        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            frappe.get_list("CRM Visit Meeting Record", filters=record_filter, fields=["conclusion"])
        # The account is Private to self.sales: a colleague reaches neither the visit nor its record.
        frappe.set_user(self.other_sales)
        self.assertEqual(frappe.get_list("CRM Visit", filters={"name": visit["id"]}, fields=["name"]), [])
        self.assertEqual(frappe.get_list("CRM Visit Meeting Record", filters=record_filter, fields=["conclusion"]), [])
        self.assertFalse(frappe.get_doc("CRM Visit Meeting Record", name).has_permission("read"))
        with self.assertRaises(frappe.PermissionError):
            client_get("CRM Visit Meeting Record", name)

        # Once the colleague holds the visit's action on a Public account, the visit is
        # in their scope and so is its record; the owner and a Manager read it too.
        frappe.set_user("Administrator")
        frappe.db.set_value("Customer", account["id"], "custom_crm_visibility", "Public")
        frappe.set_user(self.sales)
        update_visit(
            visit["id"], {"type": "edit", "nextAction": "Bring samples", "actionOwner": self.other_sales},
            get_visit(visit["id"])["modified"],
        )
        for user in (self.other_sales, self.sales, self.manager):
            frappe.set_user(user)
            rows = frappe.get_list("CRM Visit Meeting Record", filters=record_filter, fields=["conclusion"])
            self.assertEqual([row.conclusion for row in rows], ["Customer will drop vendor X"], user)
            self.assertTrue(frappe.get_doc("CRM Visit Meeting Record", name).has_permission("read"), user)

        # The DocPerms behind this are installed by install_crm_doc_permissions, so an
        # existing site picks them up on migrate: Sales read only, Engineers nothing.
        roles = {row.role: row for row in frappe.get_meta("CRM Visit Meeting Record").permissions}
        self.assertTrue(roles["CRM Sales"].read)
        self.assertFalse(bool(roles["CRM Sales"].write) or bool(roles["CRM Sales"].create))
        self.assertFalse(bool(roles["CRM Engineer"].read))

    def test_only_manager_can_delete_visit(self):
        account, contact = self._records(self.other_sales, "Delete")
        visit = create_visit(self._input(account, contact, self.other_sales))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            delete_visit(visit["id"])
        self.assertTrue(frappe.db.exists("CRM Visit", visit["id"]))

        frappe.set_user(self.manager)
        self.assertEqual(delete_visit(visit["id"]), {"id": visit["id"], "status": "Deleted"})
        self.assertFalse(frappe.db.exists("CRM Visit", visit["id"]))
