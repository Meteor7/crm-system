"""Canonical lifecycle states: risk or scheduling changes never complete an action."""

OPEN_ACTION_STATUSES = ("Open", "In Progress", "Blocked", "Rescheduled")
ACTION_STATUSES = (*OPEN_ACTION_STATUSES, "Done")


def open_action(row):
    return row.get("status") in OPEN_ACTION_STATUSES and not row.get("archived")
