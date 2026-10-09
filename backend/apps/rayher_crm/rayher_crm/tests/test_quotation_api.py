from __future__ import annotations

import os
from contextlib import ExitStack
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
from rayher_crm.services import quotations as quotation_service
from rayher_crm.services.opportunities import (
    archive_strategy_opportunity,
    create_strategy_opportunity,
    unarchive_strategy_opportunity,
)
from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_EDIT, ARCHIVED_OPPORTUNITY_LINK
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

    def _refused_without_rollback(self, endpoint, *arguments) -> tuple[str, str]:
        # The API edge answers a refusal without a rollback, and the request then commits. Under test the request's
        # transaction is the test's own: a full rollback is counted here, not carried out, so what a refused request
        # wrote would still be seen.
        rollback, request_rollbacks = frappe.db.rollback, []

        def counted(*, save_point=None):
            return rollback(save_point=save_point) if save_point else request_rollbacks.append(True)

        frappe.local.response.pop("http_status_code", None)
        with patch.object(frappe.db, "rollback", side_effect=counted):
            response = endpoint(*arguments)
        self.assertEqual((request_rollbacks, response["data"], frappe.local.response.pop("http_status_code", None)), ([], None, 422))
        return response["error"]["code"], response["error"]["message"]

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

    def _request_rollbacks(self, after_rollback=None):
        """A patch of the request's full rollbacks, and the list that counts them.

        Under test the request's transaction is the test's own, fixtures included: a full rollback goes back to
        where the request began instead (a savepoint taken here), which undoes what an attempt wrote and keeps
        the fixtures. A rollback to a savepoint of the request's own is carried out as it is.
        """
        savepoint = f"crm_test_request_{frappe.generate_hash(length=8)}"
        frappe.db.savepoint(savepoint)
        rollback, rollbacks = frappe.db.rollback, []

        def to_request_start(*, save_point=None):
            if not save_point:
                rollbacks.append(savepoint)
            result = rollback(save_point=save_point or savepoint)
            if not save_point and after_rollback:
                # Model a concurrent change that becomes visible to the request after its full rollback.
                after_rollback()
            return result

        return patch.object(frappe.db, "rollback", side_effect=to_request_start), rollbacks

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

    def test_a_refused_create_leaves_no_quotation_and_the_opportunity_free(self):
        # The API edge answers a CrmApiException without a rollback and the request then commits. Under test the
        # request's transaction is the test's own: what a refused create wrote would be visible here.
        opportunity = self._opportunity()
        account_id = opportunity["accountId"]
        suffix = random_string(6)
        other_account = create_account({
            "name": f"Other Quotation Customer {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East China", "owner": self.sales,
        })
        foreign_contact = create_contact({
            "accountId": other_account["id"], "name": f"Other Quotation Contact {suffix}", "title": "Director",
            "department": "Engineering", "phone": "13800000002", "email": f"other-quotation-{suffix.lower()}@example.invalid",
            "relationship": "Developing", "owner": self.sales, "status": "Active",
        })
        quote_date = "2026-08-10"
        prefix = "PK20260810-A"
        counter_before = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,))
        without_line_key = [{"lineType": "Device", "name": "x"}]
        invalid_items = ("VALIDATION_ERROR", "Each quotation line needs a unique lineKey.")
        invalid_date = ("VALIDATION_ERROR", "Quotation date must be valid.")
        others = {"accountId": account_id, "quotationType": "Service", "quoteDate": quote_date}
        cases = (
            ({**others, "items": without_line_key}, invalid_items),
            ({"opportunityId": opportunity["id"], "quoteDate": quote_date, "items": without_line_key}, invalid_items),
            ({**others, "primaryContactId": foreign_contact["id"]}, ("CONFLICT", "ATTN must belong to the quotation customer.")),
            ({**others, "quoteDate": "not-a-date"}, invalid_date),
            ({**others, "quoteDate": "0000-00-00"}, invalid_date),
            ({**others, "quoteDate": "9" * 20}, invalid_date),
        )
        for payload, refusal in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(CrmApiException) as refused:
                    create_quotation(payload)
                self.assertEqual((refused.exception.code, refused.exception.public_message), refusal)
                self.assertEqual(
                    frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,)),
                    counter_before,
                )
        self.assertEqual(frappe.db.count("CRM Quotation", {"account": account_id}), 0)

        # Refused creates consumed no reference, and the Opportunity still takes its Quotation.
        created = create_quotation({"opportunityId": opportunity["id"], "quoteDate": quote_date})
        self.assertEqual(created["quotation"]["opportunityId"], opportunity["id"])
        self.assertTrue(created["quotation"]["refNo"].startswith(prefix))

    def test_a_creation_retry_revalidates_contact_and_address_before_writing(self):
        from frappe.model.document import Document

        for failure in (frappe.QueryDeadlockError, frappe.UniqueValidationError):
            for changed in ("inactive_contact", "moved_contact", "unlinked_address"):
                with self.subTest(failure=failure.__name__, changed=changed):
                    opportunity = self._opportunity()
                    contact_id, address_id = self.quotation_contact["id"], self.quotation_site["id"]
                    other = create_account({
                        "name": f"Retry Customer {random_string(8)}", "shortName": random_string(6),
                        "segment": "Frontend", "tier": "A", "city": "Shanghai",
                        "region": "East China", "owner": self.sales,
                    })
                    version_count = frappe.db.count("CRM Quotation Version", {"account": opportunity["accountId"]})
                    counter_before = frappe.db.sql(
                        "SELECT `current` FROM `tabSeries` WHERE `name` = %s", ("PK20320303-A",),
                    )
                    insert, attempts = Document.db_insert, []

                    def fail_first_insert(document, *args, **kwargs):
                        if document.doctype == "CRM Quotation":
                            attempts.append(document.ref_no)
                            if len(attempts) == 1:
                                raise failure("retry the creation")
                        return insert(document, *args, **kwargs)

                    def change_relation():
                        if changed == "inactive_contact":
                            frappe.db.set_value("Contact", contact_id, "custom_crm_status", "Left Company")
                        elif changed == "moved_contact":
                            frappe.db.set_value("Dynamic Link", {
                                "parent": contact_id, "parenttype": "Contact", "link_doctype": "Customer",
                            }, "link_name", other["id"])
                        else:
                            frappe.db.delete("Dynamic Link", {
                                "parent": address_id, "parenttype": "Address", "link_doctype": "Customer",
                            })

                    rolled_back, rollbacks = self._request_rollbacks(after_rollback=change_relation)
                    with rolled_back, patch("frappe.model.document.Document.db_insert", new=fail_first_insert):
                        with self.assertRaises(CrmApiException) as refused:
                            create_quotation({
                                "opportunityId": opportunity["id"], "quoteDate": "2032-03-03",
                                "primaryContactId": contact_id, "addressId": address_id,
                            })
                    expected_messages = {
                        "inactive_contact": "ATTN must be an active contact.",
                        "moved_contact": "ATTN must belong to the quotation customer.",
                        "unlinked_address": "Quotation address was not found.",
                    }
                    self.assertEqual(refused.exception.public_message, expected_messages[changed])
                    self.assertEqual((len(attempts), len(rollbacks)), (1, 1))
                    self.assertFalse(frappe.db.exists("CRM Quotation", {"opportunity": opportunity["id"]}))
                    self.assertEqual(frappe.db.count("CRM Quotation Version", {"account": opportunity["accountId"]}), version_count)
                    self.assertEqual(frappe.db.sql(
                        "SELECT `current` FROM `tabSeries` WHERE `name` = %s", ("PK20320303-A",),
                    ), counter_before)

    def test_a_creation_retry_refreshes_contact_and_address_snapshots(self):
        from frappe.model.document import Document

        for failure in (frappe.QueryDeadlockError, frappe.UniqueValidationError):
            with self.subTest(failure=failure.__name__):
                opportunity = self._opportunity()
                contact_id, address_id = self.quotation_contact["id"], self.quotation_site["id"]
                insert, attempts = Document.db_insert, []

                def fail_first_insert(document, *args, **kwargs):
                    if document.doctype == "CRM Quotation":
                        attempts.append(document.ref_no)
                        if len(attempts) == 1:
                            raise failure("retry the creation")
                    return insert(document, *args, **kwargs)

                def change_snapshot():
                    frappe.db.set_value("Contact", contact_id, "designation", "Updated Director")
                    frappe.db.set_value("Address", address_id, "address_line1", "Updated Road")

                rolled_back, rollbacks = self._request_rollbacks(after_rollback=change_snapshot)
                with rolled_back, patch("frappe.model.document.Document.db_insert", new=fail_first_insert):
                    created = create_quotation({
                        "opportunityId": opportunity["id"], "primaryContactId": contact_id, "addressId": address_id,
                    })
                self.assertEqual((len(attempts), len(rollbacks)), (2, 1))
                self.assertEqual(attempts[0], attempts[1])
                self.assertEqual(created["version"]["attentionTitle"], "Updated Director")
                self.assertIn("Updated Road", created["version"]["addressText"])

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

    def test_a_creation_the_database_rolls_back_for_a_deadlock_is_made_again(self):
        from rayher_crm.services.quotations import _next_ref_no

        opportunity = self._opportunity()
        allocations = []

        def deadlocked_once(quote_date):
            allocations.append(quote_date)
            if len(allocations) == 1:
                # As MariaDB answers the transaction it rolls back to break a deadlock (1213).
                raise frappe.QueryDeadlockError("Deadlock found when trying to get lock; try restarting transaction")
            return _next_ref_no(quote_date)

        rolled_back, rollbacks = self._request_rollbacks()
        with rolled_back, patch("rayher_crm.services.quotations._next_ref_no", side_effect=deadlocked_once):
            created = create_quotation({"opportunityId": opportunity["id"]})

        self.assertEqual((len(allocations), len(rollbacks)), (2, 1))
        self.assertEqual(created["quotation"]["opportunityId"], opportunity["id"])
        self.assertRegex(created["quotation"]["refNo"], r"^PK\d{8}-A\d+$")
        self.assertEqual(created["version"]["refNo"], created["quotation"]["refNo"])
        self.assertEqual(frappe.db.count("CRM Quotation", {"opportunity": opportunity["id"]}), 1)

    def test_a_creation_whose_insert_the_database_rolls_back_for_a_deadlock_is_made_again(self):
        from frappe.model.document import Document

        opportunity = self._opportunity()
        insert, refused = Document.db_insert, []

        def deadlocked_once(document, *args, **kwargs):
            if document.doctype == "CRM Quotation" and not refused:
                refused.append(document.ref_no)
                raise frappe.QueryDeadlockError("Deadlock found when trying to get lock; try restarting transaction")
            return insert(document, *args, **kwargs)

        rolled_back, rollbacks = self._request_rollbacks()
        with rolled_back, patch("frappe.model.document.Document.db_insert", new=deadlocked_once):
            created = create_quotation({"opportunityId": opportunity["id"]})

        self.assertEqual(len(rollbacks), 1)
        # The rolled back attempt took nothing with it: the next one is given the same reference.
        self.assertEqual(created["quotation"]["refNo"], refused[0])
        self.assertEqual(frappe.db.count("CRM Quotation", {"opportunity": opportunity["id"]}), 1)

    def test_a_creation_deadlocked_on_every_attempt_answers_with_the_deadlock(self):
        from rayher_crm.services.quotations import QUOTATION_CREATE_ATTEMPTS

        opportunity = self._opportunity()
        deadlock = frappe.QueryDeadlockError("Deadlock found when trying to get lock; try restarting transaction")
        rolled_back, rollbacks = self._request_rollbacks()
        with rolled_back, patch("rayher_crm.services.quotations._next_ref_no", side_effect=deadlock) as allocate:
            with self.assertRaises(frappe.QueryDeadlockError):
                create_quotation({"opportunityId": opportunity["id"]})

        self.assertEqual((allocate.call_count, len(rollbacks)), (QUOTATION_CREATE_ATTEMPTS, QUOTATION_CREATE_ATTEMPTS))
        self.assertFalse(frappe.db.exists("CRM Quotation", {"opportunity": opportunity["id"]}))

    def test_a_creation_that_another_beats_to_the_opportunity_is_told_it_has_its_quotation(self):
        opportunity = self._opportunity()
        # The other Quotation was given the Opportunity some other way, not under its lock (a creation and a link look
        # for it under that lock, and are told), and committed after this request's snapshot and its first look:
        # neither the check before the attempts nor that look sees it. The attempt then meets it (the insert tripping
        # on the Opportunity's unique key, and the rollback that follows), and the next attempt's look tells the
        # creation the Opportunity has its Quotation.
        other = create_quotation({"opportunityId": opportunity["id"]})
        exists, unseen = frappe.db.exists, []
        look, missed = quotation_service._assert_opportunity_has_no_quotation, []

        def before_the_other(doctype, filters=None, *args, **kwargs):
            if doctype == "CRM Quotation" and filters == {"opportunity": opportunity["id"]} and not unseen:
                unseen.append(filters)
                return None
            return exists(doctype, filters, *args, **kwargs)

        def first_look_misses(name, linking=""):
            if not missed:
                missed.append(name)
                return None
            return look(name, linking)

        messages = len(frappe.local.message_log)
        rolled_back, rollbacks = self._request_rollbacks()
        with rolled_back, patch.object(frappe.db, "exists", side_effect=before_the_other), patch.object(
            quotation_service, "_assert_opportunity_has_no_quotation", side_effect=first_look_misses
        ):
            with self.assertRaises(CrmApiException) as refused:
                create_quotation({"opportunityId": opportunity["id"]})

        self.assertEqual(
            (refused.exception.code, refused.exception.public_message),
            ("CONFLICT", "This Opportunity already has a Quotation."),
        )
        self.assertEqual((missed, len(rollbacks)), ([opportunity["id"]], 1))
        # Frappe's "must be unique" for a refused insert is not left behind for the answer to carry.
        self.assertEqual(len(frappe.local.message_log), messages)
        self.assertEqual(
            frappe.get_all("CRM Quotation", filters={"opportunity": opportunity["id"]}, pluck="name"),
            [other["quotation"]["id"]],
        )

    def _quote_on(self, account_id: str, quote_date: str) -> tuple[dict, str, int]:
        created = create_quotation({"accountId": account_id, "quotationType": "Service", "quoteDate": quote_date})
        prefix, number = created["quotation"]["refNo"].rsplit("A", 1)
        return created, f"{prefix}A", int(number)

    def test_a_reference_is_counted_on_past_those_its_date_has_already(self):
        account_id = self._opportunity()["accountId"]
        first, prefix, number = self._quote_on(account_id, "2031-03-03")
        self.assertEqual(prefix, "PK20310303-A")
        self.assertEqual(self._quote_on(account_id, "2031-03-03")[2], number + 1)

        # References issued before the date's count was kept: the count starts past the highest.
        frappe.db.sql("DELETE FROM `tabSeries` WHERE `name` = %s", (prefix,))
        self.assertEqual(self._quote_on(account_id, "2031-03-03")[2], number + 2)
        # A reference written some other way, past the count: the count goes on past it.
        frappe.db.set_value("CRM Quotation", first["quotation"]["id"], "ref_no", f"{prefix}{number + 7}", update_modified=False)
        self.assertEqual(self._quote_on(account_id, "2031-03-03")[2], number + 8)
        self.assertEqual(self._quote_on(account_id, "2031-03-03")[2], number + 9)

    def test_a_reference_is_not_given_again_once_its_quotation_is_discarded(self):
        account_id = self._opportunity()["accountId"]
        discarded, prefix, number = self._quote_on(account_id, "2031-04-04")
        discard_draft(discarded["quotation"]["id"], discarded["version"]["modified"])
        self.assertFalse(frappe.db.exists("CRM Quotation", {"ref_no": f"{prefix}{number}"}))

        self.assertEqual(self._quote_on(account_id, "2031-04-04")[1:], (prefix, number + 1))

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

    def test_a_validity_ending_after_9999_12_31_answers_422_and_writes_nothing(self):
        from rayher_crm.api.v1 import quotations as quotation_api

        refusal = ("VALIDATION_ERROR", "Quotation validity must end by 9999-12-31.")

        saved, payload = self._ready_quotation()
        quotation_id, modified = saved["quotation"]["id"], saved["version"]["modified"]
        before = get_quotation(quotation_id)
        # The date alone does not decide: the validity months move the end past 9999-12-31.
        for quote_date, months in (("9999-12-31", 1), ("9999-12-01", 1), ("9999-11-30", 2), ("9990-01-01", 120)):
            with self.subTest(quote_date=quote_date, months=months):
                draft = {**payload, "quoteDate": quote_date, "validityMonths": months}
                self.assertEqual(self._refused_without_rollback(quotation_api.save_draft, quotation_id, draft, modified), refusal)
        self.assertEqual(get_quotation(quotation_id), before)

        # A create is refused before its Quotation is written, so the Opportunity still takes one.
        opportunity = self._opportunity()
        for quotation_input in (
            {"opportunityId": opportunity["id"], "quoteDate": "9999-12-31"},
            {"accountId": opportunity["accountId"], "quotationType": "Service", "quoteDate": "9999-12-31"},
        ):
            with self.subTest(quotation_input=quotation_input):
                self.assertEqual(self._refused_without_rollback(quotation_api.create_quotation, quotation_input), refusal)
        self.assertEqual(frappe.db.count("CRM Quotation", {"account": opportunity["accountId"]}), 0)
        self.assertEqual(create_quotation({"opportunityId": opportunity["id"]})["quotation"]["opportunityId"], opportunity["id"])

        # A validity ending on 9999-12-31 itself is kept.
        kept = save_draft(quotation_id, {**payload, "quoteDate": "9989-12-31", "validityMonths": 120}, modified)
        self.assertEqual((kept["version"]["quoteDate"], kept["version"]["validUntil"]), ("9989-12-31", "9999-12-31"))

    def test_a_stored_validity_ending_after_9999_12_31_is_refused_before_any_write(self):
        # A version stored some other way (Desk, an import) can hold such a date. The commands that work its values out
        # again refuse it and leave the Quotation as it was: before they write, or, for an approval, which has written
        # its decision by then, by rolling back to its savepoint.
        refusal = ("VALIDATION_ERROR", "Quotation validity must end by 9999-12-31.")

        def store_the_last_day(version_id: str) -> None:
            frappe.db.set_value("CRM Quotation Version", version_id, "quote_date", "9999-12-31", update_modified=False)
            frappe.clear_document_cache("CRM Quotation Version", version_id)

        def assert_refused(quotation_id: str, command) -> None:
            notices = {"source_doctype": "CRM Quotation", "source_name": quotation_id}
            before, notices_before = get_quotation(quotation_id), frappe.db.count("CRM Notification Event", notices)
            with self.assertRaises(CrmApiException) as refused:
                command()
            self.assertEqual((refused.exception.code, refused.exception.public_message), refusal)
            self.assertEqual(get_quotation(quotation_id), before)
            self.assertEqual(frappe.db.count("CRM Notification Event", notices), notices_before)

        draft, _ = self._ready_quotation()
        quotation_id, modified = draft["quotation"]["id"], draft["version"]["modified"]
        store_the_last_day(draft["version"]["id"])
        assert_refused(quotation_id, lambda: submit_for_approval(quotation_id, modified))
        assert_refused(quotation_id, lambda: self._publish(quotation_id, modified))

        draft, _ = self._ready_quotation()
        quotation_id = draft["quotation"]["id"]
        pending = submit_for_approval(quotation_id, draft["version"]["modified"])
        store_the_last_day(pending["version"]["id"])
        frappe.set_user(self.manager)
        assert_refused(quotation_id, lambda: review_approval(quotation_id, "Approved", "", pending["version"]["modified"]))
        frappe.set_user(self.sales)

        draft, _ = self._ready_quotation()
        quotation_id = draft["quotation"]["id"]
        published = self._publish(quotation_id, draft["version"]["modified"])
        store_the_last_day(published["version"]["id"])
        assert_refused(quotation_id, lambda: create_version(quotation_id))

    def test_an_unreadable_quote_date_answers_422_and_leaves_the_draft_unchanged(self):
        from rayher_crm.api.v1 import quotations as quotation_api

        saved, payload = self._ready_quotation()
        quotation_id, modified = saved["quotation"]["id"], saved["version"]["modified"]
        before = get_quotation(quotation_id)
        # `getdate` raises Frappe's ValidationError for text it cannot read and OverflowError for a number too large to
        # read as a date. For a zero date, or one Frappe takes for none such as 0001-01-01, it answers None, which
        # `add_months` took for today: the draft was saved with that date and a validity counted from today.
        for quote_date in ("not-a-date", "9" * 20, "0000-00-00", "0001-01-01"):
            with self.subTest(quote_date=quote_date):
                draft = {**payload, "quoteDate": quote_date}
                self.assertEqual(
                    self._refused_without_rollback(quotation_api.save_draft, quotation_id, draft, modified),
                    ("VALIDATION_ERROR", "Quotation date must be valid."),
                )
                self.assertEqual(get_quotation(quotation_id), before)
        # A month value that is no number keeps its own message.
        self.assertEqual(
            self._refused_without_rollback(quotation_api.save_draft, quotation_id, {**payload, "validityMonths": "two"}, modified),
            ("VALIDATION_ERROR", "Quotation date and month values must be valid."),
        )
        self.assertEqual(get_quotation(quotation_id), before)

    def test_a_stored_zero_quote_date_is_refused_before_any_write(self):
        from rayher_crm.api.v1 import quotations as quotation_api

        # A draft saved before the date was checked can hold 0000-00-00, which MariaDB keeps and gives back as text.
        # Submitting it works its values out again and is refused as the date would be in a request.
        draft, _ = self._ready_quotation()
        quotation_id, version_id = draft["quotation"]["id"], draft["version"]["id"]
        frappe.db.set_value("CRM Quotation Version", version_id, "quote_date", "0000-00-00", update_modified=False)
        frappe.clear_document_cache("CRM Quotation Version", version_id)
        before = get_quotation(quotation_id)
        self.assertEqual(before["version"]["quoteDate"], "0000-00-00")
        self.assertEqual(
            self._refused_without_rollback(quotation_api.submit_for_approval, quotation_id, draft["version"]["modified"]),
            ("VALIDATION_ERROR", "Quotation date must be valid."),
        )
        self.assertEqual(get_quotation(quotation_id), before)

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

    def test_a_quotation_of_an_archived_opportunity_is_frozen_with_it_and_none_is_started_or_linked(self):
        saved, _ = self._ready_quotation()
        other = self._opportunity()
        unlinked = create_quotation({"accountId": other["accountId"]})
        frappe.set_user(self.manager)
        for name in (saved["quotation"]["opportunityId"], other["id"]):
            archive_strategy_opportunity(name)

        frappe.set_user(self.sales)
        for message, call in (
            (ARCHIVED_OPPORTUNITY_EDIT, lambda: submit_for_approval(saved["quotation"]["id"], saved["version"]["modified"])),
            (ARCHIVED_OPPORTUNITY_LINK, lambda: create_quotation({"opportunityId": other["id"]})),
            (ARCHIVED_OPPORTUNITY_LINK, lambda: link_quotation_opportunity(unlinked["quotation"]["id"], other["id"], unlinked["version"]["modified"])),
        ):
            with self.assertRaises(CrmApiException) as refused:
                call()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", message))
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", saved["version"]["id"], "approval_status"), "Not Submitted")
        self.assertFalse(frappe.db.get_value("CRM Quotation", unlinked["quotation"]["id"], "opportunity"))
        self.assertEqual(frappe.db.count("CRM Quotation", {"opportunity": other["id"]}), 0)

    def test_every_write_of_a_quotation_of_an_archived_opportunity_waits_for_the_restore(self):
        def refused(call):
            with self.assertRaises(CrmApiException) as raised:
                call()
            self.assertEqual((raised.exception.code, raised.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_EDIT))

        draft, payload = self._ready_quotation()
        pending, _ = self._ready_quotation()
        pending = submit_for_approval(pending["quotation"]["id"], pending["version"]["modified"])
        published, _ = self._ready_quotation()
        published = self._publish(published["quotation"]["id"], published["version"]["modified"])
        shapes = (draft, pending, published)
        draft_id, pending_id, published_id = (shape["quotation"]["id"] for shape in shapes)
        self.assertEqual([get_quotation(name)["quotation"]["opportunityArchived"] for name in (draft_id, pending_id, published_id)], [False] * 3)
        frappe.set_user(self.manager)
        for shape in shapes:
            archive_strategy_opportunity(shape["quotation"]["opportunityId"])

        # Frozen with its Opportunity, and said so: no draft saved or discarded, no submission, no new version, no
        # customer decision, no approval either way, no publication.
        frappe.set_user(self.sales)
        self.assertEqual([get_quotation(name)["quotation"]["opportunityArchived"] for name in (draft_id, pending_id, published_id)], [True] * 3)
        refused(lambda: save_draft(draft_id, payload, draft["version"]["modified"]))
        refused(lambda: discard_draft(draft_id, draft["version"]["modified"]))
        refused(lambda: submit_for_approval(draft_id, draft["version"]["modified"]))
        refused(lambda: create_version(published_id))
        refused(lambda: record_decision(published_id, "Accepted", "2026-10-01", "Signed", published["version"]["modified"]))
        frappe.set_user(self.manager)
        refused(lambda: review_approval(pending_id, "Rejected", "Too expensive", pending["version"]["modified"]))
        refused(lambda: review_approval(pending_id, "Approved", "", pending["version"]["modified"]))
        refused(lambda: publish_version(draft_id, draft["version"]["modified"]))
        self.assertTrue(frappe.db.exists("CRM Quotation", draft_id))
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", draft["version"]["id"], ["status", "approval_status"]), ("Draft", "Not Submitted"))
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", pending["version"]["id"], "approval_status"), "Pending")
        self.assertEqual(frappe.db.get_value("CRM Quotation", published_id, ["latest_version_no", "status"]), (1, "Published"))

        # Restored, the Quotation takes its writes again.
        unarchive_strategy_opportunity(draft["quotation"]["opportunityId"])
        frappe.set_user(self.sales)
        self.assertFalse(get_quotation(draft_id)["quotation"]["opportunityArchived"])
        self.assertEqual(save_draft(draft_id, payload, draft["version"]["modified"])["version"]["status"], "Draft")

    def test_a_quotation_started_or_linked_as_its_opportunity_is_archived_is_refused_under_its_lock(self):
        target = self._opportunity()
        unlinked = create_quotation({"accountId": target["accountId"]})
        frappe.set_user(self.manager)
        archive_strategy_opportunity(target["id"])
        frappe.set_user(self.sales)

        def stale(name, archived_message=ARCHIVED_OPPORTUNITY_LINK):
            # The first read misses the archive, as one committed after this request's snapshot would.
            doc = frappe.get_doc("CRM Opportunity", name)
            doc.archived = 0
            return doc

        prefix = f"PK{frappe.utils.getdate(frappe.utils.today()).strftime('%Y%m%d')}-A"
        counter = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,))
        with patch.object(quotation_service, "_require_opportunity", side_effect=stale):
            for call in (
                lambda: create_quotation({"opportunityId": target["id"]}),
                lambda: link_quotation_opportunity(unlinked["quotation"]["id"], target["id"], unlinked["version"]["modified"]),
            ):
                with self.assertRaises(CrmApiException) as refused:
                    call()
                self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_LINK))
        # The read under the Opportunity's lock saw it, before anything was written: no Quotation, no reference counted
        # for the day, the other not linked.
        self.assertEqual(frappe.db.count("CRM Quotation", {"opportunity": target["id"]}), 0)
        self.assertEqual(frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,)), counter)
        self.assertEqual(frappe.db.count("CRM Quotation Version", {"opportunity": target["id"]}), 0)
        self.assertFalse(frappe.db.get_value("CRM Quotation", unlinked["quotation"]["id"], "opportunity"))

    def _watched_paths(self, events: list[tuple]):
        """Spies on the reads and locks of a Quotation's creation and link, in the order they come."""

        real = {
            name: getattr(quotation_service, name)
            for name in ("_next_ref_no", "assert_account_active", "_locked_deal", "_assert_opportunity_has_no_quotation", "_lock_quotation")
        }

        def references(quote_date):
            events.append(("references",))
            return real["_next_ref_no"](quote_date)

        def account(name, message, **kwargs):
            events.append(("account",))
            return real["assert_account_active"](name, message, **kwargs)

        def deal(name, account_id):
            # And whether the Opportunity has a Quotation's row yet, as this request sees it.
            events.append(("opportunity", bool(frappe.db.exists("CRM Quotation", {"opportunity": name}))))
            return real["_locked_deal"](name, account_id)

        def look(name, linking=""):
            events.append(("its quotation looked for",))
            return real["_assert_opportunity_has_no_quotation"](name, linking)

        def quotation(name):
            events.append(("quotation",))
            return real["_lock_quotation"](name)

        stack = ExitStack()
        for name, spy in (
            ("_next_ref_no", references), ("assert_account_active", account), ("_locked_deal", deal),
            ("_assert_opportunity_has_no_quotation", look), ("_lock_quotation", quotation),
        ):
            stack.enter_context(patch.object(quotation_service, name, side_effect=spy))
        return stack

    def test_a_quotation_takes_its_opportunitys_row_before_writing_its_own_and_so_does_a_link(self):
        """Every Quotation path takes a Quotation's rows, then the Account's, then the Opportunity's: a writer its
        Quotation's row first, a link the Quotation's row; a creation, which has no Quotation's row yet, counts its
        date's reference last (on its date's row in tabSeries, no Quotation's row locked).
        None holds the Account's row while it waits for a Quotation's (an exclusive request queued on the Account's
        row holds back every shared request after it, and three would wait on each other)."""

        opportunity = self._opportunity()
        events: list[tuple] = []
        real_sql = frappe.db.sql
        statements: list[str] = []

        def sql(query, *args, **kwargs):
            statements.append(" ".join(str(query).split()))
            return real_sql(query, *args, **kwargs)

        def watched():
            stack = self._watched_paths(events)
            stack.enter_context(patch.object(frappe.db, "sql", side_effect=sql))
            return stack

        def unlocked_looks():
            # The unique `opportunity` is never read with a lock (it would take the gap that the Opportunities
            # without a Quotation share): the look, and every other statement of the two paths.
            looks = [statement for statement in statements if "`tabCRM Quotation`" in statement and "`opportunity` =" in statement]
            self.assertTrue(looks)
            self.assertFalse([statement for statement in looks if "FOR UPDATE" in statement or "LOCK IN SHARE MODE" in statement], looks)

        # The creation: the Account's row, the Opportunity's (no Quotation's row of it yet) and its Quotation looked
        # for, then its date's reference counted, before the Quotation's row is written.
        with watched():
            create_quotation({"opportunityId": opportunity["id"]})
        self.assertEqual(events, [("account",), ("opportunity", False), ("its quotation looked for",), ("references",)])
        self.assertEqual(frappe.db.count("CRM Quotation", {"opportunity": opportunity["id"]}), 1)
        unlocked_looks()

        # The link: the Quotation's row, the Account's, the Opportunity's and its Quotation looked for.
        other = self._opportunity()
        unlinked = create_quotation({"accountId": other["accountId"]})
        events.clear()
        statements.clear()
        with watched():
            link_quotation_opportunity(unlinked["quotation"]["id"], other["id"], unlinked["version"]["modified"])
        self.assertEqual(events[:4], [("quotation",), ("account",), ("opportunity", False), ("its quotation looked for",)])
        unlocked_looks()

        # The second link to the Opportunity is told it has its Quotation (its own Quotation's row taken first, as its
        # writers take it).
        second = create_quotation({"accountId": other["accountId"]})
        events.clear()
        with watched(), self.assertRaises(CrmApiException) as taken:
            link_quotation_opportunity(second["quotation"]["id"], other["id"], second["version"]["modified"])
        self.assertEqual((taken.exception.code, taken.exception.public_message), ("CONFLICT", "This Opportunity already has a Quotation."))
        self.assertEqual(events, [("quotation",), ("account",), ("opportunity", True), ("its quotation looked for",)])
        self.assertFalse(frappe.db.get_value("CRM Quotation", second["quotation"]["id"], "opportunity"))

        # A Quotation linked to the Opportunity already (a stale page) is told so.
        linked_modified = get_quotation(unlinked["quotation"]["id"])["version"]["modified"]
        events.clear()
        with watched(), self.assertRaises(CrmApiException) as linked:
            link_quotation_opportunity(unlinked["quotation"]["id"], other["id"], linked_modified)
        self.assertEqual(linked.exception.public_message, "This Quotation is already linked to an Opportunity.")
        self.assertEqual(events, [("quotation",), ("account",), ("opportunity", True), ("its quotation looked for",)])

    def test_a_quotations_creation_takes_its_opportunitys_row_and_looks_again_on_each_attempt(self):
        opportunity = self._opportunity()
        taken = create_quotation({"accountId": opportunity["accountId"]})["quotation"]["refNo"]
        events: list[tuple] = []
        refs = [taken]  # the first attempt takes a reference another Quotation has
        real_ref = quotation_service._next_ref_no

        # The retry rolls the whole transaction back, the locks with it, so each attempt takes them again; here the
        # rollback keeps this test's records (its own transaction), and the order of the reads shows the retry.
        stack = self._watched_paths(events)
        stack.enter_context(patch.object(quotation_service, "_next_ref_no", side_effect=lambda quote_date: (
            events.append(("references",)) or (refs.pop() if refs else real_ref(quote_date))
        )))
        rollback = stack.enter_context(patch.object(frappe.db, "rollback"))
        with stack:
            created = create_quotation({"opportunityId": opportunity["id"]})
        self.assertEqual(events, [("account",), ("opportunity", False), ("its quotation looked for",), ("references",)] * 2)
        rollback.assert_called_once_with()
        self.assertNotEqual(created["quotation"]["refNo"], taken)
        self.assertEqual(frappe.db.count("CRM Quotation", {"opportunity": opportunity["id"]}), 1)

    def _recorded_locks_and_writes(self, events: list[str]):
        """Spies on the Account's and the Opportunity's locked reads, the PDF's content lock and every statement that
        writes, in the order they come."""

        from rayher_crm.services import private_file_lifecycle

        real_account, real_deal = quotation_service.assert_account_active, quotation_service._locked_deal
        real_content, real_sql = private_file_lifecycle.lock_upload_contents, frappe.db.sql

        def account(name, message, **kwargs):
            events.append("account")
            return real_account(name, message, **kwargs)

        def deal(name, account_id):
            events.append("opportunity")
            return real_deal(name, account_id)

        def content(uploads):
            events.append("content lock")
            return real_content(uploads)

        def sql(query, *args, **kwargs):
            words = str(query).split(None, 1)
            if words and words[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
                events.append("write")
            return real_sql(query, *args, **kwargs)

        stack = ExitStack()
        stack.enter_context(patch.object(quotation_service, "assert_account_active", side_effect=account))
        stack.enter_context(patch.object(quotation_service, "_locked_deal", side_effect=deal))
        stack.enter_context(patch.object(private_file_lifecycle, "lock_upload_contents", side_effect=content))
        stack.enter_context(patch.object(frappe.db, "sql", side_effect=sql))
        return stack

    def test_a_lost_savepoint_does_not_replace_a_quotation_writers_own_error(self):
        """A deadlock rolls the whole transaction back, the savepoint with it: the rollback to the savepoint then fails,
        the writer's own error is still the one raised, and the transaction is rolled back whole (the request edge
        commits after a refusal it answers, so nothing a step wrote after the deadlock may be left in it)."""

        class SavepointLost(Exception):
            pass

        whole: list[str] = []

        def rollback(*args, save_point=None, **kwargs):
            if save_point:
                raise SavepointLost("SAVEPOINT does not exist")
            # The whole transaction's rollback, recorded (this test's own transaction is kept).
            whole.append("rollback")

        saved, _ = self._ready_quotation()
        quotation_id, modified = saved["quotation"]["id"], saved["version"]["modified"]
        opportunity_id = saved["quotation"]["opportunityId"]
        own = CrmApiException("VALIDATION_ERROR", "The writer's own failure.")
        frappe.set_user(self.manager)
        for what, call in (
            ("discard", lambda: discard_draft(quotation_id, modified)),
            ("submission", lambda: submit_for_approval(quotation_id, modified)),
            ("review", lambda: review_approval(quotation_id, "Approved", "", modified)),
            ("publication", lambda: publish_version(quotation_id, modified)),
            ("link", lambda: link_quotation_opportunity(quotation_id, opportunity_id, modified)),
        ):
            with self.subTest(writer=what):
                with patch.object(quotation_service, "_lock_quotation", side_effect=own), \
                        patch.object(frappe.db, "rollback", side_effect=rollback):
                    with self.assertRaises(CrmApiException) as raised:
                        call()
                self.assertIs(raised.exception, own)
                self.assertEqual(whole, ["rollback"])
                whole.clear()
        frappe.set_user(self.sales)

    def test_only_a_catalog_key_taken_meanwhile_is_answered_with_the_item_there(self):
        """A deadlock rolls the transaction back, its locks with it: answered with an item another request committed
        since, a publication would go on writing in a new transaction, without its earlier writes (an approval's
        decision). Only a duplicate key is answered so."""

        there = "CRM-QCI-THERE-" + random_string(6)
        real_get_value = frappe.db.get_value
        for failure in (
            frappe.UniqueValidationError("CRM Quotation Catalog Item", "a duplicate catalog key"),
            frappe.QueryDeadlockError("Deadlock found when trying to get lock"),
        ):
            with self.subTest(failure=type(failure).__name__):
                looks: list[str] = []

                def get_value(doctype, filters=None, *args, **kwargs):
                    if doctype == "CRM Quotation Catalog Item" and isinstance(filters, dict) and "catalog_key" in filters:
                        # Missed first (this request's snapshot), then there (as a new transaction reads it).
                        looks.append(filters["catalog_key"])
                        return None if len(looks) == 1 else there
                    return real_get_value(doctype, filters, *args, **kwargs)

                class Insert:
                    def insert(self, **kwargs):
                        raise failure

                with patch.object(frappe.db, "get_value", side_effect=get_value):
                    with patch.object(frappe, "get_doc", return_value=Insert()):
                        if isinstance(failure, frappe.UniqueValidationError):
                            self.assertEqual(quotation_service._upsert_catalog_item("Device", "Catalog Race"), there)
                        else:
                            with self.assertRaises(frappe.QueryDeadlockError):
                                quotation_service._upsert_catalog_item("Device", "Catalog Race")

    def test_a_publication_writes_nothing_before_the_accounts_and_the_opportunitys_rows(self):
        """A publication (direct, or by an approval) renders its PDF and takes its content lock, then the Account's
        and the Opportunity's rows, and only then writes, its approval's decision included: every other writer of a
        Quotation writes under the Account's row, and one waiting for what a publication wrote while the publication
        waited for the Account's row behind an exclusive request queued there would close a cycle."""

        for path in ("publication", "approval"):
            with self.subTest(path=path):
                saved, _ = self._ready_quotation()
                quotation_id, modified = saved["quotation"]["id"], saved["version"]["modified"]
                if path == "approval":
                    modified = submit_for_approval(quotation_id, modified)["version"]["modified"]
                frappe.set_user(self.manager)
                events: list[str] = []
                with self._recorded_locks_and_writes(events):
                    if path == "approval":
                        review_approval(quotation_id, "Approved", "", modified)
                    else:
                        publish_version(quotation_id, modified)
                self.assertIn("write", events)
                self.assertLess(events.index("content lock"), events.index("account"))
                self.assertLess(events.index("account"), events.index("opportunity"))
                self.assertLess(events.index("opportunity"), events.index("write"))
                self.assertEqual(frappe.db.get_value("CRM Quotation Version", saved["version"]["id"], "status"), "Published")
                frappe.set_user(self.sales)

    def test_a_quotation_writer_takes_the_accounts_row_before_the_opportunitys_and_writes_after_both(self):
        saved, payload = self._ready_quotation()
        for write in (
            lambda current: save_draft(current["quotation"]["id"], payload, current["version"]["modified"]),
            lambda current: submit_for_approval(current["quotation"]["id"], current["version"]["modified"]),
        ):
            events: list[str] = []
            with self._recorded_locks_and_writes(events):
                saved = write(saved)
            self.assertEqual(events[:2], ["account", "opportunity"])
            self.assertIn("write", events)

    def test_a_submission_numbers_its_approval_without_a_lock(self):
        """Its read of the Quotation's approvals takes no lock: a locking read through the `quotation` index would take
        the gap the newest Quotations' approvals share, and two submissions would each wait for the other's insert. It
        is read under the Quotation's row (every submission of it holds that row), through the index the DocType
        declares."""

        self.assertTrue(frappe.get_meta("CRM Quotation Approval").get_field("quotation").search_index)
        columns: dict[str, list[str]] = {}
        for row in frappe.db.sql("SHOW INDEX FROM `tabCRM Quotation Approval`", as_dict=True):
            columns.setdefault(row.Key_name, []).append(row.Column_name)
        on_quotation = [name for name, names in columns.items() if names == ["quotation"]]
        self.assertEqual(len(on_quotation), 1, on_quotation)
        plan = frappe.db.sql(f"EXPLAIN {quotation_service.APPROVAL_ATTEMPTS_QUERY}", ("CRM-QTN-INDEX-PLAN",), as_dict=True)
        self.assertEqual(plan[0]["key"], on_quotation[0])

        saved, _ = self._ready_quotation()
        real_reader = quotation_service.committed_reader
        committed: list[str] = []

        def reader():
            # The read as committed goes through a connection of its own: its statements are watched too.
            read, close = real_reader()

            def watched(query, values):
                committed.append(" ".join(str(query).split()))
                return read(query, values)

            return watched, close

        with patch.object(frappe.db, "sql", wraps=frappe.db.sql) as queries:
            with patch.object(quotation_service, "committed_reader", side_effect=reader):
                submit_for_approval(saved["quotation"]["id"], saved["version"]["modified"])
        statements = [" ".join(str(call.args[0]).split()) for call in queries.call_args_list if call.args] + committed
        reads = [statement for statement in statements if "`tabCRM Quotation Approval`" in statement and statement.upper().startswith("SELECT")]
        self.assertTrue([statement for statement in committed if "`tabCRM Quotation Approval`" in statement])
        self.assertTrue(reads)
        self.assertFalse([statement for statement in reads if "FOR UPDATE" in statement or "LOCK IN SHARE MODE" in statement], reads)
        self.assertEqual(frappe.db.get_value("CRM Quotation Approval", {"quotation": saved["quotation"]["id"]}, "attempt_no"), 1)

    def test_a_creation_refused_under_its_accounts_lock_counts_no_reference(self):
        """An archive the first read misses is seen under the Account's lock, before the date's reference is counted
        and anything is written."""

        from rayher_crm.services.accounts import ARCHIVED_ACCOUNT_LINK, archive_account

        frappe.set_user(self.sales)
        suffix = random_string(6)
        account = create_account({
            "name": f"Quotation Archived Customer {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East China", "owner": self.sales,
        })["id"]
        frappe.set_user(self.manager)
        archive_account(account)
        frappe.set_user(self.sales)
        prefix = f"PK{frappe.utils.getdate(frappe.utils.today()).strftime('%Y%m%d')}-A"
        counter = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,))
        # The first read misses the archive, as one committed after this request's snapshot would.
        with patch.object(quotation_service, "account_archived", return_value=False), \
                self.assertRaises(CrmApiException) as refused:
            create_quotation({"accountId": account})
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_ACCOUNT_LINK))
        self.assertEqual(frappe.db.count("CRM Quotation", {"account": account}), 0)
        self.assertEqual(frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,)), counter)

    def test_a_creation_that_meets_a_deadlock_at_its_opportunitys_row_is_made_again(self):
        """The Opportunity's row is waited for holding the Account's (shared), so a creation may be one of a cycle there:
        the deadlock the database breaks is rolled back and the creation made again, as one met at its insert."""

        opportunity = self._opportunity()
        deadlock = frappe.QueryDeadlockError("Deadlock found when trying to get lock; try restarting transaction")
        real_sql, met = frappe.db.sql, []

        def sql(query, *args, **kwargs):
            text = str(query)
            if not met and "`tabCRM Opportunity`" in text and "FOR UPDATE" in text.upper():
                met.append(text)
                raise deadlock
            return real_sql(query, *args, **kwargs)

        rolled_back, rollbacks = self._request_rollbacks()
        with rolled_back, patch.object(frappe.db, "sql", side_effect=sql):
            created = create_quotation({"opportunityId": opportunity["id"]})

        self.assertEqual((len(met), len(rollbacks)), (1, 1))
        self.assertEqual(
            frappe.get_all("CRM Quotation", filters={"opportunity": opportunity["id"]}, pluck="name"),
            [created["quotation"]["id"]],
        )

    def test_a_deal_that_left_the_account_read_for_it_is_refused_as_changed(self):
        """The creation, the link and the publication lock the Account their first read gives the deal, then compare
        it with the deal's under the Opportunity's lock: a deal moved since is refused as changed."""

        frappe.set_user(self.sales)
        elsewhere = create_account({
            "name": f"Quotation Elsewhere {random_string(6)}", "shortName": random_string(6), "segment": "Frontend",
            "tier": "A", "city": "\u4e0a\u6d77", "region": "\u534e\u4e1c", "owner": self.sales,
        })["id"]
        real_require = quotation_service._require_opportunity

        def moved(name, archived_message=ARCHIVED_OPPORTUNITY_LINK):
            # The first read has the deal under an Account it has left since.
            doc = real_require(name, archived_message)
            doc.account = elsewhere
            return doc

        def changed(call):
            with self.assertRaises(CrmApiException) as refusal:
                call()
            self.assertEqual(refusal.exception.code, "VERSION_CONFLICT")

        target = self._opportunity()
        prefix = f"PK{frappe.utils.getdate(frappe.utils.today()).strftime('%Y%m%d')}-A"
        counter = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,))
        with patch.object(quotation_service, "_require_opportunity", side_effect=moved):
            changed(lambda: create_quotation({"opportunityId": target["id"]}))
        self.assertEqual(frappe.db.count("CRM Quotation", {"opportunity": target["id"]}), 0)
        self.assertEqual(frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", (prefix,)), counter)
        unlinked = create_quotation({"accountId": target["accountId"]})
        with patch.object(quotation_service, "_require_opportunity", side_effect=moved):
            changed(lambda: link_quotation_opportunity(unlinked["quotation"]["id"], target["id"], unlinked["version"]["modified"]))
        self.assertFalse(frappe.db.get_value("CRM Quotation", unlinked["quotation"]["id"], "opportunity"))

        # The publication: after its PDF is rendered, before anything is written (no PDF's File).
        saved, _ = self._ready_quotation()
        version_id = saved["version"]["id"]
        real_render = quotation_service.render_quotation_pdf
        rendered: list[str] = []

        def render(master, version):
            rendered.append(version.name)
            return real_render(master, version)

        frappe.set_user(self.manager)
        with patch.object(quotation_service, "_quotation_account", return_value=elsewhere), \
                patch.object(quotation_service, "render_quotation_pdf", side_effect=render):
            changed(lambda: publish_version(saved["quotation"]["id"], saved["version"]["modified"]))
        self.assertEqual(rendered, [version_id])
        self.assertEqual(frappe.db.count("File", {"attached_to_doctype": "CRM Quotation Version", "attached_to_name": version_id}), 0)
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", version_id, ["status", "pdf_file"]), ("Draft", None))
        frappe.set_user(self.sales)

    def test_every_writer_of_a_quotation_of_an_archived_account_is_refused_a_publication_after_rendering_its_pdf(self):
        from rayher_crm.services.accounts import ARCHIVED_ACCOUNT_EDIT

        def archive_account_of(quotation):
            # Archived as no archive does (the open deal holds the archive off), as a snapshot may say it is not.
            frappe.db.set_value("Customer", quotation["quotation"]["accountId"], "custom_crm_archived", 1)

        def refused(call):
            with self.assertRaises(CrmApiException) as refusal:
                call()
            self.assertEqual((refusal.exception.code, refusal.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_ACCOUNT_EDIT))

        # A published one: no new version, no customer decision.
        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        archive_account_of(published)
        refused(lambda: create_version(published["quotation"]["id"]))
        refused(lambda: record_decision(published["quotation"]["id"], "Accepted", "2026-10-07", "Signed", published["version"]["modified"]))

        # One awaiting a Manager: neither rejected nor approved.
        saved, _ = self._ready_quotation()
        submitted = submit_for_approval(saved["quotation"]["id"], saved["version"]["modified"])
        archive_account_of(submitted)
        frappe.set_user(self.manager)
        refused(lambda: review_approval(submitted["quotation"]["id"], "Rejected", "Too expensive", submitted["version"]["modified"]))
        refused(lambda: review_approval(submitted["quotation"]["id"], "Approved", "", submitted["version"]["modified"]))

        # A draft: not published; and a publication whose first read misses the archive is refused under the
        # Account's lock, after its PDF is rendered and before anything is written (no PDF's File).
        frappe.set_user(self.sales)
        saved, _ = self._ready_quotation()
        archive_account_of(saved)
        frappe.set_user(self.manager)
        refused(lambda: publish_version(saved["quotation"]["id"], saved["version"]["modified"]))
        version_id = saved["version"]["id"]
        real_render = quotation_service.render_quotation_pdf
        rendered: list[str] = []

        def render(master, version):
            rendered.append(version.name)
            return real_render(master, version)

        with patch.object(quotation_service, "account_archived", return_value=False), \
                patch.object(quotation_service, "render_quotation_pdf", side_effect=render):
            refused(lambda: publish_version(saved["quotation"]["id"], saved["version"]["modified"]))
        self.assertEqual(rendered, [version_id])
        self.assertEqual(frappe.db.count("File", {"attached_to_doctype": "CRM Quotation Version", "attached_to_name": version_id}), 0)
        version = frappe.db.get_value("CRM Quotation Version", version_id, ["status", "pdf_file"], as_dict=True)
        self.assertEqual((version.status, version.pdf_file), ("Draft", None))
        frappe.set_user(self.sales)

    def test_a_quotation_writer_reads_its_opportunity_under_its_lock(self):
        saved, payload = self._ready_quotation()
        opportunity_id = saved["quotation"]["opportunityId"]
        real = frappe.db.get_value
        reads: list[tuple[str, bool]] = []

        def locked_read(doctype, *args, **kwargs):
            # The Opportunity's own row read under its lock (its archive flag, and the Account it is under now).
            if doctype == "CRM Opportunity" and kwargs.get("for_update"):
                reads.append((args[0], True))
            return real(doctype, *args, **kwargs)

        with patch.object(frappe.db, "get_value", side_effect=locked_read):
            saved = save_draft(saved["quotation"]["id"], payload, saved["version"]["modified"])
            self.assertEqual(reads, [(opportunity_id, True)])
            reads.clear()
            submitted = submit_for_approval(saved["quotation"]["id"], saved["version"]["modified"])
            self.assertEqual(reads, [(opportunity_id, True)])
            reads.clear()
            frappe.set_user(self.manager)
            review_approval(saved["quotation"]["id"], "Rejected", "Too expensive", submitted["version"]["modified"])
            self.assertEqual(reads, [(opportunity_id, True)])

    def test_a_publication_reads_the_archive_under_the_opportunitys_lock_before_it_writes(self):
        real_render = quotation_service.render_quotation_pdf

        def stale(name, archived_message=ARCHIVED_OPPORTUNITY_EDIT):
            # The first read misses the archive, as one committed after this request's snapshot would.
            doc = frappe.get_doc("CRM Opportunity", name)
            doc.archived = 0
            return doc

        for path in ("publication", "approval"):
            with self.subTest(path=path):
                saved, _ = self._ready_quotation()
                quotation_id, version_id, modified = saved["quotation"]["id"], saved["version"]["id"], saved["version"]["modified"]
                if path == "approval":
                    modified = submit_for_approval(quotation_id, modified)["version"]["modified"]
                frappe.set_user(self.manager)
                archive_strategy_opportunity(saved["quotation"]["opportunityId"])
                rendered: list[str] = []

                def render(master, version):
                    rendered.append(version.name)
                    return real_render(master, version)

                # Its PDF rendered in memory (its content lock taken before the Opportunity's row), then the Opportunity
                # read under its lock: refused there, before anything is written, the approval's decision included.
                stack = ExitStack()
                stack.enter_context(patch.object(quotation_service, "_require_opportunity", side_effect=stale))
                stack.enter_context(patch.object(quotation_service, "render_quotation_pdf", side_effect=render))
                queries = stack.enter_context(patch.object(frappe.db, "sql", wraps=frappe.db.sql))
                with stack, self.assertRaises(CrmApiException) as refused:
                    if path == "approval":
                        review_approval(quotation_id, "Approved", "", modified)
                    else:
                        publish_version(quotation_id, modified)
                self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_EDIT))
                self.assertEqual(rendered, [version_id])
                writes = [
                    str(call.args[0]).split(None, 1)[0].upper() for call in queries.call_args_list
                    if call.args and str(call.args[0]).split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}
                ]
                self.assertEqual(writes, [])
                version = frappe.db.get_value("CRM Quotation Version", version_id, ["status", "approval_status", "pdf_file"], as_dict=True)
                self.assertEqual(
                    (version.status, version.approval_status, version.pdf_file),
                    ("Draft", "Pending" if path == "approval" else "Not Submitted", None),
                )
                self.assertEqual(frappe.db.count("File", {"attached_to_doctype": "CRM Quotation Version", "attached_to_name": version_id}), 0)
                if path == "approval":
                    self.assertEqual(frappe.db.get_value("CRM Quotation Approval", {"quotation": quotation_id}, "status"), "Pending")
                frappe.set_user(self.sales)

    def test_the_daily_expiry_rewrites_no_lines_of_a_version(self):
        """It records Expired in the two status columns: a save would rewrite the version's lines, whose gap locks, held
        across the job's Quotations, a writer of another Quotation of the Account waits for under the Account's row."""

        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        version_id = published["version"]["id"]
        frappe.db.set_value("CRM Quotation Version", version_id, {"valid_until": "2020-01-01"}, update_modified=False)
        with patch.object(frappe.db, "sql", wraps=frappe.db.sql) as queries:
            self.assertGreaterEqual(expire_quotations(), 1)
        statements = [" ".join(str(call.args[0]).split()) for call in queries.call_args_list if call.args]
        lines = [
            statement for statement in statements
            if ("`tabCRM Quotation Item`" in statement or "`tabCRM Quotation Payment Term`" in statement)
            and statement.split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}
        ]
        self.assertEqual(lines, [])
        self.assertEqual(frappe.db.get_value("CRM Quotation Version", version_id, "status"), "Expired")
        self.assertEqual(frappe.db.get_value("CRM Quotation", published["quotation"]["id"], "status"), "Expired")

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

class TestQuotationOpportunityConcurrency(FrappeTestCase):
    INSERT = (
        "INSERT INTO `tabCRM Quotation` (name, opportunity, ref_no, creation, modified)"
        " VALUES (%s, %s, %s, NOW(6), NOW(6))"
    )

    def test_looking_for_an_opportunitys_quotation_leaves_its_index_gap_open(self):
        """The deadlock was a gap lock: a locking read of an Opportunity's Quotation, not there yet, took the gap of
        the unique `opportunity` it would go in, which the newest Opportunities without one share; the Quotation of
        another Opportunity in that gap could not be written until the request ended, so two creations (or links) of
        different Opportunities waited on each other."""

        prefix = "zz-quotation-gap-" + random_string(8).lower()  # sorts after every Opportunity's name
        looked_for, neighbour = prefix + "-a", prefix + "-b"
        connection = None
        try:
            # Nothing of this test's transaction is held: any lock the second connection meets is the read's own.
            frappe.db.commit()
            connection = frappe.db._get_connection()
            quotation_service._assert_opportunity_has_no_quotation(looked_for)
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_lock_wait_timeout = 1")
                try:
                    # Its `opportunity` index entry lands in the gap the one looked for would go in.
                    cursor.execute(self.INSERT, ("CRM-QTN-GAP-" + random_string(8), neighbour, "zz-gap-" + random_string(8)))
                except Exception as error:
                    self.fail(f"looking for an Opportunity's Quotation locked its index gap: {error}")
        finally:
            if connection:
                connection.rollback()
                connection.close()
            frappe.db.rollback()

    def test_an_opportunitys_quotation_committed_after_this_requests_snapshot_is_seen(self):
        opportunity = "zz-quotation-committed-" + random_string(8).lower()
        quotation = "CRM-QTN-COMMITTED-" + random_string(8)
        connection = None
        try:
            frappe.db.commit()
            # This request's snapshot, taken before another request commits the Opportunity's Quotation.
            frappe.db.sql("SELECT COUNT(*) FROM `tabCRM Quotation`")
            connection = frappe.db._get_connection()
            with connection.cursor() as cursor:
                cursor.execute(self.INSERT, (quotation, opportunity, "zz-committed-" + random_string(8)))
            connection.commit()
            self.assertFalse(frappe.db.exists("CRM Quotation", quotation))
            with self.assertRaises(CrmApiException) as refused:
                quotation_service._assert_opportunity_has_no_quotation(opportunity)
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("CONFLICT", "This Opportunity already has a Quotation."))
            # A link of that very Quotation (a stale page) is told it is linked.
            with self.assertRaises(CrmApiException) as linked:
                quotation_service._assert_opportunity_has_no_quotation(opportunity, linking=quotation)
            self.assertEqual(linked.exception.public_message, "This Quotation is already linked to an Opportunity.")
        finally:
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM `tabCRM Quotation` WHERE `name` = %s", (quotation,))
                connection.commit()
                connection.close()
            frappe.db.rollback()

    def test_the_next_approval_counts_one_committed_after_this_requests_snapshot(self):
        quotation = "zz-attempts-" + random_string(8).lower()
        approval = "CRM-QTA-COMMITTED-" + random_string(8)
        connection = None
        try:
            frappe.db.commit()
            # This request's snapshot, taken before another request commits the Quotation's third approval.
            frappe.db.sql("SELECT COUNT(*) FROM `tabCRM Quotation Approval`")
            connection = frappe.db._get_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO `tabCRM Quotation Approval` (name, quotation, attempt_no, creation, modified)"
                    " VALUES (%s, %s, 3, NOW(6), NOW(6))",
                    (approval, quotation),
                )
            connection.commit()
            self.assertEqual(frappe.db.sql(quotation_service.APPROVAL_ATTEMPTS_QUERY, (quotation,))[0][0], 0)
            self.assertEqual(quotation_service._next_attempt_no(quotation), 4)
        finally:
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM `tabCRM Quotation Approval` WHERE `name` = %s", (approval,))
                connection.commit()
                connection.close()
            frappe.db.rollback()

    def test_the_daily_expiry_reads_a_quotations_current_versions_under_its_lock(self):
        """A new draft committed after the job's snapshot leaves the formal version Published and the Quotation a
        Draft: the job reads the Quotation's current versions under its row's lock, as committed by then."""

        quotation = "CRM-QTN-EXPIRY-" + random_string(8)
        formal, draft = "CRM-QTV-FORMAL-" + random_string(8), "CRM-QTV-DRAFT-" + random_string(8)
        connection = None
        try:
            frappe.db.commit()
            connection = frappe.db._get_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO `tabCRM Quotation` (name, ref_no, status, current_version, current_published_version, creation, modified)"
                    " VALUES (%s, %s, 'Published', %s, %s, NOW(6), NOW(6))",
                    (quotation, "zz-expiry-" + random_string(8), formal, formal),
                )
                cursor.execute(
                    "INSERT INTO `tabCRM Quotation Version` (name, quotation, version_no, status, valid_until, creation, modified)"
                    " VALUES (%s, %s, 1, 'Published', '2020-01-01', NOW(6), NOW(6))",
                    (formal, quotation),
                )
            connection.commit()
            # The job's snapshot, which has the formal version current ...
            frappe.db.sql("SELECT COUNT(*) FROM `tabCRM Quotation`")
            # ... and a new draft committed after it.
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO `tabCRM Quotation Version` (name, quotation, version_no, status, creation, modified)"
                    " VALUES (%s, %s, 2, 'Draft', NOW(6), NOW(6))",
                    (draft, quotation),
                )
                cursor.execute("UPDATE `tabCRM Quotation` SET `current_version` = %s, `status` = 'Draft' WHERE `name` = %s", (draft, quotation))
            connection.commit()
            self.assertEqual(frappe.db.get_value("CRM Quotation", quotation, "current_version"), formal)
            expire_quotations()
            # Read under a lock: as committed, or as this request wrote it.
            statuses = [
                frappe.db.sql(f"SELECT `status` FROM `tab{doctype}` WHERE `name` = %s FOR UPDATE", (name,))[0][0]
                for doctype, name in (("CRM Quotation", quotation), ("CRM Quotation Version", formal))
            ]
            self.assertEqual(statuses, ["Draft", "Published"])
        finally:
            # The job's row locks released before the other connection removes the rows.
            frappe.db.rollback()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM `tabCRM Quotation Version` WHERE `quotation` = %s", (quotation,))
                    cursor.execute("DELETE FROM `tabCRM Quotation` WHERE `name` = %s", (quotation,))
                connection.commit()
                connection.close()
