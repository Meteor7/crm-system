"""#18 period and scope edges: plain unittest, no live site.

Weeks are ISO weeks (Monday to Sunday) in Asia/Shanghai; months, quarters and years are calendar
periods; a current period is compared with the same elapsed share of the previous one. Every card
number must equal the rows its drill-down lists.
"""
import unittest
from datetime import date, datetime

from rayher_crm.services.cockpit_metrics import build_review, period
from rayher_crm.tests.test_cockpit_metrics import COVERAGE, fixture, stage


def visit(name, day, owner="alice"):
    return {"name": name, "account": "c", "visit_owner": owner, "visit_date": day, "status": "Visited", "opportunity": "opp"}


def count(result, key):
    return next(a["actual"] for a in result["activities"] if a["key"] == key)


class TestCockpitBoundaries(unittest.TestCase):
    def test_a_week_across_the_new_year_is_one_iso_week(self):
        now = datetime(2027, 1, 2, 12)
        for anchor in ("2026-12-28", "2026-12-31", "2027-01-03"):
            with self.subTest(anchor=anchor):
                week = period({"period": "week", "anchor": anchor}, now)
                self.assertEqual((week["start"], week["end"]), (datetime(2026, 12, 28), datetime(2027, 1, 4)))
                self.assertEqual(week["start"].isocalendar()[:2], (2026, 53))
                # Five and a half days into the week, compared with the same span of the week before.
                self.assertEqual((week["previous_start"], week["previous_end"], week["as_of"]),
                                 (datetime(2026, 12, 21), datetime(2026, 12, 26, 12), now))
        data = fixture()
        data["visits"] = [visit("dec", "2026-12-31"), visit("jan", "2027-01-02"), visit("next", "2027-01-04"), visit("prior", "2026-12-24")]
        result = build_review(data, {"period": "week", "anchor": "2027-01-01"}, datetime(2027, 1, 10, 12), COVERAGE)
        self.assertEqual(sorted(r["id"] for r in result["_details"]["visits"]), ["dec", "jan"])
        visits = next(a for a in result["activities"] if a["key"] == "visits")
        self.assertEqual((visits["actual"]["value"], visits["previous"]["value"]), (2, 1))

    def test_month_ends_and_leap_february_never_compare_past_the_previous_month(self):
        march = period({"period": "month", "anchor": "2027-03-31"}, datetime(2027, 3, 31, 12))
        self.assertEqual((march["start"], march["end"]), (datetime(2027, 3, 1), datetime(2027, 4, 1)))
        # 30.5 days into March is more than all of February: the comparison stops at February's end.
        self.assertEqual((march["previous_start"], march["previous_end"]), (datetime(2027, 2, 1), datetime(2027, 3, 1)))
        leap = period({"period": "month", "anchor": "2028-02-29"}, datetime(2028, 3, 5))
        self.assertEqual((leap["start"], leap["end"], leap["historical"]), (datetime(2028, 2, 1), datetime(2028, 3, 1), True))
        self.assertEqual(leap["as_of"], datetime(2028, 2, 29, 23, 59, 59, 999999))
        data = fixture()
        data["visits"] = [visit("feb-end", "2028-02-29"), visit("mar-first", "2028-03-01"), visit("jan-end", "2028-01-31")]
        result = build_review(data, {"period": "month", "anchor": "2028-02-10"}, datetime(2028, 3, 5), COVERAGE)
        visits = next(a for a in result["activities"] if a["key"] == "visits")
        self.assertEqual([r["id"] for r in result["_details"]["visits"]], ["feb-end"])
        self.assertEqual((visits["actual"]["value"], visits["previous"]["value"]), (1, 1))

    def test_quarter_and_year_ends_are_calendar_periods_read_as_of_their_last_instant(self):
        q4 = period({"period": "quarter", "anchor": "2026-12-31"}, datetime(2027, 1, 5))
        self.assertEqual((q4["start"], q4["end"], q4["previous_start"], q4["previous_end"]),
                         (datetime(2026, 10, 1), datetime(2027, 1, 1), datetime(2026, 7, 1), datetime(2026, 10, 1)))
        self.assertEqual(q4["as_of"], datetime(2026, 12, 31, 23, 59, 59, 999999))
        q1 = period({"period": "quarter", "anchor": "2027-03-31"}, datetime(2027, 4, 1))
        self.assertEqual((q1["start"], q1["end"]), (datetime(2027, 1, 1), datetime(2027, 4, 1)))
        data = fixture()
        data["visits"] = [visit("last", "2026-12-31"), visit("first", "2027-01-01"), visit("q3", "2026-09-30")]
        year = build_review(data, {"period": "year", "anchor": "2026-06-15"}, datetime(2027, 1, 5), COVERAGE)
        self.assertEqual(sorted(r["id"] for r in year["_details"]["visits"]), ["last", "q3"])
        quarter = build_review(data, {"period": "quarter", "anchor": "2026-11-01"}, datetime(2027, 1, 5), COVERAGE)
        self.assertEqual([r["id"] for r in quarter["_details"]["visits"]], ["last"])

    def test_timestamps_fall_on_their_shanghai_day(self):
        data = fixture()
        data["opportunities"][0]["creation"] = "2026-01-01"
        data["quotes"] = [{"name": q, "account": "c", "quotation_owner": "alice", "status": "Sent", "opportunity": "opp"} for q in ("late", "new-year")]
        data["versions"] = [{"name": f"{q}-1", "quotation": q, "version_no": 1, "account": "c", "quotation_owner": "alice", "published_at": at, "status": "Published"}
                            for q, at in (("late", "2026-12-31T15:59:59Z"), ("new-year", "2026-12-31T16:00:00Z"))]
        for anchor, expected in (("2026-06-01", ["late"]), ("2027-01-01", ["new-year"])):
            with self.subTest(anchor=anchor):
                result = build_review(data, {"period": "year", "anchor": anchor}, datetime(2027, 2, 1), COVERAGE)
                self.assertEqual([r["id"] for r in result["_details"]["quotes"]], expected)
        # "Now" given in UTC is read in Shanghai: 16:00Z on 31 December is already the new year there.
        self.assertEqual(period({"period": "year", "anchor": "2027-01-01"}, "2026-12-31T16:00:01Z")["as_of"], datetime(2027, 1, 1, 0, 0, 1))
        with self.assertRaises(ValueError):
            period({"period": "year", "anchor": "2027-01-01"}, "2026-12-31T15:59:59Z")

    def test_an_empty_scope_is_zero_not_insufficient(self):
        now = datetime(2026, 9, 16, 12)
        data = fixture()
        data["visits"] = [visit("v", "2026-09-15")]
        for label, query in (("no customers", {}), ("unmatched region", {"region": "North China"}), ("unmatched market", {"market": "Backend"})):
            with self.subTest(label):
                scoped = {**data, "customers": []} if label == "no customers" else data
                result = build_review(scoped, {"period": "week", "anchor": "2026-09-14", **query}, now, COVERAGE)
                self.assertEqual({a["key"]: a["actual"] for a in result["activities"]},
                                 {k: {"value": 0, "state": "ready", "reason": None} for k in ("visits", "leads", "tests", "quotes")})
                self.assertEqual({w["key"]: (w["count"]["value"], w["count"]["state"]) for w in result["warnings"]},
                                 {k: (0, "ready") for k in ("lost", "overdue", "downgrade", "quotation_expiry", "stage6_no_po", "close_date_slip")})
                self.assertTrue(all((p["count"]["value"], p["count"]["state"]) == (0, "ready") for p in result["pipeline"]))

    def test_every_card_number_equals_its_drill_down_rows(self):
        now = datetime(2026, 9, 16, 12)
        data = fixture()
        base = data["opportunities"][0]
        data["opportunities"] += [{**base, "name": "opp2", "stage": "quotation_sent", "amount_cny": "300.00", "amount": "300.00"},
                                  {**base, "name": "opp3", "stage": "internal_validation"},
                                  {**base, "name": "opp4", "stage": "lost", "lost_at": "2026-09-10"}]
        data["stages"] = [{**stage("internal_validation_approved", "2026-08-01", "quotation_sent", "internal_validation"), "opportunity": "opp3"},
                          {**stage("marked_lost", "2026-09-10", "quotation_sent", "lost"), "opportunity": "opp4"}]
        data["actions"] = [{"name": f"a{i}", "creation": "2026-01-01", "opportunity": "opp2", "title": "Call", "action_owner": "alice",
                            "due": due, "status": "Open", "archived": 0} for i, due in enumerate(("2026-09-01", "2026-09-10", "2026-09-30"))]
        data["probabilities"] = [{"name": "p1", "opportunity": "opp", "from_level": "committed", "to_level": "upside", "changed_at": "2026-09-15 10:00:00"},
                                 {"name": "p2", "opportunity": "opp", "from_level": "upside", "to_level": "pipeline", "changed_at": "2026-09-15 11:00:00"}]
        data["visits"] = [visit("v1", "2026-09-14"), visit("v2", "2026-09-15"), visit("old", "2026-09-01")]
        data["bookings"] = [{"name": "b1", "source": "Opportunity", "source_opportunity": "opp", "status": "Confirmed", "actual_po_date": "2026-09-15",
                             "booking_owner": "alice", "currency": "CNY", "amount": "50.00"}]
        for query in ({"period": "week", "anchor": "2026-09-14"}, {"period": "year", "anchor": "2026-01-01"}, {"period": "week", "anchor": "2026-09-14", "sales": "alice"}):
            with self.subTest(query=query):
                result = build_review(data, query, now, COVERAGE, stage6_no_po_days=30)
                details = result["_details"]
                for item in result["activities"]:
                    self.assertEqual(item["actual"]["value"], len(details[item["key"]]), item["key"])
                for item in result["pipeline"]:
                    self.assertEqual(item["count"]["value"], len({r["id"] for r in details[item["key"]]}), item["key"])
                    if item["amount"]["state"] == "ready":
                        self.assertEqual(float(item["amount"]["value"]), sum(float(r["amount"]) for r in details[item["key"]]), item["key"])
                rows = {"lost": {r["id"] for r in details["lost"] if r["reviewPending"]},
                        "overdue": {(r["id"], r["actionId"]) for r in details["overdue"]},
                        "downgrade": {r["id"] for r in details["downgrade"]},
                        "quotation_expiry": {r["id"] for r in details["quotation_expiry"]},
                        "stage6_no_po": {r["id"] for r in details["stage6_no_po"]},
                        "close_date_slip": {r["id"] for r in details["close_date_slip"]}}
                for warning in result["warnings"]:
                    self.assertEqual(warning["count"]["value"], len(rows[warning["key"]]), warning["key"])
                self.assertEqual(result["stalled"]["count"]["value"], len(details["stalled"]))
                self.assertEqual(result["losses"]["count"]["value"], len({r["eventId"] for r in details["losses"]}))
                self.assertEqual(result["orders"]["count"]["value"], len(details["po"]))
                self.assertEqual(float(result["orders"]["actual"]["value"]), sum(float(r["amount"]) for r in details["po"]))
                # The fixture is not empty: the equalities above compare real rows.
                self.assertEqual((len(rows["overdue"]), len(rows["stage6_no_po"]), len(details["po"])), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
