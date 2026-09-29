"""Database-row locking for CRM optimistic concurrency control."""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CRM_ERROR_CODES, CrmApiException
from rayher_crm.services.common import normalize_expected_modified, to_iso_timestamp


LOCKABLE_DOCTYPES = frozenset({
    "Customer", "Contact", "Lead", "CRM Opportunity", "CRM Booking", "CRM Installed Tool",
    "CRM Demo Request", "CRM Evaluation", "CRM Demo Artifact", "CRM Visit", "CRM Quotation Version",
    "CRM RFQ", "CRM Cockpit Target", "CRM Probability Recovery",
    "CRM Opportunity Saved Query", "CRM Opportunity Loss Review", "CRM Warning Handling",
})


def lock_document(
    doctype: str,
    name: str,
    expected_modified: Any,
    not_found_code: str,
):
    if doctype not in LOCKABLE_DOCTYPES:
        raise ValueError(f"Unsupported lock DocType: {doctype}")
    if not_found_code != "NOT_FOUND":
        raise ValueError(f"Invalid not-found code: {not_found_code}")

    expected = normalize_expected_modified(expected_modified)
    rows = frappe.db.sql(
        f"SELECT modified FROM `tab{doctype}` WHERE name = %s FOR UPDATE",
        (name,),
        as_dict=True,
    )
    if not rows:
        raise CrmApiException(not_found_code, f"{doctype} was not found.")

    actual = to_iso_timestamp(rows[0].modified)
    if actual != expected:
        raise CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
    return frappe.get_doc(doctype, name)
