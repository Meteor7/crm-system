"""Frozen public CRM errors and safe error envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from functools import wraps
from typing import Any

import frappe

from rayher_crm.api.v1.responses import response_meta


CRM_ERROR_CODES = frozenset(
    {
        "UNAUTHENTICATED",
        "VALIDATION_ERROR",
        "PERMISSION_DENIED",
        "SCOPE_DENIED",
        "NOT_FOUND",
        "CONFLICT",
        "RFQ_APPROVAL_REQUIRED",
        "INVALID_TRANSITION",
        "VERSION_CONFLICT",
        "REPORT_NOT_READY",
        "BACKEND_NOT_CONNECTED",
        "NETWORK_ERROR",
        "INTERNAL_ERROR",
    }
)

_SCOPE_CODES = {"INSTALLED_TOOL_SCOPE_DENIED", "INSTALLED_TOOL_REASSIGN_DENIED"}
_PERMISSION_CODES = {"INSTALLED_TOOL_OPERATION_DENIED"}
_VALIDATION_CODES = {
    "INVALID_OWNER", "BOOKING_SOURCE_REQUIRED", "CONTACT_INACTIVE", "LINK_MISMATCH",
    "INVALID_REPORTING_LINE", "LEAD_CONVERSION_INCOMPLETE",
}
_INVALID_TRANSITION_CODES = {
    "INVALID_REPORT_STAGE", "INVALID_RUN_STAGE", "BOOKING_NOT_CONFIRMED",
    "BOOKING_SOURCE_INVALID", "BOOKING_STATUS_INVALID", "BOOKING_TYPE_INVALID", "QUOTATION_STAGE_INVALID",
}
_ACCOUNT_MISMATCH_CODES = {"CONTACT_ACCOUNT_MISMATCH", "SITE_ACCOUNT_MISMATCH", "ADDRESS_ACCOUNT_MISMATCH"}


def normalize_error_code(code: str) -> str:
    """Map legacy internal errors to the supported public contract."""

    if code in CRM_ERROR_CODES:
        return code
    if code in _SCOPE_CODES:
        return "SCOPE_DENIED"
    if code in _PERMISSION_CODES:
        return "PERMISSION_DENIED"
    if code.endswith("_NOT_FOUND"):
        return "NOT_FOUND"
    if code in _VALIDATION_CODES:
        return "VALIDATION_ERROR"
    if code in _INVALID_TRANSITION_CODES:
        return "INVALID_TRANSITION"
    if code == "EVALUATION_EXISTS":
        return "REPORT_NOT_READY"
    if (
        code in _ACCOUNT_MISMATCH_CODES
        or code == "CONTACT_MERGE_CONFLICT"
        or code == "RUN_EXISTS"
        or code.startswith("DUPLICATE_")
        or code.endswith("_EXISTS")
        or "_ALREADY_" in code
        or code.endswith("_LOCKED")
    ):
        return "CONFLICT"
    if code == "UPSTREAM_TIMEOUT":
        return "NETWORK_ERROR"
    raise ValueError(f"Unknown CRM error code: {code}")


class CrmApiException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        field_errors: Mapping[str, str] | None = None,
    ) -> None:
        code = normalize_error_code(code)
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.retryable = retryable
        self.field_errors = dict(field_errors or {})


def error_response(error: CrmApiException) -> dict[str, Any]:
    return {
        "data": None,
        "meta": response_meta(),
        "warnings": [],
        "error": {
            "code": error.code,
            "message": error.public_message,
            "retryable": error.retryable,
            "fieldErrors": error.field_errors,
        },
    }


HTTP_STATUS_BY_CODE = {
    "UNAUTHENTICATED": 401,
    "VALIDATION_ERROR": 422,
    "PERMISSION_DENIED": 403,
    "SCOPE_DENIED": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "RFQ_APPROVAL_REQUIRED": 409,
    "INVALID_TRANSITION": 409,
    "VERSION_CONFLICT": 409,
    "REPORT_NOT_READY": 409,
    "BACKEND_NOT_CONNECTED": 503,
    "NETWORK_ERROR": 503,
    "INTERNAL_ERROR": 500,
}


def api_endpoint(function):
    """Convert service exceptions to a stable public payload at the HTTP edge."""

    def unauthenticated_response():
        error = CrmApiException("UNAUTHENTICATED", "Authentication is required.")
        frappe.local.response["http_status_code"] = HTTP_STATUS_BY_CODE[error.code]
        return error_response(error)

    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except CrmApiException as error:
            frappe.local.response["http_status_code"] = HTTP_STATUS_BY_CODE.get(
                error.code,
                400,
            )
            return error_response(error)
        except frappe.AuthenticationError:
            return unauthenticated_response()
        except frappe.PermissionError:
            unauthenticated = getattr(frappe.session, "user", None) in (None, "", "Guest")
            code = "UNAUTHENTICATED" if unauthenticated else "PERMISSION_DENIED"
            message = "Authentication is required." if unauthenticated else "The current user is not permitted to perform this operation."
            error = CrmApiException(code, message)
            frappe.local.response["http_status_code"] = HTTP_STATUS_BY_CODE[code]
            return error_response(error)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Rayher CRM API failure")
            error = CrmApiException("INTERNAL_ERROR", "The request could not be completed.", retryable=True)
            frappe.local.response["http_status_code"] = 500
            return error_response(error)

    return wrapped
