"""Release-time inventory of native entry points, not a second authorization engine.

The services and scope hooks still make decisions. This inventory makes a new
DocType, missing hook or broader installed grant an explicit review decision.
Administrator remains Frappe's superuser; CRM Manager is an ordinary CRM role.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path


APP_ROOT = Path(__file__).parents[1]
APP_MODULE = "Rayher CRM"
CRM_ROLES = ("CRM Manager", "CRM Sales", "CRM Engineer")
PERMISSIONS = (
    "select", "read", "write", "create", "delete", "submit", "cancel", "amend", "import",
    "report", "export", "print", "email", "share",
)
NATIVE_MUTATIONS = frozenset({"write", "create", "delete", "submit", "cancel", "amend", "import"})
IMPLICIT_READ_BITS = frozenset({"select", "read", "report", "export", "print", "email", "share"})
# frappe.permissions.get_roles gives every signed-in user All and Guest, and every
# Desk user Desk User, so grants to these roles reach every CRM user.
IMPLICIT_ROLES = ("All", "Desk User", "Guest")
# Shared Frappe/ERPNext objects: only CRM-role rows are reconciled here; rows of
# other ERP roles stay ERP decisions.
SHARED_ERP_DOCTYPES = ("Customer", "Address", "Contact", "Lead")
# Frappe ships Address with an owner-only All create/write row. Installation keeps
# it and the Address hooks refuse CRM sites; any broader implicit grant is drift.
ADDRESS_IMPLICIT_MUTATIONS = {("All", 0, 1): frozenset({"write", "create"})}
# Write guards that run outside the permission hooks. Frappe runs every app's
# handlers, so only this app's hooks.py can drop one. Address before_delete is
# not listed: Frappe never fires that event (delete_doc runs on_trash and
# after_delete), and has_address_permission guards native deletes (#68).
REQUIRED_DOC_EVENTS = {
    ("Customer", "before_save"): "rayher_crm.permissions.scope.revoke_customer_address_shares_entering_crm",
    ("Customer", "before_rename"): "rayher_crm.permissions.scope.protect_standard_crm_merge",
    ("Customer Group", "before_rename"): "rayher_crm.permissions.scope.protect_crm_customer_group_name",
    ("Contact", "before_save"): "rayher_crm.permissions.scope.revoke_contact_shares_entering_crm",
    ("Contact", "before_rename"): "rayher_crm.permissions.scope.protect_standard_crm_merge",
    ("Lead", "before_save"): "rayher_crm.permissions.scope.revoke_lead_shares_entering_crm",
    ("Lead", "before_rename"): "rayher_crm.permissions.scope.protect_standard_crm_merge",
    ("Address", "before_save"): "rayher_crm.permissions.scope.revoke_address_shares_entering_crm",
    ("Address", "before_rename"): "rayher_crm.permissions.scope.protect_standard_crm_merge",
    ("User", "before_save"): "rayher_crm.permissions.scope.revoke_shares_when_user_enters_crm",
    ("User", "before_rename"): "rayher_crm.services.cockpit_identity.lock_users_before_rename",
    ("User", "after_rename"): "rayher_crm.permissions.scope.reconcile_shares_after_user_rename",
    ("File", "before_insert"): "rayher_crm.services.private_file_lifecycle.protect_private_upload",
    ("File", "before_validate"): "rayher_crm.services.managed_file_access.protect_file_write",
}
FILE_CONTENT_DELETE_HOOK = "rayher_crm.services.private_file_lifecycle.delete_file_content"
# Ends with validate_permission_registry, the gate of every migration.
MIGRATION_GATE_HOOK = "rayher_crm.setup.install.after_migrate"
# Reviewed Frappe 15 hooks that precede this app's list restrictions.
CORE_QUERY_HOOKS = {
    "Contact": ("frappe.contacts.address_and_contact.get_permission_query_conditions_for_contact",),
    "Address": ("frappe.contacts.address_and_contact.get_permission_query_conditions_for_address",),
    "File": ("frappe.core.doctype.file.file.get_permission_query_conditions",),
    "User": ("frappe.core.doctype.user.user.get_permission_query_conditions",),
}
# Shared core objects whose list boundaries live outside business row scopes.
CORE_BOUNDARY_MODULES = {
    "File": "services.managed_file_access",
    "User": "permissions.native_lists",
}


@dataclass(frozen=True)
class Policy:
    doctype: str
    category: str
    read_scope: str
    writers: tuple[str, ...]
    parent: str = ""
    query: str = ""
    detail: str = "has_crm_permission"
    # These roles describe deliberate native exceptions, never service capability.
    native_roles: tuple[str, ...] = ()


def _scope(name, query, read_scope, writers, parent="", detail="has_crm_permission"):
    return Policy(name, "scoped", read_scope, tuple(writers.split()), parent, query, detail)


def _child(name, read_scope, parent, *, standard=False):
    category = "standard_child_table" if standard else "child_table"
    return Policy(
        name,
        category,
        read_scope,
        (),
        parent,
        "scoped_child_query",
        "",
    )


POLICIES = (
    _scope("Customer", "customer_query", "Manager / Sales owner or Public / assigned Engineer; service DTOs redact fields", "accounts", detail="has_crm_permission"),
    _scope("Address", "address_query", "CRM Customer site scope; non-CRM ERP permissions preserved", "sites", "Customer", "has_address_permission"),
    _scope("Contact", "contact_query", "Current Customer and Contact ownership; native site fields restricted", "contacts", "Customer", "has_site_bearing_permission"),
    _scope("Lead", "lead_query", "Owner or linked Customer scope", "leads"),
    _scope("CRM Opportunity", "opportunity_query", "Current Account and Opportunity scope; service field projection", "opportunities leads", "Customer", "has_site_bearing_permission"),
    _scope("CRM Opportunity Probability History", "opportunity_probability_history_query", "Current Opportunity scope", "opportunities", "CRM Opportunity"),
    _scope("CRM Probability Recovery", "probability_recovery_query", "Current Opportunity scope", "probability_recovery", "CRM Opportunity"),
    _scope("CRM Probability Recovery Revision", "probability_recovery_revision_query", "Current Opportunity scope", "probability_recovery", "CRM Opportunity"),
    _scope("CRM Opportunity Loss Review", "opportunity_loss_review_query", "Current Opportunity scope", "loss_review", "CRM Opportunity"),
    _scope("CRM Opportunity Loss Review Revision", "opportunity_loss_review_revision_query", "Current Opportunity scope", "loss_review", "CRM Opportunity"),
    _scope("CRM Opportunity Stage History", "opportunity_stage_history_query", "Current Opportunity scope", "opportunity_stages", "CRM Opportunity"),
    _scope("CRM Opportunity Internal Validation", "opportunity_internal_validation_query", "Current Opportunity scope", "opportunities", "CRM Opportunity"),
    _scope("CRM Opportunity Action", "opportunity_action_query", "Current Opportunity scope", "opportunities", "CRM Opportunity"),
    _scope("CRM Opportunity History", "opportunity_history_query", "Current Opportunity scope", "opportunities leads cockpit_identity", "CRM Opportunity"),
    _scope("CRM Opportunity Stakeholder", "opportunity_stakeholder_query", "Current Opportunity; Engineer native reads denied", "stakeholders", "CRM Opportunity"),
    _scope("CRM Booking", "booking_query", "Current Account, Opportunity and Booking ownership", "bookings opportunities", "CRM Opportunity"),
    _scope("CRM Installed Tool", "installed_tool_query", "Current Account plus Sales owner or assigned Engineer", "installed_tools bookings", "Customer", "has_site_bearing_permission"),
    _scope("CRM Installed Tool Lifecycle History", "installed_tool_lifecycle_history_query", "Current Installed Tool scope", "installed_tools", "CRM Installed Tool"),
    _scope("CRM Installed Tool Service History", "installed_tool_service_history_query", "Current Installed Tool scope", "installed_tools", "CRM Installed Tool"),
    _scope("CRM Installed Tool Version History", "installed_tool_version_history_query", "Current Installed Tool scope", "installed_tools", "CRM Installed Tool"),
    _scope("CRM Demo Request", "demo_request_query", "Current Account, Sales owner or assigned Engineer", "demo_requests", "Customer"),
    _scope("CRM Demo Comment", "demo_comment_query", "Current Demo Request scope", "demo_requests demo_reports", "CRM Demo Request"),
    _scope("CRM Demo Request History", "demo_request_history_query", "Current Demo Request scope", "demo_requests demo_reports", "CRM Demo Request"),
    _scope("CRM Evaluation", "evaluation_query", "Demo Request Sales scope or current Evaluation Engineer", "evaluations demo_requests demo_resources", "CRM Demo Request"),
    _scope("CRM Evaluation Customer Review", "evaluation_customer_review_query", "Current Evaluation scope", "evaluations", "CRM Evaluation"),
    _scope("CRM Evaluation History", "evaluation_history_query", "Current Evaluation scope", "evaluations demo_resources", "CRM Evaluation"),
    _scope("CRM Test Run", "test_run_query", "Current Evaluation scope", "evaluations", "CRM Evaluation"),
    _scope("CRM Contact File", "contact_file_query", "Live metadata, current Contact scope and stakeholder capability", "contact_files", "Contact"),
    _scope("CRM Status Attachment", "status_attachment_query", "No native grant; audited service delivery only", "opportunity_status", "CRM Opportunity", "has_status_attachment_permission"),
    _scope("CRM Demo Artifact", "demo_artifact_query", "Current Demo Request plus submission state", "demo_artifacts", "CRM Demo Request"),
    _scope("CRM Notification Event", "notification_query", "Recipient and current supported source scope", "notifications", "source_doctype/source_name"),
    _scope("CRM Document Access Request", "document_access_request_query", "Manager all; requester own", "controlled_documents", "CRM Controlled Document"),
    _scope("CRM Visit", "visit_query", "Manager / Sales owner or action owner; Engineer denied", "visits", "Customer"),
    _scope("CRM Event", "event_query", "Manager / Sales owner and optional current Customer/Opportunity; Engineer denied", "events", "Customer"),
    _scope("CRM Visit Meeting Record", "visit_meeting_record_query", "Current Visit scope", "visit_meetings", "CRM Visit"),
    _scope("CRM Quotation", "quotation_query", "Manager / Sales Account and Quotation scope", "quotations quotation_planning", "Customer"),
    _scope("CRM Quotation Version", "quotation_version_query", "Current Quotation; service projection for draft-sensitive fields", "quotations", "CRM Quotation", "has_quotation_version_permission"),
    _scope("CRM Quotation Approval", "quotation_approval_query", "Manager and scoped Sales read; Engineer denied", "quotations", "CRM Quotation"),
    _scope("CRM RFQ", "rfq_query", "Current Account, Sales owner or assigned Engineer", "rfqs", "Customer"),
    _scope("CRM RFQ Version", "rfq_version_query", "Current RFQ scope", "rfqs", "CRM RFQ"),
    Policy("CRM Account Engineer Assignment", "desk_exception", "Manager all; Engineer own enabled; Sales denied", ("accounts",), "Customer", "account_engineer_assignment_query"),
    Policy("File", "file_boundary", "Managed Contact/Visit use current scope and provenance; private ordinary CRM parent attachments are hidden from native lists; ordinary ERP files retain Frappe policy", ("private_file_lifecycle",), "attached_to_doctype/attached_to_name", "file_query", "file_permission"),
    Policy("User", "user_directory", "Sales/Engineer own row; Administrator, System Manager, CRM Manager and non-CRM ERP users keep core policy", (), query="user_query", detail=""),
    _child("Allowed To Transact With", "Native parent row scope", "Customer.companies / Supplier.companies", standard=True),
    _child("Customer Credit Limit", "Native parent row scope", "Customer.credit_limits / Customer Group.credit_limits", standard=True),
    _child("Party Account", "Native parent row scope", "Customer / Customer Group / Supplier / Supplier Group accounts", standard=True),
    _child("Sales Team", "Native parent row scope", "Customer / sales transaction sales_team", standard=True),
    _child("Portal User", "Native parent row scope", "Customer.portal_users / Supplier.portal_users", standard=True),
    _child("Contact Email", "Native Contact row scope", "Contact.email_ids", standard=True),
    _child("Contact Phone", "Native Contact row scope", "Contact.phone_nos", standard=True),
    _child("Event Participants", "Native Event row scope", "Event.event_participants", standard=True),
    _child("Event Notifications", "Native Event row scope", "Event.notifications", standard=True),
    _child("Communication Link", "Native Communication row scope", "Communication.timeline_links", standard=True),
    _child("Dynamic Link", "Native Address, Contact, Event, Call Log or Common Code row scope", "links / applies_to", standard=True),
    _child("CRM Note", "Native Lead, Opportunity or Prospect row scope", "notes", standard=True),
    _child("Has Role", "Native User, Role Profile, Report, Page, Workspace, Dashboard Chart, Custom Role or Custom HTML Block row scope; a Single parent lists nothing", "roles", standard=True),
    _child("DefaultValue", "Native User row scope; system defaults belong to no user and are not listed", "User.defaults", standard=True),
    _child("User Email", "Native User row scope", "User.user_emails", standard=True),
    _child("User Social Login", "Native User row scope", "User.social_logins", standard=True),
    _child("Block Module", "Native User or Module Profile row scope", "block_modules", standard=True),
    Policy("CRM Opportunity Saved Query", "service_only", "Author writes; explicit recipients read definitions through the service", ("opportunity_board",)),
    _child("CRM Query Recipient", "Service-only Saved Query parent", "CRM Opportunity Saved Query.recipients"),
    Policy("CRM Opportunity Status", "service_only", "Current Opportunity; service projection", ("opportunity_status",), "CRM Opportunity"),
    Policy("CRM Equipment Type", "service_only", "Authenticated CRM equipment catalogue via bootstrap", ("equipment",)),
    Policy("CRM Sales Territory", "service_only", "Territory classification and totals through CRM services; not an access scope", ("territories", "territory_admin")),
    Policy("CRM Territory Assignment", "service_only", "Manager effective sales assignments; no access-scope effect", ("territory_admin",)),
    _child("CRM Quotation Follow Up", "Native Quotation row scope", "CRM Quotation.follow_ups"),
    Policy("CRM Demo Resource", "service_only", "Shared technical catalogue; Manager maintains concrete resource identities", ("demo_resources",)),
    Policy("CRM Demo Unavailability", "service_only", "Shared resource availability; Manager or named maintainer writes", ("demo_resources",), "CRM Demo Resource"),
    Policy("CRM Demo Resource Impact", "service_only", "Immutable observed impact; current Evaluation scope for service reads", ("demo_resources",), "CRM Evaluation"),
    _child("CRM Quotation Item", "Native Quotation Version row scope", "CRM Quotation Version.items"),
    _child("CRM Quotation Payment Term", "Native Quotation Version row scope", "CRM Quotation Version.payment_terms"),
    Policy("CRM Quotation Catalog Item", "catalogue", "Native catalogue for Manager and Sales", ("quotations",), native_roles=("CRM Manager", "CRM Sales")),
    Policy("CRM Controlled Document", "catalogue", "Existing shared CRM metadata catalogue; delivery-specific projection remains issue #68 follow-up", ("controlled_documents", "document_uploads"), native_roles=CRM_ROLES),
    Policy("CRM Document Upload Request", "desk_exception", "Existing Manager upload-request administration; service returns own submitted result", ("document_uploads",), native_roles=("CRM Manager",)),
    Policy("CRM File Access Audit", "manager_read", "Manager audit history", ("controlled_documents", "document_uploads", "opportunity_status"), native_roles=("CRM Manager",)),
    Policy("CRM Cockpit Settings", "manager_read", "Manager settings; service validates writes", ("cockpit_settings",), native_roles=("CRM Manager",)),
    Policy("CRM Cockpit Target", "manager_read", "Manager target rows; service validates writes", ("cockpit_settings",), native_roles=("CRM Manager",)),
    Policy("CRM Plan Commitment", "manager_read", "Manager period promises; current schedules remain independent", ("plan_commitments",), native_roles=("CRM Manager",)),
    Policy("CRM Warning Handling", "manager_read", "Manager handling state; service validates writes", ("warning_handling",), native_roles=("CRM Manager",)),
    Policy("CRM Warning Handling Revision", "manager_read", "Manager handling history", ("warning_handling",), native_roles=("CRM Manager",)),
)


def policy_map(policies=POLICIES):
    result = {}
    for policy in policies:
        if policy.doctype in result:
            raise ValueError(f"Duplicate native policy: {policy.doctype}")
        result[policy.doctype] = policy
    return result


def app_modules(root=APP_ROOT):
    return [line.strip() for line in (root / "modules.txt").read_text(encoding="utf-8").splitlines() if line.strip()]


def definitions(root=APP_ROOT):
    result = {}
    for path in (root / "rayher_crm" / "doctype").glob("*/*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        # A list-shaped file (for example a conventional test_records.json) is not a DocType.
        if isinstance(document, dict) and document.get("doctype") == "DocType":
            result[document["name"]] = document
    return result


def _static_key(key):
    """Constant and constant-tuple dictionary keys are comparable without running the code."""
    if isinstance(key, ast.Constant):
        return ("constant", key.value)
    if isinstance(key, ast.Tuple) and all(isinstance(item, ast.Constant) for item in key.elts):
        return ("tuple", tuple(item.value for item in key.elts))
    return None


def assert_no_duplicate_keys(source: str, name: str):
    for node in ast.walk(ast.parse(source, filename=name)):
        if not isinstance(node, ast.Dict):
            continue
        keys = [static for static in map(_static_key, node.keys) if static is not None]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate dictionary key in {name}:{node.lineno}")


def validate_source_registry(*, documents=None, query_hooks=None, detail_hooks=None, policies=None, modules=None):
    from rayher_crm import hooks

    registered = policy_map() if policies is None else policy_map(policies)
    documents = definitions() if documents is None else documents
    query_hooks = hooks.permission_query_conditions if query_hooks is None else query_hooks
    detail_hooks = hooks.has_permission if detail_hooks is None else detail_hooks
    modules = app_modules() if modules is None else modules
    if modules != [APP_MODULE]:
        raise ValueError(
            f"rayher_crm must keep its single {APP_MODULE} module; the DocType inventory "
            f"and the module-keyed DocShare guards in scope.py cover only that module: {modules}",
        )
    # Every registered object other than the shared Frappe/ERPNext DocTypes ships here.
    expected = {
        name
        for name, policy in registered.items()
        if name not in {*SHARED_ERP_DOCTYPES, *CORE_BOUNDARY_MODULES} and policy.category != "standard_child_table"
    }
    if set(documents) != expected:
        raise ValueError(f"CRM DocType policy inventory differs: missing={set(documents) - expected}, stale={expected - set(documents)}")
    for name, policy in registered.items():
        for writer in policy.writers:
            if not (APP_ROOT / "services" / f"{writer}.py").is_file():
                raise ValueError(f"Unknown registered business service: {name}/{writer}")
        module = CORE_BOUNDARY_MODULES.get(name, "permissions.scope")
        if policy.query and query_hooks.get(name) != f"rayher_crm.{module}.{policy.query}":
            raise ValueError(f"Missing or changed native scope hook for {name}: {policy.query}")
        if (
            policy.query
            and policy.detail
            and detail_hooks.get(name) != f"rayher_crm.{module}.{policy.detail}"
        ):
            raise ValueError(f"Missing or changed native scope hook for {name}: {policy.detail}")
        if name in documents and bool(documents[name].get("istable")) != (policy.category == "child_table"):
            raise ValueError(f"Changed child-table boundary: {name}")
        if policy.category == "service_only" and documents[name].get("permissions"):
            raise ValueError(f"Service-only object has native grants: {name}")
    for relative in ("hooks.py", "permissions/registry.py", "permissions/scope.py"):
        assert_no_duplicate_keys((APP_ROOT / relative).read_text(encoding="utf-8"), relative)
    share_handlers = hooks.doc_events.get("DocShare", {}).get("validate", ())
    if set(share_handlers if isinstance(share_handlers, list) else (share_handlers,)) != {
        "rayher_crm.permissions.scope.prevent_scoped_docshare",
        "rayher_crm.services.managed_file_access.protect_share",
    }:
        raise ValueError("Both managed-file and business-scope DocShare guards are required")
    for (doctype, event), handler in REQUIRED_DOC_EVENTS.items():
        handlers = hooks.doc_events.get(doctype, {}).get(event, ())
        if handler not in (handlers if isinstance(handlers, list) else (handlers,)):
            raise ValueError(f"Required document guard is missing or replaced: {doctype}.{event}")
    if hooks.delete_file_data_content != FILE_CONTENT_DELETE_HOOK:
        raise ValueError("Managed private file content deletion hook is required")
    if hooks.override_doctype_class.get("File") != "rayher_crm.overrides.file.ManagedFile":
        raise ValueError("Managed File controller override is required")
    required_search_overrides = {
        "frappe.desk.search.search_link": "rayher_crm.api.search.search_link",
        "frappe.desk.search.search_widget": "rayher_crm.api.search.search_widget",
    }
    for endpoint, handler in required_search_overrides.items():
        if hooks.override_whitelisted_methods.get(endpoint) != handler:
            raise ValueError(f"Scoped search override is required: {endpoint}")


def validate_site_hooks():
    """The CRM hooks must be the ones Frappe uses after merging every installed app.

    Frappe 15 joins list fragments without grouping them. Review the exact hook
    sequence instead of assuming that another fragment can only narrow access.
    The core File OR branches remain: managed-file migrations and write guards
    keep managed rows private, attached and free of ordinary aliases.
    """
    import frappe
    from frappe.core.doctype.server_script.server_script_utils import get_server_script_map
    from rayher_crm import hooks

    query_hooks = frappe.get_hooks("permission_query_conditions", {})
    permission_scripts = get_server_script_map().get("permission_query", {})
    for doctype, method in hooks.permission_query_conditions.items():
        effective = [*query_hooks.get(doctype, []), *query_hooks.get("*", [])]
        expected = [*CORE_QUERY_HOOKS.get(doctype, ()), method]
        if effective != expected:
            raise ValueError(
                f"Effective site hook differs from rayher_crm: permission_query_conditions/{doctype}: {effective}",
            )
        if permission_scripts.get(doctype):
            raise ValueError(f"Unregistered Permission Query Server Script for {doctype}")

    detail_hooks = frappe.get_hooks("has_permission", {})
    for doctype, method in hooks.has_permission.items():
        # has_controller_permissions asks every "*" hook and then the last app's
        # hook first; the first non-None answer decides.
        effective = [*detail_hooks.get(doctype, []), *detail_hooks.get("*", [])]
        if effective[-1:] != [method]:
            raise ValueError(f"Effective site hook differs from rayher_crm: has_permission/{doctype}: {effective}")
    for hook_name, registered in (
        ("override_whitelisted_methods", hooks.override_whitelisted_methods),
        ("override_doctype_class", hooks.override_doctype_class),
    ):
        installed = frappe.get_hooks(hook_name, {})
        for key, method in registered.items():
            # The last installed app's override wins.
            if installed.get(key, [])[-1:] != [method]:
                raise ValueError(
                    f"Effective site hook differs from rayher_crm: {hook_name}/{key}: {installed.get(key)}",
                )
    # frappe.utils.get_hook_method uses the first registered deletion hook.
    deletion = frappe.get_hooks("delete_file_data_content", [])
    if deletion[:1] != [hooks.delete_file_data_content]:
        raise ValueError(f"Effective site hook differs from rayher_crm: delete_file_data_content: {deletion}")
    # frappe.migrate runs after_migrate app by app in installed order and nothing follows it.
    # A hook after this gate could still change Custom DocPerm rows or enable a Permission
    # Query Server Script, so an app that has one must be installed before rayher_crm.
    migration = [
        method
        for app in frappe.get_installed_apps()
        for method in frappe.get_hooks("after_migrate", app_name=app)
    ]
    if migration[-1:] != [MIGRATION_GATE_HOOK]:
        raise ValueError(f"Effective site hook differs from rayher_crm: after_migrate: {migration}")


def permission_grants(rows):
    """Include owner/permlevel boundaries so duplicate or extra grants are visible."""
    result = {}
    for row in rows:
        key = (row.get("role"), int(row.get("permlevel") or 0), int(row.get("if_owner") or 0))
        if key in result:
            raise ValueError(f"Duplicate DocPerm: {key}")
        result[key] = frozenset(field for field in PERMISSIONS if row.get(field))
    return result


def grant_difference(actual, expected):
    """Name every role row whose installed bits differ from the registered bits."""
    return "; ".join(
        f"{role} permlevel {level} if_owner {owner}: installed {sorted(actual.get(key, ()))}, "
        f"registered {sorted(expected.get(key, ()))}"
        for key in sorted(set(actual) | set(expected))
        if actual.get(key) != expected.get(key)
        for role, level, owner in (key,)
    )


def validate_implicit_role_grants(name, rows):
    """Every CRM user holds the implicit roles, so their mutations are CRM grants too."""
    allowed = ADDRESS_IMPLICIT_MUTATIONS if name == "Address" else {}
    implicit = permission_grants(row for row in rows if row.get("role") in IMPLICIT_ROLES)
    for key, bits in implicit.items():
        if extra := (bits & NATIVE_MUTATIONS) - allowed.get(key, frozenset()):
            raise ValueError(f"Implicit role has a native mutation grant: {name}/{key}: {sorted(extra)}")
        _role, level, owner = key
        # A level-0 read without the owner boundary would let every signed-in user read
        # these shared objects, including CRM records that the hooks scope only for CRM
        # roles. Frappe ships only owner-only rows (and Lead's level-1 Desk User read).
        if level == 0 and not owner and (open_read := bits & IMPLICIT_READ_BITS):
            raise ValueError(f"Implicit role has an unrestricted read grant: {name}/{key}: {sorted(open_read)}")


def installed_permission_rows(name):
    import frappe

    # Meta intentionally omits Custom DocPerm while flags.in_install is set.
    # Read the stored effective rows directly so fresh install and migrate check
    # the same contract. Frappe uses all custom rows when any exist for a DocType.
    fields = ["role", "permlevel", "if_owner", *PERMISSIONS]
    custom = frappe.get_all("Custom DocPerm", filters={"parent": name}, fields=fields)
    return custom or frappe.get_all("DocPerm", filters={"parent": name}, fields=fields)


def installed_child_relationships(name):
    import frappe
    from frappe.model.meta import Meta

    # Frappe attaches the child type of the effective field: a DocField or Custom Field row
    # as changed by its Property Setters (Meta.apply_property_setters). Any of the three can
    # name this child, so each such parent is built from its stored rows; the Meta cache is
    # neither trusted nor replaced.
    parents = {
        *frappe.get_all("DocField", filters={"options": name}, pluck="parent"),
        *frappe.get_all("Custom Field", filters={"options": name}, pluck="dt"),
        *frappe.get_all(
            "Property Setter",
            filters={"doctype_or_field": "DocField", "property": "options", "value": name},
            pluck="doc_type",
        ),
    }
    return {
        (parent, field.fieldname)
        for parent in parents
        # Rows of a deleted DocType attach nothing.
        if frappe.db.exists("DocType", parent)
        for field in Meta(parent).get_table_fields()
        if field.options == name
    }


def installed_table_fields(parent):
    from frappe.model.meta import Meta

    # The effective table fields as stored (DocField, Custom Field and Property Setter rows),
    # read outside the Meta cache like installed_child_relationships.
    return [field for field in Meta(parent).get_table_fields() if field.options]


def validate_permission_registry(*, installed=True):
    import frappe
    from rayher_crm.permissions.scope import (
        CONDITION_DOCTYPES,
        DOCPERMS_BY_DOCTYPE,
        ROLE_DOCPERMS,
        SCOPED_CHILD_RELATIONSHIPS,
    )

    validate_source_registry()
    documents = definitions()
    policies = policy_map()
    if installed:
        validate_site_hooks()
        installed_modules = sorted(frappe.get_all("Module Def", filters={"app_name": "rayher_crm"}, pluck="name"))
        if installed_modules != [APP_MODULE]:
            raise ValueError(f"rayher_crm must keep its single {APP_MODULE} module: {installed_modules}")
        installed_objects = set(frappe.get_all("DocType", filters={"module": APP_MODULE}, pluck="name"))
        if installed_objects != set(documents):
            raise ValueError(f"Installed CRM DocType inventory differs: {installed_objects ^ set(documents)}")
    registered_query_scopes = {
        policy.doctype
        for policy in POLICIES
        if policy.query and policy.doctype not in CORE_BOUNDARY_MODULES
    }
    registered_docperm_scopes = {
        policy.doctype for policy in POLICIES if policy.category == "scoped"
    } | {"CRM Account Engineer Assignment"}
    registered_children = {
        policy.doctype
        for policy in POLICIES
        if policy.category in {"child_table", "standard_child_table"}
    }
    if set(CONDITION_DOCTYPES) != registered_query_scopes:
        raise ValueError("Scoped DocTypes and policy inventory differ")
    if set(SCOPED_CHILD_RELATIONSHIPS) != registered_children:
        raise ValueError("Scoped child relationships and policy inventory differ")
    if installed:
        for child_doctype, expected_relationships in SCOPED_CHILD_RELATIONSHIPS.items():
            if not frappe.get_meta(child_doctype).istable:
                raise ValueError(f"Registered child is no longer a child table: {child_doctype}")
            relationships = installed_child_relationships(child_doctype)
            expected_set = set(expected_relationships)
            unregistered = relationships - expected_set
            missing = expected_set - relationships
            # Only CRM-owned parents are this release's decision. An ERP admin (Customize Form,
            # a Custom Field, an ERPNext upgrade) may add or drop a table field on an ERP-owned
            # DocType; that must not abort `bench migrate` and take the whole backend down.
            # Rows of an unregistered parent are already denied at runtime (scoped_child_query
            # only builds branches for registered parents), so it is reported, not fatal.
            crm_owned = sorted(
                item for item in (unregistered | missing)
                if frappe.db.get_value("DocType", item[0], "module") == APP_MODULE
            )
            if crm_owned:
                raise ValueError(
                    f"Installed child relationships differ: {child_doctype}: "
                    f"unregistered={sorted(unregistered)}, missing={sorted(missing)}, crm_owned={crm_owned}",
                )
            if unregistered or missing:
                frappe.logger("rayher_crm").warning(
                    "ERP-owned child relationships of %s differ from the CRM registry: unregistered=%s missing=%s",
                    child_doctype, sorted(unregistered), sorted(missing),
                )
        # A list hook on a parent is only as tight as the hooks on its child tables: Frappe lists a
        # child table on the parent's DocType-level read alone (#219). Every table field of a parent
        # the CRM hooks must therefore be registered, whoever owns the parent; an unregistered one
        # lists every row. A Frappe or ERPNext upgrade that adds one fails here, not silently.
        from rayher_crm import hooks

        for parent in hooks.permission_query_conditions:
            if parent in SCOPED_CHILD_RELATIONSHIPS or not frappe.db.exists("DocType", parent):
                continue
            for field in installed_table_fields(parent):
                if (parent, field.fieldname) not in SCOPED_CHILD_RELATIONSHIPS.get(field.options, ()):
                    raise ValueError(
                        f"Child table {field.options} of {parent}.{field.fieldname} is listed without "
                        "the parent's scope: register it in SCOPED_CHILD_RELATIONSHIPS, hooks and the policies",
                    )
    for name, policy in policies.items():
        if name in CORE_BOUNDARY_MODULES:
            continue  # Shared core DocPerms; explicit list/lifecycle hooks above.
        if name in registered_docperm_scopes:
            allowed = DOCPERMS_BY_DOCTYPE.get(name, ROLE_DOCPERMS)
            for role, bits in allowed.items():
                if bits & NATIVE_MUTATIONS and (
                    (name, role) != ("CRM Account Engineer Assignment", "CRM Manager")
                    or bits & {"submit", "cancel", "amend", "import"}
                ):
                    raise ValueError(f"Unregistered native write exception: {name}/{role}")
            expected = {(role, 0, 0): frozenset(bits) for role, bits in allowed.items()}
        else:
            # The one legacy upload administration exception is explicit; widening
            # its JSON never silently widens this release contract.
            bits = {"read", "create", "write"} if name == "CRM Document Upload Request" else {"read"}
            expected = {(role, 0, 0): frozenset(bits) for role in policy.native_roles}
        # Schema bootstrapping may grant fewer convenience bits than installation,
        # but cannot broaden the allowed role, owner boundary or operation.
        if name in documents:
            for key, bits in permission_grants(documents[name].get("permissions", ())).items():
                if bits - expected.get(key, frozenset()):
                    raise ValueError(f"JSON permissions exceed policy: {name}/{key}")
        if not installed:
            continue
        rows = installed_permission_rows(name)
        if name in SHARED_ERP_DOCTYPES:
            validate_implicit_role_grants(name, rows)
            # Rows of other ERP roles, duplicates included, stay ERP decisions.
            rows = [row for row in rows if row.get("role") in CRM_ROLES]
        # A zero-bit row is a denial, not an additional grant.
        granted = {key: bits for key, bits in permission_grants(rows).items() if bits}
        registered = {key: bits for key, bits in expected.items() if bits}
        if granted != registered:
            raise ValueError(
                f"Installed permissions differ from policy: {name}: {grant_difference(granted, registered)}",
            )
