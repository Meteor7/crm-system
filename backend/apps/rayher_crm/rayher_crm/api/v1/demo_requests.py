"""Whitelisted Demo Request and Comment endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException, api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.permissions.roles import assert_capability
from rayher_crm.services import demo_request_imports, demo_requests
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_demo_requests(**query) -> dict:
    items, total, page, page_size = demo_requests.list_demo_requests(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_demo_request(id: str) -> dict:
    return success_response(demo_requests.get_demo_request(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def import_form() -> dict:
    # CRM roles no longer hold table-level create/write (they write through the services),
    # so the gate is the same capability that creating a Demo Request requires.
    assert_capability("demo_request:create")
    uploads = frappe.request.files.getlist("file")
    if len(uploads) != 1:
        raise CrmApiException("VALIDATION_ERROR", "Exactly one PDF or DOCX file is required.")
    upload = uploads[0]
    content = upload.stream.read(demo_request_imports.MAX_FILE_BYTES + 1)
    try:
        result = demo_request_imports.import_demo_request_form(
            upload.filename or "",
            upload.mimetype or "",
            content,
        )
    except ValueError as error:
        raise CrmApiException("VALIDATION_ERROR", str(error)) from error
    return success_response(result)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_demo_request(input: Any) -> dict:
    return success_response(demo_requests.create_demo_request(as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_demo_request(id: str, input: Any, expectedModified: str | None = None) -> dict:
    return success_response(demo_requests.update_demo_request(id, as_payload(input), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def transition_demo_request(id: str, command: Any, expectedModified: str | None = None) -> dict:
    return success_response(
        demo_requests.transition_demo_request(id, as_payload(command), expectedModified)
    )


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_demo_comments(demoRequestId: str, **query) -> dict:
    items, total, page, page_size = demo_requests.list_demo_comments(demoRequestId, query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def add_demo_comment(demoRequestId: str, input: Any) -> dict:
    return success_response(demo_requests.add_demo_comment(demoRequestId, as_payload(input)))
