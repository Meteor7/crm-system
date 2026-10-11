"""One deadline for a multipart CRM request, including preparation and transaction writes."""

from contextlib import contextmanager
import time

import frappe

from rayher_crm.api.v1.errors import CrmApiException


# Both nginx layers wait 120 seconds. Leave time for rollback and the response;
# preparation must also leave time for the short transaction which follows it.
UPLOAD_TIMEOUT_SECONDS = 105.0
PREPARATION_TIMEOUT_SECONDS = 90.0
DATABASE_WAIT_SECONDS = 5
UPLOAD_TIMEOUT_MESSAGE = "The upload could not finish in time. Nothing was saved. Please try again with fewer files."
REQUEST_STARTED_ENV = "rayher_crm.request_started"


class UploadExpired(CrmApiException):
    def __init__(self):
        super().__init__("VALIDATION_ERROR", UPLOAD_TIMEOUT_MESSAGE)


class UploadDeadline:
    def __init__(self, request):
        self.request = request
        # Direct service/unit-test calls have no WSGI environment. The deployed
        # entry point supplies monotonic time from before Frappe parses the body.
        self.started = getattr(request, "environ", {}).get(REQUEST_STARTED_ENV, time.monotonic())
        self.files = []
        self.rolling_back = False
        self.cleaning = False

    def remaining(self, *, preparation=False):
        limit = PREPARATION_TIMEOUT_SECONDS if preparation else UPLOAD_TIMEOUT_SECONDS
        remaining = self.started + limit - time.monotonic()
        if remaining <= 0:
            raise UploadExpired()
        return remaining

    def rollback(self):
        # Explicitly retain our file list: Frappe 15 clears after_rollback callbacks
        # BEFORE running before_commit. A refusal there still needs blob cleanup.
        from rayher_crm.services.private_file_lifecycle import discard_rolled_back_blob

        self.rolling_back = True
        frappe.db.rollback()
        for values in self.files:
            discard_rolled_back_blob(*values)
        self.files.clear()

    def before_commit(self):
        try:
            self.remaining()
        except CrmApiException:
            self.rollback()
            raise


def current_upload():
    held = getattr(frappe.local, "crm_upload_deadline", None)
    return held if held is not None and held.request is getattr(frappe.local, "request", None) else None


def defer_upload_cleanup(callback):
    """Do failed-request blob work after the response, while Frappe still owns the DB.

    Row rollback is synchronous. Blob cleanup can wait on other uploads or hash
    large files, so neither core rollback callbacks nor our fallback list may put
    that work between an expired request and its response. Direct service calls
    without a response lifecycle retain synchronous cleanup.
    """
    held = current_upload()
    callbacks = getattr(held.request, "after_response", None) if held else None
    if held is None or callbacks is None or held.cleaning:
        return False
    if not held.rolling_back and time.monotonic() < held.started + UPLOAD_TIMEOUT_SECONDS:
        return False

    def clean():
        held.cleaning = True
        try:
            callback()
        finally:
            held.cleaning = False

    callbacks.add(clean)
    return True


def begin_upload_request():
    """Bind the WSGI entry timestamp to Frappe's request before service dispatch."""
    request = getattr(frappe.local, "request", None)
    if (
        request is not None and getattr(request, "method", None) == "POST"
        and getattr(request, "mimetype", None) == "multipart/form-data"
        and getattr(request, "path", "").startswith("/api/method/rayher_crm.")
        and current_upload() is None
    ):
        frappe.local.crm_upload_deadline = UploadDeadline(request)


def preparation_timeout(maximum):
    held = current_upload()
    return min(maximum, held.remaining(preparation=True)) if held else maximum


def check_preparation():
    if held := current_upload():
        held.remaining(preparation=True)


def track_file(doc):
    if held := current_upload():
        held.files.append((doc.get_full_path(), doc.file_url, doc.content_hash))


@contextmanager
def upload_transaction():
    """The HTTP edge rolls back the WHOLE upload even after a service savepoint was released.

    Session limits apply to every query, including Frappe's internal row locks.
    The end check covers time spent writing files, parsing, serializing, and all
    accumulated waits; the commit hook also covers time after the handler returns.
    """
    begin_upload_request()
    held = current_upload()
    if held is None:
        yield
        return
    held.remaining()
    previous = frappe.db.sql("SELECT @@SESSION.innodb_lock_wait_timeout, @@SESSION.max_statement_time")[0]
    limits = (min(previous[0], DATABASE_WAIT_SECONDS), min(previous[1] or DATABASE_WAIT_SECONDS, DATABASE_WAIT_SECONDS))
    try:
        frappe.db.sql("SET SESSION innodb_lock_wait_timeout = %s, max_statement_time = %s", limits)
        frappe.db.before_commit.add(held.before_commit)
        try:
            yield
        finally:
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout = %s, max_statement_time = %s", previous)
        held.remaining()
    except Exception as error:
        held.rollback()
        if isinstance(error, frappe.QueryTimeoutError) or frappe.db.is_statement_timeout(error):
            raise CrmApiException("VALIDATION_ERROR", UPLOAD_TIMEOUT_MESSAGE) from error
        raise
