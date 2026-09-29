"""Leave one row per equipment type before the unique index on ``equipment_name`` is created.

The first catalog sync registered every stored spelling ("nansi" next to the preset "Nansi",
"kibo-4895c" next to "Kibo 4895C"). Spellings that differ only in case, accents, spacing or
punctuation are one type, so the later duplicates and the preset spellings go; the rows kept are the ones
registered first. Opportunities are not touched.
"""

import frappe

from rayher_crm.services.equipment_names import EQUIPMENT_PRESETS, equipment_key


def execute():
    if not frappe.db.table_exists("CRM Equipment Type"):
        return
    rows = frappe.db.sql(
        "SELECT `name`, `equipment_name` FROM `tabCRM Equipment Type` ORDER BY `creation` ASC, `name` ASC", as_dict=True,
    )
    seen = {equipment_key(preset) for preset in EQUIPMENT_PRESETS}
    duplicates = []
    for row in rows:
        key = equipment_key(row.equipment_name)
        if key in seen:
            duplicates.append(row.name)
        else:
            seen.add(key)
    if duplicates:
        frappe.db.delete("CRM Equipment Type", {"name": ["in", duplicates]})
    # The index also folds a few characters the key keeps apart ("〇" and "0"); of those
    # rows, too, the one registered first stays.
    frappe.db.sql(
        """DELETE later FROM `tabCRM Equipment Type` later JOIN `tabCRM Equipment Type` earlier
        ON earlier.`equipment_name` = later.`equipment_name`
        AND (earlier.`creation`, earlier.`name`) < (later.`creation`, later.`name`)"""
    )
