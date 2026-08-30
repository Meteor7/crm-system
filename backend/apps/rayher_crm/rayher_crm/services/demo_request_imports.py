"""Extract fields from completed PDF or DOCX Demo Request forms."""

from __future__ import annotations

from io import BytesIO
import re
from typing import Any
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from rayher_crm.services.file_security import MAX_DOCX_ENTRIES, MAX_DOCX_UNCOMPRESSED_BYTES, validate_and_scan


MAX_FILE_BYTES = 100 * 1024 * 1024
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WORD_NS = {"w": WORD_NAMESPACE}

FIELD_LABELS = {
    "Company Name": "companyName",
    "Contact Person": "contactPerson",
    "Industry": "industry",
    "Sales Contact": "salesContact",
    "Demo Owner": "demoOwner",
    "Size & Shape": "sizeShape",
    "Material (Substrate)": "material",
    "Specific Request": "specificRequest",
    "What to Detect / Measure": "detectMeasure",
    "Expected Results": "expectedResults",
    "Other Tools": "otherTools",
    "Primary Tool": "primaryTool",
    "Complementary Tool": "complementaryTool",
    "Timing": "timing",
    "Key Success Factors": "keySuccessFactors",
    "Internal Questions": "internalQuestions",
    "Questions for Customer": "customerQuestions",
}

HELP_TEXT = {
    "Contact Person": "Name, title, email, phone",
    "Industry": "e.g. Frontend Fab, Power devices, MEMS, Photonics, Advanced Packaging etc.",
    "Sales Contact": "Sales dept contact for this demo",
    "Demo Owner": "R&D or Applications engineer responsible",
    "Size & Shape": "Diameter, thickness, warpage, notch or flat(s), shape...",
    "Material (Substrate)": "Including crystal orientation (e.g. Si(100), GaN-on-Si, SiC 4H, etc.) Especially for substrate demo",
    "Specific Request": "e.g. surface contact handling, edge exclusion, backside constraints...",
    "What to Detect / Measure": "Defect type, typical size, density, location on wafer...",
    "Expected Results": "Pictures, dimensions, tool performance, report files...",
    "Other Tools": "Competitors, tool of record, other solutions currently used",
    "Primary Tool": "Tool selected based on discussion with customer",
    "Complementary Tool": "To demonstrate additional capabilities or for internal learning (optional)",
    "Timing": "Proposed schedule taking into account customer expectations",
    "Key Success Factors": "What should we focus on to make sure we address the right objective?",
}

WAFER_HEADERS = [
    "Slot ID", "WID", "Wafer Specificity", "Notch / Flat",
    "DOI / Metrology Items", "Result File Provided",
]
WAFER_KEYS = [
    "slotId", "wid", "waferSpecificity", "notchFlat",
    "doiMetrologyItems", "resultFileProvided",
]
STOP_LABELS = {
    "Customer Information", "Owner Information", "Sample Information", "Sample Information (see next page for details)",
    "Number of Wafers", "Demo Purpose", "Our Proposal", "Our Proposal (to be completed during demo introduction meeting)",
    "What Will Make Us Winning", "Open Questions", "Wafer Details", "Prepared by", "Approved by",
    *WAFER_HEADERS,
}


def _empty_form() -> dict[str, Any]:
    return {
        "contactPerson": "", "industry": "", "salesContact": "", "demoOwner": "",
        "sizeShape": "", "material": "", "specificRequest": "", "detectMeasure": "",
        "expectedResults": "", "otherTools": "", "primaryTool": "", "complementaryTool": "",
        "timing": "", "keySuccessFactors": "", "internalQuestions": "", "customerQuestions": "",
        "wafers": [],
    }


def _clean(value: str) -> str:
    return re.sub(r"[ \t\f\v]+", " ", value.replace("\u00a0", " ")).strip()


def _usable_value(label: str, value: str) -> str:
    cleaned = _clean(value)
    return "" if cleaned.casefold() == HELP_TEXT.get(label, "").casefold() else cleaned


def _result(file_name: str = "") -> dict[str, Any]:
    return {"fileName": file_name, "companyName": "", "formData": _empty_form(), "detectedFields": []}


def _set_field(result: dict[str, Any], label: str, value: str) -> None:
    value = _usable_value(label, value)
    if not value:
        return
    key = FIELD_LABELS[label]
    if key == "companyName":
        result[key] = value
    else:
        result["formData"][key] = value
    if key not in result["detectedFields"]:
        result["detectedFields"].append(key)


def _node_text(node: ElementTree.Element) -> str:
    return _clean("".join(part.text or "" for part in node.findall(".//w:t", WORD_NS)))


def _docx_tables(content: bytes) -> list[list[list[str]]]:
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_DOCX_ENTRIES:
                raise ValueError("The DOCX file contains too many archive entries.")
            if sum(max(0, info.file_size) for info in infos) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("The DOCX file is too large after decompression.")
            document = archive.read("word/document.xml")
    except (BadZipFile, KeyError) as error:
        raise ValueError("The DOCX file is malformed or missing its document body.") from error
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as error:
        raise ValueError("The DOCX document XML is malformed.") from error
    tables: list[list[list[str]]] = []
    for table in root.findall(".//w:tbl", WORD_NS):
        rows: list[list[str]] = []
        for row in table.findall("./w:tr", WORD_NS):
            rows.append([_node_text(cell) for cell in row.findall("./w:tc", WORD_NS)])
        tables.append(rows)
    return tables


def _parse_docx(content: bytes) -> dict[str, Any]:
    result = _result()
    for table in _docx_tables(content):
        for row in table:
            if len(row) >= 2 and row[0] in FIELD_LABELS:
                _set_field(result, row[0], row[1])
        header_index = next((index for index, row in enumerate(table) if row[:6] == WAFER_HEADERS), -1)
        if header_index < 0:
            continue
        wafers = []
        for row in table[header_index + 1:]:
            values = [_clean(value) for value in (row + [""] * 6)[:6]]
            if any(values):
                wafers.append(dict(zip(WAFER_KEYS, values)))
        if wafers:
            result["formData"]["wafers"] = wafers
            result["detectedFields"].append("wafers")
    return result


def _line_marker(line: str) -> tuple[str | None, str]:
    candidates = sorted((*FIELD_LABELS, *STOP_LABELS), key=len, reverse=True)
    folded = line.casefold()
    for label in candidates:
        label_folded = label.casefold()
        if folded == label_folded:
            return label, ""
        if folded.startswith(label_folded):
            remainder = line[len(label):]
            if remainder and (remainder[0].isspace() or remainder[0] in ":-"):
                return label, remainder.lstrip(" :-")
    return None, ""


def _text_wafers(lines: list[str]) -> list[dict[str, str]]:
    header_positions = []
    search_from = 0
    for header in WAFER_HEADERS:
        position = next((index for index in range(search_from, len(lines)) if lines[index].casefold() == header.casefold()), -1)
        if position < 0:
            return []
        header_positions.append(position)
        search_from = position + 1
    values = []
    for line in lines[header_positions[-1] + 1:]:
        marker, _ = _line_marker(line)
        if marker in {"Prepared by", "Approved by"}:
            break
        if marker is None:
            values.append(line)
    wafers = []
    for start in range(0, len(values) - 5, 6):
        row = values[start:start + 6]
        if any(row):
            wafers.append(dict(zip(WAFER_KEYS, row)))
    return wafers


def parse_drf_text(text: str) -> dict[str, Any]:
    """Parse PDF-extracted text using the stable labels in the approved DRF template."""

    lines = [_clean(line) for line in text.replace("\r", "\n").split("\n") if _clean(line)]
    result = _result()
    current_label: str | None = None
    captured: dict[str, list[str]] = {}
    for line in lines:
        marker, remainder = _line_marker(line)
        if marker:
            current_label = marker if marker in FIELD_LABELS else None
            if current_label and remainder:
                captured.setdefault(current_label, []).append(remainder)
            continue
        if current_label:
            captured.setdefault(current_label, []).append(line)
    for label, values in captured.items():
        _set_field(result, label, "\n".join(values))
    wafers = _text_wafers(lines)
    if wafers:
        result["formData"]["wafers"] = wafers
        result["detectedFields"].append("wafers")
    return result


def _pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore[no-redef]
        except ImportError as error:
            raise ValueError("PDF extraction support is unavailable on the server.") from error
    try:
        reader = PdfReader(BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as error:
        raise ValueError("The PDF file could not be read.") from error
    if not text.strip():
        raise ValueError("The PDF contains no selectable text; scanned images are not supported.")
    return text


def import_demo_request_form(file_name: str, mime_type: str, content: bytes) -> dict[str, Any]:
    """Validate, extract and map one externally completed DRF file."""

    actual_mime = validate_and_scan(file_name, mime_type, content)
    if actual_mime not in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}:
        raise ValueError("Only PDF or DOCX Demo Request forms are supported.")
    if not content:
        raise ValueError("The uploaded file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("The uploaded file exceeds the 100 MiB limit.")
    suffix = file_name.rsplit(".", 1)[-1].casefold() if "." in file_name else ""
    expected_suffix = "pdf" if actual_mime == "application/pdf" else "docx"
    if suffix != expected_suffix:
        raise ValueError("The file extension does not match its content.")
    if suffix == "docx":
        result = _parse_docx(content)
    elif suffix == "pdf":
        result = parse_drf_text(_pdf_text(content))
    else:
        raise ValueError("Only PDF or DOCX Demo Request forms are supported.")
    result["fileName"] = file_name
    if not result["detectedFields"]:
        raise ValueError("No recognizable Demo Request fields were found in the file.")
    return result
