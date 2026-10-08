import frappe
from unittest.mock import patch
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import territory_admin as service
from rayher_crm.services.regions import list_regions


class TestTerritoryAdministration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self.user("manager", "CRM Manager")
        self.sales = self.user("sales", "CRM Sales")
        self.suffix = frappe.generate_hash(length=8)
        self.addCleanup(frappe.clear_cache, doctype="Customer")
        frappe.set_user(self.manager)

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def user(self, suffix, role):
        email = f"territory-admin-{suffix}@example.invalid"
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": suffix,
                            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
        return email

    def region(self):
        return service.save_territory({"name": f"Region {self.suffix}", "parent": "China", "isGroup": False, "enabled": True, "sortOrder": 1})

    def assignment(self, territory, **changes):
        return {"territory": territory, "salesOwner": self.sales, "validFrom": "2026-01-01", "validUntil": "2026-06-30", "cancelled": False, "note": "Initial coverage", **changes}

    def test_manager_entry_point_maps_custom_region_without_changing_customer_values(self):
        region = self.region()
        self.assertIn(region["name"], list_regions())
        result = service.catalogue()
        self.assertIn(region["name"], {row["name"] for row in result["territories"]})
        self.assertNotIn(region["name"], result["unmappedRegions"])
        self.assertIn(self.sales, {person["id"] for person in result["sales"]})
        self.assertFalse(any(row["territory"] == region["name"] for row in result["assignments"]))
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException):
            service.catalogue()
        with self.assertRaises(CrmApiException):
            service.save_territory({"name": "Forbidden", "parent": "China", "isGroup": False, "enabled": True})

    def test_save_checks_versions_immutable_name_and_retains_disabled_region_in_filter(self):
        from rayher_crm.services.territories import region_tree
        region = self.region()
        payload = {"name": region["name"], "parent": "China", "isGroup": False, "enabled": False, "sortOrder": 1}
        disabled = service.save_territory(payload, region["name"], region["modified"])
        self.assertFalse(disabled["enabled"])
        self.assertIn(region["name"], region_tree(list_regions())[0])
        with self.assertRaises(CrmApiException) as stale:
            service.save_territory({**payload, "enabled": True}, region["name"], region["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        with self.assertRaises(CrmApiException):
            service.save_territory({**payload, "name": "Renamed"}, region["name"], disabled["modified"])
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.assignment(region["name"]))

    def test_assignment_ranges_prevent_overlap_and_preserve_cancelled_history(self):
        region = self.region()
        first = service.save_assignment(self.assignment(region["name"]))
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.assignment(region["name"], validFrom="2026-06-30", validUntil=None))
        second = service.save_assignment(self.assignment(region["name"], validFrom="2026-07-01", validUntil=None))
        self.assertNotEqual(first["id"], second["id"])
        cancelled = service.save_assignment(self.assignment(region["name"], cancelled=True, note="Correct mistaken assignment"), first["id"], first["modified"])
        self.assertTrue(cancelled["cancelled"])
        replacement = service.save_assignment(self.assignment(region["name"]))
        self.assertNotEqual(first["id"], replacement["id"])
        listed = [row for row in service.catalogue()["assignments"] if row["territory"] == region["name"]]
        self.assertEqual(len(listed), 3)
        self.assertEqual(sum(row["cancelled"] for row in listed), 1)
        # Assigning a second region to the same Sales user is explicitly supported.
        other = service.save_territory({"name": f"Other {self.suffix}", "parent": "China", "isGroup": False, "enabled": True})
        service.save_assignment(self.assignment(other["name"]))

    def test_assignment_case_variant_remains_joined_to_the_catalogue_leaf(self):
        region = self.region()
        submitted = region["name"].lower()
        self.assertNotEqual(submitted, region["name"])
        saved = service.save_assignment(self.assignment(submitted))
        self.assertEqual(saved["territory"], region["name"])
        self.assertEqual(frappe.db.get_value(service.ASSIGNMENT, saved["id"], "territory"), region["name"])
        revised = service.save_assignment(self.assignment(submitted, note="Confirmed coverage"), saved["id"], saved["modified"])
        catalogue = service.catalogue()
        leaf = next(row for row in catalogue["territories"] if row["name"] == region["name"])
        joined = [row for row in catalogue["assignments"] if row["territory"] == leaf["name"]]
        self.assertEqual([row["id"] for row in joined], [saved["id"]])
        self.assertEqual(revised["territory"], leaf["name"])
        self.assertEqual(joined[0]["note"], "Confirmed coverage")
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.assignment(submitted))

    def test_group_assignment_and_engineer_or_disabled_owner_are_rejected(self):
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.assignment("China"))
        region = self.region()
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.assignment(region["name"], salesOwner=self.manager))
        frappe.db.set_value("User", self.sales, "enabled", 0)
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.assignment(region["name"]))

    def test_new_leaf_uses_region_name_returned_after_registration_lock(self):
        from rayher_crm.services.regions import register_region
        submitted = f"Coastal Region {self.suffix}"
        canonical = f"Coastal-Region-{self.suffix}"
        # Simulate the options becoming visible only when registration takes its lock.
        def register_after_read(value):
            self.assertEqual(value, submitted)
            return register_region(canonical)
        with patch.object(service, "register_region", side_effect=register_after_read):
            saved = service.save_territory({"name": submitted, "parent": "China", "isGroup": False, "enabled": True})
        self.assertEqual(saved["name"], canonical)
        self.assertNotIn(canonical, service.catalogue()["unmappedRegions"])
        from rayher_crm.services.territories import region_tree
        self.assertEqual(region_tree(list_regions())[1][canonical], "China")

    def test_customer_region_variant_can_be_attached_below_a_group(self):
        from rayher_crm.services.regions import register_region
        from rayher_crm.services.territories import region_tree
        group = service.save_territory({"name": f"Coastal Area {self.suffix}", "parent": "Asia", "isGroup": True, "enabled": True})
        region_name = register_region(f"Coastal-Area-{self.suffix}")
        region = service.save_territory({"name": region_name, "parent": group["name"], "isGroup": False, "enabled": True})
        self.assertEqual(region["name"], region_name)
        self.assertNotIn(region_name, service.catalogue()["unmappedRegions"])
        self.assertEqual(region_tree(list_regions())[1][region_name], group["name"])
        service.save_assignment(self.assignment(region_name))
        # A leaf's spelling must not make its existing group impossible to edit.
        service.save_territory({"name": group["name"], "parent": "Asia", "isGroup": True, "enabled": True, "sortOrder": 3}, group["name"], group["modified"])

    def test_group_cannot_consume_an_existing_customer_region(self):
        from rayher_crm.services.regions import register_region
        canonical = register_region(f"Unplaced-Area-{self.suffix}")
        with self.assertRaises(CrmApiException) as rejected:
            service.save_territory({"name": f"Unplaced Area {self.suffix}", "parent": "Asia", "isGroup": True, "enabled": True})
        self.assertEqual(rejected.exception.code, "VALIDATION_ERROR")
        self.assertIn(canonical, service.catalogue()["unmappedRegions"])
        region = service.save_territory({"name": canonical, "parent": "China", "isGroup": False, "enabled": True})
        service.save_assignment(self.assignment(region["name"]))

    def test_case_insensitive_group_collision_returns_validation_error(self):
        from rayher_crm.services.regions import REGION_FIELD, options_text
        # A legacy option remains visible; registering a new collision is blocked.
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text([*list_regions(), "world"]), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        with self.assertRaises(CrmApiException) as rejected:
            service.save_territory({"name": "world", "parent": "China", "isGroup": False, "enabled": True})
        self.assertEqual(rejected.exception.code, "VALIDATION_ERROR")
        self.assertTrue(frappe.db.get_value(service.TERRITORY, "World", "is_group"))

    def test_new_customer_region_cannot_take_group_identity_and_legacy_collision_is_visible(self):
        from rayher_crm.services.regions import REGION_FIELD, options_text, register_region
        group = service.save_territory({"name": f"Reserved Group {self.suffix}", "parent": "Asia", "isGroup": True, "enabled": True})
        for name in (group["name"], group["name"].lower()):
            with self.subTest(name=name), self.assertRaises(CrmApiException) as rejected:
                register_region(name)
            self.assertEqual(rejected.exception.code, "VALIDATION_ERROR")
        self.assertNotIn(group["name"], list_regions())
        # Pre-existing exact group-valued Customer regions need reconciliation.
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text([*list_regions(), group["name"]]), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        self.assertEqual(register_region(group["name"]), group["name"])
        self.assertIn(group["name"], service.catalogue()["unmappedRegions"])

    def test_ambiguous_crm_roles_are_not_assignable_or_listed(self):
        region = self.region()
        user = frappe.get_doc("User", self.sales)
        user.append("roles", {"role": "CRM Engineer"})
        user.save(ignore_permissions=True)
        frappe.clear_cache(user=self.sales)
        self.addCleanup(frappe.clear_cache, user=self.sales)
        self.assertNotIn(self.sales, {row["id"] for row in service.catalogue()["sales"]})
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.assignment(region["name"]))

    def test_inactive_owner_cannot_extend_assignment_but_can_shorten_or_cancel(self):
        region = self.region()
        assignment = service.save_assignment(self.assignment(region["name"]))
        frappe.db.set_value("User", self.sales, "enabled", 0)
        for change in ({"validUntil": None}, {"validUntil": "2027-01-01"}, {"validFrom": "2025-12-01"}):
            with self.subTest(change=change), self.assertRaises(CrmApiException):
                service.save_assignment(self.assignment(region["name"], **change), assignment["id"], assignment["modified"])
        shortened = service.save_assignment(self.assignment(region["name"], validUntil="2026-05-31"), assignment["id"], assignment["modified"])
        cancelled = service.save_assignment(self.assignment(region["name"], cancelled=True), assignment["id"], shortened["modified"])
        self.assertTrue(cancelled["cancelled"])

    def test_existing_alias_and_non_english_names_remain_editable(self):
        for name, group in (("Eastern", True), ("旧分组" + self.suffix, True), ("East", False), ("旧地区" + self.suffix, False)):
            with self.subTest(name=name):
                # Explicit pre-validation legacy fixture: new reserved aliases
                # are rejected, but existing names must remain maintainable.
                doc = frappe.get_doc({"doctype": service.TERRITORY, "name": name, "territory_name": name,
                                      "parent_territory": "Asia", "is_group": int(group), "enabled": 1})
                doc.db_insert()
                result = service.save_territory({"name": name, "parent": "World", "isGroup": group,
                                                 "enabled": False, "sortOrder": 7}, name, service.to_iso_timestamp(doc.modified))
                self.assertEqual((result["name"], result["parent"], result["enabled"], result["sortOrder"]), (name, "World", False, 7))

    def test_migration_reconciles_case_variant_leaf_and_preserves_links_and_customer_values(self):
        from rayher_crm.patches.v1_0.reconcile_territory_region_identity import execute
        from rayher_crm.services.accounts import create_account
        from rayher_crm.services.regions import register_region
        from rayher_crm.services.territories import region_tree
        from rayher_crm.services.territory_tree import covered

        canonical = register_region(f"Legacy Area {self.suffix}")
        legacy = canonical.lower()
        # Explicit pre-validation fixture: new native inserts reject this alias.
        frappe.get_doc({"doctype": service.TERRITORY, "name": legacy, "territory_name": legacy,
                        "parent_territory": "China", "is_group": 0, "enabled": 1}).db_insert()
        assignment = service.save_assignment(self.assignment(legacy))
        account = create_account({"name": f"Legacy Customer {self.suffix}", "shortName": self.suffix,
                                  "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": canonical, "owner": self.sales})
        from rayher_crm.services import opportunity_board
        with patch.dict(frappe.conf, {"crm_cockpit_region_migration_verified": True}):
            saved = opportunity_board.save_opportunity_query(None, {"name": f"Leaf Query {self.suffix}", "definition": {
                "scope": {"regions": [legacy]}, "conditions": [{"field": "region", "operator": "in", "value": [legacy]}], "columns": ["title"],
            }})
        execute()
        execute()
        definition = frappe.parse_json(frappe.db.get_value(opportunity_board.SAVED_QUERY, saved["id"], "definition"))
        self.assertEqual(definition["scope"]["regions"], [canonical])
        self.assertEqual(definition["conditions"][0]["value"], [canonical])
        with patch.dict(frappe.conf, {"crm_cockpit_region_migration_verified": True}):
            opportunity_board.rules.validate_definition(definition, opportunity_board._board_context(include_rows=False)["options"])
        stored = frappe.db.get_value(service.TERRITORY, canonical, ["name", "territory_name", "parent_territory"], as_dict=True)
        self.assertEqual((stored.name, stored.territory_name, stored.parent_territory), (canonical, canonical, "China"))
        self.assertEqual(frappe.db.get_value(service.ASSIGNMENT, assignment["id"], "territory"), canonical)
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_region"), canonical)
        self.assertNotIn(canonical, service.catalogue()["unmappedRegions"])
        names, parents = region_tree(list_regions())
        self.assertIn(canonical, covered("China", names, parents))
        self.assertNotIn(legacy, names)

    def test_migration_frees_group_identity_for_explicit_customer_region_mapping(self):
        from rayher_crm.patches.v1_0.reconcile_territory_region_identity import execute
        from rayher_crm.services.accounts import create_account
        from rayher_crm.services.regions import REGION_FIELD, options_text

        group = service.save_territory({"name": f"Legacy Group {self.suffix}", "parent": "Asia", "isGroup": True, "enabled": True})
        child = service.save_territory({"name": f"Legacy Child {self.suffix}", "parent": group["name"], "isGroup": False, "enabled": True})
        # A group-valued region was legal before the new region registration guard.
        canonical = group["name"]
        # The largest legacy list must stay executable after one value splits.
        legacy_values = [canonical, *(f"Legacy Region {index} {self.suffix}" for index in range(99))]
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text([*list_regions(), *legacy_values]), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        account = create_account({"name": f"Group Customer {self.suffix}", "shortName": self.suffix,
                                  "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": canonical, "owner": self.sales})
        from rayher_crm.services import opportunity_board
        with patch.dict(frappe.conf, {"crm_cockpit_region_migration_verified": True}):
            saved = opportunity_board.save_opportunity_query(None, {"name": f"Legacy Region Query {self.suffix}", "definition": {
                "scope": {"regions": legacy_values}, "match": "all", "conditions": [
                    {"field": "region", "operator": op, "value": legacy_values} for op in ("in", "not_in")
                ], "columns": ["title"],
            }})
        execute()
        renamed = frappe.db.get_value(service.TERRITORY, child["name"], "parent_territory")
        self.assertNotEqual(renamed, group["name"])
        self.assertEqual(frappe.db.get_value(service.TERRITORY, renamed, ["is_group", "parent_territory"]), (1, "Asia"))
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_region"), canonical)
        definition = frappe.parse_json(frappe.db.get_value(opportunity_board.SAVED_QUERY, saved["id"], "definition"))
        expected = [renamed, *legacy_values]
        self.assertEqual(definition["scope"]["regions"], expected)
        for condition in definition["conditions"]:
            self.assertEqual(condition["value"], expected)
        with patch.dict(frappe.conf, {"crm_cockpit_region_migration_verified": True}):
            opportunity_board.rules.validate_definition(definition, opportunity_board._board_context(include_rows=False)["options"])
            # Service save must accept exactly the migrated definition, too.
            opportunity_board.save_opportunity_query(None, {"name": f"Migrated copy {self.suffix}", "definition": definition})
        self.assertNotEqual(opportunity_board.to_iso_timestamp(frappe.db.get_value(opportunity_board.SAVED_QUERY, saved["id"], "modified")), saved["modified"])
        self.assertIn(canonical, service.catalogue()["unmappedRegions"])
        execute()
        self.assertEqual(frappe.db.get_value(service.TERRITORY, child["name"], "parent_territory"), renamed)
        # The existing manager workflow can now complete this formerly impossible mapping.
        mapped = service.save_territory({"name": canonical, "parent": renamed, "isGroup": False, "enabled": True})
        service.save_assignment(self.assignment(mapped["name"]))
        self.assertNotIn(canonical, service.catalogue()["unmappedRegions"])

    def test_upgrade_column_default_keeps_legacy_leaf_mapped_after_reconciliation(self):
        from rayher_crm.patches.v1_0.reconcile_territory_region_identity import execute
        from rayher_crm.services.accounts import create_account
        from rayher_crm.services.regions import register_region

        canonical = register_region(f"Upgrade Leaf {self.suffix}")
        legacy = canonical.lower()
        group = f"Upgrade Group {self.suffix}"
        empty = service.save_territory({"name": f"Explicit Empty {self.suffix}", "parent": "World", "isGroup": True, "enabled": True})
        for name, parent, is_group in ((group, "Asia", 1), (legacy, group, 0)):
            # Explicit old-schema rows, before native creation enforced registration.
            frappe.get_doc({"doctype": service.TERRITORY, "name": name, "territory_name": name,
                            "parent_territory": parent, "is_group": is_group, "enabled": 1}).db_insert()
        frappe.db.set_value(service.TERRITORY, legacy, "parent_territory", group.lower(), update_modified=False)
        for name in (group, legacy):
            # Model sync gives every existing row the new column's SQL default.
            # Exercise that installed default without DDL (which would commit
            # the suite's business fixtures and defeat rollback isolation).
            frappe.db.sql("UPDATE `tabCRM Sales Territory` SET is_group=DEFAULT(is_group) WHERE name=%s", (name,))
            self.assertEqual(frappe.db.get_value(service.TERRITORY, name, "is_group"), 0)
        account = create_account({"name": f"Upgrade Customer {self.suffix}", "shortName": self.suffix,
                                  "segment": "Frontend", "tier": "A", "city": "Shanghai", "region": canonical, "owner": self.sales})
        for _ in range(2):
            execute()
            self.assertEqual(frappe.db.get_value(service.TERRITORY, group, "is_group"), 1)
            self.assertEqual(frappe.db.get_value(service.TERRITORY, canonical, ["name", "is_group", "parent_territory"]), (canonical, 0, group))
            self.assertEqual(frappe.db.get_value(service.TERRITORY, empty["name"], "is_group"), 1)
            self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_region"), canonical)
            self.assertNotIn(canonical, service.catalogue()["unmappedRegions"])
        self.assertEqual(service.save_assignment(self.assignment(canonical))["territory"], canonical)

    def test_initialization_canonicalizes_parent_links_before_classifying_nodes(self):
        from rayher_crm.patches.v1_0.initialize_territory_administration import execute
        group = service.save_territory({"name": f"Mixed Parent {self.suffix}", "parent": "Asia", "isGroup": True, "enabled": True})
        child = service.save_territory({"name": f"Mixed Child {self.suffix}", "parent": group["name"], "isGroup": False, "enabled": True})
        empty = service.save_territory({"name": f"Empty Group {self.suffix}", "parent": "World", "isGroup": True, "enabled": True})
        frappe.db.set_value(service.TERRITORY, group["name"], "is_group", 0, update_modified=False)
        frappe.db.set_value(service.TERRITORY, child["name"], "parent_territory", group["name"].lower(), update_modified=False)
        execute()
        execute()
        self.assertEqual(frappe.db.get_value(service.TERRITORY, child["name"], "parent_territory"), group["name"])
        self.assertEqual(frappe.db.get_value(service.TERRITORY, group["name"], "is_group"), 1)
        self.assertEqual(frappe.db.get_value(service.TERRITORY, empty["name"], "is_group"), 1)
        service.save_territory({"name": group["name"], "parent": "World", "isGroup": True, "enabled": True}, group["name"], group["modified"])

    def test_schema_adds_unregistered_native_leaf_to_customer_options(self):
        from rayher_crm.setup.custom_fields import _custom_fields_for_install
        from rayher_crm.services.regions import REGION_FIELD
        name = f"Native Leaf {self.suffix}"
        # Existing unregistered leaves still need schema repair after upgrade.
        frappe.get_doc({"doctype": service.TERRITORY, "name": name, "territory_name": name,
                        "parent_territory": "China", "is_group": 0, "enabled": 0}).db_insert()
        self.assertNotIn(name, list_regions())
        for options in ("\nEast China", ""):
            frappe.db.set_value("Custom Field", REGION_FIELD, "options", options, update_modified=False)
            fields = _custom_fields_for_install()["Customer"]
            registered = next(field["options"] for field in fields if field["fieldname"] == "custom_crm_region").splitlines()
            self.assertIn(name, registered)
            self.assertNotIn("China", registered)  # groups are never Customer choices

