"""Opportunities board rules: validate a query, then filter, sort, group and total its rows.

Pure functions over plain dicts, run with plain unittest. The service hands in only the rows
the current user may already read, so nothing here can widen the permission scope: a query
is always permission scope AND ``scope`` AND the combined conditions, and ``match: any``
only joins the conditions.

Decisions recorded in docs/opportunity-board/backend-handoff.md:
- Dates are Shanghai calendar days. ``before`` / ``after`` exclude the given day, ``between``
  includes both ends. Timestamps go out as UTC ISO strings.
- Stage age counts Shanghai calendar days since the last stage change. An unknown change time
  stays unknown (None), never zero, and matches no date or age condition.
- A missing CNY amount matches no amount condition and is counted apart from the known total.
- ``not_in`` keeps rows whose value is empty: a customer without a region is not in East China.
- A region value may be a sales territory (territory_tree): it stands for every region below it, so
  ``in`` reads "within" and ``not_in`` "not within". Grouping and the region column stay the customer's region.
- Only open stages (S1-S6) can have gone 21 days without a stage change; closed ones are done.
"""

from __future__ import annotations

from rayher_crm.services.action_statuses import open_action

import operator
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from rayher_crm.services.equipment_names import canonical_equipment, equipment_spellings
from rayher_crm.services.opportunity_stages import OPEN_STAGES, OPPORTUNITY_STAGES, PROBABILITY_LEVELS
from rayher_crm.services.territory_tree import ancestors

# China has kept UTC+8 without daylight saving since 1991; a fixed offset needs no tz database.
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
STALE_STAGE_DAYS = 21
PENDING = "pending"
PROBABILITY_FILTER_LEVELS = (*PROBABILITY_LEVELS, PENDING)
CENT = Decimal("0.01")

STAGE_LABELS = {
    "qualified_opportunity": "Qualified opportunity",
    "demo_done": "Demo done",
    "customer_budget_approved": "Customer budget approved",
    "rfq_validated": "RFQ validated",
    "quotation_sent": "Quotation sent",
    "internal_validation": "Internal validation",
    "po_received": "PO received",
    "lost": "Lost",
}
PROBABILITY_LABELS = {
    "low_probability": "Low probability",
    "pipeline": "Pipeline",
    "upside": "Upside",
    "committed": "Committed",
    PENDING: "Pending sales confirmation",
}
NOT_SET_LABEL = "Not set"

MATCH_MODES = ("all", "any")
LIST_OPERATORS = ("in", "not_in")
COMPARISONS = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
OPERATORS = {
    "stage": LIST_OPERATORS,
    "probabilityLevel": LIST_OPERATORS,
    "sales": LIST_OPERATORS,
    "region": LIST_OPERATORS,
    "market": LIST_OPERATORS,
    "equipment": LIST_OPERATORS,
    "customerName": ("contains",),
    "stageChangedAt": ("before", "after", "between"),
    "stageAgeDays": ("gt", "gte", "lt", "lte"),
    "amountCny": ("gt", "gte", "lt", "lte", "between"),
}
# Scope key -> the condition field whose values it takes.
SCOPE_FIELDS = {"sales": "sales", "regions": "region", "markets": "market", "equipment": "equipment"}
GROUP_FIELDS = ("region", "sales", "stage", "probabilityLevel", "equipment", "market")
SORT_FIELDS = (
    "customerName", "title", "region", "sales", "stage", "stageChangedAt", "stageAgeDays",
    "probabilityLevel", "equipment", "market", "amountCny", "nextAction",
)
COLUMNS = (
    "customerName", "title", "region", "sales", "stage", "stageChangedAt", "probabilityLevel",
    "equipment", "market", "amount", "amountCny", "nextAction",
)
DEFAULT_SORT = {"field": "stageChangedAt", "direction": "asc"}
QUERY_KEYS = ("scope", "match", "conditions", "sort", "groupBy", "page", "pageSize")
DEFINITION_KEYS = ("scope", "match", "conditions", "sort", "groupBy", "columns")

MAX_CONDITIONS = 20
MAX_VALUES = 100
MAX_TEXT = 140
MAX_STAGE_AGE_DAYS = 36500
AMOUNT_PATTERN = re.compile(r"[0-9]{1,18}(\.[0-9]{1,2})?")


class BoardQueryError(ValueError):
    """An invalid query; ``field`` is the input path, e.g. ``conditions[1].value``."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


# ---------------------------------------------------------------- validation

def validate_query(raw, options):
    """The query input: a saved definition without columns. Paging is read by the service."""

    _object(raw, QUERY_KEYS, "input")
    return _definition(raw, options)


def validate_definition(raw, options):
    """A saved query definition; it must be runnable when it is saved."""

    _object(raw, DEFINITION_KEYS, "definition")
    definition = _definition(raw, options)
    definition["columns"] = _columns(raw.get("columns"))
    return definition


def _definition(raw, options):
    return {
        "scope": _scope(raw.get("scope"), options),
        "match": _choice(_or_default(raw.get("match"), "all"), MATCH_MODES, "match"),
        "conditions": _conditions(raw.get("conditions"), options),
        "sort": _sort(raw.get("sort")),
        "groupBy": _group_by(raw.get("groupBy"), options),
    }


def _or_default(value, default):
    return default if value is None else value


ROOTS = ("input", "definition")


def _path(parent, key):
    """Error paths are relative to the query or definition object itself."""

    return key if parent in ROOTS else f"{parent}.{key}"


def _object(value, keys, path):
    if not isinstance(value, dict):
        raise BoardQueryError(path, f"{path} must be an object.")
    unknown = sorted(str(key) for key in value if key not in keys)
    if unknown:
        field = _path(path, unknown[0])
        raise BoardQueryError(field, f"Unknown field {field}.")


def _choice(value, choices, path):
    if value not in choices:
        raise BoardQueryError(path, f"{path} must be one of: {', '.join(choices)}.")
    return value


def _scope(value, options):
    if value is None:
        value = {}
    _object(value, SCOPE_FIELDS, "scope")
    return {
        key: _values(field, value.get(key), options, f"scope.{key}", allow_empty=True)
        for key, field in SCOPE_FIELDS.items()
    }


def _values(field, value, options, path, *, allow_empty):
    if value is None and allow_empty:
        return []
    if not isinstance(value, list):
        raise BoardQueryError(path, f"{path} must be an array.")
    if not value and not allow_empty:
        raise BoardQueryError(path, f"{path} must list at least one value.")
    if len(value) > MAX_VALUES:
        raise BoardQueryError(path, f"{path} may list at most {MAX_VALUES} values.")
    result = []
    for item in value:
        text = item.strip() if isinstance(item, str) else ""
        if not text or len(text) > MAX_TEXT:
            raise BoardQueryError(path, f"{path} must hold non-empty strings of at most {MAX_TEXT} characters.")
        if text not in result:
            result.append(text)
    if result:
        allowed = _allowed_values(field, options, path)
        invalid = [item for item in result if item not in allowed]
        if invalid:
            raise BoardQueryError(path, f"{path} has an unknown value: {invalid[0]}.")
    return result


def _allowed_values(field, options, path):
    if field == "stage":
        return set(OPPORTUNITY_STAGES)
    if field == "probabilityLevel":
        return set(PROBABILITY_FILTER_LEVELS)
    if field == "sales":
        return set(options["sales"])
    if field == "region":
        _require_regions(options, path)
        return set(options["regions"])
    if field == "market":
        return set(options["markets"])
    # Equipment: the catalog, which holds every type stored on an Opportunity, matched exactly.
    return set(options["equipment"])


def _require_regions(options, path):
    if not options["regionReady"]:
        raise BoardQueryError(path, "Region filters are unavailable until the region migration is verified.")


def _conditions(value, options):
    if value is None:
        return []
    if not isinstance(value, list):
        raise BoardQueryError("conditions", "conditions must be an array.")
    if len(value) > MAX_CONDITIONS:
        raise BoardQueryError("conditions", f"conditions may hold at most {MAX_CONDITIONS} entries.")
    return [_condition(item, options, f"conditions[{index}]") for index, item in enumerate(value)]


def _condition(raw, options, path):
    _object(raw, ("field", "operator", "value"), path)
    field = raw.get("field")
    if not isinstance(field, str) or field not in OPERATORS:
        raise BoardQueryError(f"{path}.field", f"{path}.field is not a supported field.")
    op = raw.get("operator")
    if not isinstance(op, str) or op not in OPERATORS[field]:
        raise BoardQueryError(f"{path}.operator", f"{field} supports: {', '.join(OPERATORS[field])}.")
    value_path = f"{path}.value"
    value = raw.get("value")
    if op in LIST_OPERATORS:
        parsed = _values(field, value, options, value_path, allow_empty=False)
    elif field == "customerName":
        parsed = _text(value, value_path)
    elif field == "stageChangedAt":
        parsed = _range(value, _day, date.fromisoformat, value_path) if op == "between" else _day(value, value_path)
    elif field == "stageAgeDays":
        parsed = _age(value, value_path)
    else:
        parsed = _range(value, _amount, Decimal, value_path) if op == "between" else _amount(value, value_path)
    return {"field": field, "operator": op, "value": parsed}


def _text(value, path):
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > MAX_TEXT:
        raise BoardQueryError(path, f"{path} must be a non-empty string of at most {MAX_TEXT} characters.")
    return text


def _day(value, path):
    try:
        if not isinstance(value, str) or datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
            raise ValueError(value)
    except ValueError as exc:
        raise BoardQueryError(path, f"{path} must be a real YYYY-MM-DD date.") from exc
    return value


def _age(value, path):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_STAGE_AGE_DAYS:
        raise BoardQueryError(path, f"{path} must be a whole number of days from 0 to {MAX_STAGE_AGE_DAYS}.")
    return value


def _amount(value, path):
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(text, str) or not AMOUNT_PATTERN.fullmatch(text.strip()):
        raise BoardQueryError(path, f"{path} must be a non-negative decimal string with at most two decimals.")
    return format(Decimal(text.strip()).quantize(CENT), "f")


def _range(value, parse, typed, path):
    if not isinstance(value, list) or len(value) != 2:
        raise BoardQueryError(path, f"{path} must hold exactly two values.")
    low, high = parse(value[0], path), parse(value[1], path)
    if typed(low) > typed(high):
        raise BoardQueryError(path, f"{path} must start at or before its end.")
    return [low, high]


def _sort(value):
    if value is None:
        return dict(DEFAULT_SORT)
    _object(value, ("field", "direction"), "sort")
    return {
        "field": _choice(value.get("field"), SORT_FIELDS, "sort.field"),
        "direction": _choice(_or_default(value.get("direction"), "asc"), ("asc", "desc"), "sort.direction"),
    }


def _group_by(value, options):
    if value is None:
        return None
    _choice(value, GROUP_FIELDS, "groupBy")
    if value == "region":
        _require_regions(options, "groupBy")
    return value


def _columns(value):
    if not isinstance(value, list) or not value:
        raise BoardQueryError("columns", "columns must list at least one column.")
    if len(set(map(str, value))) != len(value):
        raise BoardQueryError("columns", "columns must not repeat a column.")
    for column in value:
        _choice(column, COLUMNS, "columns")
    return list(value)


# ---------------------------------------------------------------- rows

class BoardRow:
    """The public row plus the typed facts the query evaluates."""

    __slots__ = ("dto", "facts")

    def __init__(self, dto, facts):
        self.dto = dto
        self.facts = facts


def stamp(value):
    """A stored timestamp as an aware datetime; naive values are site (Shanghai) time."""

    if value in (None, ""):
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=SHANGHAI) if parsed.tzinfo is None else parsed


def utc_iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _calendar_day(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _clean(value):
    text = str(value or "").strip()
    return text or None


def _money(value):
    return Decimal(str(value or 0)).quantize(CENT)


def next_actions(actions):
    """Per Opportunity: the open, unarchived action due first; undated ones last, ties by ID."""

    best = {}
    for action in actions:
        if not open_action(action):
            continue
        due = _calendar_day(action.get("due"))
        key = (due is None, due or date.max, str(action["name"]))
        current = best.get(action["opportunity"])
        if current is None or key < current[0]:
            best[action["opportunity"]] = (key, {
                "id": action["name"], "title": action.get("title") or "",
                "due": due.isoformat() if due else None,
            })
    return {opportunity: value[1] for opportunity, value in best.items()}


def board_rows(opportunities, owner_names, actions, now, equipment=(), region_parents=None):
    """One row per Opportunity; ``now`` is the evaluation time (naive values are Shanghai time).

    ``equipment`` is the catalog: a stored type is shown and matched under the catalog spelling
    with the same key, so "NANSI" rows are "Nansi" rows. ``region_parents`` is the territory tree
    (name -> parent): a row matches a region condition through its region or a territory above it.
    """

    today = stamp(now).astimezone(SHANGHAI).date()
    upcoming = next_actions(actions)
    spellings = equipment_spellings(equipment)
    parents = region_parents or {}
    return [_row(opp, owner_names, upcoming.get(opp["name"]), today, spellings, parents) for opp in opportunities]


def _row(opp, owner_names, next_action, today, spellings, region_parents):
    changed = stamp(opp.get("stage_changed_at"))
    changed_day = changed.astimezone(SHANGHAI).date() if changed else None
    # A change recorded later today (or a declared day ahead of the clock) is day 0, not negative.
    age = max((today - changed_day).days, 0) if changed_day else None
    stale = opp["stage"] in OPEN_STAGES and age is not None and age > STALE_STAGE_DAYS
    # 0 is an amount nobody has entered yet (allowed at S1): the original amount goes out as "", as on
    # the Opportunity, and the CNY amount as None; neither is ever a 0.
    amount = _money(opp.get("amount"))
    amount_cny = _money(opp.get("amount_cny")) or None
    # A value outside the four levels (legacy data) counts as not set, like an empty one.
    level = opp.get("probability_level") if opp.get("probability_level") in PROBABILITY_LEVELS else None
    # The DocType requires an owner and an account, but the database does not; such rows still list.
    owner = opp.get("opportunity_owner") or ""
    account = opp.get("account") or ""
    customer_name = _clean(opp.get("customer_name")) or account
    equipment = canonical_equipment(_clean(opp.get("tool_type")), spellings)
    dto = {
        "id": opp["name"],
        "title": opp.get("title") or "",
        "accountId": account,
        "customerName": customer_name,
        "region": _clean(opp.get("region")),
        "salesId": owner,
        "salesName": owner_names.get(owner) or owner,
        "stage": opp["stage"],
        "stageChangedAt": utc_iso(changed) if changed else None,
        "stageAgeDays": age,
        "stageUnchangedOver21Days": stale,
        "probabilityLevel": level,
        "equipment": equipment,
        "market": _clean(opp.get("market")),
        "amount": format(amount, "f") if amount else "",
        "currency": opp.get("currency") or "",
        "amountCny": format(amount_cny, "f") if amount_cny is not None else None,
        "nextAction": next_action,
    }
    facts = {
        "id": dto["id"],
        "title": dto["title"],
        "customerName": customer_name,
        "region": dto["region"],
        # The region with the territories above it; empty without a region.
        "regionPath": frozenset((dto["region"], *ancestors(dto["region"], region_parents))) if dto["region"] else frozenset(),
        "market": dto["market"],
        "equipment": dto["equipment"],
        "sales": owner or None,
        "salesName": dto["salesName"],
        "stage": dto["stage"],
        "probabilityLevel": level or PENDING,
        "stageChangedAt": changed,
        "stageDay": changed_day,
        "stageAgeDays": age,
        "stale": stale,
        "unknownAge": opp["stage"] in OPEN_STAGES and age is None,
        "amountCny": amount_cny,
        "nextActionDue": _calendar_day(next_action["due"]) if next_action else None,
    }
    return BoardRow(dto, facts)


# ---------------------------------------------------------------- evaluation

def _predicate(condition):
    field, op, value = condition["field"], condition["operator"], condition["value"]
    if op in LIST_OPERATORS:
        listed = set(value)
        if field == "region":
            def inside(facts):
                return not listed.isdisjoint(facts["regionPath"])
        else:
            def inside(facts):
                return facts[field] in listed
        return inside if op == "in" else lambda facts: not inside(facts)
    if op == "contains":
        needle = value.casefold()
        return lambda facts: needle in facts["customerName"].casefold()
    if field == "stageChangedAt":
        if op == "between":
            low, high = (date.fromisoformat(day) for day in value)
            return lambda facts: facts["stageDay"] is not None and low <= facts["stageDay"] <= high
        day = date.fromisoformat(value)
        compare = operator.lt if op == "before" else operator.gt
        return lambda facts: facts["stageDay"] is not None and compare(facts["stageDay"], day)
    if field == "amountCny" and op == "between":
        low, high = (Decimal(amount) for amount in value)
        return lambda facts: facts["amountCny"] is not None and low <= facts["amountCny"] <= high
    target = Decimal(value) if field == "amountCny" else value
    compare = COMPARISONS[op]
    return lambda facts: facts[field] is not None and compare(facts[field], target)


def _matcher(query):
    scope = [
        _predicate({"field": SCOPE_FIELDS[key], "operator": "in", "value": values})
        for key, values in query["scope"].items() if values
    ]
    predicates = [_predicate(condition) for condition in query["conditions"]]
    combine = all if query["match"] == "all" else any

    def matches(facts):
        if not all(inside(facts) for inside in scope):
            return False
        return not predicates or combine(predicate(facts) for predicate in predicates)

    return matches


def _fold(value):
    return value.casefold() if value else None


def _probability_rank(level):
    return PROBABILITY_LEVELS.index(level) + 1 if level in PROBABILITY_LEVELS else None


def _stage_rank(stage):
    return OPPORTUNITY_STAGES.index(stage) if stage in OPPORTUNITY_STAGES else None


SORT_KEYS = {
    "customerName": lambda facts: facts["customerName"].casefold(),
    "title": lambda facts: facts["title"].casefold(),
    "region": lambda facts: _fold(facts["region"]),
    "sales": lambda facts: (facts["salesName"].casefold(), facts["sales"]) if facts["sales"] else None,
    "stage": lambda facts: _stage_rank(facts["stage"]),
    "stageChangedAt": lambda facts: facts["stageChangedAt"],
    "stageAgeDays": lambda facts: facts["stageAgeDays"],
    "probabilityLevel": lambda facts: _probability_rank(facts["probabilityLevel"]),
    "equipment": lambda facts: _fold(facts["equipment"]),
    "market": lambda facts: _fold(facts["market"]),
    "amountCny": lambda facts: facts["amountCny"],
    "nextAction": lambda facts: facts["nextActionDue"],
}


def _ordered(items, key, descending, identity):
    """Known values in the requested direction, unknown ones last, ties by ``identity`` ascending."""

    items = sorted(items, key=identity)
    known = [item for item in items if key(item) is not None]
    unknown = [item for item in items if key(item) is None]
    known.sort(key=key, reverse=descending)  # Python's sort stays stable when reversed.
    return known + unknown


def _group_label(field, key, sample):
    if field == "sales":
        return sample.facts["salesName"] if key is not None else NOT_SET_LABEL
    if field == "stage":
        return STAGE_LABELS.get(key, key)
    if field == "probabilityLevel":
        return PROBABILITY_LABELS[key]
    return key if key is not None else NOT_SET_LABEL


def _totals(rows):
    known = [row.facts["amountCny"] for row in rows if row.facts["amountCny"] is not None]
    return {
        "count": len(rows),
        "knownAmountCny": format(sum(known, Decimal(0)).quantize(CENT), "f"),
        "missingAmountCount": len(rows) - len(known),
    }


def build_board(rows, query):
    """Every matching row in page order, the totals over all of them, and the group totals."""

    matches = _matcher(query)
    matched = [row for row in rows if matches(row.facts)]
    sort_key = SORT_KEYS[query["sort"]["field"]]
    descending = query["sort"]["direction"] == "desc"
    ordered = _ordered(matched, lambda row: sort_key(row.facts), descending, lambda row: row.facts["id"])
    groups = []
    field = query["groupBy"]
    if field:
        buckets = {}
        for row in ordered:
            buckets.setdefault(row.facts[field], []).append(row)
        group_key = SORT_KEYS[field]
        keys = _ordered(
            list(buckets), lambda key: group_key(buckets[key][0].facts),
            descending and query["sort"]["field"] == field, lambda key: (key is None, str(key or "")),
        )
        ordered = [row for key in keys for row in buckets[key]]
        groups = [
            {"key": key, "label": _group_label(field, key, buckets[key][0]), **_totals(buckets[key])}
            for key in keys
        ]
    summary = {
        **_totals(matched),
        "stageUnchangedOver21DaysCount": sum(1 for row in matched if row.facts["stale"]),
        "unknownStageAgeCount": sum(1 for row in matched if row.facts["unknownAge"]),
        "byProbability": [
            {"level": level, **_totals([row for row in matched if row.facts["probabilityLevel"] == level])}
            for level in PROBABILITY_FILTER_LEVELS
        ],
    }
    return ordered, summary, groups
