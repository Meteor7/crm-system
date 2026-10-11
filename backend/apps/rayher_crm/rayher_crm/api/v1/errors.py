"""Frozen public CRM errors and safe error envelopes."""

from __future__ import annotations

import re
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


PHONE_NUMBER_MESSAGE = "The phone number is not valid: use at most 20 characters from digits, spaces and + - ( ) , . # *."
EMAIL_ADDRESS_MESSAGE = "The email address is not valid."
NAME_CHARACTERS_MESSAGE = "The name cannot contain < or >."
VALUE_TOO_LONG_MESSAGE = "A value is too long."
_NUMBER_FIELD_TYPES = frozenset({"Int", "Long Int", "Float", "Currency", "Percent", "Check", "Rating", "Duration"})


def _raising_frame_locals(error: BaseException, function_name: str) -> Mapping[str, Any]:
    """Local variables of the innermost `function_name` call on the way to where `error` was raised."""

    found: Mapping[str, Any] = {}
    traceback = error.__traceback__
    while traceback is not None:
        if traceback.tb_frame.f_code.co_name == function_name:
            found = traceback.tb_frame.f_locals
        traceback = traceback.tb_next
    return found


def input_error(error: BaseException) -> CrmApiException | None:
    """The public error for a value that Frappe refused on save, or None when `error` is anything else.

    The services check what the CRM itself defines. Frappe then checks every document once more when
    it is saved: the length of each column, the Phone and Email formats of the standard fields, the
    characters a document name may contain. Such a refusal is about what the user typed, so it is
    answered like any other validation error, with a message that says what to change, and not as a
    server failure the user is invited to retry.

    Frappe words its own message in the language of the session and repeats the refused value in
    it, so the field and the limit are read from the frame that raised, not from that text.
    """

    if is_too_long(error) and not isinstance(error, frappe.CharacterLengthExceededError):
        # The database refused a value Frappe does not measure, such as a document name.
        return CrmApiException("VALIDATION_ERROR", VALUE_TOO_LONG_MESSAGE)
    if isinstance(error, frappe.CharacterLengthExceededError):
        raised = _raising_frame_locals(error, "throw_length_exceeded_error")
        field, limit = raised.get("df"), raised.get("max_length")
        label = getattr(field, "label", None)
        if (
            isinstance(label, str) and label.strip() and isinstance(limit, int)
            and getattr(field, "fieldtype", None) not in _NUMBER_FIELD_TYPES
        ):
            return CrmApiException("VALIDATION_ERROR", f"{label.strip()} is too long: at most {limit} characters.")
        return CrmApiException("VALIDATION_ERROR", VALUE_TOO_LONG_MESSAGE)
    if isinstance(error, frappe.InvalidPhoneNumberError):
        return CrmApiException("VALIDATION_ERROR", PHONE_NUMBER_MESSAGE)
    if isinstance(error, frappe.InvalidEmailAddressError):
        return CrmApiException("VALIDATION_ERROR", EMAIL_ADDRESS_MESSAGE)
    if isinstance(error, frappe.NameError) and not isinstance(error, frappe.DuplicateEntryError):
        # NameError has other causes that are the server's own; only this one is the user's input.
        name = _raising_frame_locals(error, "validate_name").get("name")
        if isinstance(name, str) and re.search("[<>]", name):
            return CrmApiException("VALIDATION_ERROR", NAME_CHARACTERS_MESSAGE)
    return None


def is_too_long(error: BaseException) -> bool:
    """Whether `error` says a value does not fit: Frappe's own check, or the database's."""

    if isinstance(error, frappe.CharacterLengthExceededError):
        return True
    return isinstance(error, frappe.db.DataError) and frappe.db.is_data_too_long(error)


def api_endpoint(function):
    """Convert service exceptions to a stable public payload at the HTTP edge."""

    def unauthenticated_response():
        error = CrmApiException("UNAUTHENTICATED", "Authentication is required.")
        frappe.local.response["http_status_code"] = HTTP_STATUS_BY_CODE[error.code]
        return error_response(error)

    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            from rayher_crm.services.upload_deadline import upload_transaction
            with upload_transaction():
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
        except frappe.TimestampMismatchError:
            # Frappe's own version check on save (a locking read of `modified`): the record was written by another
            # request after this one read it. The same answer as the services' own check (`lock_document`), not a
            # server failure: the client reads the record again before it tries again.
            frappe.db.rollback()
            frappe.clear_last_message()
            error = CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
            frappe.local.response["http_status_code"] = HTTP_STATUS_BY_CODE[error.code]
            return error_response(error)
        except Exception as failure:
            frappe.db.rollback()
            refused = input_error(failure)
            if refused:
                if is_too_long(failure):
                    # The value may be one a service put together and not one the user typed, and
                    # then the service is what has to change: keep it where a developer looks.
                    frappe.log_error(title="Rayher CRM value too long on save")
                frappe.local.response["http_status_code"] = HTTP_STATUS_BY_CODE[refused.code]
                return error_response(refused)
            frappe.log_error(title="Rayher CRM API failure")
            error = CrmApiException("INTERNAL_ERROR", "The request could not be completed.", retryable=True)
            frappe.local.response["http_status_code"] = 500
            return error_response(error)

    return wrapped
