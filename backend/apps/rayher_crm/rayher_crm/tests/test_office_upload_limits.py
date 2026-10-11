"""Office uploads near the part-count and decompressed-size limits, without a database or external scanner."""

import io
import zipfile
from unittest import TestCase
from unittest.mock import Mock

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.file_security import (
    DOCX_MIME,
    MAX_DOCX_ENTRIES,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    PPTX_MIME,
    TXT_MIME,
    XLSX_MIME,
    validate_and_scan,
)

WRONG_TYPE = "File type is not allowed or does not match its magic bytes."


def _office(document_part: str, parts: int = 0, *, padding: int = 0, extra: tuple[str, ...] = ()) -> bytes:
    """An Office ZIP whose part count is [Content_Types].xml, its document part, `parts` fillers and `extra`."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(document_part, "<document/>")
        for index in range(parts):
            archive.writestr(f"ppt/media/part{index}.xml", "<p/>")
        for name in extra:
            # Set after construction: ZipInfo would drop a leading slash.
            info = zipfile.ZipInfo()
            info.filename = name
            archive.writestr(info, "x")
        if padding:
            archive.writestr("ppt/media/padding.bin", bytes(padding))
    return output.getvalue()


def _scanner() -> Mock:
    scanner = Mock()
    scanner.scan.return_value = True
    return scanner


class TestOfficeUploadLimits(TestCase):
    def test_accepts_a_deck_of_a_few_thousand_parts(self):
        # The deck that was refused on staging had 3,092 parts and 38.5 MiB of content.
        content = _office("ppt/presentation.xml", 3090)
        scanner = _scanner()
        self.assertEqual(validate_and_scan("Nansi-0610.pptx", PPTX_MIME, content, scanner), PPTX_MIME)
        scanner.scan.assert_called_once_with(content)

    def test_accepts_exactly_the_part_limit(self):
        content = _office("ppt/presentation.xml", MAX_DOCX_ENTRIES - 2)
        self.assertEqual(validate_and_scan("limit.pptx", PPTX_MIME, content, _scanner()), PPTX_MIME)

    def test_names_the_file_over_the_part_limit_before_scanning(self):
        for name, part, mime in (
            ("deck.pptx", "ppt/presentation.xml", PPTX_MIME),
            ("sheet.xlsx", "xl/workbook.xml", XLSX_MIME),
            ("report.docx", "word/document.xml", DOCX_MIME),
        ):
            with self.subTest(name=name):
                scanner = _scanner()
                with self.assertRaises(CrmApiException) as caught:
                    validate_and_scan(name, mime, _office(part, MAX_DOCX_ENTRIES - 1), scanner)
                self.assertEqual(caught.exception.code, "VALIDATION_ERROR")
                self.assertEqual(
                    caught.exception.public_message,
                    f'"{name}" has more than {MAX_DOCX_ENTRIES} internal parts. Save it as PDF, or split it, and upload again.',
                )
                scanner.scan.assert_not_called()

    def test_names_the_file_over_the_decompressed_size_before_scanning(self):
        scanner = _scanner()
        content = _office("ppt/presentation.xml", padding=MAX_DOCX_UNCOMPRESSED_BYTES)
        with self.assertRaises(CrmApiException) as caught:
            validate_and_scan("Big deck.pptx", PPTX_MIME, content, scanner)
        self.assertEqual(
            caught.exception.public_message,
            '"Big deck.pptx" is larger than 50 MiB once decompressed. Compress its images or save it as PDF, and upload again.',
        )
        scanner.scan.assert_not_called()

    def test_accepts_exactly_the_decompressed_limit(self):
        # [Content_Types].xml and the document part hold 19 bytes between them.
        content = _office("ppt/presentation.xml", padding=MAX_DOCX_UNCOMPRESSED_BYTES - 19)
        self.assertEqual(validate_and_scan("full.pptx", PPTX_MIME, content, _scanner()), PPTX_MIME)

    def test_reads_the_type_in_the_old_order_and_keeps_its_macro_rule(self):
        both = _office("word/document.xml", extra=("xl/workbook.xml",))
        self.assertEqual(validate_and_scan("both.docx", DOCX_MIME, both, _scanner()), DOCX_MIME)
        # Only workbooks and decks were refused for a macro part, before and now.
        macro = _office("word/document.xml", extra=("word/vbaProject.bin",))
        self.assertEqual(validate_and_scan("macro.docx", DOCX_MIME, macro, _scanner()), DOCX_MIME)

    def test_a_malformed_office_file_over_a_limit_is_the_wrong_type_not_too_large(self):
        for name, extra in (("absolute.pptx", ("/etc/passwd",)), ("parent.pptx", ("../outside.xml",))):
            content = _office("ppt/presentation.xml", MAX_DOCX_ENTRIES, extra=extra)
            with self.subTest(name=name), self.assertRaises(CrmApiException) as caught:
                validate_and_scan(name, PPTX_MIME, content, _scanner())
            self.assertEqual(caught.exception.public_message, WRONG_TYPE)

    def test_a_zip_that_is_not_an_office_file_is_still_the_wrong_type(self):
        for name, content in (
            ("many.pptx", _office("other.xml", MAX_DOCX_ENTRIES + 10)),
            ("macro.pptx", _office("ppt/presentation.xml", extra=("ppt/vbaProject.bin",))),
            ("macro.xlsx", _office("xl/workbook.xml", extra=("xl/vbaProject.bin",))),
        ):
            with self.subTest(name=name), self.assertRaises(CrmApiException) as caught:
                validate_and_scan(name, PPTX_MIME if name.endswith("pptx") else XLSX_MIME, content, _scanner())
            self.assertEqual(caught.exception.public_message, WRONG_TYPE)

    def test_text_that_starts_like_a_zip_is_still_text(self):
        content = b"PK\x03\x04 is how a ZIP file starts."
        self.assertEqual(validate_and_scan("notes.txt", TXT_MIME, content, _scanner()), TXT_MIME)
