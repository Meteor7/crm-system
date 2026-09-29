from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.api.v1.opportunities import (
    create_strategy_opportunity as create_strategy_opportunity_endpoint,
    get_strategy_opportunity as get_strategy_opportunity_endpoint,
    list_strategy_opportunities as list_strategy_opportunities_endpoint,
    mark_opportunity_lost as mark_opportunity_lost_endpoint,
    update_strategy_opportunity as update_strategy_opportunity_endpoint,
)
from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import (
    advance_opportunity_for_event,
    confirm_budget_approved,
    create_opportunity_action,
    create_opportunity_stakeholder,
    create_strategy_opportunity,
    delete_opportunity_action,
    delete_strategy_opportunity,
    get_strategy_opportunity,
    list_strategy_opportunities,
    mark_opportunity_lost,
    rollback_opportunity_stage,
    update_strategy_opportunity,
)
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


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
            "owner": owner, "amount": "125000.25",
            "intentScore": 35, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "originalAmount": "125000.25", "amountCny": "125000.25", "paymentMilestones": ["30% PO", "70% FAT"],
            "strengths": ["Local service"], "redFlags": [], "informationNeeded": ["Budget"],
            "qualificationConfirmed": True, "probabilityLevel": "pipeline",
        }
        payload.update(overrides)
        return payload

    def _probability_history_count(self, opportunity_id: str) -> int:
        return frappe.db.count("CRM Opportunity Probability History", {"opportunity": opportunity_id})

    def _stage_rows(self, opportunity: dict) -> list[tuple[str, str, str, str]]:
        return [(row["from"], row["to"], row["source"], row["event"]) for row in opportunity["stageHistory"]]

    def _demo_done(self, opportunity: dict) -> dict:
        advance_opportunity_for_event(
            opportunity["id"], "demo_customer_review",
            reference_doctype="CRM Evaluation", reference_name="CRM-EVAL-TEST",
        )
        return get_strategy_opportunity(opportunity["id"])

    def _days_ago(self, days: int) -> str:
        return frappe.utils.add_days(frappe.utils.today(), -days)

    def test_create_list_update_history_and_account_360(self):
        account, site = self._account_site(self.sales, "Core")
        with self.assertRaises(CrmApiException) as terminal_create:
            create_strategy_opportunity(self._input(account, site, self.sales, stage="po_received"))
        self.assertEqual(terminal_create.exception.code, "INVALID_TRANSITION")
        unconfirmed = self._input(account, site, self.sales)
        unconfirmed.pop("qualificationConfirmed")
        with self.assertRaises(CrmApiException) as unqualified:
            create_strategy_opportunity(unconfirmed)
        self.assertEqual(
            (unqualified.exception.code, unqualified.exception.field_errors),
            ("VALIDATION_ERROR", {"qualificationConfirmed": "Required"}),
        )

        created = create_strategy_opportunity(self._input(account, site, self.sales))
        self.assertRegex(created["id"], r"^CRM-OPP-\d{5}$")
        self.assertEqual(created["account"], account["name"])
        self.assertEqual(created["site"], "Core Site")
        self.assertEqual(created["owner"], self.sales)
        self.assertEqual(created["paymentMilestones"], ["30% PO", "70% FAT"])
        self.assertRegex(created["modified"], r"Z$")
        self.assertEqual(
            (created["stage"], created["probabilityLevel"]), ("qualified_opportunity", "pipeline"),
        )
        self.assertEqual(
            [(row["from"], row["to"], row["actor"]) for row in created["probabilityHistory"]],
            [("", "pipeline", self.sales)],
        )
        self.assertEqual(self._stage_rows(created), [("", "qualified_opportunity", "creation", "created")])
        creation = created["stageHistory"][0]
        self.assertEqual((creation["actor"], creation["reachedAtBasis"]), (self.sales, "recorded"))
        self.assertEqual(created["stageChangedAt"], creation["reachedAt"])
        self.assertEqual(
            (created["budgetApprovedOn"], created["lostAtStage"], created["lostAt"], created["lostBy"]),
            ("", "", "", ""),
        )
        self.assertIsNone(created["internalValidation"])
        self.assertIsNone(created["liveBooking"])
        self.assertNotIn("probability", created)
        self.assertNotIn("forecast", created)

        before_modified = frappe.db.get_value("CRM Opportunity", created["id"], "modified")
        listed = list_strategy_opportunities()
        self.assertIn(created["id"], {item["id"] for item in listed})
        page, total, page_number, page_size = list_strategy_opportunities({
            "accountId": account["id"], "page": 1, "pageSize": 1,
        })
        self.assertEqual((len(page), total, page_number, page_size), (1, 1, 1, 1))
        filtered, filtered_total, _, _ = list_strategy_opportunities({
            "search": "Inspection", "status": "qualified_opportunity", "accountId": account["id"],
            "page": 1, "pageSize": 20,
        })
        self.assertEqual(([item["id"] for item in filtered], filtered_total), ([created["id"]], 1))
        self.assertEqual(frappe.db.get_value("CRM Opportunity", created["id"], "modified"), before_modified)

        with self.assertRaises(CrmApiException) as stale:
            update_strategy_opportunity(created["id"], {"title": "Stale"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        for stage in ("demo_done", "customer_budget_approved", "po_received", "lost"):
            with self.subTest(stage=stage), self.assertRaises(CrmApiException) as direct_stage:
                update_strategy_opportunity(created["id"], {"stage": stage}, created["modified"])
            self.assertEqual(direct_stage.exception.code, "INVALID_TRANSITION")

        renamed = update_strategy_opportunity(created["id"], {"title": "Inspection Project II"}, created["modified"])
        self.assertEqual((renamed["title"], renamed["stage"]), ("Inspection Project II", "qualified_opportunity"))
        self.assertEqual({row["actor"] for row in renamed["history"]}, {self.sales})
        self.assertNotIn("stage", {row["field"] for row in renamed["history"]})
        self.assertEqual(get_account_360(account["id"])["opportunities"][0]["id"], created["id"])

    def test_owner_sets_probability_level_and_each_change_is_audited(self):
        account, site = self._account_site(self.sales, "Probability")
        created = create_strategy_opportunity(self._input(account, site, self.sales, probabilityLevel="pipeline"))
        self.assertEqual(created["probabilityLevel"], "pipeline")
        self.assertEqual(
            [(row["from"], row["to"], row["actor"]) for row in created["probabilityHistory"]],
            [("", "pipeline", self.sales)],
        )

        raised = update_strategy_opportunity(created["id"], {"probabilityLevel": "upside"}, created["modified"])
        self.assertEqual(raised["probabilityLevel"], "upside")
        self.assertEqual(
            [(row["from"], row["to"]) for row in raised["probabilityHistory"]],
            [("pipeline", "upside"), ("", "pipeline")],
        )
        self.assertNotIn("probability_level", {row["field"] for row in raised["history"]})

        intent_only = update_strategy_opportunity(created["id"], {"intentScore": 90}, raised["modified"])
        self.assertEqual((intent_only["probabilityLevel"], intent_only["score"]), ("upside", 90))
        self.assertEqual(self._probability_history_count(created["id"]), 2)

        self._demo_done(created)
        budget = confirm_budget_approved(
            created["id"], {"approvedOn": self._days_ago(3)}, get_strategy_opportunity(created["id"])["modified"],
        )
        self.assertEqual((budget["stage"], budget["probabilityLevel"]), ("customer_budget_approved", "upside"))
        self.assertEqual(self._probability_history_count(created["id"]), 2)

        with self.assertRaises(CrmApiException) as cleared:
            update_strategy_opportunity(created["id"], {"probabilityLevel": ""}, budget["modified"])
        self.assertEqual(
            (cleared.exception.code, cleared.exception.field_errors),
            ("VALIDATION_ERROR", {"probabilityLevel": "Required"}),
        )
        with self.assertRaises(CrmApiException) as invalid:
            update_strategy_opportunity(created["id"], {"probabilityLevel": "certain"}, budget["modified"])
        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as not_owner:
            update_strategy_opportunity(created["id"], {"probabilityLevel": "low_probability"}, budget["modified"])
        self.assertEqual(not_owner.exception.code, "PERMISSION_DENIED")
        renamed = update_strategy_opportunity(
            created["id"], {"title": "Manager edit keeps the level"}, budget["modified"],
        )
        self.assertEqual((renamed["title"], renamed["probabilityLevel"]), ("Manager edit keeps the level", "upside"))
        # A Manager opening an Opportunity for Sales sets its first level.
        manager_created = create_strategy_opportunity(
            self._input(account, site, self.sales, title="Manager chosen level", probabilityLevel="committed"),
        )
        self.assertEqual(
            [(row["from"], row["to"], row["actor"]) for row in manager_created["probabilityHistory"]],
            [("", "committed", self.manager)],
        )

        # Only an Opportunity from before the levels can still be pending.
        pending = create_strategy_opportunity(self._input(account, site, self.sales, title="Pending level"))
        frappe.db.set_value("CRM Opportunity", pending["id"], "probability_level", "", update_modified=False)
        upside_rows, upside_total, _, _ = list_strategy_opportunities({
            "accountId": account["id"], "probabilityLevel": "upside", "page": 1, "pageSize": 20,
        })
        self.assertEqual(([item["id"] for item in upside_rows], upside_total), ([created["id"]], 1))
        pending_rows, pending_total, _, _ = list_strategy_opportunities({
            "accountId": account["id"], "probabilityLevel": "pending", "page": 1, "pageSize": 20,
        })
        self.assertEqual(([item["id"] for item in pending_rows], pending_total), ([pending["id"]], 1))

    def test_a_new_opportunity_needs_a_level_and_a_set_level_is_never_cleared(self):
        account, site = self._account_site(self.sales, "Level rules")
        with self.assertRaises(CrmApiException) as missing:
            create_strategy_opportunity(self._input(account, site, self.sales, probabilityLevel=""))
        self.assertEqual(
            (missing.exception.code, missing.exception.field_errors),
            ("VALIDATION_ERROR", {"probabilityLevel": "Required"}),
        )

        created = create_strategy_opportunity(self._input(account, site, self.sales, probabilityLevel="upside"))
        # Refused from the first milestone on, not only once the demo is done.
        self.assertEqual(created["stage"], "qualified_opportunity")
        with self.assertRaises(CrmApiException) as cleared:
            update_strategy_opportunity(created["id"], {"probabilityLevel": ""}, created["modified"])
        self.assertEqual(
            (cleared.exception.code, cleared.exception.field_errors),
            ("VALIDATION_ERROR", {"probabilityLevel": "Required"}),
        )
        self.assertEqual(get_strategy_opportunity(created["id"])["probabilityLevel"], "upside")

    def test_lowering_the_level_needs_a_reason_saved_with_the_change(self):
        account, site = self._account_site(self.sales, "Downgrade")
        created = create_strategy_opportunity(self._input(account, site, self.sales, probabilityLevel="committed"))

        for reason in ("", "   "):
            with self.assertRaises(CrmApiException) as unexplained:
                update_strategy_opportunity(
                    created["id"], {"probabilityLevel": "pipeline", "probabilityReason": reason}, created["modified"],
                )
            self.assertEqual(
                (unexplained.exception.code, unexplained.exception.field_errors),
                ("VALIDATION_ERROR", {"probabilityReason": "Required"}),
            )
        self.assertEqual(get_strategy_opportunity(created["id"])["probabilityLevel"], "committed")
        self.assertEqual(self._probability_history_count(created["id"]), 1)

        lowered = update_strategy_opportunity(
            created["id"],
            {"probabilityLevel": "pipeline", "probabilityReason": "  客户预算推迟到明年  ", "probabilityActionPlan": "Follow up with procurement"},
            created["modified"],
        )
        self.assertEqual(
            [(row["from"], row["to"], row["reason"]) for row in lowered["probabilityHistory"]],
            [("committed", "pipeline", "客户预算推迟到明年"), ("", "committed", "")],
        )

        # Raising the level needs no reason.
        raised = update_strategy_opportunity(created["id"], {"probabilityLevel": "upside"}, lowered["modified"])
        self.assertEqual(
            (raised["probabilityHistory"][0]["to"], raised["probabilityHistory"][0]["reason"]), ("upside", ""),
        )

    def test_the_level_the_manager_sets_on_opening_then_belongs_to_the_owner(self):
        account, site = self._account_site(self.sales, "Manager opened")
        frappe.set_user(self.manager)
        created = create_strategy_opportunity(self._input(account, site, self.sales, probabilityLevel="upside"))
        self.assertEqual((created["owner"], created["probabilityLevel"]), (self.sales, "upside"))
        self.assertEqual(
            [(row["from"], row["to"], row["actor"]) for row in created["probabilityHistory"]],
            [("", "upside", self.manager)],
        )
        with self.assertRaises(CrmApiException) as not_owner:
            update_strategy_opportunity(created["id"], {"probabilityLevel": "committed"}, created["modified"])
        self.assertEqual(not_owner.exception.code, "PERMISSION_DENIED")

    def test_an_opportunity_from_before_the_levels_gets_its_first_one_without_a_reason(self):
        account, site = self._account_site(self.sales, "Legacy level")
        created = create_strategy_opportunity(self._input(account, site, self.sales))
        frappe.db.delete("CRM Opportunity Probability History", {"opportunity": created["id"]})
        frappe.db.set_value("CRM Opportunity", created["id"], "probability_level", "", update_modified=False)
        legacy = get_strategy_opportunity(created["id"])

        # Other fields stay editable while the level is still pending.
        renamed = update_strategy_opportunity(created["id"], {"title": "Still pending"}, legacy["modified"])
        self.assertEqual((renamed["title"], renamed["probabilityLevel"]), ("Still pending", ""))

        first = update_strategy_opportunity(created["id"], {"probabilityLevel": "low_probability"}, renamed["modified"])
        self.assertEqual(
            [(row["from"], row["to"], row["reason"]) for row in first["probabilityHistory"]],
            [("", "low_probability", "")],
        )

    def test_budget_confirmation_is_a_declared_date_and_needs_a_level(self):
        account, site = self._account_site(self.sales, "Budget")
        opportunity = create_strategy_opportunity(self._input(account, site, self.sales))
        # Only an Opportunity from before the levels can reach this point without one.
        frappe.db.delete("CRM Opportunity Probability History", {"opportunity": opportunity["id"]})
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "probability_level", "", update_modified=False)
        with self.assertRaises(CrmApiException) as too_early:
            confirm_budget_approved(opportunity["id"], {"approvedOn": self._days_ago(1)}, opportunity["modified"])
        self.assertEqual(too_early.exception.code, "INVALID_TRANSITION")

        demo_done = self._demo_done(opportunity)
        self.assertEqual(
            self._stage_rows(demo_done)[0], ("qualified_opportunity", "demo_done", "event", "demo_customer_review"),
        )
        with self.assertRaises(CrmApiException) as no_level:
            confirm_budget_approved(opportunity["id"], {"approvedOn": self._days_ago(1)}, demo_done["modified"])
        self.assertEqual(
            (no_level.exception.code, no_level.exception.field_errors),
            ("VALIDATION_ERROR", {"probabilityLevel": "Required"}),
        )

        leveled = update_strategy_opportunity(opportunity["id"], {"probabilityLevel": "pipeline"}, demo_done["modified"])
        for payload in ({}, {"approvedOn": frappe.utils.add_days(frappe.utils.today(), 1)}, {"approvedOn": "2026-02-30"}):
            with self.subTest(payload=payload), self.assertRaises(CrmApiException) as invalid:
                confirm_budget_approved(opportunity["id"], payload, leveled["modified"])
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")

        declared_on = self._days_ago(10)
        approved = confirm_budget_approved(opportunity["id"], {"approvedOn": declared_on}, leveled["modified"])
        self.assertEqual((approved["stage"], approved["budgetApprovedOn"]), ("customer_budget_approved", declared_on))
        latest = approved["stageHistory"][0]
        self.assertEqual(
            (latest["from"], latest["to"], latest["source"], latest["event"], latest["reachedAtBasis"], latest["actor"]),
            ("demo_done", "customer_budget_approved", "manual", "budget_confirmed", "declared", self.sales),
        )
        self.assertEqual(latest["reachedAt"], to_iso_timestamp(frappe.utils.get_datetime(declared_on)))
        self.assertEqual(approved["stageChangedAt"], latest["reachedAt"])
        self.assertNotEqual(latest["recordedAt"], latest["reachedAt"])

        with self.assertRaises(CrmApiException) as twice:
            confirm_budget_approved(opportunity["id"], {"approvedOn": declared_on}, approved["modified"])
        self.assertEqual(twice.exception.code, "INVALID_TRANSITION")

    def test_workflow_events_advance_once_and_leave_lost_opportunities_alone(self):
        account, site = self._account_site(self.sales, "Events")
        opportunity = create_strategy_opportunity(self._input(account, site, self.sales))
        self._demo_done(opportunity)
        advanced = self._demo_done(opportunity)
        self.assertEqual(advanced["stage"], "demo_done")
        self.assertEqual(
            [(row["to"], row["event"], row["referenceDoctype"], row["referenceName"]) for row in advanced["stageHistory"]],
            [
                ("demo_done", "demo_customer_review", "CRM Evaluation", "CRM-EVAL-TEST"),
                ("qualified_opportunity", "created", "", ""),
            ],
        )
        with self.assertRaises(CrmApiException) as behind:
            advance_opportunity_for_event(
                opportunity["id"], "rfq_approved", reference_doctype="CRM RFQ", reference_name="CRM-RFQ-TEST",
            )
        self.assertEqual(behind.exception.code, "CONFLICT")
        with self.assertRaises(ValueError):
            advance_opportunity_for_event(
                opportunity["id"], "po_confirmed", reference_doctype="CRM Booking", reference_name="CRM-BKG-TEST",
            )

        lost = mark_opportunity_lost(opportunity["id"], {"lostReason": "Budget frozen"}, advanced["modified"])
        self._demo_done(opportunity)
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["stageHistory"], lost["stageHistory"])
        with self.assertRaises(CrmApiException) as lost_rfq:
            advance_opportunity_for_event(
                opportunity["id"], "rfq_approved", reference_doctype="CRM RFQ", reference_name="CRM-RFQ-TEST",
            )
        self.assertEqual(lost_rfq.exception.code, "INVALID_TRANSITION")

    def test_marking_lost_records_the_stage_and_reopening_stays_below_it(self):
        account, site = self._account_site(self.sales, "Lost")
        opportunity = self._demo_done(create_strategy_opportunity(self._input(account, site, self.sales)))
        with self.assertRaises(CrmApiException) as no_reason:
            mark_opportunity_lost(opportunity["id"], {"lostReason": "  "}, opportunity["modified"])
        self.assertEqual(no_reason.exception.code, "VALIDATION_ERROR")
        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            mark_opportunity_lost(opportunity["id"], {"lostReason": "Engineers cannot close"}, opportunity["modified"])

        frappe.set_user(self.sales)
        lost = mark_opportunity_lost(opportunity["id"], {"lostReason": "Competitor won"}, opportunity["modified"])
        self.assertEqual(
            (lost["stage"], lost["lostAtStage"], lost["lostBy"], lost["lostReason"]),
            ("lost", "demo_done", self.sales, "Competitor won"),
        )
        self.assertRegex(lost["lostAt"], r"Z$")
        self.assertEqual(lost["lostAt"], lost["stageChangedAt"])
        latest = lost["stageHistory"][0]
        self.assertEqual(
            (latest["from"], latest["to"], latest["source"], latest["event"], latest["reason"]),
            ("demo_done", "lost", "lost", "marked_lost", "Competitor won"),
        )
        with self.assertRaises(CrmApiException) as twice:
            mark_opportunity_lost(opportunity["id"], {"lostReason": "Again"}, lost["modified"])
        self.assertEqual(twice.exception.code, "INVALID_TRANSITION")
        with self.assertRaises(CrmApiException) as frozen:
            update_strategy_opportunity(opportunity["id"], {"probabilityLevel": "committed"}, lost["modified"])
        self.assertEqual(frozen.exception.code, "INVALID_TRANSITION")
        with self.assertRaises(CrmApiException) as reason_required:
            update_strategy_opportunity(opportunity["id"], {"lostReason": ""}, lost["modified"])
        self.assertEqual(reason_required.exception.code, "VALIDATION_ERROR")

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as above_loss:
            rollback_opportunity_stage(opportunity["id"], "customer_budget_approved", "Reopen higher", lost["modified"])
        self.assertEqual(above_loss.exception.code, "INVALID_TRANSITION")
        reopened = rollback_opportunity_stage(opportunity["id"], "demo_done", "Customer came back", lost["modified"])
        self.assertEqual(
            (reopened["stage"], reopened["lostAtStage"], reopened["lostAt"], reopened["lostBy"], reopened["lostReason"]),
            ("demo_done", "", "", "", ""),
        )
        latest = reopened["stageHistory"][0]
        self.assertEqual(
            (latest["from"], latest["to"], latest["source"], latest["event"], latest["reason"], latest["actor"]),
            ("lost", "demo_done", "rollback", "reopened", "Customer came back", self.manager),
        )
        self.assertEqual(reopened["stageHistory"][1]["event"], "marked_lost")

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
        with self.assertRaises(CrmApiException) as outside_action:
            mark_opportunity_lost(owned["id"], {"lostReason": "Not mine"}, owned["modified"])
        self.assertEqual(outside_action.exception.code, "SCOPE_DENIED")
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

    def test_public_child_owner_cannot_read_the_account_site(self):
        account, site = self._account_site(self.sales, "PublicRestrictedSite")
        opportunity = create_strategy_opportunity(self._input(account, site, self.sales))
        frappe.db.set_value(
            "Customer", account["id"], "custom_crm_visibility", "Public", update_modified=False,
        )
        frappe.db.set_value(
            "CRM Opportunity", opportunity["id"], "opportunity_owner", self.other_sales, update_modified=False,
        )

        frappe.set_user(self.other_sales)
        detail = get_strategy_opportunity(opportunity["id"])
        self.assertEqual((detail["siteId"], detail["site"], detail["siteRestricted"]), ("", "", True))
        self.assertFalse(
            frappe.has_permission("CRM Opportunity", "read", doc=opportunity["id"], user=self.other_sales),
        )
        self.assertEqual(
            frappe.get_list("CRM Opportunity", filters={"name": opportunity["id"]}, pluck="name"),
            [],
        )
        listed = list_strategy_opportunities({"accountId": account["id"], "page": 1, "pageSize": 20})[0]
        self.assertEqual([(row["id"], row["siteId"], row["site"]) for row in listed], [(opportunity["id"], "", "")])
        hidden_site_search = list_strategy_opportunities({
            "search": site["id"], "page": 1, "pageSize": 20,
        })[0]
        self.assertNotIn(opportunity["id"], {row["id"] for row in hidden_site_search})
        with self.assertRaises(CrmApiException) as site_write:
            update_strategy_opportunity(opportunity["id"], {"title": "Cannot retain a hidden Site"}, detail["modified"])
        self.assertEqual(site_write.exception.code, "SCOPE_DENIED")

    def test_validation_rejects_invalid_money_date_ranges_and_enums(self):
        account, site = self._account_site(self.sales, "Validation")
        cases = [
            ({"amount": 0}, "amount"), ({"amount": "1.001"}, "amount"),
            ({"intentScore": -1}, "intentScore"), ({"poDate": "2026-02-30"}, "poDate"),
            ({"stage": "Open"}, "stage"), ({"stage": "需求发现"}, "stage"),
            ({"probabilityLevel": "certain"}, "probabilityLevel"), ({"currency": "ZZZ"}, "currency"),
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
            {"stage": "demo_done"},
            created["data"]["modified"],
        )
        self.assertIsNone(blocked["data"])
        self.assertEqual(blocked["error"]["code"], "INVALID_TRANSITION")

        lost = mark_opportunity_lost_endpoint(
            created["data"]["id"], {"lostReason": "Project cancelled"}, created["data"]["modified"],
        )
        self.assertEqual((lost["data"]["stage"], lost["data"]["lostAtStage"]), ("lost", "qualified_opportunity"))
        again = mark_opportunity_lost_endpoint(
            created["data"]["id"], {"lostReason": "Again"}, lost["data"]["modified"],
        )
        self.assertIsNone(again["data"])
        self.assertEqual(again["error"]["code"], "INVALID_TRANSITION")

    def test_only_manager_can_rollback_stage_with_reason_and_fresh_version(self):
        account, site = self._account_site(self.sales, "Rollback")
        opportunity = create_strategy_opportunity(self._input(account, site, self.sales))
        current = advance_opportunity_fixture(opportunity, "rfq_validated")
        self.assertTrue(current["budgetApprovedOn"])

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            rollback_opportunity_stage(opportunity["id"], "demo_done", "Need another technical review", current["modified"])
        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            rollback_opportunity_stage(opportunity["id"], "demo_done", "Need another technical review", current["modified"])

        frappe.set_user(self.manager)
        cases = [
            ("demo_done", "   ", "VALIDATION_ERROR"),
            ("lost", "Lost is not a rollback target", "VALIDATION_ERROR"),
            ("设备规格确认", "Legacy stages are not accepted", "VALIDATION_ERROR"),
            ("quotation_sent", "Not a rollback", "INVALID_TRANSITION"),
            ("rfq_validated", "Not an earlier stage", "INVALID_TRANSITION"),
        ]
        for target, reason, code in cases:
            with self.subTest(target=target), self.assertRaises(CrmApiException) as invalid:
                rollback_opportunity_stage(opportunity["id"], target, reason, current["modified"])
            self.assertEqual(invalid.exception.code, code)
        with self.assertRaises(CrmApiException) as stale:
            rollback_opportunity_stage(
                opportunity["id"], "demo_done", "Need another technical review", "2000-01-01T00:00:00Z",
            )
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        rolled_back = rollback_opportunity_stage(
            opportunity["id"], "demo_done", "Need another technical review", current["modified"],
        )
        self.assertEqual((rolled_back["stage"], rolled_back["budgetApprovedOn"]), ("demo_done", ""))
        latest = rolled_back["stageHistory"][0]
        self.assertEqual(
            (latest["from"], latest["to"], latest["source"], latest["event"], latest["reason"], latest["actor"]),
            ("rfq_validated", "demo_done", "rollback", "rollback", "Need another technical review", self.manager),
        )
        self.assertEqual(rolled_back["stageChangedAt"], latest["reachedAt"])
        self.assertNotIn("stageRollback", {row["field"] for row in rolled_back["history"]})

    def test_rollback_to_the_first_stage_no_longer_waits_for_demo_requests(self):
        account, site = self._account_site(self.sales, "ActiveRequestRollback")
        opportunity = self._demo_done(create_strategy_opportunity(self._input(account, site, self.sales)))
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

        frappe.set_user(self.manager)
        rolled_back = rollback_opportunity_stage(
            opportunity["id"], "qualified_opportunity", "Requirements changed", opportunity["modified"],
        )
        self.assertEqual(rolled_back["stage"], "qualified_opportunity")
        self.assertEqual(frappe.db.get_value("CRM Demo Request", request.name, "status"), "Engineer Review")

    def test_only_manager_can_delete_strategy_opportunity(self):
        account, site = self._account_site(self.other_sales, "Delete")
        opportunity = create_strategy_opportunity(
            self._input(account, site, self.other_sales, probabilityLevel="pipeline"),
        )
        stage_rows = {"opportunity": opportunity["id"]}
        self.assertEqual(self._probability_history_count(opportunity["id"]), 1)
        self.assertEqual(frappe.db.count("CRM Opportunity Stage History", stage_rows), 1)
        # Stakeholders and actions link to the Opportunity too, and their APIs only archive them.
        contact = create_contact({
            "accountId": account["id"], "name": "Delete Contact", "title": "Director",
            "department": "Engineering", "phone": "13800000002",
            "email": "delete-contact@example.invalid", "relationship": "Developing",
            "owner": self.other_sales, "status": "Active",
        })
        create_opportunity_stakeholder(opportunity["id"], {
            "contactId": contact["id"], "role": "Decision Maker", "influence": "High",
            "stance": "Support", "coverage": "Monthly", "isCoach": True,
            "winResult": "Budget approved", "opportunityNotes": "Confirm FAT attendees",
        })
        action = create_opportunity_action(
            opportunity["id"],
            {"title": "Confirm scope", "owner": self.other_sales, "due": "2026-09-01", "status": "Open"},
        )
        delete_opportunity_action(opportunity["id"], action["id"])

        def relation_counts() -> tuple[int, int]:
            return (
                frappe.db.count("CRM Opportunity Stakeholder", stage_rows),
                frappe.db.count("CRM Opportunity Action", stage_rows),
            )

        self.assertEqual(relation_counts(), (1, 1))
        # An edit leaves a field-history row, which also links to the Opportunity.
        frappe.set_user("Administrator")
        update_strategy_opportunity(opportunity["id"], {"title": "Delete II"}, opportunity["modified"])
        self.assertGreaterEqual(frappe.db.count("CRM Opportunity History", stage_rows), 1)

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            delete_strategy_opportunity(opportunity["id"])
        self.assertTrue(frappe.db.exists("CRM Opportunity", opportunity["id"]))
        self.assertEqual(self._probability_history_count(opportunity["id"]), 1)
        self.assertEqual(frappe.db.count("CRM Opportunity Stage History", stage_rows), 1)
        self.assertEqual(relation_counts(), (1, 1))

        frappe.set_user("Administrator")
        self.assertEqual(
            delete_strategy_opportunity(opportunity["id"]),
            {"id": opportunity["id"], "status": "Deleted"},
        )
        self.assertFalse(frappe.db.exists("CRM Opportunity", opportunity["id"]))
        self.assertEqual(self._probability_history_count(opportunity["id"]), 0)
        self.assertEqual(frappe.db.count("CRM Opportunity Stage History", stage_rows), 0)
        self.assertEqual(frappe.db.count("CRM Opportunity History", stage_rows), 0)
        self.assertEqual(relation_counts(), (0, 0))
