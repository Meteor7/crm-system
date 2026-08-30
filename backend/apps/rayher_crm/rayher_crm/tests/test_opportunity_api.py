from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from rayher_crm.services import opportunities as opportunity_services

from rayher_crm.api.v1.opportunities import (
    create_strategy_opportunity as create_strategy_opportunity_endpoint,
    get_strategy_opportunity as get_strategy_opportunity_endpoint,
    list_strategy_opportunities as list_strategy_opportunities_endpoint,
    update_strategy_opportunity as update_strategy_opportunity_endpoint,
)
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.opportunities import (
    _calculate_opportunity_probability,
    create_strategy_opportunity,
    delete_strategy_opportunity,
    get_strategy_opportunity,
    list_strategy_opportunities,
    update_strategy_opportunity,
)
from rayher_crm.services.sites import create_site


class TestOpportunityApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-opportunity-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-opportunity-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-opportunity-engineer@example.invalid", "CRM Engineer")
        self.manager = self._user("crm-opportunity-manager@example.invalid", "CRM Manager")

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

    def _account_site(self, owner: str, suffix: str):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Opportunity {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": owner,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "上海", "type": "Fab",
            "process": "Frontend", "status": "量产",
        })
        return account, site

    def _input(self, account: dict, site: dict, owner: str, **overrides):
        payload = {
            "accountId": account["id"], "siteId": site["id"], "title": "Inspection Project",
            "owner": owner, "stage": "需求发现", "forecast": "Pipeline", "amount": "125000.25",
            "probability": 20, "intentScore": 35, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "originalAmount": "125000.25", "paymentMilestones": ["30% PO", "70% FAT"],
            "strengths": ["Local service"], "redFlags": [], "informationNeeded": ["Budget"],
        }
        payload.update(overrides)
        return payload

    def test_create_list_update_history_and_account_360(self):
        account, site = self._account_site(self.sales, "Core")
        with self.assertRaises(CrmApiException) as terminal_create:
            create_strategy_opportunity(self._input(account, site, self.sales, stage="Won"))
        self.assertEqual(terminal_create.exception.code, "INVALID_TRANSITION")
        created = create_strategy_opportunity(self._input(account, site, self.sales))
        self.assertRegex(created["id"], r"^CRM-OPP-\d{5}$")
        self.assertEqual(created["account"], account["name"])
        self.assertEqual(created["site"], "Core Site")
        self.assertEqual(created["owner"], self.sales)
        self.assertEqual(created["paymentMilestones"], ["30% PO", "70% FAT"])
        self.assertRegex(created["modified"], r"Z$")
        self.assertEqual(created["probability"], 23)

        before_modified = frappe.db.get_value("CRM Opportunity", created["id"], "modified")
        listed = list_strategy_opportunities()
        self.assertIn(created["id"], {item["id"] for item in listed})
        page, total, page_number, page_size = list_strategy_opportunities({
            "accountId": account["id"], "page": 1, "pageSize": 1,
        })
        self.assertEqual((len(page), total, page_number, page_size), (1, 1, 1, 1))
        filtered, filtered_total, _, _ = list_strategy_opportunities({
            "search": "Inspection", "status": "需求发现", "accountId": account["id"],
            "page": 1, "pageSize": 20,
        })
        self.assertEqual(([item["id"] for item in filtered], filtered_total), ([created["id"]], 1))
        self.assertEqual(frappe.db.get_value("CRM Opportunity", created["id"], "modified"), before_modified)

        with self.assertRaises(CrmApiException) as stale:
            update_strategy_opportunity(created["id"], {"stage": "Wafer Demo确认"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        with self.assertRaises(CrmApiException) as skipped_stage:
            update_strategy_opportunity(created["id"], {"stage": "预算审批"}, created["modified"])
        self.assertEqual(skipped_stage.exception.code, "INVALID_TRANSITION")

        with self.assertRaises(CrmApiException) as automatic_gate:
            update_strategy_opportunity(created["id"], {"stage": "Wafer Demo确认"}, created["modified"])
        self.assertEqual(automatic_gate.exception.code, "INVALID_TRANSITION")

        frappe.db.set_value("CRM Opportunity", created["id"], {
            "stage": "预算审批", "probability": 70,
        })
        budget = get_strategy_opportunity(created["id"])
        specified = update_strategy_opportunity(created["id"], {"stage": "设备规格确认"}, budget["modified"])
        self.assertEqual((specified["stage"], specified["probability"]), ("设备规格确认", 59))
        with self.assertRaises(CrmApiException) as rfq_gate:
            update_strategy_opportunity(created["id"], {"stage": "报价"}, specified["modified"])
        self.assertEqual(rfq_gate.exception.code, "INVALID_TRANSITION")

        frappe.db.set_value("CRM Opportunity", created["id"], {"stage": "报价", "probability": 62})
        quoted = get_strategy_opportunity(created["id"])
        with self.assertRaises(CrmApiException) as quotation_gate:
            update_strategy_opportunity(created["id"], {"stage": "采购流程"}, quoted["modified"])
        self.assertEqual(quotation_gate.exception.code, "INVALID_TRANSITION")
        self.assertEqual({row["actor"] for row in quoted["history"]}, {self.sales})
        self.assertEqual(get_account_360(account["id"])["opportunities"][0]["id"], created["id"])

    def test_owner_scope_assignment_and_account_site_integrity(self):
        account, site = self._account_site(self.sales, "Owned")
        other_account, other_site = self._account_site(self.other_sales, "Foreign")

        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as forged:
            create_strategy_opportunity(self._input(account, site, self.other_sales))
        self.assertEqual(forged.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as mismatch:
            create_strategy_opportunity(self._input(account, other_site, self.sales))
        self.assertEqual(mismatch.exception.code, "CONFLICT")

        owned = create_strategy_opportunity(self._input(account, site, self.sales))
        frappe.set_user(self.other_sales)
        foreign = create_strategy_opportunity(self._input(other_account, other_site, self.other_sales))
        self.assertEqual({row["id"] for row in list_strategy_opportunities()}, {foreign["id"]})
        self.assertEqual(get_strategy_opportunity(foreign["id"])["id"], foreign["id"])
        with self.assertRaises(CrmApiException) as outside_scope:
            get_strategy_opportunity(owned["id"])
        self.assertEqual(outside_scope.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as missing:
            get_strategy_opportunity("CRM-OPP-NOT-FOUND")
        self.assertEqual(missing.exception.code, "NOT_FOUND")

        frappe.set_user("Administrator")
        frappe.get_doc({
            "doctype": "CRM Account Engineer Assignment", "customer": account["id"],
            "engineer": self.engineer, "enabled": 1,
        }).insert(ignore_permissions=True)
        frappe.set_user(self.engineer)
        self.assertEqual({row["id"] for row in list_strategy_opportunities()}, {owned["id"]})

    def test_probability_is_derived_from_stage_and_purchase_intent(self):
        cases = [
            ("需求发现", 50, 29), ("Wafer Demo确认", 80, 65),
            ("预算审批", 80, 74), ("设备规格确认", 80, 77),
            ("报价", 80, 80), ("采购流程", 86, 88),
            ("Won", 0, 100), ("Lost", 100, 0),
        ]
        for stage, score, expected in cases:
            with self.subTest(stage=stage, score=score):
                self.assertEqual(_calculate_opportunity_probability(stage, score), expected)

    def test_validation_rejects_invalid_money_date_ranges_and_enums(self):
        account, site = self._account_site(self.sales, "Validation")
        cases = [
            ({"amount": 0}, "amount"), ({"amount": "1.001"}, "amount"),
            ({"probability": 101}, "probability"), ({"intentScore": -1}, "intentScore"),
            ({"poDate": "2026-02-30"}, "poDate"), ({"stage": "Open"}, "stage"),
            ({"forecast": "Maybe"}, "forecast"), ({"currency": "ZZZ"}, "currency"),
        ]
        for overrides, fieldname in cases:
            with self.subTest(fieldname=fieldname), self.assertRaises(CrmApiException) as invalid:
                create_strategy_opportunity(self._input(account, site, self.sales, **overrides))
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")

    def test_endpoints_return_stable_envelopes(self):
        account, site = self._account_site(self.sales, "Endpoint")
        created = create_strategy_opportunity_endpoint(self._input(account, site, self.sales))
        self.assertEqual(created["warnings"], [])
        self.assertRegex(created["meta"]["requestId"], r"^req_[0-9a-f]{24}$")

        listed = list_strategy_opportunities_endpoint()
        self.assertIn(created["data"]["id"], {item["id"] for item in listed["data"]["items"]})
        self.assertGreaterEqual(listed["meta"]["total"], 1)

        detail = get_strategy_opportunity_endpoint(created["data"]["id"])
        self.assertEqual(detail["data"]["id"], created["data"]["id"])

        blocked = update_strategy_opportunity_endpoint(
            created["data"]["id"],
            {"stage": "Wafer Demo确认"},
            created["data"]["modified"],
        )
        self.assertIsNone(blocked["data"])
        self.assertEqual(blocked["error"]["code"], "INVALID_TRANSITION")

    def test_only_manager_can_rollback_stage_with_reason_and_fresh_version(self):
        rollback = getattr(opportunity_services, "rollback_opportunity_stage", None)
        self.assertIsNotNone(rollback, "rollback_opportunity_stage must be implemented")

        account, site = self._account_site(self.sales, "Rollback")
        opportunity = create_strategy_opportunity(self._input(account, site, self.sales))
        frappe.db.set_value("CRM Opportunity", opportunity["id"], {
            "stage": "报价", "probability": 80,
        })
        current = get_strategy_opportunity(opportunity["id"])

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            rollback(opportunity["id"], "Wafer Demo确认", "Need another technical review", current["modified"])
        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            rollback(opportunity["id"], "Wafer Demo确认", "Need another technical review", current["modified"])

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as missing_reason:
            rollback(opportunity["id"], "Wafer Demo确认", "   ", current["modified"])
        self.assertEqual(missing_reason.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as forward:
            rollback(opportunity["id"], "采购流程", "Not a rollback", current["modified"])
        self.assertEqual(forward.exception.code, "INVALID_TRANSITION")
        with self.assertRaises(CrmApiException) as same_stage:
            rollback(opportunity["id"], "报价", "Not an earlier stage", current["modified"])
        self.assertEqual(same_stage.exception.code, "INVALID_TRANSITION")

        terminal = create_strategy_opportunity(self._input(account, site, self.sales, title="Terminal rollback"))
        frappe.db.set_value("CRM Opportunity", terminal["id"], {"stage": "Lost", "probability": 0})
        terminal = get_strategy_opportunity(terminal["id"])
        with self.assertRaises(CrmApiException) as terminal_target:
            rollback(terminal["id"], "Won", "Terminal states are not rollback targets", terminal["modified"])
        self.assertEqual(terminal_target.exception.code, "INVALID_TRANSITION")

        with self.assertRaises(CrmApiException) as stale:
            rollback(opportunity["id"], "Wafer Demo确认", "Need another technical review", "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        rolled_back = rollback(
            opportunity["id"], "Wafer Demo确认", "Need another technical review", current["modified"],
        )
        self.assertEqual(rolled_back["stage"], "Wafer Demo确认")
        history = next(row for row in rolled_back["history"] if row["field"] == "stageRollback")
        self.assertEqual(history["from"], "报价")
        self.assertEqual(history["to"], "Wafer Demo确认 | Need another technical review")

    def test_cannot_rollback_to_discovery_while_demo_request_is_active(self):
        account, site = self._account_site(self.sales, "ActiveRequestRollback")
        opportunity = create_strategy_opportunity(self._input(account, site, self.sales))
        frappe.db.set_value("CRM Opportunity", opportunity["id"], {"stage": "Wafer Demo确认", "probability": 38})
        request = frappe.get_doc({
            "doctype": "CRM Demo Request",
            "account": account["id"],
            "primary_contact": "missing-contact@example.invalid",
            "opportunity": opportunity["id"],
            "sales_owner": self.sales,
            "created_by_user": self.sales,
            "title": "Active Demo Request",
            "objective": "Confirm technical feasibility",
            "requested_equipment": "CIS inspection platform",
            "sample_type": "300mm CIS wafer",
            "sample_quantity": 12,
            "target_date": "2026-12-01",
            "customer_expected_date": "2026-12-02",
            "priority": "High",
            "acceptance_criteria": "Capture >= 96%",
            "status": "Engineer Review",
            "engineer_owner": self.engineer,
            "form_data": "{}",
        })
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True)
        current = get_strategy_opportunity(opportunity["id"])

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as blocked:
            opportunity_services.rollback_opportunity_stage(
                opportunity["id"], "需求发现", "Requirements changed", current["modified"],
            )
        self.assertEqual(blocked.exception.code, "CONFLICT")
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["stage"], "Wafer Demo确认")

    def test_only_manager_can_delete_strategy_opportunity(self):
        account, site = self._account_site(self.other_sales, "Delete")
        opportunity = create_strategy_opportunity(self._input(account, site, self.other_sales))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            delete_strategy_opportunity(opportunity["id"])
        self.assertTrue(frappe.db.exists("CRM Opportunity", opportunity["id"]))

        frappe.set_user("Administrator")
        self.assertEqual(
            delete_strategy_opportunity(opportunity["id"]),
            {"id": opportunity["id"], "status": "Deleted"},
        )
        self.assertFalse(frappe.db.exists("CRM Opportunity", opportunity["id"]))
