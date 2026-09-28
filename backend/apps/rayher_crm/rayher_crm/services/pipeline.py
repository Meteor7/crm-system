"""Scoped Pipeline read model over canonical CRM Opportunity and Booking rows."""

from __future__ import annotations

from decimal import Decimal
from collections.abc import Callable
from typing import Any

import frappe

from rayher_crm.permissions.roles import assert_capability
from rayher_crm.services.bookings import list_bookings
from rayher_crm.services.opportunities import list_strategy_opportunities
from rayher_crm.services.opportunity_stages import OPEN_STAGES
from rayher_crm.services.money import as_decimal, decimal_string


PIPELINE_READ_LIMIT = 200


def _read_all_pages(read_page: Callable[[dict[str, int]], tuple[list[dict[str, Any]], int, int, int]]):
    """Read a finite snapshot in bounded pages without truncating Pipeline KPI inputs."""

    items, total, _page, _page_size = read_page({"page": 1, "pageSize": PIPELINE_READ_LIMIT})
    page_count = (total + PIPELINE_READ_LIMIT - 1) // PIPELINE_READ_LIMIT
    for page in range(2, page_count + 1):
        page_items, _total, _page, _page_size = read_page({"page": page, "pageSize": PIPELINE_READ_LIMIT})
        items.extend(page_items)
    return items


def _includes(value: str, search: str) -> bool:
    return search.casefold() in value.casefold()


def project_opportunity(item: dict[str, Any]) -> dict[str, Any]:
    open_actions = sorted(
        (action for action in item.get("actions", []) if action.get("status") == "Open"),
        key=lambda action: (action.get("due") or "", action.get("id") or ""),
    )
    next_action = open_actions[0] if open_actions else None
    return {
        "id": item["id"], "accountId": item["accountId"], "accountName": item["account"],
        "title": item["title"],
        "segment": frappe.db.get_value("Customer", item["accountId"], "custom_crm_segment") or "",
        "amount": decimal_string(item.get("amount") or 0), "currency": item["currency"], "stage": item["stage"],
        "probabilityLevel": item.get("probabilityLevel") or "",
        "intentScore": int(item.get("score") or 0), "budgetStatus": "Unknown",
        "owner": item["owner"], "nextAction": next_action["title"] if next_action else "",
        "due": next_action["due"] if next_action else item.get("poDate", ""),
        "saleType": item.get("saleType", ""),
        "modified": item.get("modified", item.get("updated", "")),
    }


def list_pipeline(query: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:view")
    opportunity_items = _read_all_pages(list_strategy_opportunities)
    booking_items = _read_all_pages(list_bookings)
    opportunities = [project_opportunity(item) for item in opportunity_items]
    bookings = booking_items
    search = str(query.get("search") or "").strip()
    account_id = str(query.get("accountId") or "").strip()
    contact_id = str(query.get("contactId") or "").strip()
    source = str(query.get("source") or "").strip()
    status = str(query.get("status") or "").strip()
    owner = str(query.get("owner") or "").strip()
    date_from = str(query.get("dateFrom") or "").strip()
    date_to = str(query.get("dateTo") or "").strip()
    opportunities = [item for item in opportunities if (
        (not search or _includes(f"{item['accountName']} {item['title']}", search))
        and (not account_id or account_id == "All" or item["accountId"] == account_id)
        and (not status or status == "All" or item["stage"] == status)
        and (not owner or owner == "All" or item["owner"] == owner)
        and (not contact_id or any(person.get("contactId") == contact_id for person in item.get("stakeholders", [])))
    )]
    bookings = [item for item in bookings if (
        (not search or _includes(f"{item['accountName']} {item['title']} {item['equipment']}", search))
        and (not account_id or account_id == "All" or item["accountId"] == account_id)
        and (not status or status == "All" or item["status"] == status)
        and (not owner or owner == "All" or item["owner"] == owner)
        and (not contact_id or item.get("primaryContactId") == contact_id)
        and (not source or source == "All" or item.get("source") == source)
        and (not date_from or (item.get("ddl") or "") >= date_from)
        and (not date_to or (item.get("ddl") or "") <= date_to)
    )]
    open_opportunities = [item for item in opportunities if item["stage"] in OPEN_STAGES]
    currencies = sorted({item["currency"] for item in [*opportunities, *bookings]})
    totals = []
    for currency in currencies:
        open_amount = sum(
            (as_decimal(item["amount"]) for item in open_opportunities if item["currency"] == currency),
            Decimal("0.00"),
        )
        confirmed_amount = sum(
            (
                as_decimal(item["amount"])
                for item in bookings if item["currency"] == currency and item["status"] == "Confirmed"
            ),
            Decimal("0.00"),
        )
        totals.append({
            "currency": currency,
            "openPipeline": decimal_string(open_amount),
            "confirmedBooking": decimal_string(confirmed_amount),
        })
    return {
        "opportunities": opportunities, "bookings": bookings,
        "totals": totals,
    }


def actions_for_account(account_id: str, opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for opportunity in opportunities:
        if opportunity["accountId"] != account_id:
            continue
        for action in opportunity.get("actions", []):
            result.append({
                "id": action["id"], "accountId": account_id, "opportunityId": opportunity["id"],
                "title": action["title"], "owner": action["owner"], "due": action["due"],
                "status": action["status"], "sourceType": "Deal",
            })
    return result
