from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.visit_meetings import _meeting_range, _validate_archive, parse_meeting_file


def _xlsx(rows):
    shared = [value for row in rows for value in row]
    indexes = iter(range(len(shared)))
    xml_rows = []
    for row_number, row in enumerate(rows, 1):
        cells = "".join(f'<c t="s"><v>{next(indexes)}</v></c>' for _value in row)
        xml_rows.append(f'<row r="{row_number}">{cells}</row>')
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + "".join(f"<si><t>{value}</t></si>" for value in shared) + "</sst>")
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>")
    return stream.getvalue()


class TestVisitMeetingParser(FrappeTestCase):
    def test_parses_standard_xlsx_template_and_multiline_sections(self):
        content = _xlsx([
            ["Meeting Time", "2025/11/24 10:15~12:00"],
            ["Meeting Purpose", "Discussion about potential business"],
            ["Attendees", "Customer A"], ["", "Dongbao"],
            ["Agenda", "Introduce solution"],
            ["Summay", "Point one"], ["", "Point two"],
            ["Conclusion", "Proceed"], ["Followup", "Send proposal"],
        ])
        parsed, status, _message = parse_meeting_file("meeting.xlsx", content)
        self.assertEqual(status, "Parsed")
        self.assertEqual(parsed["attendees"], "Customer A\nDongbao")
        self.assertEqual(parsed["summary"], "Point one\nPoint two")
        self.assertEqual(_meeting_range(parsed["meeting_time"]), ("2025-11-24T10:15", "2025-11-24T12:00"))

    def test_marks_incomplete_text_for_manual_review(self):
        parsed, status, _message = parse_meeting_file("meeting.txt", b"Meeting Purpose: Intro\nAgenda: Demo")
        self.assertEqual(status, "NeedsManualReview")
        self.assertEqual(parsed["purpose"], "Intro")

    def test_archives_unsupported_formats_without_claiming_parse_success(self):
        parsed, status, _message = parse_meeting_file("meeting.png", b"image")
        self.assertEqual(parsed, {})
        self.assertEqual(status, "ArchiveOnly")

    def test_unknown_non_executable_file_can_be_archived_after_scan(self):
        class CleanScanner:
            def scan(self, _content):
                return True

        _validate_archive("meeting.notes", "application/octet-stream", b"plain meeting bytes", CleanScanner())

    def test_executable_file_is_rejected_before_archive(self):
        class CleanScanner:
            def scan(self, _content):
                return True

        with self.assertRaises(CrmApiException):
            _validate_archive("meeting.exe", "application/octet-stream", b"MZ executable", CleanScanner())
