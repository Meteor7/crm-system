"""Coordinate private blob reuse with deletion without locking unrelated business rows."""
from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path

import frappe
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils.image import strip_exif_data


_DELETE_TOKEN = object()


def _session_id():
    """Identify the MariaDB session, so a silent reconnect invalidates our locks.

    Frappe sets `auto_reconnect`, and pymysql reconnects in place -- the
    connection object survives, its server session does not, and with it every
    `GET_LOCK` this request believes it still holds. The server thread id is the
    one value that changes, so the lock cache is keyed on it. If a driver ever
    stops exposing it we fall back to a unique object, which only costs us a
    redundant re-acquisition.
    """
    try:
        return frappe.db._conn.thread_id()
    except Exception:
        return object()


def _lock_content(content_hash: str, *, required: bool = True) -> bool:
    """Hold the content lock for this request. `required=False` reports failure.

    Best-effort callers must not use the throwing form: `frappe.throw` pushes its
    text onto `frappe.local.message_log` before raising, so even a swallowed
    exception would tack "This attachment is being updated" onto the response of a
    request that failed for an entirely unrelated reason.
    """
    # Connection-scoped locks survive savepoint rollback and are released with the
    # outer transaction. A lost connection also releases them automatically.
    key = "crm-private:" + hashlib.sha256(f"{frappe.local.site}:{content_hash}".encode()).hexdigest()[:48]
    session = _session_id()
    cached = getattr(frappe.local, "crm_private_content_locks", None)
    if cached is None or cached[0] != session:
        cached = frappe.local.crm_private_content_locks = (session, set())
    held = cached[1]
    if key in held:
        return True
    if frappe.db.sql("SELECT GET_LOCK(%s, 5)", (key,))[0][0] != 1:
        if required:
            frappe.throw("This attachment is being updated. Please retry.")
        return False
    held.add(key)

    def release():
        if key not in held:
            return
        try:
            frappe.db.sql("SELECT RELEASE_LOCK(%s)", (key,))
        finally:
            held.discard(key)

    frappe.db.after_commit.add(release)
    frappe.db.after_rollback.add(release)
    return True


def _stored_content_hash(file_name: str, content: bytes) -> str:
    """The `content_hash` that `File.save_file` will give this upload.

    It is not always the upload's own: with the System Setting on (its default),
    Frappe first strips a JPEG's EXIF data by re-encoding it. The re-encoding is
    deterministic, so doing it here yields the stored bytes' hash. This mirrors
    Frappe 15's `File.save_file`; the Status lock-order test pins it.
    """
    if (
        mimetypes.guess_type(file_name)[0] == "image/jpeg"
        and frappe.get_system_settings("strip_exif_metadata_from_uploaded_images")
    ):
        content = strip_exif_data(content, "image/jpeg")
    return get_content_hash(content)


def lock_upload_contents(uploads: Iterable[tuple[str, bytes]]) -> None:
    """Take the content lock of every `(file_name, content)` upload up front.

    `protect_private_upload` otherwise takes them one File insert at a time, with
    the save's row locks already held. A `GET_LOCK` wait is invisible to InnoDB's
    deadlock detection, so a cycle through one of those rows -- for a ledger named
    from a `format:` series, Frappe's naming-series row that every such name
    shares -- would only end at the 5-second timeout. Callers take them before any
    row lock; in hash order, a save waiting here holds only content locks that sort
    earlier, which no other save taking them the same way can be waiting for. The
    per-insert calls then find their lock already held -- as long as it is the
    stored bytes' hash.

    The price: a second save of the same bytes on the same Opportunity now waits
    here, for at most those 5 seconds, rather than queueing on the Opportunity
    row; and when a request fails, these locks are released before a rolled-back
    File's own cleanup runs, which re-takes the lock best-effort and may leave the
    unreferenced bytes behind.

    And a rule for all other code: never take a content lock -- through a File
    insert, delete or rollback cleanup -- while holding a row a Status save waits
    for: its Opportunity or Customer, the Status record or its attachment rows. A
    Status save may hold that content lock while it waits for those rows, and the
    cycle would only end at the timeout. (Its hash-named ledger takes no
    naming-series row, which other flows do hold while they save files.)
    """
    for content_hash in sorted({_stored_content_hash(name, content) for name, content in uploads}):
        _lock_content(content_hash)


def _blob_matches_path(path: str, content_hash: str) -> bool:
    digest = hashlib.md5(usedforsecurity=False)
    try:
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except FileNotFoundError:
        # Only a missing blob is an answer. A storage failure must keep propagating
        # out of `delete_file_content`, or the File row is deleted while its bytes
        # stay behind with nothing left pointing at them.
        return False
    return digest.hexdigest() == content_hash


def _blob_matches(doc) -> bool:
    return _blob_matches_path(doc.get_full_path(), doc.content_hash)


def _reference_clause(file_url: str, exclude: str | None) -> tuple[str, tuple]:
    """Candidate File rows pointing at this path. `exclude` is the caller's own row.

    `exclude=None` means the caller has no row of its own left -- a rolled-back
    insert -- so every match counts. It is not "exclude nothing by accident": a
    deletion must always pass its own name, or it finds itself and refuses to run.
    """
    clause = "SELECT name FROM tabFile WHERE file_url=%s"
    params: tuple = (file_url,)
    if exclude is not None:
        clause += " AND name!=%s"
        params = (file_url, exclude)
    return clause, params


def _local_reference_names(file_url: str, exclude: str | None) -> set[str]:
    clause, params = _reference_clause(file_url, exclude)
    return {row[0] for row in frappe.db.sql(clause, params)}


def _committed_reference_names(file_url: str, exclude: str | None) -> set[str]:
    """References this transaction cannot see in its own snapshot.

    A separate, read-only connection sees rows committed after our REPEATABLE READ
    snapshot opened. It is opened per call on purpose: a cached connection would
    accumulate a snapshot of its own and stop being a current read. That costs a
    full connect, so callers only reach here once the cheap local read has failed
    to find a reason to keep the blob.

    `_get_connection`, `GET_LOCK` and `RELEASE_LOCK` are MariaDB/MySQL-specific;
    this module does not support the Postgres driver.
    """
    clause, params = _reference_clause(file_url, exclude)
    connection = frappe.db._get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(clause, params)
            return {row[0] for row in cursor.fetchall()}
    finally:
        connection.close()


def _confirm(names: set[str], file_url: str) -> bool:
    # A current PRIMARY-key read per candidate, which drops our own deletions, in
    # name order so concurrent deletes of one blob take row locks in one sequence.
    for name in sorted(names):
        if frappe.db.sql(
            "SELECT name FROM tabFile WHERE name=%s AND file_url=%s FOR UPDATE",
            (name, file_url),
        ):
            return True
    return False


def _has_live_reference(
    file_url: str, exclude: str | None = None, content_hash: str | None = None,
) -> bool:
    """True when some File row still points at this physical path.

    Equal content can occupy different paths after concurrent uploads, so only a
    reference to *this* path may block deletion. The File table is never scanned
    under a lock.

    Our own snapshot is consulted first and answers the common case -- a sibling
    attachment inserted in this very transaction -- without opening a second
    connection. Only when nothing local stands in the way, i.e. when we are about
    to unlink the bytes, do we pay for the current read.
    """
    if _confirm(_local_reference_names(file_url, exclude), file_url):
        return True
    if _confirm(_committed_reference_names(file_url, exclude), file_url):
        return True
    if not content_hash:
        return False

    # A supported same-site absolute URL can name the same local path with a
    # different stored string. Core's hash check treats it as shared, and the
    # row-delete override must do the same before upgrading thumbnail-only
    # cleanup to a full unlink. This locking read is current under REPEATABLE
    # READ and stays indexed; the content advisory lock prevents new candidates
    # from committing while the canonical comparison runs.
    from rayher_crm.patches.v1_0.add_file_content_hash_index import INDEX_NAME
    from rayher_crm.services.managed_file_access import canonical_local_reference

    try:
        reference = canonical_local_reference(file_url=file_url, is_private=True)
    except (frappe.ValidationError, frappe.PermissionError, ValueError):
        frappe.clear_last_message()
        return False
    if not reference:
        return False
    params: list[str] = [content_hash]
    exclude_clause = ""
    if exclude is not None:
        exclude_clause = " AND name!=%s"
        params.append(exclude)
    rows = frappe.db.sql(
        f"SELECT name, file_url, file_name, is_private FROM `tabFile` "
        f"FORCE INDEX ({INDEX_NAME}) WHERE content_hash=%s{exclude_clause} "
        "ORDER BY name FOR UPDATE",
        tuple(params),
        as_dict=True,
    )
    for row in rows:
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
            return True
    return False


def _unlink_private_file(path: str) -> None:
    root = Path(frappe.get_site_path("private", "files")).resolve()
    target = Path(path).resolve()
    if root not in target.parents or not target.is_file():
        return
    target.unlink()


def discard_rolled_back_blob(path: str | None, file_url: str | None, content_hash: str | None) -> None:
    """Remove a blob an aborted upload wrote, never one another record still owns.

    Callers run this from an ``except`` handler, after ``rollback(save_point=...)``
    has already dropped this upload's own File row. Frappe de-duplicates by content
    hash, so the path can be the physical file an *earlier* upload still points at --
    and that upload may have committed after this request opened its REPEATABLE READ
    snapshot. Checking references with ``frappe.db.exists`` on this connection would
    therefore miss it and delete a live attachment, so the check has to be the same
    current read, under the same content lock, that ``delete_file_content`` uses.

    Never raises: the caller is about to re-raise the original upload failure, and a
    leaked blob is a much smaller problem than a replaced exception or a deleted
    attachment that belongs to somebody else.
    """
    if not path:
        return
    if not file_url or not content_hash:
        # Without both we cannot prove the bytes at this path are the ones this
        # upload wrote, and an unconditional unlink is exactly the bug being fixed.
        with suppress(Exception):
            frappe.logger("rayher_crm").warning(
                "Leaving a rolled back upload blob in place: no file_url or content hash to check it against"
            )
        return
    try:
        # Blocks a concurrent insert of the same content from resolving to this path
        # while we decide. If the lock is unavailable the upload holding it owns the
        # blob, so leaving the bytes in place is the safe outcome.
        if not _lock_content(content_hash, required=False):
            return
        if _has_live_reference(file_url, content_hash=content_hash):
            return
        if not _blob_matches_path(path, content_hash):
            # The path already holds a different, newly uploaded file.
            return
        _unlink_private_file(path)
    except Exception:
        # Not even a failing logger may break the promise above.
        with suppress(Exception):
            frappe.logger("rayher_crm").exception("Could not remove a rolled back upload blob")


def protect_private_upload(doc, method=None) -> None:
    if doc.flags.get("crm_private_upload_finalized"):
        return
    from rayher_crm.services.managed_file_access import (
        canonical_local_reference,
        isolate_reused_upload_blob,
        protect_file_write,
        restore_service_file_name,
    )
    protect_file_write(doc, method)
    if not doc.is_private or doc.is_folder or not doc.content_hash:
        return
    # Core can de-duplicate a local upload onto a same-site absolute URL and
    # then report it as ``is_remote_file``. The still-present upload content
    # proves this is an upload that must pass the local alias guard.
    if doc.is_remote_file:
        local_reference = canonical_local_reference(
            file_url=doc.file_url, file_name=doc.file_name, is_private=doc.is_private,
        )
        if not local_reference or not doc.get("content"):
            return
    _lock_content(doc.content_hash)
    # Core de-duplicates globally before this doc-event. A CRM service upload
    # must never inherit a URL owned by an ordinary file or another delivery
    # boundary. The content lock makes the committed alias set stable while the
    # new independent path is written.
    isolate_reused_upload_blob(doc)
    # File.before_insert has already resolved/reused the blob. Cleanup may have
    # won the lock meanwhile: recreate uploaded bytes, or reject a stale copy.
    if not _blob_matches(doc):
        if doc.get("_content"):
            doc.save_file(content=doc._content, ignore_existing_file_check=True)
        else:
            frappe.throw("The source attachment was removed. Please upload the file again.")
    # Service storage uses a random physical basename to avoid same-name races.
    # Keep that URL while presenting and persisting the user-supplied name.
    restore_service_file_name(doc)
    doc.flags.crm_private_upload_finalized = True


def delete_file_content(doc, only_thumbnail=False) -> None:
    # Also covers Frappe's new-file rollback callback when its File row is gone.
    if not doc.is_private or doc.is_folder or doc.is_remote_file or not doc.content_hash:
        doc.delete_file_from_filesystem(only_thumbnail=only_thumbnail)
        return
    # Best-effort, like `discard_rolled_back_blob`: Frappe calls this from
    # `File.on_rollback`, from cascading deletes and from `after_migrate`
    # cleanups, none of which can absorb a throw. `frappe.throw` would also push
    # its text onto `message_log` and surface on an unrelated failed response.
    # Losing the lock means somebody is writing this content right now, so the
    # safe answer is to keep the bytes and let a later delete reclaim them.
    if not _lock_content(doc.content_hash, required=False):
        return
    # Inserts of this same content hold the advisory lock until commit/rollback,
    # so no new reference can appear between this check and the unlink below.
    if _has_live_reference(doc.file_url, doc.name, doc.content_hash):
        # The thumbnail stays too: Frappe derives its path from `file_url`, which
        # the surviving row shares, so removing it here would blank that row's
        # preview. Frappe's own `_delete_file_on_disk` makes the same trade.
        return
    # A rolled-back insert has no File row left. The framework can still ask
    # for thumbnail-only cleanup because another path has the same hash.
    # Keep genuine thumbnail-only calls intact while the File row exists.
    if only_thumbnail and doc.flags.new_file and not frappe.db.sql(
        "SELECT name FROM tabFile WHERE name=%s FOR UPDATE", (doc.name,),
    ):
        only_thumbnail = False
    # Core treats every equal content hash as a shared physical blob and asks
    # hooks to remove only the thumbnail. Service uploads can now have equal
    # hashes at independent URLs, so an explicit row deletion must remove its
    # own unreferenced body as well.
    if only_thumbnail and doc.flags.get("crm_delete_token") is _DELETE_TOKEN:
        only_thumbnail = False
    # A removed path may already belong to a different newly uploaded file.
    if _blob_matches(doc):
        doc.delete_file_from_filesystem(only_thumbnail=only_thumbnail)


def authorize_file_delete(doc) -> None:
    doc.flags.crm_delete_token = _DELETE_TOKEN


def _service_storage_name(file_name: str) -> str:
    """Return a collision-resistant physical basename, preserving its suffix."""
    path = Path(file_name)
    extension = path.suffix
    marker = "-" + frappe.generate_hash(length=32)
    # File.file_name is a 140-character Data field. Upload validators already
    # enforce the logical limit; trim only the private storage stem.
    stem = path.name[:-len(extension)] if extension else path.name
    maximum_stem = max(1, 140 - len(marker) - len(extension))
    return f"{stem[:maximum_stem]}{marker}{extension}"


def save_private_file(file_name, content, doctype, name, is_private=1, *, attached_to_field=None):
    # Keep the original bytes available if cleanup removes a deduplicated blob
    # before File.before_insert acquires the content lock.
    from rayher_crm.services.managed_file_access import authorize_service_upload
    upload_content = content.encode() if isinstance(content, str) else bytes(content)
    # Acquire this before core's global hash lookup. That lookup otherwise races
    # a delete or a second upload before the post-controller doc-event can split
    # an incompatible URL.
    _lock_content(_stored_content_hash(file_name, upload_content))
    storage_file_name = _service_storage_name(file_name)
    doc = frappe.get_doc({
        "doctype": "File", "file_name": storage_file_name, "content": upload_content,
        "attached_to_doctype": doctype, "attached_to_name": name,
        "attached_to_field": attached_to_field,
        "is_private": is_private,
    })
    authorize_service_upload(doc, upload_content, file_name)
    return doc.insert(ignore_permissions=True)
