"""Account-scoped Contact files stored as Frappe Private Files."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import frappe
from frappe.utils import now_datetime
from rayher_crm.services.private_file_lifecycle import save_private_file as save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.permissions.scope import conditions_for_doctype
from rayher_crm.services.contacts import _contact_account, _require_contact
from rayher_crm.services.accounts import ARCHIVED_ACCOUNT_EDIT, _require_account, assert_account_active
from rayher_crm.services.private_file_lifecycle import lock_upload_contents
from rayher_crm.services.file_security import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_REQUEST,
    MAX_REQUEST_BYTES,
    MalwareScanner,
    validate_and_scan,
)
from rayher_crm.services.common import normalize_pagination, to_iso_timestamp
from rayher_crm.services.concurrency import committed_reader


def _part(part: Mapping[str, Any]) -> tuple[str, str, bytes]:
    name = part.get("file_name")
    mime = part.get("mime_type")
    content = part.get("content")
    if not isinstance(name, str) or not isinstance(mime, str) or not isinstance(content, bytes):
        raise CrmApiException("VALIDATION_ERROR", "Each upload requires file_name, mime_type and byte content.")
    return name, mime, content


def _serialize(doc) -> dict[str, Any]:
    return {
        "id": doc.name,
        "contactId": doc.contact,
        "fileName": doc.file_name,
        "mimeType": doc.mime_type,
        "size": int(doc.size_bytes),
        "uploadedAt": to_iso_timestamp(doc.uploaded_at),
        "uploadedBy": doc.uploaded_by,
    }


def _audit(entity_id: str, account: str | None, outcome: str, reason: str = "") -> None:
    frappe.get_doc({
        "doctype": "CRM File Access Audit",
        "entity_type": "Contact File",
        "entity_id": entity_id,
        "account": account,
        "actor": frappe.session.user,
        "action": "Download",
        "outcome": outcome,
        "reason": reason[:140],
        "at": now_datetime(),
        "request_id": str(getattr(frappe.local, "request_id", "") or "")[:140],
    }).insert(ignore_permissions=True)
    frappe.local.flags.commit = True


# A Contact and the Accounts it links (none: one row, its link empty).
CONTACT_ACCOUNTS_QUERY = (
    "SELECT `crm_link`.`link_name` FROM `tabContact` AS `crm_contact` LEFT JOIN `tabDynamic Link` AS `crm_link`"
    " ON `crm_link`.`parent` = `crm_contact`.`name` AND `crm_link`.`parenttype` = 'Contact'"
    " AND `crm_link`.`parentfield` = 'links' AND `crm_link`.`link_doctype` = 'Customer'"
    " WHERE `crm_contact`.`name` = %s"
)


def _current_contact_accounts(contact: str) -> set[str]:
    """The Accounts a Contact links as committed by now, read on a connection of its own (no lock: a locking read of
    the Contact's links would lock a range of the Dynamic Link index other Contacts and Addresses share); a Contact
    this transaction made and has not committed, as the request sees it. Read under its Account's row, held shared
    to the commit, which every move of the Contact takes exclusively (its save locks the Accounts it leaves and
    joins, permissions.scope.revoke_contact_shares_entering_crm), the answer holds to the commit."""

    read, close = committed_reader()
    try:
        rows = read(CONTACT_ACCOUNTS_QUERY, (contact,))
    finally:
        close()
    if not rows:
        rows = frappe.db.sql(CONTACT_ACCOUNTS_QUERY, (contact,))
    return {row[0] for row in rows if row[0]}


def upload_contact_files(contact_id: str, uploads: Sequence[Mapping[str, Any]], scanner: MalwareScanner | None = None) -> list[dict[str, Any]]:
    assert_capability("contact:write")
    contact = _require_contact(contact_id)
    account = _contact_account(contact.name)
    if not account:
        raise CrmApiException("CONTACT_ACCOUNT_MISMATCH", "Contact has no canonical account.")
    account_doc = _require_account(account)
    if resolve_crm_role() != "Manager" and account_doc.custom_crm_owner != frappe.session.user:
        raise CrmApiException("SCOPE_DENIED", "Only the Account owner or a Manager may upload files.")
    if not uploads or len(uploads) > MAX_FILES_PER_REQUEST:
        raise CrmApiException("VALIDATION_ERROR", "Upload must contain between 1 and 10 files.")
    parts = [_part(item) for item in uploads]
    if sum(len(content) for _, _, content in parts) > MAX_REQUEST_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "Upload exceeds the 100 MiB request limit.")

    validated = [(name, validate_and_scan(name, mime, content, scanner), content) for name, mime, content in parts]
    # The files' content locks first, as a Status save takes them (private_file_lifecycle: no content lock is waited
    # for while the Account's row is held). Then the files of an archived Account's Contacts take no change: the flag
    # is read under a shared lock on the Account's row once the files are scanned (the scan takes a while; the row is
    # held from here to the commit), before they are written.
    lock_upload_contents((name, content) for name, _, content in validated)
    assert_account_active(account, ARCHIVED_ACCOUNT_EDIT)
    # A Contact moved to another Account while its files were scanned (that Account may be archived) is refused as
    # changed, before anything is written.
    if account not in _current_contact_accounts(contact.name):
        raise CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
    savepoint = f"crm_contact_files_{frappe.generate_hash(length=8)}"
    frappe.db.savepoint(savepoint)
    result = []
    try:
        for name, mime, content in validated:
            file_doc = save_file(name, content, "Contact", contact.name, is_private=1)
            meta = frappe.get_doc({
                "doctype": "CRM Contact File", "contact": contact.name, "account": account,
                "private_file": file_doc.name, "file_name": name, "mime_type": mime,
                "size_bytes": len(content), "content_hash": hashlib.sha256(content).hexdigest(),
                "uploaded_by": frappe.session.user, "uploaded_at": now_datetime(), "deleted": 0,
            }).insert(ignore_permissions=True)
            frappe.db.set_value("File", file_doc.name, {"attached_to_doctype": "CRM Contact File", "attached_to_name": meta.name, "attached_to_field": None, "owner": "Administrator"}, update_modified=False)
            meta.reload()
            result.append(_serialize(meta))
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    return result


def list_contact_files(contact_id: str, query: Mapping[str, Any] | None = None):
    assert_capability("contact:view")
    _require_contact(contact_id)
    where = f"contact = %s AND deleted = 0 AND ({conditions_for_doctype('CRM Contact File')})"
    values: tuple[Any, ...] = (contact_id,)
    if query is None:
        rows = frappe.db.sql(
            f"SELECT name FROM `tabCRM Contact File` WHERE {where} ORDER BY uploaded_at DESC, name DESC",
            values, as_dict=True,
        )
        return [_serialize(frappe.get_doc("CRM Contact File", row.name)) for row in rows]
    page, page_size, offset = normalize_pagination(query.get("page"), query.get("pageSize"))
    total = int(frappe.db.sql(f"SELECT COUNT(*) FROM `tabCRM Contact File` WHERE {where}", values)[0][0])
    rows = frappe.db.sql(
        f"SELECT name FROM `tabCRM Contact File` WHERE {where} ORDER BY uploaded_at DESC, name DESC LIMIT %s OFFSET %s",
        (*values, page_size, offset), as_dict=True,
    )
    return [_serialize(frappe.get_doc("CRM Contact File", row.name)) for row in rows], total, page, page_size


def download_contact_file(file_id: str) -> dict[str, Any]:
    try:
        assert_capability("contact:view")
    except frappe.PermissionError:
        _audit(file_id, None, "Denied", "capability denied")
        raise
    if not frappe.db.exists("CRM Contact File", file_id):
        _audit(file_id, None, "Denied", "not found")
        raise CrmApiException("CONTACT_FILE_NOT_FOUND", "Contact file was not found.")
    meta = frappe.get_doc("CRM Contact File", file_id)
    if meta.deleted:
        _audit(file_id, meta.account, "Denied", "deleted")
        raise CrmApiException("CONTACT_FILE_NOT_FOUND", "Contact file was not found.")
    if not frappe.has_permission("CRM Contact File", "read", doc=meta, user=frappe.session.user):
        _audit(file_id, meta.account, "Denied", "scope denied")
        raise CrmApiException("SCOPE_DENIED", "The file is outside the current user scope.")
    file_doc = frappe.get_doc("File", meta.private_file)
    from rayher_crm.services.managed_file_access import contact_file_matches
    if not contact_file_matches(file_doc, meta):
        _audit(file_id, meta.account, "Denied", "invalid file association")
        raise CrmApiException("CONTACT_FILE_NOT_FOUND", "Contact file was not found.")
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    _audit(file_id, meta.account, "Allowed")
    return {"content": bytes(content), "file_name": meta.file_name, "mime_type": meta.mime_type}


def delete_contact_file(file_id: str) -> dict[str, str]:
    assert_capability("contact:write")
    if not frappe.db.exists("CRM Contact File", file_id):
        raise CrmApiException("CONTACT_FILE_NOT_FOUND", "Contact file was not found.")
    meta = frappe.get_doc("CRM Contact File", file_id)
    if meta.deleted:
        raise CrmApiException("CONTACT_FILE_NOT_FOUND", "Contact file was not found.")
    if not frappe.has_permission("CRM Contact File", "read", doc=meta, user=frappe.session.user):
        raise CrmApiException("SCOPE_DENIED", "The file is outside the current user scope.")
    # The files of an archived Account's Contacts take no change (the Contact's Account as it stands now, the
    # one the file was uploaded under if the Contact has none; one that is gone is not archived).
    account = _contact_account(meta.contact) or meta.account
    assert_account_active(account, ARCHIVED_ACCOUNT_EDIT)
    # A Contact moved meanwhile is refused as changed, as an upload is.
    if account not in (_current_contact_accounts(meta.contact) or {meta.account}):
        raise CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
    meta.deleted = 1
    meta.deleted_by = frappe.session.user
    meta.deleted_at = now_datetime()
    meta.save(ignore_permissions=True)
    return {"id": meta.name}
