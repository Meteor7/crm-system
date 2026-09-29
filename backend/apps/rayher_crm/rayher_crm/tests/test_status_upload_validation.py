"""Status filename boundary checks, without a database or external scanner."""

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.services import opportunity_status as status
from rayher_crm.services.file_security import TIPRAY_HEADER


class TestStatusUploadValidation(TestCase):
    def test_accepts_140_character_names_including_extension(self):
        for name in ("a" * 136 + ".txt", "文" * 136 + ".txt", "📄" + "a" * 135 + ".txt"):
            for content in (b"plain text", TIPRAY_HEADER + b"encrypted"):
                with self.subTest(name=name, encrypted=content.startswith(TIPRAY_HEADER)):
                    scanner = Mock()
                    scanner.scan.return_value = True
                    part = {"file_name": name, "mime_type": "text/plain", "content": content}
                    self.assertEqual(status._validate_upload(part, scanner), "text/plain")
                    scanner.scan.assert_called_once_with(content)

    def test_rejects_long_names_with_422_before_scan_or_write(self):
        with (
            patch.object(status, "assert_capability"),
            patch.object(status, "_require_opportunity"),
            patch.object(status, "lock_upload_contents", side_effect=AssertionError("must not lock")) as lock,
            patch.object(status, "save_file", side_effect=AssertionError("must not write")) as save,
            patch.object(frappe.local, "response", {}, create=True),
        ):
            for length in (141, 180):
                for content in (b"plain text", TIPRAY_HEADER + b"encrypted"):
                    with self.subTest(length=length, encrypted=content.startswith(TIPRAY_HEADER)):
                        scanner = Mock()
                        scanner.scan.return_value = True
                        uploads = [{"file_name": "a" * (length - 4) + ".txt", "mime_type": "text/plain", "content": content}]
                        args = ("OPP-1", {"text": "Keep this draft"}, uploads)
                        with self.assertRaises(CrmApiException) as caught:
                            status.save_record(*args, scanner=scanner)
                        self.assertEqual(caught.exception.code, "VALIDATION_ERROR")
                        result = api_endpoint(status.save_record)(*args, scanner=scanner)
                        self.assertEqual(frappe.local.response["http_status_code"], 422)
                        self.assertEqual(result["error"]["code"], "VALIDATION_ERROR")
                        self.assertIn("140", result["error"]["message"])
                        scanner.scan.assert_not_called()
            lock.assert_not_called()
            save.assert_not_called()
