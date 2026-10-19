"""Real native User rename/merge overlaps a manager save on two connections."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Event
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import events as service
from rayher_crm.tests import test_opportunity_relations as relation_fixtures


class TestEventIdentityConcurrency(FrappeTestCase):
    _user = relation_fixtures.TestOpportunityRelations._user

    def setUp(self):
        super().setUp()
        self.assertTrue(frappe.local.site.endswith(".test"))
        self.original_user = frappe.session.user
        self.primary, self.site = frappe.local.db, frappe.local.site
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=10)
        self.manager = self._user(f"event-race-{token}-manager@example.invalid", "CRM Manager")
        self.source = self._user(f"event-race-{token}-a@example.invalid", "CRM Sales")
        self.target = f"event-race-{token}-b@example.invalid"
        self.other = self._user(f"event-race-{token}-person040@example.invalid", "CRM Sales")
        self.payload = {"title": "Identity reassignment", "owner": self.source, "startDate": "2030-09-02",
                        "endDate": "2030-09-03", "status": "Planned"}
        # The source is the immutable creator, but the current assignee is
        # someone else. Native after_rename still updates metadata owner.
        frappe.set_user(self.source)
        created = service.save_event(self.payload)
        frappe.set_user(self.manager)
        self.saved = service.save_event({**self.payload, "owner": self.other}, created["id"], created["modified"])
        self.assertEqual(frappe.db.get_value(service.DOCTYPE, self.saved["id"], "owner"), self.source)
        frappe.db.commit()
        self.addCleanup(self.remove_committed_fixtures)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def remove_committed_fixtures(self):
        frappe.local.db = self.primary
        frappe.db.rollback()
        frappe.set_user("Administrator")
        frappe.db.delete("Version", {"ref_doctype": service.DOCTYPE, "docname": self.saved["id"]})
        frappe.db.delete(service.DOCTYPE, {"name": self.saved["id"]})
        for user in (self.source, self.target, self.other, self.manager):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)

    def save(self, owner):
        return service.save_event({**self.payload, "owner": owner}, self.saved["id"], self.saved["modified"])

    def worker(self, user, operation):
        frappe.init(site=self.site)
        frappe.connect()
        try:
            frappe.set_user(user)
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout=15")
            try:
                result = operation()
                frappe.db.commit()
                return ("ok", result)
            except CrmApiException as exc:
                return (exc.code, str(exc))
            except Exception as exc:
                return (type(exc).__name__, str(exc))
        finally:
            frappe.db.rollback()
            frappe.destroy()

    def save_during_native_identity_change(self, *, merge):
        native = import_module("frappe.model.rename_doc")
        frappe.set_user("Administrator")
        if merge:
            self._user(self.target, "CRM Sales")
            frappe.db.commit()
        rename_locked, release_rename, user_attempted, business_locked = (Event() for _ in range(4))
        original_rewrite = native.update_link_field_values
        database = type(self.primary)
        original_sql = database.sql

        def paused_rewrite(*args, **kwargs):
            # before_rename has locked the real Users. Continue the real native
            # Link and metadata rewrites only after the save attempts its User.
            rename_locked.set()
            if not release_rename.wait(timeout=30):
                raise AssertionError("Native rename was never released")
            return original_rewrite(*args, **kwargs)

        def observed_sql(db, query, values=(), *args, **kwargs):
            sql = str(query)
            observing = frappe.session.user == self.manager and "FOR UPDATE" in sql.upper()
            if observing and "tabUser" in sql and self.source in str(values):
                user_attempted.set()
            result = original_sql(db, query, values, *args, **kwargs)
            if observing and "tabCRM Event" in sql:
                business_locked.set()
            return result

        with patch.object(native, "update_link_field_values", side_effect=paused_rewrite), \
                patch.object(database, "sql", new=observed_sql):
            with ThreadPoolExecutor(max_workers=2) as executor:
                renamed = executor.submit(self.worker, "Administrator", lambda: native.rename_doc(
                    "User", self.source, self.target, merge=merge, force=True,
                    ignore_permissions=True, rebuild_search=False))
                try:
                    self.assertTrue(rename_locked.wait(timeout=15))
                    saved = executor.submit(self.worker, self.manager, lambda: self.save(self.source))
                    self.assertTrue(user_attempted.wait(timeout=15))
                    business_before_user = business_locked.is_set()
                finally:
                    release_rename.set()
                renamed_result, saved_result = renamed.result(timeout=30), saved.result(timeout=30)
        self.assertFalse(business_before_user, (renamed_result, saved_result))
        self.assertEqual(renamed_result[0], "ok", renamed_result)
        self.assertEqual(saved_result[0], "VALIDATION_ERROR", saved_result)
        frappe.db.rollback()
        self.assertEqual(frappe.db.get_value(service.DOCTYPE, self.saved["id"], "owner"), self.target)
        self.assertEqual(frappe.db.get_value(service.DOCTYPE, self.saved["id"], "event_owner"), self.other)
        frappe.set_user(self.manager)
        retried = self.save(self.target)
        self.assertEqual((retried["id"], retried["owner"]), (self.saved["id"], self.target))
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": service.DOCTYPE, "docname": self.saved["id"]}))

    def test_native_rename_and_save_keep_identity_before_business_rows(self):
        self.save_during_native_identity_change(merge=False)

    def test_native_merge_and_save_keep_identity_before_business_rows(self):
        self.save_during_native_identity_change(merge=True)
