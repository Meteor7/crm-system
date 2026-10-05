"""Address-backed CRM Site helpers."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.accounts import _require_account
from rayher_crm.services.common import ensure_server_generated_id, required_text, resolve_write_owner, validate_choice


SITE_STATUSES = {"量产", "建设中", "规划中"}


def _site_account(name: str) -> str | None:
    return frappe.db.get_value(
        "Dynamic Link",
        {"parent": name, "parenttype": "Address", "parentfield": "links", "link_doctype": "Customer"},
        "link_name",
    )


def serialize_site(doc) -> dict[str, Any]:
    return {
        "id": doc.name,
        "name": doc.address_title,
        "city": doc.city or "",
        "type": doc.custom_crm_site_type or "",
        "process": doc.custom_crm_process or "",
        "status": doc.custom_crm_status,
    }


def can_read_site_data(account_id: str, user: str | None = None) -> bool:
    """Return whether the user may read Site/Address data for an Account.

    Public Account visibility only shares the Account and Contacts with another
    Sales user. Engineers retain their existing assigned-work access model.
    Callers that expose a child business record must use this narrower check
    before serializing Site identifiers, names, locations, or addresses.
    """

    resolved_user = user or getattr(frappe.session, "user", None)
    if not resolved_user or resolved_user == "Guest":
        return False
    try:
        role = resolve_crm_role(resolved_user)
    except frappe.PermissionError:
        return False
    if role in {"Manager", "Engineer"}:
        return True
    if role != "Sales":
        return False
    return frappe.db.get_value("Customer", account_id, "custom_crm_owner") == resolved_user


def _assert_site_read_scope(account_id: str) -> None:
    _require_account(account_id)
    if not can_read_site_data(account_id):
        raise CrmApiException("SCOPE_DENIED", "Only the Account owner or a Manager may view sites.")


SITE_NOT_FOUND_MESSAGE = "Site was not found, or you have no access to it."


def _account_in_reach(account_id: str) -> bool:
    try:
        _require_account(account_id)
    except CrmApiException:
        return False
    return True


def _require_site(name: str, account_id: str | None = None):
    # One answer for a Site that does not exist, for one of an Account the user may not see, and for one of an
    # Account whose Sites the user may not read (a Public Account of another Sales user): the id of a Site
    # carries its name (F1-12, as for Accounts and Contacts), so the Site is told apart from a missing one only
    # once the user may read it.
    linked_account = _site_account(name) if frappe.db.exists("Address", name) else None
    if not linked_account or not _account_in_reach(linked_account) or not can_read_site_data(linked_account):
        raise CrmApiException("SITE_NOT_FOUND", SITE_NOT_FOUND_MESSAGE)
    if account_id and linked_account != account_id:
        raise CrmApiException("SITE_ACCOUNT_MISMATCH", "The Site belongs to another Account.")
    return frappe.get_doc("Address", name)


def _assert_site_write_scope(account_id: str) -> None:
    account = _require_account(account_id)
    if resolve_crm_role() == "Sales" and account.custom_crm_owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the Account owner or a Manager may edit sites.")

def sites_for_account(account_id: str) -> list[dict[str, Any]]:
    _assert_site_read_scope(account_id)
    names = frappe.db.sql(
        """SELECT `address`.`name`
        FROM `tabAddress` AS `address`
        INNER JOIN `tabDynamic Link` AS `link` ON `link`.`parent` = `address`.`name`
        WHERE `link`.`parenttype` = 'Address' AND `link`.`parentfield` = 'links'
          AND `link`.`link_doctype` = 'Customer' AND `link`.`link_name` = %s
        ORDER BY `address`.`modified` DESC""",
        (account_id,),
        as_dict=True,
    )
    return [serialize_site(frappe.get_doc("Address", row.name)) for row in names]


def list_account_sites() -> list[dict[str, Any]]:
    """Every Site the caller may read, each with the ``accountId`` it belongs to, in one query.

    The Accounts are the ones in the caller's Customer row scope, and of those a Sales user reads the
    Sites of their own only (see ``can_read_site_data``). For a Manager and a Sales user that is what the
    Account 360 of each listed Account returns; an Engineer gets the Sites of the Accounts assigned to
    them. Pages that offer Sites across Accounts read this instead of one Account 360 per Account (#136).
    """

    assert_capability("account:view")
    scope = conditions_for_doctype("Customer")
    values: list[Any] = []
    if resolve_crm_role() == "Sales":
        scope = f"({scope}) AND `tabCustomer`.`custom_crm_owner` = %s"
        values.append(frappe.session.user)
    rows = frappe.db.sql(
        f"""SELECT `link`.`link_name` AS `account`, `address`.`name`, `address`.`address_title`,
            `address`.`city`, `address`.`custom_crm_site_type`, `address`.`custom_crm_process`,
            `address`.`custom_crm_status`
        FROM `tabAddress` AS `address`
        INNER JOIN `tabDynamic Link` AS `link` ON `link`.`parent` = `address`.`name`
        INNER JOIN `tabCustomer` ON `tabCustomer`.`name` = `link`.`link_name`
        WHERE `link`.`parenttype` = 'Address' AND `link`.`parentfield` = 'links'
          AND `link`.`link_doctype` = 'Customer' AND ({scope})
        ORDER BY `link`.`link_name`, `address`.`modified` DESC""",
        tuple(values),
        as_dict=True,
    )
    return [{"accountId": row.account, **serialize_site(row)} for row in rows]


def create_site(account_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("account:write")
    _assert_site_write_scope(account_id)
    _require_account(account_id)
    ensure_server_generated_id(payload)
    values = {
        "name": required_text(payload, "name"),
        "city": required_text(payload, "city"),
        "type": required_text(payload, "type"),
        "process": required_text(payload, "process"),
        "status": validate_choice(payload.get("status"), "status", SITE_STATUSES),
    }
    doc = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": values["name"],
            "address_type": "Other",
            "address_line1": values["name"],
            "city": values["city"],
            "country": "China",
            "custom_crm_owner": resolve_write_owner(None),
            "custom_crm_site_type": values["type"],
            "custom_crm_process": values["process"],
            "custom_crm_status": values["status"],
            "links": [{"link_doctype": "Customer", "link_name": account_id}],
        }
    ).insert(ignore_permissions=True)
    return serialize_site(doc)


def update_site(account_id: str, site_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("account:write")
    _assert_site_write_scope(account_id)
    doc = _require_site(site_id, account_id)
    ensure_server_generated_id(payload)
    values = {
        "name": required_text(payload, "name"),
        "city": required_text(payload, "city"),
        "type": required_text(payload, "type"),
        "process": required_text(payload, "process"),
        "status": validate_choice(payload.get("status"), "status", SITE_STATUSES),
    }
    doc.address_title = values["name"]
    doc.address_line1 = values["name"]
    doc.city = values["city"]
    doc.custom_crm_site_type = values["type"]
    doc.custom_crm_process = values["process"]
    doc.custom_crm_status = values["status"]
    doc.save(ignore_permissions=True)
    return serialize_site(doc)


def delete_site(account_id: str, site_id: str) -> dict[str, str]:
    assert_capability("account:write")
    _assert_site_write_scope(account_id)
    doc = _require_site(site_id, account_id)
    site_name = doc.name
    frappe.db.set_value(
        "Contact",
        {"custom_crm_site": site_name},
        "custom_crm_site",
        None,
        update_modified=False,
    )
    frappe.delete_doc("Address", site_name, ignore_permissions=True)
    return {"id": site_id, "status": "Deleted"}
