"""Opportunities board: one combined query with matching totals, plus personal saved queries.

Every read starts from the CRM row scope of ``CRM Opportunity`` (the same SQL condition as the
Opportunity list and detail), and ``opportunity_board_rules`` only ever sees those rows, so a
query's ``scope`` and conditions can narrow what a user reads but never widen it.

Saved queries live in ``CRM Opportunity Saved Query``. That DocType grants no role any
permission, so the standard document API cannot list or change them; only these services
do, and only for the user who owns them. Another user's query answers as not found.
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
from rayher_crm.services.common import as_payload, normalize_pagination, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.equipment import list_equipment_types

SAVED_QUERY = "CRM Opportunity Saved Query"
MAX_SAVED_QUERIES = 100
MAX_QUERY_NAME = 80
MAX_DEFINITION_BYTES = 64 * 1024
MAX_ID = 140
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")

# `tabCRM Opportunity` stays unaliased: the row scope condition refers to it by that name.
_ROWS_SQL = """
SELECT `tabCRM Opportunity`.`name` AS `name`, `tabCRM Opportunity`.`title` AS `title`,
    `tabCRM Opportunity`.`account` AS `account`, `crm_board_customer`.`customer_name` AS `customer_name`,
    `crm_board_customer`.`custom_crm_region` AS `region`, `crm_board_customer`.`custom_crm_segment` AS `market`,
    `tabCRM Opportunity`.`opportunity_owner` AS `opportunity_owner`, `tabCRM Opportunity`.`stage` AS `stage`,
    `tabCRM Opportunity`.`stage_changed_at` AS `stage_changed_at`,
    `tabCRM Opportunity`.`probability_level` AS `probability_level`, `tabCRM Opportunity`.`tool_type` AS `tool_type`,
    CAST(`tabCRM Opportunity`.`amount` AS CHAR) AS `amount`, `tabCRM Opportunity`.`currency` AS `currency`,
    CAST(`tabCRM Opportunity`.`amount_cny` AS CHAR) AS `amount_cny`
FROM `tabCRM Opportunity`
LEFT JOIN `tabCustomer` AS `crm_board_customer` ON `crm_board_customer`.`name` = `tabCRM Opportunity`.`account`
WHERE ({scope})
"""
_ACTIONS_SQL = """
SELECT `crm_board_action`.`name` AS `name`, `crm_board_action`.`opportunity` AS `opportunity`,
    `crm_board_action`.`title` AS `title`, `crm_board_action`.`due` AS `due`,
    `crm_board_action`.`status` AS `status`, `crm_board_action`.`archived` AS `archived`
FROM `tabCRM Opportunity Action` AS `crm_board_action`
INNER JOIN `tabCRM Opportunity` ON `tabCRM Opportunity`.`name` = `crm_board_action`.`opportunity`
WHERE `crm_board_action`.`status` = 'Open' AND `crm_board_action`.`archived` = 0 AND ({scope})
"""


def _require_board_access() -> None:
    assert_capability("deal:view")


def _payload(value: Any) -> dict[str, Any]:
    try:
        return as_payload(value)
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
    context = _board_context(include_rows=True)
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


def get_opportunity_filters() -> dict[str, Any]:
    _require_board_access()
    return _board_context(include_rows=False)["filters"]


# ---------------------------------------------------------------- saved queries

def _saved_dto(row) -> dict[str, Any]:
    return {
        "id": row.name,
        "name": row.query_name,
        "definition": json.loads(row.definition),
        "modified": to_iso_timestamp(row.modified),
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
    return lock_document(SAVED_QUERY, query_id, expected_modified, "NOT_FOUND")


def list_opportunity_queries() -> dict[str, Any]:
    _require_board_access()
    rows = frappe.get_all(
        SAVED_QUERY, filters={"query_owner": frappe.session.user},
        fields=["name", "query_name", "definition", "modified"], limit_page_length=0,
    )
    items = [_saved_dto(row) for row in rows]
    return {"items": sorted(items, key=lambda item: (item["name"].casefold(), item["id"]))}


def save_opportunity_query(query_id: Any, input_value: Any, expected_modified: Any = None) -> dict[str, Any]:
    _require_board_access()
    user = frappe.session.user
    payload = _payload(input_value)
    unknown = sorted(str(key) for key in payload if key not in ("name", "definition"))
    if unknown:
        raise CrmApiException("VALIDATION_ERROR", f"Unknown field {unknown[0]}.", field_errors={unknown[0]: "Unknown field"})
    name = _query_name(payload.get("name"))
    target = _query_id(query_id) if query_id not in (None, "") else None
    if not target and expected_modified not in (None, ""):
        raise CrmApiException("VALIDATION_ERROR", "expectedModified is only sent when updating a saved query.")
    context = _board_context(include_rows=False)
    definition = _validated(lambda: rules.validate_definition(payload.get("definition"), context["options"]), "definition")
    text = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text.encode("utf-8")) > MAX_DEFINITION_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "The saved query definition is too large.")

    # One user's saves run one at a time, so the name check and the count limit hold. The reads
    # above already fixed this transaction's snapshot, so the user's queries are read with a
    # locking read, which sees rows another save committed while this one waited for the lock.
    frappe.db.get_value("User", user, "name", for_update=True)
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
        doc.save(ignore_permissions=True)
    return _saved_dto(doc)


def delete_opportunity_query(query_id: Any, expected_modified: Any) -> dict[str, str]:
    _require_board_access()
    doc = _lock_own_query(_query_id(query_id), frappe.session.user, expected_modified)
    frappe.delete_doc(SAVED_QUERY, doc.name, ignore_permissions=True)
    return {"id": doc.name, "status": "Deleted"}
