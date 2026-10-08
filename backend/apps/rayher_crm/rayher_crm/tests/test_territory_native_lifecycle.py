"""Native Frappe lifecycle and legacy query semantics, using the real database."""
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services import territory_admin as service
from rayher_crm.tests import test_opportunity_relations as fixtures


class TestTerritoryNativeLifecycle(FrappeTestCase):
    _user = fixtures.TestOpportunityRelations._user
    _records = fixtures.TestOpportunityRelations._records

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.suffix = frappe.generate_hash(length=10)
        self.sales = self._user(f"territory-native-{self.suffix}@example.invalid", "CRM Sales")
        self.addCleanup(frappe.clear_cache, doctype="Customer")

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_native_assignment_links_are_canonical_on_insert_and_save(self):
        region = service.save_territory({"name": f"Native Region {self.suffix}", "parent": "China", "isGroup": False, "enabled": True})
        doc = frappe.get_doc({"doctype": service.ASSIGNMENT, "territory": region["name"].lower(),
                              "sales_owner": self.sales.upper(), "valid_from": "2030-09-02", "valid_until": "2030-09-30"})
        doc.insert(ignore_permissions=True)
        self.assertEqual((doc.territory, doc.sales_owner), (region["name"], self.sales))
        doc.territory = region["name"].lower()
        doc.sales_owner = self.sales.upper()
        doc.note = "Native revision"
        doc.save(ignore_permissions=True)
        stored = frappe.db.get_value(service.ASSIGNMENT, doc.name, ["territory", "sales_owner", "note"])
        self.assertEqual(stored, (region["name"], self.sales, "Native revision"))
        joined = [row for row in service.catalogue()["assignments"] if row["territory"] == region["name"]]
        self.assertEqual([row["id"] for row in joined], [doc.name])

    def test_native_group_cannot_reserve_an_unmapped_customer_region(self):
        from rayher_crm.services.regions import register_region
        canonical = register_region(f"Native Unmapped {self.suffix}")
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": service.TERRITORY, "territory_name": canonical.lower(),
                            "parent_territory": "Asia", "is_group": 1, "enabled": 1}).insert(ignore_permissions=True)
        self.assertFalse(frappe.db.exists(service.TERRITORY, canonical))
        region = service.save_territory({"name": canonical, "parent": "China", "isGroup": False, "enabled": True})
        self.assertEqual(region["name"], canonical)

    def test_native_new_leaf_registers_a_customer_region(self):
        from rayher_crm.services.regions import list_regions
        from rayher_crm.services.territories import region_tree
        title = f"Native Registered {self.suffix}"
        doc = frappe.get_doc({"doctype": service.TERRITORY, "territory_name": title,
                              "parent_territory": "China", "is_group": 0, "enabled": 1}).insert(ignore_permissions=True)
        self.assertIn(doc.name, list_regions())
        self.assertEqual(region_tree(list_regions())[1][doc.name], "China")
        self.assertNotIn(doc.name, service.catalogue()["unmappedRegions"])

    def assert_group_does_not_claim_registered_database_identity(self, *, native):
        from rayher_crm.api.v1.errors import CrmApiException
        from rayher_crm.services.regions import REGION_FIELD, list_regions, options_text

        original = list_regions()
        pairs = [(f"Café {self.suffix}", f"Cafe {self.suffix}"),
                 (f"Straße {self.suffix}", f"Strasse {self.suffix}")]
        # Legacy registered values need not satisfy today's English-only rule.
        registered = [*original, *(name for name, _ in pairs)]
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text(registered), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        for registered_name, title in pairs:
            with self.subTest(registered=registered_name, title=title):
                exception = frappe.ValidationError if native else CrmApiException
                try:
                    if native:
                        frappe.get_doc({"doctype": service.TERRITORY, "territory_name": title,
                                        "parent_territory": "Asia", "is_group": 1, "enabled": 1}).insert(ignore_permissions=True)
                    else:
                        service.save_territory({"name": title, "parent": "Asia", "isGroup": True, "enabled": True})
                except exception as error:
                    self.assertIn("belongs to a customer region", str(error))
                else:
                    # The old code accepts a group that the actual name column
                    # also resolves using the registered non-ASCII spelling.
                    self.assertEqual(frappe.db.get_value(service.TERRITORY, registered_name, "name"), title)
                    self.fail("A new group claimed a registered customer's database identity")
                self.assertFalse(frappe.db.exists(service.TERRITORY, title))
        self.assertEqual(list_regions(), registered)
        unrelated = service.save_territory({"name": f"Independent Group {self.suffix}", "parent": "Asia",
                                            "isGroup": True, "enabled": True})
        self.assertTrue(unrelated["isGroup"])
        self.assertEqual(list_regions(), registered)

    def test_native_group_cannot_reserve_registered_collation_identity(self):
        self.assert_group_does_not_claim_registered_database_identity(native=True)

    def test_api_group_cannot_reserve_registered_collation_identity(self):
        self.assert_group_does_not_claim_registered_database_identity(native=False)

    def test_existing_collation_conflict_group_remains_maintainable(self):
        from rayher_crm.services.regions import REGION_FIELD, list_regions, options_text

        title = f"Cafe History {self.suffix}"
        group = service.save_territory({"name": title, "parent": "Asia", "isGroup": True, "enabled": True})
        # Model a group predating the newly enforced reservation check.
        options = [*list_regions(), f"Café History {self.suffix}"]
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text(options), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        doc = frappe.get_doc(service.TERRITORY, group["name"])
        doc.enabled = 0
        doc.save(ignore_permissions=True)
        saved = service.save_territory({"name": title, "parent": "Asia", "isGroup": True, "enabled": True},
                                       doc.name, service.to_iso_timestamp(doc.modified))
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["name"], title)
        self.assertEqual(list_regions(), options)

    def test_native_new_group_rejects_an_existing_group_alias(self):
        from rayher_crm.api.v1.errors import CrmApiException
        title = f"North America {self.suffix}"
        alias = f"North-America {self.suffix}"
        group = service.save_territory({"name": title, "parent": "Asia", "isGroup": True, "enabled": True})
        with self.assertRaises(CrmApiException):
            service.save_territory({"name": alias, "parent": "Asia", "isGroup": True, "enabled": True})
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({"doctype": service.TERRITORY, "territory_name": alias,
                            "parent_territory": "Asia", "is_group": 1, "enabled": 1}).insert(ignore_permissions=True)
        self.assertFalse(frappe.db.exists(service.TERRITORY, alias))
        # The existing contract intentionally permits a differently spelled leaf
        # below a group; new-group duplicate checks must not prohibit it.
        leaf = service.save_territory({"name": alias, "parent": group["name"], "isGroup": False, "enabled": True})
        self.assertEqual((leaf["name"], leaf["parent"]), (alias, title))

    def test_existing_group_aliases_remain_independently_maintainable(self):
        title = f"Legacy America {self.suffix}"
        alias = f"Legacy-America {self.suffix}"
        first = service.save_territory({"name": title, "parent": "Asia", "isGroup": True, "enabled": True})
        # Historical data is not merged or blocked by a rule for new groups.
        second = frappe.get_doc({"doctype": service.TERRITORY, "name": alias, "territory_name": alias,
                                 "parent_territory": "Asia", "is_group": 1, "enabled": 1})
        second.db_insert()
        second.enabled = 0
        second.save(ignore_permissions=True)
        for name in (first["name"], second.name):
            doc = frappe.get_doc(service.TERRITORY, name)
            saved = service.save_territory({"name": name, "parent": "China", "isGroup": True, "enabled": True},
                                           name, service.to_iso_timestamp(doc.modified))
            self.assertEqual((saved["name"], saved["parent"], saved["enabled"]), (name, "China", True))

    def test_migration_reserves_earlier_options_under_database_collation(self):
        self.assert_migration_candidate_is_free(reserved_first=True)

    def test_migration_reserves_later_options_under_database_collation(self):
        self.assert_migration_candidate_is_free(reserved_first=False)

    def assert_migration_candidate_is_free(self, *, reserved_first):
        from rayher_crm.patches.v1_0.reconcile_territory_region_identity import execute
        from rayher_crm.services import opportunity_board
        from rayher_crm.services.regions import REGION_FIELD, list_regions, options_text
        for long_name in (False, True):
            with self.subTest(long_name=long_name):
                tag = f"{self.suffix}{'Long' if long_name else 'Short'}"
                old = f"Café {tag}"
                if long_name:
                    old = old.ljust(100, "x")
                canonical = old.replace("é", "e")
                def candidate(name, number):
                    suffix = " (Territory Group)" if number == 1 else f" (Territory Group {number})"
                    return name[:100 - len(suffix)] + suffix
                legacy = frappe.get_doc({"doctype": service.TERRITORY, "name": old, "territory_name": old,
                                         "parent_territory": "Asia", "is_group": 1, "enabled": 1})
                legacy.db_insert()
                child = service.save_territory({"name": f"Migration Child {tag}", "parent": old, "isGroup": False, "enabled": True})
                occupied = service.save_territory({"name": candidate(canonical, 2), "parent": "Asia", "isGroup": True, "enabled": False})
                reserved = [candidate(canonical, 1), candidate(canonical, 3)]
                options = [*list_regions(), *(reserved + [canonical] if reserved_first else [canonical] + reserved)]
                frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text(options), update_modified=False)
                frappe.clear_cache(doctype="Customer")
                account, opportunity, _ = self._records(self.sales, f"MigrationChild{tag}")
                outside, other_opportunity, _ = self._records(self.sales, f"MigrationOutside{tag}")
                frappe.set_user("Administrator")
                frappe.db.set_value("Customer", account["id"], "custom_crm_region", child["name"])
                frappe.db.set_value("Customer", outside["id"], "custom_crm_region", canonical)
                queries = []
                with patch.dict(frappe.conf, {"crm_cockpit_region_migration_verified": True}):
                    for mode in ("scope", "in", "not_in"):
                        definition = {"scope": {"sales": [self.sales]}, "conditions": [], "columns": ["title"]}
                        if mode == "scope":
                            definition["scope"]["regions"] = [old]
                        else:
                            definition["conditions"] = [{"field": "region", "operator": mode, "value": [old]}]
                        saved = opportunity_board.save_opportunity_query(None, {"name": f"Migration {mode} {tag}", "definition": definition})
                        # Other subcases may share this Sales identity, so preserve
                        # the actual complete set, rather than assume only two rows.
                        before = opportunity_board.query_opportunities({k: v for k, v in definition.items() if k != "columns"})[0]["items"]
                        expected = {row["id"] for row in before}
                        self.assertEqual(opportunity["id"] in expected, mode != "not_in")
                        self.assertEqual(other_opportunity["id"] in expected, mode == "not_in")
                        queries.append((saved["id"], expected))
                    execute()
                    renamed = frappe.db.get_value(service.TERRITORY, child["name"], "parent_territory")
                    self.assertNotEqual(renamed, old)
                    self.assertLessEqual(len(renamed), 100)
                    for region in (canonical, *reserved):
                        self.assertFalse(frappe.db.get_value(service.TERRITORY, region, "name"), region)
                    self.assertEqual(frappe.db.get_value(service.TERRITORY, occupied["name"], "enabled"), 0)
                    execute()
                    self.assertEqual(frappe.db.get_value(service.TERRITORY, child["name"], "parent_territory"), renamed)
                    self.assertEqual(list_regions(), options)
                    self.assertEqual(frappe.db.get_value("Customer", outside["id"], "custom_crm_region"), canonical)
                    for query_id, expected in queries:
                        definition = frappe.parse_json(frappe.db.get_value(opportunity_board.SAVED_QUERY, query_id, "definition"))
                        actual = opportunity_board.query_opportunities({k: v for k, v in definition.items() if k != "columns"})[0]["items"]
                        self.assertEqual({row["id"] for row in actual}, expected)
                    # The reported reverse-accent case has placeable English
                    # regions: one normal migration must free them for the API.
                    for region in (canonical, *reserved):
                        placed = service.save_territory({"name": region, "parent": "China", "isGroup": False, "enabled": True})
                        self.assertEqual(placed["name"], region)

    def test_native_set_name_cannot_claim_a_registered_region_with_a_group_title(self):
        from rayher_crm.services.regions import register_region
        canonical = register_region(f"Native Reserved ID {self.suffix}")
        for group in (0, 1):
            with self.subTest(group=group), self.assertRaises(frappe.ValidationError):
                frappe.get_doc({"doctype": service.TERRITORY, "territory_name": f"Independent Node {self.suffix}",
                                "parent_territory": "China", "is_group": group, "enabled": 1}).insert(
                                    ignore_permissions=True, set_name=canonical)
            self.assertFalse(frappe.db.exists(service.TERRITORY, canonical))

    def test_native_new_nodes_reject_invalid_and_noncanonical_names(self):
        from rayher_crm.services.regions import list_regions, register_region
        canonical = register_region(f"Native Canonical {self.suffix}")
        original_options = list_regions()
        for title, group in [(f"未知地区{self.suffix}", 0), ("A" * 101, 0),
                             (canonical.lower(), 0), (f"未知分组{self.suffix}", 1)]:
            with self.subTest(title=title), self.assertRaises(frappe.ValidationError):
                frappe.get_doc({"doctype": service.TERRITORY, "territory_name": title,
                                "parent_territory": "China", "is_group": group, "enabled": 1}).insert(ignore_permissions=True)
            self.assertFalse(frappe.db.exists(service.TERRITORY, title))
            self.assertEqual(list_regions(), original_options)

    def test_leaf_migration_preserves_exact_registered_custom_alias(self):
        self.assert_leaf_query_results_survive_migration(preset=False)

    def test_leaf_migration_preserves_exact_registered_preset_alias(self):
        self.assert_leaf_query_results_survive_migration(preset=True)

    def assert_leaf_query_results_survive_migration(self, *, preset):
        from frappe.model.rename_doc import rename_doc
        from rayher_crm.patches.v1_0.reconcile_territory_region_identity import execute
        from rayher_crm.services import opportunity_board
        from rayher_crm.services.regions import REGION_FIELD, list_regions, options_text
        from rayher_crm.services.territories import region_tree
        canonical = "East China" if preset else f"Legacy Leaf {self.suffix}"
        if not preset:
            service.save_territory({"name": canonical, "parent": "China", "isGroup": False, "enabled": True})
        old = canonical.lower()
        rename_doc(service.TERRITORY, canonical, old, force=True, ignore_permissions=True, show_alert=False, rebuild_search=False)
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text([*list_regions(), old]), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        assignment = service.save_assignment({"territory": old, "salesOwner": self.sales, "validFrom": "2030-01-01", "cancelled": False})
        account, opportunity, _ = self._records(self.sales, f"LeafAlias{self.suffix}")
        frappe.set_user("Administrator")
        frappe.db.set_value("Customer", account["id"], "custom_crm_region", old)
        saved_queries = []
        with patch.dict(frappe.conf, {"crm_cockpit_region_migration_verified": True}):
            for mode in ("scope", "in", "not_in", "parent"):
                definition = {"scope": {"sales": [self.sales]}, "conditions": [], "columns": ["title"]}
                if mode in ("scope", "parent"):
                    definition["scope"]["regions"] = ["China" if mode == "parent" else old]
                else:
                    definition["conditions"] = [{"field": "region", "operator": mode, "value": [old]}]
                saved = opportunity_board.save_opportunity_query(None, {"name": f"Leaf {mode} {self.suffix}", "definition": definition})
                before = opportunity_board.query_opportunities({key: value for key, value in definition.items() if key != "columns"})[0]["items"]
                expected = set() if mode == "not_in" else {opportunity["id"]}
                self.assertEqual({row["id"] for row in before}, expected)
                saved_queries.append((saved, expected))
            execute()
            execute()
            self.assertEqual(frappe.db.get_value(service.TERRITORY, old, "name"), old)
            self.assertEqual(region_tree(list_regions())[1][old], "China")
            self.assertEqual(frappe.db.get_value(service.ASSIGNMENT, assignment["id"], "territory"), old)
            self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_region"), old)
            for saved, expected in saved_queries:
                stored = frappe.get_doc(opportunity_board.SAVED_QUERY, saved["id"])
                definition = frappe.parse_json(stored.definition)
                self.assertEqual(definition, saved["definition"])
                actual = opportunity_board.query_opportunities({key: value for key, value in definition.items() if key != "columns"})[0]["items"]
                self.assertEqual({row["id"] for row in actual}, expected)

    def test_case_variant_group_migration_preserves_actual_saved_query_results(self):
        self.assert_saved_query_results_survive_migration(retain_old=False)

    def test_case_variant_group_migration_retains_an_exact_old_region_option(self):
        self.assert_saved_query_results_survive_migration(retain_old=True)

    def assert_saved_query_results_survive_migration(self, *, retain_old):
        from rayher_crm.patches.v1_0.reconcile_territory_region_identity import execute
        from rayher_crm.services import opportunity_board
        from rayher_crm.services.regions import REGION_FIELD, list_regions, options_text
        canonical = f"Legacy Mixed {self.suffix}"
        group = service.save_territory({"name": canonical.lower(), "parent": "Asia", "isGroup": True, "enabled": True})
        child = service.save_territory({"name": f"Native Child {self.suffix}", "parent": group["name"], "isGroup": False, "enabled": True})
        # Model a pre-guard group/region collision without bypassing query evaluation.
        retained = [group["name"]] if retain_old else []
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text([*list_regions(), canonical, *retained]), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        canonical_account, canonical_opp, _ = self._records(self.sales, f"NativeCanonical{self.suffix}")
        child_account, child_opp, _ = self._records(self.sales, f"NativeChild{self.suffix}")
        frappe.set_user("Administrator")
        frappe.db.set_value("Customer", canonical_account["id"], "custom_crm_region", group["name"] if retain_old else canonical)
        frappe.db.set_value("Customer", child_account["id"], "custom_crm_region", child["name"])
        saved_queries = []
        with patch.dict(frappe.conf, {"crm_cockpit_region_migration_verified": True}):
            for mode in ("scope", "in", "not_in"):
                definition = {"scope": {"sales": [self.sales]}, "conditions": [], "columns": ["title"]}
                if mode == "scope":
                    definition["scope"]["regions"] = [group["name"]]
                else:
                    definition["conditions"] = [{"field": "region", "operator": mode, "value": [group["name"]]}]
                saved = opportunity_board.save_opportunity_query(None, {"name": f"Native {mode} {self.suffix}", "definition": definition})
                before = opportunity_board.query_opportunities({key: value for key, value in saved["definition"].items() if key != "columns"})[0]["items"]
                inside = {child_opp["id"], *([canonical_opp["id"]] if retain_old else [])}
                expected = {canonical_opp["id"], child_opp["id"]} - inside if mode == "not_in" else inside
                self.assertEqual({row["id"] for row in before}, expected)
                saved_queries.append((saved, expected))
            execute()
            execute()
            renamed = frappe.db.get_value(service.TERRITORY, child["name"], "parent_territory")
            self.assertNotEqual(renamed, group["name"])
            for saved, expected in saved_queries:
                definition = frappe.parse_json(frappe.db.get_value(opportunity_board.SAVED_QUERY, saved["id"], "definition"))
                actual = opportunity_board.query_opportunities({key: value for key, value in definition.items() if key != "columns"})[0]["items"]
                self.assertEqual({row["id"] for row in actual}, expected)
                values = definition["scope"].get("regions") or definition["conditions"][0]["value"]
                self.assertEqual(values, [renamed, *retained])
