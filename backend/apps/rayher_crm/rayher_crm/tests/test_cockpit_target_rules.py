import unittest

from rayher_crm.services.cockpit_target_rules import aggregate, target, territory_members, UNCLASSIFIED_REGION


def row(sales="alice", value="5", **extra):
    return {"id": sales, "sales": sales, "metric": "visits", "period": "week", "anchor": "2026-10-05", "value": value, **extra}


class TestCockpitTargetRules(unittest.TestCase):
    def test_team_sum_missing_zero_and_duplicate_members(self):
        rows = [row(), row("bob", "0")]
        total = aggregate(rows, ["alice", "bob", "alice"], "visits", "week", "2026-10-05", "sales")
        self.assertEqual((total["value"], total["state"], len(total["sources"])), ("5.00", "ready", 2))
        partial = aggregate(rows, ["alice", "bob", "carol"], "visits", "week", "2026-10-05", "sales")
        self.assertEqual((partial["value"], partial["state"], partial["missing"]), (None, "insufficient", ["carol"]))
        self.assertEqual(aggregate([], ["alice"], "visits", "week", "2026-10-05", "sales")["state"], "not_set")

    def test_week_default_is_effective_and_never_multiplied_to_month(self):
        rows = [row(period="weekly_default", anchor="2026-09-28"), row(value="8", period="weekly_default", anchor="2026-10-12")]
        self.assertEqual(target(rows, "visits", "week", "2026-10-05")["value"], "5")
        self.assertEqual(target(rows, "visits", "week", "2026-10-12")["value"], "8")
        self.assertEqual(target(rows, "visits", "month", "2026-10-01")["state"], "not_set")
        rows.append(row(value="0"))
        self.assertEqual(target(rows, "visits", "week", "2026-10-05")["value"], "0")

    def test_only_leaf_territories_sum_and_unmapped_regions_are_explicit(self):
        tree = [{"name": "World", "is_group": 1}, {"name": "China", "is_group": 1, "parent_territory": "World"},
                {"name": "East", "parent_territory": "China"}, {"name": "West", "parent_territory": "China"},
                {"name": "Europe", "parent_territory": "World"}]
        members, missing = territory_members(tree, "China", ["East", "West", "China", ""])
        self.assertEqual(members, sorted(["East", "West", "China", UNCLASSIFIED_REGION]))
        self.assertEqual(missing, sorted(["China", UNCLASSIFIED_REGION]))
        members, _ = territory_members(tree, "China", ["East", "West"])
        rows = [row("", value, scope="territory", territory=name, metric="orders", period="year", anchor="2026-01-01")
                for name, value in (("East", "1500000"), ("West", "2000000"), ("China", "3500000"), ("Europe", "4000000"))]
        total = aggregate(rows, members, "orders", "year", "2026-01-01", "territory")
        self.assertEqual(total["value"], "3500000.00")
        self.assertEqual(aggregate(rows, [*members, "Unmapped"], "orders", "year", "2026-01-01", "territory")["state"], "insufficient")

    def test_corrupt_values_are_not_zero(self):
        for bad in ("NaN", "Infinity", "-1", "wrong"):
            self.assertEqual(target([row(value=bad)], "visits", "week", "2026-10-05")["state"], "insufficient")
            self.assertEqual(aggregate([row(value=bad)], ["alice"], "visits", "week", "2026-10-05", "sales")["state"], "insufficient")

    def test_duplicate_selected_key_is_unknown_but_distinct_default_weeks_are_valid(self):
        rows = [row(), row(value="8")]
        self.assertEqual(target(rows, "visits", "week", "2026-10-05")["reason"], "duplicate_targets")
        self.assertIsNone(aggregate(rows, ["alice"], "visits", "week", "2026-10-05", "sales")["value"])
        defaults = [row(period="weekly_default", anchor="2026-09-21"),
                    row(value="7", period="weekly_default", anchor="2026-09-28")]
        self.assertEqual(target(defaults, "visits", "week", "2026-10-05")["value"], "7")
        defaults.append({**defaults[-1], "value": "9"})
        self.assertEqual(target(defaults, "visits", "week", "2026-10-05")["reason"], "duplicate_targets")
        self.assertEqual(target([*defaults, row(value="0")], "visits", "week", "2026-10-05")["value"], "0")

    def test_outside_contributors_are_explicitly_not_assignable_and_preserve_existing_goals(self):
        total = aggregate([], ["former"], "visits", "week", "2026-10-05", "sales", non_targetable={"former"})
        self.assertEqual(total["state"], "insufficient")
        self.assertEqual(total["sources"][0]["reason"], "target_owner_not_assignable")
        self.assertFalse(total["sources"][0]["assignable"])
        total = aggregate([row("former", "0")], ["former"], "visits", "week", "2026-10-05", "sales", non_targetable={"former"})
        self.assertEqual((total["state"], total["value"]), ("ready", "0.00"))
