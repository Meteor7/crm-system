"""Shared-blob reference counting for private attachments."""
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.share import add as add_share
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services import private_file_lifecycle as lifecycle


class TestPrivateFileLifecycle(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.content = uuid4().hex.encode()
        self.committed: list[str] = []

    def tearDown(self):
        frappe.db.rollback()
        # A committed row outlives the suite's transaction, so the few tests that
        # need one register it here and it is removed explicitly.
        for name in self.committed:
            if frappe.db.exists("File", name):
                frappe.delete_doc("File", name, ignore_permissions=True, force=True)
        if self.committed:
            frappe.db.commit()
        frappe.set_user(self.original_user)
        super().tearDown()

    def private_file(self, filename=None, content=None):
        return lifecycle.save_private_file(
            filename or ("blob-" + uuid4().hex[:10] + ".txt"),
            content or self.content,
            None,
            None,
        )

    def ordinary_private_file(self, filename=None, content=None):
        return frappe.get_doc({
            "doctype": "File",
            "file_name": filename or ("ordinary-" + uuid4().hex[:10] + ".txt"),
            "content": content or self.content,
            "is_private": 1,
        }).insert(ignore_permissions=True)

    def test_website_owner_can_list_ordinary_unattached_file_and_folder(self):
        from frappe.client import get_list
        from frappe.permissions import SYSTEM_USER_ROLE
        from rayher_crm.services.managed_file_access import file_query

        user = "ordinary-file-owner-" + uuid4().hex[:10] + "@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": user, "first_name": "Ordinary File Owner",
            "enabled": 1, "send_welcome_email": 0, "user_type": "Website User",
        }).insert(ignore_permissions=True)
        ordinary = self.ordinary_private_file()
        folder = frappe.get_doc({
            "doctype": "File", "file_name": "OrdinaryFolder-" + uuid4().hex[:10],
            "folder": "Home", "is_folder": 1, "is_private": 1,
        }).insert(ignore_permissions=True)
        for doc in (ordinary, folder):
            frappe.db.set_value("File", doc.name, {"owner": user, "attached_to_doctype": None}, update_modified=False)
        frappe.clear_cache(user=user)
        frappe.set_user(user)
        self.assertNotIn(SYSTEM_USER_ROLE, frappe.get_roles(user))
        expected = {ordinary.name, folder.name}
        rows = get_list("File", filters={"name": ["in", sorted(expected)]}, fields=["name"])
        self.assertEqual({row["name"] for row in rows}, expected)
        policy_rows = frappe.db.sql(
            "SELECT name FROM `tabFile` WHERE name IN (%s,%s) AND " + file_query(user),
            (ordinary.name, folder.name),
        )
        self.assertEqual({row[0] for row in policy_rows}, expected)
        frappe.set_user("Administrator")

    def test_repeated_ordinary_email_attachments_are_classified_in_one_pass(self):
        from rayher_crm.services import managed_file_access as access

        communication = frappe.get_doc({
            "doctype": "Communication", "communication_type": "Communication",
            "communication_medium": "Email", "sent_or_received": "Received",
            "subject": "Ordinary repeated attachment", "content": "Normal email body",
            "sender": "sender@example.invalid",
        }).insert(ignore_permissions=True)
        files = []
        for size in (3, 5):
            while len(files) < size:
                files.append(frappe.get_doc({
                    "doctype": "File", "file_name": "mail-" + uuid4().hex + ".txt",
                    "content": self.content, "is_private": 1,
                    "attached_to_doctype": "Communication", "attached_to_name": communication.name,
                }).insert(ignore_permissions=True))
            self.assertEqual({file.file_url for file in files}, {files[0].file_url})
            with self.subTest(group_size=size), \
                patch.object(frappe.db, "sql", wraps=frappe.db.sql) as queries, \
                patch.object(access, "_crm_target", wraps=access._crm_target) as modules:
                self.assertFalse(access._protected_blob(
                    url=files[0].file_url, content_hash=files[0].content_hash,
                ))
            sql = [call.args[0] for call in queries.call_args_list]
            self.assertEqual(sql.count(access._PROTECTED_BLOB_URL_QUERY), 1)
            self.assertEqual(sql.count(access._PROTECTED_BLOB_HASH_QUERY), 1)
            self.assertLessEqual(sum("FROM `tabFile`" in query for query in sql), 3)
            self.assertLessEqual(sum("FROM `tabCRM Controlled Document`" in query for query in sql), 1)
            self.assertLessEqual(sum("FROM `tabCRM Contact File`" in query for query in sql), 1)
            self.assertLessEqual(modules.call_count, 2)

    def test_native_private_download_reuses_group_classification_but_checks_each_owner(self):
        from types import SimpleNamespace
        from frappe.core.doctype.file import file as core_file
        from frappe.core.doctype.file.utils import find_file_by_url
        from rayher_crm.services import managed_file_access as access

        user = "download-owner-" + uuid4().hex[:10] + "@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": user, "first_name": "Download Owner",
            "enabled": 1, "send_welcome_email": 0, "user_type": "Website User",
        }).insert(ignore_permissions=True)
        files = [self.ordinary_private_file() for _ in range(3)]
        url = files[0].file_url
        self.assertEqual({file.file_url for file in files}, {url})
        ordered = frappe.get_all("File", filters={"file_url": url}, fields="*")
        self.assertEqual(len(ordered), 3)
        frappe.set_user(user)
        request = SimpleNamespace(method="GET", path=url)
        with patch.object(frappe.local, "request", request, create=True), \
            patch.object(frappe.local, "form_dict", frappe._dict(), create=True), \
            patch.object(frappe.db, "sql", wraps=frappe.db.sql) as queries, \
            patch.object(core_file, "has_permission", wraps=core_file.has_permission) as permissions:
            self.assertIsNone(find_file_by_url(url))
            self.assertEqual(permissions.call_count, 3)
            self.assertEqual(sum(
                call.args[0] == access._MANAGED_FILE_CANDIDATE_QUERY for call in queries.call_args_list
            ), 1)
            # A normal owner update must invalidate the group snapshot. Native
            # owner authorization continues to run separately for each row.
            frappe.db.set_value("File", ordered[-1].name, "owner", user, update_modified=False)
            queries.reset_mock()
            permissions.reset_mock()
            self.assertEqual(find_file_by_url(url).name, ordered[-1].name)
            self.assertEqual(permissions.call_count, 3)
            self.assertEqual(sum(
                call.args[0] == access._MANAGED_FILE_CANDIDATE_QUERY for call in queries.call_args_list
            ), 1)

    def test_native_classification_reuse_expires_on_writes_savepoint_and_request_change(self):
        from types import SimpleNamespace
        from rayher_crm.services import managed_file_access as access

        ordinary = self.ordinary_private_file()
        request = SimpleNamespace(method="GET", path=ordinary.file_url)
        with patch.object(frappe.local, "request", request, create=True), \
            patch.object(frappe.local, "form_dict", frappe._dict(), create=True), \
            patch.object(frappe.db, "sql", wraps=frappe.db.sql) as queries:
            def classify():
                self.assertEqual(access._managed_file_kinds(ordinary, _native_download=True), set())

            def group_reads():
                return sum(call.args[0] == access._MANAGED_FILE_CANDIDATE_QUERY for call in queries.call_args_list)

            classify()
            classify()
            self.assertEqual(group_reads(), 1)
            frappe.db.savepoint("normal_classification_metadata")
            frappe.db.set_value("File", ordinary.name, "file_name", "renamed-ordinary.txt", update_modified=False)
            classify()
            self.assertEqual(group_reads(), 2)
            frappe.db.rollback(save_point="normal_classification_metadata")
            classify()
            self.assertEqual(group_reads(), 3)
            frappe.local.request = SimpleNamespace(method="GET", path=ordinary.file_url)
            classify()
            self.assertEqual(group_reads(), 4)
            # RPC dispatch and generic callers never use native route reuse.
            frappe.local.form_dict.cmd = "frappe.client.get"
            classify()
            classify()
            self.assertEqual(group_reads(), 6)
            frappe.local.form_dict.cmd = None
            access._managed_file_kinds(ordinary)
            self.assertEqual(group_reads(), 7)

    def test_folder_insert_checks_reference_independently_of_content(self):
        from rayher_crm.services import managed_file_access

        # Exercise guard dispatch with synthetic classification only. No File
        # row or storage reference is created by this contract test.
        doc = frappe._dict(
            is_folder=1, content="unused folder metadata", flags=frappe._dict(),
            file_name="OrdinaryFolder", file_url=None, is_private=1,
        )
        reference = "/private/files/guard-contract.txt"
        for protected in (False, True):
            with self.subTest(protected=protected), \
                patch.object(managed_file_access, "canonical_local_reference", return_value=reference), \
                patch.object(managed_file_access, "_protected_blob", return_value=protected) as classify:
                if protected:
                    with self.assertRaises(frappe.PermissionError):
                        managed_file_access.protect_file_insert(doc)
                    frappe.clear_last_message()
                else:
                    managed_file_access.protect_file_insert(doc)
                classify.assert_called_once_with(url=reference)

    def test_file_alias_inventory_uses_database_url_comparison(self):
        from rayher_crm.services.managed_file_access import (
            canonical_file_alias_inventory,
            canonical_local_reference,
        )

        target = self.ordinary_private_file(filename="inventory-" + uuid4().hex + "-café.txt")
        basename = target.file_url.rsplit("/", 1)[-1]
        urls = {
            "case": "/private/files/" + basename.upper(),
            "accent": target.file_url.replace("é", "e"),
            "space": target.file_url + " ",
            "absolute": frappe.utils.get_url() + "/private/files/" + basename.upper(),
            "other": "/private/files/unrelated-" + uuid4().hex + ".txt",
        }
        # Synthetic inventory entries exercise collation without persisting
        # duplicate references or modifying any managed attachment.
        files = {}
        for name, url in {target.name: target.file_url, **urls}.items():
            files[name] = frappe._dict(
                name=name, file_url=url, is_private=1, is_folder=0,
                canonical_reference=canonical_local_reference(file_url=url, is_private=1),
                reference_error=False,
            )
        report = canonical_file_alias_inventory(
            [target.name], snapshot={"files": files, "by_reference": {}},
        )
        self.assertEqual(report["invalid"], [])
        self.assertEqual(report["aliases"], ["absolute", "accent", "case", "space"])

    def test_protected_blob_retains_database_url_matches(self):
        from rayher_crm.services.managed_file_access import (
            _PROTECTED_BLOB_URL_QUERY,
            _protected_blob,
        )

        stored = frappe._dict(
            name="database-url-match", file_url="/private/files/Stored.txt",
            is_private=1, is_folder=0, attached_to_doctype=None,
            custom_crm_service_upload=1,
        )
        with patch.object(frappe.db, "sql", return_value=[stored]) as lookup:
            self.assertTrue(_protected_blob(url="/private/files/stored.txt"))
        self.assertEqual(lookup.call_args.args[0], _PROTECTED_BLOB_URL_QUERY)

    def test_replaced_upload_cleanup_preserves_references_and_uses_physical_paths(self):
        from rayher_crm.services.managed_file_access import _discard_detached_upload_body

        ordinary = self.ordinary_private_file(filename="retained-" + uuid4().hex + ".txt")
        source_path = Path(ordinary.get_full_path())
        self.assertIsNotNone(ordinary.flags.crm_written_body)
        _discard_detached_upload_body(ordinary.flags.crm_written_body)
        self.assertEqual(source_path.read_bytes(), self.content)

        # A temporary ordinary body with a differently spelled basename has
        # no File row of its own. Its cleanup must not touch the retained body.
        detached = frappe.get_doc({
            "doctype": "File", "file_name": source_path.name.upper(),
            "content": self.content, "is_private": 1, "__islocal": 1,
        })
        detached.save_file(content=self.content, ignore_existing_file_check=True)
        detached_path = Path(detached.get_full_path())
        record = detached.flags.crm_written_body
        self.assertIsNotNone(record)
        try:
            _discard_detached_upload_body(record)
            self.assertFalse(detached_path.exists())
            self.assertEqual(source_path.read_bytes(), self.content)
            # A later writer can reuse the name and bytes. The old rollback
            # callback must not remove that replacement body.
            detached_path.write_bytes(self.content)
            _discard_detached_upload_body(record)
            self.assertTrue(detached_path.exists())
        finally:
            detached_path.unlink(missing_ok=True)

    def test_parent_read_scope_keeps_share_only_conditions_without_file_recursion(self):
        from rayher_crm.services.managed_file_access import _parent_read_scope

        shared = "`tabCRM Visit`.`name`='own-shared-visit'"

        class ShareOnlyQuery:
            def __init__(self, doctype, user):
                self.doctype, self.user = doctype, user
                self.conditions = [shared]
                self.reference_doctype = None

            def build_match_conditions(query):
                self.assertEqual(query.reference_doctype, "CRM Visit")
                self.assertEqual(query.get_permission_query_conditions(), "")
                return ""

        with patch("frappe.model.db_query.DatabaseQuery", ShareOnlyQuery), \
            patch.object(frappe, "has_permission", return_value=True), \
            patch("rayher_crm.permissions.scope.conditions_for_doctype", return_value="1=1"):
            self.assertEqual(_parent_read_scope("CRM Visit", "own-parent-reader"), f"({shared}) AND (1=1)")
        with patch.object(frappe, "has_permission", return_value=False):
            self.assertEqual(_parent_read_scope("CRM Visit", "own-parent-reader"), "1=0")

    def test_parent_read_scope_preserves_percents_in_list_and_bound_file_queries(self):
        from rayher_crm.services.managed_file_access import _parent_read_scope

        native_share = "`tabCRM Contact File`.`name`='shared%file'"
        native_match = "`tabCRM Contact File`.`account`='Account 100% Pure'"
        crm_scope = "`tabCRM Contact File`.`uploaded_by`='crm%%user@example.invalid'"

        class NativeQuery:
            def __init__(self, doctype, user):
                self.doctype, self.user = doctype, user
                self.conditions = [native_share]

            def build_match_conditions(self):
                if self.get_permission_query_conditions():
                    raise AssertionError("CRM scope must not be mixed into native match fragments")
                return native_match

        with patch("frappe.model.db_query.DatabaseQuery", NativeQuery), \
            patch.object(frappe, "has_permission", return_value=True), \
            patch("rayher_crm.permissions.scope.conditions_for_doctype", return_value=crm_scope):
            list_scope = _parent_read_scope("CRM Contact File", "crm%user@example.invalid")
            bound_scope = _parent_read_scope(
                "CRM Contact File", "crm%user@example.invalid", for_bound_query=True,
            )

        self.assertIn(native_share, list_scope)
        self.assertIn(native_match, list_scope)
        self.assertIn("crm%user@example.invalid", list_scope)
        self.assertNotIn(crm_scope, list_scope)
        self.assertIn("shared%%file", bound_scope)
        self.assertIn("Account 100%% Pure", bound_scope)
        self.assertIn(crm_scope, bound_scope)
        # PyMySQL performs this interpolation when frappe.db.sql receives values.
        formatted = ("SELECT name FROM `tabFile` WHERE name=%s AND " + bound_scope) % ("'file-id'",)
        self.assertIn("shared%file", formatted)
        self.assertIn("Account 100% Pure", formatted)
        self.assertIn("crm%user@example.invalid", formatted)
        self.assertNotIn("crm%%user@example.invalid", formatted)

    def test_unreferenced_private_blob_is_deleted_with_its_row(self):
        file = self.private_file()
        path = Path(file.get_full_path())
        frappe.delete_doc("File", file.name, ignore_permissions=True)
        self.assertFalse(frappe.db.exists("File", file.name))
        self.assertFalse(path.exists())

    def test_shared_private_blob_survives_deleting_one_of_its_rows(self):
        kept = self.ordinary_private_file()
        other = self.ordinary_private_file()
        # Frappe de-duplicates identical content onto one physical path.
        self.assertEqual(other.file_url, kept.file_url)
        frappe.delete_doc("File", other.name, ignore_permissions=True)
        self.assertFalse(frappe.db.exists("File", other.name))
        self.assertTrue(frappe.db.exists("File", kept.name))
        self.assertEqual(Path(kept.get_full_path()).read_bytes(), self.content)

    def test_canonical_absolute_alias_survives_deleting_one_row(self):
        kept = self.ordinary_private_file(filename="canonical-delete.txt")
        other = self.ordinary_private_file(filename="canonical-delete-alias.txt")
        path = Path(kept.get_full_path())
        self.assertEqual(other.file_url, kept.file_url)
        other.file_url = frappe.utils.get_url().rstrip("/") + other.file_url
        other.db_update()
        other.reload()
        self.assertEqual(Path(other.get_full_path()), path)

        frappe.delete_doc("File", kept.name, ignore_permissions=True)
        self.assertTrue(path.exists())
        self.assertEqual(Path(other.get_full_path()).read_bytes(), self.content)
        frappe.delete_doc("File", other.name, ignore_permissions=True)
        self.assertFalse(path.exists())

    def test_deletion_hook_keeps_body_and_thumbnail_while_a_row_remains(self):
        kept = self.ordinary_private_file()
        other = self.ordinary_private_file()
        self.assertEqual(other.file_url, kept.file_url)
        with patch.object(other, "delete_file_from_filesystem") as unlink:
            lifecycle.delete_file_content(other)
            lifecycle.delete_file_content(other, only_thumbnail=True)
        unlink.assert_not_called()
        self.assertEqual(Path(kept.get_full_path()).read_bytes(), self.content)

    def test_same_display_name_never_overwrites_different_content(self):
        first = self.private_file(filename="same-name.txt")
        second = self.private_file(filename="same-name.txt", content=b"Changed " + self.content)
        self.assertNotEqual(first.file_url, second.file_url)
        self.assertEqual(Path(first.get_full_path()).read_bytes(), self.content)
        self.assertEqual(Path(second.get_full_path()).read_bytes(), b"Changed " + self.content)

    def test_orphan_cleanup_removes_a_rolled_back_upload_blob(self):
        from rayher_crm.services import demo_reports

        frappe.db.savepoint("ordinary_upload")
        file = self.private_file(filename="ordinary-orphan.txt")
        path = Path(file.get_full_path())
        frappe.db.rollback(save_point="ordinary_upload")
        demo_reports._remove_orphaned_files([(str(path), file.file_url, file.content_hash)])
        self.assertFalse(path.exists())

    def test_orphan_cleanup_keeps_a_blob_another_row_still_references(self):
        from rayher_crm.services import demo_reports

        kept = self.private_file()
        path = Path(kept.get_full_path())
        demo_reports._remove_orphaned_files([(str(path), kept.file_url, kept.content_hash)])
        self.assertEqual(path.read_bytes(), self.content)

    def test_the_deletion_hook_is_wired_to_this_module(self):
        # Everything below goes through `frappe.delete_doc`; without this the
        # suite would still pass on stock Frappe behaviour alone.
        self.assertEqual(
            frappe.get_hooks("delete_file_data_content"),
            ["rayher_crm.services.private_file_lifecycle.delete_file_content"],
        )
        self.assertEqual(
            frappe.get_hooks("doc_events").get("File", {}).get("before_insert"),
            ["rayher_crm.services.private_file_lifecycle.protect_private_upload"],
        )

    def test_delete_keeps_bytes_for_a_reference_committed_after_our_snapshot(self):
        """The case stock Frappe gets wrong.

        Frappe's own `_delete_file_on_disk` looks for sibling rows with this
        connection, so a reference committed by another session after our
        REPEATABLE READ snapshot opened is invisible to it and the bytes go. Our
        hook re-reads those candidates with a current read, so they survive.
        """
        kept = self.private_file()
        frappe.db.commit()
        self.committed.append(kept.name)
        path = Path(kept.get_full_path())
        template = frappe.db.sql("SELECT * FROM tabFile WHERE name=%s", kept.name, as_dict=True)[0]
        added_id = uuid4().hex[:10]
        template.update(name=added_id)
        connection = frappe.db._get_connection()
        try:
            with connection.cursor() as cursor:
                columns = ", ".join("`" + field + "`" for field in template)
                placeholders = ", ".join(["%s"] * len(template))
                cursor.execute(f"INSERT INTO tabFile ({columns}) VALUES ({placeholders})", tuple(template.values()))
            connection.commit()
            # Our own REPEATABLE READ snapshot predates that insert.
            self.assertFalse(frappe.db.exists("File", added_id))
            frappe.delete_doc("File", kept.name, ignore_permissions=True)
            self.assertFalse(frappe.db.exists("File", kept.name))
            self.assertEqual(path.read_bytes(), self.content)
        finally:
            frappe.db.rollback()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM tabFile WHERE name=%s", (added_id,))
            connection.commit()
            connection.close()

    def test_rolled_back_upload_blob_is_discarded_when_nothing_references_it(self):
        frappe.db.savepoint("lone_upload")
        orphan = self.private_file(content=b"Orphan " + self.content)
        path = Path(orphan.get_full_path())
        frappe.db.rollback(save_point="lone_upload")
        self.assertFalse(frappe.db.exists("File", orphan.name))
        lifecycle.discard_rolled_back_blob(str(path), orphan.file_url, orphan.content_hash)
        self.assertFalse(path.exists())

    def test_rolled_back_duplicate_never_takes_the_live_row_bytes(self):
        kept = self.ordinary_private_file()
        frappe.db.savepoint("second_upload")
        duplicate = self.ordinary_private_file()
        # De-duplication is the whole point: both rows resolve to one path, so a
        # naive unlink of the rolled-back upload would destroy `kept`.
        self.assertEqual(duplicate.file_url, kept.file_url)
        frappe.db.rollback(save_point="second_upload")
        lifecycle.discard_rolled_back_blob(
            duplicate.get_full_path(), duplicate.file_url, duplicate.content_hash
        )
        self.assertEqual(Path(kept.get_full_path()).read_bytes(), self.content)

    def test_equal_service_uploads_use_independent_urls_and_delete_independently(self):
        first = self.private_file(filename="first-service.txt")
        second = self.private_file(filename="second-service.txt")
        first_path = Path(first.get_full_path())
        second_path = Path(second.get_full_path())
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertNotEqual(first.file_url, second.file_url)
        self.assertEqual(first_path.read_bytes(), self.content)
        self.assertEqual(second_path.read_bytes(), self.content)

        frappe.delete_doc("File", second.name, ignore_permissions=True)
        self.assertFalse(second_path.exists())
        self.assertEqual(first_path.read_bytes(), self.content)

    def test_rolled_back_equal_service_upload_only_removes_its_own_blob(self):
        kept = self.private_file(filename="kept-service.txt")
        kept_path = Path(kept.get_full_path())
        frappe.db.savepoint("isolated_service_upload")
        duplicate = self.private_file(filename="rolled-back-service.txt")
        duplicate_path = Path(duplicate.get_full_path())
        self.assertNotEqual(duplicate.file_url, kept.file_url)
        frappe.db.rollback(save_point="isolated_service_upload")
        lifecycle.discard_rolled_back_blob(
            str(duplicate_path), duplicate.file_url, duplicate.content_hash,
        )
        self.assertFalse(duplicate_path.exists())
        self.assertEqual(kept_path.read_bytes(), self.content)

    def test_service_upload_splits_an_ordinary_absolute_local_url(self):
        content = b"ordinary-absolute-before-service-" + self.content
        ordinary = self.ordinary_private_file(
            filename="ordinary-absolute.txt", content=content,
        )
        ordinary.file_url = frappe.utils.get_url() + ordinary.file_url
        ordinary.db_update()
        ordinary.reload()
        self.assertEqual(Path(ordinary.get_full_path()).read_bytes(), content)

        managed = self.private_file(filename="managed-after-absolute.txt", content=content)
        self.assertEqual(ordinary.content_hash, managed.content_hash)
        self.assertNotEqual(ordinary.file_url, managed.file_url)
        self.assertEqual(Path(ordinary.get_full_path()).read_bytes(), content)
        self.assertEqual(Path(managed.get_full_path()).read_bytes(), content)

    def test_ordinary_upload_splits_a_preexisting_managed_blob(self):
        content = b"managed-before-ordinary-" + self.content
        managed = self.private_file(filename="managed-first.txt", content=content)
        ordinary = self.ordinary_private_file(
            filename="ordinary-after-managed.txt", content=content,
        )
        self.assertEqual(ordinary.content_hash, managed.content_hash)
        self.assertNotEqual(ordinary.file_url, managed.file_url)
        self.assertEqual(Path(ordinary.get_full_path()).read_bytes(), content)
        self.assertEqual(Path(managed.get_full_path()).read_bytes(), content)

    def test_external_remote_file_with_a_hash_keeps_ordinary_frappe_behavior(self):
        remote = frappe.get_doc({
            "doctype": "File", "file_name": "external-manual.pdf",
            "file_url": "https://files.example.invalid/external-manual.pdf",
            "is_private": 1, "content_hash": "a" * 32,
        }).insert(ignore_permissions=True)
        self.assertTrue(remote.is_remote_file)
        self.assertEqual(
            remote.file_url,
            "https://files.example.invalid/external-manual.pdf",
        )

    def test_same_site_link_outside_file_storage_stays_an_ordinary_remote_file(self):
        # Core keeps a same-site absolute URL as a remote link unless it names
        # "/files/" storage (File.validate_remote_file and get_full_path).
        site_url = frappe.utils.get_url().rstrip("/")
        for path in ("/assets/frappe/images/frappe-framework-logo.svg", "/app/customer"):
            with self.subTest(path=path):
                remote = frappe.get_doc({
                    "doctype": "File", "file_name": "same-site-link-" + uuid4().hex[:10],
                    "file_url": site_url + path, "is_private": 0,
                }).insert(ignore_permissions=True)
                self.assertTrue(remote.is_remote_file)
                self.assertEqual(remote.file_url, site_url + path)

    def test_folder_flag_cannot_restore_the_uploader_shortcut(self):
        from frappe.client import set_value

        user = f"crm-managed-folder-{uuid4().hex[:10]}@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": user, "first_name": "Managed Folder Flag",
            "enabled": 1, "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
        frappe.set_user(user)
        managed = lifecycle.save_private_file(
            "rfq-folder.txt", b"RFQ-FOLDER-" + self.content,
            "CRM RFQ Version", "missing-version-" + uuid4().hex[:10],
        )
        managed_path = Path(managed.get_full_path())
        self.assertEqual(frappe.db.get_value("File", managed.name, "owner"), user)
        with self.assertRaises(frappe.PermissionError):
            set_value("File", managed.name, "is_folder", 1)
        self.assertEqual(frappe.db.get_value("File", managed.name, "is_folder"), 0)

        # Even a folder flag already stored on the row keeps the owner out.
        frappe.db.set_value("File", managed.name, "is_folder", 1, update_modified=False)
        stored = frappe.get_doc("File", managed.name)
        for permission_type in ("read", "write", "delete"):
            self.assertFalse(stored.has_permission(permission_type, user=user))
        self.assertFalse(stored.is_downloadable())
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("File", managed.name)
        self.assertTrue(managed_path.exists())

    def test_maximum_logical_name_keeps_its_extension_and_bounded_storage_name(self):
        logical_name = ("x" * 136) + ".txt"
        self.assertEqual(len(logical_name), 140)
        managed = self.private_file(
            filename=logical_name, content=b"maximum-name-" + self.content,
        )
        storage_name = managed.file_url.rsplit("/", 1)[-1]
        self.assertEqual(managed.file_name, logical_name)
        self.assertLessEqual(len(storage_name), 140)
        self.assertTrue(storage_name.endswith(".txt"))
        self.assertNotEqual(storage_name, logical_name)

    def test_discard_without_url_or_hash_leaves_the_blob_alone(self):
        kept = self.private_file()
        path = Path(kept.get_full_path())
        lifecycle.discard_rolled_back_blob(str(path), None, None)
        lifecycle.discard_rolled_back_blob(str(path), kept.file_url, None)
        self.assertEqual(path.read_bytes(), self.content)

    def test_private_file_privacy_change_still_works(self):
        other = frappe.get_doc({
            "doctype": "File",
            "file_name": "unrelated-privacy-" + uuid4().hex[:10] + ".txt",
            "content": self.content,
            "is_private": 1,
        }).insert(ignore_permissions=True)
        path = Path(other.get_full_path())
        frappe.db.commit()
        self.committed.append(other.name)
        other = frappe.get_doc("File", other.name)
        try:
            other.is_private = 0
            other.save()
            self.assertEqual(Path(other.get_full_path()).read_bytes(), self.content)
            self.assertEqual(other.is_private, 0)
        finally:
            frappe.db.rollback()
        self.assertEqual(path.read_bytes(), self.content)

    def test_privacy_move_rejects_unresolved_persisted_source_without_touching_blobs(self):
        from rayher_crm.overrides.file import ManagedFile

        managed = self.private_file(content=b"privacy-source-policy-" + self.content)
        managed_url = managed.file_url
        managed_path = Path(managed.get_full_path())
        managed_content = managed_path.read_bytes()
        frappe.db.commit()
        self.committed.append(managed.name)

        # This is a storage-policy unit test: an unresolved ordinary metadata
        # row must fail before any path is selected, even if the write hook is
        # absent. No body or managed path is supplied as the incoming reference.
        ordinary = ManagedFile({
            "doctype": "File", "name": "unresolved-source-" + uuid4().hex[:10],
            "file_name": "unresolved-display.txt", "file_url": "", "is_private": 0,
            "is_folder": 0,
        })
        for is_folder in (0, 1):
            stored = frappe._dict(
                name=ordinary.name, file_name="unresolved-display.txt", file_url="",
                is_private=1, is_folder=is_folder, content_hash=None,
            )
            with self.subTest(is_folder=is_folder), \
                patch("rayher_crm.services.managed_file_access.protect_file_write"), \
                patch.object(frappe.db, "sql", return_value=[stored]), \
                patch("rayher_crm.overrides.file.shutil.move") as move, \
                patch.object(type(frappe.db.after_rollback), "add") as register_rollback:
                with self.assertRaises(frappe.ValidationError):
                    ordinary.handle_is_private_changed()
                move.assert_not_called()
                register_rollback.assert_not_called()
            self.assertEqual(managed_path.read_bytes(), managed_content)
        frappe.db.rollback()
        managed.reload()
        self.assertEqual((managed.is_private, managed.file_url), (1, managed_url))
        self.assertEqual(managed_path.read_bytes(), managed_content)

    def test_privacy_write_rejects_unresolved_source_before_core_folder_validation(self):
        from rayher_crm.services.managed_file_access import protect_file_write

        ordinary = frappe.get_doc({
            "doctype": "File", "name": "unresolved-policy-" + uuid4().hex[:10],
            "file_name": "unresolved-display.txt", "file_url": "", "is_private": 0,
            "is_folder": 0,
        })
        for is_folder in (0, 1):
            stored = frappe._dict(
                name=ordinary.name, file_name="unresolved-display.txt", file_url="",
                is_private=1, is_folder=is_folder, content_hash=None,
            )
            with self.subTest(is_folder=is_folder), \
                patch.object(ordinary, "is_new", return_value=False), \
                patch.object(frappe.db, "get_value", return_value=stored), \
                patch("rayher_crm.services.managed_file_access._managed_file_kinds") as classify:
                with self.assertRaises(frappe.ValidationError):
                    protect_file_write(ordinary)
                classify.assert_not_called()

    def test_native_optimizer_preserves_ordinary_deduplicated_uploads(self):
        from io import BytesIO
        from PIL import Image

        image = BytesIO()
        Image.new("RGB", (8, 8), tuple(uuid4().bytes[:3])).save(image, format="PNG")
        original = image.getvalue()
        optimized = BytesIO()
        Image.open(BytesIO(original)).save(optimized, format="PNG", optimize=True)
        self.assertNotEqual(original, optimized.getvalue())
        source = self.ordinary_private_file("original-" + uuid4().hex[:10] + ".png", original)
        duplicate = self.ordinary_private_file("duplicate-" + uuid4().hex[:10] + ".png", original)
        self.assertEqual(source.file_url, duplicate.file_url)
        self.assertNotEqual(source.file_name, duplicate.file_name)
        duplicate = frappe.get_doc("File", duplicate.name)
        target_url = "/private/files/" + duplicate.file_name

        with patch("frappe.core.doctype.file.file.optimize_image", return_value=optimized.getvalue()):
            duplicate.optimize_file()

        duplicate.reload()
        self.assertEqual(duplicate.file_url, target_url)
        self.assertEqual(duplicate.get_content(), optimized.getvalue())
        source.reload()
        self.assertNotEqual(source.file_url, duplicate.file_url)
        self.assertEqual(source.get_content(), original)

    def test_native_optimizer_locks_content_before_rows_and_rechecks_snapshot(self):
        from frappe.core.doctype.file.file import File
        from rayher_crm.overrides.file import ManagedFile

        ordinary = ManagedFile({
            "doctype": "File", "name": "optimizer-lock-contract",
            "file_name": "ordinary.png", "file_url": "/private/files/ordinary.png",
            "is_private": 1, "is_folder": 0,
        })
        snapshot = frappe._dict(
            name=ordinary.name, file_url=ordinary.file_url, file_name=ordinary.file_name,
            is_private=1, is_folder=0, content_hash="ordinary-content",
        )
        for changed in (False, True):
            calls = []
            locked = frappe._dict(snapshot)
            if changed:
                locked.content_hash = "updated-content"

            def lock_content(digest):
                calls.append(("content", digest))

            def read_locked(*args, **kwargs):
                if "FOR UPDATE" not in args[0]:
                    return []  # Framework exception translation can read metadata.
                calls.append(("siblings" if "file_url_index" in args[0] else "row", "FOR UPDATE NOWAIT" in args[0]))
                return [locked]

            with self.subTest(changed=changed), \
                patch("rayher_crm.overrides.file._managed_file_kinds", return_value=set()), \
                patch.object(frappe.db, "get_value", return_value=snapshot), \
                patch("rayher_crm.services.private_file_lifecycle._lock_content", side_effect=lock_content), \
                patch.object(frappe.db, "sql", side_effect=read_locked), \
                patch("rayher_crm.services.managed_file_access._protected_blob", return_value=False) as classify, \
                patch.object(File, "optimize_file", return_value="optimized") as optimize:
                if changed:
                    with self.assertRaises(frappe.ValidationError):
                        ordinary.optimize_file()
                    frappe.clear_last_message()
                    classify.assert_not_called()
                    optimize.assert_not_called()
                else:
                    self.assertEqual(ordinary.optimize_file(), "optimized")
                    optimize.assert_called_once()
                self.assertEqual(calls, [
                    ("content", "ordinary-content"), ("siblings", True), ("row", True),
                ])

    def test_native_optimizer_reports_prewrite_lock_contention_as_retry(self):
        from frappe.core.doctype.file.file import File
        from rayher_crm.overrides.file import ManagedFile

        ordinary = ManagedFile({"doctype": "File", "name": "ordinary-lock-retry"})
        for error in (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
            with self.subTest(error=error.__name__), \
                patch.object(ManagedFile, "_validate_native_optimization", side_effect=error), \
                patch.object(File, "optimize_file") as optimize:
                with self.assertRaisesRegex(frappe.ValidationError, "Please retry optimization"):
                    ordinary.optimize_file()
                frappe.clear_last_message()
                optimize.assert_not_called()

        # A core-stage error is not relabeled as a pre-write retry: filesystem
        # work may already have happened after successful validation.
        with patch.object(ManagedFile, "_validate_native_optimization"), \
            patch.object(File, "optimize_file", side_effect=frappe.QueryDeadlockError):
            with self.assertRaises(frappe.QueryDeadlockError):
                ordinary.optimize_file()

    def test_native_optimizer_requires_its_verified_own_overwrite_path(self):
        from frappe.core.doctype.file.file import File
        from rayher_crm.overrides.file import ManagedFile

        ordinary = ManagedFile({
            "doctype": "File", "name": "optimizer-policy-" + uuid4().hex[:10],
            "file_name": "ordinary-image.png", "file_url": "/private/files/ordinary-image.png",
            "is_private": 1, "is_folder": 0,
        })
        stored = frappe._dict(
            name=ordinary.name, file_url=ordinary.file_url, file_name=ordinary.file_name,
            is_private=1, is_folder=0, content_hash=None,
        )
        with patch("rayher_crm.overrides.file._managed_file_kinds", return_value=set()), \
            patch.object(frappe.db, "get_value", return_value=stored), \
            patch("rayher_crm.services.private_file_lifecycle._lock_content"), \
            patch.object(frappe.db, "sql", return_value=[stored]), \
            patch("rayher_crm.services.managed_file_access._protected_blob", return_value=False), \
            patch.object(File, "optimize_file", return_value="ordinary-optimized") as optimize:
            self.assertEqual(ordinary.optimize_file(), "ordinary-optimized")
            optimize.assert_called_once()
            optimize.reset_mock()
            ordinary.file_name = "renamed-display.png"
            with self.assertRaises(frappe.PermissionError):
                ordinary.optimize_file()
            optimize.assert_not_called()

        ordinary.file_name = "ordinary-image.png"
        with patch("rayher_crm.overrides.file._managed_file_kinds", return_value=set()), \
            patch.object(frappe.db, "get_value", return_value=stored), \
            patch("rayher_crm.services.private_file_lifecycle._lock_content"), \
            patch.object(frappe.db, "sql", return_value=[stored]), \
            patch("rayher_crm.services.managed_file_access._protected_blob", return_value=True), \
            patch.object(File, "optimize_file") as optimize:
            with self.assertRaises(frappe.PermissionError):
                ordinary.optimize_file()
            optimize.assert_not_called()

    def test_native_optimizer_never_delegates_based_on_incoming_folder_or_remote_state(self):
        from frappe.core.doctype.file.file import File
        from rayher_crm.overrides.file import ManagedFile

        local_url = "/private/files/ordinary-image.png"
        remote_url = "https://example.invalid/ordinary-image.png"
        api_url = "/api/method/ordinary.image"
        for label, stored_url, incoming_url, incoming_folder in (
            ("incoming-folder", local_url, local_url, 1),
            ("incoming-remote", local_url, remote_url, 0),
            ("persisted-remote", remote_url, remote_url, 0),
            ("persisted-api", api_url, api_url, 0),
        ):
            ordinary = ManagedFile({
                "doctype": "File", "name": "optimizer-flags-" + uuid4().hex[:10],
                "file_name": "ordinary-image.png", "file_url": incoming_url,
                "is_private": 1, "is_folder": incoming_folder,
            })
            stored = frappe._dict(
                name=ordinary.name, file_url=stored_url, file_name=ordinary.file_name,
                is_private=1, is_folder=0, content_hash=None,
            )
            with self.subTest(case=label), \
                patch("rayher_crm.overrides.file._managed_file_kinds", return_value=set()), \
                patch.object(frappe.db, "get_value", return_value=stored), \
                patch("rayher_crm.services.private_file_lifecycle._lock_content"), \
                patch.object(frappe.db, "sql", return_value=[stored]), \
                patch("rayher_crm.services.managed_file_access._protected_blob", return_value=False), \
                patch.object(File, "optimize_file") as optimize:
                with self.assertRaises(frappe.PermissionError):
                    ordinary.optimize_file()
                optimize.assert_not_called()

    def test_unresolvable_local_reference_is_denied_before_permission_lookup(self):
        from rayher_crm.services.managed_file_access import _managed_file_kinds

        for is_folder in (0, 1):
            ordinary = frappe._dict(
                name="unresolved-reference", file_name="unresolved-display.txt",
                file_url="/private/files/unresolved-storage.txt", is_private=1, is_folder=is_folder,
            )
            # Model a canonicalizer failure directly, without constructing an
            # alternate path or reading any body through an invalid reference.
            with self.subTest(is_folder=is_folder), \
                patch("rayher_crm.services.managed_file_access.canonical_local_reference", side_effect=ValueError("unresolved storage")), \
                patch.object(frappe.db, "sql") as lookup:
                with self.assertRaises(frappe.PermissionError):
                    _managed_file_kinds(ordinary)
                lookup.assert_not_called()

    def test_ordinary_remote_api_and_folder_classification_remains_supported(self):
        from rayher_crm.services.managed_file_access import _managed_file_kinds

        for file_url in ("https://example.invalid/ordinary.png", "/api/method/ordinary.delivery"):
            ordinary = frappe._dict(
                name="ordinary-reference", file_url=file_url, file_name="ordinary.png",
                is_private=0, is_folder=0,
            )
            with self.subTest(file_url=file_url), patch.object(frappe.db, "sql", return_value=[]):
                self.assertEqual(_managed_file_kinds(ordinary), set())
        folder = frappe._dict(name="Home/Attachments", file_name="Attachments", file_url=None, is_folder=1)
        with patch.object(frappe.db, "sql", return_value=[]), \
            patch("rayher_crm.services.managed_file_access.canonical_local_reference") as canonicalize:
            self.assertEqual(_managed_file_kinds(folder), set())
            canonicalize.assert_not_called()

    def test_every_file_inventory_blocks_unresolvable_local_rows_before_mutation(self):
        from importlib import import_module

        unresolved = frappe._dict(
            name="unresolved-inventory", file_url="/private/files/unresolved-storage.txt",
            file_name="unresolved-display.txt", is_private=1, is_folder=0,
            attached_to_doctype=None, attached_to_name=None,
            custom_crm_service_upload=0, canonical_reference=None, reference_error=True,
        )
        snapshot = {"files": {unresolved.name: unresolved}, "by_reference": {}}
        problem = {"file": unresolved.name, "reason": "invalid-local-file-reference"}
        for patch_name in (
            "protect_contact_files", "protect_visit_files", "protect_controlled_document_files",
            "protect_service_managed_files",
        ):
            migration = import_module("rayher_crm.patches.v1_0." + patch_name)
            with self.subTest(patch=patch_name), \
                patch.object(migration, "canonical_local_file_inventory", return_value=snapshot), \
                patch.object(frappe, "get_all", return_value=[]), \
                patch.object(frappe.db, "set_value") as update, \
                patch.object(frappe.db, "delete") as delete:
                self.assertIn(problem, migration.inventory()["problems"])
                with self.assertRaises(RuntimeError):
                    migration.execute()
                update.assert_not_called()
                delete.assert_not_called()

    def test_equal_managed_hash_does_not_block_ordinary_privacy_change(self):
        content = b"independent-managed-privacy-" + self.content
        managed = self.private_file(filename="managed-privacy.txt", content=content)
        ordinary = self.ordinary_private_file(
            filename="ordinary-privacy.txt", content=content,
        )
        managed_url = managed.file_url
        managed_path = Path(managed.get_full_path())
        ordinary_private_path = Path(ordinary.get_full_path())
        self.assertNotEqual(managed.file_url, ordinary.file_url)
        frappe.db.commit()
        self.committed.extend((managed.name, ordinary.name))

        ordinary = frappe.get_doc("File", ordinary.name)
        ordinary.is_private = 0
        ordinary.save(ignore_permissions=True)
        ordinary_public_path = Path(ordinary.get_full_path())
        managed.reload()
        self.assertEqual(ordinary.is_private, 0)
        self.assertEqual(ordinary_public_path.read_bytes(), content)
        self.assertFalse(ordinary_private_path.exists())
        self.assertEqual((managed.is_private, managed.file_url), (1, managed_url))
        self.assertEqual(managed_path.read_bytes(), content)

        frappe.db.rollback()
        ordinary.reload()
        managed.reload()
        self.assertEqual(ordinary.is_private, 1)
        self.assertEqual(Path(ordinary.get_full_path()), ordinary_private_path)
        self.assertEqual(ordinary_private_path.read_bytes(), content)
        self.assertEqual((managed.is_private, managed.file_url), (1, managed_url))
        self.assertEqual(Path(managed.get_full_path()), managed_path)
        self.assertEqual(managed_path.read_bytes(), content)

    def test_privacy_change_moves_canonical_siblings_not_equal_hash_paths(self):
        content = b"canonical-privacy-siblings-" + self.content
        primary = self.ordinary_private_file(filename="canonical-siblings.txt", content=content)
        raw_sibling = self.ordinary_private_file(filename="raw-sibling.txt", content=content)
        absolute_sibling = self.ordinary_private_file(filename="absolute-sibling.txt", content=content)
        self.assertEqual(
            {primary.file_url, raw_sibling.file_url, absolute_sibling.file_url},
            {primary.file_url},
        )
        absolute_url = frappe.utils.get_url().rstrip("/") + primary.file_url
        absolute_sibling.file_url = absolute_url
        absolute_sibling.db_update()

        independent = self.private_file(filename="independent-same-hash.txt", content=content)
        frappe.db.set_value(
            "File", independent.name,
            {"custom_crm_service_upload": 0, "attached_to_doctype": None, "attached_to_name": None},
            update_modified=False,
        )
        independent.reload()
        self.assertNotEqual(independent.file_url, primary.file_url)
        private_path = Path(primary.get_full_path())
        independent_path = Path(independent.get_full_path())
        original_urls = {
            primary.name: primary.file_url,
            raw_sibling.name: raw_sibling.file_url,
            absolute_sibling.name: absolute_url,
            independent.name: independent.file_url,
        }
        frappe.db.commit()
        self.committed.extend((
            primary.name, raw_sibling.name, absolute_sibling.name, independent.name,
        ))

        primary = frappe.get_doc("File", primary.name)
        primary.is_private = 0
        primary.save(ignore_permissions=True)
        expected_public_url = "/files/" + private_path.name
        for name in (primary.name, raw_sibling.name, absolute_sibling.name):
            moved = frappe.get_doc("File", name)
            self.assertEqual((moved.is_private, moved.file_url), (0, expected_public_url))
        independent.reload()
        self.assertEqual((independent.is_private, independent.file_url), (1, original_urls[independent.name]))
        self.assertEqual(independent_path.read_bytes(), content)
        self.assertFalse(private_path.exists())
        self.assertEqual(Path(primary.get_full_path()).read_bytes(), content)

        frappe.db.rollback()
        for name, expected_url in original_urls.items():
            restored = frappe.get_doc("File", name)
            self.assertEqual((restored.is_private, restored.file_url), (1, expected_url))
        self.assertEqual(private_path.read_bytes(), content)
        self.assertEqual(independent_path.read_bytes(), content)

    def test_privacy_change_target_collision_keeps_source_and_rows_unchanged(self):
        private = self.ordinary_private_file(
            filename="privacy-collision.txt", content=b"private-" + self.content,
        )
        public = frappe.get_doc({
            "doctype": "File", "file_name": "privacy-collision.txt",
            "content": b"public-" + self.content, "is_private": 0,
        }).insert(ignore_permissions=True)
        private_path = Path(private.get_full_path())
        public_path = Path(public.get_full_path())
        original_url = private.file_url
        private.is_private = 0
        with self.assertRaises(FileExistsError):
            private.save(ignore_permissions=True)
        self.assertEqual(private_path.read_bytes(), b"private-" + self.content)
        self.assertEqual(public_path.read_bytes(), b"public-" + self.content)
        stored = frappe.db.get_value(
            "File", private.name, ["is_private", "file_url"], as_dict=True,
        )
        self.assertEqual((stored.is_private, stored.file_url), (1, original_url))

    def test_repeated_privacy_changes_restore_original_path_on_rollback(self):
        ordinary = self.ordinary_private_file(
            filename="privacy-twice.txt", content=b"privacy-twice-" + self.content,
        )
        private_path = Path(ordinary.get_full_path())
        frappe.db.commit()
        self.committed.append(ordinary.name)

        ordinary = frappe.get_doc("File", ordinary.name)
        ordinary.is_private = 0
        ordinary.save(ignore_permissions=True)
        public_path = Path(ordinary.get_full_path())
        ordinary = frappe.get_doc("File", ordinary.name)
        ordinary.is_private = 1
        ordinary.save(ignore_permissions=True)
        self.assertTrue(private_path.exists())
        self.assertFalse(public_path.exists())

        ordinary = frappe.get_doc("File", ordinary.name)
        ordinary.is_private = 0
        ordinary.save(ignore_permissions=True)
        self.assertFalse(private_path.exists())
        self.assertTrue(public_path.exists())
        frappe.db.rollback()

        ordinary.reload()
        self.assertEqual((ordinary.is_private, Path(ordinary.get_full_path())), (1, private_path))
        self.assertTrue(private_path.exists())
        self.assertFalse(public_path.exists())

    def test_service_target_file_denies_native_owner_share_alias_and_delete(self):
        user = f"crm-managed-file-owner-{uuid4().hex[:10]}@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": user, "first_name": "Managed File Owner",
            "enabled": 1, "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
        frappe.set_user(user)
        managed = lifecycle.save_private_file(
            "rfq-secret.txt", b"RFQ-SECRET-" + self.content,
            "CRM RFQ Version", "missing-version-" + uuid4().hex[:10],
        )
        managed_path = Path(managed.get_full_path())

        # Model a pre-release ordinary alias that resolves to the same private
        # blob. Runtime classification must follow the canonical URL back to the
        # service-owned row even when this alias has no provenance of its own.
        frappe.set_user("Administrator")
        alias = frappe.get_doc({
            "doctype": "File", "file_name": "legacy-rfq-alias.txt",
            "file_url": managed.file_url, "is_private": 1,
            "content_hash": managed.content_hash, "owner": user,
        })
        alias.name = frappe.generate_hash(length=10)
        alias.db_insert()
        from rayher_crm.patches.v1_0.protect_service_managed_files import inventory
        inventory_problems = {
            (row["file"], row["reason"]) for row in inventory()["problems"]
        }
        self.assertIn((managed.name, "missing-service-parent"), inventory_problems)
        self.assertIn((alias.name, "shared-url-outside-service-file"), inventory_problems)

        for file_name in (managed.name, alias.name):
            with self.subTest(file=file_name), self.assertRaises(frappe.PermissionError):
                add_share("File", file_name, user=user, read=1, write=1)
        legacy_share = frappe.get_doc({
            "doctype": "DocShare", "user": user, "share_doctype": "File",
            "share_name": managed.name, "read": 1, "write": 1,
        })
        legacy_share.name = frappe.generate_hash(length=10)
        legacy_share.db_insert()
        from rayher_crm.patches.v1_0.protect_service_managed_files import execute
        with self.assertRaisesRegex(RuntimeError, "storage review"):
            execute()
        self.assertEqual(frappe.db.get_value("File", managed.name, "owner"), user)
        self.assertTrue(frappe.db.exists("DocShare", legacy_share.name))

        frappe.set_user(user)
        try:
            self.assertFalse(frappe.get_list(
                "File", filters={"name": ("in", (managed.name, alias.name))}, pluck="name",
            ))
            for file_name in (managed.name, alias.name):
                file_doc = frappe.get_doc("File", file_name)
                with self.subTest(file=file_name):
                    for permission_type in ("read", "write", "delete"):
                        self.assertFalse(file_doc.has_permission(permission_type, user=user))
                    self.assertFalse(file_doc.is_downloadable())
                    with self.assertRaises(frappe.PermissionError):
                        file_doc.get_content()
                    file_doc.flags.crm_restricted_read_token = object()
                    with self.assertRaises(frappe.PermissionError):
                        file_doc.get_content()
                    with self.assertRaises(frappe.PermissionError):
                        frappe.delete_doc("File", file_name)
            self.assertTrue(managed_path.exists())

            ordinary = frappe.get_doc({
                "doctype": "File", "file_name": "ordinary-owner.txt",
                "content": b"ORDINARY-" + self.content, "is_private": 1,
            }).insert(ignore_permissions=True)
            ordinary_path = Path(ordinary.get_full_path())
            self.assertTrue(ordinary.has_permission("delete", user=user))
            frappe.delete_doc("File", ordinary.name)
            self.assertFalse(ordinary_path.exists())
        finally:
            frappe.set_user("Administrator")
            for file_name in (alias.name, managed.name):
                if frappe.db.exists("File", file_name):
                    frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)

    def test_clean_service_file_migration_reowners_and_removes_legacy_share(self):
        user = f"crm-managed-migration-{uuid4().hex[:10]}@example.invalid"
        frappe.get_doc({
            "doctype": "User", "email": user, "first_name": "Managed Migration",
            "enabled": 1, "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
        parent = frappe.get_doc({
            "doctype": "CRM Notification Event", "actor": "Administrator",
            "category": "Document", "recipient_user": "Administrator",
            "title": "Managed File Migration", "message": "Migration parent",
            "route": "/documents", "created_at": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True)
        frappe.set_user(user)
        managed = lifecycle.save_private_file(
            "managed-migration.txt", b"MANAGED-MIGRATION-" + self.content,
            parent.doctype, parent.name,
        )
        frappe.set_user("Administrator")
        share = frappe.get_doc({
            "doctype": "DocShare", "user": user, "share_doctype": "File",
            "share_name": managed.name, "read": 1, "write": 1,
        })
        share.name = frappe.generate_hash(length=10)
        share.db_insert()

        from rayher_crm.patches.v1_0.protect_service_managed_files import execute, inventory
        self.assertEqual(inventory(), {"files": [managed.name], "problems": []})
        execute()
        self.assertEqual(frappe.db.get_value("File", managed.name, "owner"), "Administrator")
        self.assertFalse(frappe.db.exists("DocShare", share.name))
        frappe.delete_doc("File", managed.name, ignore_permissions=True, force=True)
