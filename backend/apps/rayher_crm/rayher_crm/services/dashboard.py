"""Management Dashboard aggregation over scoped canonical CRM read models."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, capabilities_for_user
from rayher_crm.services.accounts import list_accounts
from rayher_crm.services.demo_requests import list_demo_requests
from rayher_crm.services.evaluations import list_evaluations
from rayher_crm.services.opportunities import list_strategy_opportunities
from rayher_crm.services.opportunity_stages import OPEN_STAGES, PO_RECEIVED
from rayher_crm.services.pipeline import actions_for_account, list_pipeline
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.services.visits import list_visits
from rayher_crm.services.money import as_decimal

PAGE_SIZE = 200

def _read_all_pages(read_page, base_query=None):
    query = dict(base_query or {})
    first, total, _page, _page_size = read_page({**query, "page": 1, "pageSize": PAGE_SIZE})
    items = list(first)
    for page in range(2, (int(total) + PAGE_SIZE - 1) // PAGE_SIZE + 1):
        page_items, _total, _page, _page_size = read_page({**query, "page": page, "pageSize": PAGE_SIZE})
        items.extend(page_items)
    return items


def _count_by(rows: list[dict], read: Callable[[dict], str]) -> list[dict]:
    counts: dict[str, int] = {}
    for row in rows:
        label = read(row)
        counts[label] = counts.get(label, 0) + 1
    return [{"label": label, "count": count} for label, count in counts.items()]


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def _known_amount(value: Any) -> Decimal:
    """An amount nobody has entered yet ("", allowed at S1) adds nothing to a money sum; it is not a 0 value."""

    return Decimal("0.00") if value is None or value == "" else as_decimal(value)


def _sum_amount(rows: list[dict]) -> Decimal:
    return sum((_known_amount(row["amount"]) for row in rows), Decimal("0.00"))


def _missing_amount_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if not row["amount"])


def _amount_by(rows: list[dict], read_label: Callable[[dict], str], read_amount: Callable[[dict], Any]) -> list[dict]:
    totals: dict[tuple[str, str], dict[str, Decimal | int]] = {}
    for row in rows:
        label = read_label(row)
        currency = str(row.get("currency") or "").upper()
        current = totals.setdefault((label, currency), {"count": 0, "amount": Decimal("0.00")})
        current["count"] += 1
        current["amount"] += _known_amount(read_amount(row))
    return [
        {"label": label, "currency": currency, "count": int(value["count"]), "amount": _money(value["amount"])}
        for (label, currency), value in totals.items()
    ]


def get_dashboard(query: dict[str, Any]) -> dict[str, Any]:
    assert_capability("dashboard:view")
    dashboard_range = str(query.get("range") or "").strip()
    if dashboard_range not in {"month", "quarter", "year"}:
        raise CrmApiException("VALIDATION_ERROR", "range must be month, quarter, or year.")
    segment = str(query.get("segment") or "").strip()
    accounts = _read_all_pages(list_accounts, {"segment": segment or "All"})
    account_ids = {item["id"] for item in accounts}
    pipeline = list_pipeline({})
    opportunities = [item for item in pipeline["opportunities"] if item["accountId"] in account_ids]
    # An Opportunity whose amount is still unknown ("", allowed at S1) counts like any other in its stage,
    # owner, account, segment and currency group, but money sums add known amounts only: it adds no value,
    # never a 0, and each group that shows money reports how many amounts it leaves out.
    unpriced = [item for item in opportunities if not item["amount"]]
    priced = [item for item in opportunities if item["amount"]]
    bookings = [item for item in pipeline["bookings"] if item["accountId"] in account_ids]
    strategy = [item for item in list_strategy_opportunities() if item["accountId"] in account_ids]
    actions = []
    for account_id in account_ids:
        actions.extend(actions_for_account(account_id, strategy))
    demos = [item for item in _read_all_pages(list_demo_requests) if item["accountId"] in account_ids]
    evaluations = [item for item in _read_all_pages(list_evaluations) if item["accountId"] in account_ids]
    visits = (
        [item for item in _read_all_pages(list_visits) if item["accountId"] in account_ids]
        if "visit:view" in capabilities_for_user()
        else []
    )
    open_opportunities = [item for item in opportunities if item["stage"] in OPEN_STAGES]
    confirmed = [item for item in bookings if item["status"] == "Confirmed"]
    as_of = to_iso_timestamp(frappe.utils.now_datetime())
    today = as_of[:10]

    stage_labels = list(OPEN_STAGES)
    funnel = []
    for stage in stage_labels:
        rows = [item for item in open_opportunities if item["stage"] == stage]
        for currency in sorted({item["currency"] for item in rows}):
            currency_rows = [item for item in rows if item["currency"] == currency]
            funnel.append({
                "stage": stage,
                "currency": currency,
                "amount": _money(_sum_amount(currency_rows)),
                "count": len(currency_rows),
                "missingAmountCount": _missing_amount_count(currency_rows),
            })
    owners = sorted({item["owner"] for item in [*open_opportunities, *confirmed]})
    owner_performance = []
    for owner in owners:
        owner_rows = [item for item in [*open_opportunities, *confirmed] if item["owner"] == owner]
        for currency in sorted({item["currency"] for item in owner_rows}):
            owner_open = [item for item in open_opportunities if item["owner"] == owner and item["currency"] == currency]
            owner_bookings = [item for item in confirmed if item["owner"] == owner and item["currency"] == currency]
            owner_performance.append({
                "owner": owner, "currency": currency,
                "pipeline": _money(_sum_amount(owner_open)),
                "booking": _money(_sum_amount(owner_bookings)),
                "pipelineMissingAmountCount": _missing_amount_count(owner_open),
            })
    account_map = {item["id"]: item for item in accounts}
    top_accounts = []
    for account_id in account_ids:
        account_rows = [item for item in [*open_opportunities, *confirmed] if item["accountId"] == account_id]
        for currency in sorted({item["currency"] for item in account_rows}):
            pipeline_rows = [item for item in open_opportunities if item["accountId"] == account_id and item["currency"] == currency]
            booking_rows = [item for item in confirmed if item["accountId"] == account_id and item["currency"] == currency]
            top_accounts.append({
                "accountId": account_id, "accountName": account_map[account_id]["name"], "currency": currency,
                "pipeline": _money(_sum_amount(pipeline_rows)), "booking": _money(_sum_amount(booking_rows)),
                "pipelineMissingAmountCount": _missing_amount_count(pipeline_rows),
            })
    top_accounts.sort(key=lambda item: (item["accountName"], item["currency"]))

    def distribution(field: str) -> list[dict]:
        result = []
        for label in dict.fromkeys(item[field] for item in accounts):
            ids = {item["id"] for item in accounts if item[field] == label}
            rows = [item for item in [*open_opportunities, *confirmed] if item["accountId"] in ids]
            for currency in sorted({item["currency"] for item in rows}):
                pipeline_rows = [item for item in open_opportunities if item["accountId"] in ids and item["currency"] == currency]
                booking_rows = [item for item in confirmed if item["accountId"] in ids and item["currency"] == currency]
                result.append({
                    "label": label, "currency": currency,
                    "pipeline": _money(_sum_amount(pipeline_rows)), "booking": _money(_sum_amount(booking_rows)),
                    "pipelineMissingAmountCount": _missing_amount_count(pipeline_rows),
                })
        return result

    booking_months: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"amount": Decimal("0.00"), "count": 0})
    for booking in confirmed:
        month = booking["bookingDate"][:7]
        booking_months[(month, booking["currency"])]["amount"] += _known_amount(booking["amount"])
        booking_months[(month, booking["currency"])]["count"] += 1
    booking_by_month = [
        {"label": label, "currency": currency, "amount": _money(value["amount"]), "count": int(value["count"])}
        for (label, currency), value in sorted(booking_months.items())
    ]
    weekly_actions = sorted(
        (item for item in actions if item["status"] == "Open"), key=lambda item: (item["due"], item["id"]),
    )[:5]
    return {
        "asOf": as_of,
        "kpis": {
            # Money only, with no count beside it: a currency whose Opportunities all lack an amount gets no
            # row, since its total would be a fake 0; the two missing counts below say what is left out.
            "moneyByCurrency": [{
                "currency": currency,
                "openPipeline": _money(_sum_amount([item for item in open_opportunities if item["currency"] == currency])),
                "confirmedBooking": _money(_sum_amount([item for item in confirmed if item["currency"] == currency])),
                "cumulativeWon": _money(_sum_amount([item for item in opportunities if item["stage"] == PO_RECEIVED and item["currency"] == currency])),
            } for currency in sorted({item["currency"] for item in [*priced, *bookings]})],
            "openPipelineMissingAmountCount": sum(item["stage"] in OPEN_STAGES for item in unpriced),
            "cumulativeWonMissingAmountCount": sum(item["stage"] == PO_RECEIVED for item in unpriced),
            "overdueActions": sum(item["status"] == "Open" and item["due"] < today for item in actions),
            "pendingDemoRequests": sum(item["status"] in {"Engineer Review", "Manager Approval"} for item in demos),
            "activeEvaluations": sum(item["status"] not in {"Accepted", "Rejected"} for item in evaluations),
        },
        "funnel": funnel, "bookingByMonth": booking_by_month,
        "ownerPerformance": owner_performance, "topAccounts": top_accounts,
        "segmentDistribution": distribution("segment"), "regionDistribution": distribution("region"),
        "tierDistribution": _count_by(accounts, lambda item: item["tier"]),
        "riskDistribution": _count_by(accounts, lambda item: item["risk"]),
        "process": {
            "requirementsByStatus": [], "budgetByStatus": [],
            "actionsBySource": _count_by([item for item in actions if item["status"] == "Open"], lambda item: item["sourceType"]),
            "actionsByTimeliness": _count_by([item for item in actions if item["status"] == "Open"], lambda item: "已逾期" if item["due"] < today else "未逾期"),
            "demoByStatus": _count_by(demos, lambda item: item["status"]),
            "demoByPriority": _count_by(demos, lambda item: item["priority"]),
            "evaluationByStatus": _count_by(evaluations, lambda item: item["status"]),
            "evaluationRunResults": _count_by([run for item in evaluations for run in item["runs"]], lambda item: item["status"]),
            "visitsByStatus": _count_by(visits, lambda item: item["status"]),
            "visitsByOwner": _count_by(visits, lambda item: item["owner"]),
        },
        "attentionAccounts": sorted(
            ({**item, "pipelineAmount": 0}
             for item in accounts if item["risk"] != "稳健"),
            key=lambda item: item["name"],
        )[:4],
        "weeklyActions": weekly_actions,
        "deliveryAlerts": [{
            "id": item["id"], "type": "Demo Request", "title": item["title"],
            "detail": f"{item['accountName']} · 等待经理审批", "tone": "warning",
        } for item in demos if item["status"] == "Manager Approval"][:4],
        "completeness": [
            {"label": "客户基础档案", "value": sum(item["completeness"] >= 80 for item in accounts), "total": len(accounts)},
            {"label": "关键人关系", "value": sum(item["stakeholderCount"] > 0 for item in accounts), "total": len(accounts)},
            {"label": "采购需求字段", "value": 0, "total": 0},
            {"label": "Next Action", "value": 0, "total": 0},
        ],
    }
