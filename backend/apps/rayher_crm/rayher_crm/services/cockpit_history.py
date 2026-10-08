"""Business-time and audited-history helpers shared by cockpit activity readers."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

SHANGHAI = timezone(timedelta(hours=8))


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


def covered(coverage, key, at):
    value = coverage.get(key)
    try:
        return bool(value and stamp(value) <= at)
    except (ValueError, TypeError):
        return False


def field_at(opp, field, at, histories, coverage, now):
    if at < now and not covered(coverage, "fields", at):
        return None
    result = opp.get(field)
    for row in sorted(histories, key=lambda r: (stamp(r["at"]), str(r.get("creation", "")), r.get("name", "")), reverse=True):
        if row["field"] == field and stamp(row["at"]) > at:
            # User Links follow native rename/merge; the original audit text does
            # not. An unresolved legacy identity must remain unknown.
            result = row.get("from_owner") if field == "opportunity_owner" else row.get("from_value")
    return result


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
