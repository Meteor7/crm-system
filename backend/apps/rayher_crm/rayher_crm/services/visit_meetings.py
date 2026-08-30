"""Visit meeting-record uploads, deterministic parsing, and manual correction."""

from __future__ import annotations

from io import BytesIO
import os
import mimetypes
import re
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import frappe
from frappe.utils import now_datetime
from frappe.utils.file_manager import save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability
from rayher_crm.services.common import normalize_expected_modified, to_iso_timestamp
from rayher_crm.services.file_security import ClamdScanner, MAX_FILE_BYTES, MalwareScanner, validate_and_scan

LABELS = {
    "meeting time": "meeting_time", "meeting purpose": "purpose", "attendees": "attendees",
    "agenda": "agenda", "summary": "summary", "summay": "summary", "conclusion": "conclusion",
    "followup": "followup", "follow-up": "followup", "follow up": "followup",
}
REQUIRED_CONTENT = ("purpose", "attendees", "agenda", "summary", "conclusion", "followup")
STRICT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".txt", ".png", ".jpg", ".jpeg"}
EXECUTABLE_EXTENSIONS = {".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".js", ".jse", ".vbs", ".vbe", ".msi", ".scr", ".hta", ".jar", ".sh"}
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SHEET_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _clean(value: Any) -> str:
    return re.sub(r"[ \t\f\v]+", " ", str(value or "").replace("\u00a0", " ")).strip()


def _label(value: str) -> str:
    return LABELS.get(_clean(value).rstrip(":：").casefold(), "")


def _parse_rows(rows: list[list[str]]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    active = ""
    for row in rows:
        values = [_clean(value) for value in row]
        key = _label(values[0]) if values else ""
        if key:
            active = key
            content = "\n".join(value for value in values[1:] if value)
            if content:
                parsed[key] = content
        elif active:
            content = "\n".join(value for value in values if value)
            if content:
                parsed[active] = "\n".join(filter(None, (parsed.get(active), content)))
    return parsed


def _parse_text(text: str) -> dict[str, str]:
    rows: list[list[str]] = []
    for line in text.replace("\r", "\n").split("\n"):
        line = _clean(line)
        if not line:
            rows.append([])
            continue
        match = re.match(r"^([^:：,\t]+)[:：,\t]\s*(.*)$", line)
        rows.append([match.group(1), match.group(2)] if match else [line])
    return _parse_rows(rows)


def _docx(content: bytes) -> dict[str, str]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise ValueError("DOCX 文件结构损坏。") from error
    rows = []
    for row in root.findall(".//w:tbl/w:tr", WORD_NS):
        cells = []
        for cell in row.findall("./w:tc", WORD_NS):
            cells.append(_clean("".join(node.text or "" for node in cell.findall(".//w:t", WORD_NS))))
        rows.append(cells)
    parsed = _parse_rows(rows)
    if parsed:
        return parsed
    paragraphs = [_clean("".join(node.text or "" for node in paragraph.findall(".//w:t", WORD_NS))) for paragraph in root.findall(".//w:p", WORD_NS)]
    return _parse_text("\n".join(paragraphs))


def _xlsx(content: bytes) -> dict[str, str]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [_clean("".join(node.text or "" for node in item.findall(".//x:t", SHEET_NS))) for item in root.findall("x:si", SHEET_NS)]
            sheet_name = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))[0]
            sheet = ElementTree.fromstring(archive.read(sheet_name))
    except (BadZipFile, KeyError, IndexError, ElementTree.ParseError) as error:
        raise ValueError("XLSX 文件结构损坏。") from error
    rows = []
    for row in sheet.findall(".//x:sheetData/x:row", SHEET_NS):
        values = []
        for cell in row.findall("x:c", SHEET_NS):
            kind = cell.attrib.get("t")
            raw = cell.findtext("x:v", default="", namespaces=SHEET_NS)
            if kind == "s" and raw.isdigit() and int(raw) < len(shared):
                value = shared[int(raw)]
            elif kind == "inlineStr":
                value = _clean("".join(node.text or "" for node in cell.findall(".//x:t", SHEET_NS)))
            else:
                value = _clean(raw)
            values.append(value)
        rows.append(values)
    return _parse_rows(rows)


def _pdf(content: bytes) -> dict[str, str]:
    try:
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    except Exception as error:
        raise ValueError("PDF 无法读取。") from error
    if not text.strip():
        raise ValueError("PDF 没有可复制文本，扫描件暂不支持解析。")
    return _parse_text(text)


def parse_meeting_file(file_name: str, content: bytes) -> tuple[dict[str, str], str, str]:
    suffix = os.path.splitext(file_name)[1].casefold()
    try:
        if suffix == ".xlsx":
            parsed = _xlsx(content)
        elif suffix == ".docx":
            parsed = _docx(content)
        elif suffix == ".pdf":
            parsed = _pdf(content)
        elif suffix in {".txt", ".csv"}:
            parsed = _parse_text(content.decode("utf-8-sig"))
        else:
            return {}, "ArchiveOnly", "文件已归档，此格式需手动补录。"
    except (ValueError, UnicodeDecodeError) as error:
        return {}, "NeedsManualReview", str(error)
    detected = [key for key in REQUIRED_CONTENT if parsed.get(key)]
    if len(detected) == len(REQUIRED_CONTENT):
        return parsed, "Parsed", "会议记录解析成功。"
    if detected or parsed.get("meeting_time"):
        return parsed, "NeedsManualReview", "部分模板字段未识别，请检查并补录。"
    return parsed, "NeedsManualReview", "未识别到会议模板字段，请手动补录。"


def _meeting_range(value: str) -> tuple[str, str]:
    cleaned = _clean(value)
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}:\d{2})\s*[~～-]\s*(\d{1,2}:\d{2})", cleaned)
    if not match:
        return cleaned, ""
    day = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return f"{day}T{match.group(4)}", f"{day}T{match.group(5)}"


def _validate_archive(file_name: str, mime_type: str, content: bytes, scanner: MalwareScanner | None) -> None:
    suffix = os.path.splitext(file_name.strip())[1].casefold()
    if suffix in STRICT_EXTENSIONS:
        validate_and_scan(file_name, mime_type, content, scanner)
        return
    if not content or len(content) > MAX_FILE_BYTES or not file_name.strip() or len(file_name) > 180:
        raise CrmApiException("VALIDATION_ERROR", "File is empty, too large, or has an invalid name.")
    if file_name != os.path.basename(file_name) or suffix in EXECUTABLE_EXTENSIONS or content.startswith((b"MZ", b"\x7fELF", b"#!")):
        raise CrmApiException("VALIDATION_ERROR", "Executable files cannot be archived as meeting records.")
    try:
        clean = (scanner or ClamdScanner()).scan(content)
    except Exception as error:
        raise CrmApiException("INTERNAL_ERROR", "File security scanner is unavailable.", retryable=True) from error
    if not clean:
        raise CrmApiException("VALIDATION_ERROR", "File failed malware screening.")


def _serialize_record(doc) -> dict[str, Any]:
    return {
        "id": doc.name, "visitId": doc.visit, "meetingStart": doc.meeting_start or "", "meetingEnd": doc.meeting_end or "",
        "purpose": doc.purpose or "", "attendees": doc.attendees or "", "agenda": doc.agenda or "", "summary": doc.summary or "",
        "conclusion": doc.conclusion or "", "followup": doc.followup or "", "parseStatus": doc.parse_status,
        "parseMessage": doc.parse_message or "", "parsedAt": to_iso_timestamp(doc.parsed_at) if doc.parsed_at else "",
        "manuallyCorrected": bool(doc.manually_corrected), "modified": to_iso_timestamp(doc.modified),
    }


def get_record(visit_id: str) -> dict[str, Any] | None:
    name = frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit_id}, "name")
    return _serialize_record(frappe.get_doc("CRM Visit Meeting Record", name)) if name else None


def list_attachments(visit_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all("File", filters={"attached_to_doctype": "CRM Visit", "attached_to_name": visit_id, "is_private": 1}, fields=["name", "file_name", "file_type", "file_size", "creation", "owner"], order_by="creation desc")
    return [{"id": row.name, "visitId": visit_id, "fileName": row.file_name, "mimeType": mimetypes.guess_type(row.file_name)[0] or "application/octet-stream", "size": int(row.file_size or 0), "uploadedAt": to_iso_timestamp(row.creation), "uploadedBy": row.owner} for row in rows]


def _lock_editable_visit(visit_id: str):
    rows = frappe.db.sql(
        """
        SELECT name, status
        FROM `tabCRM Visit`
        WHERE name = %s
        FOR UPDATE
        """,
        (visit_id,),
        as_dict=True,
    )
    if not rows:
        raise CrmApiException("NOT_FOUND", "Visit was not found.")
    if rows[0].status == "Manager Reviewed":
        raise CrmApiException("INVALID_TRANSITION", "Manager-reviewed Visit records cannot be changed.")
    from rayher_crm.services.visits import _require_visit
    _require_visit(visit_id)
    return frappe.get_doc("CRM Visit", visit_id)


def upload(visit_id: str, file_name: str, mime_type: str, content: bytes, scanner: MalwareScanner | None = None) -> None:
    assert_capability("visit:write")
    _lock_editable_visit(visit_id)
    _validate_archive(file_name, mime_type, content, scanner)
    savepoint = f"crm_visit_meeting_upload_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    created_file = None
    try:
        created_file = save_file(file_name, content, "CRM Visit", visit_id, is_private=1)
        parsed, status, message = parse_meeting_file(file_name, content)
        existing = frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit_id}, "name")
        doc = frappe.get_doc("CRM Visit Meeting Record", existing) if existing else frappe.new_doc("CRM Visit Meeting Record")
        meeting_start, meeting_end = _meeting_range(parsed.get("meeting_time", ""))
        doc.update({"visit": visit_id, "meeting_start": meeting_start, "meeting_end": meeting_end, "purpose": parsed.get("purpose", ""), "attendees": parsed.get("attendees", ""), "agenda": parsed.get("agenda", ""), "summary": parsed.get("summary", ""), "conclusion": parsed.get("conclusion", ""), "followup": parsed.get("followup", ""), "parse_status": status, "parse_message": message, "parsed_at": now_datetime(), "manually_corrected": 0})
        doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
        _mark_record_submitted(visit_id)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        if created_file:
            try:
                created_file.delete_file()
            except Exception:
                pass
        raise


def update_record(visit_id: str, payload: dict[str, Any], expected_modified: Any = None) -> dict[str, Any]:
    assert_capability("visit:write")
    _lock_editable_visit(visit_id)
    existing = frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit_id}, "name")
    doc = frappe.get_doc("CRM Visit Meeting Record", existing) if existing else frappe.new_doc("CRM Visit Meeting Record")
    if existing:
        expected = normalize_expected_modified(expected_modified)
        if to_iso_timestamp(doc.modified) != expected:
            raise CrmApiException("VERSION_CONFLICT", "Meeting record was changed by another user.")
    savepoint = f"crm_visit_meeting_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.update({"visit": visit_id, "meeting_start": _clean(payload.get("meetingStart")), "meeting_end": _clean(payload.get("meetingEnd")), "purpose": _clean(payload.get("purpose")), "attendees": _clean(payload.get("attendees")), "agenda": _clean(payload.get("agenda")), "summary": _clean(payload.get("summary")), "conclusion": _clean(payload.get("conclusion")), "followup": _clean(payload.get("followup")), "parse_status": "Parsed", "parse_message": "会议记录已人工确认。", "parsed_at": doc.parsed_at or now_datetime(), "manually_corrected": 1})
        doc.save(ignore_permissions=True) if existing else doc.insert(ignore_permissions=True)
        _mark_record_submitted(visit_id)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return _serialize_record(doc)


def _mark_record_submitted(visit_id: str) -> None:
    visit = frappe.get_doc("CRM Visit", visit_id)
    if visit.status == "Manager Reviewed":
        raise CrmApiException("INVALID_TRANSITION", "Manager-reviewed Visit records cannot be changed.")
    if visit.status == "Visited":
        visit.status = "Minutes Submitted"
        visit.save(ignore_permissions=True)


def download(file_id: str) -> dict[str, Any]:
    assert_capability("visit:view")
    if not frappe.db.exists("File", file_id):
        raise CrmApiException("NOT_FOUND", "Meeting attachment was not found.")
    file_doc = frappe.get_doc("File", file_id)
    if file_doc.attached_to_doctype != "CRM Visit" or not file_doc.attached_to_name:
        raise CrmApiException("NOT_FOUND", "Meeting attachment was not found.")
    from rayher_crm.services.visits import _require_visit
    _require_visit(file_doc.attached_to_name)
    content = file_doc.get_content()
    return {"content": content.encode() if isinstance(content, str) else bytes(content), "file_name": file_doc.file_name, "mime_type": mimetypes.guess_type(file_doc.file_name)[0] or "application/octet-stream"}
