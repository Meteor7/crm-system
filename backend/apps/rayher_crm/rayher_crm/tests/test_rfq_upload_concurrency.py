"""An Opportunity changed by another request while its RFQ's file is being scanned and converted.

The scan and the conversion run before the RFQ's row exists, so the other request has nothing to wait for. A second
database connection stands in for it; the rows it must see are committed, and taken out again by hand at the end.
"""

from __future__ import annotations

import os
from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.database import get_db
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfWriter

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.scope import OPPORTUNITY_SCOPED_CHILD_DOCTYPES
from rayher_crm.services import rfqs as rfq_service
from rayher_crm.services.opportunity_stages import CUSTOMER_BUDGET_APPROVED, QUALIFIED_OPPORTUNITY
from rayher_crm.services.rfqs import create_rfq
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture
# The module, not its class: a test class imported by name is collected and run again with this one.
from rayher_crm.tests import test_rfq_api as rfq_tests

STAGE_MESSAGE = "RFQ can only be created when the Opportunity is at customer_budget_approved."


class TestRfqUploadConcurrency(FrappeTestCase):
    _user = rfq_tests.TestRfqApi._user
    _opportunity = rfq_tests.TestRfqApi._opportunity

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        # Registered first, so that it runs last: after the cleanup that discards the committed rows as Administrator.
        self.addCleanup(frappe.set_user, self.original_user)
        # Nothing an earlier test left pending may be committed with this test's rows.
        frappe.db.rollback()
        frappe.set_user("Administrator")
        self.sales = self._user("crm-rfq-race-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-rfq-race-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-rfq-race-engineer@example.invalid", "CRM Engineer")
        frappe.db.commit()

    def _committed_opportunity(self) -> dict:
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        account, site = self.last_account, self.last_site
        frappe.db.commit()
        self.addCleanup(self._discard, opportunity["id"], account, site)
        # A read opens this request's snapshot, before the other request commits.
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity["id"], "stage"), CUSTOMER_BUDGET_APPROVED)
        return opportunity

    def _discard(self, opportunity_id: str, account: str, site: str) -> None:
        frappe.set_user("Administrator")
        frappe.db.rollback()
        # Permanently: a deletion that keeps a Deleted Document would commit that archive instead.
        for doctype in OPPORTUNITY_SCOPED_CHILD_DOCTYPES:
            frappe.db.delete(doctype, {"opportunity": opportunity_id})
        frappe.db.delete("CRM Notification Event", {"source_doctype": "CRM Opportunity", "source_name": opportunity_id})
        frappe.delete_doc("CRM Opportunity", opportunity_id, ignore_permissions=True, force=True, delete_permanently=True)
        # A Site is an Address (services/sites.py); a DocType that does not exist would be ignored silently.
        frappe.delete_doc("Address", site, ignore_permissions=True, force=True, delete_permanently=True)
        frappe.db.delete("CRM Notification Event", {"source_doctype": "Customer", "source_name": account})
        frappe.delete_doc("Customer", account, ignore_permissions=True, force=True, delete_permanently=True)
        with patch("frappe.enqueue"):
            frappe.db.commit()

    def _committed_by_the_other_request(self, assignment: str, values: tuple) -> None:
        other = get_db(
            host=frappe.conf.db_host, port=frappe.conf.db_port, user=frappe.conf.db_user or frappe.conf.db_name,
            password=frappe.conf.db_password, cur_db_name=frappe.conf.db_name,
        )
        other.connect()
        try:
            other.sql(f"UPDATE `tabCRM Opportunity` SET {assignment}, `modified` = NOW(6) WHERE `name` = %s", values)
            other.commit()
        finally:
            other.close()

    def _refused_and_undone(self, opportunity: dict, code: str, message: str) -> None:
        real_discard = rfq_service.discard_rolled_back_blob
        discarded: list[tuple[str, str]] = []

        def discard(path, file_url, content_hash):
            discarded.append((path, file_url))
            return real_discard(path, file_url, content_hash)

        # Bytes of this test alone, so that no other upload shares the file the refusal takes back out.
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_metadata({"/Title": f"Raced RFQ {frappe.generate_hash(length=12)}"})
        writer.write(output)
        part = {"file_name": "raced-customer-rfq.pdf", "mime_type": "application/pdf", "content": output.getvalue()}
        frappe.set_user(self.sales)
        with patch.object(rfq_service, "discard_rolled_back_blob", side_effect=discard):
            with self.assertRaises(CrmApiException) as refused:
                create_rfq({"opportunityId": opportunity["id"], "engineerId": self.engineer}, part, rfq_tests.CleanScanner())
        self.assertEqual((refused.exception.code, refused.exception.public_message), (code, message))
        self.assertFalse(frappe.db.exists("CRM RFQ", {"opportunity": opportunity["id"]}))
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "recipient_user": self.engineer, "title": "RFQ requires Engineer review",
            "message": ["like", f"{opportunity['title']}%"],
        }))
        self.assertTrue(discarded)
        for path, file_url in discarded:
            self.assertFalse(frappe.db.exists("File", {"file_url": file_url}), file_url)
            self.assertFalse(os.path.exists(path), path)

    def test_a_stage_rolled_back_during_the_scan_refuses_the_rfq_and_undoes_it(self):
        opportunity = self._committed_opportunity()
        self._committed_by_the_other_request("`stage` = %s", (QUALIFIED_OPPORTUNITY, opportunity["id"]))
        # The snapshot still allows an RFQ; the stage read under the Opportunity's lock does not.
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity["id"], "stage"), CUSTOMER_BUDGET_APPROVED)
        self._refused_and_undone(opportunity, "INVALID_TRANSITION", STAGE_MESSAGE)

    def test_an_owner_reassigned_during_the_scan_refuses_the_rfq_written_with_the_former_owner(self):
        opportunity = self._committed_opportunity()
        self._committed_by_the_other_request("`opportunity_owner` = %s", (self.other_sales, opportunity["id"]))
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity["id"], "opportunity_owner"), self.sales)
        self._refused_and_undone(opportunity, "VERSION_CONFLICT", "The record was changed by another request.")
