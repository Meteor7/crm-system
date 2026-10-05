"""Fail closed before exposing legacy service-managed attachments."""

from __future__ import annotations

import frappe

from rayher_crm.services.managed_file_access import (
    PROVENANCE_FIELD,
    canonical_file_alias_inventory,
    canonical_local_file_inventory,
    invalid_local_reference_problems,
)


_NATIVE_SCOPED_DOCTYPES = {
    "CRM Contact File", "CRM Controlled Document", "CRM Visit",
}


def inventory() -> dict:
    snapshot = canonical_local_file_inventory()
    crm_doctypes = set(frappe.get_all(
        "DocType", filters={"module": "Rayher CRM"}, pluck="name",
    ))
    rows = [
        row for row in snapshot["files"].values()
        if (
            frappe.utils.cint(row.get(PROVENANCE_FIELD))
            or row.attached_to_doctype in crm_doctypes
        )
        and row.attached_to_doctype not in _NATIVE_SCOPED_DOCTYPES
    ]
    problems: list[dict[str, str]] = invalid_local_reference_problems(snapshot)
    for row in rows:
        reference = row.canonical_reference
        if (
            row.reference_error
            or row.is_folder
            or not row.is_private
            or not reference
            or not reference.startswith("/private/files/")
        ):
            problems.append({"file": row.name, "reason": "nonprivate-or-remote-service-file"})
        elif str(row.file_url or "") != reference:
            problems.append({"file": row.name, "reason": "noncanonical-service-file-url"})
        if not row.attached_to_doctype or not row.attached_to_name:
            problems.append({"file": row.name, "reason": "missing-service-association"})
        elif not frappe.db.exists(row.attached_to_doctype, row.attached_to_name):
            problems.append({"file": row.name, "reason": "missing-service-parent"})

    target_names = sorted(row.name for row in rows)
    if target_names:
        aliases = canonical_file_alias_inventory(target_names, snapshot=snapshot)
        problems.extend(
            {"file": name, "reason": "shared-url-outside-service-file"}
            for name in aliases["aliases"]
        )
    problems.sort(key=lambda row: (row["reason"], row["file"]))
    return {"files": target_names, "problems": problems}


def execute() -> None:
    report = inventory()
    if report["problems"]:
        # Public URLs bypass Python, and an ambiguous alias can carry an
        # independent owner or share. Traffic stays paused until an operator
        # resolves those rows from the release backup.
        raise RuntimeError(
            "Service-managed File migration requires storage review: "
            + frappe.as_json(report["problems"])
        )
    if report["files"]:
        frappe.db.set_value(
            "File", {"name": ("in", report["files"])},
            "owner", "Administrator", update_modified=False,
        )
        frappe.db.delete(
            "DocShare", {"share_doctype": "File", "share_name": ("in", report["files"])},
        )
