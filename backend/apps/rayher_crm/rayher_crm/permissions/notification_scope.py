"""An inbox copy follows the recipient's current permission on its source."""
import frappe
from frappe.model.db_query import DatabaseQuery

from rayher_crm.permissions.roles import capabilities_for_user, resolve_crm_role


# Only server-owned notification sources. In particular, Notification Event is
# not a source: recursively authorizing inbox copies would be unsafe.
SOURCE_DOCTYPES = (
    "Customer", "Contact", "Lead", "CRM Opportunity", "CRM Booking",
    "CRM Demo Comment", "CRM Demo Request", "CRM Evaluation", "CRM Installed Tool",
    "CRM Installed Tool Service History", "CRM Opportunity Action",
    "CRM Opportunity Internal Validation", "CRM Opportunity Probability History",
    "CRM Opportunity Stage History", "CRM Probability Recovery Revision",
    "CRM Quotation", "CRM Quotation Version", "CRM RFQ", "CRM Visit",
    "CRM Document Access Request", "CRM Document Upload Request",
)


def source_condition(doctype: str, user: str, *, for_bound_query: bool = False) -> str:
    """Build source scope for native no-values SQL or an explicitly bound query."""
    from rayher_crm.permissions.scope import DOCTYPES_TO_VIEW_CAPABILITY, conditions_for_doctype
    if doctype not in SOURCE_DOCTYPES:
        return "1=0"
    try:
        role = resolve_crm_role(user)
        capabilities = capabilities_for_user(user)
    except frappe.PermissionError:
        return "1=0"
    if doctype == "CRM Document Upload Request":
        # Submitters read their own approval result through the service, even
        # though the native approval workspace belongs to Managers.
        return "1=1" if role == "Manager" else (
            f"`tab{doctype}`.`submitted_by`={frappe.db.escape(user, percent=for_bound_query)}"
        )
    if DOCTYPES_TO_VIEW_CAPABILITY[doctype] not in capabilities:
        return "1=0"
    if not frappe.has_permission(doctype, "read", user=user):
        return "1=0"
    class ServiceScopeQuery(DatabaseQuery):
        def get_permission_query_conditions(self):
            # Keep Frappe's percent=False native match fragment separate from
            # the CRM predicate, which uses the default escaped-percent form.
            return ""

    # Reuse the CRM service predicate while retaining Frappe's User Permission
    # and share matching. Some native hooks intentionally require Account
    # ownership for raw site data and are stricter than the service DTO scope.
    try:
        query = ServiceScopeQuery(doctype, user=user)
        query.reference_doctype = doctype
        match_scope = query.build_match_conditions()
    except frappe.PermissionError:
        return "1=0"
    native_parts = [condition for condition in query.conditions if condition]
    native_parts.append(match_scope)
    if for_bound_query:
        native_parts = [condition.replace("%", "%%") for condition in native_parts if condition]
    # CRM predicates use escaped-percent literals, and child predicates can
    # also contain native parent fragments prepared for bound SQL. Native
    # Frappe lists pass no values, so collapse that complete predicate once.
    crm_scope = conditions_for_doctype(doctype, user, for_bound_query=True)
    if not for_bound_query:
        crm_scope = crm_scope.replace("%%", "%")
    scope_parts = [
        *native_parts,
        crm_scope,
    ]
    return " AND ".join(
        f"({condition})" for condition in dict.fromkeys(scope_parts) if condition
    ) or "1=0"


def can_read_source(doctype: str, name: str, user: str) -> bool:
    if doctype not in SOURCE_DOCTYPES or not name:
        return False
    condition = source_condition(doctype, user, for_bound_query=True)
    return bool(frappe.db.sql(
        f"SELECT name FROM `tab{doctype}` WHERE name=%s AND ({condition}) LIMIT 1", (name,),
    ))


def notification_condition(user: str, *, for_bound_query: bool = False) -> str:
    """Require both the inbox recipient and current permission on its source."""
    if not frappe.db.get_value("User", user, "enabled"):
        return "1=0"
    cases = []
    for doctype in SOURCE_DOCTYPES:
        condition = source_condition(doctype, user, for_bound_query=for_bound_query)
        if condition == "1=0":
            continue
        cases.append(
            f"WHEN {frappe.db.escape(doctype, percent=for_bound_query)} THEN EXISTS ("
            f"SELECT 1 FROM `tab{doctype}` WHERE `tab{doctype}`.`name`="
            f"`tabCRM Notification Event`.`source_name` AND ({condition}))"
        )
    source_scope = (
        "CASE `tabCRM Notification Event`.`source_doctype` "
        + " ".join(cases)
        + " ELSE 0 END"
    ) if cases else "1=0"
    escaped_user = frappe.db.escape(user, percent=for_bound_query)
    return f"(`tabCRM Notification Event`.`recipient_user`={escaped_user} AND ({source_scope}))"
