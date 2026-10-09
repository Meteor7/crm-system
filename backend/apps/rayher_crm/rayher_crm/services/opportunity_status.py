"""Opportunity-scoped Status notes and private attachments, saved atomically.

One row per attachment in `CRM Status Attachment`, soft-deleted on removal. The
bytes behind a removed attachment are never unlinked: keeping them costs disk,
while deleting them costs a content lock, a tombstone column, an after-commit
queue and an hourly sweep -- and every one of those was a source of defects.
This mirrors `CRM Contact File`, which has always worked this way.
"""
from __future__ import annotations

import hashlib
from contextlib import suppress
from typing import Any

import frappe
from frappe.utils import now_datetime
from frappe.utils.html_utils import sanitize_html
from rayher_crm.services.private_file_lifecycle import discard_rolled_back_blob, lock_upload_contents
from rayher_crm.services.private_file_lifecycle import save_private_file as save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.permissions.roles import assert_capability, resolve_crm_role
from rayher_crm.services.common import normalize_expected_modified, required_text, to_iso_timestamp
from rayher_crm.services.file_security import (
    MAX_FILES_PER_REQUEST, MAX_REQUEST_BYTES, TIPRAY_HEADER, detect_mime, validate_and_scan,
)
from rayher_crm.services.opportunities import _require_opportunity
from rayher_crm.services.opportunity_archive import assert_opportunity_not_archived

DOCTYPE = "CRM Opportunity Status"
ATTACHMENT_DOCTYPE = "CRM Status Attachment"
MAX_TEXT_LENGTH = 10000
MAX_FILE_NAME_LENGTH = 140  # Both File and CRM Status Attachment use Data fields.


def _payload(row) -> dict:
    return {
        "id": row.name,
        "fileName": row.file_name,
        "mimeType": row.mime_type,
        "size": int(row.size_bytes),
    }


def _query_active(status_ids: list[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {status_id: [] for status_id in status_ids}
    if not status_ids:
        return grouped
    # One save shares its `uploaded_at`, and the rows are hash-named: `creation`
    # keeps them in upload order.
    rows = frappe.db.sql(
        """SELECT name, status, file_name, mime_type, size_bytes
             FROM `tabCRM Status Attachment`
            WHERE status IN %s AND deleted = 0
            ORDER BY uploaded_at ASC, creation ASC, name ASC""",
        (tuple(status_ids),),
        as_dict=True,
    )
    for row in rows:
        grouped[row.status].append(_payload(row))
    return grouped


def _serialize(row, files: list[dict]) -> dict:
    return {
        "id": row.name, "text": row.information, "files": files,
        "updatedAt": to_iso_timestamp(row.modified), "updatedBy": row.modified_by,
        "modified": to_iso_timestamp(row.modified),
    }


def _require_record(opportunity_id: str, record_id: str):
    if not frappe.db.exists(DOCTYPE, {"name": record_id, "opportunity": opportunity_id}):
        raise CrmApiException("NOT_FOUND", "Status record was not found.")
    return frappe.get_doc(DOCTYPE, record_id)


def list_records(opportunity_id: str) -> list[dict]:
    assert_capability("deal:view")
    _require_opportunity(opportunity_id)
    rows = frappe.get_all(
        DOCTYPE, filters={"opportunity": opportunity_id},
        fields=["name", "information", "modified", "modified_by"],
        order_by="modified desc, name desc",
    )
    grouped = _query_active([row.name for row in rows])
    return [_serialize(row, grouped[row.name]) for row in rows]


def _stored_file_name(file_name: str) -> str:
    # Frappe's XSS filter rewrites a Data value once it finds a tag in it, after
    # its own length check: stray `<` and `&` become entities, attributes gain
    # quotes, open tags gain closing ones. The stored name can so be longer than
    # the one the user typed. Mirror that rewrite here.
    if "<" not in file_name and ">" not in file_name:
        return file_name
    return sanitize_html(file_name)


def _validate_upload(part: dict, scanner) -> str:
    # The length as typed first: the filter parses the whole name, so it must never see an unbounded one.
    if len(part["file_name"]) > MAX_FILE_NAME_LENGTH:
        raise CrmApiException("VALIDATION_ERROR", "File name including extension must not exceed 140 characters.")
    if len(_stored_file_name(part["file_name"])) > MAX_FILE_NAME_LENGTH:
        raise CrmApiException(
            "VALIDATION_ERROR",
            "File name including extension must not exceed 140 characters once the HTML filter has rewritten it.",
        )
    mime = part["mime_type"]
    if part["file_name"].lower().endswith(".csv") and mime == "application/vnd.ms-excel":
        mime = "text/csv"
    elif mime in ("", "application/octet-stream"):
        mime = detect_mime(part["content"], part["file_name"]) or mime
    return validate_and_scan(part["file_name"], mime, part["content"], scanner)


def _storage_name(part: dict) -> str:
    # TipRay-protected bytes are no image, whatever the name says: Frappe would try
    # to strip EXIF from a ".jpg" and fail. The other upload services store them
    # the same way; the ledger keeps the real name and type.
    if part["content"].startswith(TIPRAY_HEADER):
        return f"tipray-{frappe.generate_hash(length=20)}.bin"
    return part["file_name"]


def _lock_write_scope(opportunity_id: str) -> None:
    # The Account's row first, then the Opportunity's: the order the Account's archive, and every writer that starts
    # a record under an Account, take them in. Each is read under its own lock, as committed (a current read under
    # REPEATABLE READ): the Account named by the snapshot's Opportunity, then the Opportunity alone. One moved to
    # another Account meanwhile is refused as changed, and that Account's row is not taken (after the Opportunity's,
    # it would reverse the order).
    account = frappe.db.get_value("CRM Opportunity", opportunity_id, "account")
    customers = frappe.db.sql(
        "SELECT `name`, `custom_crm_owner`, `custom_crm_visibility` FROM `tabCustomer` WHERE `name` = %s FOR UPDATE",
        (account,), as_dict=True,
    ) if account else []
    rows = frappe.db.sql(
        "SELECT `opportunity_owner`, `archived`, `account` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE",
        (opportunity_id,), as_dict=True,
    )
    if not rows:
        raise CrmApiException("NOT_FOUND", "Opportunity was not found.")
    opportunity = rows[0]
    if (opportunity.account or None) != (account or None):
        raise CrmApiException("VERSION_CONFLICT", "The record was changed by another request.")
    customer = customers[0] if customers else None
    # As committed now: an archived Opportunity takes no status record and no scorecard link.
    assert_opportunity_not_archived(opportunity.archived)
    # Match the existing Sales policy: owned opportunity AND an owned/public account.
    if resolve_crm_role() == "Sales" and (
        opportunity.opportunity_owner != frappe.session.user or not customer
        or (customer.custom_crm_owner != frappe.session.user and customer.custom_crm_visibility != "Public")
    ):
        raise CrmApiException("SCOPE_DENIED", "The Opportunity is outside the current user scope.")


def _lock_attachments(status_id: str) -> list[dict]:
    """Current read of this Status record's attachment rows, locked by primary key.

    `_lock_write_scope` already serialises every save against one Opportunity and
    its Account, and the version check turns away a save that began before another
    one committed; this adds a current read of the `deleted` flags.

    It must not lock a range of the non-unique `status` index. Under REPEATABLE
    READ that takes next-key and gap locks reaching the neighbouring Status record
    -- hash-named, so usually on another Opportunity -- whose attachment insert
    then has to wait on the range; with any lock the two saves take in the
    opposite order that is a deadlock. Frappe's naming-series row, which every
    `format:` name shares, was one: reproduced on MariaDB 10.6. The names come
    from a plain read and the rows are locked by primary key, which takes record
    locks -- plus, where a locked key starts an index page, the gap before it.

    Only rows that are still active: nothing ever un-deletes one, and it keeps the
    list within the 10-attachment cap. Past MariaDB's 1000-value
    `in_predicate_conversion_threshold` the list becomes a derived table, and the
    plan can turn into a full index scan that locks every row.
    """
    names = frappe.db.sql(
        "SELECT name FROM `tabCRM Status Attachment` WHERE status = %s AND deleted = 0",
        (status_id,), pluck=True,
    )
    if not names:
        return []
    return frappe.db.sql(
        """SELECT name, deleted FROM `tabCRM Status Attachment`
            WHERE name IN %s ORDER BY name FOR UPDATE""",
        (tuple(names),), as_dict=True,
    )


def save_record(opportunity_id: str, payload: dict[str, Any], uploads: list[dict], scanner=None) -> dict:
    assert_capability("deal:write")
    _require_opportunity(opportunity_id)
    text = required_text(payload, "text")
    if len(text) > MAX_TEXT_LENGTH:
        raise CrmApiException("VALIDATION_ERROR", "Status information must not exceed 10000 characters.")
    retained = payload.get("retainedFileIds", [])
    if not isinstance(retained, list) or any(not isinstance(item, str) for item in retained) or len(set(retained)) != len(retained):
        raise CrmApiException("VALIDATION_ERROR", "retainedFileIds must contain unique file IDs.")
    if len(retained) + len(uploads) > MAX_FILES_PER_REQUEST:
        raise CrmApiException("VALIDATION_ERROR", "A Status record supports at most 10 attachments.")
    if sum(len(part["content"]) for part in uploads) > MAX_REQUEST_BYTES:
        raise CrmApiException("VALIDATION_ERROR", "Upload exceeds the 100 MiB request limit.")
    validated = [(part, _validate_upload(part, scanner), _storage_name(part)) for part in uploads]
    record_id = payload.get("recordId")
    if record_id is not None and not isinstance(record_id, str):
        raise CrmApiException("VALIDATION_ERROR", "recordId must be a string.")
    # Before any row lock, so a wait here never holds what another save needs.
    lock_upload_contents((storage_name, part["content"]) for part, _, storage_name in validated)
    savepoint = "crm_status_" + frappe.generate_hash(length=8)
    written: list[tuple[str, str, str]] = []
    frappe.db.savepoint(savepoint)
    try:
        _lock_write_scope(opportunity_id)
        if record_id:
            rows = frappe.db.sql(
                "SELECT name FROM `tabCRM Opportunity Status` WHERE name = %s AND opportunity = %s FOR UPDATE",
                (record_id, opportunity_id),
            )
            if not rows:
                raise CrmApiException("NOT_FOUND", "Status record was not found.")
            doc = frappe.get_doc(DOCTYPE, record_id, for_update=True)
            if to_iso_timestamp(doc.modified) != normalize_expected_modified(payload.get("expectedModified")):
                raise CrmApiException("VERSION_CONFLICT", "Status was changed by another request. Reload before editing.")
            active = {row.name for row in _lock_attachments(doc.name) if not int(row.deleted or 0)}
        else:
            doc = frappe.get_doc({"doctype": DOCTYPE, "opportunity": opportunity_id})
            active = set()
        if any(file_id not in active for file_id in retained):
            raise CrmApiException("VALIDATION_ERROR", "Attachments must belong to this Status record.")
        doc.information = text
        if not record_id:
            doc.insert(ignore_permissions=True)
        now = now_datetime()
        actor = frappe.session.user
        for part, mime, storage_name in validated:
            # Tracked for the rollback path below.
            # The ledger row does not exist yet, so the File starts unattached and is
            # re-pointed below -- the same two-step `CRM Contact File` uses. Naming a
            # doctype with no row would leave a File pointing at nothing.
            file_doc = save_file(storage_name, part["content"], None, None, is_private=1)
            written.append((file_doc.get_full_path(), file_doc.file_url, file_doc.content_hash))
            meta = frappe.get_doc({
                "doctype": ATTACHMENT_DOCTYPE, "status": doc.name, "opportunity": opportunity_id,
                "private_file": file_doc.name, "file_name": part["file_name"], "mime_type": mime,
                "size_bytes": len(part["content"]),
                "content_hash": hashlib.sha256(part["content"]).hexdigest(),
                "uploaded_by": actor, "uploaded_at": now, "deleted": 0,
            }).insert(ignore_permissions=True)
            # `File.has_permission` short-circuits to True for a file's own owner,
            # before it ever consults the attached document. Administrator ownership
            # keeps the uploader on the scoped download endpoint like every other
            # non-superuser: Administrator itself is allowed through earlier still.
            frappe.db.set_value("File", file_doc.name, {
                "owner": "Administrator",
                "attached_to_doctype": ATTACHMENT_DOCTYPE,
                "attached_to_name": meta.name,
                "attached_to_field": None,
            }, update_modified=False)
        for file_id in sorted(active - set(retained)):
            removed = frappe.get_doc(ATTACHMENT_DOCTYPE, file_id)
            removed.deleted = 1
            removed.deleted_by = actor
            removed.deleted_at = now
            removed.save(ignore_permissions=True)
        doc.save(ignore_permissions=True)
        return _serialize(doc, _query_active([doc.name])[doc.name])
    except Exception:
        # A deadlock rolls back the whole transaction, savepoint included; the
        # `ROLLBACK TO SAVEPOINT` would then raise and replace the error that
        # explains the failure. The request edge still rolls back in full.
        try:
            frappe.db.rollback(save_point=savepoint)
        except Exception:
            with suppress(Exception):
                # Error level: the app logger drops warnings unless it runs under the dev server.
                frappe.logger("rayher_crm").error(
                    "Status save could not roll back to its savepoint", exc_info=True,
                )
        # "Never unlink bytes" is about attachments a user removed, which stay
        # reachable in the ledger. Bytes from a save that never happened belong to
        # nobody, and demo reports and visit records already discard theirs.
        # `discard_rolled_back_blob` is reference-counted and never raises, so it
        # cannot take a blob an earlier upload de-duplicated onto the same path,
        # and it cannot replace the exception we are about to re-raise.
        for path, file_url, content_hash in written:
            discard_rolled_back_blob(path, file_url, content_hash)
        raise


def _audit_download(file_id: str, account: str | None, outcome: str, reason: str = "") -> None:
    frappe.get_doc({
        "doctype": "CRM File Access Audit", "entity_type": "Status Attachment",
        "entity_id": file_id, "account": account, "actor": frappe.session.user,
        "action": "Download", "outcome": outcome, "reason": reason[:140],
        "at": now_datetime(),
        "request_id": str(getattr(frappe.local, "request_id", "") or "")[:140],
    }).insert(ignore_permissions=True)
    # Download is a GET; also persist denied access when the API catches the error.
    frappe.local.flags.commit = True


def download_file(opportunity_id: str, record_id: str, file_id: str) -> dict:
    account = None
    try:
        assert_capability("deal:view")
        opportunity = _require_opportunity(opportunity_id)
        account = opportunity.account
        doc = _require_record(opportunity_id, record_id)
        meta = frappe.db.get_value(
            ATTACHMENT_DOCTYPE, file_id,
            ["name", "status", "private_file", "file_name", "mime_type", "deleted"],
            as_dict=True,
        )
        if not meta or meta.status != doc.name or int(meta.deleted or 0):
            raise CrmApiException("NOT_FOUND", "Status attachment was not found.")
        file_doc = frappe.get_doc("File", meta.private_file)
        if not file_doc.is_private:
            raise CrmApiException("NOT_FOUND", "Status attachment was not found.")
        from rayher_crm.services.managed_file_access import authorize_restricted_file_read
        authorize_restricted_file_read(file_doc)
        content = file_doc.get_content()
    except CrmApiException as error:
        _audit_download(file_id, account, "Denied", error.code)
        raise
    except frappe.PermissionError:
        _audit_download(file_id, account, "Denied", "capability denied")
        raise
    except (frappe.DoesNotExistError, FileNotFoundError):
        _audit_download(file_id, account, "Denied", "file missing")
        raise CrmApiException("NOT_FOUND", "Status attachment was not found.")
    except Exception as error:
        # Any other storage failure. Re-raised as it is, it would reach the generic
        # handler of `api_endpoint`, whose rollback takes this audit row with it; a
        # `CrmApiException` leaves the request's commit flag to persist the row.
        _audit_download(file_id, account, "Denied", f"storage error: {type(error).__name__}")
        try:
            frappe.log_error(title="Status attachment could not be read")
        except Exception:
            # Escaping from here would reach the very rollback this branch avoids.
            with suppress(Exception):
                frappe.logger("rayher_crm").exception("Status attachment could not be read")
        raise CrmApiException(
            "INTERNAL_ERROR", "The attachment could not be read.", retryable=True,
        ) from error
    _audit_download(file_id, account, "Allowed")
    return {
        "content": content.encode() if isinstance(content, str) else bytes(content),
        "file_name": meta.file_name,
        "mime_type": meta.mime_type,
    }
