"""Opportunities board: one combined query with matching totals, plus personal saved queries.

Every read starts from the CRM row scope of ``CRM Opportunity`` (the same SQL condition as the
Opportunity list and detail), and ``opportunity_board_rules`` only ever sees those rows, so a
query's ``scope`` and conditions can narrow what a user reads but never widen it.

Saved queries live in ``CRM Opportunity Saved Query``. That DocType grants no role any
permission, so the standard document API cannot list or change them. These services
allow owner-only changes and explicitly shared, read-only access to definitions.
Every execution still uses the recipient's own current Opportunity scope.
"""

from __future__ import annotations

import json
import re
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services import cockpit
from rayher_crm.services import opportunity_board_rules as rules
from rayher_crm.services.common import as_payload, normalize_expected_modified, normalize_pagination, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.equipment import list_equipment_types

SAVED_QUERY = "CRM Opportunity Saved Query"
MAX_SAVED_QUERIES = 100
MAX_QUERY_NAME = 80
# Room for lossless expansion of legacy region/group predicates during migration.
MAX_DEFINITION_BYTES = 256 * 1024
MAX_ID = 140
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

# `tabCRM Opportunity` stays unaliased: the row scope condition refers to it by that name. An archived Opportunity
# leaves the board, and so do the deals of an archived Account (closed, or archived themselves), as they leave the
# cockpit's other figures.
_ROWS_SQL = """
SELECT `tabCRM Opportunity`.`name` AS `name`, `tabCRM Opportunity`.`title` AS `title`,
    `tabCRM Opportunity`.`account` AS `account`, `crm_board_customer`.`customer_name` AS `customer_name`,
    `crm_board_customer`.`custom_crm_region` AS `region`, `crm_board_customer`.`custom_crm_segment` AS `market`,
    `tabCRM Opportunity`.`opportunity_owner` AS `opportunity_owner`, `tabCRM Opportunity`.`stage` AS `stage`,
    `tabCRM Opportunity`.`stage_changed_at` AS `stage_changed_at`,
    `tabCRM Opportunity`.`creation` AS `creation`, `tabCRM Opportunity`.`po_date` AS `po_date`,
    `tabCRM Opportunity`.`probability_level` AS `probability_level`, `tabCRM Opportunity`.`tool_type` AS `tool_type`,
    CAST(`tabCRM Opportunity`.`amount` AS CHAR) AS `amount`, `tabCRM Opportunity`.`currency` AS `currency`,
    CAST(`tabCRM Opportunity`.`amount_cny` AS CHAR) AS `amount_cny`
FROM `tabCRM Opportunity`
LEFT JOIN `tabCustomer` AS `crm_board_customer` ON `crm_board_customer`.`name` = `tabCRM Opportunity`.`account`
WHERE `tabCRM Opportunity`.`archived` = 0 AND COALESCE(`crm_board_customer`.`custom_crm_archived`, 0) = 0 AND ({scope})
"""
_ACTIONS_SQL = """
SELECT `crm_board_action`.`name` AS `name`, `crm_board_action`.`opportunity` AS `opportunity`,
    `crm_board_action`.`title` AS `title`, `crm_board_action`.`due` AS `due`,
    `crm_board_action`.`status` AS `status`, `crm_board_action`.`archived` AS `archived`
FROM `tabCRM Opportunity Action` AS `crm_board_action`
INNER JOIN `tabCRM Opportunity` ON `tabCRM Opportunity`.`name` = `crm_board_action`.`opportunity`
LEFT JOIN `tabCustomer` AS `crm_board_action_customer` ON `crm_board_action_customer`.`name` = `tabCRM Opportunity`.`account`
WHERE `crm_board_action`.`status` IN ('Open', 'In Progress', 'Blocked', 'Rescheduled') AND `crm_board_action`.`archived` = 0
  AND `tabCRM Opportunity`.`archived` = 0 AND COALESCE(`crm_board_action_customer`.`custom_crm_archived`, 0) = 0 AND ({scope})
"""


def _require_board_access() -> None:
    assert_capability("deal:view")


def _payload(value: Any) -> dict[str, Any]:
    try:
        return dict(as_payload(value))
    except (ValueError, RecursionError) as exc:  # malformed or absurdly nested JSON text
        raise CrmApiException("VALIDATION_ERROR", "A JSON object is required.") from exc


def _validated(check, prefix=""):
    try:
        return check()
    except rules.BoardQueryError as exc:
        field = f"{prefix}.{exc.field}" if prefix and exc.field not in rules.ROOTS else exc.field
        raise CrmApiException("VALIDATION_ERROR", str(exc), field_errors={field: str(exc)}) from exc


def _option(value: str, label: str | None = None) -> dict[str, str]:
    return {"value": value, "label": label or value}


def _board_context(*, include_rows: bool) -> dict[str, Any]:
    """The options a query is checked against and, when asked, the rows the user may read."""

    scope = conditions_for_doctype("CRM Opportunity")
    now = frappe.utils.now_datetime()
    opportunities = frappe.db.sql(_ROWS_SQL.format(scope=scope), as_dict=True)
    # Region readiness, the region list and the market list follow the Review filter exactly.
    _customers, _people, review_filters = cockpit.options()
    role = resolve_crm_role()
    sales_ids = {row["opportunity_owner"] for row in opportunities if row["opportunity_owner"]}
    if role == "Manager":
        sales_ids |= {row["id"] for row in review_filters["sales"]}
    elif role == "Sales":
        sales_ids.add(frappe.session.user)
    names = {
        row.name: row.full_name
        for row in frappe.get_all("User", filters={"name": ["in", sorted(sales_ids)]}, fields=["name", "full_name"])
    } if sales_ids else {}
    options = {
        "sales": sales_ids,
        # The equipment catalog: presets, then custom types; every stored value is one of them.
        "equipment": list_equipment_types(),
        "regions": review_filters["regions"],
        "regionParents": review_filters.get("regionParents", {}),
        "markets": review_filters["markets"],
        "regionReady": bool(review_filters["regionReady"]),
    }
    if include_rows:
        from rayher_crm.services.board_activity import attach
        attach(opportunities, now)
    return {
        "asOf": to_iso_timestamp(now),
        "rows": rules.board_rows(
            opportunities, names, frappe.db.sql(_ACTIONS_SQL.format(scope=scope), as_dict=True), now,
            equipment=options["equipment"], region_parents=options["regionParents"],
        ) if include_rows else [],
        "options": options,
        "filters": {
            "sales": sorted((_option(sales_id, names.get(sales_id)) for sales_id in sales_ids),
                            key=lambda item: (item["label"].casefold(), item["value"])),
            # The sales territory tree in display order; regionParents is the parent of each value that has one.
            "regions": [_option(value) for value in options["regions"]],
            "regionParents": options["regionParents"],
            "markets": [_option(value) for value in options["markets"]],
            "equipment": [_option(value) for value in options["equipment"]],
            "stages": [_option(stage, label) for stage, label in rules.STAGE_LABELS.items()],
            "probabilityLevels": [
                _option(level, rules.PROBABILITY_LABELS[level]) for level in rules.PROBABILITY_FILTER_LEVELS
            ],
            "regionReady": options["regionReady"],
        },
    }


def query_opportunities(input_value: Any) -> tuple[dict[str, Any], int, int, int]:
    _require_board_access()
    payload = _payload(input_value)
    saved_definition = _consume_saved_reference(payload)
    context = _board_context(include_rows=True)
    _allow_saved_sales(context, saved_definition)
    query = _validated(lambda: rules.validate_query(payload, context["options"]))
    page, page_size, offset = normalize_pagination(payload.get("page"), payload.get("pageSize"))
    ordered, summary, groups = rules.build_board(context["rows"], query)
    data = {
        "items": [row.dto for row in ordered[offset:offset + page_size]],
        "asOf": context["asOf"],
        "summary": summary,
        "groups": groups,
    }
    return data, len(ordered), page, page_size


def export_opportunities(input_value):
    """One request/read transaction, one ordered set, one summary and asOf.

    MariaDB 10.6 uses REPEATABLE READ: all ordinary source reads share the
    request's read view. There are no browser pagination windows or stored row
    snapshots; every export re-evaluates the caller's scope and saved access.
    """
    _require_board_access()
    payload = _payload(input_value)
    saved_definition = _consume_saved_reference(payload)
    context = _board_context(include_rows=True)
    _allow_saved_sales(context, saved_definition)
    query = _validated(lambda: rules.validate_query(payload, context["options"]))
    rows, summary, groups = rules.build_board(context["rows"], query)
    return {"items": [row.dto for row in rows], "summary": summary, "groups": groups, "asOf": context["asOf"]}


def _consume_saved_reference(payload, *, for_update=False):
    reference = payload.pop("savedQuery", None)
    if reference is None:
        return
    if not isinstance(reference, dict) or set(reference) != {"id", "modified"}:
        raise CrmApiException("VALIDATION_ERROR", "savedQuery must contain an id and modified version.")
    query_id = _query_id(reference["id"])
    # Shared current reads allow simultaneous exports while preventing revoke,
    # edit and delete until readers finish. A save takes X locks from the start
    # so it never upgrades a shared lock when updating its source query.
    lock = "FOR UPDATE" if for_update else "LOCK IN SHARE MODE"
    rows = frappe.db.sql("SELECT name, query_owner, modified, definition FROM `tabCRM Opportunity Saved Query` WHERE name=%s " + lock,
                         (query_id,), as_dict=True)
    if not rows:
        raise CrmApiException("NOT_FOUND", "Saved query was not found.")
    row = rows[0]
    recipients = frappe.db.sql("""SELECT user FROM `tabCRM Query Recipient`
        WHERE parent=%s AND parenttype=%s AND parentfield='recipients' """ + lock, (row.name, SAVED_QUERY), pluck=True)
    if row.query_owner != frappe.session.user and frappe.session.user not in recipients:
        raise CrmApiException("NOT_FOUND", "Saved query was not found.")
    if to_iso_timestamp(row.modified) != normalize_expected_modified(reference["modified"]):
        raise CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
    return json.loads(row.definition)


def _allow_saved_sales(context, definition):
    """A shared predicate may mention colleagues whose rows the reader cannot see.

    Only values in the authorized, version-matched source definition supplement
    validation. Row access was already enforced independently by _board_context.
    """
    if not definition:
        return
    values = set(definition.get("scope", {}).get("sales", []))

    def visit(group):
        for node in group.get("conditions", []):
            if "conditions" in node:
                visit(node)
            elif node.get("field") == "sales" and isinstance(node.get("value"), list):
                values.update(node["value"])
    visit(definition)
    context["options"]["sales"] = set(context["options"]["sales"]) | values


def get_opportunity_filters() -> dict[str, Any]:
    _require_board_access()
    return _board_context(include_rows=False)["filters"]


# ---------------------------------------------------------------- saved queries

def _saved_dto(row, recipients=None) -> dict[str, Any]:
    mine = row.query_owner == frappe.session.user
    if recipients is None:
        recipients = [child.user for child in row.get("recipients", [])]
    return {
        "id": row.name,
        "name": row.query_name,
        "definition": json.loads(row.definition),
        "modified": to_iso_timestamp(row.modified),
        "owner": row.query_owner, "readOnly": not mine,
        # Sharing is a set of other identities. Native User merges can retain
        # duplicate/self child Links; expose their effective access without a
        # write during GET. The next versioned share save replaces those rows.
        "recipients": sorted(set(recipients) - {row.query_owner}) if mine else [],
    }


def _query_id(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > MAX_ID:
        raise CrmApiException("VALIDATION_ERROR", "id must be a saved query id.", field_errors={"id": "Invalid value"})
    return text


def _query_name(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > MAX_QUERY_NAME or _CONTROL_CHARACTERS.search(text):
        raise CrmApiException(
            "VALIDATION_ERROR", f"name must be 1 to {MAX_QUERY_NAME} characters without control characters.",
            field_errors={"name": "Invalid value"},
        )
    return text


def _lock_own_query(query_id: str, user: str, expected_modified: Any):
    # Someone else's query answers exactly like a missing one, before any version check.
    owner = frappe.db.get_value(SAVED_QUERY, query_id, "query_owner", for_update=True)
    if owner != user:
        raise CrmApiException("NOT_FOUND", "Saved query was not found.")
    lock_document(SAVED_QUERY, query_id, expected_modified, "NOT_FOUND")
    return frappe.get_doc(SAVED_QUERY, query_id, for_update=True)


def _lock_query_writes():
    # A copy locks another owner's source as well as the writer's query range.
    # Serializing these infrequent definition mutations before either lock avoids
    # reciprocal-copy cycles. Share and delete follow the same order. Reads never
    # take this mutex and retain compatible shared current-read locks.
    # Do not use a DocType/document row: native User.after_rename scans every
    # table's owner/modified_by fields and can wait on that row while holding
    # Users and recipient Links. Series has no such audit fields. This reserved
    # non-counter row takes one transaction-scoped X lock, including first use;
    # INSERT IGNORE + SELECT FOR UPDATE would risk shared-lock upgrades.
    frappe.db.sql("""INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, 0)
        ON DUPLICATE KEY UPDATE `current`=`current`""", ("rayher_crm.saved_query_write_lock",))


def _query_user_identity(user):
    return (user.name, frappe.utils.get_datetime(user.creation)) if user and user.creation else None


def _query_author_changed():
    # A cache miss under an old DB snapshot can repopulate the shared cache with
    # the former User. Invalidate it for the next request; never retry this write.
    frappe.clear_document_cache("User", frappe.session.user)
    raise CrmApiException("VALIDATION_ERROR", "Your user identity changed. Sign in again before changing saved queries.")


def _query_author_snapshot():
    fields = ["name", "creation"]
    snapshot = _query_user_identity(frappe.db.get_value("User", frappe.session.user, fields, as_dict=True))
    # Cookie authentication retains the original User document in request-local
    # cache even when it needed no DB snapshot. API-key authentication uses
    # ordinary DB reads. Require both pieces of identity evidence to agree.
    cached = _query_user_identity(frappe.get_cached_value("User", frappe.session.user, fields, as_dict=True))
    if not snapshot or snapshot != cached:
        _query_author_changed()
    return snapshot


def _lock_query_users(author_snapshot, recipients=()):
    # Native rename/merge takes Users before rewriting query Links. Include the
    # author in the same database-ordered set as recipients: locking the author
    # separately could invert a native merge between author and recipient.
    requested = sorted({frappe.session.user, *recipients})
    placeholders = ", ".join(["%s"] * len(requested))
    rows = frappe.db.sql(
        f"SELECT name, creation, name=%s AS is_author FROM `tabUser` "
        f"WHERE name IN ({placeholders}) ORDER BY name FOR UPDATE",
        (frappe.session.user, *requested), as_dict=True,
    )
    author = next((row for row in rows if row.is_author), None)
    if not author_snapshot or _query_user_identity(author) != author_snapshot:
        _query_author_changed()
    return author.name


def list_opportunity_queries() -> dict[str, Any]:
    _require_board_access()
    rows = frappe.db.sql("""SELECT q.name, q.query_name, q.definition, q.modified, q.query_owner
        FROM `tabCRM Opportunity Saved Query` q WHERE q.query_owner=%s OR EXISTS (
            SELECT 1 FROM `tabCRM Query Recipient` r WHERE r.parent=q.name
            AND r.parenttype=%s AND r.parentfield='recipients' AND r.user=%s)""",
        (frappe.session.user, SAVED_QUERY, frappe.session.user), as_dict=True)
    mine = [row.name for row in rows if row.query_owner == frappe.session.user]
    recipients = frappe.get_all("CRM Query Recipient", filters={"parent": ["in", mine], "parenttype": SAVED_QUERY, "parentfield": "recipients"},
                                fields=["parent", "user"], limit_page_length=0) if mine else []
    items = [_saved_dto(row, [r.user for r in recipients if r.parent == row.name]) for row in rows]
    return {"items": sorted(items, key=lambda item: (item["name"].casefold(), item["id"]))}


def save_opportunity_query(query_id: Any, input_value: Any, expected_modified: Any = None) -> dict[str, Any]:
    _require_board_access()
    author_snapshot = _query_author_snapshot()
    _lock_query_writes()
    user = _lock_query_users(author_snapshot)
    payload = _payload(input_value)
    saved_definition = _consume_saved_reference(payload, for_update=True)
    unknown = sorted(str(key) for key in payload if key not in ("name", "definition"))
    if unknown:
        raise CrmApiException("VALIDATION_ERROR", f"Unknown field {unknown[0]}.", field_errors={unknown[0]: "Unknown field"})
    name = _query_name(payload.get("name"))
    target = _query_id(query_id) if query_id not in (None, "") else None
    if not target and expected_modified not in (None, ""):
        raise CrmApiException("VALIDATION_ERROR", "expectedModified is only sent when updating a saved query.")
    context = _board_context(include_rows=False)
    _allow_saved_sales(context, saved_definition)
    definition = _validated(lambda: rules.validate_definition(payload.get("definition"), context["options"]), "definition")
    text = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text.encode("utf-8")) > MAX_DEFINITION_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "The saved query definition is too large.")

    # The mutation mutex protects the name/count checks. Use a current read even
    # if the request established its ordinary snapshot before acquiring the mutex.
    doc = _lock_own_query(target, user, expected_modified) if target else None
    target = doc.name if doc else None  # the stored id; MariaDB matched the client's id case-insensitively
    mine = frappe.db.sql(
        f"SELECT `name`, `query_name` FROM `tab{SAVED_QUERY}` WHERE `query_owner` = %s FOR UPDATE",
        (user,), as_dict=True,
    )
    if doc is None and len(mine) >= MAX_SAVED_QUERIES:
        raise CrmApiException("VALIDATION_ERROR", f"A user can keep at most {MAX_SAVED_QUERIES} saved queries.")
    if any(row.name != target and row.query_name.strip().casefold() == name.casefold() for row in mine):
        raise CrmApiException("CONFLICT", "Another saved query already has this name.", field_errors={"name": "Duplicate"})
    if doc is None:
        doc = frappe.get_doc({"doctype": SAVED_QUERY, "query_owner": user, "query_name": name, "definition": text})
        doc.insert(ignore_permissions=True)
    else:
        doc.query_name = name
        doc.definition = text
        doc.save(ignore_permissions=True, ignore_version=False)
    return _saved_dto(doc)


def delete_opportunity_query(query_id: Any, expected_modified: Any) -> dict[str, str]:
    _require_board_access()
    author_snapshot = _query_author_snapshot()
    _lock_query_writes()
    user = _lock_query_users(author_snapshot)
    doc = _lock_own_query(_query_id(query_id), user, expected_modified)
    frappe.delete_doc(SAVED_QUERY, doc.name, ignore_permissions=True)
    return {"id": doc.name, "status": "Deleted"}


def query_recipient_options():
    _require_board_access()
    from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE
    roles = frappe.get_all("Has Role", filters={"parenttype": "User", "role": ["in", list(CRM_ROLE_TO_PROFILE)]}, fields=["parent", "role"], limit_page_length=0)
    by_user = {}
    for row in roles:
        by_user.setdefault(row.parent, set()).add(row.role)
    eligible = [user for user, assigned in by_user.items() if len(assigned) == 1 and user != frappe.session.user]
    users = frappe.get_all("User", filters={"name": ["in", eligible], "enabled": 1}, fields=["name", "full_name"], limit_page_length=0) if eligible else []
    return {"items": sorted([{"value": user.name, "label": user.full_name or user.name} for user in users], key=lambda row: (row["label"].casefold(), row["value"]))}


def share_opportunity_query(query_id, recipients, expected_modified):
    _require_board_access()
    author_snapshot = _query_author_snapshot()
    _lock_query_writes()
    from rayher_crm.permissions.roles import CRM_ROLE_TO_PROFILE
    if isinstance(recipients, str):
        try:
            recipients = json.loads(recipients)
        except (ValueError, TypeError) as exc:
            raise CrmApiException("VALIDATION_ERROR", "Choose a list of recipients.") from exc
    if not isinstance(recipients, list) or len(recipients) > 100 or any(not isinstance(user, str) or not user.strip() or len(user) > 140 for user in recipients):
        raise CrmApiException("VALIDATION_ERROR", "Choose at most 100 recipient users.")
    requested_users = sorted(set(recipients))
    author = _lock_query_users(author_snapshot, requested_users)
    canonical = set()
    for requested in requested_users:
        user = frappe.db.get_value("User", requested, ["name", "enabled"], as_dict=True, for_update=True)
        roles = frappe.db.sql("SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='User' FOR UPDATE", (user.name if user else requested,), pluck=True)
        if not user or not user.enabled or len(set(roles).intersection(CRM_ROLE_TO_PROFILE)) != 1 or user.name == author:
            raise CrmApiException("VALIDATION_ERROR", "Recipients must be other enabled users with exactly one CRM role.")
        canonical.add(user.name)
    doc = _lock_own_query(_query_id(query_id), author, expected_modified)
    doc.set("recipients", [{"user": user} for user in sorted(canonical)])
    doc.save(ignore_permissions=True, ignore_version=False)
    return _saved_dto(doc)
