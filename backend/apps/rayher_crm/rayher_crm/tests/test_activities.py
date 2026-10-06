"""Source facts, not UI rows, determine counts and business dates."""
import unittest
from datetime import datetime

from rayher_crm.services.activities import activity_facts, audited_action_completion, last_activity_at
from rayher_crm.services.cockpit_metrics import build_review
from rayher_crm.tests.test_cockpit_metrics import COVERAGE, fixture, history, stage


NOW = datetime(2026, 10, 5, 12)


class TestActivities(unittest.TestCase):
    def test_future_created_undated_fact_does_not_hide_historical_stalls(self):
        data = fixture()
        query = {"period": "week", "anchor": "2026-09-07"}
        data["actions"] = [{"name": "future", "title": "Later action", "due": "2026-10-01", "creation": "2026-10-01", "opportunity": "opp", "status": "Done"}]
        self.assertEqual(build_review(data, query, NOW, COVERAGE)["stalled"]["count"]["value"], 1)
        data["actions"][0]["creation"] = "2026-09-01"
        self.assertIsNone(build_review(data, query, NOW, COVERAGE)["stalled"]["count"]["value"])

    def test_linked_visit_at_previous_customer_prevents_stall_without_widening_kpis(self):
        data = fixture()
        data["visits"] = [{"name": "previous-customer", "account": "old-account", "opportunity": "opp", "visit_owner": "alice",
                           "status": "Visited", "visit_date": "2026-09-10", "creation": "2026-09-10"}]
        result = build_review(data, {"period": "week", "anchor": "2026-09-07"}, NOW, COVERAGE)
        self.assertEqual(result["stalled"]["count"]["value"], 0)
        self.assertEqual(result["_details"]["visits"], [])

    def test_team_lead_count_does_not_require_historical_sales_attribution(self):
        data = fixture()
        data["leads"] = [{"name": "lead", "custom_crm_converted_at": "2026-09-08", "custom_crm_converted_account": "c", "custom_crm_converted_opportunity": "opp"}]
        for coverage in ({}, {**COVERAGE, "fields": "2026-10-01"}):
            with self.subTest(coverage=coverage):
                result = build_review(data, {"period": "week", "anchor": "2026-09-07"}, NOW, coverage)
                self.assertEqual(next(row["actual"]["value"] for row in result["activities"] if row["key"] == "leads"), 1)
                self.assertEqual(len(result["_details"]["leads"]), 1)
                self.assertIsNone(result["_details"]["leads"][0]["owner"])
                scoped = build_review(data, {"period": "week", "anchor": "2026-09-07", "sales": "alice"}, NOW, coverage)
                self.assertIsNone(next(row["actual"]["value"] for row in scoped["activities"] if row["key"] == "leads"))

    def test_precoverage_legacy_done_action_does_not_erase_known_stalled_count(self):
        data = fixture()
        query = {"period": "month", "anchor": "2026-10-01"}
        data["actions"] = [{"name": "legacy", "creation": "2024-01-01", "opportunity": "opp", "title": "Legacy action", "status": "Done", "action_owner": "alice", "due": "2024-01-01"}]
        result = build_review(data, query, NOW, COVERAGE)
        self.assertEqual(result["stalled"]["count"]["value"], 1)
        # A post-coverage completion with missing evidence still might be recent.
        data["actions"][0]["creation"] = "2026-09-01"
        result = build_review(data, query, NOW, COVERAGE)
        self.assertIsNone(result["stalled"]["count"]["value"])
        data["actions"][0]["creation"] = "2024-01-01"
        data["history"] = [history("actionUpdated", "2026-09-01", {"id": "legacy", "status": "Open"}, {"id": "legacy", "status": "Done"})]
        self.assertIsNone(build_review(data, query, NOW, COVERAGE)["stalled"]["count"]["value"])

    def test_malformed_history_coverage_stays_insufficient_instead_of_crashing(self):
        data = fixture()
        data["actions"] = [{"name": "legacy", "creation": "2024-01-01", "opportunity": "opp", "title": "Legacy action", "status": "Done", "action_owner": "alice", "due": "2024-01-01"}]
        for raw in ("2025/01/01", ["2025-01-01"]):
            with self.subTest(raw=raw):
                result = build_review(data, {"period": "month", "anchor": "2026-10-01"}, NOW, {**COVERAGE, "actions": raw})
                self.assertIsNone(result["stalled"]["count"]["value"])

    def test_backfill_accepts_the_legacy_completed_spelling_without_inventing_a_new_cycle(self):
        action = {"name": "a", "status": "Done"}
        old = {"id": "a", "status": "Completed"}
        rows = [history("actionCreated", "2024-09-01", "", old),
                history("actionUpdated", "2026-09-04", old, {"id": "a", "status": "Done", "remark": "Edited later"})]
        self.assertEqual(audited_action_completion(action, rows), datetime(2024, 9, 1))

    def test_backfill_replays_latest_done_cycle_and_rejects_a_broken_chain(self):
        action = {"name": "a", "status": "Done"}
        opened, done = {"id": "a", "status": "Open"}, {"id": "a", "status": "Done"}
        rows = [history("actionCreated", "2026-09-01", "", done),
                history("actionUpdated", "2026-09-02", done, opened),
                history("actionUpdated", "2026-09-03", opened, done),
                history("actionUpdated", "2026-09-04", done, {**done, "remark": "Note"})]
        self.assertEqual(audited_action_completion(action, rows), datetime(2026, 9, 3))
        self.assertIsNone(audited_action_completion(action, rows[:2]))
        self.assertIsNone(audited_action_completion(action, rows[3:]))
        self.assertIsNone(audited_action_completion({**action, "status": "Open"}, rows))

    def test_backfill_does_not_skip_a_broken_newer_cycle_and_reuse_an_old_completion(self):
        action = {"name": "a", "status": "Done"}
        opened, done = {"id": "a", "status": "Open"}, {"id": "a", "status": "Done"}
        first = history("actionUpdated", "2026-09-01", opened, done)
        for after in ({}, "invalid-json", {"id": "different", "status": "Done"}):
            with self.subTest(after=after):
                broken = history("actionUpdated", "2026-09-20", opened, after)
                self.assertIsNone(audited_action_completion(action, [first, broken]))
        unrelated = history("actionUpdated", "2026-09-20", {"id": "other", "status": "Open"}, {})
        self.assertEqual(audited_action_completion(action, [first, unrelated]), datetime(2026, 9, 1))

    def test_recent_completion_prevents_false_stall_and_unknown_completion_prevents_exact_count(self):
        data = fixture()
        query = {"period": "month", "anchor": "2026-10-01"}
        data["visits"] = [{"name": "v", "account": "c", "opportunity": "opp", "visit_owner": "alice", "visit_date": "2026-10-01", "status": "Visited"}]
        self.assertEqual(build_review(data, query, NOW, COVERAGE)["stalled"]["count"]["value"], 0)
        data["visits"][0]["visit_date"] = None
        result = build_review(data, query, NOW, COVERAGE)
        self.assertIsNone(result["stalled"]["count"]["value"])
        self.assertEqual(result["_details"]["stalled"], [])

    def test_visit_is_one_fact_even_when_read_through_two_relations(self):
        data = fixture()
        visit = {"name": "v", "account": "c", "opportunity": "opp", "visit_owner": "alice",
                 "subject": "Customer meeting", "visit_date": "2026-09-08", "status": "Visited",
                 "customer_kind": "Existing", "creation": "2026-09-10"}
        data["visits"] = [visit, dict(visit)]
        facts = activity_facts(data, COVERAGE, NOW)
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0]["sourceDoctype"], facts[0]["sourceId"]), ("CRM Visit", "v"))
        self.assertEqual(facts[0]["occurredAt"], "2026-09-07T16:00:00Z")
        self.assertEqual(facts[0]["recordedAt"], "2026-09-09T16:00:00Z")
        self.assertEqual(facts[0]["customerKind"], "existing")

    def test_planned_visit_and_unknown_classification_are_not_completed(self):
        data = fixture()
        data["visits"] = [{"name": "v", "account": "c", "visit_owner": "alice", "visit_date": "2026-10-06", "status": "Planned"}]
        fact = activity_facts(data, COVERAGE, NOW)[0]
        self.assertFalse(fact["done"])
        self.assertIsNone(fact["occurredAt"])
        self.assertIsNone(fact["customerKind"])
        self.assertEqual(fact["plannedAt"], "2026-10-05T16:00:00Z")

    def test_completed_test_runs_count_by_run_not_evaluation_and_keep_missing_dates(self):
        data = fixture()
        data["requests"] = [{"name": "r", "account": "c", "opportunity": "opp", "sales_owner": "alice"}]
        data["evaluations"] = [{"name": "e", "account": "c", "demo_request": "r", "status": "Customer Review"}]
        data["tests"] = [{"name": "t1", "evaluation": "e", "run_date": "2026-09-08", "status": "Completed", "test_round": 1},
                         {"name": "t2", "evaluation": "e", "run_date": None, "status": "Completed", "test_round": 2},
                         {"name": "t3", "evaluation": "e", "run_date": "2026-09-10", "status": "Draft", "test_round": 3}]
        facts = [f for f in activity_facts(data, COVERAGE, NOW) if f["done"]]
        self.assertEqual([f["sourceId"] for f in facts], ["t1", "t2"])
        self.assertIsNone(facts[1]["occurredAt"])
        self.assertEqual(facts[1]["timeBasis"], "unknown")

    def test_quote_revisions_use_first_publication_snapshot_and_one_fact(self):
        data = fixture()
        data["quotes"] = [{"name": "q", "account": "c", "quotation_owner": "bob", "opportunity": "opp", "status": "Published"}]
        data["versions"] = [{"name": "qv2", "quotation": "q", "version_no": 2, "published_at": "2026-09-15", "account": "c", "quotation_owner": "bob", "currency": "CNY", "total": "400"},
                            {"name": "qv1", "quotation": "q", "version_no": 1, "published_at": "2026-09-08", "account": "c", "quotation_owner": "alice", "currency": "CNY", "total": "250"}]
        facts = activity_facts(data, COVERAGE, NOW)
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0]["owner"], facts[0]["amountCny"], facts[0]["eventId"]), ("alice", "250.00", "qv1"))
        data["versions"][1]["currency"] = "USD"
        self.assertIsNone(activity_facts(data, COVERAGE, NOW)[0]["amountCny"])

    def test_lead_conversion_replays_sales_owner_and_preserves_unknown_owner(self):
        data = fixture()
        data["opportunities"][0]["opportunity_owner"] = "bob"
        data["history"] = [history("opportunity_owner", "2026-09-12", "alice", "bob")]
        data["leads"] = [{"name": "l", "custom_crm_status": "Converted", "custom_crm_converted_at": "2026-09-08", "custom_crm_converted_account": "c", "custom_crm_converted_opportunity": "opp"}]
        self.assertEqual(activity_facts(data, COVERAGE, NOW)[0]["owner"], "alice")
        self.assertIsNone(activity_facts(data, {}, NOW)[0]["owner"])

    def test_done_action_uses_completion_not_due_date_and_reopen_removes_completion(self):
        data = fixture()
        action = {"name": "a", "opportunity": "opp", "title": "Follow up", "action_owner": "alice", "due": "2026-09-01", "status": "Done", "completed_at": "2026-09-08 12:00:00", "archived": 0}
        data["actions"] = [action]
        fact = activity_facts(data, COVERAGE, NOW)[0]
        self.assertEqual(fact["occurredAt"], "2026-09-08T04:00:00Z")
        action.update(status="Open", completed_at=None)
        fact = activity_facts(data, COVERAGE, NOW)[0]
        self.assertFalse(fact["done"])
        self.assertIsNone(fact["occurredAt"])
        action["archived"] = 1
        self.assertEqual(activity_facts(data, COVERAGE, NOW), [])

    def test_legacy_done_action_without_completion_stays_unknown(self):
        data = fixture()
        data["actions"] = [{"name": "a", "opportunity": "opp", "status": "Done", "due": "2026-09-01", "action_owner": "alice", "creation": "2026-08-01"}]
        fact = activity_facts(data, COVERAGE, NOW)[0]
        self.assertTrue(fact["done"])
        self.assertIsNone(fact["occurredAt"])
        self.assertEqual(fact["timeBasis"], "unknown")

    def test_latest_substantive_activity_ignores_plans_remarks_and_future_events(self):
        data = fixture()
        data["visits"] = [{"name": "v", "account": "c", "opportunity": "opp", "visit_owner": "alice", "visit_date": "2026-09-08", "status": "Visited"},
                          {"name": "future", "account": "c", "opportunity": "opp", "visit_owner": "alice", "visit_date": "2026-12-08", "status": "Visited"}]
        data["actions"] = [{"name": "a", "opportunity": "opp", "action_owner": "alice", "due": "2026-09-15", "status": "Open"}]
        facts = activity_facts(data, COVERAGE, NOW)
        self.assertEqual(last_activity_at(facts, "opp", NOW), datetime(2026, 9, 8))
        self.assertIsNone(last_activity_at(facts, "opp", datetime(2026, 9, 7)))


if __name__ == "__main__":
    unittest.main()
