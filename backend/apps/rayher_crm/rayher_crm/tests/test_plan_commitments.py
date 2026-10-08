from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import cockpit, plan_commitments as service
from rayher_crm.tests.test_opportunity_relations import TestOpportunityRelations


class TestPlanCommitments(FrappeTestCase):
    _user = TestOpportunityRelations._user

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("commitment-sales@example.invalid", "CRM Sales")
        self.other = self._user("commitment-other@example.invalid", "CRM Sales")
        self.manager = self._user("commitment-manager@example.invalid", "CRM Manager")
        frappe.set_user(self.manager)

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def payload(self, **values):
        return {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "5", "note": "Meeting promise", **values}

    def result(self):
        ready = lambda value: {"state": "ready", "value": value}
        return {"period": {"kind": "week", "start": "2030-09-02"}, "filters": {"sales": [{"id": self.sales, "name": "Sales"}]},
                "sales": [{"id": self.sales, "visits": ready(2)}], "summary": {"visits": ready(2)}, "_details": {}}

    def test_plan_materializes_only_its_activity_period_without_annual_orders(self):
        base = {"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "0"}
        selected = cockpit.save_target(base)
        cockpit.save_target({**base, "anchor": "2030-08-26", "value": "7"})
        cockpit.save_target({**base, "metric": "orders", "period": "year", "anchor": "2030-01-01", "value": "1000000"})
        with patch.object(cockpit, "target_dto", wraps=cockpit.target_dto) as serialized:
            result = self.result()
            service.attach(result, {"sales": self.sales})
        own = {call.args[0]["name"] for call in serialized.call_args_list if call.args[0]["sales_owner"] == self.sales}
        self.assertEqual(own, {selected["id"]})
        visit = result["commitments"]["people"][0]["activities"][0]
        self.assertEqual(visit["target"]["value"], "0.00")

    def test_permissions_cas_zero_and_native_audit(self):
        saved = service.save(self.payload())
        changed = service.save(self.payload(value="0", note="Cancelled travel"), saved["modified"])
        self.assertEqual(changed["value"], "0")
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": service.DOCTYPE, "docname": saved["id"]}))
        with self.assertRaises(CrmApiException) as stale:
            service.save(self.payload(), saved["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        doc = frappe.get_doc(service.DOCTYPE, saved["id"])
        self.assertTrue(frappe.has_permission(service.DOCTYPE, "read", doc=doc))
        self.assertFalse(frappe.has_permission(service.DOCTYPE, "write", doc=doc))
        frappe.set_user(self.sales)
        self.assertFalse(frappe.has_permission(service.DOCTYPE, "read", doc=doc))
        with self.assertRaises(CrmApiException) as denied:
            service.save(self.payload(), changed["modified"])
        self.assertEqual(denied.exception.code, "PERMISSION_DENIED")

    def test_case_variant_sales_identity_cannot_bypass_cas_or_create_duplicates(self):
        saved = service.save(self.payload())
        with self.assertRaises(CrmApiException) as duplicate:
            service.save(self.payload(sales=self.sales.upper(), value="9"))
        self.assertEqual(duplicate.exception.code, "VERSION_CONFLICT")
        changed = service.save(self.payload(sales=self.sales.upper(), value="9"), saved["modified"])
        self.assertEqual((changed["id"], changed["sales"], changed["value"]), (saved["id"], self.sales, "9"))
        self.assertEqual(frappe.db.count(service.DOCTYPE, {"sales_owner": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02"}), 1)

    def test_user_rename_preserves_commitment_identity_and_audit(self):
        from frappe.model.rename_doc import rename_doc
        saved = service.save(self.payload())
        renamed = "renamed-commitment-sales@example.invalid"
        frappe.set_user("Administrator")
        rename_doc("User", self.sales, renamed, force=True, ignore_permissions=True, rebuild_search=False)
        frappe.set_user(self.manager)
        current = frappe.db.get_value(service.DOCTYPE, saved["id"], "modified")
        with self.assertRaises(CrmApiException) as duplicate:
            service.save(self.payload(sales=renamed))
        self.assertEqual(duplicate.exception.code, "VERSION_CONFLICT")
        changed = service.save(self.payload(sales=renamed, value="8"), service.to_iso_timestamp(current))
        self.assertEqual((changed["id"], changed["sales"], changed["value"]), (saved["id"], renamed, "8"))
        self.assertEqual(frappe.db.count(service.DOCTYPE, {"sales_owner": renamed, "metric": "visits", "period": "week", "anchor": "2030-09-02"}), 1)
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": service.DOCTYPE, "docname": saved["id"]}))

        frappe.set_user("Administrator")
        self._user(self.sales, "CRM Sales")
        frappe.set_user(self.manager)
        fresh = service.save(self.payload())
        self.assertNotEqual(fresh["id"], saved["id"])
        self.assertEqual(fresh["sales"], self.sales)

    def test_legacy_owner_casing_loads_record_and_audit_without_rewriting_history(self):
        saved = service.save(self.payload())
        saved = service.save(self.payload(value="7", note="Preserved meeting note"), saved["modified"])
        frappe.db.set_value(service.DOCTYPE, saved["id"], "sales_owner", self.sales.upper(), update_modified=False)
        for query in ({"sales": self.sales}, {}):
            with self.subTest(query=query), patch.object(cockpit, "targetable_sales", return_value={self.sales}):
                result = self.result()
                service.attach(result, query)
                self.assertEqual([row["id"] for row in result["commitments"]["people"]], [self.sales])
                commitment = result["commitments"]["people"][0]["activities"][0]["commitment"]
                self.assertEqual((commitment["value"], commitment["record"]["id"], commitment["record"]["sales"]),
                                 ("7", saved["id"], self.sales))
                self.assertEqual(result["commitments"]["team"][0]["commitment"]["value"], "7.00")
                self.assertTrue(result["commitments"]["history"][saved["id"]])
        self.assertEqual(frappe.db.get_value(service.DOCTYPE, saved["id"], "sales_owner"), self.sales.upper())
        self.assertEqual(service.to_iso_timestamp(frappe.db.get_value(service.DOCTYPE, saved["id"], "modified")), saved["modified"])
        updated = service.save(self.payload(value="8"), commitment["record"]["modified"])
        self.assertEqual((updated["id"], updated["sales"], updated["value"]), (saved["id"], self.sales, "8"))

    def test_whole_period_values_and_current_sales_eligibility(self):
        for changes in ({"value": "-1"}, {"value": "1.1"}, {"value": True}, {"value": "1000000000"}, {"anchor": "2030-09-03"},
                        {"metric": "orders"}, {"period": []}, {"sales": self.manager}, {"note": "x" * 1001}, {"id": "client-id"}):
            with self.subTest(changes=changes), self.assertRaises(CrmApiException):
                service.save(self.payload(**changes))
        frappe.db.set_value("User", self.sales, "enabled", 0)
        with self.assertRaises(CrmApiException):
            service.save(self.payload())

    def test_stale_sales_identity_requires_plan_reload(self):
        for owner in ("missing-commitment@example.invalid", self.manager):
            with self.subTest(owner=owner), self.assertRaises(CrmApiException) as error:
                service.save(self.payload(sales=owner))
            self.assertEqual(error.exception.code, "VERSION_CONFLICT")
        frappe.db.set_value("User", self.sales, "enabled", 0)
        with self.assertRaises(CrmApiException) as disabled:
            service.save(self.payload())
        self.assertEqual(disabled.exception.code, "VERSION_CONFLICT")

    def test_legacy_duplicates_preserve_both_commitments_and_reject_ambiguous_updates(self):
        first = service.save(self.payload())
        second = service.save(self.payload(sales=self.other, value="8"))
        first = service.save(self.payload(value="6", note="First preserved note"), first["modified"])
        second = service.save(self.payload(sales=self.other, value="9", note="Second preserved note"), second["modified"])
        # Existing duplicates remain inspectable; new native merges now reject
        # this collision before rewriting either Link or touching the audit.
        frappe.db.set_value(service.DOCTYPE, first["id"], "sales_owner", self.other.upper(), update_modified=False)
        result = self.result()
        service.attach(result, {"sales": self.other})
        commitment = result["commitments"]["people"][0]["activities"][0]["commitment"]
        self.assertEqual((commitment["state"], commitment["reason"]), ("insufficient", "duplicate_targets"))
        self.assertIsNone(commitment["record"])
        self.assertEqual({row["id"]: (row["value"], row["note"]) for row in commitment["conflicts"]},
                         {first["id"]: ("6", "First preserved note"), second["id"]: ("9", "Second preserved note")})
        for original in (first, second):
            self.assertTrue(result["commitments"]["history"][original["id"]])
        for original in (first, second):
            with self.assertRaises(CrmApiException) as conflict:
                service.save(self.payload(sales=self.other, value="9"), original["modified"])
            self.assertEqual(conflict.exception.code, "VERSION_CONFLICT")
            self.assertEqual(str(frappe.db.get_value(service.DOCTYPE, original["id"], "commitment_value")), original["value"])
        self.assertEqual(frappe.db.count(service.DOCTYPE, {"sales_owner": self.other, "metric": "visits", "period": "week", "anchor": "2030-09-02"}), 2)
        scoped = self.result()
        service.attach(scoped, {"sales": self.other, "market": "Power"})
        self.assertNotIn("conflicts", scoped["commitments"]["people"][0]["activities"][0]["commitment"])
        self.assertEqual(scoped["commitments"]["history"], {})

    def test_batched_history_caps_each_visible_record_and_excludes_other_scopes(self):
        first = service.save(self.payload())
        second = service.save(self.payload(metric="events"))
        hidden = service.save(self.payload(sales=self.other))
        for saved in (first, second, hidden):
            for index in range(22):
                frappe.get_doc({"doctype": "Version", "ref_doctype": service.DOCTYPE, "docname": saved["id"],
                                "data": frappe.as_json({"changed": [["note", str(index), str(index + 1)]]})}).insert(ignore_permissions=True)
        result = self.result()
        with patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
            service.attach(result, {"sales": self.sales})
        history_queries = [call for call in sql.call_args_list if "ROW_NUMBER()" in str(call.args[0])]
        self.assertEqual(len(history_queries), 1)
        histories = result["commitments"]["history"]
        self.assertEqual(set(histories), {first["id"], second["id"]})
        for saved in (first, second):
            expected = frappe.get_all("Version", filters={"ref_doctype": service.DOCTYPE, "docname": saved["id"]},
                                      order_by="creation desc, name", pluck="name", limit_page_length=20)
            self.assertEqual([entry["id"] for entry in histories[saved["id"]]], expected)
            self.assertEqual(len(histories[saved["id"]]), 20)
        scoped = self.result()
        with patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
            service.attach(scoped, {"sales": self.sales, "equipment": "Inspection"})
        self.assertFalse(any("ROW_NUMBER()" in str(call.args[0]) for call in sql.call_args_list))

    def test_read_comparison_keeps_missing_and_scope_units_and_periods_distinct(self):
        saved = service.save(self.payload(value="0"))
        target = cockpit.save_target({"sales": self.sales, "metric": "visits", "period": "week", "anchor": "2030-09-02", "value": "6"})
        frappe.db.set_value("CRM Cockpit Target", target["id"], "sales_owner", self.sales.upper(), update_modified=False)
        result = self.result()
        with patch.object(cockpit, "targetable_sales", return_value={self.sales, self.other}):
            service.attach(result, {})
        mine = next(row for row in result["commitments"]["people"] if row["id"] == self.sales)["activities"][0]
        self.assertEqual((mine["scheduled"]["value"], mine["commitment"]["value"], mine["target"]["value"]), (2, "0", "6.00"))
        team = result["commitments"]["team"][0]
        self.assertEqual(team["commitment"]["state"], "insufficient")
        self.assertIn(self.other, team["commitment"]["missing"])
        self.assertNotIn(self.sales, team["target"]["missing"])
        monthly = self.result()
        monthly["period"] = {"kind": "month", "start": "2030-09-01"}
        service.attach(monthly, {"sales": self.sales})
        row = monthly["commitments"]["people"][0]["activities"][0]
        self.assertEqual((row["target"]["state"], row["commitment"]["state"]), ("not_set", "not_set"))
        scoped = self.result()
        service.attach(scoped, {"sales": self.sales, "equipment": "Inspection"})
        self.assertFalse(scoped["commitments"]["allocated"])
        self.assertFalse(scoped["commitments"]["people"][0]["canEdit"])
        self.assertEqual(scoped["commitments"]["people"][0]["activities"][0]["commitment"]["state"], "not_applicable")
        self.assertEqual(scoped["commitments"]["history"], {})
        service.save(self.payload(value="2"), saved["modified"])
        service.attach(result, {"sales": self.sales})
        self.assertTrue(result["commitments"]["history"][saved["id"]])

    def test_equipment_details_filter_before_pagination_and_reject_unknown_groups(self):
        result = {"equipmentGroups": [{"id": "unclassified"}, {"id": "equipment:inspection"}], "asOf": "2030-09-02",
                  "_details": {"scheduled_activities": [{"id": "other", "equipmentGroup": "equipment:inspection"},
                                                       {"id": "one", "equipmentGroup": "unclassified"}, {"id": "two", "equipmentGroup": "unclassified"}]}}
        with patch.object(cockpit, "calculate_plan", return_value=result):
            output = cockpit.get_plan_details({"metric": "scheduled_activities", "equipmentGroup": "unclassified", "pageSize": 1, "page": 2})
            self.assertEqual((output["total"], output["items"][0]["id"]), (2, "two"))
            with self.assertRaises(CrmApiException):
                cockpit.get_plan_details({"metric": "scheduled_activities", "equipmentGroup": "missing"})
