"""SQL-backed row scope shared by CRM list and detail permission checks."""

from __future__ import annotations

import frappe
from frappe.permissions import add_permission, update_permission_property

from rayher_crm.permissions.roles import capabilities_for_role, resolve_crm_role


SCOPED_DOCTYPES = (
    "Customer", "Contact", "Lead", "CRM Opportunity", "CRM Booking", "CRM Installed Tool",
    "CRM Demo Request", "CRM Evaluation", "CRM Visit",
    "CRM Contact File", "CRM Demo Artifact", "CRM Notification Event",
    "CRM Quotation", "CRM Quotation Version", "CRM Quotation Approval",
    "CRM RFQ", "CRM RFQ Version",
)
ROLE_DOCPERMS = {
    "CRM Manager": {"read", "write", "create", "delete", "report", "export", "print", "email", "share"},
    "CRM Sales": {"read", "write", "create", "report", "export", "print", "email"},
    "CRM Engineer": {"read", "report", "export", "print"},
}
INSTALLED_TOOL_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": {"read", "report", "export", "print"},
    "CRM Engineer": {"read", "write", "report", "export", "print"},
}
DEMO_REQUEST_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": {"read", "write", "create", "report", "export", "print", "email"},
    "CRM Engineer": {"read", "report", "export", "print"},
}
EVALUATION_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": {"read", "report", "export", "print"},
    "CRM Engineer": {"read", "write", "report", "export", "print"},
}
VISIT_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": {"read", "write", "create", "report", "export", "print", "email"},
    "CRM Engineer": set(),
}
CONTACT_FILE_DOCPERMS = {
    "CRM Manager": {"read", "write", "create", "report", "export"},
    "CRM Sales": {"read", "write", "create", "report", "export"},
    "CRM Engineer": {"read", "report", "export"},
}
ARTIFACT_DOCPERMS = {
    "CRM Manager": {"read", "create", "report", "export"},
    "CRM Sales": {"read", "create", "report", "export"},
    "CRM Engineer": {"read", "report", "export"},
}
NOTIFICATION_DOCPERMS = {
    "CRM Manager": {"read"},
    "CRM Sales": {"read"},
    "CRM Engineer": {"read"},
}
QUOTATION_DOCPERMS = {
    "CRM Manager": ROLE_DOCPERMS["CRM Manager"],
    "CRM Sales": {"read", "write", "create", "report", "export", "print", "email"},
}
PERMISSION_FIELDS = ("read", "write", "create", "delete", "report", "export", "print", "email", "share")
ROLE_TO_SERVER_ROLE = {"Manager": "CRM Manager", "Sales": "CRM Sales", "Engineer": "CRM Engineer"}
DOCTYPES_TO_VIEW_CAPABILITY = {
    "Customer": "account:view", "Contact": "contact:view", "Lead": "requirement:view",
    "CRM Opportunity": "deal:view", "CRM Booking": "deal:view", "CRM Installed Tool": "service:view",
    "CRM Demo Request": "demo_request:view", "CRM Evaluation": "evaluation:view", "CRM Visit": "visit:view",
    "CRM Contact File": "stakeholder:view", "CRM Demo Artifact": "demo_request:view",
    "CRM Notification Event": "dashboard:view", "CRM Quotation": "quotation:view",
    "CRM Quotation Version": "quotation:view", "CRM Quotation Approval": "quotation:view",
    "CRM RFQ": "rfq:view", "CRM RFQ Version": "rfq:view",
}


def _permissions_for_doctype(doctype: str, role: str) -> set[str]:
    permissions = {
        "CRM Installed Tool": INSTALLED_TOOL_DOCPERMS,
        "CRM Demo Request": DEMO_REQUEST_DOCPERMS,
        "CRM Evaluation": EVALUATION_DOCPERMS,
        "CRM Visit": VISIT_DOCPERMS,
        "CRM Contact File": CONTACT_FILE_DOCPERMS,
        "CRM Demo Artifact": ARTIFACT_DOCPERMS,
        "CRM Notification Event": NOTIFICATION_DOCPERMS,
        "CRM Quotation": QUOTATION_DOCPERMS,
        "CRM Quotation Version": QUOTATION_DOCPERMS,
        "CRM Quotation Approval": {
            "CRM Manager": {"read"}, "CRM Sales": {"read"}, "CRM Engineer": set(),
        },
        "CRM RFQ": {
            "CRM Manager": {"read", "report", "export"},
            "CRM Sales": {"read", "create", "report", "export"},
            "CRM Engineer": {"read", "report", "export"},
        },
        "CRM RFQ Version": {
            "CRM Manager": {"read", "report", "export"},
            "CRM Sales": {"read", "report", "export"},
            "CRM Engineer": {"read", "report", "export"},
        },
    }.get(doctype, ROLE_DOCPERMS)
    return set(permissions.get(ROLE_TO_SERVER_ROLE[role], set()))


def install_crm_doc_permissions() -> None:
    """Install explicit DocPerm rows so standard ERPNext roles do not mask CRM scope."""

    for doctype in SCOPED_DOCTYPES:
        permissions = {
            "CRM Installed Tool": INSTALLED_TOOL_DOCPERMS,
            "CRM Demo Request": DEMO_REQUEST_DOCPERMS,
            "CRM Evaluation": EVALUATION_DOCPERMS,
            "CRM Visit": VISIT_DOCPERMS,
            "CRM Contact File": CONTACT_FILE_DOCPERMS,
            "CRM Demo Artifact": ARTIFACT_DOCPERMS,
            "CRM Notification Event": NOTIFICATION_DOCPERMS,
            "CRM Quotation": QUOTATION_DOCPERMS,
            "CRM Quotation Version": QUOTATION_DOCPERMS,
            "CRM Quotation Approval": {
                "CRM Manager": {"read"},
                "CRM Sales": {"read"},
                "CRM Engineer": set(),
            },
            "CRM RFQ": {
                "CRM Manager": {"read", "report", "export"},
                "CRM Sales": {"read", "create", "report", "export"},
                "CRM Engineer": {"read", "report", "export"},
            },
            "CRM RFQ Version": {
                "CRM Manager": {"read", "report", "export"},
                "CRM Sales": {"read", "report", "export"},
                "CRM Engineer": {"read", "report", "export"},
            },
        }.get(doctype, ROLE_DOCPERMS)
        for role, allowed in permissions.items():
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


def conditions_for_doctype(doctype: str, user: str | None = None) -> str:
    if doctype not in SCOPED_DOCTYPES:
        raise ValueError(f"Unsupported scoped DocType: {doctype}")

    resolved_user = user or getattr(frappe.session, "user", None)
    role = _role_for_query(resolved_user)
    if not role or not resolved_user:
        return "1=0"
    if doctype == "CRM Notification Event":
        return f"`tabCRM Notification Event`.`recipient_user` = {frappe.db.escape(resolved_user)}"
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


def contact_file_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Contact File", user)


def demo_artifact_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Demo Artifact", user)


def notification_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Notification Event", user)


def visit_query(user: str | None = None) -> str:
    return conditions_for_doctype("CRM Visit", user)


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


def has_crm_permission(doc, user: str | None = None, permission_type: str | None = None) -> bool:
    resolved_user = user or getattr(frappe.session, "user", None)
    if not resolved_user or resolved_user == "Guest":
        return False
    role = _role_for_query(resolved_user)
    if not role:
        return False
    view_capability = DOCTYPES_TO_VIEW_CAPABILITY.get(doc.doctype)
    if view_capability and view_capability not in capabilities_for_role(role):
        return False
    if permission_type and permission_type not in _permissions_for_doctype(doc.doctype, role):
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
    if doc.doctype == "Contact":
        rows = frappe.db.sql(
            "SELECT 1 FROM `tabDynamic Link` AS `crm_owned_link` "
            "INNER JOIN `tabCustomer` AS `crm_owned_customer` "
            "ON `crm_owned_customer`.`name` = `crm_owned_link`.`link_name` "
            "WHERE `crm_owned_link`.`parent` = %s "
            "AND `crm_owned_link`.`parenttype` = 'Contact' "
            "AND `crm_owned_link`.`parentfield` = 'links' "
            "AND `crm_owned_link`.`link_doctype` = 'Customer' "
            "AND `crm_owned_customer`.`custom_crm_owner` = %s LIMIT 1",
            (doc.name, resolved_user),
        )
        return bool(rows)
    account_id = frappe.db.get_value(doc.doctype, doc.name, "account")
    return bool(
        account_id
        and frappe.db.get_value("Customer", account_id, "custom_crm_owner") == resolved_user
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
