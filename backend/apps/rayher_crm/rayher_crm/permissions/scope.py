"""SQL-backed row scope shared by CRM list and detail permission checks."""

from __future__ import annotations

import frappe
from frappe.permissions import AUTOMATIC_ROLES, add_permission, get_valid_perms, update_permission_property

from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE, capabilities_for_role, resolve_crm_role


SCOPED_DOCTYPES = (
    "Customer", "Contact", "Lead", "CRM Opportunity", "CRM Opportunity Probability History",
    "CRM Probability Recovery", "CRM Probability Recovery Revision", "CRM Opportunity Loss Review",
    "CRM Opportunity Loss Review Revision", "CRM Opportunity Stage History", "CRM Opportunity Internal Validation",
    "CRM Opportunity Action", "CRM Opportunity History", "CRM Booking",
    "CRM Installed Tool", "CRM Demo Request", "CRM Evaluation",
    "CRM Evaluation Customer Review", "CRM Visit", "CRM Visit Meeting Record",
    "CRM Contact File", "CRM Status Attachment", "CRM Demo Artifact",
    "CRM Notification Event", "CRM Opportunity Stakeholder", "CRM Installed Tool Lifecycle History",
    "CRM Installed Tool Service History", "CRM Installed Tool Version History", "CRM Demo Comment",
    "CRM Demo Request History", "CRM Evaluation History", "CRM Test Run",
    "CRM Document Access Request",
    "CRM Quotation", "CRM Quotation Version", "CRM Quotation Approval",
    "CRM RFQ", "CRM RFQ Version",
)
# Address keeps ERPNext's own role permissions and adds CRM read-only roles. Its hooks
# add CRM-only row and write checks without changing the global All role. Engineer assignments remain Manager-
# managed configuration, but their native reads are scoped to the assigned Engineer.
CONDITION_DOCTYPES = SCOPED_DOCTYPES + ("Address", "CRM Account Engineer Assignment")
# Every CRM DocType belongs to the whitelisted services in api/v1: they check the business
# rules, drive the state machines and append the history rows the cockpit reads. The standard
# Frappe document API (/api/resource, frappe.client, the Desk form) writes straight to the
# table and skips all of that, so no CRM role gets write, create or delete on any of them.
MUTATING_PERMISSIONS = frozenset({"write", "create", "delete"})
# Frappe ships these with an "All" row that lets every signed-in user change them.
SHARED_STANDARD_DOCTYPES = ("Customer", "Contact", "Lead")
UNIVERSAL_ROLE = "All"
ROLE_DOCPERMS = {
    "CRM Manager": {"read", "report", "export", "print", "email", "share"},
    "CRM Sales": {"read", "report", "export", "print", "email"},
    "CRM Engineer": {"read", "report", "export", "print"},
}
# Engineers work Installed Tools and Demo Requests, and never see Visits.
INSTALLED_TOOL_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": {"read", "report", "export", "print"},
    "CRM Engineer": {"read", "report", "export", "print"},
}
DEMO_REQUEST_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": ROLE_DOCPERMS["CRM Sales"],
    "CRM Engineer": {"read", "report", "export", "print"},
}
EVALUATION_DOCPERMS = {
    "CRM Manager": {"read", "report", "export", "print"},
    "CRM Sales": {"read", "report", "export", "print"},
    "CRM Engineer": {"read", "report", "export", "print"},
}
# History, artifacts, customer review rows and contact files are record keeping: the
# services append them and nobody edits them afterwards. Opportunity actions change only
# through the Opportunity service, so they get the same read-only set.
AUDIT_DOCPERMS = {
    "CRM Manager": {"read", "report", "export"},
    "CRM Sales": {"read", "report", "export"},
    "CRM Engineer": {"read", "report", "export"},
}
# Opportunity serialization deliberately omits stakeholder/contact data for
# Engineers, even when they can work the Opportunity through an Account assignment.
STAKEHOLDER_DOCPERMS = {
    "CRM Manager": AUDIT_DOCPERMS["CRM Manager"],
    "CRM Sales": AUDIT_DOCPERMS["CRM Sales"],
    "CRM Engineer": set(),
}

# Removed together with their Opportunity by delete_strategy_opportunity.
OPPORTUNITY_CHILD_DOCTYPES = (
    "CRM Probability Recovery Revision", "CRM Probability Recovery",
    "CRM Opportunity Loss Review Revision", "CRM Opportunity Loss Review",
    "CRM Opportunity Probability History",
    "CRM Opportunity Stage History",
    "CRM Opportunity Internal Validation",
)
# Read scope is independent of the generic deletion tuple; business services own deletion.
OPPORTUNITY_SCOPED_CHILD_DOCTYPES = OPPORTUNITY_CHILD_DOCTYPES + (
    "CRM Opportunity Action",
    "CRM Opportunity History",
    "CRM Opportunity Stakeholder",
)
DEMO_REQUEST_SCOPED_CHILD_DOCTYPES = (
    "CRM Demo Comment",
    "CRM Demo Request History",
)
EVALUATION_SCOPED_CHILD_DOCTYPES = (
    "CRM Evaluation Customer Review",
    "CRM Evaluation History",
    "CRM Test Run",
)
INSTALLED_TOOL_SCOPED_CHILD_DOCTYPES = (
    "CRM Installed Tool Lifecycle History",
    "CRM Installed Tool Service History",
    "CRM Installed Tool Version History",
)
# These records carry parent-scoped notes, test results, service details or
# requester data. Frappe treats DocShare as an override for document reads, so
# sharing them would make a stale child ID survive loss of parent access.
NATIVE_SHARE_BLOCKED_DOCTYPES = (
    *OPPORTUNITY_SCOPED_CHILD_DOCTYPES,
    *INSTALLED_TOOL_SCOPED_CHILD_DOCTYPES,
    *DEMO_REQUEST_SCOPED_CHILD_DOCTYPES,
    *EVALUATION_SCOPED_CHILD_DOCTYPES,
    "CRM Visit Meeting Record",
    "CRM Demo Artifact",
    "CRM Status Attachment",
    "CRM Quotation Version",
    "CRM Quotation Approval",
    "CRM RFQ Version",
    "CRM Document Access Request",
    "CRM Account Engineer Assignment",
)
ADDRESS_NATIVE_PERMISSION_TYPES = (
    "select", "read", "write", "create", "delete", "print", "email", "share",
)
# Visits are changed only through the visit service, which writes with
# ignore_permissions. A Sales user also reads a colleague's visit as its action
# owner, so a write DocPerm would let them change it through the standard document
# API -- take it over, mark it reviewed or attach unscanned files -- skipping the
# service's owner and workflow checks.
VISIT_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": ROLE_DOCPERMS["CRM Sales"],
    "CRM Engineer": set(),
}
# A visit's meeting record is written only by the visit record service (its
# controller refuses every other write) and carries the minutes, so it is read
# exactly where its visit is: Sales within their visit scope, Engineers never.
MEETING_RECORD_DOCPERMS = {
    "CRM Manager": {"read", "report", "export"},
    "CRM Sales": {"read", "report", "export"},
    "CRM Engineer": set(),
}
# No DocPerm at all, on purpose. `File.has_permission` delegates to the document
# a file is attached to, so any read permission here would also make the bytes
# reachable through Frappe's native file route -- which does not write a
# `CRM File Access Audit` row. Status attachments are served only by
# `opportunity_status.download_file`, which audits every hit; the service reads
# the rows with raw SQL and writes them with ignore_permissions.
#
# Administrator is the one exception: `File.has_permission` returns True for it
# before it looks at ownership or the attached document, so a site administrator
# can still fetch the bytes through the native route without an audit row. That
# is Frappe's superuser, not a role this scope can constrain.
STATUS_ATTACHMENT_DOCPERMS = {
    "CRM Manager": set(),
    "CRM Sales": set(),
    "CRM Engineer": set(),
}
NOTIFICATION_DOCPERMS = {
    "CRM Manager": {"read"},
    "CRM Sales": {"read"},
    "CRM Engineer": {"read"},
}
ACCOUNT_ENGINEER_ASSIGNMENT_DOCPERMS = {
    "CRM Manager": {"read", "write", "create", "delete", "report", "export", "print", "email"},
    "CRM Sales": set(),
    "CRM Engineer": {"read"},
}
QUOTATION_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": ROLE_DOCPERMS["CRM Sales"],
}
QUOTATION_APPROVAL_DOCPERMS = {
    "CRM Manager": {"read"},
    "CRM Sales": {"read"},
    "CRM Engineer": set(),
}
DOCPERMS_BY_DOCTYPE = {
    "Address": {role: {"read"} for role in CRM_ROLE_TO_PROFILE},
    # This Manager-maintained configuration is intentionally outside SCOPED_DOCTYPES,
    # whose members are service-owned and read-only through the standard API.
    "CRM Account Engineer Assignment": ACCOUNT_ENGINEER_ASSIGNMENT_DOCPERMS,
    "CRM Installed Tool": INSTALLED_TOOL_DOCPERMS,
    "CRM Demo Request": DEMO_REQUEST_DOCPERMS,
    "CRM Evaluation": EVALUATION_DOCPERMS,
    "CRM Evaluation Customer Review": AUDIT_DOCPERMS,
    "CRM Opportunity Probability History": AUDIT_DOCPERMS,
    "CRM Probability Recovery": AUDIT_DOCPERMS,
    "CRM Probability Recovery Revision": AUDIT_DOCPERMS,
    "CRM Opportunity Loss Review": AUDIT_DOCPERMS,
    "CRM Opportunity Loss Review Revision": AUDIT_DOCPERMS,
    "CRM Opportunity Stage History": AUDIT_DOCPERMS,
    "CRM Opportunity Internal Validation": AUDIT_DOCPERMS,
    "CRM Opportunity Action": AUDIT_DOCPERMS,
    "CRM Opportunity History": AUDIT_DOCPERMS,
    "CRM Opportunity Stakeholder": STAKEHOLDER_DOCPERMS,
    "CRM Installed Tool Lifecycle History": AUDIT_DOCPERMS,
    "CRM Installed Tool Service History": AUDIT_DOCPERMS,
    "CRM Installed Tool Version History": AUDIT_DOCPERMS,
    "CRM Demo Comment": AUDIT_DOCPERMS,
    "CRM Demo Request History": AUDIT_DOCPERMS,
    "CRM Evaluation History": AUDIT_DOCPERMS,
    "CRM Test Run": AUDIT_DOCPERMS,
    "CRM Visit": VISIT_DOCPERMS,
    "CRM Contact File": AUDIT_DOCPERMS,
    "CRM Demo Artifact": AUDIT_DOCPERMS,
    "CRM Status Attachment": STATUS_ATTACHMENT_DOCPERMS,
    "CRM Visit Meeting Record": MEETING_RECORD_DOCPERMS,
    "CRM Notification Event": NOTIFICATION_DOCPERMS,
    "CRM Document Access Request": AUDIT_DOCPERMS,
    "CRM Quotation": QUOTATION_DOCPERMS,
    "CRM Quotation Version": QUOTATION_DOCPERMS,
    "CRM Quotation Approval": QUOTATION_APPROVAL_DOCPERMS,
    "CRM RFQ": AUDIT_DOCPERMS,
    "CRM RFQ Version": AUDIT_DOCPERMS,
}
CRM_SHARE_GUARDED_DOCTYPES = tuple(
    doctype for doctype in SCOPED_DOCTYPES if doctype.startswith("CRM ")
) + ("CRM Account Engineer Assignment",)
PERMISSION_FIELDS = ("read", "write", "create", "delete", "report", "export", "print", "email", "share")
ROLE_TO_SERVER_ROLE = {"Manager": "CRM Manager", "Sales": "CRM Sales", "Engineer": "CRM Engineer"}
DOCTYPES_TO_VIEW_CAPABILITY = {
    "Customer": "account:view", "Address": "account:view", "Contact": "contact:view", "Lead": "requirement:view",
    "CRM Account Engineer Assignment": "account:view",
    "CRM Opportunity": "deal:view", "CRM Opportunity Probability History": "deal:view",
    "CRM Probability Recovery": "deal:view", "CRM Probability Recovery Revision": "deal:view",
    "CRM Opportunity Loss Review": "deal:view", "CRM Opportunity Loss Review Revision": "deal:view",
    "CRM Opportunity Stage History": "deal:view", "CRM Opportunity Internal Validation": "deal:view",
    "CRM Opportunity Action": "deal:view",
    "CRM Opportunity History": "deal:view",
    "CRM Booking": "deal:view",
    "CRM Installed Tool": "service:view",
    "CRM Demo Request": "demo_request:view",
    "CRM Evaluation": "evaluation:view",
    "CRM Evaluation Customer Review": "evaluation:view",
    "CRM Visit": "visit:view",
    "CRM Contact File": "stakeholder:view",
    "CRM Status Attachment": "deal:view",
    "CRM Demo Artifact": "demo_request:view",
    "CRM Visit Meeting Record": "visit:view",
    "CRM Notification Event": "dashboard:view",
    "CRM Quotation": "quotation:view",
    "CRM Opportunity Stakeholder": "deal:view",
    "CRM Installed Tool Lifecycle History": "service:view",
    "CRM Installed Tool Service History": "service:view",
    "CRM Installed Tool Version History": "service:view",
    "CRM Demo Comment": "demo_request:view",
    "CRM Demo Request History": "demo_request:view",
    "CRM Evaluation History": "evaluation:view",
    "CRM Test Run": "evaluation:view",
    "CRM Document Access Request": "account:view",
    "CRM Quotation Version": "quotation:view", "CRM Quotation Approval": "quotation:view",
    "CRM RFQ": "rfq:view", "CRM RFQ Version": "rfq:view",
}


def _permissions_for_doctype(doctype: str, role: str) -> set[str]:
    permissions = DOCPERMS_BY_DOCTYPE.get(doctype, ROLE_DOCPERMS)
    return set(permissions.get(ROLE_TO_SERVER_ROLE[role], set()))


def install_crm_doc_permissions() -> None:
    """Install explicit DocPerm rows so standard ERPNext roles do not mask CRM scope."""

    # Address needs a non-owner read grant before DBQuery reaches its CRM row hook.
    # Reconcile only the CRM rows; existing ERP and All permissions stay intact.
    for doctype in (*SCOPED_DOCTYPES, "Address"):
        permissions = DOCPERMS_BY_DOCTYPE.get(doctype, ROLE_DOCPERMS)
        for role, allowed in permissions.items():
            if allowed & MUTATING_PERMISSIONS:
                raise ValueError(
                    f"{doctype} would let {role} change rows through the standard document API; "
                    "writes belong to the api/v1 services.",
                )
            if not frappe.db.exists(
                "Custom DocPerm",
                {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            ):
                add_permission(doctype, role, 0, "read")
            for permission_type in PERMISSION_FIELDS:
                update_permission_property(
                    doctype,
                    role,
                    0,
                    permission_type,
                    1 if permission_type in allowed else 0,
                    validate=False,
                )
        frappe.clear_cache(doctype=doctype)

    # A read share overrides a failed controller detail check, and DBQuery may OR a
    # share with owner/User Permission scope. Remove every legacy share for the new
    # sensitive records so loss of parent access also revokes old child IDs.
    blocked_placeholders = ", ".join(["%s"] * len(NATIVE_SHARE_BLOCKED_DOCTYPES))
    frappe.db.sql(
        f"DELETE FROM `tabDocShare` WHERE `share_doctype` IN ({blocked_placeholders})",
        NATIVE_SHARE_BLOCKED_DOCTYPES,
    )
    # Address is a shared ERPNext DocType. Delete shares only for sites linked to
    # CRM Customers; ordinary ERP Address shares keep their existing semantics.
    frappe.db.sql(
        "DELETE FROM `tabDocShare` WHERE `share_doctype` = 'Address' "
        "AND `share_name` IN ("
        "SELECT `crm_address_link`.`parent` FROM `tabDynamic Link` AS `crm_address_link` "
        "INNER JOIN `tabCustomer` AS `crm_address_customer` "
        "ON `crm_address_customer`.`name` = `crm_address_link`.`link_name` "
        "WHERE `crm_address_link`.`parenttype` = 'Address' "
        "AND `crm_address_link`.`parentfield` = 'links' "
        "AND `crm_address_link`.`link_doctype` = 'Customer' "
        "AND `crm_address_customer`.`customer_group` = 'CRM Customers')",
    )

    # The same holds for an Address whose Customer link points at a Customer that is gone.
    frappe.db.sql(
        "DELETE FROM `tabDocShare` WHERE `share_doctype` = 'Address' "
        "AND `share_name` IN ("
        "SELECT `crm_orphan_link`.`parent` FROM `tabDynamic Link` AS `crm_orphan_link` "
        "LEFT JOIN `tabCustomer` AS `crm_orphan_customer` "
        "ON `crm_orphan_customer`.`name` = `crm_orphan_link`.`link_name` "
        "WHERE `crm_orphan_link`.`parenttype` = 'Address' "
        "AND `crm_orphan_link`.`parentfield` = 'links' "
        "AND `crm_orphan_link`.`link_doctype` = 'Customer' "
        "AND `crm_orphan_customer`.`name` IS NULL)",
    )

    # Historical write/submit shares on the wider custom CRM surface could bypass
    # service workflows and Manager-only configuration rules. Production had no CRM
    # shares when this guard was added; keep this cleanup away from Customer/Contact/Lead.
    placeholders = ", ".join(["%s"] * len(CRM_SHARE_GUARDED_DOCTYPES))
    frappe.db.sql(
        f"UPDATE `tabDocShare` SET `write` = 0, `submit` = 0 "
        f"WHERE `share_doctype` IN ({placeholders}) AND (`write` = 1 OR `submit` = 1)",
        CRM_SHARE_GUARDED_DOCTYPES,
    )

    # Every CRM user also holds the "All" role, so leaving its write access in place would put
    # the standard document API back in business for Customers, Contacts and Leads. Frappe ships
    # that access as an owner-only row, which still covers every record the user created.
    for doctype in SHARED_STANDARD_DOCTYPES:
        for if_owner in (0, 1):
            if not frappe.db.exists(
                "Custom DocPerm",
                {"parent": doctype, "role": UNIVERSAL_ROLE, "permlevel": 0, "if_owner": if_owner},
            ):
                continue
            for permission_type in sorted(MUTATING_PERMISSIONS):
                update_permission_property(
                    doctype, UNIVERSAL_ROLE, 0, permission_type, 0, validate=False, if_owner=if_owner,
                )
        frappe.clear_cache(doctype=doctype)


def _crm_address_exists_condition(address_expression: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM `tabDynamic Link` AS `crm_boundary_link` "
        "INNER JOIN `tabCustomer` AS `crm_boundary_customer` "
        "ON `crm_boundary_customer`.`name` = `crm_boundary_link`.`link_name` "
        f"WHERE `crm_boundary_link`.`parent` = {address_expression} "
        "AND `crm_boundary_link`.`parenttype` = 'Address' "
        "AND `crm_boundary_link`.`parentfield` = 'links' "
        "AND `crm_boundary_link`.`link_doctype` = 'Customer' "
        "AND `crm_boundary_customer`.`customer_group` = 'CRM Customers')"
    )


def _orphan_customer_link_exists_condition(address_expression: str) -> str:
    """A Customer link whose Customer no longer exists.

    Frappe removes a Customer's links when it deletes the record; a failed migration or
    direct SQL is what leaves one behind. Such an Address cannot be shown to be ordinary
    ERP data, so it is handled as protected instead of falling through to the ERP path.
    """

    return (
        "EXISTS (SELECT 1 FROM `tabDynamic Link` AS `crm_orphan_link` "
        "LEFT JOIN `tabCustomer` AS `crm_orphan_customer` "
        "ON `crm_orphan_customer`.`name` = `crm_orphan_link`.`link_name` "
        f"WHERE `crm_orphan_link`.`parent` = {address_expression} "
        "AND `crm_orphan_link`.`parenttype` = 'Address' "
        "AND `crm_orphan_link`.`parentfield` = 'links' "
        "AND `crm_orphan_link`.`link_doctype` = 'Customer' "
        "AND `crm_orphan_customer`.`name` IS NULL)"
    )


def _protected_address_exists_condition(address_expression: str) -> str:
    """CRM sites and Addresses that cannot be told apart from one stay off the ERP path."""

    return (
        f"({_crm_address_exists_condition(address_expression)} "
        f"OR {_orphan_customer_link_exists_condition(address_expression)})"
    )


def _address_crm_identity(user: str | None) -> tuple[str | None, bool]:
    """Return the single CRM role and whether the identity is ambiguous."""

    if not user or user == "Guest":
        return None, False
    if user == "Administrator":
        return "Manager", False
    assigned = set(frappe.get_roles(user)).intersection(CRM_ROLE_TO_PROFILE)
    if not assigned:
        return None, False
    if len(assigned) != 1:
        return None, True
    return CRM_ROLE_TO_PROFILE[next(iter(assigned))], False


def _has_explicit_erp_address_role(user: str | None) -> bool:
    """Detect an Address DocPerm role other than automatic and CRM roles.

    The native permission engine remains responsible for the requested permission,
    owner-only rows and User Permissions. This only decides whether a mixed CRM/ERP
    identity may hand a non-CRM Address back to that engine.
    """

    if not user or user in {"Guest", "Administrator"}:
        return False
    candidate_roles = (
        set(frappe.get_roles(user))
        .difference(AUTOMATIC_ROLES)
        .difference(CRM_ROLE_TO_PROFILE)
    )
    return any(
        permission.role in candidate_roles
        and any(permission.get(permission_type) for permission_type in ADDRESS_NATIVE_PERMISSION_TYPES)
        for permission in get_valid_perms("Address", user)
    )


def _document_has_crm_customer_link(doc) -> bool:
    for link in doc.get("links") or ():
        if link.get("link_doctype") != "Customer" or not link.get("link_name"):
            continue
        if frappe.db.get_value("Customer", link.get("link_name"), "customer_group") == "CRM Customers":
            return True
    return False


def _address_customer_names(address_name: str | None, doc=None) -> tuple[str, ...]:
    customer_names = {
        link.get("link_name")
        for link in ((doc.get("links") or ()) if doc is not None else ())
        if link.get("link_doctype") == "Customer" and link.get("link_name")
    }
    if address_name:
        customer_names.update(frappe.db.sql_list(
            "SELECT `link_name` FROM `tabDynamic Link` "
            "WHERE `parent` = %s AND `parenttype` = 'Address' "
            "AND `parentfield` = 'links' AND `link_doctype` = 'Customer'",
            (address_name,),
        ))
    return tuple(sorted(customer_names))


def _lock_customer_groups(customer_names: tuple[str, ...]) -> dict[str, str | None]:
    if not customer_names:
        return {}
    placeholders = ", ".join(["%s"] * len(customer_names))
    rows = frappe.db.sql(
        f"SELECT `name`, `customer_group` FROM `tabCustomer` "
        f"WHERE `name` IN ({placeholders}) ORDER BY `name` FOR UPDATE",
        customer_names,
        as_dict=True,
    )
    return {row.name: row.customer_group for row in rows}


def _is_crm_customer_address(address_name: str | None, doc=None) -> bool:
    # During a re-parenting save the old database links and the proposed in-memory
    # links both matter: neither direction may turn a CRM mutation into an ERP one.
    if doc is not None and _document_has_crm_customer_link(doc):
        return True
    if not address_name:
        return False
    return bool(frappe.db.sql(
        "SELECT 1 FROM `tabDynamic Link` AS `crm_address_link` "
        "INNER JOIN `tabCustomer` AS `crm_address_customer` "
        "ON `crm_address_customer`.`name` = `crm_address_link`.`link_name` "
        "WHERE `crm_address_link`.`parent` = %s "
        "AND `crm_address_link`.`parenttype` = 'Address' "
        "AND `crm_address_link`.`parentfield` = 'links' "
        "AND `crm_address_link`.`link_doctype` = 'Customer' "
        "AND `crm_address_customer`.`customer_group` = 'CRM Customers' LIMIT 1",
        (address_name,),
    ))


def _has_orphan_customer_link(address_name: str | None) -> bool:
    if not address_name:
        return False
    return bool(frappe.db.sql(
        "SELECT 1 FROM `tabDynamic Link` AS `crm_orphan_link` "
        "LEFT JOIN `tabCustomer` AS `crm_orphan_customer` "
        "ON `crm_orphan_customer`.`name` = `crm_orphan_link`.`link_name` "
        "WHERE `crm_orphan_link`.`parent` = %s "
        "AND `crm_orphan_link`.`parenttype` = 'Address' "
        "AND `crm_orphan_link`.`parentfield` = 'links' "
        "AND `crm_orphan_link`.`link_doctype` = 'Customer' "
        "AND `crm_orphan_customer`.`name` IS NULL LIMIT 1",
        (address_name,),
    ))


def _lock_address(address_name: str | None):
    if address_name:
        rows = frappe.db.sql(
            "SELECT `modified` FROM `tabAddress` WHERE `name` = %s FOR UPDATE",
            (address_name,),
        )
        return rows[0][0] if rows else None
    return None


def _delete_address_shares(address_names: list[str] | tuple[str, ...]) -> None:
    if address_names:
        placeholders = ", ".join(["%s"] * len(address_names))
        frappe.db.sql(
            f"DELETE FROM `tabDocShare` WHERE `share_doctype` = 'Address' "
            f"AND `share_name` IN ({placeholders})",
            tuple(address_names),
        )


def revoke_address_shares_entering_crm(doc, method: str | None = None) -> None:
    """Atomically remove ERP shares when an Address gains a CRM Customer link."""

    del method
    customer_groups = _lock_customer_groups(
        _address_customer_names(getattr(doc, "name", None), doc=doc),
    )
    if not doc.is_new():
        _lock_address(doc.name)
    if "CRM Customers" in customer_groups.values():
        _delete_address_shares((doc.name,))


def revoke_customer_address_shares_entering_crm(doc, method: str | None = None) -> None:
    """Remove shares from linked Addresses before a Customer enters CRM scope."""

    del method
    if doc.get("customer_group") != "CRM Customers" or doc.is_new():
        return
    frappe.db.sql("SELECT `name` FROM `tabCustomer` WHERE `name` = %s FOR UPDATE", (doc.name,))
    address_names = sorted(set(frappe.db.sql_list(
        "SELECT `parent` FROM `tabDynamic Link` "
        "WHERE `parenttype` = 'Address' AND `parentfield` = 'links' "
        "AND `link_doctype` = 'Customer' AND `link_name` = %s "
        "ORDER BY `parent` FOR UPDATE",
        (doc.name,),
    )))
    for address_name in address_names:
        _lock_address(address_name)
    _delete_address_shares(tuple(address_names))


def prevent_scoped_docshare(doc, method: str | None = None) -> None:
    """Keep explicit shares from overriding CRM parent and site scope."""

    del method
    blocked = doc.share_doctype in NATIVE_SHARE_BLOCKED_DOCTYPES
    if doc.share_doctype == "Address":
        # Use the Address already loaded by DocShare's controller as the optimistic
        # boundary. Customer locks are current reads and always precede the Address
        # lock, matching both transition hooks. A concurrent re-parent changes
        # Address.modified; fail closed instead of classifying from an RR snapshot.
        address_doc = doc.get_doc()
        loaded_modified = address_doc.modified
        customer_names = _address_customer_names(doc.share_name, doc=address_doc)
        customer_groups = _lock_customer_groups(customer_names)
        locked_modified = _lock_address(doc.share_name)
        if frappe.utils.get_datetime(locked_modified) != frappe.utils.get_datetime(loaded_modified):
            frappe.throw(
                "Address changed while its sharing boundary was checked. Please retry.",
                frappe.PermissionError,
            )
        # A link to a Customer that is gone cannot show the Address is ordinary ERP data.
        blocked = "CRM Customers" in customer_groups.values() or len(customer_groups) < len(customer_names)
    if blocked:
        frappe.throw(
            f"{doc.share_doctype} records in CRM scope cannot be shared directly.",
            frappe.PermissionError,
        )


def _role_for_query(user: str | None) -> str | None:
    resolved_user = user or getattr(frappe.session, "user", None)
    if not resolved_user or resolved_user == "Guest":
        return None
    try:
        return resolve_crm_role(resolved_user)
    except frappe.PermissionError:
        return None


def _customer_condition(table: str, role: str, escaped_user: str) -> str:
    if role == "Manager":
        return "1=1"
    if role == "Sales":
        return f"({table}.`custom_crm_owner` = {escaped_user} OR COALESCE({table}.`custom_crm_visibility`, 'Private') = 'Public')"
    if role == "Engineer":
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Account Engineer Assignment` AS `crm_assignment` "
            f"WHERE `crm_assignment`.`customer` = {table}.`name` "
            f"AND `crm_assignment`.`engineer` = {escaped_user} "
            "AND `crm_assignment`.`enabled` = 1)"
        )
    return "1=0"


def _sales_parent_account_condition(
    account_expression: str,
    escaped_user: str,
    *,
    allow_unlinked: bool = False,
) -> str:
    """Keep child ownership from widening access to another Sales user's Private Account."""

    customer_table = "`crm_parent_customer`"
    customer_scope = _customer_condition(customer_table, "Sales", escaped_user)
    linked_scope = (
        "EXISTS (SELECT 1 FROM `tabCustomer` AS `crm_parent_customer` "
        f"WHERE `crm_parent_customer`.`name` = {account_expression} "
        f"AND ({customer_scope}))"
    )
    if allow_unlinked:
        return f"(COALESCE({account_expression}, '') = '' OR {linked_scope})"
    return linked_scope


def _sales_account_owner_condition(account_expression: str, escaped_user: str) -> str:
    """Restrict raw Site/Address-bearing records to the Account owner."""

    return (
        "EXISTS (SELECT 1 FROM `tabCustomer` AS `crm_owned_customer` "
        f"WHERE `crm_owned_customer`.`name` = {account_expression} "
        f"AND `crm_owned_customer`.`custom_crm_owner` = {escaped_user})"
    )


def _sales_linked_account_owner_condition(
    parent_expression: str,
    parenttype: str,
    escaped_user: str,
) -> str:
    """Require a standard Contact-like document to link to an owned Account."""

    return (
        "EXISTS (SELECT 1 FROM `tabDynamic Link` AS `crm_owned_link` "
        "INNER JOIN `tabCustomer` AS `crm_owned_customer` "
        "ON `crm_owned_customer`.`name` = `crm_owned_link`.`link_name` "
        f"WHERE `crm_owned_link`.`parent` = {parent_expression} "
        f"AND `crm_owned_link`.`parenttype` = {frappe.db.escape(parenttype)} "
        "AND `crm_owned_link`.`parentfield` = 'links' "
        "AND `crm_owned_link`.`link_doctype` = 'Customer' "
        f"AND `crm_owned_customer`.`custom_crm_owner` = {escaped_user})"
    )


def _raw_site_data_query(doctype: str, user: str | None = None) -> str:
    """Hide unredacted standard DocType rows from non-Account-owner Sales.

    Custom CRM services deliberately use ``conditions_for_doctype`` and return
    redacted DTOs. Standard Frappe resource APIs return the raw document, so a
    narrower query is required for records that carry Site/Address fields.
    """

    condition = conditions_for_doctype(doctype, user)
    resolved_user = user or getattr(frappe.session, "user", None)
    if _role_for_query(resolved_user) != "Sales":
        return condition
    escaped_user = frappe.db.escape(resolved_user)
    if doctype == "Contact":
        account_owner_scope = _sales_linked_account_owner_condition(
            "`tabContact`.`name`",
            "Contact",
            escaped_user,
        )
    else:
        account_owner_scope = _sales_account_owner_condition(
            f"`tab{doctype}`.`account`",
            escaped_user,
        )
    return f"({condition}) AND ({account_owner_scope})"


def _sales_child_condition(
    owner_condition: str,
    account_expression: str,
    escaped_user: str,
    *,
    allow_unlinked: bool = False,
) -> str:
    parent_scope = _sales_parent_account_condition(
        account_expression,
        escaped_user,
        allow_unlinked=allow_unlinked,
    )
    return f"({owner_condition}) AND ({parent_scope})"


def _parent_scope_condition(
    child_doctype: str,
    parent_doctype: str,
    parent_field: str,
    user: str,
) -> str:
    """Correlate a native child-record query with the parent's current row scope."""

    parent_scope = conditions_for_doctype(parent_doctype, user)
    return (
        f"EXISTS (SELECT 1 FROM `tab{parent_doctype}` "
        f"WHERE `tab{parent_doctype}`.`name` = `tab{child_doctype}`.`{parent_field}` "
        f"AND ({parent_scope}))"
    )


def conditions_for_doctype(doctype: str, user: str | None = None) -> str:
    if doctype not in CONDITION_DOCTYPES:
        raise ValueError(f"Unsupported scoped DocType: {doctype}")

    resolved_user = user or getattr(frappe.session, "user", None)
    role = _role_for_query(resolved_user)
    if not role or not resolved_user:
        return "1=0"
    if doctype == "CRM Notification Event":
        return f"`tabCRM Notification Event`.`recipient_user` = {frappe.db.escape(resolved_user)}"
    if doctype == "CRM Opportunity Stakeholder" and role == "Engineer":
        return "1=0"
    if doctype in OPPORTUNITY_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(doctype, "CRM Opportunity", "opportunity", resolved_user)
    if doctype in DEMO_REQUEST_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(doctype, "CRM Demo Request", "demo_request", resolved_user)
    if doctype in EVALUATION_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(doctype, "CRM Evaluation", "evaluation", resolved_user)
    if doctype in INSTALLED_TOOL_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(doctype, "CRM Installed Tool", "installed_tool", resolved_user)
    if doctype == "Address":
        escaped_user = frappe.db.escape(resolved_user)
        customer_scope = _customer_condition("`crm_customer`", role, escaped_user)
        if role == "Sales":
            # Public Accounts may be returned through redacted CRM DTOs, while the
            # native Address document exposes the complete site address.
            customer_scope = f"`crm_customer`.`custom_crm_owner` = {escaped_user}"
        return (
            "EXISTS (SELECT 1 FROM `tabDynamic Link` AS `crm_link` "
            "INNER JOIN `tabCustomer` AS `crm_customer` ON `crm_customer`.`name` = `crm_link`.`link_name` "
            "WHERE `crm_link`.`parent` = `tabAddress`.`name` "
            "AND `crm_link`.`parenttype` = 'Address' AND `crm_link`.`parentfield` = 'links' "
            "AND `crm_link`.`link_doctype` = 'Customer' "
            "AND `crm_customer`.`customer_group` = 'CRM Customers' "
            f"AND ({customer_scope}))"
        )
    if doctype == "CRM Visit Meeting Record":
        # The minutes are read exactly where their visit is. The visit condition
        # references `tabCRM Visit` unaliased, so nesting it inside a correlated
        # EXISTS on that table keeps it bound to the record's visit.
        visit_scope = conditions_for_doctype("CRM Visit", resolved_user)
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Visit` "
            "WHERE `tabCRM Visit`.`name` = `tabCRM Visit Meeting Record`.`visit` "
            f"AND ({visit_scope}))"
        )
    if doctype == "CRM Demo Artifact":
        escaped_user = frappe.db.escape(resolved_user)
        submitted = (
            "EXISTS (SELECT 1 FROM `tabCRM Demo Request History` AS `crm_history` "
            "WHERE `crm_history`.`demo_request` = `crm_request`.`name` "
            "AND `crm_history`.`to_status` = 'Engineer Review')"
        )
        if role == "Manager":
            role_scope = submitted
        elif role == "Sales":
            role_scope = _sales_child_condition(
                f"`crm_request`.`sales_owner` = {escaped_user}",
                "`crm_request`.`account`",
                escaped_user,
                allow_unlinked=True,
            )
        else:
            role_scope = f"`crm_request`.`engineer_owner` = {escaped_user} AND {submitted}"
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Demo Request` AS `crm_request` "
            "WHERE `crm_request`.`name` = `tabCRM Demo Artifact`.`demo_request` "
            "AND `crm_request`.`account` = `tabCRM Demo Artifact`.`account` "
            f"AND ({role_scope}))"
        )
    if doctype in {"CRM Quotation", "CRM Quotation Version", "CRM Quotation Approval"}:
        if role == "Manager":
            return "1=1"
        if role != "Sales":
            return "1=0"
        escaped_user = frappe.db.escape(resolved_user)
        if doctype == "CRM Quotation":
            return _sales_child_condition(
                f"`tabCRM Quotation`.`quotation_owner` = {escaped_user}",
                "`tabCRM Quotation`.`account`",
                escaped_user,
            )
        quotation_scope = _sales_child_condition(
            f"`crm_quotation`.`quotation_owner` = {escaped_user}",
            "`crm_quotation`.`account`",
            escaped_user,
        )
        if doctype == "CRM Quotation Approval":
            return (
                "EXISTS (SELECT 1 FROM `tabCRM Quotation` AS `crm_quotation` "
                "WHERE `crm_quotation`.`name` = `tabCRM Quotation Approval`.`quotation` "
                f"AND ({quotation_scope}))"
            )
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Quotation` AS `crm_quotation` "
            "WHERE `crm_quotation`.`name` = `tabCRM Quotation Version`.`quotation` "
            f"AND ({quotation_scope}))"
        )
    if doctype in {"CRM RFQ", "CRM RFQ Version"}:
        escaped_user = frappe.db.escape(resolved_user)
        if role == "Manager":
            return "1=1"
        owner_field = "sales_owner" if role == "Sales" else "engineer_owner"
        if doctype == "CRM RFQ":
            owner_scope = f"`tabCRM RFQ`.`{owner_field}` = {escaped_user}"
            if role == "Sales":
                return _sales_child_condition(
                    owner_scope,
                    "`tabCRM RFQ`.`account`",
                    escaped_user,
                )
            return owner_scope
        owner_scope = f"`crm_rfq`.`{owner_field}` = {escaped_user}"
        if role == "Sales":
            owner_scope = _sales_child_condition(
                owner_scope,
                "`crm_rfq`.`account`",
                escaped_user,
            )
        return (
            "EXISTS (SELECT 1 FROM `tabCRM RFQ` AS `crm_rfq` "
            "WHERE `crm_rfq`.`name` = `tabCRM RFQ Version`.`rfq` "
            f"AND ({owner_scope}))"
        )
    if role == "Manager":
        return "1=1"

    escaped_user = frappe.db.escape(resolved_user)
    if doctype == "CRM Account Engineer Assignment":
        if role != "Engineer":
            return "1=0"
        return (
            f"`tabCRM Account Engineer Assignment`.`engineer` = {escaped_user} "
            "AND `tabCRM Account Engineer Assignment`.`enabled` = 1"
        )
    if doctype == "CRM Document Access Request":
        return f"`tabCRM Document Access Request`.`requester` = {escaped_user}"
    if doctype == "Customer":
        return _customer_condition("`tabCustomer`", role, escaped_user)
    if doctype == "Contact":
        customer_scope = _customer_condition("`crm_customer`", role, escaped_user)
        account_condition = (
            "EXISTS (SELECT 1 FROM `tabDynamic Link` AS `crm_link` "
            "INNER JOIN `tabCustomer` AS `crm_customer` ON `crm_customer`.`name` = `crm_link`.`link_name` "
            "WHERE `crm_link`.`parent` = `tabContact`.`name` "
            "AND `crm_link`.`parenttype` = 'Contact' AND `crm_link`.`parentfield` = 'links' "
            f"AND `crm_link`.`link_doctype` = 'Customer' AND ({customer_scope}))"
        )
        return account_condition
    if doctype == "Lead":
        if role == "Sales":
            return _sales_child_condition(
                f"`tabLead`.`lead_owner` = {escaped_user}",
                "`tabLead`.`custom_crm_converted_account`",
                escaped_user,
                allow_unlinked=True,
            )
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Account Engineer Assignment` AS `crm_assignment` "
            "WHERE `crm_assignment`.`customer` = `tabLead`.`custom_crm_converted_account` "
            f"AND `crm_assignment`.`engineer` = {escaped_user} "
            "AND `crm_assignment`.`enabled` = 1)"
        )
    if doctype == "CRM Booking":
        if role == "Sales":
            return _sales_child_condition(
                f"`tabCRM Booking`.`booking_owner` = {escaped_user}",
                "`tabCRM Booking`.`account`",
                escaped_user,
            )
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Account Engineer Assignment` AS `crm_assignment` "
            "WHERE `crm_assignment`.`customer` = `tabCRM Booking`.`account` "
            f"AND `crm_assignment`.`engineer` = {escaped_user} "
            "AND `crm_assignment`.`enabled` = 1)"
        )
    if doctype == "CRM Installed Tool":
        if role == "Sales":
            return _sales_child_condition(
                f"`tabCRM Installed Tool`.`sales_owner` = {escaped_user}",
                "`tabCRM Installed Tool`.`account`",
                escaped_user,
            )
        return f"`tabCRM Installed Tool`.`engineer_owner` = {escaped_user}"
    if doctype == "CRM Demo Request":
        owner_field = "sales_owner" if role == "Sales" else "engineer_owner"
        owner_scope = f"`tabCRM Demo Request`.`{owner_field}` = {escaped_user}"
        if role == "Sales":
            return _sales_child_condition(
                owner_scope,
                "`tabCRM Demo Request`.`account`",
                escaped_user,
                allow_unlinked=True,
            )
        return owner_scope
    if doctype == "CRM Evaluation":
        if role == "Engineer":
            return f"`tabCRM Evaluation`.`evaluation_owner` = {escaped_user}"
        request_scope = _sales_child_condition(
            f"`crm_demo_request`.`sales_owner` = {escaped_user}",
            "`crm_demo_request`.`account`",
            escaped_user,
            allow_unlinked=True,
        )
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Demo Request` AS `crm_demo_request` "
            "WHERE `crm_demo_request`.`name` = `tabCRM Evaluation`.`demo_request` "
            f"AND ({request_scope}))"
        )
    if doctype == "CRM Visit":
        if role == "Sales":
            owner_scope = (
                f"(`tabCRM Visit`.`visit_owner` = {escaped_user} "
                f"OR `tabCRM Visit`.`action_owner` = {escaped_user})"
            )
            return _sales_child_condition(
                owner_scope,
                "`tabCRM Visit`.`account`",
                escaped_user,
            )
        return "1=0"
    if doctype == "CRM Status Attachment":
        # Visible exactly when its Opportunity is, and only while it is live. The
        # Opportunity condition references `tabCRM Opportunity` unaliased, so a
        # correlated EXISTS on that table keeps it bound to the parent row.
        opportunity_scope = conditions_for_doctype("CRM Opportunity", resolved_user)
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Opportunity` "
            "WHERE `tabCRM Status Attachment`.`deleted` = 0 "
            "AND `tabCRM Opportunity`.`name` = `tabCRM Status Attachment`.`opportunity` "
            f"AND ({opportunity_scope}))"
        )
    if doctype == "CRM Contact File":
        table = f"`tab{doctype}`"
        customer_scope = (
            f"`crm_customer`.`custom_crm_owner` = {escaped_user}"
            if role == "Sales"
            else _customer_condition("`crm_customer`", role, escaped_user)
        )
        live_scope = f"{table}.`deleted` = 0 AND " if doctype == "CRM Contact File" else ""
        return (
            "EXISTS (SELECT 1 FROM `tabCustomer` AS `crm_customer` "
            f"WHERE {live_scope}`crm_customer`.`name` = {table}.`account` AND ({customer_scope}))"
        )
    if role == "Sales":
        return _sales_child_condition(
            f"`tabCRM Opportunity`.`opportunity_owner` = {escaped_user}",
            "`tabCRM Opportunity`.`account`",
            escaped_user,
        )
    return (
        "EXISTS (SELECT 1 FROM `tabCRM Account Engineer Assignment` AS `crm_assignment` "
        "WHERE `crm_assignment`.`customer` = `tabCRM Opportunity`.`account` "
        f"AND `crm_assignment`.`engineer` = {escaped_user} "
        "AND `crm_assignment`.`enabled` = 1)"
    )


def customer_query(user: str | None = None) -> str:
    return conditions_for_doctype("Customer", user)


def address_query(user: str | None = None) -> str:
    resolved_user = user or getattr(frappe.session, "user", None)
    if resolved_user == "Administrator":
        # Frappe's superuser shortcut covers single documents only; lists, counts, exports and
        # link search still run this hook, and Administrator keeps every Address, CRM site or not.
        return ""
    role, ambiguous = _address_crm_identity(resolved_user)
    has_erp_role = _has_explicit_erp_address_role(resolved_user)
    if not role and not ambiguous:
        return ""
    if ambiguous:
        if has_erp_role:
            return f"NOT ({_protected_address_exists_condition('`tabAddress`.`name`')})"
        return "1=0"
    crm_scope = conditions_for_doctype("Address", resolved_user)
    if has_erp_role:
        boundary = _protected_address_exists_condition("`tabAddress`.`name`")
        return f"(NOT ({boundary}) OR ({crm_scope}))"
    return crm_scope


def contact_query(user: str | None = None) -> str:
    return _raw_site_data_query("Contact", user)


def lead_query(user: str | None = None) -> str:
    return conditions_for_doctype("Lead", user)


def opportunity_query(user: str | None = None) -> str:
    return _raw_site_data_query("CRM Opportunity", user)


def booking_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Booking", user)


def installed_tool_query(user: str | None = None) -> str:
    return _raw_site_data_query("CRM Installed Tool", user)


def demo_request_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Demo Request", user)


def evaluation_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Evaluation", user)


def opportunity_probability_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity Probability History", user)


def probability_recovery_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Probability Recovery", user)


def probability_recovery_revision_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Probability Recovery Revision", user)


def opportunity_loss_review_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity Loss Review", user)


def opportunity_loss_review_revision_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity Loss Review Revision", user)


def opportunity_stage_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity Stage History", user)


def opportunity_internal_validation_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity Internal Validation", user)


def opportunity_action_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity Action", user)


def opportunity_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity History", user)


def opportunity_stakeholder_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Opportunity Stakeholder", user)


def account_engineer_assignment_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Account Engineer Assignment", user)


def installed_tool_lifecycle_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Installed Tool Lifecycle History", user)


def installed_tool_service_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Installed Tool Service History", user)


def installed_tool_version_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Installed Tool Version History", user)


def demo_comment_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Demo Comment", user)


def demo_request_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Demo Request History", user)


def evaluation_customer_review_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Evaluation Customer Review", user)


def evaluation_history_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Evaluation History", user)


def test_run_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Test Run", user)


def contact_file_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Contact File", user)


def status_attachment_query(user: str | None = None) -> str:
    """Scope for `CRM Status Attachment`, inert while the doctype has no DocPerm.

    `db_query` refuses the doctype on the read check before it ever applies this
    condition, so nothing reaches it today. It exists so that a future decision to
    grant read starts from the right rows -- the owner's, and only the live ones --
    instead of from everything.
    """
    return conditions_for_doctype("CRM Status Attachment", user)


def has_status_attachment_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
    """Deny everyone. A controller hook can only deny, never grant.

    The empty DocPerm map is what actually closes native access to the bytes, and
    `has_crm_permission` would answer "yes" for an in-scope Sales user the moment
    somebody added `read` to it. Denying here means that grant alone cannot open
    the unaudited `/private/files/...` route; the service reads these rows with raw
    SQL and writes them with ignore_permissions, so it is unaffected.
    """
    return False


def demo_artifact_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Demo Artifact", user)


def notification_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Notification Event", user)


def document_access_request_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Document Access Request", user)


def visit_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Visit", user)


def visit_meeting_record_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Visit Meeting Record", user)


def quotation_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Quotation", user)


def quotation_version_query(user: str | None = None) -> str:
    return _raw_site_data_query("CRM Quotation Version", user)


def quotation_approval_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Quotation Approval", user)


def rfq_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM RFQ", user)


def rfq_version_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM RFQ Version", user)


def has_crm_permission(
    doc,
    user: str | None = None,
    permission_type: str | None = None,
    ptype: str | None = None,
    debug: bool = False,
) -> bool:
    # Frappe v15 calls controller hooks with ``ptype`` and ``debug``. Keep
    # ``permission_type`` for the direct service/test callers already using it.
    del debug
    resolved_user = user or getattr(frappe.session, "user", None)
    normalized_permission = permission_type or ptype
    if not resolved_user or resolved_user == "Guest":
        return False
    role = _role_for_query(resolved_user)
    if not role:
        return False
    view_capability = DOCTYPES_TO_VIEW_CAPABILITY.get(doc.doctype)
    if view_capability and view_capability not in capabilities_for_role(role):
        return False
    if normalized_permission and normalized_permission not in _permissions_for_doctype(doc.doctype, role):
        return False
    if getattr(doc, "is_new", lambda: False)():
        return role == "Manager"

    condition = conditions_for_doctype(doc.doctype, resolved_user)
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tab{doc.doctype}` WHERE `name` = %s AND ({condition}) LIMIT 1",
        (doc.name,),
    )
    return bool(rows)


def has_site_bearing_permission(
    doc,
    user: str | None = None,
    permission_type: str | None = None,
    ptype: str | None = None,
    debug: bool = False,
) -> bool:
    """Deny raw DocType/File access when Site/Address data must be redacted.

    CRM services may still return a redacted business record to its child-record
    owner. Standard DocType APIs operate on unredacted documents, so Sales users
    must also own the linked Account.
    """

    del debug
    resolved_user = user or getattr(frappe.session, "user", None)
    normalized_permission = permission_type or ptype
    if not has_crm_permission(
        doc,
        user=resolved_user,
        permission_type=normalized_permission,
    ):
        return False
    if _role_for_query(resolved_user) != "Sales":
        return True
    if doc.doctype in {"Address", "Contact"}:
        rows = frappe.db.sql(
            "SELECT 1 FROM `tabDynamic Link` AS `crm_owned_link` "
            "INNER JOIN `tabCustomer` AS `crm_owned_customer` "
            "ON `crm_owned_customer`.`name` = `crm_owned_link`.`link_name` "
            "WHERE `crm_owned_link`.`parent` = %s "
            "AND `crm_owned_link`.`parenttype` = %s "
            "AND `crm_owned_link`.`parentfield` = 'links' "
            "AND `crm_owned_link`.`link_doctype` = 'Customer' "
            "AND `crm_owned_customer`.`customer_group` = 'CRM Customers' "
            "AND `crm_owned_customer`.`custom_crm_owner` = %s LIMIT 1",
            (doc.name, doc.doctype, resolved_user),
        )
        return bool(rows)
    account_id = frappe.db.get_value(doc.doctype, doc.name, "account")
    return bool(
        account_id
        and frappe.db.get_value("Customer", account_id, "custom_crm_owner") == resolved_user
    )


def has_address_permission(
    doc,
    user: str | None = None,
    permission_type: str | None = None,
    ptype: str | None = None,
    debug: bool = False,
) -> bool | None:
    """Apply CRM site rules without changing Address access for non-CRM ERP users."""

    resolved_user = user or getattr(frappe.session, "user", None)
    role, ambiguous = _address_crm_identity(resolved_user)
    has_erp_role = _has_explicit_erp_address_role(resolved_user)
    is_crm_address = _is_crm_customer_address(getattr(doc, "name", None), doc=doc)
    if not role and not ambiguous:
        return None
    # An Address linked to a Customer that is gone cannot be shown to be ordinary ERP data.
    protected = is_crm_address or _has_orphan_customer_link(getattr(doc, "name", None))
    if ambiguous:
        return None if has_erp_role and not protected else False
    if not protected:
        return None if has_erp_role else False
    if not is_crm_address:
        return False
    return has_site_bearing_permission(
        doc,
        user=resolved_user,
        permission_type=permission_type,
        ptype=ptype,
        debug=debug,
    )


def has_quotation_version_permission(
    doc,
    user: str | None = None,
    permission_type: str | None = None,
    ptype: str | None = None,
    debug: bool = False,
) -> bool:
    """Backward-compatible named hook for quotation Version/File checks."""

    return has_site_bearing_permission(
        doc,
        user=user,
        permission_type=permission_type,
        ptype=ptype,
        debug=debug,
    )
