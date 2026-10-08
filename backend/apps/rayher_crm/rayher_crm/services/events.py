"""Sales events without outbound invitations; source-owned plans and completion facts."""
import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE, assert_capability, resolve_crm_role
from frappe.permissions import has_user_permission
from rayher_crm.services.common import (
    as_payload, normalize_expected_modified, normalize_pagination, optional_date, required_text, to_iso_timestamp,
)

DOCTYPE = "CRM Event"
FIELDS = "name title event_owner start_date end_date status account opportunity region market equipment note completed_at completed_owner modified creation"


def dto(row):
    return {"id": row.name, "title": row.title, "owner": row.event_owner,
            "startDate": str(row.start_date), "endDate": str(row.end_date), "status": row.status,
            "accountId": row.account or "", "opportunityId": row.opportunity or "",
            "region": row.region or "", "market": row.market or "", "equipment": row.equipment or "", "note": row.note or "",
            "completedAt": to_iso_timestamp(row.completed_at) if row.completed_at else None,
            "modified": to_iso_timestamp(row.modified)}


def get_event(name):
    assert_capability("event:view")
    if not frappe.db.exists(DOCTYPE, name):
        raise CrmApiException("SCOPE_DENIED", "Event is unavailable in your current scope.")
    doc = frappe.get_doc(DOCTYPE, name)
    require_read(doc)
    return dto(doc)


def require_read(doc):
    if not frappe.has_permission(DOCTYPE, "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "Event is unavailable in your current scope.")


def list_events(query):
    assert_capability("event:view")
    page, size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    search = str(query.get("search") or "").strip()
    filters = {"title": ["like", f"%{search}%"]} if search else {}
    # Both rows and count must apply native User Permissions as well as CRM hooks.
    total = frappe.get_list(DOCTYPE, filters=filters, fields=["count(name) as total"])[0].total
    rows = frappe.get_list(DOCTYPE, filters=filters, fields=FIELDS.split(),
                           order_by="start_date desc, name asc", start=offset, page_length=size)
    return [dto(row) for row in rows], total, page, size


def text(payload, key, limit=140):
    value = payload.get(key) or ""
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise CrmApiException("VALIDATION_ERROR", f"{key} must be text up to {limit} characters.")
    return value.strip()


def locked_existing(name, expected):
    rows = frappe.db.sql("""SELECT e.name, e.event_owner, e.modified, e.account, e.opportunity,
        c.custom_crm_owner, c.custom_crm_visibility, o.opportunity_owner, o.account AS opportunity_account
        FROM `tabCRM Event` e LEFT JOIN `tabCustomer` c ON c.name=e.account
        LEFT JOIN `tabCRM Opportunity` o ON o.name=e.opportunity WHERE e.name=%s FOR UPDATE""", (name,), as_dict=True)
    if not rows:
        raise CrmApiException("NOT_FOUND", "Event was not found.")
    row = rows[0]
    if resolve_crm_role() == "Sales" and (
        row.event_owner != frappe.session.user
        or (row.account and row.custom_crm_owner != frappe.session.user and row.custom_crm_visibility != "Public")
        or (row.opportunity and (row.opportunity_owner != frappe.session.user or row.opportunity_account != row.account))
    ):
        raise CrmApiException("SCOPE_DENIED", "Event is outside the current user scope.")
    doc = frappe.get_doc(DOCTYPE, name, for_update=True)
    require_read(doc)
    if normalize_expected_modified(expected) != to_iso_timestamp(row.modified):
        raise CrmApiException("VERSION_CONFLICT", "Event changed; reload before saving.")
    return doc


def validate_links(owner, account, opportunity, *, assigning):
    if assigning:
        enabled = frappe.db.get_value("User", owner, "enabled", for_update=True)
        roles = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='User' FOR UPDATE", (owner,), pluck=True)
        if not enabled or {r for r in roles if r in CRM_ROLE_TO_PROFILE} != {"CRM Sales"}:
            raise CrmApiException("INVALID_OWNER", "Event owner must be an active CRM Sales user.")
    if opportunity:
        opp = frappe.db.get_value("CRM Opportunity", opportunity, ["account", "opportunity_owner"], as_dict=True, for_update=True)
        if not account or not opp or opp.account != account or opp.opportunity_owner != owner:
            raise CrmApiException("VALIDATION_ERROR", "Choose an opportunity on this account owned by the event owner.")
    if account:
        customer = frappe.db.get_value("Customer", account, ["custom_crm_owner", "custom_crm_visibility"], as_dict=True, for_update=True)
        if not customer or (customer.custom_crm_owner != owner and customer.custom_crm_visibility != "Public"):
            raise CrmApiException("SCOPE_DENIED", "The event owner cannot access this account.")


def save_event(payload, name=None, expected_modified=None):
    assert_capability("event:write")
    payload = as_payload(payload)
    if "id" in payload:
        raise CrmApiException("VALIDATION_ERROR", "Use the event id parameter, not an id in input.")
    title = required_text(payload, "title")
    start, end = optional_date(payload.get("startDate"), "startDate"), optional_date(payload.get("endDate"), "endDate")
    status = payload.get("status")
    if len(title) > 140 or not start or not end or end < start or status not in ("Planned", "Done", "Cancelled"):
        raise CrmApiException("VALIDATION_ERROR", "Provide a title up to 140 characters, an ordered date range and a valid status.")
    owner = text(payload, "owner") or frappe.session.user
    if resolve_crm_role() == "Sales" and owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Sales users can only assign records to themselves.")
    account, opportunity = text(payload, "accountId"), text(payload, "opportunityId")
    values = {key: text(payload, key, 10000 if key == "note" else 140) for key in ("region", "market", "equipment", "note")}
    # Native User rename/merge holds User before rewriting Event links and
    # creator metadata. Lock the requested identity before the Event, including
    # existing records. Validate active roles below only when assigning, so a
    # manager can still maintain history belonging to an inactive owner.
    frappe.db.get_value("User", owner, "name", for_update=True)
    doc = locked_existing(name, expected_modified) if name else frappe.get_doc({"doctype": DOCTYPE})
    if not name and expected_modified:
        raise CrmApiException("VERSION_CONFLICT", "A new event cannot have an existing version.")
    assigning = not name or owner != doc.event_owner
    changing_links = assigning or account != (doc.account or "") or opportunity != (doc.opportunity or "")
    validate_links(owner, account, opportunity, assigning=assigning)
    # Business rows precede catalogue locks, matching Opportunity saves. Use
    # current catalogue rows; equipment cleanup shares the same catalogue lock.
    if values["region"]:
        from rayher_crm.services.regions import list_regions
        if values["region"] not in list_regions(for_update=True):
            raise CrmApiException("VALIDATION_ERROR", "Choose an existing region or leave it blank.")
    choices = (frappe.get_meta("Customer").get_field("custom_crm_segment").options or "").splitlines()
    if values["market"] and values["market"] not in choices:
        raise CrmApiException("VALIDATION_ERROR", "Choose an existing market or leave it blank.")
    if values["equipment"]:
        from rayher_crm.services.equipment import EQUIPMENT_PRESETS, lock_catalog
        if values["equipment"] not in [*EQUIPMENT_PRESETS, *lock_catalog()]:
            raise CrmApiException("VALIDATION_ERROR", "Choose an existing equipment type or leave it blank.")
    was_done = doc.status == "Done"
    doc.update({"title": title, "event_owner": owner, "start_date": start, "end_date": end, "status": status,
                "account": account or None, "opportunity": opportunity or None, **values})
    if status == "Done" and not was_done:
        doc.completed_at, doc.completed_owner = frappe.utils.now_datetime(), owner
    elif status != "Done":
        doc.completed_at = doc.completed_owner = None
    # Native create/write is intentionally disabled for these service-only
    # mutations. Still apply its User Permission restrictions to proposed links.
    # Existing disabled owners remain valid for a manager's historical edits.
    if not has_user_permission(doc, frappe.session.user) or (changing_links and not has_user_permission(doc, owner)):
        raise CrmApiException("SCOPE_DENIED", "Event links are outside the permitted scope.")
    savepoint = "crm_event_" + frappe.generate_hash(length=8)
    frappe.db.savepoint(savepoint)
    try:
        doc.save(ignore_permissions=True, ignore_version=False) if name else doc.insert(ignore_permissions=True)
        return dto(doc)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
