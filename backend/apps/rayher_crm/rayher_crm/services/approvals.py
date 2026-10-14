"""Current business approval steps; notification history never determines pending state.

This service projects existing workflows and records only who viewed a particular
submission. Decisions still go through the original business commands.
"""

from __future__ import annotations

import hashlib
from urllib.parse import quote

import frappe
from frappe.utils import now_datetime

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.notification_scope import source_condition
from rayher_crm.permissions.roles import capabilities_for_role, resolve_crm_role
from rayher_crm.services.common import to_iso_timestamp

VIEW_DOCTYPE = "CRM Approval View"


def _viewer():
    user = frappe.session.user
    role = resolve_crm_role(user)
    if not frappe.db.get_value("User", user, "enabled"):
        raise frappe.PermissionError("An active CRM user is required.")
    return user, role, set(capabilities_for_role(role))


def _task_id(kind, record, cycle):
    digest = hashlib.sha256(f"{record}\0{cycle}".encode()).hexdigest()
    return f"{kind}:{digest}"


def _view_id(user, task):
    return hashlib.sha256(f"{user}\0{task}".encode()).hexdigest()


def _pending_docs(doctype, condition, values, user, selected=None):
    if selected and selected[0] != doctype:
        return []
    scope = source_condition(doctype, user, for_bound_query=True)
    if scope == "1=0":
        return []
    selection = " AND `name` = %s" if selected else ""
    locking = " FOR UPDATE" if selected else ""
    rows = frappe.db.sql(
        f"SELECT * FROM `tab{doctype}` WHERE ({condition}) AND ({scope}){selection} "
        f"ORDER BY `creation` DESC, `name` DESC{locking}",
        (*values, selected[1]) if selected else tuple(values), as_dict=True,
    )
    # In POST these are current locking reads, not an earlier repeatable-read snapshot.
    return [frappe.get_doc({"doctype": doctype, **row}) for row in rows]


def _related_doc(doctype, name, locking=False):
    if not locking:
        return frappe.get_doc(doctype, name)
    rows = frappe.db.sql(f"SELECT * FROM `tab{doctype}` WHERE `name` = %s FOR UPDATE", (name,), as_dict=True)
    if not rows:
        raise CrmApiException("NOT_FOUND", "The approval source was not found.")
    return frappe.get_doc({"doctype": doctype, **rows[0]})


def _latest_history(doctype, parent_field, parent, filters, locking=False):
    if locking:
        where = " AND ".join(f"`{field}` = %s" for field in (parent_field, *filters))
        rows = frappe.db.sql(
            f"SELECT `name`, `actor`, `at` FROM `tab{doctype}` WHERE {where} "
            "ORDER BY `at` DESC, `creation` DESC, `name` DESC LIMIT 1 FOR UPDATE",
            (parent, *filters.values()), as_dict=True,
        )
    else:
        rows = frappe.get_all(
            doctype, filters={parent_field: parent, **filters}, fields=["name", "actor", "at"],
            order_by="at desc, creation desc, name desc", limit_page_length=1, ignore_permissions=True,
        )
    return rows[0] if rows else None


def _name(user, cache):
    if not user:
        return ""
    if user not in cache:
        cache[user] = frappe.db.get_value("User", user, "full_name") or user
    return cache[user]


def _item(kind, doc, cycle, stage, user, role, *, source=None, account="", title="",
          requester="", submitted=None, sales="", equipment="", description="", target=None):
    source = source or doc.name
    return {
        "id": _task_id(kind, doc.name, cycle), "kind": kind,
        "title": title or doc.get("title") or doc.name,
        "customer": "", "sourceId": source, "sourceRecordId": source,
        "stage": stage, "requester": "", "requesterId": requester or "",
        "sales": "", "region": "", "market": "", "equipment": equipment or "",
        "submittedAt": to_iso_timestamp(submitted or doc.creation), "unread": True,
        "recipientId": user, "recipientRole": role, "state": "pending",
        "canReadSource": True, "canHandle": True, "description": description or "",
        "sourceLabel": stage, "target": target,
        "_doctype": doc.doctype, "_record": doc.name, "_account": account,
        "_sales": sales,
    }


def _collect(user, role, capabilities, selected=None):
    items = []
    if "demo_request:engineering_review" in capabilities or "demo_request:manager_approve" in capabilities:
        for doc in _pending_docs("CRM Demo Request", "`status` IN (%s, %s)", ("Engineer Review", "Manager Approval"), user, selected):
            if doc.status == "Engineer Review":
                if "demo_request:engineering_review" not in capabilities or (role != "Manager" and doc.engineer_owner != user):
                    continue
                kind, mode, stage = "demo-engineering", "engineer", "工程评估"
            elif doc.status == "Manager Approval" and role == "Manager" and "demo_request:manager_approve" in capabilities and not doc.evaluation:
                kind, mode, stage = "demo", "manager", "Demo 申请审批"
            else:
                continue
            history = _latest_history("CRM Demo Request History", "demo_request", doc.name, {"to_status": doc.status}, bool(selected))
            items.append(_item(kind, doc, history.name if history else doc.creation, stage, user, role,
                account=doc.account, requester=history.actor if history else doc.sales_owner,
                submitted=history.at if history else doc.creation, sales=doc.sales_owner,
                equipment=doc.requested_equipment,
                target={"path": "/demo-requests", "query": {"focus": doc.name, "mode": mode}}))

    if "quotation:approve" in capabilities:
        for doc in _pending_docs("CRM Quotation", "`status` = %s", ("Draft",), user, selected):
            version = _related_doc("CRM Quotation Version", doc.current_version, bool(selected)) if doc.current_version else None
            if not version or version.status != "Draft" or version.approval_status != "Pending" or not version.current_approval:
                continue
            approval = _related_doc("CRM Quotation Approval", version.current_approval, bool(selected))
            if approval.status != "Pending" or approval.quotation != doc.name or approval.quotation_version != version.name:
                continue
            opportunity = frappe.db.get_value("CRM Opportunity", doc.opportunity, ["account", "archived", "tool_type"], as_dict=True) if doc.opportunity else None
            account_id = doc.account
            if doc.opportunity:
                account_id = opportunity.account if opportunity else None
            account = frappe.db.get_value("Customer", account_id, "custom_crm_archived") if account_id else False
            if account or (opportunity and opportunity.archived):
                continue
            items.append(_item("quotation", doc, approval.name, "报价审批", user, role,
                account=doc.account, title=doc.ref_no, requester=approval.submitted_by,
                submitted=approval.submitted_at, sales=doc.quotation_owner,
                equipment=opportunity.tool_type if opportunity else "",
                target={"path": "/quotations/" + quote(doc.name, safe=""), "query": {"version": version.name, "approval": "1"}}))
            items[-1]["sourceId"] = doc.ref_no

    if "deal:internal_validation_approve" in capabilities:
        for doc in _pending_docs("CRM Opportunity Internal Validation", "`status` = %s AND `requested_by` != %s", ("pending", user), user, selected):
            opportunity = _related_doc("CRM Opportunity", doc.opportunity, bool(selected))
            if doc.status != "pending" or doc.requested_by == user or opportunity.stage != "quotation_sent" or opportunity.archived:
                continue
            if opportunity.account and frappe.db.get_value("Customer", opportunity.account, "custom_crm_archived"):
                continue
            items.append(_item("production", doc, doc.name, "内部验证审批", user, role,
                source=opportunity.name, account=opportunity.account, title=opportunity.title,
                requester=doc.requested_by, submitted=doc.requested_at, sales=opportunity.opportunity_owner,
                equipment=opportunity.tool_type, description=doc.reason,
                target={"path": "/opportunities/" + quote(opportunity.name, safe=""), "query": {"approval": "1"}}))
            items[-1]["forbidSelfApproval"] = True

    if role in {"Engineer", "Manager"}:
        for doc in _pending_docs("CRM RFQ", "`status` IN (%s, %s)", ("Engineer Review", "Manager Approval"), user, selected):
            # RFQ's command explicitly excludes Managers from the engineering step,
            # even though the Manager capability set contains rfq:engineer_comment.
            if doc.status == "Engineer Review" and role == "Engineer" and doc.engineer_owner == user and "rfq:engineer_comment" in capabilities:
                kind, stage = "rfq-engineering", "RFQ 技术评审"
            elif doc.status == "Manager Approval" and role == "Manager" and "rfq:manager_approve" in capabilities:
                kind, stage = "rfq", "RFQ 审批"
            else:
                continue
            version = _related_doc("CRM RFQ Version", doc.current_version, bool(selected))
            requester = version.uploaded_by if kind == "rfq-engineering" else version.engineer_commented_by
            submitted = version.uploaded_at if kind == "rfq-engineering" else version.engineer_commented_at
            opportunity = frappe.get_doc("CRM Opportunity", doc.opportunity)
            items.append(_item(kind, doc, version.name, stage, user, role,
                account=doc.account, title=opportunity.title, requester=requester,
                submitted=submitted, sales=doc.sales_owner, equipment=opportunity.tool_type,
                target={"path": "/rfqs/" + quote(doc.name, safe="")}))

    if "visit:review" in capabilities:
        for doc in _pending_docs("CRM Visit", "`status` = %s", ("Minutes Submitted",), user, selected):
            if doc.status != "Minutes Submitted":
                continue
            records = frappe.get_all("CRM Visit Meeting Record", filters={"visit": doc.name},
                fields=["name", "creation", "modified", "purpose", "attendees", "agenda", "summary", "conclusion", "followup"],
                limit_page_length=1, ignore_permissions=True)
            if selected and records:
                records = [_related_doc("CRM Visit Meeting Record", records[0].name, True)]
            if not records or not all(str(records[0].get(field) or "").strip() for field in ("purpose", "attendees", "agenda", "summary", "conclusion", "followup")):
                continue
            items.append(_item("visit", doc, records[0].name, "拜访纪要审核", user, role,
                account=doc.account, title=doc.subject, requester=doc.visit_owner,
                submitted=records[0].modified, sales=doc.visit_owner,
                target={"path": "/visits", "query": {"focus": doc.name, "review": "1"}}))
            items[-1]["submittedAtLabel"] = "资料完成时间"

    if role == "Manager":
        for doctype, kind, stage, field in (
            ("CRM Document Access Request", "document", "文档访问审批", "requester"),
            ("CRM Document Upload Request", "document-upload", "文档发布审批", "submitted_by"),
        ):
            for doc in _pending_docs(doctype, "`status` = %s", ("Pending",), user, selected):
                if doc.status != "Pending":
                    continue
                title = doc.get("title")
                if kind == "document":
                    title = frappe.db.get_value("CRM Controlled Document", doc.controlled_document, "title")
                items.append(_item(kind, doc, doc.name, stage, user, role,
                    title=title, requester=doc.get(field), description=doc.get("reason") or "",
                    target={"path": "/document-center", "query": {"workspace": "approvals", "request": doc.name}}))

    if "evaluation:write" in capabilities or "evaluation:customer_review" in capabilities:
        for doc in _pending_docs("CRM Evaluation", "`status` IN (%s, %s, %s)", ("Internal Review", "Analysis", "Customer Review"), user, selected):
            if doc.status in {"Internal Review", "Analysis"} and "evaluation:write" in capabilities:
                # This is the same report gate as update_evaluation_status.
                if doc.report_status != "Ready":
                    continue
                kind, stage = "test-review", "测试内部评审"
            elif doc.status == "Customer Review" and "evaluation:customer_review" in capabilities:
                kind, stage = "customer-review", "客户评审"
            else:
                continue
            request = frappe.get_doc("CRM Demo Request", doc.demo_request)
            history = _latest_history("CRM Evaluation History", "evaluation", doc.name, {"event_type": "Status", "to_value": doc.status}, bool(selected))
            cycle = f"{int(doc.test_round or 1)}:{history.name if history else doc.status}"
            items.append(_item(kind, doc, cycle, stage, user, role,
                account=doc.account, requester=history.actor if history else doc.evaluation_owner,
                submitted=history.at if history else doc.creation, sales=request.sales_owner,
                equipment=request.requested_equipment,
                target={"path": "/evaluations", "query": {"focus": doc.name}}))

    # Names and customer metadata are resolved only for records already authorized above.
    people, accounts = {}, {}
    for item in items:
        item["requester"] = _name(item["requesterId"], people)
        item["sales"] = _name(item.pop("_sales"), people)
        account_id = item.pop("_account")
        if account_id:
            if account_id not in accounts:
                accounts[account_id] = frappe.db.get_value("Customer", account_id,
                    ["customer_name", "custom_crm_region", "custom_crm_segment"], as_dict=True) or {}
            account = accounts[account_id]
            item["customer"] = account.get("customer_name") or ""
            item["region"] = account.get("custom_crm_region") or ""
            item["market"] = account.get("custom_crm_segment") or ""
    return sorted(items, key=lambda item: (item["submittedAt"], item["id"]), reverse=True)


def list_pending_approvals():
    user, role, capabilities = _viewer()
    items = _collect(user, role, capabilities)
    if items:
        viewed = set(frappe.get_all(VIEW_DOCTYPE,
            filters={"viewer": user, "task_key": ["in", [item["id"] for item in items]]},
            pluck="task_key", ignore_permissions=True))
        for item in items:
            item["unread"] = item["id"] not in viewed
    return [{key: value for key, value in item.items() if not key.startswith("_")} for item in items]


def mark_approval_viewed(task_id):
    if not isinstance(task_id, str) or not task_id or len(task_id) > 140:
        raise CrmApiException("VALIDATION_ERROR", "A valid approval id is required.")
    user, role, capabilities = _viewer()
    item = next((item for item in _collect(user, role, capabilities) if item["id"] == task_id), None)
    if not item:
        raise CrmApiException("NOT_FOUND", "This approval is no longer pending for the current user.")
    # Match the business lock order: an internal validation holds its Opportunity first.
    lock_type, lock_name = item["_doctype"], item["_record"]
    if lock_type == "CRM Opportunity Internal Validation":
        lock_type, lock_name = "CRM Opportunity", item["sourceRecordId"]
    frappe.db.sql(f"SELECT `name` FROM `tab{lock_type}` WHERE `name` = %s FOR UPDATE", (lock_name,))
    user, role, capabilities = _viewer()
    selected = (item["_doctype"], item["_record"])
    if not any(current["id"] == task_id for current in _collect(user, role, capabilities, selected)):
        raise CrmApiException("NOT_FOUND", "This approval is no longer pending for the current user.")
    name = _view_id(user, task_id)
    viewed_at = frappe.db.get_value(VIEW_DOCTYPE, name, "viewed_at", for_update=True)
    if not viewed_at:
        savepoint = "crm_approval_view"
        frappe.db.savepoint(savepoint)
        try:
            receipt = frappe.get_doc({"doctype": VIEW_DOCTYPE, "name": name,
                "viewer": user, "task_key": task_id, "viewed_at": now_datetime()})
            receipt.insert(ignore_permissions=True)
            viewed_at = receipt.viewed_at
        except frappe.DuplicateEntryError:
            frappe.db.rollback(save_point=savepoint)
            viewed_at = frappe.db.get_value(VIEW_DOCTYPE, name, "viewed_at", for_update=True)
            if not viewed_at:
                raise
    return {"id": task_id, "viewedAt": to_iso_timestamp(viewed_at)}
