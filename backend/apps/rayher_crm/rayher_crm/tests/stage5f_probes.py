"""Explicit Stage 5F integration probes executed with ``bench execute``."""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor

import frappe

from rayher_crm.services.demo_artifacts import download_demo_artifact, save_demo_artifact
from rayher_crm.services.file_security import DOCX_MIME


class _CleanScanner:
    def scan(self, content: bytes) -> bool:
        return True


def _docx_bytes(label: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", f"<document><body>{label}</body></document>")
    return output.getvalue()


def run_demo_artifact_concurrency_probe(workers: int = 4, retain: bool = False) -> dict[str, object]:
    """Prove parent-row serialization using independent connections and exact cleanup."""

    if workers != 4:
        raise ValueError("The frozen concurrency probe requires exactly four workers.")
    site = frappe.local.site
    original_user = frappe.session.user
    suffix = frappe.generate_hash(length=10)
    sales = f"crm-artifact-probe-{suffix}@example.invalid"
    created_users: list[str] = []
    artifact_ids: list[str] = []
    private_file_ids: list[str] = []
    account_id = contact_id = request_id = None
    succeeded = False

    try:
        frappe.set_user("Administrator")
        frappe.get_doc({
            "doctype": "User", "email": sales, "first_name": "Artifact Probe Sales",
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "CRM Sales"}],
        }).insert(ignore_permissions=True)
        created_users.append(sales)
        account = frappe.get_doc({
            "doctype": "Customer", "customer_name": f"Artifact Probe {suffix}",
            "customer_type": "Company", "customer_group": "CRM Customers",
            "territory": "CRM Territory", "custom_crm_owner": sales,
            "custom_crm_short_name": suffix[:8], "custom_crm_segment": "Frontend",
            "custom_crm_tier": "A", "custom_crm_city": "Shanghai",
            "custom_crm_region": "East China",
        }).insert(ignore_permissions=True)
        account_id = account.name
        contact = frappe.get_doc({
            "doctype": "Contact", "first_name": f"Artifact Probe {suffix}",
            "custom_crm_owner": sales, "custom_crm_relationship": "Developing",
            "custom_crm_status": "Active", "custom_crm_data_quality": "Complete",
        })
        contact.append("links", {"link_doctype": "Customer", "link_name": account.name})
        contact.insert(ignore_permissions=True)
        contact_id = contact.name
        request = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": account.name,
            "primary_contact": contact.name, "sales_owner": sales, "created_by_user": sales,
            "title": f"Artifact Probe {suffix}", "objective": "Concurrency",
            "requested_equipment": "Inspection 3000", "sample_type": "Si",
            "sample_quantity": 1, "target_date": "2026-12-20",
            "customer_expected_date": "2026-12-31", "priority": "High",
            "acceptance_criteria": "Versions 1 through 4", "status": "Draft",
            "engineer_owner": "Administrator", "form_data": {},
        }).insert(ignore_permissions=True)
        request_id = request.name
        frappe.db.commit()

        def upload(index: int) -> tuple[str, int]:
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user(sales)
                content = _docx_bytes(f"worker-{index}")
                result = save_demo_artifact(
                    {
                        "demoRequestId": request_id,
                        "type": "Demo Request DOCX",
                        "visibility": "Internal",
                    },
                    {
                        "file_name": f"worker-{index}.docx",
                        "mime_type": DOCX_MIME,
                        "content": content,
                    },
                    scanner=_CleanScanner(),
                )
                frappe.db.commit()
                return result["id"], result["version"]
            except Exception:
                frappe.db.rollback()
                raise
            finally:
                frappe.destroy()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(upload, range(workers)))
        artifact_ids.extend(item[0] for item in results)
        versions = sorted(item[1] for item in results)
        if versions != [1, 2, 3, 4] or len(set(artifact_ids)) != workers:
            raise AssertionError(f"Unexpected concurrent Artifact allocation: versions={versions}")
        rows = frappe.get_all(
            "CRM Demo Artifact", filters={"name": ["in", artifact_ids]},
            fields=["name", "private_file"], ignore_permissions=True,
        )
        private_file_ids.extend(row.private_file for row in rows)
        if len(rows) != workers:
            raise AssertionError("Concurrent Artifact persistence count mismatch.")
        succeeded = True
        return {
            "workers": workers, "versions": versions,
            "uniqueArtifacts": len(set(artifact_ids)), "retained": retain,
        }
    finally:
        if not (retain and succeeded):
            frappe.set_user("Administrator")
            for artifact_id in artifact_ids:
                if frappe.db.exists("CRM Demo Artifact", artifact_id):
                    private_file = frappe.db.get_value("CRM Demo Artifact", artifact_id, "private_file")
                    if private_file and private_file not in private_file_ids:
                        private_file_ids.append(private_file)
                    frappe.db.delete("CRM Demo Artifact", {"name": artifact_id})
            for private_file in private_file_ids:
                if frappe.db.exists("File", private_file):
                    frappe.delete_doc("File", private_file, ignore_permissions=True, force=True)
            if request_id and frappe.db.exists("CRM Demo Request", request_id):
                frappe.delete_doc("CRM Demo Request", request_id, ignore_permissions=True, force=True)
            if contact_id and frappe.db.exists("Contact", contact_id):
                frappe.delete_doc("Contact", contact_id, ignore_permissions=True, force=True)
            if account_id and frappe.db.exists("Customer", account_id):
                frappe.delete_doc("Customer", account_id, ignore_permissions=True, force=True)
            for user in created_users:
                if frappe.db.exists("User", user):
                    frappe.delete_doc("User", user, ignore_permissions=True, force=True)
            frappe.db.commit()
        frappe.set_user(original_user)


def cleanup_demo_artifact_probe_rows() -> dict[str, int]:
    """Remove only residue carrying the reserved Stage 5F probe identity prefix."""

    frappe.set_user("Administrator")
    artifacts = frappe.get_all(
        "CRM Demo Artifact",
        filters={"created_by_user": ["like", "crm-artifact-probe-%@example.invalid"]},
        fields=["name", "private_file"],
        ignore_permissions=True,
    )
    for row in artifacts:
        frappe.db.delete("CRM Demo Artifact", {"name": row.name})
        if row.private_file and frappe.db.exists("File", row.private_file):
            frappe.delete_doc("File", row.private_file, ignore_permissions=True, force=True)
    requests = frappe.get_all(
        "CRM Demo Request", filters={"title": ["like", "Artifact Probe %"]},
        pluck="name", ignore_permissions=True,
    )
    for request_id in requests:
        frappe.db.delete("CRM Demo Request History", {"demo_request": request_id})
        frappe.delete_doc("CRM Demo Request", request_id, ignore_permissions=True, force=True)
    contacts = frappe.get_all(
        "Contact", filters={"first_name": ["like", "Artifact Probe %"]},
        pluck="name", ignore_permissions=True,
    )
    for contact_id in contacts:
        frappe.delete_doc("Contact", contact_id, ignore_permissions=True, force=True)
    accounts = frappe.get_all(
        "Customer", filters={"customer_name": ["like", "Artifact Probe %"]},
        pluck="name", ignore_permissions=True,
    )
    for account_id in accounts:
        frappe.delete_doc("Customer", account_id, ignore_permissions=True, force=True)
    users = frappe.get_all(
        "User", filters={"name": ["like", "crm-artifact-probe-%@example.invalid"]},
        pluck="name", ignore_permissions=True,
    )
    for user in users:
        frappe.delete_doc("User", user, ignore_permissions=True, force=True)
    frappe.db.commit()
    return {
        "artifacts": len(artifacts), "requests": len(requests),
        "contacts": len(contacts), "accounts": len(accounts), "users": len(users),
    }


def create_demo_artifact_persistence_probe() -> dict[str, object]:
    """Create committed probe artifacts for verification by a fresh app container."""

    cleanup_demo_artifact_probe_rows()
    return run_demo_artifact_concurrency_probe(retain=True)


def verify_and_cleanup_demo_artifact_persistence_probe() -> dict[str, object]:
    """Read retained private bytes in a new process, then clean the reserved rows."""

    rows = frappe.get_all(
        "CRM Demo Artifact",
        filters={"created_by_user": ["like", "crm-artifact-probe-%@example.invalid"]},
        fields=["name", "private_file", "created_by_user"],
        order_by="artifact_version asc",
        ignore_permissions=True,
    )
    if len(rows) != 4 or len({row.created_by_user for row in rows}) != 1:
        cleanup_demo_artifact_probe_rows()
        raise AssertionError(f"Persistence probe expected 4 Artifacts, found {len(rows)}.")
    try:
        frappe.set_user(rows[0].created_by_user)
        sizes = []
        for row in rows:
            file_doc = frappe.get_doc("File", row.private_file)
            if not file_doc.is_private or file_doc.attached_to_name != row.name:
                raise AssertionError("Persisted private File binding mismatch.")
            item = download_demo_artifact(row.name)
            with zipfile.ZipFile(io.BytesIO(item["content"])) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise AssertionError("Persisted DOCX content is invalid.")
            sizes.append(len(item["content"]))
        frappe.db.commit()
        return {"artifacts": len(rows), "privateFiles": len(sizes), "allNonEmpty": all(sizes)}
    finally:
        cleanup_demo_artifact_probe_rows()
