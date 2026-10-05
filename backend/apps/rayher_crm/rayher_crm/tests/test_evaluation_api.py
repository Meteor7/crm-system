from __future__ import annotations

import json
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from rayher_crm.api.v1 import evaluations as evaluations_api
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.services.accounts import get_account_360
from rayher_crm.services.dashboard import get_dashboard
from rayher_crm.services.ddl_reminders import send_ddl_reminders
from rayher_crm.services.demo_requests import transition_demo_request
from rayher_crm.services.demo_reports import release_demo_test_report
from rayher_crm.services import cockpit
from rayher_crm.services.evaluations import (
    add_evaluation_run,
    cancel_evaluation_run,
    complete_evaluation_preparation,
    get_evaluation,
    get_demo_workflow,
    list_demo_workflows,
    list_evaluations,
    set_evaluation_test_run_deadline,
    terminate_evaluation,
    update_evaluation_run,
    update_evaluation_status,
)
from rayher_crm.services.opportunities import (
    advance_opportunity_for_event,
    create_opportunity_action,
    create_strategy_opportunity,
    get_strategy_opportunity,
    mark_opportunity_lost,
    rollback_opportunity_stage,
    update_strategy_opportunity,
)
from rayher_crm.services.opportunity_stages import CUSTOMER_BUDGET_APPROVED, DEMO_DONE, LOST, QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site
from rayher_crm.services.visits import create_visit
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

    def _approved_source(self, suffix: str, sales: str, engineer: str, *, priced: bool = True):
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
            "probabilityLevel": "pipeline",
            "accountId": account.name, "siteId": site["id"],
            "title": f"Evaluation {suffix} Opportunity", "owner": sales,
            "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": 200000 if priced else "",
            "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": 200000 if priced else "", "amountCny": 200000 if priced else "",
            "qualificationConfirmed": True,
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

    def _pending_notices(self, opportunity_id: str) -> list[tuple[str, str, str]]:
        rows = frappe.get_all(
            "CRM Notification Event", filters={"source_doctype": "CRM Opportunity", "source_name": opportunity_id},
            fields=["recipient_user", "category", "route"],
        )
        return [(row.recipient_user, row.category, row.route) for row in rows]

    def test_customer_review_without_an_amount_keeps_the_demo_and_waits_for_the_amount(self):
        _account, request = self._approved_source("Unpriced", self.sales, self.engineer, priced=False)
        opportunity_id, evaluation_id = request["opportunityId"], request["evaluationId"]
        frappe.set_user(self.engineer)
        reviewed = self._reach_customer_review(evaluation_id)

        # The Demo result is saved; the Opportunity cannot enter Demo done without its amount.
        self.assertEqual(reviewed["status"], "Customer Review")
        frappe.set_user(self.sales)
        waiting = get_strategy_opportunity(opportunity_id)
        self.assertEqual((waiting["stage"], waiting["pendingStageAdvance"]), (QUALIFIED_OPPORTUNITY, DEMO_DONE))
        self.assertFalse(frappe.db.exists(
            "CRM Opportunity Stage History", {"opportunity": opportunity_id, "event": "demo_customer_review"},
        ))
        self.assertEqual(self._pending_notices(opportunity_id), [(self.sales, "Opportunity", f"/opportunities/{opportunity_id}")])

        # Another Demo event before the amount arrives changes nothing and notifies nobody again.
        frappe.set_user(self.engineer)
        advance_opportunity_for_event(
            opportunity_id, "demo_customer_review", reference_doctype="CRM Evaluation", reference_name=evaluation_id,
        )
        frappe.set_user(self.sales)
        self.assertEqual(get_strategy_opportunity(opportunity_id)["modified"], waiting["modified"])
        self.assertEqual(len(self._pending_notices(opportunity_id)), 1)

        # An edit without the amount leaves the Opportunity waiting.
        renamed = update_strategy_opportunity(opportunity_id, {"title": "Unpriced, renamed"}, waiting["modified"])
        self.assertEqual((renamed["stage"], renamed["pendingStageAdvance"]), (QUALIFIED_OPPORTUNITY, DEMO_DONE))

        # The save that enters the amount applies the waiting advance in the same transaction.
        amounts = {"amount": "200000", "originalAmount": "200000", "amountCny": "200000"}
        priced = update_strategy_opportunity(opportunity_id, amounts, renamed["modified"])
        self.assertEqual(
            (priced["stage"], priced["pendingStageAdvance"], priced["amount"], priced["amountCny"]),
            (DEMO_DONE, "", "200000.00", "200000.00"),
        )
        [move] = [row for row in priced["stageHistory"] if row["event"] == "demo_customer_review"]
        self.assertEqual(
            (move["from"], move["to"], move["source"], move["referenceDoctype"], move["referenceName"],
             move["reason"], move["reachedAtBasis"], move["actor"]),
            (QUALIFIED_OPPORTUNITY, DEMO_DONE, "event", "CRM Evaluation", evaluation_id,
             "Demo done pending amount", "recorded", self.sales),
        )
        # Reached when the amount arrived: the stage date is not backdated to the Demo review.
        self.assertEqual((move["reachedAt"], priced["stageChangedAt"]), (move["recordedAt"], move["recordedAt"]))

        # A second submit of the same form is stale, and later saves never move the stage again.
        with self.assertRaises(CrmApiException) as twice:
            update_strategy_opportunity(opportunity_id, amounts, renamed["modified"])
        self.assertEqual(twice.exception.code, "VERSION_CONFLICT")
        repriced = update_strategy_opportunity(
            opportunity_id, {"amount": "210000", "originalAmount": "210000", "amountCny": "210000"}, priced["modified"],
        )
        self.assertEqual(repriced["stage"], DEMO_DONE)
        frappe.set_user(self.engineer)
        advance_opportunity_for_event(
            opportunity_id, "demo_customer_review", reference_doctype="CRM Evaluation", reference_name=evaluation_id,
        )
        self.assertEqual(frappe.db.count(
            "CRM Opportunity Stage History", {"opportunity": opportunity_id, "event": "demo_customer_review"},
        ), 1)
        self.assertEqual(len(self._pending_notices(opportunity_id)), 1)

        # The Demo result stays as recorded throughout, and the Demo carries on as usual.
        demo = get_evaluation(evaluation_id)
        self.assertEqual((demo["status"], [run["status"] for run in demo["runs"]]), ("Customer Review", ["Completed"]))
        archived = update_evaluation_status(
            evaluation_id, {"status": "Accepted", "customerComment": "Customer signed off"}, demo["modified"],
        )
        self.assertEqual(archived["status"], "Accepted")

    def test_a_waiting_demo_done_outlasts_a_loss_and_applies_once_reopened_with_amounts(self):
        # The Demo still stands after a loss, so a reopened deal is not stuck at S1 for want of a new Demo.
        amounts = {"amount": "1000", "originalAmount": "1000", "amountCny": "1000"}

        def demo_moves(opportunity_id: str) -> int:
            return frappe.db.count(
                "CRM Opportunity Stage History", {"opportunity": opportunity_id, "event": "demo_customer_review"},
            )

        def held_then_lost(suffix: str) -> tuple[str, dict]:
            _account, request = self._approved_source(suffix, self.sales, self.engineer, priced=False)
            frappe.set_user(self.engineer)
            self._reach_customer_review(request["evaluationId"])
            frappe.set_user(self.sales)
            opportunity_id = request["opportunityId"]
            lost = mark_opportunity_lost(
                opportunity_id, {"lostReason": "Budget cut"}, get_strategy_opportunity(opportunity_id)["modified"],
            )
            self.assertEqual(
                (lost["stage"], lost["lostAtStage"], lost["pendingStageAdvance"]), (LOST, QUALIFIED_OPPORTUNITY, DEMO_DONE),
            )
            return opportunity_id, lost

        # Amounts entered while lost change nothing yet; the reopening applies the waiting advance.
        opportunity_id, lost = held_then_lost("Unpriced Lost")
        priced = update_strategy_opportunity(opportunity_id, amounts, lost["modified"])
        self.assertEqual((priced["stage"], priced["pendingStageAdvance"], priced["amount"]), (LOST, DEMO_DONE, "1000.00"))
        self.assertEqual(demo_moves(opportunity_id), 0)
        frappe.set_user(self.manager)
        reopened = rollback_opportunity_stage(opportunity_id, QUALIFIED_OPPORTUNITY, "Customer came back", priced["modified"])
        self.assertEqual((reopened["stage"], reopened["pendingStageAdvance"]), (DEMO_DONE, ""))
        self.assertEqual(demo_moves(opportunity_id), 1)

        # Reopened without amounts it keeps waiting at S1, and the save that enters them applies it.
        opportunity_id, lost = held_then_lost("Unpriced Reopened")
        frappe.set_user(self.manager)
        reopened = rollback_opportunity_stage(opportunity_id, QUALIFIED_OPPORTUNITY, "Customer came back", lost["modified"])
        self.assertEqual((reopened["stage"], reopened["pendingStageAdvance"]), (QUALIFIED_OPPORTUNITY, DEMO_DONE))
        frappe.set_user(self.sales)
        advanced = update_strategy_opportunity(opportunity_id, amounts, reopened["modified"])
        self.assertEqual((advanced["stage"], advanced["pendingStageAdvance"]), (DEMO_DONE, ""))
        self.assertEqual(demo_moves(opportunity_id), 1)

    def test_holding_the_advance_does_not_fail_when_the_owner_cannot_be_notified(self):
        _account, request = self._approved_source("Unpriced Gone", self.sales, self.engineer, priced=False)
        opportunity_id = request["opportunityId"]
        frappe.set_user("Administrator")
        frappe.db.set_value("User", self.sales, "enabled", 0)
        try:
            # The hold itself must not fail for a Sales owner who left. The Demo workflow's own notices
            # to that owner are #75, so the event is raised directly here.
            frappe.set_user(self.engineer)
            advance_opportunity_for_event(
                opportunity_id, "demo_customer_review",
                reference_doctype="CRM Evaluation", reference_name=request["evaluationId"],
            )
            frappe.set_user(self.manager)
            waiting = get_strategy_opportunity(opportunity_id)
            self.assertEqual((waiting["stage"], waiting["pendingStageAdvance"]), (QUALIFIED_OPPORTUNITY, DEMO_DONE))
            self.assertEqual(self._pending_notices(opportunity_id), [])
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("User", self.sales, "enabled", 1)

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

    def _planned_run(self, evaluation_id: str, day: str = "2026-12-10") -> dict:
        evaluation = get_evaluation(evaluation_id)
        for status in ("Scope Confirmed", "Sample Received", "Scheduled", "Testing"):
            evaluation = update_evaluation_status(evaluation_id, {"status": status}, evaluation["modified"])
        return add_evaluation_run(evaluation_id, {
            "date": day, "lot": "LOT-PLAN", "wafers": 2, "expectedModified": evaluation["modified"],
        })

    def _plan_test_ids(self, anchor: str) -> list[str]:
        user = frappe.session.user
        frappe.set_user(self.manager)
        try:
            query = {"period": "week", "anchor": anchor, "sales": self.sales}
            details = cockpit.get_plan_details({**query, "metric": "tests"})
            self.assertEqual(cockpit.get_plan(query)["summary"]["tests"], {"value": details["total"], "state": "ready", "reason": None})
            return [row["id"] for row in details["items"]]
        finally:
            frappe.set_user(user)

    def test_demo_enters_plan_after_preparation_without_a_run_or_deadline(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)
        self.assertNotIn(evaluation_id, self._plan_test_ids("2026-12-10"))
        current = complete_evaluation_preparation(evaluation_id, "wafer", current["modified"])
        self.assertNotIn(evaluation_id, self._plan_test_ids("2026-12-10"))
        current = complete_evaluation_preparation(evaluation_id, "test", current["modified"])
        self.assertEqual((current["status"], current["runs"], current["testRunDeadline"]), ("Scheduled", [], ""))
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-10"))
        current = update_evaluation_status(evaluation_id, {"status": "Testing"}, current["modified"])
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-10"))
        current = add_evaluation_run(evaluation_id, {
            "date": "2026-12-11", "lot": "LOT-REVIEW", "wafers": 1,
            "capture": 96, "falsePositive": 1, "wph": 12, "summary": "Passed",
            "expectedModified": current["modified"],
        })
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-10"))
        release_demo_test_report(
            evaluation_id,
            {"file_name": "results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
            {"file_name": "customer-results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
            scanner=CleanScanner(), expected_round=current["testRound"],
        )
        current = get_evaluation(evaluation_id)
        current = update_evaluation_status(evaluation_id, {"status": "Internal Review"}, current["modified"])
        self.assertNotIn(evaluation_id, self._plan_test_ids("2026-12-10"))

    def test_planned_run_is_rescheduled_completed_or_cancelled_in_place(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        planned = self._planned_run(evaluation_id)
        run_id = planned["runs"][0]["id"]
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-10"))

        with self.assertRaises(CrmApiException) as stale:
            update_evaluation_run(evaluation_id, run_id, {"date": "2026-12-17", "lot": "LOT-PLAN", "wafers": 2, "expectedModified": "2000-01-01T00:00:00Z"})
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        with self.assertRaises(CrmApiException) as foreign:
            update_evaluation_run(self.foreign_request["evaluationId"], run_id, {"date": "2026-12-17", "lot": "LOT-PLAN", "wafers": 2})
        self.assertEqual(foreign.exception.code, "SCOPE_DENIED")
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            cancel_evaluation_run(evaluation_id, run_id, {"reason": "No"})
        frappe.set_user(self.engineer)

        moved = update_evaluation_run(evaluation_id, run_id, {
            "date": "2026-12-17", "lot": "LOT-PLAN", "wafers": 4, "expectedModified": planned["modified"],
        })
        self.assertEqual([(r["id"], r["date"], r["status"], r["wafers"]) for r in moved["runs"]], [(run_id, "2026-12-17", "Planned", 4)])
        self.assertIn(f"Rescheduled Test Run {run_id} to 2026-12-17", moved["history"][0]["summary"])
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-10"))
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-17"))

        done = update_evaluation_run(evaluation_id, run_id, {
            "date": "2026-12-17", "lot": "LOT-PLAN", "wafers": 4, "capture": 96, "falsePositive": 1, "wph": 12,
            "summary": "Passed", "expectedModified": moved["modified"],
        })
        self.assertEqual([(r["id"], r["status"], r["capture"]) for r in done["runs"]], [(run_id, "Completed", 96.0)])
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-17"))
        with self.assertRaises(CrmApiException) as finished:
            update_evaluation_run(evaluation_id, run_id, {"date": "2026-12-18", "lot": "LOT-PLAN", "wafers": 4, "expectedModified": done["modified"]})
        self.assertEqual(finished.exception.code, "INVALID_TRANSITION")

    def test_cancelled_run_keeps_its_record_and_demo_stays_in_plan(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        planned = self._planned_run(evaluation_id)
        run_id = planned["runs"][0]["id"]
        with self.assertRaises(CrmApiException) as reason:
            cancel_evaluation_run(evaluation_id, run_id, {"reason": " "})
        self.assertEqual(reason.exception.code, "VALIDATION_ERROR")
        cancelled = cancel_evaluation_run(evaluation_id, run_id, {"reason": "Customer wafers delayed", "expectedModified": planned["modified"]})
        self.assertEqual([(r["id"], r["status"], r["summary"]) for r in cancelled["runs"]], [(run_id, "Cancelled", "Customer wafers delayed")])
        self.assertEqual(cancelled["wafers"], 0)
        self.assertEqual(cancelled["history"][0]["summary"], f"Cancelled Test Run {run_id}: Customer wafers delayed")
        self.assertIn(evaluation_id, self._plan_test_ids("2026-12-10"))
        with self.assertRaises(CrmApiException) as again:
            cancel_evaluation_run(evaluation_id, run_id, {"reason": "Twice", "expectedModified": cancelled["modified"]})
        self.assertEqual(again.exception.code, "INVALID_TRANSITION")

    def test_plan_reads_every_source_with_one_counting_rule(self):
        evaluation_id = self.request["evaluationId"]
        opportunity_id = self.request["opportunityId"]
        frappe.set_user(self.engineer)
        run_id = self._planned_run(evaluation_id)["runs"][0]["id"]
        frappe.set_user(self.sales)
        visit = create_visit({"accountId": self.account, "opportunityId": opportunity_id, "subject": "Plan visit",
                              "date": "2026-12-13", "type": "On-site", "owner": self.sales, "objective": "Agree the test scope"})
        due = create_opportunity_action(opportunity_id, {"title": "Confirm budget", "owner": self.sales, "due": "2026-12-09", "status": "Open"})
        late = create_opportunity_action(opportunity_id, {"title": "Send the site survey", "owner": self.sales, "due": "2026-11-27", "status": "Open"})
        frappe.set_user(self.other_sales)
        advance_opportunity_fixture(get_strategy_opportunity(self.foreign_request["opportunityId"]), CUSTOMER_BUDGET_APPROVED)

        frappe.set_user(self.manager)
        query = {"period": "month", "anchor": "2026-12-10", "sales": self.sales}
        plan = cockpit.get_plan(query)
        self.assertEqual(plan["period"], {"kind": "month", "start": "2026-12-01", "end": "2026-12-31",
                                          "previousAnchor": "2026-11-01", "nextAnchor": "2027-01-01"})

        def listed(metric, **scope):
            return cockpit.get_plan_details({**query, **scope, "metric": metric, "pageSize": 100})

        # The class shares one transaction, so other tests' records of the same owner may be present:
        # check this test's records, and that summary, sales row and details always agree.
        own = {"visits": visit["id"], "tests": evaluation_id, "actions": due["id"], "po": opportunity_id, "overdue": late["id"]}
        for metric, record in own.items():
            rows = listed(metric)
            self.assertIn(record, [row["id"] for row in rows["items"]], metric)
            summary = plan["overdue"] if metric == "overdue" else plan["summary"][metric]
            self.assertEqual(summary, {"value": rows["total"], "state": "ready", "reason": None}, metric)
        self.assertEqual([row["id"] for row in plan["sales"]], [self.sales])
        self.assertEqual({key: plan["sales"][0][key] for key in plan["summary"]}, plan["summary"])
        self.assertEqual([(row["name"], row["activities"]["value"]) for row in plan["markets"]],
                         [("Frontend", sum(plan["summary"][key]["value"] for key in ("visits", "tests", "actions")))])
        self.assertNotIn(late["id"], [row["id"] for row in listed("actions")["items"]])
        overdue = next(row for row in listed("overdue")["items"] if row["id"] == late["id"])
        self.assertEqual((overdue["date"], overdue["carryover"], overdue["kind"], overdue["opportunityId"]), ("2026-11-27", True, "actions", opportunity_id))
        # Stage 1 is counted, and its amount reported as missing rather than as 0.
        mine = next(row for row in listed("po")["items"] if row["id"] == opportunity_id)
        self.assertEqual((mine["amount"], mine["currency"], mine["date"], mine["probabilityLevel"]), (None, None, "2026-12-31", "pipeline"))
        self.assertTrue(plan["poAmountIncomplete"])

        everything = listed("all")
        self.assertEqual(everything["total"], sum(listed(metric)["total"] for metric in own))
        self.assertTrue(everything["items"][0]["carryover"])
        paged = [row for page in range(1, everything["total"] // 2 + 2)
                 for row in cockpit.get_plan_details({**query, "metric": "all", "page": page, "pageSize": 2})["items"]]
        self.assertEqual(paged, everything["items"])

        everyone = cockpit.get_plan({"period": "month", "anchor": "2026-12-10"})
        theirs = next(row for row in listed("po", sales=self.other_sales)["items"] if row["id"] == self.foreign_request["opportunityId"])
        self.assertEqual((theirs["amount"], theirs["currency"], theirs["status"]), ("200000.00", "CNY", CUSTOMER_BUDGET_APPROVED))
        self.assertIn({"currency": "CNY", "value": "200000.00"}, [money for row in everyone["sales"] if row["id"] == self.other_sales for money in row["poAmounts"]][:1])
        if os.environ.get("CRM_PLAN_SAMPLE"):
            print("PLAN_SAMPLE " + json.dumps({"get_plan": everyone, "get_plan_details": everything}, ensure_ascii=False))

        frappe.set_user(self.sales)
        mark_opportunity_lost(opportunity_id, {"lostReason": "Budget withdrawn"}, get_strategy_opportunity(opportunity_id)["modified"])
        frappe.set_user(self.manager)
        remaining = [row["id"] for row in listed("all")["items"]]
        self.assertTrue({visit["id"], evaluation_id} <= set(remaining))
        self.assertFalse({due["id"], late["id"], opportunity_id} & set(remaining))

    def test_deadline_skips_disabled_recipient_but_rolls_back_real_notification_failure(self):
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.manager)
        evaluation = get_evaluation(evaluation_id)
        frappe.db.set_value("User", self.engineer, "enabled", 0)
        try:
            updated = set_evaluation_test_run_deadline(evaluation_id, {
                "testRunDeadline": "2026-12-15", "expectedModified": evaluation["modified"],
            })
            self.assertEqual(updated["testRunDeadline"], "2026-12-15")
        finally:
            frappe.db.set_value("User", self.engineer, "enabled", 1)
        with patch("rayher_crm.services.notifications.create_notification", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                set_evaluation_test_run_deadline(evaluation_id, {
                    "testRunDeadline": "2026-12-16", "expectedModified": updated["modified"],
                })
        current = get_evaluation(evaluation_id)
        self.assertEqual((current["testRunDeadline"], current["modified"]), (updated["testRunDeadline"], updated["modified"]))

    def _workflow(self, request_id: str) -> dict:
        return next(item for item in list_demo_workflows() if item["id"] == request_id)

    def _set_progress(self, request_id: str, days_ago: int) -> None:
        at = frappe.utils.add_days(frappe.utils.now_datetime(), -days_ago)
        frappe.db.set_value("CRM Demo Request", request_id, "tracking", frappe.as_json({
            "lastProgressAt": to_iso_timestamp(at), "lastProgressSummary": "Progress", "lastProgressActor": self.manager,
        }))

    def test_demo_workflow_health_follows_the_dates_of_a_demo_in_progress(self):
        request_id, evaluation_id = self.request["id"], self.request["evaluationId"]
        today = frappe.utils.today()
        frappe.set_user(self.manager)

        frappe.db.set_value("CRM Demo Request", request_id, "customer_expected_date", frappe.utils.add_days(today, 30))
        self._set_progress(request_id, 0)
        self.assertEqual(self._workflow(request_id)["health"], {
            "level": "healthy", "reason": "今天有进展", "daysSinceProgress": 0, "daysToCustomerExpected": 30,
        })
        self.assertEqual(get_demo_workflow(request_id)["health"]["level"], "healthy")

        self._set_progress(request_id, 6)
        self.assertEqual(self._workflow(request_id)["health"], {
            "level": "stalled", "reason": "已连续 6 天无有效进展", "daysSinceProgress": 6, "daysToCustomerExpected": 30,
        })

        frappe.db.set_value("CRM Demo Request", request_id, "customer_expected_date", frappe.utils.add_days(today, -3))
        self.assertEqual(self._workflow(request_id)["health"], {
            "level": "critical", "reason": "客户预期已逾期 3 天", "daysSinceProgress": 6, "daysToCustomerExpected": -3,
        })

        # A Test Run deadline that has passed is red while the run is still due, and history once it is under review.
        frappe.db.set_value("CRM Demo Request", request_id, "customer_expected_date", frappe.utils.add_days(today, 30))
        self._set_progress(request_id, 0)
        frappe.db.set_value("CRM Evaluation", evaluation_id, "test_run_deadline", frappe.utils.add_days(today, -2))
        self.assertEqual(
            (self._workflow(request_id)["health"]["level"], self._workflow(request_id)["health"]["reason"]),
            ("critical", "Test Run DDL 已逾期 2 天"),
        )
        frappe.db.set_value("CRM Evaluation", evaluation_id, "status", "Customer Review")
        self.assertEqual(self._workflow(request_id)["health"]["level"], "healthy")

    def test_demo_workflow_health_without_tracking_falls_back_to_history_and_creation(self):
        request_id, evaluation_id = self.request["id"], self.request["evaluationId"]
        frappe.set_user(self.manager)
        frappe.db.set_value("CRM Demo Request", request_id, {
            "customer_expected_date": frappe.utils.add_days(frappe.utils.today(), 30), "tracking": None,
        })
        now = frappe.utils.now_datetime()

        def backdate(request_days: int, evaluation_days: int, created_days: int) -> None:
            frappe.db.sql(
                "UPDATE `tabCRM Demo Request History` SET `at` = %s WHERE `demo_request` = %s",
                (frappe.utils.add_days(now, -request_days), request_id),
            )
            frappe.db.sql(
                "UPDATE `tabCRM Evaluation History` SET `at` = %s WHERE `evaluation` = %s",
                (frappe.utils.add_days(now, -evaluation_days), evaluation_id),
            )
            frappe.db.sql(
                "UPDATE `tabCRM Demo Request` SET `creation` = %s WHERE `name` = %s",
                (frappe.utils.add_days(now, -created_days), request_id),
            )

        self.assertTrue(frappe.db.count("CRM Demo Request History", {"demo_request": request_id}))
        self.assertTrue(frappe.db.count("CRM Evaluation History", {"evaluation": evaluation_id}))
        # The newest history row counts, whichever record it is on.
        backdate(request_days=9, evaluation_days=6, created_days=12)
        self.assertEqual(self._workflow(request_id)["health"], {
            "level": "stalled", "reason": "已连续 6 天无有效进展", "daysSinceProgress": 6, "daysToCustomerExpected": 30,
        })
        backdate(request_days=2, evaluation_days=6, created_days=12)
        self.assertEqual(self._workflow(request_id)["health"]["reason"], "2 天内有进展")

        # Without any history the creation is all there is.
        frappe.db.delete("CRM Demo Request History", {"demo_request": request_id})
        frappe.db.delete("CRM Evaluation History", {"evaluation": evaluation_id})
        self.assertEqual(self._workflow(request_id)["health"]["daysSinceProgress"], 12)

    def test_demo_workflow_has_health_only_while_the_demo_is_under_way(self):
        request_id, evaluation_id = self.request["id"], self.request["evaluationId"]
        frappe.set_user(self.manager)
        frappe.db.set_value("CRM Demo Request", request_id, "customer_expected_date", frappe.utils.add_days(frappe.utils.today(), -3))
        self.assertEqual(self._workflow(request_id)["health"]["level"], "critical")

        # Returned or rejected requests are still being worked on.
        for status in ("Engineer Review", "Engineer Returned", "Manager Approval", "Manager Rejected"):
            frappe.db.set_value("CRM Demo Request", request_id, "status", status)
            self.assertEqual(self._workflow(request_id)["health"]["level"], "critical", status)
        frappe.db.set_value("CRM Demo Request", request_id, "status", "Converted")

        frappe.db.set_value("CRM Evaluation", evaluation_id, "status", "Accepted")
        archived = self._workflow(request_id)
        self.assertEqual(archived["archiveCategory"], "Completed")
        self.assertNotIn("health", archived)

        # A request is cancelled before it is converted, so it has no Evaluation.
        frappe.db.set_value("CRM Demo Request", request_id, {"status": "Cancelled", "evaluation": None})
        cancelled = self._workflow(request_id)
        self.assertEqual((cancelled["status"], cancelled["evaluation"]), ("Cancelled", None))
        self.assertNotIn("health", cancelled)

        # A draft that was never submitted is not under way either: it must not count as a customer-date risk.
        frappe.db.set_value("CRM Demo Request", request_id, "status", "Draft")
        draft = self._workflow(request_id)
        self.assertEqual((draft["status"], draft.get("stage")), ("Draft", None))
        self.assertNotIn("health", draft)

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
        # The service refuses a date in the past, so the test must not name a fixed one.
        deadline = add_days(today(), 45)
        with self.assertRaises(CrmApiException) as invalid_date:
            set_evaluation_test_run_deadline(evaluation_id, {"testRunDeadline": "2026-02-30"})
        self.assertEqual(invalid_date.exception.code, "VALIDATION_ERROR")
        evaluation = set_evaluation_test_run_deadline(
            evaluation_id, {"testRunDeadline": deadline, "expectedModified": evaluation["modified"]},
        )
        self.assertEqual(evaluation["testRunDeadline"], deadline)
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

    # A Demo Test can be terminated mid-flight: it ends as Rejected with its reason (#73).

    OPEN_STATUSES = (
        "Requested", "Scope Confirmed", "Sample Received", "Scheduled", "Testing",
        "Analysis", "Internal Review", "Customer Review",
    )

    def _evaluation_at(self, status: str, label: str = "Stop") -> tuple[dict, dict]:
        """A fresh Demo Test brought to ``status`` through the real workflow steps."""
        _account, request = self._approved_source(f"{label} {status}", self.sales, self.engineer)
        evaluation_id = request["evaluationId"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)
        steps = ("Requested", "Scope Confirmed", "Sample Received", "Scheduled", "Testing", "Internal Review", "Customer Review")
        # Analysis is a legacy post-testing step the workflow no longer enters.
        target = "Internal Review" if status == "Analysis" else status
        for step in steps[1:steps.index(target) + 1]:
            if step == "Internal Review":
                add_evaluation_run(evaluation_id, {
                    "date": "2026-12-11", "lot": "LOT-STOP", "wafers": 1,
                    "capture": 96, "falsePositive": 1, "wph": 12, "summary": "Passed",
                    "expectedModified": current["modified"],
                })
                release_demo_test_report(
                    evaluation_id,
                    {"file_name": "results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
                    {"file_name": "customer-results.csv", "mime_type": "text/csv", "content": b"metric,value\ncapture,96\n"},
                    scanner=CleanScanner(), expected_round=current["testRound"],
                )
                current = get_evaluation(evaluation_id)
            current = update_evaluation_status(evaluation_id, {"status": step}, current["modified"])
        if status == "Analysis":
            frappe.db.set_value("CRM Evaluation", evaluation_id, "status", "Analysis")
            current = get_evaluation(evaluation_id)
        self.assertEqual(current["status"], status)
        return request, current

    def _termination_notices(self, evaluation_id: str) -> list:
        return frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Evaluation", "source_name": evaluation_id,
                     "title": ["in", ["Demo Test terminated", "Demo Test moved to Rejected"]]},
            fields=["recipient_user", "title", "message", "route"], order_by="recipient_user asc",
        )

    def _undo_when_done(self) -> None:
        """Undo what this test body writes once it ends, leaving only what setUp created.

        FrappeTestCase rolls back once, after the whole class, so an extra Demo source or an
        Opportunity moved on by one test is still there for every test that runs after it.
        The name is unique, so the services' own savepoints inside the body never replace it.
        """
        savepoint = f"crm_test_body_{frappe.generate_hash(length=12)}"
        frappe.db.savepoint(savepoint)
        self.addCleanup(frappe.db.rollback, save_point=savepoint)

    def test_terminate_evaluation_from_testing_requires_reason_and_does_not_move_opportunity(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        opportunity_id = self.request["opportunityId"]
        frappe.set_user(self.engineer)
        evaluation = get_evaluation(evaluation_id)
        for branch in ("wafer", "test"):
            evaluation = complete_evaluation_preparation(evaluation_id, branch, evaluation["modified"])
        evaluation = update_evaluation_status(evaluation_id, {"status": "Testing"}, evaluation["modified"])
        before = frappe.db.get_value("CRM Opportunity", opportunity_id, ["stage", "probability", "probability_level"])

        with self.assertRaises(CrmApiException) as missing_reason:
            terminate_evaluation(evaluation["id"], {"reason": ""}, evaluation["modified"])
        self.assertEqual(missing_reason.exception.code, "VALIDATION_ERROR")

        terminated = terminate_evaluation(evaluation["id"], {"reason": "Customer paused the project"}, evaluation["modified"])
        self.assertEqual(terminated["status"], "Rejected")
        self.assertEqual(terminated["terminationReason"], "Customer paused the project")
        self.assertEqual(terminated["acceptance"], evaluation["acceptance"])

        after = frappe.db.get_value("CRM Opportunity", opportunity_id, ["stage", "probability", "probability_level"])
        self.assertEqual(after, before)

        with self.assertRaises(CrmApiException) as already_terminal:
            terminate_evaluation(evaluation["id"], {"reason": "again"}, terminated["modified"])
        self.assertEqual(already_terminal.exception.code, "INVALID_TRANSITION")

        # The Sales owner is told it was terminated and why, not that the customer rejected it;
        # the Engineer who terminated it is not told about their own action.
        self.assertEqual(
            [(row.recipient_user, row.title, row.message, row.route) for row in self._termination_notices(evaluation_id)],
            [(
                self.sales, "Demo Test terminated",
                f"{evaluation['title']}: terminated in Testing. Reason: Customer paused the project",
                f"/demo-workflow/{self.request['id']}?tab=information",
            )],
        )
        # The source request stays Converted; only its progress note records the termination.
        request = frappe.db.get_value("CRM Demo Request", self.request["id"], ["status", "tracking"], as_dict=True)
        self.assertEqual(
            (request.status, frappe.parse_json(request.tracking)["lastProgressSummary"]),
            ("Converted", "Demo Test terminated: Customer paused the project"),
        )

    def test_a_recipient_who_cannot_be_notified_does_not_block_a_termination(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        # The Sales owner has left. The Manager terminates; the Engineer who owns the Demo is still told.
        frappe.db.set_value("User", self.sales, "enabled", 0)
        frappe.set_user(self.manager)
        evaluation = get_evaluation(evaluation_id)
        terminated = terminate_evaluation(evaluation_id, {"reason": "Customer paused the project"}, evaluation["modified"])
        self.assertEqual((terminated["status"], terminated["terminationReason"]), ("Rejected", "Customer paused the project"))
        self.assertEqual([row.recipient_user for row in self._termination_notices(evaluation_id)], [self.engineer])
        self.assertEqual(frappe.db.get_value("CRM Evaluation", evaluation_id, "termination_reason"), "Customer paused the project")

    def test_a_recipient_with_two_crm_roles_does_not_block_a_status_change(self):
        # The cached role set outlives the rollback below, so it is dropped once that has run.
        self.addCleanup(frappe.clear_cache, user=self.sales)
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        # Two CRM roles make the user's role ambiguous, so no notice can be sent; the change still happens.
        self._user(self.sales, "CRM Engineer")
        frappe.set_user(self.engineer)
        evaluation = get_evaluation(evaluation_id)
        moved = update_evaluation_status(evaluation_id, {"status": "Scope Confirmed"}, evaluation["modified"])
        self.assertEqual(moved["status"], "Scope Confirmed")
        self.assertEqual(frappe.db.count("CRM Notification Event", {
            "source_doctype": "CRM Evaluation", "source_name": evaluation_id, "recipient_user": self.sales,
        }), 0)

    def test_a_disabled_evaluation_owner_does_not_block_a_deadline_change(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        frappe.db.set_value("User", self.engineer, "enabled", 0)
        frappe.set_user(self.manager)
        evaluation = get_evaluation(evaluation_id)
        deadline = add_days(today(), 30)
        updated = set_evaluation_test_run_deadline(
            evaluation_id, {"testRunDeadline": deadline, "expectedModified": evaluation["modified"]},
        )
        self.assertEqual(updated["testRunDeadline"], deadline)
        # The change is fully recorded; only the notice to the disabled owner is skipped.
        self.assertTrue(frappe.db.exists("CRM Evaluation History", {
            "evaluation": evaluation_id, "event_type": "Deadline", "to_value": deadline,
        }))
        self.assertEqual(frappe.db.count("CRM Notification Event", {
            "source_doctype": "CRM Evaluation", "source_name": evaluation_id, "recipient_user": self.engineer,
            "title": "Demo Test deadline updated",
        }), 0)

    def test_every_open_stage_can_be_terminated_keeping_its_history_and_the_opportunity(self):
        self._undo_when_done()
        fields =["stage", "probability", "probability_level", "modified"]
        for status in self.OPEN_STATUSES:
            with self.subTest(status=status):
                request, current = self._evaluation_at(status)
                opportunity_id = request["opportunityId"]
                opportunity = frappe.db.get_value("CRM Opportunity", opportunity_id, fields, as_dict=True)
                stage_moves = frappe.db.count("CRM Opportunity Stage History", {"opportunity": opportunity_id})
                reason = f"Customer paused the project in {status}"

                terminated = terminate_evaluation(current["id"], {"reason": f"  {reason}  "}, current["modified"])

                self.assertEqual(
                    (terminated["status"], terminated["terminationReason"], terminated["acceptance"]),
                    ("Rejected", reason, current["acceptance"]),
                )
                self.assertEqual(
                    {key: terminated["history"][0][key] for key in ("eventType", "from", "to", "summary", "actor")},
                    {
                        "eventType": "Status", "from": status, "to": "Rejected",
                        "summary": f"Demo Test terminated: {reason}", "actor": self.engineer,
                    },
                )
                # Earlier history, runs and reports stay exactly as they were.
                self.assertEqual(terminated["history"][1:], current["history"])
                self.assertEqual(
                    (terminated["runs"], terminated["reportStatus"]), (current["runs"], current["reportStatus"]),
                )
                self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity_id, fields, as_dict=True), opportunity)
                self.assertEqual(
                    frappe.db.count("CRM Opportunity Stage History", {"opportunity": opportunity_id}), stage_moves,
                )

                frappe.set_user(self.manager)
                workflow = get_demo_workflow(request["id"])
                self.assertEqual(
                    (workflow["status"], workflow["terminationReason"], workflow["archiveCategory"], workflow.get("stage")),
                    ("Rejected", reason, "Completed", None),
                )
                # The conclusion keeps the customer's acceptance; no customer verdict is invented.
                self.assertEqual(workflow["conclusion"]["status"], current["acceptance"])

    def test_termination_needs_a_reason_scope_and_the_current_version_and_writes_once(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)

        def writes():
            return (
                frappe.db.get_value("CRM Evaluation", evaluation_id, ["status", "termination_reason", "modified"]),
                frappe.db.count("CRM Evaluation History", {"evaluation": evaluation_id}),
                len(self._termination_notices(evaluation_id)),
            )

        untouched = writes()
        for payload in ({}, {"reason": ""}, {"reason": "   "}):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as missing:
                terminate_evaluation(evaluation_id, payload, current["modified"])
            self.assertEqual((missing.exception.code, missing.exception.field_errors), ("VALIDATION_ERROR", {"reason": "Required"}))
        with self.assertRaises(CrmApiException) as too_long:
            terminate_evaluation(evaluation_id, {"reason": "x" * 1001}, current["modified"])
        self.assertEqual((too_long.exception.code, too_long.exception.field_errors), ("VALIDATION_ERROR", {"reason": "Too long"}))
        for version, code in (("2000-01-01T00:00:00Z", "VERSION_CONFLICT"), (None, "VALIDATION_ERROR")):
            with self.subTest(version=version), self.assertRaises(CrmApiException) as refused:
                terminate_evaluation(evaluation_id, {"reason": "Customer stopped"}, version)
            self.assertEqual(refused.exception.code, code)
        with self.assertRaises(CrmApiException) as missing_demo:
            terminate_evaluation("CRM-EVAL-99999", {"reason": "Customer stopped"}, current["modified"])
        self.assertEqual(missing_demo.exception.code, "NOT_FOUND")
        # evaluation:write and the Evaluation's scope decide who may terminate, as for any other write here.
        frappe.set_user(self.other_engineer)
        with self.assertRaises(CrmApiException) as foreign:
            terminate_evaluation(evaluation_id, {"reason": "Not my Demo"}, current["modified"])
        self.assertEqual(foreign.exception.code, "SCOPE_DENIED")
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            terminate_evaluation(evaluation_id, {"reason": "Sales cannot write a Demo Test"}, current["modified"])
        self.assertEqual(writes(), untouched)

        # The longest allowed reason is kept whole; a Manager may terminate as well.
        frappe.set_user(self.manager)
        reason = "r" * 1000
        terminated = terminate_evaluation(evaluation_id, {"reason": f" {reason} "}, current["modified"])
        self.assertEqual((terminated["status"], terminated["terminationReason"]), ("Rejected", reason))
        self.assertEqual(terminated["history"][0]["summary"], f"Demo Test terminated: {reason}")
        # The terminal recipients are unchanged (Sales owner and assigned Engineer), and a notice
        # stays within the notification limit however long the reason is.
        notices = self._termination_notices(evaluation_id)
        self.assertEqual(sorted(row.recipient_user for row in notices), sorted([self.sales, self.engineer]))
        for row in notices:
            self.assertEqual((row.title, len(row.message), row.message[-1]), ("Demo Test terminated", 1000, "…"))

        # A repeated submit is refused whichever version it carries, and writes nothing a second time.
        done = writes()
        for version, code in ((terminated["modified"], "INVALID_TRANSITION"), (current["modified"], "VERSION_CONFLICT")):
            with self.subTest(repeat=code), self.assertRaises(CrmApiException) as repeated:
                terminate_evaluation(evaluation_id, {"reason": "Again"}, version)
            self.assertEqual(repeated.exception.code, code)
        self.assertEqual(writes(), done)

    def test_a_terminated_demo_leaves_active_counts_plan_and_ddl_reminders(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        deadline = add_days(today(), 7)
        # A Demo that keeps running is the control for every count below.
        _request, running = self._evaluation_at("Testing", label="Running")
        running = set_evaluation_test_run_deadline(
            running["id"], {"testRunDeadline": deadline, "expectedModified": running["modified"]},
        )
        planned = self._planned_run(evaluation_id, deadline)
        current = set_evaluation_test_run_deadline(
            evaluation_id, {"testRunDeadline": deadline, "expectedModified": planned["modified"]},
        )
        self.assertTrue({evaluation_id, running["id"]} <= set(self._plan_test_ids(deadline)))
        frappe.set_user(self.sales)
        active_demos = get_account_360(self.account)["summary"]["activeDemos"]
        active_evaluations = get_dashboard({"range": "month"})["kpis"]["activeEvaluations"]

        frappe.set_user(self.engineer)
        terminated = terminate_evaluation(evaluation_id, {"reason": "Customer stopped the evaluation"}, current["modified"])
        # The planned run stays on record as it was; Plan and the reminders read the Evaluation's
        # status, and only Completed runs are counted as tests done.
        self.assertEqual([run["status"] for run in terminated["runs"]], ["Planned"])

        plan_ids = set(self._plan_test_ids(deadline))
        self.assertNotIn(evaluation_id, plan_ids)
        self.assertIn(running["id"], plan_ids)
        frappe.set_user(self.sales)
        self.assertEqual(get_account_360(self.account)["summary"]["activeDemos"], active_demos - 1)
        self.assertEqual(get_dashboard({"range": "month"})["kpis"]["activeEvaluations"], active_evaluations - 1)

        frappe.set_user("Administrator")
        send_ddl_reminders()

        def reminders(name: str) -> int:
            return frappe.db.count("CRM Notification Event", {
                "source_doctype": "CRM Evaluation", "source_name": name, "title": ["like", "%DDL%"],
            })

        # Both Test Run deadlines are 7 days away; only the Demo still running is reminded.
        self.assertEqual(reminders(evaluation_id), 0)
        self.assertGreater(reminders(running["id"]), 0)

        # A terminated Demo's runs can no longer change.
        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as locked:
            cancel_evaluation_run(evaluation_id, terminated["runs"][0]["id"], {
                "reason": "Too late", "expectedModified": terminated["modified"],
            })
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")

    def test_a_failed_termination_rolls_back_status_reason_and_history_together(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        request_id = self.request["id"]
        frappe.set_user(self.engineer)
        planned = self._planned_run(evaluation_id)
        history = frappe.db.count("CRM Evaluation History", {"evaluation": evaluation_id})
        request = frappe.db.get_value("CRM Demo Request", request_id, ["modified", "tracking"], as_dict=True)

        # The notice is the last write, so the status, reason, history and request note are already written.
        with patch("rayher_crm.services.notifications.create_notification", side_effect=RuntimeError("notice failed")):
            with self.assertRaisesRegex(RuntimeError, "notice failed"):
                terminate_evaluation(evaluation_id, {"reason": "Customer stopped"}, planned["modified"])

        after = get_evaluation(evaluation_id)
        self.assertEqual((after["status"], after["terminationReason"], after["modified"]), ("Testing", "", planned["modified"]))
        self.assertEqual(frappe.db.count("CRM Evaluation History", {"evaluation": evaluation_id}), history)
        self.assertEqual(
            frappe.db.get_value("CRM Demo Request", request_id, ["modified", "tracking"], as_dict=True), request,
        )
        self.assertEqual(self._termination_notices(evaluation_id), [])
        # Nothing moved the version, so the same request succeeds once the failure is gone.
        terminated = terminate_evaluation(evaluation_id, {"reason": "Customer stopped"}, planned["modified"])
        self.assertEqual((terminated["status"], terminated["terminationReason"]), ("Rejected", "Customer stopped"))

    def test_archived_and_historically_rejected_demos_keep_their_meaning(self):
        self._undo_when_done()
        # An archived Demo Test has already ended and cannot be terminated.
        archived = self._in_customer_review(self.foreign_request, self.other_engineer)
        archived = update_evaluation_status(
            archived["id"], {"status": "Accepted", "customerComment": "Customer signed off"}, archived["modified"],
        )
        with self.assertRaises(CrmApiException) as ended:
            terminate_evaluation(archived["id"], {"reason": "Too late"}, archived["modified"])
        self.assertEqual(ended.exception.code, "INVALID_TRANSITION")
        after = get_evaluation(archived["id"])
        self.assertEqual(
            (after["status"], after["acceptance"], after["terminationReason"], after["modified"]),
            ("Accepted", "Accepted", "", archived["modified"]),
        )

        # A Demo rejected under the old flow carries no reason and still reads as a rejection.
        evaluation_id = self.request["evaluationId"]
        frappe.set_user("Administrator")
        frappe.db.set_value("CRM Evaluation", evaluation_id, {"status": "Rejected", "acceptance": "Rejected"})
        frappe.set_user(self.engineer)
        historical = get_evaluation(evaluation_id)
        self.assertEqual(
            (historical["status"], historical["acceptance"], historical["terminationReason"]), ("Rejected", "Rejected", ""),
        )
        with self.assertRaises(CrmApiException) as rejected:
            terminate_evaluation(evaluation_id, {"reason": "Relabel it"}, historical["modified"])
        self.assertEqual(rejected.exception.code, "INVALID_TRANSITION")
        self.assertEqual(get_evaluation(evaluation_id)["modified"], historical["modified"])

        frappe.set_user(self.manager)
        workflows = {item["id"]: item for item in list_demo_workflows()}
        self.assertEqual(
            {key: workflows[self.foreign_request["id"]][key] for key in ("status", "terminationReason")},
            {"status": "Accepted", "terminationReason": ""},
        )
        self.assertEqual(workflows[self.foreign_request["id"]]["conclusion"]["status"], "Accepted")
        self.assertEqual(
            {key: workflows[self.request["id"]][key] for key in ("status", "terminationReason")},
            {"status": "Rejected", "terminationReason": ""},
        )
        self.assertEqual(workflows[self.request["id"]]["conclusion"]["status"], "Rejected")

    def test_terminate_endpoint_takes_the_reason_and_the_version(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)
        refused = evaluations_api.terminate_evaluation(evaluation_id, " ", current["modified"])
        self.assertEqual(frappe.local.response["http_status_code"], 422)
        self.assertEqual(
            (refused["error"]["code"], refused["error"]["fieldErrors"]), ("VALIDATION_ERROR", {"reason": "Required"}),
        )
        done = evaluations_api.terminate_evaluation(evaluation_id, "Customer stopped", current["modified"])
        self.assertEqual(
            (done["data"]["id"], done["data"]["status"], done["data"]["terminationReason"]),
            (evaluation_id, "Rejected", "Customer stopped"),
        )

    def test_a_terminated_demo_takes_no_new_test_run_deadline(self):
        self._undo_when_done()
        evaluation_id = self.request["evaluationId"]
        request_id = self.request["id"]
        frappe.set_user(self.engineer)
        current = get_evaluation(evaluation_id)
        terminated = terminate_evaluation(evaluation_id, {"reason": "Customer stopped the evaluation"}, current["modified"])

        def writes():
            return (
                frappe.db.get_value("CRM Evaluation", evaluation_id, ["modified", "test_run_deadline"]),
                frappe.db.count("CRM Evaluation History", {"evaluation": evaluation_id}),
                frappe.db.get_value("CRM Demo Request", request_id, ["modified", "tracking"]),
                frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Evaluation", "source_name": evaluation_id}),
            )

        ended = writes()
        # Set by a Manager, a deadline would also notify the assigned Engineer.
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as refused:
            set_evaluation_test_run_deadline(evaluation_id, {
                "testRunDeadline": add_days(today(), 7), "expectedModified": terminated["modified"],
            })
        self.assertEqual(refused.exception.code, "INVALID_TRANSITION")
        self.assertEqual(writes(), ended)
        after = get_evaluation(evaluation_id)
        self.assertEqual(
            (after["status"], after["testRunDeadline"], after["modified"], after["history"][0]["summary"]),
            ("Rejected", "", terminated["modified"], "Demo Test terminated: Customer stopped the evaluation"),
        )
        # The source request still ends on the termination note.
        tracking = frappe.parse_json(frappe.db.get_value("CRM Demo Request", request_id, "tracking"))
        self.assertEqual(tracking["lastProgressSummary"], "Demo Test terminated: Customer stopped the evaluation")

    TIMELINE_KEYS = (
        "sales-preparation", "engineer-review", "manager-approval", "wafer-preparation",
        "test-preparation", "test-execution", "internal-review", "customer-review",
    )

    def _timeline(self, request_id: str) -> dict:
        frappe.set_user(self.manager)
        steps = get_demo_workflow(request_id)["projectTimeline"]
        # The projection keeps its shape; only states and dates tell a termination apart.
        self.assertEqual([step["key"] for step in steps], list(self.TIMELINE_KEYS))
        self.assertTrue(all(set(step) >= {"key", "label", "state", "date"} for step in steps))
        return {step["key"]: step for step in steps}

    def test_a_terminated_demo_timeline_marks_only_the_steps_it_reached(self):
        self._undo_when_done()
        approved = ("Done", "Done", "Done")
        expected = {
            # (states in TIMELINE_KEYS order, (test-execution, internal-review, customer-review) dates)
            "Requested": (approved + ("Current", "Current", "Waiting", "Waiting", "Waiting"), ("", "", "")),
            "Testing": (approved + ("Done", "Done", "Current", "Waiting", "Waiting"), ("2026-12-11", "", "")),
            "Customer Review": (("Done",) * 7 + ("Current",), ("2026-12-11", "2026-12-11", None)),
        }
        for status, (states, dates) in expected.items():
            with self.subTest(status=status):
                request, current = self._evaluation_at(status, label="Timeline")
                if status == "Testing":
                    # A run completed before the stop dates Test Execution, not the review after it.
                    current = add_evaluation_run(current["id"], {
                        "date": "2026-12-11", "lot": "LOT-STOPPED", "wafers": 1,
                        "capture": 96, "falsePositive": 1, "wph": 12, "summary": "Passed",
                        "expectedModified": current["modified"],
                    })
                terminated = terminate_evaluation(current["id"], {"reason": f"Stopped in {status}"}, current["modified"])
                timeline = self._timeline(request["id"])
                self.assertEqual(tuple(timeline[key]["state"] for key in self.TIMELINE_KEYS), states)
                # Customer Review is dated only once it was reached, and never with the expected date.
                self.assertEqual(
                    tuple(timeline[key]["date"] for key in ("test-execution", "internal-review", "customer-review")),
                    dates[:2] + (terminated["modified"] if dates[2] is None else dates[2],),
                )

        # Accepted and historical Rejected records keep today's projection: every step done and
        # Customer Review dated when the record ended.
        request, current = self._evaluation_at("Customer Review", label="Timeline Archived")
        archived = update_evaluation_status(
            current["id"], {"status": "Accepted", "customerComment": "Customer signed off"}, current["modified"],
        )
        frappe.set_user("Administrator")
        frappe.db.set_value("CRM Evaluation", self.request["evaluationId"], {"status": "Rejected", "acceptance": "Rejected"})
        frappe.set_user(self.manager)
        historical = get_evaluation(self.request["evaluationId"])
        self.assertEqual((historical["status"], historical["terminationReason"]), ("Rejected", ""))
        for request_id, ended in ((request["id"], archived), (self.request["id"], historical)):
            with self.subTest(ended=ended["status"]):
                timeline = self._timeline(request_id)
                self.assertEqual(tuple(timeline[key]["state"] for key in self.TIMELINE_KEYS), ("Done",) * 8)
                self.assertEqual(timeline["customer-review"]["date"], ended["modified"])
