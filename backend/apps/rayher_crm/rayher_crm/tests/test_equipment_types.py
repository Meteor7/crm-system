"""Site integration checks for the Opportunity equipment catalog. Run on the dedicated test site."""
from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1 import opportunities as opportunities_api
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import opportunities
from rayher_crm.services.accounts import create_account
from rayher_crm.services.equipment import (
    EQUIPMENT_PRESETS, EQUIPMENT_TYPE, custom_equipment_types, list_equipment_types, normalize_equipment,
)
from rayher_crm.services.opportunities import create_strategy_opportunity, get_strategy_opportunity, update_strategy_opportunity
from rayher_crm.services.sites import create_site
from rayher_crm.setup import equipment_types


class TestEquipmentTypes(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = "crm-equipment-sales@example.invalid"
        if not frappe.db.exists("User", self.sales):
            frappe.get_doc({"doctype": "User", "email": self.sales, "first_name": "Equipment Sales", "enabled": 1,
                            "send_welcome_email": 0, "roles": [{"role": "CRM Sales"}]}).insert(ignore_permissions=True)
        self.token = frappe.generate_hash(length=8)
        frappe.set_user(self.sales)
        self.account = create_account({"name": f"Equipment {self.token}", "shortName": f"Eq{self.token}", "segment": "Frontend",
                                       "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        self.site = create_site(self.account["id"], {"name": f"Equipment {self.token} Site", "city": "上海", "type": "Fab",
                                                     "process": "Frontend", "status": "量产"})

    def tearDown(self):
        frappe.set_user(self.original_user)
        frappe.db.rollback()
        super().tearDown()

    def _create(self, tool_type, title="Equipment Project"):
        return create_strategy_opportunity({
            "accountId": self.account["id"], "siteId": self.site["id"], "title": title, "owner": self.sales,
            "amount": "100.00", "intentScore": 35, "poDate": "2031-12-31", "toolType": tool_type,
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY", "originalAmount": "100.00",
            "amountCny": "100.00", "qualificationConfirmed": True, "probabilityLevel": "pipeline",
        })

    def _error(self, action):
        with self.assertRaises(CrmApiException) as caught:
            action()
        return caught.exception

    def test_presets_come_first_and_other_spellings_of_them_are_stored_as_the_preset(self):
        self.assertEqual(list_equipment_types()[:5], list(EQUIPMENT_PRESETS))
        for typed, stored in (("NANSI", "Nansi"), ("nan-si", "Nansi"), ("  Kibo ", "Kibo"), ("veymont", "Veymont"),
                              ("Kibo 4895C", "Kibo 4895C"), ("Probe  9", "Probe 9"),
                              # Full-width letters, zero-width spaces and a BOM do not make a new type.
                              ("ＮＡＮＳＩ", "Nansi"), ("Nan\u200bsi", "Nansi"), ("\ufeffKibo", "Kibo"), ("Ｐｒｏｂｅ ９", "Probe 9"),
                              # The unique index ignores accents, so they do not make a new type either.
                              ("Drakéns", "Drakens"), ("NÁNSI", "Nansi"), ("Na—nsi", "Nansi")):
            with self.subTest(typed=typed):
                self.assertEqual(normalize_equipment(typed, "toolType"), stored)
        for bad in ("", "   ", None, 12, "A<B>", "x" * 141, "a\x00b", "...", "/", "-", "\u200b", "!!!", "？？？", "【】"):
            with self.subTest(bad=bad):
                error = self._error(lambda: normalize_equipment(bad, "toolType"))
                self.assertEqual((error.code, list(error.field_errors)), ("VALIDATION_ERROR", ["toolType"]))

    def test_saving_an_opportunity_adds_a_custom_type_once(self):
        custom = f"Probe {self.token}"
        first = self._create(custom)
        second = self._create(custom.upper())
        self.assertEqual((first["toolType"], second["toolType"]), (custom, custom))
        self.assertEqual(list_equipment_types().count(custom), 1)
        # An accented spelling used to fail the unique index with a 500.
        self.assertEqual(self._create(f"Pröbe {self.token}")["toolType"], custom)
        # The collation also treats "〇" as "0", which the key keeps apart: the row is reused.
        zero = f"Probe0 {self.token}"
        self.assertEqual(self._create(zero)["toolType"], zero)
        self.assertEqual(self._create(f"Probe〇 {self.token}")["toolType"], zero)
        self.assertEqual(self._create("nansi")["toolType"], "Nansi")
        self.assertEqual(frappe.db.count(EQUIPMENT_TYPE, {"equipment_name": "Nansi"}), 0)

    def test_a_failed_save_leaves_no_new_custom_type(self):
        custom = f"Rolled Back {self.token}"
        with patch.object(opportunities, "append_stage_history", side_effect=RuntimeError("boom")), self.assertRaises(RuntimeError):
            self._create(custom)
        self.assertNotIn(custom, list_equipment_types())

    def test_an_unchanged_legacy_value_keeps_its_spelling_and_a_changed_one_uses_the_catalog(self):
        created = self._create("Kibo")
        # A value from before the catalog, written the old way.
        frappe.db.set_value("CRM Opportunity", created["id"], "tool_type", "kibo  4895c", update_modified=False)
        current = get_strategy_opportunity(created["id"])
        renamed = update_strategy_opportunity(created["id"], {**self._editable(current), "title": "Renamed"}, current["modified"])
        self.assertEqual((renamed["title"], renamed["toolType"]), ("Renamed", "kibo  4895c"))
        self.assertNotIn("kibo  4895c", custom_equipment_types())
        moved = update_strategy_opportunity(created["id"], {**self._editable(renamed), "toolType": "KIBO"}, renamed["modified"])
        self.assertEqual(moved["toolType"], "Kibo")
        self.assertEqual([(row["field"], row["from"], row["to"]) for row in moved["history"] if row["field"] == "tool_type"],
                         [("tool_type", "kibo  4895c", "Kibo")])

    def _editable(self, opportunity):
        keys = ("accountId", "siteId", "title", "owner", "amount", "poDate", "toolType", "saleType", "subRegion",
                "currency", "originalAmount", "amountCny", "probabilityLevel")
        return {key: opportunity[key] for key in keys}

    def test_sync_registers_each_type_once_and_keeps_stored_spellings(self):
        created = self._create("Kibo", title="Legacy A")
        other = self._create("Veymont", title="Legacy B")
        third = self._create("Aconca", title="Legacy C")
        frappe.db.set_value("CRM Opportunity", created["id"], "tool_type", " nansi", update_modified=False)
        frappe.db.set_value("CRM Opportunity", other["id"], "tool_type", f"Kibo {self.token}", update_modified=False)
        frappe.db.set_value("CRM Opportunity", third["id"], "tool_type", f"kibo-{self.token}", update_modified=False)
        for name in (f"Orphan {self.token}", "nansi"):
            frappe.get_doc({"doctype": EQUIPMENT_TYPE, "equipment_name": name}).insert(ignore_permissions=True)
        result = equipment_types.sync()
        # "nansi" is the preset Nansi, and the two Kibo spellings are one new type registered once.
        self.assertEqual([value for value in result["added"] if self.token in value], [f"Kibo {self.token}"])
        self.assertNotIn("nansi", result["added"])
        self.assertLessEqual({f"Orphan {self.token}", "nansi"}, set(result["removed"]))
        options = list_equipment_types()
        self.assertIn(f"Kibo {self.token}", options)
        for absent in ("nansi", f"kibo-{self.token}", f"Orphan {self.token}"):
            self.assertNotIn(absent, options)
        # Stored values are untouched; the board shows them under the catalog spelling.
        self.assertEqual(frappe.db.get_value("CRM Opportunity", created["id"], "tool_type"), " nansi")
        self.assertEqual(frappe.db.get_value("CRM Opportunity", third["id"], "tool_type"), f"kibo-{self.token}")
        self.assertEqual(equipment_types.sync(), {"added": [], "removed": []})
        hints = {item["value"]: item["hints"] for item in equipment_types.report()["values"]}
        self.assertIn("spelling_of_preset:Nansi", hints["nansi"])
        self.assertIn("contains_preset:Kibo", hints[f"Kibo {self.token}"])
        self.assertIn(f"same_as:kibo-{self.token}", hints[f"Kibo {self.token}"])

    def test_sync_registers_spellings_the_unique_index_treats_as_equal_once(self):
        # "〇" and "0" are two keys but one value to the collation; the more common spelling is kept.
        zero, circle = f"Probe0 {self.token}", f"Probe〇 {self.token}"
        for title, value in (("Zero A", zero), ("Zero B", zero), ("Circle", circle)):
            created = self._create("Kibo", title=title)
            frappe.db.set_value("CRM Opportunity", created["id"], "tool_type", value, update_modified=False)
        self.assertEqual([value for value in equipment_types.sync()["added"] if self.token in value], [zero])
        options = list_equipment_types()
        self.assertIn(zero, options)
        self.assertNotIn(circle, options)
        self.assertEqual([value for value in equipment_types.sync()["added"] if self.token in value], [])

    def test_only_the_service_reaches_the_catalog(self):
        self.assertFalse(frappe.has_permission(EQUIPMENT_TYPE, "read", user=self.sales))
        with self.assertRaises(frappe.PermissionError):
            frappe.get_list(EQUIPMENT_TYPE, fields=["equipment_name"])
        response = opportunities_api.list_equipment_types()
        self.assertEqual(response["data"][:5], list(EQUIPMENT_PRESETS))
