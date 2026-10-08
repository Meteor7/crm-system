"""Blue Sheet red flags, current warnings and opt-in probability suggestions."""
import json

import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import has_crm_permission
from rayher_crm.services import blue_sheet_rules as rules
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.equipment_names import equipment_key
from rayher_crm.services.opportunity_stages import CLOSED_STAGES, OPEN_STAGES
from rayher_crm.setup.indexes import OPPORTUNITY_STAKEHOLDER_INDEX


STAKEHOLDER_QUERY = f"""SELECT name, contact, role, stance, modified
    FROM `tabCRM Opportunity Stakeholder` FORCE INDEX (`{OPPORTUNITY_STAKEHOLDER_INDEX}`)
    WHERE opportunity=%s AND archived=0 ORDER BY name"""


def flags(doc):
    return rules.red_flags(doc.name, doc.get("red_flag_records"), doc.red_flags)


def _current(name, expected_modified):
    from rayher_crm.services.opportunities import _require_opportunity
    from rayher_crm.services.opportunity_status import _lock_write_scope
    _require_opportunity(name)
    # Recheck the Customer's current owner/visibility, even after an older RR snapshot.
    _lock_write_scope(name)
    lock_document("CRM Opportunity", name, expected_modified, "NOT_FOUND")
    doc = frappe.get_doc("CRM Opportunity", name, for_update=True)
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")
    return doc


def save_flags(name, payload, expected_modified):
    from rayher_crm.services.opportunities import _append_history, serialize_opportunity
    assert_capability("deal:write")
    doc = _current(name, expected_modified)
    if set(payload) != {"items"}:
        raise CrmApiException("VALIDATION_ERROR", "Provide the red flag items.")
    before = flags(doc)
    try:
        after = rules.update_flags(before, payload["items"], lambda: frappe.generate_hash(length=32),
                                   to_iso_timestamp(frappe.utils.now_datetime()), frappe.session.user)
    except ValueError as exc:
        raise CrmApiException("VALIDATION_ERROR", str(exc)) from exc
    if before != after:
        savepoint = "blue_sheet_flags_" + frappe.generate_hash(length=8)
        frappe.db.savepoint(savepoint)
        try:
            doc.red_flag_records = json.dumps(after, ensure_ascii=False)
            doc.red_flags = json.dumps([row["text"] for row in after], ensure_ascii=False)
            doc.save(ignore_permissions=True, ignore_version=False)
            _append_history(doc.name, "red_flag_records", before, after)
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            raise
    return serialize_opportunity(doc)


def _assessment(doc, *, current=False):
    stakeholders = frappe.db.sql(STAKEHOLDER_QUERY + (" FOR UPDATE" if current else ""), (doc.name,), as_dict=True)
    # Child edits do not advance the parent version. Include identity and every
    # child revision, including a contact rebind with the same role and stance.
    stakeholders = [{**row, "modified": to_iso_timestamp(row.modified) if row.modified else None} for row in stakeholders]
    records = flags(doc)
    config = frappe.conf.get("crm_blue_sheet_probability_rules")
    result = rules.assess(records, stakeholders, config)
    version = to_iso_timestamp(doc.modified)
    result.update(opportunityModified=version, currentLevel=doc.probability_level or "",
                  canApply=doc.opportunity_owner == frappe.session.user and doc.stage not in CLOSED_STAGES,
                  fingerprint=rules.fingerprint({"id": doc.name, "modified": version, "config": config,
                                                 "flags": records, "stakeholders": stakeholders}))
    if doc.stage in CLOSED_STAGES:
        result.update(state="closed", suggestedLevel=None, ruleId=None, reason=None)
    return result


def get_assessment(name):
    from rayher_crm.services.opportunities import _require_opportunity
    assert_capability("deal:view")
    if resolve_crm_role() not in {"Manager", "Sales"}:
        raise CrmApiException("PERMISSION_DENIED", "Blue Sheet assessment requires stakeholder access.")
    return _assessment(_require_opportunity(name))


def apply_suggestion(name, payload, expected_modified):
    from rayher_crm.services.opportunities import update_strategy_opportunity, _append_history, serialize_opportunity, _require_opportunity
    from rayher_crm.services.cockpit_identity import lock_opportunity_owners, check_current_opportunity_owner
    assert_capability("deal:write")
    if resolve_crm_role() not in {"Manager", "Sales"}:
        raise CrmApiException("PERMISSION_DENIED", "Blue Sheet assessment requires stakeholder access.")
    if set(payload) - {"fingerprint", "probabilityReason", "probabilityActionPlan"}:
        raise CrmApiException("VALIDATION_ERROR", "Unsupported suggestion confirmation field.")
    _require_opportunity(name)
    # Match the strategy editor and native User rename: User before Opportunity.
    identities = lock_opportunity_owners(name, {})
    doc = _current(name, expected_modified)
    check_current_opportunity_owner(name, identities)
    assessment = _assessment(doc, current=True)
    if payload.get("fingerprint") != assessment["fingerprint"]:
        raise CrmApiException("VERSION_CONFLICT", "Blue Sheet facts or rules changed. Refresh the suggestion.")
    if assessment["state"] != "suggested" or not assessment["canApply"]:
        raise CrmApiException("INVALID_TRANSITION", "Only the owner can confirm an available suggestion for an open Opportunity.")
    if assessment["suggestedLevel"] == doc.probability_level:
        return serialize_opportunity(doc)
    savepoint = "blue_sheet_apply_" + frappe.generate_hash(length=8)
    frappe.db.savepoint(savepoint)
    try:
        update_strategy_opportunity(doc.name, {"probabilityLevel": assessment["suggestedLevel"],
            "probabilityReason": payload.get("probabilityReason"),
            "probabilityActionPlan": payload.get("probabilityActionPlan")}, expected_modified)
        _append_history(doc.name, "blueSheetSuggestion", doc.probability_level or "", assessment)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return serialize_opportunity(frappe.get_doc("CRM Opportunity", doc.name, for_update=True))


def warning_rows(opportunities, customers, query):
    """Current unresolved flags on readable open deals, independent of report dates."""
    if not opportunities or not frappe.has_permission("CRM Opportunity", "read"):
        return []
    rows = frappe.get_list("CRM Opportunity", filters={"name": ["in", [row["name"] for row in opportunities]], "stage": ["in", OPEN_STAGES]},
        fields=["name", "title", "account", "opportunity_owner", "tool_type", "red_flags", "red_flag_records"], limit_page_length=0)
    names = {row["name"]: row["customer_name"] for row in customers}
    result = []
    for row in rows:
        if query.get("sales") and row.opportunity_owner != query["sales"]:
            continue
        if query.get("equipment") and equipment_key(row.tool_type) != equipment_key(query["equipment"]):
            continue
        for flag in flags(row):
            if flag["status"] == "Open":
                result.append({"id": row.name, "eventId": flag["id"], "title": row.title, "customer": names.get(row.account, row.account),
                               "accountId": row.account, "kind": "opportunity", "at": flag["updatedAt"],
                               "owner": row.opportunity_owner, "redFlagText": flag["text"], "redFlagSeverity": flag["severity"],
                               "redFlagUpdatedAt": flag["updatedAt"]})
    rank = {"High": 0, "Medium": 1, "Low": 2, "": 3}
    return sorted(result, key=lambda row: (rank[row["redFlagSeverity"]], row["id"], row["eventId"]))
