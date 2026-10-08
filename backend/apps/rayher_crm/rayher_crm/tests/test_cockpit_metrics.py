"""Run with plain unittest; these rules must not depend on a live site."""
import json
import unittest
from datetime import date, datetime
from decimal import Decimal

from rayher_crm.services.cockpit_metrics import BEFORE_HISTORY, build_review, handling_key, period, quotation_expiry, stamp

NOW = datetime(2026, 9, 16, 12)
COVERAGE = {key: "2025-01-01" for key in ("stage", "fields", "actions", "po", "probability")}
QUERY = {"period": "week", "anchor": "2026-09-07"}


def fixture():
    data = {key: [] for key in ("customers", "people", "opportunities", "history", "stages", "actions", "probabilities", "visits", "leads", "requests", "evaluations", "tests", "quotes", "versions")}
    data["customers"] = [{"name": "c", "customer_name": "Customer", "custom_crm_region": "East China", "custom_crm_segment": "Frontend"}]
    data["people"] = [{"name": "alice", "full_name": "Alice"}, {"name": "bob", "full_name": "Bob"}]
    data["opportunities"] = [{"name": "opp", "creation": "2026-01-01", "title": "Opportunity", "account": "c", "opportunity_owner": "alice", "stage": "demo_done", "amount": "200.00", "currency": "CNY", "amount_cny": "200.00"}]
    data["bookings"] = []
    data["booking_dates_ready"] = True
    data["cny_amount_ready"] = True
    return data


def stage(event, when, before="qualified_opportunity", after="demo_done", **extra):
    return {"name": event + when, "opportunity": "opp", "event": event, "reached_at": when, "recorded_at": when,
            "reached_at_basis": "recorded", "source": "event", "from_stage": before, "to_stage": after, **extra}


def booking(day="2026-09-13", **extra):
    return {"name": "booking", "source": "Opportunity", "source_opportunity": "opp", "status": "Confirmed",
            "actual_po_date": day, "booking_owner": "bob", "currency": "CNY", "amount": "1.00", **extra}


def history(field, when, before, after):
    return {"name": field + when, "opportunity": "opp", "field": field, "at": when,
            **({"from_owner": before, "to_owner": after} if field == "opportunity_owner" else {}),
            "from_value": json.dumps(before) if isinstance(before, dict) else before,
            "to_value": json.dumps(after) if isinstance(after, dict) else after}


class TestCockpitMetrics(unittest.TestCase):
    def test_pending_downgrades_keep_history_use_current_owner_and_reappear_on_next_event(self):
        data = fixture()
        data["probabilities"] = [{"name": "first", "opportunity": "opp", "from_level": "committed", "to_level": "upside", "changed_at": "2026-09-08", "reason": "Delay"}]
        data["recoveries"] = [{"name": "recovery", "probability_change": "first", "plan": "Meet buyer", "acted_at": None}]
        def review(sales=""):
            return build_review(data, {**QUERY, "sales": sales}, NOW, COVERAGE)
        self.assertEqual(review()["_details"]["downgrade"][0]["recovery"]["state"], "pending")
        data["recoveries"][0]["plan"] = "Edited plan"
        self.assertEqual(len(review()["_details"]["downgrade"]), 1)
        data["opportunities"][0]["opportunity_owner"] = "bob"
        data["history"] = [history("opportunity_owner", "2026-09-15", "alice", "bob")]
        self.assertEqual(len(review("alice")["_details"]["downgrade"]), 0)
        self.assertEqual(len(review("alice")["_details"]["downgrade_history"]), 0)
        self.assertEqual(len(review("bob")["_details"]["downgrade_history"]), 1)
        self.assertEqual(review("bob")["_details"]["downgrade"][0]["currentOwner"], "bob")
        data["recoveries"][0].update(acted_at="2026-09-16", acted_by="bob", action_taken="Met buyer")
        self.assertEqual(len(review()["_details"]["downgrade"]), 0)
        audit = review()["_details"]["downgrade_history"][0]
        self.assertEqual((audit["recovery"]["state"], audit["recovery"]["actionTaken"]), ("handled", "Met buyer"))
        data["probabilities"].append({**data["probabilities"][0], "name": "second", "from_level": "upside", "to_level": "pipeline", "changed_at": "2026-09-10"})
        # A legacy event without a plan remains actionable, never implicitly handled.
        self.assertIsNone(review()["_details"]["downgrade"][0]["recovery"])
        self.assertEqual(next(w["count"]["value"] for w in review()["warnings"] if w["key"] == "downgrade"), 1)
        data["probabilities"].append({**data["probabilities"][1], "name": "third", "changed_at": "2026-09-11"})
        self.assertEqual(len(review()["_details"]["downgrade"]), 2)
        self.assertEqual(next(w["count"]["value"] for w in review()["warnings"] if w["key"] == "downgrade"), 1)
        data["probabilities"].append({**data["probabilities"][1], "name": "outside", "changed_at": "2026-09-15"})
        self.assertEqual(len(review()["_details"]["downgrade"]), 2)

    def test_last_complete_week_and_shanghai_boundary(self):
        result = period({}, NOW)
        self.assertEqual(str(result["start"]), "2026-09-07 00:00:00")
        self.assertEqual(str(result["end"]), "2026-09-14 00:00:00")
        self.assertEqual(stamp("2026-09-13T16:00:00Z"), datetime(2026, 9, 14))
        monday = period({}, datetime(2026, 9, 14))
        self.assertEqual(monday["start"], datetime(2026, 9, 7))

    def test_partial_period_uses_same_elapsed_progress(self):
        result = period({"period": "month", "anchor": "2026-09-01"}, NOW)
        self.assertEqual(result["previous_end"], datetime(2026, 8, 16, 12))
        with self.assertRaises(ValueError):
            period({"period": "week", "anchor": "2027-01-01"}, NOW)

    def test_historical_stage_is_one_bucket_and_owner_amount_replay(self):
        data = fixture()
        data["opportunities"][0]["opportunity_owner"] = "bob"
        data["history"] = [history("opportunity_owner", "2026-09-15", "alice", "bob"), history("amount_cny", "2026-09-15", "100.00", "200.00")]
        data["stages"] = [stage("demo_customer_review", "2026-09-15")]
        result = build_review(data, {**QUERY, "sales": "alice"}, NOW, COVERAGE)
        self.assertEqual([r["count"]["value"] for r in result["pipeline"][:6]], [1, 0, 0, 0, 0, 0])
        self.assertEqual(result["_details"]["qualified_opportunity"][0]["amount"], "100.00")

    def test_no_coverage_does_not_use_current_values_or_first_history_row(self):
        data = fixture()
        data["history"] = [history("amount", "2026-01-01", "0", "200")]
        result = build_review(data, QUERY, NOW, {})
        self.assertEqual(result["pipeline"][1]["count"]["state"], "insufficient")
        self.assertIsNone(result["pipeline"][1]["amount"]["value"])

    def test_migration_unknown_cannot_restore_earlier_state(self):
        data = fixture()
        data["stages"] = [stage("migration", "2026-09-15", source="migration", reached_at_basis="upper_bound")]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["pipeline"][0]["count"]["state"], "insufficient")

    def test_foreign_currency_is_not_summed_into_cny(self):
        data = fixture(); data["opportunities"][0].update(currency="USD", amount_cny=None)
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["pipeline"][1]["count"]["value"], 1)
        self.assertEqual(result["pipeline"][1]["amount"]["state"], "insufficient")

    def test_cny_sums_sales_entered_values_across_original_currencies(self):
        data = fixture()
        base = data["opportunities"][0]
        data["opportunities"] = [{**base, "name": str(i), "currency": currency,
                                  "amount": "999999", "amount_cny": value}
                                 for i, (currency, value) in enumerate(
                                     [("CNY", "1000000.10"), ("USD", "2000000.20"), ("EUR", "3000000.30")])]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["pipeline"][1]["amount"]["value"], "6000000.60")
        self.assertEqual(result["sales"][0]["pipeline"]["value"], "6000000.60")
        self.assertEqual({r["currency"] for r in result["_details"]["demo_done"]}, {"CNY"})
        self.assertEqual({r["amount"] for r in result["_details"]["demo_done"]}, {"1000000.10", "2000000.20", "3000000.30"})
        self.assertEqual({r["amount"] for r in result["_details"]["stalled"]}, {"1000000.10", "2000000.20", "3000000.30"})
        # Opportunity estimates never stand in for order amounts; without a PO the year's orders are ¥0.
        self.assertEqual(result["orders"]["actual"]["value"], "0.00")

    def test_cny_missing_or_zero_never_falls_back_to_original_amount(self):
        for missing in (None, "", 0, "0.00", "-1", "NaN"):
            with self.subTest(missing=missing):
                data = fixture()
                data["opportunities"].append({**data["opportunities"][0], "name": "missing", "amount_cny": missing})
                result = build_review(data, QUERY, NOW, COVERAGE)
                self.assertEqual(result["pipeline"][1]["count"]["value"], 2)
                self.assertIsNone(result["pipeline"][1]["amount"]["value"])
                self.assertEqual(result["sales"][0]["pipeline"]["state"], "insufficient")
                row = next(r for r in result["_details"]["demo_done"] if r["id"] == "missing")
                self.assertIsNone(row["amount"])

    def test_amounts_left_blank_at_s1_stay_unknown_after_demo_done_until_entered(self):
        # Blank S1 amounts are stored as 0.00, and the Customer Review event may still take the deal to S2.
        # Sales entered both on 2026-09-15, after the week viewed; history records them as filled in from empty.
        data = fixture()
        data["opportunities"][0].update(amount="300.00", amount_cny="300.00")
        data["opportunities"].append({**data["opportunities"][0], "name": "priced", "amount": "200.00", "amount_cny": "200.00"})
        data["history"] = [history("amount", "2026-09-15", "", "300.00"), history("amount_cny", "2026-09-15", "", "300.00")]
        past = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(past["pipeline"][1]["count"]["value"], 2)
        self.assertEqual((past["pipeline"][1]["amount"]["state"], past["sales"][0]["pipeline"]["state"]),
                         ("insufficient", "insufficient"))
        self.assertEqual({r["id"]: r["amount"] for r in past["_details"]["demo_done"]}, {"opp": None, "priced": "200.00"})
        current = build_review(data, {"period": "month", "anchor": "2026-09-01"}, NOW, COVERAGE)
        self.assertEqual(current["pipeline"][1]["amount"]["value"], "500.00")

    def test_cny_backfill_falls_back_to_the_cny_original_amount_before_filling(self):
        data = fixture()
        data["opportunities"][0]["amount_cny"] = "250.00"
        data["history"] = [history("amount_cny", "2026-09-15", "", "250.00"), history("amount", "2026-09-12", "180.00", "200.00")]
        data["stages"] = [stage("marked_lost", "2026-09-08", "demo_done", "lost"),
                          stage("reopened", "2026-09-10", "lost", "demo_done")]
        result = build_review(data, QUERY, NOW, COVERAGE)
        # Before the backfill, an Opportunity priced in CNY replays its original amount of that time.
        self.assertEqual(result["pipeline"][1]["amount"]["value"], "200.00")
        self.assertEqual(result["losses"]["items"][0]["amount"], "180.00")
        current = build_review(data, {"period": "month", "anchor": "2026-09-01"}, NOW, COVERAGE)
        self.assertEqual(current["pipeline"][1]["amount"]["value"], "250.00")
        # Any other currency stays missing until Sales enter it.
        data["opportunities"][0]["currency"] = "USD"
        foreign = build_review(data, QUERY, NOW, COVERAGE)
        self.assertIsNone(foreign["pipeline"][1]["amount"]["value"])
        self.assertIsNone(foreign["losses"]["items"][0]["amount"])
        data["history"].append(history("currency", "2026-09-14", "CNY", "USD"))
        switched = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(switched["pipeline"][1]["amount"]["value"], "200.00")

    def test_cny_empty_scope_is_zero_but_old_schema_is_insufficient(self):
        data = fixture()
        data["opportunities"] = []
        self.assertEqual(build_review(data, QUERY, NOW, COVERAGE)["pipeline"][1]["amount"]["value"], "0.00")
        data["cny_amount_ready"] = False
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["pipeline"][1]["amount"]["reason"], "amount_cny_unavailable")
        self.assertIsNone(result["sales"][0]["pipeline"]["value"])
        self.assertEqual(result["orders"]["count"]["value"], 0)

    def test_cny_s1_not_valued_and_filters_match_detail_and_sales(self):
        data = fixture()
        base = data["opportunities"][0]
        data["opportunities"] += [
            {**base, "name": "s1", "stage": "qualified_opportunity", "amount_cny": "900000"},
            {**base, "name": "bob", "opportunity_owner": "bob", "amount_cny": "500"}]
        result = build_review(data, {**QUERY, "sales": "alice", "region": "East China", "market": "Frontend"}, NOW, COVERAGE)
        self.assertEqual(result["pipeline"][0]["amount"]["state"], "not_applicable")
        self.assertEqual(result["pipeline"][1]["amount"]["value"], "200.00")
        self.assertEqual(result["sales"][0]["pipeline"]["value"], "200.00")
        self.assertEqual(len(result["_details"]["demo_done"]), 1)
        excluded = build_review(data, {**QUERY, "region": "South China"}, NOW, COVERAGE)
        self.assertEqual(excluded["pipeline"][1]["amount"]["value"], "0.00")

    def test_current_cny_is_usable_without_claiming_historical_coverage(self):
        data = fixture()
        data["opportunities"][0].update(currency="USD", amount_cny="1400.25")
        current = build_review(data, {"period": "month", "anchor": "2026-09-01"}, NOW, {})
        self.assertEqual(current["pipeline"][1]["amount"]["value"], "1400.25")
        self.assertEqual(current["stalled"]["count"]["state"], "insufficient")
        past = build_review(data, QUERY, NOW, {})
        self.assertIsNone(past["pipeline"][1]["amount"]["value"])

    def test_po_uses_current_bookings_not_repeated_stage_events(self):
        data = fixture()
        data["stages"] = [stage("po_confirmed", "2026-02-01"), stage("rollback", "2026-03-01"),
                          stage("po_confirmed", "2026-08-01"), stage("migration", "2026-09-01", source="migration")]
        self.assertEqual(build_review(data, QUERY, NOW, COVERAGE)["orders"]["count"]["value"], 0)
        data["bookings"] = [booking(name="replacement"), booking(name="old", status="Cancelled")]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["orders"]["count"]["value"], 1)
        self.assertEqual([(r["id"], r["kind"]) for r in result["_details"]["po"]], [("replacement", "booking")])
        self.assertEqual(result["orders"]["actual"]["value"], "1.00")

    def test_po_actual_calendar_date_bounds_and_current_period(self):
        data = fixture()
        data["bookings"] = [booking(day, name=str(i)) for i, day in enumerate(
            ["2025-12-31", "2026-01-01", "2026-09-13", "2026-09-14", "2026-09-16", "2026-09-17"])]
        result = build_review(data, QUERY, NOW, {})
        self.assertEqual({r["id"] for r in result["_details"]["po"]}, {"1", "2"})
        self.assertEqual(result["pipeline"][-1]["count"]["value"], 2)
        self.assertEqual(result["orders"]["missingDate"]["value"], 0)
        current = build_review(data, {"period": "month", "anchor": "2026-09-01"}, NOW, {})
        self.assertEqual(current["orders"]["count"]["value"], 4)
        # Completed prior year ends at Shanghai midnight, not the UTC date.
        prior = build_review(data, {"period": "year", "anchor": "2025-01-01"}, NOW, {})
        self.assertEqual(prior["orders"]["count"]["value"], 1)

    def test_po_status_source_and_missing_dates(self):
        data = fixture()
        data["bookings"] = [booking(name="confirmed"), booking(name="completed", status="Completed"),
                            booking(name="pending", status="Pending"), booking(name="cancelled", status="Cancelled"),
                            booking(name="upsell", source="Upsell"),
                            booking(None, name="legacy"), booking(None, name="legacy-complete", status="Completed"),
                            booking(None, name="rolled-back", status="Pending"),
                            booking(None, name="cancelled-missing", status="Cancelled")]
        result = build_review(data, QUERY, NOW, {})
        self.assertEqual(result["orders"]["count"]["value"], 2)
        self.assertEqual(result["orders"]["missingDate"]["value"], 2)
        self.assertEqual({r["id"] for r in result["_details"]["po_missing_date"]}, {"legacy", "legacy-complete"})
        self.assertTrue(all(r["at"] is None for r in result["_details"]["po_missing_date"]))

    def test_po_backfill_correction_rollback_and_cancel_change_current_total(self):
        data = fixture()
        row = booking(None, creation="2026-09-15")
        data["bookings"] = [row]
        self.assertEqual(build_review(data, QUERY, NOW, {})["orders"]["missingDate"]["value"], 1)
        for day, status, expected, missing in [
            ("2026-01-01", "Confirmed", 1, 0), ("2025-12-31", "Confirmed", 0, 0),
            ("2026-09-13", "Completed", 1, 0), ("2026-09-13", "Cancelled", 0, 0),
            (None, "Pending", 0, 0), ("2026-09-13", "Confirmed", 1, 0)]:
            with self.subTest(day=day, status=status):
                row.update(actual_po_date=day, status=status)
                result = build_review(data, QUERY, NOW, {})
                self.assertEqual(result["orders"]["count"]["value"], expected)
                self.assertEqual(result["orders"]["missingDate"]["value"], missing)

    def test_po_current_opportunity_owner_and_customer_filters_without_history(self):
        data = fixture()
        data["bookings"] = [booking(), booking(None, name="missing")]
        data["opportunities"][0].update(opportunity_owner="alice", sub_region="South China")
        data["history"] = [history("opportunity_owner", "2026-09-15", "bob", "alice")]
        result = build_review(data, {**QUERY, "sales": "alice", "region": "East China", "market": "Frontend"}, NOW, {})
        self.assertEqual(result["orders"]["count"]["value"], 1)
        self.assertEqual(result["sales"][0]["poCount"]["value"], 1)
        self.assertEqual(result["orders"]["missingDate"]["value"], 1)
        for filters in [{"sales": "bob"}, {"region": "South China"}, {"market": "Advanced Packaging"}]:
            filtered = build_review(data, {**QUERY, **filters}, NOW, {})
            self.assertEqual(filtered["orders"]["count"]["value"], 0)
            self.assertEqual(filtered["orders"]["missingDate"]["value"], 0)

    def test_po_old_schema_is_insufficient_not_zero(self):
        data = fixture()
        data["booking_dates_ready"] = False
        data["bookings"] = [booking()]
        result = build_review(data, QUERY, NOW, COVERAGE)
        for value in [result["orders"]["count"], result["orders"]["missingDate"], result["orders"]["missingAmount"],
                      result["orders"]["actual"], result["pipeline"][-1]["count"], result["pipeline"][-1]["amount"],
                      result["sales"][0]["poCount"], result["sales"][0]["orders"]]:
            self.assertEqual(value["state"], "insufficient")
            self.assertIsNone(value["value"])
        self.assertEqual(result["_details"]["po"], [])
        self.assertEqual(result["orders"]["series"], [])

    def test_po_amount_uses_the_cny_order_amount_or_the_entered_cny_amount(self):
        data = fixture()
        data["bookings"] = [booking("2026-02-10", name="cny", amount="1000.50", amount_cny="999999"),
                            booking("2026-03-01", name="usd", currency="USD", amount="700", amount_cny="5000.25"),
                            booking("2026-03-01", name="eur", currency="EUR", amount="300", amount_cny="2000"),
                            booking("2026-09-14", name="after-cutoff", amount="99"),
                            booking(None, name="undated", currency="USD", amount_cny=0),
                            booking("2026-04-01", name="cancelled", status="Cancelled", amount="5"),
                            booking("2026-04-01", name="upsell", source="Upsell", amount="5"),
                            # Foreign orders outside the year's scope never need a CNY amount.
                            booking("2026-09-14", name="after-cutoff-usd", currency="USD", amount="1"),
                            booking("2025-12-31", name="last-year-eur", currency="EUR", amount="1"),
                            booking("2026-04-01", name="pending-usd", status="Pending", currency="USD", amount="1"),
                            booking("2026-04-01", name="cancelled-usd", status="Cancelled", currency="USD", amount="1"),
                            booking("2026-04-01", name="upsell-usd", source="Upsell", currency="USD", amount="1")]
        result = build_review(data, QUERY, NOW, {})
        self.assertEqual(result["orders"]["actual"]["value"], "8000.75")
        self.assertEqual(result["pipeline"][-1]["amount"]["value"], "8000.75")
        self.assertEqual(result["sales"][0]["orders"]["value"], "8000.75")
        self.assertEqual(result["sales"][1]["orders"]["value"], "0.00")
        self.assertEqual(result["orders"]["missingAmount"]["value"], 0)
        self.assertEqual(result["orders"]["series"], [
            {"date": "2026-02-10", "amount": "1000.50", "cumulative": "1000.50", "fraction": 41 / 365},
            {"date": "2026-03-01", "amount": "7000.25", "cumulative": "8000.75", "fraction": 60 / 365}])
        self.assertEqual({(r["amount"], r["currency"]) for r in result["_details"]["po"]},
                         {("1000.50", "CNY"), ("5000.25", "CNY"), ("2000.00", "CNY")})
        self.assertIsNone(result["_details"]["po_missing_date"][0]["amount"])
        self.assertEqual(result["_details"]["po_missing_amount"], [])

    def test_po_amount_missing_cny_is_listed_to_backfill_not_counted_as_zero(self):
        data = fixture()
        data["opportunities"].append({**data["opportunities"][0], "name": "opp-bob", "opportunity_owner": "bob"})
        data["bookings"] = [booking("2026-02-10", name="cny", amount="100"),
                            booking("2026-03-01", name="usd", currency="USD", amount="700", amount_cny=0),
                            booking("2026-03-02", name="eur-old-schema", currency="EUR", amount="300"),
                            booking("2026-03-03", name="zero", amount=0),
                            booking("2026-03-04", name="bob", source_opportunity="opp-bob", amount="9")]
        result = build_review(data, QUERY, NOW, {})
        self.assertEqual(result["orders"]["count"]["value"], 5)
        self.assertEqual(result["orders"]["actual"], {"value": None, "state": "insufficient", "reason": "booking_cny_amount_missing"})
        self.assertEqual(result["pipeline"][-1]["amount"]["state"], "insufficient")
        # Only the rep with a missing amount is unknown; a CNY order is complete as entered, even at 0.
        self.assertEqual(result["sales"][0]["orders"]["state"], "insufficient")
        self.assertEqual(result["sales"][1]["orders"]["value"], "9.00")
        self.assertEqual(result["orders"]["series"], [])
        self.assertEqual(result["orders"]["missingAmount"]["value"], 2)
        self.assertEqual({r["id"] for r in result["_details"]["po_missing_amount"]}, {"usd", "eur-old-schema"})
        self.assertTrue(all(r["amount"] is None and r["at"] for r in result["_details"]["po_missing_amount"]))
        self.assertEqual(next(r["amount"] for r in result["_details"]["po"] if r["id"] == "zero"), "0.00")
        # Backfilling every missing amount makes the year's total known again.
        data["bookings"][1]["amount_cny"] = "50"
        data["bookings"][2]["amount_cny"] = "25.5"
        filled = build_review(data, QUERY, NOW, {})
        self.assertEqual(filled["orders"]["actual"]["value"], "184.50")
        self.assertEqual(filled["orders"]["missingAmount"]["value"], 0)
        self.assertEqual([r["cumulative"] for r in filled["orders"]["series"]], ["100.00", "150.00", "175.50", "175.50", "184.50"])

    def test_po_amount_accepts_database_value_shapes_and_leap_years(self):
        data = fixture()
        data["bookings"] = [booking(date(2026, 2, 10), name="float", currency=None, amount=1000.5),
                            booking("2026-03-01", name="decimal", currency="usd", amount=Decimal("700"), amount_cny=Decimal("5000.25"))]
        result = build_review(data, QUERY, NOW, {})
        self.assertEqual(result["orders"]["actual"]["value"], "6000.75")
        self.assertEqual(result["orders"]["series"][0], {"date": "2026-02-10", "amount": "1000.50", "cumulative": "1000.50", "fraction": 41 / 365})
        json.dumps(result)
        leap = fixture()
        leap["bookings"] = [booking("2028-02-29", name="leap", amount="3")]
        result = build_review(leap, {"period": "month", "anchor": "2028-03-01"}, datetime(2028, 3, 1, 12), {})
        self.assertEqual(result["orders"]["series"], [{"date": "2028-02-29", "amount": "3.00", "cumulative": "3.00", "fraction": 60 / 366}])

    def test_po_amount_follows_the_count_scope_and_the_past_year(self):
        data = fixture()
        data["bookings"] = [booking(amount="10"), booking("2025-06-30", name="last-year", amount="7")]
        for filters, expected in [({}, "10.00"), ({"sales": "alice"}, "10.00"), ({"sales": "bob"}, "0.00"),
                                  ({"region": "South China"}, "0.00"), ({"market": "Frontend"}, "10.00")]:
            with self.subTest(filters=filters):
                result = build_review(data, {**QUERY, **filters}, NOW, {})
                self.assertEqual(result["orders"]["actual"]["value"], expected)
                self.assertEqual(len(result["orders"]["series"]), int(expected != "0.00"))
        prior = build_review(data, {"period": "year", "anchor": "2025-01-01"}, NOW, {})
        self.assertEqual(prior["orders"]["actual"]["value"], "7.00")
        self.assertEqual(prior["orders"]["series"], [{"date": "2025-06-30", "amount": "7.00", "cumulative": "7.00", "fraction": 181 / 365}])

    def test_lost_warning_counts_four_weeks_and_lists_older_unreviewed_losses_as_backlog(self):
        data = fixture()
        data["stages"] = [stage("marked_lost", "2026-09-08", "quotation_sent", "lost"),
                          {**stage("marked_lost", "2026-08-10", "demo_done", "lost"), "name": "old", "opportunity": "old"},
                          {**stage("marked_lost", "2026-08-12", "demo_done", "lost"), "name": "older", "opportunity": "older"},
                          {**stage("marked_lost", "2025-03-01", "demo_done", "lost"), "name": "ancient", "opportunity": "ancient"}]
        for name in ("old", "older", "ancient"):
            data["opportunities"].append({**data["opportunities"][0], "name": name, "title": name})
        data["loss_reviews"] = [{"name": "rv-old", "opportunity": "old", "stage_event": "old", "review_status": "Reviewed",
                                 "review_note": "Report shared", "reviewed_by": "bob", "reviewed_at": "2026-08-20", "modified": "2026-08-20"}]
        result = build_review(data, QUERY, NOW, COVERAGE)
        rows = {r["id"]: r for r in result["_details"]["lost"]}
        # The recent loss has no review row yet (legacy data): pending, inside the window, not overdue.
        self.assertEqual((rows["opp"]["reviewPending"], rows["opp"]["reviewOverdue"], rows["opp"]["review"]), (True, False, None))
        # A loss older than four weeks leaves the zone; while unreviewed it sits in the backlog, uncounted.
        self.assertNotIn("older", rows)
        backlog = {r["id"]: r for r in result["_details"]["lost_backlog"]}
        self.assertEqual((backlog["older"]["reviewPending"], backlog["older"]["reviewOverdue"]), (True, True))
        self.assertNotIn("old", rows)
        self.assertNotIn("old", backlog)
        # Older than the 12-month loss panel and still unreviewed: in the backlog (the backfill made it
        # pending, so the page must reach it), not in the panel.
        self.assertEqual((backlog["ancient"]["reviewPending"], backlog["ancient"]["reviewOverdue"]), (True, True))
        self.assertNotIn("ancient", {r["id"] for r in result["_details"]["losses"]})
        self.assertEqual(next(w["count"]["value"] for w in result["warnings"] if w["key"] == "lost"), 1)
        self.assertEqual((result["losses"]["reviewed"]["value"], result["losses"]["pending"]["value"]), (1, 2))
        reviewed = next(r for r in result["_details"]["losses"] if r["id"] == "old")["review"]
        self.assertEqual((reviewed["status"], reviewed["note"], reviewed["reviewedBy"]), ("reviewed", "Report shared", "bob"))
        # Reviewing the recent loss clears it from the warning but keeps the row in the window.
        data["loss_reviews"].append({"name": "rv-opp", "opportunity": "opp", "stage_event": "marked_lost2026-09-08",
                                     "review_status": "Reviewed", "review_note": "Done", "reviewed_by": "bob",
                                     "reviewed_at": "2026-09-20", "modified": "2026-09-20"})
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(next(w["count"]["value"] for w in result["warnings"] if w["key"] == "lost"), 0)
        self.assertIn("opp", {r["id"] for r in result["_details"]["lost"]})

    def test_pending_loss_older_than_a_year_remains_reviewable_without_changing_annual_metrics(self):
        data = fixture()
        data["opportunities"][0]["creation"] = "2024-01-01"
        old_event = stage("marked_lost", "2025-01-10", "quotation_sent", "lost")
        data["stages"] = [old_event]
        data["loss_reviews"] = [{
            "name": "old-review", "opportunity": "opp", "stage_event": old_event["name"],
            "review_status": "Pending", "modified": "2026-09-01",
        }]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual([row["review"]["id"] for row in result["_details"]["lost_backlog"]], ["old-review"])
        self.assertEqual(result["_details"]["lost"], [])
        self.assertEqual(result["_details"]["losses"], [])
        data["loss_reviews"][0].update({"review_status": "Reviewed", "reviewed_at": "2026-09-08"})
        reviewed = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(reviewed["_details"]["lost_backlog"], [])

    def test_overdue_counts_actions_and_downgrades_carry_their_cny_estimate(self):
        data = fixture()
        base = {"creation": "2026-08-01", "opportunity": "opp", "action_owner": "engineer", "status": "Open", "archived": 0}
        data["actions"] = [{**base, "name": "a1", "title": "Call", "due": "2026-09-01"}, {**base, "name": "a2", "title": "Visit", "due": "2026-09-05"}]
        data["probabilities"] = [{"name": "p1", "opportunity": "opp", "from_level": "committed", "to_level": "upside", "changed_at": "2026-09-08", "reason": "Delay"}]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual([w["key"] for w in result["warnings"]], ["lost", "overdue", "downgrade", "quotation_expiry", "stage6_no_po", "close_date_slip"])
        self.assertEqual(len(result["_details"]["overdue"]), 2)
        self.assertEqual(next(w["count"]["value"] for w in result["warnings"] if w["key"] == "overdue"), 2)
        # The action owner is who has to act; the row owner stays the opportunity owner for the filters.
        self.assertEqual({(r["owner"], r["actionOwner"]) for r in result["_details"]["overdue"]}, {("alice", "engineer")})
        row = result["_details"]["downgrade"][0]
        self.assertEqual((row["amount"], row["currency"], row["stage"]), ("200.00", "CNY", "demo_done"))

    def test_overdue_actions_clear_when_done_or_moved_after_the_viewed_period(self):
        data = fixture()
        base = {"creation": "2026-08-01", "opportunity": "opp", "action_owner": "alice", "archived": 0}
        # Current rows: a1 done on Monday, a2 moved to after the week, a3 still open and overdue.
        data["actions"] = [{**base, "name": "a1", "title": "Call", "due": "2026-09-01", "status": "Done"},
                           {**base, "name": "a2", "title": "Visit", "due": "2026-09-20", "status": "Open"},
                           {**base, "name": "a3", "title": "Quote", "due": "2026-09-02", "status": "Open"}]
        # a4 is open and overdue on a deal that was open that week but has received its PO since: cleared.
        data["opportunities"].append({**data["opportunities"][0], "name": "won", "stage": "po_received"})
        data["stages"] = [{**stage("stage_changed", "2026-09-15", "demo_done", "po_received"), "opportunity": "won", "name": "won-po"}]
        data["actions"].append({**base, "name": "a4", "opportunity": "won", "title": "Invoice", "due": "2026-09-02", "status": "Open"})
        snapshot = lambda name, title, due: json.dumps({"id": name, "title": title, "owner": "alice", "due": due, "status": "Open", "archived": False})
        data["history"] = [{"name": "h1", "opportunity": "opp", "field": "actionUpdated", "at": "2026-09-14 09:00:00", "from_value": snapshot("a1", "Call", "2026-09-01"), "to_value": "{}"},
                           {"name": "h2", "opportunity": "opp", "field": "actionUpdated", "at": "2026-09-14 10:00:00", "from_value": snapshot("a2", "Visit", "2026-09-03"), "to_value": "{}"}]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual([r["actionId"] for r in result["_details"]["overdue"]], ["a3"])
        self.assertEqual(next(w["count"]["value"] for w in result["warnings"] if w["key"] == "overdue"), 1)

    def test_equipment_filter_follows_the_opportunity_and_reports_unlinked_activity(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "Inspection"
        data["opportunities"].append({**data["opportunities"][0], "name": "opp2", "title": "Metrology deal", "tool_type": "Metrology"})
        data["visits"] = [{"name": v, "account": "c", "opportunity": o, "visit_owner": "alice", "subject": v, "visit_date": "2026-09-08", "status": "Visited"}
                          for v, o in (("v-insp", "opp"), ("v-metro", "opp2"), ("v-none", None))]
        data["actions"] = [{"name": a, "creation": "2026-08-01", "opportunity": o, "title": a, "action_owner": "alice", "due": "2026-09-01", "status": "Open", "archived": 0}
                           for a, o in (("a-insp", "opp"), ("a-metro", "opp2"))]
        data["stages"] = [{**stage("marked_lost", "2026-09-08", "quotation_sent", "lost"), "opportunity": "opp2", "name": "lost-metro"}]
        data["probabilities"] = [{"name": "p-insp", "opportunity": "opp", "from_level": "committed", "to_level": "upside", "changed_at": "2026-09-08", "reason": "Delay"}]
        everything = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(len(everything["_details"]["visits"]), 3)
        self.assertIsNone(next(a for a in everything["activities"] if a["key"] == "visits")["unclassified"])
        insp = build_review(data, {**QUERY, "equipment": "Inspection"}, NOW, COVERAGE)
        self.assertEqual([r["id"] for r in insp["_details"]["visits"]], ["v-insp"])
        # The visit with no opportunity cannot be classified: left out and reported, not counted as Inspection.
        self.assertEqual(next(a for a in insp["activities"] if a["key"] == "visits")["unclassified"], 1)
        self.assertEqual({r["actionId"] for r in insp["_details"]["overdue"]}, {"a-insp"})
        self.assertEqual(insp["_details"]["lost"], [])
        self.assertEqual(len(insp["_details"]["downgrade"]), 1)
        self.assertEqual({r["id"] for r in insp["_details"]["demo_done"]}, {"opp"})
        metro = build_review(data, {**QUERY, "equipment": "Metrology"}, NOW, COVERAGE)
        self.assertEqual([r["id"] for r in metro["_details"]["lost"]], ["opp2"])
        self.assertEqual(metro["_details"]["downgrade"], [])
        self.assertEqual(next(w["count"]["value"] for w in metro["warnings"] if w["key"] == "overdue"), 1)

    def test_equipment_filter_matches_stored_spellings_and_moved_opportunities(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "KIBO "
        data["visits"] = [{"name": v, "account": "c", "opportunity": o, "visit_owner": "alice", "subject": v, "visit_date": "2026-09-08", "status": "Visited"}
                          for v, o in (("v-own", "opp"), ("v-moved", "opp-moved"))]
        # opp-moved is now at a customer outside the loaded scope; the visit keeps its own customer.
        data["equipment_opportunities"] = [{"name": "opp-moved", "tool_type": "Kibo"}]
        kibo = build_review(data, {**QUERY, "equipment": "Kibo"}, NOW, COVERAGE)
        self.assertEqual({r["id"] for r in kibo["_details"]["visits"]}, {"v-own", "v-moved"})
        self.assertEqual(next(a for a in kibo["activities"] if a["key"] == "visits")["unclassified"], 0)
        self.assertEqual({r["id"] for r in kibo["_details"]["demo_done"]}, {"opp"})
        self.assertEqual(build_review(data, {**QUERY, "equipment": "Nansi"}, NOW, COVERAGE)["_details"]["visits"], [])

    def test_equipment_filter_keeps_a_quote_with_a_missing_opportunity_insufficient(self):
        data = fixture()
        data["quotes"] = [{"name": "quote", "account": "c", "quotation_owner": "alice", "status": "Published", "opportunity": "gone", "current_published_version": "qv"}]
        data["quotation_opportunities"] = []
        for query in (QUERY, {**QUERY, "equipment": "Kibo"}):
            count = next(w["count"] for w in build_review(data, query, NOW, COVERAGE)["warnings"] if w["key"] == "quotation_expiry")
            self.assertEqual(count["state"], "insufficient")

    def test_equipment_filter_applies_to_leads_tests_quotes_and_orders(self):
        data = fixture()
        data["opportunities"][0]["tool_type"] = "Kibo"
        data["opportunities"].append({**data["opportunities"][0], "name": "opp2", "tool_type": "Nansi"})
        data["leads"] = [{"name": n, "custom_crm_converted_at": "2026-09-08", "custom_crm_converted_account": "c", "custom_crm_converted_opportunity": o}
                         for n, o in (("lead1", "opp"), ("lead2", "opp2"))]
        data["requests"] = [{"name": r, "account": "c", "sales_owner": "alice", "opportunity": o} for r, o in (("rq1", "opp"), ("rq2", "opp2"))]
        data["evaluations"] = [{"name": e, "account": "c", "demo_request": r} for e, r in (("ev1", "rq1"), ("ev2", "rq2"))]
        data["tests"] = [{"name": t, "evaluation": e, "run_date": "2026-09-09", "status": "Completed"} for t, e in (("run1", "ev1"), ("run2", "ev2"))]
        # q3's opportunity is at another customer: only quotation_opportunities knows its equipment.
        data["quotes"] = [{"name": q, "account": "c", "quotation_owner": "alice", "status": "Published", "opportunity": o}
                          for q, o in (("q1", "opp"), ("q2", "opp2"), ("q3", "opp-elsewhere"))]
        data["quotation_opportunities"] = [{"name": "opp-elsewhere", "stage": "quotation_sent", "tool_type": "KIBO"}]
        data["versions"] = [{"quotation": q, "version_no": 1, "published_at": "2026-09-09", "account": "c", "quotation_owner": "alice", "status": "Published"}
                            for q in ("q1", "q2", "q3")]
        data["bookings"] = [booking(), booking(name="b2", source_opportunity="opp2")]
        everything = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual({a["key"]: a["actual"]["value"] for a in everything["activities"]}, {"visits": 0, "leads": 2, "tests": 2, "quotes": 3, "followups": 0})
        self.assertEqual(everything["orders"]["count"]["value"], 2)
        kibo = build_review(data, {**QUERY, "equipment": "Kibo"}, NOW, COVERAGE)
        self.assertEqual({a["key"]: a["actual"]["value"] for a in kibo["activities"]}, {"visits": 0, "leads": 1, "tests": 1, "quotes": 2, "followups": 0})
        self.assertEqual({r["id"] for r in kibo["_details"]["quotes"]}, {"q1", "q3"})
        self.assertEqual({r["id"] for r in kibo["_details"]["tests"]}, {"run1"})
        self.assertEqual(kibo["orders"]["count"]["value"], 1)
        # Data gaps on the Nansi deal do not make the Kibo counts unknown; unfiltered they do.
        data["leads"].append({"name": "lead3", "custom_crm_status": "Converted", "custom_crm_converted_account": "c", "custom_crm_converted_opportunity": "opp2"})
        data["quotes"].append({"name": "q4", "account": "c", "quotation_owner": "alice", "status": "Sent", "opportunity": "opp2"})
        states = lambda query: {a["key"]: a["actual"]["state"] for a in build_review(data, {**QUERY, "sales": "alice", **query}, NOW, COVERAGE)["activities"]}
        self.assertEqual((states({})["leads"], states({})["quotes"]), ("insufficient", "insufficient"))
        self.assertEqual((states({"equipment": "Kibo"})["leads"], states({"equipment": "Kibo"})["quotes"]), ("ready", "ready"))

    def test_quotation_expiry_matches_equipment_by_type(self):
        data = fixture()
        data["quotes"] = [{"name": "q-exp", "account": "c", "quotation_owner": "alice", "status": "Published", "opportunity": "opp-elsewhere", "current_published_version": "v-exp"}]
        data["versions"] = [{"name": "v-exp", "quotation": "q-exp", "version_no": 1, "published_at": "2026-09-01", "account": "c", "quotation_owner": "alice",
                             "status": "Published", "valid_until": "2026-09-20"}]
        data["quotation_opportunities"] = [{"name": "opp-elsewhere", "stage": "quotation_sent", "tool_type": "KIBO"}]
        self.assertEqual([r["id"] for r in quotation_expiry(data, {"equipment": "Kibo"}, NOW, 14, NOW)["items"]], ["q-exp"])
        self.assertEqual(quotation_expiry(data, {"equipment": "Nansi"}, NOW, 14, NOW)["items"], [])

    def test_stage6_without_po_flags_deals_in_internal_validation_past_the_threshold(self):
        data = fixture()
        data["opportunities"][0]["stage"] = "internal_validation"
        for name, stage_now in (("opp-new", "internal_validation"), ("opp-old", "internal_validation"), ("opp-moved", "po_received")):
            data["opportunities"].append({**data["opportunities"][0], "name": name, "title": name, "stage": stage_now,
                                          "creation": "2024-06-01" if name == "opp-old" else "2026-01-01"})
        s6 = lambda opp, when: {**stage("stage_changed", when, "quotation_sent", "internal_validation"), "opportunity": opp, "name": f"s6-{opp}"}
        # opp-old has no S6 entry: stage history is complete from 2025-01-01, so it has been in S6 at least since creation.
        data["stages"] = [s6("opp", "2026-08-01"), s6("opp-new", "2026-09-10"), s6("opp-moved", "2026-08-01"),
                          {**stage("stage_changed", "2026-09-15", "internal_validation", "po_received"), "opportunity": "opp-moved", "name": "po-moved"}]
        result = build_review(data, QUERY, NOW, COVERAGE, stage6_no_po_days=30)
        rows = {r["id"]: r for r in result["_details"]["stage6_no_po"]}
        # opp-moved was still in S6 at the end of the viewed week but has its PO now, so it is cleared.
        self.assertEqual(set(rows), {"opp", "opp-old"})
        self.assertEqual((rows["opp"]["daysInStage"], rows["opp"]["daysAtLeast"]), (43, False))
        self.assertTrue(rows["opp"]["enteredAt"].startswith("2026-07-31T16:00:00"))
        self.assertEqual((rows["opp-old"]["enteredAt"], rows["opp-old"]["daysAtLeast"]), (None, True))
        self.assertEqual([r["id"] for r in result["_details"]["stage6_no_po"]], ["opp-old", "opp"])
        self.assertEqual(next(w["count"] for w in result["warnings"] if w["key"] == "stage6_no_po"), {"value": 2, "state": "ready", "reason": None})
        self.assertEqual(result["stage6NoPo"], {"thresholdDays": 30})
        longer = build_review(data, QUERY, NOW, COVERAGE, stage6_no_po_days=60)
        self.assertEqual([r["id"] for r in longer["_details"]["stage6_no_po"]], ["opp-old"])
        # Without stage history coverage the entry of opp-old is unknown: the count is not a clean number.
        current = {"period": "week", "anchor": "2026-09-14"}
        unknown = build_review(data, current, NOW, {k: v for k, v in COVERAGE.items() if k != "stage"})
        self.assertEqual(next(w["count"]["state"] for w in unknown["warnings"] if w["key"] == "stage6_no_po"), "insufficient")

    def test_stage6_action_takes_a_deal_out_of_the_count_until_its_follow_up_day(self):
        data = fixture()
        data["opportunities"][0]["stage"] = "internal_validation"
        data["opportunities"].append({**data["opportunities"][0], "name": "opp-old", "title": "opp-old", "creation": "2024-06-01"})
        data["stages"] = [{**stage("stage_changed", "2026-08-01", "quotation_sent", "internal_validation"), "opportunity": "opp", "name": "s6-opp"}]
        acted = lambda when: {"id": "h", "actionTaken": "Asked purchasing", "actedAt": "2026-09-15T02:00:00Z", "followUpOn": when, "nextStep": "Chase"}
        for follow_up, handled in (("2026-09-17", True), ("2026-09-16", False), (None, False)):
            with self.subTest(follow_up=follow_up):
                # The entry event names the warning; an entry before the history is one warning too.
                data["warning_handlings"] = {handling_key("stage6_no_po", "opp", "s6-opp"): acted(follow_up),
                                             handling_key("stage6_no_po", "opp-old", BEFORE_HISTORY): {"id": "p", "nextStep": "Plan only"}}
                result = build_review(data, QUERY, NOW, COVERAGE, stage6_no_po_days=30)
                open_rows = {r["id"]: r["handling"] for r in result["_details"]["stage6_no_po"]}
                handled_rows = {r["id"]: r["handling"] for r in result["_details"]["stage6_no_po_handled"]}
                # A next step alone never clears; an action clears only before its follow-up day (today is 2026-09-16).
                self.assertEqual((set(open_rows), set(handled_rows)), ({"opp-old"}, {"opp"}) if handled else ({"opp", "opp-old"}, set()))
                self.assertEqual((open_rows["opp-old"]["sourceEvent"], open_rows["opp-old"]["nextStep"], open_rows["opp-old"]["state"]),
                                 (BEFORE_HISTORY, "Plan only", "open"))
                self.assertEqual(next(w["count"]["value"] for w in result["warnings"] if w["key"] == "stage6_no_po"), 1 if handled else 2)
        # Without a record the row still carries what the page needs to start one.
        del data["warning_handlings"]
        blank = build_review(data, QUERY, NOW, COVERAGE, stage6_no_po_days=30)["_details"]["stage6_no_po"][0]["handling"]
        self.assertEqual((blank["id"], blank["warningType"], blank["history"], blank["state"]), (None, "stage6_no_po", [], "open"))

    def test_stage6_without_po_edges_latest_entry_threshold_day_and_minimums(self):
        data = fixture()
        data["opportunities"][0]["stage"] = "internal_validation"
        for name in ("back", "exact", "after", "migrated", "recent-min", "no-entry"):
            data["opportunities"].append({**data["opportunities"][0], "name": name, "title": name})
        move = lambda opp, when, before, after, **extra: {**stage("stage_changed", when, before, after), "opportunity": opp, "name": f"{opp}-{when}-{after}", **extra}
        data["stages"] = [
            # S6, back to S5, then S6 again: days count from the latest entry.
            move("back", "2026-07-01", "quotation_sent", "internal_validation"), move("back", "2026-07-10", "internal_validation", "quotation_sent"),
            move("back", "2026-08-20", "quotation_sent", "internal_validation"),
            move("exact", "2026-08-14", "quotation_sent", "internal_validation"),
            # Left and re-entered S6 after the viewed week: the entry at or before its end counts.
            move("after", "2026-08-01", "quotation_sent", "internal_validation"), move("after", "2026-09-14", "internal_validation", "quotation_sent"),
            move("after", "2026-09-15", "quotation_sent", "internal_validation"),
            move("migrated", "2026-07-01", "quotation_sent", "internal_validation", source="migration"),
            move("recent-min", "2026-09-01", "quotation_sent", "internal_validation", reached_at_basis="upper_bound"),
        ]
        data["stages"].append(move("opp", "2026-08-01", "quotation_sent", "internal_validation"))
        # "no-entry" was created after the history start, so a missing entry means the history is inconsistent.
        result = build_review(data, QUERY, NOW, COVERAGE, stage6_no_po_days=30)
        rows = {r["id"]: r for r in result["_details"]["stage6_no_po"]}
        self.assertEqual({k: (r["daysInStage"], r["daysAtLeast"]) for k, r in rows.items()},
                         {"opp": (43, False), "exact": (30, False), "after": (43, False), "migrated": (74, True)})
        self.assertEqual((rows["opp"]["at"], rows["migrated"]["at"]), (rows["opp"]["enteredAt"], None))
        # A minimum under the threshold and an entry that cannot be placed leave the count unknown, not 0.
        count = next(w["count"] for w in result["warnings"] if w["key"] == "stage6_no_po")
        self.assertEqual(count["state"], "insufficient")
        self.assertEqual([r["id"] for r in build_review(data, QUERY, NOW, COVERAGE, stage6_no_po_days=20)["_details"]["stage6_no_po"] if r["id"] == "back"], ["back"])
        # Without those two the count is a clean number again; an unknown stage on a deal no longer in S6 does not matter.
        data["opportunities"] = [o for o in data["opportunities"] if o["name"] not in ("recent-min", "no-entry")]
        data["opportunities"].append({**data["opportunities"][0], "name": "elsewhere", "stage": "demo_done"})
        data["stages"].append({**move("elsewhere", "2026-09-10", "qualified_opportunity", "demo_done"), "source": "migration", "recorded_at": "2026-09-15"})
        count = next(w["count"] for w in build_review(data, QUERY, NOW, COVERAGE, stage6_no_po_days=30)["warnings"] if w["key"] == "stage6_no_po")
        self.assertEqual(count, {"value": 4, "state": "ready", "reason": None})

    def test_stage6_without_po_each_unknown_leaves_the_count_insufficient(self):
        def s6_count(data, query=QUERY, coverage=COVERAGE, days=30):
            return next(w["count"] for w in build_review(data, query, NOW, coverage, stage6_no_po_days=days)["warnings"] if w["key"] == "stage6_no_po")
        entry = lambda when, **extra: {**stage("stage_changed", when, "quotation_sent", "internal_validation"), "name": "s6-" + when, **extra}
        data = fixture()
        data["opportunities"][0]["stage"] = "internal_validation"
        data["stages"] = [entry("2026-08-01")]
        self.assertEqual(s6_count(data)["value"], 1)
        # A deal still in S6 whose stage at the cutoff is unknown (a migration recorded after it).
        data["stages"] = [entry("2026-08-01", source="migration", recorded_at="2026-09-15")]
        self.assertEqual(s6_count(data)["state"], "insufficient")
        # A minimum under the threshold on its own.
        data["stages"] = [entry("2026-09-01", reached_at_basis="upper_bound")]
        self.assertEqual(s6_count(data)["state"], "insufficient")
        self.assertEqual(s6_count(data, days=10), {"value": 1, "state": "ready", "reason": None})
        # A sales filter on a past period needs the owner history too.
        data["stages"] = [entry("2026-08-01")]
        self.assertEqual(s6_count(data, {**QUERY, "sales": "alice"})["value"], 1)
        self.assertEqual(s6_count(data, {**QUERY, "sales": "alice"}, {k: v for k, v in COVERAGE.items() if k != "fields"})["state"], "insufficient")
        # An entry older than the complete history only proves the deal was in S6 from the history start.
        late_history = {**COVERAGE, "stage": "2026-09-01"}
        self.assertEqual(s6_count(data, coverage=late_history)["state"], "insufficient")
        rows = build_review(data, QUERY, NOW, late_history, stage6_no_po_days=10)["_details"]["stage6_no_po"]
        self.assertEqual([(r["daysInStage"], r["daysAtLeast"], r["enteredAt"]) for r in rows], [(12, True, None)])
        # No usable stage coverage (missing, after the cutoff, unreadable): an exact entry past the threshold may
        # have been followed by unrecorded ones, so the count is unknown, in the current week as well.
        current = {"period": "week", "anchor": "2026-09-14"}
        for broken in ({k: v for k, v in COVERAGE.items() if k != "stage"}, {**COVERAGE, "stage": "2026-12-01"}, {**COVERAGE, "stage": "not a date"}):
            self.assertEqual(s6_count(data, current, broken)["state"], "insufficient")
            self.assertEqual(build_review(data, current, NOW, broken)["_details"]["stage6_no_po"], [])
            self.assertEqual(s6_count(data, coverage=broken)["state"], "insufficient")
            # An exact entry under the threshold is not overdue, with or without the history.
            self.assertEqual(s6_count(data, current, broken, days=60), {"value": 0, "state": "ready", "reason": None})
            # An entry that is only an upper bound, even far past the threshold, needs the history as well.
            data["stages"] = [entry("2026-08-01", reached_at_basis="upper_bound")]
            self.assertEqual(s6_count(data, current, broken)["state"], "insufficient")
            data["stages"] = [entry("2026-08-01")]
        # An exact entry before the history start whose own stay is under the threshold is not overdue either;
        # past it, only the history start is certain (3 days to the cutoff), so a 5-day threshold stays unknown.
        data["stages"] = [entry("2026-09-05")]
        self.assertEqual(s6_count(data, coverage={**COVERAGE, "stage": "2026-09-10"}), {"value": 0, "state": "ready", "reason": None})
        self.assertEqual(s6_count(data, coverage={**COVERAGE, "stage": "2026-09-10"}, days=5)["state"], "insufficient")
        self.assertEqual(s6_count(data, coverage={**COVERAGE, "stage": "2026-09-10"}, days=3), {"value": 1, "state": "ready", "reason": None})

    def test_reopened_losses_need_no_post_mortem_but_stay_on_record(self):
        data = fixture()
        data["stages"] = [stage("marked_lost", "2026-09-08", "quotation_sent", "lost"),
                          stage("reopened", "2026-09-10", "lost", "demo_done")]
        result = build_review(data, QUERY, NOW, COVERAGE)
        row = result["_details"]["lost"][0]
        self.assertEqual((row["reviewPending"], row["reopenedAt"]), (False, "2026-09-09T16:00:00Z"))
        self.assertEqual(next(w["count"]["value"] for w in result["warnings"] if w["key"] == "lost"), 0)
        self.assertEqual(len(result["_details"]["losses"]), 1)
        # Lost, reopened and lost again is two losses in the 12-month panel.
        again = fixture()
        again["stages"] = [stage("marked_lost", "2026-09-08", "quotation_sent", "lost"), stage("reopened", "2026-09-09", "lost", "demo_done"),
                           stage("marked_lost", "2026-09-10", "demo_done", "lost")]
        twice = build_review(again, QUERY, NOW, COVERAGE)
        self.assertEqual((twice["losses"]["count"]["value"], twice["losses"]["pending"]["value"]), (2, 1))
        self.assertEqual(next(w["count"]["value"] for w in twice["warnings"] if w["key"] == "lost"), 1)
        # Reopened after the viewed period ended: still no post-mortem owed in that completed week.
        data["stages"][1] = stage("reopened", "2026-09-15", "lost", "demo_done")
        later = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual((later["_details"]["lost"][0]["reviewPending"], later["_details"]["lost"][0]["reopenedAt"]), (False, "2026-09-14T16:00:00Z"))
        self.assertEqual(next(w["count"]["value"] for w in later["warnings"] if w["key"] == "lost"), 0)

    def test_loss_estimate_replays_cny_amount_after_reopening(self):
        data = fixture()
        data["stages"] = [stage("marked_lost", "2026-09-08", "quotation_sent", "lost"),
                          stage("rollback", "2026-09-10", "lost", "demo_done")]
        data["history"] = [history("amount_cny", "2026-09-10", "695.00", "200.00"),
                           history("currency", "2026-09-10", "USD", "CNY")]
        result = build_review(data, QUERY, NOW, COVERAGE)
        for row in [result["losses"]["items"][0], result["_details"]["lost"][0], result["_details"]["losses"][0]]:
            self.assertEqual((row["amount"], row["currency"]), ("695.00", "CNY"))
        unknown = build_review(data, QUERY, NOW, {**COVERAGE, "fields": "2026-09-09"})
        row = unknown["losses"]["items"][0]
        self.assertIsNone(row["amount"])
        self.assertEqual(row["currency"], "CNY")

    def test_downgrade_remains_after_upgrade_and_empty_is_not_a_rank(self):
        data = fixture()
        data["probabilities"] = [{"name": day, "opportunity": "opp", "from_level": a, "to_level": b, "changed_at": day, "reason": "Budget changed"} for a, b, day in (
            ("", "pipeline", "2026-09-07"), ("committed", "upside", "2026-09-08"), ("upside", "committed", "2026-09-09"), ("upside", "", "2026-09-10"))]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["warnings"][2]["count"]["value"], 1)
        self.assertEqual(len(result["_details"]["downgrade"]), 1)
        self.assertEqual(result["_details"]["downgrade"][0]["reason"], "Budget changed")

    def test_actions_replay_soft_delete_and_ignore_noop_for_stall(self):
        data = fixture()
        action = {"id": "act", "title": "Follow up", "owner": "alice", "due": "2026-09-01", "status": "Open"}
        data["actions"] = [{"name": "act", "creation": "2026-08-01", "opportunity": "opp", "title": "Follow up", "action_owner": "alice", "due": "2026-09-01", "status": "Open", "archived": 1}]
        data["history"] = [history("actionCreated", "2026-08-01", "", action),
                           history("actionUpdated", "2026-09-12", action, action), history("actionDeleted", "2026-09-15", "", "act")]
        result = build_review(data, QUERY, NOW, COVERAGE)
        # Deleted after the week: it was overdue then, but a deleted action no longer warns (current state).
        self.assertEqual(result["warnings"][1]["count"]["value"], 0)
        self.assertEqual(result["stalled"]["items"][0]["days"], 43)
        self.assertEqual(result["stalled"]["items"][0]["severity"], "high")
        current = build_review(data, {"period": "week", "anchor": "2026-09-14"}, NOW, COVERAGE)
        self.assertEqual(current["warnings"][1]["count"]["value"], 0)
        self.assertEqual(current["stalled"]["items"][0]["days"], 46)

    def test_due_today_is_not_overdue_and_completion_clears_it(self):
        data = fixture()
        data["actions"] = [{"name": "act", "creation": "2026-08-01", "opportunity": "opp", "title": "Follow up", "action_owner": "alice", "due": "2026-09-13", "status": "Open", "archived": 0}]
        self.assertEqual(build_review(data, QUERY, NOW, COVERAGE)["warnings"][1]["count"]["value"], 0)
        data["actions"][0].update(due="2026-09-01", status="Done")
        self.assertEqual(build_review(data, QUERY, NOW, COVERAGE)["warnings"][1]["count"]["value"], 0)

    def test_activity_anchors_dedup_and_test_owner(self):
        data = fixture()
        data["visits"] = [{"name": f"v{i}", "account": "c", "visit_owner": "alice", "visit_date": "2026-09-08", "status": status} for i, status in enumerate(["Planned", "Visited", "Minutes Submitted", "Manager Reviewed"])]
        data["leads"] = [{"name": "lead", "custom_crm_converted_at": "2026-09-08", "custom_crm_converted_account": "c", "custom_crm_converted_opportunity": "opp"}]
        data["stages"] = [stage("lead_converted", "2026-09-08", reference_doctype="Lead", reference_name="lead")]
        data["evaluations"] = [{"name": "evaluation", "account": "c", "demo_request": "request", "evaluation_owner": "engineer"}]
        data["requests"] = [{"name": "request", "account": "c", "sales_owner": "alice"}]
        data["tests"] = [{"name": "run", "evaluation": "evaluation", "run_date": "2026-09-09", "status": "Completed"}]
        data["quotes"] = [{"name": "quote", "account": "c", "quotation_owner": "alice", "status": "Published"}]
        data["versions"] = [{"quotation": "quote", "version_no": i, "published_at": day, "account": "c", "quotation_owner": "alice", "status": status} for i, day, status in [(1, "2026-09-08", "Superseded"), (2, "2026-09-09", "Published")]]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual([r["actual"]["value"] for r in result["activities"]], [3, 1, 1, 1, 0])
        self.assertEqual(result["_details"]["tests"][0]["owner"], "alice")
        data["leads"][0]["custom_crm_converted_at"] = None
        self.assertEqual(build_review(data, QUERY, NOW, COVERAGE)["activities"][1]["actual"]["value"], 1)
        data["versions"][0]["published_at"] = "2026-09-01"
        self.assertEqual(build_review(data, QUERY, NOW, COVERAGE)["activities"][3]["actual"]["value"], 0)

    def test_region_uses_customer_not_opportunity(self):
        data = fixture(); data["opportunities"][0]["sub_region"] = "South China"
        self.assertEqual(build_review(data, {**QUERY, "region": "East China"}, NOW, COVERAGE)["pipeline"][1]["count"]["value"], 1)
        self.assertEqual(build_review(data, {**QUERY, "region": "South China"}, NOW, COVERAGE)["pipeline"][1]["count"]["value"], 0)

    def test_a_territory_spelled_out_as_regions_selects_every_region_it_covers(self):
        # cockpit.scoped() spells a territory out as the regions it covers; without that list the name stands alone.
        data = fixture()
        china = {**QUERY, "region": "China", "regions": {"China", "East China", "South China"}}
        count = lambda query: build_review(data, query, NOW, COVERAGE)["pipeline"][1]["count"]["value"]
        self.assertEqual(count(china), 1)
        self.assertEqual(count({**china, "regions": {"China", "South China"}}), 0)
        self.assertEqual(count({**QUERY, "region": "China"}), 0)
        data["quotes"] = [{"name": "q-exp", "account": "c", "quotation_owner": "alice", "status": "Published", "opportunity": "opp", "current_published_version": "v-exp"}]
        data["versions"] = [{"name": "v-exp", "quotation": "q-exp", "version_no": 1, "published_at": "2026-09-01", "account": "c", "quotation_owner": "alice",
                             "status": "Published", "valid_until": "2026-09-20"}]
        expiring = lambda query: [r["id"] for r in quotation_expiry(data, query, NOW, 14, NOW)["items"]]
        self.assertEqual(expiring(china), ["q-exp"])
        self.assertEqual(expiring({**china, "regions": {"China", "South China"}}), [])

    def test_po_uses_actual_date_year_and_stall_requires_lookback_coverage(self):
        data = fixture()
        data["stages"] = [stage("po_confirmed", "2025-12-31", recorded_at="2026-01-02")]
        data["bookings"] = [booking("2025-12-31")]
        result = build_review(data, QUERY, NOW, {**COVERAGE, "actions": "2026-09-10"})
        self.assertEqual(result["orders"]["count"]["value"], 0)
        self.assertEqual(result["stalled"]["count"]["state"], "insufficient")
        self.assertEqual(result["stalled"]["items"], [])

    def test_backdated_migration_is_not_evidence_of_period_end_state(self):
        data = fixture()
        data["stages"] = [stage("migration", "2026-01-01", recorded_at="2026-09-15", source="migration", reached_at_basis="upper_bound")]
        result = build_review(data, QUERY, NOW, COVERAGE)
        self.assertEqual(result["pipeline"][1]["count"]["state"], "insufficient")


if __name__ == "__main__":
    unittest.main()
