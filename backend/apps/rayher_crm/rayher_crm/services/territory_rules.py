"""Validation of administrative territory changes, independent of Frappe."""
from datetime import date


def validate_tree(rows, changed):
    nodes = {row["name"]: dict(row) for row in rows}
    nodes[changed["name"]] = changed
    # Validate this branch, including descendants whose depth changes with a move.
    # An unrelated invalid legacy branch must still be repairable one branch at a time.
    affected, pending = set(), [changed["name"]]
    while pending:
        name = pending.pop()
        if name in affected:
            continue
        affected.add(name)
        pending.extend(row["name"] for row in nodes.values() if row.get("parent_territory") == name)
    for name in affected:
        seen = set()
        current = name
        while current:
            if current not in nodes:
                raise ValueError("Parent territory does not exist.")
            if current in seen:
                raise ValueError("A territory cannot sit below itself.")
            seen.add(current)
            if len(seen) > 4:
                raise ValueError("The territory tree supports at most four levels.")
            parent = nodes[current].get("parent_territory")
            if parent in nodes and not nodes[parent].get("is_group"):
                raise ValueError("A region cannot contain other territories.")
            current = parent
    parent = changed.get("parent_territory")
    if changed.get("enabled") and parent and not nodes[parent].get("enabled"):
        raise ValueError("Choose an active parent territory.")
    if not changed.get("enabled") and any(row.get("parent_territory") == changed["name"] and row.get("enabled") for row in nodes.values()):
        raise ValueError("Deactivate or move active children first.")


def date_range(start, end):
    try:
        first = date.fromisoformat(str(start))
        last = date.fromisoformat(str(end)) if end else date.max
    except (TypeError, ValueError):
        raise ValueError("Use valid effective dates in YYYY-MM-DD format.") from None
    if last < first:
        raise ValueError("Effective end cannot precede effective start.")
    return first, last


def overlaps(start, end, rows, exclude=None):
    first, last = date_range(start, end)
    for row in rows:
        if row.get("name") == exclude or row.get("cancelled"):
            continue
        other_first, other_last = date_range(row["valid_from"], row.get("valid_until"))
        if first <= other_last and other_first <= last:
            return True
    return False
