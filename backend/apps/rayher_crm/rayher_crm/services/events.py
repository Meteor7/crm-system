"""Sales events without outbound invitations; source-owned plans and completion facts."""
import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE, assert_capability, resolve_crm_role
from frappe.permissions import has_user_permission
from rayher_crm.services.common import (
    as_payload, normalize_expected_modified, normalize_pagination, optional_date, required_text, to_iso_timestamp,
)
from rayher_crm.services.accounts import (
    ARCHIVED_ACCOUNT_EDIT, ARCHIVED_ACCOUNT_LINK, ARCHIVED_ACCOUNT_REOPEN, lock_accounts,
)
from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_LINK, assert_opportunity_not_archived

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


def canonical_name(doctype, name):
    """The record's own name, as the database has it: its collation matches a name without regard to case, accents,
    width and the like, and a name so matched is that record's. The locks, the archive flags, the checks and the stored
    link all take the record's own (Frappe would store that one anyway)."""

    return (frappe.db.get_value(doctype, name, "name") or name) if name else name


def locked_existing(name):
    """The Event's row alone, under its lock. Its Accounts' and Opportunities' rows come after it (lock_links), and its
    scope and version are checked once those are held (check_existing)."""

    if not frappe.db.sql("SELECT `name` FROM `tabCRM Event` WHERE `name` = %s FOR UPDATE", (name,)):
        raise CrmApiException("NOT_FOUND", "Event was not found.")
    return frappe.get_doc(DOCTYPE, name, for_update=True)


def lock_links(doc, account, opportunity):
    """The rows of the Accounts and the Opportunities the Event leaves and names, in the order the Account's archive and
    every writer under an Account take them in (accounts.require_active_account): the Accounts' rows shared, by one
    statement in the database's name order (accounts.lock_accounts), then the Opportunities' exclusively, likewise.
    Returns the Accounts' archive flags and the Opportunities' rows, as committed."""

    flags = lock_accounts((doc.account, account))
    names = sorted({name for name in (doc.opportunity, opportunity) if name})
    deals = {}
    if names:
        rows = frappe.db.sql(
            "SELECT `name`, `account`, `opportunity_owner`, `archived` FROM `tabCRM Opportunity` "
            f"WHERE `name` IN ({', '.join(['%s'] * len(names))}) ORDER BY `name` FOR UPDATE",
            names, as_dict=True,
        )
        deals = {str(row.name).casefold(): row for row in rows}
    return flags, deals


def check_existing(doc, expected):
    # Every row read here is held already (the Event's and its Opportunity's exclusively, its Account's shared): a
    # current read of each, without raising a lock.
    row = frappe.db.sql("""SELECT e.event_owner, e.modified, e.account, e.opportunity,
        c.custom_crm_owner, c.custom_crm_visibility, o.opportunity_owner, o.account AS opportunity_account
        FROM `tabCRM Event` e LEFT JOIN `tabCustomer` c ON c.name=e.account
        LEFT JOIN `tabCRM Opportunity` o ON o.name=e.opportunity WHERE e.name=%s LOCK IN SHARE MODE""", (doc.name,), as_dict=True)[0]
    if resolve_crm_role() == "Sales" and (
        row.event_owner != frappe.session.user
        or (row.account and row.custom_crm_owner != frappe.session.user and row.custom_crm_visibility != "Public")
        or (row.opportunity and (row.opportunity_owner != frappe.session.user or row.opportunity_account != row.account))
    ):
        raise CrmApiException("SCOPE_DENIED", "Event is outside the current user scope.")
    require_read(doc)
    if normalize_expected_modified(expected) != to_iso_timestamp(row.modified):
        raise CrmApiException("VERSION_CONFLICT", "Event changed; reload before saving.")


def lock_owner(owner):
    # The owner's User row is held from the start of the save; its roles under their locks with it, after the Event's
    # row and before the Accounts'. Judged once the Event's scope and version are (check_owner).
    enabled = frappe.db.get_value("User", owner, "enabled", for_update=True)
    roles = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='User' FOR UPDATE", (owner,), pluck=True)
    return enabled, roles


def check_owner(enabled, roles):
    if not enabled or {r for r in roles if r in CRM_ROLE_TO_PROFILE} != {"CRM Sales"}:
        raise CrmApiException("INVALID_OWNER", "Event owner must be an active CRM Sales user.")


def validate_links(owner, account, opportunity, deals, *, linking):
    if opportunity:
        opp = deals.get(opportunity.casefold())
        if not account or not opp or opp.account != account or opp.opportunity_owner != owner:
            raise CrmApiException("VALIDATION_ERROR", "Choose an opportunity on this account owned by the event owner.")
        # An archived Opportunity takes no new Event (the flag as committed, under its row's lock); an Event that names
        # it already is a record of its own and is still kept up, as a Visit is.
        if linking:
            assert_opportunity_not_archived(opp.archived, ARCHIVED_OPPORTUNITY_LINK)
    if account:
        # The Account's row is held shared (lock_links): a current read, without raising the lock.
        customers = frappe.db.sql(
            "SELECT `custom_crm_owner`, `custom_crm_visibility` FROM `tabCustomer` WHERE `name` = %s LOCK IN SHARE MODE",
            (account,), as_dict=True,
        )
        customer = customers[0] if customers else None
        if not customer or (customer.custom_crm_owner != owner and customer.custom_crm_visibility != "Public"):
            raise CrmApiException("SCOPE_DENIED", "The event owner cannot access this account.")


def assert_account_rules(before, account, opportunity, status, flags):
    """An archived Account takes no new Event, nor one moved under it; an Event under it is not moved out, nor given
    another deal, and one done or cancelled is not planned again ("Nothing is reopened"): otherwise it is still kept up
    (its dates, its notes, done or cancelled, its deal cleared: a way to keep it up once the deal's owner changed since,
    as assigning it to the deal's new owner is), as a Visit planned before the archive is. `before` is the Event as it
    was: whether it is new, its Account, its deal and its status."""

    new, old_account, old_opportunity, old_status = before
    moved = not new and (account or "") != (old_account or "")
    if account and flags.get(account) and (new or moved):
        raise CrmApiException("INVALID_TRANSITION", ARCHIVED_ACCOUNT_LINK)
    if new or not old_account or not flags.get(old_account):
        return
    if moved or (opportunity and opportunity != (old_opportunity or "")):
        raise CrmApiException("INVALID_TRANSITION", ARCHIVED_ACCOUNT_EDIT)
    if status == "Planned" and old_status in ("Done", "Cancelled"):
        raise CrmApiException("INVALID_TRANSITION", ARCHIVED_ACCOUNT_REOPEN)


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
    account, opportunity = canonical_name("Customer", account), canonical_name("CRM Opportunity", opportunity)
    values = {key: text(payload, key, 10000 if key == "note" else 140) for key in ("region", "market", "equipment", "note")}
    # Native User rename/merge holds User before rewriting Event links and
    # creator metadata. Lock the requested identity before the Event, including
    # existing records. Validate active roles below only when assigning, so a
    # manager can still maintain history belonging to an inactive owner.
    frappe.db.get_value("User", owner, "name", for_update=True)
    doc = locked_existing(name) if name else frappe.get_doc({"doctype": DOCTYPE})
    if not name and expected_modified:
        raise CrmApiException("VERSION_CONFLICT", "A new event cannot have an existing version.")
    assigning = not name or owner != doc.event_owner
    changing_links = assigning or account != (doc.account or "") or opportunity != (doc.opportunity or "")
    # Then the owner's roles, then the Accounts' rows and the Opportunities' (lock_links): the User, the Event, the
    # Accounts, the Opportunities, the order every writer takes them in. The checks come once all are held, in the
    # order the save had them: the Event's scope and version, the owner, the links.
    owner_rows = lock_owner(owner) if assigning else None
    flags, deals = lock_links(doc, account, opportunity)
    if name:
        check_existing(doc, expected_modified)
    if owner_rows:
        check_owner(*owner_rows)
    validate_links(owner, account, opportunity, deals, linking=not name or opportunity != (doc.opportunity or ""))
    before = (doc.is_new(), doc.account, doc.opportunity, doc.status)
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
    # An archived Account's rules once the reader's Desk permissions are checked (an Account they may not read is not
    # told archived), before anything is written.
    assert_account_rules(before, account, opportunity, status, flags)
    savepoint = "crm_event_" + frappe.generate_hash(length=8)
    frappe.db.savepoint(savepoint)
    try:
        doc.save(ignore_permissions=True, ignore_version=False) if name else doc.insert(ignore_permissions=True)
        return dto(doc)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
