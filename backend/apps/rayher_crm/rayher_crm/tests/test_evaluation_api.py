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
from rayher_crm.services.opportunities import create_strategy_opportunity, get_strategy_opportunity, mark_opportunity_lost
from rayher_crm.services.opportunity_stages import CUSTOMER_BUDGET_APPROVED, DEMO_DONE, LOST, QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


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
            "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": 200000,
            "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": 200000, "qualificationConfirmed": True,
        })
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

    def _reach_customer_review(self, evaluation_id: str) -> dict:
        current = get_evaluation(evaluation_id)
        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            current = update_evaluation_status(evaluation_id, {"status": status}, current["modified"])
        add_evaluation_run(evaluation_id, {
            "date": "2026-12-11", "lot": "LOT-REVIEW", "wafers": 1,
            "capture": 96, "falsePositive": 1, "wph": 12, "summary": "Passed",
            "expectedModified": current["modified"],
        })
        release_demo_test_report(
            evaluation_id,
            {"file_name": "results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
            {"file_name": "customer-results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
            scanner=CleanScanner(),
            expected_round=current["testRound"],
        )
        current = get_evaluation(evaluation_id)
        for status in ("Internal Review", "Customer Review"):
            current = update_evaluation_status(evaluation_id, {"status": status}, current["modified"])
        return current

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
            expected_round=1,
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
            expected_round=1,
        )
        evaluation = get_evaluation(evaluation_id)
        for status in ("Internal Review", "Customer Review", "Accepted"):
            command = {"status": status}
            if status == "Accepted":
                command["customerComment"] = "Customer signed off on the demo"
            evaluation = update_evaluation_status(evaluation_id, command, evaluation["modified"])
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
        # Entering Customer Review is the demo milestone; archiving the Demo Test moves nothing further.
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.request["opportunityId"], "stage"),
            DEMO_DONE,
        )
        review_moves = frappe.get_all(
            "CRM Opportunity Stage History",
            filters={"opportunity": self.request["opportunityId"], "event": "demo_customer_review"},
            fields=["from_stage", "to_stage", "reference_doctype", "reference_name"],
        )
        self.assertEqual(
            [(row.from_stage, row.to_stage, row.reference_doctype, row.reference_name) for row in review_moves],
            [(QUALIFIED_OPPORTUNITY, DEMO_DONE, "CRM Evaluation", evaluation_id)],
        )
        self.assertEqual(
            frappe.db.count("CRM Opportunity Stage History", {"opportunity": self.request["opportunityId"]}), 2,
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

    def _in_customer_review(self, request: dict, engineer: str) -> dict:
        """Take a Demo Test to Customer Review with a completed round-1 run and reports."""
        evaluation_id = request["evaluationId"]
        frappe.set_user(engineer)
        current = get_evaluation(evaluation_id)
        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            current = update_evaluation_status(evaluation_id, {"status": status}, current["modified"])
        add_evaluation_run(evaluation_id, {
            "date": "2026-12-11", "lot": "LOT-ARCHIVE", "wafers": 1,
            "capture": 60, "falsePositive": 9, "wph": 12, "summary": "Below criteria",
            "expectedModified": current["modified"],
        })
        release_demo_test_report(
            evaluation_id,
            {"file_name": "results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,60\n"},
            {"file_name": "customer-results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,60\n"},
            scanner=CleanScanner(),
            expected_round=1,
        )
        current = get_evaluation(evaluation_id)
        for status in ("Internal Review", "Customer Review"):
            current = update_evaluation_status(evaluation_id, {"status": status}, current["modified"])
        return current

    def test_archive_never_waits_on_the_opportunity_stage(self):
        # With Reject gone, archiving is the only way out of Customer Review. An
        # Opportunity that has left the Demo gate -- closed as Lost after the customer
        # turned the demo down, or moved back once the Demo Request was converted --
        # must not hold the Demo Test there, and must stay where Sales put it.
        for request, engineer, stage in (
            (self.request, self.engineer, LOST),
            (self.foreign_request, self.other_engineer, QUALIFIED_OPPORTUNITY),
        ):
            current = self._in_customer_review(request, engineer)
            opportunity_id = request["opportunityId"]
            values = {"stage": stage, "lost_reason": "Demo not accepted"} if stage == LOST else {"stage": stage}
            frappe.db.set_value("CRM Opportunity", opportunity_id, values)

            archived = update_evaluation_status(
                request["evaluationId"],
                {"status": "Accepted", "customerComment": "客户不认可检出率，项目关闭"},
                current["modified"],
            )

            self.assertEqual(archived["status"], "Accepted")
            self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity_id, "stage"), stage)

    def test_retest_records_the_comment_and_does_not_advance_opportunity(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)

        class CleanScanner:
            def scan(self, content: bytes) -> bool:
                return True

        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            current = update_evaluation_status(evaluation_id, {"status": status}, current["modified"])
        add_evaluation_run(evaluation_id, {
            "date": "2026-12-11", "lot": "LOT-RETEST", "wafers": 1,
            "capture": 90, "falsePositive": 4, "wph": 12, "summary": "Marginal",
            "expectedModified": current["modified"],
        })
        release_demo_test_report(
            evaluation_id,
            {"file_name": "results.csv", "mime_type": "text/csv", "content": b"metric,value"},
            {"file_name": "customer-results.csv", "mime_type": "text/csv", "content": b"metric,value"},
            scanner=CleanScanner(),
            expected_round=1,
        )
        current = get_evaluation(evaluation_id)
        for status in ("Internal Review", "Customer Review"):
            current = update_evaluation_status(evaluation_id, {"status": status}, current["modified"])
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.request["opportunityId"], "stage"), DEMO_DONE,
        )
        current = set_evaluation_test_run_deadline(evaluation_id, {
            "testRunDeadline": "2099-01-15", "expectedModified": current["modified"],
        })
        self.assertEqual(current["testRunDeadline"], "2099-01-15")

        retested = update_evaluation_status(
            evaluation_id,
            {"status": "Testing", "customerComment": "Capture rate did not meet the acceptance criteria"},
            current["modified"],
        )
        self.assertEqual((retested["status"], retested["testRound"]), ("Testing", 2))
        self.assertEqual(
            retested["history"][0]["summary"],
            "Demo Test retest requested, round 2: Capture rate did not meet the acceptance criteria",
        )
        # The round-1 deadline is history: carried over it would mark the new round
        # overdue from day one and keep the DDL reminders firing for it.
        self.assertEqual(retested["testRunDeadline"], "")
        # Clearing it is a deadline change like any other, so it leaves a Deadline row
        # right behind the retest Status row instead of vanishing silently.
        self.assertEqual(
            {key: retested["history"][1][key] for key in ("eventType", "from", "to", "summary")},
            {
                "eventType": "Deadline", "from": "2099-01-15", "to": "",
                "summary": "Cleared round 1 Test Run deadline for retest",
            },
        )
        # A retest is not an outcome, so the Opportunity must stay where it was.
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.request["opportunityId"], "stage"),
            DEMO_DONE,
        )
        self.assertEqual([run["round"] for run in retested["runs"]], [1])

        # The old round remains in the archive, but must not date the new timeline.
        workflow = next(item for item in list_demo_workflows() if item["id"] == self.request["id"])
        timeline = {step["key"]: step for step in workflow["projectTimeline"]}
        self.assertEqual((timeline["test-execution"]["state"], timeline["test-execution"]["date"]), ("Current", ""))
        self.assertEqual((timeline["internal-review"]["state"], timeline["internal-review"]["date"]), ("Waiting", ""))
        self.assertEqual([run["round"] for run in workflow["evaluation"]["runs"]], [1])

        # Test Runs and Evaluations are service-owned: no CRM role may write or
        # create them through the standard document API, so nobody can re-tag
        # the historical round-1 run, forge a Completed run in the new round, or
        # wind the Evaluation back to round 1 to pass the Internal Review gate.
        round_one_run = retested["runs"][0]["id"]
        for user in (self.manager, self.engineer):
            frappe.set_user(user)
            moved = frappe.get_doc("CRM Test Run", round_one_run)
            moved.test_round = 2
            with self.assertRaises(frappe.PermissionError):
                moved.save()
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc({
                    "doctype": "CRM Test Run", "evaluation": evaluation_id, "run_date": "2026-12-17",
                    "lot": "LOT-FORGED", "wafers": 1, "status": "Completed",
                }).insert()
            wound = frappe.get_doc("CRM Evaluation", evaluation_id)
            wound.test_round = 1
            with self.assertRaises(frappe.PermissionError):
                wound.save()
            frappe.set_user("Administrator")
        self.assertEqual(frappe.db.get_value("CRM Test Run", round_one_run, "test_round"), 1)
        self.assertEqual(frappe.db.count("CRM Test Run", {"evaluation": evaluation_id}), 1)
        # Even a privileged writer cannot change the round marker after creation.
        moved = frappe.get_doc("CRM Test Run", round_one_run)
        moved.test_round = 2
        with self.assertRaises(frappe.ValidationError):
            moved.save()
        moved = frappe.get_doc("CRM Test Run", round_one_run)
        moved.evaluation = self.foreign_request["evaluationId"]
        with self.assertRaises(frappe.ValidationError):
            moved.save()
        edited = frappe.get_doc("CRM Test Run", round_one_run)
        edited.summary = "Summary edits stay allowed"
        edited.save()
        self.assertEqual(frappe.db.get_value("CRM Test Run", round_one_run, "summary"), "Summary edits stay allowed")
        # The Evaluation's own round only ever advances by one through the
        # service: even a privileged writer can neither wind it back nor skip.
        for bogus_round in (1, 3):
            wound = frappe.get_doc("CRM Evaluation", evaluation_id)
            wound.test_round = bogus_round
            with self.assertRaises(frappe.ValidationError):
                wound.save()
        self.assertEqual(frappe.db.get_value("CRM Evaluation", evaluation_id, "test_round"), 2)
        untouched = frappe.get_doc("CRM Evaluation", evaluation_id)
        untouched.criteria = "Unrelated edits stay allowed"
        untouched.save()
        self.assertEqual(frappe.db.get_value("CRM Evaluation", evaluation_id, "test_round"), 2)
        # A run inserted with an arbitrary round is stamped from the parent instead.
        stamped = frappe.get_doc({
            "doctype": "CRM Test Run", "evaluation": evaluation_id, "test_round": 7,
            "run_date": "2026-12-17", "lot": "LOT-DIRECT", "wafers": 1, "status": "Planned",
        }).insert()
        self.assertEqual(stamped.test_round, 2)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "CRM Test Run", "evaluation": "CRM-EVAL-MISSING", "test_round": 1,
                "run_date": "2026-12-17", "lot": "LOT-ORPHAN", "wafers": 1, "status": "Planned",
            }).insert()
        frappe.delete_doc("CRM Test Run", stamped.name, force=True)

        # Round-2 reports alone must not reopen Internal Review: the round-1
        # Completed run is history, not evidence that the retest was performed.
        release_demo_test_report(
            evaluation_id,
            {"file_name": "results-r2.csv", "mime_type": "text/csv", "content": b"metric,value"},
            {"file_name": "customer-results-r2.csv", "mime_type": "text/csv", "content": b"metric,value"},
            scanner=CleanScanner(),
            expected_round=2,
        )
        current = get_evaluation(evaluation_id)
        self.assertEqual(current["reportStatus"], "Ready")
        with self.assertRaises(CrmApiException) as no_round_two_run:
            update_evaluation_status(evaluation_id, {"status": "Internal Review"}, current["modified"])
        self.assertEqual(no_round_two_run.exception.code, "INVALID_TRANSITION")
        self.assertIn("round 2", no_round_two_run.exception.public_message)

        # A run completed in round 2 is tagged with that round and opens the gate.
        current = add_evaluation_run(evaluation_id, {
            "date": "2026-12-18", "lot": "LOT-RETEST-2", "wafers": 1,
            "capture": 97, "falsePositive": 2, "wph": 12, "summary": "Retest passed",
            "expectedModified": current["modified"],
        })
        self.assertEqual([run["round"] for run in current["runs"]], [1, 2])
        self.assertEqual(
            frappe.db.get_value("CRM Test Run", current["runs"][-1]["id"], "test_round"), 2,
        )
        reviewed = update_evaluation_status(evaluation_id, {"status": "Internal Review"}, current["modified"])
        self.assertEqual((reviewed["status"], reviewed["testRound"]), ("Internal Review", 2))

        workflow = next(item for item in list_demo_workflows() if item["id"] == self.request["id"])
        timeline = {step["key"]: step for step in workflow["projectTimeline"]}
        self.assertEqual(timeline["test-execution"]["date"], "2026-12-18")
        self.assertEqual(timeline["internal-review"]["date"], "2026-12-18")
        self.assertEqual([run["round"] for run in workflow["evaluation"]["runs"]], [1, 2])
        # The deal moved on during round 2; re-entering Customer Review must not move it again.
        advance_opportunity_fixture(get_strategy_opportunity(self.request["opportunityId"]), CUSTOMER_BUDGET_APPROVED)
        reviewed = update_evaluation_status(evaluation_id, {"status": "Customer Review"}, reviewed["modified"])
        self.assertEqual((reviewed["status"], reviewed["testRound"]), ("Customer Review", 2))
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.request["opportunityId"], "stage"),
            CUSTOMER_BUDGET_APPROVED,
        )
        self.assertEqual(
            frappe.db.count(
                "CRM Opportunity Stage History",
                {"opportunity": self.request["opportunityId"], "event": "demo_customer_review"},
            ),
            1,
        )

    def test_customer_review_does_not_advance_a_lost_opportunity(self):
        opportunity_id = self.foreign_request["opportunityId"]
        frappe.set_user(self.other_sales)
        lost = mark_opportunity_lost(
            opportunity_id, {"lostReason": "Customer postponed the fab expansion."},
            get_strategy_opportunity(opportunity_id)["modified"],
        )
        self.assertEqual((lost["stage"], lost["lostAtStage"]), (LOST, QUALIFIED_OPPORTUNITY))

        frappe.set_user(self.other_engineer)
        reviewed = self._reach_customer_review(self.foreign_request["evaluationId"])
        # Customer feedback on a lost deal is still recorded, but it does not reopen the deal.
        self.assertEqual(reviewed["status"], "Customer Review")
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity_id, "stage"), LOST)
        self.assertFalse(frappe.db.exists(
            "CRM Opportunity Stage History", {"opportunity": opportunity_id, "event": "demo_customer_review"},
        ))
