from __future__ import annotations

import io
import zipfile

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.file_manager import save_file

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.evaluations import list_demo_workflows
from rayher_crm.services.demo_artifacts import (
    download_demo_artifact,
    insert_service_artifact,
    list_demo_artifacts,
    save_demo_artifact,
)
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.opportunity_stages import QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class CleanScanner:
    def scan(self, content: bytes) -> bool:
        return True


def docx(name: str = "demo-request.docx") -> dict:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document><body>CRM request</body></document>")
    return {"file_name": name, "mime_type": DOCX_MIME, "content": output.getvalue()}


def xlsx(name: str = "results.xlsx", *, macro: bool = False) -> dict:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
        if macro:
            archive.writestr("xl/vbaProject.bin", b"macro")
    return {"file_name": name, "mime_type": XLSX_MIME, "content": output.getvalue()}


def pptx(name: str = "manual.pptx", *, macro: bool = False) -> dict:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("ppt/presentation.xml", "<presentation />")
        if macro:
            archive.writestr("ppt/vbaProject.bin", b"macro")
    return {"file_name": name, "mime_type": PPTX_MIME, "content": output.getvalue()}


class TestDemoArtifactApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self._user("crm-artifact-manager@example.invalid", "CRM Manager")
        self.sales = self._user("crm-artifact-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-artifact-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-artifact-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._user("crm-artifact-other-engineer@example.invalid", "CRM Engineer")
        self.account = self._account("Artifact Core", self.sales)
        self.foreign_account = self._account("Artifact Foreign", self.other_sales)
        self.draft = self._request("Draft", self.account, self.sales, self.engineer)
        self.submitted = self._request("Engineer Review", self.account, self.sales, self.engineer)
        self.foreign_request = self._request(
            "Engineer Review", self.foreign_account, self.other_sales, self.other_engineer,
        )
        self.evaluation = self._evaluation(self.submitted)
        self.foreign_evaluation = self._evaluation(self.foreign_request)
        frappe.set_user(self.sales)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _account(self, name: str, owner: str) -> str:
        return frappe.get_doc({
            "doctype": "Customer", "customer_name": name, "customer_type": "Company",
            "customer_group": "CRM Customers", "territory": "CRM Territory",
            "custom_crm_owner": owner, "custom_crm_short_name": name[:8],
            "custom_crm_segment": "Frontend", "custom_crm_tier": "A",
            "custom_crm_city": "Shanghai", "custom_crm_region": "East China",
        }).insert(ignore_permissions=True).name

    def _request(self, status: str, account: str, sales: str, engineer: str):
        contact = frappe.get_doc({
            "doctype": "Contact", "first_name": f"{account} Contact", "custom_crm_owner": sales,
            "custom_crm_relationship": "Developing", "custom_crm_status": "Active",
            "custom_crm_data_quality": "Complete",
        })
        contact.append("links", {"link_doctype": "Customer", "link_name": account})
        contact.insert(ignore_permissions=True)
        previous_user = frappe.session.user
        frappe.set_user(sales)
        suffix = frappe.generate_hash(length=8)
        site = create_site(account, {
            "name": f"Artifact Site {suffix}", "city": "Shanghai", "type": "Fab",
            "process": "Frontend", "status": "量产",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account, "siteId": site["id"], "title": f"Artifact Opportunity {suffix}",
            "owner": sales, "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": 100000,
            "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": 100000, "amountCny": 100000, "qualificationConfirmed": True,
        })
        frappe.set_user(previous_user)
        request = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": account, "primary_contact": contact.name,
            "opportunity": opportunity["id"],
            "sales_owner": sales, "created_by_user": sales, "title": f"{account} Demo",
            "objective": "Detect particles", "requested_equipment": "Inspection 3000",
            "sample_type": "Si", "sample_quantity": 1, "target_date": "2026-12-20",
            "customer_expected_date": "2026-12-31", "priority": "High",
            "acceptance_criteria": "Capture above 95%", "status": status,
            "engineer_owner": engineer, "form_data": {},
        }).insert(ignore_permissions=True)
        if status != "Draft":
            frappe.get_doc({
                "doctype": "CRM Demo Request History", "demo_request": request.name,
                "at": frappe.utils.now_datetime(), "actor": sales, "from_status": "Draft",
                "to_status": "Engineer Review", "comment": "Submitted",
            }).insert(ignore_permissions=True)
        return request

    def _evaluation(self, request):
        return frappe.get_doc({
            "doctype": "CRM Evaluation", "account": request.account,
            "demo_request": request.name, "title": request.title, "status": "Requested",
            "evaluation_owner": request.engineer_owner, "planned_end": "2026-12-20",
            "acceptance": "Pending", "report_status": "Not Ready",
            "report_version": 0, "criteria": request.acceptance_criteria,
        }).insert(ignore_permissions=True)

    def _input(self, request, *, evaluation=None, artifact_type="Demo Request DOCX", visibility="Internal"):
        result = {
            "demoRequestId": request.name,
            "type": artifact_type,
            "visibility": visibility,
        }
        if evaluation:
            result["evaluationId"] = evaluation.name
        return result

    def test_generic_upload_rejects_non_request_type_customer_visibility_and_link_mismatch(self):
        upload = docx()
        with self.assertRaises(CrmApiException) as external:
            save_demo_artifact(
                self._input(self.submitted, artifact_type="External Demo Test Report PDF"),
                upload, scanner=CleanScanner(),
            )
        self.assertEqual(external.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as visibility:
            save_demo_artifact(
                self._input(self.submitted, visibility="Customer Review"),
                upload, scanner=CleanScanner(),
            )
        self.assertEqual(visibility.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as mismatch:
            save_demo_artifact(
                self._input(self.submitted, evaluation=self.foreign_evaluation),
                upload, scanner=CleanScanner(),
            )
        self.assertEqual(mismatch.exception.code, "VALIDATION_ERROR")
        self.assertEqual(
            frappe.db.count("CRM Demo Artifact", {"demo_request": self.submitted.name}),
            0,
        )

    def test_secure_upload_accepts_xlsx_csv_and_txt_but_rejects_macros_and_nul(self):
        from rayher_crm.services.file_security import validate_and_scan

        workbook = xlsx()
        self.assertEqual(
            validate_and_scan(workbook["file_name"], workbook["mime_type"], workbook["content"], CleanScanner()),
            XLSX_MIME,
        )
        self.assertEqual(validate_and_scan("results.csv", "text/csv", b"metric,value\nyield,99\n", CleanScanner()), "text/csv")
        self.assertEqual(validate_and_scan("notes.txt", "text/plain", "测试完成".encode(), CleanScanner()), "text/plain")
        with self.assertRaises(CrmApiException):
            macro_workbook = xlsx(macro=True)
            validate_and_scan(
                macro_workbook["file_name"], macro_workbook["mime_type"], macro_workbook["content"], CleanScanner(),
            )
        with self.assertRaises(CrmApiException):
            validate_and_scan("notes.txt", "text/plain", b"safe\0payload", CleanScanner())

    def test_secure_upload_accepts_plain_pptx_and_rejects_macros(self):
        from rayher_crm.services.file_security import validate_and_scan

        presentation = pptx()
        self.assertEqual(
            validate_and_scan(presentation["file_name"], presentation["mime_type"], presentation["content"], CleanScanner()),
            PPTX_MIME,
        )
        macro = pptx(macro=True)
        with self.assertRaises(CrmApiException):
            validate_and_scan(macro["file_name"], macro["mime_type"], macro["content"], CleanScanner())

    def test_secure_upload_accepts_tipray_envelope_and_scans_unchanged_bytes(self):
        from rayher_crm.services.file_security import validate_and_scan

        encrypted = b"%TSD-Header-###%" + bytes(range(64))

        class RecordingScanner:
            content = None

            def scan(self, content: bytes) -> bool:
                self.content = content
                return True

        scanner = RecordingScanner()
        actual_mime = validate_and_scan(
            "report.pdf", "application/pdf", encrypted, scanner,
        )

        self.assertEqual(actual_mime, "application/pdf")
        self.assertEqual(scanner.content, encrypted)

    def test_versions_are_server_allocated_strictly_increasing_and_files_are_private(self):
        first = save_demo_artifact(
            self._input(self.submitted, evaluation=self.evaluation),
            docx("request-v-client-99.docx"), scanner=CleanScanner(),
        )
        second = save_demo_artifact(
            self._input(self.submitted, evaluation=self.evaluation),
            docx("request-second.docx"), scanner=CleanScanner(),
        )

        self.assertEqual((first["version"], second["version"]), (1, 2))
        self.assertRegex(first["id"], r"^CRM-ART-\d{5}$")
        # Only Test/Customer Reports belong to a test round; the request form does not.
        self.assertNotIn("round", first)
        for item in (first, second):
            meta = frappe.get_doc("CRM Demo Artifact", item["id"])
            file_doc = frappe.get_doc("File", meta.private_file)
            self.assertTrue(file_doc.is_private)
            self.assertEqual(
                (file_doc.attached_to_doctype, file_doc.attached_to_name),
                ("CRM Demo Artifact", meta.name),
            )
            self.assertEqual(meta.created_by_user, self.sales)
            self.assertTrue(meta.content_hash)

    def test_draft_owner_and_submitted_roles_follow_visibility_contract(self):
        draft_upload = docx("draft.docx")
        draft = save_demo_artifact(
            self._input(self.draft), draft_upload, scanner=CleanScanner(),
        )
        submitted = save_demo_artifact(
            self._input(self.submitted), docx("submitted.docx"), scanner=CleanScanner(),
        )
        self.assertEqual(
            [item["id"] for item in list_demo_artifacts(self.draft.name)],
            [draft["id"]],
        )
        self.assertEqual(download_demo_artifact(draft["id"])["content"], draft_upload["content"])

        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException) as foreign:
            download_demo_artifact(draft["id"])
        self.assertEqual(foreign.exception.code, "SCOPE_DENIED")

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as unsubmitted:
            download_demo_artifact(draft["id"])
        self.assertEqual(unsubmitted.exception.code, "PERMISSION_DENIED")
        self.assertEqual(download_demo_artifact(submitted["id"])["file_name"], "submitted.docx")
        workflow = next(item for item in list_demo_workflows() if item["id"] == self.submitted.name)
        self.assertEqual([artifact["id"] for artifact in workflow["artifacts"]], [submitted["id"]])

        frappe.set_user(self.engineer)
        self.assertEqual(download_demo_artifact(submitted["id"])["file_name"], "submitted.docx")

    def test_download_audits_allowed_and_denied_without_exposing_raw_file_scope(self):
        item = save_demo_artifact(
            self._input(self.submitted), docx("audit.docx"), scanner=CleanScanner(),
        )
        frappe.local.flags.commit = False
        result = download_demo_artifact(item["id"])
        self.assertEqual(result["mime_type"], DOCX_MIME)
        self.assertTrue(frappe.local.flags.commit)
        self.assertEqual(
            frappe.db.count("CRM File Access Audit", {"entity_id": item["id"], "outcome": "Allowed"}),
            1,
        )

        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException) as denied:
            download_demo_artifact(item["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        self.assertEqual(
            frappe.db.count("CRM File Access Audit", {
                "entity_id": item["id"], "actor": self.other_sales, "outcome": "Denied",
            }),
            1,
        )
        meta = frappe.get_doc("CRM Demo Artifact", item["id"])
        self.assertFalse(
            frappe.has_permission("File", "read", doc=frappe.get_doc("File", meta.private_file), user=self.other_sales),
        )

    def _report_values(self, private_file: str, **overrides):
        values = {
            "demo_request": self.submitted.name, "evaluation": self.evaluation.name,
            "account": self.submitted.account, "artifact_type": "Customer Report",
            "private_file": private_file, "file_name": "[Customer] forged.pdf",
            "mime_type": "application/pdf", "size_bytes": 6, "artifact_version": 99,
            "test_round": 1, "visibility": "Customer Review",
            "content_hash": frappe.generate_hash(length=64),
            "created_by_user": self.engineer, "created_at": frappe.utils.now_datetime(),
        }
        values.update(overrides)
        return values

    def test_report_artifacts_cannot_be_created_through_the_standard_document_api(self):
        frappe.set_user("Administrator")
        file_doc = save_file("forged.txt", b"forged", "CRM Evaluation", self.evaluation.name, is_private=1)
        before = frappe.db.count("CRM Demo Artifact", {"demo_request": self.submitted.name})

        # No CRM role holds create on the DocType: posting to /api/resource/CRM Demo Artifact
        # is refused before the controller runs, for a Manager as much as for Sales.
        for user in (self.manager, self.sales):
            frappe.set_user(user)
            self.assertFalse(frappe.has_permission("CRM Demo Artifact", "create", user=user), user)
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc({"doctype": "CRM Demo Artifact", **self._report_values(file_doc.name)}).insert()

        # Code that skips permission checks still cannot create one outside an upload service.
        frappe.set_user("Administrator")
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({"doctype": "CRM Demo Artifact", **self._report_values(file_doc.name)}).insert(
                ignore_permissions=True,
            )
        self.assertEqual(frappe.db.count("CRM Demo Artifact", {"demo_request": self.submitted.name}), before)

    def test_download_refuses_a_file_owned_by_another_record(self):
        frappe.set_user("Administrator")
        foreign_file = save_file(
            "other-customer.txt", b"secret", "CRM Demo Request", self.foreign_request.name, is_private=1,
        )
        forged = insert_service_artifact(self._report_values(foreign_file.name))

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as refused:
            download_demo_artifact(forged.name)
        self.assertEqual(refused.exception.code, "PERMISSION_DENIED")
        self.assertEqual(
            frappe.db.count("CRM File Access Audit", {"entity_id": forged.name, "outcome": "Denied"}), 1,
        )

        # A file attached to the artifact's own Evaluation is still served.
        frappe.set_user("Administrator")
        own_file = save_file("own-report.txt", b"own report", "CRM Evaluation", self.evaluation.name, is_private=1)
        own = insert_service_artifact(self._report_values(own_file.name, artifact_version=100))
        frappe.set_user(self.manager)
        self.assertEqual(download_demo_artifact(own.name)["content"], b"own report")

    def test_owner_patch_covers_every_file_an_artifact_points_at(self):
        from rayher_crm.patches.v1_0.protect_demo_artifact_files import execute

        frappe.set_user("Administrator")
        # The current shape: the upload service re-points the File at its artifact.
        current = save_file("current.txt", b"current report", "CRM Evaluation", self.evaluation.name, is_private=1)
        current_artifact = insert_service_artifact(self._report_values(current.name, artifact_version=200))
        frappe.db.set_value("File", current.name, {
            "attached_to_doctype": "CRM Demo Artifact", "attached_to_name": current_artifact.name,
        }, update_modified=False)
        # The legacy shape: still attached to the Evaluation, which
        # `_file_belongs_to_artifact` keeps serving -- so it needs the same
        # treatment, and sweeping `attached_to_doctype` alone would skip it.
        legacy = save_file("legacy.txt", b"legacy report", "CRM Evaluation", self.evaluation.name, is_private=1)
        insert_service_artifact(self._report_values(legacy.name, artifact_version=201))
        unrelated = save_file("unrelated.txt", b"nothing to do with artifacts", None, None, is_private=1)
        for name in (current.name, legacy.name, unrelated.name):
            frappe.db.set_value("File", name, "owner", self.sales, update_modified=False)

        execute()
        execute()  # idempotent

        self.assertEqual(frappe.db.get_value("File", current.name, "owner"), "Administrator")
        self.assertEqual(frappe.db.get_value("File", legacy.name, "owner"), "Administrator")
        self.assertEqual(frappe.db.get_value("File", unrelated.name, "owner"), self.sales)

        # No file any artifact points at is left with an uploader owner, whichever
        # of the two accepted locations it sits in. The remaining native read path
        # goes through the attached document and is therefore scope-checked; the
        # owner shortcut this patch removes ignored scope entirely, which is why it
        # survived the uploader losing the role.
        self.assertEqual(
            frappe.db.sql(
                """SELECT file.`name` FROM `tabFile` file
                     JOIN `tabCRM Demo Artifact` artifact ON artifact.`private_file` = file.`name`
                    WHERE file.`owner` != 'Administrator'"""
            ),
            (),
        )
