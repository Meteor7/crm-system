"""Site integration checks for the Opportunities board. Run on the dedicated test site."""
from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1 import cockpit as cockpit_api
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import opportunity_board
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import create_opportunity_action, create_strategy_opportunity
from rayher_crm.services.sites import create_site

SAVED = opportunity_board.SAVED_QUERY
COLUMNS = ["customerName", "stage", "stageChangedAt", "amount"]


class TestOpportunityBoardApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-board-sales@example.invalid", "CRM Sales", "Board Sales")
        self.other_sales = self._user("crm-board-other@example.invalid", "CRM Sales", "Board Other")
        self.manager = self._user("crm-board-manager@example.invalid", "CRM Manager", "Board Manager")
        self.engineer = self._user("crm-board-engineer@example.invalid", "CRM Engineer", "Board Engineer")
        self.token = frappe.generate_hash(length=8)
        self.mine = self._opportunity(self.sales, "Mine", "Board Inspection", "100.00")
        self.theirs = self._opportunity(self.other_sales, "Theirs", "Board Metrology", "250.50")
        self.unpriced = self._opportunity(self.other_sales, "Unpriced", "Board Metrology", "80.00")
        now = frappe.utils.now_datetime()
        # 21 Shanghai days is not yet stale, 22 is; an unknown change time stays unknown.
        frappe.db.set_value("CRM Opportunity", self.mine, "stage_changed_at", now - timedelta(days=21), update_modified=False)
        frappe.db.set_value("CRM Opportunity", self.theirs, "stage_changed_at", now - timedelta(days=22), update_modified=False)
        frappe.db.set_value("CRM Opportunity", self.unpriced, {"stage_changed_at": None, "amount_cny": 0}, update_modified=False)
        frappe.set_user(self.sales)
        create_opportunity_action(self.mine, {"title": "Later", "due": "2031-01-02", "status": "Open"})
        create_opportunity_action(self.mine, {"title": "First", "due": "2031-01-01", "status": "Open"})
        create_opportunity_action(self.mine, {"title": "Closed", "due": "2030-01-01", "status": "Done"})
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.original_user)
        # Each test starts from the same three Opportunities; the class-level rollback alone would stack them.
        frappe.db.rollback()
        super().tearDown()

    def _user(self, email, role, first_name):
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": first_name, "enabled": 1,
                            "send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
        return email

    def _opportunity(self, owner, suffix, tool_type, amount):
        frappe.set_user(owner)
        account = create_account({"name": f"Board {suffix} {self.token}", "shortName": f"{suffix}{self.token}",
                                  "segment": "Frontend", "tier": "A", "city": "上海", "region": "华东", "owner": owner})
        site = create_site(account["id"], {"name": f"{suffix} {self.token} Site", "city": "上海", "type": "Fab",
                                           "process": "Frontend", "status": "量产"})
        created = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": f"Board {suffix}", "owner": owner,
            "amount": amount, "intentScore": 35, "poDate": "2031-12-31", "toolType": tool_type,
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY", "originalAmount": amount,
            "amountCny": amount, "qualificationConfirmed": True, "probabilityLevel": "pipeline",
        })
        frappe.set_user("Administrator")
        return created["id"]

    def _as(self, user, action):
        frappe.set_user(user)
        try:
            return action()
        finally:
            frappe.set_user("Administrator")

    def _query(self, user, **query):
        data, total, page, size = self._as(user, lambda: opportunity_board.query_opportunities(query))
        return data, total, page, size

    def _error(self, user, action):
        with self.assertRaises(CrmApiException) as caught:
            self._as(user, action)
        return caught.exception

    def test_sales_reads_only_their_own_rows_whatever_the_conditions(self):
        data, total, _page, _size = self._query(self.sales)
        self.assertEqual(([row["id"] for row in data["items"]], total), ([self.mine], 1))
        row = data["items"][0]
        self.assertEqual((row["customerName"], row["region"], row["market"], row["salesId"], row["salesName"]),
                         (f"Board Mine {self.token}", "East China", "Frontend", self.sales, "Board Sales"))
        self.assertEqual((row["stageAgeDays"], row["stageUnchangedOver21Days"], row["amountCny"]), (21, False, "100.00"))
        self.assertEqual((row["nextAction"]["title"], row["nextAction"]["due"]), ("First", "2031-01-01"))
        # OR joins conditions only; it never reaches past the permission scope.
        data, total, _page, _size = self._query(self.sales, match="any", conditions=[
            {"field": "customerName", "operator": "contains", "value": "Theirs"},
            {"field": "equipment", "operator": "in", "value": ["Board Metrology"]},
        ])
        self.assertEqual((data["items"], total, data["summary"]["count"]), ([], 0, 0))
        error = self._error(self.sales, lambda: opportunity_board.query_opportunities({"scope": {"sales": [self.other_sales]}}))
        self.assertEqual((error.code, list(error.field_errors)), ("VALIDATION_ERROR", ["scope.sales"]))
        data, total, _page, _size = self._query(self.engineer)
        self.assertEqual((data["items"], total), ([], 0))

    def test_totals_cover_every_match_on_every_page(self):
        scope = {"sales": [self.sales, self.other_sales]}
        first, total, page, size = self._query(self.manager, scope=scope, pageSize=1,
                                               sort={"field": "amountCny", "direction": "desc"})
        self.assertEqual(([row["id"] for row in first["items"]], total, page, size), ([self.theirs], 3, 1, 1))
        later, _total, _page, _size = self._query(self.manager, scope=scope, page=3, pageSize=1,
                                                  sort={"field": "amountCny", "direction": "desc"})
        self.assertEqual([row["id"] for row in later["items"]], [self.unpriced])
        past, _total, _page, _size = self._query(self.manager, scope=scope, page=9, pageSize=1)
        self.assertEqual(past["items"], [])
        for data in (first, later, past):
            summary = data["summary"]
            self.assertEqual((summary["count"], summary["knownAmountCny"], summary["missingAmountCount"]), (3, "350.50", 1))
            self.assertEqual((summary["stageUnchangedOver21DaysCount"], summary["unknownStageAgeCount"]), (1, 1))
            self.assertEqual([(r["level"], r["count"]) for r in summary["byProbability"]],
                             [("low_probability", 0), ("pipeline", 3), ("upside", 0), ("committed", 0), ("pending", 0)])
        grouped, _total, _page, _size = self._query(self.manager, scope=scope, groupBy="sales", pageSize=1)
        self.assertEqual([(g["key"], g["label"], g["count"], g["knownAmountCny"], g["missingAmountCount"]) for g in grouped["groups"]],
                         [(self.other_sales, "Board Other", 2, "250.50", 1), (self.sales, "Board Sales", 1, "100.00", 0)])
        stale, total, _page, _size = self._query(self.manager, scope=scope, conditions=[
            {"field": "stageAgeDays", "operator": "gt", "value": 21}])
        self.assertEqual(([row["id"] for row in stale["items"]], total), ([self.theirs], 1))
        priced, total, _page, _size = self._query(self.manager, scope=scope, conditions=[
            {"field": "amountCny", "operator": "gte", "value": "0"}])
        self.assertEqual(total, 2)

    def test_an_opportunity_without_an_amount_is_listed_as_missing_never_as_zero(self):
        frappe.set_user(self.sales)
        account = create_account({"name": f"Board Unknown {self.token}", "shortName": f"Unknown{self.token}",
                                  "segment": "Frontend", "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        site = create_site(account["id"], {"name": f"Unknown {self.token} Site", "city": "上海", "type": "Fab",
                                           "process": "Frontend", "status": "量产"})
        unknown = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": "Board Unknown", "owner": self.sales,
            "amount": "", "intentScore": 35, "poDate": "2031-12-31", "toolType": "Board Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "USD", "originalAmount": "",
            "amountCny": "", "qualificationConfirmed": True, "probabilityLevel": "pipeline",
        })["id"]
        data, total, _page, _size = self._query(self.sales)
        row = next(item for item in data["items"] if item["id"] == unknown)
        self.assertEqual((total, row["amount"], row["currency"], row["amountCny"]), (2, "", "USD", None))
        summary = data["summary"]
        self.assertEqual((summary["count"], summary["knownAmountCny"], summary["missingAmountCount"]), (2, "100.00", 1))

    def test_filters_follow_the_callers_scope(self):
        mine = self._as(self.sales, opportunity_board.get_opportunity_filters)
        self.assertEqual(mine["sales"], [{"value": self.sales, "label": "Board Sales"}])
        # Equipment is the shared catalog, like markets: the presets, then custom types in the order added.
        equipment = [option["value"] for option in mine["equipment"]]
        self.assertEqual(equipment[:5], ["Aconca", "Drakens", "Kibo", "Nansi", "Veymont"])
        self.assertLess(equipment.index("Board Inspection"), equipment.index("Board Metrology"))
        self.assertEqual([s["value"] for s in mine["stages"]][:2], ["qualified_opportunity", "demo_done"])
        self.assertEqual([p["value"] for p in mine["probabilityLevels"]],
                         ["low_probability", "pipeline", "upside", "committed", "pending"])
        self.assertIn("Frontend", [m["value"] for m in mine["markets"]])
        managed = self._as(self.manager, opportunity_board.get_opportunity_filters)
        self.assertLessEqual({self.sales, self.other_sales}, {s["value"] for s in managed["sales"]})

    def test_region_queries_need_the_verified_region_migration(self):
        ready = {"sales": [], "markets": ["Frontend"], "regions": ["East China", "South China"], "regionReady": True}
        with patch.object(opportunity_board.cockpit, "options", return_value=([], [], ready)):
            data, total, _page, _size = self._query(self.sales, scope={"regions": ["East China"]}, groupBy="region")
            self.assertEqual((total, data["groups"][0]["key"]), (1, "East China"))
            data, total, _page, _size = self._query(self.sales, scope={"regions": ["South China"]})
            self.assertEqual(total, 0)
        with patch.object(opportunity_board.cockpit, "options", return_value=([], [], {**ready, "regions": [], "regionReady": False})):
            error = self._error(self.sales, lambda: opportunity_board.query_opportunities({"groupBy": "region"}))
            self.assertEqual((error.code, list(error.field_errors)), ("VALIDATION_ERROR", ["groupBy"]))
            filters = self._as(self.sales, opportunity_board.get_opportunity_filters)
            self.assertEqual((filters["regions"], filters["regionReady"]), ([], False))

    def test_saved_queries_belong_to_their_owner_only(self):
        definition = {"scope": {"sales": [self.sales]}, "match": "all", "conditions": [
            {"field": "stage", "operator": "in", "value": ["demo_done"]}], "groupBy": None, "columns": COLUMNS}
        saved = self._as(self.sales, lambda: opportunity_board.save_opportunity_query(None, {"name": " Demo done ", "definition": definition}))
        self.assertEqual((saved["name"], saved["definition"]["columns"], saved["definition"]["sort"]),
                         ("Demo done", COLUMNS, {"field": "stageChangedAt", "direction": "asc"}))
        self.assertRegex(saved["modified"], r"Z$")
        self.assertEqual([item["id"] for item in self._as(self.sales, opportunity_board.list_opportunity_queries)["items"]], [saved["id"]])
        self.assertEqual(self._as(self.other_sales, opportunity_board.list_opportunity_queries)["items"], [])
        other_definition = {**definition, "scope": {}}
        for action in (
            lambda: opportunity_board.save_opportunity_query(saved["id"], {"name": "Taken", "definition": other_definition}, saved["modified"]),
            lambda: opportunity_board.delete_opportunity_query(saved["id"], saved["modified"]),
        ):
            error = self._error(self.other_sales, action)
            self.assertEqual(error.code, "NOT_FOUND")
        for user in (self.sales, self.other_sales, self.manager):
            self.assertFalse(frappe.has_permission(SAVED, "read", user=user))
            frappe.set_user(user)
            try:
                with self.assertRaises(frappe.PermissionError):
                    frappe.get_list(SAVED, fields=["name", "definition"])
            finally:
                frappe.set_user("Administrator")

        cases = [
            (lambda: opportunity_board.save_opportunity_query(saved["id"], {"name": "Renamed", "definition": definition}), "VALIDATION_ERROR"),
            (lambda: opportunity_board.save_opportunity_query(None, {"name": "demo DONE", "definition": definition}), "CONFLICT"),
            (lambda: opportunity_board.save_opportunity_query(None, {"name": "New", "definition": definition}, saved["modified"]), "VALIDATION_ERROR"),
            (lambda: opportunity_board.save_opportunity_query(None, {"name": "New", "definition": {**definition, "page": 2}}), "VALIDATION_ERROR"),
            (lambda: opportunity_board.save_opportunity_query(None, {"name": "Bad\nname", "definition": definition}), "VALIDATION_ERROR"),
            (lambda: opportunity_board.save_opportunity_query(None, {"name": "New", "definition": definition, "shared": True}), "VALIDATION_ERROR"),
        ]
        for action, code in cases:
            self.assertEqual(self._error(self.sales, action).code, code)
        updated = self._as(self.sales, lambda: opportunity_board.save_opportunity_query(
            saved["id"], {"name": "Renamed", "definition": {**definition, "groupBy": "stage"}}, saved["modified"]))
        self.assertEqual((updated["id"], updated["name"], updated["definition"]["groupBy"]), (saved["id"], "Renamed", "stage"))
        stale = self._error(self.sales, lambda: opportunity_board.delete_opportunity_query(saved["id"], saved["modified"]))
        self.assertEqual(stale.code, "VERSION_CONFLICT")
        deleted = self._as(self.sales, lambda: opportunity_board.delete_opportunity_query(saved["id"], updated["modified"]))
        self.assertEqual(deleted, {"id": saved["id"], "status": "Deleted"})
        self.assertFalse(frappe.db.exists(SAVED, saved["id"]))

    def test_saved_names_are_kept_as_typed_and_ids_match_their_stored_spelling(self):
        definition = {"columns": COLUMNS}
        typed = "停留 > 21 天 <b>S6</b>"
        saved = self._as(self.sales, lambda: opportunity_board.save_opportunity_query(None, {"name": typed, "definition": definition}))
        self.assertEqual(saved["name"], typed)
        longest = self._as(self.sales, lambda: opportunity_board.save_opportunity_query(None, {"name": "<x>" * 26, "definition": definition}))
        self.assertEqual(longest["name"], "<x>" * 26)
        # A differently cased id still finds the same row; saving it unrenamed must not look like a duplicate.
        updated = self._as(self.sales, lambda: opportunity_board.save_opportunity_query(
            saved["id"].upper(), {"name": typed, "definition": {**definition, "groupBy": "stage"}}, saved["modified"]))
        self.assertEqual((updated["id"], updated["definition"]["groupBy"]), (saved["id"], "stage"))

    def test_out_of_range_input_is_a_validation_error_not_a_crash(self):
        saved = self._as(self.sales, lambda: opportunity_board.save_opportunity_query(None, {"name": "Mine", "definition": {"columns": COLUMNS}}))
        for action in (
            lambda: opportunity_board.query_opportunities({"page": float("inf")}),
            lambda: opportunity_board.query_opportunities({"pageSize": float("-inf")}),
            lambda: opportunity_board.delete_opportunity_query(saved["id"], "9999-12-31T23:59:59-14:00"),
            lambda: opportunity_board.delete_opportunity_query(saved["id"], "0001-01-01T00:00:00+14:00"),
            lambda: opportunity_board.delete_opportunity_query(["not", "an", "id"], saved["modified"]),
        ):
            self.assertEqual(self._error(self.sales, action).code, "VALIDATION_ERROR")
        frappe.set_user(self.sales)
        try:
            for text in ("[" * 100000 + "]" * 100000, json.dumps({"page": 1}) + "x"):
                response = cockpit_api.query_opportunities(input=text)
                self.assertEqual((response["error"]["code"], frappe.local.response["http_status_code"]), ("VALIDATION_ERROR", 422))
        finally:
            frappe.set_user("Administrator")

    def test_endpoints_return_the_standard_envelope(self):
        frappe.set_user(self.sales)
        response = cockpit_api.query_opportunities(input=json.dumps({"page": 1, "pageSize": 25}))
        self.assertEqual((response["meta"]["page"], response["meta"]["pageSize"], response["meta"]["total"]), (1, 25, 1))
        self.assertEqual(set(response["data"]), {"items", "asOf", "summary", "groups"})
        self.assertEqual(response["warnings"], [])
        for bad in ("{not json", json.dumps({"conditions": [{"field": "stage", "operator": "in", "value": ["won"]}]}), None):
            response = cockpit_api.query_opportunities(input=bad)
            self.assertEqual((response["error"]["code"], frappe.local.response["http_status_code"]), ("VALIDATION_ERROR", 422))
        saved = cockpit_api.save_opportunity_query(input=json.dumps({"name": "Mine", "definition": {"columns": COLUMNS}}))
        self.assertEqual(saved["data"]["name"], "Mine")
        listed = cockpit_api.list_opportunity_queries()
        self.assertEqual([item["id"] for item in listed["data"]["items"]], [saved["data"]["id"]])
        deleted = cockpit_api.delete_opportunity_query(id=saved["data"]["id"], expectedModified=saved["data"]["modified"])
        self.assertEqual(deleted["data"]["status"], "Deleted")
        self.assertIn("regionReady", cockpit_api.get_opportunity_filters()["data"])
        frappe.set_user("Administrator")

    def test_legacy_rows_the_database_allows_do_not_break_the_board(self):
        # A spelling from before the catalog, a row without an owner, and an unknown probability level.
        frappe.db.set_value("CRM Opportunity", self.theirs, "tool_type", "board METROLOGY", update_modified=False)
        frappe.db.set_value("CRM Opportunity", self.unpriced, {"opportunity_owner": None, "probability_level": "high"},
                            update_modified=False)
        data, total, _page, _size = self._query(self.manager, scope={"equipment": ["Board Metrology"]},
                                                sort={"field": "sales", "direction": "asc"})
        self.assertEqual(total, 2)
        rows = {row["id"]: row for row in data["items"]}
        self.assertEqual(rows[self.theirs]["equipment"], "Board Metrology")
        self.assertEqual((rows[self.unpriced]["salesId"], rows[self.unpriced]["probabilityLevel"]), ("", None))
        filters = self._as(self.manager, opportunity_board.get_opportunity_filters)
        self.assertNotIn("", [option["value"] for option in filters["sales"]])
        self.assertEqual([option["value"] for option in filters["equipment"]].count("Board Metrology"), 1)
