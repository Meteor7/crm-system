"""Read-only stage-history ratios and pipeline coverage for Review."""
from decimal import Decimal

from rayher_crm.services.cockpit_metrics import (
    covered, field_at, grouped, in_region, insufficient, iso, metric, month_shift, number, period, stamp,
)
from rayher_crm.services.equipment_names import equipment_key
from rayher_crm.services.opportunity_stages import MILESTONE_STAGES, OPEN_STAGES

CONVERSIONS = tuple(zip(MILESTONE_STAGES[:4], MILESTONE_STAGES[1:5])) + (("quotation_sent", "po_received"),)


def conversion_threshold(value):
    parsed = number(value)
    return parsed if parsed is not None and parsed <= 100 else Decimal(45)


def build_conversions(data, query, now, coverage, threshold=45):
    """SPEC 4.2 divides distinct stage arrivals, not current funnel populations.

    Count each stage's arrivals independently inside the 24-calendar-month window.
    A later-stage arrival can originate before that window, so do not cap at 100%
    or silently replace this formula with a same-cohort calculation.
    """
    now = stamp(now)
    at = period(query, now)["as_of"]
    start = stamp(month_shift(at.date(), -24))
    threshold = conversion_threshold(threshold)
    customers = {row["name"]: row for row in data["customers"]}
    field_history = grouped(data["history"], "opportunity")
    selected = {}
    owner_unknown = False
    for opportunity in data["opportunities"]:
        customer = customers.get(opportunity.get("account"))
        if not customer or stamp(opportunity["creation"]) > at:
            continue
        if not in_region(query, customer):
            continue
        if query.get("market") and customer.get("custom_crm_segment") != query["market"]:
            continue
        if query.get("equipment") and equipment_key(opportunity.get("tool_type")) != equipment_key(query["equipment"]):
            continue
        owner = field_at(opportunity, "opportunity_owner", at, field_history.get(opportunity["name"], []), coverage, now)
        if query.get("sales") and not owner:
            owner_unknown = True
            continue
        if query.get("sales") and owner != query["sales"]:
            continue
        selected[opportunity["name"]] = (opportunity, customer, owner)

    reached = {stage: {} for stage in MILESTONE_STAGES}
    uncertain = False
    for event in data["stages"]:
        context = selected.get(event.get("opportunity"))
        stage = event.get("to_stage")
        if not context or stage not in reached:
            continue
        try:
            when = stamp(event.get("reached_at"))
            recorded = stamp(event.get("recorded_at"))
        except (ValueError, TypeError, OverflowError):
            uncertain = True
            continue
        if event.get("reached_at_basis") not in {"recorded", "declared", "evidence"} or not when:
            # Migration recorded_at is import time; reached_at is the business upper bound.
            upper_bound = when if event.get("reached_at_basis") == "upper_bound" and when else recorded
            if not upper_bound or upper_bound >= start:
                uncertain = True
            continue
        if not start <= when <= at:
            continue
        opportunity, customer, owner = context
        row = {"id": opportunity["name"], "title": opportunity["title"], "accountId": opportunity["account"],
               "customer": customer.get("customer_name") or opportunity["account"], "owner": owner,
               "at": iso(when), "kind": "opportunity", "stage": stage, "eventId": event.get("name")}
        previous = reached[stage].get(opportunity["name"])
        if not previous or when > stamp(previous["at"]):
            reached[stage][opportunity["name"]] = row

    complete = covered(coverage, "stage", start) and not uncertain and not owner_unknown
    if query.get("sales") and at < now and not covered(coverage, "fields", at):
        complete = False
    rows = []
    for source, destination in CONVERSIONS:
        denominator, numerator = len(reached[source]), len(reached[destination])
        raw_rate = Decimal(numerator) * 100 / denominator if denominator else None
        if not complete:
            rate = insufficient("stage_history_incomplete")
        elif denominator == 0:
            rate = metric(None, "not_applicable", "no_source_stage")
        else:
            rate = metric(format(raw_rate, ".2f"))
        rows.append({"fromStage": source, "toStage": destination, "fromCount": denominator, "toCount": numerator,
                     "rate": rate, "bottleneck": raw_rate < threshold if rate["state"] == "ready" else None})
    raw_coverage = coverage.get("stage")
    try:
        verified_from = iso(stamp(raw_coverage))
    except (ValueError, TypeError, OverflowError):
        verified_from = None
    details = {f"reached_{stage}": sorted(records.values(), key=lambda row: (stamp(row["at"]), row["id"]), reverse=True)
               for stage, records in reached.items()}
    return {"start": start.date().isoformat(), "end": at.date().isoformat(), "verifiedFrom": verified_from,
            "complete": complete, "thresholdPercent": float(threshold), "items": rows}, details


def pipeline_coverage(review):
    """Reuse the identical S2-S6 amounts, YTD bookings and scope-specific target."""
    amounts = [row["amount"] for row in review["pipeline"] if row["key"] in OPEN_STAGES[1:]]
    total = metric(format(sum((number(row["value"]) for row in amounts), Decimal(0)), ".2f")) \
        if len(amounts) == 5 and all(row["state"] == "ready" and number(row["value"]) is not None for row in amounts) \
        else insufficient("pipeline_amount_incomplete")
    target, actual = review["orders"]["target"], review["orders"]["actual"]
    remaining = metric(None, target["state"], target.get("reason"))
    if target["state"] == "ready":
        remaining = metric(None, actual["state"], actual.get("reason"))
        if actual["state"] == "ready":
            target_value, actual_value = number(target["value"]), number(actual["value"])
            remaining = metric(format(target_value - actual_value, ".2f")) \
                if target_value is not None and actual_value is not None else insufficient("order_amount_incomplete")
    ratio = metric(None, remaining["state"], remaining.get("reason"))
    if remaining["state"] == "ready":
        difference = Decimal(remaining["value"])
        if difference <= 0:
            ratio = metric(None, "not_applicable", "annual_target_met")
        elif total["state"] != "ready":
            ratio = insufficient("pipeline_amount_incomplete")
        else:
            ratio = metric(format(Decimal(total["value"]) / difference, ".2f"))
    return {"openPipeline": total, "remainingTarget": remaining, "ratio": ratio, "referenceMin": 3, "referenceMax": 4,
            "targetScope": target.get("scope"), "targetState": target["state"]}
