"""Frappe-backed CRM quotation lifecycle and PDF services."""

from __future__ import annotations

import base64
import io
import hashlib
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import frappe
from frappe.utils import add_months, getdate, now_datetime, today

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.notification_scope import can_read_source
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype, has_crm_permission
from rayher_crm.services.common import normalize_pagination, required_text, to_iso_timestamp
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.contacts import _contact_account
from rayher_crm.services.money import decimal_string
from rayher_crm.services.notifications import create_notification, notify_if_reachable
from rayher_crm.services.quotation_rules import QuotationRuleError, calculate_totals, validate_payment_terms
from rayher_crm.services.opportunity_stages import PUBLISHABLE_QUOTATION_STAGES
from rayher_crm.services.sites import can_read_site_data

PUBLISHABLE_OPPORTUNITY_STAGES = set(PUBLISHABLE_QUOTATION_STAGES)
DECISION_STATUSES = {"Accepted", "Rejected"}
APPROVAL_DECISIONS = {"Approved", "Rejected"}
FIXED_INCOTERM = "FOB上海  FOB Shanghai"
FIXED_PAYMENT_TERMS = (
    {"percentage": "30", "triggerCondition": "30% PO总价", "description": "收到订单1周内，买方电汇方式支付订单总价30%作为预付款。"},
    {"percentage": "30", "triggerCondition": "30% PO总价", "description": "发货前两周内，买方电汇方式支付订单总价30%作为发货款。"},
    {"percentage": "30", "triggerCondition": "30% PO总价", "description": "设备验收完成后两周内，支付订单总价30%，发货之后两个月之内组织验收。"},
    {"percentage": "10", "triggerCondition": "10% PO总价", "description": "设备发货之后一年，买方付10% PO的尾款。"},
)
FIXED_INSTALLATION = "Installation, 5 days"
FIXED_TRAINING = "Maintenance training, 5 days /4 EE\nApplication training: 5 days /4 PE\nOperator training: 2 days/ 3 operators"
FIXED_DOCUMENTATION = "Documentation(manual printout on cleanroom paper)"
FIXED_PACKING = "Packing in stretched foil, alupack film and wooden crates"
MAX_QUOTATION_LINES = 200
MAX_DATA_LENGTH = 140
MAX_DESCRIPTION_LENGTH = 5000
MAX_TERM_MONTHS = 120
QUOTATION_TYPES = {"Device", "Service"}
PAYMENT_TERM_DESCRIPTIONS = (
    "收到订单1周内，买方电汇方式支付订单总价{percentage}%作为预付款。",
    "发货前两周内，买方电汇方式支付订单总价{percentage}%作为发货款。",
    "设备验收完成后两周内，支付订单总价{percentage}%，发货之后两个月之内组织验收。",
    "设备发货之后一年，买方付{percentage}% PO的尾款。",
)


CATALOG_LEVELS = {"Device", "System", "Accessory"}
CATALOG_PARENT_LEVEL = {"Device": None, "System": "Device", "Accessory": "System"}
INITIAL_QUOTATION_CATALOG = (
    ("Device", "Drakens 4482 宏观缺陷自动检测设备(6”/8”/12”)", None),
    ("System", "检测腔体 Process module", "Drakens 4482 宏观缺陷自动检测设备(6”/8”/12”)"),
    ("System", "晶圆传输系统 EFEM", "Drakens 4482 宏观缺陷自动检测设备(6”/8”/12”)"),
)
INITIAL_QUOTATION_ACCESSORIES = {
    "检测腔体 Process module": (
        "四通道时域照明系统", "高分辨四通道采集系统", "自动缺陷检测系统及ADC分类系统",
        "高精度运动平台(含6”/8” adaptor)", "结果查看器 Results viewer license", "FFU 洁净单元",
        "inside lighting(Yellow)", "Vac System", "Safety System", "Power Supply", "离子棒",
        "SECS GEM标准通讯协议", "符合SEMI2、8标准", "class 10 洁净微环境",
    ),
    "晶圆传输系统 EFEM": (
        "RFID reader", "Barcode reader", "Wafer ID reader", "机械手+两套手臂", "背面非接触式手指(8寸)",
        "背面非接触式手指(6寸)", "Load port（12寸/8寸/6寸兼容）", "边缘夹持晶圆对位系统(8寸)",
        "边缘夹持晶圆对位系统(6寸)", "PC, Frame and Cover", "Light tower(RGBY)",
        "inside lighting(Yellow)", "Vac System", "Safety System", "Power Supply", "离子棒", "EFEM兼容多个检测模块升级",
    ),
}


def _normalize_catalog_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _catalog_key(level: str, parent_id: str | None, name: str) -> str:
    normalized = _normalize_catalog_name(name)
    if not normalized:
        raise CrmApiException("VALIDATION_ERROR", "Catalog name is required.")
    if len(normalized) > MAX_DATA_LENGTH:
        raise CrmApiException("VALIDATION_ERROR", f"Catalog name cannot exceed {MAX_DATA_LENGTH:,} characters.")
    value = f"{level}|{parent_id or ''}|{normalized.casefold()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _upsert_catalog_item(level: str, name: str, parent_id: str | None = None) -> str:
    if level not in CATALOG_LEVELS:
        raise CrmApiException("VALIDATION_ERROR", "Catalog level must be Device, System or Accessory.")
    normalized = _normalize_catalog_name(name)
    expected_parent_level = CATALOG_PARENT_LEVEL[level]
    if expected_parent_level is None:
        if parent_id:
            raise CrmApiException("VALIDATION_ERROR", "Device catalog items cannot have a parent.")
    else:
        parent = frappe.db.get_value(
            "CRM Quotation Catalog Item", parent_id, ["name", "item_level"], as_dict=True,
        ) if parent_id else None
        if not parent or parent.item_level != expected_parent_level:
            raise CrmApiException("VALIDATION_ERROR", f"{level} catalog parent must be {expected_parent_level}.")
    key = _catalog_key(level, parent_id, normalized)
    existing = frappe.db.get_value("CRM Quotation Catalog Item", {"catalog_key": key}, "name")
    if existing:
        return existing
    try:
        return frappe.get_doc({
            "doctype": "CRM Quotation Catalog Item", "item_level": level,
            "item_name": normalized, "parent_item": parent_id, "catalog_key": key,
        }).insert(ignore_permissions=True).name
    except Exception:
        existing = frappe.db.get_value("CRM Quotation Catalog Item", {"catalog_key": key}, "name")
        if existing:
            return existing
        raise


def seed_quotation_catalog() -> None:
    ids: dict[str, str] = {}
    for level, name, parent_name in INITIAL_QUOTATION_CATALOG:
        ids[name] = _upsert_catalog_item(level, name, ids.get(parent_name or ""))
    for system_name, accessories in INITIAL_QUOTATION_ACCESSORIES.items():
        for name in accessories:
            _upsert_catalog_item("Accessory", name, ids[system_name])


def list_catalog() -> list[dict[str, str]]:
    assert_capability("quotation:view")
    rows = frappe.get_all(
        "CRM Quotation Catalog Item",
        fields=["name", "item_level", "item_name", "parent_item"],
        order_by="creation asc, name asc",
        limit_page_length=1000,
    )
    return [{"id": row.name, "level": row.item_level, "name": row.item_name, "parentId": row.parent_item or ""} for row in rows]
def _text(payload: dict[str, Any], key: str, default: str = "") -> str:
    return str(payload.get(key) if payload.get(key) is not None else default).strip()


def _bounded_text(value: str, field: str, limit: int) -> str:
    if len(value) > limit:
        raise CrmApiException("VALIDATION_ERROR", f"{field} cannot exceed {limit:,} characters.")
    return value


def _db_decimal(value: Any) -> str:
    return decimal_string(str(value or 0))


def _next_ref_no(quote_date: str) -> str:
    date_key = getdate(quote_date).strftime("%Y%m%d")
    prefix = f"PK{date_key}-A"
    rows = frappe.db.sql(
        "SELECT ref_no FROM `tabCRM Quotation` WHERE ref_no LIKE %s FOR UPDATE",
        (f"{prefix}%",),
        as_dict=True,
    )
    sequences = [
        int(row.ref_no[len(prefix):])
        for row in rows
        if row.ref_no.startswith(prefix) and row.ref_no[len(prefix):].isdigit()
    ]
    return f"{prefix}{max(sequences, default=0) + 1}"

def _require_quotation(name: str):
    if not frappe.db.exists("CRM Quotation", name):
        raise CrmApiException("QUOTATION_NOT_FOUND", "Quotation was not found.")
    doc = frappe.get_doc("CRM Quotation", name)
    if not frappe.has_permission("CRM Quotation", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The Quotation is outside the current user scope.")
    return doc


def _assert_quotation_address_scope(account_id: str, message: str) -> None:
    if not can_read_site_data(account_id):
        raise CrmApiException("SCOPE_DENIED", message)


def _lock_quotation(name: str):
    rows = frappe.db.sql(
        "SELECT `name` FROM `tabCRM Quotation` WHERE `name` = %s FOR UPDATE",
        (name,),
    )
    if not rows:
        raise CrmApiException("QUOTATION_NOT_FOUND", "Quotation was not found.")
    doc = _require_quotation(name)
    _assert_quotation_address_scope(
        doc.account,
        "Only the Account owner or a Manager may modify quotations containing Site/Address data.",
    )
    return doc


def _require_version(master, version_id: str | None, *, fallback: str | None = None):
    selected_id = version_id or fallback
    if not selected_id or not frappe.db.exists("CRM Quotation Version", selected_id):
        raise CrmApiException("NOT_FOUND", "Quotation version was not found.")
    version = frappe.get_doc("CRM Quotation Version", selected_id)
    if version.quotation != master.name:
        raise CrmApiException("NOT_FOUND", "Quotation version was not found.")
    return version

def _require_opportunity(name: str):
    if not frappe.db.exists("CRM Opportunity", name):
        raise CrmApiException("OPPORTUNITY_NOT_FOUND", "Opportunity was not found.")
    doc = frappe.get_doc("CRM Opportunity", name)
    if not has_crm_permission(doc, user=frappe.session.user, permission_type="read"):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")
    return doc


def _validate_contact(contact_id: str, account: str) -> None:
    if not contact_id or not frappe.db.exists("Contact", contact_id):
        raise CrmApiException("CONTACT_NOT_FOUND", "ATTN contact was not found.")
    if _contact_account(contact_id) != account:
        raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "ATTN must belong to the quotation customer.")
    if frappe.db.get_value("Contact", contact_id, "custom_crm_status") != "Active":
        raise CrmApiException("CONTACT_INACTIVE", "ATTN must be an active contact.")


def _validate_address(address_id: str, account: str) -> None:
    _assert_quotation_address_scope(
        account,
        "Only the Account owner or a Manager may use quotation addresses.",
    )
    if not address_id or not frappe.db.exists("Address", address_id):
        raise CrmApiException("ADDRESS_NOT_FOUND", "Quotation address was not found.")
    if not frappe.db.exists("Dynamic Link", {"parent": address_id, "parenttype": "Address", "link_doctype": "Customer", "link_name": account}):
        raise CrmApiException("ADDRESS_ACCOUNT_MISMATCH", "Address must belong to the quotation customer.")


def _snapshot(account: str, contact_id: str = "", address_id: str = "") -> dict[str, str]:
    customer_name = frappe.db.get_value("Customer", account, "customer_name") or account
    contact = frappe.db.get_value("Contact", contact_id, ["first_name", "last_name", "designation", "phone", "mobile_no"], as_dict=True) if contact_id else None
    address = frappe.db.get_value("Address", address_id, ["address_line1", "address_line2", "city", "state", "pincode", "country"], as_dict=True) if address_id else None
    contact_name = " ".join(part for part in ((contact.first_name if contact else ""), (contact.last_name if contact else "")) if part).strip()
    address_text = ", ".join(str(value).strip() for value in (
        address.address_line1 if address else "", address.address_line2 if address else "", address.city if address else "",
        address.state if address else "", address.pincode if address else "", address.country if address else "",
    ) if value and str(value).strip())
    return {
        "customer_name_snapshot": customer_name, "attention_name_snapshot": contact_name or contact_id,
        "attention_title_snapshot": (contact.designation if contact else "") or "",
        "attention_phone_snapshot": ((contact.phone or contact.mobile_no) if contact else "") or "",
        "address_snapshot": address_text,
    }


def _item_rows(payload_items: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(payload_items, list) or not payload_items:
        raise CrmApiException("VALIDATION_ERROR", "At least one device is required.")
    if len(payload_items) > MAX_QUOTATION_LINES:
        raise CrmApiException("VALIDATION_ERROR", f"Quotation cannot exceed {MAX_QUOTATION_LINES} lines.")
    normalized, rule_items, seen = [], [], set()
    for index, item in enumerate(payload_items, start=1):
        line_key = _bounded_text(_text(item, "lineKey"), "lineKey", MAX_DATA_LENGTH)
        line_type = _text(item, "lineType")
        if not line_key or line_key in seen:
            raise CrmApiException("VALIDATION_ERROR", "Each quotation line needs a unique lineKey.")
        seen.add(line_key)
        parent_key = _bounded_text(_text(item, "parentDeviceKey"), "parentDeviceKey", MAX_DATA_LENGTH)
        parent_system_key = _bounded_text(_text(item, "parentSystemKey"), "parentSystemKey", MAX_DATA_LENGTH)
        catalog_item = _bounded_text(_text(item, "catalogItemId"), "catalogItemId", MAX_DATA_LENGTH)
        item_name = _bounded_text(required_text(item, "name"), "name", MAX_DATA_LENGTH)
        model = _bounded_text(_text(item, "model"), "model", MAX_DATA_LENGTH)
        description = _bounded_text(_text(item, "description"), "description", MAX_DESCRIPTION_LENGTH)
        pricing_mode = "Charged" if line_type == "Device" else "Included" if line_type == "System" else _text(item, "pricingMode", "Included")
        quantity = 1 if line_type == "System" else item.get("quantity")
        unit_price = "0" if line_type == "System" else item.get("unitPrice")
        rule = {
            "lineKey": line_key, "lineType": line_type, "parentDeviceKey": parent_key,
            "parentSystemKey": parent_system_key, "pricingMode": pricing_mode,
            "quantity": quantity, "unitPrice": unit_price,
        }
        rule_items.append(rule)
        normalized.append({
            "line_key": line_key, "line_type": line_type, "parent_device_key": parent_key,
            "parent_system_key": parent_system_key, "catalog_item": catalog_item or None,
            "item_name": item_name, "model": model, "description": description,
            "pricing_mode": pricing_mode, "quantity": quantity, "unit_price": unit_price, "idx": index,
        })
    return normalized, rule_items
def _payment_rows(payload_terms: Any, publishing: bool) -> list[dict[str, Any]]:
    terms = list(payload_terms if isinstance(payload_terms, (list, tuple)) else FIXED_PAYMENT_TERMS)
    if len(terms) != len(PAYMENT_TERM_DESCRIPTIONS):
        raise CrmApiException("VALIDATION_ERROR", "Exactly four payment percentages are required.")
    try:
        validate_payment_terms(terms, publishing=publishing)
    except QuotationRuleError as exc:
        raise CrmApiException("VALIDATION_ERROR", str(exc)) from exc
    rows = []
    for index, (term, description) in enumerate(zip(terms, PAYMENT_TERM_DESCRIPTIONS), start=1):
        percentage = Decimal(str(term.get("percentage") if term.get("percentage") is not None else "0"))
        label = format(percentage.normalize(), "f")
        rows.append({
            "percentage": str(percentage),
            "trigger_condition": f"{label}% PO总价",
            "description": description.format(percentage=label),
            "idx": index,
        })
    return rows


def _validated_values(master, payload: dict[str, Any], publishing: bool) -> dict[str, Any]:
    contact_id, address_id = _text(payload, "primaryContactId"), _text(payload, "addressId")
    if contact_id: _validate_contact(contact_id, master.account)
    elif publishing: raise CrmApiException("VALIDATION_ERROR", "ATTN is required before publishing.")
    if address_id: _validate_address(address_id, master.account)
    elif publishing: raise CrmApiException("VALIDATION_ERROR", "Address is required before publishing.")
    items, rule_items = _item_rows(payload.get("items"))
    discount_type, discount_value = _text(payload, "discountType", "None"), payload.get("discountValue", "0")
    try:
        totals = calculate_totals(rule_items, discount_type=discount_type, discount_value=discount_value)
        device_prices = {r["lineKey"]: r for r in rule_items if r["lineType"] == "Device"}
        systems = {r["lineKey"]: r for r in rule_items if r["lineType"] == "System"}
        for row, rule in zip(items, rule_items):
            if rule["lineType"] == "System":
                row["line_amount"] = "0.00"
                continue
            if rule["lineType"] == "Device":
                source = [rule]
            else:
                source = [dict(device_prices[rule["parentDeviceKey"]], quantity=1, unitPrice=0)]
                if rule["parentSystemKey"]:
                    source.append(systems[rule["parentSystemKey"]])
                source.append(rule)
            row["line_amount"] = calculate_totals(source, discount_type="None", discount_value="0")["subtotal"]
    except (QuotationRuleError, KeyError) as exc:
        raise CrmApiException("VALIDATION_ERROR", str(exc)) from exc
    quote_date = _text(payload, "quoteDate", today())
    try:
        quote_day = getdate(quote_date)
        validity_months = int(payload.get("validityMonths") or 1)
        delivery_months = int(payload.get("deliveryMonths") or 4)
        warranty_months = int(payload.get("warrantyMonths") or 12)
    except (TypeError, ValueError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "Quotation date and month values must be valid.") from exc
    if not all(1 <= value <= MAX_TERM_MONTHS for value in (validity_months, delivery_months, warranty_months)):
        raise CrmApiException("VALIDATION_ERROR", f"Validity, delivery and warranty months must be between 1 and {MAX_TERM_MONTHS}.")
    valid_until = str(add_months(quote_day, validity_months))
    values = {
        "primary_contact": contact_id or None, "address": address_id or None, "quote_date": quote_date,
        "validity_months": validity_months, "valid_until": valid_until,
        "currency": "CNY", "items": items, "subtotal": totals["subtotal"], "discount_type": discount_type,
        "discount_value": discount_value, "discount_amount": totals["discountAmount"], "total": totals["total"],
        "payment_terms": _payment_rows(payload.get("paymentTerms"), publishing), "incoterm": FIXED_INCOTERM,
        "delivery_months": delivery_months, "delivery_start": "收到买方正式PO为准",
        "warranty_months": warranty_months, "warranty_start": "自发货日起",
        "installation": FIXED_INSTALLATION, "training": FIXED_TRAINING,
        "documentation": FIXED_DOCUMENTATION, "packing": FIXED_PACKING,
    }
    values.update(_snapshot(master.account, contact_id, address_id))
    return values


def _serialize_item(row) -> dict[str, Any]:
    return {
        "lineKey": row.line_key, "lineType": row.line_type,
        "parentDeviceKey": row.parent_device_key or "", "parentSystemKey": row.parent_system_key or "",
        "catalogItemId": row.catalog_item or "", "name": row.item_name,
        "model": row.model or "", "description": row.description or "", "pricingMode": row.pricing_mode,
        "quantity": int(row.quantity or 0), "unitPrice": _db_decimal(row.unit_price), "lineAmount": _db_decimal(row.line_amount),
    }
def _serialized_validity_months(doc) -> int:
    stored = int(doc.validity_months or 0)
    if stored > 0:
        return stored
    quote_day, valid_day = getdate(doc.quote_date), getdate(doc.valid_until)
    months = (valid_day.year - quote_day.year) * 12 + valid_day.month - quote_day.month
    if months > 0 and getdate(add_months(quote_day, months)) == valid_day:
        return months
    return 1


def _serialize_version(doc) -> dict[str, Any]:
    can_read_address = can_read_site_data(doc.account)
    return {
        "id": doc.name, "version": int(doc.version_no or 0), "quotationType": doc.quotation_type or "Device", "status": doc.status, "modified": to_iso_timestamp(doc.modified),
        "approvalStatus": doc.approval_status or "Not Submitted", "currentApprovalId": doc.current_approval or "",
        "refNo": doc.ref_no, "opportunityId": doc.opportunity or "", "accountId": doc.account, "owner": doc.quotation_owner,
        "primaryContactId": doc.primary_contact or "", "addressId": (doc.address or "") if can_read_address else "", "addressRestricted": not can_read_address, "customerName": doc.customer_name_snapshot or "",
        "attentionName": doc.attention_name_snapshot or "", "attentionTitle": doc.attention_title_snapshot or "", "attentionPhone": doc.attention_phone_snapshot or "", "addressText": (doc.address_snapshot or "") if can_read_address else "",
        "quoteDate": str(doc.quote_date or ""), "validityMonths": _serialized_validity_months(doc), "validUntil": str(doc.valid_until or ""), "currency": "CNY",
        "items": [_serialize_item(row) for row in doc.items], "subtotal": _db_decimal(doc.subtotal), "discountType": doc.discount_type,
        "discountValue": _db_decimal(doc.discount_value), "discountAmount": _db_decimal(doc.discount_amount), "total": _db_decimal(doc.total),
        "paymentTerms": [{"percentage": _db_decimal(row.percentage), "triggerCondition": row.trigger_condition, "description": row.description or ""} for row in doc.payment_terms],
        "incoterm": doc.incoterm or "", "deliveryMonths": int(doc.delivery_months or 0), "deliveryStart": doc.delivery_start or "", "warrantyMonths": int(doc.warranty_months or 0), "warrantyStart": doc.warranty_start or "",
        "installation": doc.installation or "", "training": doc.training or "", "documentation": doc.documentation or "", "packing": doc.packing or "",
        "feedbackDate": str(doc.feedback_date or ""), "feedbackNote": doc.feedback_note or "", "pdfAvailable": bool(doc.pdf_file) and can_read_address, "publishedAt": to_iso_timestamp(doc.published_at) if doc.published_at else "",
    }


def _serialize_approval(doc) -> dict[str, Any]:
    return {
        "id": doc.name,
        "quotationId": doc.quotation,
        "versionId": doc.quotation_version,
        "attempt": int(doc.attempt_no or 0),
        "status": doc.status,
        "submittedBy": doc.submitted_by,
        "submittedAt": to_iso_timestamp(doc.submitted_at),
        "decidedBy": doc.decided_by or "",
        "decidedAt": to_iso_timestamp(doc.decided_at) if doc.decided_at else "",
        "comment": doc.decision_comment or "",
    }


def _serialize_master(master) -> dict[str, Any]:
    version = frappe.get_doc("CRM Quotation Version", master.current_version) if master.current_version else None
    status = "Expired" if version and version.status == "Published" and version.valid_until and getdate(version.valid_until) < getdate(today()) else master.status
    return {
        "id": master.name, "refNo": master.ref_no, "quotationType": master.quotation_type or "Device", "opportunityId": master.opportunity or "",
        "opportunityTitle": (frappe.db.get_value("CRM Opportunity", master.opportunity, "title") or master.opportunity) if master.opportunity else "Others",
        "accountId": master.account, "accountName": frappe.db.get_value("Customer", master.account, "customer_name") or master.account,
        "owner": master.quotation_owner, "status": status,
        "approvalStatus": (version.approval_status or "Not Submitted") if version else "Not Submitted",
        "latestVersion": int(master.latest_version_no or 0),
        "currentVersionId": master.current_version or "", "currentPublishedVersionId": master.current_published_version or "", "modified": to_iso_timestamp(master.modified),
    }


def list_quotations(query: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    assert_capability("quotation:view")
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    clauses, values = [f"({conditions_for_doctype('CRM Quotation')})"], []
    opportunity_id = _text(query, "opportunityId")
    if opportunity_id:
        clauses.append("`opportunity` = %s"); values.append(opportunity_id)
    status = _text(query, "status")
    if status and status != "All": clauses.append("`status` = %s"); values.append(status)
    quotation_type = _text(query, "quotationType")
    if quotation_type and quotation_type != "All":
        if quotation_type not in QUOTATION_TYPES:
            raise CrmApiException("VALIDATION_ERROR", "Quotation type must be Device or Service.")
        clauses.append("`quotation_type` = %s"); values.append(quotation_type)
    approval_status = _text(query, "approvalStatus")
    if approval_status and approval_status != "All":
        clauses.append(
            "EXISTS (SELECT 1 FROM `tabCRM Quotation Version` AS `approval_version` "
            "WHERE `approval_version`.`name` = `tabCRM Quotation`.`current_version` "
            "AND `approval_version`.`approval_status` = %s)"
        )
        values.append(approval_status)
    where = " AND ".join(clauses)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Quotation` WHERE {where}", tuple(values))[0][0])
    rows = frappe.db.sql(f"SELECT `name` FROM `tabCRM Quotation` WHERE {where} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s", tuple(values + [page_size, offset]), as_dict=True)
    return [_serialize_master(frappe.get_doc("CRM Quotation", row.name)) for row in rows], total, page, page_size


def quotations_for_account(account_id: str) -> list[dict[str, Any]]:
    assert_capability("quotation:view")
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabCRM Quotation` WHERE `account` = %s "
        f"AND ({conditions_for_doctype('CRM Quotation')}) ORDER BY `modified` DESC, `name` DESC",
        (account_id,),
        as_dict=True,
    )
    return [_serialize_master(frappe.get_doc("CRM Quotation", row.name)) for row in rows]


def get_quotation(name: str, version_id: str | None = None) -> dict[str, Any]:
    assert_capability("quotation:view")
    master = _require_quotation(name)
    selected = _require_version(master, version_id, fallback=master.current_version)
    if selected.quotation != master.name: raise CrmApiException("NOT_FOUND", "Quotation version was not found.")
    history = frappe.get_all("CRM Quotation Version", filters={"quotation": master.name}, fields=["name"], order_by="version_no desc")
    approvals = frappe.get_all("CRM Quotation Approval", filters={"quotation": master.name}, fields=["name"], order_by="attempt_no desc")
    return {
        "quotation": _serialize_master(master),
        "version": _serialize_version(selected),
        "versions": [_serialize_version(frappe.get_doc("CRM Quotation Version", row.name)) for row in history],
        "approvals": [_serialize_approval(frappe.get_doc("CRM Quotation Approval", row.name)) for row in approvals],
    }


def create_quotation(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("quotation:write")
    quotation_type = _text(payload, "quotationType", "Device")
    if quotation_type not in QUOTATION_TYPES:
        raise CrmApiException("VALIDATION_ERROR", "Quotation type must be Device or Service.")
    opportunity_id = _text(payload, "opportunityId")
    opportunity = _require_opportunity(opportunity_id) if opportunity_id else None
    if opportunity and frappe.db.exists("CRM Quotation", {"opportunity": opportunity.name}):
        raise CrmApiException("QUOTATION_ALREADY_EXISTS", "This Opportunity already has a Quotation.")
    account = opportunity.account if opportunity else required_text(payload, "accountId")
    if not frappe.db.exists("Customer", account):
        raise CrmApiException("ACCOUNT_NOT_FOUND", "Account was not found.")
    account_doc = frappe.get_doc("Customer", account)
    if not frappe.has_permission("Customer", "read", doc=account_doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The account is outside the current user scope.")
    _assert_quotation_address_scope(
        account,
        "Only the Account owner or a Manager may create quotations containing Site/Address data.",
    )
    initial = dict(payload)
    initial_quote_date = _text(initial, "quoteDate", today())
    initial["quoteDate"] = initial_quote_date
    owner = opportunity.opportunity_owner if opportunity else frappe.session.user
    if resolve_crm_role() == "Sales" and owner != frappe.session.user: raise CrmApiException("SCOPE_DENIED", "Sales can only create quotations for owned Opportunities.")
    master = None
    for _ in range(5):
        try:
            ref_no = _next_ref_no(initial_quote_date)
        except (TypeError, ValueError) as exc:
            raise CrmApiException("VALIDATION_ERROR", "Quotation date must be valid.") from exc
        try:
            master = frappe.get_doc({"doctype": "CRM Quotation", "ref_no": ref_no, "quotation_type": quotation_type, "opportunity": opportunity.name if opportunity else None, "account": account, "quotation_owner": owner, "status": "Draft", "latest_version_no": 1}).insert(ignore_permissions=True)
            break
        except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
            # Another transaction may have allocated the same sequence while
            # the date had no existing row; recompute from the now-visible max.
            frappe.db.rollback()
    if master is None:
        raise CrmApiException("CONFLICT", "Could not allocate a unique quotation reference.")
    if not initial.get("items"):
        initial["items"] = [{"lineKey": "device-1", "lineType": "Device", "name": "New Device" if quotation_type == "Device" else "New Service Item", "quantity": 1, "unitPrice": "0"}]
    values = _validated_values(master, initial, False)
    version = frappe.get_doc({"doctype": "CRM Quotation Version", "quotation": master.name, "version_no": 1, "quotation_type": quotation_type, "status": "Draft", "approval_status": "Not Submitted", "ref_no": ref_no, "opportunity": opportunity.name if opportunity else None, "account": account, "quotation_owner": owner, **values}).insert(ignore_permissions=True)
    master.current_version = version.name; master.save(ignore_permissions=True)
    return get_quotation(master.name)


def link_quotation_opportunity(
    name: str,
    opportunity_id: str,
    expected_modified: str | None = None,
) -> dict[str, Any]:
    assert_capability("quotation:write")
    savepoint = f"crm_quotation_link_opportunity_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        master = _lock_quotation(name)
        version = lock_document("CRM Quotation Version", master.current_version, expected_modified, "NOT_FOUND")
        master.reload()
        if version.name != master.current_version:
            raise CrmApiException("QUOTATION_VERSION_LOCKED", "The current quotation version changed. Refresh before linking.")
        if master.opportunity:
            raise CrmApiException("QUOTATION_OPPORTUNITY_ALREADY_LINKED", "This Quotation is already linked to an Opportunity.")

        opportunity = _require_opportunity(required_text({"opportunityId": opportunity_id}, "opportunityId"))
        if opportunity.account != master.account:
            raise CrmApiException("LINK_MISMATCH", "The Opportunity must belong to the same Account as the Quotation.")
        if frappe.db.exists("CRM Quotation", {"opportunity": opportunity.name}):
            raise CrmApiException("QUOTATION_ALREADY_EXISTS", "This Opportunity already has a Quotation.")

        master.opportunity = opportunity.name
        master.save(ignore_permissions=True)
        if version.status == "Draft":
            version.opportunity = opportunity.name
            version.save(ignore_permissions=True)
        return get_quotation(master.name)
    except (frappe.UniqueValidationError, frappe.DuplicateEntryError) as exc:
        frappe.db.rollback(save_point=savepoint)
        raise CrmApiException("QUOTATION_ALREADY_EXISTS", "This Opportunity already has a Quotation.") from exc
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def _apply_values(version, values: dict[str, Any]) -> None:
    for fieldname, value in values.items():
        if fieldname in {"items", "payment_terms"}:
            version.set(fieldname, value)
        else:
            setattr(version, fieldname, value)


def save_draft(name: str, payload: dict[str, Any], expected_modified: str | None = None) -> dict[str, Any]:
    assert_capability("quotation:write")
    master = _lock_quotation(name)
    version = lock_document("CRM Quotation Version", master.current_version, expected_modified, "NOT_FOUND")
    master.reload()
    if version.name != master.current_version:
        raise CrmApiException("QUOTATION_VERSION_LOCKED", "The current quotation version changed. Refresh before saving.")
    if version.status != "Draft": raise CrmApiException("QUOTATION_VERSION_LOCKED", "Published quotation versions are immutable.")
    if version.approval_status == "Pending": raise CrmApiException("QUOTATION_VERSION_LOCKED", "A quotation pending approval cannot be edited.")
    _apply_values(version, _validated_values(master, payload, False))
    version.save(ignore_permissions=True); master.status = "Draft"; master.save(ignore_permissions=True)
    return get_quotation(master.name)


def _version_payload(version) -> dict[str, Any]:
    return {
        "primaryContactId": version.primary_contact or "",
        "addressId": version.address or "",
        "quoteDate": str(version.quote_date or ""),
        "validityMonths": _serialized_validity_months(version),
        "items": [_serialize_item(row) for row in version.items],
        "discountType": version.discount_type,
        "discountValue": _db_decimal(version.discount_value),
        "paymentTerms": [
            {
                "percentage": _db_decimal(row.percentage),
                "triggerCondition": row.trigger_condition,
                "description": row.description or "",
            }
            for row in version.payment_terms
        ],
        "deliveryMonths": int(version.delivery_months or 0),
        "warrantyMonths": int(version.warranty_months or 0),
    }


def create_version(name: str) -> dict[str, Any]:
    assert_capability("quotation:write")
    master = _lock_quotation(name)
    current = _require_version(master, None, fallback=master.current_version)
    if current.status == "Draft": raise CrmApiException("QUOTATION_DRAFT_EXISTS", "Finish or discard the current draft before creating a new version.")
    source = _require_version(master, None, fallback=master.current_published_version or master.current_version)
    number = int(master.latest_version_no or 0) + 1
    values = _validated_values(master, _version_payload(source), False)
    version = frappe.get_doc({"doctype": "CRM Quotation Version", "quotation": master.name, "version_no": number, "quotation_type": master.quotation_type or "Device", "status": "Draft", "approval_status": "Not Submitted", "ref_no": master.ref_no, "opportunity": master.opportunity, "account": master.account, "quotation_owner": master.quotation_owner, **values}).insert(ignore_permissions=True)
    master.latest_version_no = number; master.current_version = version.name; master.status = "Draft"; master.save(ignore_permissions=True)
    return get_quotation(master.name)


def discard_draft(name: str, expected_modified: str | None = None) -> dict[str, Any]:
    assert_capability("quotation:write")
    savepoint = f"crm_quotation_discard_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        master = _lock_quotation(name)
        version = lock_document("CRM Quotation Version", master.current_version, expected_modified, "NOT_FOUND")
        master.reload()
        if version.quotation != master.name or version.name != master.current_version:
            raise CrmApiException("NOT_FOUND", "Quotation version was not found.")
        if version.status != "Draft": raise CrmApiException("QUOTATION_VERSION_LOCKED", "Only the current draft can be discarded.")
        if version.approval_status == "Pending": raise CrmApiException("QUOTATION_VERSION_LOCKED", "A quotation pending approval cannot be discarded.")
        # Approval history is immutable. A draft that went to review keeps its record, so it is revised
        # and submitted again, never discarded together with a Manager's decision.
        if frappe.db.exists("CRM Quotation Approval", {"quotation_version": version.name}):
            raise CrmApiException("QUOTATION_VERSION_LOCKED", "A draft that has been through approval cannot be discarded. Revise it and submit it again.")
        published = _require_version(master, None, fallback=master.current_published_version) if master.current_published_version else None
        # Frappe refuses to delete a document that a Link field still names. The Quotation names the draft as
        # its current version, so it is pointed back at the published version (or at nothing) before the delete.
        if published:
            master.current_version = published.name; master.latest_version_no = published.version_no; master.status = published.status
        else:
            master.current_version = None
        master.save(ignore_permissions=True)
        version.delete(ignore_permissions=True)
        if published:
            return get_quotation(master.name)
        # The draft was the only version, so the Quotation goes with it.
        master.delete(ignore_permissions=True)
        return {"id": name, "deleted": True}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise

def _catalog_item_for_row(row, level: str, parent_id: str | None) -> str:
    normalized = _normalize_catalog_name(row.item_name)
    expected_key = _catalog_key(level, parent_id, normalized)
    if row.catalog_item:
        existing = frappe.db.get_value("CRM Quotation Catalog Item", row.catalog_item, ["name", "catalog_key"], as_dict=True)
        if not existing or existing.catalog_key != expected_key:
            raise CrmApiException("VALIDATION_ERROR", "Selected catalog item does not match the quotation hierarchy.")
        return existing.name
    return _upsert_catalog_item(level, normalized, parent_id)


def _register_version_catalog(version) -> None:
    if (version.quotation_type or "Device") != "Device":
        return
    device_ids: dict[str, str] = {}
    system_ids: dict[str, str] = {}
    for row in version.items:
        if row.line_type == "Device":
            device_ids[row.line_key] = _catalog_item_for_row(row, "Device", None)
            row.catalog_item = device_ids[row.line_key]
        elif row.line_type == "System":
            parent_id = device_ids.get(row.parent_device_key)
            if not parent_id:
                raise CrmApiException("VALIDATION_ERROR", "System catalog item requires its parent device.")
            system_ids[row.line_key] = _catalog_item_for_row(row, "System", parent_id)
            row.catalog_item = system_ids[row.line_key]
        elif row.line_type == "Accessory" and row.parent_system_key:
            parent_id = system_ids.get(row.parent_system_key)
            if not parent_id:
                raise CrmApiException("VALIDATION_ERROR", "Accessory catalog item requires its parent system.")
            row.catalog_item = _catalog_item_for_row(row, "Accessory", parent_id)
    version.save(ignore_permissions=True)

def _pdf_context(master, version) -> dict[str, Any]:
    data = _serialize_version(version)
    pricing = calculate_totals(data["items"], discount_type="None", discount_value="0", currency="CNY")
    group_by_key = {group["lineKey"]: dict(group) for group in pricing["deviceGroups"]}
    device_number = 0
    device_count = 0
    template_items = []
    device_groups = []
    system_numbers: dict[str, int] = {}
    for item in data["items"]:
        row = dict(item)
        if item["lineType"] == "Device":
            device_number += 1
            device_count += int(item["quantity"])
            row["displayIndex"] = device_number
            group = group_by_key[item["lineKey"]]
            row.update({"configurationSubtotal": group["configurationSubtotal"], "configurationUnitTotal": group["configurationUnitTotal"]})
            device_groups.append({**group, "displayIndex": device_number, "name": item["name"], "model": item["model"]})
            system_numbers[item["lineKey"]] = 0
        elif item["lineType"] == "System":
            system_numbers[item["parentDeviceKey"]] = system_numbers.get(item["parentDeviceKey"], 0) + 1
            row["displayIndex"] = f"{device_number}.{system_numbers[item['parentDeviceKey']]}"
        else:
            row["displayIndex"] = ""
        template_items.append(row)
    if device_count <= 0:
        raise CrmApiException("VALIDATION_ERROR", "At least one device is required.")
    logo_path = Path(frappe.get_app_path("rayher_crm", "public", "images", "quotation-planck-logo.png"))
    data.update({
        "items": template_items, "deviceGroups": device_groups, "deviceCount": device_count,
        "deviceCountLabel": f"{device_count}台总价（RMB）",
        "logoDataUri": "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode("ascii"),
        "opportunityTitle": (frappe.db.get_value("CRM Opportunity", master.opportunity, "title") or master.opportunity) if master.opportunity else "Others",
        "seller": frappe.db.get_value("User", master.quotation_owner, "full_name") or master.quotation_owner,
        "quoteDateDisplay": getdate(version.quote_date).strftime("%Y/%m/%d"),
    })
    return data
def render_quotation_html(master, version) -> str:
    return frappe.render_template(
        "rayher_crm/templates/quotation/service_quotation.html" if (master.quotation_type or "Device") == "Service" else "rayher_crm/templates/quotation/quotation.html",
        _pdf_context(master, version),
    )


def _assert_publishable_opportunity(master, message: str) -> None:
    if not master.opportunity:
        return
    opportunity = _require_opportunity(master.opportunity)
    if opportunity.stage not in PUBLISHABLE_OPPORTUNITY_STAGES:
        raise CrmApiException("QUOTATION_STAGE_INVALID", message)


def render_quotation_pdf(master, version) -> bytes:
    from bs4 import BeautifulSoup
    from frappe.utils.pdf import get_pdf
    from pypdf import PdfReader, PdfWriter

    rendered = render_quotation_html(master, version)
    soup = BeautifulSoup(rendered, "html.parser")
    header = soup.find(id="header-html")
    if header is None:
        raise CrmApiException("QUOTATION_PDF_FAILED", "Quotation header template was not found.")
    header.extract()
    header.attrs.pop("id", None)
    header["class"] = [name for name in header.get("class", []) if name != "hidden-pdf"]
    placeholder = soup.new_tag("div", id="header-html")
    placeholder.string = " "
    soup.body.insert(0, placeholder)
    header_html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        + "<style>@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;font-family:Arial,'Microsoft YaHei','Noto Sans CJK SC',sans-serif}.quotation-overlay{position:absolute;left:17mm;top:0;width:176mm;height:20mm}.page-header{position:relative;width:176mm;height:20mm}.ref-cell{position:absolute;right:0;top:0;text-align:right;font-size:12.5pt;font-weight:700;white-space:nowrap}.logo{position:absolute;left:0;top:0;width:43mm;height:auto}.header-rule{position:absolute;left:0;top:16mm;width:176mm;border-top:1px solid #111}</style>"
        + "</head><body><div class='quotation-overlay'>"
        + str(header)
        + "</div></body></html>"
    )
    body_pdf = get_pdf(
        str(soup).replace("@page { size: A4; margin: 35mm 17mm 18mm 17mm; }", ""),
        {"margin-top": "35mm", "margin-bottom": "18mm", "margin-left": "17mm", "margin-right": "17mm"},
    )
    overlay_pdf = get_pdf(
        header_html,
        {"margin-top": "0mm", "margin-bottom": "0mm", "margin-left": "0mm", "margin-right": "0mm"},
    )
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(body_pdf)).pages:
        header_page = PdfReader(io.BytesIO(overlay_pdf)).pages[0]
        page.merge_page(header_page, over=True)
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _release_pdf(master, version, pdf_content: bytes) -> str:
    from rayher_crm.services.private_file_lifecycle import save_private_file as save_file
    filename = f"{master.ref_no}-V{int(version.version_no)}.pdf"
    return save_file(filename, pdf_content, "CRM Quotation Version", version.name, is_private=1, attached_to_field="pdf_file").file_url


def _publish_locked(master, version, approval_status: str) -> None:
    released_file = None
    try:
        _apply_values(version, _validated_values(master, _version_payload(version), True))
        _register_version_catalog(version)
        previous = master.current_published_version
        version.save(ignore_permissions=True)
        pdf_content = render_quotation_pdf(master, version)
        version.status = "Published"
        version.approval_status = approval_status
        version.published_at = now_datetime()
        version.save(ignore_permissions=True)
        version.pdf_file = _release_pdf(master, version, pdf_content)
        released_file = frappe.db.get_value("File", {"file_url": version.pdf_file}, "name")
        version.save(ignore_permissions=True)
        if previous and previous != version.name:
            prior = frappe.get_doc("CRM Quotation Version", previous)
            if prior.status in {"Published", "Expired", "Accepted", "Rejected"}: prior.status = "Superseded"; prior.save(ignore_permissions=True)
        master.current_published_version = version.name; master.current_version = version.name; master.status = "Published"; master.save(ignore_permissions=True)
        if master.opportunity:
            from rayher_crm.services.opportunities import advance_opportunity_for_event

            advance_opportunity_for_event(
                master.opportunity, "quotation_published",
                reference_doctype="CRM Quotation Version", reference_name=version.name,
            )
    except Exception:
        if released_file and frappe.db.exists("File", released_file):
            frappe.delete_doc("File", released_file, ignore_permissions=True, force=True)
        raise


def _manager_users() -> list[str]:
    users = frappe.get_all(
        "Has Role",
        filters={"role": "CRM Manager", "parenttype": "User"},
        pluck="parent",
    )
    managers = []
    for user in sorted(set(users)):
        if not frappe.db.get_value("User", user, "enabled"):
            continue
        try:
            if resolve_crm_role(user) == "Manager":
                managers.append(user)
        except frappe.PermissionError:
            continue
    return managers


def submit_for_approval(name: str, expected_modified: str | None = None) -> dict[str, Any]:
    assert_capability("quotation:submit")
    savepoint = f"crm_quotation_submit_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        master = _lock_quotation(name)
        _assert_publishable_opportunity(master, "Opportunity must reach the quotation stage before approval.")
        version = lock_document("CRM Quotation Version", master.current_version, expected_modified, "NOT_FOUND")
        master.reload()
        if version.name != master.current_version or version.status != "Draft":
            raise CrmApiException("QUOTATION_VERSION_LOCKED", "Only the current draft can be submitted for approval.")
        if version.approval_status == "Pending":
            raise CrmApiException("QUOTATION_APPROVAL_ALREADY_PENDING", "This quotation is already pending approval.")
        _apply_values(version, _validated_values(master, _version_payload(version), True))
        _register_version_catalog(version)
        managers = [
            user for user in _manager_users()
            if user != frappe.session.user and can_read_source("CRM Quotation", master.name, user)
        ]
        if not managers:
            raise CrmApiException("VALIDATION_ERROR", "No active CRM Manager is available to approve this quotation.")
        last_attempt = frappe.db.sql(
            "SELECT COALESCE(MAX(`attempt_no`), 0) FROM `tabCRM Quotation Approval` WHERE `quotation` = %s FOR UPDATE",
            (master.name,),
        )[0][0]
        approval = frappe.get_doc({
            "doctype": "CRM Quotation Approval",
            "quotation": master.name,
            "quotation_version": version.name,
            "attempt_no": int(last_attempt or 0) + 1,
            "status": "Pending",
            "submitted_by": frappe.session.user,
            "submitted_at": now_datetime(),
        }).insert(ignore_permissions=True)
        version.approval_status = "Pending"
        version.current_approval = approval.name
        version.save(ignore_permissions=True)
        master.status = "Draft"
        master.save(ignore_permissions=True)
        for manager in managers:
            create_notification(
                recipient=manager,
                category="Quotation",
                title=f"Quotation {master.ref_no} requires approval",
                message=f"{master.ref_no} has been submitted by {frappe.session.user}.",
                route=f"/quotations/{master.name}",
                source_doctype="CRM Quotation",
                source_name=master.name,
            )
        return get_quotation(master.name)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def _lock_approval(approval_id: str):
    rows = frappe.db.sql(
        "SELECT `name`, `status` FROM `tabCRM Quotation Approval` WHERE `name` = %s FOR UPDATE",
        (approval_id,),
        as_dict=True,
    )
    if not rows:
        raise CrmApiException("NOT_FOUND", "Quotation approval was not found.")
    if rows[0].status != "Pending":
        raise CrmApiException("QUOTATION_APPROVAL_ALREADY_DECIDED", "This quotation approval has already been decided.")
    return frappe.get_doc("CRM Quotation Approval", approval_id)


def review_approval(
    name: str,
    decision: str,
    comment: str = "",
    expected_modified: str | None = None,
) -> dict[str, Any]:
    assert_capability("quotation:approve")
    if decision not in APPROVAL_DECISIONS:
        raise CrmApiException("VALIDATION_ERROR", "Approval decision must be Approved or Rejected.")
    normalized_comment = str(comment or "").strip()
    if decision == "Rejected" and not normalized_comment:
        raise CrmApiException("VALIDATION_ERROR", "A rejection reason is required.")
    if len(normalized_comment) > 1000:
        raise CrmApiException("VALIDATION_ERROR", "Approval comment cannot exceed 1,000 characters.")
    savepoint = f"crm_quotation_review_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        master = _lock_quotation(name)
        version = _require_version(master, None, fallback=master.current_version)
        if not version.current_approval:
            raise CrmApiException("NOT_FOUND", "Quotation approval was not found.")
        approval = _lock_approval(version.current_approval)
        version = lock_document("CRM Quotation Version", version.name, expected_modified, "NOT_FOUND")
        master.reload()
        if version.name != master.current_version or version.status != "Draft" or version.approval_status != "Pending":
            raise CrmApiException("QUOTATION_VERSION_LOCKED", "Only the current pending quotation can be reviewed.")
        if approval.quotation != master.name or approval.quotation_version != version.name:
            raise CrmApiException("QUOTATION_VERSION_LOCKED", "The pending approval does not match the current quotation version.")
        approval.status = decision
        approval.decided_by = frappe.session.user
        approval.decided_at = now_datetime()
        approval.decision_comment = normalized_comment
        approval.flags.allow_approval_decision = True
        approval.save(ignore_permissions=True)
        if decision == "Approved":
            _assert_publishable_opportunity(master, "Opportunity must remain in a publishable stage.")
            version.approval_status = "Approved"
            version.save(ignore_permissions=True)
            _publish_locked(master, version, "Approved")
        else:
            version.approval_status = "Rejected"
            version.save(ignore_permissions=True)
            master.status = "Draft"
            master.save(ignore_permissions=True)
        if master.quotation_owner != frappe.session.user:
            notify_if_reachable(
                recipient=master.quotation_owner,
                category="Quotation",
                title=f"Quotation {master.ref_no} {decision.lower()}",
                message=normalized_comment or f"Quotation {master.ref_no} was approved and published.",
                route=f"/quotations/{master.name}",
                source_doctype="CRM Quotation",
                source_name=master.name,
            )
        return get_quotation(master.name)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def publish_version(name: str, expected_modified: str | None = None) -> dict[str, Any]:
    assert_capability("quotation:publish")
    savepoint = f"crm_quotation_publish_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        master = _lock_quotation(name)
        _assert_publishable_opportunity(master, "Opportunity must reach the quotation stage before publishing.")
        version = lock_document("CRM Quotation Version", master.current_version, expected_modified, "NOT_FOUND")
        master.reload()
        if version.name != master.current_version:
            raise CrmApiException("QUOTATION_VERSION_LOCKED", "The current quotation version changed. Refresh before publishing.")
        if version.status != "Draft" or version.approval_status == "Pending":
            raise CrmApiException("QUOTATION_VERSION_LOCKED", "Only an unlocked current draft can be published directly.")
        _publish_locked(master, version, "Not Required")
        return get_quotation(master.name)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def record_decision(name: str, decision: str, feedback_date: str, feedback_note: str, expected_modified: str | None = None) -> dict[str, Any]:
    assert_capability("quotation:write")
    if decision not in DECISION_STATUSES: raise CrmApiException("VALIDATION_ERROR", "Decision must be Accepted or Rejected.")
    if not isinstance(feedback_date, str) or not feedback_date.strip() or not isinstance(feedback_note, str) or not feedback_note.strip():
        raise CrmApiException("VALIDATION_ERROR", "Customer feedback date and note are required.")
    try:
        parsed_feedback_date = getdate(feedback_date)
    except Exception as exc:
        raise CrmApiException("VALIDATION_ERROR", "Customer feedback date must be valid.") from exc
    master = _lock_quotation(name)
    if not master.current_published_version:
        raise CrmApiException("QUOTATION_VERSION_LOCKED", "A formal quotation version is required before recording a decision.")
    version = lock_document("CRM Quotation Version", master.current_published_version, expected_modified, "NOT_FOUND")
    master.reload()
    if version.quotation != master.name:
        raise CrmApiException("NOT_FOUND", "Quotation version was not found.")
    if version.name != master.current_version or version.status not in {"Published", "Expired"}: raise CrmApiException("QUOTATION_VERSION_LOCKED", "Only the latest formal version can receive a decision.")
    version.status = decision; version.feedback_date = parsed_feedback_date; version.feedback_note = feedback_note.strip(); version.save(ignore_permissions=True)
    master.status = decision; master.save(ignore_permissions=True)

    return get_quotation(master.name)

def expire_quotations() -> int:
    rows = frappe.get_all("CRM Quotation Version", filters={"status": "Published", "valid_until": ["<", today()]}, fields=["name", "quotation"])
    expired = 0
    for row in rows:
        master_rows = frappe.db.sql("SELECT `name` FROM `tabCRM Quotation` WHERE `name` = %s FOR UPDATE", (row.quotation,))
        if not master_rows:
            continue
        version_rows = frappe.db.sql(
            "SELECT `status`, `valid_until`, `quotation` FROM `tabCRM Quotation Version` WHERE `name` = %s FOR UPDATE",
            (row.name,), as_dict=True,
        )
        if not version_rows:
            continue
        current = version_rows[0]
        master = frappe.get_doc("CRM Quotation", row.quotation)
        if current.status != "Published" or current.quotation != master.name or not current.valid_until or getdate(current.valid_until) >= getdate(today()):
            continue
        if master.current_published_version != row.name or master.current_version != row.name:
            continue
        version = frappe.get_doc("CRM Quotation Version", row.name)
        version.status = "Expired"; version.save(ignore_permissions=True)
        master.status = "Expired"; master.save(ignore_permissions=True)
        expired += 1
    return expired


def get_preview_pdf(name: str, version_id: str | None = None) -> tuple[str, bytes]:
    assert_capability("quotation:view")
    master = _require_quotation(name)
    version = _require_version(master, version_id, fallback=master.current_version)
    filename = f"{master.ref_no}-V{int(version.version_no)}-preview.pdf"
    return filename, render_quotation_pdf(master, version)

def get_pdf_file(name: str, version_id: str | None = None) -> tuple[str, bytes]:
    assert_capability("quotation:view")
    master = _require_quotation(name)
    _assert_quotation_address_scope(
        master.account,
        "Only the Account owner or a Manager may download quotation PDFs containing an address.",
    )
    if not version_id and not master.current_published_version:
        raise CrmApiException("QUOTATION_PDF_NOT_FOUND", "Published quotation PDF was not found.")
    version = _require_version(master, version_id, fallback=master.current_published_version)
    if not version.pdf_file or version.status == "Draft": raise CrmApiException("QUOTATION_PDF_NOT_FOUND", "Published quotation PDF was not found.")
    file_name = frappe.db.get_value("File", {"file_url": version.pdf_file}, "name")
    if not file_name: raise CrmApiException("QUOTATION_PDF_NOT_FOUND", "Published quotation PDF was not found.")
    file_doc = frappe.get_doc("File", file_name)
    from rayher_crm.services.managed_file_access import authorize_restricted_file_read
    authorize_restricted_file_read(file_doc)
    return f"{master.ref_no}-V{int(version.version_no)}.pdf", file_doc.get_content()
