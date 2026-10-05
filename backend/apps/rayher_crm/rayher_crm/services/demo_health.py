"""Health of a Demo that is still in progress: red, orange or green on the Demo boards."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from rayher_crm.services.common import SHANGHAI_TIMEZONE


# Red: the customer expects the result within this many days, or the day has passed.
CUSTOMER_EXPECTED_WARNING_DAYS = 7
# Orange: this many days without recorded progress.
STALLED_AFTER_DAYS = 5


def calendar_day(value: Any) -> date | None:
    """The calendar day of a date or a timestamp, in Shanghai time like every CRM date."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            if len(text) == 10:
                return date.fromisoformat(text)
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TIMEZONE)
    return parsed.astimezone(SHANGHAI_TIMEZONE).date()


def derive_demo_health(
    *,
    last_progress_at: Any,
    customer_expected_date: Any,
    test_run_deadline: Any,
    today: Any,
) -> dict[str, Any]:
    """Health of one Demo in progress, in the order the boards explain it.

    Red first: the customer's expected date is at most 7 days away or has passed, or a Test Run
    deadline has passed. Then orange: 5 days without recorded progress. Otherwise green.
    The reasons are the texts the Demo boards show and translate; keep them in step with
    demoHealthReason in the frontend.
    """

    current = calendar_day(today)
    if current is None:
        raise ValueError("today must be a date.")
    last_progress = calendar_day(last_progress_at)
    expected = calendar_day(customer_expected_date)
    deadline = calendar_day(test_run_deadline)
    days_since_progress = max(0, (current - last_progress).days) if last_progress else 0
    days_to_expected = (expected - current).days if expected else None

    def health(level: str, reason: str) -> dict[str, Any]:
        return {
            "level": level,
            "reason": reason,
            "daysSinceProgress": days_since_progress,
            "daysToCustomerExpected": days_to_expected,
        }

    if days_to_expected is not None and days_to_expected <= CUSTOMER_EXPECTED_WARNING_DAYS:
        if days_to_expected < 0:
            return health("critical", f"客户预期已逾期 {-days_to_expected} 天")
        if days_to_expected == 0:
            return health("critical", "客户预期为今天")
        return health("critical", f"距客户预期仅 {days_to_expected} 天")
    if deadline is not None and deadline < current:
        return health("critical", f"Test Run DDL 已逾期 {(current - deadline).days} 天")
    if days_since_progress >= STALLED_AFTER_DAYS:
        return health("stalled", f"已连续 {days_since_progress} 天无有效进展")
    if last_progress is None:
        # No progress was ever recorded, so none is claimed for today.
        return health("healthy", "正常推进")
    if days_since_progress == 0:
        return health("healthy", "今天有进展")
    if days_since_progress <= 2:
        return health("healthy", f"{days_since_progress} 天内有进展")
    return health("healthy", "正常推进")
