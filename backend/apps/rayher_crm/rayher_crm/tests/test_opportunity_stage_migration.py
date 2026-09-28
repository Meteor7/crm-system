from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.patches.v1_0 import migrate_opportunity_seven_stages
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import create_strategy_opportunity, mark_opportunity_lost
from rayher_crm.services.sites import create_site
from rayher_crm.setup import opportunity_stage_migration as migration
from rayher_crm.setup.opportunity_stage_migration import Evidence, Snapshot, plan_opportunity, validate_override


def _at(day: int) -> datetime:
    return datetime(2026, 8, day, 9, 0, 0)


class TestOpportunityStagePlanner(FrappeTestCase):
    def _snapshot(self, stage: str, **evidence) -> Snapshot:
        return Snapshot(name="CRM-OPP-TEST", stage=stage, created_at=_at(1), **evidence)

    def test_legacy_stages_and_aliases_map_to_milestones(self):
        expected = {
            "需求发现": "qualified_opportunity",
            "Wafer Demo确认": "qualified_opportunity",
            "技术确认": "qualified_opportunity",
            "预算审批": "demo_done",
            "设备规格确认": "customer_budget_approved",
            "报价": "rfq_validated",
            "商务谈判": "rfq_validated",
            "采购流程": "quotation_sent",
            "Won": "po_received",
            "Closed Won": "po_received",
            "Lost": "lost",
            "Closed Lost": "lost",
        }
        for legacy, stage in expected.items():
            with self.subTest(legacy=legacy):
                self.assertEqual(plan_opportunity(self._snapshot(legacy)).stage, stage)
        reviewed = plan_opportunity(self._snapshot("Wafer Demo确认", has_customer_review=True))
        self.assertEqual(reviewed.stage, "demo_done")
        self.assertIn("demo_stage_reviewed", reviewed.warnings)
        with self.assertRaises(ValueError):
            plan_opportunity(self._snapshot("qualified_opportunity"))

    def test_evidence_rows_stop_below_the_current_stage(self):
        plan = plan_opportunity(self._snapshot(
            "采购流程",
            source_lead="CRM-LEAD-00001",
            has_customer_review=True,
            customer_review=Evidence(_at(3), "evidence", "Evaluation E1 进入客户评审", "CRM Evaluation", "E1"),
            budget_confirmed=Evidence(_at(5), "evidence", "旧历史中手动推进到 设备规格确认"),
            rfq_approved=Evidence(_at(7), "evidence", "RFQ R1 经理批准", "CRM RFQ", "R1"),
            quotation_published=Evidence(_at(9), "evidence", "报价版本 Q1 首次发布", "CRM Quotation Version", "Q1"),
            stage_arrival=Evidence(_at(10), "evidence", "旧历史中进入 采购流程 的时间"),
        ))
        self.assertEqual(
            [(row.to_stage, row.event, row.reached_at, row.basis) for row in plan.rows],
            [
                ("qualified_opportunity", "lead_converted", _at(1), "evidence"),
                ("demo_done", "demo_customer_review", _at(3), "evidence"),
                ("customer_budget_approved", "budget_confirmed", _at(5), "evidence"),
                ("rfq_validated", "rfq_approved", _at(7), "evidence"),
                ("quotation_sent", "migration", _at(10), "evidence"),
            ],
        )
        self.assertEqual((plan.rows[0].reference_doctype, plan.rows[0].reference_name), ("Lead", "CRM-LEAD-00001"))
        self.assertEqual(plan.stage_changed_at, _at(10))
        self.assertTrue(plan.rows[-1].reason.startswith("旧阶段 采购流程"))
        self.assertEqual(plan.warnings, [])

    def test_lost_keeps_the_stage_it_was_lost_at(self):
        plan = plan_opportunity(self._snapshot(
            "Lost",
            rfq_approved=Evidence(_at(7), "evidence", "RFQ R1 经理批准", "CRM RFQ", "R1"),
            quotation_published=Evidence(_at(9), "evidence", "报价版本 Q1 首次发布"),
            lost=Evidence(_at(12), "evidence", "旧历史中标记 Lost"),
            lost_by="sales@example.invalid",
            lost_from_stage="报价",
        ))
        self.assertEqual(
            (plan.stage, plan.lost_at_stage, plan.lost_at, plan.lost_by, plan.stage_changed_at),
            ("lost", "rfq_validated", _at(12), "sales@example.invalid", _at(12)),
        )
        self.assertEqual(
            [(row.to_stage, row.event) for row in plan.rows],
            [("qualified_opportunity", "created"), ("rfq_validated", "rfq_approved"), ("lost", "migration")],
        )

        unknown = plan_opportunity(self._snapshot("Closed Lost"))
        self.assertEqual((unknown.stage, unknown.lost_at_stage), ("lost", ""))
        self.assertEqual([row.to_stage for row in unknown.rows], ["qualified_opportunity", "lost"])
        self.assertEqual((unknown.rows[-1].reached_at, unknown.rows[-1].basis), (None, "unknown"))
        self.assertEqual(set(unknown.warnings), {"lost_at_stage_unknown", "arrival_time_unknown"})

    def test_a_customer_review_after_the_loss_does_not_move_the_lost_stage(self):
        def lost_from_demo(review_day: int) -> Snapshot:
            return self._snapshot(
                "Lost",
                has_customer_review=True,
                customer_review=Evidence(_at(review_day), "evidence", "Evaluation E1 进入客户评审", "CRM Evaluation", "E1"),
                lost=Evidence(_at(12), "evidence", "旧历史中标记 Lost"),
                lost_from_stage="Wafer Demo确认",
            )

        # The Evaluation entered Customer Review three days after the loss: the deal was lost
        # before the Demo was reviewed.
        after = plan_opportunity(lost_from_demo(15))
        self.assertEqual((after.stage, after.lost_at_stage, after.lost_at), ("lost", "qualified_opportunity", _at(12)))
        self.assertEqual([row.to_stage for row in after.rows], ["qualified_opportunity", "lost"])
        self.assertEqual(after.warnings, [])

        before = plan_opportunity(lost_from_demo(3))
        self.assertEqual((before.stage, before.lost_at_stage), ("lost", "demo_done"))
        self.assertEqual([row.to_stage for row in before.rows], ["qualified_opportunity", "demo_done", "lost"])

    def test_upper_bounds_fill_in_when_the_arrival_was_not_recorded(self):
        budget = plan_opportunity(self._snapshot(
            "设备规格确认",
            rfq_created=Evidence(_at(6), "upper_bound", "RFQ R1 创建（预算批准不晚于此）", "CRM RFQ", "R1"),
        ))
        self.assertEqual((budget.rows[-1].reached_at, budget.rows[-1].basis), (_at(6), "upper_bound"))
        won = plan_opportunity(self._snapshot(
            "Won",
            first_booking=Evidence(_at(14), "upper_bound", "Booking B1 创建（收到 PO 不晚于此）", "CRM Booking", "B1"),
            has_live_booking=True,
        ))
        self.assertEqual(
            (won.stage_changed_at, won.rows[-1].basis, won.rows[-1].reference_name, won.warnings),
            (_at(14), "upper_bound", "B1", []),
        )
        accepted = plan_opportunity(self._snapshot(
            "预算审批", stage_arrival=Evidence(_at(8), "evidence", "旧历史中进入 预算审批 的时间"),
        ))
        self.assertEqual(
            (accepted.stage, accepted.rows[-1].reached_at, accepted.rows[-1].basis), ("demo_done", _at(8), "upper_bound"),
        )
        booked_early = plan_opportunity(self._snapshot("采购流程", has_live_booking=True))
        self.assertIn("live_booking_before_po_received", booked_early.warnings)

    def test_sales_overrides_win_and_are_validated(self):
        corrected = plan_opportunity(
            self._snapshot("需求发现"),
            validate_override("CRM-OPP-TEST", {"stage": "demo_done", "note": "客户已看过 Demo"}),
        )
        self.assertEqual(corrected.stage, "demo_done")
        self.assertIn("override", corrected.warnings)
        self.assertIn("销售修正：客户已看过 Demo", corrected.rows[-1].reason)
        self.assertEqual(corrected.rows[-1].basis, "unknown")

        lost = plan_opportunity(
            self._snapshot("报价"), validate_override("CRM-OPP-TEST", {"stage": "lost", "note": "客户取消项目"}),
        )
        self.assertEqual((lost.stage, lost.lost_at_stage), ("lost", "rfq_validated"))
        moved_loss = plan_opportunity(
            self._snapshot("Lost", lost_from_stage="报价"),
            validate_override("CRM-OPP-TEST", {"lostAtStage": "quotation_sent"}),
        )
        self.assertEqual(moved_loss.lost_at_stage, "quotation_sent")
        for invalid in ({"stage": "internal_validation"}, {"stage": "Won"}, {"lostAtStage": "po_received"}, "demo_done"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_override("CRM-OPP-TEST", invalid)


class TestOpportunityStageMigrationPatch(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-migration-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-migration-engineer@example.invalid", "CRM Engineer")
        self.legacy_ids: list[str] = []

    def tearDown(self):
        # after_migrate refuses legacy stage values, so a failed test must not leave any behind.
        legacy_values = migration._legacy_values()
        if self.legacy_ids:
            frappe.db.sql(
                "UPDATE `tabCRM Opportunity` SET `stage` = 'qualified_opportunity' "
                f"WHERE `name` IN ({', '.join(['%s'] * len(self.legacy_ids))}) "
                f"AND BINARY `stage` IN ({', '.join(['%s'] * len(legacy_values))})",
                (*self.legacy_ids, *legacy_values),
            )
        frappe.conf.pop(migration.OVERRIDES_KEY, None)
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _legacy_opportunity(self, account: dict, site: dict, title: str, legacy_stage: str) -> str:
        frappe.set_user(self.sales)
        created = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": title, "owner": self.sales,
            "amount": "100000.00", "intentScore": 30, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY", "originalAmount": "100000.00",
            "qualificationConfirmed": True,
        })
        frappe.set_user("Administrator")
        self.legacy_ids.append(created["id"])
        # Recreate the state before the upgrade: a legacy stage and no stage history.
        frappe.db.delete("CRM Opportunity Stage History", {"opportunity": created["id"]})
        frappe.db.set_value(
            "CRM Opportunity", created["id"], {"stage": legacy_stage, "stage_changed_at": None}, update_modified=False,
        )
        return created["id"]

    def _old_stage_history(self, opportunity_id: str, before: str, after: str, at: datetime) -> None:
        frappe.get_doc({
            "doctype": "CRM Opportunity History", "opportunity": opportunity_id, "actor": self.sales,
            "at": at, "field": "stage", "from_value": before, "to_value": after,
        }).insert(ignore_permissions=True)

    def _customer_review(self, account_id: str, opportunity_id: str, at: datetime) -> str:
        request = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": account_id, "opportunity": opportunity_id,
            "primary_contact": "missing-contact@example.invalid", "sales_owner": self.sales,
            "created_by_user": self.sales, "title": "Migration Demo", "objective": "Customer review evidence",
            "requested_equipment": "Inspection 3000", "sample_type": "Si", "sample_quantity": 1,
            "target_date": "2026-08-20", "customer_expected_date": "2026-08-21", "priority": "High",
            "acceptance_criteria": "Capture above 95%", "status": "Converted",
            "engineer_owner": self.engineer, "form_data": "{}",
        })
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True)
        evaluation = frappe.get_doc({
            "doctype": "CRM Evaluation", "account": account_id, "demo_request": request.name,
            "title": "Migration Evaluation", "status": "Accepted", "evaluation_owner": self.engineer,
            "planned_end": "2026-08-20", "acceptance": "Accepted", "report_status": "Ready",
        }).insert(ignore_permissions=True)
        frappe.get_doc({
            "doctype": "CRM Evaluation History", "evaluation": evaluation.name, "demo_request": request.name,
            "actor": self.engineer, "at": at, "event_type": "Status", "from_value": "Internal Review",
            "to_value": "Customer Review", "summary": "Demo Test moved to Customer Review",
        }).insert(ignore_permissions=True)
        return evaluation.name

    def _report_ids(self, path: str) -> set[str]:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            return {row["opportunity"] for row in csv.DictReader(handle)}

    def test_patch_migrates_legacy_rows_once_and_verify_passes(self):
        frappe.set_user(self.sales)
        account = create_account({
            "name": "Stage Migration", "shortName": "StageMigration", "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": "Stage Migration Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        won = self._legacy_opportunity(account, site, "Legacy won", "Closed Won")
        self._old_stage_history(won, "采购流程", "Won", _at(12))
        lost = self._legacy_opportunity(account, site, "Legacy lost", "Lost")
        self._old_stage_history(lost, "报价", "Lost", _at(13))
        reviewed = self._legacy_opportunity(account, site, "Legacy demo", "Wafer Demo确认")
        evaluation = self._customer_review(account["id"], reviewed, _at(4))
        corrected = self._legacy_opportunity(account, site, "Legacy corrected", "需求发现")
        # Already on the new stages: `lost` must not be mistaken for the legacy `Lost`.
        frappe.set_user(self.sales)
        current = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": "Already migrated", "owner": self.sales,
            "amount": "100000.00", "intentScore": 30, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY", "originalAmount": "100000.00",
            "qualificationConfirmed": True,
        })
        current = mark_opportunity_lost(current["id"], {"lostReason": "Lost after the upgrade"}, current["modified"])
        frappe.set_user("Administrator")
        frappe.conf[migration.OVERRIDES_KEY] = {
            corrected: {"stage": "demo_done", "note": "客户已看过 Demo"},
            "CRM-OPP-99999": {"stage": "lost"},
        }

        preview = migration.dry_run()
        self.assertEqual({won, lost, reviewed, corrected} - self._report_ids(preview["report"]), set())
        self.assertIn("CRM-OPP-99999", preview["unusedOverrides"])
        self.assertNotIn(current["id"], self._report_ids(preview["report"]))
        self.assertEqual(frappe.db.get_value("CRM Opportunity", won, "stage"), "Closed Won")

        migrate_opportunity_seven_stages.execute()
        history_filter = {"opportunity": ["in", self.legacy_ids]}
        rows_after_first_run = frappe.db.count("CRM Opportunity Stage History", history_filter)
        migrate_opportunity_seven_stages.execute()
        self.assertEqual(frappe.db.count("CRM Opportunity Stage History", history_filter), rows_after_first_run)
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", current["id"], ["stage", "legacy_stage"]), ("lost", None),
        )
        self.assertEqual(
            frappe.get_all("CRM Opportunity Stage History", filters={"opportunity": current["id"], "source": "migration"}),
            [],
        )

        won_doc = frappe.get_doc("CRM Opportunity", won)
        self.assertEqual(
            (won_doc.stage, won_doc.legacy_stage, won_doc.stage_changed_at), ("po_received", "Closed Won", _at(12)),
        )
        lost_doc = frappe.get_doc("CRM Opportunity", lost)
        self.assertEqual(
            (lost_doc.stage, lost_doc.lost_at_stage, lost_doc.lost_by, lost_doc.lost_at),
            ("lost", "rfq_validated", self.sales, _at(13)),
        )
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", reviewed, ["stage", "stage_changed_at"]), ("demo_done", _at(4)),
        )
        self.assertEqual(frappe.db.get_value("CRM Opportunity", corrected, "stage"), "demo_done")

        migration_rows = frappe.get_all(
            "CRM Opportunity Stage History",
            filters={"opportunity": reviewed, "event": "migration"},
            fields=["to_stage", "source", "actor", "reached_at", "reached_at_basis", "reference_doctype", "reference_name"],
        )
        self.assertEqual(
            [(row.to_stage, row.source, row.actor, row.reached_at, row.reached_at_basis,
              row.reference_doctype, row.reference_name) for row in migration_rows],
            [("demo_done", "migration", "Administrator", _at(4), "evidence", "CRM Evaluation", evaluation)],
        )
        corrected_reason = frappe.db.get_value(
            "CRM Opportunity Stage History", {"opportunity": corrected, "event": "migration"}, "reason",
        )
        self.assertIn("销售修正：客户已看过 Demo", corrected_reason)

        result = migration.verify()
        errors = [
            finding for finding in result["findings"]
            if finding["opportunity"] in self.legacy_ids and finding["severity"] == "error"
        ]
        self.assertEqual(errors, [])
