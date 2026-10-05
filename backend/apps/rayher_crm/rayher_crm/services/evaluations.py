"""Evaluation, Test Run, and read-only Demo workflow services."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability
from rayher_crm.rayher_crm.doctype.crm_evaluation.crm_evaluation import OPEN_RETEST_ROUND_FLAG
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.common import normalize_pagination, optional_date, required_text, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.demo_health import calendar_day, derive_demo_health
from rayher_crm.services.opportunities import advance_opportunity_for_event
from rayher_crm.services.notifications import active_crm_users, notify_if_reachable


STATUS_NEXT = {
    "Requested": "Scope Confirmed",
    "Scope Confirmed": "Sample Received",
    "Sample Received": "Scheduled",
    "Scheduled": "Testing",
    "Testing": "Internal Review",
    "Analysis": "Customer Review",
    "Internal Review": "Customer Review",
    "Customer Review": "Accepted",
}
TERMINAL_STATUSES = {"Accepted", "Rejected"}
RUN_STATUSES = {"Scheduled", "Testing"}
PREPARATION_STATUSES = {"Requested", "Scope Confirmed", "Sample Received", "Scheduled"}
TERMINATION_REASON_MAX_LENGTH = 1000
# create_notification refuses a longer message; a termination reason alone may reach 1000.
NOTIFICATION_MESSAGE_LIMIT = 1000


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return frappe.parse_json(value)
        except Exception:
            return default
    return value


def _require_evaluation(name: str):
    if not frappe.db.exists("CRM Evaluation", name):
        raise CrmApiException("EVALUATION_NOT_FOUND", "Evaluation was not found.")
    doc = frappe.get_doc("CRM Evaluation", name)
    if not frappe.has_permission("CRM Evaluation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
    return doc


def _lock_evaluation(name: str):
    rows = frappe.db.sql("SELECT `name` FROM `tabCRM Evaluation` WHERE `name` = %s FOR UPDATE", (name,))
    if not rows:
        raise CrmApiException("EVALUATION_NOT_FOUND", "Evaluation was not found.")
    return frappe.get_doc("CRM Evaluation", name)


def serialize_test_run(doc) -> dict[str, Any]:
    return {
        "id": doc.name, "date": str(doc.run_date or ""), "lot": doc.lot,
        "round": int(doc.test_round or 1),
        "wafers": int(doc.wafers or 0), "status": doc.status,
        "capture": float(doc.capture) if doc.capture is not None else None,
        "falsePositive": float(doc.false_positive) if doc.false_positive is not None else None,
        "wph": float(doc.wph) if doc.wph is not None else None,
        "summary": doc.summary or "",
    }


def _runs(evaluation_id: str) -> list[dict[str, Any]]:
    names = frappe.get_all(
        "CRM Test Run", filters={"evaluation": evaluation_id}, pluck="name",
        order_by="run_date asc, creation asc, name asc", ignore_permissions=True,
    )
    return [serialize_test_run(frappe.get_doc("CRM Test Run", name)) for name in names]


def _customer_reviews(evaluation: str) -> list[dict[str, Any]]:
    """Customer Review is record-keeping: every round's comment is kept, oldest first."""
    rows = frappe.get_all(
        "CRM Evaluation Customer Review",
        filters={"evaluation": evaluation},
        fields=["name", "test_round", "comment", "author", "at"],
        order_by="at asc",
    )
    return [
        {
            "id": row.name,
            "round": int(row.test_round or 1),
            "comment": row.comment or "",
            "author": row.author or "",
            "createdAt": to_iso_timestamp(row.at),
        }
        for row in rows
    ]


def _history(evaluation_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CRM Evaluation History", filters={"evaluation": evaluation_id},
        fields=["name", "actor", "at", "event_type", "from_value", "to_value", "summary"],
        order_by="at desc, creation desc, name desc", ignore_permissions=True,
    )
    return [{
        "id": row.name, "actor": row.actor, "at": to_iso_timestamp(row.at),
        "eventType": row.event_type, "from": row.from_value or "",
        "to": row.to_value or "", "summary": row.summary,
    } for row in rows]


def append_evaluation_history(
    doc, event_type: str, summary: str, from_value: Any = "", to_value: Any = "",
) -> None:
    frappe.get_doc({
        "doctype": "CRM Evaluation History", "evaluation": doc.name,
        "demo_request": doc.demo_request, "actor": frappe.session.user,
        "at": frappe.utils.now_datetime(), "event_type": event_type,
        "from_value": "" if from_value is None else str(from_value),
        "to_value": "" if to_value is None else str(to_value),
        "summary": summary,
    }).insert(ignore_permissions=True)


def _has_completed_test_run(evaluation_id: str, test_round: int) -> bool:
    """A retest opens a new round, so only runs completed in *this* round count.

    Round-1 runs stay attached to the evaluation as history; without the round
    filter the Internal Review gate would reopen on them as soon as the new
    round's reports were uploaded, without any retest actually being run.
    """
    return bool(frappe.db.exists(
        "CRM Test Run",
        {"evaluation": evaluation_id, "status": "Completed", "test_round": int(test_round or 1)},
    ))


def _preparation_status(doc, branch: str) -> str:
    explicit = getattr(doc, f"{branch}_preparation_status", None)
    if explicit in {"Pending", "Completed"}:
        return explicit
    if doc.status in {"Scheduled", "Testing", "Analysis", "Internal Review", "Customer Review", "Accepted"}:
        return "Completed"
    if branch == "wafer" and doc.status == "Sample Received":
        return "Completed"
    return "Pending"


def serialize_evaluation(doc) -> dict[str, Any]:
    runs = _runs(doc.name)
    result = {
        "id": doc.name, "accountId": doc.account,
        "accountName": frappe.db.get_value("Customer", doc.account, "customer_name") or doc.account or "Self Test",
        "demoRequestId": doc.demo_request,
        "segment": frappe.db.get_value("Customer", doc.account, "custom_crm_segment") or "",
        "title": doc.title, "status": doc.status, "owner": doc.evaluation_owner,
        # Set only by terminate_evaluation: Rejected with a reason is a termination,
        # Rejected without one is a record archived under the old flow.
        "terminationReason": getattr(doc, "termination_reason", None) or "",
        "plannedEnd": str(doc.planned_end or ""), "testRunDeadline": str(doc.test_run_deadline or ""),
        "wafers": sum(run["wafers"] for run in runs if run["status"] != "Cancelled"), "acceptance": doc.acceptance,
        "reportStatus": doc.report_status,
        "reportVersion": int(doc.report_version or 0), "criteria": doc.criteria or "",
        "testRound": int(doc.test_round or 1), "customerReviews": _customer_reviews(doc.name),
        "waferPreparationStatus": _preparation_status(doc, "wafer"),
        "testPreparationStatus": _preparation_status(doc, "test"),
        "runs": runs, "history": _history(doc.name), "modified": to_iso_timestamp(doc.modified),
    }
    for branch in ("wafer", "test"):
        completed_by = getattr(doc, f"{branch}_preparation_completed_by", None)
        completed_at = getattr(doc, f"{branch}_preparation_completed_at", None)
        if completed_by:
            result[f"{branch}PreparationCompletedBy"] = completed_by
        if completed_at:
            result[f"{branch}PreparationCompletedAt"] = to_iso_timestamp(completed_at)
    if doc.requirement_id:
        result["requirementId"] = doc.requirement_id
    from rayher_crm.services.demo_artifacts import _serialize
    artifact_fields = (
        ("report_artifact_id", "reportArtifactId", "reportArtifact", "Test Report"),
        ("internal_report_artifact_id", "internalReportArtifactId", "internalReportArtifact", "Test Report"),
        ("external_report_artifact_id", "externalReportArtifactId", "externalReportArtifact", "Test Report"),
        ("customer_report_artifact_id", "customerReportArtifactId", "customerReportArtifact", "Customer Report"),
    )
    for fieldname, id_key, artifact_key, artifact_type in artifact_fields:
        artifact_id = getattr(doc, fieldname, None)
        if artifact_id and frappe.db.exists(
            "CRM Demo Artifact", {"name": artifact_id, "artifact_type": artifact_type},
        ):
            result[id_key] = artifact_id
            result[artifact_key] = _serialize(frappe.get_doc("CRM Demo Artifact", artifact_id))
    return result


def list_evaluations(query: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    assert_capability("evaluation:view")
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    where = [f"({conditions_for_doctype('CRM Evaluation')})"]
    values: list[Any] = []
    for query_field, column in (("accountId", "account"), ("status", "status"), ("owner", "evaluation_owner")):
        value = query.get(query_field)
        if value and value != "All":
            where.append(f"`{column}` = %s")
            values.append(value)
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        where.append("(`title` LIKE %s OR `account` LIKE %s OR `evaluation_owner` LIKE %s)")
        values.extend([pattern, pattern, pattern])
    date_from = optional_date(query.get("dateFrom"), "dateFrom")
    date_to = optional_date(query.get("dateTo"), "dateTo")
    if date_from and date_to and date_from > date_to:
        raise CrmApiException("VALIDATION_ERROR", "dateFrom must not be later than dateTo.")
    if date_from:
        where.append("`test_run_deadline` >= %s")
        values.append(date_from)
    if date_to:
        where.append("`test_run_deadline` <= %s")
        values.append(date_to)
    where_sql = " AND ".join(where)
    total = int(frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabCRM Evaluation` WHERE {where_sql}", tuple(values),
    )[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Evaluation` WHERE {where_sql} "
        "ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]), as_dict=True,
    )
    return [serialize_evaluation(frappe.get_doc("CRM Evaluation", row.name)) for row in rows], total, page, page_size


def get_evaluation(name: str) -> dict[str, Any]:
    assert_capability("evaluation:view")
    return serialize_evaluation(_require_evaluation(name))


def _update_request_tracking(doc, summary: str) -> None:
    if not doc.demo_request or not frappe.db.exists("CRM Demo Request", doc.demo_request):
        raise CrmApiException("DEMO_REQUEST_NOT_FOUND", "The source Demo Request was not found.")
    request = frappe.get_doc("CRM Demo Request", doc.demo_request)
    request.tracking = {
        "lastProgressAt": to_iso_timestamp(frappe.utils.now_datetime()),
        "lastProgressSummary": summary, "lastProgressActor": frappe.session.user,
        "nextAction": "", "nextActionOwner": "", "nextActionDue": "",
    }
    request.save(ignore_permissions=True)


def _notify_status_change(doc, request, previous_status: str) -> None:
    recipients = {request.sales_owner}
    if doc.status == "Internal Review":
        recipients.update(active_crm_users("Manager"))
    if doc.status in TERMINAL_STATUSES:
        recipients.add(doc.evaluation_owner)
    if doc.status == "Rejected" and doc.get("termination_reason"):
        # A termination ends the process; it is not a customer rejection.
        title = "Demo Test terminated"
        message = f"{doc.title}: terminated in {previous_status}. Reason: {doc.termination_reason}"
        if len(message) > NOTIFICATION_MESSAGE_LIMIT:
            message = message[:NOTIFICATION_MESSAGE_LIMIT - 1] + "…"
    else:
        title = f"Demo Test moved to {doc.status}"
        message = f"{doc.title}: {previous_status} -> {doc.status}"
    # The notice follows a status change that has already been written: someone who has left (or whose CRM role
    # is missing or ambiguous) is skipped instead of failing it, while any other write failure still rolls it back.
    for recipient in sorted(recipients - {frappe.session.user, None, ""}):
        notify_if_reachable(
            recipient=recipient, category="Evaluation",
            title=title, message=message,
            route=f"/demo-workflow/{request.name}?tab=information",
            source_doctype="CRM Evaluation", source_name=doc.name,
        )


def update_evaluation_status(name: str, command: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("evaluation:write")
    _require_evaluation(name)
    next_status = command.get("status") if isinstance(command, Mapping) else None
    doc = lock_document("CRM Evaluation", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Evaluation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
    if next_status == "Testing" and not all(
        _preparation_status(doc, branch) == "Completed" for branch in ("wafer", "test")
    ):
        raise CrmApiException("INVALID_TRANSITION", "Wafer and Test Preparation must both be completed.")
    if doc.status == "Testing" and next_status == "Internal Review":
        if not _has_completed_test_run(name, int(doc.test_round or 1)):
            raise CrmApiException(
                "INVALID_TRANSITION",
                f"Complete at least one Test Run in round {int(doc.test_round or 1)} before Internal Review.",
            )
        report_ids = (doc.internal_report_artifact_id, doc.external_report_artifact_id)
        if not all(artifact_id and frappe.db.exists(
            "CRM Demo Artifact", {"name": artifact_id, "artifact_type": "Test Report"},
        ) for artifact_id in report_ids):
            raise CrmApiException("INVALID_TRANSITION", "Upload Internal and External Test Reports before Internal Review.")
    allowed = {doc.status}
    if doc.status not in TERMINAL_STATUSES:
        if doc.status in STATUS_NEXT:
            allowed.add(STATUS_NEXT[doc.status])
        # Customer Review records a comment and then either archives or reopens testing.
        # Rejected is not a status step: only terminate_evaluation reaches it, and records
        # archived before Customer Review became an outcome-free step still carry it.
        if doc.status == "Customer Review":
            allowed.add("Testing")
    if next_status not in allowed:
        raise CrmApiException("INVALID_TRANSITION", f"Evaluation cannot move from {doc.status} to {next_status}.")
    if next_status == "Customer Review" and doc.report_status != "Ready":
        raise CrmApiException("REPORT_NOT_READY", "A Test Report is required before Customer Review.")
    if next_status == doc.status:
        return serialize_evaluation(doc)
    leaving_customer_review = doc.status == "Customer Review"
    customer_comment = ""
    if leaving_customer_review:
        customer_comment = required_text(command, "customerComment")
        if len(customer_comment) > 1000:
            raise CrmApiException(
                "VALIDATION_ERROR",
                "customerComment is too long.",
                field_errors={"customerComment": "Maximum length is 1000"},
            )
    is_retest = leaving_customer_review and next_status == "Testing"

    savepoint = f"crm_evaluation_status_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        previous_status = doc.status
        doc.status = next_status
        if next_status == "Sample Received":
            doc.wafer_preparation_status = "Completed"
        elif next_status == "Scheduled":
            doc.wafer_preparation_status = "Completed"
            doc.test_preparation_status = "Completed"
        doc.acceptance = next_status if next_status in TERMINAL_STATUSES else "Pending"
        commented_round = int(doc.test_round or 1)
        previous_deadline = str(doc.test_run_deadline or "")
        if is_retest:
            # A retest opens a new round. Artifacts are append-only and stay exactly
            # where they are; clearing the pointers re-arms the Internal Review gate so
            # the new round cannot advance on the previous round's reports.
            doc.test_round = commented_round + 1
            doc.flags[OPEN_RETEST_ROUND_FLAG] = True
            # The previous round's deadline is history too: left in place it would flag
            # the new round as overdue and keep the DDL reminders firing for it.
            doc.test_run_deadline = None
            doc.report_status = "Not Ready"
            doc.report_artifact_id = None
            doc.internal_report_artifact_id = None
            doc.external_report_artifact_id = None
            doc.customer_report_artifact_id = None
        doc.save(ignore_permissions=True)
        if customer_comment:
            frappe.get_doc({
                "doctype": "CRM Evaluation Customer Review",
                "evaluation": doc.name,
                "demo_request": doc.demo_request,
                "test_round": commented_round,
                "comment": customer_comment,
                "author": frappe.session.user,
                "at": frappe.utils.now_datetime(),
            }).insert(ignore_permissions=True)
        if is_retest and previous_deadline:
            # Mirror set_evaluation_test_run_deadline: every deadline change leaves a
            # Deadline row. Written before the Status row so the retest stays newest.
            append_evaluation_history(
                doc, "Deadline", f"Cleared round {commented_round} Test Run deadline for retest",
                previous_deadline, "",
            )
        if is_retest:
            history_summary = f"Demo Test retest requested, round {doc.test_round}: {customer_comment}"
        elif next_status == "Accepted" and customer_comment:
            history_summary = f"Demo Test archived with customer comment: {customer_comment}"
        else:
            history_summary = f"Demo Test moved to {next_status}"
        append_evaluation_history(doc, "Status", history_summary, previous_status, next_status)
        request = frappe.get_doc("CRM Demo Request", doc.demo_request)
        if next_status == "Customer Review" and request.opportunity:
            advance_opportunity_for_event(
                request.opportunity, "demo_customer_review",
                reference_doctype="CRM Evaluation", reference_name=doc.name,
            )
        _update_request_tracking(doc, history_summary)
        _notify_status_change(doc, request, previous_status)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_evaluation(doc)


def terminate_evaluation(name: str, payload: Mapping[str, Any], expected_modified: Any) -> dict[str, Any]:
    """End a Demo Test mid-flight, from any stage before it is archived (#73).

    It ends as Rejected with the reason on the Evaluation. The customer's acceptance
    is kept as it was, runs and reports stay as they are, and the Opportunity is
    neither advanced nor rolled back.
    """
    assert_capability("evaluation:write")
    _require_evaluation(name)
    reason = str((payload or {}).get("reason") or "").strip()
    if not reason:
        raise CrmApiException(
            "VALIDATION_ERROR", "A reason is required to terminate a Demo Test.", field_errors={"reason": "Required"},
        )
    if len(reason) > TERMINATION_REASON_MAX_LENGTH:
        raise CrmApiException(
            "VALIDATION_ERROR",
            f"reason must be at most {TERMINATION_REASON_MAX_LENGTH} characters.",
            field_errors={"reason": "Too long"},
        )
    doc = lock_document("CRM Evaluation", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Evaluation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
    if doc.status in TERMINAL_STATUSES:
        raise CrmApiException("INVALID_TRANSITION", f"Evaluation is already {doc.status}.")

    savepoint = f"crm_evaluation_terminate_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        previous_status = doc.status
        doc.status = "Rejected"
        doc.termination_reason = reason
        # Terminating the process is not a customer verdict: doc.acceptance is left as it is.
        doc.save(ignore_permissions=True)
        summary = f"Demo Test terminated: {reason}"
        append_evaluation_history(doc, "Status", summary, previous_status, doc.status)
        request = frappe.get_doc("CRM Demo Request", doc.demo_request)
        _update_request_tracking(doc, summary)
        _notify_status_change(doc, request, previous_status)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_evaluation(doc)


def complete_evaluation_preparation(
    name: str, branch: str, expected_modified: Any,
) -> dict[str, Any]:
    assert_capability("evaluation:write")
    if branch not in {"wafer", "test"}:
        raise CrmApiException("VALIDATION_ERROR", "branch must be wafer or test.")
    _require_evaluation(name)
    doc = lock_document("CRM Evaluation", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Evaluation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
    if doc.status not in PREPARATION_STATUSES:
        raise CrmApiException("INVALID_TRANSITION", "Preparation cannot be changed in the current stage.")
    if _preparation_status(doc, branch) == "Completed":
        return serialize_evaluation(doc)

    setattr(doc, f"{branch}_preparation_status", "Completed")
    setattr(doc, f"{branch}_preparation_completed_by", frappe.session.user)
    setattr(doc, f"{branch}_preparation_completed_at", frappe.utils.now_datetime())
    previous_status = doc.status
    if all(_preparation_status(doc, item) == "Completed" for item in ("wafer", "test")):
        doc.status = "Scheduled"
    doc.save(ignore_permissions=True)
    append_evaluation_history(
        doc, "Preparation", f"Completed {branch.title()} Preparation",
        "Pending", "Completed",
    )
    if previous_status != doc.status:
        append_evaluation_history(doc, "Status", f"Demo Test moved to {doc.status}", previous_status, doc.status)
    _update_request_tracking(doc, f"Completed {branch.title()} Preparation")
    doc.reload()
    return serialize_evaluation(doc)


def _positive_wafers(value: Any) -> int:
    if isinstance(value, bool):
        raise CrmApiException("VALIDATION_ERROR", "wafers must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "wafers must be a positive integer.") from exc
    if str(value).strip() != str(parsed) or parsed < 1:
        raise CrmApiException("VALIDATION_ERROR", "wafers must be a positive integer.")
    return parsed


def _metric(value: Any, fieldname: str) -> float:
    if isinstance(value, bool):
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a finite number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a finite number.") from exc
    if not math.isfinite(parsed):
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} must be a finite number.")
    return parsed


def _validate_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_date = optional_date(payload.get("date"), "date")
    if not run_date:
        raise CrmApiException("VALIDATION_ERROR", "date is required.")
    lot = required_text(payload, "lot")
    wafers = _positive_wafers(payload.get("wafers"))
    raw_metrics = (payload.get("capture"), payload.get("falsePositive"), payload.get("wph"))
    present = tuple(value not in (None, "") for value in raw_metrics)
    if any(present) and not all(present):
        raise CrmApiException("VALIDATION_ERROR", "capture, falsePositive, and wph must be all empty or all provided.")
    summary = str(payload.get("summary") or "").strip()
    if all(present):
        capture = _metric(raw_metrics[0], "capture")
        false_positive = _metric(raw_metrics[1], "falsePositive")
        wph = _metric(raw_metrics[2], "wph")
        if not 0 <= capture <= 100 or not 0 <= false_positive <= 100 or wph < 0:
            raise CrmApiException("VALIDATION_ERROR", "Metric values are outside their allowed range.")
        if not summary:
            raise CrmApiException("VALIDATION_ERROR", "summary is required for a completed Test Run.")
        status = "Completed"
    else:
        capture = false_positive = wph = None
        status = "Planned"
    return {
        "run_date": run_date, "lot": lot, "wafers": wafers, "status": status,
        "capture": capture, "false_positive": false_positive, "wph": wph, "summary": summary,
    }


def add_evaluation_run(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("evaluation:write")
    current = _require_evaluation(name)
    if current.status in TERMINAL_STATUSES:
        raise CrmApiException("INVALID_REPORT_STAGE", "Terminal Evaluation cannot accept Test Runs.")
    if current.status not in RUN_STATUSES:
        raise CrmApiException("INVALID_RUN_STAGE", "Test Runs are only allowed in Scheduled or Testing.")
    values = _validate_run(payload)
    expected_modified = payload.get("expectedModified") if "expectedModified" in payload else None
    doc = lock_document("CRM Evaluation", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Evaluation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
    if doc.status in TERMINAL_STATUSES:
        raise CrmApiException("INVALID_REPORT_STAGE", "Terminal Evaluation cannot accept Test Runs.")
    if doc.status not in RUN_STATUSES:
        raise CrmApiException("INVALID_RUN_STAGE", "Test Runs are only allowed in Scheduled or Testing.")

    savepoint = f"crm_test_run_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        # The controller stamps ``test_round`` from the parent on insert.
        run = frappe.get_doc({
            "doctype": "CRM Test Run", "evaluation": doc.name, **values,
        }).insert(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        append_evaluation_history(
            doc, "Test Run", f"{run.status} Test Run {run.name}", "", run.name,
        )
        _update_request_tracking(doc, f"{'Completed' if run.status == 'Completed' else 'Created'} Test Run {run.name}")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_evaluation(doc)


def _lock_planned_run(name: str, run_id: Any, payload: dict[str, Any]):
    """Lock the Evaluation, then return it with its still-Planned run of the current round."""
    current = _require_evaluation(name)
    if current.status in TERMINAL_STATUSES:
        raise CrmApiException("INVALID_REPORT_STAGE", "Terminal Evaluation cannot change Test Runs.")
    expected_modified = payload.get("expectedModified") if "expectedModified" in payload else None
    doc = lock_document("CRM Evaluation", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Evaluation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
    if doc.status in TERMINAL_STATUSES:
        raise CrmApiException("INVALID_REPORT_STAGE", "Terminal Evaluation cannot change Test Runs.")
    if doc.status not in RUN_STATUSES:
        raise CrmApiException("INVALID_RUN_STAGE", "Test Runs can only change in Scheduled or Testing.")
    if not isinstance(run_id, str) or not frappe.db.exists("CRM Test Run", {"name": run_id, "evaluation": doc.name}):
        raise CrmApiException("NOT_FOUND", "Test Run was not found on this Evaluation.")
    run = frappe.get_doc("CRM Test Run", run_id)
    if run.status != "Planned":
        raise CrmApiException("INVALID_RUN_STAGE", f"Only a Planned Test Run can change; this one is {run.status}.")
    if int(run.test_round or 1) != int(doc.test_round or 1):
        raise CrmApiException("INVALID_RUN_STAGE", "A Test Run of an earlier round is history and cannot change.")
    return doc, run


def update_evaluation_run(name: str, run_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Reschedule or edit a Planned run, or complete it by providing its results."""
    assert_capability("evaluation:write")
    values = _validate_run(payload)
    doc, run = _lock_planned_run(name, run_id, payload)
    savepoint = f"crm_test_run_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        previous_date = str(run.run_date or "")
        run.update(values)
        run.save(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        if run.status == "Completed":
            summary, before, after = f"Completed Test Run {run.name}", "Planned", "Completed"
        elif previous_date != str(run.run_date):
            summary, before, after = f"Rescheduled Test Run {run.name} to {run.run_date}", previous_date, str(run.run_date)
        else:
            summary, before, after = f"Updated Test Run {run.name}", "", run.name
        append_evaluation_history(doc, "Test Run", summary, before, after)
        _update_request_tracking(doc, summary)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_evaluation(doc)


def cancel_evaluation_run(name: str, run_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """A plan that will not happen is cancelled with its reason; the record itself stays."""
    assert_capability("evaluation:write")
    reason = required_text(payload, "reason")
    if len(reason) > 500:
        raise CrmApiException("VALIDATION_ERROR", "reason is too long.", field_errors={"reason": "Maximum length is 500"})
    doc, run = _lock_planned_run(name, run_id, payload)
    savepoint = f"crm_test_run_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        run.status = "Cancelled"
        run.summary = reason
        run.save(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        summary = f"Cancelled Test Run {run.name}: {reason}"
        append_evaluation_history(doc, "Test Run", summary, "Planned", "Cancelled")
        _update_request_tracking(doc, summary)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_evaluation(doc)


def set_evaluation_test_run_deadline(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("evaluation:write")
    _require_evaluation(name)
    deadline = optional_date(payload.get("testRunDeadline"), "testRunDeadline")
    if not deadline:
        raise CrmApiException("VALIDATION_ERROR", "testRunDeadline is required.")
    if deadline < frappe.utils.today():
        raise CrmApiException("VALIDATION_ERROR", "testRunDeadline cannot be in the past.")
    expected_modified = payload.get("expectedModified") if "expectedModified" in payload else None
    doc = lock_document("CRM Evaluation", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Evaluation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Evaluation is outside the current user scope.")
    if doc.status in TERMINAL_STATUSES:
        # An archived or terminated Demo Test has ended: a new deadline would add history,
        # overwrite the request's closing note and notify people about a finished test.
        raise CrmApiException(
            "INVALID_TRANSITION", f"A Test Run deadline cannot be set on an Evaluation that is already {doc.status}.",
        )
    savepoint = f"crm_evaluation_deadline_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        previous_deadline = str(doc.test_run_deadline or "")
        doc.test_run_deadline = deadline
        doc.save(ignore_permissions=True)
        append_evaluation_history(
            doc, "Deadline", f"Updated Test Run deadline to {deadline}", previous_deadline, deadline,
        )
        _update_request_tracking(doc, f"Updated Test Run deadline to {deadline}")
        if doc.evaluation_owner != frappe.session.user:
            request = frappe.get_doc("CRM Demo Request", doc.demo_request)
            notify_if_reachable(
                recipient=doc.evaluation_owner, category="Evaluation",
                title="Demo Test deadline updated",
                message=f"{doc.title}: Test Run deadline is {deadline}.",
                route=f"/demo-workflow/{request.name}?tab=information",
                source_doctype="CRM Evaluation", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_evaluation(doc)


def _workflow_stage(request_status: str, evaluation_status: str | None) -> str | None:
    if request_status in {"Engineer Review", "Engineer Returned"}:
        return "Engineer Review"
    if request_status in {"Manager Approval", "Manager Rejected"}:
        return "Manager Approval"
    if request_status != "Converted":
        return None
    if evaluation_status in {None, "Requested", "Scope Confirmed", "Sample Received", "Scheduled"}:
        return "Test Preparation"
    if evaluation_status == "Testing":
        return "Test Execution"
    if evaluation_status in {"Analysis", "Internal Review"}:
        return "Internal Review"
    if evaluation_status == "Customer Review":
        return "Customer Review"
    return None


def _termination_stage(evaluation: dict[str, Any]) -> str:
    """The workflow stage a terminated Demo Test stopped in, read from its termination row."""
    stop = next(
        (row for row in evaluation["history"] if row["eventType"] == "Status" and row["to"] == "Rejected"),
        None,
    )
    # Without that row nothing past the approved request can be claimed as reached.
    return _workflow_stage("Converted", stop["from"] if stop else None) or "Test Preparation"


def _workflow_timeline(
    request,
    evaluation: dict[str, Any] | None,
    stage: str | None,
    history: list[Any],
) -> list[dict[str, Any]]:
    # Accepted and historical Rejected records went all the way through. A terminated
    # one (Rejected with a reason) shows the steps before its stop as done, the stop as
    # where it stood, and nothing after it as reached or dated.
    terminated = bool(evaluation and evaluation["status"] == "Rejected" and evaluation.get("terminationReason"))
    completed = bool(evaluation and evaluation["status"] in TERMINAL_STATUSES) and not terminated
    if terminated:
        stage = _termination_stage(evaluation)
    current_index = {
        "Engineer Review": 1,
        "Manager Approval": 2,
        "Test Preparation": 3,
        "Test Execution": 5,
        "Internal Review": 6,
        "Customer Review": 7,
    }.get(stage or "", 0)
    # Both preparation branches belong to the Test Preparation stop.
    last_reached = 4 if stage == "Test Preparation" else current_index

    def reached_date(index: int, value: str) -> str:
        return "" if terminated and index > last_reached else value

    def state(index: int, key: str) -> str:
        if completed:
            return "Done"
        if stage == "Test Preparation" and key in {"wafer-preparation", "test-preparation"}:
            branch = "wafer" if key == "wafer-preparation" else "test"
            return "Done" if evaluation and evaluation[f"{branch}PreparationStatus"] == "Completed" else "Current"
        if index < current_index:
            return "Done"
        return "Current" if index == current_index else "Waiting"

    def transition(to_status: str):
        return next((item for item in reversed(history) if item.to_status == to_status), None)

    engineer_completed = transition("Manager Approval")
    manager_completed = transition("Converted")
    current_round = int((evaluation or {}).get("testRound") or 1)
    completed_runs = [
        run for run in (evaluation["runs"] if evaluation else [])
        if run["status"] == "Completed" and int(run.get("round") or 1) == current_round
    ]
    run_date = completed_runs[-1]["date"] if completed_runs else ""

    return [
        {
            "key": "sales-preparation", "label": "Sales Preparation", "state": state(0, "sales-preparation"),
            "actor": request.created_by_user or request.sales_owner,
            "date": to_iso_timestamp(request.creation),
        },
        {
            "key": "engineer-review", "label": "Engineer Review", "state": state(1, "engineer-review"),
            "actor": engineer_completed.actor if engineer_completed else request.engineer_owner,
            "date": to_iso_timestamp(engineer_completed.at) if engineer_completed else "",
        },
        {
            "key": "manager-approval", "label": "Manager Approval", "state": state(2, "manager-approval"),
            "actor": manager_completed.actor if manager_completed else (request.approved_by or ""),
            "date": to_iso_timestamp(manager_completed.at) if manager_completed else str(request.approved_date or ""),
        },
        {
            "key": "wafer-preparation", "label": "Wafer Preparation", "state": state(3, "wafer-preparation"),
            "actor": (evaluation or {}).get("waferPreparationCompletedBy") or (evaluation or {}).get("owner") or request.engineer_owner,
            "date": str((evaluation or {}).get("waferPreparationCompletedAt") or ""),
        },
        {
            "key": "test-preparation", "label": "Test Preparation", "state": state(4, "test-preparation"),
            "actor": (evaluation or {}).get("testPreparationCompletedBy") or (evaluation or {}).get("owner") or request.engineer_owner,
            "date": str((evaluation or {}).get("testPreparationCompletedAt") or ""),
        },
        {
            "key": "test-execution", "label": "Test Execution", "state": state(5, "test-execution"),
            "actor": (evaluation or {}).get("owner") or request.engineer_owner,
            "date": reached_date(5, run_date),
        },
        {
            "key": "internal-review", "label": "Internal Review", "state": state(6, "internal-review"),
            "actor": (evaluation or {}).get("owner") or request.engineer_owner,
            "date": reached_date(6, run_date),
        },
        {
            "key": "customer-review", "label": "Customer Review", "state": state(7, "customer-review"),
            "date": reached_date(7, (
                str((evaluation or {}).get("modified") or "") if completed or terminated
                else str(request.customer_expected_date or "")
            )),
        },
    ]


def _last_recorded_activity(request, request_history: list[Any], evaluation: dict[str, Any] | None) -> Any:
    """When a Demo last moved, for a row whose tracking was never written or cannot be read.

    Every Demo action writes tracking. A row without it was inserted directly (staging data, a
    migration); the history of its Demo Request and of its Demo Test, and its creation, still say when
    it last moved. Without them such a Demo would never count as stalled.
    """

    days = [calendar_day(row.at) for row in request_history]
    if evaluation:
        days += [calendar_day(row["at"]) for row in evaluation["history"]]
    return max((day for day in days if day), default=None) or request.creation


def list_demo_workflows(query: dict[str, Any] | None = None):
    assert_capability("demo_request:view")
    from rayher_crm.services.demo_artifacts import list_demo_artifacts
    where = f"({conditions_for_doctype('CRM Demo Request')})"
    page = page_size = total = None
    if query is None:
        request_rows = frappe.db.sql(
            f"SELECT `name` FROM `tabCRM Demo Request` WHERE {where} ORDER BY `modified` DESC, `name` DESC",
            as_dict=True,
        )
    else:
        request_id = str(query.get("id") or "").strip()
        contact_id = str(query.get("contactId") or "").strip()
        values: list[Any] = []
        if request_id:
            where += " AND `name` = %s"
            values.append(request_id)
        if contact_id and contact_id != "All":
            where += " AND `primary_contact` = %s"
            values.append(contact_id)
        page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
        total = int(frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabCRM Demo Request` WHERE {where}", tuple(values),
        )[0][0])
        request_rows = frappe.db.sql(
            f"SELECT `name` FROM `tabCRM Demo Request` WHERE {where} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
            (*values, page_size, offset), as_dict=True,
        )
    request_names = [row.name for row in request_rows]
    today = frappe.utils.getdate(frappe.utils.today())
    history_by_request: dict[str, list[Any]] = {name: [] for name in request_names}
    if request_names:
        history_rows = frappe.get_all(
            "CRM Demo Request History",
            filters={"demo_request": ["in", request_names]},
            fields=["demo_request", "at", "actor", "to_status"],
            order_by="at asc, creation asc, name asc",
            ignore_permissions=True,
        )
        for history_row in history_rows:
            history_by_request.setdefault(history_row.demo_request, []).append(history_row)

    result: list[dict[str, Any]] = []
    for row in request_rows:
        request = frappe.get_doc("CRM Demo Request", row.name)
        form = _json_value(request.form_data, {})
        evaluation = None
        if request.evaluation and frappe.db.exists("CRM Evaluation", request.evaluation):
            evaluation = serialize_evaluation(frappe.get_doc("CRM Evaluation", request.evaluation))
        workflow = {
            "id": request.name, "accountId": request.account, "siteId": "",
            "opportunityId": request.opportunity or "", "title": request.title,
            "account": frappe.db.get_value("Customer", request.account, "customer_name") or request.account or "Self Test",
            "opportunity": frappe.db.get_value("CRM Opportunity", request.opportunity, "title") if request.opportunity else "自测",
            "salesOwner": request.sales_owner, "engineerOwner": request.engineer_owner,
            "equipment": request.requested_equipment, "owner": request.engineer_owner,
            "status": evaluation["status"] if evaluation else request.status,
            # conclusion.status stays the customer's acceptance; a termination is told apart by its reason.
            "terminationReason": evaluation.get("terminationReason", "") if evaluation else "",
            "archiveCategory": "Completed" if request.status in {"Converted", "Cancelled"} and evaluation and evaluation["status"] in TERMINAL_STATUSES else "In Progress",
            "tracking": _json_value(request.tracking, {}),
            "customerExpectedDate": str(request.customer_expected_date or ""),
            "request": {
                "objective": request.objective, "requestedEquipment": request.requested_equipment,
                "sampleType": request.sample_type, "sampleQuantity": int(request.sample_quantity or 0),
                "priority": request.priority, "acceptanceCriteria": request.acceptance_criteria,
                "salesOwner": request.sales_owner, "specificRequest": form.get("specificRequest", ""),
                "detectMeasure": form.get("detectMeasure", ""), "expectedResults": form.get("expectedResults", ""),
                "complementaryTool": form.get("complementaryTool", ""), "contactPerson": form.get("contactPerson", ""),
                "industry": form.get("industry", ""), "testPlan": request.test_plan or "",
                "assignedEquipment": request.assigned_equipment or "", "resourceWindow": request.resource_window or "",
                "estimatedCompletionDate": str(request.estimated_completion_date or ""),
                "technicalRisk": request.technical_risk or "", "engineerComment": request.engineer_comment or "",
                "managerDecision": request.manager_decision or "", "managerComment": request.manager_comment or "",
            },
            "evaluation": ({
                "id": evaluation["id"], "status": evaluation["status"], "owner": evaluation["owner"],
                "testRunDeadline": evaluation["testRunDeadline"], "runs": evaluation["runs"],
                "waferPreparationStatus": evaluation["waferPreparationStatus"],
                "waferPreparationCompletedBy": evaluation.get("waferPreparationCompletedBy", ""),
                "waferPreparationCompletedAt": evaluation.get("waferPreparationCompletedAt", ""),
                "testPreparationStatus": evaluation["testPreparationStatus"],
                "testPreparationCompletedBy": evaluation.get("testPreparationCompletedBy", ""),
                "testPreparationCompletedAt": evaluation.get("testPreparationCompletedAt", ""),
            } if evaluation else None),
            "artifacts": list_demo_artifacts(request.name),
            "conclusion": {
                "status": evaluation["acceptance"] if evaluation else "Pending",
                "customerFeedback": (evaluation.get("customerReviews") or [{}])[-1].get("comment", "") if evaluation else "",
            },
            "testRound": evaluation["testRound"] if evaluation else 1,
            "customerReviews": evaluation.get("customerReviews", []) if evaluation else [],
            "approvals": [], "executions": [], "wafers": [],
            "testRuns": ([{
                "id": run["id"], "date": run["date"], "recipe": run["lot"],
                "capture": run["capture"], "falsePositive": run["falsePositive"], "wph": run["wph"],
                "result": run["summary"],
            } for run in evaluation["runs"]] if evaluation else []),
        }
        stage = _workflow_stage(request.status, evaluation["status"] if evaluation else None)
        if stage:
            workflow["stage"] = stage
        # Health describes a Demo that is under way, which is one with a lifecycle stage. A draft that
        # was never submitted and a Demo that has ended (archived, terminated, cancelled) have none, so
        # the boards neither colour them, count them as at risk, nor match them to a health filter.
        if stage:
            tracking = workflow["tracking"] if isinstance(workflow["tracking"], Mapping) else {}
            # The Test Run deadline counts until the run is done; once the results are under review it is history.
            run_is_due = bool(evaluation) and evaluation["status"] in PREPARATION_STATUSES | RUN_STATUSES
            workflow["health"] = derive_demo_health(
                last_progress_at=calendar_day(tracking.get("lastProgressAt")) or _last_recorded_activity(
                    request, history_by_request.get(request.name, []), evaluation,
                ),
                customer_expected_date=request.customer_expected_date,
                test_run_deadline=evaluation["testRunDeadline"] if run_is_due else None,
                today=today,
            )
        workflow["projectTimeline"] = _workflow_timeline(
            request,
            evaluation,
            stage,
            history_by_request.get(request.name, []),
        )
        result.append(workflow)
    return result if query is None else (result, total, page, page_size)


def get_demo_workflow(name: str) -> dict[str, Any]:
    workflow_id = required_text({"id": name}, "id")
    items, _total, _page, _page_size = list_demo_workflows({
        "id": workflow_id, "page": 1, "pageSize": 1,
    })
    if not items:
        raise CrmApiException("DEMO_REQUEST_NOT_FOUND", "Demo project was not found.")
    return items[0]
