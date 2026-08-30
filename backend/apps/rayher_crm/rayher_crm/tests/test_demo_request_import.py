"""Pure parsing tests for externally completed Demo Request forms."""

from __future__ import annotations

from io import BytesIO
from unittest import TestCase
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.demo_request_imports import import_demo_request_form, parse_drf_text


def _docx_with_tables() -> bytes:
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def cell(value: str) -> str:
        return f'<w:tc><w:p><w:r><w:t>{escape(value)}</w:t></w:r></w:p></w:tc>'

    def row(*values: str) -> str:
        return f"<w:tr>{''.join(cell(value) for value in values)}</w:tr>"

    request_rows = [
        row("Company Name", "Example Semiconductor Co."),
        row("Contact Person", "Ada Liu, Process Director, ada@example.com"),
        row("Industry", "Frontend Fab"),
        row("Sales Contact", "Demo Staff 01"),
        row("Demo Owner", "Zhou Ning"),
        row("Size & Shape", "300 mm, 775 um, notch"),
        row("Material (Substrate)", "Si(100)"),
        row("Specific Request", "3 mm edge exclusion"),
        row("What to Detect / Measure", "Particles above 1 um"),
        row("Expected Results", "KLARF and PDF"),
        row("Other Tools", "KLA Surfscan"),
        row("Primary Tool", "Aconca FS Edge"),
        row("Complementary Tool", "Nansi"),
        row("Timing", "2026-09-15"),
        row("Key Success Factors", "Capture rate >= 95%"),
        row("Internal Questions", "Confirm recipe owner"),
        row("Questions for Customer", "Confirm delivery date"),
    ]
    wafer_rows = [
        row("Slot ID", "WID", "Wafer Specificity", "Notch / Flat", "DOI / Metrology Items", "Result File Provided"),
        row("1", "W-001", "300 mm Si", "Notch up", "Particles", "Reference KLARF"),
        row("", "", "", "", "", ""),
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{namespace}"><w:body>'
        f"<w:tbl>{''.join(request_rows)}</w:tbl>"
        f"<w:tbl>{''.join(wafer_rows)}</w:tbl>"
        "</w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="xml" ContentType="application/xml" />
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
              <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" />
            </Types>""",
        )
        archive.writestr("word/document.xml", xml)
    return output.getvalue()


class DemoRequestImportTest(TestCase):
    def test_docx_import_maps_request_fields_and_nonempty_wafer_rows(self):
        result = import_demo_request_form(
            "completed-drf.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _docx_with_tables(),
        )

        self.assertEqual(result["companyName"], "Example Semiconductor Co.")
        self.assertEqual(result["formData"]["contactPerson"], "Ada Liu, Process Director, ada@example.com")
        self.assertEqual(result["formData"]["primaryTool"], "Aconca FS Edge")
        self.assertEqual(result["formData"]["timing"], "2026-09-15")
        self.assertEqual(result["formData"]["wafers"], [{
            "slotId": "1",
            "wid": "W-001",
            "waferSpecificity": "300 mm Si",
            "notchFlat": "Notch up",
            "doiMetrologyItems": "Particles",
            "resultFileProvided": "Reference KLARF",
        }])

    def test_pdf_style_text_stops_values_at_the_next_known_label(self):
        result = parse_drf_text("""
            Company Name\nExample Semiconductor Co.\nContact Person\nAda Liu, ada@example.com
            Industry\nFrontend Fab\nSales Contact\nDemo Staff 01\nDemo Owner\nZhou Ning
            Size & Shape\n300 mm round\nMaterial (Substrate)\nSi(100)
            What to Detect / Measure\nParticles above 1 um\nExpected Results\nKLARF and PDF
            Primary Tool\nAconca FS Edge\nTiming\n2026-09-15
            Key Success Factors\nCapture rate >= 95%\nInternal Questions\nConfirm recipe
            Questions for Customer\nConfirm delivery
        """)

        self.assertEqual(result["companyName"], "Example Semiconductor Co.")
        self.assertEqual(result["formData"]["material"], "Si(100)")
        self.assertEqual(result["formData"]["expectedResults"], "KLARF and PDF")
        self.assertNotIn("Primary Tool", result["formData"]["expectedResults"])

    def test_rejects_empty_and_unsupported_files(self):
        with self.assertRaisesRegex(CrmApiException, "required"):
            import_demo_request_form("empty.pdf", "application/pdf", b"")
        with self.assertRaisesRegex(CrmApiException, "allowed"):
            import_demo_request_form("legacy.doc", "application/msword", b"legacy")
