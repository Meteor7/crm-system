from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.scope import OPPORTUNITY_CHILD_DOCTYPES
from rayher_crm.services import opportunity_status as service
from rayher_crm.tests.test_opportunity_relations import TestOpportunityRelations


def _delete_committed_opportunity(name):
    # Creating an Opportunity writes stage and probability history; remove those rows too so a
    # committed fixture leaves nothing behind (force alone would skip the link check and leak them).
    for doctype in OPPORTUNITY_CHILD_DOCTYPES:
        frappe.db.delete(doctype, {"opportunity": name})
    frappe.delete_doc("CRM Opportunity", name, ignore_permissions=True, force=True)


class CleanScanner:
    def scan(self, content):
        return True


class TestOpportunityStatus(FrappeTestCase):
    _user = TestOpportunityRelations._user
    _records = TestOpportunityRelations._records
    _action_input = TestOpportunityRelations._action_input

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-status-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-status-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-status-engineer@example.invalid", "CRM Engineer")
        # A fixed suffix names the Customer, so repeated runs collided and Frappe
        # appended "- 1", "- 2" ... Unique per run, and torn down by hand for the
        # one case that has to commit.
        self.account, opportunity, self.contact = self._records(
            self.sales, "StatusFeature" + uuid4().hex[:8]
        )
        self.opportunity_id = opportunity["id"]
        self.site = frappe.db.get_value("CRM Opportunity", self.opportunity_id, "site")

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def discard_committed_fixtures(self):
        """Undo by hand what a commit put beyond the reach of the rollback.

        `FrappeTestCase` leans on one transaction for the whole suite, so a test
        that commits leaks its Customer, Site, Contact, Opportunity, Status rows,
        File rows and audit rows into the site permanently -- every run adding
        another set.
        """
        frappe.set_user("Administrator")
        frappe.db.rollback()
        # `CRM File Access Audit.on_trash` refuses deletion -- the table is
        # append-only by design -- so the rows this test committed come out with
        # raw SQL, scoped to its own Account.
        frappe.db.sql(
            "DELETE FROM `tabCRM File Access Audit` WHERE entity_type = %s AND account = %s",
            ("Status Attachment", self.account["id"]),
        )
        for name in frappe.get_all(
            service.ATTACHMENT_DOCTYPE, filters={"opportunity": self.opportunity_id}, pluck="name"
        ):
            file_id = frappe.db.get_value(service.ATTACHMENT_DOCTYPE, name, "private_file")
            frappe.delete_doc(service.ATTACHMENT_DOCTYPE, name, ignore_permissions=True, force=True)
            if file_id and frappe.db.exists("File", file_id):
                frappe.delete_doc("File", file_id, ignore_permissions=True, force=True)
        for name in frappe.get_all(
            service.DOCTYPE, filters={"opportunity": self.opportunity_id}, pluck="name"
        ):
            frappe.delete_doc(service.DOCTYPE, name, ignore_permissions=True, force=True)
        _delete_committed_opportunity(self.opportunity_id)
        frappe.delete_doc("Contact", self.contact["id"], ignore_permissions=True, force=True)
        if self.site:
            frappe.delete_doc("CRM Site", self.site, ignore_permissions=True, force=True)
        frappe.delete_doc("Customer", self.account["id"], ignore_permissions=True, force=True)
        with patch("frappe.enqueue"):
            frappe.db.commit()

    def upload(self, name="meeting.txt", content=b"Customer requirements confirmed"):
        return {"file_name": name, "mime_type": "text/plain", "content": content}

    def save(self, text="Confirmed\nWaiting for samples", files=None, **values):
        return service.save_record(
            self.opportunity_id, {"text": text, "retainedFileIds": [], **values},
            files or [], CleanScanner(),
        )

    def blob_path(self, attachment_id: str) -> Path:
        file_id = frappe.db.get_value(service.ATTACHMENT_DOCTYPE, attachment_id, "private_file")
        return Path(frappe.get_doc("File", file_id).get_full_path())

    def exif_stripping_on(self):
        """Frappe's own default, forced so the case does not depend on the site's setting."""
        read_setting = frappe.get_system_settings

        def setting(key, *args, **kwargs):
            if key == "strip_exif_metadata_from_uploaded_images":
                return 1
            return read_setting(key, *args, **kwargs)

        return patch("frappe.get_system_settings", side_effect=setting)

    def broken_app_logger(self):
        """The `rayher_crm` file logger cannot be created; every other logger still works."""
        get_logger = frappe.logger

        def logger(module=None, *args, **kwargs):
            if module == "rayher_crm":
                raise RuntimeError("log directory unavailable")
            return get_logger(module, *args, **kwargs)

        return patch("frappe.logger", side_effect=logger)

    def test_round_trip_private_files_edit_and_removed_download(self):
        created = self.save(files=[self.upload(), self.upload("scope.txt", b"Inspection scope")])
        self.assertEqual(len(created["files"]), 2)
        self.assertEqual(service.list_records(self.opportunity_id)[0], created)
        attachment_id = created["files"][0]["id"]
        row = frappe.db.get_value(
            service.ATTACHMENT_DOCTYPE, attachment_id,
            ["status", "opportunity", "private_file", "mime_type", "size_bytes", "uploaded_by", "deleted"],
            as_dict=True,
        )
        self.assertEqual(row.status, created["id"])
        self.assertEqual(row.opportunity, self.opportunity_id)
        self.assertEqual(row.mime_type, "text/plain")
        self.assertEqual(row.size_bytes, len(b"Customer requirements confirmed"))
        self.assertEqual(row.uploaded_by, self.sales)
        self.assertEqual(int(row.deleted), 0)
        self.assertEqual(frappe.db.get_value("File", row.private_file, "is_private"), 1)
        downloaded = service.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertEqual(downloaded["content"], b"Customer requirements confirmed")
        self.assertEqual(downloaded["file_name"], "meeting.txt")
        updated = self.save(
            "Updated", recordId=created["id"], expectedModified=created["modified"],
            retainedFileIds=[attachment_id],
        )
        self.assertEqual([item["id"] for item in updated["files"]], [attachment_id])
        self.assertEqual(len(service.list_records(self.opportunity_id)), 1)
        with self.assertRaises(CrmApiException):
            service.download_file(self.opportunity_id, created["id"], created["files"][1]["id"])

    def test_removing_an_attachment_keeps_its_row_bytes_and_removal_history(self):
        body = b"Removed attachment " + frappe.generate_hash(length=12).encode()
        created = self.save(files=[self.upload(), self.upload("removed-only.txt", body)])
        kept_id, removed_id = [item["id"] for item in created["files"]]
        path = self.blob_path(removed_id)
        file_id = frappe.db.get_value(service.ATTACHMENT_DOCTYPE, removed_id, "private_file")
        with patch("frappe.enqueue") as enqueue:
            updated = self.save(
                "Removed", recordId=created["id"], expectedModified=created["modified"],
                retainedFileIds=[kept_id],
            )
        # Removal is one UPDATE inside the caller's transaction: nothing is queued.
        enqueue.assert_not_called()
        self.assertEqual([item["id"] for item in updated["files"]], [kept_id])
        with self.assertRaises(CrmApiException):
            service.download_file(self.opportunity_id, created["id"], removed_id)
        removed = frappe.db.get_value(
            service.ATTACHMENT_DOCTYPE, removed_id, ["deleted", "deleted_by", "deleted_at"], as_dict=True
        )
        self.assertEqual(int(removed.deleted), 1)
        self.assertEqual(removed.deleted_by, self.sales)
        self.assertTrue(removed.deleted_at)
        # The File row and its bytes are retained. Nothing touches storage.
        self.assertTrue(frappe.db.exists("File", file_id))
        self.assertEqual(path.read_bytes(), body)
        with self.assertRaises(CrmApiException) as reactivated:
            self.save(
                "Reactivate", recordId=created["id"], expectedModified=updated["modified"],
                retainedFileIds=[kept_id, removed_id],
            )
        self.assertEqual(reactivated.exception.code, "VALIDATION_ERROR")
        self.assertEqual(int(frappe.db.get_value(service.ATTACHMENT_DOCTYPE, removed_id, "deleted")), 1)
        self.assertEqual(
            service.download_file(self.opportunity_id, created["id"], kept_id)["content"],
            b"Customer requirements confirmed",
        )

    def test_removing_a_deduplicated_attachment_spares_the_other_record(self):
        shared = b"Shared status attachment " + frappe.generate_hash(length=10).encode()
        first = self.save("First", files=[self.upload("shared.txt", shared)])
        second = self.save("Second", files=[self.upload("shared.txt", shared)])
        first_id, second_id = first["files"][0]["id"], second["files"][0]["id"]
        # Frappe de-duplicates equal bytes onto a single physical path; the test is
        # meaningless unless that actually happened here.
        self.assertEqual(self.blob_path(first_id), self.blob_path(second_id))
        self.save(
            "First without the attachment", recordId=first["id"],
            expectedModified=first["modified"], retainedFileIds=[],
        )
        self.assertEqual(
            service.download_file(self.opportunity_id, second["id"], second_id)["content"], shared
        )
        self.assertTrue(self.blob_path(second_id).exists())

    def test_removal_rollback_restores_the_attachment(self):
        created = self.save(files=[self.upload()])
        attachment_id = created["files"][0]["id"]
        frappe.db.savepoint("status_removal")
        self.save("Removed", recordId=created["id"], expectedModified=created["modified"])
        self.assertEqual(service.list_records(self.opportunity_id)[0]["files"], [])
        frappe.db.rollback(save_point="status_removal")
        self.assertEqual(service.list_records(self.opportunity_id)[0]["files"], created["files"])
        self.assertEqual(
            service.download_file(self.opportunity_id, created["id"], attachment_id)["content"],
            b"Customer requirements confirmed",
        )
        self.assertEqual(int(frappe.db.get_value(service.ATTACHMENT_DOCTYPE, attachment_id, "deleted")), 0)

    def test_scope_and_readonly_writer_rejection(self):
        created = self.save(files=[self.upload()])
        frappe.set_user(self.other_sales)
        operations = (
            lambda: service.list_records(self.opportunity_id),
            lambda: self.save(),
            lambda: service.download_file(self.opportunity_id, created["id"], created["files"][0]["id"]),
        )
        for operation in operations:
            with self.assertRaises(CrmApiException) as denied:
                operation()
            self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            self.save()

    def test_foreign_record_and_file_ids_cannot_be_attached(self):
        created = self.save(files=[self.upload()])
        with self.assertRaises(CrmApiException):
            self.save(retainedFileIds=[created["files"][0]["id"]])
        _, other, _ = self._records(self.sales, "StatusOther")
        with self.assertRaises(CrmApiException) as mismatch:
            service.save_record(other["id"], {
                "text": "wrong", "recordId": created["id"],
                "expectedModified": created["modified"], "retainedFileIds": [],
            }, [])
        self.assertEqual(mismatch.exception.code, "NOT_FOUND")
        with self.assertRaises(CrmApiException):
            service.download_file(other["id"], created["id"], created["files"][0]["id"])
        # An attachment of another Status record on the same Opportunity is also foreign.
        sibling = self.save("Sibling", files=[self.upload("sibling.txt", b"Sibling attachment")])
        with self.assertRaises(CrmApiException):
            service.download_file(self.opportunity_id, created["id"], sibling["files"][0]["id"])
        with self.assertRaises(CrmApiException) as borrowed:
            self.save(
                "Borrow", recordId=created["id"], expectedModified=created["modified"],
                retainedFileIds=[sibling["files"][0]["id"]],
            )
        self.assertEqual(borrowed.exception.code, "VALIDATION_ERROR")

    def test_conflict_does_not_overwrite_newer_text_or_files(self):
        created = self.save()
        updated = self.save("Newer", recordId=created["id"], expectedModified=created["modified"])
        with self.assertRaises(CrmApiException) as conflict:
            self.save("Stale", recordId=created["id"], expectedModified=created["modified"])
        self.assertEqual(conflict.exception.code, "VERSION_CONFLICT")
        self.assertEqual(service.list_records(self.opportunity_id)[0]["text"], updated["text"])

    def test_invalid_uploads_and_scan_failure_leave_no_record(self):
        cases = [("   ", []), ("x" * 10001, []), ("Note", [self.upload()] * 11), ("Note", [self.upload(content=b"")])]
        for text, files in cases:
            with self.assertRaises(CrmApiException):
                self.save(text, files)
        with patch.object(service, "validate_and_scan", side_effect=CrmApiException("VALIDATION_ERROR", "Rejected")):
            with self.assertRaises(CrmApiException):
                self.save(files=[self.upload()])
        self.assertEqual(service.list_records(self.opportunity_id), [])
        self.assertEqual(frappe.db.count(service.ATTACHMENT_DOCTYPE, {"opportunity": self.opportunity_id}), 0)

    def test_malformed_payloads_are_rejected_before_anything_is_written(self):
        created = self.save(files=[self.upload()])
        attachment_id = created["files"][0]["id"]
        rejected = (
            {"retainedFileIds": attachment_id},                      # not a list
            {"retainedFileIds": [1]},                                # not strings
            {"retainedFileIds": [attachment_id, attachment_id]},     # duplicates
        )
        for payload in rejected:
            with self.subTest(payload=payload):
                with self.assertRaises(CrmApiException) as denied:
                    self.save("Rejected", recordId=created["id"],
                              expectedModified=created["modified"], **payload)
                self.assertEqual(denied.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as denied:
            self.save("Rejected", recordId=7)
        self.assertEqual(denied.exception.code, "VALIDATION_ERROR")
        # Nothing was written: the record still has exactly its one attachment.
        self.assertEqual([item["id"] for item in service.list_records(self.opportunity_id)[0]["files"]],
                         [attachment_id])

    def test_a_request_over_the_total_byte_limit_is_refused(self):
        from rayher_crm.services.file_security import MAX_REQUEST_BYTES

        oversized = [self.upload("big.txt", b"x" * (MAX_REQUEST_BYTES + 1))]
        with self.assertRaises(CrmApiException) as denied:
            self.save("Too large", oversized)
        self.assertEqual(denied.exception.code, "VALIDATION_ERROR")
        self.assertEqual(service.list_records(self.opportunity_id), [])

    def test_a_file_turned_public_behind_the_ledger_is_not_served(self):
        created = self.save(files=[self.upload()])
        attachment_id = created["files"][0]["id"]
        file_id = frappe.db.get_value(service.ATTACHMENT_DOCTYPE, attachment_id, "private_file")
        # Nothing in the app does this, but the download path must not assume it.
        frappe.db.set_value("File", file_id, "is_private", 0, update_modified=False)
        with self.assertRaises(CrmApiException) as denied:
            service.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertEqual(denied.exception.code, "NOT_FOUND")

    def test_a_storage_failure_still_leaves_an_audit_row(self):
        from frappe.app import sync_database
        from frappe.core.doctype.file.file import File
        from rayher_crm.api.v1 import opportunity_status as api

        self.addCleanup(self.discard_committed_fixtures)
        created = self.save(files=[self.upload()])
        attachment_id = created["files"][0]["id"]
        with patch.object(File, "get_content", side_effect=OSError("disk is gone")):
            with self.assertRaises(CrmApiException) as failed:
                service.download_file(self.opportunity_id, created["id"], attachment_id)
            self.assertEqual((failed.exception.code, failed.exception.retryable), ("INTERNAL_ERROR", True))
            # As a GET request through the API edge, whose generic handler rolled back.
            frappe.local.flags.commit = False
            response = api.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertEqual(response["error"]["code"], "INTERNAL_ERROR")
        self.assertEqual(frappe.local.response["http_status_code"], 500)
        self.assertTrue(frappe.local.flags.commit)
        previous_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict(method="GET")
            self.assertFalse(sync_database(True))
        finally:
            frappe.local.request = previous_request
            frappe.local.flags.commit = False
        connection = frappe.db._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT reason FROM `tabCRM File Access Audit`"
                    " WHERE entity_type=%s AND entity_id=%s AND outcome='Denied'",
                    ("Status Attachment", attachment_id),
                )
                denied = [reason for (reason,) in cursor.fetchall()]
        finally:
            connection.close()
        self.assertEqual(denied, ["storage error: OSError"] * 2)

    def test_a_failing_error_log_does_not_cost_the_storage_failure_audit(self):
        from frappe.core.doctype.file.file import File

        created = self.save(files=[self.upload()])
        attachment_id = created["files"][0]["id"]
        self.addCleanup(lambda: frappe.local.flags.update(commit=False))
        with patch.object(File, "get_content", side_effect=OSError("disk is gone")), \
                patch("frappe.log_error", side_effect=RuntimeError("error log unavailable")), \
                self.broken_app_logger():
            with self.assertRaises(CrmApiException) as failed:
                service.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertEqual(failed.exception.code, "INTERNAL_ERROR")
        self.assertEqual(frappe.get_all("CRM File Access Audit", filters={
            "entity_type": "Status Attachment", "entity_id": attachment_id, "outcome": "Denied",
        }, pluck="reason"), ["storage error: OSError"])

    def test_a_lost_savepoint_does_not_replace_the_original_error(self):
        """A deadlock rolls back the whole transaction, taking the savepoint with it."""

        class Deadlock(Exception):
            pass

        def lose_the_transaction(*args, **kwargs):
            frappe.db.sql("ROLLBACK")
            raise Deadlock

        # Not even a failing logger may take the original error's place.
        with patch.object(service, "save_file", side_effect=lose_the_transaction), self.broken_app_logger():
            with self.assertRaises(Deadlock):
                self.save(files=[self.upload()])

    def test_a_failing_cleanup_and_logger_do_not_replace_the_upload_failure(self):
        """`discard_rolled_back_blob` must keep its promise never to raise."""
        from rayher_crm.services import private_file_lifecycle as lifecycle

        write_file = service.save_file
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("storage failed")
            return write_file(*args, **kwargs)

        with patch.object(service, "save_file", side_effect=fail_second), \
                patch.object(lifecycle, "_has_live_reference", side_effect=OSError("second connection refused")), \
                self.broken_app_logger():
            with self.assertRaisesRegex(RuntimeError, "storage failed"):
                self.save(files=[self.upload("one.txt", b"first bytes"), self.upload("two.txt", b"second bytes")])

    def test_a_status_save_never_waits_on_the_shared_naming_series_row(self):
        """Every `format:` name shares one `tabSeries` row, and other flows hold it while saving files."""
        self.addCleanup(self.discard_committed_fixtures)
        # The fixtures' own `format:` names took that row; committing releases it.
        frappe.db.commit()
        connection = frappe.db._get_connection()
        timeout = frappe.db.sql("SELECT @@SESSION.innodb_lock_wait_timeout")[0][0]
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_lock_wait_timeout = 1")
                cursor.execute("SELECT current FROM `tabSeries` WHERE name = '' FOR UPDATE")
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout = 1")
            created = self.save(files=[self.upload("one.txt", b"first"), self.upload("two.txt", b"second")])
            self.assertEqual(len(created["files"]), 2)
        finally:
            frappe.db.sql(f"SET SESSION innodb_lock_wait_timeout = {int(timeout)}")
            connection.rollback()
            connection.close()

    def test_attachments_of_one_save_keep_their_upload_order(self):
        names = [f"part-{index}.txt" for index in range(6)]
        created = self.save(files=[self.upload(name, name.encode()) for name in names])
        self.assertEqual([item["fileName"] for item in created["files"]], names)
        listed = service.list_records(self.opportunity_id)[0]["files"]
        self.assertEqual([item["fileName"] for item in listed], names)

    def test_a_tipray_protected_jpeg_is_stored_as_opaque_bytes(self):
        """Frappe would strip EXIF from a ".jpg" -- and fail on bytes that are no image."""
        from rayher_crm.services.file_security import TIPRAY_HEADER

        protected = TIPRAY_HEADER + uuid4().bytes * 8
        self.addCleanup(lambda: frappe.local.flags.update(commit=False))
        with self.exif_stripping_on():
            created = self.save(files=[{"file_name": "photo.jpg", "mime_type": "image/jpeg", "content": protected}])
        attachment = created["files"][0]
        self.assertEqual((attachment["fileName"], attachment["mimeType"]), ("photo.jpg", "image/jpeg"))
        file_id = frappe.db.get_value(service.ATTACHMENT_DOCTYPE, attachment["id"], "private_file")
        self.assertRegex(frappe.db.get_value("File", file_id, "file_name"), r"^tipray-\w+\.bin$")
        downloaded = service.download_file(self.opportunity_id, created["id"], attachment["id"])
        self.assertEqual(
            (downloaded["content"], downloaded["file_name"], downloaded["mime_type"]),
            (protected, "photo.jpg", "image/jpeg"),
        )

    def test_every_upload_content_lock_is_taken_before_any_file_is_written(self):
        """Up front, and on the stored bytes' hash that `protect_private_upload` locks."""
        from io import BytesIO

        from frappe.core.doctype.file.utils import get_content_hash
        from PIL import Image
        from rayher_crm.services import private_file_lifecycle as lifecycle

        exif = Image.Exif()
        exif[0x010E] = "camera"
        photo = BytesIO()
        Image.new("RGB", (32, 24), (200, 30, 30)).save(photo, format="JPEG", exif=exif.tobytes())
        uploads = [
            self.upload("second.txt", b"second upload"),
            {"file_name": "photo.jpg", "mime_type": "image/jpeg", "content": photo.getvalue()},
            self.upload("first.txt", b"first upload"),
            self.upload("again.txt", b"second upload"),
        ]
        events = []
        take_lock, write_file = lifecycle._lock_content, service.save_file

        def recorded_lock(content_hash, **kwargs):
            events.append(("lock", content_hash))
            return take_lock(content_hash, **kwargs)

        def recorded_write(*args, **kwargs):
            events.append(("write", args[0]))
            return write_file(*args, **kwargs)

        with self.exif_stripping_on(), \
                patch.object(lifecycle, "_lock_content", side_effect=recorded_lock), \
                patch.object(service, "save_file", side_effect=recorded_write):
            created = self.save(files=uploads)
        stored = {
            frappe.db.get_value("File", frappe.db.get_value(service.ATTACHMENT_DOCTYPE, item["id"], "private_file"), "content_hash")
            for item in created["files"]
        }
        first_write = events.index(("write", "second.txt"))
        self.assertEqual([value for _, value in events[:first_write]], sorted(stored))
        # Frappe re-encoded the JPEG, so a lock on the upload's own hash would miss.
        self.assertNotIn(get_content_hash(photo.getvalue()), stored)

    def test_partial_storage_failure_rolls_back_record_and_attachment_rows(self):
        save_file = service.save_file
        before = frappe.db.count(service.ATTACHMENT_DOCTYPE, {"opportunity": self.opportunity_id})
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("storage failed")
            return save_file(*args, **kwargs)

        with patch.object(service, "save_file", side_effect=fail_second), self.assertRaises(RuntimeError):
            self.save(files=[self.upload(), self.upload("second.txt", b"Second")])
        self.assertEqual(service.list_records(self.opportunity_id), [])
        self.assertEqual(
            frappe.db.count(service.ATTACHMENT_DOCTYPE, {"opportunity": self.opportunity_id}), before
        )

    def test_native_file_access_cannot_bypass_the_audited_endpoint(self):
        from frappe.core.doctype.file.utils import find_file_by_url

        created = self.save(files=[self.upload()])
        attachment_id = created["files"][0]["id"]
        file_id = frappe.db.get_value(service.ATTACHMENT_DOCTYPE, attachment_id, "private_file")
        file_doc = frappe.get_doc("File", file_id)
        # The uploader must not keep File's native owner shortcut.
        self.assertEqual(file_doc.owner, "Administrator")
        self.assertEqual(file_doc.attached_to_doctype, service.ATTACHMENT_DOCTYPE)
        self.assertEqual(file_doc.attached_to_name, attachment_id)
        self.assertEqual(
            service.download_file(self.opportunity_id, created["id"], attachment_id)["content"],
            b"Customer requirements confirmed",
        )
        # `CRM Status Attachment` grants no read DocPerm, so File.has_permission --
        # which delegates to the attached document -- denies the native routes too.
        self.assertFalse(frappe.has_permission(service.ATTACHMENT_DOCTYPE, "read",
                                               doc=frappe.get_doc(service.ATTACHMENT_DOCTYPE, attachment_id)))
        self.assertFalse(frappe.has_permission("File", "read", doc=file_doc))
        self.assertIsNone(find_file_by_url(file_doc.file_url, name=file_id))
        self.save("Removed attachment", recordId=created["id"], expectedModified=created["modified"])
        with self.assertRaises(CrmApiException):
            service.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertIsNone(find_file_by_url(file_doc.file_url, name=file_id))

    def test_scope_query_hides_other_owners_and_removed_rows(self):
        created = self.save(files=[self.upload(), self.upload("second.txt", b"Second attachment")])
        kept_id, removed_id = [item["id"] for item in created["files"]]
        self.save(
            "Removed", recordId=created["id"], expectedModified=created["modified"],
            retainedFileIds=[kept_id],
        )
        from rayher_crm.permissions.scope import status_attachment_query

        def visible(user):
            frappe.set_user(user)
            return {
                row[0] for row in frappe.db.sql(
                    "SELECT name FROM `tabCRM Status Attachment` WHERE "
                    + status_attachment_query()
                )
            }

        self.assertEqual(visible(self.sales) & {kept_id, removed_id}, {kept_id})
        self.assertEqual(visible(self.other_sales) & {kept_id, removed_id}, set())

    def test_csv_browser_mime_aliases_are_normalized_without_bypassing_content_checks(self):
        for mime in ("text/csv", "application/vnd.ms-excel", "application/octet-stream", ""):
            part = {"file_name": "measurements.csv", "mime_type": mime, "content": b"wafer,value\n1,2"}
            created = self.save(files=[part])
            self.assertEqual(created["files"][0]["mimeType"], "text/csv")
            self.assertEqual(
                service.download_file(self.opportunity_id, created["id"], created["files"][0]["id"])["content"],
                part["content"],
            )
        with self.assertRaises(CrmApiException):
            self.save(files=[{"file_name": "fake.csv", "mime_type": "application/vnd.ms-excel", "content": b"MZ\x00executable"}])
        for ext, mime in (("doc", "application/msword"), ("xls", "application/vnd.ms-excel"), ("ppt", "application/vnd.ms-powerpoint")):
            with self.assertRaises(CrmApiException):
                self.save(files=[{"file_name": "legacy." + ext, "mime_type": mime,
                                  "content": bytes.fromhex("d0cf11e0a1b11ae1") + b"legacy"}])

    def test_opportunity_with_status_records_cannot_be_deleted(self):
        from rayher_crm.services.opportunities import delete_strategy_opportunity

        created = self.save(files=[self.upload()])
        frappe.set_user("Administrator")
        manager = self._user("crm-status-delete-manager@example.invalid", "CRM Manager")
        frappe.set_user(manager)
        with self.assertRaises(CrmApiException) as blocked:
            delete_strategy_opportunity(self.opportunity_id)
        self.assertEqual(blocked.exception.code, "CONFLICT")
        self.assertTrue(frappe.db.exists("CRM Opportunity", self.opportunity_id))
        self.assertTrue(frappe.db.exists(service.DOCTYPE, created["id"]))
        frappe.set_user(self.sales)
        self.assertEqual(
            service.download_file(self.opportunity_id, created["id"], created["files"][0]["id"])["content"],
            b"Customer requirements confirmed",
        )

    def test_download_audits_success_and_denials_and_commits_denied_get(self):
        from frappe.app import sync_database
        from rayher_crm.api.v1 import opportunity_status as api

        self.addCleanup(self.discard_committed_fixtures)
        created = self.save(files=[self.upload()])
        attachment_id = created["files"][0]["id"]
        account = frappe.db.get_value("CRM Opportunity", self.opportunity_id, "account")
        service.download_file(self.opportunity_id, created["id"], attachment_id)
        allowed = frappe.get_all("CRM File Access Audit", filters={
            "entity_type": "Status Attachment", "entity_id": attachment_id, "outcome": "Allowed",
        }, fields=["actor", "account", "action"])
        self.assertEqual(len(allowed), 1)
        self.assertEqual(allowed[0].actor, self.sales)
        self.assertEqual(allowed[0].account, account)
        self.assertEqual(allowed[0].action, "Download")
        frappe.set_user(self.other_sales)
        response = api.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertEqual(response["error"]["code"], "SCOPE_DENIED")
        frappe.set_user(self.engineer)
        with patch.object(service, "assert_capability", side_effect=frappe.PermissionError):
            response = api.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertEqual(response["error"]["code"], "PERMISSION_DENIED")
        frappe.set_user(self.sales)
        self.save("Removed", recordId=created["id"], expectedModified=created["modified"])
        frappe.db.commit()
        frappe.local.flags.commit = False
        response = api.download_file(self.opportunity_id, created["id"], attachment_id)
        self.assertEqual(response["error"]["code"], "NOT_FOUND")
        self.assertTrue(frappe.local.flags.commit)
        previous_request = getattr(frappe.local, "request", None)
        try:
            frappe.local.request = frappe._dict(method="GET")
            self.assertFalse(sync_database(True))
        finally:
            frappe.local.request = previous_request
            frappe.local.flags.commit = False
        connection = frappe.db._get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT reason, actor FROM " + chr(96) + "tabCRM File Access Audit" + chr(96)
                    + " WHERE entity_type=%s AND entity_id=%s AND outcome='Denied'",
                    ("Status Attachment", attachment_id),
                )
                denied = cursor.fetchall()
            self.assertEqual({reason for reason, _ in denied}, {"SCOPE_DENIED", "capability denied", "NOT_FOUND"})
            self.assertIn(("NOT_FOUND", self.sales), denied)
        finally:
            connection.close()


class TestOpportunityStatusConcurrency(FrappeTestCase):
    _user = TestOpportunityRelations._user
    _records = TestOpportunityRelations._records

    def test_locking_a_records_attachments_leaves_the_neighbouring_index_gap_open(self):
        """The deadlock was a gap lock: `_lock_attachments` must take record locks only.

        A range lock on the non-unique `status` index also covers the gap before the
        next Status value, so the neighbouring record's attachment insert waited on
        it while holding the naming-series row this save needed next. Removed rows
        stay unlocked too: a long removal history must not grow the key list.
        """
        prefix = "zz-status-gap-" + uuid4().hex[:8]  # sorts after every hash-named record
        locked, neighbour = prefix + "-b", prefix + "-a"
        insert = (
            "INSERT INTO `tabCRM Status Attachment` (name, status, private_file, deleted, creation, modified)"
            " VALUES (%s, %s, %s, %s, NOW(6), NOW(6))"
        )
        lock_now = "SELECT name FROM `tabCRM Status Attachment` WHERE name = %s FOR UPDATE NOWAIT"
        active, removed = ("CRM-SA-GAP-" + uuid4().hex[:8] for _ in range(2))
        connection = None
        try:
            frappe.db.sql(insert, (active, locked, "gap-" + uuid4().hex, 0))
            frappe.db.sql(insert, (removed, locked, "gap-" + uuid4().hex, 1))
            # Committed, so any lock the second connection meets is `_lock_attachments`'s own.
            frappe.db.commit()
            connection = frappe.db._get_connection()
            rows = service._lock_attachments(locked)
            self.assertEqual([(item.name, int(item.deleted)) for item in rows], [(active, 0)])
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_lock_wait_timeout = 1")
                try:
                    # Its `status` index entry lands in the gap right before `locked`.
                    cursor.execute(insert, ("CRM-SA-GAP-" + uuid4().hex[:8], neighbour, "gap-" + uuid4().hex, 0))
                    cursor.execute(lock_now, (removed,))
                except Exception as error:
                    self.fail(f"_lock_attachments locked more than the record's active rows: {error}")
                with self.assertRaises(Exception) as waited:
                    cursor.execute(lock_now, (active,))
                # Lock wait timeout: the active row itself is still serialised.
                self.assertEqual(waited.exception.args[0], 1205)
        finally:
            if connection:
                connection.rollback()
                connection.close()
            frappe.db.rollback()
            frappe.db.sql("DELETE FROM `tabCRM Status Attachment` WHERE name IN %s", ((active, removed),))
            frappe.db.commit()

    def test_committed_scope_changes_during_scan_are_checked_with_current_reads(self):
        original_user = frappe.session.user
        frappe.set_user("Administrator")
        sales = self._user("crm-status-concurrent-sales@example.invalid", "CRM Sales")
        other = self._user("crm-status-concurrent-other@example.invalid", "CRM Sales")
        for change in ("both", "account", "opportunity", "visibility", "public_allowed"):
            with self.subTest(change=change):
                account, opportunity, contact = self._records(sales, "StatusRace" + uuid4().hex[:8])
                site = frappe.db.get_value("CRM Opportunity", opportunity["id"], "site")
                if change in ("visibility", "public_allowed"):
                    frappe.db.set_value("Customer", account["id"], {"custom_crm_owner": other, "custom_crm_visibility": "Public"})
                # The second connection must see committed fixtures, not the test transaction.
                frappe.db.commit()
                connection = frappe.db._get_connection()

                class TransferScanner:
                    def scan(scanner, content):
                        with connection.cursor() as cursor:
                            if change in ("both", "opportunity"):
                                cursor.execute("UPDATE `tabCRM Opportunity` SET opportunity_owner=%s WHERE name=%s", (other, opportunity["id"]))
                            if change in ("both", "account"):
                                cursor.execute("UPDATE `tabCustomer` SET custom_crm_owner=%s WHERE name=%s", (other, account["id"]))
                            if change == "visibility":
                                cursor.execute("UPDATE `tabCustomer` SET custom_crm_visibility='Private' WHERE name=%s", (account["id"],))
                        connection.commit()
                        return True

                try:
                    self.assertEqual(frappe.db.sql("SELECT @@tx_isolation")[0][0], "REPEATABLE-READ")
                    payload = {"text": "Concurrent save", "retainedFileIds": []}
                    upload = [{"file_name": "race.txt", "mime_type": "text/plain", "content": uuid4().hex.encode()}]
                    if change == "public_allowed":
                        saved = service.save_record(opportunity["id"], payload, upload, TransferScanner())
                        self.assertEqual(saved["text"], "Concurrent save")
                    else:
                        with self.assertRaises(CrmApiException) as denied:
                            service.save_record(opportunity["id"], payload, upload, TransferScanner())
                        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
                        self.assertFalse(frappe.db.exists(service.DOCTYPE, {"opportunity": opportunity["id"]}))
                        self.assertFalse(frappe.db.exists(service.ATTACHMENT_DOCTYPE, {"opportunity": opportunity["id"]}))
                finally:
                    frappe.db.rollback()
                    connection.close()
                    frappe.set_user("Administrator")
                    for name in frappe.get_all(service.ATTACHMENT_DOCTYPE, filters={"opportunity": opportunity["id"]}, pluck="name"):
                        frappe.delete_doc(service.ATTACHMENT_DOCTYPE, name, ignore_permissions=True, force=True)
                    for name in frappe.get_all(service.DOCTYPE, filters={"opportunity": opportunity["id"]}, pluck="name"):
                        frappe.delete_doc(service.DOCTYPE, name, ignore_permissions=True, force=True)
                    _delete_committed_opportunity(opportunity["id"])
                    frappe.delete_doc("Contact", contact["id"], ignore_permissions=True)
                    frappe.delete_doc("CRM Site", site, ignore_permissions=True)
                    frappe.delete_doc("Customer", account["id"], ignore_permissions=True)
                    with patch("frappe.enqueue"):
                        frappe.db.commit()
        frappe.set_user(original_user)
