from __future__ import annotations

import hashlib
from io import BytesIO
from unittest.mock import patch

import frappe
from pypdf import PdfWriter

from rayher_crm.setup import controlled_documents


def install_test_controlled_documents() -> None:
    document_id = controlled_documents.ACONCA_DOCUMENT_ID
    if frappe.db.exists("CRM Controlled Document", document_id):
        document = frappe.get_doc("CRM Controlled Document", document_id)
        stale_files = [document.private_file, document.preview_file]
        frappe.db.set_value(
            "CRM Controlled Document",
            document_id,
            {"private_file": None, "preview_file": None},
            update_modified=False,
        )
        for file_name in stale_files:
            if file_name and frappe.db.exists("File", file_name):
                frappe.db.delete("File", {"name": file_name})

    source = b"PK\x03\x04test-controlled-presentation"
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(19):
        writer.add_blank_page(width=612, height=792)
    writer.write(output)
    preview = output.getvalue()

    # Tests create their own in-memory source; production no longer bundles demo documents.
    spec = {
        "document_id": document_id,
        "title": "Test Controlled Presentation",
        "product": "Test Product",
        "applicable_tool": "Test Tool",
        "file_name": "test-controlled-presentation.pptx",
        "preview_file_name": "test-controlled-presentation.pdf",
        "version": "test",
        "revision": "R1",
        "content_hash": hashlib.sha256(source).hexdigest(),
        "preview_content_hash": hashlib.sha256(preview).hexdigest(),
    }
    assets = {
        spec["file_name"]: source,
        spec["preview_file_name"]: preview,
    }
    with (
        patch.object(controlled_documents, "APPROVED_DOCUMENTS", (spec,)),
        patch.object(controlled_documents, "_verified_asset", side_effect=lambda name, _hash: assets[name]),
    ):
        controlled_documents.install_approved_controlled_documents()
