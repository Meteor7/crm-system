"""Site integration checks. Run after bench migrate on the rehearsal site."""
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import cockpit, cockpit_settings
from rayher_crm.services.cockpit_metrics import build_review
from rayher_crm.tests.test_cockpit_plan import fixture as plan_fixture


class TestCockpitApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")
        self._reset_settings()
        self.sales = "cockpit-sales@example.invalid"
        if not frappe.db.exists("User", self.sales):
            frappe.get_doc({"doctype": "User", "email": self.sales, "first_name": "Cockpit Test",
                            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "CRM Sales"}]}).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        self._reset_settings()
        frappe.set_user(self.previous_user)
        super().tearDown()

    def _reset_settings(self):
        frappe.db.delete("Singles", {"doctype": cockpit_settings.SETTINGS})
        frappe.clear_document_cache(cockpit_settings.SETTINGS, cockpit_settings.SETTINGS)

    def test_booking_date_loader_guards_old_schema(self):
        for has_date in (False, True):
            with self.subTest(has_date=has_date):
                meta = SimpleNamespace(has_field=lambda name: has_date)
                def records(doctype, fields, field, names):
                    if doctype == "CRM Opportunity":
                        return [{"name": "opp"}]
                    if doctype == "CRM Booking":
                        return [{"name": "booking", "source_opportunity": "opp"}]
                    return []
                with patch.object(cockpit.frappe, "get_meta", return_value=meta), patch.object(cockpit, "linked", side_effect=records) as linked:
                    data = cockpit.load_data([{"name": "customer"}], [])
                calls = [call for call in linked.call_args_list if call.args[0] == "CRM Booking"]
                self.assertEqual(data["booking_dates_ready"], has_date)
                self.assertEqual(len(calls), int(has_date))
                self.assertEqual(len(data["bookings"]), int(has_date))
                if has_date:
                    self.assertIn("actual_po_date", calls[0].args[1].split())
                    self.assertIn("source", calls[0].args[1].split())
                    self.assertEqual(calls[0].args[2:], ("source_opportunity", {"opp"}))

    def test_conversion_reads_real_stage_history_and_reuses_individual_annual_target(self):
        from rayher_crm.tests.test_quotation_api import TestQuotationApi
        from rayher_crm.services.opportunity_stages import MILESTONE_STAGES

        # Real service-created opportunities and real immutable history rows.
        opportunities = [TestQuotationApi._opportunity(self) for _ in range(2)]
        frappe.set_user("Administrator")
        for opportunity in opportunities:
            for stage in MILESTONE_STAGES:
                if stage == "internal_validation":
                    continue
                frappe.get_doc({"doctype": "CRM Opportunity Stage History", "opportunity": opportunity["id"],
                                "to_stage": stage, "source": "migration", "event": "migration", "actor": self.sales,
                                "recorded_at": "2029-06-01 12:00:00", "reached_at": "2029-06-01 12:00:00",
                                "reached_at_basis": "evidence"}).insert(ignore_permissions=True)
        config = {"crm_cockpit_history_complete_from": {"stage": "2028-01-01", "fields": "2028-01-01"},
                  "crm_cockpit_conversion_threshold": 44.5}
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 1, 15, 12)), patch.dict(frappe.conf, config):
            cockpit.save_target({"sales": self.sales, "metric": "orders", "period": "year", "anchor": "2030-01-01", "value": "400000"})
            query = {"period": "week", "anchor": "2030-01-15", "sales": self.sales}
            result = cockpit.get_review(query)
            self.assertTrue(result["conversions"]["complete"])
            self.assertEqual(result["conversions"]["thresholdPercent"], 44.5)
            self.assertEqual(result["conversions"]["items"][-1]["rate"]["value"], "100.00")
            self.assertEqual(result["pipelineCoverage"]["openPipeline"]["value"], "200000.00")
            self.assertEqual(result["pipelineCoverage"]["ratio"]["value"], "0.50")
            self.assertNotIn("_details", result)
            # Stage 6 without PO: 30 days unless the site sets a whole number of days from 1 to 365.
            self.assertEqual(result["stage6NoPo"], {"thresholdDays": 30})
            for configured, expected in ((45, 45), ("0", 30), (1000, 30), ("x", 30), (7.5, 30)):
                with self.subTest(configured=configured), patch.dict(frappe.conf, {"crm_cockpit_stage6_no_po_days": configured}):
                    self.assertEqual(cockpit.get_review(query)["stage6NoPo"]["thresholdDays"], expected)
            warnings = cockpit.get_warnings(query)
            self.assertEqual(warnings["stage6NoPo"], {"thresholdDays": 30})
            self.assertIsInstance(warnings["stage6NoPoItems"], list)
            self.assertIn("stage6_no_po", [w["key"] for w in warnings["warnings"]])
            first = cockpit.get_details({**query, "metric": "reached_po_received", "pageSize": 1})
            second = cockpit.get_details({**query, "metric": "reached_po_received", "pageSize": 1, "page": 2})
            self.assertEqual((first["total"], len(first["items"]), second["page"]), (2, 1, 2))
            self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
            self.assertEqual(cockpit.get_review({**query, "market": "Frontend"})["pipelineCoverage"]["ratio"]["state"], "not_applicable")
            with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {}}):
                self.assertEqual(cockpit.get_review(query)["conversions"]["items"][0]["rate"]["state"], "insufficient")
            frappe.set_user(self.sales)
            with self.assertRaises(CrmApiException) as denied:
                cockpit.get_details({**query, "metric": "reached_po_received"})
            self.assertEqual(denied.exception.code, "PERMISSION_DENIED")

    def test_cny_loader_guards_new_column_independently_of_booking_dates(self):
        for has_cny in (False, True):
            with self.subTest(has_cny=has_cny):
                def meta(doctype):
                    return SimpleNamespace(has_field=lambda field: doctype == "CRM Opportunity" and field == "amount_cny" and has_cny)
                with patch.object(cockpit.frappe, "get_meta", side_effect=meta), patch.object(cockpit, "linked", return_value=[]) as linked:
                    data = cockpit.load_data([{"name": "customer"}], [])
                call = next(call for call in linked.call_args_list if call.args[0] == "CRM Opportunity")
                self.assertEqual("amount_cny" in call.args[1].split(), has_cny)
                self.assertEqual(data["cny_amount_ready"], has_cny)
                self.assertFalse(data["booking_dates_ready"])

    def test_booking_cny_loader_reads_amount_and_currency_and_guards_the_new_column(self):
        for has_cny in (False, True):
            with self.subTest(has_cny=has_cny):
                def meta(doctype):
                    return SimpleNamespace(has_field=lambda field: doctype == "CRM Booking" and (field == "actual_po_date" or (field == "amount_cny" and has_cny)))
                with patch.object(cockpit.frappe, "get_meta", side_effect=meta), patch.object(cockpit, "linked", return_value=[]) as linked:
                    cockpit.load_data([{"name": "customer"}], [])
                fields = next(call for call in linked.call_args_list if call.args[0] == "CRM Booking").args[1].split()
                self.assertLessEqual({"amount", "currency", "actual_po_date"}, set(fields))
                self.assertEqual("amount_cny" in fields, has_cny)

    def test_all_read_and_write_paths_reject_non_managers_before_loading_data(self):
        for role in ("Sales", "Engineer"):
            with patch.object(cockpit, "resolve_crm_role", return_value=role), patch.object(cockpit, "options") as load:
                for action in (lambda: cockpit.get_review({}), lambda: cockpit.get_details({"metric": "lost"}),
                               lambda: cockpit.get_warnings({}),
                               lambda: cockpit.get_plan({"period": "week", "anchor": "2026-09-21"}),
                               lambda: cockpit.get_plan_details({"period": "week", "anchor": "2026-09-21", "metric": "all"}),
                               lambda: cockpit.save_target({})):
                    with self.assertRaises(CrmApiException) as error:
                        action()
                    self.assertEqual(error.exception.code, "PERMISSION_DENIED")
                load.assert_not_called()

    def test_plan_reads_future_periods_and_validates_its_query(self):
        with patch.object(cockpit, "resolve_crm_role", return_value="Manager"):
            plan = cockpit.get_plan({"period": "year", "anchor": "2031-05-05"})
            self.assertEqual(plan["period"], {"kind": "year", "start": "2031-01-01", "end": "2031-12-31",
                                              "previousAnchor": "2030-01-01", "nextAnchor": "2032-01-01"})
            self.assertEqual(set(plan["summary"]), {"visits", "tests", "actions", "po"})
            self.assertEqual(set(plan["filters"]), {"sales", "markets", "regions", "regionParents", "regionReady", "equipment"})
            # The equipment catalog of the Opportunities board; presets are always offered.
            self.assertIn("Kibo", plan["filters"]["equipment"])
            with patch.object(cockpit, "list_equipment_types", return_value=["Kibo", "-"]):
                self.assertEqual(cockpit.options()[2]["equipment"], ["Kibo"])
            self.assertIsNotNone(cockpit.get_plan({"period": "week", "anchor": "2026-09-21", "equipment": "Kibo"})["equipmentUnclassified"])
            self.assertIn("equipment", cockpit.get_review({"period": "week", "equipment": "Kibo"})["filters"])
            self.assertNotIn("_details", plan)
            details = cockpit.get_plan_details({"period": "year", "anchor": "2031-05-05", "metric": "all"})
            self.assertEqual((details["page"], details["pageSize"], details["asOf"][-1]), (1, 50, "Z"))
            for query in ({"period": "week"}, {"period": "week", "anchor": "next"}, {"period": "day", "anchor": "2026-09-21"},
                          {"period": "week", "anchor": "2026-09-21", "sales": "nobody@example.invalid"},
                          {"period": "week", "anchor": "2026-09-21", "market": "No such market"},
                          {"period": "week", "anchor": "2026-09-21", "equipment": "No such equipment"}):
                with self.subTest(query=query), self.assertRaises(CrmApiException) as error:
                    cockpit.get_plan(query)
                self.assertEqual(error.exception.code, "VALIDATION_ERROR")
            with self.assertRaises(CrmApiException) as error:
                cockpit.get_plan_details({"period": "week", "anchor": "2026-09-21", "metric": "leads"})
            self.assertEqual(error.exception.code, "VALIDATION_ERROR")

    def test_plan_resolves_engineer_assignees_in_bulk_without_making_them_sales(self):
        engineer = "cockpit-engineer@example.invalid"
        if not frappe.db.exists("User", engineer):
            frappe.get_doc({"doctype": "User", "email": engineer, "first_name": "Plan Engineer",
                            "enabled": 1, "send_welcome_email": 0,
                            "roles": [{"role": "CRM Engineer"}]}).insert(ignore_permissions=True)
        engineer_name = frappe.db.get_value("User", engineer, "full_name")
        data = plan_fixture()
        data["opportunities"][0]["opportunity_owner"] = self.sales
        for action in data["actions"]:
            action["action_owner"] = engineer if action["action_owner"] == "engineer" else self.sales
        business_rows = {
            "Customer": data["customers"], "CRM Opportunity": data["opportunities"],
            "CRM Visit": [], "CRM Demo Request": [], "CRM Evaluation": [],
            "CRM Opportunity Action": [row for row in data["actions"] if row["status"] == "Open" and not row["archived"]],
        }
        real_read = cockpit.read

        def records(doctype, fields, filters=None):
            if doctype in business_rows:
                return business_rows[doctype]
            # User names and CRM Sales membership come from the actual site.
            return real_read(doctype, fields, filters)

        query = {"period": "week", "anchor": "2026-09-23", "sales": self.sales, "metric": "actions", "pageSize": 1}
        with patch.object(cockpit, "resolve_crm_role", return_value="Manager"), patch.object(cockpit, "read", side_effect=records) as read:
            details = cockpit.get_plan_details(query)
            self.assertEqual((details["total"], len(details["items"])), (2, 1))
            row = details["items"][0]
            self.assertEqual((row["actionOwner"], row["actionOwnerName"], row["salesOwner"]),
                             (engineer, engineer_name, self.sales))
            user_calls = [call for call in read.call_args_list if call.args[0] == "User"]
            assignee_calls = [call for call in user_calls if engineer in call.args[2]["name"][1]]
            self.assertEqual(len(user_calls), 2)  # Sales options and one assignee batch.
            self.assertEqual(len(assignee_calls), 1)
            self.assertEqual(set(assignee_calls[0].args[2]["name"][1]), {engineer, self.sales})
            plan = cockpit.get_plan(query)
            self.assertNotIn(engineer, [person["id"] for person in plan["filters"]["sales"]])
            self.assertNotIn(engineer, [person["id"] for person in plan["sales"]])
            with self.assertRaises(CrmApiException) as error:
                cockpit.get_plan({**query, "sales": engineer})
            self.assertEqual(error.exception.code, "VALIDATION_ERROR")

    def test_empty_plan_does_not_query_user_names(self):
        meta = SimpleNamespace(has_field=lambda name: True)
        with patch.object(cockpit.frappe, "get_meta", return_value=meta), patch.object(cockpit, "read") as read:
            data = cockpit.load_plan_data([], [])
        self.assertEqual(data["actions"], [])
        self.assertEqual(data["action_people"], [])
        read.assert_not_called()

    def test_individual_targets_are_versioned_and_defaults_do_not_overwrite_past(self):
        today = frappe.utils.now_datetime().date()
        next_monday = today + timedelta(days=7 - today.weekday())
        payload = {"sales": self.sales, "metric": "visits", "period": "weekly_default", "anchor": str(next_monday), "value": "8"}
        saved = cockpit.save_target(payload)
        with self.assertRaises(CrmApiException) as conflict:
            cockpit.save_target({**payload, "value": "9"})
        self.assertEqual(conflict.exception.code, "CONFLICT")
        updated = cockpit.save_target({**payload, "value": "9"}, saved["modified"])
        self.assertEqual(updated["value"], "9.00")
        with self.assertRaises(CrmApiException) as stale:
            cockpit.save_target({**payload, "value": "10"}, saved["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        with self.assertRaises(CrmApiException):
            cockpit.save_target({**payload, "anchor": str(next_monday - timedelta(days=7))})
        with self.assertRaises(CrmApiException):
            cockpit.save_target({**payload, "sales": "", "value": "8"})
        with self.assertRaises(CrmApiException):
            cockpit.save_target({**payload, "value": "1.5"})

    def test_series_fraction_matches_the_elapsed_fraction_on_the_as_of_day(self):
        result = {"period": {"start": "2026-09-07", "kind": "week", "asOf": "2026-09-13T15:59:59Z"}, "activities": [], "orders": {}}
        with patch.object(cockpit, "read", return_value=[]):
            cockpit.attach_targets(result, {"sales": "", "market": "", "region": ""})
        data = {key: [] for key in ("people", "history", "stages", "actions", "probabilities", "visits", "leads", "requests", "evaluations", "tests", "quotes", "versions")}
        data["customers"] = [{"name": "c", "customer_name": "Customer", "custom_crm_region": "", "custom_crm_segment": ""}]
        data["opportunities"] = [{"name": "opp", "creation": "2026-01-01", "title": "Opportunity", "account": "c", "opportunity_owner": "alice", "stage": "demo_done", "amount": "1", "currency": "CNY"}]
        data["bookings"] = [{"name": "b", "source": "Opportunity", "source_opportunity": "opp", "status": "Confirmed", "actual_po_date": "2026-09-13", "currency": "CNY", "amount": "1"}]
        data["booking_dates_ready"] = True
        review = build_review(data, {"period": "week", "anchor": "2026-09-07"}, datetime(2026, 9, 16, 12), {})
        self.assertEqual(review["orders"]["series"][-1]["fraction"], result["orders"]["elapsedFraction"])

    def test_targets_are_not_summed_or_allocated_to_regions(self):
        row = {"name": "target", "sales_owner": self.sales, "metric": "visits", "period": "week", "anchor": "2026-09-07", "target_value": "0", "modified": "2026-09-01 12:00:00"}
        def result():
            return {"period": {"start": "2026-09-07", "kind": "week", "asOf": "2026-09-13T15:59:59Z"}, "activities": [{"key": "visits"}], "orders": {}}
        with patch.object(cockpit, "read", return_value=[row]):
            own = result(); cockpit.attach_targets(own, {"sales": self.sales, "market": "", "region": ""})
            self.assertEqual(own["activities"][0]["target"]["value"], "0")
            team = result(); cockpit.attach_targets(team, {"sales": "", "market": "", "region": ""})
            self.assertEqual(team["activities"][0]["target"]["state"], "not_applicable")
            regional = result(); cockpit.attach_targets(regional, {"sales": self.sales, "market": "", "region": "East China"})
            self.assertEqual(regional["activities"][0]["target"]["state"], "not_applicable")
