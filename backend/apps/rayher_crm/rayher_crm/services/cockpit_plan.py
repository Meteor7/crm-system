"""Plan calculations: what is scheduled in a period, read from the current records.

Pure functions, like cockpit_metrics, so the counting rules can be tested without Frappe.
Plan never replays history: a future period has no past, and a past period shows what is
still open in it today.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from rayher_crm.services.cockpit_metrics import bounds, in_region, insufficient, iso, metric, number, stamp, supported_bounds
from rayher_crm.services.equipment_names import equipment_key
from rayher_crm.services.opportunity_stages import OPEN_STAGES, PROBABILITY_LEVELS
from rayher_crm.services.activities import DEMO_PLANNED, activity_facts, open_action, cny_quote_value

KINDS = ("visits", "tests", "quotes", "followups", "actions", "po", "events")
PLAN_METRICS = ("all", *KINDS, "overdue", "tests_other", "quotation_carryover", "scheduled_activities")
# Both preparations are complete in Scheduled; Testing remains a plan until review.
PLAN_EVALUATION_STATUSES = DEMO_PLANNED


def plan_period(query):
    kind = query.get("period") or "week"
    start, end = supported_bounds(kind, date.fromisoformat(query["anchor"]))
    previous_start, _ = bounds(kind, start - timedelta(days=1))
    return {"kind": kind, "start": start, "end": end - timedelta(days=1),
            "previousAnchor": previous_start.isoformat(), "nextAnchor": end.isoformat()}


def day_of(value):
    when = stamp(value)
    return when.date() if when else None


def cny_amount(opp, cny_amount_ready):
    """Review's current-value rule: the CNY amount Sales entered, never a conversion."""
    if not cny_amount_ready:
        return None
    value = number(opp.get("amount_cny"))
    return format(value, ".2f") if value is not None and value > 0 else None


def money(rows):
    """CNY only, as in Review. A row without a CNY amount is left out and reported, never added as 0."""
    known = [Decimal(r["amount"]) for r in rows if r.get("amount") is not None]
    amounts = [{"currency": "CNY", "value": format(sum(known, Decimal(0)), ".2f")}] if known else []
    return {"poAmounts": amounts, "poAmountIncomplete": len(known) < len(rows)}


def build_plan(data, query, now):
    facts = activity_facts(data, {}, now)
    planned = {key: [f for f in facts if f["metric"] == key and not f["done"]] for key in ("visits", "tests", "actions")}
    sources = {key: {r["name"]: r for r in data[key]} for key in ("visits", "evaluations", "actions")}
    window = plan_period(query)
    start, end = window["start"], window["end"]
    customers = {r["name"]: r for r in data["customers"]}
    opportunities = {r["name"]: r for r in data["opportunities"]}
    requests = {r["name"]: r for r in data["requests"]}
    action_names = {r["name"]: (r.get("full_name") or "").strip() or None for r in data.get("action_people", [])}
    owner_filter = query.get("sales")
    # Equipment belongs to the opportunity, as in Review: visits and Demo tests count only through the
    # opportunity they are linked to; those without one are left out and reported.
    equipment_filter = equipment_key(query.get("equipment"))
    equipment_of = {name: equipment_key(tool_type) for name, tool_type in
                    {**data.get("equipment", {}), **{r["name"]: r.get("tool_type") for r in [*data["opportunities"], *data.get("quotation_opportunities", [])]}}.items()}
    unclassified = {"visits": 0, "tests": 0}

    def equipment_ok(opportunity_id):
        return not equipment_filter or bool(opportunity_id and equipment_of.get(opportunity_id) == equipment_filter)
    rows = {key: [] for key in (*KINDS, "overdue", "tests_other")}
    undated = {key: [] for key in (*KINDS, "overdue")}

    def in_scope(account, owner):
        customer = customers.get(account)
        return bool(customer and (not owner_filter or owner == owner_filter)
                    and (not query.get("market") or customer.get("custom_crm_segment") == query["market"])
                    and in_region(query, customer))

    def equipment_identity(opportunity=None, standalone=None):
        key = equipment_of.get(opportunity) if opportunity else equipment_key(standalone)
        return f"equipment:{key}" if key else "unclassified"

    def missing_date(key, account, owner, opportunity=None):
        undated[key].append({"equipmentGroup": equipment_identity(opportunity), "salesOwner": owner or None,
                             "market": customers[account].get("custom_crm_segment") or None})

    def item(kind, record, account, owner, day, status, **extra):
        customer = customers[account]
        return {"id": record["name"], "kind": kind,
                "title": record.get("title") or record.get("subject") or record["name"],
                "accountId": account, "customer": customer.get("customer_name") or account,
                "date": day.isoformat() if day else None, "salesOwner": owner or None,
                "market": customer.get("custom_crm_segment") or None,
                "status": status, "carryover": False, "equipmentGroup": equipment_identity(extra.get("opportunityId")), **extra}

    for fact in planned["visits"]:
        row = sources["visits"][fact["sourceId"]]
        if row["status"] != "Planned" or not in_scope(row["account"], row.get("visit_owner")):
            continue
        if equipment_filter and not row.get("opportunity"):
            # Report only what this period would have shown, like the Review counts.
            day = day_of(fact["plannedAt"])
            if day is not None and start <= day <= end:
                unclassified["visits"] += 1
            continue
        if not equipment_ok(row.get("opportunity")):
            continue
        day = day_of(fact["plannedAt"])
        if day is None:
            missing_date("visits", row["account"], row.get("visit_owner"), row.get("opportunity"))
        elif start <= day <= end:
            extra = {"opportunityId": row["opportunity"]} if row.get("opportunity") else {}
            rows["visits"].append(item("visits", row, row["account"], row.get("visit_owner"), day, "Planned", **extra))

    for fact in planned["tests"]:
        evaluation = sources["evaluations"][fact["sourceId"]]
        if evaluation.get("status") not in PLAN_EVALUATION_STATUSES:
            continue
        # Match the preparation UI's legacy fallback: absent flags in Scheduled/Testing
        # mean completed, while an explicit Pending flag still means not ready.
        if any(evaluation.get(f"{branch}_preparation_status") == "Pending" for branch in ("wafer", "test")):
            continue
        request = requests.get(evaluation.get("demo_request"), {})
        if request.get("status") == "Cancelled":
            continue
        account, owner = request.get("account") or evaluation.get("account"), request.get("sales_owner")
        if not in_scope(account, owner):
            continue
        if equipment_filter and not request.get("opportunity"):
            unclassified["tests"] += 1
            continue
        if not equipment_ok(request.get("opportunity")):
            continue
        # One active Demo, regardless of Test Run count/results or its deadline.
        # Keep an absent/original deadline; never invent a day to make it fit the calendar.
        day = day_of(fact["plannedAt"])
        demo_key = "tests" if day is not None and start <= day <= end else "tests_other"
        rows[demo_key].append(item("tests", evaluation, account, owner, day, evaluation["status"],
                                  evaluationId=evaluation["name"],
                                  **({"opportunityId": request["opportunity"]} if request.get("opportunity") else {})))

    quotes = {r["name"]: r for r in data.get("quotes", [])}
    versions = {r["name"]: r for r in data.get("versions", [])}

    quote_opportunities = {**opportunities, **{r["name"]: r for r in data.get("quotation_opportunities", [])}}

    def quote_in_scope(quote):
        return (in_scope(quote.get("account"), quote.get("quotation_owner"))
                and equipment_ok(quote.get("opportunity"))
                and (not quote.get("opportunity") or quote_opportunities.get(quote["opportunity"], {}).get("stage") in OPEN_STAGES))

    for quote in quotes.values():
        version = versions.get(quote.get("current_version"), {})
        if not quote_in_scope(quote) or version.get("status") != "Draft":
            continue
        day = day_of(quote.get("planned_send_date"))
        if day and day <= end:
            amount = cny_quote_value(version)
            entry = item("quotes", quote, quote["account"], quote.get("quotation_owner"), day, "Draft",
                         quotationId=quote["name"], quotationVersionId=version["name"],
                         amount=amount, currency="CNY" if amount is not None else None,
                         **({"opportunityId": quote["opportunity"]} if quote.get("opportunity") else {}))
            entry["title"] = quote.get("ref_no") or quote["name"]
            if day < start:
                entry["carryover"] = True
                rows["overdue"].append(entry)
            else:
                rows["quotes"].append(entry)

    for followup in data.get("followups", []):
        quote = quotes.get(followup.get("parent"), {})
        version = versions.get(quote.get("current_published_version"), {})
        if followup.get("status") != "Open" or not quote_in_scope(quote) or version.get("status") not in {"Published", "Expired"}:
            continue
        day = day_of(followup.get("due"))
        if not day:
            missing_date("followups", quote["account"], quote.get("quotation_owner"), quote.get("opportunity"))
            missing_date("overdue", quote["account"], quote.get("quotation_owner"), quote.get("opportunity"))
        elif day <= end:
            entry = item("followups", followup, quote["account"], quote.get("quotation_owner"), day, "Open",
                         quotationId=quote["name"], **({"opportunityId": quote["opportunity"]} if quote.get("opportunity") else {}))
            if day < start:
                entry["carryover"] = True
                rows["overdue"].append(entry)
            else:
                rows["followups"].append(entry)

    for fact in planned["actions"]:
        row = sources["actions"][fact["sourceId"]]
        opp = opportunities.get(row["opportunity"])
        if not open_action(row) or not opp or opp.get("stage") not in OPEN_STAGES:
            continue
        owner = opp.get("opportunity_owner")
        if not in_scope(opp["account"], owner) or not equipment_ok(opp["name"]):
            continue
        day = day_of(fact["plannedAt"])
        if day is None:
            missing_date("actions", opp["account"], owner, opp["name"])
            missing_date("overdue", opp["account"], owner, opp["name"])
        elif day <= end:
            entry = item("actions", row, opp["account"], owner, day, row["status"],
                         actionOwner=row.get("action_owner") or None,
                         actionOwnerName=action_names.get(row.get("action_owner")), opportunityId=opp["name"])
            if day < start:
                # Carried over with its own due date; never part of this period's action count.
                rows["overdue"].append({**entry, "carryover": True})
            else:
                rows["actions"].append(entry)

    for event in data.get("events", []):
        if event.get("status") != "Planned":
            continue
        owner, account = event.get("event_owner"), event.get("account")
        customer = customers.get(account, {}) if account else {"custom_crm_region": event.get("region"), "custom_crm_segment": event.get("market")}
        if (account and not in_scope(account, owner)) or (owner_filter and owner != owner_filter):
            continue
        if not in_region(query, customer) or (query.get("market") and customer.get("custom_crm_segment") != query["market"]):
            continue
        if equipment_filter and (not equipment_ok(event.get("opportunity")) if account else equipment_key(event.get("equipment")) != equipment_filter):
            continue
        first, last = day_of(event.get("start_date")), day_of(event.get("end_date"))
        if not first or not last or last < first:
            undated["events"].append({"equipmentGroup": equipment_identity(event.get("opportunity"), event.get("equipment") if not account else None), "salesOwner": owner or None, "market": customer.get("custom_crm_segment") or None})
        elif first <= end and last >= start:
            rows["events"].append({"id": event["name"], "kind": "events", "title": event["title"],
                "accountId": account or "", "customer": customer.get("customer_name") or account or "",
                "salesOwner": owner or None, "market": customer.get("custom_crm_segment") or None,
                "date": max(first, start).isoformat(), "startDate": first.isoformat(), "endDate": last.isoformat(),
                "status": "Planned", "carryover": False,
                "equipmentGroup": equipment_identity(event.get("opportunity"), event.get("equipment") if not account else None),
                **({"opportunityId": event["opportunity"]} if event.get("opportunity") else {})})

    for opp in data["opportunities"]:
        owner = opp.get("opportunity_owner")
        if opp.get("stage") not in OPEN_STAGES or not in_scope(opp["account"], owner) or not equipment_ok(opp["name"]):
            continue
        # An Opportunity without an expected PO date is simply not scheduled in any period.
        day = day_of(opp.get("po_date"))
        if day is None or not start <= day <= end:
            continue
        # S1 has no reliable amount yet: it is counted, and its amount reported as missing.
        amount = None if opp["stage"] == OPEN_STAGES[0] else cny_amount(opp, data.get("cny_amount_ready"))
        level = opp.get("probability_level")
        rows["po"].append(item("po", opp, opp["account"], owner, day, opp["stage"], opportunityId=opp["name"],
                               amount=amount, currency="CNY" if amount is not None else None,
                               probabilityLevel=level if level in PROBABILITY_LEVELS else None))

    order = {kind: index for index, kind in enumerate(KINDS)}
    for key in rows:
        rows[key].sort(key=lambda r: (r["date"] or "9999-12-31", order[r["kind"]], r["id"]))

    def count(key, selected=None):
        if any(selected is None or selected(r) for r in undated[key]):
            return insufficient("missing_date")
        return metric(len(rows[key] if selected is None else [r for r in rows[key] if selected(r)]))

    def activities(selected):
        if any(selected(r) for key in ("visits", "tests", "quotes", "followups", "actions", "events") for r in undated[key]):
            return insufficient("missing_date")
        return metric(sum(1 for key in ("visits", "tests", "quotes", "followups", "actions", "events") for r in rows[key] if selected(r)))

    people = {r["name"]: r.get("full_name") or r["name"] for r in data["people"]}
    current = [r for key in KINDS for r in rows[key]]
    # A rep or market whose only records lack a date still gets its row, so the gap is visible.
    gaps = [r for key in KINDS for r in undated[key]]
    owners = sorted({r["salesOwner"] for r in (*current, *gaps)}, key=lambda value: (value is None, value or ""))
    sales = []
    for owner in owners:
        mine = lambda r, owner=owner: r["salesOwner"] == owner
        sales.append({"id": owner, "name": people.get(owner, owner) if owner else "",
                      **{key: count(key, mine) for key in KINDS},
                      **money([r for r in rows["po"] if mine(r)])})
    names = sorted({r["market"] for r in (*current, *gaps)}, key=lambda value: (value is None, value or ""))
    markets = []
    for name in names:
        here = lambda r, name=name: r["market"] == name
        markets.append({"name": name, "activities": activities(here), "po": count("po", here),
                        **money([r for r in rows["po"] if here(r)])})

    # Each source has one canonical platform identity. Missing equipment is a
    # real group; it is not allocated to every registered platform.
    group_names = {f"equipment:{equipment_key(name)}": name for name in data.get("equipment_labels", []) if equipment_key(name)}
    equipment_groups = []
    for group in sorted({r["equipmentGroup"] for r in (*current, *gaps)}):
        here = lambda r, group=group: r["equipmentGroup"] == group
        equipment_groups.append({"id": group, "name": group_names.get(group, group.removeprefix("equipment:")) if group != "unclassified" else None,
                                 "activities": activities(here), "po": count("po", here),
                                 **money([r for r in rows["po"] if here(r)])})

    details = {key: rows[key] for key in (*KINDS, "overdue", "tests_other")}
    details["scheduled_activities"] = [row for row in current if row["kind"] != "po"]
    details["quotation_carryover"] = [row for row in rows["overdue"] if row["kind"] in {"quotes", "followups"}]
    # Carryover first, then the period in date order.
    carryover = rows["overdue"] if query.get("includeOverdue", True) else []
    details["all"] = carryover + sorted(current + rows["tests_other"], key=lambda r: (r["date"] or "9999-12-31", order[r["kind"]], r["id"]))
    return {"period": {"kind": window["kind"], "start": start.isoformat(), "end": end.isoformat(),
                       "previousAnchor": window["previousAnchor"], "nextAnchor": window["nextAnchor"]},
            "asOf": iso(now),
            "summary": {key: count(key) for key in KINDS}, "overdue": count("overdue"),
            "otherDemos": metric(len(rows["tests_other"])),
            "quotationCarryover": insufficient("missing_date") if undated["followups"] else metric(len(details["quotation_carryover"])),
            "quoteAmounts": money(rows["quotes"])["poAmounts"], "quoteAmountIncomplete": money(rows["quotes"])["poAmountIncomplete"],
            **money(rows["po"]), "sales": sales, "markets": markets, "equipmentGroups": equipment_groups,
            "expectedPO": {"items": rows["po"][:5], "total": len(rows["po"])},
            # Only under an equipment filter: planned visits and active Demo tests with no opportunity.
            "equipmentUnclassified": unclassified if equipment_filter else None,
            "_details": details}
