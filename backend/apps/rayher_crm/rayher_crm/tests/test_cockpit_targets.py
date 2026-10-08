from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import cockpit, territory_admin
from rayher_crm.tests.test_opportunity_relations import TestOpportunityRelations


class TestCockpitTargets(FrappeTestCase):
    _user = TestOpportunityRelations._user
    _records = TestOpportunityRelations._records

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("target-sales@example.invalid", "CRM Sales")
        self.suffix = frappe.generate_hash(length=8)
        self.addCleanup(frappe.clear_cache, doctype="Customer")

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def leaf(self):
        return territory_admin.save_territory({"name": f"Target Region {self.suffix}", "parent": "China",
                                              "isGroup": False, "enabled": True, "sortOrder": 0})

    def result(self):
        return {"period": {"start": "2030-09-02", "kind": "week", "asOf": "2030-09-08T15:59:59Z"},
                "activities": [{"key": "visits"}], "orders": {}, "filters": {"sales": [{"id": self.sales}]}}

    def test_followup_target_is_saved_and_read_for_the_exact_period(self):
        payload = {"sales": self.sales, "metric": "followups", "period": "week", "anchor": "2030-09-02", "value": "7"}
        saved = cockpit.save_target(payload)
        result = self.result()
        result["activities"] = [{"key": "followups"}]
        cockpit.attach_targets(result, {"sales": self.sales})
        target = result["activities"][0]["target"]
        self.assertEqual((target["value"], target["record"]["id"]), ("7.00", saved["id"]))
        result["period"]["kind"] = "month"
        result["period"]["start"] = "2030-09-01"
        cockpit.attach_targets(result, {"sales": self.sales})
        self.assertEqual(result["activities"][0]["target"]["state"], "not_set")

    def test_statistics_do_not_materialize_other_target_periods(self):
        base = {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5"}
        selected = cockpit.save_target(base)
        cockpit.save_target({**base, "anchor": "2030-08-26"})
        cockpit.save_target({**base, "period": "month", "anchor": "2030-09-01"})
        annual = cockpit.save_target({**base, "metric": "orders", "period": "year", "anchor": "2030-01-01"})
        cockpit.save_target({**base, "metric": "orders", "period": "year", "anchor": "2029-01-01"})
        materialized = []
        serialize = cockpit.target_dto
        def observe(row):
            materialized.append(row["name"])
            return serialize(row)
        with patch.object(cockpit, "target_dto", side_effect=observe):
            result = self.result()
            cockpit.attach_targets(result, {"sales": self.sales})
        own = [row for row in result["targets"] if row["sales"] == self.sales]
        self.assertEqual({row["id"] for row in own}, {selected["id"], annual["id"]})
        self.assertEqual(set(materialized), {row["id"] for row in result["targets"]})
        self.assertEqual(result["activities"][0]["target"]["value"], "5.00")

    def test_week_defaults_keep_latest_ties_and_case_identity_but_exclude_future_and_old_defaults(self):
        base = {"sales": self.sales, "metric": "visits", "period": "weekly_default", "anchor": "2030-08-19", "value": "3"}
        old = cockpit.save_target(base)
        latest = cockpit.save_target({**base, "anchor": "2030-08-26", "value": "5"})
        future = cockpit.save_target({**base, "anchor": "2030-09-09", "value": "7"})
        duplicate = frappe.copy_doc(frappe.get_doc(cockpit.TARGET, latest["id"]))
        duplicate.name = frappe.generate_hash(length=32)
        duplicate.insert(ignore_permissions=True)
        frappe.db.set_value(cockpit.TARGET, duplicate.name, {"sales_owner": self.sales.upper(), "target_scope": None}, update_modified=False)
        result = self.result()
        cockpit.attach_targets(result, {"sales": self.sales})
        ids = {row["id"] for row in result["targets"]}
        self.assertTrue({latest["id"], duplicate.name} <= ids)
        self.assertTrue({old["id"], future["id"]}.isdisjoint(ids))
        self.assertEqual(result["activities"][0]["target"]["reason"], "duplicate_targets")
        explicit = cockpit.save_target({**base, "period": "week", "anchor": "2030-09-02", "value": "9"})
        cockpit.attach_targets(result, {"sales": self.sales})
        self.assertEqual(result["activities"][0]["target"]["record"]["id"], explicit["id"])
        self.assertFalse(any(row["period"] == "weekly_default" for row in cockpit.period_target_rows("month", "2030-09-01")))

    def test_statistics_read_orders_in_asof_year_for_a_new_year_week(self):
        base = {"sales": self.sales, "metric": "orders", "period": "year", "value": "100"}
        old = cockpit.save_target({**base, "anchor": "2029-01-01"})
        current = cockpit.save_target({**base, "anchor": "2030-01-01", "value": "200"})
        result = self.result()
        result["period"].update(start="2029-12-31", asOf="2030-01-06T15:59:59Z")
        cockpit.attach_targets(result, {"sales": self.sales})
        self.assertEqual(result["orders"]["target"]["record"]["id"], current["id"])
        self.assertNotIn(old["id"], {row["id"] for row in result["targets"]})

    def test_editor_reads_exact_key_preserves_cas_and_historical_identity(self):
        base = {"sales": self.sales, "metric": "visits", "period": "weekly_default", "anchor": "2030-08-19", "value": "3"}
        saved = cockpit.save_target(base)
        cockpit.save_target({**base, "anchor": "2030-08-26", "value": "5"})
        frappe.db.set_value(cockpit.TARGET, saved["id"], {"target_scope": None, "sales_owner": self.sales.upper(), "territory": None}, update_modified=False)
        frappe.db.set_value("User", self.sales, "enabled", 0)
        found = cockpit.get_target({**base, "sales": self.sales.upper()})
        self.assertEqual((found["id"], found["modified"], found["sales"]), (saved["id"], saved["modified"], self.sales))
        self.assertIsNone(cockpit.get_target({**base, "anchor": "2030-09-02"}))
        # Reading a historical effective date does not apply the future-only write rule.
        frappe.db.set_value(cockpit.TARGET, saved["id"], "anchor", "2020-01-06", update_modified=False)
        self.assertEqual(cockpit.get_target({**base, "anchor": "2020-01-06"})["id"], saved["id"])
        for change in ({"anchor": "2030-09-03"}, {"metric": "orders"}, {"scope": "territory"}):
            with self.subTest(change=change), self.assertRaises(CrmApiException):
                cockpit.get_target({**base, **change})

    def test_editor_rejects_duplicates_instead_of_choosing_a_cas_winner(self):
        base = {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5"}
        saved = cockpit.save_target(base)
        duplicate = frappe.copy_doc(frappe.get_doc(cockpit.TARGET, saved["id"]))
        duplicate.name = frappe.generate_hash(length=32)
        duplicate.insert(ignore_permissions=True)
        with self.assertRaises(CrmApiException) as error:
            cockpit.get_target(base)
        self.assertEqual(error.exception.code, "CONFLICT")

    def test_leaf_annual_target_is_versioned_and_never_added_to_personal_goal(self):
        leaf = self.leaf()
        payload = {"scope": "territory", "territory": leaf["name"], "sales": "", "metric": "orders",
                   "period": "year", "anchor": "2030-01-01", "value": "1500000"}
        saved = cockpit.save_target(payload)
        self.assertEqual((saved["scope"], saved["sales"], saved["territory"]), ("territory", "", leaf["name"]))
        updated = cockpit.save_target({**payload, "value": "2000000"}, saved["modified"])
        self.assertEqual(updated["value"], "2000000.00")
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": cockpit.TARGET, "docname": saved["id"]}))
        with self.assertRaises(CrmApiException) as stale:
            cockpit.save_target({**payload, "value": "3000000"}, saved["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        cockpit.save_target({"sales": self.sales, "metric": "orders", "period": "year", "anchor": "2030-01-01", "value": "9000000"})
        result = self.result()
        cockpit.attach_targets(result, {"region": leaf["name"]}, customers=[{"custom_crm_region": leaf["name"]}])
        self.assertEqual(result["orders"]["target"]["value"], "2000000.00")
        self.assertEqual(result["orders"]["target"]["sources"][0]["record"]["id"], saved["id"])
        personal = self.result()
        cockpit.attach_targets(personal, {"sales": self.sales})
        self.assertEqual(personal["orders"]["target"]["value"], "9000000.00")
        for change in ({"territory": "China"}, {"sales": self.sales}, {"metric": "visits"}, {"period": "month"}):
            with self.subTest(change=change), self.assertRaises(CrmApiException):
                cockpit.save_target({**payload, **change})
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as denied:
            cockpit.save_target(payload)
        self.assertEqual(denied.exception.code, "PERMISSION_DENIED")

    def test_missing_leaf_and_unmapped_customer_regions_keep_total_incomplete(self):
        leaf = self.leaf()
        cockpit.save_target({"scope": "territory", "territory": leaf["name"], "metric": "orders",
                             "period": "year", "anchor": "2030-01-01", "value": "0"})
        result = self.result()
        cockpit.attach_targets(result, {"region": "China"}, customers=[{"custom_crm_region": "China"}])
        self.assertEqual(result["orders"]["target"]["state"], "insufficient")
        self.assertIsNone(result["orders"]["target"]["value"])
        self.assertIn("China", result["orders"]["target"]["missing"])
        with patch.object(territory_admin, "list_regions", return_value=["China", leaf["name"]]):
            self.assertEqual(territory_admin.catalogue()["unmappedRegions"], ["China"])
        # Deactivation retains a region's existing classification and targets.
        territory_admin.save_territory({"name": leaf["name"], "parent": "China", "isGroup": False,
                                       "enabled": False, "sortOrder": 0}, leaf["name"], leaf["modified"])
        result = self.result()
        cockpit.attach_targets(result, {"region": leaf["name"]})
        self.assertEqual(result["orders"]["target"]["value"], "0.00")

    def test_legacy_personal_target_keeps_identity_and_missing_owners_are_not_zero(self):
        payload = {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5"}
        saved = cockpit.save_target(payload)
        frappe.db.set_value(cockpit.TARGET, saved["id"], "target_scope", None, update_modified=False)
        updated = cockpit.save_target({**payload, "value": "6"}, saved["modified"])
        self.assertEqual(updated["id"], saved["id"])
        self.assertEqual(updated["scope"], "sales")
        result = self.result()
        result["_details"] = {"visits": [{"owner": "former-sales@example.invalid"}]}
        cockpit.attach_targets(result, {})
        self.assertEqual(result["activities"][0]["target"]["state"], "insufficient")
        self.assertIn("former-sales@example.invalid", result["activities"][0]["target"]["missing"])
        frappe.db.set_value("User", self.sales, "enabled", 0)
        with self.assertRaises(CrmApiException):
            cockpit.save_target({**payload, "value": "7"}, updated["modified"])

    def test_target_roster_excludes_disabled_and_other_roles_and_outsiders_affect_only_their_metric(self):
        departed = self._user(f"departed-{self.suffix}@example.invalid", "CRM Sales")
        manager = self._user(f"manager-{self.suffix}@example.invalid", "CRM Manager")
        ambiguous = self._user(f"mixed-{self.suffix}@example.invalid", "CRM Sales")
        frappe.get_doc("User", ambiguous).add_roles("CRM Manager")
        frappe.db.set_value("User", departed, "enabled", 0)
        roster = cockpit.targetable_sales()
        self.assertIn(self.sales, roster)
        self.assertTrue({departed, manager, ambiguous}.isdisjoint(roster))
        # Isolate aggregation from other tests' installed Sales fixtures.
        result = self.result()
        result["activities"] = [{"key": "visits"}, {"key": "tests"}]
        result["_details"] = {"tests": [{"owner": manager}]}
        cockpit.save_target({"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "0"})
        with patch.object(cockpit, "targetable_sales", return_value={self.sales}):
            cockpit.attach_targets(result, {})
        self.assertEqual(result["targetOptions"]["teamMembers"], [self.sales])
        self.assertEqual(result["activities"][0]["target"]["state"], "ready")
        self.assertNotIn(manager, result["activities"][0]["target"]["missing"])
        source = next(row for row in result["activities"][1]["target"]["sources"] if row["member"] == manager)
        self.assertEqual(source["reason"], "target_owner_not_assignable")
        self.assertFalse(source["assignable"])

    def test_canonical_and_renamed_sales_keep_one_target_and_original_audit_id(self):
        from frappe.model.rename_doc import rename_doc
        payload = {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5"}
        saved = cockpit.save_target(payload)
        with self.assertRaises(CrmApiException) as duplicate:
            cockpit.save_target({**payload, "sales": self.sales.upper()})
        self.assertEqual(duplicate.exception.code, "CONFLICT")
        changed = cockpit.save_target({**payload, "sales": self.sales.upper(), "value": "6"}, saved["modified"])
        self.assertEqual((changed["id"], changed["sales"]), (saved["id"], self.sales))
        # Legacy scope and a changed User Link must still resolve the same record.
        frappe.db.set_value(cockpit.TARGET, saved["id"], "target_scope", None, update_modified=False)
        renamed = f"target-renamed-{self.suffix}@example.invalid"
        rename_doc("User", self.sales, renamed, force=True, ignore_permissions=True, rebuild_search=False)
        current = cockpit.to_iso_timestamp(frappe.db.get_value(cockpit.TARGET, saved["id"], "modified"))
        with self.assertRaises(CrmApiException):
            cockpit.save_target({**payload, "sales": renamed})
        updated = cockpit.save_target({**payload, "sales": renamed, "value": "7"}, current)
        self.assertEqual((updated["id"], updated["sales"], updated["value"]), (saved["id"], renamed, "7.00"))
        self.assertEqual(frappe.db.count(cockpit.TARGET, {"sales_owner": renamed, "metric": "visits", "period": "week", "anchor": "2030-09-02"}), 1)
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": cockpit.TARGET, "docname": saved["id"]}))
        self._user(self.sales, "CRM Sales")
        fresh = cockpit.save_target(payload)
        self.assertNotEqual(fresh["id"], saved["id"])

    def test_legacy_casing_is_visible_to_personal_team_and_annual_targets_without_get_writes(self):
        payload = {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5"}
        saved = cockpit.save_target(payload)
        annual = cockpit.save_target({**payload, "metric": "orders", "period": "year", "anchor": "2030-01-01", "value": "500"})
        for row in (saved, annual):
            frappe.db.set_value(cockpit.TARGET, row["id"], "sales_owner", self.sales.upper(), update_modified=False)
        personal = self.result()
        cockpit.attach_targets(personal, {"sales": self.sales})
        self.assertEqual(personal["activities"][0]["target"]["value"], "5.00")
        self.assertEqual(personal["orders"]["target"]["value"], "500.00")
        record = personal["activities"][0]["target"]["record"]
        self.assertEqual((record["sales"], record["modified"]), (self.sales, saved["modified"]))
        self.assertEqual(frappe.db.get_value(cockpit.TARGET, saved["id"], "sales_owner"), self.sales.upper())
        team = self.result()
        with patch.object(cockpit, "targetable_sales", return_value={self.sales}):
            cockpit.attach_targets(team, {})
        self.assertEqual(team["activities"][0]["target"]["value"], "5.00")
        updated = cockpit.save_target({**payload, "value": "6"}, record["modified"])
        self.assertEqual((updated["id"], updated["sales"]), (saved["id"], self.sales))
        self.assertEqual(frappe.db.get_value(cockpit.TARGET, saved["id"], "sales_owner"), self.sales)

    def test_legacy_case_duplicates_never_choose_one_and_save_refuses_to_merge_them(self):
        payload = {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5"}
        saved = cockpit.save_target(payload)
        duplicate = frappe.get_doc({"doctype": cockpit.TARGET, "name": frappe.generate_hash(length=32),
            "sales_owner": self.sales, "target_scope": "Sales", "metric": "visits", "period": "week",
            "anchor": "2030-09-02", "target_value": "8", "changed_by": "Administrator"}).insert(ignore_permissions=True)
        frappe.db.set_value(cockpit.TARGET, duplicate.name, "sales_owner", self.sales.upper(), update_modified=False)
        result = self.result()
        cockpit.attach_targets(result, {"sales": self.sales})
        self.assertEqual(result["activities"][0]["target"]["reason"], "duplicate_targets")
        team = self.result()
        with patch.object(cockpit, "targetable_sales", return_value={self.sales}):
            cockpit.attach_targets(team, {})
        self.assertEqual(team["activities"][0]["target"]["state"], "insufficient")
        self.assertIsNone(team["activities"][0]["target"]["value"])
        with self.assertRaises(CrmApiException) as conflict:
            cockpit.save_target({**payload, "value": "9"}, saved["modified"])
        self.assertEqual(conflict.exception.code, "CONFLICT")
        self.assertEqual(frappe.db.count(cockpit.TARGET, {"sales_owner": self.sales, "metric": "visits", "anchor": "2030-09-02"}), 2)

    def owner_history(self):
        from rayher_crm.services.opportunities import update_strategy_opportunity
        account, opportunity, _ = self._records(self.sales, f"History{self.suffix}")
        frappe.set_user("Administrator")
        other = self._user(f"history-next-{self.suffix}@example.invalid", "CRM Sales")
        cutoff = frappe.utils.now_datetime()
        update_strategy_opportunity(opportunity["id"], {"owner": other}, opportunity["modified"])
        event = frappe.get_doc("CRM Opportunity History", {"opportunity": opportunity["id"], "field": "opportunity_owner"})
        return account, opportunity, other, cutoff, event

    def replay_owner(self, account, opportunity, cutoff):
        from rayher_crm.services.cockpit_metrics import field_at
        data = cockpit.load_data([{"name": account["id"]}], [])
        current = next(row for row in data["opportunities"] if row["name"] == opportunity["id"])
        return field_at(current, "opportunity_owner", cutoff, data["history"], {"fields": "2000-01-01"}, frappe.utils.now_datetime())

    def test_transferred_owner_rename_keeps_historical_identity_target_and_original_text(self):
        from frappe.model.rename_doc import rename_doc
        from rayher_crm.services.cockpit_identity import backfill_owner_identities
        account, opportunity, other, cutoff, event = self.owner_history()
        original = self.sales
        self.assertEqual((event.from_owner, event.to_owner), (original, other))
        # Exercise the upgrade of an old raw-only row, including canonical casing.
        frappe.db.set_value("CRM Opportunity History", event.name,
            {"from_value": original.upper(), "from_owner": None, "to_owner": None, "owner_identity_resolved": 0}, update_modified=False)
        backfill_owner_identities()
        renamed = f"history-renamed-{self.suffix}@example.invalid"
        target = cockpit.save_target({"sales": original, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5"})
        rename_doc("User", original, renamed, force=True, ignore_permissions=True, rebuild_search=False)
        event.reload()
        self.assertEqual((event.from_value, event.from_owner, event.to_owner), (original.upper(), renamed, other))
        owner = self.replay_owner(account, opportunity, cutoff)
        self.assertEqual(owner, renamed)
        self._user(original, "CRM Sales")
        self.assertEqual(self.replay_owner(account, opportunity, cutoff), renamed)
        result = self.result()
        result["_details"] = {"visits": [{"owner": owner}]}
        with patch.object(cockpit, "targetable_sales", return_value={renamed}):
            cockpit.attach_targets(result, {})
        total = result["activities"][0]["target"]
        self.assertEqual((total["state"], total["value"], len(total["sources"])), ("ready", "5.00", 1))
        self.assertEqual(total["sources"][0]["record"]["id"], target["id"])
        # Both identity sides follow native rename and the DB transaction rolls back.
        frappe.db.savepoint("identity_chain")
        final = f"history-final-{self.suffix}@example.invalid"
        rename_doc("User", renamed, final, force=True, ignore_permissions=True, rebuild_search=False)
        rename_doc("User", other, f"history-other-{self.suffix}@example.invalid", force=True, ignore_permissions=True, rebuild_search=False)
        self.assertEqual(self.replay_owner(account, opportunity, cutoff), final)
        frappe.db.rollback(save_point="identity_chain")
        self.assertEqual(self.replay_owner(account, opportunity, cutoff), renamed)
        self.assertEqual(frappe.db.get_value("CRM Opportunity History", event.name, "to_owner"), other)

    def test_legacy_orphan_email_reuse_stays_unknown_through_backfill_and_new_user_rename(self):
        from frappe.model.rename_doc import rename_doc
        from rayher_crm.services.cockpit_identity import backfill_owner_identities
        account, opportunity, _, cutoff, event = self.owner_history()
        orphan = f"reused-history-{self.suffix}@example.invalid"
        frappe.db.set_value("CRM Opportunity History", event.name,
            {"from_value": orphan, "from_owner": None, "to_owner": None, "owner_identity_resolved": 0}, update_modified=False)
        self._user(orphan, "CRM Sales")  # Created after this event; cannot be its old owner.
        backfill_owner_identities()
        event.reload()
        self.assertEqual(event.owner_identity_resolved, 1)
        self.assertIsNone(event.from_owner)
        self.assertIsNone(self.replay_owner(account, opportunity, cutoff))
        rename_doc("User", orphan, f"reused-renamed-{self.suffix}@example.invalid", force=True, ignore_permissions=True, rebuild_search=False)
        backfill_owner_identities()
        self.assertIsNone(self.replay_owner(account, opportunity, cutoff))
        self.assertEqual(frappe.db.get_value("CRM Opportunity History", event.name, "from_value"), orphan)

    def test_owner_merge_to_a_newer_user_preserves_proven_identity_and_backfill_is_idempotent(self):
        from frappe.model.rename_doc import rename_doc
        from rayher_crm.services.cockpit_identity import backfill_owner_identities
        account, opportunity, _, cutoff, event = self.owner_history()
        destination = self._user(f"merge-new-{self.suffix}@example.invalid", "CRM Sales")
        self.assertGreater(frappe.db.get_value("User", destination, "creation"), event.at)
        rename_doc("User", self.sales, destination, merge=True, force=True, ignore_permissions=True, rebuild_search=False)
        backfill_owner_identities()
        self.assertEqual(self.replay_owner(account, opportunity, cutoff), destination)
        event.reload()
        self.assertEqual((event.from_value, event.from_owner), (self.sales, destination))
