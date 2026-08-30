from __future__ import annotations

from datetime import datetime, timezone

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CRM_ERROR_CODES, CrmApiException, api_endpoint, error_response
from rayher_crm.services.common import ensure_server_generated_id, normalize_pagination, read_all_pages, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document


class TestServiceFoundation(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.customer = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "Stage 5B Lock Customer",
                "customer_type": "Company",
                "customer_group": "CRM Customers",
                "territory": "CRM Territory",
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_pagination_defaults_parses_strings_and_caps_at_200(self):
        self.assertEqual(normalize_pagination(None, None), (1, 20, 0))
        self.assertEqual(normalize_pagination("2", "25"), (2, 25, 25))
        self.assertEqual(normalize_pagination(3, 100000), (3, 200, 400))

        for page, page_size in ((0, 20), (1, 0), ("bad", 20), (1, "bad")):
            with self.assertRaises(CrmApiException) as raised:
                normalize_pagination(page, page_size)
            self.assertEqual(raised.exception.code, "VALIDATION_ERROR")

    def test_read_all_pages_fetches_items_beyond_the_first_page(self):
        source = list(range(201))
        queries = []

        def read_page(query):
            queries.append(query)
            start = (query["page"] - 1) * query["pageSize"]
            return source[start:start + query["pageSize"]], len(source), query["page"], query["pageSize"]

        self.assertEqual(read_all_pages(read_page, {"accountId": "ACC-001"}), source)
        self.assertEqual(queries, [
            {"accountId": "ACC-001", "page": 1, "pageSize": 200},
            {"accountId": "ACC-001", "page": 2, "pageSize": 200},
        ])

    def test_timestamp_serialization_is_timezone_explicit(self):
        self.assertEqual(to_iso_timestamp(datetime(2026, 8, 4, 15, 0, 0)), "2026-08-04T07:00:00Z")
        self.assertEqual(
            to_iso_timestamp(datetime(2026, 8, 4, 7, 0, 0, tzinfo=timezone.utc)),
            "2026-08-04T07:00:00Z",
        )

    def test_create_payload_rejects_a_client_generated_id(self):
        ensure_server_generated_id({"name": "Business Name"})

        with self.assertRaises(CrmApiException) as raised:
            ensure_server_generated_id({"id": "ACC-CLIENT", "name": "Business Name"})
        self.assertEqual(raised.exception.code, "VALIDATION_ERROR")

    def test_lock_document_accepts_current_modified_without_writing(self):
        expected = to_iso_timestamp(self.customer.modified)
        modified_before = frappe.db.get_value("Customer", self.customer.name, "modified")

        locked = lock_document("Customer", self.customer.name, expected, "NOT_FOUND")

        self.assertEqual(locked.name, self.customer.name)
        self.assertEqual(frappe.db.get_value("Customer", self.customer.name, "modified"), modified_before)

    def test_lock_document_fails_closed_for_missing_stale_or_unknown_records(self):
        with self.assertRaises(CrmApiException) as missing_token:
            lock_document("Customer", self.customer.name, None, "NOT_FOUND")
        self.assertEqual(missing_token.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as stale:
            lock_document("Customer", self.customer.name, "2000-01-01T00:00:00Z", "NOT_FOUND")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        with self.assertRaises(CrmApiException) as missing:
            lock_document("Customer", "missing-customer", "2000-01-01T00:00:00Z", "NOT_FOUND")
        self.assertEqual(missing.exception.code, "NOT_FOUND")

    def test_error_envelope_uses_supported_codes_and_redacts_internal_details(self):
        self.assertEqual(CRM_ERROR_CODES, {
            "UNAUTHENTICATED", "PERMISSION_DENIED", "SCOPE_DENIED", "NOT_FOUND",
            "VALIDATION_ERROR", "CONFLICT", "RFQ_APPROVAL_REQUIRED", "INVALID_TRANSITION", "VERSION_CONFLICT",
            "REPORT_NOT_READY", "BACKEND_NOT_CONNECTED", "NETWORK_ERROR", "INTERNAL_ERROR",
        })

        response = error_response(
            CrmApiException(
                "VALIDATION_ERROR",
                "Invalid account",
                field_errors={"name": "Required"},
            )
        )
        self.assertIsNone(response["data"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(response["error"]["fieldErrors"], {"name": "Required"})
        self.assertNotIn("traceback", str(response).lower())
        self.assertNotIn("sql", str(response).lower())

    def test_authentication_failures_return_401_instead_of_raw_403(self):
        @api_endpoint
        def raises_authentication_error():
            raise frappe.AuthenticationError("expired session")

        @api_endpoint
        def raises_guest_permission_error():
            raise frappe.PermissionError("login required")

        original_user = frappe.session.user
        try:
            frappe.set_user("Guest")
            for endpoint in (raises_authentication_error, raises_guest_permission_error):
                with self.subTest(endpoint=endpoint.__name__):
                    response = endpoint()
                    self.assertEqual(response["error"]["code"], "UNAUTHENTICATED")
                    self.assertEqual(frappe.local.response["http_status_code"], 401)
                    self.assertEqual(response["error"]["message"], "Authentication is required.")
        finally:
            frappe.set_user(original_user)

    def test_legacy_service_codes_are_normalized_before_the_public_envelope(self):
        cases = {
            "ACCOUNT_NOT_FOUND": "NOT_FOUND",
            "INVALID_OWNER": "VALIDATION_ERROR",
            "BOOKING_ALREADY_EXISTS": "CONFLICT",
            "BOOKING_NOT_CONFIRMED": "INVALID_TRANSITION",
            "QUOTATION_STAGE_INVALID": "INVALID_TRANSITION",
            "ADDRESS_ACCOUNT_MISMATCH": "CONFLICT",
            "EVALUATION_EXISTS": "REPORT_NOT_READY",
            "INSTALLED_TOOL_SCOPE_DENIED": "SCOPE_DENIED",
            "UPSTREAM_TIMEOUT": "NETWORK_ERROR",
        }
        for legacy, canonical in cases.items():
            with self.subTest(legacy=legacy):
                self.assertEqual(CrmApiException(legacy, "safe").code, canonical)
