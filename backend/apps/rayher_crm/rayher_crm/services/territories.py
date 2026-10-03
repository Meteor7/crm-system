"""Sales territories: the stored tree over the Customer regions. Its rules are in territory_tree.

Territories classify and total. They are in no permission rule.
"""

from __future__ import annotations

import frappe

from rayher_crm.services.regions import REGION_PRESETS
from rayher_crm.services.territory_tree import ordered

DOCTYPE = "CRM Sales Territory"
# The tree every site starts with. The business names the rest of it later (#17).
DEFAULT_TERRITORIES = (
    ("World", None), ("Asia", "World"), ("China", "Asia"), *((region, "China") for region in REGION_PRESETS),
)


def ensure_default_territories() -> None:
    """Seed the default tree once: a site that has territories keeps them as they are."""

    if frappe.db.count(DOCTYPE):
        return
    for position, (name, parent) in enumerate(DEFAULT_TERRITORIES):
        frappe.get_doc({
            "doctype": DOCTYPE, "territory_name": name, "parent_territory": parent, "sort_order": position,
        }).insert(ignore_permissions=True)


def region_tree(regions: list[str]) -> tuple[list[str], dict[str, str]]:
    """Every name a region filter can select, in display order, and the parent of each that has one.

    The territories come first, each before the ones below it; the regions no territory is named after follow.
    """

    rows = frappe.get_all(
        DOCTYPE, fields=["name", "parent_territory as parent", "sort_order"], limit_page_length=0,
    )
    return ordered(rows, regions)
