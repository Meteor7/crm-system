"""Permission-preserving wrappers for Frappe link search endpoints."""

from __future__ import annotations

import frappe
from frappe.desk.search import build_for_autosuggest, search_widget as frappe_search_widget
from frappe.model.db_query import DatabaseQuery


_WAREHOUSE_ADDRESS_QUERY = "erpnext.controllers.queries.get_warehouse_address"
# Current Frappe 15 reads a non-positive page_length as link validation and caps it at
# frappe.desk.search.PAGE_LENGTH_FOR_LINK_VALIDATION; the pinned release predates that name.
_LINK_VALIDATION_PAGE_LENGTH = 25_000


def _address_link_rows(
    filters, txt, start, page_length, reference_doctype, *, as_dict=False, warehouse_lookup=False,
):
    from rayher_crm.permissions.scope import address_link_query_scope

    filters = list(filters)
    filters.extend([["Address", "disabled", "=", 0], ["Address", "name", "like", f"%{txt}%"]])
    page_length = frappe.utils.cint(page_length)
    if page_length <= 0:
        # DatabaseQuery drops the LIMIT clause for 0 and MariaDB refuses a negative one.
        page_length = _LINK_VALIDATION_PAGE_LENGTH
    with address_link_query_scope(warehouse_lookup=warehouse_lookup):
        return frappe.get_list(
            "Address", fields=["name"], filters=filters, distinct=True,
            order_by="name", limit_start=frappe.utils.cint(start),
            limit_page_length=page_length,
            reference_doctype=reference_doctype, ignore_permissions=False,
            as_list=not as_dict,
        )


def _name_only_address_filters(filters):
    """Selection grants may filter identifiers, not inspect arbitrary fields."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
    if not filters:
        return []
    if isinstance(filters, dict):
        from frappe.utils.data import make_filter_tuple

        filters = [make_filter_tuple("Address", key, value) for key, value in filters.items()]
    if not isinstance(filters, list):
        frappe.throw("Address Link filters must use name or disabled.")
    normalized = []
    for condition in filters:
        if not isinstance(condition, (list, tuple)) or len(condition) not in (3, 4):
            frappe.throw("Address Link filters must use name or disabled.")
        condition = list(condition)
        if len(condition) == 3:
            condition.insert(0, "Address")
        if condition[0] != "Address" or condition[1] not in {"name", "disabled"}:
            frappe.throw("Address Link filters must use name or disabled.")
        normalized.append(condition)
    return normalized


def _rayher_permission_query_handlers(doctype: str) -> tuple[str, ...]:
    handlers = frappe.get_hooks("permission_query_conditions", {}).get(doctype, ())
    if isinstance(handlers, str):
        handlers = (handlers,)
    return tuple(str(handler) for handler in handlers if str(handler).startswith("rayher_crm."))


def _has_rayher_permission_query(doctype: str) -> bool:
    return bool(_rayher_permission_query_handlers(doctype))


def _search_scope_requirements(
    doctype: str, reference_doctype: str | None = None,
) -> tuple[bool, bool]:
    """Return whether to enforce row permissions and replace a custom query."""

    # Frappe authorises a child table through its parent DocType alone, so the
    # flag would list every row of every parent, whether or not a CRM hook
    # covers the table (Communication Link, Event Participants, ...).
    if frappe.get_meta(doctype).istable:
        return True, _has_rayher_permission_query(doctype)
    handlers = _rayher_permission_query_handlers(doctype)
    if not handlers:
        return False, False
    user = frappe.session.user
    has_crm_rule = False
    for handler in handlers:
        condition = str(frappe.call(frappe.get_attr(handler), user, doctype=doctype) or "").strip()
        has_crm_rule = has_crm_rule or bool(condition)
        if condition not in {"", "1=1"}:
            return True, True
    # A CRM Manager's predicate may be unrestricted while native User
    # Permissions, owner grants or a share-only grant still limit the rows.
    # Inspect those native restrictions without evaluating the CRM hooks again.
    native_query = DatabaseQuery(doctype, user=user)
    native_query.reference_doctype = reference_doctype or doctype
    native_query.build_match_conditions(as_condition=False)
    # An empty CRM hook leaves ordinary ERP custom queries intact. A CRM rule
    # such as Manager's 1=1 still retains its native User Permission limits.
    native_scope = bool(native_query.match_conditions or native_query.conditions)
    return native_scope, native_scope and has_crm_rule


@frappe.whitelist()
def search_link(
    doctype: str,
    txt: str,
    query: str | None = None,
    filters: str | dict | list | None = None,
    page_length: int = 10,
    searchfield: str | None = None,
    reference_doctype: str | None = None,
    ignore_user_permissions: bool = False,
):
    results = search_widget(
        doctype,
        txt.strip(),
        query,
        searchfield=searchfield,
        page_length=page_length,
        filters=filters,
        reference_doctype=reference_doctype,
        ignore_user_permissions=ignore_user_permissions,
    )
    return build_for_autosuggest(results, doctype=doctype)


@frappe.whitelist()
def search_widget(
    doctype: str,
    txt: str,
    query: str | None = None,
    searchfield: str | None = None,
    start: int = 0,
    page_length: int = 10,
    filters: str | None | dict | list = None,
    filter_fields=None,
    as_dict: bool = False,
    reference_doctype: str | None = None,
    ignore_user_permissions: bool = False,
):
    enforce_row_permissions, replace_custom_query = _search_scope_requirements(doctype, reference_doctype)
    if doctype == "Address":
        from rayher_crm.permissions.scope import address_link_requires_name_only

        if query == _WAREHOUSE_ADDRESS_QUERY and replace_custom_query:
            warehouse_filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
            if not isinstance(warehouse_filters, dict):
                frappe.throw("Warehouse Address search requires a warehouse filter.")
            return _address_link_rows(
                [
                    ["Dynamic Link", "parenttype", "=", "Address"],
                    ["Dynamic Link", "parentfield", "=", "links"],
                    ["Dynamic Link", "link_doctype", "=", "Warehouse"],
                    ["Dynamic Link", "link_name", "=", warehouse_filters.get("warehouse")],
                ],
                txt, start, page_length, reference_doctype,
                warehouse_lookup=reference_doctype == "Stock Entry",
            )
        if address_link_requires_name_only():
            return _address_link_rows(
                _name_only_address_filters(filters), txt, start, page_length,
                reference_doctype, as_dict=as_dict,
            )
    if enforce_row_permissions:
        # Frappe otherwise turns this caller-controlled flag into
        # get_list(ignore_permissions=True), which skips every row predicate.
        ignore_user_permissions = False
    # Preserve ERP queries whose filter fields only exist in the custom query
    # when no CRM predicate restricts the caller (for example warehouse Address).
    if replace_custom_query:
        query = None
    return frappe_search_widget(
        doctype,
        txt,
        query,
        searchfield=searchfield,
        start=start,
        page_length=page_length,
        filters=filters,
        filter_fields=filter_fields,
        as_dict=as_dict,
        reference_doctype=reference_doctype,
        ignore_user_permissions=ignore_user_permissions,
    )
