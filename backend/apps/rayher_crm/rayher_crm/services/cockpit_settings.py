"""Warnings thresholds a Manager edits on the page; site config and the built-in default are the fallbacks."""
from __future__ import annotations

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.services.common import as_payload, normalize_expected_modified, to_iso_timestamp
from rayher_crm.services.cockpit_metrics import number

SETTINGS = "CRM Cockpit Settings"
# field: (API key, site config key, default, lowest value). A quotation threshold of 0 flags only quotes expiring today.
THRESHOLDS = {
    "quote_expiry_days": ("quoteExpiryDays", "crm_cockpit_quote_expiry_days", 14, 0),
    "stage6_no_po_days": ("stage6NoPoDays", "crm_cockpit_stage6_no_po_days", 30, 1),
}


def _conf_value(raw, lowest):
    if raw in (None, ""):
        return None
    value = number(raw)
    if value is None or value != value.to_integral_value() or not lowest <= value <= 365:
        return None
    return int(value)


def _conf(key, default, lowest):
    return _conf_value(frappe.conf.get(key, default), lowest)


def thresholds(*, for_update=False) -> dict[str, tuple[int, str]]:
    """Each threshold with where it came from: settings, site_config or default."""
    result = {}
    # Raw rows, not get_single_value: an Int never saved would read as 0, which is a valid quotation threshold.
    if for_update:
        # Same lock as save_settings, including the first save with no Singles
        # rows yet. Handling must use current thresholds, not an older snapshot.
        frappe.db.sql("SELECT `name` FROM `tabDocType` WHERE `name` = %s FOR UPDATE", (SETTINGS,))
    saved = dict(frappe.db.sql("SELECT `field`, `value` FROM `tabSingles` WHERE `doctype` = %s" + (" FOR UPDATE" if for_update else ""), (SETTINGS,)))
    # A row that install or migrate may leave has every Int at 0 (an upgrade leaves none); only a Manager's save counts.
    if saved.get("configured") != "1":
        saved = {}
    for field, (_, key, default, lowest) in THRESHOLDS.items():
        value = _conf_value(saved.get(field), lowest)
        if value is not None:
            result[field] = (value, "settings")
        elif key in frappe.conf and _conf(key, default, lowest) is not None:
            result[field] = (_conf(key, default, lowest), "site_config")
        else:
            result[field] = (default, "default")
    return result


def _require_manager():
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Warnings settings are available to CRM Managers only.")


def _modified():
    # The settings row may not exist before the first save, so the DocType row is the lock that
    # serializes saves; the locking read below then sees the latest committed version.
    frappe.db.sql("SELECT `name` FROM `tabDocType` WHERE `name` = %s FOR UPDATE", (SETTINGS,))
    meta = dict(frappe.db.sql("SELECT `field`, `value` FROM `tabSingles` WHERE `doctype` = %s AND `field` IN ('modified', 'configured') FOR UPDATE",
                              (SETTINGS,)))
    # A row left by install/migrate has no saved version yet, like no row at all.
    return meta.get("modified") if meta.get("configured") == "1" else None


def _dto():
    values = thresholds()
    modified = frappe.db.sql("SELECT `field`, `value` FROM `tabSingles` WHERE `doctype` = %s AND `field` IN ('modified', 'modified_by', 'configured')", (SETTINGS,))
    meta = dict(modified) if dict(modified).get("configured") == "1" else {}
    return {**{api: values[field][0] for field, (api, *_rest) in THRESHOLDS.items()},
            "sources": {api: values[field][1] for field, (api, *_rest) in THRESHOLDS.items()},
            "modified": to_iso_timestamp(meta["modified"]) if meta.get("modified") else None,
            "modifiedBy": meta.get("modified_by") or None,
            "modifiedByName": (frappe.db.get_value("User", meta["modified_by"], "full_name") or meta["modified_by"]) if meta.get("modified_by") else None}


def get_settings() -> dict:
    _require_manager()
    return _dto()


def save_settings(payload, expected_modified=None) -> dict:
    _require_manager()
    payload = as_payload(payload)
    values, errors = {}, {}
    for field, (api, _key, _default, lowest) in THRESHOLDS.items():
        value = payload.get(api)
        text = str(value).strip() if isinstance(value, (int, str)) and not isinstance(value, bool) else ""
        # ASCII digits only: str.isdigit() also accepts superscripts that int() rejects.
        if not (text.isascii() and text.isdecimal()) or not lowest <= int(text) <= 365:
            errors[api] = f"Enter a whole number of days from {lowest} to 365"
        else:
            values[field] = int(text)
    if errors:
        raise CrmApiException("VALIDATION_ERROR", "Thresholds must be whole days (quotation 0–365, stage 6 1–365).", field_errors=errors)
    # The settings row is the lock: a stale page must reload rather than overwrite a newer save.
    current = _modified()
    doc = frappe.get_single(SETTINGS)
    saved = thresholds()
    if all(saved[field] == (value, "settings") for field, value in values.items()):
        # A retried save that already landed returns the saved values instead of a conflict.
        return _dto()
    expected = normalize_expected_modified(expected_modified) if expected_modified else None
    if (to_iso_timestamp(current) if current else None) != expected:
        raise CrmApiException("VERSION_CONFLICT", "The thresholds were changed by someone else. Reload before saving.")
    doc.update({**values, "configured": 1})
    # Track changes keeps a Version row per save: who changed which threshold, and when.
    doc.save(ignore_permissions=True)
    return _dto()
