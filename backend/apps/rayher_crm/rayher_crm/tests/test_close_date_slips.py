"""Audited postponements and incomplete actions, without a live Frappe site."""
import unittest
from datetime import datetime, timedelta

from rayher_crm.services.close_date_slips import current_slip
from rayher_crm.services.cockpit_metrics import build_review, handling_key
from rayher_crm.services.cockpit_plan import build_plan
from rayher_crm.tests.test_cockpit_metrics import fixture, history, stage, COVERAGE
from rayher_crm.tests.test_cockpit_plan import fixture as plan_fixture, WEEK, NOW as PLAN_NOW

NOW = datetime(2026, 10, 5, 12)
QUERY = {"period": "week", "anchor": "2026-10-05"}


class TestCloseDateSlips(unittest.TestCase):
    def test_cross_year_same_quarter_restoration_and_new_instance(self):
        first = history("po_date", "2026-10-01", "2026-12-31", "2027-01-01")
        rows = [first]
        self.assertEqual(current_slip(rows, "2027-01-01", NOW), first)
        rows.append(history("po_date", "2026-10-02", "2027-01-01", "2027-03-31"))
        self.assertEqual(current_slip(rows, "2027-03-31", NOW), first)
        self.assertIsNone(current_slip(rows, "2027-03-30", NOW))  # Unrecorded change is not evidence.
        second = history("po_date", "2026-10-03", "2027-03-31", "2027-04-01")
        rows.append(second)
        self.assertEqual(current_slip(list(reversed(rows)), "2027-04-01", NOW), second)
        rows.append(history("po_date", "2026-10-04", "2027-04-01", "2027-02-01"))
        self.assertIsNone(current_slip(rows, "2027-02-01", NOW))
        rows.append(history("po_date", "2026-10-05", "2027-02-01", "2027-03-31"))
        self.assertIsNone(current_slip(rows, "2027-03-31", NOW))

    def test_invalid_initial_same_quarter_and_future_dates_do_not_create_slips(self):
        for before, after in (("", "2027-01-01"), ("bad", "2027-01-01"), ("2026-10-01", "2026-12-31"), ("2027-01-01", "2026-12-31")):
            with self.subTest(before=before, after=after):
                self.assertIsNone(current_slip([history("po_date", "2026-10-01", before, after)], after, NOW))
        self.assertIsNone(current_slip([history("po_date", "2026-10-06", "2026-12-31", "2027-01-01")], "2027-01-01", NOW))

    def data(self):
        data = fixture()
        data["opportunities"][0].update(po_date="2027-01-01", tool_type="Kibo")
        data["history"] = [history("po_date", "2026-10-01", "2026-12-31", "2027-01-01")]
        return data

    def test_review_cutoff_current_owner_scope_and_unknown_coverage(self):
        data = self.data()
        review = lambda query=QUERY, coverage=COVERAGE: build_review(data, query, NOW, coverage)
        row = review()["_details"]["close_date_slip"][0]
        self.assertEqual((row["previousPoDate"], row["postponedPoDate"]), ("2026-12-31", "2027-01-01"))
        for filters in ({"anchor": "2026-09-21"}, {"sales": "bob"}, {"region": "South China"}, {"equipment": "Nansi"}):
            self.assertEqual(review({**QUERY, **filters})["_details"]["close_date_slip"], [])
        self.assertEqual(next(w["count"]["state"] for w in review(coverage={})["warnings"] if w["key"] == "close_date_slip"), "insufficient")
        data["opportunities"][0]["opportunity_owner"] = "bob"
        self.assertEqual(review({**QUERY, "sales": "alice"})["_details"]["close_date_slip"], [])
        self.assertEqual(review({**QUERY, "sales": "bob"})["_details"]["close_date_slip"][0]["owner"], "bob")
        data["opportunities"][0]["stage"] = "lost"
        self.assertEqual(review()["_details"]["close_date_slip"], [])

    def test_plan_never_clears_action_pauses_until_follow_up_and_new_event_stays_open(self):
        data = self.data()
        event = data["history"][0]["name"]
        record = {"nextStep": "Call buyer"}
        data["warning_handlings"] = {handling_key("close_date_slip", "opp", event): record}
        review = lambda: build_review(data, QUERY, NOW, COVERAGE)["_details"]
        self.assertEqual(len(review()["close_date_slip"]), 1)
        record.update(actedAt="2026-10-05T00:00:00Z", actionTaken="Called buyer", followUpOn="2026-10-06")
        self.assertEqual((len(review()["close_date_slip"]), len(review()["close_date_slip_handled"])), (0, 1))
        record["followUpOn"] = "2026-10-05"
        self.assertEqual(len(review()["close_date_slip"]), 1)
        record["followUpOn"] = "2026-10-20"
        data["history"].append(history("po_date", "2026-10-05", "2027-01-01", "2027-04-01"))
        data["opportunities"][0]["po_date"] = "2027-04-01"
        self.assertEqual(review()["close_date_slip"][0]["handling"]["state"], "open")

    def test_every_incomplete_status_survives_plan_carryover_and_overdue(self):
        for status in ("Open", "In Progress", "Blocked", "Rescheduled", "Done"):
            with self.subTest(status=status):
                data = plan_fixture()
                for action in data["actions"]:
                    action["status"] = status
                plan = build_plan(data, WEEK, PLAN_NOW)
                self.assertEqual(plan["summary"]["actions"]["value"], 0 if status == "Done" else 3)
                self.assertEqual(plan["overdue"]["value"], 0 if status == "Done" else 1)
                if status != "Done":
                    self.assertEqual(plan["_details"]["actions"][0]["status"], status)
                data = fixture()
                data["actions"] = [{"name": "a", "opportunity": "opp", "creation": "2026-01-01", "title": "Call", "due": "2026-10-01", "status": status}]
                rows = build_review(data, QUERY, NOW, COVERAGE)["_details"]["overdue"]
                self.assertEqual(len(rows), 0 if status == "Done" else 1)

    def test_unconfigured_stage6_default_is_56_days(self):
        data = fixture()
        data["opportunities"][0]["stage"] = "internal_validation"
        for days in (55, 56):
            data["stages"] = [stage("approval", (NOW - timedelta(days=days)).isoformat(), "quotation_sent", "internal_validation")]
            result = build_review(data, QUERY, NOW, COVERAGE)
            self.assertEqual(result["stage6NoPo"]["thresholdDays"], 56)
            self.assertEqual(len(result["_details"]["stage6_no_po"]), int(days == 56))

