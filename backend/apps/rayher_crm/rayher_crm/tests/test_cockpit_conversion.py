"""History ratios never substitute today's funnel counts or missing data with zero."""
import unittest
from datetime import datetime

from rayher_crm.services.cockpit_conversion import build_conversions, conversion_threshold, pipeline_coverage
from rayher_crm.services.cockpit_metrics import metric
from rayher_crm.services.opportunity_stages import MILESTONE_STAGES, OPEN_STAGES

NOW = datetime(2026, 9, 22, 12)
QUERY = {"period": "week", "anchor": "2026-09-22"}
COVERAGE = {"stage": "2024-01-01", "fields": "2024-01-01"}


def fixture():
    return {"customers": [{"name": "c", "customer_name": "Customer", "custom_crm_region": "East China", "custom_crm_segment": "Frontend"}],
            "opportunities": [{"name": "opp", "title": "Opportunity", "creation": "2023-01-01", "account": "c", "opportunity_owner": "alice", "stage": "lost"}],
            "stages": [], "history": []}


def event(stage, when="2026-09-01", opportunity="opp", **extra):
    return {"name": f"{stage}-{when}-{opportunity}", "opportunity": opportunity, "to_stage": stage,
            "reached_at": when, "recorded_at": when, "reached_at_basis": "recorded", **extra}


def review(target=1000, actual=500):
    return {"pipeline": [{"key": key, "amount": metric("300")} for key in OPEN_STAGES] + [{"key": "po", "amount": metric("9999")}],
            "orders": {"target": metric(str(target)), "actual": metric(str(actual))}}


class TestConversions(unittest.TestCase):
    def test_counts_distinct_ever_reached_stages_including_lost_not_current_funnel(self):
        data = fixture()
        data["stages"] = [event(stage) for stage in MILESTONE_STAGES if stage != "internal_validation"]
        data["stages"].append(event("demo_done", "2026-09-21", source="rollback"))
        result, details = build_conversions(data, QUERY, NOW, COVERAGE)
        self.assertTrue(result["complete"])
        self.assertEqual(len(result["items"]), 5)
        self.assertTrue(all(row["rate"]["value"] == "100.00" for row in result["items"]))
        self.assertEqual((result["items"][-1]["fromStage"], result["items"][-1]["toStage"]), ("quotation_sent", "po_received"))
        self.assertEqual(len(details["reached_demo_done"]), 1)
        self.assertEqual(details["reached_demo_done"][0]["at"], "2026-09-20T16:00:00Z")

    def test_24_calendar_month_boundaries_cutoff_and_timezone(self):
        data = fixture()
        for when, expected in (("2024-09-21T15:59:59Z", 0), ("2024-09-21T16:00:00Z", 1),
                               ("2026-09-22T04:00:00Z", 1), ("2026-09-22T04:00:01Z", 0)):
            data["stages"] = [event("qualified_opportunity", when)]
            result, _ = build_conversions(data, QUERY, NOW, COVERAGE)
            self.assertEqual(result["items"][0]["fromCount"], expected)
        self.assertEqual(result["start"], "2024-09-22")
        historical, _ = build_conversions(data, {"period": "week", "anchor": "2026-09-07"}, NOW, COVERAGE)
        self.assertEqual((historical["start"], historical["end"]), ("2024-09-13", "2026-09-13"))
        leap, _ = build_conversions(data, {"period": "month", "anchor": "2024-02-01"}, NOW, COVERAGE)
        self.assertEqual(leap["start"], "2022-02-28")

    def test_stage_independent_ratio_is_not_capped_or_cohort_intersected(self):
        data = fixture()
        data["opportunities"].append({**data["opportunities"][0], "name": "old"})
        data["stages"] = [event("qualified_opportunity"), event("demo_done"),
                          event("qualified_opportunity", "2023-01-01", "old"), event("demo_done", opportunity="old")]
        result, _ = build_conversions(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["items"][0]["rate"]["value"], "200.00")

    def test_missing_coverage_unknown_and_upper_bound_dates_are_not_successful_zero(self):
        data = fixture()
        data["stages"] = [event("qualified_opportunity")]
        for coverage in ({}, {"stage": "bad"}, {"stage": "2024-09-23"}):
            result, details = build_conversions(data, QUERY, NOW, coverage)
            self.assertEqual(result["items"][0]["rate"]["state"], "insufficient")
            self.assertEqual(len(details["reached_qualified_opportunity"]), 1)
            self.assertIsNone(result["items"][0]["bottleneck"])
        for basis in ("unknown", "upper_bound", None):
            data["stages"] = [event("qualified_opportunity", reached_at_basis=basis)]
            result, details = build_conversions(data, QUERY, NOW, COVERAGE)
            self.assertFalse(result["complete"])
            self.assertEqual(details["reached_qualified_opportunity"], [])
        data["stages"] = [event("demo_done", "bad")]
        self.assertFalse(build_conversions(data, QUERY, NOW, COVERAGE)[0]["complete"])

    def test_old_upper_bound_is_outside_window_and_evidence_dates_are_counted(self):
        data = fixture()
        data["stages"] = [event("qualified_opportunity", "2023-01-01", reached_at_basis="upper_bound", recorded_at="2026-09-15"),
                          event("demo_done", reached_at_basis="evidence"), event("quotation_sent", reached_at_basis="declared")]
        result, details = build_conversions(data, QUERY, NOW, COVERAGE)
        self.assertTrue(result["complete"])
        self.assertEqual(len(details["reached_demo_done"]), 1)
        self.assertEqual(result["items"][0]["rate"]["reason"], "no_source_stage")

    def test_filters_replay_owner_at_cutoff_and_keep_customer_master_scope(self):
        data = fixture()
        data["opportunities"][0]["opportunity_owner"] = "bob"
        data["history"] = [{"name": "owner-change", "opportunity": "opp", "at": "2026-09-15", "field": "opportunity_owner", "from_value": "alice", "to_value": "bob"}]
        data["stages"] = [event("qualified_opportunity")]
        historical = {"period": "week", "anchor": "2026-09-07", "sales": "alice", "region": "East China", "market": "Frontend"}
        result, details = build_conversions(data, historical, NOW, COVERAGE)
        self.assertEqual(result["items"][0]["fromCount"], 1)
        self.assertEqual(details["reached_qualified_opportunity"][0]["owner"], "alice")
        for changed in ({"sales": "bob"}, {"region": "Other"}, {"market": "Other"}):
            self.assertEqual(build_conversions(data, {**historical, **changed}, NOW, COVERAGE)[0]["items"][0]["fromCount"], 0)
        # A territory, spelled out by cockpit.scoped() as the regions it covers, selects all of them.
        china = {**historical, "region": "China", "regions": {"China", "East China"}}
        self.assertEqual(build_conversions(data, china, NOW, COVERAGE)[0]["items"][0]["fromCount"], 1)
        self.assertEqual(build_conversions(data, {**china, "regions": {"China"}}, NOW, COVERAGE)[0]["items"][0]["fromCount"], 0)
        result, _ = build_conversions(data, historical, NOW, {"stage": "2024-01-01"})
        self.assertFalse(result["complete"])

    def test_bottleneck_uses_unrounded_ratio_at_configured_boundary(self):
        data = fixture()
        data["opportunities"] = [{**data["opportunities"][0], "name": f"opp{i}"} for i in range(3)]
        data["stages"] = [event("qualified_opportunity", opportunity=f"opp{i}") for i in range(3)] + [event("demo_done", opportunity="opp0")]
        row = build_conversions(data, QUERY, NOW, COVERAGE, "33.332")[0]["items"][0]
        self.assertEqual(row["rate"]["value"], "33.33")
        self.assertFalse(row["bottleneck"])
        self.assertTrue(build_conversions(data, QUERY, NOW, COVERAGE, "33.334")[0]["items"][0]["bottleneck"])

    def test_latest_arrival_and_detail_order_compare_instants_not_iso_string_shapes(self):
        data = fixture()
        data["opportunities"].append({**data["opportunities"][0], "name": "other"})
        data["stages"] = [event("demo_done", "2026-09-01T00:00:00Z", name="old"),
                          event("demo_done", "2026-09-01T00:00:00.500000Z", name="new"),
                          event("demo_done", "2026-09-01T00:00:00.250000Z", opportunity="other")]
        rows = build_conversions(data, QUERY, NOW, COVERAGE)[1]["reached_demo_done"]
        self.assertEqual([row["id"] for row in rows], ["opp", "other"])
        self.assertEqual(rows[0]["eventId"], "new")
        data["stages"].reverse()
        self.assertEqual(build_conversions(data, QUERY, NOW, COVERAGE)[1]["reached_demo_done"], rows)

    def test_zero_denominator_and_strict_configurable_bottleneck(self):
        data = fixture()
        empty, _ = build_conversions(data, QUERY, NOW, COVERAGE)
        self.assertEqual(empty["items"][0]["rate"]["state"], "not_applicable")
        data["stages"] = [event("qualified_opportunity")]
        zero, _ = build_conversions(data, QUERY, NOW, COVERAGE)
        self.assertEqual(zero["items"][0]["rate"]["value"], "0.00")
        self.assertTrue(zero["items"][0]["bottleneck"])
        self.assertFalse(build_conversions(data, QUERY, NOW, COVERAGE, 0)[0]["items"][0]["bottleneck"])
        for invalid in (None, -1, 101, True, "NaN", "Infinity", "bad"):
            self.assertEqual(conversion_threshold(invalid), 45)
        self.assertEqual(conversion_threshold("44.5"), 44.5)


class TestPipelineCoverage(unittest.TestCase):
    def test_s2_to_s6_only_divided_by_actual_remaining_annual_target(self):
        result = pipeline_coverage(review())
        self.assertEqual(result["openPipeline"]["value"], "1500.00")
        self.assertEqual(result["remainingTarget"]["value"], "500.00")
        self.assertEqual(result["ratio"]["value"], "3.00")

    def test_target_met_zero_or_exceeded_is_not_infinity_or_negative_ratio(self):
        for target, actual in ((0, 0), (1000, 1000), (1000, 1500)):
            result = pipeline_coverage(review(target, actual))
            self.assertEqual(result["ratio"]["reason"], "annual_target_met")
            self.assertEqual(result["ratio"]["state"], "not_applicable")
        self.assertEqual(pipeline_coverage(review(1000, 1500))["remainingTarget"]["value"], "-500.00")

    def test_missing_amounts_targets_and_unsupported_scope_propagate_unknown(self):
        for state in ("not_set", "not_applicable", "insufficient"):
            data = review(); data["orders"]["target"] = metric(None, state)
            self.assertEqual(pipeline_coverage(data)["ratio"]["state"], state)
        for section in ("actual", "target"):
            data = review(); data["orders"][section] = metric(None, "insufficient")
            self.assertEqual(pipeline_coverage(data)["ratio"]["state"], "insufficient")
        for amount in (metric(None, "insufficient"), metric("NaN"), metric(None)):
            data = review(); data["pipeline"][1]["amount"] = amount
            self.assertEqual(pipeline_coverage(data)["ratio"]["state"], "insufficient")
        data = review(); data["pipeline"].pop(1)
        self.assertEqual(pipeline_coverage(data)["ratio"]["state"], "insufficient")

    def test_equipment_filter_matches_the_type_whatever_its_stored_spelling(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "KIBO "
        data["stages"] = [event("qualified_opportunity")]
        query = {"period": "week", "anchor": "2026-09-07"}
        self.assertEqual(build_conversions(data, {**query, "equipment": "Kibo"}, NOW, COVERAGE)[0]["items"][0]["fromCount"], 1)
        self.assertEqual(build_conversions(data, {**query, "equipment": "Nansi"}, NOW, COVERAGE)[0]["items"][0]["fromCount"], 0)


if __name__ == "__main__":
    unittest.main()
