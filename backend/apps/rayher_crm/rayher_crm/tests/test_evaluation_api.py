from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.demo_requests import transition_demo_request
from rayher_crm.services.demo_reports import release_demo_test_report
from rayher_crm.services.evaluations import (
    add_evaluation_run,
    complete_evaluation_preparation,
    get_evaluation,
    get_demo_workflow,
    list_demo_workflows,
    list_evaluations,
    set_evaluation_test_run_deadline,
    update_evaluation_status,
)
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.sites import create_site


class CleanScanner:
    def scan(self, content: bytes) -> bool:
        return True


class TestEvaluationApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self._user("crm-eval-manager@example.invalid", "CRM Manager")
        self.sales = self._user("crm-eval-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-eval-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-eval-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._user("crm-eval-other-engineer@example.invalid", "CRM Engineer")
        self.account, self.request = self._approved_source("Core", self.sales, self.engineer)
        self.foreign_account, self.foreign_request = self._approved_source(
            "Foreign", self.other_sales, self.other_engineer,
        )

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
            user.enabled = 1
            if role not in {row.role for row in user.roles}:
                user.append("roles", {"role": role})
                user.save(ignore_permissions=True)
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _approved_source(self, suffix: str, sales: str, engineer: str):
        frappe.set_user("Administrator")
        account = frappe.get_doc({
            "doctype": "Customer", "customer_name": f"Evaluation {suffix}", "customer_type": "Company",
            "customer_group": "CRM Customers", "territory": "CRM Territory", "custom_crm_owner": sales,
            "custom_crm_short_name": suffix, "custom_crm_segment": "Frontend", "custom_crm_tier": "A",
            "custom_crm_city": "Shanghai", "custom_crm_region": "East China",
        }).insert(ignore_permissions=True)
        contact = frappe.get_doc({
            "doctype": "Contact", "first_name": f"{suffix} Contact", "custom_crm_owner": sales,
            "custom_crm_relationship": "Developing", "custom_crm_status": "Active",
            "custom_crm_data_quality": "Complete",
        })
        contact.append("links", {"link_doctype": "Customer", "link_name": account.name})
        contact.insert(ignore_permissions=True)
        frappe.set_user(sales)
        site = create_site(account.name, {
            "name": f"{suffix} Evaluation Site", "city": "Shanghai", "type": "Fab",
            "process": "Frontend", "status": "量产",
        })
        opportunity = create_strategy_opportunity({
            "accountId": account.name, "siteId": site["id"],
            "title": f"Evaluation {suffix} Opportunity", "owner": sales,
            "stage": "需求发现", "forecast": "Pipeline", "amount": 200000,
            "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": 200000,
        })
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "stage", "Wafer Demo确认")
        frappe.set_user("Administrator")
        request = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": account.name, "primary_contact": contact.name,
            "requirement_id": f"REQ-{suffix}", "opportunity": opportunity["id"],
            "sales_owner": sales, "created_by_user": sales,
            "title": f"Evaluation {suffix} Demo", "objective": "Detect particles",
            "requested_equipment": "Inspection 3000", "sample_type": "Si", "sample_quantity": 1,
            "target_date": "2026-12-20", "customer_expected_date": "2026-12-31", "priority": "High",
            "acceptance_criteria": "Capture above 95%", "status": "Manager Approval",
            "engineer_owner": engineer, "feasibility": "Feasible", "test_plan": "Particle recipe",
            "assigned_equipment": "Inspection 3000", "resource_window": "Week 48",
            "estimated_completion_date": "2026-12-20", "technical_risk": "Contamination",
            "engineer_comment": "Feasible", "manager_decision": "Pending", "form_data": {},
        }).insert(ignore_permissions=True)
        frappe.set_user(self.manager)
        approved = transition_demo_request(request.name, {"type": "manager_approve", "comment": "Approved"})
        return account.name, approved["request"]

    def test_scoped_list_get_strict_status_graph_cas_and_acceptance(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.sales)
        items, total, page, page_size = list_evaluations({
            "accountId": self.account, "page": 1, "pageSize": 10,
        })
        self.assertEqual((len(items), total, page, page_size), (1, 1, 1, 10))
        current = get_evaluation(evaluation_id)
        self.assertEqual(current["status"], "Requested")
        before_modified = frappe.db.get_value("CRM Evaluation", evaluation_id, "modified")
        self.assertEqual(get_evaluation(evaluation_id)["modified"], current["modified"])
        self.assertEqual(frappe.db.get_value("CRM Evaluation", evaluation_id, "modified"), before_modified)

        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as stale:
            update_evaluation_status(evaluation_id, {"status": "Scope Confirmed"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        current = update_evaluation_status(evaluation_id, {"status": "Scope Confirmed"}, current["modified"])
        with self.assertRaises(CrmApiException) as jump:
            update_evaluation_status(evaluation_id, {"status": "Testing"}, current["modified"])
        self.assertEqual(jump.exception.code, "INVALID_TRANSITION")
        for status in ("Sample Received", "Scheduled", "Testing"):
            current = update_evaluation_status(evaluation_id, {"status": status}, current["modified"])
        self.assertEqual(current["acceptance"], "Pending")

        frappe.set_user(self.other_engineer)
        self.assertNotIn(evaluation_id, {item["id"] for item in list_evaluations({})[0]})
        with self.assertRaises(CrmApiException) as denied:
            get_evaluation(evaluation_id)
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

    def test_parallel_preparation_requires_both_branches_before_execution(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)

        wafer = complete_evaluation_preparation(
            evaluation_id, "wafer", current["modified"],
        )
        self.assertEqual(wafer["waferPreparationStatus"], "Completed")
        self.assertEqual(wafer["testPreparationStatus"], "Pending")
        self.assertEqual(wafer["status"], "Requested")
        with self.assertRaises(CrmApiException) as blocked:
            update_evaluation_status(evaluation_id, {"status": "Testing"}, wafer["modified"])
        self.assertEqual(blocked.exception.code, "INVALID_TRANSITION")

        test = complete_evaluation_preparation(
            evaluation_id, "test", wafer["modified"],
        )
        self.assertEqual(test["testPreparationStatus"], "Completed")
        self.assertEqual(test["status"], "Scheduled")
        testing = update_evaluation_status(
            evaluation_id, {"status": "Testing"}, test["modified"],
        )
        self.assertEqual(testing["status"], "Testing")

        with self.assertRaises(CrmApiException) as no_report:
            update_evaluation_status(evaluation_id, {"status": "Internal Review"}, testing["modified"])
        self.assertEqual(no_report.exception.code, "INVALID_TRANSITION")
        release_demo_test_report(
            evaluation_id,
            {"file_name": "results.txt", "mime_type": "text/plain", "content": b"capture=96"},
            {"file_name": "customer-results.txt", "mime_type": "text/plain", "content": b"capture=96"},
            scanner=CleanScanner(),
        )
        completed = get_evaluation(evaluation_id)
        self.assertEqual(completed["runs"], [])
        with self.assertRaises(CrmApiException) as no_completed_run:
            update_evaluation_status(
                evaluation_id, {"status": "Internal Review"}, completed["modified"],
            )
        self.assertEqual(no_completed_run.exception.code, "INVALID_TRANSITION")
        completed = add_evaluation_run(evaluation_id, {
            "date": "2026-12-11", "lot": "LOT-REVIEW", "wafers": 12,
            "capture": 96.8, "falsePositive": 1.1, "wph": 18.5,
            "summary": "CIS wafer acceptance criteria met",
            "expectedModified": completed["modified"],
        })
        internal = update_evaluation_status(
            evaluation_id, {"status": "Internal Review"}, completed["modified"],
        )
        self.assertEqual(internal["status"], "Internal Review")
        self.assertTrue(
            {"Created", "Preparation", "Status", "Report", "Test Run"}.issubset(
                {row["eventType"] for row in internal["history"]},
            ),
        )
        manager_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Evaluation", "source_name": evaluation_id,
                     "recipient_user": self.manager, "title": "Demo Test moved to Internal Review"},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (manager_notice.category, manager_notice.route),
            ("Evaluation", f"/demo-workflow/{self.request['id']}?tab=information"),
        )
        frappe.set_user(self.manager)
        self.assertEqual(get_evaluation(evaluation_id)["id"], evaluation_id)
        frappe.set_user(self.engineer)

        with self.assertRaises(CrmApiException) as stale:
            complete_evaluation_preparation(evaluation_id, "wafer", current["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

    def test_test_run_stage_validation_metrics_server_id_total_and_report_lock(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        evaluation = get_evaluation(evaluation_id)
        with self.assertRaises(CrmApiException) as stage:
            add_evaluation_run(evaluation_id, {
                "date": "2026-12-10", "lot": "LOT-1", "wafers": 1,
                "capture": None, "falsePositive": None, "wph": None, "summary": "",
            })
        self.assertEqual(stage.exception.code, "INVALID_TRANSITION")

        for status in ("Scope Confirmed", "Sample Received", "Scheduled"):
            evaluation = update_evaluation_status(evaluation_id, {"status": status}, evaluation["modified"])
        invalid_runs = [
            ({"date": "2026-02-30", "lot": "LOT", "wafers": 1, "capture": None, "falsePositive": None, "wph": None, "summary": ""}, "VALIDATION_ERROR"),
            ({"date": "2026-12-10", "lot": "LOT", "wafers": 0, "capture": None, "falsePositive": None, "wph": None, "summary": ""}, "VALIDATION_ERROR"),
            ({"date": "2026-12-10", "lot": "LOT", "wafers": 1, "capture": 95, "falsePositive": None, "wph": 10, "summary": "done"}, "VALIDATION_ERROR"),
            ({"date": "2026-12-10", "lot": "LOT", "wafers": 1, "capture": 101, "falsePositive": 1, "wph": 10, "summary": "done"}, "VALIDATION_ERROR"),
            ({"date": "2026-12-10", "lot": "LOT", "wafers": 1, "capture": 95, "falsePositive": 1, "wph": 10, "summary": ""}, "VALIDATION_ERROR"),
        ]
        for payload, code in invalid_runs:
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as error:
                add_evaluation_run(evaluation_id, payload)
            self.assertEqual(error.exception.code, code)

        planned = add_evaluation_run(evaluation_id, {
            "date": "2026-12-10", "lot": "LOT-PLAN", "wafers": 2,
            "capture": None, "falsePositive": None, "wph": None, "summary": "",
            "expectedModified": evaluation["modified"],
        })
        self.assertRegex(planned["runs"][0]["id"], r"^CRM-RUN-\d{5}$")
        self.assertEqual((planned["runs"][0]["status"], planned["wafers"]), ("Planned", 2))
        completed = add_evaluation_run(evaluation_id, {
            "date": "2026-12-11", "lot": "LOT-DONE", "wafers": 3,
            "capture": 96.5, "falsePositive": 1.2, "wph": 12, "summary": "Passed",
            "expectedModified": planned["modified"],
        })
        self.assertEqual((completed["runs"][1]["status"], completed["wafers"]), ("Completed", 5))
        self.assertEqual(completed["reportStatus"], "Not Ready")

    def test_deadline_forward_completion_and_read_only_workflow_projection(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.manager)
        frappe.db.set_value("CRM Demo Request", self.request["id"], "status", "Manager Approval")
        workflow = next(item for item in list_demo_workflows() if item["id"] == self.request["id"])
        self.assertEqual(workflow["stage"], "Manager Approval")
        frappe.db.set_value("CRM Demo Request", self.request["id"], "status", "Converted")
        workflow = next(item for item in list_demo_workflows() if item["id"] == self.request["id"])
        self.assertEqual(workflow["stage"], "Test Preparation")
        exact = get_demo_workflow(self.request["id"])
        self.assertEqual(exact["id"], self.request["id"])
        with self.assertRaises(CrmApiException) as missing_workflow:
            get_demo_workflow("CRM-DR-99999")
        self.assertEqual(missing_workflow.exception.code, "NOT_FOUND")

        frappe.set_user(self.manager)
        evaluation = get_evaluation(evaluation_id)
        with self.assertRaises(CrmApiException) as invalid_date:
            set_evaluation_test_run_deadline(evaluation_id, {"testRunDeadline": "2026-02-30"})
        self.assertEqual(invalid_date.exception.code, "VALIDATION_ERROR")
        evaluation = set_evaluation_test_run_deadline(
            evaluation_id, {"testRunDeadline": "2026-12-15", "expectedModified": evaluation["modified"]},
        )
        self.assertEqual(evaluation["testRunDeadline"], "2026-12-15")
        deadline_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Evaluation", "source_name": evaluation_id,
                     "recipient_user": self.engineer, "title": "Demo Test deadline updated"},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (deadline_notice.category, deadline_notice.route),
            ("Evaluation", f"/demo-workflow/{self.request['id']}?tab=information"),
        )
        frappe.set_user(self.engineer)
        self.assertEqual(get_evaluation(evaluation_id)["id"], evaluation_id)
        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            evaluation = update_evaluation_status(evaluation_id, {"status": status}, evaluation["modified"])
        add_evaluation_run(evaluation_id, {
            "date": "2026-12-11", "lot": "LOT-DONE", "wafers": 1,
            "capture": 96, "falsePositive": 1, "wph": 12, "summary": "Passed",
            "expectedModified": evaluation["modified"],
        })
        release_demo_test_report(
            evaluation_id,
            {"file_name": "results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
            {"file_name": "customer-results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
            scanner=CleanScanner(),
        )
        evaluation = get_evaluation(evaluation_id)
        for status in ("Internal Review", "Customer Review", "Accepted"):
            evaluation = update_evaluation_status(evaluation_id, {"status": status}, evaluation["modified"])
        self.assertEqual(evaluation["acceptance"], "Accepted")
        sales_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Evaluation", "source_name": evaluation_id,
                     "recipient_user": self.sales, "title": "Demo Test moved to Accepted"},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (sales_notice.category, sales_notice.route),
            ("Evaluation", f"/demo-workflow/{self.request['id']}?tab=information"),
        )
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.request["opportunityId"], "stage"),
            "预算审批",
        )

        request_modified = frappe.db.get_value("CRM Demo Request", self.request["id"], "modified")
        evaluation_modified = frappe.db.get_value("CRM Evaluation", evaluation_id, "modified")
        workflows = list_demo_workflows()
        workflow = next(item for item in workflows if item["id"] == self.request["id"])
        self.assertEqual(workflow["evaluation"]["id"], evaluation_id)
        self.assertEqual(workflow["evaluation"]["runs"][0]["status"], "Completed")
        timeline = {step["key"]: step for step in workflow["projectTimeline"]}
        self.assertTrue(timeline["sales-preparation"]["date"].endswith("Z"))
        self.assertEqual(timeline["engineer-review"]["date"], "")
        self.assertTrue(timeline["manager-approval"]["date"].endswith("Z"))
        self.assertEqual(timeline["test-execution"]["date"], "2026-12-11")
        self.assertEqual(timeline["internal-review"]["date"], "2026-12-11")
        self.assertEqual(timeline["customer-review"]["state"], "Done")
        self.assertEqual(frappe.db.get_value("CRM Demo Request", self.request["id"], "modified"), request_modified)
        self.assertEqual(frappe.db.get_value("CRM Evaluation", evaluation_id, "modified"), evaluation_modified)

        scoped, total, page, page_size = list_demo_workflows({
            "contactId": self.request["primaryContactId"], "page": 1, "pageSize": 10,
        })
        self.assertEqual((len(scoped), total, page, page_size), (1, 1, 1, 10))
        self.assertEqual(scoped[0]["id"], self.request["id"])

    def test_rejected_evaluation_does_not_advance_opportunity(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)
        with self.assertRaises(CrmApiException) as missing_reason:
            update_evaluation_status(evaluation_id, {"status": "Rejected"}, current["modified"])
        self.assertEqual(missing_reason.exception.field_errors, {"reason": "Required"})
        rejected = update_evaluation_status(
            evaluation_id,
            {"status": "Rejected", "reason": "Capture rate did not meet the acceptance criteria"},
            current["modified"],
        )
        self.assertEqual(rejected["status"], "Rejected")
        self.assertEqual(
            rejected["history"][0]["summary"],
            "Demo Test rejected: Capture rate did not meet the acceptance criteria",
        )
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.request["opportunityId"], "stage"),
            "Wafer Demo确认",
        )
