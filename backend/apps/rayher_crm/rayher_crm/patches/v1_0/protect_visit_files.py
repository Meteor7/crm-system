"""Keep legacy Visit files private; provenance is granted only by a real rescan."""
import frappe

from rayher_crm.services.managed_file_access import (
    canonical_file_alias_inventory,
    canonical_local_file_inventory,
    invalid_local_reference_problems,
)


def inventory():
    snapshot = canonical_local_file_inventory()
    rows = [
        row for row in snapshot["files"].values()
        if row.attached_to_doctype == "CRM Visit"
    ]
    problems = invalid_local_reference_problems(snapshot)
    for row in rows:
        reference = row.canonical_reference
        if row.is_folder or not row.is_private or not reference or not reference.startswith("/private/files/"):
            problems.append({"file": row.name, "reason": "nonprivate-or-remote-visit-file"})
        elif str(row.file_url or "") != reference:
            problems.append({"file": row.name, "reason": "noncanonical-visit-file-url"})
        if not row.attached_to_name or not frappe.db.exists("CRM Visit", row.attached_to_name):
            problems.append({"file": row.name, "reason": "missing-visit-parent"})

    target_names = [row.name for row in rows]
    aliases = canonical_file_alias_inventory(target_names, snapshot=snapshot)
    problems.extend(
        {"file": name, "reason": "shared-url-outside-visit-file"}
        for name in aliases["aliases"]
    )
    problems.sort(key=lambda row: (row["reason"], row["file"]))
    return {"files": sorted(target_names), "problems": problems}


def execute():
    report = inventory()
    if report["problems"]:
        # Public URLs are served without Python permission checks. An operator
        # must resolve them before migration may complete or traffic resume.
        raise RuntimeError("Visit File migration requires storage review: " + frappe.as_json(report["problems"]))
    if report["files"]:
        frappe.db.delete("DocShare", {"share_doctype": "File", "share_name": ["in", report["files"]]})
