"""Concrete Demo resources, half-open unavailability and source-scoped impact history."""
from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import frappe
from frappe.permissions import has_user_permission

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import as_payload, ensure_server_generated_id, normalize_expected_modified, required_text, to_iso_timestamp
from rayher_crm.services.demo_resource_rules import ACTIVE, resource_state
from rayher_crm.services.notifications import active_crm_users, notify_if_reachable

RESOURCE = "CRM Demo Resource"
UNAVAILABLE = "CRM Demo Unavailability"
IMPACT = "CRM Demo Resource Impact"
EVALUATION_FIELDS = "name title account demo_request evaluation_owner status demo_resource resource_start resource_end resource_revision modified test_round"


def lock_catalogue():
    frappe.db.sql("SELECT name FROM `tabDocType` WHERE name=%s FOR UPDATE", (RESOURCE,))


def locked(doctype, name, expected):
    if doctype not in (RESOURCE, UNAVAILABLE, "CRM Evaluation"):
        raise ValueError("Unsupported resource lock")
    rows = frappe.db.sql(f"SELECT name, modified FROM `tab{doctype}` WHERE name=%s FOR UPDATE", (name,), as_dict=True)
    if not rows:
        raise CrmApiException("NOT_FOUND", "Record was not found.")
    doc = frappe.get_doc(doctype, rows[0].name, for_update=True)
    if doctype == "CRM Evaluation" and not frappe.has_permission(doctype, "read", doc=doc):
        raise CrmApiException("SCOPE_DENIED", "Demo is outside your current scope.")
    if normalize_expected_modified(expected) != to_iso_timestamp(rows[0].modified):
        raise CrmApiException("VERSION_CONFLICT", "Record changed; reload before saving.")
    return doc


def text(payload, key, limit=140, required=True):
    value = required_text(payload, key) if required else str(payload.get(key) or "").strip()
    if len(value) > limit:
        raise CrmApiException("VALIDATION_ERROR", f"{key} must be at most {limit} characters.")
    return value


def window(payload):
    result = []
    for key in ("start", "end"):
        try:
            parsed = datetime.fromisoformat(str(payload.get(key) or "").replace("Z", "+00:00"))
            if not parsed.tzinfo:
                raise ValueError("Missing time zone")
            local = parsed.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
            if local.year < 1000:
                raise ValueError("Outside database datetime range")
            result.append(local)
        except (ValueError, OverflowError) as exc:
            raise CrmApiException("VALIDATION_ERROR", "Provide start and end with an explicit time zone.") from exc
    if result[0] >= result[1]:
        raise CrmApiException("VALIDATION_ERROR", "End must be later than start.")
    return result


def resource_dto(doc):
    return {"id": doc.name, "code": doc.resource_code, "title": doc.title, "platform": doc.platform,
            "maintainer": doc.maintainer, "enabled": bool(doc.enabled), "modified": to_iso_timestamp(doc.modified),
            "canMaintain": resolve_crm_role() == "Manager" or (resolve_crm_role() == "Engineer" and doc.maintainer == frappe.session.user)}


def unavailable_dto(doc):
    return {"id": doc.name, "resourceId": doc.resource, "start": to_iso_timestamp(doc.starts_at),
            "end": to_iso_timestamp(doc.ends_at), "reason": doc.reason, "status": doc.status,
            "modified": to_iso_timestamp(doc.modified)}


def get_catalogue():
    assert_capability("evaluation:view")
    resources = frappe.get_all(RESOURCE, fields=["name", "resource_code", "title", "platform", "maintainer", "enabled", "modified"], order_by="resource_code", limit_page_length=0)
    maintainers = []
    if resolve_crm_role() == "Manager":
        users = sorted({*active_crm_users("Manager"), *active_crm_users("Engineer")})
        maintainers = [{"id": name, "name": frappe.db.get_value("User", name, "full_name") or name} for name in users]
    return {"resources": [resource_dto(row) for row in resources], "maintainers": maintainers}


def get_unavailability(resource):
    assert_capability("evaluation:view")
    if not frappe.db.exists(RESOURCE, resource):
        raise CrmApiException("NOT_FOUND", "Resource was not found.")
    return [unavailable_dto(row) for row in frappe.get_all(UNAVAILABLE, filters={"resource": resource},
            fields=["name", "resource", "starts_at", "ends_at", "reason", "status", "modified"], order_by="starts_at desc, name", limit_page_length=0)]


def save_resource(payload, name=None, expected=None):
    if resolve_crm_role() != "Manager":
        raise CrmApiException("PERMISSION_DENIED", "Only Managers maintain the resource catalogue.")
    payload = as_payload(payload)
    if not name:
        ensure_server_generated_id(payload)
        if expected is not None:
            raise CrmApiException("VALIDATION_ERROR", "New equipment must not provide a previous version.")
    lock_catalogue()
    doc = locked(RESOURCE, name, expected) if name else frappe.get_doc({"doctype": RESOURCE})
    code, title, platform, maintainer = (text(payload, key) for key in ("code", "title", "platform", "maintainer"))
    if name and code != doc.resource_code:
        raise CrmApiException("VALIDATION_ERROR", "Equipment ID cannot be changed.")
    if not isinstance(payload.get("enabled"), bool):
        raise CrmApiException("VALIDATION_ERROR", "enabled must be true or false.")
    if not name or maintainer != doc.maintainer:
        if maintainer not in {*active_crm_users("Manager"), *active_crm_users("Engineer")}:
            raise CrmApiException("VALIDATION_ERROR", "Choose an active Manager or Engineer as maintainer.")
    if not name and frappe.db.get_value(RESOURCE, {"resource_code": code}, "name", for_update=True):
        raise CrmApiException("VALIDATION_ERROR", "Equipment ID already exists.")
    doc.update({"resource_code": code, "title": title, "platform": platform, "maintainer": maintainer, "enabled": int(payload["enabled"])})
    doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
    return resource_dto(doc)


def save_unavailability(resource, payload, name=None, expected=None):
    assert_capability("evaluation:write")
    payload = as_payload(payload)
    if not name:
        ensure_server_generated_id(payload)
        if expected is not None:
            raise CrmApiException("VALIDATION_ERROR", "New intervals must not provide a previous version.")
    start, end = window(payload)
    reason = text(payload, "reason", 1000)
    if payload.get("status") not in ("Active", "Resolved"):
        raise CrmApiException("VALIDATION_ERROR", "Status must be Active or Resolved.")
    lock_catalogue()
    if not frappe.db.exists(RESOURCE, resource):
        raise CrmApiException("NOT_FOUND", "Resource was not found.")
    machine = frappe.get_doc(RESOURCE, resource, for_update=True)
    if resolve_crm_role() != "Manager" and machine.maintainer != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the resource maintainer or a Manager can edit availability.")
    doc = locked(UNAVAILABLE, name, expected) if name else frappe.get_doc({"doctype": UNAVAILABLE, "resource": machine.name, "revision": 1})
    if doc.resource != machine.name:
        raise CrmApiException("SCOPE_DENIED", "Unavailability belongs to another resource.")
    before = (str(doc.starts_at or ""), str(doc.ends_at or ""), doc.status)
    after = (str(start), str(end), payload["status"])
    if name and before != after:
        doc.revision = int(doc.revision or 1) + 1
    doc.update({"starts_at": start, "ends_at": end, "reason": reason, "status": payload["status"]})
    savepoint = "demo_resource_" + frappe.generate_hash(length=8)
    frappe.db.savepoint(savepoint)
    try:
        doc.save(ignore_permissions=True) if name else doc.insert(ignore_permissions=True)
        capture_impacts()
        return unavailable_dto(doc)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def require_evaluation(name):
    from rayher_crm.services.evaluations import _require_evaluation
    assert_capability("evaluation:view")
    return _require_evaluation(name)


def _linked_rows(doctype, names, fields):
    """Batch only identities linked by the already selected source evaluations."""
    names = sorted({name for name in names if name})
    result = {}
    for offset in range(0, len(names), 500):
        rows = frappe.get_all(doctype, filters={"name": ["in", names[offset:offset + 500]]},
                              fields=["name", *fields], order_by="name", limit_page_length=0)
        result.update({row.name: row for row in rows})
    return result


def enriched(evaluations):
    rows = [dict(row) for row in evaluations]
    active = [row for row in rows if row.get("status") in ACTIVE]
    requests = _linked_rows("CRM Demo Request", (row.get("demo_request") for row in active),
                            ["status", "sales_owner", "opportunity"])
    relevant = [row for row in active if requests.get(row.get("demo_request"), {}).get("status") != "Cancelled"]
    customers = _linked_rows("Customer", (row.get("account") for row in relevant),
                             ["customer_name", "custom_crm_region", "custom_crm_segment"])
    opportunities = _linked_rows("CRM Opportunity", (requests.get(row.get("demo_request"), {}).get("opportunity") for row in relevant), ["tool_type"])
    for row in rows:
        request = requests.get(row.get("demo_request"), {})
        customer = customers.get(row.get("account"), {})
        row.update(request_status=request.get("status"), owner=request.get("sales_owner"),
                   customer=customer.get("customer_name") or "Self Test", region=customer.get("custom_crm_region") or "",
                   market=customer.get("custom_crm_segment") or "",
                   equipment=opportunities.get(request.get("opportunity"), {}).get("tool_type") or "")
    return rows


def current_states(rows, now, *, for_update=False):
    if for_update:
        blocked = frappe.db.sql("SELECT name, resource, starts_at, ends_at, status, reason, revision FROM `tabCRM Demo Unavailability` WHERE status='Active' FOR UPDATE", as_dict=True)
        resources = {row.name: row for row in frappe.db.sql("SELECT name, resource_code, title FROM `tabCRM Demo Resource` FOR UPDATE", as_dict=True)}
    else:
        blocked = frappe.get_all(UNAVAILABLE, filters={"status": "Active"}, fields=["name", "resource", "starts_at", "ends_at", "status", "reason", "revision"], limit_page_length=0)
        resources = {row.name: row for row in frappe.get_all(RESOURCE, fields=["name", "resource_code", "title"], limit_page_length=0)}
    result = []
    for row in enriched(rows):
        state = resource_state(row, blocked, now)
        resource = resources.get(row.get("demo_resource"))
        if not resource and state["state"] not in ("inactive", "elapsed"):
            state = {"state": "unknown", "impacts": []}
        result.append({**row, **state, "resourceName": f"{resource.resource_code} · {resource.title}" if resource else ""})
    return result


def get_schedule(name, *, for_update=False):
    doc = require_evaluation(name)
    current = current_states([doc.as_dict()], frappe.utils.now_datetime(), for_update=for_update)[0]
    active = {row["key"] for row in current["impacts"]}
    history_rows = (frappe.db.sql("SELECT name, detected_at, snapshot FROM `tabCRM Demo Resource Impact` WHERE evaluation=%s ORDER BY detected_at DESC, name FOR UPDATE", (name,), as_dict=True)
                    if for_update else frappe.get_all(IMPACT, filters={"evaluation": name}, fields=["name", "detected_at", "snapshot"], order_by="detected_at desc, name", limit_page_length=0))
    history = [{"id": row.name, "detectedAt": to_iso_timestamp(row.detected_at), "current": row.name in active,
                "snapshot": frappe.parse_json(row.snapshot)} for row in history_rows]
    return {"evaluationId": name, "resourceId": doc.demo_resource or "", "start": to_iso_timestamp(doc.resource_start) if doc.resource_start else None,
            "end": to_iso_timestamp(doc.resource_end) if doc.resource_end else None, "modified": to_iso_timestamp(doc.modified),
            "state": current["state"], "impacts": current["impacts"], "history": history,
            "canWrite": doc.status in ACTIVE and current.get("request_status") != "Cancelled" and (resolve_crm_role() == "Manager" or (resolve_crm_role() == "Engineer" and doc.evaluation_owner == frappe.session.user))}


def save_schedule(name, payload, expected):
    from rayher_crm.services.evaluations import append_evaluation_history
    assert_capability("evaluation:write")
    require_evaluation(name)
    payload = as_payload(payload)
    resource = text(payload, "resourceId", required=False)
    start, end = window(payload) if resource else (None, None)
    if not resource and (payload.get("start") or payload.get("end")):
        raise CrmApiException("VALIDATION_ERROR", "Clear dates together with the resource.")
    lock_catalogue()
    doc = locked("CRM Evaluation", name, expected)
    if resolve_crm_role() != "Manager" and doc.evaluation_owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the current Demo Engineer or a Manager may arrange resources.")
    if doc.status not in ACTIVE or frappe.db.get_value("CRM Demo Request", doc.demo_request, "status") == "Cancelled":
        raise CrmApiException("INVALID_TRANSITION", "This Demo is no longer awaiting testing.")
    before = (doc.demo_resource or "", str(doc.resource_start or ""), str(doc.resource_end or ""))
    after = (resource, str(start or ""), str(end or ""))
    if before == after:
        return get_schedule(name, for_update=True)
    if resource:
        machine = frappe.db.get_value(RESOURCE, resource, ["name", "enabled"], as_dict=True, for_update=True)
        if not machine or (not machine.enabled and machine.name != (doc.demo_resource or "")):
            raise CrmApiException("VALIDATION_ERROR", "Choose a resource accepting new assignments.")
        resource = machine.name
    savepoint = "demo_schedule_" + frappe.generate_hash(length=8)
    frappe.db.savepoint(savepoint)
    try:
        doc.update({"demo_resource": resource or None, "resource_start": start, "resource_end": end,
                    "resource_revision": int(doc.resource_revision or 0) + 1})
        if not has_user_permission(doc, frappe.session.user):
            raise CrmApiException("SCOPE_DENIED", "Resource is outside your permitted Demo scope.")
        doc.save(ignore_permissions=True)
        append_evaluation_history(doc, "Resource Schedule", "Changed the concrete resource schedule", frappe.as_json(before), frappe.as_json(after))
        capture_impacts()
        return get_schedule(name, for_update=True)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def capture_impacts():
    """Lock active source rows before creating notices; retain terminal history untouched."""
    lock_catalogue()
    # The status-leading index avoids locking archived schedules while scanning
    # the resource range, even under MariaDB's repeatable-read isolation.
    rows = frappe.db.sql(f"SELECT {', '.join(EVALUATION_FIELDS.split())} FROM `tabCRM Evaluation` FORCE INDEX (crm_active_demo_resource_schedule) WHERE status IN %(statuses)s AND demo_resource > '' ORDER BY name FOR UPDATE",
                         {"statuses": tuple(sorted(ACTIVE))}, as_dict=True)
    now = frappe.utils.now_datetime()
    managers = active_crm_users("Manager")
    created = 0
    for row in current_states(rows, now, for_update=True):
        for impact in row["impacts"]:
            # The caller can have established an RR snapshot before waiting for
            # the catalogue lock. Both dedupe reads must see earlier commits.
            if not frappe.db.get_value(IMPACT, impact["key"], "name", for_update=True):
                frappe.get_doc({"doctype": IMPACT, "impact_key": impact["key"], "evaluation": row["name"], "resource": impact["resourceId"],
                                "unavailability": impact["unavailabilityId"], "detected_at": now, "snapshot": frappe.as_json(impact)}).insert(ignore_permissions=True)
            for user in sorted({*managers, row.get("owner"), row.get("evaluation_owner")} - {None, ""}):
                key = sha256(f"demo-resource:{impact['key']}:{user}".encode()).hexdigest()
                if frappe.db.get_value("CRM Notification Event", {"dedupe_key": key}, "name", for_update=True):
                    continue
                notice = notify_if_reachable(recipient=user, category="Evaluation", title="Demo 设备不可用",
                    message=f"{row['title']} 的安排与 {row['resourceName']} 不可用时段相交，请调整设备或时间。"[:1000],
                    route=f"/demo-workflow/{row['demo_request']}", source_doctype="CRM Evaluation", source_name=row["name"], dedupe_key=key)
                created += int(notice is not None)
    return created


def warning_summary(query):
    """Current future resource risks, filtered like the cockpit; never historical reconstruction."""
    from rayher_crm.services.equipment import equipment_key
    assert_capability("evaluation:view")
    rows = frappe.get_list("CRM Evaluation", filters={"status": ["in", sorted(ACTIVE)]}, fields=EVALUATION_FIELDS.split(), limit_page_length=0)
    selected = []
    for row in current_states(rows, frappe.utils.now_datetime()):
        if query.get("sales") and row.get("owner") != query["sales"]:
            continue
        if query.get("region") and row.get("region") not in query.get("regions", {query["region"]}):
            continue
        if query.get("market") and row.get("market") != query["market"]:
            continue
        if query.get("equipment") and equipment_key(row.get("equipment")) != equipment_key(query["equipment"]):
            continue
        if row["state"] in ("blocked", "unknown"):
            selected.append({"id": row["name"], "demoRequestId": row["demo_request"], "title": row["title"], "customer": row["customer"],
                             "owner": row.get("owner"), "engineer": row["evaluation_owner"], "resourceName": row["resourceName"],
                             "state": row["state"], "impacts": row["impacts"]})
    return {"count": sum(row["state"] == "blocked" for row in selected), "unknown": sum(row["state"] == "unknown" for row in selected), "items": selected}
