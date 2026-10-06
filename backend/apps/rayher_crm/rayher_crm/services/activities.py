"""One source fact per business activity; no database reads or invented historical dates.

The caller supplies records already limited to the user's current scope. Facts retain
source IDs so Review, Plan and query readers can use the same identity and business time.
Current-state corrections, reopening and cancellation change the current activity fact;
the source's audit history remains authoritative for what was recorded previously.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rayher_crm.services.cockpit_history import action_json, field_at, grouped, iso, stamp, substantive


VISIT_DONE = frozenset({"Visited", "Minutes Submitted", "Manager Reviewed"})
DEMO_PLANNED = frozenset({"Scheduled", "Testing"})
ACTION_DONE_HISTORY = frozenset({"Done", "Completed"})


def unique_records(rows):
    """A source joined through two associations remains one record."""
    return list({row["name"]: row for row in rows}.values())


def open_action(row):
    return row.get("status") == "Open" and not row.get("archived")


def cny_quote_value(version):
    if version.get("currency") != "CNY":
        return None
    try:
        value = Decimal(str(version.get("total")))
        return format(value, ".2f") if value.is_finite() and value >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def audited_action_completion(action, histories):
    """Recover only the evidenced start of the current Done cycle, never due/modified.

    Reverse through same-status edits until the actual transition. A broken status
    chain cannot establish when the current completion happened.
    """
    if action.get("status") != "Done":
        return None
    for row in sorted(histories, key=lambda r: (stamp(r["at"]), str(r.get("creation", "")), r.get("name", "")), reverse=True):
        if row.get("field") not in {"actionCreated", "actionUpdated"}:
            continue
        after = action_json(row.get("to_value"))
        before = action_json(row.get("from_value"))
        if not after:
            # A broken newer row may hide a reopening/new completion cycle.
            # Never walk past evidence about this action (or an unidentified row).
            if not before or before["id"] == action["name"]:
                return None
            continue
        if after["id"] != action["name"]:
            if before and before["id"] == action["name"]:
                return None
            continue
        if after.get("status") not in ACTION_DONE_HISTORY:
            return None
        if row["field"] == "actionCreated":
            return stamp(row["at"])
        if not before or before["id"] != action["name"] or not before.get("status"):
            return None
        if before["status"] not in ACTION_DONE_HISTORY:
            return stamp(row["at"])
    return None


def completion_before_coverage(fact, coverage, histories):
    """Whether an undated legacy action is bounded by the complete action audit.

    This does not invent a completion date. A pre-coverage action still Done, with
    no later creation/reopening/completion in the complete audit, was already Done
    at the coverage boundary. Missing/broken audit snapshots cannot establish that.
    """
    if fact["sourceDoctype"] != "CRM Opportunity Action":
        return False
    try:
        boundary = stamp(coverage.get("actions"))
    except (ValueError, TypeError):
        return False
    created = stamp(fact.get("recordedAt"))
    if not boundary or not created or created > boundary:
        return False
    for row in histories:
        if row.get("field") not in {"actionCreated", "actionUpdated"} or stamp(row["at"]) < boundary:
            continue
        after = action_json(row.get("to_value"))
        before = action_json(row.get("from_value"))
        if not after:
            return False
        if after["id"] != fact["sourceId"]:
            if before and before["id"] == fact["sourceId"]:
                return False
            continue
        if row["field"] == "actionCreated" or not before or before["id"] != fact["sourceId"]:
            return False
        if before.get("status") not in ACTION_DONE_HISTORY or after.get("status") not in ACTION_DONE_HISTORY:
            return False
    return True


def activity_facts(data, coverage, now):
    now = stamp(now)
    opportunities = {r["name"]: r for r in data.get("opportunities", [])}
    histories = grouped(data.get("history", []), "opportunity")
    facts = []

    def add(record, doctype, metric, kind, account, owner, opportunity=None, *, done=False,
            occurred=None, planned=None, event=None, recorded=None, **extra):
        facts.append({"id": record["name"], "sourceDoctype": doctype, "sourceId": record["name"],
                      "sourceKey": f"{doctype}:{record['name']}", "status": record.get("status") or record.get("custom_crm_status"),
                      "eventId": event or record["name"], "metric": metric, "kind": kind,
                      "title": record.get("title") or record.get("subject") or record.get("ref_no") or record["name"],
                      "accountId": account, "owner": owner, "opportunityId": opportunity,
                      "done": done, "plannedAt": iso(planned), "occurredAt": iso(occurred) if done else None,
                      "recordedAt": iso(recorded or record.get("creation")),
                      "createdAt": iso(record.get("creation")),
                      "timeBasis": "business" if occurred and done else "unknown",
                      "customerKind": None, **extra})

    for visit in unique_records(data.get("visits", [])):
        status = visit.get("status")
        if status not in VISIT_DONE and status != "Planned":
            continue
        add(visit, "CRM Visit", "visits", "visit", visit.get("account"), visit.get("visit_owner"), visit.get("opportunity"),
            done=status in VISIT_DONE, occurred=visit.get("visit_date"), planned=visit.get("visit_date"), recorded=visit.get("completed_at"),
            customerKind={"Existing": "existing", "Prospect": "prospect"}.get(visit.get("customer_kind")))

    conversions = {r["reference_name"]: r for r in sorted(data.get("stages", []), key=lambda r: str(r.get("reached_at") or ""), reverse=True)
                   if r.get("event") == "lead_converted" and r.get("reference_doctype") == "Lead" and r.get("reached_at")}
    for lead in unique_records(data.get("leads", [])):
        event = conversions.get(lead["name"], {})
        when = lead.get("custom_crm_converted_at") or event.get("reached_at")
        if not when and lead.get("custom_crm_status") != "Converted":
            continue
        opp = opportunities.get(lead.get("custom_crm_converted_opportunity") or event.get("opportunity"), {})
        owner = field_at(opp, "opportunity_owner", stamp(when), histories.get(opp.get("name"), []), coverage, now) if when and opp else None
        add(lead, "Lead", "leads", "lead", lead.get("custom_crm_converted_account") or opp.get("account"), owner,
            opp.get("name"), done=True, occurred=when, event=event.get("name"), recorded=event.get("recorded_at"))

    requests = {r["name"]: r for r in data.get("requests", [])}
    evaluations = {r["name"]: r for r in data.get("evaluations", [])}
    for run in unique_records(data.get("tests", [])):
        if run.get("status") != "Completed":
            continue
        evaluation = evaluations.get(run.get("evaluation"), {})
        request = requests.get(evaluation.get("demo_request"), {})
        add(run, "CRM Test Run", "tests", "test", request.get("account") or evaluation.get("account"), request.get("sales_owner"),
            request.get("opportunity"), done=True, occurred=run.get("run_date"), evaluationId=run.get("evaluation"), round=run.get("test_round"))

    for evaluation in evaluations.values():
        if evaluation.get("status") not in DEMO_PLANNED:
            continue
        request = requests.get(evaluation.get("demo_request"), {})
        if request.get("status") == "Cancelled" or any(
            evaluation.get(f"{branch}_preparation_status") == "Pending" for branch in ("wafer", "test")
        ):
            continue
        add(evaluation, "CRM Evaluation", "tests", "test", request.get("account") or evaluation.get("account"), request.get("sales_owner"),
            request.get("opportunity"), planned=evaluation.get("test_run_deadline"), evaluationId=evaluation["name"])

    versions = grouped([r for r in data.get("versions", []) if r.get("published_at")], "quotation")
    for quote in unique_records(data.get("quotes", [])):
        published = versions.get(quote["name"], [])
        if not published:
            if quote.get("status") == "Draft":
                continue
            first = {}
        else:
            first = min(published, key=lambda r: (stamp(r["published_at"]), r["version_no"]))
        add(quote, "CRM Quotation", "quotes", "quotation", first.get("account") if first else quote.get("account"),
            first.get("quotation_owner") if first else quote.get("quotation_owner"), quote.get("opportunity"), done=True,
            occurred=first.get("published_at"), event=first.get("name"), recorded=first.get("published_at"), amountCny=cny_quote_value(first))

    for action in unique_records(data.get("actions", [])):
        if action.get("archived"):
            continue
        opp = opportunities.get(action.get("opportunity"), {})
        add(action, "CRM Opportunity Action", "actions", "action", opp.get("account"), action.get("action_owner"),
            action.get("opportunity"), done=action.get("status") == "Done", occurred=action.get("completed_at"), planned=action.get("due"))
    return facts


def last_activity_at(facts, opportunity, at, histories=()):
    """Latest evidenced activity, plus the existing substantive-action history contract.

    Missing times are not replaced by creation/modified timestamps. Callers must retain
    their history-completeness indicator before interpreting no recent fact as inactivity.
    """
    at = stamp(at)
    dates = [stamp(f["occurredAt"]) for f in facts if f.get("opportunityId") == opportunity and f["done"]
             and f.get("occurredAt") and stamp(f["occurredAt"]) <= at]
    dates.extend(stamp(r["at"]) for r in histories if stamp(r["at"]) <= at and substantive(r))
    return max(dates) if dates else None
