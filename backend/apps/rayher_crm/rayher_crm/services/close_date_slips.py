"""Cross-quarter PO postponements identified by their immutable field-history row."""
from datetime import date

from rayher_crm.services.cockpit_history import stamp


def day(value):
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def quarter(value):
    return value.year * 4 + (value.month - 1) // 3


def current_slip(history, current_date, now):
    """Latest still-active slip; bringing the date back to its original quarter clears it.

    Same-quarter edits retain identity. Another cross-quarter postponement replaces
    it with a new instance. Bad dates cannot establish a postponement. A later
    unrecorded date change cannot be reconstructed from an earlier history row.
    """
    events = []
    for row in history:
        if row.get("field") != "po_date" or not row.get("name"):
            continue
        try:
            at = stamp(row.get("at"))
        except (ValueError, TypeError):
            continue
        if at and at <= now:
            events.append((at, str(row.get("creation") or ""), row["name"], row))
    active = None
    latest_date = None
    for _, _, _, row in sorted(events):
        before, after = day(row.get("from_value")), day(row.get("to_value"))
        latest_date = after
        if before and after and quarter(after) > quarter(before):
            active = row
        elif not after or (active and quarter(after) <= quarter(day(active["from_value"]))):
            active = None
    # Only evidence connected to today's saved value may create an actionable row.
    current = day(current_date)
    return active if active and current and latest_date == current else None
