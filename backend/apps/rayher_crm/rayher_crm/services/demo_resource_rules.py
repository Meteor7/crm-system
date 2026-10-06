"""Pure Demo resource interval rules; all input datetimes are Shanghai naive."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256

ACTIVE = frozenset({"Requested", "Scope Confirmed", "Sample Received", "Scheduled", "Testing"})


def moment(value):
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def interval(start, end):
    start, end = moment(start), moment(end)
    return (start, end) if start and end and start < end else None


def resource_state(evaluation, unavailable, now):
    """Return current readiness and every overlapping instance, never guess dates."""
    if evaluation.get("status") not in ACTIVE or evaluation.get("request_status") == "Cancelled":
        return {"state": "inactive", "impacts": []}
    planned = interval(evaluation.get("resource_start"), evaluation.get("resource_end"))
    resource = evaluation.get("demo_resource")
    if not resource or not planned:
        return {"state": "unknown", "impacts": []}
    start, end = planned
    if end <= now:
        return {"state": "elapsed", "impacts": []}
    impacts = []
    for row in unavailable:
        blocked = interval(row.get("starts_at"), row.get("ends_at"))
        if row.get("resource") != resource or row.get("status") != "Active" or not blocked:
            continue
        left, right = max(start, blocked[0], now), min(end, blocked[1])
        if left >= right:
            continue
        identity = f"{evaluation['name']}:{evaluation.get('resource_revision') or 0}:{row['name']}:{row.get('revision') or 1}"
        timestamp = lambda value: value.replace(tzinfo=timezone(timedelta(hours=8))).isoformat()
        impacts.append({"key": sha256(identity.encode()).hexdigest(), "evaluationId": evaluation["name"],
                        "resourceId": resource, "unavailabilityId": row["name"], "reason": row.get("reason") or "",
                        "plannedStart": timestamp(start), "plannedEnd": timestamp(end),
                        "unavailableStart": timestamp(blocked[0]), "unavailableEnd": timestamp(blocked[1])})
    return {"state": "blocked" if impacts else "available", "impacts": impacts}
