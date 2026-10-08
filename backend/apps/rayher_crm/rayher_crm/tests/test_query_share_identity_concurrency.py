"""Real User rename/merge must not invert saved-query sharing locks."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Event
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import opportunity_board as service
from rayher_crm.tests import test_opportunity_board_api as board_fixtures


class TestQueryShareIdentityConcurrency(FrappeTestCase):
    _user = board_fixtures.TestOpportunityBoardApi._user

    def setUp(self):
        super().setUp()
        self.assertTrue(frappe.local.site.endswith(".test"))
        self.original_user = frappe.session.user
        self.primary = frappe.local.db
        self.site = frappe.local.site
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=10)
        self.manager = self._user(f"share-race-{token}-manager@example.invalid", "CRM Manager", "Share Manager")
        self.source = self._user(f"share-race-{token}-a@example.invalid", "CRM Sales", "Share A")
        self.target = f"share-race-{token}-b@example.invalid"
        frappe.set_user(self.manager)
        definition = {"scope": {}, "match": "all", "conditions": [], "columns": ["customerName", "amountCny"]}
        saved = service.save_opportunity_query(None, {"name": "Identity race", "definition": definition})
        self.saved = service.share_opportunity_query(saved["id"], [self.source], saved["modified"])
        frappe.db.commit()
        self.addCleanup(self.remove_committed_fixtures)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def remove_committed_fixtures(self):
        frappe.local.db = self.primary
        frappe.db.rollback()
        frappe.set_user("Administrator")
        frappe.db.delete("CRM Query Recipient", {"parent": self.saved["id"]})
        frappe.db.delete(service.SAVED_QUERY, {"name": self.saved["id"]})
        frappe.db.delete("Version", {"ref_doctype": service.SAVED_QUERY, "docname": self.saved["id"]})
        for user in (self.source, self.target, self.manager):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)

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

    def observe_source_lock(self, attempted):
        database = type(self.primary)
        original = database.sql

        def observed(db, query, values=(), *args, **kwargs):
            # Observe the real SQL boundary without replacing database behavior.
            if (frappe.session.user == self.manager and "tabUser" in str(query)
                    and "FOR UPDATE" in str(query).upper() and self.source in str(values)):
                attempted.set()
            return original(db, query, values, *args, **kwargs)

        return patch.object(database, "sql", new=observed)

    def share_waits_before_children(self, *, merge):
        native = import_module("frappe.model.rename_doc")
        frappe.set_user("Administrator")
        if merge:
            self._user(self.target, "CRM Sales", "Share B")
            frappe.db.commit()
        rename_locked, release_rename, share_attempted, query_locked = (Event() for _ in range(4))
        original_rewrite = native.update_link_field_values
        original_query_lock = service._lock_own_query

        def paused_rewrite(*args, **kwargs):
            rename_locked.set()
            if not release_rename.wait(timeout=30):
                raise AssertionError("Native rename was never released")
            return original_rewrite(*args, **kwargs)

        def observed_query_lock(*args, **kwargs):
            doc = original_query_lock(*args, **kwargs)
            query_locked.set()
            return doc

        with patch.object(native, "update_link_field_values", side_effect=paused_rewrite), \
                patch.object(service, "_lock_own_query", side_effect=observed_query_lock), \
                self.observe_source_lock(share_attempted):
            with ThreadPoolExecutor(max_workers=2) as executor:
                renamed = executor.submit(self.worker, "Administrator", lambda: native.rename_doc(
                    "User", self.source, self.target, merge=merge, force=True,
                    ignore_permissions=True, rebuild_search=False))
                try:
                    self.assertTrue(rename_locked.wait(timeout=15))
                    shared = executor.submit(self.worker, self.manager, lambda: service.share_opportunity_query(
                        self.saved["id"], [self.source], self.saved["modified"]))
                    self.assertTrue(share_attempted.wait(timeout=15))
                    locked_children_before_user = query_locked.is_set()
                finally:
                    release_rename.set()
                renamed_result, shared_result = renamed.result(timeout=30), shared.result(timeout=30)
        self.assertFalse(locked_children_before_user, (renamed_result, shared_result))
        self.assertEqual(renamed_result[0], "ok", renamed_result)
        self.assertEqual(shared_result[0], "VALIDATION_ERROR", shared_result)
        frappe.db.rollback()
        self.assertEqual(frappe.get_all("CRM Query Recipient", filters={"parent": self.saved["id"]}, pluck="user"), [self.target])
        frappe.set_user(self.manager)
        retried = service.share_opportunity_query(self.saved["id"], [self.target], self.saved["modified"])
        self.assertEqual(retried["recipients"], [self.target])

    def test_native_rename_and_share_follow_user_before_query_order(self):
        self.share_waits_before_children(merge=False)

    def test_native_merge_and_share_follow_user_before_query_order(self):
        self.share_waits_before_children(merge=True)

    def save_after_author_identity_changed(self, *, merge, reuse=False):
        native = import_module("frappe.model.rename_doc")
        frappe.set_user("Administrator")
        if merge:
            self._user(self.target, "CRM Manager", "New Author")
            frappe.db.commit()
        snapshot_ready, release_writer = Event(), Event()
        original_mutex = service._lock_query_writes

        def paused_mutex():
            original_mutex()
            # An authenticated request can have an ordinary snapshot/cache of
            # its author before the administrator changes that identity.
            self.assertEqual(frappe.db.get_value("User", self.manager, "name"), self.manager)
            snapshot_ready.set()
            if not release_writer.wait(timeout=30):
                raise AssertionError("Author save was never released")

        payload = {"name": "Concurrent new query", "definition": {
            "scope": {}, "match": "all", "conditions": [], "columns": ["customerName", "amountCny"]}}
        with patch.object(service, "_lock_query_writes", side_effect=paused_mutex), \
                ThreadPoolExecutor(max_workers=1) as executor:
            saved = executor.submit(self.worker, self.manager, lambda: service.save_opportunity_query(None, payload))
            try:
                self.assertTrue(snapshot_ready.wait(timeout=15))
                native.rename_doc("User", self.manager, self.target, merge=merge, force=True,
                                  ignore_permissions=True, rebuild_search=False)
                frappe.db.commit()
                if reuse:
                    self._user(self.manager, "CRM Manager", "Replacement Author")
                    frappe.db.commit()
            finally:
                release_writer.set()
            outcome = saved.result(timeout=30)
        frappe.db.rollback()
        stale = frappe.get_all(service.SAVED_QUERY, filters={"query_owner": self.manager}, pluck="name")
        # Keep cleanup reliable even when the original implementation persists
        # the broken row that these assertions are intended to expose.
        for name in stale:
            frappe.db.delete(service.SAVED_QUERY, {"name": name})
        frappe.db.commit()
        self.assertEqual(outcome[0], "VALIDATION_ERROR", outcome)
        self.assertEqual(stale, [])
        frappe.set_user(self.target)
        retried = service.save_opportunity_query(None, payload)
        self.assertEqual(retried["owner"], self.target)
        self.assertFalse(retried["readOnly"])
        frappe.db.delete(service.SAVED_QUERY, {"name": retried["id"]})
        frappe.db.commit()

    def test_native_author_rename_rejects_save_from_old_request_snapshot(self):
        self.save_after_author_identity_changed(merge=False)

    def test_native_author_merge_rejects_save_from_old_request_snapshot(self):
        self.save_after_author_identity_changed(merge=True)

    def test_native_author_rename_and_email_reuse_rejects_old_request(self):
        self.save_after_author_identity_changed(merge=False, reuse=True)

    def test_native_author_merge_and_email_reuse_rejects_old_request(self):
        self.save_after_author_identity_changed(merge=True, reuse=True)

    def test_cached_authenticated_author_is_not_replaced_before_service_snapshot(self):
        from types import SimpleNamespace
        from frappe.sessions import Session

        native = import_module("frappe.model.rename_doc")
        frappe.set_user("Administrator")
        frappe.get_cached_value("User", self.manager, "enabled")
        frappe.get_roles(self.manager)
        frappe.db.commit()
        authenticated, release_request = Event(), Event()
        payload = {"name": "Cached author query", "definition": {
            "scope": {}, "match": "all", "conditions": [], "columns": ["customerName", "amountCny"]}}

        def cached_request():
            # Exercise the real cookie-session enabled check and request cache.
            Session.validate_user(SimpleNamespace(user=self.manager))
            service._require_board_access()
            original_creation = frappe.get_cached_value("User", self.manager, "creation")
            # Model authentication satisfied entirely from cache, without an
            # old database snapshot; keep the authenticated User in local cache.
            frappe.db.rollback()
            authenticated.set()
            if not release_request.wait(timeout=30):
                raise AssertionError("Cached request was never released")
            self.assertEqual(frappe.get_cached_value("User", self.manager, "creation"), original_creation)
            self.assertNotEqual(frappe.db.get_value("User", self.manager, "creation"), original_creation)
            return service.save_opportunity_query(None, payload)

        with ThreadPoolExecutor(max_workers=1) as executor:
            saved = executor.submit(self.worker, self.manager, cached_request)
            try:
                self.assertTrue(authenticated.wait(timeout=15))
                native.rename_doc("User", self.manager, self.target, force=True,
                                  ignore_permissions=True, rebuild_search=False)
                frappe.db.commit()
                self._user(self.manager, "CRM Manager", "Replacement Author")
                frappe.db.commit()
            finally:
                release_request.set()
            outcome = saved.result(timeout=30)
        frappe.db.rollback()
        stale = frappe.get_all(service.SAVED_QUERY, filters={"query_owner": self.manager}, pluck="name")
        for name in stale:
            frappe.db.delete(service.SAVED_QUERY, {"name": name})
        frappe.db.commit()
        self.assertEqual(outcome[0], "VALIDATION_ERROR", outcome)
        self.assertEqual(stale, [])
        # A genuinely new request for the replacement identity remains valid.
        with ThreadPoolExecutor(max_workers=1) as executor:
            retried = executor.submit(self.worker, self.manager, lambda: service.save_opportunity_query(None, payload)).result(timeout=30)
        self.assertEqual(retried[0], "ok", retried)
        frappe.db.delete(service.SAVED_QUERY, {"name": retried[1]["id"]})
        frappe.db.commit()

    def test_author_and_recipient_lock_together_before_native_merge(self):
        native = import_module("frappe.model.rename_doc")
        frappe.set_user("Administrator")
        frappe.db.sql("SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE", (self.source,))
        attempted = Event()
        with self.observe_source_lock(attempted), ThreadPoolExecutor(max_workers=1) as executor:
            shared = executor.submit(self.worker, self.manager, lambda: service.share_opportunity_query(
                self.saved["id"], [self.source], self.saved["modified"]))
            try:
                self.assertTrue(attempted.wait(timeout=15))
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=1")
                # Author sorts after recipient. Locking the author separately
                # first would prevent the native merge taking this second lock.
                frappe.db.sql("SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE", (self.manager,))
                native.rename_doc("User", self.source, self.manager, merge=True, force=True,
                                  ignore_permissions=True, rebuild_search=False)
                frappe.db.commit()
            finally:
                frappe.db.rollback()
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=50")
            outcome = shared.result(timeout=30)
        self.assertEqual(outcome[0], "VALIDATION_ERROR", outcome)

    def test_case_variant_recipients_lock_in_database_order_before_native_merge(self):
        native = import_module("frappe.model.rename_doc")
        frappe.set_user("Administrator")
        self._user(self.target, "CRM Sales", "Share B")
        frappe.db.commit()
        # The merge has reached A first. The sharing request's client spelling
        # sorts B before A; while it waits on A, B must remain available to merge.
        frappe.db.sql("SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE", (self.source,))
        attempted = Event()
        with self.observe_source_lock(attempted), ThreadPoolExecutor(max_workers=1) as executor:
            shared = executor.submit(self.worker, self.manager, lambda: service.share_opportunity_query(
                self.saved["id"], [self.target.upper(), self.source], self.saved["modified"]))
            try:
                self.assertTrue(attempted.wait(timeout=15))
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=1")
                # An inverted request already owns B and this real lock times out.
                frappe.db.sql("SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE", (self.target,))
                native.rename_doc("User", self.source, self.target, merge=True, force=True,
                                  ignore_permissions=True, rebuild_search=False)
                frappe.db.commit()
            finally:
                frappe.db.rollback()
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=50")
            outcome = shared.result(timeout=30)
        self.assertEqual(outcome[0], "VALIDATION_ERROR", outcome)
        frappe.db.rollback()
        self.assertEqual(frappe.get_all("CRM Query Recipient", filters={"parent": self.saved["id"]}, pluck="user"), [self.target])
