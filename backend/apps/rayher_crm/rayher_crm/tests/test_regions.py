from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.patches.v1_0 import normalize_crm_regions
from rayher_crm.services.accounts import create_account, list_account_regions, list_accounts, update_account
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.regions import REGION_FIELD, REGION_PRESETS, preset_region
from rayher_crm.services.sites import create_site
from rayher_crm.setup import custom_fields
from rayher_crm.setup import region_migration as migration
from rayher_crm.setup.region_migration import plan_values


class TestRegionSpellings(FrappeTestCase):
    def test_chinese_and_short_spellings_name_the_english_preset(self):
        cases = {
            "华东": "East China", "华东区": "East China", " east ": "East China", "EAST-CHINA": "East China",
            "华东 East China": "East China", "華南": "South China", "华西地区": "West China",
            "North": "North China", "华中": "Central China", "Central China": "Central China",
        }
        for value, preset in cases.items():
            self.assertEqual(preset_region(value), preset, value)
        for value in ("华东/华南", "华东 South China", "上海", "Overseas", ""):
            self.assertEqual(preset_region(value), "", value)

    def test_plan_settles_overrides_and_presets_before_the_common_custom_spelling(self):
        plans, options = plan_values(
            Counter({"华东": 3, "East": 1, "Over seas": 1, "Overseas": 2, "上海": 1, "东北": 1, "": 4}),
            "\nEast China\nSouth China\nWest China\nNorth China\nCentral China\nKorea\n成都",
            {"上海": "华东"},
        )

        self.assertEqual({value: (plan.target, plan.rule) for value, plan in plans.items()}, {
            "华东": ("East China", "preset"),
            "East": ("East China", "preset"),
            "Overseas": ("Overseas", "custom"),
            "Over seas": ("Overseas", "existing_option"),
            "上海": ("East China", "override"),
            # A Chinese city is not guessed and never becomes an option.
            "东北": ("东北", "unmapped"),
            "": ("", "empty"),
        })
        self.assertEqual(plans["东北"].warnings, ["not_english"])
        # Existing custom options nobody uses (Korea, 成都) are dropped.
        self.assertEqual(options, [*REGION_PRESETS, "Overseas"])


class TestRegionOptions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        # Registered regions live in the Customer meta cache; clear it after the class rollback.
        cls.addClassCleanup(frappe.clear_cache, doctype="Customer")
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-region-sales@example.invalid", "CRM Sales")
        self.addCleanup(frappe.clear_cache, doctype="Customer")

    def tearDown(self):
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

    def _account_input(self, name: str, region: str) -> dict:
        return {
            "name": name, "shortName": name[:8], "segment": "Frontend", "tier": "A",
            "city": "上海", "region": region, "owner": self.sales,
        }

    def _site(self, account: dict) -> dict:
        return create_site(account["id"], {
            "name": f"{account['name']} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })

    def _opportunity_input(self, account: dict, site: dict, title: str, sub_region: str) -> dict:
        return {
            "probabilityLevel": "pipeline", "accountId": account["id"], "siteId": site["id"], "title": title,
            "owner": self.sales, "amount": "100000.00", "intentScore": 30, "poDate": "2026-12-31",
            "toolType": "Inspection", "saleType": "New Equipment", "subRegion": sub_region, "currency": "CNY",
            "originalAmount": "100000.00", "amountCny": "100000.00", "qualificationConfirmed": True,
        }

    def _report_names(self, path: str) -> set[str]:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            return {row["name"] for row in csv.DictReader(handle)}

    def test_accounts_store_presets_in_english_and_filter_by_any_spelling(self):
        frappe.set_user(self.sales)
        east = create_account(self._account_input("RegionFilter East", "华东区"))
        south = create_account(self._account_input("RegionFilter South", "south"))

        self.assertEqual((east["region"], south["region"]), ("East China", "South China"))
        self.assertEqual(list_account_regions()[: len(REGION_PRESETS)], list(REGION_PRESETS))
        updated = update_account(east["id"], self._account_input("RegionFilter East", "华中"), east["modified"])
        self.assertEqual(updated["region"], "Central China")
        items = list_accounts({"search": "RegionFilter", "region": "华南"})[0]
        self.assertEqual([item["id"] for item in items], [south["id"]])

    def test_custom_regions_are_english_registered_once_and_reused(self):
        frappe.set_user(self.sales)
        first = create_account(self._account_input("Region Custom One", "  Southeast   Asia "))
        second = create_account(self._account_input("Region Custom Two", "south-east asia"))

        self.assertEqual((first["region"], second["region"]), ("Southeast Asia", "Southeast Asia"))
        self.assertEqual(list_account_regions().count("Southeast Asia"), 1)
        # A blank first option keeps a new Customer from defaulting to East China.
        self.assertTrue(frappe.db.get_value("Custom Field", REGION_FIELD, "options").startswith("\n"))
        with self.assertRaises(CrmApiException) as chinese:
            create_account(self._account_input("Region Custom Chinese", "东北"))
        self.assertEqual(chinese.exception.code, "VALIDATION_ERROR")
        self.assertEqual(chinese.exception.field_errors, {"region": "Use an English region name"})
        self.assertNotIn("东北", list_account_regions())

    def test_existing_account_can_register_new_region_and_segment_while_saving(self):
        frappe.set_user(self.sales)
        payload = self._account_input("RegionEdit Custom", "East")
        account = create_account(payload)
        region = "Custom Region " + frappe.generate_hash(length=8)
        segment = "Custom Segment " + frappe.generate_hash(length=8)
        self.assertNotIn(region, list_account_regions())
        changed = update_account(account["id"], {**payload, "region": region}, account["modified"])
        self.assertEqual(changed["region"], region)
        self.assertIn(region, list_account_regions())
        changed = update_account(account["id"], {**payload, "region": region, "segment": segment}, changed["modified"])
        self.assertEqual(changed["segment"], segment)
        stored = frappe.get_doc("Customer", account["id"])
        self.assertEqual((stored.custom_crm_region, stored.custom_crm_segment), (region, segment))

    def test_failed_account_save_rolls_back_new_region_and_segment_registration(self):
        frappe.set_user(self.sales)
        payload = self._account_input("RegionEdit Rollback", "East")
        account = create_account(payload)
        region = "Rollback Region " + frappe.generate_hash(length=8)
        segment = "Rollback Segment " + frappe.generate_hash(length=8)
        def fail(_):
            raise RuntimeError("simulated business save failure")
        with self.assertRaises(RuntimeError):
            update_account(account["id"], {**payload, "region": region, "segment": segment}, account["modified"], failure_injector=fail)
        self.assertNotIn(region, list_account_regions())
        stored = frappe.get_doc("Customer", account["id"])
        self.assertEqual((stored.custom_crm_region, stored.custom_crm_segment), ("East China", "Frontend"))
        self.assertNotIn(segment, stored.meta.get_field("custom_crm_segment").options.split("\n"))

    def test_opportunity_region_must_be_a_shared_option(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Region Opportunity", "华北"))
        site = self._site(account)

        opportunity = create_strategy_opportunity(self._opportunity_input(account, site, "Region north", "华北区"))
        self.assertEqual(opportunity["subRegion"], "North China")
        with self.assertRaises(CrmApiException) as unknown:
            create_strategy_opportunity(self._opportunity_input(account, site, "Region unknown", "Mars"))
        self.assertEqual(unknown.exception.field_errors, {"subRegion": "Unknown region"})

    def test_patch_normalizes_stored_regions_once_and_verify_passes(self):
        frappe.set_user(self.sales)
        preset = create_account(self._account_input("Region Legacy Preset", "East China"))
        corrected = create_account(self._account_input("Region Legacy Corrected", "East China"))
        chinese = create_account(self._account_input("Region Legacy Chinese", "East China"))
        opportunity = create_strategy_opportunity(
            self._opportunity_input(preset, self._site(preset), "Region legacy", "East China"),
        )
        frappe.set_user("Administrator")
        # Recreate the free text stored before the upgrade.
        frappe.db.set_value("Customer", preset["id"], "custom_crm_region", "华东", update_modified=False)
        frappe.db.set_value("Customer", corrected["id"], "custom_crm_region", "Korea ", update_modified=False)
        frappe.db.set_value("Customer", chinese["id"], "custom_crm_region", "东北", update_modified=False)
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "sub_region", "east", update_modified=False)
        modified_before = frappe.db.get_value("Customer", preset["id"], "modified")
        frappe.conf[migration.OVERRIDES_KEY] = {"Korea": "South Korea", "Nowhere": "East China"}

        preview = migration.dry_run()
        self.assertEqual(frappe.db.get_value("Customer", preset["id"], "custom_crm_region"), "华东")
        mapping = {(value["from"], value["to"], value["rule"]) for value in preview["values"]}
        self.assertLessEqual(
            {("华东", "East China", "preset"), ("Korea ", "South Korea", "override"), ("east", "East China", "preset")},
            mapping,
        )
        self.assertIn("Nowhere", preview["unusedOverrides"])
        self.assertIn("东北", preview["unmapped"])
        self.assertLessEqual({preset["id"], corrected["id"], chinese["id"], opportunity["id"]}, self._report_names(preview["report"]))

        # A value nobody mapped stops the migration before anything is written.
        with self.assertRaises(RuntimeError) as blocked:
            normalize_crm_regions.execute()
        self.assertIn("东北 (1)", str(blocked.exception))
        self.assertEqual(frappe.db.get_value("Customer", preset["id"], "custom_crm_region"), "华东")

        frappe.conf[migration.OVERRIDES_KEY] = {**frappe.conf[migration.OVERRIDES_KEY], "东北": "North China"}
        normalize_crm_regions.execute()
        self.assertEqual(migration.apply_migration()["changes"], 0)
        self.assertEqual(
            frappe.db.get_value("Customer", preset["id"], ["custom_crm_region", "modified"]), ("East China", modified_before),
        )
        self.assertEqual(frappe.db.get_value("Customer", corrected["id"], "custom_crm_region"), "South Korea")
        self.assertEqual(frappe.db.get_value("Customer", chinese["id"], "custom_crm_region"), "North China")
        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity["id"], "sub_region"), "East China")
        self.assertEqual(frappe.db.get_value("Custom Field", REGION_FIELD, "fieldtype"), "Select")
        self.assertIn("South Korea", list_account_regions())
        self.assertNotIn("东北", list_account_regions())

        result = migration.verify()
        self.assertTrue(result["ok"], result["findings"])
        self.assertNotIn("custom_region_not_english", {finding["check"] for finding in result["findings"]})

    def test_a_chinese_option_fails_verify(self):
        field = frappe.get_doc("Custom Field", REGION_FIELD)
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", f"{field.options}\n上海", update_modified=False)
        self.addCleanup(frappe.db.set_value, "Custom Field", REGION_FIELD, "options", field.options, update_modified=False)

        result = migration.verify()

        self.assertFalse(result["ok"])
        self.assertIn(("error", "custom_region_not_english", "上海"), {
            (finding["severity"], finding["check"], finding["detail"]) for finding in result["findings"]
        })

    def test_migrate_drops_custom_regions_nobody_uses(self):
        frappe.set_user(self.sales)
        moved = create_account(self._account_input("Region Unused Custom", "Pacific Rim"))
        create_account(self._account_input("Region Kept Custom", "Nordic"))
        update_account(moved["id"], self._account_input("Region Unused Custom", "East China"), moved["modified"])
        self.assertIn("Pacific Rim", list_account_regions())

        frappe.set_user("Administrator")
        options = next(
            field["options"] for field in custom_fields._custom_fields_for_install()["Customer"]
            if field["fieldname"] == "custom_crm_region"
        )

        values = [line for line in options.splitlines() if line]
        self.assertEqual(values[: len(REGION_PRESETS)], list(REGION_PRESETS))
        self.assertIn("Nordic", values)
        self.assertNotIn("Pacific Rim", values)
        self.assertTrue(options.startswith("\n"))
