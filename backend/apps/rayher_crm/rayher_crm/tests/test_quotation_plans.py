import unittest

from rayher_crm.services.activities import activity_facts
from rayher_crm.services.cockpit_plan import build_plan
from rayher_crm.tests.test_cockpit_plan import fixture, WEEK, NOW


def quote_data():
    data = fixture()
    data["quotes"] = [{"name": "q", "ref_no": "PK-1", "account": "c1", "opportunity": "opp1",
                       "quotation_owner": "alice", "status": "Draft", "current_version": "v2",
                       "current_published_version": "v1", "planned_send_date": "2026-09-23"}]
    data["versions"] = [{"name": "v1", "quotation": "q", "status": "Published", "currency": "CNY", "total": "90000"},
                        {"name": "v2", "quotation": "q", "status": "Draft", "currency": "CNY", "total": "100000"}]
    data["followups"] = [{"name": "f", "parent": "q", "title": "Confirm quote", "status": "Open", "due": "2026-09-18"}]
    return data


class TestQuotationPlans(unittest.TestCase):
    def test_draft_value_and_followup_carryover_use_original_source(self):
        data = quote_data()
        plan = build_plan(data, WEEK, NOW)
        self.assertEqual(plan["summary"]["quotes"]["value"], 1)
        self.assertEqual(plan["quoteAmounts"], [{"currency": "CNY", "value": "100000.00"}])
        followup = next(r for r in plan["_details"]["overdue"] if r["kind"] == "followups")
        self.assertEqual((followup["id"], followup["quotationId"], followup["carryover"]), ("f", "q", True))
        self.assertEqual(plan["quotationCarryover"]["value"], 1)
        self.assertEqual(plan["_details"]["quotation_carryover"], [followup])
        self.assertNotIn("f", [r["id"] for r in build_plan(data, {**WEEK, "includeOverdue": False}, NOW)["_details"]["all"]])
        data["followups"][0]["due"] = "2026-09-23"
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["followups"]["value"], 1)
        data["versions"][1]["currency"] = "USD"
        plan = build_plan(data, WEEK, NOW)
        self.assertEqual(plan["quoteAmounts"], [])
        self.assertTrue(plan["quoteAmountIncomplete"])

    def test_current_published_quote_state_and_closed_opportunity_remove_pending(self):
        for status in ("Accepted", "Rejected", "Superseded"):
            data = quote_data(); data["versions"][0]["status"] = status
            self.assertFalse(any(r["kind"] == "followups" for r in build_plan(data, WEEK, NOW)["_details"]["all"]))
        data = quote_data(); data["opportunities"][0]["stage"] = "lost"
        self.assertFalse(any(r["kind"] in {"quotes", "followups"} for r in build_plan(data, WEEK, NOW)["_details"]["all"]))
        data = quote_data(); data["quotes"][0]["opportunity"] = None
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["quotes"]["value"], 1)
        self.assertEqual(build_plan(data, {**WEEK, "equipment": "Inspection"}, NOW)["summary"]["quotes"]["value"], 0)

    def test_completion_is_one_fact_and_survives_quote_close_but_not_reopening(self):
        data = quote_data()
        row = data["followups"][0]
        row.update(status="Done", completed_at="2026-09-18 10:00:00", completed_owner="alice", completed_version="v1")
        data["followups"].append(dict(row))
        data["versions"][0]["status"] = "Accepted"
        facts = [f for f in activity_facts(data, {}, NOW) if f["metric"] == "followups"]
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0]["owner"], facts[0]["quotationId"], facts[0]["quotationVersionId"]), ("alice", "q", "v1"))
        self.assertTrue(facts[0]["done"])
        data["followups"] = [{**row, "status": "Open", "completed_at": None}]
        fact = next(f for f in activity_facts(data, {}, NOW) if f["metric"] == "followups")
        self.assertFalse(fact["done"])
        self.assertIsNone(fact["occurredAt"])
        data["followups"][0]["status"] = "Cancelled"
        self.assertFalse(any(f["metric"] == "followups" for f in activity_facts(data, {}, NOW)))
