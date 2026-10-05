"""SQL-backed row scope shared by CRM list and detail permission checks."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

import frappe
from frappe.model.db_query import DatabaseQuery
from frappe.permissions import AUTOMATIC_ROLES, add_permission, get_valid_perms, update_permission_property

from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE, capabilities_for_role, resolve_crm_role
from rayher_crm.setup.indexes import LEAD_CONVERTED_ACCOUNT_INDEX


_ADDRESS_LINK_USER: ContextVar[str | None] = ContextVar("crm_address_link_user", default=None)
_WAREHOUSE_LINK_USER: ContextVar[str | None] = ContextVar("crm_warehouse_link_user", default=None)


@contextmanager
def address_link_query_scope(*, warehouse_lookup: bool = False):
    """Enable selection grants only inside a trusted, name-only Link query."""
    token = _ADDRESS_LINK_USER.set(frappe.session.user)
    warehouse_token = _WAREHOUSE_LINK_USER.set(frappe.session.user if warehouse_lookup else None)
    try:
        yield
    finally:
        _WAREHOUSE_LINK_USER.reset(warehouse_token)
        _ADDRESS_LINK_USER.reset(token)


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
SCOPED_CHILD_RELATIONSHIPS = {
    "Allowed To Transact With": (("Customer", "companies"), ("Supplier", "companies")),
    "Customer Credit Limit": (("Customer", "credit_limits"), ("Customer Group", "credit_limits")),
    "Party Account": (
        ("Customer", "accounts"),
        ("Customer Group", "accounts"),
        ("Supplier", "accounts"),
        ("Supplier Group", "accounts"),
    ),
    "Sales Team": (
        ("Customer", "sales_team"),
        ("Delivery Note", "sales_team"),
        ("POS Invoice", "sales_team"),
        ("Sales Invoice", "sales_team"),
        ("Sales Order", "sales_team"),
    ),
    "Portal User": (("Customer", "portal_users"), ("Supplier", "portal_users")),
    "Contact Email": (("Contact", "email_ids"),),
    "Contact Phone": (("Contact", "phone_nos"),),
    "Event Participants": (("Event", "event_participants"),),
    "Event Notifications": (("Event", "notifications"),),
    "Communication Link": (("Communication", "timeline_links"),),
    "Dynamic Link": (
        ("Address", "links"),
        ("Call Log", "links"),
        ("Common Code", "applies_to"),
        ("Contact", "links"),
        ("Event", "links"),
    ),
    "CRM Note": (("Lead", "notes"), ("Opportunity", "notes"), ("Prospect", "notes")),
    "CRM Quotation Item": (("CRM Quotation Version", "items"),),
    "CRM Quotation Payment Term": (("CRM Quotation Version", "payment_terms"),),
}
CONDITION_DOCTYPES = (
    SCOPED_DOCTYPES
    + ("Address", "CRM Account Engineer Assignment")
    + tuple(SCOPED_CHILD_RELATIONSHIPS)
)
# Every CRM DocType belongs to the whitelisted services in api/v1: they check the business
# rules, drive the state machines and append the history rows the cockpit reads. The standard
# Frappe document API (/api/resource, frappe.client, the Desk form) writes straight to the
# table and skips all of that, so no CRM role gets write, create or delete on any of them.
MUTATING_PERMISSIONS = frozenset({"write", "create", "delete"})
# Frappe ships these with an "All" row that lets every signed-in user change them.
SHARED_STANDARD_DOCTYPES = ("Customer", "Contact", "Lead")
# Boundary transitions lock the records whose shares they revoke with NOWAIT
# (see _lock_transition_targets), so each lookup must reach only those rows
# through an index: a scan would also lock, and fail on, unrelated rows.
_CUSTOMER_CONVERTED_LEAD_QUERY = f"""SELECT `name` FROM `tabLead`
FORCE INDEX ({LEAD_CONVERTED_ACCOUNT_INDEX})
WHERE `custom_crm_converted_account` = %s
ORDER BY `name` FOR UPDATE NOWAIT"""
_CUSTOMER_LINKED_PARENTS_QUERY = """SELECT `parent` FROM `tabDynamic Link`
WHERE `parenttype` = %s AND `parentfield` = 'links'
AND `link_doctype` = 'Customer' AND `link_name` = %s
ORDER BY `parent` FOR UPDATE NOWAIT"""
_OWNED_LEADS_QUERY = """SELECT `name` FROM `tabLead`
WHERE `lead_owner` = %s
ORDER BY `name` FOR UPDATE NOWAIT"""
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
# Frappe applies DocShare after controller permission hooks. Every DocType in
# the Rayher CRM module is service-owned, including configuration, audit and
# upload workflow types that are intentionally outside SCOPED_DOCTYPES. Runtime
# and install cleanup therefore use the DocType module registry, not a list that
# can silently miss a new custom type.
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
    frappe.db.sql(
        "DELETE `crm_share` FROM `tabDocShare` AS `crm_share` "
        "INNER JOIN `tabDocType` AS `crm_doctype` "
        "ON `crm_doctype`.`name` = `crm_share`.`share_doctype` "
        "WHERE `crm_doctype`.`module` = 'Rayher CRM'",
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

    # A dangling Customer link cannot prove that an Address is ordinary ERP data.
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

    # Standard ERP DocTypes remain shareable for non-CRM work, but a share must
    # neither grant a CRM identity an alternate path nor expose a CRM Customer or
    # Contact to an ERP identity. Remove both kinds of legacy rows atomically.
    crm_roles = tuple(CRM_ROLE_TO_PROFILE)
    role_placeholders = ", ".join(["%s"] * len(crm_roles))
    crm_recipients = (
        "COALESCE(`crm_share`.`everyone`, 0) = 1 OR `crm_share`.`user` IN ("
        "SELECT `parent` FROM `tabHas Role` "
        f"WHERE `parenttype` = 'User' AND `role` IN ({role_placeholders}))"
    )
    frappe.db.sql(
        "DELETE `crm_share` FROM `tabDocShare` AS `crm_share` "
        "WHERE `crm_share`.`share_doctype` = 'Customer' AND ("
        f"({crm_recipients}) OR `crm_share`.`share_name` IN ("
        "SELECT `name` FROM `tabCustomer` WHERE `customer_group` = 'CRM Customers'))",
        crm_roles,
    )
    frappe.db.sql(
        "DELETE `crm_share` FROM `tabDocShare` AS `crm_share` "
        "WHERE `crm_share`.`share_doctype` = 'Contact' AND ("
        f"({crm_recipients}) OR `crm_share`.`share_name` IN ("
        "SELECT `crm_contact_link`.`parent` FROM `tabDynamic Link` AS `crm_contact_link` "
        "INNER JOIN `tabCustomer` AS `crm_contact_customer` "
        "ON `crm_contact_customer`.`name` = `crm_contact_link`.`link_name` "
        "WHERE `crm_contact_link`.`parenttype` = 'Contact' "
        "AND `crm_contact_link`.`parentfield` = 'links' "
        "AND `crm_contact_link`.`link_doctype` = 'Customer' "
        "AND `crm_contact_customer`.`customer_group` = 'CRM Customers'))",
        crm_roles,
    )
    frappe.db.sql(
        "DELETE `crm_share` FROM `tabDocShare` AS `crm_share` "
        "WHERE `crm_share`.`share_doctype` = 'Lead' AND ("
        f"({crm_recipients}) OR `crm_share`.`share_name` IN ("
        "SELECT `crm_lead`.`name` FROM `tabLead` AS `crm_lead` "
        "LEFT JOIN `tabCustomer` AS `crm_lead_customer` "
        "ON `crm_lead_customer`.`name` = `crm_lead`.`custom_crm_converted_account` "
        "WHERE `crm_lead_customer`.`customer_group` = 'CRM Customers' "
        "OR `crm_lead`.`lead_owner` IN (SELECT `parent` FROM `tabHas Role` "
        f"WHERE `parenttype` = 'User' AND `role` IN ({role_placeholders}))))",
        (*crm_roles, *crm_roles),
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
    """Match an Address linked to a Customer row that no longer exists."""

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
    """Keep CRM sites and ambiguous orphan Addresses outside the ERP read path."""

    return (
        f"({_crm_address_exists_condition(address_expression)} "
        f"OR {_orphan_customer_link_exists_condition(address_expression)})"
    )


def _address_crm_identity(user: str | None) -> tuple[str | None, bool]:
    """Return the single CRM role and whether the identity is ambiguous."""

    if not user or user in {"Guest", "Administrator"}:
        return None, False
    assigned = set(frappe.get_roles(user)).intersection(CRM_ROLE_TO_PROFILE)
    if not assigned:
        return None, False
    if len(assigned) != 1:
        return None, True
    return CRM_ROLE_TO_PROFILE[next(iter(assigned))], False


def _erp_address_permissions(user: str | None) -> tuple:
    """Return Address grants from the user's non-CRM business roles only."""
    if not user or user in {"Guest", "Administrator"}:
        return ()
    candidate_roles = (
        set(frappe.get_roles(user))
        .difference(AUTOMATIC_ROLES)
        .difference(CRM_ROLE_TO_PROFILE)
    )
    return tuple(
        permission for permission in get_valid_perms("Address", user)
        if permission.role in candidate_roles and frappe.utils.cint(permission.get("permlevel")) == 0
    )


def _erp_address_read_scope(
    user: str | None, *, for_link_search: bool = False, warehouse_lookup: bool = False,
) -> str | None:
    """Return ERP read scope, optionally including selection in a Link query."""
    # ERPNext's warehouse picker selects names regardless of Address ownership.
    # Preserve that only in the trusted stock lookup; address_query still
    # excludes protected CRM rows from this ordinary ERP branch.
    if warehouse_lookup and for_link_search and (
        frappe.has_permission("Stock Entry", "read", user=user)
        and frappe.has_permission("Warehouse", "read", user=user)
    ):
        return "all"
    rows = tuple(
        permission for permission in _erp_address_permissions(user)
        if permission.get("read") or (for_link_search and permission.get("select"))
    )
    if any(not frappe.utils.cint(permission.get("if_owner")) for permission in rows):
        return "all"
    if rows:
        return "owner"
    return None


def address_link_requires_name_only(user: str | None = None) -> bool:
    resolved_user = user or frappe.session.user
    role, ambiguous = _address_crm_identity(resolved_user)
    if not role and not ambiguous:
        return False
    ranks = {None: 0, "owner": 1, "all": 2}
    return ranks[_erp_address_read_scope(resolved_user, for_link_search=True)] > ranks[
        _erp_address_read_scope(resolved_user)
    ]


def _has_explicit_erp_address_permission(user: str | None, permission_type: str) -> bool:
    if permission_type not in ADDRESS_NATIVE_PERMISSION_TYPES:
        return False
    return any(permission.get(permission_type) for permission in _erp_address_permissions(user))


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


def _lock_customer_groups(
    customer_names: tuple[str, ...], *, nowait: bool = False,
) -> dict[str, str | None]:
    if not customer_names:
        return {}
    placeholders = ", ".join(["%s"] * len(customer_names))
    rows = frappe.db.sql(
        f"SELECT `name`, `customer_group` FROM `tabCustomer` "
        f"WHERE `name` IN ({placeholders}) ORDER BY `name` FOR UPDATE"
        + (" NOWAIT" if nowait else ""),
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
    _delete_docshares("Address", address_names)


def _delete_docshares(doctype: str, names) -> None:
    target_names = tuple(sorted({name for name in names if name}))
    if not target_names:
        return
    placeholders = ", ".join(["%s"] * len(target_names))
    frappe.db.sql(
        f"DELETE FROM `tabDocShare` WHERE `share_doctype` = %s "
        f"AND `share_name` IN ({placeholders})",
        (doctype, *target_names),
    )


def _linked_customer_names(parenttype: str, name: str | None, doc=None) -> tuple[str, ...]:
    customer_names = {
        link.get("link_name")
        for link in ((doc.get("links") or ()) if doc is not None else ())
        if link.get("link_doctype") == "Customer" and link.get("link_name")
    }
    if name:
        customer_names.update(frappe.db.sql_list(
            "SELECT `link_name` FROM `tabDynamic Link` "
            "WHERE `parent` = %s AND `parenttype` = %s "
            "AND `parentfield` = 'links' AND `link_doctype` = 'Customer'",
            (name, parenttype),
        ))
    return tuple(sorted(customer_names))


def _lock_user_crm_roles(users, *, nowait: bool = False) -> set[str]:
    user_names = tuple(sorted({user for user in users if user}))
    if not user_names:
        return set()
    placeholders = ", ".join(["%s"] * len(user_names))
    frappe.db.sql(
        f"SELECT `name` FROM `tabUser` WHERE `name` IN ({placeholders}) "
        "ORDER BY `name` FOR UPDATE" + (" NOWAIT" if nowait else ""),
        user_names,
    )
    crm_roles = tuple(CRM_ROLE_TO_PROFILE)
    role_placeholders = ", ".join(["%s"] * len(crm_roles))
    return set(frappe.db.sql_list(
        "SELECT DISTINCT `parent` FROM `tabHas Role` "
        f"WHERE `parenttype` = 'User' AND `parent` IN ({placeholders}) "
        f"AND `role` IN ({role_placeholders}) FOR UPDATE"
        + (" NOWAIT" if nowait else ""),
        (*user_names, *crm_roles),
    ))


def _lock_transition_targets(doctype: str, query: str, values: tuple) -> list[str]:
    """Lock every record whose ERP shares a boundary transition revokes, or abort it.

    The transition already holds its Customer or User row. Frappe locks an
    Address/Contact/Lead (and its links) before that record's own hook or share
    check waits for the same row, so waiting here could deadlock. Skipping the
    record is no safer: the other transaction may still roll back (a denied
    native save, a rejected share), and its record would keep ERP shares inside
    CRM scope. ``query`` must lock with NOWAIT, so the transition fails instead
    and the caller retries once the record is free.
    """

    try:
        return frappe.db.sql_list(query, values)
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw(
            f"A linked {doctype} is being changed by another request, so its sharing "
            "boundary cannot be updated now. Please retry.",
            frappe.PermissionError,
        )


def _trusted_standard_service_write(doc) -> bool:
    return (
        getattr(frappe.session, "user", None) == "Administrator"
        or bool(getattr(doc, "flags", {}).get("ignore_permissions"))
    )


def _trusted_address_service_write(doc) -> bool:
    return _trusted_standard_service_write(doc)


def revoke_address_shares_entering_crm(doc, method: str | None = None) -> None:
    """Recheck the locked CRM boundary and remove obsolete ERP shares."""

    del method
    customer_groups = _lock_customer_groups(
        _address_customer_names(getattr(doc, "name", None), doc=doc),
    )
    if not doc.is_new():
        _lock_address(doc.name)
    if "CRM Customers" in customer_groups.values():
        _delete_address_shares((doc.name,))
        if not _trusted_address_service_write(doc):
            frappe.throw(
                "CRM Address records can only be changed through the site service.",
                frappe.PermissionError,
            )


def revoke_customer_address_shares_entering_crm(doc, method: str | None = None) -> None:
    """Atomically revoke every ERP share when a Customer enters CRM scope."""

    del method
    if doc.get("customer_group") != "CRM Customers" or doc.is_new():
        return
    current = frappe.db.sql(
        "SELECT `customer_group` FROM `tabCustomer` WHERE `name` = %s FOR UPDATE",
        (doc.name,),
    )
    if not current or current[0][0] == "CRM Customers":
        return
    # Every linked record is locked (or the promotion aborts) before any share is
    # deleted, so no record can keep an ERP share once this promotion commits.
    address_names = sorted(set(_lock_transition_targets(
        "Address", _CUSTOMER_LINKED_PARENTS_QUERY, ("Address", doc.name),
    )))
    contact_names = sorted(set(_lock_transition_targets(
        "Contact", _CUSTOMER_LINKED_PARENTS_QUERY, ("Contact", doc.name),
    )))
    lead_names = sorted(set(_lock_transition_targets(
        "Lead", _CUSTOMER_CONVERTED_LEAD_QUERY, (doc.name,),
    )))
    _delete_docshares("Customer", (doc.name,))
    _delete_address_shares(tuple(address_names))
    _delete_docshares("Contact", contact_names)
    _delete_docshares("Lead", lead_names)
    if not _trusted_standard_service_write(doc):
        frappe.throw(
            "CRM Customer records can only be changed through the account service.",
            frappe.PermissionError,
        )


def revoke_contact_shares_entering_crm(doc, method: str | None = None) -> None:
    """Serialize Contact reparenting and remove obsolete ERP shares."""

    del method
    customer_groups = _lock_customer_groups(
        _linked_customer_names("Contact", getattr(doc, "name", None), doc=doc),
    )
    if "CRM Customers" in customer_groups.values():
        _delete_docshares("Contact", (doc.name,))
        if not _trusted_standard_service_write(doc):
            frappe.throw(
                "CRM Contact records can only be changed through the contact service.",
                frappe.PermissionError,
            )


def revoke_lead_shares_entering_crm(doc, method: str | None = None) -> None:
    """Serialize Lead scope changes and remove obsolete ERP shares."""

    del method
    current = None
    if not doc.is_new():
        current = frappe.db.get_value(
            "Lead", doc.name,
            ["lead_owner", "custom_crm_converted_account"], as_dict=True,
        )
    owners = tuple(filter(None, (
        doc.get("lead_owner"), current.lead_owner if current else None,
    )))
    crm_users = _lock_user_crm_roles(owners)
    customer_groups = _lock_customer_groups(tuple(sorted(set(filter(None, (
        doc.get("custom_crm_converted_account"),
        current.custom_crm_converted_account if current else None,
    ))))))
    if crm_users or "CRM Customers" in customer_groups.values():
        _delete_docshares("Lead", (doc.name,))
        if not _trusted_standard_service_write(doc):
            frappe.throw(
                "CRM Lead records can only be changed through the lead service.",
                frappe.PermissionError,
            )


def revoke_shares_when_user_enters_crm(doc, method: str | None = None) -> None:
    """Keep shares created before a role assignment from overriding CRM scope."""

    del method
    if not {row.role for row in (doc.get("roles") or ())}.intersection(CRM_ROLE_TO_PROFILE):
        return
    if not doc.is_new():
        frappe.db.sql("SELECT `name` FROM `tabUser` WHERE `name` = %s FOR UPDATE", (doc.name,))
    frappe.db.sql(
        "DELETE `crm_share` FROM `tabDocShare` AS `crm_share` "
        "LEFT JOIN `tabDocType` AS `crm_doctype` "
        "ON `crm_doctype`.`name` = `crm_share`.`share_doctype` "
        "WHERE `crm_share`.`user` = %s AND ("
        "`crm_share`.`share_doctype` IN ('Customer', 'Contact', 'Lead') "
        "OR `crm_doctype`.`module` = 'Rayher CRM')",
        (doc.name,),
    )
    # A user who already held a CRM role had these Lead shares revoked on entry,
    # and share checks reject new ones since; only a real entry takes the NOWAIT
    # locks, so later saves of the user never fail on a Lead being edited.
    previous = None if doc.is_new() else doc.get_doc_before_save()
    if previous is not None and {
        row.role for row in (previous.get("roles") or ())
    }.intersection(CRM_ROLE_TO_PROFILE):
        return
    lead_names = _lock_transition_targets("Lead", _OWNED_LEADS_QUERY, (doc.name,))
    _delete_docshares("Lead", lead_names)


def protect_crm_customer_group_name(doc, method, old, new, merge) -> None:
    """Keep the reserved group stable across native rename and merge operations."""

    del method, merge
    # Frappe loads the source by database identity before calling this hook.
    # MariaDB's case/accent-insensitive collation can resolve a supplied alias
    # to the reserved row even when Python's casefold comparison misses it.
    reserved = frappe.db.exists("Customer Group", "CRM Customers")
    target = frappe.db.exists("Customer Group", new)
    if (
        (reserved and (doc.name == reserved or target == reserved))
        or any(str(name).strip().casefold() == "crm customers" for name in (old, new))
    ):
        frappe.throw(
            "CRM Customers is reserved and cannot be renamed or merged.",
            frappe.PermissionError,
        )


def protect_standard_crm_merge(doc, method, old, new, merge) -> None:
    """Do not carry ERP shares across a native Customer/Contact/Address/Lead merge."""

    del method, old
    if not merge:
        return
    doctype = doc.doctype
    if doctype not in {"Customer", "Contact", "Address", "Lead"}:
        raise ValueError(f"Unsupported CRM merge guard: {doctype}")
    fields = {
        "Customer": "`name`, `customer_group`",
        "Contact": "`name`",
        "Address": "`name`",
        "Lead": "`name`, `lead_owner`, `custom_crm_converted_account`",
    }
    try:
        # A locking read sees rows committed after this transaction's ordinary
        # REPEATABLE READ snapshot. ORDER BY gives both merge directions the
        # same parent-lock order; NOWAIT aborts a competing save/share instead
        # of introducing a reverse wait against its User/Customer locks.
        locked = frappe.db.sql(
            f"SELECT {fields[doctype]} FROM `tab{doctype}` "
            "WHERE `name` IN (%s, %s) ORDER BY `name` FOR UPDATE NOWAIT",
            (doc.name, new), as_dict=True,
        )
        if len(locked) != 2:
            # Frappe's validate_rename reports a missing or identical target.
            return
        rows = {row.name: row for row in locked}
        target_name = next(name for name in rows if name != doc.name)
        names = tuple(sorted(rows))
        # DocShare creation takes its target first; keep that order, then take
        # related User/Customer locks with NOWAIT as promotion hooks do.
        if doctype == "Customer":
            groups = {name: rows[name].customer_group for name in names}
        elif doctype in {"Contact", "Address"}:
            links = {
                name: _locked_linked_customer_names(doctype, name, nowait=True)
                for name in names
            }
            customer_names = tuple(sorted({customer for linked in links.values() for customer in linked}))
            groups = _lock_customer_groups(customer_names, nowait=True)
            if any(customer not in groups for customer in customer_names):
                frappe.throw(
                    "A linked Customer requires review before these records can be merged.",
                    frappe.PermissionError,
                )
        else:
            owners = tuple(sorted({rows[name].lead_owner for name in names if rows[name].lead_owner}))
            crm_users = _lock_user_crm_roles(owners, nowait=True)
            customer_names = tuple(sorted({
                rows[name].custom_crm_converted_account for name in names
                if rows[name].custom_crm_converted_account
            }))
            groups = _lock_customer_groups(customer_names, nowait=True)
            if any(customer not in groups for customer in customer_names):
                frappe.throw(
                    "A converted Customer requires review before these Leads can be merged.",
                    frappe.PermissionError,
                )
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw("A merge boundary is being changed. Please retry.", frappe.PermissionError)

    reserved = frappe.db.exists("Customer Group", "CRM Customers")

    def is_crm_group(group_name: str | None) -> bool:
        return bool(group_name and reserved and frappe.db.exists("Customer Group", group_name) == reserved)

    if doctype == "Customer":
        boundaries = {name: is_crm_group(groups[name]) for name in names}
    elif doctype in {"Contact", "Address"}:
        boundaries = {
            name: any(is_crm_group(groups[customer]) for customer in links[name])
            for name in names
        }
    else:
        boundaries = {
            name: rows[name].lead_owner in crm_users
            or is_crm_group(groups.get(rows[name].custom_crm_converted_account))
            for name in names
        }
    if boundaries[doc.name] != boundaries[target_name]:
        frappe.throw(
            f"{doctype} records cannot be merged across the CRM boundary.",
            frappe.PermissionError,
        )


def reconcile_shares_after_user_rename(doc, method, old, new, merge) -> None:
    """Reconcile bulk Link rewrites before a User rename or merge commits."""

    del method, old, merge
    # Frappe loads the surviving user after rewriting DocShare.user and
    # Lead.lead_owner. Reload explicitly so a previous-save snapshot cannot
    # suppress cleanup of Leads that have just entered CRM ownership.
    revoke_shares_when_user_enters_crm(frappe.get_doc("User", new))


def _is_rayher_crm_doctype(doctype: str | None) -> bool:
    return bool(
        doctype
        and frappe.db.get_value("DocType", doctype, "module") == "Rayher CRM"
    )


def _lock_docshare_target(doctype: str, name: str):
    fields = {
        "Address": "`name`",
        "Contact": "`name`",
        "Customer": "`name`, `customer_group`",
        "Lead": "`name`, `lead_owner`, `custom_crm_converted_account`",
    }
    if doctype not in fields:
        raise ValueError(f"Unsupported shared target: {doctype}")
    rows = frappe.db.sql(
        f"SELECT {fields[doctype]} FROM `tab{doctype}` "
        "WHERE `name` = %s FOR UPDATE SKIP LOCKED",
        (name,),
        as_dict=True,
    )
    if not rows:
        frappe.throw(
            f"{doctype} changed while its sharing boundary was checked. Please retry.",
            frappe.PermissionError,
        )
    return rows[0]


def _locked_linked_customer_names(
    parenttype: str, name: str, *, nowait: bool = False,
) -> tuple[str, ...]:
    return tuple(sorted(set(frappe.db.sql_list(
        "SELECT `link_name` FROM `tabDynamic Link` "
        "WHERE `parent` = %s AND `parenttype` = %s "
        "AND `parentfield` = 'links' AND `link_doctype` = 'Customer' "
        "ORDER BY `link_name`, `name` FOR UPDATE" + (" NOWAIT" if nowait else ""),
        (name, parenttype),
    ))))


def _standard_docshare_is_blocked(doc) -> bool:
    """Preserve ERP sharing without letting it override a CRM boundary."""

    if doc.share_doctype not in SHARED_STANDARD_DOCTYPES:
        return False
    target = _lock_docshare_target(doc.share_doctype, doc.share_name)
    users = [doc.get("user")]
    if doc.share_doctype == "Lead":
        users.append(target.get("lead_owner"))
    crm_users = _lock_user_crm_roles(users)
    if frappe.utils.cint(doc.get("everyone")) or doc.get("user") in crm_users:
        return True
    if doc.share_doctype == "Lead":
        customer_groups = _lock_customer_groups(tuple(filter(None, (
            target.get("custom_crm_converted_account"),
        ))))
        return (
            target.get("lead_owner") in crm_users
            or "CRM Customers" in customer_groups.values()
        )
    if doc.share_doctype == "Customer":
        return target.customer_group == "CRM Customers"
    else:
        customer_names = _locked_linked_customer_names("Contact", doc.share_name)
    customer_groups = _lock_customer_groups(customer_names)
    return "CRM Customers" in customer_groups.values()


def prevent_scoped_docshare(doc, method: str | None = None) -> None:
    """Keep explicit shares from overriding CRM parent and site scope."""

    del method
    blocked = _is_rayher_crm_doctype(doc.share_doctype) or _standard_docshare_is_blocked(doc)
    if doc.share_doctype == "Address":
        # Share creation follows the same target -> Customer order as Address
        # save. A concurrent save is rejected immediately instead of reading its
        # old ERP snapshot and inserting a share after the save's cleanup hook.
        _lock_docshare_target("Address", doc.share_name)
        customer_names = _locked_linked_customer_names("Address", doc.share_name)
        customer_groups = _lock_customer_groups(customer_names)
        blocked = (
            "CRM Customers" in customer_groups.values()
            or len(customer_groups) < len(customer_names)
        )
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
    *,
    for_bound_query: bool = False,
) -> str:
    """Correlate a native child-record query with the parent's current row scope."""

    if not frappe.has_permission(parent_doctype, "read", user=user):
        return "1=0"

    class ParentScopeQuery(DatabaseQuery):
        def get_permission_query_conditions(self) -> str:
            # Keep Frappe's native owner/User Permission/share fragment separate
            # from the CRM condition. Frappe escapes percent signs differently;
            # only the native fragment needs doubling in a bound SQL query.
            return ""

    parent_query = ParentScopeQuery(parent_doctype, user=user)
    parent_query.reference_doctype = parent_doctype
    try:
        match_scope = parent_query.build_match_conditions()
    except frappe.PermissionError:
        return "1=0"
    # Frappe may store share restrictions on conditions rather than returning
    # them. Keep the CRM service scope even when that share-only path is used.
    native_parts = [condition for condition in parent_query.conditions if condition]
    native_parts.append(match_scope)
    if for_bound_query:
        native_parts = [condition.replace("%", "%%") for condition in native_parts if condition]
    scope_parts = [
        *native_parts,
        conditions_for_doctype(parent_doctype, user, for_bound_query=for_bound_query),
    ]
    parent_scope = " AND ".join(
        f"({condition})" for condition in dict.fromkeys(scope_parts) if condition
    )
    if not parent_scope:
        return "1=0"
    return (
        f"EXISTS (SELECT 1 FROM `tab{parent_doctype}` "
        f"WHERE `tab{parent_doctype}`.`name` = `tab{child_doctype}`.`{parent_field}` "
        f"AND ({parent_scope}))"
    )


def _native_parent_scope_condition(
    child_doctype: str,
    parent_doctype: str,
    parent_field: str,
    user: str,
) -> str | None:
    """Correlate a child-table list with the parent's complete native row scope."""

    # ``build_match_conditions`` assumes its caller already performed the
    # DocType-level read check. Without it, a User Permission on a parent the
    # user cannot read can bypass the share-only branch and leave it unscoped.
    if not (
        frappe.has_permission(parent_doctype, "read", user=user)
        or frappe.has_permission(parent_doctype, "select", user=user)
    ):
        return None
    parent_query = DatabaseQuery(parent_doctype, user=user)
    # This is a direct parent scope, so parent-specific User Permissions must
    # be evaluated with the parent as their reference DocType.
    parent_query.reference_doctype = parent_doctype
    try:
        match_scope = parent_query.build_match_conditions()
    except frappe.PermissionError:
        return None
    # In Frappe 15 the share-only branch stores its restriction directly on
    # ``conditions`` and may return an empty match string. Both sources are
    # required; treating that empty return as unrestricted exposes every child
    # of the same parent type to a user who was shared only one parent.
    scope_parts = [condition for condition in parent_query.conditions if condition]
    if match_scope:
        scope_parts.append(match_scope)
    scoped = "".join(f" AND ({condition})" for condition in dict.fromkeys(scope_parts))
    return (
        f"(`tab{child_doctype}`.`parenttype` = {frappe.db.escape(parent_doctype)} "
        f"AND `tab{child_doctype}`.`parentfield` = {frappe.db.escape(parent_field)} "
        f"AND EXISTS (SELECT 1 FROM `tab{parent_doctype}` "
        f"WHERE `tab{parent_doctype}`.`name` = `tab{child_doctype}`.`parent`{scoped}))"
    )


def scoped_child_query(user: str | None = None, doctype: str | None = None) -> str:
    """Apply each supported parent's native row scope to direct child-table lists."""

    if doctype not in SCOPED_CHILD_RELATIONSHIPS:
        raise ValueError(f"Unsupported scoped child DocType: {doctype}")
    resolved_user = user or getattr(frappe.session, "user", None)
    if not resolved_user or resolved_user == "Guest":
        return "1=0"
    if resolved_user == "Administrator":
        return ""
    branches = tuple(filter(None, (
        _native_parent_scope_condition(
            doctype,
            parent_doctype,
            parent_field,
            resolved_user,
        )
        for parent_doctype, parent_field in SCOPED_CHILD_RELATIONSHIPS[doctype]
    )))
    return f"({' OR '.join(branches)})" if branches else "1=0"


def conditions_for_doctype(
    doctype: str, user: str | None = None, *, for_bound_query: bool = False,
) -> str:
    """Return CRM row scope; escape native match fragments for bound SQL when requested.

    Native Frappe lists interpolate no query values, so the default preserves raw
    percent signs. A caller that passes values to ``frappe.db.sql`` opts in.
    """
    if doctype not in CONDITION_DOCTYPES:
        raise ValueError(f"Unsupported scoped DocType: {doctype}")

    if doctype in SCOPED_CHILD_RELATIONSHIPS:
        return scoped_child_query(user, doctype=doctype)

    resolved_user = user or getattr(frappe.session, "user", None)
    role = _role_for_query(resolved_user)
    if not role or not resolved_user:
        return "1=0"
    if doctype == "CRM Notification Event":
        from rayher_crm.permissions.notification_scope import notification_condition
        return notification_condition(resolved_user, for_bound_query=for_bound_query)
    if doctype == "CRM Opportunity Stakeholder" and role == "Engineer":
        return "1=0"
    if doctype in OPPORTUNITY_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(
            doctype, "CRM Opportunity", "opportunity", resolved_user,
            for_bound_query=for_bound_query,
        )
    if doctype in DEMO_REQUEST_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(
            doctype, "CRM Demo Request", "demo_request", resolved_user,
            for_bound_query=for_bound_query,
        )
    if doctype in EVALUATION_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(
            doctype, "CRM Evaluation", "evaluation", resolved_user,
            for_bound_query=for_bound_query,
        )
    if doctype in INSTALLED_TOOL_SCOPED_CHILD_DOCTYPES:
        return _parent_scope_condition(
            doctype, "CRM Installed Tool", "installed_tool", resolved_user,
            for_bound_query=for_bound_query,
        )
    if doctype == "Address":
        escaped_user = frappe.db.escape(resolved_user)
        # Address links Customers through its Dynamic Link child table. Frappe's
        # DBQuery only applies User Permissions from Link fields on the Address
        # parent itself, so Customer restrictions would otherwise disappear from
        # native Address lists and detail endpoints. Build the Customer's native
        # row scope explicitly, including owner/User Permission/share matching.
        class AddressCustomerQuery(DatabaseQuery):
            def get_permission_query_conditions(self) -> str:
                return ""

        customer_query = AddressCustomerQuery("Customer", user=resolved_user)
        # A Customer User Permission may be scoped specifically to Address.
        # DatabaseQuery.execute normally supplies this reference doctype; this
        # nested permission build must do the same explicitly.
        customer_query.reference_doctype = "Address"
        try:
            native_match = customer_query.build_match_conditions()
        except frappe.PermissionError:
            return "1=0"
        native_parts = [condition for condition in customer_query.conditions if condition]
        native_parts.append(native_match)
        if for_bound_query:
            native_parts = [condition.replace("%", "%%") for condition in native_parts if condition]
        # Preserve installed Customer query hooks separately from Frappe's raw
        # native match fragments. Hook predicates already follow db.escape's
        # escaped-percent convention and must not be escaped a second time.
        customer_parts = [
            *native_parts,
            DatabaseQuery.get_permission_query_conditions(customer_query),
        ]
        customer_scope = " AND ".join(
            f"({condition})" for condition in dict.fromkeys(customer_parts) if condition
        )
        if not customer_scope:
            return "1=0"
        if role == "Sales":
            # Public Accounts may be returned through redacted CRM DTOs, while the
            # native Address document exposes the complete site address.
            customer_scope = (
                f"({customer_scope}) AND `tabCustomer`.`custom_crm_owner` = {escaped_user}"
            )
        return (
            "EXISTS (SELECT 1 FROM `tabDynamic Link` AS `crm_link` "
            "INNER JOIN `tabCustomer` ON `tabCustomer`.`name` = `crm_link`.`link_name` "
            "WHERE `crm_link`.`parent` = `tabAddress`.`name` "
            "AND `crm_link`.`parenttype` = 'Address' AND `crm_link`.`parentfield` = 'links' "
            "AND `crm_link`.`link_doctype` = 'Customer' "
            "AND `tabCustomer`.`customer_group` = 'CRM Customers' "
            f"AND ({customer_scope}))"
        )
    if doctype == "CRM Visit Meeting Record":
        return _parent_scope_condition(
            doctype, "CRM Visit", "visit", resolved_user,
            for_bound_query=for_bound_query,
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
        if doctype == "CRM Quotation Approval":
            return _parent_scope_condition(
                doctype, "CRM Quotation", "quotation", resolved_user,
                for_bound_query=for_bound_query,
            )
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
        return (
            "EXISTS (SELECT 1 FROM `tabCRM Quotation` AS `crm_quotation` "
            "WHERE `crm_quotation`.`name` = `tabCRM Quotation Version`.`quotation` "
            f"AND ({quotation_scope}))"
        )
    if doctype in {"CRM RFQ", "CRM RFQ Version"}:
        if doctype == "CRM RFQ Version":
            return _parent_scope_condition(
                doctype, "CRM RFQ", "rfq", resolved_user,
                for_bound_query=for_bound_query,
            )
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
    if doctype == "CRM Contact File":
        escaped_user = frappe.db.escape(resolved_user)
        customer_scope = (
            f"`crm_customer`.`custom_crm_owner` = {escaped_user}"
            if role == "Sales"
            else _customer_condition("`crm_customer`", role, escaped_user)
        )
        return (
            "`tabCRM Contact File`.`deleted` = 0 AND EXISTS ("
            "SELECT 1 FROM `tabContact` AS c "
            "JOIN `tabDynamic Link` AS l ON l.parent=c.name AND l.parenttype='Contact' "
            "AND l.parentfield='links' AND l.link_doctype='Customer' "
            "JOIN `tabCustomer` AS `crm_customer` ON `crm_customer`.name=l.link_name "
            "WHERE c.name=`tabCRM Contact File`.`contact` "
            "AND `crm_customer`.name=`tabCRM Contact File`.`account` "
            f"AND ({customer_scope}))"
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
        return ""
    role, ambiguous = _address_crm_identity(resolved_user)
    if not role and not ambiguous:
        return ""
    erp_read_scope = _erp_address_read_scope(
        resolved_user, for_link_search=_ADDRESS_LINK_USER.get() == resolved_user,
        warehouse_lookup=_WAREHOUSE_LINK_USER.get() == resolved_user,
    )
    crm_boundary = _protected_address_exists_condition("`tabAddress`.`name`")
    if erp_read_scope == "all":
        erp_scope = f"NOT ({crm_boundary})"
    elif erp_read_scope == "owner":
        from frappe.share import get_shared

        escaped_user = frappe.db.escape(resolved_user, percent=False)
        native_scope = f"`tabAddress`.`owner` = {escaped_user}"
        # Core still honors existing read shares when new sharing is disabled.
        shared = get_shared("Address", user=resolved_user, rights=["read"])
        if shared:
            names = ", ".join(frappe.db.escape(name, percent=False) for name in sorted(set(shared)))
            native_scope = f"({native_scope} OR `tabAddress`.`name` IN ({names}))"
        erp_scope = f"(NOT ({crm_boundary}) AND ({native_scope}))"
    else:
        erp_scope = ""
    if ambiguous:
        return erp_scope or "1=0"
    crm_scope = conditions_for_doctype("Address", resolved_user)
    if erp_scope:
        return f"(({erp_scope}) OR ({crm_scope}))"
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

    condition = conditions_for_doctype(doc.doctype, resolved_user, for_bound_query=True)
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
    normalized_permission = permission_type or ptype or "read"
    if normalized_permission in MUTATING_PERMISSIONS and resolved_user != "Administrator":
        # A normal SELECT under REPEATABLE READ can keep classifying an Address as
        # ERP after a concurrent Customer promotion commits. The locking read is
        # current and holds every linked Customer until this mutation finishes, so
        # a native Address write and a CRM promotion cannot cross the boundary.
        # This is also the only native delete guard: Frappe 15 raises no
        # before_delete event, and delete_doc runs this "delete" check for every
        # caller except Administrator and ignore_permissions services.
        customer_names = set(_address_customer_names(None, doc=doc))
        if not doc.is_new():
            _lock_address(getattr(doc, "name", None))
            # Locking the Address does not refresh a previously loaded links
            # snapshot. Read persisted links with a current read as well as
            # retaining the proposed links used for create/write checks.
            customer_names.update(_locked_linked_customer_names("Address", doc.name))
        customer_groups = _lock_customer_groups(tuple(sorted(customer_names)))
        if (
            "CRM Customers" in customer_groups.values()
            or len(customer_groups) < len(customer_names)
        ):
            return False
        is_crm_address = False
        protected = False
    else:
        is_crm_address = _is_crm_customer_address(getattr(doc, "name", None), doc=doc)
        protected = is_crm_address or _has_orphan_customer_link(getattr(doc, "name", None))
    if not role and not ambiguous:
        return None
    if not protected:
        if normalized_permission == "read":
            erp_read_scope = _erp_address_read_scope(resolved_user)
            if erp_read_scope == "all":
                return None
            if erp_read_scope == "owner" and getattr(doc, "owner", None) == resolved_user:
                return None
            return False
        return None if _has_explicit_erp_address_permission(
            resolved_user, normalized_permission,
        ) else False
    if not is_crm_address:
        return False
    if ambiguous:
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
