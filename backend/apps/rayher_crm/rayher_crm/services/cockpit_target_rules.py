"""Scope-aware target selection and aggregation over already serialized records."""
from decimal import Decimal, InvalidOperation

from rayher_crm.services.territory_tree import covered

UNCLASSIFIED_REGION = "__unclassified_region__"


def amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def choose(records, key, period, anchor):
    explicit = [r for r in records if r["metric"] == key and r["period"] == period and r["anchor"] == anchor]
    if explicit:
        return explicit
    if period == "week":
        defaults = [r for r in records if r["metric"] == key and r["period"] == "weekly_default" and r["anchor"] <= anchor]
        effective = max((r["anchor"] for r in defaults), default=None)
        return [r for r in defaults if r["anchor"] == effective]
    return []


def target(records, key, period, anchor):
    selected = choose(records, key, period, anchor)
    if len(selected) > 1:
        return {"value": None, "state": "insufficient", "reason": "duplicate_targets", "record": None}
    record = selected[0] if selected else None
    valid = record is not None and amount(record["value"]) is not None
    return {"value": record["value"] if valid else None,
            "state": "ready" if valid else "insufficient" if record else "not_set",
            "reason": "invalid_target" if record and not valid else None, "record": record}


def aggregate(records, members, key, period, anchor, scope, *, non_targetable=()):
    """A total is usable only when every distinct member has a valid target."""
    parts = []
    for member in sorted(set(members)):
        rows = [r for r in records if (r.get("scope") or "sales") == scope
                and (r.get("territory") if scope == "territory" else r.get("sales")) == member]
        part = {"member": member, **target(rows, key, period, anchor)}
        if member in non_targetable:
            part["assignable"] = False
            if part["state"] == "not_set":
                part.update(state="insufficient", reason="target_owner_not_assignable")
        parts.append(part)
    missing = [r["member"] for r in parts if r["state"] != "ready"]
    ready = [r for r in parts if r["state"] == "ready"]
    invalid = any(r["state"] == "insufficient" for r in parts)
    complete = bool(parts) and not missing
    return {"value": format(sum((amount(r["value"]) for r in ready), Decimal(0)), ".2f") if complete else None,
            "state": "ready" if complete else "insufficient" if ready or invalid else "not_set",
            "reason": None if complete else "target_incomplete" if ready or invalid else "targets_missing",
            "record": None, "sources": parts, "missing": missing, "scope": scope}


def territory_members(tree, selection, customer_regions):
    """Leaf goals only; unknown customer regions stay visible as missing members."""
    names = [r["name"] for r in tree]
    parents = {r["name"]: r["parent_territory"] for r in tree if r.get("parent_territory")}
    selected = covered(selection, names, parents) if selection else set(names)
    leaves = {r["name"] for r in tree if not r.get("is_group")}
    members = selected & leaves
    # customer_regions already has the query's customer scope applied.
    missing = {region or UNCLASSIFIED_REGION for region in customer_regions if region not in leaves}
    if selection and selection not in names:
        missing.add(selection)
    return sorted(members | missing), sorted(missing)
