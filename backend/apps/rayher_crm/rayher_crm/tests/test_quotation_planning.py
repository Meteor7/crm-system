import re
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import quotation_planning as service
from rayher_crm.tests.test_quotation_api import TestQuotationApi


class TestQuotationPlanning(FrappeTestCase):
    _user = TestQuotationApi._user
    _opportunity = TestQuotationApi._opportunity
    _ready_quotation = TestQuotationApi._ready_quotation
    _publish = TestQuotationApi._publish

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("quote-plan-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("quote-plan-other@example.invalid", "CRM Sales")
        self.manager = self._user("quote-plan-manager@example.invalid", "CRM Manager")

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_schedule_uses_master_cas_and_publishing_closes_scheduling(self):
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        first = service.get_planning(quote_id)
        plan = service.save_schedule(quote_id, {"plannedSendDate": "2026-10-12"}, first["modified"])
        self.assertEqual(plan["plannedSendDate"], "2026-10-12")
        with self.assertRaises(CrmApiException) as stale:
            service.save_schedule(quote_id, {"plannedSendDate": None}, first["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        published = self._publish(quote_id, saved["version"]["modified"])
        current = service.get_planning(quote_id)
        self.assertIsNone(current["plannedSendDate"])
        with self.assertRaises(CrmApiException) as locked:
            service.save_schedule(quote_id, {"plannedSendDate": "2026-10-13"}, current["modified"])
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")
        cleared = service.save_schedule(quote_id, {"plannedSendDate": None}, current["modified"])
        self.assertIsNone(cleared["plannedSendDate"])
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", published["version"]["id"], "status"), "Published")
        from rayher_crm.services import quotations
        revision = quotations.create_version(quote_id)
        current = service.get_planning(quote_id)
        self.assertIsNone(current["plannedSendDate"])
        service.save_schedule(quote_id, {"plannedSendDate": "2026-10-20"}, current["modified"])
        quotations.discard_draft(quote_id, revision["version"]["modified"])
        self.assertIsNone(service.get_planning(quote_id)["plannedSendDate"])

    def test_follow_up_completion_snapshot_survives_note_edits_and_clears_on_reopen(self):
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        published = self._publish(quote_id, saved["version"]["modified"])
        first = service.get_planning(quote_id)
        payload = {"title": "Confirm customer response", "due": "2026-10-12", "status": "Open", "note": ""}
        result = service.save_follow_up(quote_id, payload, expected_modified=first["modified"])
        followup_id = result["followUps"][0]["id"]
        with patch("frappe.utils.now_datetime", return_value=datetime(2026, 10, 5, 15)):
            done = service.save_follow_up(quote_id, {**payload, "status": "Done"}, followup_id, result["modified"])
        completed = done["followUps"][0]["completedAt"]
        self.assertEqual(done["followUps"][0]["completedVersion"], published["version"]["id"])
        self.assertEqual(frappe.db.get_value("CRM Quotation Follow Up", followup_id, "completed_owner"), self.sales)
        changed = service.save_follow_up(quote_id, {**payload, "status": "Done", "note": "Additional context"}, followup_id, done["modified"])
        self.assertEqual(changed["followUps"][0]["completedAt"], completed)
        with self.assertRaises(CrmApiException) as stale:
            service.save_follow_up(quote_id, payload, followup_id, done["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        reopened = service.save_follow_up(quote_id, payload, followup_id, changed["modified"])
        self.assertIsNone(reopened["followUps"][0]["completedAt"])
        self.assertIsNone(reopened["followUps"][0]["completedVersion"])
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": "CRM Quotation", "docname": quote_id}))

    def test_scope_and_open_quote_checks_apply_to_child_followups(self):
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        first = service.get_planning(quote_id)
        payload = {"title": "Follow up", "due": "2026-10-12", "status": "Open", "note": ""}
        with self.assertRaises(CrmApiException) as unopened:
            service.save_follow_up(quote_id, payload, expected_modified=first["modified"])
        self.assertEqual(unopened.exception.code, "INVALID_TRANSITION")
        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException):
            service.get_planning(quote_id)
        with self.assertRaises(CrmApiException):
            service.save_schedule(quote_id, {"plannedSendDate": "2026-10-12"}, first["modified"])
        self.assertFalse(frappe.get_all("CRM Quotation Follow Up", filters={"parent": quote_id}, pluck="name"))

    def test_an_archived_opportunitys_quotation_takes_no_send_plan_and_no_follow_up_and_leaves_plan(self):
        from rayher_crm.services import cockpit
        from rayher_crm.services.opportunities import archive_strategy_opportunity, unarchive_strategy_opportunity
        from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_EDIT
        saved, _ = self._ready_quotation()
        quote_id = saved["quotation"]["id"]
        opportunity_id = saved["quotation"]["opportunityId"]
        scheduled = service.save_schedule(quote_id, {"plannedSendDate": "2030-10-14"}, service.get_planning(quote_id)["modified"])

        def planned() -> set[str]:
            frappe.set_user(self.manager)
            try:
                details = cockpit.get_plan_details({"period": "week", "anchor": "2030-10-14", "metric": "quotes", "sales": self.sales, "pageSize": 100})
            finally:
                frappe.set_user(self.sales)
            return {row.get("quotationId") for row in details["items"]}

        self.assertIn(quote_id, planned())
        frappe.set_user(self.manager)
        archive_strategy_opportunity(opportunity_id)
        frappe.set_user(self.sales)
        self.assertNotIn(quote_id, planned())
        modified = frappe.db.get_value("CRM Quotation", quote_id, "modified")
        follow_up = {"title": "Chase the customer", "due": "2030-10-15", "status": "Open", "note": ""}
        real_sql = frappe.db.sql
        statements: list[str] = []

        def watch(query, *args, **kwargs):
            statements.append(str(query))
            return real_sql(query, *args, **kwargs)

        for attempt in (
            lambda: service.save_schedule(quote_id, {"plannedSendDate": None}, scheduled["modified"]),
            lambda: service.save_follow_up(quote_id, follow_up, expected_modified=scheduled["modified"]),
        ):
            statements.clear()
            with self.assertRaises(CrmApiException) as refused, patch.object(frappe.db, "sql", side_effect=watch):
                attempt()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_EDIT))
            # The flag is read under the Opportunity's row lock, as committed, by each attempt: every statement on the
            # Opportunity's table that reads the archive's columns or the whole row, as these paths write them, is a
            # locking one without a subquery (which would read the snapshot's, without a lock), one of them FOR UPDATE
            # (a read served from the cache is not seen).
            reads = [text.upper() for text in statements if re.search(r"`tabCRM Opportunity`", text, re.I)
                     and re.search(r"\barchived(?:_at|_by)?\b|(?:SELECT|,)\s*(?:`[^`]+`\.|\w+\.)?\*", text, re.I)]
            self.assertTrue(any("FOR UPDATE" in text for text in reads), statements)
            self.assertTrue(all(("FOR UPDATE" in text or "LOCK IN SHARE MODE" in text) and text.count("SELECT") == 1
                                for text in reads), reads)
        self.assertEqual(
            frappe.db.get_value("CRM Quotation", quote_id, ["planned_send_date", "modified"]),
            (frappe.utils.getdate("2030-10-14"), modified),
        )
        self.assertFalse(frappe.get_all("CRM Quotation Follow Up", filters={"parent": quote_id}, pluck="name"))

        frappe.set_user(self.manager)
        unarchive_strategy_opportunity(opportunity_id)
        frappe.set_user(self.sales)
        self.assertIn(quote_id, planned())
        self.assertIsNone(service.save_schedule(quote_id, {"plannedSendDate": None}, scheduled["modified"])["plannedSendDate"])

    def test_account_only_service_quote_can_complete_and_cancel_followups(self):
        from rayher_crm.services import quotations
        opportunity = self._opportunity()
        created = quotations.create_quotation({"accountId": opportunity["accountId"], "quotationType": "Service"})
        quote_id = created["quotation"]["id"]
        payload = {key: created["version"][key] for key in (
            "quoteDate", "validityMonths", "items", "discountType", "discountValue", "deliveryMonths", "warrantyMonths",
        )}
        payload.update(primaryContactId=self.quotation_contact["id"], addressId=self.quotation_site["id"])
        saved = quotations.save_draft(quote_id, payload, created["version"]["modified"])
        self._publish(quote_id, saved["version"]["modified"])
        plan = service.get_planning(quote_id)
        followup = {"title": "Service response", "due": "2030-10-01", "status": "Done", "note": "Confirmed"}
        done = service.save_follow_up(quote_id, followup, expected_modified=plan["modified"])
        row = done["followUps"][0]
        self.assertTrue(row["completedAt"])
        self.assertFalse(frappe.db.get_value("CRM Quotation", quote_id, "opportunity"))
        cancelled = service.save_follow_up(quote_id, {**followup, "status": "Cancelled"}, row["id"], done["modified"])
        self.assertIsNone(cancelled["followUps"][0]["completedAt"])
