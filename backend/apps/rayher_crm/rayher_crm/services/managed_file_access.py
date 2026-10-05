"""Keep CRM attachments behind their upload service and current business scope.

This does not change the ownership or permissions of unrelated ERP attachments.
The identity of the in-memory token cannot be supplied by a JSON File payload.
"""
from __future__ import annotations

import posixpath
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote, urlsplit

import frappe

from rayher_crm.patches.v1_0.add_file_content_hash_index import INDEX_NAME as FILE_CONTENT_HASH_INDEX


_UPLOAD_TOKEN = object()
_CONTROLLED_READ_TOKEN = object()
_RESTRICTED_READ_TOKEN = object()
_WRITTEN_BODY_TOKEN = object()
_NATIVE_DOWNLOAD_CLASSIFICATION_KEY = object()
PROVENANCE_FIELD = "custom_crm_service_upload"
_PROTECTED_FIELDS = (
    "attached_to_doctype", "attached_to_name", "attached_to_field", "file_url",
    "is_private", "is_folder", "owner", "content_hash", "file_name", PROVENANCE_FIELD,
)
_MANAGED_FILE_CANDIDATE_QUERY = """SELECT name, attached_to_doctype, custom_crm_service_upload
FROM `tabFile` FORCE INDEX (PRIMARY) WHERE name=%s
UNION
SELECT name, attached_to_doctype, custom_crm_service_upload
FROM `tabFile` FORCE INDEX (file_url_index)
WHERE %s IS NOT NULL AND file_url=%s"""
_CONTROLLED_DIRECT_FILE_QUERY = """SELECT name, file_url, file_name, is_private, content_hash,
attached_to_doctype, attached_to_name
FROM `tabFile` FORCE INDEX (attached_to_doctype_attached_to_name_index)
WHERE attached_to_doctype='CRM Controlled Document'"""
_PROTECTED_BLOB_FIELDS = """name, file_url, file_name, is_private, is_folder,
content_hash, attached_to_doctype, attached_to_name, custom_crm_service_upload"""
_PROTECTED_BLOB_URL_QUERY = f"""SELECT {_PROTECTED_BLOB_FIELDS}
FROM `tabFile` FORCE INDEX (file_url_index)
WHERE %s IS NOT NULL AND file_url=%s FOR UPDATE"""
_PROTECTED_BLOB_HASH_QUERY = f"""SELECT {_PROTECTED_BLOB_FIELDS}
FROM `tabFile` FORCE INDEX ({FILE_CONTENT_HASH_INDEX})
WHERE %s IS NOT NULL AND content_hash=%s FOR UPDATE"""


def _crm_target(doctype) -> bool:
    # ERPNext also has names starting with CRM (for example CRM Note).
    return bool(doctype and frappe.db.get_value("DocType", doctype, "module") == "Rayher CRM")


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        frappe.throw("Invalid local file reference.", frappe.ValidationError)
    if port is None and parsed.scheme.lower() in {"http", "https"}:
        port = 80 if parsed.scheme.lower() == "http" else 443
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def canonical_local_reference(*, file_url=None, file_name=None, is_private=None) -> str | None:
    """Return the local URL that core File will resolve, without reading it.

    Frappe accepts a bare private ``file_name`` and resolves dot segments in a
    supplied URL on both POSIX and Windows. Use POSIX URL rules explicitly and
    treat backslashes as separators so a deployment OS cannot change this
    security decision. External HTTP(S) files and API-backed remote files are
    not local references and return ``None``.
    """
    raw = str(file_url or file_name or "")
    if not raw:
        return None
    raw = unquote(raw).replace("\\", "/")
    if "\x00" in raw:
        frappe.throw("Invalid local file reference.", frappe.ValidationError)

    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme.lower() not in {"http", "https"}:
            frappe.throw("Invalid local file reference.", frappe.ValidationError)
        if _origin(raw) != _origin(frappe.utils.get_url()):
            return None
        if "/files/" not in raw:
            # Core resolves a same-site absolute URL to storage only when it
            # contains "/files/" (File.validate_remote_file, get_full_path);
            # other same-site links remain ordinary remote links.
            return None
        path = parsed.path
    elif raw.startswith("/api/method/"):
        return None
    else:
        path = parsed.path

    if "/" not in path:
        path = f"/{'private/' if is_private else ''}files/{path}"
    elif not path.startswith("/"):
        frappe.throw("Invalid local file reference.", frappe.ValidationError)

    normalized = posixpath.normpath(path)
    is_file_url = normalized.startswith("/private/files/") or normalized.startswith("/files/")
    if not is_file_url:
        frappe.throw("Local file reference escapes the files directory.", frappe.ValidationError)
    return normalized


def canonical_local_file_inventory() -> dict:
    """Return one read-only snapshot grouped by the path Frappe will open.

    Release patches use this full-table inventory while traffic is paused. Runtime
    permission checks use indexed equality lookups instead and never call it.
    """
    files: dict[str, frappe._dict] = {}
    by_reference: dict[str, list[frappe._dict]] = {}
    rows = frappe.get_all(
        "File",
        fields=[
            "name", "file_url", "file_name", "is_private", "is_folder",
            "attached_to_doctype", "attached_to_name", PROVENANCE_FIELD,
        ],
        order_by="name",
    )
    for row in rows:
        reference = None
        reference_error = False
        try:
            if not row.is_folder or row.file_url:
                reference = canonical_local_reference(
                    file_url=row.file_url,
                    file_name=row.file_name,
                    is_private=row.is_private,
                )
        except (frappe.ValidationError, frappe.PermissionError, ValueError):
            # Inventory records the invalid row instead of leaking a caught
            # frappe.throw message into a later response.
            frappe.clear_last_message()
            reference_error = True
        entry = frappe._dict(row)
        entry.canonical_reference = reference
        entry.reference_error = reference_error
        files[row.name] = entry
        # Folder rows are included: File.validate skips them, so an older
        # folder can carry the URL of a managed blob like any other alias.
        if reference:
            by_reference.setdefault(reference, []).append(entry)
    return {"files": files, "by_reference": by_reference}


def invalid_local_reference_problems(snapshot: dict) -> list[dict[str, str]]:
    """Malformed local rows cannot be proven unrelated to a managed blob.

    Every release inventory already reads this snapshot. Report these rows
    before mutation instead of silently dropping possible historical aliases.
    Ordinary folders without a URL, remote links and API references are valid.
    """
    return [
        {"file": row.name, "reason": "invalid-local-file-reference"}
        for row in snapshot["files"].values() if row.reference_error
    ]


def canonical_file_alias_inventory(
    target_names: Iterable[str], *, snapshot: dict | None = None,
) -> dict:
    """Validate canonical private targets and find every equivalent File row."""
    snapshot = snapshot or canonical_local_file_inventory()
    targets = {str(name) for name in target_names if name}
    missing: list[str] = []
    invalid: list[str] = []
    references: set[str] = set()
    for name in sorted(targets):
        row = snapshot["files"].get(name)
        if not row:
            missing.append(name)
            continue
        reference = row.canonical_reference
        if reference and reference.startswith("/private/files/"):
            references.add(reference)
        if (
            row.reference_error
            or row.is_folder
            or not row.is_private
            or not reference
            or not reference.startswith("/private/files/")
            or str(row.file_url or "") != reference
        ):
            invalid.append(name)
    aliases = {
        row.name
        for reference in references
        for row in snapshot["by_reference"].get(reference, [])
        if row.name not in targets
    }
    # Runtime URL lookups use the File column's database collation. Exact
    # Python grouping above also covers physical-path aliases, but must not
    # discard distinct spellings that the database considers equal. Compare
    # normalized references in bounded batches, including absolute URLs and
    # filename fallbacks, without emulating MariaDB collation in Python.
    candidates = [
        (row.name, row.canonical_reference)
        for row in snapshot["files"].values()
        if row.name not in targets and row.canonical_reference
    ]
    target_names = sorted(targets)
    for offset in range(0, len(candidates), 100):
        batch = candidates[offset:offset + 100]
        reference_query = " UNION ALL ".join(
            "SELECT %s AS file_name, %s AS canonical_reference" for _ in batch
        )
        reference_values = tuple(value for candidate in batch for value in candidate)
        for target_offset in range(0, len(target_names), 500):
            target_batch = target_names[target_offset:target_offset + 500]
            placeholders = ", ".join(["%s"] * len(target_batch))
            matches = frappe.db.sql(
                f"SELECT DISTINCT candidate.file_name FROM ({reference_query}) AS candidate "
                "INNER JOIN `tabFile` AS target FORCE INDEX (file_url_index) "
                "ON target.file_url=candidate.canonical_reference "
                f"WHERE target.name IN ({placeholders})",
                reference_values + tuple(target_batch),
            )
            aliases.update(row[0] for row in matches)
    return {
        "snapshot": snapshot,
        "targets": sorted(targets),
        "missing": missing,
        "invalid": invalid,
        "aliases": sorted(aliases),
        "references": sorted(references),
    }


def _controlled_file(name) -> bool:
    return "controlled" in _managed_file_kinds(name)


def _contact_file(name) -> bool:
    return "contact" in _managed_file_kinds(name)


def _visit_file(name) -> bool:
    return "visit" in _managed_file_kinds(name)


def _managed_file_kinds(doc_or_name, *, _native_download=False) -> set[str]:
    """Classify a persisted File and canonical aliases with indexed lookups."""
    if not doc_or_name:
        return set()
    if isinstance(doc_or_name, str):
        doc = frappe.db.get_value(
            "File", doc_or_name,
            ["name", "file_url", "file_name", "is_private", "is_folder", "attached_to_doctype"],
            as_dict=True,
        )
        if not doc:
            return set()
    else:
        doc = doc_or_name
    # Never skip the candidate lookup for folders. ``is_folder`` is set on the
    # in-memory document before permission checks run, and older rows could be
    # flagged by their owner; the persisted row and its URL decide the class.
    if not getattr(doc, "name", None):
        return set()
    reference = None
    try:
        if not doc.get("is_folder") or doc.get("file_url"):
            reference = canonical_local_reference(
                file_url=doc.get("file_url"),
                file_name=doc.get("file_name"),
                is_private=doc.get("is_private"),
            )
    except (frappe.ValidationError, frappe.PermissionError, ValueError):
        frappe.clear_last_message()
        frappe.throw("The file storage reference requires administrator review.", frappe.PermissionError)

    # Reuse only classification within the stock private-URL GET/HEAD loop.
    # RPC dispatch precedes that route, so a matching path alone is insufficient.
    # Authorization still runs independently for every candidate File below.
    request = getattr(frappe.local, "request", None)
    form_dict = getattr(frappe.local, "form_dict", None) or {}
    reuse = bool(
        _native_download and request is not None
        and request.method in {"GET", "HEAD"} and not form_dict.get("cmd")
        and reference and reference.startswith("/private/files/")
        and request.path == reference == doc.get("file_url")
    )
    if reuse:
        cached = frappe.db.value_cache.get(_NATIVE_DOWNLOAD_CLASSIFICATION_KEY)
        if (
            cached and cached["request"] is request
            and cached["writes"] == frappe.db.transaction_writes
            and cached["reference"] == reference and doc.name in cached["names"]
        ):
            return set(cached["kinds"])

    # Keep the two candidate lookups as separate indexable branches. MariaDB can
    # otherwise choose a full tabFile scan for ``name = ... OR file_url = ...``
    # once the association checks below are added.
    candidates = frappe.db.sql(
        _MANAGED_FILE_CANDIDATE_QUERY,
        (doc.name, reference, reference),
        as_dict=True,
    )
    kinds = _classify_file_candidates(candidates)
    if reuse:
        # The database value cache clears on framework commit and rollback,
        # including rollback to a savepoint. The write count invalidates reuse
        # after normal Document/db.set_value or INSERT/UPDATE/DELETE writes.
        # Stock permission hooks are read-only. Extensions doing transaction
        # control/raw writes outside those framework contracts must not opt
        # into this native traversal reuse.
        frappe.db.value_cache[_NATIVE_DOWNLOAD_CLASSIFICATION_KEY] = {
            "request": request, "writes": frappe.db.transaction_writes,
            "reference": reference, "names": frozenset(row.name for row in candidates),
            "kinds": frozenset(kinds),
        }
    return kinds


def _classify_file_candidates(candidates) -> set[str]:
    """Classify a candidate union with bounded reverse-association queries.

    Repeated email attachments can share a URL indefinitely. Module lookups
    depend on distinct DocTypes, never the number of File rows in that group.
    """
    candidates = list(candidates)
    if not candidates:
        return set()
    kinds = set()
    attached_to_doctypes = {row.attached_to_doctype for row in candidates}
    native_kinds = {
        "CRM Controlled Document": "controlled",
        "CRM Contact File": "contact",
        "CRM Visit": "visit",
    }
    kinds.update(native_kinds[doctype] for doctype in attached_to_doctypes if doctype in native_kinds)
    if any(
        frappe.utils.cint(row.custom_crm_service_upload)
        and row.attached_to_doctype not in native_kinds
        for row in candidates
    ) or any(_crm_target(doctype) for doctype in attached_to_doctypes if doctype not in native_kinds):
        kinds.add("restricted")

    names = sorted({row.name for row in candidates})
    for offset in range(0, len(names), 500):
        batch = names[offset:offset + 500]
        placeholders = ", ".join(["%s"] * len(batch))
        if "controlled" not in kinds and frappe.db.sql(
            f"""SELECT name FROM `tabCRM Controlled Document`
            WHERE private_file IN ({placeholders}) OR preview_file IN ({placeholders})
            LIMIT 1""",
            tuple(batch + batch),
        ):
            kinds.add("controlled")
        if "contact" not in kinds and frappe.db.sql(
            f"""SELECT name FROM `tabCRM Contact File`
            WHERE private_file IN ({placeholders}) LIMIT 1""",
            tuple(batch),
        ):
            kinds.add("contact")
        if {"controlled", "contact"} <= kinds:
            break
    return kinds


def _controlled_file_query_condition(alias: str) -> str:
    """Build the File-list guard from bounded controlled target lookups."""
    documents = frappe.get_all(
        "CRM Controlled Document", fields=["name", "private_file", "preview_file"],
    )
    target_parents: dict[str, set[str]] = {}
    for document in documents:
        if not document.private_file:
            frappe.throw(
                "Controlled document file associations require administrator review.",
                frappe.PermissionError,
            )
        for file_name in (document.private_file, document.preview_file):
            if file_name:
                target_parents.setdefault(file_name, set()).add(document.name)
    target_names = sorted({
        file_name
        for document in documents
        for file_name in (document.private_file, document.preview_file)
        if file_name
    })
    direct_rows = frappe.db.sql(_CONTROLLED_DIRECT_FILE_QUERY, as_dict=True)
    target_rows = []
    if target_names:
        placeholders = ", ".join(["%s"] * len(target_names))
        target_rows = frappe.db.sql(
            f"""SELECT name, file_url, file_name, is_private, content_hash,
            attached_to_doctype, attached_to_name
            FROM `tabFile` FORCE INDEX (PRIMARY)
            WHERE name IN ({placeholders})""",
            tuple(target_names),
            as_dict=True,
        )

    target_by_name = {row.name: row for row in target_rows}
    if set(target_names) != set(target_by_name):
        frappe.throw(
            "Controlled document file associations require administrator review.",
            frappe.PermissionError,
        )
    for file_name, parents in target_parents.items():
        row = target_by_name[file_name]
        if len(parents) != 1 or (
            row.attached_to_doctype, row.attached_to_name,
        ) != ("CRM Controlled Document", next(iter(parents))):
            frappe.throw(
                "Controlled document file associations require administrator review.",
                frappe.PermissionError,
            )
    if any(row.name not in target_parents for row in direct_rows):
        frappe.throw(
            "Controlled document file associations require administrator review.",
            frappe.PermissionError,
        )

    controlled_rows = [*direct_rows, *target_rows]
    allowed_names = sorted({*target_names, *(row.name for row in direct_rows)})
    urls = sorted({row.file_url for row in controlled_rows if row.file_url})
    hashes = sorted({row.content_hash for row in controlled_rows if row.content_hash})
    references = set()
    for row in controlled_rows:
        try:
            reference = canonical_local_reference(
                file_url=row.file_url, file_name=row.file_name, is_private=row.is_private,
            )
        except (frappe.ValidationError, frappe.PermissionError, ValueError):
            frappe.clear_last_message()
            frappe.throw(
                "Controlled document file associations require administrator review.",
                frappe.PermissionError,
            )
        if (
            not row.is_private
            or not reference
            or not reference.startswith("/private/files/")
            or str(row.file_url or "") != reference
        ):
            frappe.throw(
                "Controlled document file associations require administrator review.",
                frappe.PermissionError,
            )
        references.add(reference)

    # Core's File permission condition is a top-level OR expression, so its
    # unattached-owner arm can bypass later app hook conditions. Reject legacy
    # aliases before returning that condition, using only the two indexed blob
    # identifiers. The release inventory remains responsible for detecting
    # malformed canonical references before traffic resumes.
    allowed_placeholders = ", ".join(["%s"] * len(allowed_names))
    if urls:
        url_placeholders = ", ".join(["%s"] * len(urls))
        if frappe.db.sql(
            f"""SELECT name FROM `tabFile` FORCE INDEX (file_url_index)
            WHERE file_url IN ({url_placeholders})
            AND name NOT IN ({allowed_placeholders}) LIMIT 1""",
            tuple(urls + allowed_names),
        ):
            frappe.throw(
                "Controlled document file associations require administrator review.",
                frappe.PermissionError,
            )
    if hashes:
        hash_placeholders = ", ".join(["%s"] * len(hashes))
        hash_candidates = frappe.db.sql(
            f"""SELECT name, file_url, file_name, is_private
            FROM `tabFile` FORCE INDEX ({FILE_CONTENT_HASH_INDEX})
            WHERE content_hash IN ({hash_placeholders})
            AND name NOT IN ({allowed_placeholders})""",
            tuple(hashes + allowed_names),
            as_dict=True,
        )
        for candidate in hash_candidates:
            try:
                reference = canonical_local_reference(
                    file_url=candidate.file_url,
                    file_name=candidate.file_name,
                    is_private=candidate.is_private,
                )
            except (frappe.ValidationError, frappe.PermissionError, ValueError):
                frappe.clear_last_message()
                continue
            if reference in references:
                frappe.throw(
                    "Controlled document file associations require administrator review.",
                    frappe.PermissionError,
                )

    conditions = [f"COALESCE({alias}.attached_to_doctype,'')='CRM Controlled Document'"]
    if target_names:
        names = ", ".join(frappe.db.escape(name, percent=False) for name in target_names)
        conditions.append(f"{alias}.name IN ({names})")
    if urls:
        urls = ", ".join(frappe.db.escape(url, percent=False) for url in urls)
        conditions.append(f"COALESCE({alias}.file_url,'') IN ({urls})")
    return "(" + " OR ".join(conditions) + ")"


def _local_url(url) -> str:
    return canonical_local_reference(file_url=url, is_private=True) or unquote(str(url or ""))


def _protected_blob(*, url=None, content_hash=None) -> bool:
    if not url and not content_hash:
        return False
    reference = _local_url(url) if url else None
    candidates: dict[str, frappe._dict] = {}
    url_matches: set[str] = set()
    for query, value in (
        (_PROTECTED_BLOB_URL_QUERY, reference),
        (_PROTECTED_BLOB_HASH_QUERY, content_hash),
    ):
        if not value:
            continue
        for row in frappe.db.sql(query, (value, value), as_dict=True):
            candidates[row.name] = row
            if query == _PROTECTED_BLOB_URL_QUERY:
                url_matches.add(row.name)

    if reference:
        same_reference = {}
        for name, row in candidates.items():
            # These rows already match under the same database URL comparison
            # used by runtime permission checks. Preserve that result even if
            # their spelling differs from this physical path.
            if name in url_matches:
                same_reference[name] = row
                continue
            try:
                candidate_reference = canonical_local_reference(
                    file_url=row.file_url,
                    file_name=row.file_name,
                    is_private=row.is_private,
                )
            except (frappe.ValidationError, frappe.PermissionError, ValueError):
                frappe.clear_last_message()
                continue
            if candidate_reference == reference:
                same_reference[name] = row
        candidates = same_reference

    # Keep the current-read URL/hash locks above. Classify direct targets first,
    # then expand distinct canonical URLs once instead of re-reading an entire
    # shared-URL group for every ordinary email attachment in it.
    if any(frappe.utils.cint(row.custom_crm_service_upload) for row in candidates.values()) or any(
        _crm_target(doctype) for doctype in {row.attached_to_doctype for row in candidates.values()}
    ):
        return True
    references = set()
    for row in candidates.values():
        try:
            candidate_reference = None
            if not row.is_folder or row.file_url:
                candidate_reference = canonical_local_reference(
                    file_url=row.file_url, file_name=row.file_name, is_private=row.is_private,
                )
            if candidate_reference:
                references.add(candidate_reference)
        except (frappe.ValidationError, frappe.PermissionError, ValueError):
            frappe.clear_last_message()
            frappe.throw("The file storage reference requires administrator review.", frappe.PermissionError)
    references = sorted(references)
    for offset in range(0, len(references), 500):
        batch = references[offset:offset + 500]
        placeholders = ", ".join(["%s"] * len(batch))
        for row in frappe.db.sql(
            "SELECT name, attached_to_doctype, custom_crm_service_upload "
            "FROM `tabFile` FORCE INDEX (file_url_index) "
            f"WHERE file_url IN ({placeholders})",
            tuple(batch), as_dict=True,
        ):
            # Preserve already locked current-read rows over snapshot copies.
            candidates.setdefault(row.name, row)
    return bool(_classify_file_candidates(candidates.values()))


def lock_canonical_file_siblings(doc) -> tuple[str | None, list[frappe._dict]]:
    """Lock File rows that resolve to the local path currently used by ``doc``.

    Core changes privacy for every equal hash. CRM service blobs can have equal
    hashes at independent paths, so callers need the narrower physical sibling
    set. Exact raw/canonical URL lookups cover stale hashes; the indexed hash
    lookup covers supported same-site absolute URL spellings.
    """
    reference = canonical_local_reference(
        file_url=doc.file_url,
        file_name=doc.file_name,
        is_private=doc.is_private,
    )
    if not reference:
        return None, []

    fields = (
        "name, file_url, file_name, is_private, content_hash, "
        "attached_to_doctype, attached_to_name, custom_crm_service_upload"
    )
    candidates: dict[str, frappe._dict] = {}
    for value in dict.fromkeys((str(doc.file_url or ""), reference)):
        if not value:
            continue
        rows = frappe.db.sql(
            f"SELECT {fields} FROM `tabFile` FORCE INDEX (file_url_index) "
            "WHERE file_url=%s ORDER BY name FOR UPDATE",
            (value,),
            as_dict=True,
        )
        candidates.update({row.name: row for row in rows})
    if doc.content_hash:
        rows = frappe.db.sql(
            f"SELECT {fields} FROM `tabFile` FORCE INDEX ({FILE_CONTENT_HASH_INDEX}) "
            "WHERE content_hash=%s ORDER BY name FOR UPDATE",
            (doc.content_hash,),
            as_dict=True,
        )
        candidates.update({row.name: row for row in rows})

    siblings = []
    for row in candidates.values():
        try:
            candidate_reference = canonical_local_reference(
                file_url=row.file_url,
                file_name=row.file_name,
                is_private=row.is_private,
            )
        except (frappe.ValidationError, frappe.PermissionError, ValueError):
            frappe.clear_last_message()
            continue
        if candidate_reference == reference:
            siblings.append(row)
    return reference, sorted(siblings, key=lambda row: row.name)


def authorize_service_upload(doc, content, logical_file_name: str) -> None:
    doc.flags.crm_upload_token = _UPLOAD_TOKEN
    # Keep the original upload bytes on the server-owned document. Core Frappe
    # may resolve an equal hash to another File row before our doc-event runs;
    # those bytes let the event split the physical path without reading the
    # other row's attachment back from disk.
    doc.flags.crm_upload_content = content
    doc.flags.crm_upload_logical_file_name = logical_file_name
    doc.set(PROVENANCE_FIELD, 1)


def restore_service_file_name(doc) -> None:
    if doc.flags.get("crm_upload_token") is _UPLOAD_TOKEN:
        doc.file_name = doc.flags.crm_upload_logical_file_name


def record_new_private_body(doc) -> None:
    """Capture server-owned evidence immediately after core writes a new body."""
    if not doc.is_new() or not doc.is_private or doc.is_folder:
        return
    path = doc.get_full_path()
    try:
        stat = Path(path).stat()
    except OSError:
        return
    doc.flags.crm_written_body = (
        _WRITTEN_BODY_TOKEN, path, doc.file_url, doc.file_name, doc.content_hash,
        (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns),
    )


def _discard_detached_upload_body(record) -> None:
    """Best-effort cleanup of the physical body replaced during an insert."""
    from contextlib import suppress
    from rayher_crm.services.private_file_lifecycle import (
        _blob_matches_path,
        _lock_content,
        _unlink_private_file,
    )

    if not isinstance(record, tuple) or len(record) != 6 or record[0] is not _WRITTEN_BODY_TOKEN:
        return
    _, path, file_url, file_name, content_hash, identity = record
    stored = frappe._dict(
        file_url=file_url, file_name=file_name, is_private=1, content_hash=content_hash,
    )
    try:
        if not stored.content_hash or not _lock_content(stored.content_hash, required=False):
            return
        # URL collation is appropriate for access decisions, but physical
        # cleanup must preserve only rows that resolve to this exact path.
        # These are current indexed locking reads under the content lock.
        _, siblings = lock_canonical_file_siblings(stored)
        if siblings or not _blob_matches_path(path, stored.content_hash):
            return
        stat = Path(path).stat()
        if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != identity:
            return
        _unlink_private_file(path)
    except Exception:
        with suppress(Exception):
            frappe.logger("rayher_crm").exception("Could not remove a replaced upload body")


def isolate_reused_upload_blob(doc) -> None:
    """Split unsafe URLs selected by core's global content de-duplication.

    Equal bytes may cross unrelated CRM delivery boundaries. Sharing a URL in
    that case either widens one boundary or makes both legitimate endpoints
    deny the now-mixed blob. Keeping service URLs independent is deliberately
    stricter than Frappe's global content-hash de-duplication; the content hash
    remains available for audit and deletion serialization.
    """
    trusted_service = doc.flags.get("crm_upload_token") is _UPLOAD_TOKEN
    raw_url = str(doc.file_url or "")
    reference = canonical_local_reference(
        file_url=doc.file_url, file_name=doc.file_name, is_private=doc.is_private,
    )
    existing_url_rows = frappe.db.sql(
        "SELECT name FROM `tabFile` FORCE INDEX (file_url_index) WHERE file_url=%s LIMIT 1",
        # Core copied this exact stored value from the row it de-duplicated
        # against. Querying the canonicalized spelling would miss a supported
        # same-site absolute URL and leave that ordinary row as a native bypass.
        (raw_url,),
    )
    if not reference or not existing_url_rows:
        return
    # Ordinary ERP uploads retain normal de-duplication unless their equal hash
    # can resolve to any protected CRM blob. They must not become an unguarded
    # alias of a service attachment when core happens to select that row first.
    if not trusted_service and not _protected_blob(
        url=raw_url, content_hash=doc.content_hash,
    ):
        return
    content = (
        doc.flags.get("crm_upload_content")
        if trusted_service else (doc.get("content") if doc.get("content") is not None else getattr(doc, "_content", None))
    )
    if content is None:
        frappe.throw("The service upload bytes are unavailable. Please upload the file again.")
    written_body = doc.flags.get("crm_written_body")
    if not (
        isinstance(written_body, tuple) and len(written_body) == 6
        and written_body[0] is _WRITTEN_BODY_TOKEN
        and written_body[2] == raw_url and written_body[4] == doc.content_hash
    ):
        written_body = None
    # Core's rollback callback reads the mutable File's final URL. Capture the
    # original storage identity as well, in case this was a freshly written
    # body instead of a reused body owned by an existing File row.
    if written_body:
        frappe.db.after_rollback.add(lambda: _discard_detached_upload_body(written_body))
    # A same-site absolute URL is local to Frappe's path resolver but makes
    # ``File.is_remote_file`` true; clear the reused reference so save_file does
    # not return before writing the independent local blob.
    doc.file_url = ""
    doc.save_file(content=content, ignore_existing_file_check=True)
    new_reference = canonical_local_reference(
        file_url=doc.file_url, file_name=doc.file_name, is_private=doc.is_private,
    )
    if not new_reference or frappe.db.sql(
        "SELECT name FROM `tabFile` FORCE INDEX (file_url_index) WHERE file_url=%s LIMIT 1",
        (str(doc.file_url or ""),),
    ):
        frappe.throw("The service attachment could not be isolated. Please upload the file again.")
    if written_body and new_reference != reference:
        _discard_detached_upload_body(written_body)


def authorize_controlled_file_read(doc) -> None:
    doc.flags.crm_controlled_read_token = _CONTROLLED_READ_TOKEN


def authorize_restricted_file_read(doc) -> None:
    doc.flags.crm_restricted_read_token = _RESTRICTED_READ_TOKEN


def protect_file_read(doc) -> None:
    if frappe.session.user == "Administrator":
        return
    # Core returns caller-supplied content before consulting file_url, so this
    # cannot expose an existing blob and keeps ordinary new File uploads usable.
    if doc.flags.get("crm_upload_token") is _UPLOAD_TOKEN or doc.get("content"):
        return
    kinds = _managed_file_kinds(doc)
    if "controlled" in kinds and doc.flags.get("crm_controlled_read_token") is not _CONTROLLED_READ_TOKEN:
        frappe.throw("Controlled document bytes are available only through the delivery service.", frappe.PermissionError)
    if "restricted" in kinds and doc.flags.get("crm_restricted_read_token") is not _RESTRICTED_READ_TOKEN:
        frappe.throw("Managed attachment bytes are available only through the delivery service.", frappe.PermissionError)
    if kinds & {"contact", "visit"} and not file_permission(
        doc, permission_type="read", _managed_kinds=kinds,
    ):
        frappe.throw("The attachment is outside the current CRM scope.", frappe.PermissionError)


def protect_file_insert(doc) -> None:
    """Called before File.before_insert can read a supplied local URL."""
    if doc.flags.get("crm_upload_token") is _UPLOAD_TOKEN:
        return
    if _crm_target(doc.attached_to_doctype) or doc.get(PROVENANCE_FIELD):
        frappe.throw("Use the CRM upload service for managed attachments.", frappe.PermissionError)
    # Core ignores content for folders and keeps their supplied reference.
    # Content only replaces an existing reference for an actual new file.
    if doc.is_folder or not doc.get("content") or doc.flags.get("copy_from_existing_file"):
        reference = canonical_local_reference(
            file_url=doc.file_url, file_name=doc.file_name, is_private=doc.is_private,
        )
        if reference and _protected_blob(url=reference):
            frappe.throw("Managed attachments cannot be copied by local reference.", frappe.PermissionError)


def protect_file_write(doc, method=None) -> None:
    """Runs before insert and before validation, including reparenting a File."""
    trusted = doc.flags.get("crm_upload_token") is _UPLOAD_TOKEN
    old = None
    if not doc.is_new() and doc.name:
        old = frappe.db.get_value("File", doc.name, list(_PROTECTED_FIELDS), as_dict=True)
    if old and not doc.is_folder and frappe.utils.cint(old.is_private) != frappe.utils.cint(doc.is_private):
        # File.validate returns early for folders. Converting an old folder or
        # unresolved row into a file cannot make its display name a disk source.
        if old.is_folder or not old.file_url:
            frappe.throw("A persisted file storage reference is required to change privacy.", frappe.ValidationError)
    managed_kinds = _managed_file_kinds(doc.name)
    managed = _crm_target(doc.attached_to_doctype) or bool(managed_kinds)
    was_managed = old and (_crm_target(old.attached_to_doctype) or bool(managed_kinds))
    if not trusted:
        if not old and (managed or doc.get(PROVENANCE_FIELD)):
            frappe.throw("Use the CRM upload service for managed attachments.", frappe.PermissionError)
        if old and (managed or was_managed or old.get(PROVENANCE_FIELD) or doc.get(PROVENANCE_FIELD)):
            if any((old.get(key) or "") != (doc.get(key) or "") for key in _PROTECTED_FIELDS):
                frappe.throw("Managed attachments can only be changed through CRM services.", frappe.PermissionError)
        if old:
            storage_changed = any((old.get(key) or "") != (doc.get(key) or "")
                for key in ("is_private", "file_url", "content_hash"))
            if storage_changed:
                # Privacy changes rewrite all same-hash File rows in core Frappe
                # without their hooks. Serialize with service uploads and check
                # current rows, including a client-supplied replacement hash.
                from rayher_crm.services.private_file_lifecycle import _lock_content
                for digest in sorted({old.content_hash, doc.content_hash} - {None, ""}):
                    _lock_content(digest)
                hash_changed = (old.content_hash or "") != (doc.content_hash or "")
                if (
                    (hash_changed and _protected_blob(content_hash=doc.content_hash))
                    or _protected_blob(url=old.file_url, content_hash=old.content_hash)
                    or _protected_blob(url=doc.file_url, content_hash=doc.content_hash)
                ):
                    frappe.throw("A shared CRM attachment cannot be rebound or made public.", frappe.PermissionError)
    if trusted and (not doc.is_private or doc.is_folder):
        frappe.throw("CRM uploads must be private files.", frappe.ValidationError)


def _parent_read_scope(doctype: str, user: str, *, for_bound_query: bool = False) -> str:
    """Retain native role/owner/User Permission/share matching in service scope.

    Raw Visit list hooks apply extra Site/Account guards that the supported
    action-owner delivery path does not use. Keep the existing business scope
    while adding Frappe's native parent match rules, without querying File.
    Bound File detail SQL needs a different percent-escape form for native rules.
    """
    from frappe.model.db_query import DatabaseQuery
    from rayher_crm.permissions.scope import conditions_for_doctype

    if not frappe.has_permission(doctype, "read", user=user):
        return "1=0"

    # Keep the CRM condition outside Frappe's native match/share expression so
    # it still bounds shared rows and retains its separate escape convention.
    class NativeScopeQuery(DatabaseQuery):
        def get_permission_query_conditions(self) -> str:
            return ""

    query = NativeScopeQuery(doctype, user=user)
    query.reference_doctype = doctype
    try:
        matched = query.build_match_conditions()
    except frappe.PermissionError:
        frappe.clear_last_message()
        return "1=0"
    # The share-only branch appends its restriction to conditions and may
    # return an empty string. Empty match must not drop that restriction.
    native_parts = [condition for condition in query.conditions if condition]
    if matched:
        native_parts.append(matched)
    if for_bound_query:
        # Frappe's native match fragments use escape(..., percent=False) for
        # unbound list SQL. The File detail query binds its name, so only those
        # fragments need percent escaping for the driver's interpolation.
        native_parts = [condition.replace("%", "%%") for condition in native_parts]
    # Native shares can widen owner/User Permission matches, but cannot widen
    # CRM's current business boundary or restore deleted Contact metadata.
    # These two CRM predicates contain only escaped CRM literals. Their default
    # percent=True form is correct for bound detail SQL; File list SQL has no
    # bound values, so it must receive the literal percent instead.
    crm_scope = conditions_for_doctype(doctype, user)
    if not for_bound_query:
        crm_scope = crm_scope.replace("%%", "%")
    parts = [*native_parts, crm_scope]
    return " AND ".join(f"({condition})" for condition in dict.fromkeys(parts))


def _contact_read_condition(user, *, for_bound_query: bool = False) -> str:
    from rayher_crm.permissions.roles import capabilities_for_user
    try:
        if "stakeholder:view" not in capabilities_for_user(user):
            return "1=0"
    except frappe.PermissionError:
        return "1=0"
    scope = _parent_read_scope("CRM Contact File", user, for_bound_query=for_bound_query)
    return (
        "`tabFile`.`is_private`=1 AND `tabFile`.`attached_to_doctype`='CRM Contact File' "
        "AND EXISTS (SELECT 1 FROM `tabCRM Contact File` "
        "WHERE `tabCRM Contact File`.`private_file`=`tabFile`.`name` "
        "AND `tabCRM Contact File`.`name`=`tabFile`.`attached_to_name` "
        f"AND ({scope}))"
    )


def _visit_read_condition(user, *, for_bound_query: bool = False) -> str:
    from rayher_crm.permissions.roles import capabilities_for_user
    try:
        if "visit:view" not in capabilities_for_user(user):
            return "1=0"
    except frappe.PermissionError:
        return "1=0"
    scope = _parent_read_scope("CRM Visit", user, for_bound_query=for_bound_query)
    return (
        "`tabFile`.`is_private`=1 AND `tabFile`.`custom_crm_service_upload`=1 "
        "AND `tabFile`.`attached_to_doctype`='CRM Visit' "
        "AND EXISTS (SELECT 1 FROM `tabCRM Visit` "
        "WHERE `tabCRM Visit`.`name`=`tabFile`.`attached_to_name` "
        f"AND ({scope}))"
    )


def file_query(user=None) -> str:
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    # Release migration inventory rejects canonical aliases before traffic
    # resumes, and File write hooks prevent creating new aliases afterwards.
    # Runtime list queries must stay bounded to indexed SQL guards instead of
    # loading and canonicalizing every File row in the application process.
    target = (
        "COALESCE(`tabFile`.`attached_to_doctype`,'')='CRM Contact File' OR EXISTS "
        "(SELECT 1 FROM `tabCRM Contact File` c WHERE c.private_file=`tabFile`.`name`)"
    )
    native_scoped = "'CRM Controlled Document', 'CRM Contact File', 'CRM Visit'"
    direct_restricted = (
        "(COALESCE(`tabFile`.`custom_crm_service_upload`,0)=1 OR EXISTS "
        "(SELECT 1 FROM `tabDocType` AS `crm_file_doctype` "
        "WHERE `crm_file_doctype`.`name`=`tabFile`.`attached_to_doctype` "
        "AND `crm_file_doctype`.`module`='Rayher CRM')) "
        f"AND COALESCE(`tabFile`.`attached_to_doctype`,'') NOT IN ({native_scoped})"
    )
    alias_restricted = (
        "EXISTS (SELECT 1 FROM `tabFile` AS `crm_managed_alias` FORCE INDEX (file_url_index) "
        "WHERE COALESCE(`tabFile`.`file_url`,'')!='' "
        "AND `crm_managed_alias`.`file_url`=`tabFile`.`file_url` AND "
        "(COALESCE(`crm_managed_alias`.`custom_crm_service_upload`,0)=1 OR EXISTS "
        "(SELECT 1 FROM `tabDocType` AS `crm_alias_doctype` "
        "WHERE `crm_alias_doctype`.`name`=`crm_managed_alias`.`attached_to_doctype` "
        "AND `crm_alias_doctype`.`module`='Rayher CRM')) "
        f"AND COALESCE(`crm_managed_alias`.`attached_to_doctype`,'') NOT IN ({native_scoped}))"
    )
    return (f"NOT ({_controlled_file_query_condition('`tabFile`')}) AND "
        f"NOT (({direct_restricted}) OR ({alias_restricted})) AND "
        f"(NOT ({target}) OR ({_contact_read_condition(user)})) AND "
        f"(COALESCE(`tabFile`.`attached_to_doctype`,'')!='CRM Visit' OR ({_visit_read_condition(user)}))")


def file_permission(doc, user=None, permission_type=None, ptype=None, _managed_kinds=None, **kwargs):
    user = user or frappe.session.user
    if user == "Administrator":
        return None
    kinds = _managed_kinds if _managed_kinds is not None else _managed_file_kinds(doc)
    if kinds & {"controlled", "restricted"}:
        return False
    scopes = []
    if "contact" in kinds:
        scopes.append(_contact_read_condition(user, for_bound_query=True))
    if "visit" in kinds:
        scopes.append(_visit_read_condition(user, for_bound_query=True))
    if not scopes:
        return None
    if (permission_type or ptype or "read") not in {"read", "select"}:
        return False
    return bool(frappe.db.sql(
        f"SELECT name FROM `tabFile` WHERE name=%s AND "
        + " AND ".join(f"({scope})" for scope in scopes),
        (doc.name,),
    ))


def protect_share(doc, method=None) -> None:
    # share.add_docshare uses ignore_permissions itself, so that flag is not an
    # exemption. These attachments follow current scope, never a durable grant.
    protected = doc.share_doctype in {"CRM Contact File", "CRM Controlled Document"}
    if doc.share_doctype == "File":
        protected = bool(_managed_file_kinds(doc.share_name))
    if protected:
        frappe.throw("Managed attachments follow current CRM access and cannot be shared separately.", frappe.PermissionError)


def contact_file_matches(file_doc, meta) -> bool:
    return bool(
        file_doc.is_private and not file_doc.is_remote_file
        and file_doc.attached_to_doctype == "CRM Contact File"
        and file_doc.attached_to_name == meta.name
        and file_doc.name == meta.private_file
    )


def reconcile_visit_files(*, apply=False, scanner=None) -> list[dict]:
    """Administrator CLI inventory; apply revalidates/scans, never deletes bytes.

    Old Visit Files do not contain trustworthy provenance. Do not infer it from
    their owner or the presence of a meeting record. Run before serving the new
    release; rejected files stay in the inventory, outside the source-file list.
    """
    if frappe.session.user != "Administrator":
        frappe.throw("Administrator is required.", frappe.PermissionError)
    from rayher_crm.services.visit_meetings import _validate_archive
    from rayher_crm.api.v1.errors import CrmApiException
    import mimetypes
    results = []
    for row in frappe.get_all("File", filters={"attached_to_doctype": "CRM Visit", PROVENANCE_FIELD: 0}, fields=["name", "attached_to_name", "file_name", "owner"]):
        owners = frappe.db.get_value(
            "CRM Visit", row.attached_to_name, ["visit_owner", "action_owner"], as_dict=True,
        ) if row.attached_to_name else None
        # A clean scan does not prove who attached the file (#78). Report the
        # uploader beside the Visit owners so an operator can reject strangers
        # before running apply=True.
        result = {
            "file": row.name, "visit": row.attached_to_name, "status": "unverified",
            "uploader": row.owner,
            "visit_owner": owners.visit_owner if owners else None,
            "action_owner": owners.action_owner if owners else None,
        }
        if apply:
            file_doc = frappe.get_doc("File", row.name)
            try:
                canonical_url = canonical_local_reference(
                    file_url=file_doc.file_url,
                    file_name=file_doc.file_name,
                    is_private=file_doc.is_private,
                )
            except (frappe.ValidationError, frappe.PermissionError, ValueError):
                frappe.clear_last_message()
                canonical_url = None
            if (
                file_doc.is_folder
                or not file_doc.is_private
                or file_doc.is_remote_file
                or not canonical_url
                or not canonical_url.startswith("/private/files/")
                or str(file_doc.file_url or "") != canonical_url
                or not frappe.db.exists("CRM Visit", row.attached_to_name)
            ):
                result["status"] = "invalid-association"
            else:
                # Scanner failures propagate: an outage must not be recorded as
                # a clean scan or quietly skip the rest of the inventory.
                try:
                    content = file_doc.get_content()
                except FileNotFoundError:
                    # A lost body belongs to this row only. It stays unverified
                    # and hidden, and the remaining rows are still scanned.
                    result["status"] = "missing-blob"
                    results.append(result)
                    continue
                content = content.encode() if isinstance(content, str) else bytes(content)
                try:
                    _validate_archive(row.file_name, mimetypes.guess_type(row.file_name)[0] or "application/octet-stream", content, scanner)
                except CrmApiException as exc:
                    if exc.retryable or exc.code != "VALIDATION_ERROR":
                        raise
                    result.update(status="rejected", code=exc.code)
                    results.append(result)
                    continue
                frappe.db.set_value("File", row.name, PROVENANCE_FIELD, 1, update_modified=False)
                result["status"] = "verified"
        results.append(result)
    return results
