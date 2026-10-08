import unittest

from rayher_crm.services.activities import activity_facts
from rayher_crm.services.cockpit_plan import build_plan
from rayher_crm.tests.test_cockpit_plan import fixture, WEEK, NOW


def data_with_event(**changes):
    data = fixture()
    data["events"] = [{"name": "event1", "title": "Exhibition", "event_owner": "alice", "status": "Planned",
        "start_date": "2026-09-20", "end_date": "2026-09-29", "region": "East China", "market": "Frontend", "equipment": "Inspection", **changes}]
    return data


class TestEventPlans(unittest.TestCase):
    def test_multi_day_event_intersects_each_period_once_and_keeps_original_dates(self):
        data = data_with_event()
        for anchor, date in (("2026-09-14", "2026-09-20"), ("2026-09-21", "2026-09-21"), ("2026-09-28", "2026-09-28")):
            result = build_plan(data, {**WEEK, "anchor": anchor}, NOW)
            self.assertEqual(result["summary"]["events"]["value"], 1)
            row = result["_details"]["events"][0]
            self.assertEqual((row["date"], row["startDate"], row["endDate"]), (date, "2026-09-20", "2026-09-29"))
        self.assertEqual(build_plan(data, {**WEEK, "anchor": "2026-10-05"}, NOW)["summary"]["events"]["value"], 0)

    def test_standalone_and_linked_classification_do_not_fabricate_or_override_customer_scope(self):
        data = data_with_event()
        for query in ({"region": "East China"}, {"market": "Frontend"}, {"equipment": "Inspection"}, {"sales": "alice"}):
            self.assertEqual(build_plan(data, {**WEEK, **query}, NOW)["summary"]["events"]["value"], 1)
        for query in ({"region": "South China"}, {"market": "Other"}, {"equipment": "Metrology"}, {"sales": "bob"}):
            self.assertEqual(build_plan(data, {**WEEK, **query}, NOW)["summary"]["events"]["value"], 0)
        data = data_with_event(account="c2", opportunity="opp2")
        self.assertEqual(build_plan(data, {**WEEK, "region": "East China"}, NOW)["summary"]["events"]["value"], 0)
        self.assertEqual(build_plan(data, {**WEEK, "region": "South China"}, NOW)["summary"]["events"]["value"], 1)
        data = data_with_event(region="", market="", equipment="")
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["events"]["value"], 1)
        self.assertEqual(build_plan(data, {**WEEK, "equipment": "Inspection"}, NOW)["summary"]["events"]["value"], 0)

    def test_done_is_one_actual_fact_and_cancelled_has_no_plan_or_fact(self):
        data = data_with_event(status="Done", completed_at="2026-09-29 17:00:00", completed_owner="bob")
        data["events"].append(dict(data["events"][0]))
        facts = [row for row in activity_facts(data, {}, NOW) if row["metric"] == "events"]
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0]["owner"], facts[0]["occurredAt"]), ("bob", "2026-09-29T09:00:00Z"))
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["events"]["value"], 0)
        data = data_with_event(status="Cancelled")
        self.assertFalse(any(row["metric"] == "events" for row in activity_facts(data, {}, NOW)))
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["events"]["value"], 0)
