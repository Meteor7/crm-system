import unittest

from rayher_crm.services.territory_rules import overlaps, validate_tree


class TestTerritoryRules(unittest.TestCase):
    def test_moves_check_descendants_cycles_depth_and_leaf_parent(self):
        rows = [dict(name=name, parent_territory=parent, is_group=group, enabled=1) for name, parent, group in (
            ("World", None, 1), ("Asia", "World", 1), ("China", "Asia", 1), ("East", "China", 0),
        )]
        with self.assertRaises(ValueError):
            validate_tree(rows, {**rows[0], "parent_territory": "China"})
        with self.assertRaises(ValueError):
            validate_tree(rows, dict(name="Too deep", parent_territory="East", is_group=0, enabled=1))
        with self.assertRaises(ValueError):
            validate_tree(rows, {**rows[1], "enabled": 0})
        validate_tree(rows, {**rows[3], "enabled": 0})
        validate_tree(rows, {**rows[2], "parent_territory": "World"})
        # Readable legacy orphan branches do not prevent maintenance elsewhere.
        validate_tree([*rows, dict(name="Orphan", parent_territory="Missing", is_group=0, enabled=1)], {**rows[3], "enabled": 0})

    def test_assignments_include_both_boundary_dates_and_allow_disjoint_successors(self):
        rows = [dict(name="first", valid_from="2026-01-01", valid_until="2026-06-30", cancelled=0)]
        self.assertTrue(overlaps("2026-06-30", None, rows))
        self.assertFalse(overlaps("2026-07-01", None, rows))
        self.assertFalse(overlaps("2026-01-01", None, rows, exclude="first"))
        self.assertFalse(overlaps("2026-01-01", None, [{**rows[0], "cancelled": 1}]))
        with self.assertRaises(ValueError):
            overlaps("2026-07-01", "2026-06-30", rows)

