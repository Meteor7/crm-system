from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import cockpit, opportunity_board
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.regions import REGION_PRESETS
from rayher_crm.services.sites import create_site
from rayher_crm.services.territories import DOCTYPE, ensure_default_territories, region_tree

TREE = ["World", "Asia", "China", *REGION_PRESETS]
PARENTS = {"Asia": "World", "China": "Asia", **{region: "China" for region in REGION_PRESETS}}
READY = {"crm_cockpit_region_migration_verified": True}


class TestSalesTerritories(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        # Registered regions live in the Customer meta cache; clear it after the class rollback.
        cls.addClassCleanup(frappe.clear_cache, doctype="Customer")
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        # Every test starts from the tree a new site has.
        frappe.db.delete(DOCTYPE)
        ensure_default_territories()
        self.sales = self._user("crm-territory-sales@example.invalid", "CRM Sales")
        self.manager = self._user("crm-territory-manager@example.invalid", "CRM Manager")
        self.addCleanup(frappe.clear_cache, doctype="Customer")

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

    def _deal(self, name: str, region: str) -> dict:
        """A customer in a region with one stage-1 Opportunity; returns the ids."""

        account = create_account({
            "name": name, "shortName": name[:8], "segment": "Frontend", "tier": "A",
            "city": "上海", "region": region, "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"{name} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline", "accountId": account["id"], "siteId": site["id"], "title": f"{name} deal",
            "owner": self.sales, "amount": "100000.00", "intentScore": 30, "poDate": "2026-12-31",
            "toolType": "Inspection", "saleType": "New Equipment", "subRegion": region, "currency": "CNY",
            "originalAmount": "100000.00", "amountCny": "100000.00", "qualificationConfirmed": True,
        })
        return {"account": account["id"], "opportunity": opportunity["id"]}

    def _query(self, region: str) -> dict:
        return {"period": "week", "anchor": frappe.utils.now_datetime().date().isoformat(),
                "sales": "", "market": "", "region": region, "equipment": ""}

    def test_a_site_starts_with_world_asia_china_and_the_five_regions(self):
        self.assertEqual(region_tree(list(REGION_PRESETS)), (TREE, PARENTS))

        # Seeding again adds nothing, and a site that has its own territories keeps them.
        ensure_default_territories()
        self.assertEqual(frappe.db.count(DOCTYPE), len(TREE))
        frappe.db.delete(DOCTYPE)
        frappe.get_doc({"doctype": DOCTYPE, "territory_name": "Europe"}).insert()
        ensure_default_territories()
        self.assertEqual(region_tree(["Overseas"]), (["Europe", "Overseas"], {}))

    def test_a_territory_cannot_sit_below_itself(self):
        world = frappe.get_doc(DOCTYPE, "World")
        for parent in ("World", "China", "East China"):
            with self.subTest(parent=parent):
                world.parent_territory = parent
                self.assertRaises(frappe.ValidationError, world.save)

        # Moving a territory elsewhere in the tree is fine.
        china = frappe.get_doc(DOCTYPE, "China")
        china.parent_territory = "World"
        china.save()
        self.assertEqual(region_tree([])[1]["China"], "World")

    def test_the_region_filter_lists_the_tree_and_a_territory_selects_the_regions_below_it(self):
        frappe.set_user(self.sales)
        east = self._deal("Territory East", "East China")
        south = self._deal("Territory South", "South China")
        overseas = self._deal("Territory Overseas", "Overseas")
        accounts = {deal["account"] for deal in (east, south, overseas)}
        frappe.set_user(self.manager)

        def selected(region):
            customers, _people, filters = cockpit.scoped(self._query(region))
            return {row["name"] for row in customers} & accounts, filters

        with patch.dict(frappe.conf, READY):
            everyone, filters = selected("")
            self.assertEqual(everyone, accounts)
            # The tree first, then the regions no territory is named after.
            self.assertEqual(filters["regions"][:len(TREE)], TREE)
            self.assertIn("Overseas", filters["regions"][len(TREE):])
            self.assertEqual(filters["regionParents"], PARENTS)
            for territory in ("China", "Asia", "World"):
                with self.subTest(territory=territory):
                    self.assertEqual(selected(territory)[0], {east["account"], south["account"]})
            self.assertEqual(selected("East China")[0], {east["account"]})
            self.assertEqual(selected("Overseas")[0], {overseas["account"]})
            with self.assertRaises(CrmApiException) as unknown:
                selected("Europe")
            self.assertEqual(unknown.exception.code, "VALIDATION_ERROR")

            # Review counts the same customers: stage-1 deals of both regions under China.
            def stage_one(region):
                rows = cockpit.calculate(self._query(region))["_details"]["qualified_opportunity"]
                return {row["id"] for row in rows} & {east["opportunity"], south["opportunity"], overseas["opportunity"]}
            self.assertEqual(stage_one("China"), {east["opportunity"], south["opportunity"]})
            self.assertEqual(stage_one("South China"), {south["opportunity"]})
            self.assertEqual(stage_one("Overseas"), {overseas["opportunity"]})

        # Until the region migration is verified there is no region list, so no tree and no territory filter.
        _everyone, filters = selected("")
        self.assertEqual((filters["regions"], filters["regionParents"], filters["regionReady"]), ([], {}, False))
        self.assertRaises(CrmApiException, selected, "China")

    def test_the_board_reads_a_territory_as_within(self):
        frappe.set_user(self.sales)
        east = self._deal("Territory Board East", "East China")
        south = self._deal("Territory Board South", "South China")
        overseas = self._deal("Territory Board Overseas", "Overseas")
        frappe.set_user(self.manager)
        mine = {"field": "customerName", "operator": "contains", "value": "Territory Board"}

        def ids(**query):
            data, _total, _page, _size = opportunity_board.query_opportunities(
                {**query, "conditions": [mine, *query.get("conditions", [])], "pageSize": 100})
            return {item["id"] for item in data["items"]}

        with patch.dict(frappe.conf, READY):
            self.assertEqual(ids(scope={"regions": ["China"]}), {east["opportunity"], south["opportunity"]})
            self.assertEqual(ids(scope={"regions": ["South China", "Overseas"]}), {south["opportunity"], overseas["opportunity"]})
            self.assertEqual(ids(conditions=[{"field": "region", "operator": "not_in", "value": ["Asia"]}]), {overseas["opportunity"]})
            filters = opportunity_board.get_opportunity_filters()
            self.assertEqual(filters["regions"][:len(TREE)], [{"value": name, "label": name} for name in TREE])
            self.assertEqual(filters["regionParents"], PARENTS)
