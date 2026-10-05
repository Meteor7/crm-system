"""Demo Request and scoped Comment services."""

from __future__ import annotations

import json
from collections.abc import Mapping
from collections.abc import Callable
from typing import Any

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype, has_crm_permission
from rayher_crm.services.accounts import _require_account
from rayher_crm.services.common import (
    ensure_server_generated_id,
    normalize_pagination,
    optional_date,
    required_text,
    resolve_write_owner,
    to_iso_timestamp,
)
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.contacts import _contact_account, _require_contact
from rayher_crm.services.notifications import active_crm_users, create_notification, notify_if_reachable
from rayher_crm.services.opportunity_stages import DEMO_REQUEST_STAGES


EDITABLE_STATUSES = {"Draft", "Engineer Returned", "Manager Rejected"}
# A Demo Request is finished once it has become a Demo or was cancelled; before that it is in progress.
FINISHED_STATUSES = ("Converted", "Cancelled")
FORM_REQUIRED_FIELDS = (
    "industry", "salesContact", "demoOwner", "sizeShape", "material", "specificRequest",
    "detectMeasure", "expectedResults", "otherTools", "primaryTool", "timing",
    "keySuccessFactors", "internalQuestions", "customerQuestions",
)
WAFER_REQUIRED_FIELDS = (
    "slotId", "wid", "waferSpecificity", "notchFlat", "doiMetrologyItems", "resultFileProvided",
)


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return frappe.parse_json(value)
        except Exception:
            return default
    return value


def _active_crm_user(user_id: Any, expected_role: str | None = None) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM user.")
    user_id = user_id.strip()
    if not frappe.db.exists("User", {"name": user_id, "enabled": 1}):
        raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM user.")
    try:
        role = resolve_crm_role(user_id)
    except frappe.PermissionError as exc:
        raise CrmApiException("INVALID_OWNER", "Owner must be an active CRM user.") from exc
    if expected_role and role != expected_role:
        raise CrmApiException("INVALID_OWNER", f"Owner must be an active CRM {expected_role} user.")
    return user_id


def _contact_display(contact_id: str) -> str:
    contact = frappe.get_doc("Contact", contact_id) if frappe.db.exists("Contact", contact_id) else None
    if contact is None:
        raise CrmApiException("CONTACT_NOT_FOUND", "Contact was not found.")
    name = " ".join(part for part in (contact.first_name, contact.last_name) if part).strip() or contact_id
    email = contact.email_id or next((row.email_id for row in contact.email_ids if row.email_id), "")
    phone = contact.phone or next((row.phone for row in contact.phone_nos if row.phone), "")
    return ", ".join(part for part in (name, contact.designation, email, phone) if part)


def _validate_contact(contact_id: str, account_id: str) -> None:
    _require_contact(contact_id)
    if _contact_account(contact_id) != account_id:
        raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "The contact belongs to another account.")
    if frappe.db.get_value("Contact", contact_id, "custom_crm_status") != "Active":
        raise CrmApiException("CONTACT_INACTIVE", "The contact must be active.")


def _validate_opportunity(opportunity_id: Any, account_id: str) -> str:
    if opportunity_id in (None, ""):
        raise CrmApiException(
            "VALIDATION_ERROR",
            "opportunityId is required.",
            field_errors={"opportunityId": "Required"},
        )
    if not isinstance(opportunity_id, str) or not opportunity_id.strip():
        raise CrmApiException("LINK_MISMATCH", "Opportunity must belong to the Demo Request Account.")
    opportunity_id = opportunity_id.strip()
    if frappe.db.get_value("CRM Opportunity", opportunity_id, "account") != account_id:
        raise CrmApiException("LINK_MISMATCH", "Opportunity must belong to the Demo Request Account.")
    stage = frappe.db.get_value("CRM Opportunity", opportunity_id, "stage")
    if stage not in DEMO_REQUEST_STAGES:
        raise CrmApiException(
            "INVALID_TRANSITION",
            "Demo Request can only be created for an Opportunity in qualified_opportunity or demo_done.",
        )
    return opportunity_id


def _validate_form_data(value: Any, *, require_customer_information: bool = True) -> tuple[dict[str, Any], str, str]:
    if not isinstance(value, Mapping):
        raise CrmApiException("VALIDATION_ERROR", "formData must be a JSON object.", field_errors={"formData": "Required"})
    form = dict(value)
    normalized: dict[str, Any] = {}
    field_errors: dict[str, str] = {}
    for fieldname in FORM_REQUIRED_FIELDS:
        raw = form.get(fieldname)
        if fieldname == "industry" and not require_customer_information:
            normalized[fieldname] = raw.strip() if isinstance(raw, str) else ""
            continue
        if not isinstance(raw, str) or not raw.strip():
            field_errors[fieldname] = "Required"
        else:
            normalized[fieldname] = raw.strip()
    complementary = form.get("complementaryTool")
    normalized["complementaryTool"] = complementary.strip() if isinstance(complementary, str) else ""
    contact_person = form.get("contactPerson")
    normalized["contactPerson"] = contact_person.strip() if isinstance(contact_person, str) else ""

    wafers = form.get("wafers")
    normalized_wafers: list[dict[str, str]] = []
    if not isinstance(wafers, list) or not wafers:
        field_errors["wafers"] = "At least one wafer is required"
    else:
        for index, wafer in enumerate(wafers):
            if not isinstance(wafer, Mapping):
                field_errors[f"wafers.{index}"] = "Invalid wafer"
                continue
            normalized_wafer: dict[str, str] = {}
            for fieldname in WAFER_REQUIRED_FIELDS:
                raw = wafer.get(fieldname)
                if not isinstance(raw, str) or not raw.strip():
                    field_errors[f"wafers.{index}.{fieldname}"] = "Required"
                else:
                    normalized_wafer[fieldname] = raw.strip()
            normalized_wafers.append(normalized_wafer)
    if field_errors:
        raise CrmApiException("VALIDATION_ERROR", "Demo Request form is incomplete.", field_errors=field_errors)

    target_date = optional_date(normalized["timing"], "formData.timing")
    if not target_date:
        raise CrmApiException("VALIDATION_ERROR", "formData.timing is required.")
    sales_owner = resolve_write_owner(normalized["salesContact"])
    engineer_owner = _active_crm_user(normalized["demoOwner"], "Engineer")
    normalized["salesContact"] = sales_owner
    normalized["demoOwner"] = engineer_owner
    normalized["wafers"] = normalized_wafers
    return normalized, sales_owner, engineer_owner


def _validate_input(payload: dict[str, Any]) -> dict[str, Any]:
    request_mode = str(payload.get("requestMode") or "Opportunity").strip()
    if request_mode not in {"Opportunity", "Self Test"}:
        raise CrmApiException("VALIDATION_ERROR", "requestMode must be Opportunity or Self Test.")
    account_id = required_text(payload, "accountId") if request_mode == "Opportunity" else ""
    account = _require_account(account_id) if account_id else None
    contact_id = str(payload.get("primaryContactId") or "").strip() if account_id else ""
    if request_mode == "Opportunity" and not contact_id:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "primaryContactId is required.",
            field_errors={"primaryContactId": "Required"},
        )
    if contact_id:
        _validate_contact(contact_id, account_id)
    opportunity_id = (
        _validate_opportunity(payload.get("opportunityId"), account_id)
        if request_mode == "Opportunity" else None
    )
    form, sales_owner, engineer_owner = _validate_form_data(
        payload.get("formData"),
        require_customer_information=request_mode != "Self Test",
    )
    if contact_id:
        form["contactPerson"] = _contact_display(contact_id)
    customer_expected_date = optional_date(payload.get("customerExpectedDate"), "customerExpectedDate")
    if not customer_expected_date:
        raise CrmApiException("VALIDATION_ERROR", "customerExpectedDate is required.")
    requirement_id = payload.get("requirementId")
    if requirement_id is not None and not isinstance(requirement_id, str):
        raise CrmApiException("VALIDATION_ERROR", "requirementId must be a stable string id.")
    requirement_id = requirement_id.strip() if isinstance(requirement_id, str) else ""
    return {
        "account": account_id,
        "primary_contact": contact_id,
        "requirement_id": requirement_id or None,
        "request_mode": request_mode,
        "opportunity": opportunity_id,
        "sales_owner": sales_owner,
        "engineer_owner": engineer_owner,
        "form_data": form,
        "customer_expected_date": customer_expected_date,
        # A label the service puts together: cut to its column, so that a long tool name is refused
        # as the field the user typed (requested_equipment) and not as this one.
        "title": f"{account.customer_name if account else 'Self Test'} - {form['primaryTool']} Demo"[:140],
        "objective": form["detectMeasure"],
        "requested_equipment": form["primaryTool"],
        "sample_type": form["material"],
        "sample_quantity": len(form["wafers"]),
        "target_date": form["timing"],
        "priority": "High",
        "acceptance_criteria": form["keySuccessFactors"],
    }


def _append_history(request_id: str, from_status: str, to_status: str, comment: str) -> None:
    frappe.get_doc({
        "doctype": "CRM Demo Request History", "demo_request": request_id,
        "at": frappe.utils.now_datetime(), "actor": frappe.session.user,
        "from_status": from_status, "to_status": to_status, "comment": comment,
    }).insert(ignore_permissions=True)


def _history(request_id: str) -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CRM Demo Request History", filters={"demo_request": request_id},
        fields=["at", "actor", "from_status", "to_status", "comment"],
        order_by="at asc, creation asc, name asc", ignore_permissions=True,
    )
    return [{
        "at": to_iso_timestamp(row.at), "actor": row.actor, "from": row.from_status or "",
        "to": row.to_status, "comment": row.comment,
    } for row in rows]


def serialize_demo_request(doc) -> dict[str, Any]:
    form_data = _json_value(doc.form_data, {})
    tracking = _json_value(doc.tracking, {})
    result = {
        "id": doc.name,
        "accountId": doc.account,
        "accountName": frappe.db.get_value("Customer", doc.account, "customer_name") or doc.account or "Self Test",
        "primaryContactId": doc.primary_contact or "",
        "segment": frappe.db.get_value("Customer", doc.account, "custom_crm_segment") or "",
        "salesOwner": doc.sales_owner,
        "createdBy": doc.created_by_user,
        "title": doc.title,
        "objective": doc.objective,
        "requestedEquipment": doc.requested_equipment,
        "sampleType": doc.sample_type,
        "sampleQuantity": int(doc.sample_quantity or 0),
        "targetDate": str(doc.target_date or ""),
        "customerExpectedDate": str(doc.customer_expected_date or ""),
        "priority": doc.priority,
        "acceptanceCriteria": doc.acceptance_criteria,
        "status": doc.status,
        "engineerOwner": doc.engineer_owner,
        "feasibility": doc.feasibility or "",
        "testPlan": doc.test_plan or "",
        "assignedEquipment": doc.assigned_equipment or "",
        "resourceWindow": doc.resource_window or "",
        "estimatedCompletionDate": str(doc.estimated_completion_date or ""),
        "technicalRisk": doc.technical_risk or "",
        "engineerComment": doc.engineer_comment or "",
        "managerDecision": doc.manager_decision or "",
        "managerComment": doc.manager_comment or "",
        "tracking": tracking,
        "formData": form_data,
        "createdAt": to_iso_timestamp(doc.creation),
        "updatedAt": to_iso_timestamp(doc.modified),
        "modified": to_iso_timestamp(doc.modified),
        "history": _history(doc.name),
    }
    optional = {
        "requirementId": doc.requirement_id,
        "opportunityId": doc.opportunity,
        "preparedBy": doc.prepared_by,
        "preparedDate": str(doc.prepared_date or ""),
        "approvedBy": doc.approved_by,
        "approvedDate": str(doc.approved_date or ""),
        "evaluationId": doc.evaluation,
    }
    result["requestMode"] = getattr(doc, "request_mode", None) or "Opportunity"
    result.update({key: value for key, value in optional.items() if value})
    return result


def _require_demo_request(name: str):
    if not frappe.db.exists("CRM Demo Request", name):
        raise CrmApiException("DEMO_REQUEST_NOT_FOUND", "Demo Request was not found.")
    doc = frappe.get_doc("CRM Demo Request", name)
    # The row condition alone, not frappe.has_permission, which would also honour a DocShare on the request.
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Demo Request is outside the current user scope.")
    return doc


def list_demo_requests(query: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    assert_capability("demo_request:view")
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    where = [f"({conditions_for_doctype('CRM Demo Request')})"]
    values: list[Any] = []
    for query_field, column in (
        ("accountId", "account"), ("owner", "sales_owner"),
        ("contactId", "primary_contact"), ("status", "status"),
    ):
        value = query.get(query_field)
        if value and value != "All":
            where.append(f"`{column}` = %s")
            values.append(value)
    if str(query.get("inProgress") or "").strip().lower() in {"1", "true"}:
        # The Demo Request workspace works on what is still to be done. Asking for that here keeps the
        # pages and the total about those records, where a page filtered afterwards came up short.
        where.append(f"`status` NOT IN ({', '.join(['%s'] * len(FINISHED_STATUSES))})")
        values.extend(FINISHED_STATUSES)
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        where.append("(`title` LIKE %s OR `requested_equipment` LIKE %s OR `account` LIKE %s)")
        values.extend([pattern, pattern, pattern])
    date_from = optional_date(query.get("dateFrom"), "dateFrom")
    date_to = optional_date(query.get("dateTo"), "dateTo")
    if date_from and date_to and date_from > date_to:
        raise CrmApiException("VALIDATION_ERROR", "dateFrom must not be later than dateTo.")
    event_date = "COALESCE(`customer_expected_date`, `target_date`)"
    if date_from:
        where.append(f"{event_date} >= %s")
        values.append(date_from)
    if date_to:
        where.append(f"{event_date} <= %s")
        values.append(date_to)
    where_sql = " AND ".join(where)
    total = int(frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabCRM Demo Request` WHERE {where_sql}", tuple(values),
    )[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Demo Request` WHERE {where_sql} "
        "ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]), as_dict=True,
    )
    return [serialize_demo_request(frappe.get_doc("CRM Demo Request", row.name)) for row in rows], total, page, page_size


def get_demo_request(name: str) -> dict[str, Any]:
    assert_capability("demo_request:view")
    return serialize_demo_request(_require_demo_request(name))


def _apply_values(doc, values: dict[str, Any]) -> None:
    for fieldname in (
        "account", "primary_contact", "requirement_id", "request_mode", "opportunity", "sales_owner", "engineer_owner",
        "customer_expected_date", "title", "objective", "requested_equipment", "sample_type",
        "sample_quantity", "target_date", "priority", "acceptance_criteria",
    ):
        setattr(doc, fieldname, values[fieldname])
    doc.form_data = values["form_data"]


def _notify_engineer_review(doc, summary: str) -> None:
    if not doc.engineer_owner or doc.engineer_owner == frappe.session.user:
        return
    notify_if_reachable(
        recipient=doc.engineer_owner,
        category="Demo",
        title="Demo Request requires engineering review",
        message=f"{doc.title}: {summary}",
        route=f"/demo-workflow/{doc.name}?tab=information",
        source_doctype="CRM Demo Request",
        source_name=doc.name,
    )


def create_demo_request(
    payload: dict[str, Any],
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    assert_capability("demo_request:create")
    ensure_server_generated_id(payload)
    values = _validate_input(payload)
    status = "Engineer Review" if payload.get("submit") is True else "Draft"
    now = frappe.utils.now_datetime()
    savepoint = f"crm_demo_create_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        if values["opportunity"]:
            # Lock the Opportunity so two requests cannot both pass the active-request check,
            # and re-check its stage under that lock.
            locked = frappe.db.sql(
                "SELECT `stage` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE",
                (values["opportunity"],),
            )
            if not locked or locked[0][0] not in DEMO_REQUEST_STAGES:
                raise CrmApiException(
                    "INVALID_TRANSITION",
                    "Demo Request can only be created for an Opportunity in qualified_opportunity or demo_done.",
                )
            active_request = frappe.db.get_value(
                "CRM Demo Request",
                {
                    "opportunity": values["opportunity"],
                    "status": ["not in", ["Cancelled", "Converted"]],
                },
                "name",
            )
            if active_request:
                raise CrmApiException(
                    "CONFLICT",
                    "The Opportunity already has an active Demo Request.",
                )
        if failure_injector:
            failure_injector("after_opportunity_advance")
        doc = frappe.get_doc({
            "doctype": "CRM Demo Request", "created_by_user": frappe.session.user,
            "status": status, "feasibility": "Pending" if status == "Engineer Review" else "",
            "tracking": {
                "lastProgressAt": to_iso_timestamp(now),
                "lastProgressSummary": "Created and submitted for Engineer Review" if status == "Engineer Review" else "Created Demo Request draft",
                "lastProgressActor": frappe.session.user,
                "nextAction": "", "nextActionOwner": "", "nextActionDue": "",
            },
            "prepared_by": frappe.session.user, "prepared_date": frappe.utils.today(),
        })
        _apply_values(doc, values)
        doc.insert(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_request_insert")
        history_summary = "Created and submitted for Engineer Review" if status == "Engineer Review" else "Created Demo Request draft"
        _append_history(doc.name, "", status, history_summary)
        if status == "Engineer Review":
            _notify_engineer_review(doc, history_summary)
            if failure_injector:
                failure_injector("after_notification_insert")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_demo_request(doc)


def update_demo_request(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("demo_request:create")
    current = _require_demo_request(name)
    requested_mode = str(payload.get("requestMode") or "Opportunity").strip()
    requested_opportunity = str(payload.get("opportunityId") or "").strip() or None
    if (
        requested_mode != (current.request_mode or "Opportunity")
        or requested_opportunity != current.opportunity
    ):
        raise CrmApiException(
            "VALIDATION_ERROR",
            "The Opportunity linked to a Demo Request cannot be changed.",
            field_errors={"opportunityId": "Cannot be changed after creation"},
        )
    if current.status not in EDITABLE_STATUSES:
        raise CrmApiException("INVALID_TRANSITION", "The Demo Request cannot be edited in its current status.")
    values = _validate_input(payload)
    doc = lock_document("CRM Demo Request", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("CRM Demo Request", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Demo Request is outside the current user scope.")
    if doc.status not in EDITABLE_STATUSES:
        raise CrmApiException("INVALID_TRANSITION", "The Demo Request cannot be edited in its current status.")
    if values["request_mode"] != (doc.request_mode or "Opportunity") or values["opportunity"] != doc.opportunity:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "The Opportunity linked to a Demo Request cannot be changed.",
            field_errors={"opportunityId": "Cannot be changed after creation"},
        )
    from_status = doc.status
    _apply_values(doc, values)
    if payload.get("submit") is True:
        doc.status = "Engineer Review"
        doc.feasibility = "Pending"
        doc.manager_decision = ""
        doc.manager_comment = ""
    doc.prepared_by = frappe.session.user
    doc.prepared_date = frappe.utils.today()
    doc.tracking = {
        "lastProgressAt": to_iso_timestamp(frappe.utils.now_datetime()),
        "lastProgressSummary": "Updated and submitted for Engineer Review" if payload.get("submit") is True else "Updated Demo Request",
        "lastProgressActor": frappe.session.user,
        "nextAction": "", "nextActionOwner": "", "nextActionDue": "",
    }
    doc.save(ignore_permissions=True)
    _append_history(
        doc.name, from_status, doc.status,
        "Updated and submitted for Engineer Review" if payload.get("submit") is True else "Updated Demo Request",
    )
    if payload.get("submit") is True:
        _notify_engineer_review(doc, "Updated and submitted for Engineer Review")
    doc.reload()
    return serialize_demo_request(doc)


def _lock_demo_request(name: str):
    rows = frappe.db.sql(
        "SELECT `name` FROM `tabCRM Demo Request` WHERE `name` = %s FOR UPDATE", (name,),
    )
    if not rows:
        raise CrmApiException("DEMO_REQUEST_NOT_FOUND", "Demo Request was not found.")
    return frappe.get_doc("CRM Demo Request", name)


def _transition_comment(command: Mapping[str, Any], fieldname: str = "comment", *, required: bool = True) -> str:
    value = command.get(fieldname)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if required:
        raise CrmApiException("VALIDATION_ERROR", f"{fieldname} is required.", field_errors={fieldname: "Required"})
    return ""


def _serialize_evaluation(doc) -> dict[str, Any]:
    from rayher_crm.services.evaluations import serialize_evaluation

    return serialize_evaluation(doc)


def _submitted_once(request_id: str) -> bool:
    """Whether Sales ever submitted the request for Engineer Review: from then on its Engineer reads it."""

    return bool(frappe.db.exists(
        "CRM Demo Request History", {"demo_request": request_id, "to_status": "Engineer Review"},
    ))


def _notify_transition(doc, command_type: str, summary: str) -> None:
    recipients = {
        "submit": {doc.engineer_owner},
        "cancel": {doc.engineer_owner},
        "engineer_return": {doc.sales_owner},
        "engineer_approve": {doc.sales_owner, *active_crm_users("Manager")},
        "manager_reject": {doc.sales_owner, doc.engineer_owner},
        "manager_approve": {doc.sales_owner, doc.engineer_owner},
    }[command_type] - {frappe.session.user, None, ""}
    # A draft cancelled before it was ever submitted was never the Engineer's to see: no notice of it either.
    if command_type == "cancel" and not _submitted_once(doc.name):
        recipients.discard(doc.engineer_owner)
    for recipient in sorted(recipients):
        notify_if_reachable(
            recipient=recipient,
            category="Demo",
            title=f"Demo Request moved to {doc.status}",
            message=f"{doc.title}: {summary}",
            route=f"/demo-workflow/{doc.name}?tab=information",
            source_doctype="CRM Demo Request",
            source_name=doc.name,
        )


def transition_demo_request(
    name: str,
    command: dict[str, Any],
    expected_modified: Any = None,
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not isinstance(command, Mapping):
        raise CrmApiException("VALIDATION_ERROR", "command must be a JSON object.")
    command_type = command.get("type")
    capability = {
        "submit": "demo_request:create",
        "cancel": "demo_request:create",
        "engineer_return": "demo_request:engineering_review",
        "engineer_approve": "demo_request:engineering_review",
        "manager_reject": "demo_request:manager_approve",
        "manager_approve": "demo_request:manager_approve",
    }.get(command_type)
    if not capability:
        raise CrmApiException("VALIDATION_ERROR", "Unknown Demo Request command.")
    assert_capability(capability)
    role = resolve_crm_role()
    if command_type in {"manager_reject", "manager_approve"} and role != "Manager":
        raise frappe.PermissionError("Only CRM Manager may approve or reject Demo Requests.")

    current = _require_demo_request(name)
    if command_type == "manager_approve" and current.evaluation:
        raise CrmApiException("EVALUATION_EXISTS", "The Demo Request already has an Evaluation.")
    doc = lock_document("CRM Demo Request", name, expected_modified, "NOT_FOUND") \
        if expected_modified is not None else _lock_demo_request(name)
    if not frappe.has_permission("CRM Demo Request", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Demo Request is outside the current user scope.")
    if command_type == "manager_approve" and doc.evaluation:
        raise CrmApiException("EVALUATION_EXISTS", "The Demo Request already has an Evaluation.")

    from_status = doc.status
    evaluation = None
    history_comment = ""
    if command_type == "submit":
        if from_status not in EDITABLE_STATUSES:
            raise CrmApiException("INVALID_TRANSITION", "The Demo Request cannot be submitted from its current status.")
        doc.status = "Engineer Review"
        doc.feasibility = "Pending"
        doc.manager_decision = ""
        doc.manager_comment = ""
        history_comment = "Sales submitted for Engineer Review"
    elif command_type == "cancel":
        if from_status not in EDITABLE_STATUSES:
            raise CrmApiException("INVALID_TRANSITION", "The Demo Request cannot be cancelled from its current status.")
        doc.status = "Cancelled"
        history_comment = _transition_comment(command, required=False) or "Sales cancelled Demo Request"
    elif command_type == "engineer_return":
        if from_status != "Engineer Review":
            raise CrmApiException("INVALID_TRANSITION", "Only a Demo Request in Engineer Review can be returned.")
        comment = _transition_comment(command)
        doc.status = "Engineer Returned"
        doc.feasibility = "Need More Info"
        doc.engineer_comment = comment
        history_comment = f"Engineer returned: {comment}"
    elif command_type == "engineer_approve":
        if from_status != "Engineer Review":
            raise CrmApiException("INVALID_TRANSITION", "Only a Demo Request in Engineer Review can be approved by Engineer.")
        required_values = {
            fieldname: _transition_comment(command, fieldname)
            for fieldname in (
                "engineerOwner", "testPlan", "assignedEquipment", "resourceWindow",
                "estimatedCompletionDate", "technicalRisk", "comment",
            )
        }
        completion_date = optional_date(required_values["estimatedCompletionDate"], "estimatedCompletionDate")
        next_engineer = _active_crm_user(required_values["engineerOwner"], "Engineer")
        if role == "Engineer" and next_engineer != doc.engineer_owner:
            raise CrmApiException("PERMISSION_DENIED", "Engineer cannot reassign Demo Request ownership.")
        previous_engineer = doc.engineer_owner
        doc.status = "Manager Approval"
        doc.feasibility = "Feasible"
        doc.engineer_owner = next_engineer
        doc.test_plan = required_values["testPlan"]
        doc.assigned_equipment = required_values["assignedEquipment"]
        doc.resource_window = required_values["resourceWindow"]
        doc.estimated_completion_date = completion_date
        doc.technical_risk = required_values["technicalRisk"]
        doc.engineer_comment = required_values["comment"]
        doc.manager_decision = "Pending"
        history_comment = f"Engineer approved: {required_values['comment']}"
        if previous_engineer != next_engineer:
            history_comment += f"; owner {previous_engineer} -> {next_engineer}"
    elif command_type == "manager_reject":
        if from_status != "Manager Approval":
            raise CrmApiException("INVALID_TRANSITION", "Only a Demo Request in Manager Approval can be rejected.")
        comment = _transition_comment(command)
        doc.status = "Manager Rejected"
        doc.manager_decision = "Rejected"
        doc.manager_comment = comment
        history_comment = comment
    else:
        if from_status != "Manager Approval":
            raise CrmApiException("INVALID_TRANSITION", "Only a Demo Request in Manager Approval can be approved.")
        comment = _transition_comment(command, required=False)
        history_comment = comment or "Manager approved Demo Request"

    savepoint = f"crm_demo_transition_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        if command_type == "manager_approve":
            evaluation = frappe.get_doc({
                "doctype": "CRM Evaluation", "account": doc.account,
                "requirement_id": doc.requirement_id, "demo_request": doc.name,
                "title": doc.title, "status": "Requested", "evaluation_owner": doc.engineer_owner,
                "planned_end": doc.estimated_completion_date or doc.target_date,
                "wafer_preparation_status": "Pending",
                "test_preparation_status": "Pending",
                "acceptance": "Pending", "report_status": "Not Ready",
                "report_version": 0, "criteria": doc.acceptance_criteria,
            }).insert(ignore_permissions=True)
            from rayher_crm.services.evaluations import append_evaluation_history

            append_evaluation_history(
                evaluation, "Created", f"Created from Demo Request {doc.name}", "", "Requested",
            )
            if failure_injector:
                failure_injector("after_evaluation_insert")
            doc.status = "Converted"
            doc.manager_decision = "Approved"
            doc.manager_comment = _transition_comment(command, required=False)
            doc.evaluation = evaluation.name
            doc.approved_by = frappe.session.user
            doc.approved_date = frappe.utils.today()
            history_comment = f"Manager approved and created {evaluation.name}"
            if doc.manager_comment:
                history_comment += f": {doc.manager_comment}"

        now = frappe.utils.now_datetime()
        doc.tracking = {
            "lastProgressAt": to_iso_timestamp(now), "lastProgressSummary": history_comment,
            "lastProgressActor": frappe.session.user,
            "nextAction": "", "nextActionOwner": "", "nextActionDue": "",
        }
        doc.save(ignore_permissions=True)
        if failure_injector:
            failure_injector("after_request_update")
        _append_history(doc.name, from_status, doc.status, history_comment)
        if failure_injector:
            failure_injector("after_history_insert")
        _notify_transition(doc, command_type, history_comment)
        if failure_injector:
            failure_injector("after_notification_insert")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise

    doc.reload()
    if evaluation:
        evaluation.reload()
    return {
        "request": serialize_demo_request(doc),
        "evaluation": _serialize_evaluation(evaluation) if evaluation else None,
    }


def serialize_comment(doc) -> dict[str, Any]:
    mentioned_people = _json_value(getattr(doc, "mentioned_people", None), [])
    if not mentioned_people and doc.mentioned_person:
        mentioned_people = [{
            "id": doc.mentioned_person,
            "name": doc.mentioned_person_label or doc.mentioned_person,
        }]
    result = {
        "id": doc.name, "demoRequestId": doc.demo_request, "author": doc.author,
        "role": doc.role, "body": doc.body, "mentionedPeople": mentioned_people,
        "createdAt": to_iso_timestamp(doc.at),
    }
    if doc.mentioned_person:
        result["mentionedPersonId"] = doc.mentioned_person
        result["mentionedPerson"] = doc.mentioned_person_label or doc.mentioned_person
    return result


def list_demo_comments(demo_request_id: str, query: dict[str, Any] | None = None):
    assert_capability("demo_request:view")
    _require_demo_request(demo_request_id)
    filters = {"demo_request": demo_request_id}
    if query is None:
        rows = frappe.get_all(
            "CRM Demo Comment", filters=filters, pluck="name",
            order_by="at desc, creation desc, name desc", ignore_permissions=True,
        )
        return [serialize_comment(frappe.get_doc("CRM Demo Comment", name)) for name in rows]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    total = int(frappe.db.count("CRM Demo Comment", filters=filters))
    rows = frappe.get_all(
        "CRM Demo Comment", filters=filters, pluck="name",
        order_by="at desc, creation desc, name desc", start=offset, page_length=page_size,
        ignore_permissions=True,
    )
    return [serialize_comment(frappe.get_doc("CRM Demo Comment", name)) for name in rows], total, page, page_size


def add_demo_comment(demo_request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("demo_request:view")
    request = _require_demo_request(demo_request_id)
    body = required_text(payload, "body")
    mentioned_ids = payload.get("mentionedPersonIds")
    if mentioned_ids is None:
        mentioned_ids = [payload["mentionedPersonId"]] if payload.get("mentionedPersonId") else []
    if not isinstance(mentioned_ids, list):
        raise CrmApiException("INVALID_OWNER", "Mentioned users must be a list.")
    mentioned_people = []
    for mentioned_person in dict.fromkeys(mentioned_ids):
        mentioned_person = _active_crm_user(mentioned_person)
        if not has_crm_permission(request, user=mentioned_person, permission_type="read"):
            raise CrmApiException(
                "INVALID_OWNER", "Mentioned user must have access to this Demo Request.",
            )
        mentioned_people.append({
            "id": mentioned_person,
            "name": frappe.db.get_value("User", mentioned_person, "full_name") or mentioned_person,
        })
    mentioned_person = mentioned_people[0]["id"] if mentioned_people else None
    mentioned_label = mentioned_people[0]["name"] if mentioned_people else None
    savepoint = f"crm_demo_comment_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc = frappe.get_doc({
            "doctype": "CRM Demo Comment", "demo_request": demo_request_id,
            "author": frappe.session.user, "role": resolve_crm_role(), "body": body,
            "mentioned_person": mentioned_person, "mentioned_person_label": mentioned_label,
            "mentioned_people": json.dumps(mentioned_people, ensure_ascii=False),
            "at": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True)
        for mentioned in mentioned_people:
            if mentioned["id"] == frappe.session.user:
                continue
            create_notification(
                recipient=mentioned["id"], category="Demo",
                title="You were mentioned in a Demo comment",
                message=body,
                route=f"/demo-workflow/{demo_request_id}?tab=comment",
                source_doctype="CRM Demo Comment", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_comment(doc)
