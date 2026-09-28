"""Lead services backed by the standard ERPNext Lead DocType."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

import frappe
from frappe.utils import validate_email_address

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.common import (
    delete_manager_scoped_document,
    ensure_server_generated_id,
    normalize_pagination,
    optional_date,
    required_text,
    resolve_write_owner,
    to_iso_timestamp,
    validate_choice,
)
from rayher_crm.services.concurrency import lock_document
from rayher_crm.services.notifications import create_notification


LEAD_STATUSES = {"New", "Working", "Qualified", "Nurturing", "Disqualified", "Converted"}
LEAD_SOURCES = {"Website", "Trade Show", "Partner Referral", "Outbound", "Customer Referral", "Other"}
MAX_OPPORTUNITY_AMOUNT = Decimal("999999999999999999.99")


def delete_lead(name: str) -> dict[str, str]:
    return delete_manager_scoped_document("Lead", name, "deal:write", "LEAD_NOT_FOUND")


def serialize_lead(doc) -> dict[str, Any]:
    result = {
        "id": doc.name,
        "name": " ".join(part for part in (doc.first_name, doc.last_name) if part).strip() or doc.name,
        "company": doc.company_name or "",
        "title": doc.job_title or "",
        "phone": doc.phone or "",
        "email": doc.email_id or "",
        "source": doc.custom_crm_source,
        "status": doc.custom_crm_status,
        "owner": doc.lead_owner,
        "interest": doc.custom_crm_interest or "",
        "firstContactNote": doc.custom_crm_first_contact_note or "",
        "nextAction": doc.custom_crm_next_action or "",
        "nextActionDue": str(doc.custom_crm_next_action_due or ""),
        "activities": [],
        "createdAt": to_iso_timestamp(doc.creation),
        "updatedAt": to_iso_timestamp(doc.modified),
        "modified": to_iso_timestamp(doc.modified),
    }
    converted_fields = {
        "convertedAt": doc.custom_crm_converted_at,
        "convertedAccountId": doc.custom_crm_converted_account,
        "convertedContactId": doc.custom_crm_converted_contact,
        "convertedOpportunityId": doc.custom_crm_converted_opportunity,
    }
    for key, value in converted_fields.items():
        if value:
            result[key] = to_iso_timestamp(value) if key == "convertedAt" else value
    if doc.custom_crm_status == "Converted":
        result["convertedReusedAccount"] = bool(doc.custom_crm_reused_account)
        result["convertedReusedContact"] = bool(doc.custom_crm_reused_contact)
    return result


def _validate_lead(payload: dict[str, Any]) -> dict[str, Any]:
    phone = str(payload.get("phone") or "").strip()
    email = str(payload.get("email") or "").strip()
    if not phone and not email:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "A phone number or email address is required.",
            field_errors={"phone": "Phone or email required", "email": "Phone or email required"},
        )
    if email:
        validated_email = validate_email_address(email)
        if not validated_email:
            raise CrmApiException(
                "VALIDATION_ERROR",
                "email is invalid.",
                field_errors={"email": "Invalid email"},
            )
        email = validated_email
    return {
        "name": required_text(payload, "name"),
        "company": required_text(payload, "company"),
        "title": required_text(payload, "title"),
        "phone": phone,
        "email": email,
        "source": validate_choice(payload.get("source"), "source", LEAD_SOURCES),
        "status": validate_choice(payload.get("status"), "status", LEAD_STATUSES),
        "owner": resolve_write_owner(payload.get("owner")),
        "interest": str(payload.get("interest") or "").strip(),
        "first_contact_note": str(payload.get("firstContactNote") or "").strip(),
        "next_action": str(payload.get("nextAction") or "").strip(),
        "next_action_due": optional_date(payload.get("nextActionDue"), "nextActionDue"),
    }


def _require_lead(name: str):
    if not frappe.db.exists("Lead", name):
        raise CrmApiException("LEAD_NOT_FOUND", "Lead was not found.")
    doc = frappe.get_doc("Lead", name)
    if not frappe.has_permission("Lead", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The lead is outside the current user scope.")
    return doc


def list_leads(query: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int, int]:
    assert_capability("deal:view")
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    where = [f"({conditions_for_doctype('Lead')})"]
    values: list[Any] = []
    search = str(query.get("search") or "").strip()
    if search:
        pattern = f"%{search}%"
        where.append("(`first_name` LIKE %s OR `last_name` LIKE %s OR `company_name` LIKE %s OR `email_id` LIKE %s)")
        values.extend([pattern, pattern, pattern, pattern])
    status = query.get("status")
    if status and status != "All":
        where.append("`custom_crm_status` = %s")
        values.append(status)
    source = query.get("source")
    if source and source != "All":
        where.append("`custom_crm_source` = %s")
        values.append(source)
    owner = query.get("owner")
    if owner and owner != "All":
        where.append("`lead_owner` = %s")
        values.append(owner)
    where_sql = " AND ".join(where)
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabLead` WHERE {where_sql}", tuple(values))[0][0])
    rows = frappe.db.sql(
        f"SELECT `name` FROM `tabLead` WHERE {where_sql} ORDER BY `modified` DESC, `name` DESC LIMIT %s OFFSET %s",
        tuple([*values, page_size, offset]),
        as_dict=True,
    )
    return [serialize_lead(frappe.get_doc("Lead", row.name)) for row in rows], total, page, page_size


def _apply_lead(doc, values: dict[str, Any]) -> None:
    doc.first_name = values["name"]
    doc.last_name = None
    doc.company_name = values["company"]
    doc.job_title = values["title"]
    doc.phone = values["phone"]
    doc.email_id = values["email"]
    doc.status = "Converted" if values["status"] == "Converted" else "Lead"
    doc.lead_owner = values["owner"]
    doc.custom_crm_source = values["source"]
    doc.custom_crm_status = values["status"]
    doc.custom_crm_interest = values["interest"]
    doc.custom_crm_first_contact_note = values["first_contact_note"]
    doc.custom_crm_next_action = values["next_action"]
    doc.custom_crm_next_action_due = values["next_action_due"]


def create_lead(payload: dict[str, Any]) -> dict[str, Any]:
    assert_capability("deal:write")
    if frappe.db.get_single_value("CRM Settings", "auto_creation_of_contact"):
        raise CrmApiException(
            "INTERNAL_ERROR",
            "CRM Lead configuration is not ready. Run the rayher_crm migration.",
        )
    ensure_server_generated_id(payload)
    values = _validate_lead(payload)
    if values["status"] == "Converted":
        raise CrmApiException("VALIDATION_ERROR", "A Lead cannot be created as Converted.")
    savepoint = f"crm_lead_create_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        doc = frappe.new_doc("Lead")
        _apply_lead(doc, values)
        doc.insert(ignore_permissions=True)
        if doc.lead_owner != frappe.session.user:
            create_notification(
                recipient=doc.lead_owner, category="Lead", title="Lead assigned",
                message=f"You are now responsible for {doc.lead_name}.",
                route=f"/leads/{doc.name}", source_doctype="Lead", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_lead(doc)


def update_lead(name: str, payload: dict[str, Any], expected_modified: Any) -> dict[str, Any]:
    assert_capability("deal:write")
    existing = _require_lead(name)
    if existing.custom_crm_status == "Converted":
        raise CrmApiException("LEAD_ALREADY_CONVERTED", "Converted Leads cannot be edited.")
    values = _validate_lead(payload)
    if values["status"] == "Converted":
        raise CrmApiException("VALIDATION_ERROR", "Use the Lead conversion endpoint to convert a Lead.")
    doc = lock_document("Lead", name, expected_modified, "NOT_FOUND")
    if not frappe.has_permission("Lead", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The lead is outside the current user scope.")
    previous_owner = doc.lead_owner
    savepoint = f"crm_lead_update_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        _apply_lead(doc, values)
        doc.save(ignore_permissions=True)
        if previous_owner != doc.lead_owner and doc.lead_owner != frappe.session.user:
            create_notification(
                recipient=doc.lead_owner, category="Lead", title="Lead reassigned",
                message=f"You are now responsible for {doc.lead_name}.",
                route=f"/leads/{doc.name}", source_doctype="Lead", source_name=doc.name,
            )
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    doc.reload()
    return serialize_lead(doc)


def get_lead(name: str) -> dict[str, Any]:
    assert_capability("deal:view")
    return serialize_lead(_require_lead(name))


def _opportunity_amount(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise CrmApiException("VALIDATION_ERROR", "opportunityAmount must be a positive amount.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CrmApiException("VALIDATION_ERROR", "opportunityAmount must be a positive amount.") from exc
    if not amount.is_finite() or amount <= 0 or amount > MAX_OPPORTUNITY_AMOUNT or amount.as_tuple().exponent < -2:
        raise CrmApiException("VALIDATION_ERROR", "opportunityAmount must be positive with at most two decimal places.")
    return amount


def _conversion_result(doc) -> dict[str, Any]:
    return {
        "lead": serialize_lead(doc),
        "accountId": doc.custom_crm_converted_account,
        "contactId": doc.custom_crm_converted_contact,
        "opportunityId": doc.custom_crm_converted_opportunity,
        "reusedAccount": bool(doc.custom_crm_reused_account),
        "reusedContact": bool(doc.custom_crm_reused_contact),
    }


def _lock_lead_for_conversion(name: str):
    rows = frappe.db.sql("SELECT `name` FROM `tabLead` WHERE `name` = %s FOR UPDATE", (name,))
    if not rows:
        raise CrmApiException("LEAD_NOT_FOUND", "Lead was not found.")
    doc = frappe.get_doc("Lead", name)
    if not frappe.has_permission("Lead", "read", doc=doc, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The lead is outside the current user scope.")
    return doc


def _validate_conversion(payload: dict[str, Any]) -> dict[str, Any]:
    from rayher_crm.services.opportunities import assert_qualification_confirmed

    assert_qualification_confirmed(payload)
    po_date = optional_date(payload.get("opportunityCloseDate"), "opportunityCloseDate")
    if not po_date:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "opportunityCloseDate is required.",
            field_errors={"opportunityCloseDate": "Required"},
        )
    currency = str(payload.get("currency") or "CNY").strip().upper()
    if not frappe.db.exists("Currency", currency):
        raise CrmApiException("VALIDATION_ERROR", "currency is invalid.", field_errors={"currency": "Invalid value"})
    return {
        "title": required_text(payload, "opportunityTitle"),
        "amount": _opportunity_amount(payload.get("opportunityAmount")),
        "po_date": po_date,
        "currency": currency,
        "owner": resolve_write_owner(payload.get("opportunityOwner")),
        "tool_type": required_text(payload, "toolType"),
    }


def convert_lead(
    name: str,
    payload: dict[str, Any],
    *,
    failure_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Atomically convert a Lead to CRM records, returning prior IDs on retries."""

    assert_capability("deal:write")
    lead = _lock_lead_for_conversion(name)
    if lead.custom_crm_status == "Converted":
        result = _conversion_result(lead)
        if all(result[key] for key in ("accountId", "contactId", "opportunityId")):
            return result
        raise CrmApiException("LEAD_CONVERSION_INCOMPLETE", "The Lead has an incomplete conversion record.")

    values = _validate_conversion(payload)
    savepoint = f"crm_convert_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    try:
        from rayher_crm.services.accounts import _require_account, create_account
        from rayher_crm.services.contacts import _contact_account, _require_contact, create_contact
        from rayher_crm.services.opportunities import insert_qualified_opportunity
        from rayher_crm.services.sites import _require_site, create_site, sites_for_account

        account_id = str(payload.get("accountId") or "").strip()
        reused_account = bool(account_id)
        if account_id:
            _require_account(account_id)
        else:
            new_account = payload.get("newAccount")
            if not isinstance(new_account, dict):
                raise CrmApiException("VALIDATION_ERROR", "accountId or newAccount is required.")
            account_payload = dict(new_account)
            account_payload["owner"] = frappe.session.user
            account_id = create_account(account_payload)["id"]
        if failure_injector:
            failure_injector("account")

        site_id = str(payload.get("siteId") or "").strip()
        if site_id:
            _require_site(site_id, account_id)
        elif reused_account:
            existing_sites = sites_for_account(account_id)
            if not existing_sites:
                raise CrmApiException("SITE_NOT_FOUND", "The selected Account has no available Site.")
            site_id = existing_sites[0]["id"]
        else:
            new_site = payload.get("newSite")
            if not isinstance(new_site, dict):
                raise CrmApiException("VALIDATION_ERROR", "newSite is required for a new Account.")
            site_id = create_site(account_id, dict(new_site))["id"]
        if failure_injector:
            failure_injector("site")

        contact_id = str(payload.get("contactId") or "").strip()
        reused_contact = bool(contact_id)
        if contact_id:
            _require_contact(contact_id)
            if _contact_account(contact_id) != account_id:
                raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "The contact belongs to another account.")
        else:
            new_contact = payload.get("newContact")
            if not isinstance(new_contact, dict):
                raise CrmApiException("VALIDATION_ERROR", "contactId or newContact is required.")
            contact_payload = dict(new_contact)
            contact_payload["accountId"] = account_id
            contact_payload["siteId"] = site_id
            contact_payload["owner"] = frappe.session.user
            contact_id = create_contact(contact_payload)["id"]
        if failure_injector:
            failure_injector("contact")

        sub_region = frappe.db.get_value("Customer", account_id, "custom_crm_region") or ""
        opportunity = insert_qualified_opportunity(
            {
                "account": account_id,
                "site": site_id,
                "source_lead": lead.name,
                "title": values["title"],
                "amount": values["amount"],
                "currency": values["currency"],
                "original_amount": values["amount"],
                "po_date": values["po_date"],
                "opportunity_owner": values["owner"],
                "tool_type": values["tool_type"],
                "score": 20,
                "sale_type": "New Equipment",
                "sub_region": sub_region,
            },
            event="lead_converted",
            reference_doctype="Lead",
            reference_name=lead.name,
        )
        frappe.get_doc(
            {
                "doctype": "CRM Opportunity History",
                "opportunity": opportunity.name,
                "actor": frappe.session.user,
                "at": frappe.utils.now_datetime(),
                "field": "leadConversion",
                "from_value": "",
                "to_value": lead.name,
            }
        ).insert(ignore_permissions=True)
        if failure_injector:
            failure_injector("opportunity")

        lead.status = "Converted"
        lead.custom_crm_status = "Converted"
        lead.custom_crm_converted_account = account_id
        lead.custom_crm_converted_contact = contact_id
        lead.custom_crm_converted_opportunity = opportunity.name
        lead.custom_crm_converted_at = frappe.utils.now_datetime()
        lead.custom_crm_reused_account = reused_account
        lead.custom_crm_reused_contact = reused_contact
        lead.save(ignore_permissions=True)
        if failure_injector:
            failure_injector("lead")
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise

    lead.reload()
    return _conversion_result(lead)
