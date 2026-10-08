"""Native User list restriction; File policy lives in services.managed_file_access.

Frappe core User permissions and the CRM personnel service are unchanged.
"""
from __future__ import annotations

import frappe

from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE

SYSTEM_MANAGER = "System Manager"
CRM_MANAGER = "CRM Manager"


def user_query(user: str | None = None) -> str:
    """Show a Sales user or an Engineer only their own row in the native User list.

    User is one of Frappe's core DocTypes: whoever may select from it gets every column of every row,
    and every desk user may select. That gave each CRM user the last login time and address of all
    the others. The people the CRM shows (owners, engineers) come from its own endpoints.

    Three kinds of user keep Frappe's list:
    - whoever administers the system (Administrator, System Manager);
    - a user whose sole CRM role is Manager, who assigns Engineers in the Desk form of CRM Account Engineer
      Assignment, the only place that is done, and has to find them in its link field;
    - a user without a CRM role, who is not the CRM's to narrow: an ERP user still finds colleagues
      in a link field.
    A user who holds a Sales or Engineer role next to an ERP role is narrowed like any other Sales
    user or Engineer: the CRM role is what brings the limit.
    """

    resolved_user = user or getattr(frappe.session, "user", None)
    if not resolved_user:
        return "1=0"
    if not restricted_user(resolved_user, frappe.get_roles(resolved_user)):
        return ""
    return f"`tabUser`.`name` = {_literal(resolved_user)}"


def restricted_user(user, roles) -> bool:
    roles = set(roles)
    crm_roles = roles.intersection(CRM_ROLE_TO_PROFILE)
    return bool(
        user != "Administrator" and crm_roles and SYSTEM_MANAGER not in roles
        and crm_roles != {CRM_MANAGER}
    )


def user_share_is_blocked(doc) -> bool:
    """Shares are ORed outside list predicates; serialize with recipient role saves."""
    if doc.share_doctype != "User":
        return False
    if frappe.utils.cint(doc.get("everyone")):
        return True
    # Updating a DocShare already holds its row; never wait behind a role save
    # that holds User and is about to revoke that same grant.
    try:
        users = frappe.db.sql_list(
            "SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE NOWAIT", (doc.get("user"),),
        )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw("The user's sharing boundary is being changed. Please retry.", frappe.PermissionError)
    if not users:
        return False  # Core link validation refuses a missing recipient.
    recipient = users[0]
    # Frappe gives every User a self-share for editing their own profile.
    if frappe.db.exists("User", doc.share_name) == recipient:
        return False
    try:
        roles = frappe.db.sql_list(
            "SELECT role FROM `tabHas Role` WHERE parenttype='User' AND parent=%s FOR UPDATE NOWAIT",
            (recipient,),
        )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw("The user's roles are being changed. Please retry.", frappe.PermissionError)
    return restricted_user(recipient, roles)


def reconcile_user_shares(doc=None) -> None:
    """Remove foreign-row grants on install/migrate and before a role transition."""
    if doc is not None:
        if restricted_user(doc.name, (row.role for row in doc.get("roles") or ())):
            frappe.db.sql(
                "DELETE FROM `tabDocShare` WHERE share_doctype='User' "
                "AND user=%s AND share_name!=user", (doc.name,),
            )
        return
    frappe.db.sql(
        "DELETE s FROM `tabDocShare` s WHERE s.share_doctype='User' AND "
        "(s.everyone=1 OR (s.user!='Administrator' AND s.share_name!=s.user "
        "AND EXISTS (SELECT 1 FROM `tabHas Role` r WHERE r.parenttype='User' "
        "AND r.parent=s.user AND r.role IN ('CRM Sales','CRM Engineer')) "
        "AND NOT EXISTS (SELECT 1 FROM `tabHas Role` e WHERE e.parenttype='User' "
        "AND e.parent=s.user AND e.role='System Manager')))"
    )


def _literal(value: str) -> str:
    """`value` as an SQL string literal for a list condition.

    frappe.db.escape doubles every % by default, for a query that is formatted with arguments
    afterwards. A list query is not: the doubled % would stay in it, and a user whose address
    contains % would be compared with a different address. Where Frappe does format a query that
    carries these conditions (reportview.get_match_cond), it doubles the % of the whole condition
    itself.
    """

    return frappe.db.escape(value, percent=False)
