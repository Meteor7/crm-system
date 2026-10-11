"""Frappe's WSGI entry point with upload timing and final-refusal responses."""

import json
import time

import frappe
from frappe.app import application as frappe_application, after_response_wrapper, process_response
from werkzeug.wrappers import Response

from rayher_crm.api.v1.errors import HTTP_STATUS_BY_CODE, error_response
from rayher_crm.services.upload_deadline import REQUEST_STARTED_ENV, UploadExpired


def application(environ, start_response):
    # Server-owned WSGI data, not a client header. Capture this BEFORE Frappe
    # constructs its Request, parses multipart bodies, or authenticates the user.
    environ[REQUEST_STARTED_ENV] = time.monotonic()
    try:
        return frappe_application(environ, start_response)
    except UploadExpired as error:
        # Frappe 15 commits outside application()'s exception handler. The guard
        # has already rolled back; the API decorator cannot see this refusal.
        try:
            response = Response(
                json.dumps({"message": error_response(error)}),
                status=HTTP_STATUS_BY_CODE[error.code], content_type="application/json",
            )
            response.headers["Cache-Control"] = "no-store"
            process_response(response)
            # Frappe never returned its own ClosingIterator on this exception.
            return after_response_wrapper(response)(environ, start_response)
        except BaseException:
            frappe.destroy()
            raise
    except BaseException:
        # Match the cleanup that Frappe's successful response iterator owns.
        frappe.destroy()
        raise
