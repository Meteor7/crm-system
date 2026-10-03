"""Run with plain unittest; the Plan counting rules must not depend on a live site."""
import unittest
from datetime import datetime

from rayher_crm.services.cockpit_plan import build_plan, plan_period

NOW = datetime(2026, 9, 18, 11)
WEEK = {"period": "week", "anchor": "2026-09-23"}


def fixture():
    return {
        "customers": [
            {"name": "c1", "customer_name": "Customer One", "custom_crm_region": "East China", "custom_crm_segment": "Frontend"},
            {"name": "c2", "customer_name": "Customer Two", "custom_crm_region": "South China", "custom_crm_segment": ""},
        ],
        "people": [{"name": "alice", "full_name": "Alice"}, {"name": "bob", "full_name": "Bob"}],
        "action_people": [{"name": "engineer", "full_name": "Engineer Chen"}, {"name": "alice", "full_name": "Alice"}],
        "cny_amount_ready": True,
        "opportunities": [
            {"name": "opp1", "title": "Inspection", "account": "c1", "opportunity_owner": "alice", "stage": "rfq_validated",
             "po_date": "2026-09-25", "probability_level": "upside", "amount_cny": "6800000"},
            {"name": "opp2", "title": "Metrology", "account": "c2", "opportunity_owner": "bob", "stage": "quotation_sent",
             "po_date": "2026-09-27", "probability_level": "", "amount_cny": None},
        ],
        "visits": [
            {"name": "v1", "account": "c1", "visit_owner": "alice", "subject": "On-site", "visit_date": "2026-09-21", "status": "Planned"},
            {"name": "v2", "account": "c2", "visit_owner": "bob", "subject": "Sunday call", "visit_date": "2026-09-27", "status": "Planned"},
            {"name": "v3", "account": "c1", "visit_owner": "alice", "subject": "Done", "visit_date": "2026-09-22", "status": "Visited"},
            {"name": "v4", "account": "c1", "visit_owner": "alice", "subject": "Next week", "visit_date": "2026-09-28", "status": "Planned"},
        ],
        "requests": [{"name": "req1", "account": "c1", "sales_owner": "alice", "opportunity": "opp1", "status": "Converted"}],
        "evaluations": [{"name": "ev1", "account": "c1", "demo_request": "req1", "title": "Wafer test", "status": "Testing", "test_round": 2, "test_run_deadline": "2026-09-23",
                         "wafer_preparation_status": "Completed", "test_preparation_status": "Completed"}],
        "tests": [
            {"name": "run-old", "evaluation": "ev1", "run_date": "2026-09-22", "test_round": 1, "status": "Planned"},
            {"name": "run-now", "evaluation": "ev1", "run_date": "2026-09-23", "test_round": 2, "status": "Planned"},
            {"name": "run-done", "evaluation": "ev1", "run_date": "2026-09-23", "test_round": 2, "status": "Completed"},
            {"name": "run-off", "evaluation": "ev1", "run_date": "2026-09-24", "test_round": 2, "status": "Cancelled"},
        ],
        "actions": [
            {"name": "a1", "opportunity": "opp1", "title": "Budget", "action_owner": "engineer", "due": "2026-09-24", "status": "Open", "archived": 0},
            {"name": "a2", "opportunity": "opp1", "title": "Delivery", "action_owner": "alice", "due": "2026-09-24", "status": "Open", "archived": 0},
            {"name": "a-old", "opportunity": "opp1", "title": "Terms", "action_owner": "alice", "due": "2026-09-18", "status": "Open", "archived": 0},
            {"name": "a-done", "opportunity": "opp1", "title": "Done", "action_owner": "alice", "due": "2026-09-24", "status": "Done", "archived": 0},
            {"name": "a-gone", "opportunity": "opp1", "title": "Archived", "action_owner": "alice", "due": "2026-09-24", "status": "Open", "archived": 1},
        ],
    }


def ids(rows):
    return [r["id"] for r in rows]


class TestPlanPeriod(unittest.TestCase):

    def test_equipment_filter_keeps_only_linked_records_of_that_equipment(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "Inspection"
        data["opportunities"][1]["tool_type"] = "Metrology"
        data["visits"][0]["opportunity"] = "opp1"
        insp = build_plan(data, {**WEEK, "equipment": "Inspection"}, NOW)
        details = insp["_details"]["all"] if "all" in insp["_details"] else [r for rows in insp["_details"].values() for r in rows]
        self.assertEqual({r["id"] for r in details if r["kind"] == "po"}, {"opp1"})
        self.assertEqual({r["id"] for r in details if r["kind"] == "visits"}, {"v1"})
        self.assertTrue(all(r.get("opportunityId") == "opp1" for r in details if r["kind"] in ("actions", "tests")))
        # v2 has no opportunity: it cannot be placed under any equipment, so it is left out and reported.
        self.assertEqual(insp["equipmentUnclassified"], {"visits": 1, "tests": 0})
        metro = build_plan(data, {**WEEK, "equipment": "Metrology"}, NOW)
        metro_rows = metro["_details"]["all"] if "all" in metro["_details"] else [r for rows in metro["_details"].values() for r in rows]
        self.assertEqual({r["id"] for r in metro_rows if r["kind"] == "po"}, {"opp2"})
        self.assertEqual([r for r in metro_rows if r["kind"] in ("tests", "actions")], [])
        self.assertIsNone(build_plan(data, WEEK, NOW)["equipmentUnclassified"])

    def test_equipment_filter_matches_stored_spellings_and_closed_linked_opportunities(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "kibo"
        data["visits"][0]["opportunity"] = "opp-closed"
        data["equipment"] = {"opp-closed": "KIBO"}
        kibo = build_plan(data, {**WEEK, "equipment": "Kibo"}, NOW)
        rows = kibo["_details"]["all"] if "all" in kibo["_details"] else [r for rows in kibo["_details"].values() for r in rows]
        self.assertEqual({r["id"] for r in rows if r["kind"] == "po"}, {"opp1"})
        self.assertEqual({r["id"] for r in rows if r["kind"] == "visits"}, {"v1"})

    def test_periods_are_inclusive_monday_to_sunday_and_allow_the_future(self):
        self.assertEqual(plan_period({"period": "week", "anchor": "2027-01-01"}),
                         {"kind": "week", "start": datetime(2026, 12, 28).date(), "end": datetime(2027, 1, 3).date(),
                          "previousAnchor": "2026-12-21", "nextAnchor": "2027-01-04"})
        quarter = plan_period({"period": "quarter", "anchor": "2026-11-15"})
        self.assertEqual((quarter["start"].isoformat(), quarter["end"].isoformat()), ("2026-10-01", "2026-12-31"))
        year = plan_period({"period": "year", "anchor": "2027-06-01"})
        self.assertEqual((year["previousAnchor"], year["nextAnchor"]), ("2026-01-01", "2028-01-01"))

    def test_anchor_is_required(self):
        with self.assertRaises(ValueError):
            plan_period({"period": "week", "anchor": ""})
        with self.assertRaises(ValueError):
            plan_period({"period": "day", "anchor": "2026-09-21"})


class TestPlanRules(unittest.TestCase):
    def test_summary_counts_only_what_is_still_planned_in_the_period(self):
        plan = build_plan(fixture(), WEEK, NOW)
        self.assertEqual(plan["period"], {"kind": "week", "start": "2026-09-21", "end": "2026-09-27",
                                          "previousAnchor": "2026-09-14", "nextAnchor": "2026-09-28"})
        self.assertEqual(plan["asOf"], "2026-09-18T03:00:00Z")
        self.assertEqual({key: value["value"] for key, value in plan["summary"].items()},
                         {"visits": 2, "tests": 1, "actions": 2, "po": 2})
        self.assertEqual(plan["overdue"], {"value": 1, "state": "ready", "reason": None})
        details = plan["_details"]
        self.assertEqual(ids(details["visits"]), ["v1", "v2"])
        self.assertEqual(ids(details["tests"]), ["ev1"])
        self.assertEqual(details["tests"][0]["evaluationId"], "ev1")
        self.assertEqual(details["tests"][0]["salesOwner"], "alice")
        self.assertEqual(ids(details["actions"]), ["a1", "a2"])
        self.assertEqual(details["actions"][0]["actionOwner"], "engineer")
        self.assertEqual(details["actions"][0]["actionOwnerName"], "Engineer Chen")
        self.assertEqual(details["actions"][0]["salesOwner"], "alice")

    def test_action_assignee_name_does_not_change_sales_attribution_or_filters(self):
        data = fixture()
        self.assertNotIn("engineer", [person["name"] for person in data["people"]])
        plan = build_plan(data, {**WEEK, "sales": "alice"}, NOW)
        self.assertEqual([(row["actionOwner"], row["actionOwnerName"], row["salesOwner"])
                          for row in plan["_details"]["actions"]],
                         [("engineer", "Engineer Chen", "alice"), ("alice", "Alice", "alice")])
        self.assertEqual([row["id"] for row in plan["sales"]], ["alice"])
        self.assertEqual(plan["_details"]["overdue"][0]["actionOwnerName"], "Alice")
        for filters in ({"sales": "bob"}, {"region": "South China"}):
            self.assertEqual(build_plan(data, {**WEEK, **filters}, NOW)["_details"]["actions"], [])

    def test_unavailable_assignee_name_is_null_without_losing_the_id(self):
        for full_name in (None, "", "  \t "):
            with self.subTest(full_name=full_name):
                data = fixture()
                data["action_people"][0]["full_name"] = full_name
                row = build_plan(data, WEEK, NOW)["_details"]["actions"][0]
                self.assertEqual((row["actionOwner"], row["actionOwnerName"]), ("engineer", None))
        data = fixture()
        data["action_people"] = []
        row = build_plan(data, WEEK, NOW)["_details"]["actions"][0]
        self.assertEqual((row["actionOwner"], row["actionOwnerName"]), ("engineer", None))
        data["actions"][0]["action_owner"] = None
        row = build_plan(data, WEEK, NOW)["_details"]["actions"][0]
        self.assertEqual((row["actionOwner"], row["actionOwnerName"]), (None, None))

    def test_overdue_keeps_its_due_date_and_leads_the_full_list(self):
        details = build_plan(fixture(), WEEK, NOW)["_details"]
        self.assertEqual([(r["id"], r["date"], r["carryover"]) for r in details["overdue"]], [("a-old", "2026-09-18", True)])
        self.assertEqual(ids(details["all"]), ["a-old", "v1", "ev1", "a1", "a2", "opp1", "v2", "opp2"])
        self.assertEqual(len(details["all"]), sum(len(details[key]) for key in ("visits", "tests", "actions", "po", "overdue")))

    def test_tests_of_a_finished_or_cancelled_flow_are_not_plans(self):
        for change in ({"status": status} for status in ("Requested", "Scope Confirmed", "Sample Received", "Analysis", "Internal Review", "Customer Review", "Accepted", "Rejected")):
            data = fixture()
            data["evaluations"][0].update(change)
            self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["tests"]["value"], 0, change)
        data = fixture()
        data["requests"][0]["status"] = "Cancelled"
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["tests"]["value"], 0)

    def test_demo_needs_both_preparations_but_no_test_run(self):
        for status in ("Scheduled", "Testing"):
            data = fixture()
            data.pop("tests")
            evaluation = data["evaluations"][0]
            evaluation["status"] = status
            for branch in ("wafer", "test"):
                evaluation[f"{branch}_preparation_status"] = "Pending"
                self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["tests"]["value"], 0)
                evaluation[f"{branch}_preparation_status"] = "Completed"
            plan = build_plan(data, WEEK, NOW)
            self.assertEqual(plan["summary"]["tests"]["value"], 1)
            self.assertEqual(plan["_details"]["tests"][0]["status"], status)
            # Legacy records use the same preparation fallback as the Demo Test UI.
            evaluation.pop("wafer_preparation_status")
            evaluation.pop("test_preparation_status")
            self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["tests"]["value"], 1)

    def test_run_results_and_rounds_do_not_remove_or_duplicate_a_demo(self):
        for status in ("Planned", "Completed", "Cancelled"):
            data = fixture()
            for run in data["tests"]:
                run["status"] = status
            data["evaluations"][0]["test_round"] = 3
            self.assertEqual(ids(build_plan(data, WEEK, NOW)["_details"]["tests"]), ["ev1"])
        data["evaluations"][0]["status"] = "Internal Review"
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["tests"]["value"], 0)
        data["evaluations"][0]["status"] = "Testing"
        data["evaluations"][0]["test_run_deadline"] = None
        self.assertEqual(build_plan(data, WEEK, NOW)["summary"]["tests"]["value"], 1)

    def test_active_demo_deadline_never_gates_counting_or_invents_a_calendar_day(self):
        for deadline in (None, "2026-09-18", "2026-09-23", "2027-02-01"):
            for period in ("week", "month", "quarter", "year"):
                data = fixture()
                data["evaluations"][0]["test_run_deadline"] = deadline
                plan = build_plan(data, {**WEEK, "period": period, "includeOverdue": False}, NOW)
                self.assertEqual(plan["summary"]["tests"], {"value": 1, "state": "ready", "reason": None})
                self.assertEqual(plan["_details"]["tests"][0]["date"], deadline)
                self.assertEqual(plan["sales"][0]["tests"], plan["summary"]["tests"])
                self.assertEqual(plan["markets"][0]["activities"]["state"], "ready")
                self.assertEqual(len(plan["_details"]["all"]), sum(m["value"] for m in plan["summary"].values()))
                filtered = build_plan(data, {**WEEK, "sales": "bob"}, NOW)
                self.assertEqual(filtered["summary"]["tests"]["value"], 0)

    def test_actions_and_po_need_an_open_opportunity(self):
        for stage in ("po_received", "lost"):
            data = fixture()
            data["opportunities"][0]["stage"] = stage
            plan = build_plan(data, WEEK, NOW)
            self.assertEqual((plan["summary"]["actions"]["value"], plan["overdue"]["value"], ids(plan["_details"]["po"])), (0, 0, ["opp2"]))

    def test_amounts_are_cny_and_a_missing_amount_is_reported_not_zeroed(self):
        plan = build_plan(fixture(), WEEK, NOW)
        self.assertEqual(plan["poAmounts"], [{"currency": "CNY", "value": "6800000.00"}])
        self.assertTrue(plan["poAmountIncomplete"])
        first, second = plan["expectedPO"]["items"]
        self.assertEqual((first["amount"], first["currency"], first["probabilityLevel"], first["status"]), ("6800000.00", "CNY", "upside", "rfq_validated"))
        self.assertEqual((second["amount"], second["currency"], second["probabilityLevel"]), (None, None, None))
        by_owner = {row["id"]: row for row in plan["sales"]}
        self.assertEqual((by_owner["alice"]["poAmounts"], by_owner["alice"]["poAmountIncomplete"]), ([{"currency": "CNY", "value": "6800000.00"}], False))
        self.assertEqual((by_owner["bob"]["poAmounts"], by_owner["bob"]["poAmountIncomplete"]), ([], True))

    def test_stage_one_is_counted_without_an_amount(self):
        data = fixture()
        data["opportunities"][0]["stage"] = "qualified_opportunity"
        plan = build_plan(data, WEEK, NOW)
        self.assertEqual(plan["summary"]["po"]["value"], 2)
        self.assertEqual((plan["poAmounts"], plan["poAmountIncomplete"]), ([], True))

    def test_no_expected_po_is_an_empty_complete_amount(self):
        plan = build_plan(fixture(), {"period": "week", "anchor": "2026-10-05"}, NOW)
        self.assertEqual((plan["summary"]["po"], plan["poAmounts"], plan["poAmountIncomplete"], plan["expectedPO"]),
                         ({"value": 0, "state": "ready", "reason": None}, [], False, {"items": [], "total": 0}))

    def test_sales_and_markets_add_up_to_the_summary(self):
        plan = build_plan(fixture(), WEEK, NOW)
        self.assertEqual([(r["id"], r["name"]) for r in plan["sales"]], [("alice", "Alice"), ("bob", "Bob")])
        for key in ("visits", "tests", "actions", "po"):
            self.assertEqual(sum(r[key]["value"] for r in plan["sales"]), plan["summary"][key]["value"])
        self.assertEqual([(r["name"], r["activities"]["value"], r["po"]["value"]) for r in plan["markets"]],
                         [("Frontend", 4, 1), (None, 1, 1)])

    def test_unowned_records_form_their_own_group(self):
        data = fixture()
        data["visits"][1]["visit_owner"] = None
        plan = build_plan(data, WEEK, NOW)
        self.assertEqual([(r["id"], r["name"], r["visits"]["value"]) for r in plan["sales"]][-1], (None, "", 1))

    def test_filters_apply_to_summary_and_details_alike(self):
        plan = build_plan(fixture(), {**WEEK, "sales": "bob"}, NOW)
        self.assertEqual({key: value["value"] for key, value in plan["summary"].items()}, {"visits": 1, "tests": 0, "actions": 0, "po": 1})
        self.assertEqual((plan["overdue"]["value"], ids(plan["_details"]["all"])), (0, ["v2", "opp2"]))
        plan = build_plan(fixture(), {**WEEK, "market": "Frontend"}, NOW)
        self.assertEqual(ids(plan["_details"]["all"]), ["a-old", "v1", "ev1", "a1", "a2", "opp1"])
        plan = build_plan(fixture(), {**WEEK, "region": "South China"}, NOW)
        self.assertEqual(ids(plan["_details"]["all"]), ["v2", "opp2"])
        # A territory, spelled out by cockpit.scoped() as the regions it covers, selects all of them.
        china = {**WEEK, "region": "China", "regions": {"China", "East China", "South China"}}
        self.assertEqual(ids(build_plan(fixture(), china, NOW)["_details"]["all"]), ids(build_plan(fixture(), WEEK, NOW)["_details"]["all"]))
        self.assertEqual(ids(build_plan(fixture(), {**china, "regions": {"China", "South China"}}, NOW)["_details"]["all"]), ["v2", "opp2"])

    def test_a_record_without_its_date_is_not_a_zero(self):
        data = fixture()
        data["visits"][0]["visit_date"] = None
        plan = build_plan(data, WEEK, NOW)
        self.assertEqual(plan["summary"]["visits"], {"value": None, "state": "insufficient", "reason": "missing_date"})
        self.assertEqual(plan["summary"]["tests"]["state"], "ready")
        self.assertEqual(plan["markets"][0]["activities"]["state"], "insufficient")
        data = fixture()
        data["actions"][0]["due"] = None
        plan = build_plan(data, WEEK, NOW)
        self.assertEqual((plan["summary"]["actions"]["state"], plan["overdue"]["state"]), ("insufficient", "insufficient"))

    def test_missing_dates_only_affect_their_sales_and_market_groups(self):
        for source, field, kind in (("visits", "visit_date", "visits"),
                                    ("actions", "due", "actions")):
            with self.subTest(kind=kind):
                data = fixture()
                data[source][0][field] = None
                plan = build_plan(data, WEEK, NOW)
                alice = next(row for row in plan["sales"] if row["id"] == "alice")
                bob = next(row for row in plan["sales"] if row["id"] == "bob")
                self.assertEqual(plan["summary"][kind]["state"], "insufficient")
                self.assertEqual(alice[kind]["state"], "insufficient")
                filtered_bob = build_plan(data, {**WEEK, "sales": "bob"}, NOW)
                self.assertEqual(bob[kind], filtered_bob["summary"][kind])
                unaffected = next(row for row in plan["markets"] if row["name"] is None)
                self.assertEqual(unaffected["activities"], {"value": 1, "state": "ready", "reason": None})
                affected = next(row for row in plan["markets"] if row["name"] == "Frontend")
                self.assertEqual(affected["activities"]["state"], "insufficient")

    def test_a_rep_with_only_undated_records_still_shows_the_gap(self):
        data = fixture()
        data["people"].append({"name": "carol", "full_name": "Carol"})
        data["visits"].append({"name": "v5", "account": "c1", "visit_owner": "carol", "subject": "No date", "visit_date": None, "status": "Planned"})
        plan = build_plan(data, WEEK, NOW)
        carol = next(row for row in plan["sales"] if row["id"] == "carol")
        self.assertEqual((carol["name"], carol["visits"]["state"], carol["tests"]), ("Carol", "insufficient", {"value": 0, "state": "ready", "reason": None}))
        alice = next(row for row in plan["sales"] if row["id"] == "alice")
        self.assertEqual(alice["visits"], {"value": 1, "state": "ready", "reason": None})

    def test_period_only_details_exclude_carryover_before_pagination(self):
        old = build_plan(fixture(), WEEK, NOW)
        current = build_plan(fixture(), {**WEEK, "includeOverdue": False}, NOW)
        self.assertTrue(any(row["carryover"] for row in old["_details"]["all"]))
        self.assertEqual(current["_details"]["all"], [row for row in old["_details"]["all"] if not row["carryover"]])
        self.assertEqual(len(current["_details"]["all"]), sum(metric["value"] for metric in current["summary"].values()))
        self.assertEqual(current["overdue"], old["overdue"])
        self.assertEqual(current["_details"]["overdue"], old["_details"]["overdue"])

    def test_expected_po_lists_the_first_five_of_the_po_details(self):
        data = fixture()
        data["opportunities"] = [{**data["opportunities"][0], "name": f"opp{i}", "po_date": f"2026-09-2{7 - i % 3}"} for i in range(7)]
        plan = build_plan(data, WEEK, NOW)
        self.assertEqual(plan["expectedPO"]["total"], 7)
        self.assertEqual(plan["expectedPO"]["items"], plan["_details"]["po"][:5])
        self.assertEqual(ids(plan["_details"]["po"]), ["opp2", "opp5", "opp1", "opp4", "opp0", "opp3", "opp6"])


if __name__ == "__main__":
    unittest.main()
