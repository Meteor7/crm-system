"""Run with plain unittest; the board's query rules must not depend on a live site."""
import unittest
from datetime import datetime

from rayher_crm.services.opportunity_board_rules import (
    BoardQueryError, board_rows, build_board, validate_definition, validate_query,
)

# Site time is Shanghai; 2026-09-22 10:00 there is 02:00 UTC.
NOW = datetime(2026, 9, 22, 10, 0)
OPTIONS = {
    "sales": {"alice", "bob"},
    "regions": ["East China", "South China"],
    "markets": ["Frontend", "Advanced Packaging"],
    "equipment": ["Aconca", "Drakens", "Kibo", "Nansi", "Veymont", "Inspection", "Metrology"],
    "regionReady": True,
}


def opportunity(name, **values):
    row = {
        "name": name, "title": f"Title {name}", "account": f"acc-{name}", "customer_name": f"Customer {name}",
        "region": "East China", "market": "Frontend", "opportunity_owner": "alice", "stage": "demo_done",
        "stage_changed_at": datetime(2026, 9, 10, 9, 0), "probability_level": "pipeline", "tool_type": "Inspection",
        "amount": "100.00", "currency": "CNY", "amount_cny": "100.00",
    }
    row.update(values)
    return row


def rows(*opportunities, actions=(), now=NOW):
    return board_rows(list(opportunities), {"alice": "Alice", "bob": "Bob"}, list(actions), now)


def run(board_rows_, **query):
    ordered, summary, groups = build_board(board_rows_, validate_query(query, OPTIONS))
    return [row.dto["id"] for row in ordered], summary, groups


# Regions in a territory tree: World > Asia > China > the two regions; Overseas is a region outside the tree.
REGION_PARENTS = {"Asia": "World", "China": "Asia", "East China": "China", "South China": "China"}
TERRITORY_OPTIONS = {
    **OPTIONS, "regions": ["World", "Asia", "China", "East China", "South China", "Overseas"],
    "regionParents": REGION_PARENTS,
}


def invalid(query, options=OPTIONS):
    with unittest.TestCase().assertRaises(BoardQueryError) as caught:
        validate_query(query, options)
    return caught.exception.field


class TestValidation(unittest.TestCase):
    def test_defaults_mean_no_restriction(self):
        self.assertEqual(validate_query({}, OPTIONS), {
            "scope": {"sales": [], "regions": [], "markets": [], "equipment": []},
            "match": "all", "conditions": [], "sort": {"field": "stageChangedAt", "direction": "asc"}, "groupBy": None,
        })

    def test_unknown_fields_operators_and_values_are_rejected_not_ignored(self):
        cases = [
            ({"filters": []}, "filters"),
            ({"scope": {"owner": ["alice"]}}, "scope.owner"),
            ({"match": "or"}, "match"),
            ({"conditions": [{"field": "forecast", "operator": "in", "value": ["Commit"]}]}, "conditions[0].field"),
            ({"conditions": [{"field": "stage", "operator": "eq", "value": "demo_done"}]}, "conditions[0].operator"),
            ({"conditions": [{"field": "stage", "operator": "in", "value": ["won"]}]}, "conditions[0].value"),
            ({"conditions": [{"field": "stage", "operator": "in", "value": []}]}, "conditions[0].value"),
            ({"conditions": [{"field": "stage", "operator": "in", "value": "demo_done"}]}, "conditions[0].value"),
            ({"conditions": [{"field": "probabilityLevel", "operator": "in", "value": [""]}]}, "conditions[0].value"),
            ({"conditions": [{"field": "sales", "operator": "in", "value": ["mallory"]}]}, "conditions[0].value"),
            ({"conditions": [{"field": "market", "operator": "not_in", "value": ["Memory"]}]}, "conditions[0].value"),
            ({"conditions": [{"field": "stage", "operator": "in", "value": ["lost"], "extra": 1}]}, "conditions[0].extra"),
            ({"conditions": [{"field": "customerName", "operator": "contains", "value": "  "}]}, "conditions[0].value"),
            ({"sort": {"field": "modified"}}, "sort.field"),
            ({"sort": {"field": "stage", "direction": "up"}}, "sort.direction"),
            ({"groupBy": "site"}, "groupBy"),
            ({"scope": {"sales": ["nobody"]}}, "scope.sales"),
            # Equipment comes from the catalog now; a spelling outside it is not silently matched to nothing.
            ({"scope": {"equipment": ["nansi"]}}, "scope.equipment"),
            ({"conditions": [{"field": "equipment", "operator": "in", "value": ["Kibo 4895C"]}]}, "conditions[0].value"),
            ({"conditions": [{"field": "stage", "operator": "in", "value": ["lost"]}] * 21}, "conditions"),
        ]
        for query, field in cases:
            with self.subTest(query=query):
                self.assertEqual(invalid(query), field)

    def test_dates_must_be_real_iso_days_and_ranges_must_be_ordered(self):
        for value in ("2026-7-1", "20260701", "2026-02-30", "2026-07-01T00:00:00", 20260701):
            with self.subTest(value=value):
                self.assertEqual(invalid({"conditions": [{"field": "stageChangedAt", "operator": "after", "value": value}]}),
                                 "conditions[0].value")
        for value in (["2026-07-02", "2026-07-01"], ["2026-07-01"], "2026-07-01"):
            with self.subTest(value=value):
                self.assertEqual(invalid({"conditions": [{"field": "stageChangedAt", "operator": "between", "value": value}]}),
                                 "conditions[0].value")
        self.assertEqual(
            validate_query({"conditions": [{"field": "stageChangedAt", "operator": "between",
                                            "value": ["2026-07-01", "2026-07-01"]}]}, OPTIONS)["conditions"][0]["value"],
            ["2026-07-01", "2026-07-01"],
        )

    def test_amounts_are_exact_decimals_and_ages_are_whole_days(self):
        for value in (1.5, "1.234", "-1", "1e3", "", True, None, ["1", "2"]):
            with self.subTest(value=value):
                self.assertEqual(invalid({"conditions": [{"field": "amountCny", "operator": "gt", "value": value}]}),
                                 "conditions[0].value")
        self.assertEqual(invalid({"conditions": [{"field": "amountCny", "operator": "between", "value": ["9", "1"]}]}),
                         "conditions[0].value")
        parsed = validate_query({"conditions": [{"field": "amountCny", "operator": "gte", "value": "1000"}]}, OPTIONS)
        self.assertEqual(parsed["conditions"][0]["value"], "1000.00")
        for value in (True, 1.0, "21", -1, 36501):
            with self.subTest(value=value):
                self.assertEqual(invalid({"conditions": [{"field": "stageAgeDays", "operator": "gt", "value": value}]}),
                                 "conditions[0].value")

    def test_region_queries_fail_explicitly_until_regions_are_ready(self):
        unready = {**OPTIONS, "regions": [], "regionReady": False}
        self.assertEqual(invalid({"scope": {"regions": ["East China"]}}, unready), "scope.regions")
        self.assertEqual(invalid({"conditions": [{"field": "region", "operator": "in", "value": ["East China"]}]}, unready),
                         "conditions[0].value")
        self.assertEqual(invalid({"groupBy": "region"}, unready), "groupBy")
        # An empty region scope and sorting by region stay allowed.
        validate_query({"scope": {"regions": []}, "sort": {"field": "region", "direction": "desc"}}, unready)
        self.assertEqual(invalid({"scope": {"regions": ["West China"]}}), "scope.regions")

    def test_a_territory_is_a_region_value_like_any_other(self):
        self.assertEqual(
            validate_query({"scope": {"regions": ["China"]}}, TERRITORY_OPTIONS)["scope"]["regions"], ["China"])
        self.assertEqual(invalid({"scope": {"regions": ["Europe"]}}, TERRITORY_OPTIONS), "scope.regions")
        # The definition that is saved keeps the territory, not the regions it covers today.
        definition = validate_definition({
            "columns": ["region"], "conditions": [{"field": "region", "operator": "not_in", "value": ["Asia"]}],
        }, TERRITORY_OPTIONS)
        self.assertEqual(definition["conditions"][0]["value"], ["Asia"])

    def test_saved_definitions_need_known_unique_columns_and_no_paging(self):
        definition = validate_definition({"columns": ["customerName", "stage"], "match": "any"}, OPTIONS)
        self.assertEqual((definition["columns"], definition["match"]), (["customerName", "stage"], "any"))
        for raw, field in (({"columns": []}, "columns"), ({"columns": ["stage", "stage"]}, "columns"),
                           ({"columns": ["site"]}, "columns"), ({}, "columns"),
                           ({"columns": ["stage"], "page": 2}, "page")):
            with self.subTest(raw=raw), self.assertRaises(BoardQueryError) as caught:
                validate_definition(raw, OPTIONS)
            self.assertEqual(caught.exception.field, field)


class TestRows(unittest.TestCase):
    def test_row_contract_and_utc_timestamps(self):
        [row] = rows(opportunity("o1", stage_changed_at=datetime(2026, 7, 1, 0, 30), amount="125000.25",
                                 currency="USD", amount_cny=None, probability_level="", region=" ", tool_type=None),
                     actions=[{"name": "a1", "opportunity": "o1", "title": "Call", "due": "2026-09-30", "status": "Open", "archived": 0}])
        self.assertEqual(row.dto, {
            "id": "o1", "title": "Title o1", "accountId": "acc-o1", "customerName": "Customer o1", "region": None,
            "salesId": "alice", "salesName": "Alice", "stage": "demo_done",
            "stageChangedAt": "2026-06-30T16:30:00Z", "stageAgeDays": 83, "stageUnchangedOver21Days": True,
            "probabilityLevel": None, "equipment": None, "market": "Frontend", "amount": "125000.25", "currency": "USD",
            "amountCny": None, "nextAction": {"id": "a1", "title": "Call", "due": "2026-09-30"},
        })

    def test_an_unknown_amount_is_empty_on_the_row_and_missing_in_the_totals(self):
        # An S1 Opportunity saved without an amount stores 0 in every amount column: unknown, never 0.
        board = rows(opportunity("s1", stage="qualified_opportunity", amount="0.00", amount_cny="0.00"), opportunity("s2"))
        unknown = next(row for row in board if row.dto["id"] == "s1")
        self.assertEqual((unknown.dto["amount"], unknown.dto["currency"], unknown.dto["amountCny"]), ("", "CNY", None))
        _ids, summary, groups = run(board, groupBy="stage")
        self.assertEqual((summary["count"], summary["knownAmountCny"], summary["missingAmountCount"]), (2, "100.00", 1))
        self.assertEqual(
            [(group["key"], group["count"], group["knownAmountCny"], group["missingAmountCount"]) for group in groups],
            [("qualified_opportunity", 1, "0.00", 1), ("demo_done", 1, "100.00", 0)],
        )

    def test_stage_age_uses_shanghai_days_and_21_days_is_not_yet_stale(self):
        board = rows(
            opportunity("day21", stage_changed_at=datetime(2026, 9, 1, 23, 59)),
            opportunity("day22", stage_changed_at=datetime(2026, 8, 31, 23, 59)),
            # 2026-08-31 16:30 UTC is already 2026-09-01 in Shanghai.
            opportunity("utc", stage_changed_at="2026-08-31T16:30:00+00:00"),
            opportunity("closed", stage="lost", stage_changed_at=datetime(2026, 1, 1)),
            opportunity("unknown", stage_changed_at=None),
            opportunity("unknown-closed", stage="po_received", stage_changed_at=None),
            opportunity("future", stage_changed_at=datetime(2026, 9, 23, 8)),
        )
        ages = {row.dto["id"]: (row.dto["stageAgeDays"], row.dto["stageUnchangedOver21Days"]) for row in board}
        self.assertEqual(ages, {"day21": (21, False), "day22": (22, True), "utc": (21, False), "closed": (264, False),
                                "unknown": (None, False), "unknown-closed": (None, False), "future": (0, False)})
        _ids, summary, _groups = run(board)
        self.assertEqual((summary["stageUnchangedOver21DaysCount"], summary["unknownStageAgeCount"]), (1, 1))
        ids, _summary, _groups = run(board, conditions=[{"field": "stageAgeDays", "operator": "gt", "value": 21}])
        self.assertEqual(ids, ["closed", "day22"])
        ids, _summary, _groups = run(board, conditions=[{"field": "stageAgeDays", "operator": "lte", "value": 21}])
        self.assertEqual(sorted(ids), ["day21", "future", "utc"])

    def test_next_action_is_the_earliest_open_one_with_undated_last_and_ties_by_id(self):
        actions = [
            {"name": "b", "opportunity": "o1", "title": "B", "due": "2026-09-25", "status": "Open", "archived": 0},
            {"name": "a", "opportunity": "o1", "title": "A", "due": "2026-09-25", "status": "Open", "archived": 0},
            {"name": "done", "opportunity": "o1", "title": "Done", "due": "2026-09-01", "status": "Done", "archived": 0},
            {"name": "gone", "opportunity": "o1", "title": "Gone", "due": "2026-09-01", "status": "Open", "archived": 1},
            {"name": "undated", "opportunity": "o2", "title": "Later", "due": None, "status": "Open", "archived": 0},
        ]
        board = {row.dto["id"]: row.dto["nextAction"] for row in rows(opportunity("o1"), opportunity("o2"), opportunity("o3"), actions=actions)}
        self.assertEqual(board, {"o1": {"id": "a", "title": "A", "due": "2026-09-25"},
                                 "o2": {"id": "undated", "title": "Later", "due": None}, "o3": None})


class TestQuery(unittest.TestCase):
    def setUp(self):
        self.board = rows(
            opportunity("o1", stage="demo_done", opportunity_owner="alice", region="East China", amount_cny="100.00",
                        stage_changed_at=datetime(2026, 7, 1, 0, 30), customer_name="Acme 50% Fab"),
            opportunity("o2", stage="quotation_sent", opportunity_owner="bob", region="South China", amount_cny="250.50",
                        stage_changed_at=datetime(2026, 6, 30, 23, 59), probability_level="committed"),
            opportunity("o3", stage="lost", opportunity_owner="alice", region=None, amount_cny=None,
                        stage_changed_at=datetime(2026, 7, 2), probability_level="", market=""),
            opportunity("o4", stage="rfq_validated", opportunity_owner="bob", region="East China", amount_cny="0",
                        stage_changed_at=None, probability_level="upside", tool_type="Metrology"),
        )

    def test_dates_are_shanghai_days_after_and_before_exclude_the_day_between_includes_both(self):
        def ids(op, value):
            return sorted(run(self.board, conditions=[{"field": "stageChangedAt", "operator": op, "value": value}])[0])
        self.assertEqual(ids("after", "2026-07-01"), ["o3"])
        self.assertEqual(ids("after", "2026-06-30"), ["o1", "o3"])
        self.assertEqual(ids("before", "2026-07-01"), ["o2"])
        self.assertEqual(ids("between", ["2026-07-01", "2026-07-01"]), ["o1"])
        self.assertEqual(ids("between", ["2026-06-30", "2026-07-02"]), ["o1", "o2", "o3"])

    def test_missing_amounts_never_match_and_are_counted_apart(self):
        def ids(op, value):
            return sorted(run(self.board, conditions=[{"field": "amountCny", "operator": op, "value": value}])[0])
        self.assertEqual(ids("gte", "0"), ["o1", "o2"])
        self.assertEqual(ids("lt", "999"), ["o1", "o2"])
        self.assertEqual(ids("between", ["100", "100.00"]), ["o1"])
        _ids, summary, _groups = run(self.board)
        self.assertEqual((summary["count"], summary["knownAmountCny"], summary["missingAmountCount"]), (4, "350.50", 2))

    def test_any_joins_conditions_but_scope_still_applies(self):
        conditions = [{"field": "stage", "operator": "in", "value": ["lost"]},
                      {"field": "region", "operator": "in", "value": ["South China"]}]
        self.assertEqual(sorted(run(self.board, match="any", conditions=conditions)[0]), ["o2", "o3"])
        self.assertEqual(run(self.board, match="all", conditions=conditions)[0], [])
        self.assertEqual(run(self.board, match="any", conditions=conditions, scope={"sales": ["alice"]})[0], ["o3"])
        self.assertEqual(sorted(run(self.board, scope={"regions": ["East China"], "equipment": ["Inspection"]})[0]), ["o1"])

    def test_list_operators_pending_and_empty_values(self):
        def ids(field, op, value):
            return sorted(run(self.board, conditions=[{"field": field, "operator": op, "value": value}])[0])
        self.assertEqual(ids("probabilityLevel", "in", ["pending"]), ["o3"])
        self.assertEqual(ids("probabilityLevel", "not_in", ["pending", "pipeline"]), ["o2", "o4"])
        self.assertEqual(ids("region", "in", ["East China"]), ["o1", "o4"])
        # A row without a region is not in East China.
        self.assertEqual(ids("region", "not_in", ["East China"]), ["o2", "o3"])
        self.assertEqual(ids("market", "not_in", ["Frontend"]), ["o3"])
        self.assertEqual(ids("customerName", "contains", "50%"), ["o1"])
        self.assertEqual(ids("customerName", "contains", "acme"), ["o1"])
        self.assertEqual(ids("customerName", "contains", "_"), [])

    def test_sort_puts_unknown_values_last_in_both_directions_with_id_ties(self):
        self.assertEqual(run(self.board, sort={"field": "stageChangedAt", "direction": "asc"})[0], ["o2", "o1", "o3", "o4"])
        self.assertEqual(run(self.board, sort={"field": "stageChangedAt", "direction": "desc"})[0], ["o3", "o1", "o2", "o4"])
        self.assertEqual(run(self.board, sort={"field": "amountCny", "direction": "desc"})[0], ["o2", "o1", "o3", "o4"])
        self.assertEqual(run(self.board, sort={"field": "region", "direction": "asc"})[0], ["o1", "o4", "o2", "o3"])
        self.assertEqual(run(self.board, sort={"field": "region", "direction": "desc"})[0], ["o2", "o1", "o4", "o3"])
        self.assertEqual(run(self.board, sort={"field": "stage", "direction": "asc"})[0], ["o1", "o4", "o2", "o3"])
        self.assertEqual(run(self.board, sort={"field": "probabilityLevel", "direction": "desc"})[0], ["o2", "o4", "o1", "o3"])

    def test_groups_order_the_rows_and_total_every_match(self):
        ids, summary, groups = run(self.board, groupBy="region", sort={"field": "amountCny", "direction": "desc"})
        self.assertEqual(ids, ["o1", "o4", "o2", "o3"])
        self.assertEqual(groups, [
            {"key": "East China", "label": "East China", "count": 2, "knownAmountCny": "100.00", "missingAmountCount": 1},
            {"key": "South China", "label": "South China", "count": 1, "knownAmountCny": "250.50", "missingAmountCount": 0},
            {"key": None, "label": "Not set", "count": 1, "knownAmountCny": "0.00", "missingAmountCount": 1},
        ])
        ids, _summary, groups = run(self.board, groupBy="region", sort={"field": "region", "direction": "desc"})
        self.assertEqual([group["key"] for group in groups], ["South China", "East China", None])
        _ids, _summary, groups = run(self.board, groupBy="probabilityLevel")
        self.assertEqual([(group["key"], group["label"]) for group in groups],
                         [("pipeline", "Pipeline"), ("upside", "Upside"), ("committed", "Committed"),
                          ("pending", "Pending sales confirmation")])
        _ids, _summary, groups = run(self.board, groupBy="sales")
        self.assertEqual([(group["key"], group["label"], group["count"]) for group in groups], [("alice", "Alice", 2), ("bob", "Bob", 2)])

    def test_probability_summary_always_lists_all_five_levels(self):
        _ids, summary, _groups = run(self.board, conditions=[{"field": "stage", "operator": "not_in", "value": ["lost"]}])
        self.assertEqual(summary["byProbability"], [
            {"level": "low_probability", "count": 0, "knownAmountCny": "0.00", "missingAmountCount": 0},
            {"level": "pipeline", "count": 1, "knownAmountCny": "100.00", "missingAmountCount": 0},
            {"level": "upside", "count": 1, "knownAmountCny": "0.00", "missingAmountCount": 1},
            {"level": "committed", "count": 1, "knownAmountCny": "250.50", "missingAmountCount": 0},
            {"level": "pending", "count": 0, "knownAmountCny": "0.00", "missingAmountCount": 0},
        ])


class TestLegacyRows(unittest.TestCase):
    """Spellings from before the catalog, and rows the DocType would refuse but the database holds."""

    def test_legacy_spellings_of_a_catalog_type_are_shown_and_matched_as_that_type(self):
        board = board_rows([
            opportunity("o1", tool_type="NANSI"), opportunity("o2", tool_type="nan-si"),
            opportunity("o3", tool_type="Nansi"), opportunity("o4", tool_type="inspection "),
            opportunity("o5", tool_type="Kibo 4895C"),
        ], {"alice": "Alice"}, [], NOW, equipment=OPTIONS["equipment"])
        # A value with no catalog match keeps its own spelling instead of disappearing.
        self.assertEqual([row.dto["equipment"] for row in board], ["Nansi", "Nansi", "Nansi", "Inspection", "Kibo 4895C"])
        self.assertEqual(run(board, scope={"equipment": ["Nansi"]})[0], ["o1", "o2", "o3"])
        self.assertEqual(run(board, conditions=[{"field": "equipment", "operator": "not_in", "value": ["Nansi"]}])[0], ["o4", "o5"])
        _ids, _summary, groups = run(board, groupBy="equipment")
        self.assertEqual([(group["key"], group["count"]) for group in groups], [("Inspection", 1), ("Kibo 4895C", 1), ("Nansi", 3)])

    def test_rows_without_an_owner_or_account_or_with_an_unknown_level_still_list(self):
        board = rows(
            opportunity("o1"),
            opportunity("o2", opportunity_owner=None, account=None, customer_name=None, probability_level="high"),
        )
        row = board[1].dto
        self.assertEqual((row["salesId"], row["salesName"], row["accountId"], row["customerName"], row["probabilityLevel"]),
                         ("", "", "", "", None))
        for field, expected in (("sales", ["o1", "o2"]), ("customerName", ["o2", "o1"]), ("probabilityLevel", ["o1", "o2"])):
            self.assertEqual(run(board, sort={"field": field, "direction": "asc"})[0], expected, field)
        _ids, _summary, groups = run(board, groupBy="sales")
        self.assertEqual([(group["key"], group["label"], group["count"]) for group in groups],
                         [("alice", "Alice", 1), (None, "Not set", 1)])
        _ids, _summary, groups = run(board, groupBy="probabilityLevel")
        self.assertEqual([(group["key"], group["label"]) for group in groups],
                         [("pipeline", "Pipeline"), ("pending", "Pending sales confirmation")])
        self.assertEqual(run(board, conditions=[{"field": "probabilityLevel", "operator": "in", "value": ["pending"]}])[0], ["o2"])


class TestTerritories(unittest.TestCase):
    def setUp(self):
        self.board = board_rows([
            opportunity("east"), opportunity("south", region="South China"),
            opportunity("overseas", region="Overseas"), opportunity("none", region=None),
        ], {"alice": "Alice"}, [], NOW, region_parents=REGION_PARENTS)

    def run_board(self, **query):
        ordered, _summary, groups = build_board(self.board, validate_query(query, TERRITORY_OPTIONS))
        return sorted(row.dto["id"] for row in ordered), groups

    def test_a_territory_selects_the_regions_below_it(self):
        def scoped(*regions):
            return self.run_board(scope={"regions": list(regions)})[0]

        def where(op, *regions):
            return self.run_board(conditions=[{"field": "region", "operator": op, "value": list(regions)}])[0]

        self.assertEqual(scoped("China"), ["east", "south"])
        self.assertEqual(scoped("World"), ["east", "south"])
        self.assertEqual(scoped("South China"), ["south"])
        self.assertEqual(scoped("East China", "Overseas"), ["east", "overseas"])
        self.assertEqual(where("in", "Asia"), ["east", "south"])
        # Not within China: a region outside the tree, and no region at all.
        self.assertEqual(where("not_in", "China"), ["none", "overseas"])
        self.assertEqual(where("not_in", "East China"), ["none", "overseas", "south"])
        self.assertEqual(self.run_board(scope={"regions": ["China"]}, conditions=[
            {"field": "region", "operator": "not_in", "value": ["South China"]}])[0], ["east"])

    def test_groups_and_the_region_column_stay_the_customers_own_region(self):
        ids, groups = self.run_board(scope={"regions": ["China"]}, groupBy="region")

        self.assertEqual(ids, ["east", "south"])
        self.assertEqual([(group["key"], group["count"]) for group in groups], [("East China", 1), ("South China", 1)])
        self.assertEqual({row.dto["id"]: row.dto["region"] for row in self.board},
                         {"east": "East China", "south": "South China", "overseas": "Overseas", "none": None})

    def test_rows_built_without_a_tree_match_their_own_region_only(self):
        board = rows(opportunity("east"), opportunity("south", region="South China"))
        ordered, _summary, _groups = build_board(board, validate_query({"scope": {"regions": ["East China"]}}, OPTIONS))
        self.assertEqual([row.dto["id"] for row in ordered], ["east"])


if __name__ == "__main__":
    unittest.main()
