"""Manager-only Review business service; no browser-side table access."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.services.common import as_payload, paginate_items, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.opportunity_stages import OPEN_STAGES
from rayher_crm.services.cockpit_metrics import (
    ACTIVITIES, bounds, build_review, metric, number, period, stamp,
)
from rayher_crm.services.cockpit_plan import PLAN_METRICS, build_plan, plan_period
from rayher_crm.services.cockpit_conversion import build_conversions, pipeline_coverage
from rayher_crm.services.equipment import equipment_key, list_equipment_types
from rayher_crm.services.cockpit_settings import thresholds
from rayher_crm.services import territory_tree
from rayher_crm.services.territories import region_tree
from rayher_crm.services.warning_handling import FIELDS as HANDLING_FIELDS, HANDLING, REVISION, REVISION_FIELDS, handling_records

TARGET = "CRM Cockpit Target"


def require_manager():
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Review is available to CRM Managers only.")


def read(doctype, fields, filters=None):
    return [dict(row) for row in frappe.get_all(doctype, fields=fields.split(), filters=filters or {}, limit_page_length=0)]


def linked(doctype, fields, field, names):
    return read(doctype, fields, {field: ["in", list(names)]}) if names else []


def options():
    meta = frappe.get_meta("Customer")
    region = meta.get_field("custom_crm_region")
    segment = meta.get_field("custom_crm_segment")
    regions = [v.strip() for v in (region.options or "").splitlines() if v.strip()] if region else []
    markets = [v.strip() for v in (segment.options or "").splitlines() if v.strip()] if segment else []
    customers = read("Customer", "name customer_name custom_crm_region custom_crm_segment")
    ready = bool(frappe.conf.get("crm_cockpit_region_migration_verified") and region and region.fieldtype == "Select"
                 and regions and all(not r.get("custom_crm_region") or r["custom_crm_region"] in regions for r in customers))
    sales_ids = {r["parent"] for r in read("Has Role", "parent", {"role": "CRM Sales", "parenttype": "User"})}
    people = linked("User", "name full_name", "name", sales_ids)
    # The region filter lists the sales territory tree, each territory before the ones below it, then the
    # regions no territory is named after; regionParents is the parent of each name that has one.
    names, parents = region_tree(regions) if ready else ([], {})
    return customers, people, {"sales": [{"id": r["name"], "name": r["full_name"] or r["name"]} for r in people],
                              "markets": markets, "regions": names, "regionParents": parents, "regionReady": ready,
                              # The same catalog as the Opportunities board; equipment is an opportunity field.
                              # A legacy type of only punctuation ("-") has no comparison key, so it cannot filter.
                              "equipment": [t for t in list_equipment_types() if equipment_key(t)]}


def load_data(customers, people):
    ids = {r["name"] for r in customers}
    opportunity_fields = "name creation title account source_lead opportunity_owner stage amount currency lost_at lost_at_stage lost_reason tool_type"
    cny_amount_ready = bool(frappe.get_meta("CRM Opportunity").has_field("amount_cny"))
    if cny_amount_ready:
        opportunity_fields += " amount_cny"
    opps = linked("CRM Opportunity", opportunity_fields, "account", ids)
    opp_ids = {r["name"] for r in opps}

    def activity_sources(doctype, fields):
        # Source accounts are snapshots and can differ after an Opportunity moves.
        # Keep these facts for stall detection; activity KPIs still filter by source account.
        return list({row["name"]: row for row in (
            *linked(doctype, fields, "account", ids), *linked(doctype, fields, "opportunity", opp_ids)
        )}.values())
    booking_meta = frappe.get_meta("CRM Booking")
    booking_dates_ready = bool(booking_meta.has_field("actual_po_date"))
    # A CNY order's amount is already in CNY; another currency needs the entered amount_cny (5c44a82).
    booking_fields = "name source source_opportunity status actual_po_date booking_owner amount currency"
    if booking_meta.has_field("amount_cny"):
        booking_fields += " amount_cny"
    bookings = linked("CRM Booking", booking_fields, "source_opportunity", opp_ids) if booking_dates_ready else []
    quotes = activity_sources("CRM Quotation", "name creation account quotation_owner ref_no status opportunity current_published_version")
    # A quotation keeps its customer snapshot when its opportunity changes customer.
    # Fetch linked stage only, even outside the customer filter; do not widen the
    # opportunity set used by any other Review metric.
    quote_opp_ids = {r["opportunity"] for r in quotes if r.get("opportunity")}
    quotation_opportunities = [{"name": r["name"], "stage": r.get("stage"), "tool_type": r.get("tool_type")} for r in opps if r["name"] in quote_opp_ids]
    quotation_opportunities += linked("CRM Opportunity", "name stage tool_type", "name", quote_opp_ids - opp_ids)
    probability_fields = "name opportunity from_level to_level changed_at actor"
    if frappe.get_meta("CRM Opportunity Probability History").has_field("reason"):
        probability_fields += " reason"
    stages = linked("CRM Opportunity Stage History", "name creation opportunity from_stage to_stage source event recorded_at reached_at reached_at_basis reference_doctype reference_name reason", "opportunity", opp_ids)
    leads = linked("Lead", "name creation lead_owner custom_crm_status custom_crm_converted_at custom_crm_converted_account custom_crm_converted_opportunity", "custom_crm_converted_opportunity", opp_ids)
    missing_lead_ids = {r["reference_name"] for r in stages if r["event"] == "lead_converted" and r.get("reference_doctype") == "Lead"} - {r["name"] for r in leads}
    leads += linked("Lead", "name creation lead_owner custom_crm_status custom_crm_converted_at custom_crm_converted_account custom_crm_converted_opportunity", "name", missing_lead_ids)
    visits = activity_sources("CRM Visit", "name creation account opportunity visit_owner subject visit_date status customer_kind completed_at")
    requests = activity_sources("CRM Demo Request", "name creation account sales_owner opportunity")
    evaluations = list({row["name"]: row for row in (
        *linked("CRM Evaluation", "name creation account demo_request", "account", ids),
        *linked("CRM Evaluation", "name creation account demo_request", "demo_request", {r["name"] for r in requests})
    )}.values())
    # Equipment of a linked opportunity now at another customer (usually none: links start at one customer).
    moved_ids = {r["opportunity"] for r in (*visits, *requests) if r.get("opportunity")} - opp_ids - quote_opp_ids
    handling_fields = " ".join(HANDLING_FIELDS)
    handlings = list({r["name"]: r for r in (*linked(HANDLING, handling_fields, "opportunity", opp_ids),
                                             *linked(HANDLING, handling_fields, "source_id", {r["name"] for r in quotes}))}.values())
    return {
        "customers": customers, "people": people, "opportunities": opps,
        "bookings": bookings, "booking_dates_ready": booking_dates_ready,
        "cny_amount_ready": cny_amount_ready,
        "history": linked("CRM Opportunity History", "name creation opportunity at field from_value to_value", "opportunity", opp_ids),
        "stages": stages,
        "actions": linked("CRM Opportunity Action", "name creation opportunity title action_owner due status archived completed_at", "opportunity", opp_ids),
        "probabilities": linked("CRM Opportunity Probability History", probability_fields, "opportunity", opp_ids),
        "recoveries": linked("CRM Probability Recovery", "name opportunity probability_change plan action_taken acted_by acted_at", "opportunity", opp_ids),
        "loss_reviews": linked("CRM Opportunity Loss Review", "name opportunity stage_event review_status review_note reviewed_by reviewed_at reopened_at modified", "opportunity", opp_ids),
        "visits": visits,
        "leads": leads,
        "requests": requests,
        "equipment_opportunities": linked("CRM Opportunity", "name tool_type", "name", moved_ids),
        "evaluations": evaluations,
        "tests": linked("CRM Test Run", "name creation evaluation run_date test_round status", "evaluation", {r["name"] for r in evaluations}),
        "quotes": quotes, "quotation_opportunities": quotation_opportunities,
        "versions": linked("CRM Quotation Version", "name quotation version_no published_at account quotation_owner status valid_until currency total", "quotation", {r["name"] for r in quotes}),
        # Next steps and S6 actions Managers recorded on Warnings rows (overdue, quotation expiry, S6).
        "warning_handlings": handling_records(handlings, linked(REVISION, " ".join(REVISION_FIELDS), "handling", {r["name"] for r in handlings})),
    }


def scoped(query):
    """Validated filters, the customers they select and the stable filter options.

    The region filter names a region or a sales territory; a territory selects the customers of every region
    below it. The regions it covers are added to the query as "regions" for the rules that check a customer.
    """
    customers, people, filters = options()
    if query["region"] and (not filters["regionReady"] or query["region"] not in filters["regions"]):
        raise CrmApiException("VALIDATION_ERROR", "Region migration is not verified or region is invalid.")
    if query["market"] and query["market"] not in filters["markets"]:
        raise CrmApiException("VALIDATION_ERROR", "Invalid market.")
    if query.get("equipment") and query["equipment"] not in filters["equipment"]:
        raise CrmApiException("VALIDATION_ERROR", "Invalid equipment type.")
    if query["sales"] and query["sales"] not in {r["id"] for r in filters["sales"]}:
        raise CrmApiException("VALIDATION_ERROR", "Invalid sales owner.")
    if query["region"]:
        query["regions"] = territory_tree.covered(query["region"], filters["regions"], filters["regionParents"])
    customers = [r for r in customers if (not query["region"] or r["custom_crm_region"] in query["regions"])
                 and (not query["market"] or r["custom_crm_segment"] == query["market"])]
    return customers, people, filters


def calculate(query):
    require_manager()
    query = {key: str(query.get(key) or "").strip() for key in ("period", "anchor", "sales", "market", "region", "equipment")}
    now = frappe.utils.now_datetime()
    try:
        period(query, now)
    except (ValueError, TypeError, OverflowError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "Invalid Review period or anchor.") from exc
    customers, people, filters = scoped(query)
    coverage = frappe.conf.get("crm_cockpit_history_complete_from") or {}
    if not isinstance(coverage, dict):
        coverage = {}
    # Days before a quotation expires, and days a deal may stay in internal validation (S6) without a PO,
    # before Warnings flags them: the Manager's settings page, else site config, else 14 and 30.
    limits = thresholds()
    data = load_data(customers, people)
    result = build_review(data, query, now, coverage, limits["quote_expiry_days"][0], limits["stage6_no_po_days"][0])
    result["filters"] = filters
    attach_targets(result, query)
    result["conversions"], conversion_details = build_conversions(
        data, query, now, coverage, frappe.conf.get("crm_cockpit_conversion_threshold", 45))
    result["_details"].update(conversion_details)
    result["pipelineCoverage"] = pipeline_coverage(result)
    return result


def get_review(query):
    result = calculate(query)
    result.pop("_details")
    return result


def _with_editable_plans(rows):
    """Give each pending downgrade what the meeting needs to edit its plan in place: the plan
    version, its last editor and the Opportunity version the save is checked against."""
    from rayher_crm.services.probability_recovery import plans_for_opportunities

    ids = sorted({row["id"] for row in rows})
    if not ids:
        return rows
    plans = plans_for_opportunities(ids)
    versions = {r.name: to_iso_timestamp(r.modified) for r in frappe.get_all(
        "CRM Opportunity", filters={"name": ["in", ids]}, fields=["name", "modified"])}
    result = []
    for row in rows:
        plan = plans.get(row.get("eventId"))
        latest = plan["history"][0] if plan and plan["history"] else None
        recovery = dict(row["recovery"]) if row.get("recovery") else None
        if recovery is not None and plan:
            recovery.update(id=plan["id"], modified=plan["modified"],
                            editedBy=latest["actor"] if latest else None, editedAt=latest["at"] if latest else None)
        result.append({**row, "recovery": recovery, "opportunityModified": versions.get(row["id"])})
    return result


def get_warnings(query):
    """The Warnings page: every row behind the Review banner counts, same scope and period.

    Without an anchor it is the current period: the post-mortem card on a deal the daily notices point
    at, and the Plan and Board tabs, send a Manager here for this week's rows, whereas Review (period())
    defaults to the last completed week.
    """
    if not str(query.get("anchor") or "").strip():
        query = {**query, "anchor": frappe.utils.now_datetime().date().isoformat()}
    result = calculate(query)
    details = result["_details"]
    # Stall detection needs 35 days of action history; without it a row is "unknown", never "not stalled".
    stalled_known = result["stalled"]["count"]["state"] == "ready"
    stalled = {r["id"] for r in details["stalled"]}
    result = {"period": result["period"], "filters": result["filters"], "warnings": result["warnings"],
              "quotationExpiry": result["quotationExpiry"],
              "lost": details["lost"],
              "lostBacklog": details["lost_backlog"],
              "overdue": [{**row, "stalled": (row["id"] in stalled) if stalled_known else None} for row in details["overdue"]],
              "downgrade": _with_editable_plans(details["downgrade"]),
              "quotationExpiryItems": details["quotation_expiry"],
              "stage6NoPo": result["stage6NoPo"],
              "stage6NoPoItems": details["stage6_no_po"],
              # S6 deals with a recorded action whose follow-up day is still ahead: listed, never counted.
              "stage6NoPoHandledItems": details["stage6_no_po_handled"]}
    result["names"] = _names(result)
    return result


def _names(result):
    """Display names for everyone the page shows: reviewers and plan editors are usually Managers
    and action owners may be engineers, none of whom are in the Sales filter list."""
    handled = ("overdue", "quotationExpiryItems", "stage6NoPoItems", "stage6NoPoHandledItems")
    users = {r.get("owner") for key in ("lost", "lostBacklog", "overdue", "downgrade", "quotationExpiryItems", "stage6NoPoItems", "stage6NoPoHandledItems") for r in result[key]}
    for record in (r.get("handling") or {} for key in handled for r in result[key]):
        users |= {record.get("planBy"), record.get("actedBy")} | {h.get("actor") for h in record.get("history", [])}
    users |= {r.get("actionOwner") for r in result["overdue"]} | {r.get("currentOwner") for r in result["downgrade"]}
    users |= {(r.get("review") or {}).get("reviewedBy") for r in result["lost"] + result["lostBacklog"]}
    users |= {(r.get("recovery") or {}).get("editedBy") for r in result["downgrade"]}
    users = sorted(u for u in users if u)
    if not users:
        return {}
    return {r.name: r.full_name or r.name for r in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"])}


def get_details(query):
    result = calculate(query)
    key = query.get("metric")
    if key not in result["_details"]:
        raise CrmApiException("VALIDATION_ERROR", "Unknown Review metric.")
    items, total, page, size = paginate_items(result["_details"][key], query)
    return {"items": items, "total": total, "page": page, "pageSize": size, "asOf": result["period"]["asOf"]}


def load_plan_data(customers, people, equipment=False):
    """Only what is still open today; Plan reads the current schedule, never history.

    ``equipment``: also read the equipment of opportunities that visits and Demo tests link to
    but that are not in the open list (closed, or now at another customer); only an equipment filter needs them.
    """
    ids = {r["name"] for r in customers}
    opportunity_fields = "name title account opportunity_owner stage po_date probability_level tool_type"
    cny_amount_ready = bool(frappe.get_meta("CRM Opportunity").has_field("amount_cny"))
    if cny_amount_ready:
        opportunity_fields += " amount_cny"
    opps = [r for r in linked("CRM Opportunity", opportunity_fields, "account", ids) if r["stage"] in OPEN_STAGES]
    evaluations = linked("CRM Evaluation",
                         "name account demo_request title status test_run_deadline "
                         "wafer_preparation_status test_preparation_status", "account", ids)
    actions = read("CRM Opportunity Action", "name opportunity title action_owner due status archived",
                   {"opportunity": ["in", [r["name"] for r in opps]], "status": "Open", "archived": 0}) if opps else []
    # Action assignees can be engineers or managers. Keep their labels separate
    # from the CRM Sales filter and fetch them in one batch, never once per row.
    action_owner_ids = {r["action_owner"] for r in actions if r.get("action_owner")}
    visits = read("CRM Visit", "name account opportunity visit_owner subject visit_date status",
                  {"account": ["in", list(ids)], "status": "Planned"}) if ids else []
    requests = linked("CRM Demo Request", "name account sales_owner opportunity status", "account", ids)
    unlisted_ids = {r["opportunity"] for r in (*visits, *requests) if r.get("opportunity")} - {r["name"] for r in opps} if equipment else set()
    return {
        "customers": customers, "people": people, "opportunities": opps, "cny_amount_ready": cny_amount_ready,
        "visits": visits,
        "requests": requests,
        "evaluations": evaluations,
        "actions": actions,
        "action_people": linked("User", "name full_name", "name", action_owner_ids),
        # Visits and Demo tests can point at opportunities that are no longer open, or now at another customer.
        "equipment": {r["name"]: r.get("tool_type") for r in linked("CRM Opportunity", "name tool_type", "name", unlisted_ids)},
    }


def calculate_plan(query):
    require_manager()
    include_overdue = str(query.get("includeOverdue", True)).lower() not in ("false", "0")
    query = {key: str(query.get(key) or "").strip() for key in ("period", "anchor", "sales", "market", "region", "equipment")}
    try:
        plan_period(query)
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "Invalid Plan period or anchor.") from exc
    customers, people, filters = scoped(query)
    data = load_plan_data(customers, people, equipment=bool(query["equipment"]))
    result = build_plan(data, {**query, "includeOverdue": include_overdue}, frappe.utils.now_datetime())
    result["filters"] = filters
    return result


def get_plan(query):
    result = calculate_plan(query)
    result.pop("_details")
    return result


def get_plan_details(query):
    key = str(query.get("metric") or "all")
    if key not in PLAN_METRICS:
        raise CrmApiException("VALIDATION_ERROR", "Unknown Plan metric.")
    result = calculate_plan(query)
    items, total, page, size = paginate_items(result["_details"][key], {"page": query.get("page"), "pageSize": query.get("pageSize") or 50})
    return {"items": items, "total": total, "page": page, "pageSize": size, "asOf": result["asOf"]}


def target_dto(row):
    return {"id": row["name"], "sales": row["sales_owner"], "metric": row["metric"], "period": row["period"],
            "anchor": str(row["anchor"]), "value": str(row["target_value"]), "modified": to_iso_timestamp(row["modified"])}


def attach_targets(result, query):
    # Individual targets are per person only: never split by market, region or equipment.
    applicable = bool(query["sales"] and not query["market"] and not query["region"] and not query.get("equipment"))
    rows = read(TARGET, "name sales_owner metric period anchor target_value modified", {"sales_owner": query["sales"]}) if query["sales"] else []
    start = result["period"]["start"]
    kind = result["period"]["kind"]

    def find(key, kind, anchor):
        matches = [r for r in rows if r["metric"] == key and r["period"] == kind and str(r["anchor"]) == anchor]
        if not matches and kind == "week":
            matches = sorted([r for r in rows if r["metric"] == key and r["period"] == "weekly_default" and str(r["anchor"]) <= anchor], key=lambda r: str(r["anchor"]), reverse=True)
        if not applicable:
            return {**metric(None, "not_applicable"), "record": None}
        return {**metric(str(matches[0]["target_value"]) if matches else None, "ready" if matches else "not_set"),
                "record": target_dto(matches[0]) if matches else None}

    for item in result["activities"]:
        item["target"] = find(item["key"], kind, start)
    year = stamp(result["period"]["asOf"]).year
    result["orders"]["target"] = find("orders", "year", f"{year}-01-01")
    result["targets"] = [target_dto(r) for r in rows]
    annual = result["orders"]["target"]["value"]
    day = stamp(result["period"]["asOf"]).date()
    elapsed = (day - datetime(year, 1, 1).date()).days + 1
    days = (datetime(year + 1, 1, 1) - datetime(year, 1, 1)).days
    result["orders"]["planned"] = metric(format(number(annual) * elapsed / days, ".2f")) if annual is not None else metric(None, result["orders"]["target"]["state"])
    result["orders"]["elapsedFraction"] = elapsed / days


def save_target(payload, expected_modified=None):
    require_manager()
    payload = as_payload(payload)
    owner, key, kind = payload.get("sales"), payload.get("metric"), payload.get("period")
    if key not in {*ACTIVITIES, "orders"} or kind not in {"week", "month", "quarter", "year", "weekly_default"} or (key == "orders" and kind != "year"):
        raise CrmApiException("VALIDATION_ERROR", "Invalid target metric or period.")
    if not isinstance(owner, str) or not frappe.db.exists("Has Role", {"parent": owner, "parenttype": "User", "role": "CRM Sales"}):
        raise CrmApiException("VALIDATION_ERROR", "A sales owner is required.")
    if not frappe.db.get_value("User", owner, "enabled"):
        raise CrmApiException("VALIDATION_ERROR", "The sales owner is disabled.")
    value = number(payload.get("value"))
    if value is None or value > number("999999999999.99") or (key != "orders" and value != value.to_integral_value()) or value.as_tuple().exponent < -2:
        raise CrmApiException("VALIDATION_ERROR", "Target must be a non-negative count or a CNY amount with at most two decimals.")
    try:
        anchor = datetime.strptime(payload.get("anchor", ""), "%Y-%m-%d").date()
        start, _ = bounds("week" if kind == "weekly_default" else kind, anchor)
        if anchor != start:
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "Target anchor must be the first day of its period.") from exc
    if kind == "weekly_default" and anchor <= frappe.utils.now_datetime().date():
        raise CrmApiException("VALIDATION_ERROR", "Default weekly targets take effect from a future Monday.")
    name = sha256(f"{owner}|{key}|{kind}|{anchor}".encode()).hexdigest()[:32]
    # Serialize creates as well as updates. The stable unique key prevents duplicate goals.
    frappe.db.get_value("User", owner, "name", for_update=True)
    exists = frappe.db.exists(TARGET, name)
    if exists:
        if not expected_modified:
            raise CrmApiException("CONFLICT", "This target already exists. Reload before editing.")
        doc = lock_document(TARGET, name, expected_modified, "NOT_FOUND")
    else:
        if expected_modified:
            raise CrmApiException("CONFLICT", "This target no longer exists. Reload before saving.")
        doc = frappe.get_doc({"doctype": TARGET, "name": name, "sales_owner": owner, "metric": key, "period": kind, "anchor": anchor})
    doc.target_value = format(value, ".2f")
    doc.changed_by = frappe.session.user
    if exists:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    return target_dto(doc.as_dict())
