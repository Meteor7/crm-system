"""Native User changes committed after an assignment writer's RR snapshot."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Event
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import territory_admin as service
from rayher_crm.tests import test_opportunity_relations as fixtures


class TestTerritoryIdentityConcurrency(FrappeTestCase):
    _user = fixtures.TestOpportunityRelations._user

    def setUp(self):
        super().setUp()
        self.assertTrue(frappe.local.site.endswith(".test"))
        self.original_user = frappe.session.user
        self.primary, self.site = frappe.local.db, frappe.local.site
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=10)
        self.sales = self._user(f"territory-race-{token}-a@example.invalid", "CRM Sales")
        self.destination = self._user(f"territory-race-{token}-b@example.invalid", "CRM Sales")
        self.region = service.save_territory({"name": f"Race Region {token}", "parent": "China", "isGroup": False, "enabled": True})["name"]
        self.payload = {"territory": self.region, "salesOwner": self.sales, "validFrom": "2030-09-02", "validUntil": "2030-09-30", "cancelled": False, "note": "Coverage"}
        # Release setup's catalogue/User locks before the other connection writes.
        frappe.db.commit()
        self.addCleanup(self.remove_committed_fixtures)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def remove_committed_fixtures(self):
        frappe.local.db = self.primary
        frappe.db.rollback()
        frappe.set_user("Administrator")
        names = frappe.get_all(service.ASSIGNMENT, filters={"territory": self.region}, pluck="name")
        for name in names:
            frappe.db.delete("Version", {"ref_doctype": service.ASSIGNMENT, "docname": name})
        frappe.db.delete(service.ASSIGNMENT, {"territory": self.region})
        frappe.db.delete(service.TERRITORY, {"name": self.region})
        from rayher_crm.services.regions import REGION_FIELD, list_regions, options_text
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", options_text([name for name in list_regions() if name != self.region]), update_modified=False)
        frappe.clear_cache(doctype="Customer")
        for user in (self.sales, self.destination, self.sales.replace("-a@", "-renamed@")):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)

    def change_user(self, change):
        frappe.init(site=self.site)
        frappe.connect()
        try:
            frappe.set_user("Administrator")
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout=15")
            if change in ("rename", "merge"):
                from frappe.model.rename_doc import rename_doc
                destination = self.destination if change == "merge" else self.sales.replace("-a@", "-renamed@")
                rename_doc("User", self.sales, destination, merge=change == "merge", force=True, ignore_permissions=True, rebuild_search=False)
            else:
                user = frappe.get_doc("User", self.sales)
                if change == "disable":
                    user.enabled = 0
                else:
                    user.set("roles", [row for row in user.roles if row.role != "CRM Sales"])
                user.save(ignore_permissions=True)
            frappe.db.commit()
        finally:
            frappe.db.rollback()
            frappe.destroy()

    def stale_snapshot(self, change):
        self.assertEqual(frappe.db.get_value("User", self.sales, "enabled"), 1)
        self.assertIn("CRM Sales", frappe.get_roles(self.sales))
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(self.change_user, change).result(timeout=30)
        # Demonstrate the old snapshot actually remains readable on this connection.
        self.assertEqual(frappe.db.get_value("User", self.sales, "enabled"), 1)

    def native_doc(self):
        return frappe.get_doc({"doctype": service.ASSIGNMENT, "territory": self.region, "sales_owner": self.sales,
                               "valid_from": "2030-09-02", "valid_until": "2030-09-30", "cancelled": 0})

    def assert_new_rejected(self, change, *, native=False):
        self.stale_snapshot(change)
        with self.assertRaises((CrmApiException, frappe.ValidationError)):
            self.native_doc().insert(ignore_permissions=True) if native else service.save_assignment(self.payload)
        self.assertFalse(frappe.db.sql("SELECT name FROM `tabCRM Territory Assignment` WHERE territory=%s FOR UPDATE", (self.region,)))

    def test_new_assignment_rejects_disable_committed_after_snapshot(self):
        self.assert_new_rejected("disable")

    def test_new_assignment_rejects_role_removal_committed_after_snapshot(self):
        self.assert_new_rejected("role")

    def test_native_insert_rejects_disable_committed_after_snapshot(self):
        self.assert_new_rejected("disable", native=True)

    def test_native_rename_cannot_leave_a_new_assignment_on_the_removed_user(self):
        self.assert_new_rejected("rename")

    def test_native_merge_cannot_leave_a_new_assignment_on_the_removed_user(self):
        self.assert_new_rejected("merge")

    def test_reactivation_rejects_disable_committed_after_snapshot(self):
        saved = service.save_assignment({**self.payload, "cancelled": True})
        frappe.db.commit()
        self.stale_snapshot("disable")
        with self.assertRaises(CrmApiException):
            service.save_assignment(self.payload, saved["id"], saved["modified"])

    def test_native_extension_rejects_role_removal_committed_after_snapshot(self):
        doc = self.native_doc().insert(ignore_permissions=True)
        frappe.db.commit()
        self.stale_snapshot("role")
        doc.valid_until = "2030-10-31"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_disabled_history_can_be_shortened_annotated_and_cancelled(self):
        saved = service.save_assignment(self.payload)
        frappe.db.commit()
        self.stale_snapshot("disable")
        changed = service.save_assignment({**self.payload, "validUntil": "2030-09-20", "note": "Historical correction"}, saved["id"], saved["modified"])
        self.assertEqual(changed["note"], "Historical correction")
        doc = frappe.get_doc(service.ASSIGNMENT, saved["id"])
        doc.cancelled = 1
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.cancelled, 1)

    def save_worker(self):
        frappe.init(site=self.site)
        frappe.connect()
        try:
            frappe.set_user("Administrator")
            frappe.flags.assignment_save_worker = True
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout=15")
            try:
                saved = service.save_assignment(self.payload)
                frappe.db.commit()
                return "ok", saved
            except CrmApiException as exc:
                return exc.code, str(exc)
        finally:
            frappe.db.rollback()
            frappe.destroy()

    def assert_save_waits_before_catalogue(self, change):
        native = import_module("frappe.model.rename_doc")
        rename_ready, release, user_attempted, catalogue_locked = (Event() for _ in range(4))
        original_rewrite = native.update_link_field_values
        database = type(self.primary)
        original_sql = database.sql

        def pause_rewrite(*args, **kwargs):
            rename_ready.set()
            if not release.wait(timeout=30):
                raise AssertionError("Native identity change was not released")
            return original_rewrite(*args, **kwargs)

        def observed_sql(db, query, values=(), *args, **kwargs):
            sql = str(query)
            observing = frappe.flags.get("assignment_save_worker") and "FOR UPDATE" in sql.upper()
            if observing and "tabUser" in sql and self.sales in str(values):
                user_attempted.set()
            result = original_sql(db, query, values, *args, **kwargs)
            if observing and "tabDocType" in sql and service.TERRITORY in str(values):
                catalogue_locked.set()
            return result

        with patch.object(native, "update_link_field_values", side_effect=pause_rewrite), patch.object(database, "sql", new=observed_sql):
            with ThreadPoolExecutor(max_workers=2) as pool:
                changed = pool.submit(self.change_user, change)
                try:
                    self.assertTrue(rename_ready.wait(timeout=15))
                    saved = pool.submit(self.save_worker)
                    self.assertTrue(user_attempted.wait(timeout=15))
                    self.assertFalse(catalogue_locked.is_set())
                finally:
                    release.set()
                changed.result(timeout=30)
                self.assertEqual(saved.result(timeout=30)[0], "VALIDATION_ERROR")
        self.assertFalse(frappe.db.sql("SELECT name FROM `tabCRM Territory Assignment` WHERE territory=%s FOR UPDATE", (self.region,)))

    def test_save_waits_for_native_rename_before_locking_catalogue(self):
        self.assert_save_waits_before_catalogue("rename")

    def test_save_waits_for_native_merge_before_locking_catalogue(self):
        self.assert_save_waits_before_catalogue("merge")

    def assert_native_save_orders_catalogue_before_parent(self, *, assignment):
        if assignment:
            api_record = service.save_assignment(self.payload)
            native_record = service.save_assignment({**self.payload, "salesOwner": self.destination,
                                                    "validFrom": "2030-10-01", "validUntil": "2030-10-31"})
            native_name = native_record["id"]
        else:
            api_record = service.save_territory({"name": self.region, "parent": "China", "isGroup": False,
                                                "enabled": True, "sortOrder": 1}, self.region,
                                               service.to_iso_timestamp(frappe.db.get_value(service.TERRITORY, self.region, "modified")))
            native_name = "Asia"
        frappe.db.commit()
        api_has_catalogue, native_attempted = Event(), Event()
        database = type(self.primary)
        original_sql = database.sql

        def observed_sql(db, query, values=(), *args, **kwargs):
            catalogue = "tabDocType" in str(query) and "FOR UPDATE" in str(query).upper() and service.TERRITORY in str(values)
            if catalogue and frappe.flags.get("native_catalogue_race"):
                native_attempted.set()
            result = original_sql(db, query, values, *args, **kwargs)
            if catalogue and frappe.flags.get("api_catalogue_race") and not api_has_catalogue.is_set():
                api_has_catalogue.set()
                if not native_attempted.wait(timeout=20):
                    raise AssertionError("Native save did not attempt the catalogue")
            return result

        def worker(native):
            frappe.init(site=self.site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=15")
                if native:
                    frappe.flags.native_catalogue_race = True
                    doc = frappe.get_doc(service.ASSIGNMENT if assignment else service.TERRITORY, native_name)
                    if assignment:
                        doc.note = "Native concurrent correction"
                    else:
                        doc.sort_order = int(doc.sort_order or 0) + 1
                    doc.save(ignore_permissions=True)
                else:
                    frappe.flags.api_catalogue_race = True
                    if assignment:
                        service.save_assignment({**self.payload, "note": "API concurrent correction"}, api_record["id"], api_record["modified"])
                    else:
                        service.save_territory({"name": self.region, "parent": "China", "isGroup": False,
                                                "enabled": True, "sortOrder": 2}, self.region, api_record["modified"])
                # This test checks two independent updates; neither needs to persist.
                return "ok"
            except Exception as exc:
                return type(exc).__name__, str(exc)
            finally:
                frappe.db.rollback()
                frappe.destroy()

        with patch.object(database, "sql", new=observed_sql):
            with ThreadPoolExecutor(max_workers=2) as pool:
                api = pool.submit(worker, False)
                self.assertTrue(api_has_catalogue.wait(timeout=15))
                native = pool.submit(worker, True)
                self.assertEqual((api.result(timeout=35), native.result(timeout=35)), ("ok", "ok"))

    def test_native_assignment_save_does_not_invert_api_catalogue_lock(self):
        self.assert_native_save_orders_catalogue_before_parent(assignment=True)

    def test_native_territory_save_does_not_invert_api_catalogue_lock(self):
        self.assert_native_save_orders_catalogue_before_parent(assignment=False)
