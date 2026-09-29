"""Opportunity equipment types: five presets plus the custom types Sales add, like regions.

``CRM Opportunity.tool_type`` stores the type as text. The options are the presets below,
followed by the custom types kept in ``CRM Equipment Type`` in the order they were added.

- A new entry that is a preset in another case or spacing ("NANSI", "Nan-si") is stored as the
  preset; one that matches an existing custom type that way reuses its spelling.
- Anything else becomes a new custom type when the Opportunity is saved. Text is stored after
  NFKC (full-width letters become ASCII) with invisible format characters removed, compared by
  its letters and digits only, and a type without a letter or digit is refused.
- Every change to the catalog, and every save that uses a custom type, first locks one fixed row,
  so two saves cannot add the same type twice and ``sync`` cannot drop a type a save is using.
- An Opportunity saved without changing its type keeps the stored spelling, so values from
  before the catalog are never rewritten. Spellings that differ only in case, accents, spacing or
  punctuation are one type (``services.equipment_names``): the board shows and filters them
  under the catalog spelling.
- ``setup.equipment_types.sync`` registers each stored type once on migrate and drops custom
  types nobody uses any more.
"""

from __future__ import annotations

import re
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability
from rayher_crm.services.equipment_names import EQUIPMENT_PRESETS, equipment_key, normalized_text  # noqa: F401 - re-exported


EQUIPMENT_TYPE = "CRM Equipment Type"
MAX_EQUIPMENT_TEXT = 140
# Angle brackets are refused because Frappe rewrites them on the Opportunity's Data field.
_REFUSED = re.compile(r"[\x00-\x1f\x7f<>]")


def custom_equipment_types() -> list[str]:
    rows = frappe.get_all(EQUIPMENT_TYPE, fields=["equipment_name"], order_by="creation asc, name asc", limit_page_length=0)
    return [row.equipment_name for row in rows if row.equipment_name]


def list_equipment_types() -> list[str]:
    """Presets first, then custom types in the order they were added, one spelling per type."""

    result = list(EQUIPMENT_PRESETS)
    keys = {equipment_key(item) for item in result}
    for value in custom_equipment_types():
        key = equipment_key(value)
        if key not in keys:
            keys.add(key)
            result.append(value)
    return result


def list_equipment_type_options() -> list[str]:
    assert_capability("deal:view")
    return list_equipment_types()


def matching_equipment(value: str, options: list[str]) -> str:
    """The stored spelling for a submitted type, or "" when it would be a new custom type."""

    key = equipment_key(value)
    preset = next((item for item in EQUIPMENT_PRESETS if equipment_key(item) == key), "")
    if preset:
        return preset
    if value in options:
        return value
    return next((option for option in options if equipment_key(option) == key), "")


def normalize_equipment(value: Any, fieldname: str) -> str:
    """Validate a submitted type and return the spelling it will be stored as; writes nothing."""

    text = " ".join(normalized_text(value).split()) if isinstance(value, str) else ""
    if not text:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} is required.", field_errors={fieldname: "Required"})
    if len(text) > MAX_EQUIPMENT_TEXT or _REFUSED.search(text):
        raise CrmApiException(
            "VALIDATION_ERROR",
            f"{fieldname} must be at most {MAX_EQUIPMENT_TEXT} characters without control characters or < >.",
            field_errors={fieldname: "Invalid value"},
        )
    if not equipment_key(text):
        raise CrmApiException(
            "VALIDATION_ERROR", f"{fieldname} must contain a letter or a digit.", field_errors={fieldname: "Invalid value"},
        )
    return matching_equipment(text, list_equipment_types()) or text


def lock_catalog() -> list[str]:
    """Serialize catalog changes on one fixed row (the catalog table itself may be empty) and
    return the custom types as last committed, which a plain read under an older snapshot may miss."""

    frappe.db.sql("SELECT `name` FROM `tabDocType` WHERE `name` = %s FOR UPDATE", (EQUIPMENT_TYPE,))
    rows = frappe.db.sql(f"SELECT `equipment_name` FROM `tab{EQUIPMENT_TYPE}` ORDER BY `creation`, `name` FOR UPDATE")
    return [row[0] for row in rows if row[0]]


def register_equipment(value: str) -> str:
    """Make sure a custom type is in the options; call it inside the saving request's savepoint.

    A save that uses a custom type holds the catalog lock until it commits, so ``sync`` never
    drops that type in between.
    """

    preset = next((item for item in EQUIPMENT_PRESETS if equipment_key(item) == equipment_key(value)), "")
    if preset:
        return preset
    match = matching_equipment(value, [*EQUIPMENT_PRESETS, *lock_catalog()])
    if match:
        return match
    # The unique index compares with the column's collation, which still folds a few characters
    # the key keeps apart (for example "〇" and "0"); reuse that row instead of failing the insert.
    same = frappe.db.sql(
        f"SELECT `equipment_name` FROM `tab{EQUIPMENT_TYPE}` WHERE `equipment_name` = %s LIMIT 1 FOR UPDATE", (value,),
    )
    if same:
        return same[0][0]
    frappe.get_doc({"doctype": EQUIPMENT_TYPE, "equipment_name": value}).insert(ignore_permissions=True)
    return value
