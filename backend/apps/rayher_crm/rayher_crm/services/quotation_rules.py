"""Pure pricing and validation rules for CRM quotations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from rayher_crm.services.money import MoneyValidationError, as_decimal


MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.0001")


class QuotationRuleError(ValueError):
    """Raised when a quotation violates a publishable business rule."""


def _decimal(value: Any, field: str, *, scale: Decimal = MONEY_QUANTUM) -> Decimal:
    if scale == MONEY_QUANTUM:
        try:
            return as_decimal(value)
        except MoneyValidationError as exc:
            raise QuotationRuleError(f"{field} must fit DECIMAL(20,2).") from exc
    if isinstance(value, bool):
        raise QuotationRuleError(f"{field} must be numeric.")
    try:
        parsed = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError) as exc:
        raise QuotationRuleError(f"{field} must be numeric.") from exc
    if not parsed.is_finite() or parsed < 0 or parsed.as_tuple().exponent < scale.as_tuple().exponent:
        raise QuotationRuleError(f"{field} must be non-negative.")
    return parsed.quantize(scale, rounding=ROUND_HALF_UP)


def _quantity(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise QuotationRuleError("quantity must be numeric.")
    try:
        parsed = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError) as exc:
        raise QuotationRuleError("quantity must be numeric.") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise QuotationRuleError("quantity must be greater than zero.")
    if parsed != parsed.to_integral_value():
        raise QuotationRuleError("quantity must be a whole number.")
    return parsed


def money_string(value: Decimal) -> str:
    return f"{value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP):.2f}"


def calculate_totals(
    items: list[dict[str, Any]],
    *,
    discount_type: str,
    discount_value: Any,
    currency: str = "CNY",
) -> dict[str, Any]:
    if currency != "CNY":
        raise QuotationRuleError("Quotation currency must be CNY.")

    device_groups: dict[str, dict[str, Any]] = {}
    system_parents: dict[str, str] = {}
    for item in items:
        line_type = item.get("lineType")
        line_key = str(item.get("lineKey") or "").strip()
        if line_type == "Device":
            if not line_key or line_key in device_groups:
                raise QuotationRuleError("Each device must have a unique lineKey.")
            quantity = _quantity(item.get("quantity"))
            line_amount = quantity * _decimal(item.get("unitPrice"), "unitPrice")
            device_groups[line_key] = {"quantity": quantity, "subtotal": line_amount}
        elif line_type == "System":
            parent_key = str(item.get("parentDeviceKey") or "").strip()
            if not line_key or line_key in system_parents:
                raise QuotationRuleError("Each system must have a unique lineKey.")
            if parent_key not in device_groups:
                raise QuotationRuleError("System must reference an existing parent device.")
            system_parents[line_key] = parent_key
        elif line_type != "Accessory":
            raise QuotationRuleError("lineType must be Device, System or Accessory.")

    subtotal = sum((group["subtotal"] for group in device_groups.values()), Decimal("0"))
    for item in items:
        if item.get("lineType") != "Accessory":
            continue
        quantity = _quantity(item.get("quantity"))
        parent_key = str(item.get("parentDeviceKey") or "").strip()
        if parent_key not in device_groups:
            raise QuotationRuleError("Accessory must reference an existing parent device.")
        parent_system_key = str(item.get("parentSystemKey") or "").strip()
        if parent_system_key and system_parents.get(parent_system_key) != parent_key:
            raise QuotationRuleError("Accessory must reference a system under the same parent device.")
        pricing_mode = item.get("pricingMode")
        if pricing_mode not in {"Included", "Charged"}:
            raise QuotationRuleError("Accessory pricingMode must be Included or Charged.")
        if pricing_mode == "Included":
            continue
        line_amount = quantity * _decimal(item.get("unitPrice"), "unitPrice")
        device_groups[parent_key]["subtotal"] += line_amount
        subtotal += line_amount

    subtotal = subtotal.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if discount_type == "None":
        _decimal(discount_value, "discountValue")
        discount_amount = Decimal("0")
    elif discount_type == "Percentage":
        value = _decimal(discount_value, "discountValue", scale=PERCENT_QUANTUM)
        if value > Decimal("100"):
            raise QuotationRuleError("Percentage discount cannot exceed 100.")
        discount_amount = (subtotal * value / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    elif discount_type == "Fixed Amount":
        discount_amount = _decimal(discount_value, "discountValue")
    else:
        raise QuotationRuleError("discountType must be None, Percentage or Fixed Amount.")
    if discount_amount > subtotal:
        raise QuotationRuleError("Discount cannot exceed quotation subtotal.")

    serialized_groups = []
    for line_key, group in device_groups.items():
        group_subtotal = group["subtotal"].quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        serialized_groups.append({
            "lineKey": line_key,
            "quantity": int(group["quantity"]),
            "configurationSubtotal": money_string(group_subtotal),
            "configurationUnitTotal": money_string(group_subtotal / group["quantity"]),
        })
    return {
        "subtotal": money_string(subtotal),
        "discountAmount": money_string(discount_amount),
        "total": money_string(subtotal - discount_amount),
        "deviceGroups": serialized_groups,
    }


def validate_payment_terms(terms: list[dict[str, Any]], *, publishing: bool) -> None:
    total = sum((_decimal(term.get("percentage"), "payment percentage", scale=PERCENT_QUANTUM) for term in terms), Decimal("0"))
    if publishing and total != Decimal("100.0000"):
        raise QuotationRuleError("Payment percentages must total 100 when publishing.")