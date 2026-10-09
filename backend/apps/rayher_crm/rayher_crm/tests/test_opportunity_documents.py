from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import opportunity_documents as service
from rayher_crm.services.opportunities import archive_strategy_opportunity
from rayher_crm.services.visits import create_visit
from rayher_crm.tests.test_opportunity_relations import TestOpportunityRelations
from rayher_crm.tests.test_opportunity_status import _delete_committed_opportunity


class TestOpportunityDocuments(FrappeTestCase):
    _user = TestOpportunityRelations._user
    _records = TestOpportunityRelations._records

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("document-library-sales@example.invalid", "CRM Sales")
        self.other = self._user("document-library-other@example.invalid", "CRM Sales")
        self.account, opportunity, self.contact = self._records(self.sales, "Documents" + uuid4().hex[:8])
        self.opportunity = opportunity["id"]

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_the_library_says_when_its_opportunity_is_archived(self):
        self.assertFalse(service.get_documents(self.opportunity)["archived"])
        frappe.set_user("Administrator")
        archive_strategy_opportunity(self.opportunity)
        frappe.set_user(self.sales)
        self.assertTrue(service.get_documents(self.opportunity)["archived"])

    def test_links_have_versions_audit_partial_updates_and_no_file_copies(self):
        before_count = frappe.db.count("File")
        first = service.get_documents(self.opportunity)
        self.assertEqual(first["links"]["productScorecard"]["state"], "missing")
        result = service.save_links(self.opportunity, {
            "productScorecard": "https://example.com/product?a=1&b=2",
            "dealScorecard": "https://example.com/deal",
        }, first["modified"])
        self.assertEqual(result["links"]["productScorecard"]["url"], "https://example.com/product?a=1&b=2")
        with self.assertRaises(CrmApiException) as stale:
            service.save_links(self.opportunity, {"productScorecard": ""}, first["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        cleared = service.save_links(self.opportunity, {"productScorecard": ""}, result["modified"])
        self.assertEqual(cleared["links"]["dealScorecard"]["url"], "https://example.com/deal")
        self.assertEqual(cleared["links"]["productScorecard"]["state"], "missing")
        self.assertEqual(frappe.db.count("CRM Opportunity History", {"opportunity": self.opportunity, "field": "productScorecard"}), 2)
        self.assertEqual(service.get_documents(self.opportunity), service.get_documents(self.opportunity))
        self.assertEqual(frappe.db.count("File"), before_count)

    def test_existing_table_schema_accepts_long_scorecard_links(self):
        # Fresh site creation skips the length check used by existing-site migrations.
        from frappe.database.mariadb.schema import MariaDBTable

        table = MariaDBTable("CRM Opportunity")
        self.assertFalse(table.is_new())
        table.validate()
        first = service.get_documents(self.opportunity)
        url = "https://example.com/" + "a" * 1500
        saved = service.save_links(self.opportunity, {"productScorecard": url}, first["modified"])
        self.assertEqual(saved["links"]["productScorecard"]["url"], url)
        self.assertEqual(frappe.db.get_value("CRM Opportunity", self.opportunity, "product_scorecard_url"), url)

    def test_opportunity_access_and_invalid_legacy_links(self):
        first = service.get_documents(self.opportunity)
        with self.assertRaises(CrmApiException):
            service.save_links(self.opportunity, {"dealScorecard": "not a URL"}, first["modified"])
        frappe.db.set_value("CRM Opportunity", self.opportunity, "deal_scorecard_url", "not a URL")
        self.assertEqual(service.get_documents(self.opportunity)["links"]["dealScorecard"], {"url": "", "state": "invalid"})
        frappe.set_user(self.other)
        with self.assertRaises(CrmApiException):
            service.get_documents(self.opportunity)
        with self.assertRaises(CrmApiException):
            service.save_links(self.opportunity, {"dealScorecard": "https://example.com"}, first["modified"])

    def test_visit_aggregation_applies_source_scope_and_exact_opportunity_link(self):
        frappe.set_user("Administrator")
        frappe.db.set_value("Customer", self.account["id"], "custom_crm_visibility", "Public")
        common = {"accountId": self.account["id"], "opportunityId": self.opportunity,
                  "date": "2026-10-05", "type": "On-site", "objective": "Confirm requirement"}
        own = create_visit({**common, "owner": self.sales, "subject": "Visible visit"})
        create_visit({**common, "owner": self.other, "subject": "Another sales visit"})
        create_visit({**common, "owner": self.sales, "opportunityId": "", "subject": "Account-only visit"})
        frappe.set_user(self.sales)
        groups = service.get_documents(self.opportunity)["groups"]
        visits = next(group["items"] for group in groups if group["kind"] == "visit")
        self.assertEqual([row["id"] for row in visits], [own["id"]])

    def test_customer_visibility_revoked_after_initial_check_blocks_save(self):
        frappe.set_user("Administrator")
        site = frappe.db.get_value("CRM Opportunity", self.opportunity, "site")
        frappe.db.set_value("Customer", self.account["id"], {
            "custom_crm_owner": self.other, "custom_crm_visibility": "Public",
        })
        frappe.db.commit()
        connection = frappe.db._get_connection()
        original_require = service._require_opportunity

        def revoke_after_check(opportunity_id):
            doc = original_require(opportunity_id)
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE `tabCustomer` SET custom_crm_visibility='Private' WHERE name=%s",
                    (self.account["id"],),
                )
            connection.commit()
            return doc

        try:
            frappe.set_user(self.sales)
            self.assertEqual(frappe.db.sql("SELECT @@tx_isolation")[0][0], "REPEATABLE-READ")
            first = service.get_documents(self.opportunity)
            with patch.object(service, "_require_opportunity", side_effect=revoke_after_check):
                with self.assertRaises(CrmApiException) as denied:
                    service.save_links(self.opportunity, {"dealScorecard": "https://example.com/deal"}, first["modified"])
            self.assertEqual(denied.exception.code, "SCOPE_DENIED")
            self.assertFalse(frappe.db.get_value("CRM Opportunity", self.opportunity, "deal_scorecard_url"))
            self.assertFalse(frappe.db.exists("CRM Opportunity History", {
                "opportunity": self.opportunity, "field": "dealScorecard",
            }))
        finally:
            frappe.db.rollback()
            connection.close()
            frappe.set_user("Administrator")
            _delete_committed_opportunity(self.opportunity)
            frappe.delete_doc("Contact", self.contact["id"], ignore_permissions=True)
            frappe.delete_doc("CRM Site", site, ignore_permissions=True)
            frappe.delete_doc("Customer", self.account["id"], ignore_permissions=True)
            with patch("frappe.enqueue"):
                frappe.db.commit()
