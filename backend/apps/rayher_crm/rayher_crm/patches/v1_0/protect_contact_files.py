"""Idempotent, targeted Contact File ownership and legacy-share migration."""
import frappe

from rayher_crm.services.managed_file_access import (
    canonical_file_alias_inventory,
    canonical_local_file_inventory,
    invalid_local_reference_problems,
)


def inventory():
    rows = frappe.get_all("CRM Contact File", fields=["name", "contact", "private_file"])
    targets = {}
    snapshot = canonical_local_file_inventory()
    problems = invalid_local_reference_problems(snapshot)
    for row in snapshot["files"].values():
        if row.attached_to_doctype != "CRM Contact File":
            continue
        reference = row.canonical_reference
        if row.is_folder or not row.is_private or not reference or not reference.startswith("/private/files/"):
            problems.append({"file": row.name, "reason": "nonprivate-contact-file-alias"})
        elif str(row.file_url or "") != reference:
            problems.append({"file": row.name, "reason": "noncanonical-contact-file-url"})
    for row in rows:
        file = snapshot["files"].get(row.private_file)
        reference = file and file.canonical_reference
        if not file or file.is_folder or not file.is_private or not reference or not reference.startswith("/private/files/"):
            problems.append({"metadata": row.name, "reason": "missing-or-nonprivate-file"})
            continue
        if str(file.file_url or "") != reference:
            problems.append({"metadata": row.name, "reason": "noncanonical-contact-file-url"})
            continue
        association = (file.attached_to_doctype, file.attached_to_name)
        if association not in {("CRM Contact File", row.name), ("Contact", row.contact)}:
            problems.append({"metadata": row.name, "reason": "unexpected-file-association"})
            continue
        if file.name in targets:
            problems.append({"metadata": row.name, "reason": "file-referenced-by-multiple-metadata-rows"})
            continue
        targets[file.name] = row.name
    # Every canonical-equivalent alias can carry an independent access grant, including
    # historical CRM aliases with an ordinary uploader as owner. A DocType/module
    # name is not evidence of its provenance. Resolve these before migration.
    if targets:
        aliases = canonical_file_alias_inventory(
            targets, snapshot=snapshot,
        )
        problems.extend(
            {"file": name, "reason": "shared-url-outside-contact-metadata"}
            for name in aliases["aliases"]
        )
    return {"targets": targets, "problems": problems}


def execute():
    report = inventory()
    if report["problems"]:
        # The patch must not be marked applied while an uploader-owned exception
        # remains. No File ownership or share has changed at this point.
        raise RuntimeError("Contact File migration requires association review: " + frappe.as_json(report["problems"]))
    for file_name, metadata_name in report["targets"].items():
        frappe.db.set_value("File", file_name, {
            "owner": "Administrator", "attached_to_doctype": "CRM Contact File",
            "attached_to_name": metadata_name, "attached_to_field": None,
        }, update_modified=False)
    attached = frappe.get_all("File", filters={"attached_to_doctype": "CRM Contact File"}, pluck="name")
    if attached:
        # Include stale File aliases attached to this metadata so that neither an
        # old owner nor a File-level share can outlive the business association.
        frappe.db.set_value("File", {"name": ["in", attached]}, "owner", "Administrator", update_modified=False)
        frappe.db.delete("DocShare", {"share_doctype": "File", "share_name": ["in", attached]})
    frappe.db.delete("DocShare", {"share_doctype": "CRM Contact File"})
