"""Contact services backed by standard Contact and Dynamic Link."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, capabilities_for_user, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype, has_crm_permission
from rayher_crm.services.accounts import _require_account
from rayher_crm.services.common import (
    ensure_server_generated_id,
    normalize_pagination,
    read_all_pages,
    required_text,
    resolve_write_owner,
    to_iso_timestamp,
    validate_choice,
)
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.notifications import create_notification, record_route


CONTACT_RELATIONSHIPS = {"Strong", "Developing", "Weak"}
CONTACT_STATUSES = {"Active", "Left Company", "Archived"}
CONTACT_BUYING_ROLES = {
    "Decision Maker", "Economic Buyer", "Champion", "Technical Champion",
    "Technical Evaluator", "Procurement", "Influencer", "Blocker", "User",
}
CONTACT_INFLUENCE = {"High", "Medium", "Low"}


def _contact_account(name: str) -> str | None:
    return frappe.db.get_value(
        "Dynamic Link",
        {"parent": name, "parenttype": "Contact", "parentfield": "links", "link_doctype": "Customer"},
        "link_name",
    )


def _require_contact(name: str):
    if not frappe.db.exists("Contact", name):
        raise CrmApiException("CONTACT_NOT_FOUND", "Contact was not found.")
    doc = frappe.get_doc("Contact", name)
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The contact is outside the current user scope.")
    return doc


def serialize_contact(doc) -> dict[str, Any]:
    from rayher_crm.services.sites import can_read_site_data

    account_id = _contact_account(doc.name)
    account = frappe.db.get_value(
        "Customer",
        account_id,
        ["customer_name", "custom_crm_short_name", "custom_crm_owner"],
        as_dict=True,
    ) if account_id else None
    can_read_site = can_read_site_data(account_id) if account_id else False
    site_name = (
        frappe.db.get_value("Address", doc.custom_crm_site, "address_title")
        if doc.custom_crm_site and can_read_site
        else None
    )
    display_name = " ".join(part for part in (doc.first_name, doc.last_name) if part).strip() or doc.name
    modified = to_iso_timestamp(doc.modified)
    result = {
        "id": doc.name,
        "accountId": account_id,
        "name": display_name,
        "title": doc.designation or "",
        "department": doc.department or "",
        "phone": doc.phone or "",
        "email": doc.email_id or "",
        "relationship": doc.custom_crm_relationship,
        "owner": doc.custom_crm_owner,
        "status": doc.custom_crm_status,
        "dataQuality": doc.custom_crm_data_quality,
        "updatedAt": modified,
        "modified": modified,
        "accountName": account.customer_name if account else "",
        "accountShortName": (account.custom_crm_short_name or account.customer_name) if account else "",
        "opportunityRoles": [],
    }
    if doc.custom_crm_site and can_read_site:
        result["siteId"] = doc.custom_crm_site
    if site_name:
        result["siteName"] = site_name
    if doc.custom_crm_reports_to:
        result["reportsToContactId"] = doc.custom_crm_reports_to
    if doc.custom_crm_merged_into:
        result["mergedIntoContactId"] = doc.custom_crm_merged_into
    if doc.custom_crm_buying_role:
        result["role"] = doc.custom_crm_buying_role
    if doc.custom_crm_influence:
        result["influence"] = doc.custom_crm_influence
    if doc.custom_crm_reports_to:
        result["reportsTo"] = doc.custom_crm_reports_to
    return result


def _validate_reporting_line(contact_id: str | None, account_id: str, parent_id: str | None) -> None:
    if not parent_id:
        return
    parent = _require_contact(parent_id)
    if _contact_account(parent.name) != account_id:
        raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "The reporting contact belongs to another account.")
    if parent.custom_crm_status != "Active":
        raise CrmApiException("CONTACT_INACTIVE", "The reporting contact must be active.")
    seen = set()
    current = parent
    while current and current.name not in seen:
        if contact_id and current.name == contact_id:
            raise CrmApiException("INVALID_REPORTING_LINE", "The reporting line would create a cycle.")
        seen.add(current.name)
        next_name = current.custom_crm_reports_to
        current = frappe.get_doc("Contact", next_name) if next_name else None


def _validated_contact(payload: dict[str, Any], contact_id: str | None = None) -> dict[str, Any]:
    account_id = required_text(payload, "accountId")
    account = _require_account(account_id)
    if resolve_crm_role() == "Sales" and account.custom_crm_owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the Account owner or a Manager may edit contacts.")
    site_id = payload.get("siteId") or None
    if site_id:
        from rayher_crm.services.sites import _require_site

        _require_site(site_id, account_id)
    parent_id = payload.get("reportsToContactId") or None
    _validate_reporting_line(contact_id, account_id, parent_id)
    role = str(payload.get("role") or "").strip()
    influence = str(payload.get("influence") or "").strip()
    if role:
        role = validate_choice(role, "role", CONTACT_BUYING_ROLES)
    if influence:
        influence = validate_choice(influence, "influence", CONTACT_INFLUENCE)
    return {
        "account_id": account_id,
        "name": required_text(payload, "name"),
        "title": required_text(payload, "title"),
        "department": required_text(payload, "department"),
        "phone": str(payload.get("phone") or "").strip(),
        "email": str(payload.get("email") or "").strip(),
        "relationship": validate_choice(payload.get("relationship"), "relationship", CONTACT_RELATIONSHIPS),
        "status": validate_choice(payload.get("status"), "status", CONTACT_STATUSES),
        "owner": resolve_write_owner(payload.get("owner"), shared_sales=False),
        "site": site_id,
        "reports_to": parent_id,
        "buying_role": role,
        "influence": influence,
    }


def _apply_contact(doc, values: dict[str, Any]) -> None:
    doc.first_name = values["name"]
    doc.last_name = None
    doc.designation = values["title"]
    doc.department = values["department"]
    doc.set("phone_nos", [])
    if values["phone"]:
        doc.append("phone_nos", {"phone": values["phone"], "is_primary_phone": 1})
    doc.set("email_ids", [])
    if values["email"]:
        doc.append("email_ids", {"email_id": values["email"], "is_primary": 1})
    doc.custom_crm_owner = values["owner"]
    doc.custom_crm_site = values["site"]
    doc.custom_crm_reports_to = values["reports_to"]
    doc.custom_crm_relationship = values["relationship"]
    doc.custom_crm_status = values["status"]
    doc.custom_crm_data_quality = "Complete" if values["phone"] and values["email"] else "Needs Review"
    doc.custom_crm_buying_role = values["buying_role"]
    doc.custom_crm_influence = values["influence"]
    doc.set("links", [])
    doc.append("links", {"link_doctype": "Customer", "link_name": values["account_id"]})


def list_contacts(query: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    assert_capability("contact:view")
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    where = [f"({conditions_for_doctype('Contact')})"]
    values: list[Any] = []
    contact_id = str(query.get("contactId") or "").strip()
    if contact_id:
        where.append("`tabContact`.`name` = %s")
        values.append(contact_id)
    account_id = query.get("accountId")
    if account_id and account_id != "All":
        where.append("`crm_link`.`link_name` = %s")
        values.append(account_id)
    site_id = str(query.get("siteId") or "").strip()
    if site_id and site_id != "All":
        from rayher_crm.services.sites import _site_account, can_read_site_data

        site_account = _site_account(site_id)
        if not site_account or not can_read_site_data(site_account):
            raise CrmApiException("SCOPE_DENIED", "The Site filter is outside the current user scope.")
        where.append("`tabContact`.`custom_crm_site` = %s")
        values.append(site_id)
    owner = str(query.get("owner") or "").strip()
    if owner and owner != "All":
        where.append("`tabContact`.`custom_crm_owner` = %s")
        values.append(owner)
    status = query.get("contactStatus")
    if status and status != "All":
        where.append("`tabContact`.`custom_crm_status` = %s")
        values.append(status)
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        where.append("(`tabContact`.`first_name` LIKE %s OR `tabContact`.`last_name` LIKE %s OR `tabContact`.`email_id` LIKE %s)")
        values.extend([pattern, pattern, pattern])
    base = (
        " FROM `tabContact` INNER JOIN `tabDynamic Link` AS `crm_link` ON `crm_link`.`parent` = `tabContact`.`name` "
        "AND `crm_link`.`parenttype` = 'Contact' AND `crm_link`.`parentfield` = 'links' AND `crm_link`.`link_doctype` = 'Customer' "
    )
    where_sql = " AND ".join(where)
    total = int(frappe.db.sql(f"SELECT COUNT(DISTINCT `tabContact`.`name`){base} WHERE {where_sql}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT DISTINCT `tabContact`.`name`{base} WHERE {where_sql} ORDER BY `tabContact`.`modified` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]),
        as_dict=True,
    )
    return [serialize_contact(frappe.get_doc("Contact", row.name)) for row in rows], total, page, page_size


def contacts_for_account(account_id: str) -> list[dict[str, Any]]:
    return read_all_pages(list_contacts, {"accountId": account_id, "contactStatus": "Active"})


def create_contact(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("contact:write")
    ensure_server_generated_id(payload)
    values = _validated_contact(payload)
    savepoint = f"crm_contact_create_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc = frappe.new_doc("Contact")
        _apply_contact(doc, values)
        doc.insert(ignore_permissions=True)
        if doc.custom_crm_owner != frappe.session.user:
            create_notification(
                recipient=doc.custom_crm_owner, category="Contact",
                title="Contact assigned", message=f"You are now responsible for {doc.first_name}.",
                route=record_route("/contacts", doc.name), source_doctype="Contact", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_contact(doc)


def update_contact(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("contact:write")
    _require_contact(name)
    values = _validated_contact(payload, name)
    doc = lock_document("Contact", name, expected_modified, "NOT_FOUND")
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The contact is outside the current user scope.")
    previous_owner = doc.custom_crm_owner
    savepoint = f"crm_contact_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        _apply_contact(doc, values)
        doc.save(ignore_permissions=True)
        if previous_owner != doc.custom_crm_owner and doc.custom_crm_owner != frappe.session.user:
            create_notification(
                recipient=doc.custom_crm_owner, category="Contact",
                title="Contact reassigned", message=f"You are now responsible for {doc.first_name}.",
                route=record_route("/contacts", doc.name), source_doctype="Contact", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_contact(doc)


def get_contact(name: str) -> dict[str, Any]:
    assert_capability("contact:view")
    doc = _require_contact(name)
    reports_to = serialize_contact(_require_contact(doc.custom_crm_reports_to)) if doc.custom_crm_reports_to else None
    direct_report_names = frappe.db.sql(
        "SELECT `name` FROM `tabContact` "
        "WHERE `custom_crm_reports_to` = %s "
        f"AND ({conditions_for_doctype('Contact')})",
        (name,),
        as_dict=True,
    )
    direct_reports = [
        serialize_contact(frappe.get_doc("Contact", item.name))
        for item in direct_report_names
    ]
    capabilities = capabilities_for_user()
    opportunities: list[dict[str, Any]] = []
    visits: list[dict[str, Any]] = []
    demo_requests: list[dict[str, Any]] = []
    bookings: list[dict[str, Any]] = []
    if "deal:view" in capabilities:
        from rayher_crm.services.bookings import list_bookings
        from rayher_crm.services.opportunities import list_strategy_opportunities

        opportunities = read_all_pages(list_strategy_opportunities, {"contactId": name})
        bookings = read_all_pages(list_bookings, {"contactId": name})
    if "visit:view" in capabilities:
        from rayher_crm.services.visits import list_visits

        visits = read_all_pages(list_visits, {"contactId": name})
    if "demo_request:view" in capabilities:
        from rayher_crm.services.demo_requests import list_demo_requests

        demo_requests = read_all_pages(list_demo_requests, {"contactId": name})

    opportunity_rows = [{
        "id": item["id"], "title": item["title"], "stage": item["stage"],
        "role": next((person["role"] for person in item.get("stakeholders", []) if person.get("contactId") == name), ""),
        "href": f"/opportunities/{item['id']}",
    } for item in opportunities]
    visit_rows = [{
        "id": item["id"], "subject": item["subject"], "date": item["date"],
        "href": f"/visits/{item['id']}",
    } for item in visits]
    demo_rows = [{
        "id": item["id"], "title": item["title"], "status": item["status"],
        "href": f"/demo-workflow/{item['id']}",
    } for item in demo_requests]
    booking_rows = [{
        "id": item["id"], "title": item["title"], "status": item["status"],
        "href": f"/booking/{item['id']}",
    } for item in bookings]
    timeline = [
        *[{
            "id": f"opportunity:{item['id']}", "at": item.get("modified") or item.get("updated") or "",
            "type": "Opportunity", "title": item["title"], "summary": item["stage"],
            "href": f"/opportunities/{item['id']}",
        } for item in opportunities],
        *[{
            "id": f"visit:{item['id']}", "at": item.get("date") or item.get("modified") or "",
            "type": "Visit", "title": item["subject"], "summary": item["status"],
            "href": f"/visits/{item['id']}",
        } for item in visits],
        *[{
            "id": f"demo-request:{item['id']}", "at": item.get("modified") or item.get("updatedAt") or item.get("createdAt") or "",
            "type": "Demo Request", "title": item["title"], "summary": item["status"],
            "href": f"/demo-workflow/{item['id']}",
        } for item in demo_requests],
        *[{
            "id": f"booking:{item['id']}", "at": item.get("modified") or item.get("bookingDate") or "",
            "type": "Booking", "title": item["title"], "summary": item["status"],
            "href": f"/booking/{item['id']}",
        } for item in bookings],
    ]
    timeline.sort(key=lambda item: (item["at"], item["id"]), reverse=True)
    result = {
        "contact": serialize_contact(doc),
        "directReports": direct_reports,
        "opportunities": opportunity_rows,
        "visits": visit_rows,
        "demoRequests": demo_rows,
        "bookings": booking_rows,
        "timeline": timeline,
    }
    if reports_to:
        result["reportsTo"] = reports_to
    return result


def _lock_contact_pair(first: str, second: str) -> None:
    names = sorted({first, second})
    rows = frappe.db.sql(
        "SELECT `name` FROM `tabContact` WHERE `name` IN (%s, %s) ORDER BY `name` FOR UPDATE",
        tuple(names),
    )
    if len(rows) != 2:
        raise CrmApiException("CONTACT_NOT_FOUND", "A contact to merge was not found.")


def merge_contacts(
    survivor_id: str,
    duplicate_id: str,
    *,
    failure_injector: Callable[[], None] | None = None,
) -> dict[str, Any]:
    assert_capability("contact:merge")
    if survivor_id == duplicate_id:
        raise CrmApiException("VALIDATION_ERROR", "A contact cannot be merged into itself.")
    survivor = _require_contact(survivor_id)
    duplicate = _require_contact(duplicate_id)
    if _contact_account(survivor.name) != _contact_account(duplicate.name):
        raise CrmApiException("CONTACT_MERGE_CONFLICT", "Contacts from different accounts cannot be merged.")
    _lock_contact_pair(survivor_id, duplicate_id)
    savepoint = f"crm_merge_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        duplicate.custom_crm_status = "Archived"
        duplicate.custom_crm_merged_into = survivor.name
        duplicate.save(ignore_permissions=True)
        if failure_injector:
            failure_injector()
        direct_reports = frappe.get_all("Contact", filters={"custom_crm_reports_to": duplicate.name}, pluck="name")
        for contact_name in direct_reports:
            frappe.db.set_value("Contact", contact_name, "custom_crm_reports_to", survivor.name, update_modified=True)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    survivor.reload()
    return serialize_contact(survivor)


def delete_contact(
    name: str,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Soft-archive a Contact while retaining inbound links as historical references."""

    assert_capability("contact:delete")
    doc = _require_contact(name)
    frappe.db.sql("SELECT `name` FROM `tabContact` WHERE `name` = %s FOR UPDATE", (name,))
    savepoint = f"crm_contact_delete_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc.custom_crm_status = "Archived"
        doc.save(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_contact_archive")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return {"id": name, "status": "Deleted"}
