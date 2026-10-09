"""Scheduling and follow-ups belong to the original quotation, including account-only quotes."""
import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import as_payload, normalize_expected_modified, optional_date, required_text, to_iso_timestamp
from rayher_crm.services.opportunity_archive import assert_opportunity_not_archived
from rayher_crm.services.opportunity_stages import OPEN_STAGES
from rayher_crm.services.quotations import _require_quotation


def dto(master):
    return {"quotationId": master.name, "modified": to_iso_timestamp(master.modified),
            "plannedSendDate": str(master.planned_send_date) if master.planned_send_date else None,
            "followUps": [{"id": row.name, "title": row.title, "due": str(row.due), "status": row.status,
                           "note": row.note or "", "completedAt": to_iso_timestamp(row.completed_at) if row.completed_at else None,
                           "completedVersion": row.completed_version or None} for row in master.follow_ups]}


def get_planning(quotation_id):
    assert_capability("quotation:view")
    return dto(_require_quotation(quotation_id))


def locked(quotation_id, expected_modified):
    assert_capability("quotation:write")
    # Check authorization before returning a version conflict; lock both current
    # ownership rows so an earlier RR snapshot cannot retain revoked access.
    _require_quotation(quotation_id)
    rows = frappe.db.sql(
        """SELECT q.quotation_owner, q.modified, q.current_version, q.current_published_version,
                  c.name AS account, c.custom_crm_owner, c.custom_crm_visibility,
                  q.opportunity, o.stage, o.archived AS opportunity_archived
             FROM `tabCRM Quotation` q
             LEFT JOIN `tabCustomer` c ON c.name=q.account
             LEFT JOIN `tabCRM Opportunity` o ON o.name=q.opportunity
            WHERE q.name=%s FOR UPDATE""", (quotation_id,), as_dict=True,
    )
    if not rows:
        raise CrmApiException("NOT_FOUND", "Quotation was not found.")
    row = rows[0]
    if resolve_crm_role() == "Sales" and (
        row.quotation_owner != frappe.session.user or not row.account
        or (row.custom_crm_owner != frappe.session.user and row.custom_crm_visibility != "Public")
    ):
        raise CrmApiException("SCOPE_DENIED", "Quotation is outside the current user scope.")
    # A Quotation of an archived Opportunity is frozen with it, its send plan and its follow-ups too: the flag as
    # committed, the Opportunity's row read under its lock by the join above, after the Quotation's and its Account's.
    assert_opportunity_not_archived(row.opportunity_archived)
    if normalize_expected_modified(expected_modified) != to_iso_timestamp(row.modified):
        raise CrmApiException("VERSION_CONFLICT", "Quotation changed; reload before saving its plan.")
    return frappe.get_doc("CRM Quotation", quotation_id, for_update=True), row


def open_version(master, scope):
    if scope.opportunity and scope.stage not in OPEN_STAGES:
        return None
    if not master.current_published_version:
        return None
    version = frappe.get_doc("CRM Quotation Version", master.current_published_version, for_update=True)
    return version if version.quotation == master.name and version.status in {"Published", "Expired"} else None


def save_schedule(quotation_id, payload, expected_modified):
    payload = as_payload(payload)
    date = optional_date(payload.get("plannedSendDate"), "plannedSendDate")
    master, scope = locked(quotation_id, expected_modified)
    if date:
        version = frappe.get_doc("CRM Quotation Version", master.current_version, for_update=True) if master.current_version else None
        if not version or version.quotation != master.name or version.status != "Draft" or (scope.opportunity and scope.stage not in OPEN_STAGES):
            raise CrmApiException("INVALID_TRANSITION", "Schedule only a current draft on an open quotation.")
    master.planned_send_date = date
    return persist(master)


def save_follow_up(quotation_id, payload, follow_up_id=None, expected_modified=None):
    payload = as_payload(payload)
    title = required_text(payload, "title")
    if len(title) > 140:
        raise CrmApiException("VALIDATION_ERROR", "Title must be at most 140 characters.")
    due = optional_date(payload.get("due"), "due")
    status = payload.get("status")
    note = payload.get("note") or ""
    if not due or status not in ("Open", "Done", "Cancelled") or not isinstance(note, str) or len(note) > 10000:
        raise CrmApiException("VALIDATION_ERROR", "Provide a due date, valid status and a note up to 10000 characters.")
    master, scope = locked(quotation_id, expected_modified)
    current = next((row for row in master.follow_ups if row.name == follow_up_id), None) if follow_up_id else None
    if follow_up_id and current is None:
        raise CrmApiException("NOT_FOUND", "Follow-up was not found on this quotation.")
    version = open_version(master, scope)
    was_done = bool(current and current.status == "Done")
    if (status == "Open" or (status == "Done" and not was_done)) and not version:
        raise CrmApiException("INVALID_TRANSITION", "The quotation must have an open published version for a follow-up.")
    if current is None and len(master.follow_ups) >= 1000:
        raise CrmApiException("VALIDATION_ERROR", "This quotation has reached the follow-up limit.")
    row = current or master.append("follow_ups", {})
    row.update({"title": title, "due": due, "status": status, "note": note.strip()})
    if status == "Done" and not was_done:
        row.completed_at = frappe.utils.now_datetime()
        row.completed_owner = master.quotation_owner
        row.completed_version = version.name
    elif status != "Done":
        row.completed_at = row.completed_owner = row.completed_version = None
    return persist(master)


def persist(master):
    savepoint = "quote_planning_" + frappe.generate_hash(length=8)
    frappe.db.savepoint(savepoint)
    try:
        master.save(ignore_permissions=True, ignore_version=False)
        return dto(master)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
