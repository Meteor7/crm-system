"""The actual WSGI response boundary around Frappe's commit-time exception."""

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.utils import CallbackManager
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request, Response

from rayher_crm import wsgi
from rayher_crm.services.upload_deadline import UploadDeadline, UploadExpired, UPLOAD_TIMEOUT_MESSAGE


class TestUploadWsgi(TestCase):
    def environment(self):
        return EnvironBuilder(path="/api/method/rayher_crm.api.v1.rfqs.create_rfq", method="POST",
            content_type="multipart/form-data; boundary=test").get_environ()

    def test_parsing_time_is_deducted_from_both_deadlines(self):
        clock = [1000.0]

        def frappe_with_slow_parsing(environ, start_response):
            clock[0] += 20  # make_form_dict runs before Frappe's before_request hooks
            held = UploadDeadline(Request(environ))
            self.assertEqual(held.remaining(preparation=True), 70)
            self.assertEqual(held.remaining(), 85)
            return Response("ok")(environ, start_response)

        with patch.object(wsgi.time, "monotonic", lambda: clock[0]), \
                patch.object(wsgi, "frappe_application", side_effect=frappe_with_slow_parsing):
            response = wsgi.application(self.environment(), lambda *args: None)
            self.assertEqual(b"".join(response), b"ok")
            response.close()

    def test_commit_expiry_returns_the_crm_envelope_and_closes_frappe(self):
        statuses = []
        callbacks = CallbackManager()
        finished = []
        callbacks.add(lambda: finished.append("cleanup"))
        with patch.object(wsgi, "frappe_application", side_effect=UploadExpired()), \
                patch.object(frappe.local, "request", SimpleNamespace(after_response=callbacks), create=True), \
                patch.object(wsgi, "process_response") as decorate, \
                patch.object(frappe, "destroy", side_effect=lambda: finished.append("destroy")) as destroy:
            response = wsgi.application(self.environment(), lambda status, headers: statuses.append(status))
            data = json.loads(b"".join(response))["message"]
            self.assertEqual(statuses, ["422 UNPROCESSABLE ENTITY"])
            self.assertIsNone(data["data"])
            self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")
            self.assertEqual(data["error"]["message"], UPLOAD_TIMEOUT_MESSAGE)
            decorate.assert_called_once()
            destroy.assert_not_called()
            self.assertEqual(finished, [])
            response.close()
            destroy.assert_called_once()
            self.assertEqual(finished, ["cleanup", "destroy"])

    def test_other_framework_exceptions_are_not_mislabeled_as_upload_timeouts(self):
        with patch.object(wsgi, "frappe_application", side_effect=RuntimeError("framework failed")), \
                patch.object(frappe, "destroy") as destroy, self.assertRaisesRegex(RuntimeError, "framework failed"):
            wsgi.application(self.environment(), lambda *args: None)
        destroy.assert_called_once()
