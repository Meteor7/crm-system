from __future__ import annotations

import os

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.demo_artifacts import download_demo_artifact, insert_service_artifact
from rayher_crm.services.demo_reports import release_demo_test_report, upload_customer_report
from rayher_crm.services.evaluations import (
    add_evaluation_run,
    get_evaluation,
    update_evaluation_status,
)
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.opportunity_stages import DEMO_DONE, QUALIFIED_OPPORTUNITY
from rayher_crm.services.private_file_lifecycle import save_private_file
from rayher_crm.services.sites import create_site


def report_pair(file_name: str, mime_type: str, content: bytes):
    return (
        {"file_name": file_name, "mime_type": mime_type, "content": content},
        {"file_name": f"customer-{file_name}", "mime_type": mime_type, "content": content},
    )


class TestDemoReportApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self._user("crm-report-manager@example.invalid", "CRM Manager")
        self.sales = self._user("crm-report-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-report-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-report-engineer@example.invalid", "CRM Engineer")
        self.account, self.request, self.evaluation = self._source("Core")

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

    def _source(self, suffix: str):
        frappe.set_user("Administrator")
        unique = frappe.generate_hash(length=8)
        account = frappe.get_doc({
            "doctype": "Customer", "customer_name": f"Report {suffix} {unique}",
            "customer_type": "Company", "customer_group": "CRM Customers",
            "territory": "CRM Territory", "custom_crm_owner": self.sales,
            "custom_crm_short_name": unique, "custom_crm_segment": "Frontend",
            "custom_crm_tier": "A", "custom_crm_city": "Shanghai",
            "custom_crm_region": "East China",
        }).insert(ignore_permissions=True)
        contact = frappe.get_doc({
            "doctype": "Contact", "first_name": f"Report {suffix} Contact {unique}",
            "custom_crm_owner": self.sales, "custom_crm_relationship": "Developing",
            "custom_crm_status": "Active", "custom_crm_data_quality": "Complete",
        })
        contact.append("links", {"link_doctype": "Customer", "link_name": account.name})
        contact.insert(ignore_permissions=True)
        frappe.set_user(self.sales)
        site = create_site(account.name, {
            "name": f"Report Site {unique}", "city": "Shanghai", "type": "Fab",
            "process": "Frontend", "status": "量产",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account.name, "siteId": site["id"],
            "title": f"Report Opportunity {unique}", "owner": self.sales,
            "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": 100000,
            "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": 100000, "amountCny": 100000, "qualificationConfirmed": True,
        })
        frappe.set_user("Administrator")
        request = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": account.name,
            "primary_contact": contact.name, "opportunity": opportunity["id"], "sales_owner": self.sales,
            "created_by_user": self.sales, "title": f"Report {suffix} Particle Demo {unique}",
            "objective": "Detect canonical particles", "requested_equipment": "Inspection 3000",
            "sample_type": "Si", "sample_quantity": 2, "target_date": "2026-12-20",
            "customer_expected_date": "2026-12-31", "priority": "High",
            "acceptance_criteria": "Capture above 95%", "status": "Converted",
            "engineer_owner": self.engineer, "form_data": {},
            "tracking": {},
        }).insert(ignore_permissions=True)
        frappe.get_doc({
            "doctype": "CRM Demo Request History", "demo_request": request.name,
            "at": frappe.utils.now_datetime(), "actor": self.sales,
            "from_status": "Draft", "to_status": "Engineer Review", "comment": "Submitted",
        }).insert(ignore_permissions=True)
        evaluation = frappe.get_doc({
            "doctype": "CRM Evaluation", "account": account.name,
            "demo_request": request.name, "title": request.title, "status": "Requested",
            "evaluation_owner": self.engineer, "planned_end": "2026-12-20",
            "test_run_deadline": "2026-12-15", "acceptance": "Pending",
            "report_status": "Not Ready",
            "report_version": 0, "criteria": request.acceptance_criteria,
        }).insert(ignore_permissions=True)
        request.evaluation = evaluation.name
        request.save(ignore_permissions=True)
        return account, request, evaluation

    def _ready_for_upload(self, evaluation_id: str):
        frappe.set_user(self.engineer)
        evaluation = get_evaluation(evaluation_id)
        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            evaluation = update_evaluation_status(evaluation_id, {"status": status}, evaluation["modified"])
        return evaluation

    def _legacy_report(self, evaluation, version: int):
        content = b"legacy external report"
        file_doc = save_private_file(
            f"legacy-{version}.txt", content, "CRM Evaluation", evaluation.name,
        )
        artifact = insert_service_artifact({
            "demo_request": evaluation.demo_request,
            "evaluation": evaluation.name,
            "account": evaluation.account,
            "artifact_type": "Test Report",
            "private_file": file_doc.name,
            "file_name": f"legacy-{version}.pdf",
            "mime_type": "application/pdf",
            "size_bytes": len(content),
            "artifact_version": version,
            "visibility": "Customer Review",
            "content_hash": frappe.generate_hash(length=64),
            "created_by_user": self.manager,
            "created_at": frappe.utils.now_datetime(),
        })
        frappe.db.set_value(
            "CRM Demo Artifact", artifact.name,
            "artifact_type", "External Demo Test Report PDF", update_modified=False,
        )
        artifact.artifact_type = "External Demo Test Report PDF"
        frappe.db.set_value(
            "File", file_doc.name,
            {"attached_to_doctype": "CRM Demo Artifact", "attached_to_name": artifact.name},
            update_modified=False,
        )
        frappe.db.set_value(
            "CRM Evaluation", evaluation.name,
            {
                "report_status": "Released",
                "report_artifact_id": artifact.name,
                "report_version": version,
            },
            update_modified=False,
        )
        evaluation.report_status = "Released"
        evaluation.report_artifact_id = artifact.name
        evaluation.report_version = version
        return artifact, file_doc, file_doc.get_full_path()

    def test_uploaded_report_is_versioned_and_gates_internal_review(self):
        frappe.set_user(self.engineer)
        evaluation = get_evaluation(self.evaluation.name)
        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            evaluation = update_evaluation_status(self.evaluation.name, {"status": status}, evaluation["modified"])
        self.assertEqual(evaluation["runs"], [])
        with self.assertRaises(CrmApiException) as blocked:
            update_evaluation_status(self.evaluation.name, {"status": "Internal Review"}, evaluation["modified"])
        self.assertEqual(blocked.exception.code, "INVALID_TRANSITION")

        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        first = release_demo_test_report(
            self.evaluation.name, *report_pair("results.txt", "text/plain", b"capture=98.5"),
            scanner=CleanScanner(),
            expected_round=1,
        )
        second = release_demo_test_report(
            self.evaluation.name,
            *report_pair("results.csv", "text/csv", b"metric,value\ncapture,98.5\n"),
            scanner=CleanScanner(),
            expected_round=1,
        )
        self.assertEqual((first["internalReportArtifact"]["type"], first["version"], first["internalReportArtifact"]["visibility"]), ("Test Report", 1, "Internal"))
        self.assertEqual((second["internalReportArtifact"]["type"], second["version"], second["internalReportArtifact"]["fileName"]), ("Test Report", 2, "[Internal] results.csv"))
        current = get_evaluation(self.evaluation.name)
        self.assertEqual(current["reportArtifact"]["id"], second["internalReportArtifact"]["id"])
        self.assertEqual(current["reportArtifact"]["fileName"], "[Internal] results.csv")
        self.assertEqual(current["runs"], [])
        current = add_evaluation_run(self.evaluation.name, {
            "date": "2026-08-10", "lot": "CIS-300MM-LOT-01", "wafers": 12,
            "capture": 96.8, "falsePositive": 1.1, "wph": 18.5,
            "summary": "CIS wafer acceptance criteria met",
            "expectedModified": current["modified"],
        })
        advanced = update_evaluation_status(self.evaluation.name, {"status": "Internal Review"}, current["modified"])
        self.assertEqual(advanced["status"], "Internal Review")

    def test_sales_is_denied_and_manager_can_upload_in_scope(self):
        self._ready_for_upload(self.evaluation.name)
        payload = {"file_name": "results.txt", "mime_type": "text/plain", "content": b"capture=98.5"}

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            release_demo_test_report(self.evaluation.name, payload, payload, expected_round=1)

        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        frappe.set_user(self.manager)
        result = release_demo_test_report(self.evaluation.name, payload, payload, scanner=CleanScanner(), expected_round=1)
        artifact = result["internalReportArtifact"]
        self.assertEqual((artifact["type"], artifact["fileName"], artifact["visibility"]), (
            "Test Report", "[Internal] results.txt", "Internal",
        ))
        stored = frappe.get_doc("File", frappe.db.get_value("CRM Demo Artifact", artifact["id"], "private_file"))
        self.assertTrue(stored.is_private)

    def test_sales_closes_customer_review_in_scope_and_nothing_else(self):
        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        payload = {"file_name": "feedback.txt", "mime_type": "text/plain", "content": b"customer feedback"}
        current = self._ready_for_upload(self.evaluation.name)

        # Testing is Engineer work: the status step is refused outright, and the
        # Customer Report is refused by stage, not by scope or capability.
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            update_evaluation_status(self.evaluation.name, {"status": "Internal Review"}, current["modified"])
        with self.assertRaises(CrmApiException) as too_early:
            upload_customer_report(self.evaluation.name, payload, scanner=CleanScanner(), expected_round=1)
        self.assertEqual(too_early.exception.code, "INVALID_TRANSITION")

        evaluation = self._reach_customer_review(self.evaluation.name)

        # Another Sales user's scope does not reach this Demo at all.
        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException) as foreign_upload:
            upload_customer_report(self.evaluation.name, payload, scanner=CleanScanner(), expected_round=1)
        self.assertEqual(foreign_upload.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as foreign_status:
            update_evaluation_status(
                self.evaluation.name, {"status": "Accepted", "customerComment": "Signed off"}, evaluation["modified"],
            )
        self.assertEqual(foreign_status.exception.code, "SCOPE_DENIED")

        # The owning Sales user uploads the Customer Report and closes the review with a retest.
        frappe.set_user(self.sales)
        uploaded = upload_customer_report(self.evaluation.name, payload, scanner=CleanScanner(), expected_round=1)
        self.assertEqual((uploaded["round"], uploaded["version"]), (1, 1))
        self.assertEqual(
            frappe.db.get_value("CRM Demo Artifact", uploaded["artifact"]["id"], "created_by_user"), self.sales,
        )
        evaluation = get_evaluation(self.evaluation.name)
        retested = update_evaluation_status(
            self.evaluation.name,
            {"status": "Testing", "customerComment": "Capture rate is still below target"},
            evaluation["modified"],
        )
        self.assertEqual((retested["status"], retested["testRound"]), ("Testing", 2))
        self.assertEqual(frappe.db.count("CRM Evaluation Customer Review", {
            "evaluation": self.evaluation.name, "author": self.sales, "test_round": 1,
        }), 1)
        # The Applied Engineer has to run the new round, so the retest reaches them.
        self.assertTrue(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM Evaluation", "source_name": self.evaluation.name,
            "recipient_user": self.engineer, "title": "Demo Test moved to Testing",
        }))

        # Back in Testing the new round is Engineer work again.
        with self.assertRaises(frappe.PermissionError):
            update_evaluation_status(self.evaluation.name, {"status": "Internal Review"}, retested["modified"])

    def test_sales_archives_customer_review_with_a_comment(self):
        evaluation = self._reach_customer_review(self.evaluation.name)
        frappe.set_user(self.sales)
        unchanged = update_evaluation_status(
            self.evaluation.name, {"status": "Customer Review"}, evaluation["modified"],
        )
        self.assertEqual(unchanged["status"], "Customer Review")
        archived = update_evaluation_status(
            self.evaluation.name, {"status": "Accepted", "customerComment": "Customer signed off"}, unchanged["modified"],
        )
        self.assertEqual((archived["status"], archived["testRound"]), ("Accepted", 1))
        self.assertEqual(frappe.db.get_value("CRM Evaluation Customer Review", {
            "evaluation": self.evaluation.name, "test_round": 1,
        }, "author"), self.sales)
        self.assertTrue(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM Evaluation", "source_name": self.evaluation.name, "recipient_user": self.engineer,
        }))

    def test_sales_stale_customer_review_close_is_a_version_conflict(self):
        evaluation = self._reach_customer_review(self.evaluation.name)
        stale = evaluation["modified"]
        frappe.set_user(self.engineer)
        update_evaluation_status(
            self.evaluation.name, {"status": "Testing", "customerComment": "Engineer asked for another round"}, stale,
        )
        # Sales still looks at the Customer Review view: a conflict, not a permission refusal,
        # so the page keeps its records instead of treating the user as locked out.
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as conflict:
            update_evaluation_status(
                self.evaluation.name, {"status": "Accepted", "customerComment": "Signed off"}, stale,
            )
        self.assertEqual(conflict.exception.code, "VERSION_CONFLICT")

    def test_report_upload_archive_and_retest_skip_unreachable_recipients(self):
        from rayher_crm.tests.test_contact_file_api import Scanner

        for recipient in (self.sales, self.engineer):
            for reason in ("disabled", "role_removed"):
                for outcome in ("Accepted", "Testing"):
                    with self.subTest(recipient=recipient, reason=reason, outcome=outcome):
                        _, _, evaluation = self._source(f"Unreachable {reason} {outcome}")
                        current = self._ready_for_upload(evaluation.name)
                        before = frappe.db.count("CRM Notification Event", {
                            "source_doctype": "CRM Evaluation", "source_name": evaluation.name,
                            "recipient_user": recipient,
                        })
                        frappe.set_user("Administrator")
                        user = frappe.get_doc("User", recipient)
                        enabled, roles = user.enabled, [row.role for row in user.roles]
                        if reason == "disabled":
                            user.enabled = 0
                        else:
                            user.set("roles", [{"role": role} for role in roles if not role.startswith("CRM ")])
                        user.save(ignore_permissions=True)
                        frappe.clear_cache(user=recipient)
                        try:
                            # The Manager acts on the business record; the departed participant is
                            # only a notification recipient, never the authenticated actor.
                            frappe.set_user(self.manager)
                            result = release_demo_test_report(evaluation.name,
                                *report_pair("results.txt", "text/plain", f"capture=98.5;{evaluation.name}".encode()),
                                scanner=Scanner(), expected_round=1)
                            self.assertEqual(result["version"], 1)
                            current = get_evaluation(evaluation.name)
                            current = add_evaluation_run(evaluation.name, {
                                "date": "2026-08-10", "lot": "LOT-UNREACHABLE", "wafers": 1,
                                "capture": 96, "falsePositive": 1, "wph": 10, "summary": "Passed",
                                "expectedModified": current["modified"],
                            })
                            for status in ("Internal Review", "Customer Review"):
                                current = update_evaluation_status(evaluation.name,
                                    {"status": status}, current["modified"])
                            customer_report = upload_customer_report(evaluation.name, {
                                "file_name": "customer.txt", "mime_type": "text/plain",
                                "content": f"Customer feedback {evaluation.name}".encode(),
                            }, scanner=Scanner(), expected_round=1)
                            self.assertEqual(customer_report["version"], 1)
                            current = get_evaluation(evaluation.name)
                            final = update_evaluation_status(evaluation.name, {
                                "status": outcome, "customerComment": "Reviewed with customer",
                            }, current["modified"])
                            self.assertEqual(final["status"], outcome)
                            self.assertEqual(final["testRound"], 2 if outcome == "Testing" else 1)
                            self.assertEqual(frappe.db.count("CRM Notification Event", {
                                "source_doctype": "CRM Evaluation", "source_name": evaluation.name,
                                "recipient_user": recipient,
                            }), before)
                            reachable = self.engineer if recipient == self.sales else self.sales
                            self.assertTrue(frappe.db.exists("CRM Notification Event", {
                                "source_doctype": "CRM Evaluation", "source_name": evaluation.name,
                                "recipient_user": reachable, "title": "Customer Report uploaded",
                            }))
                        finally:
                            frappe.set_user("Administrator")
                            user.reload()
                            user.enabled = enabled
                            user.set("roles", [{"role": role} for role in roles])
                            user.save(ignore_permissions=True)
                            frappe.clear_cache(user=recipient)

    def test_tipray_report_is_stored_byte_for_byte(self):
        self._ready_for_upload(self.evaluation.name)
        encrypted = b"%TSD-Header-###%" + bytes(range(256))

        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        frappe.set_user(self.manager)
        result = release_demo_test_report(
            self.evaluation.name,
            *report_pair("encrypted-report.pdf", "application/pdf", encrypted),
            scanner=CleanScanner(),
            expected_round=1,
        )
        artifact = result["internalReportArtifact"]

        private_file = frappe.db.get_value(
            "CRM Demo Artifact", artifact["id"], "private_file",
        )
        stored = frappe.get_doc("File", private_file)
        with open(stored.get_full_path(), "rb") as stored_file:
            self.assertEqual(stored_file.read(), encrypted)
        downloaded = download_demo_artifact(artifact["id"])
        self.assertEqual(downloaded["content"], encrypted)
        self.assertEqual(downloaded["file_name"], "[Internal] encrypted-report.pdf")
        self.assertEqual(downloaded["mime_type"], "application/pdf")
        self.assertEqual(artifact["mimeType"], "application/pdf")
        self.assertEqual(
            frappe.db.get_value("CRM Demo Artifact", artifact["id"], "size_bytes"),
            len(encrypted),
        )

    def test_legacy_single_report_is_migrated_as_internal_without_status_regression(self):
        from rayher_crm.patches.v1_0.backfill_demo_request_mode_and_reports import execute

        artifact, _file, _path = self._legacy_report(self.evaluation, 1)
        execute()

        migrated = frappe.get_doc("CRM Evaluation", self.evaluation.name)
        artifact.reload()
        self.assertEqual(migrated.internal_report_artifact_id, artifact.name)
        self.assertFalse(migrated.external_report_artifact_id)
        self.assertEqual(migrated.report_status, "Released")
        self.assertEqual(artifact.visibility, "Internal")

    def test_artifact_evaluation_notification_and_private_file_roll_back_together(self):
        for stage in ("after_artifact_insert", "after_evaluation_update", "after_notification_insert"):
            _account, _request, evaluation = self._source(stage)
            self._ready_for_upload(evaluation.name)
            before_files = frappe.db.count("File", {"attached_to_doctype": "CRM Demo Artifact"})
            before_notifications = frappe.db.count(
                "CRM Notification Event", {"source_name": evaluation.name},
            )

            def fail(current: str) -> None:
                if current == stage:
                    raise RuntimeError(stage)

            frappe.set_user(self.manager)
            class CleanScanner:
                def scan(self, content: bytes) -> bool:
                    return True

            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, stage):
                release_demo_test_report(
                    evaluation.name,
                    *report_pair("results.txt", "text/plain", b"capture=98.5"),
                    scanner=CleanScanner(), failure_injector=fail,
                    expected_round=1,
                )
            restored = frappe.get_doc("CRM Evaluation", evaluation.name)
            self.assertEqual((restored.report_status, restored.report_artifact_id, restored.report_version), (
                "Not Ready", None, 0,
            ))
            self.assertEqual(frappe.db.count("CRM Demo Artifact", {"evaluation": evaluation.name}), 0)
            self.assertEqual(
                frappe.db.count("CRM Notification Event", {"source_name": evaluation.name}),
                before_notifications,
            )
            self.assertEqual(
                frappe.db.count("File", {"attached_to_doctype": "CRM Demo Artifact"}),
                before_files,
            )

    def test_failed_reupload_of_identical_bytes_keeps_the_earlier_report_on_disk(self):
        # Frappe de-duplicates uploads by content hash: the second upload's File row
        # points at the first upload's physical file. Rolling the second upload back
        # must remove only its own rows, never the file the first artifact still owns.
        _account, _request, evaluation = self._source("dedup")
        self._ready_for_upload(evaluation.name)

        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        frappe.set_user(self.manager)
        content = b"capture=98.5 identical bytes"
        first = release_demo_test_report(
            evaluation.name, *report_pair("results.txt", "text/plain", content), scanner=CleanScanner(),
            expected_round=1,
        )
        first_artifact = frappe.get_doc("CRM Demo Artifact", first["internalReportArtifact"]["id"])
        first_path = frappe.get_doc("File", first_artifact.private_file).get_full_path()
        self.assertTrue(os.path.exists(first_path))

        def fail(current: str) -> None:
            if current == "after_notification_insert":
                raise RuntimeError("after_notification_insert")

        with self.assertRaisesRegex(RuntimeError, "after_notification_insert"):
            release_demo_test_report(
                evaluation.name, *report_pair("results-again.txt", "text/plain", content),
                scanner=CleanScanner(), failure_injector=fail,
                expected_round=1,
            )

        self.assertTrue(os.path.exists(first_path))
        self.assertTrue(frappe.db.exists("CRM Demo Artifact", first_artifact.name))
        self.assertEqual(download_demo_artifact(first_artifact.name)["content"], content)

    def test_external_report_cleanup_is_idempotent_and_preserves_business_history(self):
        from rayher_crm.setup.demo_report_cleanup import cleanup_external_demo_reports

        self._ready_for_upload(self.evaluation.name)
        _account, request_without_manual, evaluation_without_manual = self._source("Cleanup")
        self._ready_for_upload(evaluation_without_manual.name)

        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        frappe.set_user(self.manager)
        manual = release_demo_test_report(
            self.evaluation.name, *report_pair("manual.txt", "text/plain", b"manual report"),
            scanner=CleanScanner(),
            expected_round=1,
        )
        first_legacy, first_file, first_path = self._legacy_report(self.evaluation, 2)
        second_legacy, second_file, second_path = self._legacy_report(evaluation_without_manual, 1)
        audit = frappe.get_doc({
            "doctype": "CRM File Access Audit", "entity_type": "Demo Artifact",
            "entity_id": first_legacy.name, "account": self.evaluation.account,
            "actor": self.manager, "action": "Download", "outcome": "Allowed",
            "at": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True)
        self.evaluation.reload()
        evaluation_without_manual.reload()
        before = {
            self.evaluation.name: (self.evaluation.status, self.evaluation.acceptance),
            evaluation_without_manual.name: (
                evaluation_without_manual.status, evaluation_without_manual.acceptance,
            ),
        }
        histories = {
            self.request.name: frappe.db.count("CRM Demo Request History", {"demo_request": self.request.name}),
            request_without_manual.name: frappe.db.count(
                "CRM Demo Request History", {"demo_request": request_without_manual.name},
            ),
        }

        first = cleanup_external_demo_reports()
        second = cleanup_external_demo_reports()

        self.assertGreaterEqual(first["artifactsDeleted"], 2)
        self.assertEqual(second, {
            "artifactsDeleted": 0,
            "filesDeleted": 0,
            "evaluationsRepaired": 0,
            "physicalFilesDeleted": 0,
        })
        for artifact_id in (first_legacy.name, second_legacy.name):
            self.assertFalse(frappe.db.exists("CRM Demo Artifact", artifact_id))
        for file_id, path in ((first_file.name, first_path), (second_file.name, second_path)):
            self.assertFalse(frappe.db.exists("File", file_id))
            self.assertFalse(os.path.exists(path))
        self.assertTrue(frappe.db.exists("CRM File Access Audit", audit.name))

        with_manual = frappe.get_doc("CRM Evaluation", self.evaluation.name)
        without_manual = frappe.get_doc("CRM Evaluation", evaluation_without_manual.name)
        self.assertEqual(
            (with_manual.report_artifact_id, with_manual.report_version, with_manual.report_status),
            (manual["internalReportArtifact"]["id"], manual["version"], "Ready"),
        )
        self.assertEqual(
            (without_manual.report_artifact_id, without_manual.report_version, without_manual.report_status),
            (None, 0, "Not Ready"),
        )
        self.assertEqual((with_manual.status, with_manual.acceptance), before[self.evaluation.name])
        self.assertEqual(
            (without_manual.status, without_manual.acceptance), before[evaluation_without_manual.name],
        )
        for request_id, count in histories.items():
            self.assertEqual(
                frappe.db.count("CRM Demo Request History", {"demo_request": request_id}), count,
            )

    def _reach_customer_review(self, evaluation_id: str, expected_round: int = 1):
        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        # Callers may already have walked the preparation chain.
        if get_evaluation(evaluation_id)["status"] not in ("Testing", "Internal Review", "Customer Review"):
            self._ready_for_upload(evaluation_id)
        frappe.set_user(self.engineer)
        release_demo_test_report(
            evaluation_id, *report_pair(f"round{expected_round}.txt", "text/plain", b"capture=98.5"),
            scanner=CleanScanner(),
            expected_round=expected_round,
        )
        evaluation = get_evaluation(evaluation_id)
        evaluation = add_evaluation_run(evaluation_id, {
            "date": "2026-08-10", "lot": "CIS-300MM-LOT-01", "wafers": 12,
            "capture": 96.8, "falsePositive": 1.1, "wph": 18.5,
            "summary": "round complete",
            "expectedModified": evaluation["modified"],
        })
        evaluation = update_evaluation_status(
            evaluation_id, {"status": "Internal Review"}, evaluation["modified"],
        )
        return update_evaluation_status(
            evaluation_id, {"status": "Customer Review"}, evaluation["modified"],
        )

    def test_retest_opens_a_new_round_and_keeps_every_earlier_report(self):
        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        evaluation = self._reach_customer_review(self.evaluation.name)
        self.assertEqual(evaluation["testRound"], 1)

        retested = update_evaluation_status(
            self.evaluation.name,
            {"status": "Testing", "customerComment": "False positive rate is still too high"},
            evaluation["modified"],
        )
        self.assertEqual(retested["status"], "Testing")
        self.assertEqual(retested["testRound"], 2)
        self.assertEqual(retested["reportStatus"], "Not Ready")
        self.assertNotIn("internalReportArtifactId", retested)
        self.assertNotIn("externalReportArtifactId", retested)
        self.assertEqual(
            [(row["round"], row["comment"]) for row in retested["customerReviews"]],
            [(1, "False positive rate is still too high")],
        )

        # Round 1 reports are never overwritten, and the gate has closed again.
        self.assertEqual(frappe.db.count("CRM Demo Artifact", {
            "evaluation": self.evaluation.name, "artifact_type": "Test Report",
        }), 2)
        with self.assertRaises(CrmApiException) as blocked:
            update_evaluation_status(
                self.evaluation.name, {"status": "Internal Review"}, retested["modified"],
            )
        self.assertEqual(blocked.exception.code, "INVALID_TRANSITION")

        release_demo_test_report(
            self.evaluation.name, *report_pair("round2.txt", "text/plain", b"capture=99.1"),
            scanner=CleanScanner(),
            expected_round=2,
        )
        rounds = frappe.get_all(
            "CRM Demo Artifact",
            filters={"evaluation": self.evaluation.name, "artifact_type": "Test Report"},
            fields=["test_round"],
        )
        self.assertEqual(sorted(int(row.test_round) for row in rounds), [1, 1, 2, 2])

    def test_a_report_from_a_window_opened_before_the_retest_is_refused(self):
        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        def reports() -> int:
            return frappe.db.count("CRM Demo Artifact", {
                "evaluation": self.evaluation.name, "artifact_type": "Test Report",
            })

        evaluation = self._reach_customer_review(self.evaluation.name)
        retested = update_evaluation_status(
            self.evaluation.name,
            {"status": "Testing", "customerComment": "False positive rate is still too high"},
            evaluation["modified"],
        )
        self.assertEqual(retested["testRound"], 2)

        # The upload window still names round 1, so filing it would label round-2 work as round 1.
        with self.assertRaises(CrmApiException) as stale:
            release_demo_test_report(
                self.evaluation.name, *report_pair("stale.txt", "text/plain", b"capture=99.1"),
                scanner=CleanScanner(),
                expected_round=1,
            )
        self.assertEqual(stale.exception.code, "CONFLICT")

        # A caller that names no round cannot be checked, so it is refused rather than trusted.
        with self.assertRaises(CrmApiException) as unnamed:
            release_demo_test_report(
                self.evaluation.name, *report_pair("stale.txt", "text/plain", b"capture=99.1"),
                scanner=CleanScanner(),
            )
        self.assertEqual(unnamed.exception.code, "VALIDATION_ERROR")
        self.assertEqual(reports(), 2)

        self._reach_customer_review(self.evaluation.name, expected_round=2)
        self.assertEqual(reports(), 4)

        feedback = {"file_name": "feedback.txt", "mime_type": "text/plain", "content": b"customer feedback"}
        with self.assertRaises(CrmApiException) as stale_feedback:
            upload_customer_report(
                self.evaluation.name, feedback, scanner=CleanScanner(), expected_round=1,
            )
        self.assertEqual(stale_feedback.exception.code, "CONFLICT")
        reloaded = upload_customer_report(
            self.evaluation.name, feedback, scanner=CleanScanner(), expected_round=2,
        )
        self.assertEqual(reloaded["round"], 2)

    def test_leaving_customer_review_requires_a_comment_and_archives_on_accept(self):
        evaluation = self._reach_customer_review(self.evaluation.name)
        for status in ("Accepted", "Testing"):
            with self.assertRaises(CrmApiException) as missing:
                update_evaluation_status(
                    self.evaluation.name, {"status": status}, evaluation["modified"],
                )
            self.assertEqual(missing.exception.code, "VALIDATION_ERROR")

        archived = update_evaluation_status(
            self.evaluation.name,
            {"status": "Accepted", "customerComment": "Customer accepted the demo results"},
            evaluation["modified"],
        )
        self.assertEqual((archived["status"], archived["acceptance"]), ("Accepted", "Accepted"))
        self.assertEqual(
            [(row["round"], row["comment"]) for row in archived["customerReviews"]],
            [(1, "Customer accepted the demo results")],
        )
        # Customer Review already marked the demo as done; archiving does not move the Opportunity on.
        self.assertEqual(frappe.db.get_value("CRM Opportunity", self.request.opportunity, "stage"), DEMO_DONE)

    def test_rejection_is_no_longer_reachable(self):
        evaluation = self._reach_customer_review(self.evaluation.name)
        with self.assertRaises(CrmApiException) as blocked:
            update_evaluation_status(
                self.evaluation.name,
                {"status": "Rejected", "customerComment": "no"},
                evaluation["modified"],
            )
        self.assertEqual(blocked.exception.code, "INVALID_TRANSITION")

    def test_customer_report_is_stored_per_round_and_only_during_customer_review(self):
        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        payload = {"file_name": "feedback.txt", "mime_type": "text/plain", "content": b"customer feedback"}

        self._ready_for_upload(self.evaluation.name)
        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as too_early:
            upload_customer_report(self.evaluation.name, payload, scanner=CleanScanner(), expected_round=1)
        # errors.py folds INVALID_REPORT_STAGE into INVALID_TRANSITION at the API boundary.
        self.assertEqual(too_early.exception.code, "INVALID_TRANSITION")

        self._reach_customer_review(self.evaluation.name)
        first = upload_customer_report(self.evaluation.name, payload, scanner=CleanScanner(), expected_round=1)
        self.assertEqual((first["round"], first["version"]), (1, 1))
        self.assertEqual(first["artifact"]["type"], "Customer Report")
        self.assertEqual(first["artifact"]["fileName"], "[Customer] feedback.txt")
        self.assertEqual(first["artifact"]["visibility"], "Customer Review")

        second = upload_customer_report(self.evaluation.name, {
            "file_name": "feedback-v2.txt", "mime_type": "text/plain", "content": b"revised feedback",
        }, scanner=CleanScanner(), expected_round=1)
        self.assertEqual((second["round"], second["version"]), (1, 2))
        self.assertEqual(frappe.db.count("CRM Demo Artifact", {
            "evaluation": self.evaluation.name, "artifact_type": "Customer Report",
        }), 2)

        current = get_evaluation(self.evaluation.name)
        self.assertEqual(current["customerReportArtifact"]["id"], second["artifact"]["id"])
        self.assertEqual(current["customerReportArtifact"]["round"], 1)

        # The uploader must not keep native access to the blob once they fall out of
        # scope: the URL outlives their assignment, and File's owner shortcut would
        # serve it without download_demo_artifact's scope check or its audit row.
        # While they are still the Evaluation owner they legitimately pass, through
        # the attached document -- so the scope has to move before asserting.
        files = []
        for artifact_id in (first["artifact"]["id"], second["artifact"]["id"]):
            private_file = frappe.db.get_value("CRM Demo Artifact", artifact_id, "private_file")
            file_doc = frappe.get_doc("File", private_file)
            self.assertEqual(file_doc.owner, "Administrator")
            self.assertNotEqual(file_doc.owner, self.engineer)
            files.append(file_doc)
        # The real author is still recorded, on the artifact itself.
        self.assertEqual(
            frappe.db.get_value("CRM Demo Artifact", second["artifact"]["id"], "created_by_user"),
            self.engineer,
        )
        frappe.set_user("Administrator")
        other_engineer = self._user("crm-report-other-engineer@example.invalid", "CRM Engineer")
        frappe.db.set_value("CRM Evaluation", self.evaluation.name, "evaluation_owner", other_engineer)
        frappe.db.set_value("CRM Demo Request", self.request.name, "engineer_owner", other_engineer)
        frappe.set_user(self.engineer)
        for file_doc in files:
            self.assertFalse(frappe.has_permission("File", "read", doc=file_doc, user=self.engineer))
