"""Manager-only Review business service; no browser-side table access."""
from __future__ import annotations

from datetime import datetime

import frappe
from rayher_crm.services.action_statuses import OPEN_ACTION_STATUSES

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
from rayher_crm.services import cockpit_target_rules as target_rules, territory_admin
from rayher_crm.services.territories import region_tree
from rayher_crm.services.warning_handling import FIELDS as HANDLING_FIELDS, HANDLING, REVISION, REVISION_FIELDS, handling_records

TARGET = "CRM Cockpit Target"


def require_manager():
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Review is available to CRM Managers only.")


def read(doctype, fields, filters=None):
    return [dict(row) for row in frappe.get_all(doctype, fields=fields.split(), filters=filters or {}, limit_page_length=0)]


def linked(doctype, fields, field, names, **filters):
    return read(doctype, fields, {field: ["in", list(names)], **filters}) if names else []


def options():
    meta = frappe.get_meta("Customer")
    region = meta.get_field("custom_crm_region")
    segment = meta.get_field("custom_crm_segment")
    regions = [v.strip() for v in (region.options or "").splitlines() if v.strip()] if region else []
    markets = [v.strip() for v in (segment.options or "").splitlines() if v.strip()] if segment else []
    # An archived Account (a Manager's archive, in place of a delete) is out of the cockpit with everything
    # under it: the figures below are keyed on these ids.
    customers = read("Customer", "name customer_name custom_crm_region custom_crm_segment", {"custom_crm_archived": 0})
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
    opportunity_fields = "name creation title account source_lead opportunity_owner stage amount currency lost_at lost_at_stage lost_reason tool_type po_date"
    cny_amount_ready = bool(frappe.get_meta("CRM Opportunity").has_field("amount_cny"))
    if cny_amount_ready:
        opportunity_fields += " amount_cny"
    # An archived Opportunity (a Manager's archive, in place of a delete) is out of every figure and warning,
    # with its bookings, stages, actions and plans, which are all keyed on these ids.
    opps = linked("CRM Opportunity", opportunity_fields, "account", ids, archived=0)
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
    quotation_opportunities = [{"name": r["name"], "stage": r.get("stage"), "tool_type": r.get("tool_type"), "archived": 0} for r in opps if r["name"] in quote_opp_ids]
    # The archive flag travels with the stage: a quotation of an archived Opportunity is no expiry warning
    # (quotation_expiry leaves it out, as it leaves a closed deal's out), and the KPI stays whole.
    quotation_opportunities += linked("CRM Opportunity", "name stage tool_type archived", "name", quote_opp_ids - opp_ids)
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
        "customers": customers, "people": people, "opportunities": opps, "events": event_rows(ids),
        "bookings": bookings, "booking_dates_ready": booking_dates_ready,
        "cny_amount_ready": cny_amount_ready,
        "history": linked("CRM Opportunity History", "name creation opportunity at field from_value to_value from_owner to_owner", "opportunity", opp_ids),
        "stages": stages,
        "actions": linked("CRM Opportunity Action", "name creation opportunity title action_owner due status archived completed_at", "opportunity", opp_ids),
        "probabilities": linked("CRM Opportunity Probability History", probability_fields, "opportunity", opp_ids),
        "recoveries": linked("CRM Probability Recovery", "name opportunity probability_change plan action_taken acted_by acted_at", "opportunity", opp_ids),
        "loss_reviews": linked("CRM Opportunity Loss Review", "name opportunity stage_event review_status review_category review_note reviewed_by reviewed_at reopened_at modified", "opportunity", opp_ids),
        "visits": visits,
        "leads": leads,
        "requests": requests,
        "equipment_opportunities": linked("CRM Opportunity", "name tool_type", "name", moved_ids),
        "evaluations": evaluations,
        "tests": linked("CRM Test Run", "name creation evaluation run_date test_round status", "evaluation", {r["name"] for r in evaluations}),
        "quotes": quotes, "quotation_opportunities": quotation_opportunities,
        "followups": linked("CRM Quotation Follow Up", "name parent creation title due status completed_at completed_owner completed_version", "parent", {r["name"] for r in quotes}),
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
    result = build_review(data, query, now, coverage, limits["quote_expiry_days"][0], limits["stage6_no_po_days"][0], limits["stalled_days"][0], limits["stall_escalation_days"][0])
    result["filters"] = filters
    attach_targets(result, query, customers=customers)
    result["conversions"], conversion_details = build_conversions(
        data, query, now, coverage, frappe.conf.get("crm_cockpit_conversion_threshold", 45))
    result["_details"].update(conversion_details)
    result["pipelineCoverage"] = pipeline_coverage(result)
    from rayher_crm.services.demo_resources import warning_summary
    result["demoResources"] = warning_summary(query)
    resource_risks = result["demoResources"]
    result["warnings"].append({"key": "demo_resources", "count": metric(resource_risks["count"],
        "insufficient" if resource_risks["unknown"] else "ready", "missing_resource_schedule" if resource_risks["unknown"] else None)})
    from rayher_crm.services.blue_sheet import warning_rows
    result["_details"]["red_flags"] = warning_rows(data["opportunities"], customers, query)
    result["warnings"].append({"key": "red_flags", "count": metric(len(result["_details"]["red_flags"]))})
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
              "closeDateSlipItems": details["close_date_slip"],
              "redFlagItems": details["red_flags"],
              "closeDateSlipHandledItems": details["close_date_slip_handled"],
              "demoResources": result["demoResources"],
              # S6 deals with a recorded action whose follow-up day is still ahead: listed, never counted.
              "stage6NoPoHandledItems": details["stage6_no_po_handled"]}
    result["names"] = _names(result)
    return result


def _names(result):
    """Display names for everyone the page shows: reviewers and plan editors are usually Managers
    and action owners may be engineers, none of whom are in the Sales filter list."""
    handled = ("overdue", "quotationExpiryItems", "stage6NoPoItems", "stage6NoPoHandledItems", "closeDateSlipItems", "closeDateSlipHandledItems")
    users = {r.get("owner") for key in ("lost", "lostBacklog", "overdue", "downgrade", "quotationExpiryItems", "stage6NoPoItems", "stage6NoPoHandledItems", "closeDateSlipItems", "closeDateSlipHandledItems") for r in result[key]}
    for record in (r.get("handling") or {} for key in handled for r in result[key]):
        users |= {record.get("planBy"), record.get("actedBy")} | {h.get("actor") for h in record.get("history", [])}
    users |= {r.get("actionOwner") for r in result["overdue"]} | {r.get("currentOwner") for r in result["downgrade"]}
    users |= {(r.get("review") or {}).get("reviewedBy") for r in result["lost"] + result["lostBacklog"]}
    users |= {(r.get("recovery") or {}).get("editedBy") for r in result["downgrade"]}
    users |= {row.get("owner") for row in result.get("redFlagItems", [])}
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


def event_rows(account_ids):
    # Keep native row permissions while limiting the database result to this
    # customer scope plus standalone events. Notes are not cockpit facts.
    scope = [["account", "is", "not set"]]
    if account_ids:
        scope.append(["account", "in", sorted(account_ids)])
    fields = "name title event_owner start_date end_date status account opportunity region market equipment completed_at completed_owner creation"
    return [dict(row) for row in frappe.get_list("CRM Event", or_filters=scope,
                                                fields=fields.split(), limit_page_length=0)]


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
    opps = [r for r in linked("CRM Opportunity", opportunity_fields, "account", ids, archived=0) if r["stage"] in OPEN_STAGES]
    evaluations = linked("CRM Evaluation",
                         "name account demo_request title status test_run_deadline "
                         "wafer_preparation_status test_preparation_status", "account", ids)
    actions = read("CRM Opportunity Action", "name opportunity title action_owner due status archived",
                   {"opportunity": ["in", [r["name"] for r in opps]], "status": ["in", list(OPEN_ACTION_STATUSES)], "archived": 0}) if opps else []
    # Action assignees can be engineers or managers. Keep their labels separate
    # from the CRM Sales filter and fetch them in one batch, never once per row.
    action_owner_ids = {r["action_owner"] for r in actions if r.get("action_owner")}
    visits = read("CRM Visit", "name account opportunity visit_owner subject visit_date status",
                  {"account": ["in", list(ids)], "status": "Planned"}) if ids else []
    requests = linked("CRM Demo Request", "name account sales_owner opportunity status", "account", ids)
    quotes = linked("CRM Quotation", "name ref_no account opportunity quotation_owner status current_version current_published_version planned_send_date", "account", ids)
    quote_ids = {r["name"] for r in quotes}
    # A Quotation of an archived Opportunity is frozen with it (no send, no follow-up): read without its deal, it
    # leaves Plan as a closed deal's does.
    quotation_opportunities = linked("CRM Opportunity", "name stage tool_type", "name", {r["opportunity"] for r in quotes if r.get("opportunity")}, archived=0)
    versions = linked("CRM Quotation Version", "name quotation status currency total", "quotation", quote_ids)
    followups = linked("CRM Quotation Follow Up", "name parent creation title due status completed_at completed_owner completed_version", "parent", quote_ids)
    events = event_rows(ids)
    unlisted_ids = {r["opportunity"] for r in (*visits, *requests, *events) if r.get("opportunity")} - {r["name"] for r in opps}
    return {
        "customers": customers, "people": people, "opportunities": opps, "cny_amount_ready": cny_amount_ready, "events": events,
        "quotes": quotes, "versions": versions, "followups": followups, "quotation_opportunities": quotation_opportunities,
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
    data["equipment_labels"] = filters["equipment"]
    result = build_plan(data, {**query, "includeOverdue": include_overdue}, frappe.utils.now_datetime())
    result["filters"] = filters
    return result


def get_plan(query):
    result = calculate_plan(query)
    from rayher_crm.services.plan_commitments import attach
    attach(result, query)
    result.pop("_details")
    return result


def get_plan_details(query):
    key = str(query.get("metric") or "all")
    if key not in PLAN_METRICS:
        raise CrmApiException("VALIDATION_ERROR", "Unknown Plan metric.")
    result = calculate_plan(query)
    rows = result["_details"][key]
    group = query.get("equipmentGroup")
    if group is not None:
        if group not in {row["id"] for row in result["equipmentGroups"]}:
            raise CrmApiException("VALIDATION_ERROR", "Unknown equipment summary group.")
        rows = [row for row in rows if row["equipmentGroup"] == group]
    items, total, page, size = paginate_items(rows, {"page": query.get("page"), "pageSize": query.get("pageSize") or 50})
    return {"items": items, "total": total, "page": page, "pageSize": size, "asOf": result["asOf"]}


def target_dto(row):
    return {"id": row["name"], "sales": row.get("sales_owner") or "", "scope": "territory" if row.get("target_scope") == "Territory" else "sales",
            "territory": row.get("territory") or "", "metric": row["metric"], "period": row["period"],
            "anchor": str(row["anchor"]), "value": str(row["target_value"]), "modified": to_iso_timestamp(row["modified"])}


def targetable_sales():
    from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE
    roles = {}
    for row in read("Has Role", "parent role", {"parenttype": "User", "role": ["in", list(CRM_ROLE_TO_PROFILE)]}):
        roles.setdefault(row["parent"], set()).add(row["role"])
    candidates = {owner for owner, assigned in roles.items() if assigned == {"CRM Sales"}}
    return {row["name"] for row in linked("User", "name enabled", "name", candidates) if row["enabled"]}


def target_rows(where="", values=(), *, limit=None):
    # MariaDB's User identity comparison also accepts legacy casing. Expose the
    # canonical Link without rewriting a target or its audit history on a GET.
    return [target_dto(r) for r in frappe.db.sql("""SELECT t.name, t.target_scope,
        COALESCE(u.name, t.sales_owner) AS sales_owner, t.territory, t.metric,
        t.period, t.anchor, t.target_value, t.modified
        FROM `tabCRM Cockpit Target` t LEFT JOIN `tabUser` u ON u.name=t.sales_owner"""
        + (" WHERE " + where if where else "") + (" LIMIT 2" if limit == 2 else ""), values, as_dict=True)]


def period_target_rows(kind, anchor, *, orders_year=None):
    """Materialize only this period and the latest applicable weekly defaults.

    Keep all ties: duplicate business keys must remain visibly insufficient.
    User Link comparisons/grouping use the database's native identity collation.
    """
    rows = target_rows("t.period=%s AND t.anchor=%s AND t.metric IN %s "
                       "AND COALESCE(NULLIF(t.target_scope, ''), 'Sales')='Sales'",
                       (kind, anchor, tuple(ACTIVITIES)))
    if kind == "week":
        rows += target_rows("""t.period='weekly_default' AND t.metric IN %s
            AND COALESCE(NULLIF(t.target_scope, ''), 'Sales')='Sales'
            AND (t.sales_owner, t.metric, t.anchor) IN (
                SELECT sales_owner, metric, MAX(anchor) FROM `tabCRM Cockpit Target`
                WHERE period='weekly_default' AND anchor<=%s
                  AND COALESCE(NULLIF(target_scope, ''), 'Sales')='Sales'
                GROUP BY sales_owner, metric)""", (tuple(ACTIVITIES), anchor))
    if orders_year is not None:
        rows += target_rows("t.metric='orders' AND t.period='year' AND t.anchor=%s", (f"{orders_year}-01-01",))
    return rows


def get_target(query):
    """An exact editor key, independent of the period currently being reviewed."""
    require_manager()
    scope = query.get("scope") or "sales"
    owner, territory = query.get("sales") or "", query.get("territory") or ""
    key, kind = query.get("metric"), query.get("period")
    if (scope not in ("sales", "territory") or not isinstance(owner, str) or not isinstance(territory, str)
            or not isinstance(key, str) or key not in (*ACTIVITIES, "orders")
            or not isinstance(kind, str) or kind not in ("week", "month", "quarter", "year", "weekly_default")
            or (key == "orders" and kind != "year")
            or (scope == "sales" and (not owner or territory))
            or (scope == "territory" and (not territory or owner or key != "orders"))):
        raise CrmApiException("VALIDATION_ERROR", "Choose a valid target owner, metric and period.")
    try:
        anchor = datetime.strptime(query.get("anchor", ""), "%Y-%m-%d").date()
        start, _ = bounds("week" if kind == "weekly_default" else kind, anchor)
        if anchor != start:
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "Target anchor must be the first day of its period.") from exc
    rows = target_rows("""COALESCE(NULLIF(t.target_scope, ''), 'Sales')=%s
        AND COALESCE(t.sales_owner, '')=%s AND COALESCE(t.territory, '')=%s
        AND t.metric=%s AND t.period=%s AND t.anchor=%s""",
        ("Sales" if scope == "sales" else "Territory", owner, territory, key, kind, anchor), limit=2)
    if len(rows) > 1:
        raise CrmApiException("CONFLICT", "Duplicate targets exist for this period; reconcile them before saving.")
    return rows[0] if rows else None


def attach_targets(result, query, *, customers=None):
    start = result["period"]["start"]
    kind = result["period"]["kind"]
    year = stamp(result["period"]["asOf"]).year
    rows = period_target_rows(kind, start, orders_year=year)
    tree = territory_admin.tree_rows()
    leaves = sorted(r["name"] for r in tree if not r.get("is_group"))
    # Match the target editor/save eligibility, keeping historical filter choices
    # independent. Only an activity's own outside contributors affect its target.
    members = targetable_sales()
    result["targetOptions"] = {"territories": leaves, "teamMembers": sorted(members)}
    not_allocated = {**metric(None, "not_applicable", "targets_not_allocated_to_scope"), "record": None}
    personal = [r for r in rows if r["scope"] == "sales" and r["sales"] == query.get("sales")]
    unallocated = bool(query.get("market") or query.get("equipment"))

    for item in result["activities"]:
        owners = {r.get("owner") or "__unknown_sales_owner__" for r in result.get("_details", {}).get(item["key"], [])}
        item["target"] = (dict(not_allocated) if unallocated or query.get("region") else
                          target_rules.target(personal, item["key"], kind, start) if query.get("sales") else
                          target_rules.aggregate(rows, members | owners, item["key"], kind, start, "sales", non_targetable=owners - members))
    anchor = f"{year}-01-01"
    if unallocated or (query.get("sales") and query.get("region")):
        result["orders"]["target"] = dict(not_allocated)
    elif query.get("sales"):
        result["orders"]["target"] = {**target_rules.target(personal, "orders", "year", anchor), "scope": "sales"}
    else:
        regions, unmapped = target_rules.territory_members(tree, query.get("region"), [r.get("custom_crm_region") for r in customers or []])
        # Legacy parent targets cannot turn a Customer stored on a group into a valid leaf allocation.
        region_targets = [r for r in rows if r["scope"] == "territory" and r["territory"] in leaves]
        result["orders"]["target"] = target_rules.aggregate(region_targets, regions, "orders", "year", anchor, "territory")
        result["targetOptions"]["unmappedRegions"] = unmapped
    result["targets"] = rows
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
    scope = payload.get("scope") or "sales"
    if not isinstance(scope, str) or scope not in {"sales", "territory"}:
        raise CrmApiException("VALIDATION_ERROR", "Choose a sales or territory target.")
    if not isinstance(key, str) or not isinstance(kind, str) or key not in {*ACTIVITIES, "orders"} or kind not in {"week", "month", "quarter", "year", "weekly_default"} or (key == "orders" and kind != "year"):
        raise CrmApiException("VALIDATION_ERROR", "Invalid target metric or period.")
    territory = payload.get("territory") or ""
    if scope == "territory":
        if not isinstance(territory, str) or owner or key != "orders" or kind != "year":
            raise CrmApiException("VALIDATION_ERROR", "Territory targets are annual orders on a leaf region, without a sales owner.")
    elif not isinstance(owner, str) or not owner or territory:
        raise CrmApiException("VALIDATION_ERROR", "A sales owner is required, without a territory allocation.")
    # An atomic upsert serializes first inserts and updates for this transaction.
    # Take it before either scope's locks: assignments take User then catalogue,
    # so catalogue -> Series -> User would create a three-transaction cycle.
    # Series has no owner/modified_by fields scanned by User.after_rename;
    # locking a DocType row here before User would invert native rename locks.
    frappe.db.sql("""INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, 0)
        ON DUPLICATE KEY UPDATE `current`=`current`""", ("rayher_crm.cockpit_target_write_lock",))
    if scope == "territory":
        territory_admin.lock_catalogue()
        nodes = territory_admin.tree_rows(for_update=True)
        if not any(r["name"] == territory and not r.get("is_group") for r in nodes):
            raise CrmApiException("VALIDATION_ERROR", "Choose a leaf territory; parent totals are calculated.")
    else:
        from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE
        user = frappe.db.get_value("User", owner, ["name", "enabled"], as_dict=True, for_update=True)
        if not user or not user.enabled:
            raise CrmApiException("VALIDATION_ERROR", "Choose an enabled user with exactly the CRM Sales role.")
        owner = user.name
        roles = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='User' FOR UPDATE", (owner,), pluck=True)
        if {r for r in roles if r in CRM_ROLE_TO_PROFILE} != {"CRM Sales"}:
            raise CrmApiException("VALIDATION_ERROR", "Choose an enabled user with exactly the CRM Sales role.")
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
    # Links change during User/Territory rename; target IDs and Version records
    # must survive. Include legacy empty Sales scope in the current business key.
    matches = frappe.db.sql("""SELECT name FROM `tabCRM Cockpit Target`
        WHERE COALESCE(NULLIF(target_scope, ''), 'Sales')=%s
          AND COALESCE(sales_owner, '')=%s AND COALESCE(territory, '')=%s
          AND metric=%s AND period=%s AND anchor=%s FOR UPDATE""",
        ("Sales" if scope == "sales" else "Territory", owner if scope == "sales" else "", territory, key, kind, anchor), pluck=True)
    if len(matches) > 1:
        raise CrmApiException("CONFLICT", "Duplicate targets exist for this period; reconcile them before saving.")
    exists = bool(matches)
    # A reused old email must not collide with a renamed user's retained ID.
    name = matches[0] if exists else frappe.generate_hash(length=32)
    if exists:
        if not expected_modified:
            raise CrmApiException("CONFLICT", "This target already exists. Reload before editing.")
        doc = lock_document(TARGET, name, expected_modified, "NOT_FOUND")
        doc = frappe.get_doc(TARGET, name, for_update=True)
        if scope == "sales":
            doc.target_scope = "Sales"
            doc.sales_owner = owner
    else:
        if expected_modified:
            raise CrmApiException("CONFLICT", "This target no longer exists. Reload before saving.")
        doc = frappe.get_doc({"doctype": TARGET, "name": name, "sales_owner": owner if scope == "sales" else None,
                              "target_scope": "Sales" if scope == "sales" else "Territory", "territory": territory or None,
                              "metric": key, "period": kind, "anchor": anchor})
    doc.target_value = format(value, ".2f")
    doc.changed_by = frappe.session.user
    if exists:
        # Target edits always retain the native audit diff, including in the
        # Frappe test runner which otherwise disables Version creation.
        doc.save(ignore_permissions=True, ignore_version=False)
    else:
        doc.insert(ignore_permissions=True)
    return target_dto(doc.as_dict())
