from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from html import unescape
from unittest.mock import patch

import frappe
from frappe.permissions import add_user_permission, remove_user_permission
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.opportunity_stages import (
    CUSTOMER_BUDGET_APPROVED,
    QUALIFIED_OPPORTUNITY,
    QUOTATION_SENT,
    RFQ_VALIDATED,
)
from rayher_crm.services.quotations import (
    _pdf_context, _validated_values, create_quotation, create_version, discard_draft, get_pdf_file, get_preview_pdf, get_quotation, list_quotations,
    expire_quotations, link_quotation_opportunity, publish_version, record_decision, render_quotation_html, review_approval, save_draft, submit_for_approval,
)
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestQuotationApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-quotation-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-quotation-other-sales@example.invalid", "CRM Sales")
        self.manager = self._user("crm-quotation-manager@example.invalid", "CRM Manager")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
            user.enabled = 1
            if role not in {row.role for row in user.roles}:
                user.append("roles", {"role": role})
                user.save(ignore_permissions=True)
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "Quotation Sales",
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _opportunity(self):
        suffix = random_string(6)
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"Quotation Customer {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "\u4e0a\u6d77", "region": "\u534e\u4e1c", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"Quotation Site {suffix}", "city": "\u4e0a\u6d77", "type": "Fab",
            "process": "Frontend", "status": "\u91cf\u4ea7",
        })
        self.quotation_site = site
        self.quotation_contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"Quotation Contact {suffix}",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"quotation-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account["id"], "siteId": site["id"], "title": f"Quotation Project {suffix}",
            "owner": self.sales, "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": "100000.00",
            "probability": 60, "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "\u534e\u4e1c", "currency": "CNY",
            "originalAmount": "100000.00", "amountCny": "100000.00", "paymentMilestones": [],
            "strengths": [], "redFlags": [], "informationNeeded": [], "qualificationConfirmed": True,
        })
        opportunity = advance_opportunity_fixture(opportunity, RFQ_VALIDATED)
        return opportunity

    def _publish(self, name: str, expected_modified: str):
        frappe.set_user(self.manager)
        try:
            return publish_version(name, expected_modified)
        finally:
            frappe.set_user(self.sales)

    def _ready_quotation(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validityMonths", "items",
                "discountType", "discountValue", "deliveryMonths", "warrantyMonths",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        saved = save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        return saved, payload

    def test_account_360_includes_customer_quotations(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})

        account = get_account_360(opportunity["accountId"])

        self.assertIn(created["quotation"]["id"], {row["id"] for row in account["quotations"]})
        self.assertTrue(all(row["accountId"] == opportunity["accountId"] for row in account["quotations"]))

    def test_review_expiry_reads_formal_version_and_current_owner_despite_new_draft(self):
        from rayher_crm.services.cockpit import get_details, get_review

        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        quote_id, version_id = published["quotation"]["id"], published["version"]["id"]
        frappe.db.set_value("CRM Quotation Version", version_id, {
            "published_at": "2026-09-01 10:00:00", "valid_until": "2026-10-06",
        }, update_modified=False)
        draft = create_version(quote_id)
        frappe.db.set_value("CRM Quotation", quote_id, "quotation_owner", self.other_sales, update_modified=False)
        query = {"period": "week", "anchor": "2026-09-22", "sales": self.other_sales}
        with self.assertRaises(CrmApiException) as denied:
            get_review(query)
        self.assertEqual(denied.exception.code, "PERMISSION_DENIED")
        frappe.set_user(self.manager)
        with patch("frappe.utils.now_datetime", return_value=datetime(2026, 9, 22, 12)):
            review = get_review(query)
            self.assertEqual(review["quotationExpiry"], {"referenceDate": "2026-09-22", "thresholdDays": 14})
            self.assertEqual(next(w["count"]["value"] for w in review["warnings"] if w["key"] == "quotation_expiry"), 1)
            result = get_details({**query, "metric": "quotation_expiry", "pageSize": 1})
            self.assertEqual(result["total"], 1)
            row = result["items"][0]
            self.assertEqual((row["id"], row["quotationVersionId"], row["owner"], row["daysToExpiry"]),
                             (quote_id, version_id, self.other_sales, 14))
            self.assertNotEqual(row["quotationVersionId"], draft["version"]["id"])
            self.assertEqual(get_details({**query, "sales": self.sales, "metric": "quotation_expiry"})["total"], 0)
            self.assertEqual(get_quotation(quote_id, row["quotationVersionId"])["version"]["id"], version_id)
            with patch.dict(frappe.conf, {"crm_cockpit_quote_expiry_days": 13}):
                self.assertEqual(get_details({**query, "metric": "quotation_expiry"})["total"], 0)
            for invalid in (-1, "invalid", True, 366, "1.5"):
                with patch.dict(frappe.conf, {"crm_cockpit_quote_expiry_days": invalid}):
                    self.assertEqual(get_review(query)["quotationExpiry"]["thresholdDays"], 14)

    def test_review_expiry_clears_after_customer_decision(self):
        from rayher_crm.services.cockpit import get_details

        for decision in ("Accepted", "Rejected"):
            saved, _ = self._ready_quotation()
            published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
            quote_id = published["quotation"]["id"]
            frappe.db.set_value("CRM Quotation Version", published["version"]["id"], {
                "published_at": "2026-09-01 10:00:00", "valid_until": "2026-09-22",
            }, update_modified=False)
            query = {"period": "week", "anchor": "2026-09-22", "sales": self.sales, "metric": "quotation_expiry"}
            frappe.set_user(self.manager)
            with patch("frappe.utils.now_datetime", return_value=datetime(2026, 9, 22, 12)):
                self.assertIn(quote_id, {r["id"] for r in get_details(query)["items"]})
            frappe.set_user(self.sales)
            record_decision(quote_id, decision, "2026-09-22", "Customer response", published["version"]["modified"])
            frappe.set_user(self.manager)
            with patch("frappe.utils.now_datetime", return_value=datetime(2026, 9, 22, 12)):
                self.assertNotIn(quote_id, {r["id"] for r in get_details(query)["items"]})

    def test_closed_quote_stays_excluded_after_opportunity_changes_customer_outside_market(self):
        from rayher_crm.services.cockpit import get_details, load_data

        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        quote_id, opportunity_id = published["quotation"]["id"], published["quotation"]["opportunityId"]
        frappe.db.set_value("CRM Quotation Version", published["version"]["id"], {
            "published_at": "2026-09-01 10:00:00", "valid_until": "2026-09-29",
        }, update_modified=False)
        destination = create_account({"name": f"Moved customer {random_string(6)}", "shortName": random_string(6), "segment": "Backend",
                                      "tier": "A", "city": "Shanghai", "region": "East China", "owner": self.sales})
        # Reassignment does not rewrite the already-published quotation snapshot.
        frappe.db.set_value("CRM Opportunity", opportunity_id, "account", destination["id"], update_modified=False)
        frappe.set_user(self.manager)
        query = {"period": "week", "anchor": "2026-09-22", "sales": self.sales, "metric": "quotation_expiry"}
        with patch("frappe.utils.now_datetime", return_value=datetime(2026, 9, 22, 12)):
            for closed_stage in ("lost", "po_received"):
                frappe.db.set_value("CRM Opportunity", opportunity_id, "stage", closed_stage, update_modified=False)
                for scope in ({}, {"market": "Frontend"}):
                    self.assertNotIn(quote_id, {r["id"] for r in get_details({**query, **scope})["items"]})
            original_customer = frappe.get_doc("Customer", published["quotation"]["accountId"]).as_dict()
            loaded = load_data([original_customer], [])
            self.assertNotIn(opportunity_id, {r["name"] for r in loaded["opportunities"]})
            self.assertIn(opportunity_id, {r["name"] for r in loaded["quotation_opportunities"]})

    def test_public_non_owner_sales_gets_redacted_address_and_cannot_download_full_pdf(self):
        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        quotation_id = published["quotation"]["id"]
        version_id = published["version"]["id"]
        account_id = published["quotation"]["accountId"]
        frappe.db.set_value("Customer", account_id, "custom_crm_visibility", "Public", update_modified=False)
        frappe.db.set_value("CRM Quotation", quotation_id, "quotation_owner", self.other_sales, update_modified=False)
        frappe.db.set_value("CRM Quotation Version", version_id, "quotation_owner", self.other_sales, update_modified=False)

        frappe.set_user(self.other_sales)
        detail = get_quotation(quotation_id)
        self.assertEqual((detail["version"]["addressId"], detail["version"]["addressText"], detail["version"]["addressRestricted"]), ("", "", True))
        self.assertFalse(detail["version"]["pdfAvailable"])
        context = _pdf_context(
            frappe.get_doc("CRM Quotation", quotation_id),
            frappe.get_doc("CRM Quotation Version", version_id),
        )
        self.assertEqual((context["addressId"], context["addressText"]), ("", ""))
        version = frappe.get_doc("CRM Quotation Version", version_id)
        self.assertFalse(version.has_permission("read", user=self.other_sales))
        self.assertEqual(
            frappe.get_list(
                "CRM Quotation Version",
                filters={"name": version_id},
                pluck="name",
            ),
            [],
        )
        file_id = frappe.db.get_value("File", {"file_url": version.pdf_file}, "name")
        self.assertTrue(file_id)
        self.assertFalse(frappe.get_doc("File", file_id).is_downloadable())
        with self.assertRaises(CrmApiException) as denied:
            get_pdf_file(quotation_id)
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as write_denied:
            create_version(quotation_id)
        self.assertEqual(write_denied.exception.code, "SCOPE_DENIED")

    def test_public_non_owner_sales_cannot_create_unusable_quotation_drafts(self):
        opportunity = self._opportunity()
        account_id = opportunity["accountId"]
        frappe.db.set_value(
            "Customer",
            account_id,
            "custom_crm_visibility",
            "Public",
            update_modified=False,
        )
        frappe.db.set_value(
            "CRM Opportunity",
            opportunity["id"],
            "opportunity_owner",
            self.other_sales,
            update_modified=False,
        )

        frappe.set_user(self.other_sales)
        before = frappe.db.count("CRM Quotation", {"account": account_id})
        for payload in (
            {"opportunityId": opportunity["id"]},
            {"accountId": account_id, "quotationType": "Service"},
        ):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as denied:
                create_quotation(payload)
            self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        self.assertEqual(frappe.db.count("CRM Quotation", {"account": account_id}), before)

    def test_sales_submission_requires_manager_approval_and_preserves_retries(self):
        saved, payload = self._ready_quotation()
        with self.assertRaises(frappe.PermissionError):
            publish_version(saved["quotation"]["id"], saved["version"]["modified"])

        submitted = submit_for_approval(saved["quotation"]["id"], saved["version"]["modified"])
        self.assertEqual(submitted["version"]["approvalStatus"], "Pending")
        self.assertFalse(submitted["version"]["pdfAvailable"])
        self.assertEqual(submitted["approvals"][0]["status"], "Pending")
        manager_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Quotation", "source_name": saved["quotation"]["id"],
                     "recipient_user": self.manager},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (manager_notice.category, manager_notice.route),
            ("Quotation", f"/quotations/{saved['quotation']['id']}"),
        )
        listed, total, _, _ = list_quotations({"approvalStatus": "Pending", "page": 1, "pageSize": 20})
        self.assertGreaterEqual(total, 1)
        self.assertIn(saved["quotation"]["id"], {row["id"] for row in listed})
        for mutation in (
            lambda: save_draft(saved["quotation"]["id"], payload, submitted["version"]["modified"]),
            lambda: discard_draft(saved["quotation"]["id"], submitted["version"]["modified"]),
        ):
            with self.assertRaises(CrmApiException) as locked:
                mutation()
            self.assertEqual(locked.exception.code, "CONFLICT")

        frappe.set_user(self.manager)
        self.assertEqual(get_quotation(saved["quotation"]["id"])["quotation"]["id"], saved["quotation"]["id"])
        with self.assertRaises(CrmApiException) as reason_required:
            review_approval(saved["quotation"]["id"], "Rejected", "", submitted["version"]["modified"])
        self.assertEqual(reason_required.exception.code, "VALIDATION_ERROR")
        rejected = review_approval(saved["quotation"]["id"], "Rejected", "Revise commercial terms", submitted["version"]["modified"])
        self.assertEqual(rejected["version"]["approvalStatus"], "Rejected")
        self.assertEqual(rejected["approvals"][0]["comment"], "Revise commercial terms")
        rejected_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Quotation", "source_name": saved["quotation"]["id"],
                     "recipient_user": self.sales, "title": ["like", "%rejected"]},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (rejected_notice.category, rejected_notice.route),
            ("Quotation", f"/quotations/{saved['quotation']['id']}"),
        )

        frappe.set_user(self.sales)
        payload["items"][0]["unitPrice"] = "120000.00"
        revised = save_draft(saved["quotation"]["id"], payload, rejected["version"]["modified"])
        resubmitted = submit_for_approval(saved["quotation"]["id"], revised["version"]["modified"])
        self.assertEqual([row["attempt"] for row in resubmitted["approvals"]], [2, 1])

        frappe.set_user(self.manager)
        approved = review_approval(saved["quotation"]["id"], "Approved", "Approved", resubmitted["version"]["modified"])
        self.assertEqual((approved["version"]["status"], approved["version"]["approvalStatus"]), ("Published", "Approved"))
        self.assertTrue(approved["version"]["pdfAvailable"])
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", approved["quotation"]["opportunityId"], "stage"),
            QUOTATION_SENT,
        )
        approved_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Quotation", "source_name": saved["quotation"]["id"],
                     "recipient_user": self.sales, "title": ["like", "%approved"]},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (approved_notice.category, approved_notice.route),
            ("Quotation", f"/quotations/{saved['quotation']['id']}"),
        )
        with self.assertRaises(CrmApiException) as decided:
            review_approval(saved["quotation"]["id"], "Approved", "Again", resubmitted["version"]["modified"])
        self.assertEqual(decided.exception.code, "CONFLICT")
        approval = frappe.get_doc("CRM Quotation Approval", approved["approvals"][0]["id"])
        approval.decision_comment = "tampered"
        with self.assertRaises(frappe.ValidationError):
            approval.save(ignore_permissions=True)

    def test_submission_skips_manager_without_current_quotation_scope(self):
        saved, _ = self._ready_quotation()
        restricted = self._user("crm-quotation-restricted-manager@example.invalid", "CRM Manager")
        frappe.set_user(self.other_sales)
        unrelated = create_account({
            "name": f"Restricted Manager Account {random_string(6)}",
            "shortName": "Restricted",
            "segment": "Frontend",
            "tier": "A",
            "city": "Shanghai",
            "region": "East China",
            "owner": self.other_sales,
        })
        frappe.set_user("Administrator")
        add_user_permission("Customer", unrelated["id"], restricted, ignore_permissions=True)
        frappe.clear_cache(user=restricted)
        try:
            frappe.set_user(self.sales)
            submitted = submit_for_approval(saved["quotation"]["id"], saved["version"]["modified"])
            self.assertEqual(submitted["version"]["approvalStatus"], "Pending")
            self.assertFalse(frappe.db.exists("CRM Notification Event", {
                "source_doctype": "CRM Quotation",
                "source_name": saved["quotation"]["id"],
                "recipient_user": restricted,
            }))
            self.assertTrue(frappe.db.exists("CRM Notification Event", {
                "source_doctype": "CRM Quotation",
                "source_name": saved["quotation"]["id"],
                "recipient_user": self.manager,
            }))
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", unrelated["id"], restricted, ignore_permissions=True)
            frappe.clear_cache(user=restricted)

    def test_decision_skips_revoked_owner_but_real_notice_failure_rolls_back(self):
        saved, _ = self._ready_quotation()
        name = saved["quotation"]["id"]
        submitted = submit_for_approval(name, saved["version"]["modified"])
        frappe.set_user(self.manager)
        with patch("rayher_crm.services.notifications.create_notification", side_effect=RuntimeError("notice write failed")):
            with self.assertRaisesRegex(RuntimeError, "notice write failed"):
                review_approval(name, "Rejected", "Revise terms", submitted["version"]["modified"])
        self.assertEqual(get_quotation(name)["version"]["approvalStatus"], "Pending")
        account = frappe.db.get_value("CRM Quotation", name, "account")
        frappe.db.set_value("Customer", account, {
            "custom_crm_owner": self.other_sales, "custom_crm_visibility": "Private",
        })
        result = review_approval(name, "Rejected", "Revise terms", submitted["version"]["modified"])
        self.assertEqual(result["version"]["approvalStatus"], "Rejected")
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM Quotation", "source_name": name, "recipient_user": self.sales,
            "title": ["like", "%rejected"],
        }))

    def test_approval_publish_failure_rolls_back_decision_and_file(self):
        saved, _ = self._ready_quotation()
        submitted = submit_for_approval(saved["quotation"]["id"], saved["version"]["modified"])
        frappe.set_user(self.manager)
        with patch("rayher_crm.services.quotations.render_quotation_pdf", side_effect=RuntimeError("render failed")):
            with self.assertRaises(RuntimeError):
                review_approval(saved["quotation"]["id"], "Approved", "", submitted["version"]["modified"])
        current = get_quotation(saved["quotation"]["id"])
        self.assertEqual((current["version"]["status"], current["version"]["approvalStatus"]), ("Draft", "Pending"))
        self.assertEqual(current["approvals"][0]["status"], "Pending")
        self.assertFalse(current["version"]["pdfAvailable"])

    def test_approval_and_publish_wait_for_the_validated_rfq(self):
        saved, _ = self._ready_quotation()
        quotation_id = saved["quotation"]["id"]
        opportunity_id = saved["quotation"]["opportunityId"]
        # Test data only: the Opportunity has not passed the RFQ approval yet.
        frappe.db.set_value("CRM Opportunity", opportunity_id, "stage", CUSTOMER_BUDGET_APPROVED)
        for attempt in (
            lambda: submit_for_approval(quotation_id, saved["version"]["modified"]),
            lambda: self._publish(quotation_id, saved["version"]["modified"]),
        ):
            with self.assertRaises(CrmApiException) as blocked:
                attempt()
            self.assertEqual(blocked.exception.code, "INVALID_TRANSITION")
        self.assertEqual(get_quotation(quotation_id)["version"]["status"], "Draft")
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity_id, "stage"), CUSTOMER_BUDGET_APPROVED)

        frappe.db.set_value("CRM Opportunity", opportunity_id, "stage", RFQ_VALIDATED)
        published = self._publish(quotation_id, saved["version"]["modified"])
        self.assertEqual(published["version"]["status"], "Published")
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity_id, "stage"), QUOTATION_SENT)

    def test_create_list_detail_and_save_draft_against_real_schema(self):
        opportunity = self._opportunity()
        created = create_quotation({
            "opportunityId": opportunity["id"],
        })

        self.assertRegex(created["quotation"]["refNo"], r"^PK\d{8}-A\d+$")
        self.assertEqual(created["quotation"]["refNo"], created["version"]["refNo"])
        self.assertEqual(created["quotation"]["opportunityTitle"], opportunity["title"])
        listed, total, page, page_size = list_quotations({
            "opportunityId": opportunity["id"], "page": 1, "pageSize": 20,
        })
        self.assertEqual((total, page, page_size), (1, 1, 20))
        self.assertEqual([row["id"] for row in listed], [created["quotation"]["id"]])
        self.assertEqual(get_quotation(created["quotation"]["id"])["quotation"]["id"], created["quotation"]["id"])

        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validUntil", "items",
                "discountType", "discountValue", "paymentTerms", "incoterm",
                "deliveryMonths", "deliveryStart", "warrantyMonths", "warrantyStart",
                "installation", "training", "documentation", "packing",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        payload["quoteDate"] = "2026-08-10"
        payload["validityMonths"] = 2
        payload["deliveryMonths"] = 4
        payload["warrantyMonths"] = 12
        payload["incoterm"] = "CLIENT MUST NOT OVERRIDE"
        payload["paymentTerms"] = [
            {**term, "percentage": percentage}
            for term, percentage in zip(payload["paymentTerms"], ("20", "30", "40", "10"))
        ]
        payload["items"][0]["name"] = "Updated Device"
        payload["items"][0]["unitPrice"] = "123.45"
        payload["discountType"] = "Percentage"
        payload["discountValue"] = "10"
        saved = save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        self.assertEqual(saved["version"]["items"][0]["name"], "Updated Device")
        self.assertEqual(saved["version"]["items"][0]["unitPrice"], "123.45")
        self.assertEqual(saved["version"]["items"][0]["lineAmount"], "123.45")
        self.assertEqual(saved["version"]["subtotal"], "123.45")
        self.assertEqual(saved["version"]["discountValue"], "10.00")
        self.assertEqual(saved["version"]["discountAmount"], "12.35")
        self.assertEqual(saved["version"]["total"], "111.10")
        self.assertEqual(saved["version"]["primaryContactId"], self.quotation_contact["id"])
        self.assertEqual(saved["version"]["addressId"], self.quotation_site["id"])
        self.assertEqual(saved["version"]["customerName"], created["quotation"]["accountName"])
        self.assertEqual(saved["version"]["validityMonths"], 2)
        self.assertEqual(saved["version"]["validUntil"], "2026-10-10")
        self.assertEqual(saved["version"]["deliveryMonths"], 4)
        self.assertEqual(saved["version"]["warrantyMonths"], 12)
        self.assertEqual(saved["version"]["incoterm"], "FOB上海  FOB Shanghai")
        self.assertEqual(
            [term["percentage"] for term in saved["version"]["paymentTerms"]],
            ["20.00", "30.00", "40.00", "10.00"],
        )
        self.assertIn("20%", saved["version"]["paymentTerms"][0]["triggerCondition"])
        self.assertIn("40%", saved["version"]["paymentTerms"][2]["description"])

        frappe.db.set_value(
            "CRM Quotation Version", saved["version"]["id"],
            "validity_months", 0, update_modified=False,
        )
        legacy = get_quotation(created["quotation"]["id"])
        self.assertEqual(legacy["version"]["validityMonths"], 2)

        preview = unescape(render_quotation_html(
            frappe.get_doc("CRM Quotation", created["quotation"]["id"]),
            frappe.get_doc("CRM Quotation Version", saved["version"]["id"]),
        )).replace("\xa0", " ")
        for literal in (
            f"Ref. No.: {created['quotation']['refNo']}",
            "Updated Device",
            "FOB上海  FOB Shanghai",
            "收到订单1周内，买方电汇方式支付订单总价20%作为预付款。",
            "4月内(标准交期) 收到买方正式PO为准。",
            "12 个月自发货日起维保",
            "报价有效期2个月",
            "Installation, 5 days",
            "Packing in stretched foil, alupack film and wooden crates",
            "示例企业032有限公司",
            "2026/08/10",
        ):
            self.assertIn(literal, preview)

        payload["discountType"] = "Fixed Amount"
        payload["discountValue"] = "11.10"
        fixed_saved = save_draft(
            created["quotation"]["id"], payload, saved["version"]["modified"],
        )
        reloaded = get_quotation(created["quotation"]["id"])
        self.assertEqual(fixed_saved["version"]["discountType"], "Fixed Amount")
        self.assertEqual(reloaded["version"]["discountValue"], "11.10")
        self.assertEqual(reloaded["version"]["discountAmount"], "11.10")
        self.assertEqual(reloaded["version"]["total"], "112.35")

    def test_others_service_quotation_and_payment_total_gate(self):
        opportunity = self._opportunity()
        account_id = opportunity["accountId"]
        created = create_quotation({
            "accountId": account_id,
            "quotationType": "Service",
        })
        self.assertEqual(created["quotation"]["quotationType"], "Service")
        self.assertEqual(created["quotation"]["opportunityId"], "")
        self.assertEqual(created["quotation"]["opportunityTitle"], "Others")
        self.assertEqual(created["version"]["quotationType"], "Service")

        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validityMonths", "items",
                "discountType", "discountValue", "paymentTerms", "deliveryMonths", "warrantyMonths",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        payload["items"][0].update({"name": "Annual preventive maintenance", "unitPrice": "8000"})
        payload["paymentTerms"] = [
            {**term, "percentage": percentage}
            for term, percentage in zip(payload["paymentTerms"], ("20", "20", "20", "20"))
        ]
        saved = save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        with self.assertRaises(CrmApiException) as invalid_total:
            submit_for_approval(created["quotation"]["id"], saved["version"]["modified"])
        self.assertEqual(invalid_total.exception.code, "VALIDATION_ERROR")
        self.assertIn("100", str(invalid_total.exception))

        payload["paymentTerms"][3]["percentage"] = "40"
        saved = save_draft(created["quotation"]["id"], payload, saved["version"]["modified"])
        submitted = submit_for_approval(created["quotation"]["id"], saved["version"]["modified"])
        self.assertEqual(submitted["version"]["approvalStatus"], "Pending")
        html = render_quotation_html(
            frappe.get_doc("CRM Quotation", created["quotation"]["id"]),
            frappe.get_doc("CRM Quotation Version", saved["version"]["id"]),
        )
        self.assertIn("Service Quotation", html)
        self.assertIn("Annual preventive maintenance", html)

    def test_others_can_link_an_opportunity_without_rewriting_published_history(self):
        opportunity = self._opportunity()
        created = create_quotation({"accountId": opportunity["accountId"], "quotationType": "Service"})
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validityMonths", "items",
                "discountType", "discountValue", "paymentTerms", "deliveryMonths", "warrantyMonths",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        saved = save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        published = self._publish(created["quotation"]["id"], saved["version"]["modified"])

        linked = link_quotation_opportunity(
            created["quotation"]["id"], opportunity["id"], published["version"]["modified"],
        )
        self.assertEqual(linked["quotation"]["opportunityId"], opportunity["id"])
        self.assertEqual(linked["quotation"]["opportunityTitle"], opportunity["title"])
        self.assertEqual(linked["version"]["opportunityId"], "")

        other = create_quotation({"accountId": opportunity["accountId"], "quotationType": "Device"})
        with self.assertRaises(CrmApiException) as occupied:
            link_quotation_opportunity(other["quotation"]["id"], opportunity["id"], other["version"]["modified"])
        self.assertEqual(occupied.exception.code, "CONFLICT")

    def test_publish_version_history_decision_and_pdf(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validUntil", "items",
                "discountType", "discountValue", "paymentTerms", "incoterm",
                "deliveryMonths", "deliveryStart", "warrantyMonths", "warrantyStart",
                "installation", "training", "documentation", "packing",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        saved = save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        first = self._publish(created["quotation"]["id"], saved["version"]["modified"])
        self.assertEqual(first["version"]["status"], "Published")
        self.assertTrue(first["version"]["pdfAvailable"])

        second_draft = create_version(created["quotation"]["id"])
        self.assertEqual(second_draft["version"]["version"], 2)
        second = self._publish(created["quotation"]["id"], second_draft["version"]["modified"])
        statuses = {row["version"]: row["status"] for row in second["versions"]}
        self.assertEqual(statuses[1], "Superseded")
        self.assertEqual(statuses[2], "Published")

        for feedback_date, feedback_note in (("2026-08-10", 123), ("not-a-date", "Approved")):
            with self.subTest(feedback_date=feedback_date, feedback_note=feedback_note), self.assertRaises(CrmApiException) as invalid:
                record_decision(created["quotation"]["id"], "Accepted", feedback_date, feedback_note, second["version"]["modified"])
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")

        decided = record_decision(created["quotation"]["id"], "Accepted", "2026-08-10", "Customer approved", second["version"]["modified"])
        self.assertEqual(decided["version"]["status"], "Accepted")
        file_name, content = get_pdf_file(created["quotation"]["id"])
        self.assertRegex(file_name, r"^PK\d{8}-A\d+-V2\.pdf$")
        self.assertTrue(content.startswith(b"%PDF"))
    def test_template_context_preview_and_publish_render_atomicity(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validUntil", "items",
                "discountType", "discountValue", "paymentTerms", "incoterm",
                "deliveryMonths", "deliveryStart", "warrantyMonths", "warrantyStart",
                "installation", "training", "documentation", "packing",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        payload["discountType"] = "None"
        payload["discountValue"] = "0"
        payload["items"] = [
            {"lineKey": "device-1", "lineType": "Device", "parentDeviceKey": "", "name": "Process Module", "model": "PM-1", "description": "Primary process module", "pricingMode": "Charged", "quantity": 2, "unitPrice": "10000"},
            {"lineKey": "accessory-1", "lineType": "Accessory", "parentDeviceKey": "device-1", "name": "FFU", "model": "", "description": "Clean unit", "pricingMode": "Charged", "quantity": 1, "unitPrice": "5000"},
            {"lineKey": "device-2", "lineType": "Device", "parentDeviceKey": "", "name": "EFEM", "model": "EF-1", "description": "Transfer system", "pricingMode": "Charged", "quantity": 1, "unitPrice": "20000"},
        ]
        saved = save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        master = frappe.get_doc("CRM Quotation", created["quotation"]["id"])
        version = frappe.get_doc("CRM Quotation Version", saved["version"]["id"])
        context = _pdf_context(master, version)
        self.assertEqual(context["deviceCount"], 3)
        self.assertEqual(context["deviceGroups"], [
            {"lineKey": "device-1", "quantity": 2, "configurationSubtotal": "25000.00", "configurationUnitTotal": "12500.00", "displayIndex": 1, "name": "Process Module", "model": "PM-1"},
            {"lineKey": "device-2", "quantity": 1, "configurationSubtotal": "20000.00", "configurationUnitTotal": "20000.00", "displayIndex": 2, "name": "EFEM", "model": "EF-1"},
        ])
        self.assertEqual(context["items"][0]["configurationUnitTotal"], "12500.00")
        self.assertEqual(context["items"][2]["configurationUnitTotal"], "20000.00")
        self.assertEqual([row["displayIndex"] for row in context["items"]], [1, "", 2])
        filename, preview = get_preview_pdf(master.name, version.name)
        self.assertTrue(filename.endswith("-preview.pdf"))
        self.assertTrue(preview.startswith(b"%PDF"))
        with patch("rayher_crm.services.quotations.render_quotation_pdf", side_effect=RuntimeError("render failed")):
            with self.assertRaises(RuntimeError):
                self._publish(master.name, saved["version"]["modified"])
        version.reload()
        self.assertEqual(version.status, "Draft")
        self.assertFalse(version.pdf_file)
        self.assertTrue(frappe.db.exists("CRM Quotation Version", version.name))
        retry_modified = get_quotation(master.name)["version"]["modified"]
        self.assertIsNotNone(retry_modified)

        attached_before = set(frappe.get_all("File", filters={"attached_to_doctype": "CRM Quotation Version", "attached_to_name": version.name}, pluck="name"))
        from frappe.model.document import Document
        real_save = Document.save

        def fail_master_after_file(document, *args, **kwargs):
            if document.doctype == "CRM Quotation" and document.name == master.name and document.status == "Published":
                raise RuntimeError("master save failed")
            return real_save(document, *args, **kwargs)

        with patch("frappe.model.document.Document.save", new=fail_master_after_file):
            with self.assertRaises(RuntimeError):
                self._publish(
                    master.name,
                    retry_modified,
                )
        attached_after = set(frappe.get_all("File", filters={"attached_to_doctype": "CRM Quotation Version", "attached_to_name": version.name}, pluck="name"))
        self.assertEqual(attached_after, attached_before)
        version.reload()
        self.assertEqual(version.status, "Draft")
        self.assertFalse(version.pdf_file)
    def test_save_draft_rejects_fractional_quantity(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validUntil", "items",
                "discountType", "discountValue", "paymentTerms", "incoterm",
                "deliveryMonths", "deliveryStart", "warrantyMonths", "warrantyStart",
                "installation", "training", "documentation", "packing",
            )
        }
        payload["items"][0]["quantity"] = "1.5"
        with self.assertRaises(CrmApiException) as raised:
            save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        self.assertEqual(raised.exception.code, "VALIDATION_ERROR")

        for unit_price in ("1.001", "100000000000000000000000"):
            invalid_payload = deepcopy(payload)
            invalid_payload["items"][0]["quantity"] = 1
            invalid_payload["items"][0]["unitPrice"] = unit_price
            with self.subTest(unit_price=unit_price), self.assertRaises(CrmApiException) as invalid:
                save_draft(created["quotation"]["id"], invalid_payload, created["version"]["modified"])
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
    def test_validated_values_rejects_unbounded_payloads(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        master = frappe.get_doc("CRM Quotation", created["quotation"]["id"])
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validityMonths", "items",
                "discountType", "discountValue", "deliveryMonths", "warrantyMonths",
            )
        }
        too_many = deepcopy(payload)
        too_many["items"] = [deepcopy(payload["items"][0])]
        too_many["items"].extend({
            "lineKey": f"accessory-{index}", "lineType": "Accessory", "parentDeviceKey": "device-1",
            "name": "Included", "model": "", "description": "", "pricingMode": "Included",
            "quantity": 1, "unitPrice": "0",
        } for index in range(200))
        cases = [
            (too_many, "200"),
            ({**deepcopy(payload), "items": [{**payload["items"][0], "name": "N" * 141}]}, "140"),
            ({**deepcopy(payload), "items": [{**payload["items"][0], "model": "M" * 141}]}, "140"),
            ({**deepcopy(payload), "items": [{**payload["items"][0], "description": "D" * 5001}]}, "5,000"),
            ({**deepcopy(payload), "validityMonths": 121}, "120"),
        ]
        for candidate, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(CrmApiException, message):
                _validated_values(master, candidate, False)
    def test_stale_destructive_lifecycle_commands_are_rejected(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validityMonths", "items",
                "discountType", "discountValue", "deliveryMonths", "warrantyMonths",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        stale_modified = created["version"]["modified"]
        saved = save_draft(created["quotation"]["id"], payload, stale_modified)
        with self.assertRaises(CrmApiException) as discard_error:
            discard_draft(created["quotation"]["id"], stale_modified)
        self.assertEqual(discard_error.exception.code, "VERSION_CONFLICT")
        published = self._publish(created["quotation"]["id"], saved["version"]["modified"])
        with self.assertRaises(CrmApiException) as decision_error:
            record_decision(created["quotation"]["id"], "Accepted", "2026-08-10", "Approved", saved["version"]["modified"])
        self.assertEqual(decision_error.exception.code, "VERSION_CONFLICT")
        with self.assertRaises(CrmApiException) as missing_error:
            get_quotation(created["quotation"]["id"], "CRM-QTV-MISSING")
        self.assertEqual(missing_error.exception.code, "NOT_FOUND")
        self.assertEqual(get_quotation(created["quotation"]["id"])["version"]["modified"], published["version"]["modified"])

    def test_discard_removes_a_first_draft_together_with_its_quotation(self):
        saved, _ = self._ready_quotation()
        quotation_id = saved["quotation"]["id"]

        self.assertEqual(discard_draft(quotation_id, saved["version"]["modified"]), {"id": quotation_id, "deleted": True})

        self.assertFalse(frappe.db.exists("CRM Quotation Version", saved["version"]["id"]))
        self.assertFalse(frappe.db.exists("CRM Quotation", quotation_id))

    def test_discard_of_a_later_draft_returns_to_the_published_version(self):
        saved, _ = self._ready_quotation()
        quotation_id = saved["quotation"]["id"]
        first = self._publish(quotation_id, saved["version"]["modified"])
        draft = create_version(quotation_id)

        restored = discard_draft(quotation_id, draft["version"]["modified"])

        self.assertFalse(frappe.db.exists("CRM Quotation Version", draft["version"]["id"]))
        self.assertEqual(
            (restored["quotation"]["currentVersionId"], restored["quotation"]["status"], restored["quotation"]["latestVersion"]),
            (first["version"]["id"], "Published", 1),
        )
        self.assertEqual([row["id"] for row in restored["versions"]], [first["version"]["id"]])
        self.assertEqual(create_version(quotation_id)["version"]["version"], 2)

    def test_discard_of_a_later_draft_restores_the_status_the_customer_decided(self):
        saved, _ = self._ready_quotation()
        quotation_id = saved["quotation"]["id"]
        first = self._publish(quotation_id, saved["version"]["modified"])
        decided = record_decision(quotation_id, "Accepted", "2026-08-10", "Customer approved", first["version"]["modified"])
        self.assertEqual(decided["quotation"]["status"], "Accepted")
        draft = create_version(quotation_id)
        self.assertEqual(draft["quotation"]["status"], "Draft")

        restored = discard_draft(quotation_id, draft["version"]["modified"])

        self.assertEqual(
            (restored["quotation"]["currentVersionId"], restored["quotation"]["status"], restored["version"]["status"]),
            (first["version"]["id"], "Accepted", "Accepted"),
        )

    def test_a_draft_that_has_been_through_approval_is_not_discarded(self):
        # Approval history is immutable: discarding a rejected draft would take the Manager's decision with it.
        saved, _ = self._ready_quotation()
        quotation_id = saved["quotation"]["id"]
        submitted = submit_for_approval(quotation_id, saved["version"]["modified"])
        frappe.set_user(self.manager)
        rejected = review_approval(quotation_id, "Rejected", "Revise commercial terms", submitted["version"]["modified"])
        frappe.set_user(self.sales)
        notices = frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Quotation", "source_name": quotation_id})

        with self.assertRaises(CrmApiException) as refused:
            discard_draft(quotation_id, rejected["version"]["modified"])

        self.assertEqual(refused.exception.code, "CONFLICT")
        self.assertIn("been through approval", refused.exception.public_message)
        after = get_quotation(quotation_id)
        self.assertEqual((after["version"]["id"], after["version"]["status"], after["version"]["approvalStatus"]), (saved["version"]["id"], "Draft", "Rejected"))
        self.assertEqual([(row["attempt"], row["status"], row["comment"]) for row in after["approvals"]], [(1, "Rejected", "Revise commercial terms")])
        self.assertEqual(
            frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Quotation", "source_name": quotation_id}),
            notices,
        )

    def test_a_rejected_later_draft_is_not_discarded_either(self):
        saved, _ = self._ready_quotation()
        quotation_id = saved["quotation"]["id"]
        submitted = submit_for_approval(quotation_id, saved["version"]["modified"])
        frappe.set_user(self.manager)
        first = review_approval(quotation_id, "Approved", "Approved", submitted["version"]["modified"])
        frappe.set_user(self.sales)
        draft = create_version(quotation_id)
        resubmitted = submit_for_approval(quotation_id, draft["version"]["modified"])
        frappe.set_user(self.manager)
        rejected = review_approval(quotation_id, "Rejected", "Too low", resubmitted["version"]["modified"])
        frappe.set_user(self.sales)

        with self.assertRaises(CrmApiException) as refused:
            discard_draft(quotation_id, rejected["version"]["modified"])

        self.assertEqual(refused.exception.code, "CONFLICT")
        after = get_quotation(quotation_id)
        self.assertEqual(
            (after["quotation"]["currentVersionId"], after["quotation"]["currentPublishedVersionId"]),
            (draft["version"]["id"], first["version"]["id"]),
        )
        self.assertEqual([(row["attempt"], row["status"]) for row in after["approvals"]], [(2, "Rejected"), (1, "Approved")])

    def test_decision_does_not_overwrite_a_draft_created_after_master_read(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        payload = {
            key: created["version"][key]
            for key in (
                "primaryContactId", "addressId", "quoteDate", "validityMonths", "items",
                "discountType", "discountValue", "deliveryMonths", "warrantyMonths",
            )
        }
        payload["primaryContactId"] = self.quotation_contact["id"]
        payload["addressId"] = self.quotation_site["id"]
        saved = save_draft(created["quotation"]["id"], payload, created["version"]["modified"])
        published = self._publish(created["quotation"]["id"], saved["version"]["modified"])

        from rayher_crm.services import quotations as quotation_service

        real_lock_document = quotation_service.lock_document
        concurrent_draft = None

        def create_draft_before_version_lock(*args, **kwargs):
            nonlocal concurrent_draft
            if concurrent_draft is None:
                concurrent_draft = create_version(created["quotation"]["id"])
            return real_lock_document(*args, **kwargs)

        with patch(
            "rayher_crm.services.quotations.lock_document",
            side_effect=create_draft_before_version_lock,
        ):
            with self.assertRaises(CrmApiException) as conflict:
                record_decision(
                    created["quotation"]["id"], "Accepted", "2026-08-10", "Approved",
                    published["version"]["modified"],
                )

        self.assertEqual(conflict.exception.code, "CONFLICT")
        current = get_quotation(created["quotation"]["id"])
        self.assertEqual(current["quotation"]["currentVersionId"], concurrent_draft["version"]["id"])
        self.assertEqual(current["version"]["status"], "Draft")

    def test_expiry_rechecks_stale_candidates_and_preserves_terminal_status(self):
        opportunity = self._opportunity()
        created = create_quotation({"opportunityId": opportunity["id"]})
        version = frappe.get_doc("CRM Quotation Version", created["version"]["id"])
        version.status = "Accepted"
        version.valid_until = "2020-01-01"
        version.save(ignore_permissions=True)
        master = frappe.get_doc("CRM Quotation", created["quotation"]["id"])
        master.current_version = version.name
        master.current_published_version = version.name
        master.status = "Accepted"
        master.save(ignore_permissions=True)

        stale_rows = [frappe._dict(name=version.name, quotation=master.name)]
        with patch("rayher_crm.services.quotations.frappe.get_all", return_value=stale_rows):
            self.assertEqual(expire_quotations(), 0)
        version.reload()
        master.reload()
        self.assertEqual(version.status, "Accepted")
        self.assertEqual(master.status, "Accepted")

    def test_a_published_quotation_past_its_validity_is_expired_before_the_daily_job_records_it(self):
        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        quote_id, version_id = published["quotation"]["id"], published["version"]["id"]
        frappe.db.set_value("CRM Quotation Version", version_id, {
            "published_at": "2026-09-01 10:00:00", "valid_until": "2020-01-01",
        }, update_modified=False)
        frappe.clear_document_cache("CRM Quotation Version", version_id)

        def listed(status: str) -> set[str]:
            return {row["id"] for row in list_quotations({"status": status, "page": 1, "pageSize": 50})[0]}

        # The daily job has not run: the stored status is still Published, and the list, its filter and the
        # detail all say Expired.
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", version_id, "status"), "Published")
        detail = get_quotation(quote_id)
        self.assertEqual((detail["quotation"]["status"], detail["version"]["status"]), ("Expired", "Expired"))
        self.assertEqual(detail["versions"][0]["status"], "Expired")
        self.assertIn(quote_id, listed("Expired"))
        self.assertNotIn(quote_id, listed("Published"))
        self.assertEqual(next(row["status"] for row in list_quotations({"status": "Expired", "page": 1, "pageSize": 50})[0] if row["id"] == quote_id), "Expired")

        # The job records it: nothing the pages read changes.
        self.assertGreaterEqual(expire_quotations(), 1)
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", version_id, "status"), "Expired")
        detail = get_quotation(quote_id)
        self.assertEqual((detail["quotation"]["status"], detail["version"]["status"]), ("Expired", "Expired"))
        self.assertIn(quote_id, listed("Expired"))
        self.assertNotIn(quote_id, listed("Published"))

        # A Published Quotation within its validity is Published everywhere.
        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        current = get_quotation(published["quotation"]["id"])
        self.assertEqual((current["quotation"]["status"], current["version"]["status"]), ("Published", "Published"))
        self.assertIn(published["quotation"]["id"], listed("Published"))
        self.assertNotIn(published["quotation"]["id"], listed("Expired"))

    def test_reference_migration_plan_is_deterministic_per_initial_date(self):
        from rayher_crm.patches.v1_0.normalize_quotation_reference_numbers import plan_reference_updates
        rows = [
            {"name": "Q-2", "creation": "2026-08-10 09:00:00", "initial_date": "2026-08-10"},
            {"name": "Q-1", "creation": "2026-08-10 08:00:00", "initial_date": "2026-08-10"},
            {"name": "Q-3", "creation": "2026-08-11 08:00:00", "initial_date": "2026-08-11"},
        ]
        self.assertEqual(plan_reference_updates(rows), {
            "Q-1": "PK20260810-A1", "Q-2": "PK20260810-A2", "Q-3": "PK20260811-A1",
        })
