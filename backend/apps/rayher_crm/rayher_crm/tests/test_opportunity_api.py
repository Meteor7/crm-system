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
    request_internal_validation,
    rollback_opportunity_stage,
    update_opportunity_stakeholder,
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

    def test_s1_amount_is_optional_but_required_once_advanced(self):
        account, site = self._account_site(self.sales, "AmountOptional")
        payload = self._input(account, site, self.sales)
        payload.pop("amount")
        payload.pop("originalAmount")
        payload.pop("amountCny")

        created = create_strategy_opportunity(payload)
        self.assertEqual((created["amount"], created["originalAmount"], created["amountCny"]), ("", "", ""))
        # Stored as the columns' "not entered yet" 0, never read back as a 0 amount.
        self.assertEqual(
            tuple(frappe.db.get_value("CRM Opportunity", created["id"], ["amount", "original_amount", "amount_cny"])),
            (0, 0, 0),
        )
        # Blank and exact zero mean the same at S1.
        for amounts in (
            {"amount": "", "originalAmount": "", "amountCny": ""},
            {"amount": "0", "originalAmount": "0.00", "amountCny": 0},
        ):
            with self.subTest(amounts=amounts):
                unknown = create_strategy_opportunity(self._input(account, site, self.sales, **amounts))
                self.assertEqual((unknown["amount"], unknown["originalAmount"], unknown["amountCny"]), ("", "", ""))

        # Still at S1: an edit that also omits amounts is accepted, and the amounts reopen unknown.
        edited = update_strategy_opportunity(created["id"], {"title": "Still S1, no amount"}, created["modified"])
        self.assertEqual((edited["title"], edited["amount"], edited["amountCny"]), ("Still S1, no amount", "", ""))
        self.assertEqual(get_strategy_opportunity(created["id"])["originalAmount"], "")
        self.assertNotIn("amount", {row["field"] for row in edited["history"]})

        # At S1 an amount can be entered and taken out again; its history runs from and back to empty.
        priced = update_strategy_opportunity(
            created["id"], {"amount": "1000", "originalAmount": "1000", "amountCny": "1000"}, edited["modified"],
        )
        self.assertEqual((priced["amount"], priced["originalAmount"], priced["amountCny"]), ("1000.00", "1000.00", "1000.00"))
        cleared = update_strategy_opportunity(
            created["id"], {"amount": "", "originalAmount": "", "amountCny": ""}, priced["modified"],
        )
        self.assertEqual((cleared["amount"], cleared["originalAmount"], cleared["amountCny"]), ("", "", ""))
        self.assertEqual(
            sorted((row["from"], row["to"]) for row in cleared["history"] if row["field"] == "amount"),
            [("", "1000.00"), ("1000.00", "")],
        )

        # From Demo done on the amounts are required (#22): the Customer Review event leaves the Opportunity
        # at S1, waiting, and the save that enters the amounts applies the advance.
        waiting = advance_opportunity_fixture(cleared, "demo_done")
        self.assertEqual(
            (waiting["stage"], waiting["pendingStageAdvance"], waiting["amount"], waiting["amountCny"]),
            ("qualified_opportunity", "demo_done", "", ""),
        )
        advanced = update_strategy_opportunity(
            waiting["id"], {"amount": "1000", "originalAmount": "1000", "amountCny": "1000"}, waiting["modified"],
        )
        self.assertEqual((advanced["stage"], advanced["pendingStageAdvance"]), ("demo_done", ""))

        # An edit at S2 cannot take the amounts out again, and names the field to fill in
        # (amount and original amount as amountCny), not only a top-level message.
        for amounts, field_errors in (
            ({"amount": "", "originalAmount": "", "amountCny": ""}, {"amount": "Invalid amount"}),
            (
                {"currency": "USD", "amount": "50000.00", "originalAmount": "50000.00", "amountCny": ""},
                {"amountCny": "Required"},
            ),
            ({"amount": "0", "originalAmount": "50000.00", "amountCny": "50000.00"}, {"amount": "Invalid amount"}),
            ({"amount": "-1", "originalAmount": "50000.00", "amountCny": "50000.00"}, {"amount": "Invalid amount"}),
            (
                {"amount": "50000.001", "originalAmount": "50000.00", "amountCny": "50000.00"},
                {"amount": "Invalid amount"},
            ),
            (
                {"amount": "50000.00", "originalAmount": "0", "amountCny": "50000.00"},
                {"originalAmount": "Invalid amount"},
            ),
        ):
            with self.subTest(amounts=amounts), self.assertRaises(CrmApiException) as invalid:
                update_strategy_opportunity(advanced["id"], amounts, advanced["modified"])
            self.assertEqual((invalid.exception.code, invalid.exception.field_errors), ("VALIDATION_ERROR", field_errors))

        filled = update_strategy_opportunity(
            advanced["id"],
            {"title": "S2 with amount", "amount": "50000.00", "originalAmount": "50000.00", "amountCny": "50000.00"},
            advanced["modified"],
        )
        self.assertEqual((filled["amount"], filled["originalAmount"], filled["amountCny"]), ("50000.00", "50000.00", "50000.00"))

    def test_no_forward_stage_move_without_the_amounts(self):
        # Rows from before the gate may sit past S1 without amounts; none of them moves forward until
        # the amounts are entered. Marking lost and a Manager rollback stay available.
        account, site = self._account_site(self.sales, "Gate")
        moves = {
            "demo_done": lambda current: confirm_budget_approved(
                current["id"], {"approvedOn": frappe.utils.today()}, current["modified"],
            ),
            "customer_budget_approved": lambda current: advance_opportunity_for_event(
                current["id"], "rfq_approved", reference_doctype="CRM RFQ", reference_name="gate",
            ),
            "rfq_validated": lambda current: advance_opportunity_for_event(
                current["id"], "quotation_published", reference_doctype="CRM Quotation Version", reference_name="gate",
            ),
            # Refused when it is requested, before any Manager is asked to approve it.
            "quotation_sent": lambda current: request_internal_validation(current["id"], {}, current["modified"]),
        }
        for stage, move in moves.items():
            with self.subTest(stage=stage):
                frappe.set_user(self.sales)
                opportunity = advance_opportunity_fixture(
                    create_strategy_opportunity(self._input(account, site, self.sales, title=f"Gate {stage}")), stage,
                )
                frappe.db.set_value(
                    "CRM Opportunity", opportunity["id"], {"amount": 0, "original_amount": 0, "amount_cny": 0},
                    update_modified=False,
                )
                current = get_strategy_opportunity(opportunity["id"])
                self.assertEqual((current["stage"], current["amount"], current["amountCny"]), (stage, "", ""))
                with self.assertRaises(CrmApiException) as blocked:
                    move(current)
                self.assertEqual(
                    (blocked.exception.code, blocked.exception.field_errors),
                    (
                        "VALIDATION_ERROR",
                        {
                            "amount": "Required from Demo done", "originalAmount": "Required from Demo done",
                            "amountCny": "Required from Demo done",
                        },
                    ),
                )
                self.assertEqual(get_strategy_opportunity(opportunity["id"])["stage"], stage)

                if stage != "demo_done":
                    frappe.set_user(self.manager)
                    rolled_back = rollback_opportunity_stage(
                        opportunity["id"], "demo_done", "Amounts were never entered", current["modified"],
                    )
                    self.assertEqual(rolled_back["stage"], "demo_done")
                    current = rolled_back
                frappe.set_user(self.sales)
                lost = mark_opportunity_lost(opportunity["id"], {"lostReason": "No budget"}, current["modified"])
                self.assertEqual(lost["stage"], "lost")

    def test_an_amount_without_an_original_amount_is_its_own_original(self):
        # Every edit past S1 requires the original amount, so an Opportunity must not get there without one.
        account, site = self._account_site(self.sales, "Original")
        created = create_strategy_opportunity(self._input(
            account, site, self.sales, amount="100", originalAmount="", amountCny="100",
        ))
        self.assertEqual((created["amount"], created["originalAmount"]), ("100.00", "100.00"))
        # An original amount that was entered is kept, and one sent blank beside a new amount follows it.
        kept = update_strategy_opportunity(created["id"], {"amount": "120", "originalAmount": "110"}, created["modified"])
        self.assertEqual((kept["amount"], kept["originalAmount"], kept["amountCny"]), ("120.00", "110.00", "120.00"))
        unpriced = create_strategy_opportunity(self._input(
            account, site, self.sales, title="Unpriced original", amount="", originalAmount="", amountCny="",
        ))
        priced = update_strategy_opportunity(
            unpriced["id"], {"amount": "80", "originalAmount": "", "amountCny": "80"}, unpriced["modified"],
        )
        self.assertEqual((priced["amount"], priced["originalAmount"]), ("80.00", "80.00"))

        # A row from before this rule may hold an amount without its original: the Demo done waits for it
        # like for any other missing amount, and the next save completes it and moves the Opportunity.
        legacy = create_strategy_opportunity(self._input(account, site, self.sales, title="Legacy original"))
        frappe.db.set_value("CRM Opportunity", legacy["id"], "original_amount", 0, update_modified=False)
        waiting = self._demo_done(legacy)
        self.assertEqual(
            (waiting["stage"], waiting["pendingStageAdvance"], waiting["originalAmount"]),
            ("qualified_opportunity", "demo_done", ""),
        )
        moved = update_strategy_opportunity(legacy["id"], {"title": "Legacy original, saved"}, waiting["modified"])
        self.assertEqual(
            (moved["stage"], moved["pendingStageAdvance"], moved["originalAmount"]), ("demo_done", "", moved["amount"]),
        )
        # From there on an ordinary edit goes through.
        self.assertEqual(
            update_strategy_opportunity(legacy["id"], {"title": "Edited at Demo done"}, moved["modified"])["title"],
            "Edited at Demo done",
        )

    def test_a_waiting_opportunity_can_be_deleted_with_its_notice(self):
        account, site = self._account_site(self.sales, "WaitingDelete")
        opportunity = create_strategy_opportunity(self._input(
            account, site, self.sales, amount="", originalAmount="", amountCny="",
        ))
        waiting = self._demo_done(opportunity)
        self.assertEqual(waiting["pendingStageAdvance"], "demo_done")
        notice = {"source_doctype": "CRM Opportunity", "source_name": opportunity["id"]}
        self.assertEqual(frappe.db.count("CRM Notification Event", notice), 1)
        # Another Opportunity's notice is not touched.
        other = create_strategy_opportunity(self._input(
            account, site, self.sales, title="Other waiting", amount="", originalAmount="", amountCny="",
        ))
        self._demo_done(other)
        other_notice = {"source_doctype": "CRM Opportunity", "source_name": other["id"]}

        frappe.set_user("Administrator")
        self.assertEqual(delete_strategy_opportunity(opportunity["id"]), {"id": opportunity["id"], "status": "Deleted"})
        self.assertFalse(frappe.db.exists("CRM Opportunity", opportunity["id"]))
        self.assertEqual(frappe.db.count("CRM Notification Event", notice), 0)
        self.assertEqual(frappe.db.count("CRM Notification Event", other_notice), 1)

    def test_a_cny_opportunity_takes_its_cny_amount_from_the_amount(self):
        # A CNY Opportunity has one amount (#87): whatever the form sends as the CNY amount, the amount wins.
        account, site = self._account_site(self.sales, "CnyFollows")
        created = create_strategy_opportunity(self._input(
            account, site, self.sales, currency="CNY", amount="100", originalAmount="100", amountCny="90",
        ))
        self.assertEqual((created["amount"], created["amountCny"]), ("100.00", "100.00"))
        repriced = update_strategy_opportunity(created["id"], {"amount": "250", "originalAmount": "250"}, created["modified"])
        self.assertEqual((repriced["amount"], repriced["amountCny"]), ("250.00", "250.00"))
        only_cny = update_strategy_opportunity(created["id"], {"amountCny": "999"}, repriced["modified"])
        self.assertEqual((only_cny["amount"], only_cny["amountCny"]), ("250.00", "250.00"))
        blank = create_strategy_opportunity(self._input(
            account, site, self.sales, title="CNY, amount unknown", currency="CNY",
            amount="", originalAmount="", amountCny="500",
        ))
        self.assertEqual((blank["amount"], blank["amountCny"]), ("", ""))

        # Another currency keeps the CNY amount Sales entered by hand.
        foreign = create_strategy_opportunity(self._input(
            account, site, self.sales, title="USD deal", currency="USD",
            amount="100", originalAmount="100", amountCny="720",
        ))
        self.assertEqual((foreign["amount"], foreign["amountCny"]), ("100.00", "720.00"))
        # Switching it to CNY makes the CNY amount follow from then on.
        switched = update_strategy_opportunity(foreign["id"], {"currency": "CNY"}, foreign["modified"])
        self.assertEqual((switched["amount"], switched["amountCny"]), ("100.00", "100.00"))

        # Leaving CNY does not keep the mirrored figure as a 1:1 conversion: the CNY amount is unknown
        # again at S1, and asked for from Demo done on, unless the caller sends one with the change.
        left = update_strategy_opportunity(created["id"], {"currency": "USD"}, only_cny["modified"])
        self.assertEqual((left["currency"], left["amount"], left["amountCny"]), ("USD", "250.00", ""))
        advanced = self._demo_done(create_strategy_opportunity(self._input(
            account, site, self.sales, title="CNY at Demo done", currency="CNY", amount="300", originalAmount="300",
        )))
        with self.assertRaises(CrmApiException) as unconverted:
            update_strategy_opportunity(advanced["id"], {"currency": "USD"}, advanced["modified"])
        self.assertEqual(unconverted.exception.field_errors, {"amountCny": "Required"})
        converted = update_strategy_opportunity(
            advanced["id"], {"currency": "USD", "amountCny": "2150"}, advanced["modified"],
        )
        self.assertEqual((converted["currency"], converted["amount"], converted["amountCny"]), ("USD", "300.00", "2150.00"))

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

    def test_a_deal_lost_at_stage_one_stays_editable_without_amounts(self):
        account, site = self._account_site(self.sales, "LostEarly")
        blank = {"amount": "", "originalAmount": "", "amountCny": ""}
        early = create_strategy_opportunity(self._input(account, site, self.sales, **blank))
        lost = mark_opportunity_lost(early["id"], {"lostReason": "Budget frozen"}, early["modified"])
        self.assertEqual((lost["stage"], lost["lostAtStage"], lost["amount"]), ("lost", "qualified_opportunity", ""))
        # It never got past S1, so a later edit does not ask for amounts it never had.
        edited = update_strategy_opportunity(lost["id"], {"competition": "Lost to a rival"}, lost["modified"])
        self.assertEqual(
            (edited["stage"], edited["competition"], edited["amount"], edited["amountCny"]),
            ("lost", "Lost to a rival", "", ""),
        )
        # A migrated loss that does not say where it was lost is not known to be an early one: amounts are required.
        frappe.db.set_value("CRM Opportunity", lost["id"], "lost_at_stage", None, update_modified=False)
        unknown_stage = get_strategy_opportunity(lost["id"])
        with self.assertRaises(CrmApiException) as undated:
            update_strategy_opportunity(lost["id"], {"competition": "Unknown stage"}, unknown_stage["modified"])
        self.assertEqual(undated.exception.field_errors, {"amount": "Invalid amount"})
        # A deal lost further on had its amounts to get there, and an edit cannot take them out.
        late = self._demo_done(create_strategy_opportunity(self._input(account, site, self.sales, title="Late")))
        lost_late = mark_opportunity_lost(late["id"], {"lostReason": "Competitor won"}, late["modified"])
        self.assertEqual(lost_late["lostAtStage"], "demo_done")
        with self.assertRaises(CrmApiException) as missing:
            update_strategy_opportunity(lost_late["id"], {"competition": "Too late", **blank}, lost_late["modified"])
        self.assertEqual(
            (missing.exception.code, missing.exception.field_errors), ("VALIDATION_ERROR", {"amount": "Invalid amount"}),
        )

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
            # Blank or zero is an amount not entered yet at S1; anything else still has to be an exact amount.
            ({"amount": "-1"}, "amount"), ({"amount": "1.001"}, "amount"),
            ({"originalAmount": True}, "originalAmount"), ({"amountCny": "not-money"}, "amountCny"),
            ({"intentScore": -1}, "intentScore"), ({"poDate": "2026-02-30"}, "poDate"),
            ({"stage": "Open"}, "stage"), ({"stage": "需求发现"}, "stage"),
            ({"probabilityLevel": "certain"}, "probabilityLevel"), ({"currency": "ZZZ"}, "currency"),
        ]
        for overrides, fieldname in cases:
            with self.subTest(fieldname=fieldname):
                with self.assertRaises(CrmApiException) as invalid:
                    create_strategy_opportunity(self._input(account, site, self.sales, **overrides))
                self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
                # A money field also names itself, not only a message, and the message is the one the front end maps.
                if fieldname in ("amount", "originalAmount", "amountCny"):
                    self.assertEqual(invalid.exception.field_errors, {fieldname: "Invalid amount"})
                    self.assertEqual(
                        invalid.exception.public_message,
                        f"{fieldname} must be positive with at most two decimal places.",
                    )

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

    def test_single_sales_objective_has_a_length_limit(self):
        account, site = self._account_site(self.sales, "ObjectiveLimit")
        limit = "x" * 2000
        # The limit counts the trimmed text.
        accepted = create_strategy_opportunity(self._input(
            account, site, self.sales, title="At the limit", singleSalesObjective=f"  {limit}  ",
        ))
        self.assertEqual(accepted["singleSalesObjective"], limit)
        too_long = {"singleSalesObjective": limit + "x"}
        expected = ("VALIDATION_ERROR", {"singleSalesObjective": "Maximum length is 2000"})
        # The front end maps this exact message to its Chinese copy.
        message = "singleSalesObjective is too long."
        with self.assertRaises(CrmApiException) as created:
            create_strategy_opportunity(self._input(account, site, self.sales, title="Too long", **too_long))
        self.assertEqual((created.exception.code, created.exception.field_errors), expected)
        self.assertEqual(created.exception.public_message, message)
        with self.assertRaises(CrmApiException) as updated:
            update_strategy_opportunity(accepted["id"], too_long, accepted["modified"])
        self.assertEqual((updated.exception.code, updated.exception.field_errors), expected)
        self.assertEqual(get_strategy_opportunity(accepted["id"])["singleSalesObjective"], limit)

        # A value that is already stored stays valid even when it is longer than the limit (Frappe's HTML cleaning
        # of Small Text can lengthen one): an unrelated edit goes through, a changed value is held to the limit.
        overlong = "y" * 2001
        frappe.db.set_value("CRM Opportunity", accepted["id"], "single_sales_objective", overlong, update_modified=False)
        stored = get_strategy_opportunity(accepted["id"])
        retitled = update_strategy_opportunity(accepted["id"], {"title": "Retitled"}, stored["modified"])
        self.assertEqual((retitled["title"], retitled["singleSalesObjective"]), ("Retitled", overlong))
        with self.assertRaises(CrmApiException) as changed:
            update_strategy_opportunity(accepted["id"], {"singleSalesObjective": "z" * 2001}, retitled["modified"])
        self.assertEqual((changed.exception.code, changed.exception.field_errors), expected)
        # The same holds when the stored value is padded with blanks (the request value is trimmed).
        frappe.db.set_value(
            "CRM Opportunity", accepted["id"], "single_sales_objective", " " + overlong + "\n", update_modified=False,
        )
        padded = get_strategy_opportunity(accepted["id"])
        again = update_strategy_opportunity(accepted["id"], {"title": "Retitled again"}, padded["modified"])
        self.assertEqual(again["title"], "Retitled again")
        shortened = update_strategy_opportunity(
            accepted["id"], {"singleSalesObjective": "short"}, again["modified"],
        )
        self.assertEqual(shortened["singleSalesObjective"], "short")

    def test_single_sales_objective_and_stakeholder_response_mode(self):
        account, site = self._account_site(self.sales, "BlueSheet")
        # Callers that never send the objective still create an Opportunity; it reads back as not set.
        plain = create_strategy_opportunity(self._input(account, site, self.sales, title="Plain Blue Sheet"))
        self.assertEqual(plain["singleSalesObjective"], "")

        created = create_strategy_opportunity(self._input(
            account, site, self.sales, singleSalesObjective="  Win the Q4 wafer inspection line  ",
        ))
        self.assertEqual(created["singleSalesObjective"], "Win the Q4 wafer inspection line")

        updated = update_strategy_opportunity(
            created["id"], {"singleSalesObjective": "Revised objective"}, created["modified"],
        )
        self.assertEqual(updated["singleSalesObjective"], "Revised objective")
        self.assertIn(
            ("single_sales_objective", "Win the Q4 wafer inspection line", "Revised objective"),
            [(row["field"], row["from"], row["to"]) for row in updated["history"]],
        )
        # A partial edit that does not resend the objective keeps the stored one.
        retitled = update_strategy_opportunity(created["id"], {"title": "Another edit"}, updated["modified"])
        self.assertEqual((retitled["title"], retitled["singleSalesObjective"]), ("Another edit", "Revised objective"))
        self.assertEqual(get_strategy_opportunity(created["id"])["singleSalesObjective"], "Revised objective")
        listed, _, _, _ = list_strategy_opportunities({"opportunityId": created["id"], "page": 1, "pageSize": 20})
        self.assertEqual([item["singleSalesObjective"] for item in listed], ["Revised objective"])

        contact = create_contact({
            "accountId": account["id"], "name": "Pat Buyer", "title": "Buyer",
            "department": "Procurement", "phone": "13800000002",
            "email": "bluesheet-buyer@example.invalid", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        stakeholder_input = {
            "contactId": contact["id"], "role": "Economic Buyer", "influence": "High", "stance": "Support",
            "coverage": "Weekly", "responseMode": "Growth",
        }

        def rejected(function, *args) -> tuple:
            with self.assertRaises(CrmApiException) as raised:
                function(*args)
            return raised.exception.code, raised.exception.field_errors

        invalid = ("VALIDATION_ERROR", {"responseMode": "Invalid value"})
        self.assertEqual(rejected(
            create_opportunity_stakeholder, created["id"], {**stakeholder_input, "responseMode": "Panic"},
        ), invalid)
        self.assertEqual(get_strategy_opportunity(created["id"])["stakeholders"], [])

        stakeholder = create_opportunity_stakeholder(created["id"], stakeholder_input)
        self.assertEqual(stakeholder["responseMode"], "Growth")

        def stored_mode(stakeholder_id: str) -> str:
            reloaded = get_strategy_opportunity(created["id"])
            return next(item["responseMode"] for item in reloaded["stakeholders"] if item["id"] == stakeholder_id)

        self.assertEqual(stored_mode(stakeholder["id"]), "Growth")
        for mode in ("Even Keel", "Overconfident", "Trouble"):
            with self.subTest(mode=mode):
                changed = update_opportunity_stakeholder(
                    created["id"], stakeholder["id"], {**stakeholder_input, "responseMode": mode},
                )
                self.assertEqual(changed["responseMode"], mode)
                self.assertEqual(stored_mode(stakeholder["id"]), mode)
        # Updates take the full payload; the editor resends the stored mode, so an unrelated edit keeps it.
        restanced = update_opportunity_stakeholder(created["id"], stakeholder["id"], {
            **stakeholder_input, "stance": "Neutral", "responseMode": stored_mode(stakeholder["id"]),
        })
        self.assertEqual((restanced["stance"], restanced["responseMode"]), ("Neutral", "Trouble"))
        self.assertEqual(stored_mode(stakeholder["id"]), "Trouble")

        for mode in ("Panic", "growth"):
            with self.subTest(mode=mode):
                self.assertEqual(rejected(
                    update_opportunity_stakeholder, created["id"], stakeholder["id"],
                    {**stakeholder_input, "responseMode": mode},
                ), invalid)
        self.assertEqual(stored_mode(stakeholder["id"]), "Trouble")
        # Non-string falsy values are rejected as well; they must not silently clear the stored mode.
        for mode in (False, 0, [], {}):
            with self.subTest(mode=repr(mode)):
                self.assertEqual(rejected(
                    update_opportunity_stakeholder, created["id"], stakeholder["id"],
                    {**stakeholder_input, "responseMode": mode},
                ), invalid)
                self.assertEqual(stored_mode(stakeholder["id"]), "Trouble")

        # A page from before the field does not send the mode at all: the update keeps what is stored.
        # Only null or "" clears it.
        omitted = {key: value for key, value in stakeholder_input.items() if key != "responseMode"}
        kept = update_opportunity_stakeholder(created["id"], stakeholder["id"], {**omitted, "coverage": "Quarterly"})
        self.assertEqual((kept["coverage"], kept["responseMode"]), ("Quarterly", "Trouble"))
        self.assertEqual(stored_mode(stakeholder["id"]), "Trouble")
        blanked = update_opportunity_stakeholder(
            created["id"], stakeholder["id"], {**omitted, "responseMode": None},
        )
        self.assertEqual(blanked["responseMode"], "")
        update_opportunity_stakeholder(
            created["id"], stakeholder["id"], {**stakeholder_input, "responseMode": "Trouble"},
        )
        self.assertEqual(stored_mode(stakeholder["id"]), "Trouble")

        cleared = update_opportunity_stakeholder(
            created["id"], stakeholder["id"], {**stakeholder_input, "responseMode": ""},
        )
        self.assertEqual(cleared["responseMode"], "")
        self.assertEqual(stored_mode(stakeholder["id"]), "")

        # A stakeholder from before the field has no mode stored; it reads as blank and stays editable.
        legacy_contact = create_contact({
            "accountId": account["id"], "name": "Lee Legacy", "title": "Engineer",
            "department": "Engineering", "phone": "13800000002",
            "email": "bluesheet-legacy@example.invalid", "relationship": "Developing",
            "owner": self.sales, "status": "Active",
        })
        legacy_input = {**stakeholder_input, "contactId": legacy_contact["id"]}
        legacy_input.pop("responseMode")
        legacy = create_opportunity_stakeholder(created["id"], legacy_input)
        self.assertEqual(legacy["responseMode"], "")
        frappe.db.set_value("CRM Opportunity Stakeholder", legacy["id"], "response_mode", None, update_modified=False)
        self.assertEqual(stored_mode(legacy["id"]), "")
        recovered = update_opportunity_stakeholder(
            created["id"], legacy["id"], {**legacy_input, "coverage": "Monthly", "responseMode": ""},
        )
        self.assertEqual((recovered["coverage"], recovered["responseMode"]), ("Monthly", ""))
        self.assertEqual(stored_mode(legacy["id"]), "")
        # A page from before the field edits that stakeholder without sending the mode: still blank, no error.
        untouched = update_opportunity_stakeholder(created["id"], legacy["id"], {**legacy_input, "coverage": "Quarterly"})
        self.assertEqual((untouched["coverage"], untouched["responseMode"]), ("Quarterly", ""))
