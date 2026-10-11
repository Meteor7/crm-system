"""Real MariaDB rollback at the HTTP boundary, plus deterministic slow preparation."""

import os
from pathlib import Path
import subprocess
from unittest import TestCase
from unittest.mock import Mock, patch

from werkzeug.wrappers import Request

import frappe
from frappe.database import get_db
from frappe.tests.utils import FrappeTestCase
from frappe.utils import CallbackManager

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.services import rfqs, upload_deadline
from rayher_crm.services.private_file_lifecycle import save_private_file
from rayher_crm.services.upload_deadline import (
    UPLOAD_TIMEOUT_MESSAGE, begin_upload_request, current_upload, upload_transaction,
)


def request():
    # File validation also reads request.host/headers through Frappe's get_url.
    return Request.from_values(
        base_url=f"http://{getattr(frappe.local, 'site', 'uploads.test')}",
        method="POST", content_type="multipart/form-data",
        path="/api/method/rayher_crm.api.v1.rfqs.create_rfq",
    )


class DeadlineFixture:
    def deadline(self):
        self.clock = 1000.0
        for context in (
            patch.object(frappe.local, "request", request(), create=True),
            patch.object(frappe.local, "response", {}, create=True),
            patch.object(frappe.local, "crm_upload_deadline", None, create=True),
            patch.object(upload_deadline.time, "monotonic", lambda: self.clock),
        ):
            context.start()
            self.addCleanup(context.stop)
        begin_upload_request()


class TestUploadPreparation(DeadlineFixture, TestCase):
    def setUp(self):
        self.deadline()

    def test_scan_and_conversion_share_one_budget(self):
        def scanned(*args):
            self.clock += 50
            return "deck.pptx", rfqs.PPTX_MIME, b"office content"

        seen = []

        def convert(command, **kwargs):
            process = Mock(pid=12345, returncode=0)

            def wait(timeout=None):
                seen.append(timeout)
                self.clock += 35
                Path(command[-1]).with_suffix(".pdf").write_bytes(b"%PDF-1.4\npreview")
            process.wait.side_effect = wait
            return process

        with patch.object(rfqs, "_file_part", side_effect=scanned), patch.object(rfqs.subprocess, "Popen", side_effect=convert):
            prepared = rfqs._prepare_version({})
        self.assertEqual(prepared[3][1], rfqs.PDF_MIME)
        self.assertEqual(seen, [40])
        self.assertEqual(current_upload().remaining(preparation=True), 5)

    def test_50_second_scan_cannot_be_followed_by_85_second_conversion(self):
        self.clock += 50
        process = Mock(pid=12345, returncode=-9)

        def wait(timeout=None):
            if timeout is not None:
                self.assertEqual(timeout, 40)
                self.clock += timeout
                raise subprocess.TimeoutExpired("soffice", timeout)

        process.wait.side_effect = wait
        with patch.object(rfqs.subprocess, "Popen", return_value=process) as start, \
                patch.object(rfqs.os, "killpg", create=True) as kill, \
                self.assertRaises(CrmApiException) as refused:
            rfqs._office_preview("deck.pptx", b"office content")
        self.assertEqual(refused.exception.public_message, UPLOAD_TIMEOUT_MESSAGE)
        self.assertTrue(start.call_args.kwargs["start_new_session"])
        kill.assert_called_once_with(process.pid, rfqs.signal.SIGKILL)
        self.assertEqual(process.wait.call_count, 2)  # reap the terminated process

    def test_preparation_that_returns_late_is_refused_before_the_transaction(self):
        def late(*args):
            self.clock += 135
            return None
        with patch.object(rfqs, "_file_part", return_value=("deck.pptx", rfqs.PPTX_MIME, b"x")), \
                patch.object(rfqs, "_preview", side_effect=late), self.assertRaises(CrmApiException):
            rfqs._prepare_version({})

    def test_a_new_request_does_not_inherit_an_old_deadline(self):
        first = current_upload()
        self.clock += 200
        frappe.local.request = request()
        begin_upload_request()
        self.assertIsNot(current_upload(), first)
        self.assertEqual(current_upload().remaining(), upload_deadline.UPLOAD_TIMEOUT_SECONDS)


class TestUploadTransaction(DeadlineFixture, FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, self.original_user)
        self.deadline()

    def test_late_write_rolls_back_rows_and_blobs_through_the_api(self):
        written = []

        @api_endpoint
        def upload():
            doc = save_private_file("deadline.txt", f"deadline {frappe.generate_hash()}".encode(), None, None)
            written.append((doc.name, doc.get_full_path()))
            self.clock += 106  # includes the final save/serialization, after scanning
            return {"data": {"id": doc.name}}

        result = upload()
        self.assertEqual(result["error"]["message"], UPLOAD_TIMEOUT_MESSAGE)
        self.assertIsNone(result["data"])
        for name, path in written:
            self.assertFalse(frappe.db.exists("File", name))
            self.assertFalse(os.path.exists(path))

    def test_expiry_between_handler_return_and_commit_still_rolls_back(self):
        with upload_transaction():
            doc = save_private_file("before-commit.txt", f"commit {frappe.generate_hash()}".encode(), None, None)
        self.clock += 106
        with self.assertRaises(CrmApiException):
            frappe.db.commit()
        self.assertFalse(frappe.db.exists("File", doc.name))
        self.assertFalse(os.path.exists(doc.get_full_path()))

    def test_database_timeouts_are_restored_after_success_and_failure(self):
        query = "SELECT @@SESSION.innodb_lock_wait_timeout, @@SESSION.max_statement_time"
        original = frappe.db.sql(query)[0]
        for refused in (False, True):
            try:
                with upload_transaction():
                    limited = frappe.db.sql(query)[0]
                    self.assertLessEqual(limited[0], 5)
                    self.assertLessEqual(limited[1], 5)
                    self.assertGreater(limited[1], 0)
                    if refused:
                        raise ValueError("refuse this upload")
            except ValueError:
                pass
            self.assertEqual(frappe.db.sql(query)[0], original)

    def test_a_real_statement_timeout_refuses_the_entire_upload(self):
        written = []

        @api_endpoint
        def upload():
            created = frappe.get_doc({"doctype": "ToDo", "description": "statement timeout rollback"}).insert()
            written.append(created.name)
            frappe.db.sql("SELECT SLEEP(2)")  # MariaDB error 1969, not QueryTimeoutError
            return {"data": "unexpected success"}

        with patch.object(upload_deadline, "DATABASE_WAIT_SECONDS", 1):
            result = upload()
        self.assertEqual(result["error"]["message"], UPLOAD_TIMEOUT_MESSAGE)
        self.assertEqual(frappe.local.response["http_status_code"], 422)
        self.assertTrue(written)
        self.assertFalse(frappe.db.exists("ToDo", written[0]))

    def test_expired_upload_cleans_blobs_after_the_response(self):
        callbacks = frappe.local.request.after_response = CallbackManager()
        with upload_transaction():
            doc = save_private_file("deferred-cleanup.txt", f"deferred {frappe.generate_hash()}".encode(), None, None)
        self.clock += 106
        with self.assertRaises(CrmApiException):
            frappe.db.commit()
        self.assertFalse(frappe.db.exists("File", doc.name))
        # The rows are already gone; potentially slow blob work is outside the
        # response path, and still runs before Frappe destroys the connection.
        self.assertTrue(os.path.exists(doc.get_full_path()))
        callbacks.run()
        self.assertFalse(os.path.exists(doc.get_full_path()))

    def test_a_real_row_lock_timeout_refuses_the_entire_upload(self):
        # A committed fixture visible to a second connection, removed permanently
        # below. The upload must undo its own earlier writes when this row is busy.
        row = frappe.get_doc({"doctype": "ToDo", "description": "upload deadline lock fixture"}).insert()
        frappe.db.commit()
        other = get_db(host=frappe.conf.db_host, port=frappe.conf.db_port,
            user=frappe.conf.db_user or frappe.conf.db_name, password=frappe.conf.db_password, cur_db_name=frappe.conf.db_name)
        other.connect()
        written = []
        try:
            other.sql("SELECT name FROM tabToDo WHERE name=%s FOR UPDATE", (row.name,))

            @api_endpoint
            def upload():
                created = frappe.get_doc({"doctype": "ToDo", "description": "must be rolled back"}).insert()
                written.append(created.name)
                # Exercise lock-wait classification separately from error 1969
                # covered above; equal query/lock limits otherwise race.
                frappe.db.sql("SET SESSION max_statement_time = 0")
                frappe.db.sql("SELECT name FROM tabToDo WHERE name=%s FOR UPDATE", (row.name,))
                return {"data": "unexpected success"}

            with patch.object(upload_deadline, "DATABASE_WAIT_SECONDS", 1):
                result = upload()
            self.assertEqual(result["error"]["message"], UPLOAD_TIMEOUT_MESSAGE)
            self.assertTrue(written)
            self.assertFalse(frappe.db.exists("ToDo", written[0]))
        finally:
            other.rollback()
            other.close()
            frappe.db.rollback()
            frappe.db.delete("ToDo", {"name": row.name})
            frappe.db.commit()
