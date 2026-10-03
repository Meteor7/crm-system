from __future__ import annotations

import unittest

from rayher_crm.services.territory_tree import ancestors, covered, ordered


def row(name, parent=None, sort_order=0):
    return {"name": name, "parent": parent, "sort_order": sort_order}


ROWS = [
    row("South China", "China", 2),
    row("Europe", "World"),
    row("China", "Asia"),
    row("East China", "China", 1),
    row("World"),
    row("Asia", "World"),
]
REGIONS = ["East China", "South China", "Overseas"]


class TestTerritoryTree(unittest.TestCase):
    def test_a_territory_is_listed_before_the_ones_below_it(self):
        names, parents = ordered(ROWS, REGIONS)

        # Siblings follow their sort order, then their name; a region outside the tree comes last, on its own.
        self.assertEqual(names, ["World", "Asia", "China", "East China", "South China", "Europe", "Overseas"])
        self.assertEqual(parents, {
            "Asia": "World", "China": "Asia", "East China": "China", "South China": "China", "Europe": "World",
        })

    def test_a_territory_covers_itself_and_everything_below_it(self):
        names, parents = ordered(ROWS, REGIONS)

        self.assertEqual(covered("China", names, parents), {"China", "East China", "South China"})
        self.assertEqual(covered("East China", names, parents), {"East China"})
        self.assertEqual(covered("Europe", names, parents), {"Europe"})
        # World is the tree, not everything: a region nobody placed in the tree is not below it.
        self.assertEqual(covered("World", names, parents), set(names) - {"Overseas"})
        self.assertEqual(covered("Overseas", names, parents), {"Overseas"})
        self.assertEqual(ancestors("East China", parents), ["China", "Asia", "World"])
        self.assertEqual(ancestors("World", parents), [])
        self.assertEqual(ancestors("Overseas", parents), [])

    def test_stored_parents_that_are_missing_or_loop_never_break_the_list(self):
        rows = [
            row("Orphan", "Deleted"), row("Self", "Self"),
            row("Loop A", "Loop B"), row("Loop B", "Loop A"), row("Below loop", "Loop B"),
        ]

        names, parents = ordered(rows, ["Self"])

        # Every territory is listed once. A missing or own parent makes it a root; what no root leads to
        # follows in name order, a loop cut at the first of its names.
        self.assertEqual(names, ["Orphan", "Self", "Below loop", "Loop A", "Loop B"])
        self.assertEqual(parents, {"Loop B": "Loop A"})
        self.assertEqual(covered("Loop A", names, parents), {"Loop A", "Loop B"})
        # Parents handed in from elsewhere may loop as well; the walk up still ends.
        self.assertEqual(ancestors("a", {"a": "b", "b": "a"}), ["b"])

    def test_without_territories_the_regions_are_listed_as_they_are(self):
        self.assertEqual(ordered([], REGIONS), (REGIONS, {}))
        self.assertEqual(ordered([], []), ([], {}))


if __name__ == "__main__":
    unittest.main()
