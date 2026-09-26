"""Shared-blob reference counting for private attachments."""
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import frappe
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

    def test_unreferenced_private_blob_is_deleted_with_its_row(self):
        file = self.private_file()
        path = Path(file.get_full_path())
        frappe.delete_doc("File", file.name, ignore_permissions=True)
        self.assertFalse(frappe.db.exists("File", file.name))
        self.assertFalse(path.exists())

    def test_shared_private_blob_survives_deleting_one_of_its_rows(self):
        kept = self.private_file()
        other = self.private_file()
        # Frappe de-duplicates identical content onto one physical path.
        self.assertEqual(other.file_url, kept.file_url)
        frappe.delete_doc("File", other.name, ignore_permissions=True)
        self.assertFalse(frappe.db.exists("File", other.name))
        self.assertTrue(frappe.db.exists("File", kept.name))
        self.assertEqual(Path(kept.get_full_path()).read_bytes(), self.content)

    def test_deletion_hook_keeps_body_and_thumbnail_while_a_row_remains(self):
        kept = self.private_file()
        other = self.private_file()
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
        kept = self.private_file()
        frappe.db.savepoint("second_upload")
        duplicate = self.private_file()
        # De-duplication is the whole point: both rows resolve to one path, so a
        # naive unlink of the rolled-back upload would destroy `kept`.
        self.assertEqual(duplicate.file_url, kept.file_url)
        frappe.db.rollback(save_point="second_upload")
        lifecycle.discard_rolled_back_blob(
            duplicate.get_full_path(), duplicate.file_url, duplicate.content_hash
        )
        self.assertEqual(Path(kept.get_full_path()).read_bytes(), self.content)

    def test_discard_without_url_or_hash_leaves_the_blob_alone(self):
        kept = self.private_file()
        path = Path(kept.get_full_path())
        lifecycle.discard_rolled_back_blob(str(path), None, None)
        lifecycle.discard_rolled_back_blob(str(path), kept.file_url, None)
        self.assertEqual(path.read_bytes(), self.content)

    def test_private_file_privacy_change_still_works(self):
        other = self.private_file(filename="unrelated-privacy-" + uuid4().hex[:10] + ".txt")
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
