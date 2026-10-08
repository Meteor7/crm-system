"""Three real Manager writes must not cycle through Series, User and catalogue."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services import cockpit, territory_admin
from rayher_crm.tests import test_opportunity_relations as fixtures


class TestTargetAssignmentConcurrency(FrappeTestCase):
    _user = fixtures.TestOpportunityRelations._user

    def setUp(self):
        super().setUp()
        self.assertTrue(frappe.local.site.endswith(".test"))
        self.original_user = frappe.session.user
        self.primary, self.site = frappe.local.db, frappe.local.site
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=10)
        self.manager = self._user(f"target-cycle-{token}-manager@example.invalid", "CRM Manager")
        self.sales = self._user(f"target-cycle-{token}-sales@example.invalid", "CRM Sales")
        frappe.set_user(self.manager)
        self.region = territory_admin.save_territory({"name": f"Target Cycle {token}", "parent": "China",
                                                    "isGroup": False, "enabled": True})["name"]
        self.personal_payload = {"sales": self.sales, "metric": "visits", "period": "week",
                                 "anchor": "2030-09-02", "value": "5"}
        self.personal = cockpit.save_target(self.personal_payload)
        self.territory_payload = {"scope": "territory", "territory": self.region, "metric": "orders",
                                  "period": "year", "anchor": "2030-01-01", "value": "123.45"}
        self.assignment_payload = {"territory": self.region, "salesOwner": self.sales,
                                   "validFrom": "2030-09-02", "validUntil": "2030-09-30",
                                   "cancelled": False, "note": "Concurrent coverage"}
        frappe.db.commit()
        self.addCleanup(self.remove_committed_fixtures)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def remove_committed_fixtures(self):
        frappe.local.db = self.primary
        frappe.db.rollback()
        frappe.set_user("Administrator")
        for doctype, filters in ((cockpit.TARGET, {"sales_owner": self.sales}),
                                 (cockpit.TARGET, {"territory": self.region}),
                                 (territory_admin.ASSIGNMENT, {"territory": self.region})):
            for name in frappe.get_all(doctype, filters=filters, pluck="name"):
                frappe.db.delete("Version", {"ref_doctype": doctype, "docname": name})
            frappe.db.delete(doctype, filters)
        frappe.db.delete(territory_admin.TERRITORY, {"name": self.region})
        from rayher_crm.services.regions import REGION_FIELD, list_regions, options_text
        frappe.db.set_value("Custom Field", REGION_FIELD, "options",
                            options_text([name for name in list_regions() if name != self.region]), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        for user in (self.sales, self.manager):
            frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)

    def worker(self, kind, *, native_assignment):
        frappe.init(site=self.site)
        frappe.connect()
        try:
            frappe.set_user(self.manager)
            frappe.flags.target_assignment_cycle_worker = kind
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout=15")
            if kind == "assignment":
                if native_assignment:
                    doc = frappe.get_doc({"doctype": territory_admin.ASSIGNMENT,
                                          "territory": self.region, "sales_owner": self.sales,
                                          "valid_from": "2030-09-02", "valid_until": "2030-09-30",
                                          "cancelled": 0, "note": "Concurrent coverage"})
                    result = doc.insert(ignore_permissions=True).name
                else:
                    result = territory_admin.save_assignment(self.assignment_payload)["id"]
            elif kind == "personal":
                result = cockpit.save_target({**self.personal_payload, "value": "7"}, self.personal["modified"])["id"]
            else:
                result = cockpit.save_target(self.territory_payload)["id"]
            frappe.db.commit()
            return "ok", result
        except Exception as exc:
            return type(exc).__name__, str(exc)
        finally:
            frappe.db.rollback()
            frappe.destroy()

    def assert_three_writes_complete(self, *, native_assignment):
        assignment_has_user, personal_attempts_user, territory_attempts_series, release_assignment = (Event() for _ in range(4))
        database = type(self.primary)
        original_sql = database.sql

        def observed_sql(db, query, values=(), *args, **kwargs):
            sql = str(query)
            kind = frappe.flags.get("target_assignment_cycle_worker")
            user_lock = "tabUser" in sql and "FOR UPDATE" in sql.upper() and self.sales in str(values)
            series_lock = "tabSeries" in sql and "rayher_crm.cockpit_target_write_lock" in str(values)
            if kind == "personal" and user_lock:
                personal_attempts_user.set()
            if kind == "territory" and series_lock:
                territory_attempts_series.set()
            result = original_sql(db, query, values, *args, **kwargs)
            if kind == "assignment" and user_lock and not assignment_has_user.is_set():
                assignment_has_user.set()
                if not release_assignment.wait(timeout=25):
                    raise AssertionError("Assignment writer was not released")
            return result

        with patch.object(database, "sql", new=observed_sql):
            with ThreadPoolExecutor(max_workers=3) as pool:
                assignment = pool.submit(self.worker, "assignment", native_assignment=native_assignment)
                try:
                    self.assertTrue(assignment_has_user.wait(timeout=15))
                    personal = pool.submit(self.worker, "personal", native_assignment=native_assignment)
                    self.assertTrue(personal_attempts_user.wait(timeout=15))
                    territory = pool.submit(self.worker, "territory", native_assignment=native_assignment)
                    self.assertTrue(territory_attempts_series.wait(timeout=15))
                finally:
                    release_assignment.set()
                results = [future.result(timeout=35) for future in (assignment, personal, territory)]
        self.assertEqual([result[0] for result in results], ["ok", "ok", "ok"], results)
        frappe.db.rollback()
        self.assertEqual(str(frappe.db.get_value(cockpit.TARGET, results[1][1], "target_value")), "7.00")
        self.assertEqual(str(frappe.db.get_value(cockpit.TARGET, results[2][1], "target_value")), "123.45")
        self.assertEqual(frappe.db.get_value(territory_admin.ASSIGNMENT, results[0][1], "sales_owner"), self.sales)

    def test_api_assignment_and_both_target_scopes_complete(self):
        self.assert_three_writes_complete(native_assignment=False)

    def test_native_assignment_and_both_target_scopes_complete(self):
        self.assert_three_writes_complete(native_assignment=True)
