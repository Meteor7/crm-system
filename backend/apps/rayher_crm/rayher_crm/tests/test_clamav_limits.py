"""Exercise the deployed clamd, including content the outer Office limit cannot count."""

from io import BytesIO
from unittest import TestCase
from zipfile import ZipFile, ZIP_DEFLATED

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.file_security import PPTX_MIME, validate_and_scan


def archive(entries):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zipped:
        for name, content in entries:
            zipped.writestr(name, content)
    return output.getvalue()


def deck(extra):
    return archive([
        ("[Content_Types].xml", b"<Types/>"),
        ("ppt/presentation.xml", b"<presentation/>"),
        *extra,
    ])


class TestClamavLimits(TestCase):
    def test_real_scanner_accepts_a_large_clean_deck(self):
        content = deck([(f"ppt/slides/slide{i}.xml", f"<slide>{i}</slide>".encode()) for i in range(3090)])
        self.assertEqual(validate_and_scan("large-clean.pptx", PPTX_MIME, content), PPTX_MIME)

    def test_nested_file_count_is_refused_even_with_only_three_outer_parts(self):
        nested = archive((f"file{i}.txt", f"part {i}: harmless content".encode()) for i in range(10020))
        with self.assertRaises(CrmApiException) as refused:
            validate_and_scan("nested-limit.pptx", PPTX_MIME, deck([("ppt/embeddings/inner.zip", nested)]))
        self.assertEqual(refused.exception.public_message, "File failed malware screening.")

    def test_nested_depth_is_refused_even_with_only_three_outer_parts(self):
        nested = b"harmless content at the bottom"
        for depth in range(22):
            nested = archive([(f"level{depth}.zip", nested)])
        with self.assertRaises(CrmApiException) as refused:
            validate_and_scan("deep-limit.pptx", PPTX_MIME, deck([("ppt/embeddings/inner.zip", nested)]))
        self.assertEqual(refused.exception.public_message, "File failed malware screening.")
