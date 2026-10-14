from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import approvals, document_access, opportunities, quotations
from rayher_crm.services.accounts import create_account
from rayher_crm.services.sites import create_site


class TestApprovals(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.tag = frappe.generate_hash(length=8)
        self.sales = self._user("sales", "CRM Sales")
        self.engineer = self._user("engineer", "CRM Engineer")
        self.other_engineer = self._user("other-engineer", "CRM Engineer")
        self.manager = self._user("manager", "CRM Manager")
        self.other_manager = self._user("other-manager", "CRM Manager")
        frappe.set_user(self.sales)
        self.account = create_account({"name": f"Approvals {self.tag}", "shortName": "Approvals",
            "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": "East", "owner": self.sales})["id"]
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, label, role):
        # Each run creates isolated actors; bypass only the fixture creation rate limit.
        with patch("frappe.core.doctype.user.user.throttle_user_creation"):
            return frappe.get_doc({"doctype": "User", "email": f"approval-{label}-{self.tag}@example.invalid",
                "first_name": label, "enabled": 1, "send_welcome_email": 0,
                "roles": [{"role": role}]}).insert(ignore_permissions=True).name

    def _insert(self, doctype, **fields):
        # Persist minimal business state, not notification-derived test doubles.
        return frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True, ignore_mandatory=True)

    def _demo(self, status="Engineer Review", engineer=None):
        doc = self._insert("CRM Demo Request", account=self.account, request_mode="Self Test",
            sales_owner=self.sales, created_by_user=self.sales, engineer_owner=engineer or self.engineer,
            title=f"Approval demo {self.tag}", status=status, requested_equipment="Inspection",
            objective="Inspect", sample_type="Si", sample_quantity=1, target_date="2026-12-01",
            customer_expected_date="2026-12-01", priority="High", acceptance_criteria="Wafer map")
        self._history(doc, status)
        return doc

    def _history(self, doc, status):
        return self._insert("CRM Demo Request History", demo_request=doc.name,
            actor=self.sales, at=frappe.utils.now_datetime(), to_status=status, comment="Submitted")

    def _opportunity(self):
        return self._insert("CRM Opportunity", account=self.account, title=f"Approval deal {self.tag}",
            opportunity_owner=self.sales, stage="quotation_sent", archived=0, tool_type="Inspection")

    def _items(self, user, record):
        frappe.set_user(user)
        return [item for item in approvals.list_pending_approvals() if item["sourceRecordId"] == record]

    def test_demo_assignment_and_manager_override_are_not_role_wide(self):
        doc = self._demo()
        self.assertEqual(self._items(self.sales, doc.name), [])
        self.assertEqual(self._items(self.other_engineer, doc.name), [])
        item = self._items(self.engineer, doc.name)[0]
        self.assertEqual((item["kind"], item["recipientId"]), ("demo-engineering", self.engineer))
        self.assertEqual(item["target"]["query"], {"focus": doc.name, "mode": "engineer"})
        self.assertEqual(self._items(self.manager, doc.name)[0]["kind"], "demo-engineering")

    def test_reads_are_side_effect_free_and_no_notice_is_needed(self):
        doc = self._demo("Manager Approval")
        self.assertFalse(frappe.db.exists("CRM Notification Event", {"source_name": doc.name}))
        count = frappe.db.count(approvals.VIEW_DOCTYPE)
        with patch("rayher_crm.services.notifications.list_notifications", side_effect=AssertionError("not a pending source")):
            first = self._items(self.manager, doc.name)[0]
            second = self._items(self.manager, doc.name)[0]
        self.assertEqual(first, second)
        self.assertTrue(first["unread"])
        self.assertEqual(frappe.db.count(approvals.VIEW_DOCTYPE), count)

    def test_view_is_idempotent_per_user_and_reverts_to_unread_on_resubmission(self):
        doc = self._demo("Manager Approval")
        item = self._items(self.manager, doc.name)[0]
        first = approvals.mark_approval_viewed(item["id"])
        self.assertEqual(approvals.mark_approval_viewed(item["id"]), first)
        self.assertFalse(self._items(self.manager, doc.name)[0]["unread"])
        self.assertTrue(self._items(self.other_manager, doc.name)[0]["unread"])
        frappe.db.set_value(doc.doctype, doc.name, "title", "Ordinary edit")
        self.assertEqual(self._items(self.manager, doc.name)[0]["id"], item["id"])
        self.assertFalse(self._items(self.manager, doc.name)[0]["unread"])
        frappe.set_user("Administrator")
        self._history(doc, "Manager Approval")
        repeated = self._items(self.manager, doc.name)[0]
        self.assertNotEqual(repeated["id"], item["id"])
        self.assertTrue(repeated["unread"])
        with self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(item["id"])

    def test_processed_or_reassigned_tasks_cannot_be_marked_viewed(self):
        doc = self._demo()
        item = self._items(self.engineer, doc.name)[0]
        frappe.db.set_value(doc.doctype, doc.name, "engineer_owner", self.other_engineer)
        self.assertEqual(self._items(self.engineer, doc.name), [])
        with self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(item["id"])
        assigned = self._items(self.other_engineer, doc.name)[0]
        frappe.db.set_value(doc.doctype, doc.name, "status", "Converted")
        self.assertEqual(self._items(self.other_engineer, doc.name), [])
        with self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(assigned["id"])

    def test_post_rechecks_after_the_authoritative_lock(self):
        doc = self._demo("Manager Approval")
        item = self._items(self.manager, doc.name)[0]
        original = frappe.db.sql

        def decided_while_waiting(query, *args, **kwargs):
            if "FOR UPDATE" in query and "`tabCRM Demo Request`" in query and query.startswith("SELECT `name`"):
                frappe.db.set_value(doc.doctype, doc.name, "status", "Converted")
            return original(query, *args, **kwargs)

        with patch.object(frappe.db, "sql", side_effect=decided_while_waiting), self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(item["id"])
        self.assertFalse(frappe.db.exists(approvals.VIEW_DOCTYPE, {"viewer": self.manager, "task_key": item["id"]}))

    def test_disabled_or_changed_role_cannot_use_old_task(self):
        doc = self._demo("Manager Approval")
        item = self._items(self.manager, doc.name)[0]
        frappe.set_user("Administrator")
        user = frappe.get_doc("User", self.manager)
        user.set("roles", [{"role": "CRM Sales"}])
        user.save(ignore_permissions=True)
        frappe.clear_cache(user=self.manager)
        self.assertEqual(self._items(self.manager, doc.name), [])
        with self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(item["id"])
        frappe.set_user("Administrator")
        frappe.db.set_value("User", self.other_manager, "enabled", 0)
        frappe.clear_cache(user=self.other_manager)
        frappe.set_user(self.other_manager)
        with self.assertRaises(frappe.PermissionError):
            approvals.list_pending_approvals()

    def test_internal_validation_forbids_self_review_and_stale_stages(self):
        opportunity = self._opportunity()
        validation = self._insert("CRM Opportunity Internal Validation", opportunity=opportunity.name,
            attempt_no=1, status="pending", reason="Production requested", expected_po_date="2026-12-01",
            requested_by=self.manager, requested_at=frappe.utils.now_datetime(), booking_draft="{}")
        self.assertEqual(self._items(self.manager, opportunity.name), [])
        item = self._items(self.other_manager, opportunity.name)[0]
        self.assertEqual(item["kind"], "production")
        self.assertTrue(item["forbidSelfApproval"])
        frappe.db.set_value(opportunity.doctype, opportunity.name, "stage", "po_received")
        self.assertEqual(self._items(self.other_manager, opportunity.name), [])
        with self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(item["id"])

    def test_internal_validation_matches_business_scope_with_native_restrictions(self):
        frappe.set_user(self.sales)
        site = create_site(self.account, {"name": f"Validation {self.tag}", "city": "Shanghai",
            "type": "Fab", "process": "Frontend", "status": "量产"})
        for doctype, reviewer in (("CRM Opportunity Internal Validation", self.manager), ("CRM Opportunity", self.other_manager)):
            with self.subTest(doctype=doctype):
                frappe.set_user("Administrator")
                opportunity = self._opportunity()
                frappe.db.set_value(opportunity.doctype, opportunity.name, {"site": site["id"],
                    "po_date": "2026-12-31", "sub_region": "East", "sale_type": "New Equipment",
                    "probability_level": "pipeline", "currency": "CNY"})
                validation = self._insert("CRM Opportunity Internal Validation", opportunity=opportunity.name,
                    attempt_no=1, status="pending", reason="Production requested", expected_po_date="2026-12-01",
                    requested_by=self.sales, requested_at=frappe.utils.now_datetime(), booking_draft="{}")
                permission = self._insert("User Permission", user=reviewer, allow="User",
                    for_value=self.other_engineer, apply_to_all_doctypes=0, applicable_for=doctype)
                frappe.clear_cache(user=reviewer)
                frappe.set_user(reviewer)
                record = validation.name if doctype == validation.doctype else opportunity.name
                self.assertFalse(frappe.get_list(doctype, filters={"name": record}, pluck="name"))
                current = opportunities.get_strategy_opportunity(opportunity.name)
                self.assertEqual(current["internalValidation"]["id"], validation.name)
                listed, _, _, _ = opportunities.list_strategy_opportunities({"opportunityId": opportunity.name})
                self.assertEqual([row["id"] for row in listed], [opportunity.name])
                item = self._items(reviewer, opportunity.name)[0]
                self.assertEqual(item["kind"], "production")
                approvals.mark_approval_viewed(item["id"])
                self.assertEqual(self._items(self.sales, opportunity.name), [])
                self.assertEqual(self._items(self.engineer, opportunity.name), [])
                frappe.set_user(reviewer)
                decided = opportunities.review_internal_validation(opportunity.name,
                    {"validationId": validation.name, "decision": "rejected", "comment": "Wait for the PO"},
                    current["modified"])
                self.assertEqual(decided["internalValidation"]["status"], "rejected")
                self.assertEqual(self._items(reviewer, opportunity.name), [])
                frappe.set_user("Administrator")
                frappe.delete_doc("User Permission", permission.name, ignore_permissions=True)
                frappe.clear_cache(user=reviewer)

    def test_rfq_manager_capability_does_not_allow_engineering_action(self):
        opportunity = self._opportunity()
        rfq = self._insert("CRM RFQ", opportunity=opportunity.name, account=self.account,
            sales_owner=self.sales, engineer_owner=self.engineer, status="Engineer Review")
        version = self._insert("CRM RFQ Version", rfq=rfq.name, version_no=1, status="Engineer Review",
            file_name="source.pdf", uploaded_by=self.sales, uploaded_at=frappe.utils.now_datetime())
        frappe.db.set_value(rfq.doctype, rfq.name, "current_version", version.name)
        self.assertEqual(self._items(self.manager, rfq.name), [])
        self.assertEqual(self._items(self.other_engineer, rfq.name), [])
        self.assertEqual(self._items(self.engineer, rfq.name)[0]["kind"], "rfq-engineering")
        frappe.db.set_value(rfq.doctype, rfq.name, "status", "Manager Approval")
        frappe.db.set_value(version.doctype, version.name, {"engineer_commented_by": self.engineer,
            "engineer_commented_at": frappe.utils.now_datetime()})
        self.assertEqual(self._items(self.engineer, rfq.name), [])
        self.assertEqual(self._items(self.manager, rfq.name)[0]["kind"], "rfq")

    def test_evaluation_scope_and_retest_round_identity(self):
        request = self._demo("Converted")
        evaluation = self._insert("CRM Evaluation", demo_request=request.name, account=self.account,
            title="Review test", evaluation_owner=self.engineer, status="Internal Review", report_status="Ready")
        self.assertEqual(self._items(self.sales, evaluation.name), [])
        self.assertEqual(self._items(self.other_engineer, evaluation.name), [])
        self.assertEqual(self._items(self.engineer, evaluation.name)[0]["kind"], "test-review")
        frappe.db.set_value(evaluation.doctype, evaluation.name, "status", "Customer Review")
        item = self._items(self.sales, evaluation.name)[0]
        self.assertEqual(item["kind"], "customer-review")
        approvals.mark_approval_viewed(item["id"])
        self.assertFalse(self._items(self.sales, evaluation.name)[0]["unread"])
        # An already-opened second round as written by the customer retest service.
        frappe.db.set_value(evaluation.doctype, evaluation.name, "test_round", 2)
        second = self._items(self.sales, evaluation.name)[0]
        self.assertNotEqual(second["id"], item["id"])
        self.assertTrue(second["unread"])

    def test_document_upload_pending_is_manager_only_and_view_storage_is_service_only(self):
        upload = self._insert("CRM Document Upload Request", title="Release manual", status="Pending",
            submitted_by=self.sales, file_name="manual.pdf", mime_type="application/pdf")
        self.assertEqual(self._items(self.sales, upload.name), [])
        self.assertEqual(self._items(self.engineer, upload.name), [])
        item = self._items(self.manager, upload.name)[0]
        self.assertEqual(item["kind"], "document-upload")
        approvals.mark_approval_viewed(item["id"])
        receipt = approvals._view_id(self.manager, item["id"])
        for user in (self.manager, self.other_manager, self.sales, self.engineer):
            self.assertFalse(frappe.has_permission(approvals.VIEW_DOCTYPE, "read", user=user))
            self.assertFalse(frappe.has_permission(approvals.VIEW_DOCTYPE, "create", user=user))
        self.assertTrue(frappe.db.exists(approvals.VIEW_DOCTYPE, receipt))

    def test_pending_source_query_has_no_thousand_row_cutoff(self):
        opportunity = self._opportunity()
        rfq = self._insert("CRM RFQ", opportunity=opportunity.name, account=self.account,
            sales_owner=self.sales, engineer_owner=self.engineer, status="Engineer Review")
        frappe.set_user(self.engineer)
        original = frappe.db.sql
        captured = []

        def observe(query, *args, **kwargs):
            if query.startswith("SELECT * FROM `tabCRM RFQ`"):
                captured.append(query)
            return original(query, *args, **kwargs)

        with patch.object(frappe.db, "sql", side_effect=observe):
            rows = approvals._pending_docs("CRM RFQ", "`status` = %s", ("Engineer Review",), self.engineer)
        self.assertIn(rfq.name, {row.name for row in rows})
        self.assertTrue(captured)
        self.assertNotIn("LIMIT", captured[0])

    def test_visit_uses_latest_complete_record_time_and_keeps_same_view_on_edits(self):
        visit = self._insert("CRM Visit", account=self.account, visit_owner=self.sales,
            subject="Review minutes", status="Minutes Submitted", visit_date="2026-10-14", visit_type="On-site")
        record = self._insert("CRM Visit Meeting Record", visit=visit.name,
            purpose="Purpose", attendees="Attendees", agenda="Agenda", summary="Summary",
            conclusion="Conclusion", followup="Followup", parse_status="Parsed")
        frappe.db.set_value(record.doctype, record.name,
            {"creation": "2026-10-01 08:00:00", "modified": "2026-10-14 09:30:00"}, update_modified=False)
        item = self._items(self.manager, visit.name)[0]
        self.assertEqual(item["submittedAt"], "2026-10-14T01:30:00Z")
        self.assertEqual(item["submittedAtLabel"], "资料完成时间")
        approvals.mark_approval_viewed(item["id"])
        frappe.db.set_value(record.doctype, record.name, "summary", "Updated complete minutes")
        updated = self._items(self.manager, visit.name)[0]
        self.assertEqual(updated["id"], item["id"])
        self.assertFalse(updated["unread"])
        frappe.db.set_value(record.doctype, record.name, "purpose", "")
        self.assertEqual(self._items(self.manager, visit.name), [])

    def test_quotation_targets_current_pending_version_by_master_id_not_display_number(self):
        opportunity = self._opportunity()
        master = self._insert("CRM Quotation", ref_no=f"Q-{self.tag}-002", account=self.account,
            opportunity=opportunity.name, quotation_owner=self.sales, status="Draft", latest_version_no=2)
        previous = self._insert("CRM Quotation Version", quotation=master.name, version_no=1,
            status="Published", approval_status="Approved", ref_no=master.ref_no,
            account=self.account, quotation_owner=self.sales)
        current = self._insert("CRM Quotation Version", quotation=master.name, version_no=2,
            status="Draft", approval_status="Pending", ref_no=master.ref_no,
            account=self.account, quotation_owner=self.sales)
        old_approval = self._insert("CRM Quotation Approval", quotation=master.name,
            quotation_version=previous.name, attempt_no=1, status="Pending",
            submitted_by=self.sales, submitted_at=frappe.utils.now_datetime())
        approval = self._insert("CRM Quotation Approval", quotation=master.name,
            quotation_version=current.name, attempt_no=2, status="Pending",
            submitted_by=self.sales, submitted_at=frappe.utils.now_datetime())
        frappe.db.set_value(current.doctype, current.name, "current_approval", approval.name)
        frappe.db.set_value(master.doctype, master.name, "current_version", current.name)
        self.assertNotEqual(master.name, master.ref_no)
        self.assertEqual(self._items(self.sales, master.name), [])
        self.assertEqual(self._items(self.engineer, master.name), [])
        rows = self._items(self.manager, master.name)
        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.assertEqual((item["kind"], item["sourceId"], item["sourceRecordId"]),
            ("quotation", master.ref_no, master.name))
        self.assertEqual(item["target"], {"path": "/quotations/" + master.name,
            "query": {"version": current.name, "approval": "1"}})

        # Frozen parents and a completed quotation never remain actionable.
        frappe.db.set_value("Customer", self.account, "custom_crm_archived", 1)
        self.assertEqual(self._items(self.manager, master.name), [])
        with self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(item["id"])
        frappe.db.set_value("Customer", self.account, "custom_crm_archived", 0)
        frappe.db.set_value(opportunity.doctype, opportunity.name, "archived", 1)
        self.assertEqual(self._items(self.manager, master.name), [])
        frappe.db.set_value(opportunity.doctype, opportunity.name, "archived", 0)
        frappe.db.set_value(master.doctype, master.name, "status", "Accepted")
        self.assertEqual(self._items(self.manager, master.name), [])
        frappe.db.set_value(master.doctype, master.name, "status", "Draft")

        # Historical pending approvals cannot stand in for the current version.
        frappe.db.set_value(current.doctype, current.name, "current_approval", old_approval.name)
        self.assertEqual(self._items(self.manager, master.name), [])
        frappe.db.set_value(current.doctype, current.name, "current_approval", approval.name)
        frappe.db.set_value(master.doctype, master.name, "current_version", None)
        self.assertEqual(self._items(self.manager, master.name), [])

    def test_quotation_archive_gate_follows_the_opportunity_current_account(self):
        opportunity = self._opportunity()
        master = self._insert("CRM Quotation", ref_no=f"Q-{self.tag}-MOVED", account=self.account,
            opportunity=opportunity.name, quotation_owner=self.sales, status="Draft", latest_version_no=1)
        version = self._insert("CRM Quotation Version", quotation=master.name, version_no=1,
            status="Draft", approval_status="Pending", ref_no=master.ref_no,
            account=self.account, quotation_owner=self.sales)
        approval = self._insert("CRM Quotation Approval", quotation=master.name,
            quotation_version=version.name, attempt_no=1, status="Pending",
            submitted_by=self.sales, submitted_at=frappe.utils.now_datetime())
        frappe.db.set_value(version.doctype, version.name, "current_approval", approval.name)
        frappe.db.set_value(master.doctype, master.name, "current_version", version.name)
        frappe.set_user(self.sales)
        current_account = create_account({"name": f"Moved approvals {self.tag}", "shortName": "Moved",
            "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": "East", "owner": self.sales})["id"]
        frappe.set_user("Administrator")
        frappe.db.set_value(opportunity.doctype, opportunity.name, "account", current_account)

        # A quotation retains its addressed customer, but follows its deal's archive gate.
        frappe.db.set_value("Customer", self.account, "custom_crm_archived", 1)
        item = self._items(self.manager, master.name)[0]
        quotations._assert_quotation_writable(master)
        approvals.mark_approval_viewed(item["id"])

        frappe.db.set_value("Customer", self.account, "custom_crm_archived", 0)
        frappe.db.set_value("Customer", current_account, "custom_crm_archived", 1)
        self.assertEqual(self._items(self.manager, master.name), [])
        with self.assertRaises(CrmApiException):
            quotations._assert_quotation_writable(master)
        with self.assertRaises(CrmApiException):
            approvals.mark_approval_viewed(item["id"])

    def test_document_access_matches_manager_service_with_native_user_restrictions(self):
        controlled = self._insert("CRM Controlled Document", document_id=f"APPROVAL-SCOPE-{self.tag}",
            title="Restricted process manual", category="Technical", version="1", revision="R1",
            status="Released", confidentiality="Restricted", access_mode="Request")
        request = self._insert("CRM Document Access Request", controlled_document=controlled.name,
            version_id=f"{controlled.name}/1/R1", document_version="1", document_revision="R1",
            requester=self.sales, reason="Prepare customer review", status="Pending")
        self._insert("User Permission", user=self.manager, allow="User", for_value=self.other_engineer,
            apply_to_all_doctypes=0, applicable_for="CRM Document Access Request")
        frappe.clear_cache(user=self.manager)
        frappe.set_user(self.manager)
        self.assertFalse(frappe.get_list("CRM Document Access Request", filters={"name": request.name}, pluck="name"))
        self.assertIn(request.name, {row["id"] for row in document_access.list_requests()})
        item = self._items(self.manager, request.name)[0]
        approvals.mark_approval_viewed(item["id"])
        self.assertEqual(self._items(self.sales, request.name), [])
        self.assertEqual(self._items(self.engineer, request.name), [])
        frappe.set_user(self.manager)
        self.assertEqual(document_access.decide_request(request.name, "approve-original")["status"], "Approved")
        self.assertEqual(self._items(self.manager, request.name), [])

    def test_document_access_queue_is_current_pending_manager_only_and_targets_exact_request(self):
        controlled = self._insert("CRM Controlled Document", document_id=f"APPROVAL-DOC-{self.tag}",
            title="Restricted process manual", category="Technical", version="1", revision="R1",
            status="Released", confidentiality="Restricted", access_mode="Request")
        request = self._insert("CRM Document Access Request", controlled_document=controlled.name,
            version_id=f"{controlled.name}/1/R1", document_version="1", document_revision="R1",
            requester=self.sales, reason="Prepare customer review", status="Pending")
        self.assertEqual(self._items(self.sales, request.name), [])
        self.assertEqual(self._items(self.engineer, request.name), [])
        item = self._items(self.manager, request.name)[0]
        self.assertEqual((item["kind"], item["title"], item["requesterId"]),
            ("document", controlled.title, self.sales))
        self.assertEqual(item["sourceRecordId"], request.name)
        self.assertEqual(item["target"], {"path": "/document-center",
            "query": {"workspace": "approvals", "request": request.name}})
        for status in ("Approved", "Rejected", "More Info Required"):
            frappe.db.set_value(request.doctype, request.name, "status", status)
            self.assertEqual(self._items(self.manager, request.name), [])
            with self.assertRaises(CrmApiException):
                approvals.mark_approval_viewed(item["id"])
