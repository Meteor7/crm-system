import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.loss_review import LOSS_REVIEW, LOSS_REVIEW_REVISION, backfill_loss_reviews, review_loss
from rayher_crm.services.opportunities import (
    archive_strategy_opportunity,
    create_strategy_opportunity,
    get_strategy_opportunity,
    mark_opportunity_lost,
    rollback_opportunity_stage,
)
from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_EDIT
from rayher_crm.services.sites import create_site


class TestLossReview(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("sales", "CRM Sales")
        self.manager = self._user("manager", "CRM Manager")
        frappe.set_user(self.sales)
        account = create_account({"name": f"Loss {frappe.generate_hash(length=8)}", "shortName": "Loss",
                                  "segment": "Frontend", "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        site = create_site(account["id"], {"name": "Loss Fab", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产"})
        self.opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": "Loss inspection", "owner": self.sales,
            "amount": "100.00", "amountCny": "100.00", "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "probabilityLevel": "committed", "qualificationConfirmed": True,
        })

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, label, role):
        email = f"crm-loss-review-{label}@example.invalid"
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": label, "enabled": 1,
                            "send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
        return email

    def _lose(self, reason="Competitor won on price"):
        return mark_opportunity_lost(self.opportunity["id"], {"lostReason": reason}, self.opportunity["modified"])

    def _review(self, review, status="Reviewed", note="Price gap confirmed; report shared", modified=None, reason=None):
        payload = {"status": status, "reviewNote": note}
        if status == "Reviewed":
            payload["reviewCategory"] = "Price"
        if reason is not None:
            payload["revertReason"] = reason
        return review_loss(self.opportunity["id"], review["id"], payload, modified or review["modified"])

    def test_new_confirmation_requires_category_without_mutating_review_or_audit(self):
        review = self._lose()["lossReviews"][0]
        frappe.set_user(self.manager)
        payload = {"status": "Reviewed", "reviewNote": "Buyer confirmed the outcome"}
        for category in (None, "", " ", "Guessed"):
            with self.subTest(category=category):
                candidate = payload if category is None else {**payload, "reviewCategory": category}
                with self.assertRaises(CrmApiException) as invalid:
                    review_loss(self.opportunity["id"], review["id"], candidate, review["modified"])
                self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
                self.assertIn("reviewCategory", invalid.exception.field_errors)
                unchanged = get_strategy_opportunity(self.opportunity["id"])["lossReviews"][0]
                self.assertEqual((unchanged["status"], unchanged["modified"]), ("pending", review["modified"]))
                self.assertEqual(len(unchanged["history"]), 1)
        saved = review_loss(self.opportunity["id"], review["id"], {**payload, "reviewCategory": "Other"}, review["modified"])
        reverted = self._review(saved, status="Pending", reason="Recheck evidence")
        # A retained formal category is still valid when a reverted review is confirmed again.
        confirmed = review_loss(self.opportunity["id"], review["id"], payload, reverted["modified"])
        self.assertEqual((confirmed["status"], confirmed["reviewCategory"]), ("reviewed", "Other"))

    def test_legacy_reviewed_blank_category_can_be_edited_but_new_confirmation_cannot_stay_blank(self):
        initial = self._lose()["lossReviews"][0]
        frappe.set_user(self.manager)
        # Imported already-reviewed data is preserved without inventing its category.
        frappe.db.set_value(LOSS_REVIEW, initial["id"], {"review_status": "Reviewed", "review_note": "Legacy conclusion",
            "review_category": "", "reviewed_by": self.manager, "reviewed_at": frappe.utils.now_datetime()})
        legacy = get_strategy_opportunity(self.opportunity["id"])["lossReviews"][0]
        payload = {"status": "Reviewed", "reviewNote": "Clarified legacy conclusion"}
        edited = review_loss(self.opportunity["id"], initial["id"], payload, legacy["modified"])
        self.assertEqual((edited["status"], edited["reviewCategory"]), ("reviewed", ""))
        reverted = self._review(edited, status="Pending", reason="Needs new confirmation")
        with self.assertRaises(CrmApiException) as invalid:
            review_loss(self.opportunity["id"], initial["id"], payload, reverted["modified"])
        self.assertIn("reviewCategory", invalid.exception.field_errors)

    def test_formal_category_is_manager_audited_and_revert_preserves_history(self):
        lost = self._lose("Sales wrote price but the review found lead time")
        initial = lost["lossReviews"][0]
        frappe.set_user(self.manager)
        payload = {"status": "Reviewed", "reviewNote": "Buyer confirmed delivery date", "reviewCategory": "Delivery lead time"}
        saved = review_loss(self.opportunity["id"], initial["id"], payload, initial["modified"])
        self.assertEqual(saved["reviewCategory"], "Delivery lead time")
        self.assertEqual(saved["lostReason"], "Sales wrote price but the review found lead time")
        self.assertEqual(saved["history"][0]["category"], "Delivery lead time")
        changed = review_loss(self.opportunity["id"], saved["id"], {**payload, "reviewCategory": "Other"}, saved["modified"])
        self.assertEqual(changed["reviewCategory"], "Other")
        with self.assertRaises(CrmApiException) as stale:
            review_loss(self.opportunity["id"], saved["id"], payload, saved["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        with self.assertRaises(CrmApiException):
            review_loss(self.opportunity["id"], saved["id"], {**payload, "reviewCategory": "Guessed"}, changed["modified"])
        cleared = review_loss(self.opportunity["id"], saved["id"], {**payload, "reviewCategory": ""}, changed["modified"])
        self.assertEqual(cleared["reviewCategory"], "")
        self.assertEqual(cleared["history"][0]["category"], "")
        changed = review_loss(self.opportunity["id"], saved["id"], {**payload, "reviewCategory": "Other"}, cleared["modified"])
        reverted = self._review(changed, status="Pending", reason="Await buyer evidence")
        self.assertEqual((reverted["status"], reverted["reviewCategory"]), ("pending", "Other"))
        self.assertEqual(reverted["history"][0]["category"], "Other")

    def test_a_post_mortem_of_an_archived_lost_deal_waits_for_the_restore(self):
        review = self._lose()["lossReviews"][0]
        frappe.set_user(self.manager)
        archive_strategy_opportunity(self.opportunity["id"])
        with self.assertRaises(CrmApiException) as refused:
            self._review(review)
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_EDIT))
        self.assertEqual(get_strategy_opportunity(self.opportunity["id"])["lossReviews"][0]["status"], "pending")

    def test_marking_lost_opens_a_pending_review_that_survives_reopening(self):
        lost = self._lose()
        self.assertEqual(len(lost["lossReviews"]), 1)
        review = lost["lossReviews"][0]
        self.assertEqual((review["status"], review["lostReason"], review["lostAtStage"], review["lostBy"]),
                         ("pending", "Competitor won on price", "qualified_opportunity", self.sales))
        self.assertEqual(review["stageEventId"], lost["stageHistory"][0]["id"])
        self.assertEqual([r["kind"] for r in review["history"]], ["Created"])

        frappe.set_user(self.manager)
        reopened = rollback_opportunity_stage(self.opportunity["id"], "qualified_opportunity", "Customer came back", lost["modified"])
        self.assertEqual(reopened["lostReason"], "")
        self.assertEqual(len(reopened["lossReviews"]), 1)
        kept = reopened["lossReviews"][0]
        self.assertEqual(kept["lostReason"], "Competitor won on price")
        self.assertIsNotNone(kept["reopenedAt"])
        self.assertEqual([r["kind"] for r in kept["history"]], ["Reopened", "Created"])

        # Losing the deal again opens a second review; the first one stays.
        frappe.set_user(self.sales)
        again = mark_opportunity_lost(self.opportunity["id"], {"lostReason": "Budget cancelled"}, reopened["modified"])
        self.assertEqual([r["lostReason"] for r in again["lossReviews"]], ["Budget cancelled", "Competitor won on price"])
        self.assertIsNone(again["lossReviews"][0]["reopenedAt"])

    def test_only_a_manager_reviews_and_every_change_is_audited(self):
        review = self._lose()["lossReviews"][0]
        with self.assertRaises(CrmApiException) as denied:
            self._review(review)
        self.assertEqual(denied.exception.code, "PERMISSION_DENIED")

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as empty:
            self._review(review, note="  ")
        self.assertEqual(empty.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as stale:
            self._review(review, modified="2020-01-01T00:00:00.000000Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        reviewed = self._review(review)
        self.assertEqual((reviewed["status"], reviewed["reviewNote"], reviewed["reviewedBy"]),
                         ("reviewed", "Price gap confirmed; report shared", self.manager))
        self.assertIsNotNone(reviewed["reviewedAt"])
        # The Sales reason is untouched by the post-mortem.
        self.assertEqual(reviewed["lostReason"], "Competitor won on price")
        self.assertEqual(get_strategy_opportunity(self.opportunity["id"])["lostReason"], "Competitor won on price")
        # Resubmitting the same conclusion is a no-op: no new revision, same version.
        same = self._review(reviewed)
        self.assertEqual(same["modified"], reviewed["modified"])
        updated = self._review(reviewed, note="Price gap confirmed; escalate to distributor")
        self.assertEqual((updated["status"], updated["reviewedBy"]), ("reviewed", self.manager))
        # A revert needs its own reason: resending the conclusion is not one, and a blank reason is rejected.
        for reason in (None, " "):
            with self.assertRaises(CrmApiException) as no_reason:
                self._review(updated, status="Pending", note=updated["reviewNote"], reason=reason)
            self.assertEqual(no_reason.exception.field_errors, {"revertReason": "Enter 1-4000 characters"})
        reverted = self._review(updated, status="Pending", note="ignored", reason="Needs a second look")
        self.assertEqual((reverted["status"], reverted["reviewedBy"], reverted["reviewedAt"]), ("pending", None, None))
        # The conclusion survives the revert; the reason lives in the audit trail.
        self.assertEqual(reverted["reviewNote"], "Price gap confirmed; escalate to distributor")
        self.assertEqual((reverted["history"][0]["kind"], reverted["history"][0]["reason"]), ("ReviewReverted", "Needs a second look"))
        with self.assertRaises(CrmApiException) as twice:
            self._review(reverted, status="Pending", reason="Another reason")
        self.assertEqual(twice.exception.code, "INVALID_TRANSITION")
        self.assertEqual([r["kind"] for r in reverted["history"]], ["ReviewReverted", "ReviewUpdated", "Reviewed", "Created"])
        self.assertEqual(frappe.db.count(LOSS_REVIEW_REVISION, {"opportunity": self.opportunity["id"]}), 4)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc(LOSS_REVIEW_REVISION, reverted["history"][0]["id"], ignore_permissions=True)

    def test_backfill_creates_one_pending_review_per_lost_event_and_is_idempotent(self):
        lost = self._lose()
        event = lost["stageHistory"][0]["id"]
        frappe.set_user("Administrator")
        frappe.db.delete(LOSS_REVIEW_REVISION, {"opportunity": self.opportunity["id"]})
        frappe.db.delete(LOSS_REVIEW, {"opportunity": self.opportunity["id"]})
        first = backfill_loss_reviews()
        self.assertEqual(first["created"], 1)
        self.assertEqual(backfill_loss_reviews()["created"], 0)
        rows = frappe.get_all(LOSS_REVIEW, filters={"opportunity": self.opportunity["id"]},
                              fields=["stage_event", "review_status", "lost_reason", "lost_at_stage", "reopened_at"])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0].stage_event, rows[0].review_status, rows[0].lost_reason, rows[0].lost_at_stage),
                         (event, "Pending", "Competitor won on price", "qualified_opportunity"))
        self.assertIsNone(rows[0].reopened_at)
