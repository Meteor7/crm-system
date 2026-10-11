"""The release gate refuses uploads before core can write or fetch bytes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

import frappe
from frappe.core.doctype.file.file import File
from frappe.utils import file_manager
from rayher_crm.overrides.file import ManagedFile
from rayher_crm.security import attachment_gate


class TestAttachmentGate(TestCase):
    def setUp(self):
        self.traceback_flag = frappe.local.flags.get("disable_traceback")
        self.message_log = getattr(frappe.local, "message_log", None)
        frappe.local.message_log = []

    def tearDown(self):
        frappe.local.flags.disable_traceback = self.traceback_flag
        frappe.local.message_log = self.message_log

    def test_all_enabled_forms_block_before_core_file_insert(self):
        for enabled in (1, True, "1", "true"):
            with self.subTest(enabled=enabled), patch.dict(frappe.conf, {"crm_attachment_uploads_paused": enabled}), patch.object(File, "before_insert") as core:
                with self.assertRaises(frappe.PermissionError):
                    ManagedFile({"doctype": "File", "file_name": "blocked.txt", "content": "blocked"}).before_insert()
                core.assert_not_called()

    def test_disabled_forms_preserve_existing_insert_guard(self):
        for disabled in (0, False, "0", "false", None):
            with self.subTest(disabled=disabled), patch.dict(frappe.conf, {"crm_attachment_uploads_paused": disabled}):
                attachment_gate.reject_new_file()

    def test_multipart_rejected_before_handler(self):
        request = SimpleNamespace(files={"file": object()})
        with patch.dict(frappe.conf, {"crm_attachment_uploads_paused": True}), patch.object(frappe.local, "request", request, create=True):
            with self.assertRaises(frappe.PermissionError):
                attachment_gate.reject_upload_request()

    def test_core_json_and_file_reads_are_not_blocked_by_request_gate(self):
        request = SimpleNamespace(files={})
        with patch.dict(frappe.conf, {"crm_attachment_uploads_paused": True}), patch.object(frappe.local, "request", request, create=True):
            attachment_gate.reject_upload_request()

    def _assert_legacy_write_blocked(self, is_private):
        # Exercise real Frappe save_file and registered hooks. Only redirect its
        # filesystem into a disposable directory; do not stub the writer/gate.
        name = f"attachment-gate-{uuid4().hex}.txt"
        content = uuid4().hex.encode()
        before = frappe.db.count("File")
        with TemporaryDirectory() as directory:
            def files_path(*parts, is_private=0):
                return str(Path(directory, "private" if is_private else "public", *parts))

            with patch.dict(frappe.conf, {"crm_attachment_uploads_paused": True}), patch.object(
                file_manager, "get_files_path", side_effect=files_path
            ):
                with self.assertRaises(frappe.PermissionError):
                    file_manager.save_file(name, content, None, None, is_private=is_private)
            self.assertEqual(list(Path(directory).rglob("*")), [], "Rejected upload left filesystem entries")
        self.assertEqual(frappe.db.count("File"), before)
        self.assertFalse(frappe.db.exists("File", {"content_hash": file_manager.get_content_hash(content)}))

    def test_legacy_public_save_has_no_file_or_record_residue(self):
        self._assert_legacy_write_blocked(is_private=0)

    def test_legacy_private_save_has_no_file_or_record_residue(self):
        self._assert_legacy_write_blocked(is_private=1)

    def test_unpaused_legacy_writer_still_writes_public_and_private_bytes(self):
        # Positive control: these same temporary paths are writable, and the
        # hook leaves the writer unchanged when paused=False. Stub only the
        # subsequent document insert, so this test creates no database rows.
        for is_private in (0, 1):
            with self.subTest(is_private=is_private), TemporaryDirectory() as directory:
                def files_path(*parts, is_private=0):
                    return str(Path(directory, "private" if is_private else "public", *parts))

                name, content = f"attachment-gate-{uuid4().hex}.txt", uuid4().hex.encode()
                document = Mock(flags=SimpleNamespace())
                with patch.dict(frappe.conf, {"crm_attachment_uploads_paused": False}), patch.object(
                    file_manager, "get_files_path", side_effect=files_path
                ), patch.object(frappe, "get_doc", return_value=document):
                    file_manager.save_file(name, content, None, None, is_private=is_private)
                self.assertEqual(Path(files_path(name, is_private=is_private)).read_bytes(), content)
                document.insert.assert_called_once_with()
