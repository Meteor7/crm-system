"""Reconcile legacy leaf spelling with the registered region's database identity.

Leaves retain their exact registered spelling, including legacy case variants.
A leaf with no exact registered option uses the canonical registered spelling.
A legacy group occupying a region's identity
gets a distinct group name, freeing the original region for explicit placement in
the administration UI. Customer values and existing hierarchy are preserved;
Frappe rename updates links, the naming field and audit references together.
"""
import json

import frappe
from frappe.model.rename_doc import rename_doc

from rayher_crm.services.regions import list_regions
from rayher_crm.services.territory_admin import group_name_reserves_region


def _available_group_name(old, registered):
    suffix_number = 1
    while True:
        suffix = " (Territory Group)" if suffix_number == 1 else f" (Territory Group {suffix_number})"
        candidate = old[:100 - len(suffix)] + suffix
        if not group_name_reserves_region(candidate, registered) and not frappe.db.get_value(
            "CRM Sales Territory", candidate, "name", for_update=True
        ):
            return candidate
        suffix_number += 1


def _retarget_saved_regions(old, target, retained_region):
    """Preserve the set a saved group predicate selected before the rename.

    Query predicates use exact Python membership. Retain the old group spelling
    only when it is itself a registered Customer region, even if a different
    case variant was the first option to discover the database collision.
    """
    doctype = "CRM Opportunity Saved Query"
    replacement = [target, retained_region] if retained_region is not None else [target]

    def expand(values):
        if not isinstance(values, list) or old not in values:
            return values
        return list(dict.fromkeys(item for value in values for item in (replacement if value == old else [value])))

    def visit(group):
        for node in group.get("conditions", []):
            if "conditions" in node:
                visit(node)
            elif node.get("field") == "region":
                node["value"] = expand(node.get("value"))

    for row in frappe.db.sql("SELECT name, definition FROM `tabCRM Opportunity Saved Query` FOR UPDATE", as_dict=True):
        definition = json.loads(row.definition)
        before = json.dumps(definition, ensure_ascii=False)
        scope = definition.get("scope", {})
        if "regions" in scope:
            scope["regions"] = expand(scope["regions"])
        visit(definition)
        after = json.dumps(definition, ensure_ascii=False)
        if before != after:
            doc = frappe.get_doc(doctype, row.name, for_update=True)
            doc.definition = after
            doc.save(ignore_permissions=True, ignore_version=False)


def execute():
    doctype = "CRM Sales Territory"
    frappe.db.sql("SELECT name FROM `tabDocType` WHERE name=%s FOR UPDATE", (doctype,))
    # Safe on repeated execution: preserve explicitly declared empty groups.
    from rayher_crm.patches.v1_0.initialize_territory_administration import execute as initialize
    initialize()
    registered = list_regions(for_update=True)
    reconciled = set()
    for canonical in registered:
        rows = frappe.db.sql(
            "SELECT name, is_group FROM `tabCRM Sales Territory` WHERE name=%s FOR UPDATE",
            (canonical,), as_dict=True,
        )
        if not rows or rows[0].name in reconciled:
            continue
        old = rows[0].name
        target = _available_group_name(old, registered) if rows[0].is_group else (old if old in registered else canonical)
        if old != target:
            rename_doc(doctype, old, target, force=True, ignore_permissions=True,
                              show_alert=False, rebuild_search=False)
            # Saved definitions contain JSON strings, not native Link fields.
            # A case-only leaf rename must update those references as well.
            retained_region = old if rows[0].is_group and old in registered else None
            _retarget_saved_regions(old, target, retained_region)
        reconciled.add(canonical)
