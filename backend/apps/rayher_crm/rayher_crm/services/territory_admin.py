"""Manager maintenance of territory classification and effective sales assignments.

Territories never grant access to a Customer or Opportunity. A catalogue lock serializes
tree edits and assignment changes, including the first assignment for an empty region.
"""
import re

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import resolve_crm_role
from rayher_crm.services.common import as_payload, optional_date, required_text, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.regions import collapse_region, is_english_region, list_regions, matching_region, register_region
from rayher_crm.services.territory_rules import date_range, overlaps, validate_tree

TERRITORY = "CRM Sales Territory"
ASSIGNMENT = "CRM Territory Assignment"
TREE_FIELDS = ["name", "parent_territory", "is_group", "enabled", "sort_order", "modified"]
ASSIGNMENT_FIELDS = ["name", "territory", "sales_owner", "valid_from", "valid_until", "cancelled", "note", "modified"]


def require_manager():
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Territory administration is available to CRM Managers only.")


def lock_catalogue():
    frappe.db.sql("SELECT `name` FROM `tabDocType` WHERE `name` = %s FOR UPDATE", (TERRITORY,))


def tree_rows(*, for_update=False):
    if for_update:
        return frappe.db.sql(
            "SELECT `name`, `parent_territory`, `is_group`, `enabled`, `sort_order`, `modified` "
            "FROM `tabCRM Sales Territory` FOR UPDATE", as_dict=True,
        )
    return frappe.get_all(TERRITORY, fields=TREE_FIELDS, limit_page_length=0)


def territory_dto(row):
    return {"name": row.name, "parent": row.parent_territory or None, "isGroup": bool(row.is_group),
            "enabled": bool(row.enabled), "sortOrder": row.sort_order or 0, "modified": to_iso_timestamp(row.modified)}


def assignment_dto(row):
    return {"id": row.name, "territory": row.territory, "salesOwner": row.sales_owner,
            "validFrom": str(row.valid_from), "validUntil": str(row.valid_until) if row.valid_until else None,
            "cancelled": bool(row.cancelled), "note": row.note or "", "modified": to_iso_timestamp(row.modified)}


def catalogue():
    require_manager()
    rows = tree_rows()
    known = {row.name for row in rows if not row.is_group}
    sales = frappe.get_all("Has Role", filters={"role": "CRM Sales", "parenttype": "User"}, pluck="parent")
    people = frappe.get_all("User", filters={"name": ["in", sales], "enabled": 1}, fields=["name", "full_name"]) if sales else []
    return {"territories": [territory_dto(row) for row in rows],
            "assignments": [assignment_dto(row) for row in frappe.get_all(ASSIGNMENT, fields=ASSIGNMENT_FIELDS, order_by="valid_from desc, name", limit_page_length=0)],
            "unmappedRegions": [name for name in list_regions() if name not in known],
            "sales": [{"id": row.name, "name": row.full_name or row.name} for row in people if active_sales(row.name)],
            "today": str(frappe.utils.getdate())}


def boolean(payload, name):
    value = payload.get(name)
    if not isinstance(value, bool):
        raise CrmApiException("VALIDATION_ERROR", f"{name} must be true or false.")
    return int(value)


def group_name_reserves_region(title, registered):
    if matching_region(title, registered):
        return True
    if not registered:
        return False
    # Legacy options can contain non-ASCII names. Compare their database
    # identity without expanding region aliases or rewriting stored values.
    charset, collation = frappe.db.sql("""SELECT CHARACTER_SET_NAME, COLLATION_NAME
        FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
        AND TABLE_NAME='tabCRM Sales Territory' AND COLUMN_NAME='name'""")[0]
    if not all(re.fullmatch(r"[A-Za-z0-9_]+", value or "") for value in (charset, collation)):
        frappe.throw("The territory name column has an invalid character set or collation.")
    placeholders = ", ".join(["%s"] * len(registered))
    return bool(frappe.db.sql(
        f"SELECT CONVERT(%s USING {charset}) COLLATE {collation} IN ({placeholders})",
        (title, *registered),
    )[0][0])


def validate_territory_document(doc):
    lock_catalogue()
    registered = None
    if doc.is_new():
        title = doc.territory_name
        if title != collapse_region(title) or not is_english_region(title) or len(title) > 100:
            frappe.throw("Use an English territory name of at most 100 characters.")
        if doc.name != title:
            frappe.throw("A new territory ID must match its territory name.")
        registered = list_regions(for_update=True)
        canonical = title if title in registered else matching_region(title, registered)
        if doc.is_group and group_name_reserves_region(title, registered):
            frappe.throw("This name belongs to a customer region. Place it as a region or choose a different group name.")
        if not doc.is_group and canonical and canonical != title:
            frappe.throw("Use the exact registered customer region name when creating a leaf territory.")
    rows = tree_rows(for_update=True)
    if doc.is_new() and doc.is_group and matching_region(doc.territory_name, [row.name for row in rows]):
        frappe.throw("A territory with this name already exists.")
    changed = {"name": doc.name or doc.territory_name, "parent_territory": doc.parent_territory,
               "is_group": doc.is_group, "enabled": doc.enabled}
    try:
        validate_tree(rows, changed)
    except ValueError as exc:
        frappe.throw(str(exc))
    before = doc.get_doc_before_save()
    if before and (doc.territory_name != before.territory_name or doc.is_group != before.is_group):
        frappe.throw("Territory names and node types cannot be changed; move or deactivate the existing territory.")
    if registered is not None and not doc.is_group and doc.territory_name not in registered:
        # Native Desk/integration inserts use the same catalogue lock and region
        # registration as the CRM API. Existing legacy names remain maintainable.
        register_region(doc.territory_name)


def save_territory(payload, name=None, expected_modified=None):
    require_manager()
    payload = as_payload(payload)
    if payload.get("id"):
        raise CrmApiException("VALIDATION_ERROR", "A territory ID is generated from its name.")
    lock_catalogue()
    rows = tree_rows(for_update=True)
    existing = {row.name for row in rows}
    is_group, enabled = boolean(payload, "isGroup"), boolean(payload, "enabled")
    sort_order = payload.get("sortOrder", 0)
    if isinstance(sort_order, bool) or not isinstance(sort_order, int) or not -10000 <= sort_order <= 10000:
        raise CrmApiException("VALIDATION_ERROR", "Sort order must be a whole number between -10000 and 10000.")
    parent = payload.get("parent") or None
    if parent and (not isinstance(parent, str) or parent not in existing):
        raise CrmApiException("VALIDATION_ERROR", "Choose an existing parent territory.")
    title = required_text(payload, "name")
    if not name:
        title = collapse_region(title)
    # A group label is not a customer region. Allow a differently spelled region
    # below it, preserving the spelling already stored on Customer records.
    comparable = [row.name for row in rows if is_group or not row.is_group]
    registered = list_regions(for_update=bool(is_group and not name))
    if is_group and not name and group_name_reserves_region(title, registered):
        raise CrmApiException("VALIDATION_ERROR", "This name belongs to a customer region. Place it as a region or choose a different group name.")
    if not name:
        title = matching_region(title, [*([] if is_group else registered), *comparable]) or title
    if not name and (not is_english_region(title) or len(title) > 100):
        raise CrmApiException("VALIDATION_ERROR", "Use an English territory name of at most 100 characters.")
    if name:
        doc = lock_document(TERRITORY, name, expected_modified, "NOT_FOUND")
        doc = frappe.get_doc(TERRITORY, name, for_update=True)
        if title != doc.name or is_group != doc.is_group:
            raise CrmApiException("VALIDATION_ERROR", "Territory name and type cannot be changed.")
    else:
        # Use MariaDB's identity comparison, including case-insensitive collation.
        if frappe.db.get_value(TERRITORY, title, "name", for_update=True):
            raise CrmApiException("VALIDATION_ERROR", "A territory with this name already exists.")
        doc = frappe.get_doc({"doctype": TERRITORY, "territory_name": title})
    doc.update({"parent_territory": parent, "is_group": is_group, "enabled": enabled, "sort_order": sort_order})
    try:
        validate_tree(rows, {"name": title, "parent_territory": parent, "is_group": is_group, "enabled": enabled})
    except ValueError as exc:
        raise CrmApiException("VALIDATION_ERROR", str(exc)) from exc
    savepoint = "territory_" + frappe.generate_hash(length=8)
    frappe.db.savepoint(savepoint)
    try:
        if not is_group and not name:
            canonical = register_region(title)
            if canonical != title:
                if frappe.db.get_value(TERRITORY, canonical, "name", for_update=True):
                    raise CrmApiException("VALIDATION_ERROR", "The canonical region name is already in use; reload the catalogue.")
                if len(canonical) > 100:
                    raise CrmApiException("VALIDATION_ERROR", "The registered region name exceeds 100 characters.")
                title = canonical
                doc.territory_name = canonical
                validate_tree(rows, {"name": title, "parent_territory": parent, "is_group": is_group, "enabled": enabled})
        doc.save(ignore_permissions=True)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return territory_dto(doc)


def active_sales(user):
    if not frappe.db.get_value("User", user, "enabled"):
        return False
    try:
        return resolve_crm_role(user) == "Sales"
    except frappe.PermissionError:
        return False


def lock_assignment_sales(user):
    """Read current eligibility before locking catalogue or assignment rows.

    Validation only requires eligibility when adding responsibility. Historical
    records remain maintainable when the person is no longer an active Sales.
    """
    from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE
    current = frappe.db.get_value("User", user, ["name", "enabled"], as_dict=True, for_update=True) if user else None
    if not current:
        return False
    roles = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='User' FOR UPDATE",
                          (current.name,), pluck=True)
    return bool(current.enabled) and {role for role in roles if role in CRM_ROLE_TO_PROFILE} == {"CRM Sales"}


def validate_assignment_document(doc):
    lock_catalogue()
    region = frappe.db.get_value(TERRITORY, doc.territory, ["is_group", "enabled"], as_dict=True, for_update=True)
    if not region or region.is_group:
        frappe.throw("Assign sales responsibility only to a leaf region.")
    before = doc.get_doc_before_save()
    if before and doc.territory != before.territory:
        frappe.throw("An assignment cannot move to a different region; cancel it and create a new assignment.")
    if before and doc.sales_owner != before.sales_owner:
        frappe.throw("End or cancel the old assignment and create a new one for a different Sales user.")
    if not doc.cancelled and not region.enabled and (not before or before.cancelled):
        frappe.throw("Reactivate the region before adding an assignment.")
    if not before or doc.sales_owner != before.sales_owner or (before.cancelled and not doc.cancelled):
        if not doc.flags.crm_assignment_sales_active:
            frappe.throw("Choose an active CRM Sales user.")
    rows = frappe.db.sql(
        "SELECT `name`, `valid_from`, `valid_until`, `cancelled` FROM `tabCRM Territory Assignment` "
        "WHERE `territory` = %s FOR UPDATE", (doc.territory,), as_dict=True,
    )
    try:
        start, end = date_range(doc.valid_from, doc.valid_until)
        if before and not doc.cancelled:
            old_start, old_end = date_range(before.valid_from, before.valid_until)
            if start < old_start or end > old_end:
                if not region.enabled:
                    frappe.throw("Reactivate the region before extending an assignment period.")
                if not doc.flags.crm_assignment_sales_active:
                    frappe.throw("Choose an active CRM Sales user before extending an assignment period.")
        if not doc.cancelled and overlaps(doc.valid_from, doc.valid_until, rows, exclude=doc.name):
            frappe.throw("This region already has a sales assignment during that period; end it before adding a successor.")
    except ValueError as exc:
        frappe.throw(str(exc))


def save_assignment(payload, name=None, expected_modified=None):
    require_manager()
    payload = as_payload(payload)
    owner = required_text(payload, "salesOwner")
    lock_assignment_sales(owner)
    lock_catalogue()
    if payload.get("id"):
        raise CrmApiException("VALIDATION_ERROR", "Assignment IDs are generated by the server.")
    start = optional_date(payload.get("validFrom"), "validFrom")
    end = optional_date(payload.get("validUntil"), "validUntil")
    if not start:
        raise CrmApiException("VALIDATION_ERROR", "An effective start date is required.")
    note = payload.get("note") or ""
    if not isinstance(note, str) or len(note) > 2000:
        raise CrmApiException("VALIDATION_ERROR", "Note must be at most 2000 characters.")
    doc = lock_document(ASSIGNMENT, name, expected_modified, "NOT_FOUND") if name else frappe.get_doc({"doctype": ASSIGNMENT})
    if name:
        doc = frappe.get_doc(ASSIGNMENT, name, for_update=True)
    # The leaf is saved under its stored spelling: MariaDB resolves a case variant to the row, and the page
    # matches assignments to catalogue leaves by exact name.
    territory = required_text(payload, "territory")
    territory = frappe.db.get_value(TERRITORY, territory, "name") or territory
    doc.update({"territory": territory, "sales_owner": owner,
                "valid_from": start, "valid_until": end, "cancelled": boolean(payload, "cancelled"), "note": note.strip()})
    try:
        doc.save(ignore_permissions=True)
    except frappe.ValidationError as exc:
        raise CrmApiException("VALIDATION_ERROR", str(exc)) from exc
    return assignment_dto(doc)
