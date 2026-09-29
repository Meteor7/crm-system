"""Customer regions: five domestic presets stored in English, plus regions Sales add along the way.

The options live on the ``Customer.custom_crm_region`` Select field, and the Opportunity
``sub_region`` column draws from the same list.

- A Chinese or short spelling of a preset ("华东", "华东区", "East") is stored as the preset.
- A custom region that differs from an existing option only in case, spacing or punctuation
  reuses the existing spelling, so the list does not grow near-duplicates.
- New custom regions must be written in English, like the presets.
- A custom region nobody uses any more is dropped from the options on the next migrate.
"""

from __future__ import annotations

import re
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException


REGION_PRESETS = ("East China", "South China", "West China", "North China", "Central China")
REGION_FIELD = "Customer-custom_crm_region"

_PRESET_ALIASES = {
    "East China": ("华东", "華東", "east", "eastern", "eastchina", "easternchina"),
    "South China": ("华南", "華南", "south", "southern", "southchina", "southernchina"),
    "West China": ("华西", "華西", "west", "western", "westchina", "westernchina"),
    "North China": ("华北", "華北", "north", "northern", "northchina", "northernchina"),
    "Central China": ("华中", "華中", "central", "centralchina"),
}
_ALIAS_TO_PRESET = {alias: preset for preset, aliases in _PRESET_ALIASES.items() for alias in aliases}
_CHINESE_PREFIXES = ("中国",)
_CHINESE_SUFFIXES = ("大区", "地区", "区域", "区")
_LATIN_SUFFIXES = ("region", "area")
_SEPARATORS = re.compile(r"[\s\-_/\\()（）.,，、·:：]+")
_RUNS = re.compile(r"[㐀-鿿]+|[a-z]+|[^㐀-鿿a-z]+")
_HAN = re.compile(r"[㐀-鿿]")
_ENGLISH_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 &'().,/-]*$")


def collapse_region(value: Any) -> str:
    return " ".join(str(value or "").split())


def region_key(value: Any) -> str:
    """Compare regions ignoring case, spacing and punctuation."""

    return _SEPARATORS.sub("", collapse_region(value).casefold())


def _strip_affixes(text: str, prefixes: tuple[str, ...], suffixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if text.startswith(prefix) and len(text) > len(prefix):
            text = text[len(prefix):]
            break
    for suffix in suffixes:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def preset_region(value: Any) -> str:
    """Return the preset a spelling stands for, or "" when it names no preset.

    Chinese and English parts must agree: "华东 East China" is East China, "华东/华南" is not a preset.
    """

    key = region_key(value)
    if not key:
        return ""
    runs = _RUNS.findall(key)
    if any(not (_HAN.match(run) or run.isalpha()) for run in runs):
        return ""
    chinese = "".join(run for run in runs if _HAN.match(run))
    latin = "".join(run for run in runs if not _HAN.match(run))
    presets = set()
    if chinese:
        presets.add(_ALIAS_TO_PRESET.get(_strip_affixes(chinese, _CHINESE_PREFIXES, _CHINESE_SUFFIXES)))
    if latin:
        presets.add(_ALIAS_TO_PRESET.get(latin) or _ALIAS_TO_PRESET.get(_strip_affixes(latin, (), _LATIN_SUFFIXES)))
    return presets.pop() if len(presets) == 1 and None not in presets else ""


def is_english_region(value: Any) -> bool:
    return bool(_ENGLISH_NAME.match(collapse_region(value)))


def options_text(options: list[str]) -> str:
    """Select options with a blank first line, so a new Customer never defaults to East China."""

    return "\n".join(["", *options])


def region_options(raw_options: Any) -> list[str]:
    """Presets first, then custom regions in the order Sales added them."""

    result: list[str] = []
    for value in [*REGION_PRESETS, *str(raw_options or "").splitlines()]:
        normalized = collapse_region(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def matching_region(value: Any, options: list[str]) -> str:
    """Return the stored spelling for a submitted region, or "" when it is a new custom region."""

    preset = preset_region(value)
    if preset:
        return preset
    key = region_key(value)
    return next((option for option in options if region_key(option) == key), "")


def _region_field(*, for_update: bool = False) -> dict[str, Any]:
    lock = " FOR UPDATE" if for_update else ""
    rows = frappe.db.sql(
        "SELECT `name`, `fieldtype`, `options` FROM `tabCustom Field` "
        "WHERE `dt` = 'Customer' AND `fieldname` = 'custom_crm_region' LIMIT 1" + lock,
        as_dict=True,
    )
    if not rows:
        raise CrmApiException("INTERNAL_ERROR", "Customer region field is not configured.")
    return rows[0]


def list_regions() -> list[str]:
    return region_options(_region_field().get("options"))


def _require_region_text(value: Any, fieldname: str) -> str:
    text = collapse_region(value)
    if not text:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} is required.", field_errors={fieldname: "Required"})
    return text


def resolve_region(value: Any, fieldname: str) -> str:
    """Return the stored spelling of an existing region; unknown regions are rejected."""

    text = _require_region_text(value, fieldname)
    match = matching_region(text, list_regions())
    if not match:
        raise CrmApiException(
            "VALIDATION_ERROR", f"{fieldname} is not a known region.", field_errors={fieldname: "Unknown region"},
        )
    return match


def register_region(value: Any, fieldname: str = "region") -> str:
    """Return the stored spelling for a submitted region, adding a new custom region to the shared options."""

    text = _require_region_text(value, fieldname)
    match = matching_region(text, list_regions())
    if match:
        return match
    if not is_english_region(text):
        raise CrmApiException(
            "VALIDATION_ERROR",
            f"{fieldname} must be an English region name.",
            field_errors={fieldname: "Use an English region name"},
        )
    field = _region_field(for_update=True)
    options = region_options(field.get("options"))
    match = matching_region(text, options)
    if match:
        return match
    frappe.db.set_value("Custom Field", field["name"], "options", options_text([*options, text]), update_modified=False)
    frappe.clear_cache(doctype="Customer")
    return text
