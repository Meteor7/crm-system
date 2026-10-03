"""Sales territory rules: the order territories are listed in and the regions a territory covers.

Pure functions over plain values, run with plain unittest.

- A territory is named like the Customer region it stands for, or groups the territories below it.
- A territory covers the names below it and its own, so it selects the customers whose region is one of them.
- A region no territory is named after is listed after the tree, on its own.
- The tree reads what is stored and never fails on it: a parent that does not exist, or parents that loop,
  end the walk up.
"""

from __future__ import annotations


def ordered(rows, regions):
    """Every selectable name in display order, a territory before the ones below it, and the parent of each.

    ``rows`` are territories as ``{"name", "parent", "sort_order"}``; ``regions`` are the Customer region options.
    """

    rows = sorted(rows, key=lambda row: (row.get("sort_order") or 0, row["name"]))
    known = {row["name"] for row in rows}
    children: dict[str | None, list[str]] = {}
    for row in rows:
        parent = row.get("parent")
        children.setdefault(parent if parent in known and parent != row["name"] else None, []).append(row["name"])
    names: list[str] = []
    parents: dict[str, str] = {}

    def walk(name, parent):
        if name in listed:
            return
        listed.add(name)
        names.append(name)
        if parent:
            parents[name] = parent
        for child in children.get(name, ()):
            walk(child, name)

    listed: set[str] = set()
    for root in children.get(None, ()):
        walk(root, None)
    # Parents that loop have no root; list those territories too, each loop cut at its first name.
    for row in rows:
        walk(row["name"], None)
    return [*names, *(region for region in regions if region not in listed)], parents


def ancestors(name, parents):
    """The territories above a name, nearest first."""

    above: list[str] = []
    seen = {name}
    while parents.get(name) and parents[name] not in seen:
        name = parents[name]
        seen.add(name)
        above.append(name)
    return above


def covered(name, names, parents):
    """The names a territory covers: its own and every name below it."""

    return {other for other in names if other == name or name in ancestors(other, parents)}
