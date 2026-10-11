from __future__ import annotations

import os
from io import BytesIO
from unittest.mock import Mock, patch

import frappe
from frappe.permissions import add_user_permission, remove_user_permission
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string
from pypdf import PdfWriter

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import (
    archive_strategy_opportunity,
    create_strategy_opportunity,
    get_strategy_opportunity,
    mark_opportunity_lost,
    rollback_opportunity_stage,
    update_strategy_opportunity,
)
from rayher_crm.services import rfqs as rfq_service
from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_LINK
from rayher_crm.services.opportunity_stages import (
    CUSTOMER_BUDGET_APPROVED,
    DEMO_DONE,
    LOST,
    QUALIFIED_OPPORTUNITY,
    QUOTATION_SENT,
    RFQ_VALIDATED,
)
from rayher_crm.services.rfqs import (
    create_rfq,
    download_rfq_file,
    get_rfq,
    list_rfqs,
    preview_rfq_file,
    review_rfq,
    revise_rfq,
    submit_engineer_comment,
)
from rayher_crm.services.sites import create_site
from rayher_crm.services.file_security import TIPRAY_HEADER
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class CleanScanner:
    def scan(self, content: bytes) -> bool:
        return True


def pdf_part(name: str = "customer-rfq.pdf") -> dict:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return {"file_name": name, "mime_type": "application/pdf", "content": output.getvalue()}


class TestRfqApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-rfq-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-rfq-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-rfq-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._user("crm-rfq-other-engineer@example.invalid", "CRM Engineer")
        self.manager = self._user("crm-rfq-manager@example.invalid", "CRM Manager")

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
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _opportunity(self):
        suffix = random_string(6)
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"RFQ Customer {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East China", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"RFQ Site {suffix}", "city": "Shanghai", "type": "Fab",
            "process": "Frontend", "status": "\u91cf\u4ea7",
        })
        self.last_account, self.last_site = account["id"], site["id"]
        return create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account["id"], "siteId": site["id"], "title": f"RFQ Project {suffix}",
            "owner": self.sales, "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": "100000.00",
            "probability": 20, "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": "100000.00", "amountCny": "100000.00", "paymentMilestones": [], "strengths": [],
            "redFlags": [], "informationNeeded": [], "qualificationConfirmed": True,
        })

    def test_no_rfq_is_started_for_an_archived_opportunity(self):
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        frappe.set_user(self.manager)
        archive_strategy_opportunity(opportunity["id"])
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as refused:
            create_rfq({"opportunityId": opportunity["id"], "engineerId": self.engineer}, pdf_part(), CleanScanner())
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_LINK))
        self.assertFalse(frappe.db.exists("CRM RFQ", {"opportunity": opportunity["id"]}))

    def test_an_rfq_started_as_its_opportunity_is_archived_is_refused_under_its_lock_and_undone(self):
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        frappe.set_user(self.manager)
        archive_strategy_opportunity(opportunity["id"])
        frappe.set_user(self.sales)
        real_assert, real_read = rfq_service.assert_opportunity_not_archived, rfq_service.opportunity_archived
        real_discard = rfq_service.discard_rolled_back_blob
        seen: list[tuple[bool, bool]] = []
        discarded: list[tuple[str, str]] = []

        def first_read_misses(doc_or_flag, message=None):
            # The first read, of the Opportunity loaded before any lock, misses the archive, as one committed after
            # this request's snapshot would; the flag read under the lock is checked.
            if isinstance(doc_or_flag, bool):
                real_assert(doc_or_flag, message)

        def locked_read(name, *, for_update=False):
            seen.append((for_update, bool(frappe.db.exists("CRM RFQ", {"opportunity": name}))))
            return real_read(name, for_update=for_update)

        def discard(path, file_url, content_hash):
            discarded.append((path, file_url))
            return real_discard(path, file_url, content_hash)

        # Bytes of this test alone, so that no other upload shares the file the refusal takes back out.
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_metadata({"/Title": f"Archived RFQ {frappe.generate_hash(length=12)}"})
        writer.write(output)
        part = {"file_name": "archived-customer-rfq.pdf", "mime_type": "application/pdf", "content": output.getvalue()}
        with patch.object(rfq_service, "assert_opportunity_not_archived", side_effect=first_read_misses), \
                patch.object(rfq_service, "opportunity_archived", side_effect=locked_read), \
                patch.object(rfq_service, "discard_rolled_back_blob", side_effect=discard):
            with self.assertRaises(CrmApiException) as refused:
                create_rfq({"opportunityId": opportunity["id"], "engineerId": self.engineer}, part, CleanScanner())
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_LINK))
        # The RFQ's row was there (its file scanned, converted and written) when the Opportunity's was read under its
        # lock, the order the RFQ review and the stage rollback take them in; the refusal undid the rows and took the
        # file's bytes back out of the disk.
        self.assertEqual(seen, [(True, True)])
        self.assertFalse(frappe.db.exists("CRM RFQ", {"opportunity": opportunity["id"]}))
        self.assertTrue(discarded)
        for path, file_url in discarded:
            self.assertFalse(frappe.db.exists("File", {"file_url": file_url}), file_url)
            self.assertFalse(os.path.exists(path), path)

    def test_revision_with_a_stale_version_is_refused_before_its_file_is_scanned(self):
        # The version is checked before the scan and the conversion, and before the status: a page that missed
        # another user's revision is told so, as it was before the scan moved ahead of the lock.
        # Named to run after test_complete_workflow..., whose list assertions see every RFQ this class leaves in
        # the shared transaction, as the other tests that keep an RFQ are.
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        created = create_rfq({"opportunityId": opportunity["id"], "engineerId": self.engineer}, pdf_part(), CleanScanner())
        frappe.set_user(self.engineer)
        commented = submit_engineer_comment(created["id"], "Specification is feasible.", created["modified"])
        frappe.set_user(self.manager)
        returned = review_rfq(created["id"], "Returned", "Please use revision two.", commented["modified"])
        frappe.set_user(self.sales)
        revise_rfq(created["id"], pdf_part("customer-rfq-r2.pdf"), returned["modified"], CleanScanner())
        for token, code, message in (
            (returned["modified"], "VERSION_CONFLICT", "The record was changed by another request."),
            (None, "VALIDATION_ERROR", "expectedModified is required."),
        ):
            with self.subTest(token=token):
                scanner = Mock()
                scanner.scan.return_value = True
                with patch.object(rfq_service, "_office_preview", side_effect=AssertionError("must not convert")):
                    with self.assertRaises(CrmApiException) as refused:
                        revise_rfq(created["id"], pdf_part("stale.pdf"), token, scanner)
                self.assertEqual((refused.exception.code, refused.exception.public_message), (code, message))
                scanner.scan.assert_not_called()
        self.assertEqual(len(get_rfq(created["id"])["versions"]), 2)

    def test_complete_workflow_scope_revision_and_opportunity_gate(self):
        opportunity = self._opportunity()
        with self.assertRaises(CrmApiException) as too_early:
            create_rfq({"opportunityId": opportunity["id"], "engineerId": self.engineer}, pdf_part(), CleanScanner())
        self.assertEqual(too_early.exception.code, "INVALID_TRANSITION")
        opportunity = advance_opportunity_fixture(opportunity, CUSTOMER_BUDGET_APPROVED)
        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer, "note": "Customer RFQ"},
            pdf_part(), CleanScanner(),
        )
        self.assertEqual((created["status"], created["latestVersion"]), ("Engineer Review", 1))
        assigned = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "recipient_user": self.engineer,
                     "title": "RFQ requires Engineer review"},
            fields=["category", "route", "source_doctype"],
        )[0]
        self.assertEqual(
            (assigned.category, assigned.route, assigned.source_doctype),
            ("RFQ", f"/rfqs/{created['id']}", "CRM RFQ"),
        )
        with self.assertRaises(CrmApiException) as duplicate:
            create_rfq({"opportunityId": opportunity["id"], "engineerId": self.engineer}, pdf_part("duplicate.pdf"), CleanScanner())
        self.assertEqual(duplicate.exception.code, "CONFLICT")

        sales_rows, _, _, _ = list_rfqs({"page": 1, "pageSize": 20})
        self.assertEqual([row["id"] for row in sales_rows], [created["id"]])
        frappe.set_user(self.other_sales)
        self.assertEqual(list_rfqs({"page": 1, "pageSize": 20})[0], [])
        frappe.set_user(self.engineer)
        self.assertEqual([row["id"] for row in list_rfqs({"page": 1, "pageSize": 20})[0]], [created["id"]])
        self.assertEqual(preview_rfq_file(created["id"])["mime_type"], "application/pdf")
        with self.assertRaises(frappe.PermissionError):
            download_rfq_file(created["id"])
        frappe.set_user(self.other_engineer)
        self.assertEqual(list_rfqs({"page": 1, "pageSize": 20})[0], [])

        frappe.set_user(self.sales)
        specified = get_strategy_opportunity(opportunity["id"])
        with self.assertRaises(CrmApiException) as required:
            update_strategy_opportunity(opportunity["id"], {"stage": RFQ_VALIDATED}, specified["modified"])
        self.assertEqual(required.exception.code, "INVALID_TRANSITION")

        frappe.set_user(self.engineer)
        commented = submit_engineer_comment(created["id"], "Specification is feasible.", created["modified"])
        self.assertEqual(commented["status"], "Manager Approval")
        manager_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "recipient_user": self.manager,
                     "title": "RFQ requires Manager approval"},
            fields=["category", "route"],
        )[0]
        self.assertEqual((manager_notice.category, manager_notice.route), ("RFQ", f"/rfqs/{created['id']}"))
        frappe.set_user(self.manager)
        self.assertEqual(get_rfq(created["id"])["id"], created["id"])
        with self.assertRaises(CrmApiException) as reason_required:
            review_rfq(created["id"], "Returned", "", commented["modified"])
        self.assertEqual(reason_required.exception.code, "VALIDATION_ERROR")
        returned = review_rfq(created["id"], "Returned", "Please use revision two.", commented["modified"])
        returned_notices = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "title": "RFQ Returned"},
            pluck="recipient_user",
        )
        self.assertEqual(set(returned_notices), {self.sales, self.engineer})

        frappe.set_user(self.manager)
        revised = revise_rfq(created["id"], pdf_part("customer-rfq-r2.pdf"), returned["modified"], CleanScanner())
        self.assertEqual((revised["status"], len(revised["versions"])), ("Engineer Review", 2))
        self.assertEqual(revised["currentVersion"]["engineerComment"], "")
        self.assertEqual(revised["versions"][1]["engineerComment"], "Specification is feasible.")

        frappe.set_user(self.engineer)
        recommmented = submit_engineer_comment(created["id"], "Revision two confirmed.", revised["modified"])
        frappe.set_user(self.manager)
        approved = review_rfq(created["id"], "Approved", "", recommmented["modified"])
        self.assertEqual(approved["status"], "Approved")
        approved_notices = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "title": "RFQ Approved"},
            pluck="recipient_user",
        )
        self.assertEqual(set(approved_notices), {self.sales, self.engineer})
        self.assertEqual(download_rfq_file(created["id"])["file_name"], "customer-rfq-r2.pdf")
        with self.assertRaises(CrmApiException) as decided:
            review_rfq(created["id"], "Approved", "Again", approved["modified"])
        self.assertEqual(decided.exception.code, "INVALID_TRANSITION")

        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity["id"], "stage"), RFQ_VALIDATED)
        approval_moves = frappe.get_all(
            "CRM Opportunity Stage History",
            filters={"opportunity": opportunity["id"], "event": "rfq_approved"},
            fields=["from_stage", "to_stage", "reference_doctype", "reference_name"],
        )
        self.assertEqual(
            [(row.from_stage, row.to_stage, row.reference_doctype, row.reference_name) for row in approval_moves],
            [(CUSTOMER_BUDGET_APPROVED, RFQ_VALIDATED, "CRM RFQ", created["id"])],
        )
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as locked:
            revise_rfq(created["id"], pdf_part("late.pdf"), approved["modified"], CleanScanner())
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")
        latest = get_strategy_opportunity(opportunity["id"])
        with self.assertRaises(CrmApiException) as manual:
            update_strategy_opportunity(opportunity["id"], {"stage": QUOTATION_SENT}, latest["modified"])
        self.assertEqual(manual.exception.code, "INVALID_TRANSITION")

        frappe.set_user(self.manager)
        account = frappe.db.get_value("CRM RFQ", created["id"], "account")
        frappe.db.set_value("Customer", account, {
            "custom_crm_owner": self.other_sales,
            "custom_crm_visibility": "Private",
        })
        rollback_reason = "Customer changed the equipment specification."
        rolled_back = rollback_opportunity_stage(
            opportunity["id"], CUSTOMER_BUDGET_APPROVED, rollback_reason, latest["modified"],
        )
        self.assertEqual(rolled_back["stage"], CUSTOMER_BUDGET_APPROVED)
        reopened = get_rfq(created["id"])
        self.assertEqual(reopened["status"], "Sales Revision")
        self.assertEqual(reopened["currentVersion"]["status"], "Returned")
        self.assertEqual(reopened["currentVersion"]["managerComment"], rollback_reason)
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_name": created["id"],
            "recipient_user": self.sales,
            "title": "RFQ revision required after stage rollback",
        }))

        revised_after_rollback = revise_rfq(
            created["id"], pdf_part("rollback-revision.pdf"), reopened["modified"], CleanScanner(),
        )
        self.assertEqual(revised_after_rollback["status"], "Engineer Review")
        self.assertEqual(revised_after_rollback["currentVersion"]["uploadedBy"], self.manager)

    def test_revision_skips_unreachable_existing_engineer_and_notifies_reachable_one(self):
        for mode in ("reachable", "disabled", "role_removed", "source_scope_lost"):
            with self.subTest(recipient_state=mode):
                opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
                created = create_rfq(
                    {"opportunityId": opportunity["id"], "engineerId": self.engineer},
                    pdf_part(), CleanScanner(),
                )
                frappe.set_user(self.engineer)
                commented = submit_engineer_comment(created["id"], "Please review.", created["modified"])
                frappe.set_user(self.manager)
                returned = review_rfq(created["id"], "Returned", "Revision needed.", commented["modified"])
                frappe.set_user("Administrator")
                engineer = frappe.get_doc("User", self.engineer)
                original_enabled = engineer.enabled
                original_roles = [row.role for row in engineer.roles]
                unrelated = None
                try:
                    if mode == "disabled":
                        engineer.enabled = 0
                        engineer.save(ignore_permissions=True)
                    elif mode == "role_removed":
                        engineer.set("roles", [{"role": role} for role in original_roles if role != "CRM Engineer"])
                        engineer.save(ignore_permissions=True)
                    elif mode == "source_scope_lost":
                        frappe.set_user(self.other_sales)
                        unrelated = create_account({
                            "name": f"Revision notice scope {random_string(6)}", "shortName": "Notice",
                            "segment": "Frontend", "tier": "A", "city": "Shanghai",
                            "region": "East China", "owner": self.other_sales,
                        })
                        frappe.set_user("Administrator")
                        add_user_permission("Customer", unrelated["id"], self.engineer, ignore_permissions=True)
                    frappe.clear_cache(user=self.engineer)
                    frappe.set_user(self.sales)
                    revised = revise_rfq(
                        created["id"], pdf_part("revised-recipient-policy.pdf"), returned["modified"], CleanScanner(),
                    )
                    self.assertEqual((revised["status"], revised["latestVersion"], len(revised["versions"])),
                                     ("Engineer Review", 2, 2))
                    self.assertEqual(revised["currentVersion"]["uploadedBy"], self.sales)
                    notice = {"source_name": created["id"], "recipient_user": self.engineer,
                              "title": "RFQ revision requires Engineer review"}
                    self.assertEqual(bool(frappe.db.exists("CRM Notification Event", notice)), mode == "reachable")
                finally:
                    frappe.set_user("Administrator")
                    if unrelated:
                        remove_user_permission("Customer", unrelated["id"], self.engineer, ignore_permissions=True)
                    engineer = frappe.get_doc("User", self.engineer)
                    engineer.enabled = original_enabled
                    engineer.set("roles", [{"role": role} for role in original_roles])
                    engineer.save(ignore_permissions=True)
                    frappe.clear_cache(user=self.engineer)

    def test_revision_notification_persistence_failure_rolls_back_version_and_master(self):
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer},
            pdf_part(), CleanScanner(),
        )
        frappe.set_user(self.engineer)
        commented = submit_engineer_comment(created["id"], "Please review.", created["modified"])
        frappe.set_user(self.manager)
        returned = review_rfq(created["id"], "Returned", "Revision needed.", commented["modified"])
        before = get_rfq(created["id"])
        with patch("rayher_crm.services.notifications.create_notification",
                   side_effect=RuntimeError("notification persistence unavailable")):
            with self.assertRaisesRegex(RuntimeError, "notification persistence unavailable"):
                revise_rfq(created["id"], pdf_part("failed-notice-revision.pdf"), returned["modified"], CleanScanner())
        after = get_rfq(created["id"])
        self.assertEqual((after["status"], after["latestVersion"], after["modified"], len(after["versions"])),
                         (before["status"], before["latestVersion"], before["modified"], len(before["versions"])))
        self.assertEqual(after["currentVersion"]["id"], before["currentVersion"]["id"])

    def test_engineer_comment_skips_manager_restricted_by_user_permission(self):
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer},
            pdf_part(),
            CleanScanner(),
        )
        restricted = self._user("crm-rfq-restricted-manager@example.invalid", "CRM Manager")
        frappe.set_user(self.other_sales)
        unrelated = create_account({
            "name": f"Restricted RFQ Manager {random_string(6)}",
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
            frappe.set_user(self.engineer)
            commented = submit_engineer_comment(
                created["id"], "Specification is feasible.", created["modified"],
            )
            self.assertEqual(commented["status"], "Manager Approval")
            self.assertFalse(frappe.db.exists("CRM Notification Event", {
                "source_name": created["id"],
                "recipient_user": restricted,
                "title": "RFQ requires Manager approval",
            }))
            self.assertTrue(frappe.db.exists("CRM Notification Event", {
                "source_name": created["id"],
                "recipient_user": self.manager,
                "title": "RFQ requires Manager approval",
            }))
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", unrelated["id"], restricted, ignore_permissions=True)
            frappe.clear_cache(user=restricted)

    def test_manager_approval_needs_a_budget_approved_open_opportunity(self):
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer}, pdf_part(), CleanScanner(),
        )
        frappe.set_user(self.engineer)
        commented = submit_engineer_comment(created["id"], "Specification is feasible.", created["modified"])

        # Test data only: the Opportunity is back before its budget approval when the Manager decides.
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "stage", DEMO_DONE)
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as early:
            review_rfq(created["id"], "Approved", "", commented["modified"])
        self.assertEqual(early.exception.code, "CONFLICT")
        self.assertEqual(get_rfq(created["id"])["status"], "Manager Approval")
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity["id"], "stage"), DEMO_DONE)

        frappe.db.set_value("CRM Opportunity", opportunity["id"], "stage", CUSTOMER_BUDGET_APPROVED)
        frappe.set_user(self.sales)
        lost = mark_opportunity_lost(
            opportunity["id"], {"lostReason": "Customer selected another supplier."},
            get_strategy_opportunity(opportunity["id"])["modified"],
        )
        self.assertEqual((lost["stage"], lost["lostAtStage"]), (LOST, CUSTOMER_BUDGET_APPROVED))
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as lost_deal:
            review_rfq(created["id"], "Approved", "", commented["modified"])
        self.assertEqual(lost_deal.exception.code, "INVALID_TRANSITION")
        self.assertEqual(get_rfq(created["id"])["status"], "Manager Approval")
        self.assertFalse(frappe.db.exists(
            "CRM Opportunity Stage History", {"opportunity": opportunity["id"], "event": "rfq_approved"},
        ))

    def test_manager_decision_skips_revoked_sales_but_real_notice_failure_rolls_back(self):
        opportunity = advance_opportunity_fixture(self._opportunity(), CUSTOMER_BUDGET_APPROVED)
        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer}, pdf_part(), CleanScanner(),
        )
        frappe.set_user(self.engineer)
        commented = submit_engineer_comment(created["id"], "Specification is feasible.", created["modified"])
        frappe.set_user(self.manager)
        with patch("rayher_crm.services.notifications.create_notification", side_effect=RuntimeError("notice write failed")):
            with self.assertRaisesRegex(RuntimeError, "notice write failed"):
                review_rfq(created["id"], "Returned", "Revise specification", commented["modified"])
        self.assertEqual(get_rfq(created["id"])["status"], "Manager Approval")
        account = frappe.db.get_value("CRM RFQ", created["id"], "account")
        frappe.db.set_value("Customer", account, {
            "custom_crm_owner": self.other_sales, "custom_crm_visibility": "Private",
        })
        returned = review_rfq(created["id"], "Returned", "Revise specification", commented["modified"])
        self.assertEqual(returned["status"], "Sales Revision")
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM RFQ", "source_name": created["id"], "recipient_user": self.sales,
            "title": "RFQ Returned",
        }))

    def test_manager_can_upload_an_initial_rfq_for_the_opportunity_owner(self):
        opportunity = self._opportunity()
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "stage", CUSTOMER_BUDGET_APPROVED)
        frappe.set_user(self.manager)

        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer, "note": "Manager upload"},
            pdf_part("manager-upload.pdf"),
            CleanScanner(),
        )

        self.assertEqual(created["salesOwner"], self.sales)
        self.assertEqual(created["currentVersion"]["uploadedBy"], self.manager)

    def test_private_parent_blocks_assigned_sales_from_rfq_list_detail_and_files(self):
        opportunity = self._opportunity()
        frappe.db.set_value("CRM Opportunity", opportunity["id"], {
            "stage": CUSTOMER_BUDGET_APPROVED,
            "opportunity_owner": self.other_sales,
        })
        frappe.set_user(self.manager)
        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer},
            pdf_part("private-parent.pdf"),
            CleanScanner(),
        )

        frappe.set_user(self.other_sales)
        self.assertEqual(list_rfqs({"page": 1, "pageSize": 20})[0], [])
        for reader in (get_rfq, preview_rfq_file, download_rfq_file):
            with self.subTest(reader=reader.__name__), self.assertRaises(CrmApiException) as denied:
                reader(created["id"])
            self.assertEqual(denied.exception.code, "SCOPE_DENIED")

        frappe.db.set_value(
            "Customer", opportunity["accountId"], "custom_crm_visibility", "Public", update_modified=False,
        )
        rows = list_rfqs({"page": 1, "pageSize": 20})[0]
        self.assertEqual([row["id"] for row in rows], [created["id"]])
        self.assertEqual((rows[0]["opportunity"]["siteId"], rows[0]["opportunity"]["site"]), ("", ""))
        self.assertEqual(get_rfq(created["id"])["opportunity"]["siteId"], "")
        self.assertEqual(preview_rfq_file(created["id"])["mime_type"], "application/pdf")
        self.assertEqual(download_rfq_file(created["id"])["file_name"], "private-parent.pdf")

        frappe.db.set_value(
            "Customer", opportunity["accountId"], "custom_crm_visibility", "Private", update_modified=False,
        )
        self.assertEqual(list_rfqs({"page": 1, "pageSize": 20})[0], [])
        with self.assertRaises(CrmApiException) as revoked:
            get_rfq(created["id"])
        self.assertEqual(revoked.exception.code, "SCOPE_DENIED")

    def test_failed_preview_generation_rolls_back_create(self):
        opportunity = self._opportunity()
        # At the RFQ stage, so the create gets past the stage gate and fails in the preview step.
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "stage", CUSTOMER_BUDGET_APPROVED)
        before = frappe.db.count("CRM RFQ")
        with patch("rayher_crm.services.rfqs._preview", side_effect=CrmApiException("VALIDATION_ERROR", "conversion failed")):
            with self.assertRaises(CrmApiException) as failure:
                create_rfq(
                    {"opportunityId": opportunity["id"], "engineerId": self.engineer},
                    pdf_part(), CleanScanner(),
                )
        self.assertEqual(str(failure.exception), "conversion failed")
        self.assertEqual(frappe.db.count("CRM RFQ"), before)

    def test_tipray_file_can_be_created_and_downloaded_without_preview(self):
        opportunity = self._opportunity()
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "stage", CUSTOMER_BUDGET_APPROVED)
        before = frappe.db.count("CRM RFQ")
        content = TIPRAY_HEADER + bytes(range(256))

        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer},
            {
                "file_name": "protected-rfq.pdf",
                "mime_type": "application/pdf",
                "content": content,
            },
            CleanScanner(),
        )

        self.assertEqual(frappe.db.count("CRM RFQ"), before + 1)
        version = frappe.get_doc("CRM RFQ Version", created["currentVersionId"])
        stored = frappe.get_doc("File", version.original_file)
        self.assertTrue(stored.file_name.startswith("tipray-"))
        self.assertTrue(stored.file_name.endswith(".bin"))
        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as protected:
            preview_rfq_file(created["id"])
        self.assertEqual(protected.exception.code, "VALIDATION_ERROR")
        self.assertIn("cannot be previewed online", str(protected.exception))
        frappe.set_user(self.sales)
        downloaded = download_rfq_file(created["id"])
        self.assertEqual(downloaded["file_name"], "protected-rfq.pdf")
        self.assertEqual(downloaded["mime_type"], "application/pdf")
        self.assertEqual(downloaded["content"], content)
