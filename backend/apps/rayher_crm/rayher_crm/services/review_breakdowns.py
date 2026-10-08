"""Review breakdowns preserve source snapshots and distinguish unknown data."""
from decimal import Decimal, InvalidOperation

LOSS_CATEGORIES = ("Price", "Local competitor preferred", "Specs / throughput", "Budget cancelled or delayed", "Delivery lead time", "Other")
VISIT_KINDS = ("existing", "prospect", "unclassified")


def value_metric(value, complete=True, reason="missing_event_or_owner"):
    return {"value": value if complete else None, "state": "ready" if complete else "insufficient", "reason": None if complete else reason}


def visit_kind(row):
    return row.get("customerKind") if row.get("customerKind") in VISIT_KINDS else "unclassified"


def quote_amount(rows, complete):
    total, missing = Decimal(0), 0
    for row in rows:
        try:
            amount = Decimal(str(row.get("amountCny")))
            if not amount.is_finite() or amount < 0:
                raise ValueError("Unknown snapshot amount")
            total += amount
        except (InvalidOperation, ValueError, TypeError):
            missing += 1
    return {"total": value_metric(format(total, ".2f"), complete and not missing, "missing_quote_amount_or_event"),
            "known": format(total, ".2f"), "missing": missing}


def activity_breakdown(key, current, previous, current_complete, previous_complete):
    if key == "visits":
        rows = []
        for kind in VISIT_KINDS:
            actual = sum(visit_kind(row) == kind for row in current)
            prior = sum(visit_kind(row) == kind for row in previous)
            rows.append({"key": kind, "actual": value_metric(actual, current_complete), "previous": value_metric(prior, previous_complete),
                         "delta": actual - prior if current_complete and previous_complete else None})
        return {"customerKinds": rows}
    if key == "quotes":
        actual, prior = quote_amount(current, current_complete), quote_amount(previous, previous_complete)
        delta = format(Decimal(actual["known"]) - Decimal(prior["known"]), ".2f") if actual["total"]["state"] == prior["total"]["state"] == "ready" else None
        return {"quoteAmount": {"actual": actual["total"], "previous": prior["total"], "delta": delta,
                                "known": actual["known"], "missing": actual["missing"],
                                "previousKnown": prior["known"], "previousMissing": prior["missing"]}}
    return {}


def loss_category(row):
    review = row.get("review") or {}
    if review.get("status") != "reviewed":
        return "pending"
    return review.get("category") if review.get("category") in LOSS_CATEGORIES else "unclassified"


def loss_breakdown(rows, complete, unknown_categories=()):
    reviewed = sum((row.get("review") or {}).get("status") == "reviewed" for row in rows)
    completion = value_metric(format(Decimal(reviewed) * 100 / len(rows), ".2f"), complete) if rows else {"value": None, "state": "not_applicable", "reason": "no_losses"}
    if not complete or unknown_categories:
        completion = value_metric(None, False, "history_coverage")
    return {"completionPercent": completion,
            "categories": [{"key": category, "count": value_metric(sum(loss_category(row) == category for row in rows), complete and category not in unknown_categories, "history_coverage")}
                           for category in (*LOSS_CATEGORIES, "unclassified", "pending")]}
