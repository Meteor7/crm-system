from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.api.v1 import read_only_views as read_only_api
from rayher_crm.services import read_only_views
from rayher_crm.setup.controlled_documents import (
    ACONCA_DOCUMENT_ID,
    LEGACY_MUSHI_DOCUMENT_ID,
    NANSI_DOCUMENT_ID,
)


class TestStage5GReadOnlyViews(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        for document_id in (ACONCA_DOCUMENT_ID, NANSI_DOCUMENT_ID, LEGACY_MUSHI_DOCUMENT_ID):
            frappe.db.delete("CRM Controlled Document", {"name": document_id})
        self.manager = "crm-stage5g-view-manager@example.invalid"
        if not frappe.db.exists("User", self.manager):
            frappe.get_doc({
                "doctype": "User",
                "email": self.manager,
                "first_name": "Stage5G View Manager",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": "CRM Manager"}],
            }).insert(ignore_permissions=True)
        frappe.set_user(self.manager)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_requirement_and_contract_views_are_paginated_empty_sources(self):
        requirements = read_only_views.list_requirements({"page": "2", "pageSize": "5", "search": "not-seed"})
        contracts = read_only_views.list_contracts({"page": "3", "pageSize": "7"})
        self.assertEqual(requirements, ([], 0, 2, 5))
        self.assertEqual(contracts, ([], 0, 3, 7))

    def test_controlled_documents_is_empty_without_seeded_legacy_content(self):
        documents = read_only_views.list_controlled_documents()
        self.assertEqual(documents, [])
        self.assertTrue(all(item["access"] == "Request" for item in documents))
        with self.assertRaises(CrmApiException) as missing:
            read_only_views.request_controlled_document_access("DOC-V1", "Customer evaluation")
        self.assertEqual(missing.exception.code, "NOT_FOUND")

    def test_read_only_endpoints_keep_stable_envelopes(self):
        requirements = read_only_api.list_requirements(page="4", pageSize="9")
        contracts = read_only_api.list_contracts(page="2", pageSize="6")
        documents = read_only_api.list_controlled_documents()
        self.assertEqual(requirements["data"], {"items": []})
        self.assertEqual(requirements["meta"]["page"], 4)
        self.assertEqual(requirements["meta"]["total"], 0)
        self.assertEqual(contracts["data"], {"items": []})
        self.assertEqual(contracts["meta"]["pageSize"], 6)
        self.assertEqual(documents["data"]["items"], [])
        self.assertEqual(documents["meta"]["total"], 0)

    def test_queries_validate_pagination_and_require_a_crm_identity(self):
        with self.assertRaises(CrmApiException):
            read_only_views.list_requirements({"page": "0"})
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            read_only_views.list_contracts({})

    def test_each_read_only_view_enforces_a_server_capability(self):
        cases = (
            ("requirement:view", lambda: read_only_views.list_requirements({})),
            ("contract:view", lambda: read_only_views.list_contracts({})),
            ("account:view", read_only_views.list_controlled_documents),
        )
        for capability, invoke in cases:
            with self.subTest(capability=capability), patch.object(
                read_only_views, "assert_capability", side_effect=frappe.PermissionError("denied")
            ) as guarded:
                with self.assertRaises(frappe.PermissionError):
                    invoke()
                guarded.assert_called_once_with(capability)

    def test_empty_get_views_do_not_write_business_rows(self):
        before = {
            "Customer": frappe.db.count("Customer"),
            "CRM Opportunity": frappe.db.count("CRM Opportunity"),
            "CRM Visit": frappe.db.count("CRM Visit"),
        }
        read_only_views.list_requirements({})
        read_only_views.list_contracts({})
        read_only_views.list_controlled_documents()
        after = {doctype: frappe.db.count(doctype) for doctype in before}
        self.assertEqual(after, before)
