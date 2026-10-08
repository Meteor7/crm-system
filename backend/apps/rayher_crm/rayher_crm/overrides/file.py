"""Guard references before Frappe reads bytes, and the native download route."""
import re
import shutil
from pathlib import Path

import frappe
from frappe.core.doctype.file.file import File

from rayher_crm.services.managed_file_access import (
    _managed_file_kinds,
    file_permission,
    protect_file_insert,
    protect_file_read,
)


class ManagedFile(File):
    def before_insert(self):
        # A doc_event runs after File.before_insert, when reference-only copies
        # already have content. Preserve the distinction at the controller edge.
        protect_file_insert(self)
        super().before_insert()
        # Run the post-core guard here as well as keeping the registered hook.
        # This location is unambiguously after core's hash de-duplication and
        # validate_duplicate_entry URL rewrite; the hook call that follows is
        # idempotently skipped through the document flag.
        from rayher_crm.services.private_file_lifecycle import protect_private_upload
        protect_private_upload(self)

    def get_content(self):
        # Several core helpers read File bytes after using the module-level
        # owner/attachment shortcut instead of the app permission hook. Keep
        # controlled sources behind their audited delivery service even there.
        protect_file_read(self)
        return super().get_content()

    def save_file_on_filesystem(self):
        result = super().save_file_on_filesystem()
        from rayher_crm.services.managed_file_access import record_new_private_body
        record_new_private_body(self)
        return result

    @frappe.whitelist()
    def optimize_file(self):
        try:
            self._validate_native_optimization()
        except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
            # Desk may already hold this File row before invoking the method.
            # All guarded locking finishes before core can rewrite any bytes.
            frappe.throw("The file is busy. Please retry optimization.", frappe.ValidationError)
        return super().optimize_file()

    def _validate_native_optimization(self):
        # Core rewrites the blob at /private/files/<file_name> with
        # save_file(overwrite=True). Service uploads present their logical name
        # while their bytes live under a random basename, so that path belongs
        # to another file; managed bytes are never rewritten in place.
        if _managed_file_kinds(self):
            frappe.throw("Managed attachments cannot be optimized in place.", frappe.PermissionError)
        from rayher_crm.services.managed_file_access import _protected_blob, canonical_local_reference
        from rayher_crm.services.private_file_lifecycle import _lock_content

        fields = ("name", "file_url", "file_name", "is_private", "is_folder", "content_hash")
        snapshot = frappe.db.get_value("File", self.name, fields, as_dict=True)
        if not snapshot or snapshot.is_folder or not snapshot.file_url:
            frappe.throw("A persisted file storage reference is required to optimize a file.", frappe.ValidationError)
        reference = canonical_local_reference(file_url=snapshot.file_url, is_private=snapshot.is_private)
        if not reference:
            frappe.throw("Native file optimization requires persisted local storage.", frappe.PermissionError)
        # Serialize equal-content optimizers before this method takes more rows.
        # A legacy row without a hash can still use its canonical URL as a key.
        _lock_content(snapshot.content_hash or f"native-file-url:{reference}")
        # An earlier in-place optimization can leave aliases with different
        # hashes. Desk can already hold its own row, so do not wait on siblings.
        frappe.db.sql(
            "SELECT name FROM `tabFile` FORCE INDEX (file_url_index) "
            "WHERE file_url=%s ORDER BY name FOR UPDATE NOWAIT",
            (snapshot.file_url,),
        )
        rows = frappe.db.sql(
            "SELECT name, file_url, file_name, is_private, is_folder, content_hash "
            "FROM `tabFile` FORCE INDEX (PRIMARY) WHERE name=%s FOR UPDATE NOWAIT",
            (self.name,), as_dict=True,
        )
        if not rows or rows[0].is_folder or not rows[0].file_url:
            frappe.throw("A persisted file storage reference is required to optimize a file.", frappe.ValidationError)
        stored = rows[0]
        if any(stored.get(field) != snapshot.get(field) for field in fields):
            frappe.throw("The file changed while preparing optimization. Please retry.")
        reference = canonical_local_reference(file_url=stored.file_url, is_private=stored.is_private)
        # Incoming folder/remote flags are never permission to invoke core's
        # optimizer. Every delegation requires a verified persisted local storage path.
        if not reference:
            frappe.throw("Native file optimization requires persisted local storage.", frappe.PermissionError)
        if frappe.utils.cint(self.is_folder):
            frappe.throw("Folders cannot be optimized.", frappe.PermissionError)
        incoming_reference = canonical_local_reference(file_url=self.file_url, is_private=self.is_private)
        # Deduplicated ordinary uploads can retain a different filename from
        # their shared URL. Core writes that persisted filename when optimizing;
        # validate the incoming name and both paths before delegating.
        safe_file_name = re.sub(r"[/\\%?#]", "_", stored.file_name)
        target = f"/{'private/' if self.is_private else ''}files/{safe_file_name}"
        if (
            incoming_reference != reference or self.file_name != stored.file_name
            or frappe.utils.cint(self.is_private) != frappe.utils.cint(stored.is_private)
        ):
            frappe.throw("File optimization must use its persisted storage path.", frappe.PermissionError)
        if _protected_blob(url=reference, content_hash=stored.content_hash) or (
            target != reference and _protected_blob(url=target)
        ):
            frappe.throw("Managed attachments cannot be optimized in place.", frappe.PermissionError)

    def on_trash(self):
        # Tell the filesystem hook this is a real File-row deletion. Core only
        # passes ``only_thumbnail=True`` when another row has the same hash,
        # even when that row owns a different physical URL.
        from rayher_crm.services.private_file_lifecycle import authorize_file_delete
        authorize_file_delete(self)
        return super().on_trash()

    def handle_is_private_changed(self):
        """Move only File rows that resolve to this physical path.

        Core updates every equal content hash. Managed service uploads keep
        equal content at independent paths, so that would rebind protected rows
        while moving only this File's bytes.
        """
        from rayher_crm.services.managed_file_access import (
            _ordinary_private_crm_attachment,
            _protected_blob,
            canonical_local_reference,
            lock_canonical_file_siblings,
            protect_file_write,
        )

        protect_file_write(self)
        stored_rows = frappe.db.sql(
            "SELECT name, file_url, file_name, is_private, is_folder, content_hash "
            "FROM `tabFile` FORCE INDEX (PRIMARY) WHERE name=%s FOR UPDATE",
            (self.name,),
            as_dict=True,
        )
        if not stored_rows or stored_rows[0].is_folder or self.is_folder or not stored_rows[0].file_url:
            frappe.throw("A persisted file storage reference is required to change privacy.", frappe.ValidationError)
        stored = stored_rows[0]
        if self.is_remote_file:
            return

        # The incoming display name/privacy never selects a disk source. Core
        # accepts filename fallbacks, but a row without a persisted URL does not
        # establish ownership of that path and cannot use this mover.
        reference, siblings = lock_canonical_file_siblings(stored)
        old_private = frappe.utils.cint(stored.is_private)
        old_prefix = "/private/files/" if old_private else "/files/"
        if not reference or not reference.startswith(old_prefix):
            frappe.throw("The persisted file storage reference requires administrator review.", frappe.ValidationError)
        incoming_reference = canonical_local_reference(
            file_url=self.file_url, is_private=stored.is_private,
        )
        if incoming_reference != reference:
            frappe.throw("A file storage reference cannot change together with privacy.", frappe.ValidationError)
        new_private = frappe.utils.cint(self.is_private)
        if new_private == old_private:
            return

        relative_path = reference[len(old_prefix):]
        new_prefix = "/private/files/" if new_private else "/files/"
        updated_file_url = new_prefix + relative_path
        if _protected_blob(url=reference, content_hash=stored.content_hash) or _protected_blob(url=updated_file_url):
            frappe.throw("A managed attachment cannot be moved through a native privacy change.", frappe.PermissionError)
        if new_private:
            # The bulk sibling UPDATE below bypasses each sibling's save hooks.
            # Revoke its formerly-public CRM grants under the same File locks,
            # and serialize Address/Customer promotions before moving any bytes.
            restricted = [
                row.name for row in siblings
                if _ordinary_private_crm_attachment(frappe._dict(row, is_private=1))
            ]
            if restricted:
                frappe.db.delete("DocShare", {"share_doctype": "File", "share_name": ("in", restricted)})
        old_file_url = stored.file_url
        source = Path(frappe.get_site_path(
            "private" if old_private else "public", "files", *relative_path.split("/"),
        ))
        target = Path(frappe.get_site_path(
            "private" if new_private else "public", "files", *relative_path.split("/"),
        ))
        if not source.exists():
            frappe.throw(f"Cannot find file {source} on disk", exc=FileNotFoundError)
        if target.exists():
            frappe.throw(f"A file with same name {target} already exists", exc=FileExistsError)

        shutil.move(source, target)
        self.file_url = updated_file_url

        def restore_path_after_rollback():
            # An existing File row is back at its old database values after the
            # rollback, so its bytes must follow that restored URL. Deriving the
            # destination from the row also makes repeated privacy changes in
            # one transaction idempotent regardless of callback order.
            restored = frappe.db.get_value(
                "File", self.name, ["file_url", "is_private"], as_dict=True,
            )
            if restored:
                expected_reference = canonical_local_reference(
                    file_url=restored.file_url,
                    is_private=restored.is_private,
                )
                if expected_reference not in {reference, updated_file_url}:
                    return
                expected_private = expected_reference.startswith("/private/files/")
                expected_prefix = "/private/files/" if expected_private else "/files/"
                expected_path = Path(frappe.get_site_path(
                    "private" if expected_private else "public", "files",
                    *expected_reference[len(expected_prefix):].split("/"),
                ))
                if expected_path.exists():
                    return
                for current_path in (target, source):
                    if current_path != expected_path and current_path.exists():
                        shutil.move(current_path, expected_path)
                        return
                return
            # A File created and privacy-changed in one transaction has no
            # restored row; its insert callbacks may already have removed the
            # paths, and orphan cleanup is safe and idempotent if they did not.
            from rayher_crm.services.private_file_lifecycle import discard_rolled_back_blob
            for orphan_path, orphan_url in ((target, updated_file_url), (source, old_file_url)):
                discard_rolled_back_blob(str(orphan_path), orphan_url, stored.content_hash)

        frappe.db.after_rollback.add(restore_path_after_rollback)

        sibling_names = sorted(row.name for row in siblings if row.name != self.name)
        if sibling_names:
            placeholders = ", ".join(["%s"] * len(sibling_names))
            frappe.db.sql(
                f"UPDATE `tabFile` SET `file_url`=%s, `is_private`=%s "
                f"WHERE `name` IN ({placeholders})",
                (updated_file_url, frappe.utils.cint(self.is_private), *sibling_names),
            )

        if (
            self.attached_to_doctype and self.attached_to_name
            and self.fetch_attached_to_field(old_file_url)
        ):
            if frappe.get_meta(self.attached_to_doctype).issingle:
                frappe.db.set_single_value(
                    self.attached_to_doctype, self.attached_to_field, self.file_url,
                )
            else:
                frappe.db.set_value(
                    self.attached_to_doctype, self.attached_to_name,
                    self.attached_to_field, self.file_url,
                )

    def has_permission(self, permtype="read", *, debug=False, user=None):
        # Document.has_permission would otherwise let an old DocShare restore
        # access after the app controller has denied it. This class boundary is
        # used by native detail endpoints and runs after that share fallback.
        # flags.ignore_permissions is deliberately not honoured for managed
        # rows: core sets it for clients after a parent-level check only
        # (attach_file, file_manager.remove_file). CRM services change managed
        # rows with db.set_value or the upload token instead.
        user = user or frappe.session.user
        if user != "Administrator":
            kinds = _managed_file_kinds(self)
            if kinds & {"controlled", "restricted"}:
                return False
            permitted = file_permission(
                self, user=user, permission_type=permtype, _managed_kinds=kinds,
            )
            if permitted is False:
                return False
        return super().has_permission(permtype, debug=debug, user=user)

    def is_downloadable(self):
        # Frappe's private-URL handler calls this directly, bypassing app-level
        # has_permission hooks and otherwise accepting the original uploader.
        kinds = (
            _managed_file_kinds(self, _native_download=True)
            if frappe.session.user != "Administrator" else None
        )
        permitted = file_permission(self, permission_type="read", _managed_kinds=kinds)
        return permitted if permitted is not None else super().is_downloadable()
