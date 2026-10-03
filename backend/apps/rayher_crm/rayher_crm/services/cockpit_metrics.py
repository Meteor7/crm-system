"""Review calculations. Pure functions so historical rules can be tested without Frappe."""
from __future__ import annotations

import calendar
import json
from hashlib import sha256
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from rayher_crm.services.equipment_names import equipment_key
from rayher_crm.services.opportunity_stages import INTERNAL_VALIDATION, OPEN_STAGES, PROBABILITY_LEVELS

SHANGHAI = timezone(timedelta(hours=8))
ACTIVITIES = ("visits", "leads", "tests", "quotes")


def stamp(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, time.min)
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.astimezone(SHANGHAI).replace(tzinfo=None) if result.tzinfo else result


def iso(value):
    dt = stamp(value)
    return dt.replace(tzinfo=SHANGHAI).astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def month_shift(day, months):
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return day.replace(year=year, month=month + 1, day=min(day.day, calendar.monthrange(year, month + 1)[1]))


def bounds(kind, anchor):
    if kind == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=7)
    if kind == "month":
        start = anchor.replace(day=1)
        return start, month_shift(start, 1)
    if kind == "quarter":
        start = anchor.replace(month=(anchor.month - 1) // 3 * 3 + 1, day=1)
        return start, month_shift(start, 3)
    if kind == "year":
        return date(anchor.year, 1, 1), date(anchor.year + 1, 1, 1)
    raise ValueError("Invalid period")


def period(query, now):
    now = stamp(now)
    kind = query.get("period") or "week"
    anchor = date.fromisoformat(query["anchor"]) if query.get("anchor") else now.date() - timedelta(days=now.weekday() + 7)
    start, end = bounds(kind, anchor)
    start, end = stamp(start), stamp(end)
    if start > now:
        raise ValueError("Future periods are not supported")
    cutoff = min(end, now)
    prior_start, prior_end = bounds(kind, (start - timedelta(days=1)).date())
    prior_start, prior_end = stamp(prior_start), stamp(prior_end)
    comparison_end = min(prior_end, prior_start + (cutoff - start)) if now < end else prior_end
    return {"kind": kind, "start": start, "end": end, "cutoff": cutoff,
            "previous_start": prior_start, "previous_end": comparison_end,
            "historical": end <= now, "as_of": cutoff - timedelta(microseconds=1) if end <= now else now}


def covered(coverage, key, at):
    value = coverage.get(key)
    try:
        return bool(value and stamp(value) <= at)
    except (ValueError, TypeError):
        return False


def metric(value=None, state="ready", reason=None):
    return {"value": value, "state": state, "reason": reason}


def insufficient(reason="history_coverage"):
    return metric(None, "insufficient", reason)


def in_region(query, customer):
    """Whether a customer passes the region filter.

    The filter names a region or a sales territory. cockpit.scoped() spells it out as query["regions"],
    the regions it covers; without that list it is the one region it names.
    """

    region = query.get("region")
    return not region or customer.get("custom_crm_region") in query.get("regions", (region,))


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def field_at(opp, field, at, histories, coverage, now):
    if at < now and not covered(coverage, "fields", at):
        return None
    result = opp.get(field)
    for row in sorted(histories, key=lambda r: (stamp(r["at"]), str(r.get("creation", "")), r.get("name", "")), reverse=True):
        if row["field"] == field and stamp(row["at"]) > at:
            result = row.get("from_value")
    return result


def stage_at(opp, at, histories, coverage, now):
    if stamp(opp["creation"]) > at:
        return None
    if at >= now:
        return opp["stage"]
    if not covered(coverage, "stage", at):
        return None
    if any(r.get("source") == "migration" and stamp(r["recorded_at"]) > at for r in histories):
        return None
    state = opp["stage"]
    # Inverse replay preserves rollback and lost/reopen transitions.
    for row in sorted(histories, key=lambda r: (stamp(r.get("reached_at") or r["recorded_at"]), stamp(r["recorded_at"]), str(r.get("creation", ""))), reverse=True):
        when = stamp(row.get("reached_at") or row["recorded_at"])
        if when > at:
            if row.get("source") == "migration" or row.get("reached_at_basis") in {"unknown", "upper_bound"}:
                return None
            state = row.get("from_stage")
    return state


def last_entry(histories, stage, at):
    """The stage-history row of the last entry into ``stage`` by ``at``; ``None`` when it predates the history."""
    rows = [r for r in histories if r.get("to_stage") == stage and stamp(r.get("reached_at") or r["recorded_at"]) <= at]
    if not rows:
        return None
    return max(rows, key=lambda r: (stamp(r.get("reached_at") or r["recorded_at"]), stamp(r["recorded_at"]), str(r.get("creation", ""))))


def stage_entered(histories, stage, at):
    """When an opportunity last entered ``stage`` by ``at``, and whether that moment is only an upper bound.

    A migration row or an unknown/upper-bound date says the stage was reached no later than it, so the
    time spent in the stage since then is a minimum. No row means the entry predates the history.
    """
    row = last_entry(histories, stage, at)
    if row is None:
        return None, False
    return stamp(row.get("reached_at") or row["recorded_at"]), row.get("source") == "migration" or row.get("reached_at_basis") in {"unknown", "upper_bound"}


# A Warnings row is one warning instance: the same action overdue again after a new due date, a new
# quotation version or a new entry into S6 is a new warning with its own handling record.
BEFORE_HISTORY = "before_history"
HANDLING_TYPES = ("overdue", "quotation_expiry", "stage6_no_po")


def handling_key(kind, source_id, source_event):
    return sha256(f"{kind}|{source_id}|{source_event}".encode()).hexdigest()[:40]


def handling_state(record, today):
    """Only an S6 action clears its row, and only until the follow-up day (``today`` is YYYY-MM-DD)."""
    handled = record["warningType"] == "stage6_no_po" and bool(record.get("actedAt")) and (record.get("followUpOn") or "") > today
    return "handled" if handled else "open"


def handling_for(data, kind, source_id, source_event, today):
    """The saved next step and action of one warning, or an empty record the page can start from."""
    record = {"warningType": kind, "sourceId": source_id, "sourceEvent": source_event, "id": None, "modified": None,
              "nextStep": None, "planBy": None, "planAt": None, "actionTaken": None, "actedBy": None, "actedAt": None,
              "followUpOn": None, "history": []}
    record.update(data.get("warning_handlings", {}).get(handling_key(kind, source_id, source_event)) or {})
    return {**record, "state": handling_state(record, today)}


def stage6_stay(entered, at_least, created, history_start, at, threshold):
    """Days a deal still in S6 has spent there at ``at`` and whether that is a minimum; ``None`` days = unknown.

    A recorded entry did happen, and an unrecorded later one could only shorten the stay, so an exact entry
    under the threshold settles it even without complete history. Anything else needs the stage history to be
    complete from ``history_start``: an entry before it, or none for a deal created by then, only proves the
    deal was in S6 at the start, which is then the one certain bound.
    """
    days = (at.date() - entered.date()).days if entered else None
    if entered and not at_least and days < threshold:
        return days, False
    if history_start is None:
        # Without complete stage history an entry may have been followed by unrecorded ones.
        return None, False
    if (entered is None and created <= history_start) or (entered and entered < history_start):
        days, at_least = (at.date() - history_start.date()).days, True
    if days is None or (at_least and days < threshold):
        # No entry for a deal created after the history start (it always has one), or a minimum under the threshold.
        return None, False
    return days, at_least


def action_json(value):
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        return parsed if isinstance(parsed, dict) and parsed.get("id") else None
    except (ValueError, TypeError):
        return None


def substantive(row):
    if row["field"] == "actionCreated":
        return bool(action_json(row.get("to_value")))
    if row["field"] != "actionUpdated":
        return False
    before, after = action_json(row.get("from_value")), action_json(row.get("to_value"))
    return bool(before and after and any((before.get(k) or "") != (after.get(k) or "") for k in ("title", "owner", "due", "status")))


def actions_at(actions, histories, at):
    state = {r["name"]: {"id": r["name"], "title": r["title"], "owner": r.get("action_owner"),
                          "due": str(r.get("due") or ""), "status": r["status"], "archived": bool(r.get("archived"))}
             for r in actions if stamp(r["creation"]) <= at}
    for row in sorted(histories, key=lambda r: (stamp(r["at"]), str(r.get("creation", "")), r.get("name", "")), reverse=True):
        if stamp(row["at"]) <= at:
            continue
        if row["field"] == "actionUpdated":
            before = action_json(row.get("from_value"))
            if before and before["id"] in state:
                state[before["id"]].update(before)
        elif row["field"] == "actionDeleted":
            action_id = str(row.get("to_value") or "").strip('"')
            if action_id in state:
                state[action_id]["archived"] = False
        elif row["field"] == "actionCreated":
            after = action_json(row.get("to_value"))
            if after:
                state.pop(after["id"], None)
    return [r for r in state.values() if not r["archived"]]


def grouped(rows, field):
    result = {}
    for row in rows:
        result.setdefault(row.get(field), []).append(row)
    return result


def booking_cny_amount(booking):
    """The order's amount in CNY as text: a CNY order's own amount, otherwise the entered amount_cny.

    A CNY order is complete as entered, even at 0. In another currency, 0 or missing means nobody
    has entered the CNY amount yet; that is None here, never ¥0.
    """
    if str(booking.get("currency") or "CNY").upper() == "CNY":
        value = number(booking.get("amount"))
        return format(value, ".2f") if value is not None else None
    value = number(booking.get("amount_cny"))
    return format(value, ".2f") if value is not None and value > 0 else None


def quotation_expiry(data, query, reference, days=14, now=None):
    """Current formal versions expiring in an inclusive business-date window.

    A newer draft does not withdraw the published version. Decisions and replacement
    are read from the current formal version, not reconstructed as historical facts.
    """
    customers = {r["name"]: r for r in data["customers"]}
    opportunities = {r["name"]: r for r in data.get("quotation_opportunities", data["opportunities"])}
    versions = {r["name"]: r for r in data["versions"] if r.get("name")}
    today = stamp(now or reference).date()
    rows, incomplete = [], False
    for quote in data["quotes"]:
        customer = customers.get(quote.get("account"))
        if not customer or not in_region(query, customer) \
                or (query.get("market") and customer.get("custom_crm_segment") != query["market"]):
            continue
        owner = quote.get("quotation_owner")
        if query.get("sales") and owner and owner != query["sales"]:
            continue
        opportunity = opportunities.get(quote.get("opportunity"))
        if quote.get("opportunity") and not opportunity:
            # Its equipment is unknown too, so an equipment filter cannot report a clean zero.
            incomplete = True
            continue
        if query.get("equipment") and (not opportunity or equipment_key(opportunity.get("tool_type")) != equipment_key(query["equipment"])):
            continue
        if opportunity and opportunity.get("stage") in {"po_received", "lost"}:
            continue
        version_id = quote.get("current_published_version")
        if not version_id:
            incomplete |= quote.get("status") not in {"Draft", "Accepted", "Rejected", "Expired"}
            continue
        version = versions.get(version_id)
        if not version or version.get("quotation") != quote["name"]:
            incomplete = True
            continue
        if version.get("status") != "Published":
            continue
        try:
            published = stamp(version.get("published_at"))
            deadline = stamp(version.get("valid_until"))
        except (ValueError, TypeError, OverflowError):
            published = deadline = None
        if not published or not deadline or not owner:
            incomplete = True
            continue
        remaining = (deadline.date() - reference.date()).days
        if published > reference or deadline.date() < today or not 0 <= remaining <= days:
            continue
        rows.append({"id": quote["name"], "title": quote.get("ref_no") or quote["name"],
                     "accountId": quote["account"], "customer": customer.get("customer_name") or quote["account"],
                     "owner": owner, "at": iso(deadline), "kind": "quotation", "publishedAt": iso(published),
                     "quotationVersionId": version_id, "quotationVersionNo": version.get("version_no"),
                     "validUntil": deadline.date().isoformat(), "daysToExpiry": remaining,
                     "opportunityId": quote.get("opportunity")})
    rows.sort(key=lambda row: (row["validUntil"], row["id"]))
    return {"count": insufficient("quotation_expiry_data_missing") if incomplete else metric(len(rows)),
            "items": rows, "referenceDate": reference.date().isoformat(), "thresholdDays": days}


# Warnings counts the losses of the last four weeks. Older unreviewed losses, however old, are listed
# apart as a post-mortem backlog, flagged overdue, and never counted: every loss the backfill made
# pending must be reachable from the page.
LOST_WINDOW_DAYS = 28


def build_review(data, query, now, coverage, quotation_expiry_days=14, stage6_no_po_days=30):
    now = stamp(now)
    window = period(query, now)
    at = window["as_of"]
    # Handling state is current, like post-mortems and downgrade actions: an S6 follow-up day is judged today.
    today = now.date().isoformat()
    customers = {r["name"]: r for r in data["customers"]}
    opportunities = {r["name"]: r for r in data["opportunities"]}
    histories = grouped(data["history"], "opportunity")
    stages = grouped(data["stages"], "opportunity")
    actions = grouped(data["actions"], "opportunity")
    recoveries = {r["probability_change"]: r for r in data.get("recoveries", [])}
    owner_filter = query.get("sales")
    # Equipment belongs to the opportunity: a record counts under an equipment filter only through the
    # opportunity it is linked to. Records with no opportunity are left out and reported, never guessed.
    # Spellings that differ only in case, spacing or punctuation are one type, as on the Opportunities board.
    # A linked opportunity now at another customer still gives its equipment.
    equipment_filter = equipment_key(query.get("equipment"))
    equipment_of = {r["name"]: equipment_key(r.get("tool_type")) for r in
                    (*data.get("equipment_opportunities", []), *data.get("quotation_opportunities", []), *data["opportunities"])}
    unclassified = {key: [] for key in ACTIVITIES}

    def equipment_ok(opportunity_id):
        return not equipment_filter or bool(opportunity_id and equipment_of.get(opportunity_id) == equipment_filter)
    cny_amount_ready = bool(data.get("cny_amount_ready"))
    details = {key: [] for key in (*ACTIVITIES, *OPEN_STAGES, "po", "po_missing_date", "po_missing_amount", "lost", "lost_backlog", "overdue", "downgrade", "downgrade_history", "stalled", "losses", "stage6_no_po", "stage6_no_po_handled")}

    def in_scope(account, owner):
        customer = customers.get(account)
        return bool(customer and (not owner_filter or owner == owner_filter)
                    and (not query.get("market") or customer.get("custom_crm_segment") == query["market"])
                    and in_region(query, customer))

    def entry(record, account, owner, when, kind, **extra):
        return {"id": record["name"], "title": record.get("title") or record.get("subject") or record.get("ref_no") or record["name"],
                "accountId": account, "customer": customers.get(account, {}).get("customer_name", account or ""),
                "owner": owner, "at": iso(when), "kind": kind, **extra}

    def cny_amount_at(opp, when, history):
        if not cny_amount_ready:
            return None
        value = number(field_at(opp, "amount_cny", when, history, coverage, now))
        if value is None or value <= 0:
            # The first fill (backfill or Sales) starts from empty. Before it, an Opportunity priced in
            # CNY is its own CNY amount (history is trusted); other currencies, and a current value
            # nobody has entered yet, stay missing.
            before_first_fill = any(r["field"] == "amount_cny" and stamp(r["at"]) > when for r in history)
            if not before_first_fill or field_at(opp, "currency", when, history, coverage, now) != "CNY":
                return None
            value = number(field_at(opp, "amount", when, history, coverage, now))
        return format(value, ".2f") if value is not None and value > 0 else None

    events = {key: [] for key in ACTIVITIES}
    missing = set()
    for row in data["visits"]:
        if row["status"] not in {"Visited", "Minutes Submitted", "Manager Reviewed"}:
            continue
        if in_scope(row["account"], row["visit_owner"]):
            if equipment_filter and not row.get("opportunity"):
                if row.get("visit_date"):
                    unclassified["visits"].append(entry(row, row["account"], row["visit_owner"], row["visit_date"], "visit"))
                continue
            if not equipment_ok(row.get("opportunity")):
                continue
            if row.get("visit_date"):
                events["visits"].append(entry(row, row["account"], row["visit_owner"], row["visit_date"], "visit"))
            else:
                missing.add("visits")
    conversions = {r["reference_name"]: r for r in sorted(data["stages"], key=lambda r: str(r.get("reached_at") or ""), reverse=True)
                   if r["event"] == "lead_converted" and r.get("reference_doctype") == "Lead" and r.get("reached_at")}
    for row in data["leads"]:
        event = conversions.get(row["name"], {})
        when = row.get("custom_crm_converted_at") or event.get("reached_at")
        opp = opportunities.get(row.get("custom_crm_converted_opportunity") or event.get("opportunity"), {})
        account = row.get("custom_crm_converted_account") or opp.get("account")
        owner = field_at(opp, "opportunity_owner", stamp(when), histories.get(opp.get("name"), []), coverage, now) if when and opp else None
        if account in customers and (when or row.get("custom_crm_status") == "Converted"):
            # A gap on another equipment's deal does not make this equipment's count unknown.
            if owner_filter and owner is None and equipment_ok(opp.get("name")):
                missing.add("leads")
            if in_scope(account, owner) and equipment_ok(opp.get("name")):
                if when:
                    events["leads"].append(entry(row, account, owner, when, "lead"))
                else:
                    missing.add("leads")
    requests = {r["name"]: r for r in data["requests"]}
    evaluations = {r["name"]: r for r in data["evaluations"]}
    for row in data["tests"]:
        if row["status"] != "Completed":
            continue
        evaluation = evaluations.get(row["evaluation"], {})
        request = requests.get(evaluation.get("demo_request"), {})
        account, owner = request.get("account") or evaluation.get("account"), request.get("sales_owner")
        if not request and account in customers:
            missing.add("tests")
        if in_scope(account, owner):
            if equipment_filter and not request.get("opportunity"):
                if row.get("run_date") and owner:
                    unclassified["tests"].append(entry(row, account, owner, row["run_date"], "test"))
                continue
            if not equipment_ok(request.get("opportunity")):
                continue
            if row.get("run_date") and owner:
                events["tests"].append(entry(row, account, owner, row["run_date"], "test", evaluationId=row["evaluation"], round=row.get("test_round")))
            else:
                missing.add("tests")
    versions = grouped([r for r in data["versions"] if r.get("published_at")], "quotation")
    for quote in data["quotes"]:
        published = versions.get(quote["name"], [])
        if not published:
            if quote.get("status") != "Draft" and in_scope(quote["account"], quote["quotation_owner"]) and equipment_ok(quote.get("opportunity")):
                missing.add("quotes")
            continue
        first = min(published, key=lambda r: (stamp(r["published_at"]), r["version_no"]))
        if equipment_filter and not quote.get("opportunity"):
            if in_scope(first["account"], first["quotation_owner"]):
                unclassified["quotes"].append(entry(quote, first["account"], first["quotation_owner"], first["published_at"], "quotation"))
            continue
        if in_scope(first["account"], first["quotation_owner"]) and equipment_ok(quote.get("opportunity")):
            events["quotes"].append(entry(quote, first["account"], first["quotation_owner"], first["published_at"], "quotation"))

    def during(rows, start, end):
        return [r for r in rows if start <= stamp(r["at"]) < end]

    activity = []
    for key, rows in events.items():
        details[key] = during(rows, window["start"], window["cutoff"])
        current = len(details[key])
        previous = len(during(rows, window["previous_start"], window["previous_end"]))
        activity.append({"key": key, "unclassified": len(during(unclassified[key], window["start"], window["cutoff"])) if equipment_filter else None,
                         "actual": insufficient("missing_event_or_owner") if key in missing else metric(current),
                         "previous": insufficient("missing_event_or_owner") if key in missing else metric(previous),
                         "delta": None if key in missing else current - previous})

    stage_complete = not window["historical"] or covered(coverage, "stage", at)
    fields_complete = not window["historical"] or covered(coverage, "fields", at)
    actions_complete = not window["historical"] or covered(coverage, "actions", at)
    stalled_complete = covered(coverage, "actions", at - timedelta(days=35))
    stage_unknown = False
    stage6_unknown = False
    for opp in data["opportunities"]:
        if stamp(opp["creation"]) > at:
            continue
        history = histories.get(opp["name"], [])
        owner = field_at(opp, "opportunity_owner", at, history, coverage, now)
        if not in_scope(opp["account"], owner) or not equipment_ok(opp["name"]):
            continue
        stage = stage_at(opp, at, stages.get(opp["name"], []), coverage, now)
        if stage is None:
            stage_unknown = True
            # Only a deal still in S6 now can be flagged, so only its unknown stage leaves the S6 count unknown.
            stage6_unknown |= opp.get("stage") == INTERNAL_VALIDATION
            continue
        if stage not in OPEN_STAGES:
            continue
        row = entry(opp, opp["account"], owner, at, "opportunity", stage=stage,
                    amount=cny_amount_at(opp, at, history), currency="CNY")
        details[stage].append(row)
        # Which actions were overdue follows the viewed period; whether they still are is current state,
        # like post-mortems and downgrade actions: done, archived, moved past the period end, or the deal
        # closed since (warning_handling._source takes no next step on a closed deal) clears the row.
        current_actions = {r["name"]: r for r in actions.get(opp["name"], [])} if opp.get("stage") in OPEN_STAGES else {}
        for action in actions_at(actions.get(opp["name"], []), history, at):
            if not (action.get("due") and action["status"] == "Open" and date.fromisoformat(str(action["due"])[:10]) < at.date()):
                continue
            now_action = current_actions.get(action["id"])
            if not now_action or now_action.get("status") != "Open" or now_action.get("archived") or not now_action.get("due"):
                continue
            due = str(now_action["due"])[:10]
            if date.fromisoformat(due) >= at.date():
                continue
            details["overdue"].append({**row, "actionId": action["id"], "actionTitle": now_action.get("title") or action["title"], "due": due,
                                       "actionOwner": now_action.get("action_owner") or action.get("owner"),
                                       "handling": handling_for(data, "overdue", action["id"], due, today)})
        # Internal validation (S6) with no PO for too long. Like overdue actions, the viewed period decides
        # the time in the stage; moving on, receiving the PO or losing the deal since then clears the row.
        if stage == INTERNAL_VALIDATION and opp.get("stage") == INTERNAL_VALIDATION:
            entered, at_least = stage_entered(stages.get(opp["name"], []), INTERNAL_VALIDATION, at)
            history_start = stamp(coverage["stage"]) if covered(coverage, "stage", at) else None
            days, at_least = stage6_stay(entered, at_least, stamp(opp["creation"]), history_start, at, stage6_no_po_days)
            if days is None:
                stage6_unknown = True
            elif days >= stage6_no_po_days:
                exact = None if at_least else iso(entered)
                # The deal is in S6 now, so its warning is the current S6 entry even when a past period is viewed.
                entry_row = last_entry(stages.get(opp["name"], []), INTERNAL_VALIDATION, now)
                handling = handling_for(data, "stage6_no_po", opp["name"], (entry_row or {}).get("name") or BEFORE_HISTORY, today)
                # A recorded action takes the deal out of the count until its follow-up day; it stays listed apart.
                details["stage6_no_po_handled" if handling["state"] == "handled" else "stage6_no_po"].append(
                    {**row, "at": exact, "enteredAt": exact, "daysInStage": days, "daysAtLeast": at_least, "handling": handling})
        changes = [stamp(r["at"]) for r in history if stamp(r["at"]) <= at and substantive(r)]
        last = max([stamp(opp["creation"]), *changes])
        boundary = stamp(coverage.get("actions")) if stalled_complete else None
        lower_bound = bool(boundary and last < boundary)
        age = (at.date() - (boundary if lower_bound else last).date()).days
        if age >= 21 and stalled_complete:
            details["stalled"].append({**row, "lastActionAt": None if lower_bound else iso(last), "days": age, "daysAtLeast": lower_bound, "severity": "high" if age >= 35 else "warning"})

    year_start = datetime(at.year, 1, 1)
    # Current Booking state, including later backfills/corrections; never replay PO events.
    po_ready = bool(data.get("booking_dates_ready"))
    po_by_day = {}
    for booking in data.get("bookings", []) if po_ready else []:
        if booking.get("source") != "Opportunity" or booking.get("status") not in {"Confirmed", "Completed"}:
            continue
        opp = opportunities.get(booking.get("source_opportunity"))
        if not opp or not in_scope(opp["account"], opp.get("opportunity_owner")) or not equipment_ok(opp["name"]):
            continue
        when = stamp(booking.get("actual_po_date"))
        amount_cny = booking_cny_amount(booking)
        row = entry(booking, opp["account"], opp.get("opportunity_owner"), when, "booking",
                    opportunityId=opp["name"], status=booking["status"], amount=amount_cny, currency="CNY")
        if when is None:
            # No date means no year assignment. Scope still uses current customer and owner.
            details["po_missing_date"].append(row)
        elif year_start.date() <= when.date() <= at.date():
            details["po"].append(row)
            if amount_cny is None:
                details["po_missing_amount"].append(row)
            else:
                po_by_day[when.date()] = po_by_day.get(when.date(), Decimal(0)) + Decimal(amount_cny)

    loss_start = stamp(month_shift(at.date(), -12))
    # Four calendar weeks ending on the as_of day (Shanghai dates), for current and completed periods alike.
    lost_start = datetime.combine(at.date() - timedelta(days=LOST_WINDOW_DAYS - 1), time.min)
    reviews = {r["stage_event"]: r for r in data.get("loss_reviews", [])}
    for event in data["stages"]:
        if event["event"] != "marked_lost":
            continue
        when = stamp(event.get("reached_at"))
        if not when or when > at or event.get("source") == "migration":
            continue
        opp = opportunities.get(event["opportunity"])
        if not opp or not equipment_ok(opp["name"]):
            continue
        owner = field_at(opp, "opportunity_owner", when, histories.get(opp["name"], []), coverage, now)
        if not in_scope(opp["account"], owner):
            continue
        row = entry(opp, opp["account"], owner, when, "opportunity", reason=event.get("reason"), stage=event.get("from_stage"), eventId=event["name"])
        row["amount"] = cny_amount_at(opp, when, histories.get(opp["name"], []))
        row["currency"] = "CNY"
        # A reopened deal no longer needs a post-mortem; the loss row stays for the record. Like the
        # review itself, this is current state, so reopening clears the warning in a completed period too.
        reopened_at = next((stamp(r["recorded_at"]) for r in sorted(stages.get(opp["name"], []), key=lambda r: str(r.get("recorded_at") or ""))
                            if r["event"] == "reopened" and r.get("recorded_at") and when < stamp(r["recorded_at"])), None)
        review = reviews.get(event["name"])
        # Like downgrade handling, the review state is current: a post-mortem recorded later still
        # clears the warning when a completed period is viewed.
        reviewed = bool(review and review.get("review_status") == "Reviewed")
        pending = not reviewed and reopened_at is None
        row["review"] = ({"id": review["name"], "status": "reviewed" if reviewed else "pending",
                          "note": review.get("review_note") or "", "reviewedBy": review.get("reviewed_by") or None,
                          "reviewedAt": iso(stamp(review["reviewed_at"])) if review.get("reviewed_at") else None,
                          "modified": iso(stamp(review["modified"])) if review.get("modified") else None} if review else None)
        row["reviewPending"] = pending
        row["reviewOverdue"] = pending and when < lost_start
        row["reopenedAt"] = iso(reopened_at) if reopened_at else None
        if when >= lost_start:
            details["lost"].append(row)
        elif pending:
            # A backfilled pending review must stay reachable even outside the annual statistics.
            details["lost_backlog"].append(row)
        if when >= loss_start:
            details["losses"].append(row)
    rank = {v: i for i, v in enumerate(PROBABILITY_LEVELS)}
    for event in data["probabilities"]:
        when = stamp(event["changed_at"])
        if not (window["start"] <= when <= at) or event["from_level"] not in rank or event["to_level"] not in rank:
            continue
        if rank[event["to_level"]] >= rank[event["from_level"]]:
            continue
        opp = opportunities.get(event["opportunity"])
        if not opp or not equipment_ok(opp["name"]):
            continue
        # Both pending and handled downgrade views follow current responsibility.
        owner = opp.get("opportunity_owner")
        recovery = recoveries.get(event["name"])
        recovery_dto = ({"plan": recovery["plan"], "state": "handled" if recovery.get("acted_at") else "pending",
                         "actionTaken": recovery.get("action_taken"), "actedBy": recovery.get("acted_by"),
                         "actedAt": iso(stamp(recovery["acted_at"])) if recovery.get("acted_at") else None} if recovery else None)
        row = entry(opp, opp["account"], owner, when, "opportunity", reason=event.get("reason"),
                    fromLevel=event["from_level"], toLevel=event["to_level"], eventId=event["name"],
                    currentOwner=opp.get("opportunity_owner"), recovery=recovery_dto, stage=opp.get("stage"),
                    amount=cny_amount_at(opp, at, histories.get(opp["name"], [])), currency="CNY")
        # The event window remains historical. Resolution and responsibility are current,
        # so recording an action clears the warning even when viewing a completed period.
        if in_scope(opp["account"], owner):
            details["downgrade_history"].append(row)
        if (not recovery or not recovery.get("acted_at")) and in_scope(opp["account"], opp.get("opportunity_owner")):
            details["downgrade"].append({**row, "owner": opp.get("opportunity_owner")})
    stages_ready = stage_complete and not stage_unknown and (not owner_filter or fields_complete)
    expiring = quotation_expiry(data, query, at, quotation_expiry_days, now)
    details["quotation_expiry"] = [{**r, "handling": handling_for(data, "quotation_expiry", r["id"], r["quotationVersionId"], today)} for r in expiring["items"]]

    def count(rows, ready=True):
        return metric(len({r["id"] for r in rows})) if ready else insufficient()

    def po_count(rows):
        return count(rows) if po_ready else insufficient("actual_po_date_unavailable")

    def po_amount(rows):
        # One order without its CNY amount makes the total unknown: it is listed to backfill, never counted as 0.
        if not po_ready:
            return insufficient("actual_po_date_unavailable")
        if any(r["amount"] is None for r in rows):
            return insufficient("booking_cny_amount_missing")
        return metric(format(sum((Decimal(r["amount"]) for r in rows), Decimal(0)), ".2f"))

    def po_series():
        # Cumulative CNY by actual PO date for the annual chart; fraction matches orders.elapsedFraction.
        if po_amount(details["po"])["state"] != "ready":
            return []
        first = date(at.year, 1, 1)
        days = (date(at.year + 1, 1, 1) - first).days
        total, series = Decimal(0), []
        for day in sorted(po_by_day):
            total += po_by_day[day]
            series.append({"date": day.isoformat(), "amount": format(po_by_day[day], ".2f"),
                           "cumulative": format(total, ".2f"), "fraction": ((day - first).days + 1) / days})
        return series

    def amount(rows, ready=True):
        if not cny_amount_ready:
            return insufficient("amount_cny_unavailable")
        if not ready:
            return insufficient()
        if any(r.get("currency") != "CNY" or number(r.get("amount")) is None for r in rows):
            return insufficient("cny_amount_unavailable")
        return metric(format(sum((number(r["amount"]) for r in rows), Decimal(0)), ".2f"))

    def event_count(rows, ready=True):
        # One row per loss event: a deal lost, reopened and lost again is two losses.
        return metric(len({r["eventId"] for r in rows})) if ready else insufficient()

    def action_count(rows, ready=True):
        # The zone lists actions, so an opportunity with two overdue actions counts twice.
        return metric(len({(r["id"], r["actionId"]) for r in rows})) if ready else insufficient()

    lost_ready = covered(coverage, "stage", lost_start) and (not owner_filter or covered(coverage, "fields", lost_start))
    warnings = [
        {"key": "lost", "count": count([r for r in details["lost"] if r["reviewPending"]], lost_ready)},
        {"key": "overdue", "count": action_count(details["overdue"], stages_ready and actions_complete)},
        {"key": "downgrade", "count": count(details["downgrade"], covered(coverage, "probability", window["start"]))},
    ]
    warnings.append({"key": "quotation_expiry", "count": expiring["count"]})
    warnings.append({"key": "stage6_no_po", "count": count(details["stage6_no_po"], not stage6_unknown and (not owner_filter or fields_complete))})
    pipeline = [{"key": key, "count": count(details[key], stages_ready),
                 "amount": metric(None, "not_applicable") if i == 0 else amount(details[key], stages_ready and fields_complete)} for i, key in enumerate(OPEN_STAGES)]
    pipeline.append({"key": "po", "count": po_count(details["po"]), "amount": po_amount(details["po"])})
    people = {r["name"]: r.get("full_name") or r["name"] for r in data["people"]}
    all_rows = [r for key in (*ACTIVITIES, *OPEN_STAGES, "po", "po_missing_date") for r in details[key]]
    owners = sorted({r["owner"] for r in all_rows if r.get("owner")} | ({owner_filter} if owner_filter else set(people)))
    reps = []
    for owner in owners:
        select = lambda key: [r for r in details[key] if r.get("owner") == owner]
        reps.append({"id": owner, "name": people.get(owner, owner),
                     "activities": {key: insufficient("missing_event_or_owner") if key in missing or any(not r.get("owner") for r in details[key]) else metric(len(select(key))) for key in ACTIVITIES},
                     "pipeline": amount([r for key in OPEN_STAGES[1:] for r in select(key)], stages_ready and fields_complete),
                     "poCount": po_count(select("po")),
                     "orders": po_amount(select("po"))})
    for key in details:
        details[key].sort(key=lambda r: (r.get("at") or "", r["id"]), reverse=True)
    details["quotation_expiry"].sort(key=lambda row: (row["validUntil"], row["id"]))
    details["stalled"].sort(key=lambda r: (-r["days"], r["id"]))
    details["stage6_no_po"].sort(key=lambda r: (-r["daysInStage"], r["id"]))
    details["stage6_no_po_handled"].sort(key=lambda r: (-r["daysInStage"], r["id"]))
    losses_ready = covered(coverage, "stage", loss_start) and (not owner_filter or covered(coverage, "fields", loss_start))
    public_window = {"kind": window["kind"], "start": window["start"].date().isoformat(),
                     "end": (window["end"] - timedelta(days=1)).date().isoformat(), "asOf": iso(at),
                     "previousStart": window["previous_start"].date().isoformat(), "previousEnd": iso(window["previous_end"]),
                     "complete": window["historical"], "previousAnchor": window["previous_start"].date().isoformat(),
                     "nextAnchor": window["end"].date().isoformat(), "hasNext": window["end"] <= now}
    return {"period": public_window, "activities": activity, "pipeline": pipeline, "warnings": warnings, "sales": reps,
            "quotationExpiry": {"referenceDate": expiring["referenceDate"], "thresholdDays": expiring["thresholdDays"]},
            "stage6NoPo": {"thresholdDays": stage6_no_po_days},
            "orders": {"actual": po_amount(details["po"]), "series": po_series(), "count": po_count(details["po"]),
                       "missingDate": po_count(details["po_missing_date"]), "missingAmount": po_count(details["po_missing_amount"])},
            "stalled": {"count": count(details["stalled"], stages_ready and stalled_complete), "items": details["stalled"][:5]},
            "losses": {"count": event_count(details["losses"], losses_ready), "items": details["losses"][:5],
                       "reviewed": event_count([r for r in details["losses"] if r["review"] and r["review"]["status"] == "reviewed"], losses_ready),
                       "pending": event_count([r for r in details["losses"] if r["reviewPending"]], losses_ready)},
            "_details": details}
