"""Read-through Opportunity library: no copied files or external storage writes."""
import frappe

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, capabilities_for_user
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.document_links import scorecard_url
from rayher_crm.services.opportunities import _require_opportunity, _append_history
from rayher_crm.services import demo_artifacts, opportunity_status

LINKS = {"productScorecard": "product_scorecard_url", "dealScorecard": "deal_scorecard_url"}


def _links(doc):
    result = {}
    for key, column in LINKS.items():
        raw = doc.get(column) or ""
        try:
            result[key] = {"url": scorecard_url(raw), "state": "ready" if raw.strip() else "missing"}
        except ValueError:
            # Imported legacy values must never become executable links.
            result[key] = {"url": "", "state": "invalid"}
    return result


def _visible(doctype, opportunity_id):
    for name in frappe.get_all(doctype, filters={"opportunity": opportunity_id}, pluck="name",
                               order_by="modified desc, name asc", limit_page_length=0):
        doc = frappe.get_doc(doctype, name)
        if frappe.has_permission(doctype, "read", doc=doc, user=frappe.session.user):
            yield doc


def get_documents(opportunity_id):
    assert_capability("deal:view")
    doc = _require_opportunity(opportunity_id)
    capabilities = set(capabilities_for_user())
    groups = []
    status_items = []
    for record in opportunity_status.list_records(opportunity_id):
        for file in record["files"]:
            status_items.append({"id": file["id"], "title": file["fileName"], "recordId": record["id"],
                                 "at": record["updatedAt"], "fileId": file["id"], "sourceId": opportunity_id})
    groups.append({"kind": "status", "items": status_items})
    for kind, doctype, capability, title_field in (
        ("rfq", "CRM RFQ", "rfq:view", "name"),
        ("quotation", "CRM Quotation", "quotation:view", "ref_no"),
        ("visit", "CRM Visit", "visit:view", "subject"),
    ):
        if capability not in capabilities:
            continue
        items = [{"id": row.name, "sourceId": row.name, "title": row.get(title_field) or row.name,
                  "status": row.status, "at": to_iso_timestamp(row.modified)}
                 for row in _visible(doctype, opportunity_id)]
        groups.append({"kind": kind, "items": items})
    if "demo_request:view" in capabilities:
        items = []
        for request in _visible("CRM Demo Request", opportunity_id):
            for artifact in demo_artifacts.list_demo_artifacts(request.name):
                items.append({"id": artifact["id"], "sourceId": request.name, "fileId": artifact["id"],
                              "title": artifact["fileName"], "status": artifact["type"],
                              "version": artifact["version"], "at": artifact["createdAt"]})
        groups.append({"kind": "demo", "items": items})
    return {"opportunityId": doc.name, "title": doc.title, "modified": to_iso_timestamp(doc.modified),
            "archived": bool(doc.archived), "links": _links(doc), "groups": groups}


def save_links(opportunity_id, payload, expected_modified):
    assert_capability("deal:write")
    _require_opportunity(opportunity_id)
    if not isinstance(payload, dict) or set(payload) - set(LINKS) or not payload:
        raise CrmApiException("VALIDATION_ERROR", "Supply productScorecard or dealScorecard.")
    values = {}
    for key, value in payload.items():
        try:
            values[key] = scorecard_url(value)
        except ValueError as exc:
            raise CrmApiException("VALIDATION_ERROR", str(exc), field_errors={key: str(exc)}) from exc
    # Lock both Opportunity and Customer with current reads: a public Customer
    # may have become private since the initial permission check's RR snapshot.
    opportunity_status._lock_write_scope(opportunity_id)
    lock_document("CRM Opportunity", opportunity_id, expected_modified, "NOT_FOUND")
    doc = frappe.get_doc("CRM Opportunity", opportunity_id, for_update=True)
    changed = [(key, doc.get(LINKS[key]) or "", value) for key, value in values.items()
               if (doc.get(LINKS[key]) or "") != value]
    for key, _, value in changed:
        doc.set(LINKS[key], value)
    if changed:
        doc.save(ignore_permissions=True)
        for key, previous, value in changed:
            _append_history(doc.name, key, previous, value)
    return {"modified": to_iso_timestamp(doc.modified), "links": _links(doc)}
