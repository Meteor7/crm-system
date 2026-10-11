"""Fail-closed upload validation and ClamAV INSTREAM client."""

from __future__ import annotations

import io
import os
import socket
import struct
import time
import zipfile
from pathlib import PurePath
from typing import Protocol

import frappe

from rayher_crm.api.v1.errors import CrmApiException


MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FILES_PER_REQUEST = 10
MAX_REQUEST_BYTES = 100 * 1024 * 1024
# A real deck can contain thousands of parts. This is a document complexity limit,
# not proof that ClamAV completed its scan: nested content consumes its own limits.
# The deployed scanner must reject exceeded limits (AlertExceedsMax).
MAX_DOCX_ENTRIES = 5_000
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
TIPRAY_HEADER = b"%TSD-Header-###%"
SCAN_TIMEOUT_SECONDS = 60.0
CONNECT_TIMEOUT_SECONDS = 5.0
# Non-HTTP callers using a request context retain a scan budget. Multipart HTTP
# requests share upload_deadline's preparation budget with conversion as well.
REQUEST_SCAN_BUDGET_SECONDS = 90.0
SCAN_BUDGET_MESSAGE = "These files take too long to scan in one upload. Upload fewer at a time."

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
CSV_MIME = "text/csv"
TXT_MIME = "text/plain"
PNG_MIME = "image/png"
JPEG_MIME = "image/jpeg"
EXTENSION_FOR_MIME = {
    PDF_MIME: ".pdf", DOCX_MIME: ".docx", XLSX_MIME: ".xlsx", PPTX_MIME: ".pptx",
    CSV_MIME: ".csv", TXT_MIME: ".txt", PNG_MIME: ".png", JPEG_MIME: ".jpg",
}


class MalwareScanner(Protocol):
    def scan(self, content: bytes) -> bool: ...


class ClamdScanner:
    """Minimal ClamAV INSTREAM client; any unavailable/unknown result fails closed.

    `timeout` bounds the whole scan, not each read: clamd answers only once the whole file is scanned, and a 30 MB
    deck of 3,092 parts takes about 25 s.
    """

    def __init__(self, host: str | None = None, port: int | None = None, timeout: float = SCAN_TIMEOUT_SECONDS):
        self.host = host or os.environ.get("CRM_CLAMD_HOST", "clamav")
        self.port = port or int(os.environ.get("CRM_CLAMD_PORT", "3310"))
        self.timeout = timeout

    def scan(self, content: bytes) -> bool:
        deadline = time.monotonic() + self.timeout

        def left() -> float:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("The ClamAV scan ran past its deadline.")
            return remaining

        with socket.create_connection((self.host, self.port), timeout=min(CONNECT_TIMEOUT_SECONDS, left())) as connection:
            connection.settimeout(left())
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(content), 64 * 1024):
                chunk = content[offset:offset + 64 * 1024]
                connection.settimeout(left())
                connection.sendall(struct.pack(">I", len(chunk)) + chunk)
            connection.settimeout(left())
            connection.sendall(struct.pack(">I", 0))
            response = bytearray()
            while len(response) < 4096:
                connection.settimeout(left())
                chunk = connection.recv(4096 - len(response))
                if not chunk:
                    break
                response.extend(chunk)
                if b"\0" in chunk:
                    break
        message = bytes(response).rstrip(b"\0\n").decode("utf-8", "replace")
        if message.endswith(" OK"):
            return True
        if message.endswith(" FOUND"):
            return False
        raise RuntimeError("ClamAV returned an unknown scan result")


def _request_scan_budget() -> float | None:
    """Seconds left for scanning in this web request, counted from its first scan; None outside a request."""

    from rayher_crm.services.upload_deadline import current_upload
    if held := current_upload():
        return held.remaining(preparation=True)
    request = getattr(frappe.local, "request", None)
    if request is None:
        return None
    # Kept with the request it belongs to: a process that reuses frappe.local (a test run) starts a new one.
    held = getattr(frappe.local, "crm_scan_deadline", None)
    if held is None or held[0] is not request:
        held = frappe.local.crm_scan_deadline = (request, time.monotonic() + REQUEST_SCAN_BUDGET_SECONDS)
    return held[1] - time.monotonic()


def scan_content(content: bytes, scanner: MalwareScanner | None = None) -> bool:
    """Scan with `scanner`, or with clamd in what is left of the request's scan budget.

    Files of one request are scanned one after another before anything is written, so a request that runs out
    of budget is refused whole and can be sent again in smaller parts.
    """

    if scanner is not None:
        from rayher_crm.services.upload_deadline import check_preparation
        check_preparation()
        clean = scanner.scan(content)
        check_preparation()
        return clean
    budget = _request_scan_budget()
    if budget is None:
        return ClamdScanner().scan(content)
    if budget <= 0:
        raise CrmApiException("VALIDATION_ERROR", SCAN_BUDGET_MESSAGE)
    started = time.monotonic()
    try:
        return ClamdScanner(timeout=min(SCAN_TIMEOUT_SECONDS, budget)).scan(content)
    except TimeoutError as error:
        # Only the budget, not clamd itself, cut this scan short: the user can do something about that.
        if budget < SCAN_TIMEOUT_SECONDS and time.monotonic() - started >= budget:
            raise CrmApiException("VALIDATION_ERROR", SCAN_BUDGET_MESSAGE) from error
        raise


OFFICE_DOCUMENT_PARTS = (
    (DOCX_MIME, "word/document.xml"),
    (XLSX_MIME, "xl/workbook.xml"),
    (PPTX_MIME, "ppt/presentation.xml"),
)
OFFICE_TOO_MANY_PARTS_MESSAGE = '"{file_name}" has more than {limit} internal parts. Save it as PDF, or split it, and upload again.'
OFFICE_TOO_LARGE_MESSAGE = '"{file_name}" is larger than {limit} MiB once decompressed. Compress its images or save it as PDF, and upload again.'


def _office_mime(content: bytes, file_name: str) -> str | None:
    """Name the Office type of a ZIP upload, or None when it is not a well-formed Office file.

    The type comes from the part list, so only a file that is an Office file can fail on its size, and that
    failure names the file and the limit instead of reading as a wrong file type.
    """

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return None
    names = {info.filename for info in infos}
    mime = next((mime for mime, part in OFFICE_DOCUMENT_PARTS if part in names), None)
    if mime is None or "[Content_Types].xml" not in names:
        return None
    for info in infos:
        path = PurePath(info.filename)
        if info.flag_bits & 0x1 or path.is_absolute() or ".." in path.parts:
            return None
    if mime != DOCX_MIME and any(name.lower().endswith("vbaproject.bin") for name in names):
        return None
    if len(infos) > MAX_DOCX_ENTRIES:
        raise CrmApiException(
            "VALIDATION_ERROR", OFFICE_TOO_MANY_PARTS_MESSAGE.format(file_name=file_name, limit=MAX_DOCX_ENTRIES)
        )
    if sum(info.file_size for info in infos) > MAX_DOCX_UNCOMPRESSED_BYTES:
        raise CrmApiException(
            "VALIDATION_ERROR",
            OFFICE_TOO_LARGE_MESSAGE.format(file_name=file_name, limit=MAX_DOCX_UNCOMPRESSED_BYTES // (1024 * 1024)),
        )
    return mime


def detect_mime(content: bytes, file_name: str | None = None) -> str | None:
    if content.startswith(b"%PDF-"):
        return PDF_MIME
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG_MIME
    if content.startswith(b"\xff\xd8\xff"):
        return JPEG_MIME
    if content.startswith(b"PK\x03\x04"):
        office_mime = _office_mime(content, file_name or "")
        if office_mime:
            return office_mime
    extension = os.path.splitext(file_name or "")[1].lower()
    if extension in {".csv", ".txt"} and b"\0" not in content:
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return CSV_MIME if extension == ".csv" else TXT_MIME
    return None


PDF_UNREADABLE_MESSAGE = "The PDF file could not be read."
PDF_SCRIPT_MESSAGE = "The PDF contains scripts and cannot be uploaded."


def _assert_storable_pdf(content: bytes) -> None:
    """Refuse a PDF that Frappe would refuse when the file is saved.

    File.check_content opens every PDF to look for scripts. A PDF it cannot open raises from inside
    the save, and one that carries a script is refused there; both reached the user as a server
    failure. The same check runs here first, so each gets a message of its own.
    """

    from frappe.utils.pdf import pdf_contains_js

    try:
        scripted = pdf_contains_js(content)
    except Exception as error:
        raise CrmApiException("VALIDATION_ERROR", PDF_UNREADABLE_MESSAGE) from error
    if scripted:
        raise CrmApiException("VALIDATION_ERROR", PDF_SCRIPT_MESSAGE)


def validate_and_scan(file_name: str, claimed_mime: str, content: bytes, scanner: MalwareScanner | None = None) -> str:
    if not isinstance(content, bytes) or not content:
        raise CrmApiException("VALIDATION_ERROR", "File content is required.")
    if len(content) > MAX_FILE_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "File exceeds the 100 MiB limit.")
    if not isinstance(file_name, str) or not file_name.strip() or len(file_name) > 180:
        raise CrmApiException("VALIDATION_ERROR", "File name is invalid.")
    normalized = file_name.strip()
    if (
        normalized != os.path.basename(normalized)
        or any(char in normalized for char in ("/", "\\"))
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise CrmApiException("VALIDATION_ERROR", "File name is invalid.")

    if content.startswith(TIPRAY_HEADER):
        actual_mime = claimed_mime if claimed_mime in EXTENSION_FOR_MIME else None
    else:
        actual_mime = detect_mime(content, normalized)
    if not actual_mime:
        raise CrmApiException("VALIDATION_ERROR", "File type is not allowed or does not match its magic bytes.")
    extension = os.path.splitext(normalized)[1].lower()
    allowed_extensions = {".jpg", ".jpeg"} if actual_mime == JPEG_MIME else {EXTENSION_FOR_MIME[actual_mime]}
    if extension not in allowed_extensions or claimed_mime != actual_mime:
        raise CrmApiException("VALIDATION_ERROR", "File extension or MIME does not match its content.")
    # A Tipray-encrypted file is opaque: there is no PDF here to open.
    if actual_mime == PDF_MIME and not content.startswith(TIPRAY_HEADER):
        _assert_storable_pdf(content)

    try:
        clean = scan_content(content, scanner)
    except CrmApiException:
        raise
    except Exception as exc:
        raise CrmApiException("INTERNAL_ERROR", "File security scanner is unavailable.", retryable=True) from exc
    if not clean:
        raise CrmApiException("VALIDATION_ERROR", "File failed malware screening.")
    return actual_mime
