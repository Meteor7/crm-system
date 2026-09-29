"""Exact money wire helpers shared by CRM services.

Money crosses the JSON boundary as a fixed two-decimal string.  Python floats
are deliberately not accepted because they may already have lost precision.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from rayher_crm.api.v1.errors import CrmApiException


CENT = Decimal("0.01")
MAX_DECIMAL_20_2 = Decimal("999999999999999999.99")


class MoneyValidationError(ValueError):
    """Raised when a value cannot satisfy the DECIMAL(20,2) contract."""


def as_decimal(value: Any) -> Decimal:
    if isinstance(value, (bool, float)):
        raise MoneyValidationError("money must be supplied as an exact decimal value")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MoneyValidationError("money must be a decimal value") from exc
    if (
        not parsed.is_finite()
        or parsed < 0
        or parsed > MAX_DECIMAL_20_2
        or parsed.as_tuple().exponent < -2
    ):
        raise MoneyValidationError("money must fit DECIMAL(20,2)")
    return parsed.quantize(CENT)


def decimal_string(value: Any) -> str:
    return format(as_decimal(value), ".2f")


def required_positive_money(value: Any, fieldname: str) -> Decimal:
    """A money input someone must fill in: positive, with at most two decimal places."""

    if value is None or str(value).strip() == "":
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} is required.", field_errors={fieldname: "Required"})
    message = f"{fieldname} must be positive with at most two decimal places."
    try:
        parsed = as_decimal(value)
    except MoneyValidationError as exc:
        raise CrmApiException("VALIDATION_ERROR", message, field_errors={fieldname: "Invalid amount"}) from exc
    if not parsed:
        raise CrmApiException("VALIDATION_ERROR", message, field_errors={fieldname: "Invalid amount"})
    return parsed


def optional_money_text(value: Any) -> str:
    """Zero is an amount nobody has entered yet, so it goes out as an empty string."""

    amount = as_decimal(value or 0)
    return decimal_string(amount) if amount else ""


def weighted_decimal_string(value: Any, probability: Any) -> str:
    try:
        percentage = Decimal(str(probability))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MoneyValidationError("probability must be numeric") from exc
    if not percentage.is_finite() or percentage < 0 or percentage > 100:
        raise MoneyValidationError("probability must be between 0 and 100")
    weighted = (as_decimal(value) * percentage / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
    return format(weighted, ".2f")


def aggregate_by_currency(
    rows: Iterable[Mapping[str, Any]],
    *,
    amount_key: str = "amount",
    currency_key: str = "currency",
) -> list[dict[str, str]]:
    totals: dict[str, Decimal] = {}
    for row in rows:
        currency = str(row.get(currency_key) or "").strip().upper()
        if not currency:
            raise MoneyValidationError("currency is required for aggregation")
        totals[currency] = totals.get(currency, Decimal("0.00")) + as_decimal(row.get(amount_key))
        if totals[currency] > MAX_DECIMAL_20_2:
            raise MoneyValidationError("currency aggregate exceeds DECIMAL(20,2)")
    return [
        {"currency": currency, "amount": format(amount, ".2f")}
        for currency, amount in sorted(totals.items())
    ]
