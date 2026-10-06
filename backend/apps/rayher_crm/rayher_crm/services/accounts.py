"""Customer-backed Account services."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, capabilities_for_user, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.common import (
    delete_manager_scoped_document,
    ensure_server_generated_id,
    normalize_pagination,
    read_all_pages,
    required_text,
    resolve_write_owner,
    to_iso_timestamp,
    validate_choice,
)
from rayher_crm.services.concurrency import committed_reader, lock_document
from rayher_crm.services.notifications import create_notification, record_route
from rayher_crm.services.opportunity_stages import OPEN_STAGES
from rayher_crm.services.regions import collapse_region, list_regions, matching_region, register_region


DEFAULT_ACCOUNT_SEGMENTS = ("Frontend", "Advanced Packaging")
ACCOUNT_TIERS = {"S", "A", "B"}
ACCOUNT_VISIBILITY = {"Private", "Public"}


def _customer_kind(value):
    if value is None or value == "":
        return ""
    return validate_choice(value, "customerKind", {"Prospect", "Existing"})


def _segment_options(raw_options: Any) -> list[str]:
    values = [*DEFAULT_ACCOUNT_SEGMENTS, *str(raw_options or "").splitlines()]
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _segment_field(*, for_update: bool = False) -> dict[str, Any]:
    lock = " FOR UPDATE" if for_update else ""
    rows = frappe.db.sql(
        "SELECT `name`, `options` FROM `tabCustom Field` "
        "WHERE `dt` = 'Customer' AND `fieldname` = 'custom_crm_segment' LIMIT 1" + lock,
        as_dict=True,
    )
    if not rows:
        raise CrmApiException("INTERNAL_ERROR", "Customer segment field is not configured.")
    return rows[0]


def list_account_segments() -> list[str]:
    assert_capability("account:view")
    return _segment_options(_segment_field().get("options"))


def list_account_regions() -> list[str]:
    assert_capability("account:view")
    return list_regions()


def list_account_cities() -> list[str]:
    assert_capability("account:view")
    rows = frappe.db.sql(
        f"SELECT DISTINCT `custom_crm_city` AS `city` FROM `tabCustomer` "
        f"WHERE ({conditions_for_doctype('Customer')}) "
        "AND COALESCE(`custom_crm_city`, '') != '' ORDER BY `custom_crm_city` ASC",
        as_dict=True,
    )
    return [row.city.strip() for row in rows if row.city and row.city.strip()]


def _register_account_segment(segment: str) -> None:
    field = _segment_field(for_update=True)
    segments = _segment_options(field.get("options"))
    if segment in segments:
        return
    frappe.db.set_value(
        "Custom Field",
        field["name"],
        "options",
        "\n".join([*segments, segment]),
        update_modified=False,
    )
    frappe.clear_cache(doctype="Customer")


def delete_account(name: str) -> dict[str, str]:
    return delete_manager_scoped_document("Customer", name, "account:write", "ACCOUNT_NOT_FOUND")


def _account_counts(customer: str) -> tuple[int, int]:
    stakeholder_count = frappe.db.sql(
        """SELECT COUNT(DISTINCT `contact`.`name`)
        FROM `tabContact` AS `contact`
        INNER JOIN `tabDynamic Link` AS `link` ON `link`.`parent` = `contact`.`name`
        WHERE `link`.`parenttype` = 'Contact' AND `link`.`parentfield` = 'links'
          AND `link`.`link_doctype` = 'Customer' AND `link`.`link_name` = %s
          AND COALESCE(`contact`.`custom_crm_status`, 'Active') != 'Archived'""",
        (customer,),
    )[0][0]
    site_count = frappe.db.count("Dynamic Link", {"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"})
    return int(stakeholder_count or 0), int(site_count or 0)


def _account_activity_metrics(account_id: str) -> dict[str, Any]:
    opportunity_scope = conditions_for_doctype("CRM Opportunity")
    opportunities = frappe.db.sql(
        f"SELECT `name`, `stage`, `currency`, `score`, CAST(`amount` AS CHAR) AS `amount` "
        f"FROM `tabCRM Opportunity` WHERE ({opportunity_scope}) AND `account` = %s",
        (account_id,),
        as_dict=True,
    )
    open_opportunities = [item for item in opportunities if item.stage in OPEN_STAGES]
    # 0 is an amount nobody has entered yet (allowed at S1): it adds no value and no second currency,
    # and is counted apart so the total is not read as complete.
    priced = [item for item in open_opportunities if Decimal(str(item.amount or 0)) > 0]
    currencies = {str(item.currency or "") for item in priced}
    pipeline_amount = (
        sum((Decimal(str(item.amount)) for item in priced), Decimal("0"))
        if len(currencies) <= 1 else Decimal("0")
    )
    intent_score = max((int(item.score or 0) for item in opportunities), default=0)
    open_ids = [item.name for item in open_opportunities]
    actions = frappe.get_all(
        "CRM Opportunity Action",
        filters={"opportunity": ["in", open_ids], "archived": 0, "status": "Open"},
        fields=["name AS id", "title", "due"],
        order_by="due asc, name asc",
    ) if open_ids else []
    next_action = actions[0] if actions else None
    due = str(next_action.due or "") if next_action else ""
    overdue = bool(due and due < frappe.utils.today())
    return {
        "pipelineAmount": float(pipeline_amount),
        "pipelineMissingAmountCount": len(open_opportunities) - len(priced),
        "intentScore": intent_score,
        "risk": "高风险" if overdue else "关注" if open_opportunities and not next_action else "稳健",
        "nextAction": str(next_action.title or "") if next_action else "",
        "nextActionDue": due,
    }


def serialize_account(doc) -> dict[str, Any]:
    stakeholder_count, site_count = _account_counts(doc.name)
    is_non_owner_sales = resolve_crm_role() == "Sales" and doc.custom_crm_owner != frappe.session.user
    if is_non_owner_sales:
        site_count = 0
    activity = _account_activity_metrics(doc.name)
    if is_non_owner_sales:
        activity = {
            "pipelineAmount": 0,
            "pipelineMissingAmountCount": 0,
            "intentScore": 0,
            "risk": "稳健",
            "nextAction": "",
            "nextActionDue": "",
        }
    modified = to_iso_timestamp(doc.modified)
    populated = sum(bool(getattr(doc, field, None)) for field in (
        "customer_name", "custom_crm_short_name", "custom_crm_segment",
        "custom_crm_tier", "custom_crm_city", "custom_crm_region", "custom_crm_owner",
    ))
    return {
        "id": doc.name,
        "name": doc.customer_name,
        "shortName": doc.custom_crm_short_name or doc.customer_name,
        "segment": doc.custom_crm_segment,
        "tier": doc.custom_crm_tier,
        "customerKind": doc.get("custom_crm_customer_kind") or "",
        "city": doc.custom_crm_city or "",
        "region": doc.custom_crm_region or "",
        "owner": doc.custom_crm_owner,
        "visibility": doc.custom_crm_visibility or "Private",
        # The Sites, pipeline, intent, next step and risk above are zeroed for a Sales user who does not own the
        # Account; said here, so that the pages show "owner only" and not a zero.
        "metricsRestricted": is_non_owner_sales,
        "pipelineAmount": activity["pipelineAmount"],
        "pipelineMissingAmountCount": activity["pipelineMissingAmountCount"],
        "intentScore": activity["intentScore"],
        "stakeholderCount": stakeholder_count,
        "siteCount": site_count,
        "requirementCount": 0,
        "completeness": round(populated / 7 * 100),
        "risk": activity["risk"],
        "nextAction": activity["nextAction"],
        "nextActionDue": activity["nextActionDue"],
        "updatedAt": modified,
        "modified": modified,
    }


def _validate_account_input(
    payload: dict[str, Any],
    existing_owner: str | None = None,
    existing_visibility: str | None = None,
) -> dict[str, str]:
    requested_owner = required_text(payload, "owner")
    owner = resolve_write_owner(requested_owner, shared_sales=False)
    return {
        "name": required_text(payload, "name"),
        "short_name": required_text(payload, "shortName"),
        "segment": required_text(payload, "segment"),
        "tier": validate_choice(payload.get("tier"), "tier", ACCOUNT_TIERS),
        "city": required_text(payload, "city"),
        "region": required_text(payload, "region"),
        "owner": owner,
        "visibility": validate_choice(
            payload.get("visibility") if payload.get("visibility") is not None else (existing_visibility or "Private"),
            "visibility",
            ACCOUNT_VISIBILITY,
        ),
    }


ACCOUNT_NOT_FOUND_MESSAGE = "Account was not found, or you have no access to it."
ACCOUNT_NAME_TAKEN_MESSAGE = "An Account with this name exists already."
ACCOUNT_NAME_BUSY_MESSAGE = "Another request is naming an Account like this; try again."
# Seconds a request waits for another one that is naming an Account the same way.
NAME_LOCK_TIMEOUT = 5


# By site: a worker serving several sites asks each site's own column.
_collation: dict[str, str] = {}


def _customer_name_collation() -> str:
    """The collation of `tabCustomer.customer_name`, which decides what the name comparison calls equal."""

    site = str(getattr(frappe.local, "site", "") or "")
    if site not in _collation:
        rows = frappe.db.sql(
            "SELECT `COLLATION_NAME` FROM `information_schema`.`COLUMNS` WHERE `TABLE_SCHEMA` = DATABASE() "
            "AND `TABLE_NAME` = 'tabCustomer' AND `COLUMN_NAME` = 'customer_name'",
        )
        _collation[site] = (rows[0][0] if rows and rows[0][0] else "utf8mb4_unicode_ci")
    return _collation[site]


def _name_key(name: str) -> str:
    """The lock of a name: keyed by the name as the database compares it (the column's collation: case, accents
    and the width of a character aside), so that two spellings the comparison calls one name take one lock."""

    folded = frappe.db.sql(
        f"SELECT HEX(WEIGHT_STRING(%s COLLATE {_customer_name_collation()}))", (name,),
    )[0][0]
    return "crm-account-name:" + hashlib.sha256(f"{frappe.local.site}:{folded}".encode()).hexdigest()[:48]


def _hold_name(name: str) -> None:
    """Hold the name until this request commits or rolls back, so that two requests naming an Account the same
    way (two creates, a create and a rename) take turns: the second sees what the first committed."""

    key = _name_key(name)
    held = getattr(frappe.local, "crm_account_name_locks", None)
    if held is None:
        held = frappe.local.crm_account_name_locks = set()
    if key in held:
        return
    if frappe.db.sql("SELECT GET_LOCK(%s, %s)", (key, NAME_LOCK_TIMEOUT))[0][0] != 1:
        raise CrmApiException("ACCOUNT_NAME_LOCKED", ACCOUNT_NAME_BUSY_MESSAGE, retryable=True)
    held.add(key)

    def release():
        if key not in held:
            return
        try:
            frappe.db.sql("SELECT RELEASE_LOCK(%s)", (key,))
        finally:
            held.discard(key)

    frappe.db.after_commit.add(release)
    frappe.db.after_rollback.add(release)


def _accounts_named(name: str, *, except_account: str | None = None) -> list[str]:
    """The ids of the Accounts the user may see whose name is this one, case and spacing aside: those this
    request sees (its snapshot and its own writes) and those committed by now, read on a connection of its own,
    as the snapshot (REPEATABLE READ) may predate an Account another request named the same way and committed
    while this one waited for the name."""

    # Every Customer the list shows the user, the ERP ones included: the list has no group filter either.
    where = [
        f"({conditions_for_doctype('Customer')})",
        "LOWER(TRIM(`customer_name`)) = %s",
    ]
    values: list[Any] = [name]
    if except_account:
        where.append("`name` != %s")
        values.append(except_account)
    query = f"SELECT `name` FROM `tabCustomer` WHERE {' AND '.join(where)}"
    names = set(frappe.db.sql(query, values, pluck=True))
    read, close = committed_reader()
    try:
        names.update(row[0] for row in read(query, values))
    finally:
        close()
    return sorted(names)


def _assert_name_free(payload: dict[str, Any], name: str, *, except_account: str | None = None) -> None:
    """An Account named as one the user sees is refused until they say it is another company (`confirmDuplicate`):
    the same name, whatever the case and spacing. The ids they may look at are named, so that they can decide;
    Accounts out of their reach are not compared, as Salesforce's duplicate rules enforce sharing. The short name
    is an alias that companies of one group share, and is not compared. The name is held to the commit, and the
    Accounts compared are those committed by now, so that two requests naming Accounts the same way take turns."""

    normalized = name.strip().lower()
    _hold_name(normalized)
    if payload.get("confirmDuplicate") is True:
        return
    taken = _accounts_named(normalized, except_account=except_account)
    if taken:
        raise CrmApiException("DUPLICATE_ACCOUNT", ACCOUNT_NAME_TAKEN_MESSAGE, field_errors={"name": ", ".join(taken)})


def _require_account(name: str):
    # One answer for an Account that does not exist and for a Private Account of someone else. The id of an
    # Account is its name: two answers would let a Sales user list the company's Accounts by trying names.
    if frappe.db.exists("Customer", name):
        doc = frappe.get_doc("Customer", name)
        if frappe.has_permission("Customer", "read", doc=doc, user=frappe.session.user):
            return doc
    raise CrmApiException("ACCOUNT_NOT_FOUND", ACCOUNT_NOT_FOUND_MESSAGE)


def list_accounts(query: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    assert_capability("account:view")
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    where = [f"({conditions_for_doctype('Customer')})"]
    values: list[Any] = []
    account_id = str(query.get("accountId") or "").strip()
    if account_id:
        where.append("`name` = %s")
        values.append(account_id)
    search = str(query.get("search") or "").strip()
    if search:
        # The owner by the name the pages show (the user's full name) as well as by their id; the search's own
        # `%` and `_` are letters, not wildcards.
        pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(
            "(`customer_name` LIKE %s OR `custom_crm_short_name` LIKE %s OR `custom_crm_owner` LIKE %s "
            "OR `custom_crm_owner` IN (SELECT `name` FROM `tabUser` WHERE `full_name` LIKE %s))"
        )
        values.extend([pattern, pattern, pattern, pattern])
    segment = query.get("segment")
    if segment and segment != "All":
        where.append("`custom_crm_segment` = %s")
        values.append(segment)
    region = collapse_region(query.get("region"))
    if region and region != "All":
        where.append("`custom_crm_region` = %s")
        values.append(matching_region(region, list_regions()) or region)
    city = query.get("city")
    if city and city != "All":
        where.append("`custom_crm_city` = %s")
        values.append(city)
    owner = query.get("owner")
    if owner:
        where.append("`custom_crm_owner` = %s")
        values.append(owner)
    where_sql = " AND ".join(where)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCustomer` WHERE {where_sql}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCustomer` WHERE {where_sql} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]),
        as_dict=True,
    )
    return [serialize_account(frappe.get_doc("Customer", row.name)) for row in rows], total, page, page_size


def create_account(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("account:write")
    ensure_server_generated_id(payload)
    values = _validate_account_input(payload)
    _assert_name_free(payload, values["name"])
    customer_kind = _customer_kind(payload.get("customerKind"))
    savepoint = f"crm_account_create_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        _register_account_segment(values["segment"])
        values["region"] = register_region(values["region"])
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": values["name"],
                "customer_type": "Company",
                "customer_group": "CRM Customers",
                "territory": "CRM Territory",
                "custom_crm_owner": values["owner"],
                "custom_crm_short_name": values["short_name"],
                "custom_crm_segment": values["segment"],
                "custom_crm_tier": values["tier"],
                "custom_crm_city": values["city"],
                "custom_crm_region": values["region"],
                "custom_crm_visibility": values["visibility"],
                "custom_crm_customer_kind": customer_kind,
            }
        ).insert(ignore_permissions=True)
        if doc.custom_crm_owner != frappe.session.user:
            create_notification(
                recipient=doc.custom_crm_owner, category="Account",
                title="Account assigned", message=f"You are now responsible for {doc.customer_name}.",
                route=record_route("/accounts", doc.name), source_doctype="Customer", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        frappe.clear_cache(doctype="Customer")
        raise
    return serialize_account(doc)


def update_account(
    name: str,
    payload: dict[str, Any],
    expected_modified: Any,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    assert_capability("account:write")
    current = _require_account(name)
    if resolve_crm_role() == "Sales" and current.custom_crm_owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the Account owner or a Manager may edit this Account.")
    values = _validate_account_input(payload, current.custom_crm_owner, current.custom_crm_visibility or "Private")
    if values["name"] != current.customer_name:
        _assert_name_free(payload, values["name"], except_account=name)
    doc = lock_document("Customer", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("Customer", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("ACCOUNT_NOT_FOUND", ACCOUNT_NOT_FOUND_MESSAGE)
    savepoint = f"crm_account_update_{frappe.generate_hash(length=8)}"
    previous_owner = doc.custom_crm_owner
    frappe.db.savepoint(savepoint)
    try:
        _register_account_segment(values["segment"])
        values["region"] = register_region(values["region"])
        # Registering a new Select option clears the shared cache, but the
        # locked document still holds its old Meta instance. Keep the lock and
        # version check above; reload with current metadata before validation.
        doc = frappe.get_doc("Customer", name, for_update=True)
        if "customerKind" in payload:
            doc.custom_crm_customer_kind = _customer_kind(payload["customerKind"])
        doc.update(
            {
                "customer_name": values["name"],
                "custom_crm_owner": values["owner"],
                "custom_crm_short_name": values["short_name"],
                "custom_crm_segment": values["segment"],
                "custom_crm_tier": values["tier"],
                "custom_crm_city": values["city"],
                "custom_crm_region": values["region"],
                "custom_crm_visibility": values["visibility"],
            }
        )
        doc.save(ignore_permissions=True)
        if previous_owner != doc.custom_crm_owner and doc.custom_crm_owner != frappe.session.user:
            create_notification(
                recipient=doc.custom_crm_owner, category="Account",
                title="Account reassigned", message=f"You are now responsible for {doc.customer_name}.",
                route=record_route("/accounts", doc.name), source_doctype="Customer", source_name=doc.name,
            )
        if failure_injector:
            failure_injector("after_account_update")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        frappe.clear_cache(doctype="Customer")
        raise
    doc.reload()
    return serialize_account(doc)


def get_account_360(name: str) -> dict[str, Any]:
    assert_capability("account:view")
    doc = _require_account(name)
    from rayher_crm.services.bookings import list_bookings
    from rayher_crm.services.contacts import contacts_for_account
    from rayher_crm.services.demo_requests import list_demo_requests
    from rayher_crm.services.evaluations import list_evaluations
    from rayher_crm.services.opportunities import list_strategy_opportunities
    from rayher_crm.services.pipeline import actions_for_account, list_pipeline
    from rayher_crm.services.quotations import quotations_for_account
    from rayher_crm.services.sites import can_read_site_data, sites_for_account
    from rayher_crm.services.visits import list_visits

    pipeline = list_pipeline({"accountId": name})
    strategy_opportunities = [item for item in list_strategy_opportunities() if item["accountId"] == name]
    demo_requests = read_all_pages(list_demo_requests, {"accountId": name})
    evaluations = read_all_pages(list_evaluations, {"accountId": name})
    visits = read_all_pages(list_visits, {"accountId": name})
    completed_visit_dates = sorted(
        item["date"] for item in visits if item["status"] in {"Visited", "Minutes Submitted", "Manager Reviewed"}
    )
    capabilities = capabilities_for_user()
    can_read_business_data = can_read_site_data(name)

    return {
        "account": serialize_account(doc),
        "sites": sites_for_account(name) if can_read_business_data else [],
        "contacts": contacts_for_account(name) if "contact:view" in capabilities else [],
        "requirements": [],
        "opportunities": pipeline["opportunities"],
        "bookings": [item for item in list_bookings() if item["accountId"] == name],
        "demoRequests": demo_requests,
        "evaluations": evaluations,
        "quotations": quotations_for_account(name) if "quotation:view" in capabilities else [],
        "contracts": [],
        "actions": actions_for_account(name, strategy_opportunities),
        "visits": visits,
        "summary": {
            "activeDemos": sum(item["status"] not in {"Accepted", "Rejected"} for item in evaluations),
            "contractsAtRisk": 0,
            "lastVisit": completed_visit_dates[-1] if completed_visit_dates else "—",
        },
    }
