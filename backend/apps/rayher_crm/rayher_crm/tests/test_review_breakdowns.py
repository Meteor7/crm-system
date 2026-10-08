import unittest
from datetime import datetime

from rayher_crm.services.cockpit_metrics import build_review
from rayher_crm.services.review_breakdowns import loss_breakdown, loss_category
from rayher_crm.tests.test_cockpit_metrics import COVERAGE, fixture, stage, history
from rayher_crm.services.cockpit_metrics import handling_key
from rayher_crm.services.opportunity_stages import INTERNAL_VALIDATION, OPEN_STAGES

QUERY = {"period": "week", "anchor": "2026-09-07"}
NOW = datetime(2026, 9, 16, 12)


class TestReviewBreakdowns(unittest.TestCase):
    def unknown_owner_data(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "Inspection"
        data["history"] = [history("opportunity_owner", "2026-09-15", None, "alice")]
        data["history"][0]["from_value"] = "unresolved-original-user"
        return data

    def test_unknown_historical_owner_affects_only_its_pipeline_bucket_and_rep_amount(self):
        data = self.unknown_owner_data()
        result = build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
        pipeline = {row["key"]: row for row in result["pipeline"]}
        self.assertEqual(pipeline["demo_done"]["count"]["state"], "insufficient")
        self.assertEqual(pipeline["demo_done"]["amount"]["state"], "insufficient")
        self.assertTrue(all(pipeline[key]["count"]["value"] == 0 for key in OPEN_STAGES if key != "demo_done"))
        self.assertFalse(result["_details"]["demo_done"])
        self.assertEqual(result["sales"][0]["pipeline"]["state"], "insufficient")
        team = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(next(r for r in team["pipeline"] if r["key"] == "demo_done")["amount"]["value"], "200.00")
        self.assertTrue(all(row["pipeline"]["state"] == "insufficient" for row in team["sales"]))
        for extra in ({"market": "Power"}, {"region": "South China"}, {"equipment": "Metrology"}):
            excluded = build_review(data, {**QUERY, "sales": "alice", **extra}, NOW, COVERAGE)
            self.assertTrue(all(row["count"]["value"] == 0 for row in excluded["pipeline"]))
        for closed in ("lost", "po_received"):
            data["opportunities"][0]["stage"] = closed
            closed_result = build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
            self.assertTrue(all(row["count"]["value"] == 0 for row in closed_result["pipeline"]))
            self.assertEqual(closed_result["stalled"]["count"]["value"], 0)
        data["opportunities"][0]["stage"] = OPEN_STAGES[0]
        self.assertTrue(all(row["pipeline"]["value"] == "0.00" for row in build_review(data, QUERY, NOW, COVERAGE)["sales"]))

    def test_unknown_owner_warnings_require_an_actually_eligible_candidate(self):
        data = self.unknown_owner_data()
        data["opportunities"][0]["stage"] = INTERNAL_VALIDATION
        data["stages"] = [stage("advance", "2026-07-01", after=INTERNAL_VALIDATION)]
        data["actions"] = [{"name": "action", "opportunity": "opp", "creation": "2026-07-01", "title": "Follow up",
                            "due": "2026-09-01", "status": "Open", "action_owner": "alice", "archived": 0}]
        def review():
            return build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
        result = review()
        warnings = {r["key"]: r["count"] for r in result["warnings"]}
        self.assertEqual(warnings["overdue"]["state"], "insufficient")
        self.assertEqual(warnings["stage6_no_po"]["state"], "insufficient")
        self.assertEqual(result["stalled"]["count"]["state"], "insufficient")
        self.assertTrue(all(not result["_details"][key] for key in ("overdue", "stage6_no_po", "stalled")))
        data["actions"][0]["status"] = "Done"
        data["actions"][0]["completed_at"] = "2026-09-12"
        source = data["stages"][0]["name"]
        data["warning_handlings"] = {handling_key("stage6_no_po", "opp", source): {
            "warningType": "stage6_no_po", "actedAt": "2026-09-14", "followUpOn": "2026-09-30"}}
        cleared = review()
        self.assertEqual(next(r["count"]["value"] for r in cleared["warnings"] if r["key"] == "overdue"), 0)
        self.assertEqual(next(r["count"]["value"] for r in cleared["warnings"] if r["key"] == "stage6_no_po"), 0)
        self.assertEqual(cleared["stalled"]["count"]["value"], 0)
        data["warning_handlings"] = {}
        data["stages"] = [stage("advance", "2026-09-10", after=INTERNAL_VALIDATION)]
        self.assertEqual(next(r["count"]["value"] for r in review()["warnings"] if r["key"] == "stage6_no_po"), 0)

    def test_unknown_loss_owner_preserves_known_period_category_and_review_state_exclusions(self):
        for day, status, category, annual, recent in (
            ("2026-09-08", "Pending", "", True, True),
            ("2026-09-08", "Reviewed", "Price", True, False),
            ("2026-02-01", "Pending", "", True, False),
            ("2024-02-01", "Pending", "", False, False),
        ):
            with self.subTest(day=day, status=status):
                data = self.unknown_owner_data()
                data["opportunities"][0].update(stage="lost", creation="2024-01-01")
                event = stage("marked_lost", day, after="lost")
                data["stages"] = [event]
                data["loss_reviews"] = [{"name": "review", "stage_event": event["name"], "review_status": status, "review_category": category}]
                result = build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
                self.assertEqual(result["losses"]["count"]["state"], "insufficient" if annual else "ready")
                self.assertEqual(result["losses"]["pending"]["state"], "insufficient" if annual and status == "Pending" else "ready")
                self.assertEqual(result["losses"]["reviewed"]["state"], "insufficient" if annual and status == "Reviewed" else "ready")
                cats = {r["key"]: r["count"] for r in result["losses"]["categories"]}
                self.assertEqual(cats[category or "pending"]["state"], "insufficient" if annual else "ready")
                self.assertEqual(cats["Other"]["value"], 0)
                self.assertEqual(next(r["count"]["state"] for r in result["warnings"] if r["key"] == "lost"), "insufficient" if recent else "ready")
                self.assertFalse(result["_details"]["losses"])
        data["stages"] = [stage("marked_lost", "2026-09-08", after="lost"), stage("reopened", "2026-09-09")]
        reopened = build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
        self.assertEqual(next(r["count"]["value"] for r in reopened["warnings"] if r["key"] == "lost"), 0)

    def test_missing_activity_owner_is_limited_to_its_business_period(self):
        for day, actual_ready, previous_ready in (("2020-01-01", True, True), ("2026-09-08", False, True),
                                                  ("2026-09-03", True, False), (None, False, False),
                                                  ("2026-09-06T16:00:00Z", False, True)):
            with self.subTest(day=day):
                data = fixture()
                data["quotes"] = [{"name": "q", "account": "c", "opportunity": "opp", "quotation_owner": None, "status": "Sent"}]
                data["versions"] = [{"name": "v", "quotation": "q", "account": "c", "quotation_owner": None,
                                     "published_at": day, "version_no": 1, "currency": "CNY", "total": "100"}]
                data["followups"] = [{"name": "follow", "parent": "q", "status": "Done", "completed_owner": None, "completed_at": day}]
                data["visits"] = [{"name": "visit", "account": "c", "visit_owner": None, "status": "Visited", "visit_date": day, "customer_kind": "Existing"}]
                result = build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
                for key in ("quotes", "followups", "visits"):
                    activity = next(row for row in result["activities"] if row["key"] == key)
                    self.assertEqual(activity["actual"]["state"], "ready" if actual_ready else "insufficient")
                    self.assertEqual(activity["previous"]["state"], "ready" if previous_ready else "insufficient")
                    self.assertEqual(activity["delta"], 0 if actual_ready and previous_ready else None)
                    self.assertEqual(result["sales"][0]["activities"][key]["state"], "ready" if actual_ready else "insufficient")
                    if key == "quotes":
                        self.assertEqual(activity["quoteAmount"]["actual"]["state"], activity["actual"]["state"])
                        self.assertEqual(activity["quoteAmount"]["previous"]["state"], activity["previous"]["state"])
                    if key == "visits":
                        self.assertTrue(all(row["actual"]["state"] == activity["actual"]["state"] and row["previous"]["state"] == activity["previous"]["state"] for row in activity["customerKinds"]))

    def test_activity_other_owner_equipment_and_backdated_business_dates_keep_their_scope(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "Inspection"
        visit = {"name": "v", "account": "c", "opportunity": "opp", "visit_owner": "bob", "status": "Visited",
                 "visit_date": None, "creation": "2026-09-20"}
        data["visits"] = [visit]
        def activity(extra):
            return next(r for r in build_review(data, {**QUERY, "sales": "alice", **extra}, NOW, COVERAGE)["activities"] if r["key"] == "visits")
        self.assertEqual(activity({})["actual"]["value"], 0)
        visit["visit_owner"] = None
        self.assertEqual(activity({"equipment": "Metrology"})["actual"]["value"], 0)
        # Creation is not the business visit date: late entry cannot prove the visit happened later.
        self.assertEqual(activity({})["actual"]["state"], "insufficient")
        visit.update(visit_owner="alice", visit_date="2026-09-08")
        self.assertEqual(activity({})["actual"]["value"], 1)

    def test_current_closure_clears_actions_without_erasing_unknown_historical_pipeline(self):
        data = self.unknown_owner_data()
        data["opportunities"][0]["stage"] = "lost"
        data["stages"] = [stage("marked_lost", "2026-09-15", before="demo_done", after="lost")]
        data["actions"] = [{"name": "action", "opportunity": "opp", "creation": "2026-07-01", "title": "Follow up",
                            "due": "2026-09-01", "status": "Open", "action_owner": "alice", "archived": 0}]
        result = build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
        self.assertEqual(next(r["count"]["state"] for r in result["pipeline"] if r["key"] == "demo_done"), "insufficient")
        self.assertEqual(next(r["count"]["value"] for r in result["warnings"] if r["key"] == "overdue"), 0)
        self.assertEqual(result["losses"]["count"]["value"], 0)

    def test_visit_snapshots_split_and_detail_totals_without_current_master_inference(self):
        data = fixture()
        data["customers"][0]["custom_crm_customer_kind"] = "Existing"
        data["visits"] = [{"name": name, "account": "c", "visit_owner": "alice", "opportunity": "opp", "status": "Visited",
                           "visit_date": day, "customer_kind": kind} for name, day, kind in (
                               ("a", "2026-09-08", "Existing"), ("b", "2026-09-09", "Prospect"),
                               ("c", "2026-09-10", ""), ("previous", "2026-09-03", "Existing"))]
        result = build_review(data, QUERY, NOW, COVERAGE)
        activity = next(row for row in result["activities"] if row["key"] == "visits")
        self.assertEqual(activity["actual"]["value"], 3)
        self.assertEqual([(row["key"], row["actual"]["value"], row["delta"]) for row in activity["customerKinds"]],
                         [("existing", 1, 0), ("prospect", 1, 1), ("unclassified", 1, 1)])
        self.assertEqual([row["id"] for row in result["_details"]["visits_unclassified"]], ["c"])

    def test_first_quote_amount_and_completed_followups_survive_later_quote_closure(self):
        data = fixture()
        data["quotes"] = [{"name": "q", "account": "c", "quotation_owner": "alice", "opportunity": "opp", "status": "Accepted"}]
        first = {"name": "v1", "quotation": "q", "account": "c", "quotation_owner": "alice", "published_at": "2026-09-08", "version_no": 1, "currency": "CNY", "total": "1500000.00"}
        data["versions"] = [first, {**first, "name": "v2", "published_at": "2026-09-09", "version_no": 2, "total": "9000000.00"}]
        done = {"name": "f1", "parent": "q", "title": "Call", "status": "Done", "completed_at": "2026-09-09", "completed_owner": "alice", "completed_version": "v1"}
        data["followups"] = [done, done, {**done, "name": "open", "status": "Open"}, {**done, "name": "cancelled", "status": "Cancelled"}]
        result = build_review(data, QUERY, NOW, COVERAGE)
        by_key = {row["key"]: row for row in result["activities"]}
        self.assertEqual(by_key["quotes"]["quoteAmount"]["actual"]["value"], "1500000.00")
        self.assertEqual(by_key["followups"]["actual"]["value"], 1)
        self.assertEqual(result["_details"]["quotes"][0]["quotationVersionId"], "v1")
        self.assertEqual(result["sales"][0]["activities"]["followups"]["value"], 1)
        data["versions"][0]["currency"] = "USD"
        amount = next(row for row in build_review(data, QUERY, NOW, COVERAGE)["activities"] if row["key"] == "quotes")["quoteAmount"]
        self.assertEqual((amount["actual"]["state"], amount["missing"], amount["delta"]), ("insufficient", 1, None))
        data["followups"][0]["status"] = "Open"
        self.assertEqual(next(row for row in build_review(data, QUERY, NOW, COVERAGE)["activities"] if row["key"] == "followups")["actual"]["value"], 0)

    def test_only_reviewed_categories_count_and_unknown_history_remains_unknown(self):
        rows = [{"reason": "Price", "review": {"status": "pending", "category": "Price"}},
                {"review": {"status": "reviewed", "category": "Delivery lead time"}},
                {"review": {"status": "reviewed", "category": ""}}]
        self.assertEqual([loss_category(row) for row in rows], ["pending", "Delivery lead time", "unclassified"])
        result = loss_breakdown(rows, True)
        self.assertEqual(result["completionPercent"]["value"], "66.67")
        counts = {row["key"]: row["count"]["value"] for row in result["categories"]}
        self.assertEqual((counts["Price"], counts["pending"], counts["unclassified"]), (0, 1, 1))
        self.assertEqual(loss_breakdown([], True)["completionPercent"]["state"], "not_applicable")
        self.assertEqual(loss_breakdown([], False)["completionPercent"]["state"], "insufficient")

    def test_both_quote_periods_keep_their_own_known_subtotal_and_missing_count(self):
        for current_missing, prior_missing in ((0, 2), (1, 2), (1, 0), (0, 0)):
            with self.subTest(current_missing=current_missing, prior_missing=prior_missing):
                data = fixture()
                data["quotes"], data["versions"] = [], []
                for prefix, day, known, missing in (("current", "2026-09-08", "1500000", current_missing),
                                                     ("prior", "2026-09-03", "2000000", prior_missing)):
                    for index in range(missing + 1):
                        name = f"{prefix}-{index}"
                        data["quotes"].append({"name": name, "account": "c", "quotation_owner": "alice", "opportunity": "opp", "status": "Sent"})
                        data["versions"].append({"name": f"version-{name}", "quotation": name, "account": "c", "quotation_owner": "alice",
                                                 "published_at": day, "version_no": 1, "currency": "USD" if index else "CNY", "total": known})
                amount = next(row for row in build_review(data, QUERY, NOW, COVERAGE)["activities"] if row["key"] == "quotes")["quoteAmount"]
                self.assertEqual((amount["known"], amount["missing"]), ("1500000.00", current_missing))
                self.assertEqual((amount["previousKnown"], amount["previousMissing"]), ("2000000.00", prior_missing))
                self.assertEqual(amount["actual"]["value"], None if current_missing else "1500000.00")
                self.assertEqual(amount["previous"]["value"], None if prior_missing else "2000000.00")
                self.assertEqual(amount["delta"], None if current_missing or prior_missing else "-500000.00")

    def test_configured_stall_and_escalation_use_evidenced_activity_at_exact_boundaries(self):
        data = fixture()
        data["visits"] = [{"name": "v", "account": "c", "visit_owner": "alice", "opportunity": "opp", "status": "Visited", "visit_date": "2026-09-03"}]
        def stalled(warning, escalation):
            return build_review(data, QUERY, NOW, COVERAGE, stalled_days=warning, stall_escalation_days=escalation)["stalled"]
        self.assertEqual(stalled(11, 15)["count"]["value"], 0)
        self.assertEqual(stalled(10, 15)["items"][0]["severity"], "warning")
        self.assertEqual(stalled(10, 10)["items"][0]["severity"], "high")

    def test_loss_category_cards_match_full_review_details_and_keep_sales_reason(self):
        data = fixture()
        event = stage("marked_lost", "2026-09-08", after="closed_lost", reason="Original sales note")
        data["stages"] = [event]
        data["opportunities"][0]["stage"] = "closed_lost"
        data["loss_reviews"] = [{"name": "review", "stage_event": event["name"], "review_status": "Reviewed", "review_category": "Price"}]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["losses"]["completionPercent"]["value"], "100.00")
        self.assertEqual(next(row["count"]["value"] for row in result["losses"]["categories"] if row["key"] == "Price"), 1)
        self.assertEqual(result["_details"]["loss_reason:Price"][0]["reason"], "Original sales note")
        data["loss_reviews"][0]["review_status"] = "Pending"
        pending = build_review(data, QUERY, NOW, COVERAGE)
        self.assertFalse(pending["_details"]["loss_reason:Price"])
        self.assertEqual(len(pending["_details"]["loss_reason:pending"]), 1)
