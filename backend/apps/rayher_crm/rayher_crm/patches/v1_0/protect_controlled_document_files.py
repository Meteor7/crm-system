"""Fail-closed inventory and legacy-share cleanup for controlled sources."""

from __future__ import annotations

import frappe

from rayher_crm.services.managed_file_access import (
    canonical_file_alias_inventory,
    canonical_local_file_inventory,
    invalid_local_reference_problems,
)


def inventory() -> dict:
    targets: dict[str, set[str]] = {}
    seen_problems: set[tuple[str, str, str]] = set()
    snapshot = canonical_local_file_inventory()
    problems: list[dict[str, str]] = invalid_local_reference_problems(snapshot)

    def problem(*, reason: str, document: str = "", file: str = "") -> None:
        key = (reason, document, file)
        if key in seen_problems:
            return
        seen_problems.add(key)
        row = {"reason": reason}
        if document:
            row["document"] = document
        if file:
            row["file"] = file
        problems.append(row)

    documents = frappe.get_all(
        "CRM Controlled Document", fields=["name", "private_file", "preview_file"], order_by="name",
    )
    for document in documents:
        if not document.private_file:
            problem(reason="missing-private-file", document=document.name)
        for field_name in ("private_file", "preview_file"):
            file_name = document.get(field_name)
            if not file_name:
                continue
            file = snapshot["files"].get(file_name)
            if not file:
                problem(reason=f"missing-{field_name.replace('_', '-')}", document=document.name, file=file_name)
                continue
            canonical_url = file.canonical_reference
            if file.is_folder or not file.is_private or not canonical_url or not canonical_url.startswith("/private/files/"):
                problem(reason="nonprivate-or-nonlocal-controlled-file", document=document.name, file=file.name)
            elif canonical_url != file.file_url:
                problem(reason="noncanonical-controlled-file-url", document=document.name, file=file.name)
            if (file.attached_to_doctype, file.attached_to_name) != ("CRM Controlled Document", document.name):
                problem(reason="unexpected-controlled-file-association", document=document.name, file=file.name)
            targets.setdefault(file.name, set()).add(document.name)

    for file_name, parents in targets.items():
        if len(parents) > 1:
            problem(reason="file-referenced-by-multiple-controlled-documents", file=file_name)

    for file in snapshot["files"].values():
        if file.attached_to_doctype != "CRM Controlled Document":
            continue
        if file.name not in targets:
            problem(reason="attached-file-not-canonical", document=file.attached_to_name or "", file=file.name)

    target_names = sorted(targets)
    if target_names:
        aliases = canonical_file_alias_inventory(
            target_names, snapshot=snapshot,
        )
        for alias in aliases["aliases"]:
            problem(reason="shared-url-outside-controlled-document", file=alias)

    problems.sort(key=lambda row: (row["reason"], row.get("document", ""), row.get("file", "")))
    return {"targets": target_names, "problems": problems}


def execute() -> None:
    report = inventory()
    if report["problems"]:
        # Inventory is deliberately complete before the first mutation. A
        # same-URL alias or broken parent must be reviewed, never partly fixed.
        raise RuntimeError(
            "Controlled Document File migration requires association review: "
            + frappe.as_json(report["problems"])
        )
    if report["targets"]:
        frappe.db.set_value(
            "File", {"name": ["in", report["targets"]]}, "owner", "Administrator", update_modified=False,
        )
        frappe.db.delete(
            "DocShare", {"share_doctype": "File", "share_name": ["in", report["targets"]]},
        )
    frappe.db.delete("DocShare", {"share_doctype": "CRM Controlled Document"})
