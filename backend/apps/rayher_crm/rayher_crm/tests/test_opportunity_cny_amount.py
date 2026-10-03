from __future__ import annotations

import csv

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.patches.v1_0 import backfill_opportunity_cny_amount
from rayher_crm.services.accounts import create_account
from rayher_crm.services.leads import convert_lead, create_lead
from rayher_crm.services.opportunities import (
    create_strategy_opportunity,
    get_strategy_opportunity,
    update_strategy_opportunity,
)
from rayher_crm.services.sites import create_site
from rayher_crm.setup import opportunity_cny_backfill
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestOpportunityCnyAmount(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-cny-sales@example.invalid", "CRM Sales")
        frappe.set_user(self.sales)
        self.account = create_account({
            "name": f"CNY Amount {frappe.generate_hash(length=6)}", "shortName": "CNY", "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "East China", "owner": self.sales,
        })
        self.site = create_site(self.account["id"], {
            "name": "CNY Amount Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })

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

    def _input(self, **overrides) -> dict:
        payload = {
            "probabilityLevel": "pipeline", "accountId": self.account["id"], "siteId": self.site["id"],
            "title": "CNY Amount Opportunity", "owner": self.sales, "amount": "200000", "intentScore": 40,
            "poDate": "2026-12-31", "toolType": "Inspection", "saleType": "New Equipment", "subRegion": "East China",
            "currency": "CNY", "originalAmount": "200000", "amountCny": "200000", "qualificationConfirmed": True,
        }
        payload.update(overrides)
        return payload

    def _history(self, opportunity_id: str, field: str) -> list[tuple[str, str, str]]:
        rows = frappe.get_all(
            "CRM Opportunity History", filters={"opportunity": opportunity_id, "field": field},
            fields=["from_value", "to_value", "actor"], order_by="creation asc",
        )
        return [(row.from_value or "", row.to_value or "", row.actor) for row in rows]

    def _clear_cny_amount(self, opportunity_id: str) -> None:
        # Test data only: an Opportunity from before the field, or one Sales have not filled in yet.
        frappe.db.set_value("CRM Opportunity", opportunity_id, "amount_cny", 0, update_modified=False)

    def test_create_rejects_an_invalid_cny_amount_leaves_a_missing_one_unknown_and_returns_it(self):
        for value in ("-5", "1.234", "not-money"):
            with self.assertRaises(CrmApiException) as failure:
                create_strategy_opportunity(self._input(amountCny=value))
            self.assertEqual(failure.exception.code, "VALIDATION_ERROR", value)
            self.assertEqual(failure.exception.field_errors, {"amountCny": "Invalid amount"}, value)
        # A new Opportunity is qualified (S1), where the CNY amount may still be unknown: "", never 0.
        # That is for another currency; a CNY Opportunity takes its CNY amount from its amount (#87).
        for currency, expected in (("USD", ""), ("CNY", "200000.00")):
            for value in (None, "", "0"):
                payload = self._input(currency=currency)
                if value is None:
                    payload.pop("amountCny")
                else:
                    payload["amountCny"] = value
                self.assertEqual(create_strategy_opportunity(payload)["amountCny"], expected, (currency, value))

        created = create_strategy_opportunity(self._input(currency="USD", amount="30000", originalAmount="30000", amountCny="213000.5"))

        self.assertEqual((created["currency"], created["amount"], created["amountCny"]), ("USD", "30000.00", "213000.50"))
        self.assertEqual(get_strategy_opportunity(created["id"])["amountCny"], "213000.50")

    def test_an_empty_cny_amount_blocks_other_edits_until_it_is_filled_in(self):
        # Past S1 only: a qualified Opportunity may keep its amounts unknown.
        created = advance_opportunity_fixture(
            create_strategy_opportunity(self._input(currency="USD", amountCny="1")), "demo_done",
        )
        self._clear_cny_amount(created["id"])
        current = get_strategy_opportunity(created["id"])
        self.assertEqual(current["amountCny"], "")

        with self.assertRaises(CrmApiException) as blocked:
            update_strategy_opportunity(created["id"], {"title": "Renamed without CNY"}, current["modified"])
        self.assertEqual(blocked.exception.field_errors, {"amountCny": "Required"})

        updated = update_strategy_opportunity(
            created["id"], {"title": "Renamed with CNY", "amountCny": "1420000.40"}, current["modified"],
        )
        self.assertEqual((updated["title"], updated["amountCny"]), ("Renamed with CNY", "1420000.40"))
        # The first CNY amount is filled in from empty, not changed from 0.
        self.assertEqual(self._history(created["id"], "amount_cny"), [("", "1420000.40", self.sales)])

    def test_saving_unchanged_amounts_records_no_amount_history(self):
        # In USD, so the CNY amount is one Sales enter by hand and can change on its own.
        created = create_strategy_opportunity(self._input(currency="USD"))

        # The editor sends the whole form back, amounts included, even when only the title changed.
        renamed = update_strategy_opportunity(
            created["id"], self._input(title="Renamed only", currency="USD"), created["modified"],
        )
        changed = update_strategy_opportunity(created["id"], {"amountCny": "210000.5"}, renamed["modified"])

        fields = frappe.get_all("CRM Opportunity History", filters={"opportunity": created["id"]}, pluck="field")
        self.assertNotIn("amount", fields)
        self.assertNotIn("original_amount", fields)
        self.assertEqual(changed["amountCny"], "210000.50")
        self.assertEqual(self._history(created["id"], "amount_cny"), [("200000.00", "210000.50", self.sales)])

    def test_a_cny_opportunity_saved_without_its_cny_amount_is_filled_by_the_second_backfill(self):
        # Between #120 and the CNY rule a CNY Opportunity could be saved with an amount and no CNY amount.
        from rayher_crm.patches.v1_0 import sync_cny_opportunity_amounts

        created = create_strategy_opportunity(self._input(title="Saved before the CNY rule", amount="64000.5", originalAmount="64000.5"))
        foreign = create_strategy_opportunity(self._input(title="Saved in USD", currency="USD", amountCny=""))
        self._clear_cny_amount(created["id"])
        self.assertEqual(get_strategy_opportunity(created["id"])["amountCny"], "")

        frappe.set_user("Administrator")
        sync_cny_opportunity_amounts.execute()
        sync_cny_opportunity_amounts.execute()

        self.assertEqual(get_strategy_opportunity(created["id"])["amountCny"], "64000.50")
        self.assertEqual(self._history(created["id"], "amount_cny"), [("", "64000.50", "Administrator")])
        # Another currency has no CNY amount to derive: it stays for Sales to enter.
        self.assertEqual(get_strategy_opportunity(foreign["id"])["amountCny"], "")

    def test_a_cny_opportunity_holding_a_different_cny_amount_takes_its_amount_in_the_second_backfill(self):
        from rayher_crm.patches.v1_0 import sync_cny_opportunity_amounts

        divergent = create_strategy_opportunity(self._input(title="CNY amount typed apart"))
        unpriced = create_strategy_opportunity(self._input(title="CNY amount beside no amount", amount="", originalAmount=""))
        foreign = create_strategy_opportunity(self._input(title="Saved in USD", currency="USD", amountCny="1420000"))
        # Test data only: a CNY amount entered by hand before a CNY Opportunity took it from its amount.
        frappe.db.set_value("CRM Opportunity", divergent["id"], "amount_cny", 199999, update_modified=False)
        frappe.db.set_value("CRM Opportunity", unpriced["id"], "amount_cny", 500, update_modified=False)
        modified = frappe.db.get_value("CRM Opportunity", divergent["id"], "modified")

        frappe.set_user("Administrator")
        # The dry run names what the patch is about to overwrite, with the old and the new value, and changes nothing.
        dry_run = opportunity_cny_backfill.dry_run()
        planned = dry_run["sync"]
        listed = {row["name"]: (row["amountCny"], row["becomes"]) for row in planned["opportunities"]}
        self.assertEqual(listed[divergent["id"]], ("199999.00", "200000.00"))
        self.assertEqual(listed[unpriced["id"]], ("500.00", ""))
        self.assertNotIn(foreign["id"], listed)
        self.assertEqual(planned["count"], len(listed))
        self.assertTrue(planned["report"].endswith(".csv"))
        # The one that ends up without a CNY amount is counted among those Sales still have to fill in,
        # with the empty CNY amount it will have; the one that takes its amount is not.
        with open(dry_run["stillMissing"]["report"], encoding="utf-8-sig", newline="") as handle:
            still_missing = {row["opportunity"]: row["amount_cny"] for row in csv.DictReader(handle)}
        self.assertEqual(still_missing.get(unpriced["id"]), "")
        self.assertNotIn(divergent["id"], still_missing)
        self.assertEqual(dry_run["stillMissing"]["count"], len(still_missing))
        self.assertEqual(frappe.db.get_value("CRM Opportunity", divergent["id"], "amount_cny"), 199999)
        self.assertEqual(self._history(divergent["id"], "amount_cny"), [])

        sync_cny_opportunity_amounts.execute()
        sync_cny_opportunity_amounts.execute()

        self.assertEqual(get_strategy_opportunity(divergent["id"])["amountCny"], "200000.00")
        # One history row from the old value to the new, and the Opportunity does not look edited.
        self.assertEqual(self._history(divergent["id"], "amount_cny"), [("199999.00", "200000.00", "Administrator")])
        self.assertEqual(frappe.db.get_value("CRM Opportunity", divergent["id"], "modified"), modified)
        # An unknown amount leaves the CNY amount unknown as well; the history row keeps what was there.
        self.assertEqual(
            (get_strategy_opportunity(unpriced["id"])["amount"], get_strategy_opportunity(unpriced["id"])["amountCny"]),
            ("", ""),
        )
        self.assertEqual(self._history(unpriced["id"], "amount_cny"), [("500.00", "", "Administrator")])
        # A hand-entered CNY amount in another currency is a conversion, not a copy: it stays.
        self.assertEqual(get_strategy_opportunity(foreign["id"])["amountCny"], "1420000.00")
        self.assertEqual(self._history(foreign["id"], "amount_cny"), [])

    def test_lead_conversion_stores_the_cny_amount(self):
        lead = create_lead({
            "name": "CNY Conversion Lead", "company": self.account["name"], "title": "Process Manager",
            "phone": "13800000004", "email": "cny.conversion@example.invalid", "source": "Trade Show",
            "status": "New", "owner": self.sales, "interest": "Inspection", "firstContactNote": "Met at exhibition",
            "nextAction": "Call back", "nextActionDue": "2026-08-20", "activities": [],
        })
        conversion = {
            "accountId": self.account["id"], "siteId": self.site["id"],
            "newContact": {
                "name": "CNY Conversion Contact", "title": "Process Manager", "department": "Process",
                "phone": "13800000005", "relationship": "Developing", "status": "Active", "owner": self.sales,
            },
            "opportunityTitle": "CNY Conversion Opportunity", "opportunityAmount": "250000.50",
            "opportunityCloseDate": "2026-12-31", "opportunityOwner": self.sales, "toolType": "Inspection",
            "qualificationConfirmed": True, "opportunityProbabilityLevel": "pipeline",
        }
        # A conversion may leave the CNY amount unknown (test_lead_api); an invalid one is still refused.
        before = frappe.db.count("CRM Opportunity")
        with self.assertRaises(CrmApiException) as invalid:
            convert_lead(lead["id"], {**conversion, "opportunityAmountCny": "-1"})
        self.assertEqual(invalid.exception.field_errors, {"opportunityAmountCny": "Invalid amount"})
        self.assertEqual(frappe.db.count("CRM Opportunity"), before)

        converted = convert_lead(lead["id"], {**conversion, "opportunityAmountCny": "250000.5"})

        self.assertEqual(get_strategy_opportunity(converted["opportunityId"])["amountCny"], "250000.50")

    def test_backfill_copies_cny_amounts_once_and_lists_the_rest(self):
        cny = create_strategy_opportunity(self._input(title="Backfill CNY", amount="880000.5", originalAmount="880000.5"))
        usd = create_strategy_opportunity(self._input(title="Backfill USD", currency="USD", amount="120000", originalAmount="120000"))
        kept = create_strategy_opportunity(self._input(title="Backfill kept"))
        # Test data only: a CNY amount entered by hand before a CNY Opportunity took it from its amount.
        frappe.db.set_value("CRM Opportunity", kept["id"], "amount_cny", 199999, update_modified=False)
        for opportunity in (cny, usd):
            self._clear_cny_amount(opportunity["id"])
        modified = frappe.db.get_value("CRM Opportunity", cny["id"], "modified")

        planned = opportunity_cny_backfill.dry_run()
        self.assertEqual(frappe.db.get_value("CRM Opportunity", cny["id"], "amount_cny"), 0)
        self.assertGreaterEqual(planned["fill"]["count"], 1)

        frappe.set_user("Administrator")
        backfill_opportunity_cny_amount.execute()
        backfill_opportunity_cny_amount.execute()

        self.assertEqual(get_strategy_opportunity(cny["id"])["amountCny"], "880000.50")
        self.assertEqual(get_strategy_opportunity(usd["id"])["amountCny"], "")
        self.assertEqual(get_strategy_opportunity(kept["id"])["amountCny"], "199999.00")
        # One history row from the migration user, and the Opportunity does not look edited.
        self.assertEqual(self._history(cny["id"], "amount_cny"), [("", "880000.50", "Administrator")])
        self.assertEqual(frappe.db.get_value("CRM Opportunity", cny["id"], "modified"), modified)
        self.assertEqual(self._history(kept["id"], "amount_cny"), [])

        missing = opportunity_cny_backfill.list_missing()
        names = {row["name"] for row in missing["opportunities"]}
        self.assertIn(usd["id"], names)
        self.assertNotIn(cny["id"], names)
        self.assertEqual(
            next(row for row in missing["opportunities"] if row["name"] == usd["id"])["currency"], "USD",
        )
