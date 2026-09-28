"""Normalize legacy values before enforcing the frozen CRM enums."""

from __future__ import annotations

import frappe

from rayher_crm.services.opportunities import (
    ACTION_STATUSES,
    STAKEHOLDER_INFLUENCES,
    STAKEHOLDER_ROLES,
    STAKEHOLDER_STANCES,
)
from rayher_crm.services.opportunity_stages import OPPORTUNITY_STAGES


def _replace(doctype: str, fieldname: str, mapping: dict[str, str]) -> None:
    table = f"tab{doctype}"
    for old_value, new_value in mapping.items():
        frappe.db.sql(f"UPDATE `{table}` SET `{fieldname}` = %s WHERE `{fieldname}` = %s", (new_value, old_value))


def _assert_known(doctype: str, fieldname: str, allowed: tuple[str, ...]) -> None:
    table = f"tab{doctype}"
    placeholders = ", ".join(["%s"] * len(allowed))
    unknown = frappe.db.sql(
        f"SELECT DISTINCT `{fieldname}` FROM `{table}` WHERE COALESCE(`{fieldname}`, '') != '' AND `{fieldname}` NOT IN ({placeholders})",
        allowed,
    )
    if unknown:
        raise RuntimeError(f"Unknown {doctype}.{fieldname} enum values require an explicit migration.")


def normalize_crm_enums() -> None:
    # Legacy Opportunity stages and their old aliases are rewritten by the
    # migrate_opportunity_seven_stages patch, which runs before this hook.
    _replace("CRM Opportunity Stakeholder", "stance", {
        "Supportive": "Support", "Supporter": "Support", "Champion": "Support", "Detractor": "Against",
    })
    _replace("CRM Opportunity Action", "status", {"Completed": "Done"})
    _assert_known("CRM Opportunity", "stage", OPPORTUNITY_STAGES)
    _assert_known("CRM Opportunity Stakeholder", "role", STAKEHOLDER_ROLES)
    _assert_known("CRM Opportunity Stakeholder", "influence", STAKEHOLDER_INFLUENCES)
    _assert_known("CRM Opportunity Stakeholder", "stance", STAKEHOLDER_STANCES)
    _assert_known("CRM Opportunity Action", "status", ACTION_STATUSES)
