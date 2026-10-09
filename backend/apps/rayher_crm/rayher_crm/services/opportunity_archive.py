"""The archive of a CRM Opportunity: the sentences, and the check every writer runs.

An Opportunity archived by a Manager (in place of the delete there was) is read-only until it is restored,
and takes no new record naming it. Nothing of it is in progress once it is archived: the archive waits for its
Bookings to be cancelled and for its Demo Requests and demo tests to end. The archive itself is in services/opportunities.py; this module holds
what the other services (bookings, visits, demo requests, quotations and their plans, RFQs, status, documents, warnings, events)
import without importing the Opportunity service, which imports some of them.
"""

from __future__ import annotations

from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException


ARCHIVED_OPPORTUNITY_EDIT = "An archived Opportunity cannot be changed; a Manager can restore it from the archive."
ARCHIVED_OPPORTUNITY_LINK = "An archived Opportunity takes no new record; a Manager can restore it from the archive."
OPPORTUNITY_WITH_BOOKING_ARCHIVE = (
    "An Opportunity with a Booking that is not cancelled cannot be archived; cancel the Booking first."
)
OPPORTUNITY_WITH_DEMO_REQUEST_ARCHIVE = (
    "An Opportunity with a Demo Request in progress cannot be archived; cancel the Demo Request first."
)
OPPORTUNITY_WITH_DEMO_TEST_ARCHIVE = (
    "An Opportunity with a demo test in progress cannot be archived; finish or terminate the demo test first."
)


def assert_opportunity_not_archived(doc_or_flag: Any, message: str = ARCHIVED_OPPORTUNITY_EDIT) -> None:
    """Refuse a write on, or a new record for, an archived Opportunity. Takes the document or its flag."""

    archived = doc_or_flag.get("archived") if hasattr(doc_or_flag, "get") else doc_or_flag
    if archived:
        raise CrmApiException("INVALID_TRANSITION", message)


def opportunity_archived(name: str, *, for_update: bool = False) -> bool:
    """Whether the Opportunity is archived, as committed when read under its row lock (`for_update`)."""

    return bool(frappe.db.get_value("CRM Opportunity", name, "archived", for_update=for_update))
