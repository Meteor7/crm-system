"""Whitelisted Evaluation, Test Run, and workflow endpoints."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import api_endpoint
from rayher_crm.api.v1.responses import success_response
from rayher_crm.services import evaluations
from rayher_crm.services import demo_reports
from rayher_crm.services.common import as_payload


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_evaluations(**query) -> dict:
    items, total, page, page_size = evaluations.list_evaluations(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_evaluation(id: str) -> dict:
    return success_response(evaluations.get_evaluation(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def complete_evaluation_preparation(
    id: str, branch: str, expectedModified: str,
) -> dict:
    return success_response(
        evaluations.complete_evaluation_preparation(id, branch, expectedModified)
    )


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_evaluation_status(id: str, command: Any, expectedModified: str | None = None) -> dict:
    return success_response(evaluations.update_evaluation_status(id, as_payload(command), expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def terminate_evaluation(id: str, reason: str, expectedModified: str | None = None) -> dict:
    return success_response(evaluations.terminate_evaluation(id, {"reason": reason}, expectedModified))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def add_evaluation_run(id: str, input: Any) -> dict:
    return success_response(evaluations.add_evaluation_run(id, as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def update_evaluation_run(id: str, runId: str, input: Any) -> dict:
    return success_response(evaluations.update_evaluation_run(id, runId, as_payload(input)))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def cancel_evaluation_run(id: str, runId: str, input: Any) -> dict:
    return success_response(evaluations.cancel_evaluation_run(id, runId, as_payload(input)))


@frappe.whitelist(methods=["POST", "PUT"])
@api_endpoint
def set_evaluation_test_run_deadline(id: str, input: Any) -> dict:
    return success_response(evaluations.set_evaluation_test_run_deadline(id, as_payload(input)))


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_demo_workflows(**query) -> dict:
    items, total, page, page_size = evaluations.list_demo_workflows(query)
    return success_response({"items": items}, page=page, pageSize=page_size, total=total)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_demo_workflow(id: str) -> dict:
    return success_response(evaluations.get_demo_workflow(id))


@frappe.whitelist(methods=["POST"])
@api_endpoint
def release_demo_test_report(id: str, expectedRound: str | None = None) -> dict:
    internal = frappe.request.files.get("internalFile")
    external = frappe.request.files.get("externalFile")
    if internal is None or external is None:
        from rayher_crm.api.v1.errors import CrmApiException
        raise CrmApiException("VALIDATION_ERROR", "Internal and External Test Report files are required.")

    def part(upload):
        return {
            "file_name": upload.filename,
            "mime_type": upload.mimetype,
            "content": upload.stream.read(demo_reports.MAX_FILE_BYTES + 1),
        }

    return success_response(
        demo_reports.release_demo_test_report(id, part(internal), part(external), expected_round=expectedRound),
    )


@frappe.whitelist(methods=["POST"])
@api_endpoint
def upload_customer_report(id: str, expectedRound: str | None = None) -> dict:
    upload = frappe.request.files.get("file")
    if upload is None:
        from rayher_crm.api.v1.errors import CrmApiException
        raise CrmApiException("VALIDATION_ERROR", "A Customer Report file is required.")

    return success_response(demo_reports.upload_customer_report(id, {
        "file_name": upload.filename,
        "mime_type": upload.mimetype,
        "content": upload.stream.read(demo_reports.MAX_FILE_BYTES + 1),
    }, expected_round=expectedRound))
