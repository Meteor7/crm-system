"""Keep Desk link search inside the CRM row scope.

frappe.desk.search.search_widget turns ignore_user_permissions=1 into
get_list(ignore_permissions=True) as soon as the caller has DocType-level read. That skips
every permission_query_conditions hook, and the CRM row scope lives in those hooks. For a
DocType this app scopes, the flag is dropped here; every other DocType keeps Frappe's behaviour.
"""

from __future__ import annotations

import frappe
from frappe.desk import search as frappe_search


def _ignore_user_permissions(doctype, requested):
    from rayher_crm import hooks

    return False if doctype in hooks.permission_query_conditions else requested


@frappe.whitelist()
def search_link(
    doctype, txt, query=None, filters=None, page_length=10, searchfield=None,
    reference_doctype=None, ignore_user_permissions=False,
):
    return frappe_search.search_link(
        doctype, txt, query=query, filters=filters, page_length=page_length,
        searchfield=searchfield, reference_doctype=reference_doctype,
        ignore_user_permissions=_ignore_user_permissions(doctype, ignore_user_permissions),
    )


@frappe.whitelist()
def search_widget(
    doctype, txt, query=None, searchfield=None, start=0, page_length=10, filters=None,
    filter_fields=None, as_dict=False, reference_doctype=None, ignore_user_permissions=False,
):
    return frappe_search.search_widget(
        doctype, txt, query=query, searchfield=searchfield, start=start, page_length=page_length,
        filters=filters, filter_fields=filter_fields, as_dict=as_dict,
        reference_doctype=reference_doctype,
        ignore_user_permissions=_ignore_user_permissions(doctype, ignore_user_permissions),
    )
