"""Fail-closed upload validation and ClamAV INSTREAM client."""

from __future__ import annotations

import io
import os
import socket
import struct
import zipfile
from pathlib import PurePath
from typing import Protocol

from rayher_crm.api.v1.errors import CrmApiException


MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FILES_PER_REQUEST = 10
MAX_REQUEST_BYTES = 100 * 1024 * 1024
MAX_DOCX_ENTRIES = 500
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
TIPRAY_HEADER = b"%TSD-Header-###%"

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
    """Minimal ClamAV INSTREAM client; any unavailable/unknown result fails closed."""

    def __init__(self, host: str | None = None, port: int | None = None, timeout: float = 10.0):
        self.host = host or os.environ.get("CRM_CLAMD_HOST", "clamav")
        self.port = port or int(os.environ.get("CRM_CLAMD_PORT", "3310"))
        self.timeout = timeout

    def scan(self, content: bytes) -> bool:
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as connection:
            connection.settimeout(self.timeout)
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(content), 64 * 1024):
                chunk = content[offset:offset + 64 * 1024]
                connection.sendall(struct.pack(">I", len(chunk)) + chunk)
            connection.sendall(struct.pack(">I", 0))
            response = bytearray()
            while len(response) < 4096:
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


def _docx_is_valid(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_DOCX_ENTRIES:
                return False
            total = 0
            names = set()
            for info in infos:
                path = PurePath(info.filename)
                if info.flag_bits & 0x1 or path.is_absolute() or ".." in path.parts:
                    return False
                total += info.file_size
                if total > MAX_DOCX_UNCOMPRESSED_BYTES:
                    return False
                names.add(info.filename)
            return {"[Content_Types].xml", "word/document.xml"}.issubset(names)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def _xlsx_is_valid(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_DOCX_ENTRIES:
                return False
            total = 0
            names = set()
            for info in infos:
                path = PurePath(info.filename)
                if info.flag_bits & 0x1 or path.is_absolute() or ".." in path.parts:
                    return False
                total += info.file_size
                if total > MAX_DOCX_UNCOMPRESSED_BYTES:
                    return False
                names.add(info.filename)
            lowered = {name.lower() for name in names}
            return (
                {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names)
                and not any(name.endswith("vbaproject.bin") for name in lowered)
            )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def _pptx_is_valid(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_DOCX_ENTRIES:
                return False
            total = 0
            names = set()
            for info in infos:
                path = PurePath(info.filename)
                if info.flag_bits & 0x1 or path.is_absolute() or ".." in path.parts:
                    return False
                total += info.file_size
                if total > MAX_DOCX_UNCOMPRESSED_BYTES:
                    return False
                names.add(info.filename)
            lowered = {name.lower() for name in names}
            return (
                {"[Content_Types].xml", "ppt/presentation.xml"}.issubset(names)
                and not any(name.endswith("vbaproject.bin") for name in lowered)
            )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def detect_mime(content: bytes, file_name: str | None = None) -> str | None:
    if content.startswith(b"%PDF-"):
        return PDF_MIME
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG_MIME
    if content.startswith(b"\xff\xd8\xff"):
        return JPEG_MIME
    if content.startswith(b"PK\x03\x04") and _docx_is_valid(content):
        return DOCX_MIME
    if content.startswith(b"PK\x03\x04") and _xlsx_is_valid(content):
        return XLSX_MIME
    if content.startswith(b"PK\x03\x04") and _pptx_is_valid(content):
        return PPTX_MIME
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
        clean = (scanner or ClamdScanner()).scan(content)
    except CrmApiException:
        raise
    except Exception as exc:
        raise CrmApiException("INTERNAL_ERROR", "File security scanner is unavailable.", retryable=True) from exc
    if not clean:
        raise CrmApiException("VALIDATION_ERROR", "File failed malware screening.")
    return actual_mime
