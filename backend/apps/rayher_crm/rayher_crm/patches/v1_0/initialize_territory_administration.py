"""Classify existing tree nodes by their actual children; never infer sales ownership."""
import frappe


def execute():
    # Model sync adds is_group with default 0 on legacy sites. Only actual
    # parents are promoted here; explicit empty groups remain groups on reruns.
    frappe.db.sql("SELECT name FROM `tabDocType` WHERE name='CRM Sales Territory' FOR UPDATE")
    # Link fields on old sites may contain a spelling MariaDB resolves to the
    # parent even though Python's exact-name tree does not. Resolve that identity
    # before deriving node types, without guessing missing parents.
    frappe.db.sql("""UPDATE `tabCRM Sales Territory` child
        INNER JOIN `tabCRM Sales Territory` parent ON parent.name=child.parent_territory
        SET child.parent_territory=parent.name""")
    rows = frappe.get_all("CRM Sales Territory", fields=["name", "parent_territory", "is_group"], limit_page_length=0)
    parents = {row.parent_territory for row in rows if row.parent_territory}
    for row in rows:
        frappe.db.set_value("CRM Sales Territory", row.name, "is_group", int(bool(row.is_group) or row.name in parents), update_modified=False)
    # No owner or Customer region is changed. Unmapped region names remain selectable
    # and are reported in the administration page for an explicit mapping decision.
