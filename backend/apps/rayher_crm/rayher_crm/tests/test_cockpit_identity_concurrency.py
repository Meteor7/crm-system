"""Real requests keep durable owner identities across native User changes."""
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from unittest.mock import patch

import frappe
from frappe.model.rename_doc import rename_doc
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import create_strategy_opportunity, update_strategy_opportunity
from rayher_crm.services.sites import create_site
from rayher_crm.tests import test_opportunity_relations as relation_fixtures


class TestCockpitIdentityConcurrency(FrappeTestCase):
    _user = relation_fixtures.TestOpportunityRelations._user

    def setUp(self):
        super().setUp()
        self.assertTrue(frappe.local.site.endswith(".test"))
        self.original_user = frappe.session.user
        self.primary = frappe.local.db
        frappe.set_user("Administrator")
        self.suffix = frappe.generate_hash(length=10)
        prefix = f"owner-race-{self.suffix}"
        self.source, self.target, self.renamed, self.target_renamed = [
            f"{prefix}-{part}@example.invalid" for part in ("source", "target", "renamed", "target-renamed")]
        self._user(self.source, "CRM Sales")
        self._user(self.target, "CRM Sales")
        # Manager-created, Sales-owned: a native User rename changes the owner
        # Link without also changing the immutable Created By metadata.
        self.account = create_account({"name": f"Owner Race {self.suffix}", "shortName": self.suffix,
            "segment": "Frontend", "tier": "A", "city": "上海", "region": "华东", "owner": self.source})
        site = create_site(self.account["id"], {"name": f"Owner Race {self.suffix}", "city": "上海",
            "type": "Fab", "process": "Frontend", "status": "量产"})
        self.opportunity = create_strategy_opportunity({"accountId": self.account["id"], "siteId": site["id"],
            "title": f"Owner Race {self.suffix}", "owner": self.source, "probabilityLevel": "pipeline",
            "forecast": "Pipeline", "amount": 100000, "intentScore": 20, "poDate": "2026-12-31",
            "toolType": "Inspection", "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "originalAmount": 100000, "amountCny": 100000, "qualificationConfirmed": True})
        self.site = frappe.local.site
        frappe.db.commit()
        self.addCleanup(self.remove_committed_fixtures)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def remove_committed_fixtures(self):
        frappe.local.db = self.primary
        frappe.db.rollback()
        frappe.set_user("Administrator")
        name = self.opportunity["id"]
        for doctype in ("CRM Opportunity History", "CRM Opportunity Stage History", "CRM Opportunity Probability History"):
            frappe.db.delete(doctype, {"opportunity": name})
        frappe.db.delete("CRM Notification Event", {"source_doctype": "CRM Opportunity", "source_name": name})
        frappe.db.delete("Version", {"ref_doctype": "CRM Opportunity", "docname": name})
        frappe.db.delete("DocShare", {"share_doctype": "CRM Opportunity", "share_name": name})
        frappe.db.delete("CRM Opportunity", {"name": name})
        frappe.delete_doc("Address", self.opportunity["siteId"], force=True, ignore_permissions=True)
        frappe.delete_doc("Customer", self.account["id"], force=True, ignore_permissions=True)
        for user in (self.source, self.target, self.renamed, self.target_renamed):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)

    def stale_source_edit(self, *, merge):
        if merge:
            self._user(self.renamed, "CRM Sales")
            frappe.db.commit()
        name = self.opportunity["id"]
        with self.secondary_connection():
            frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self.assertEqual(frappe.db.get_value("CRM Opportunity", name, "opportunity_owner"), self.source)
            with self.primary_connection():
                rename_doc("User", self.source, self.renamed, merge=merge, force=True,
                           ignore_permissions=True, rebuild_search=False)
                self._user(self.source, "CRM Sales")
                frappe.db.commit()
            with self.assertRaises(CrmApiException) as stale:
                update_strategy_opportunity(name, {"owner": self.target}, self.opportunity["modified"])
            self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
            frappe.db.rollback()
        current = frappe.get_doc("CRM Opportunity", name)
        self.assertEqual(current.opportunity_owner, self.renamed)
        self.assertFalse(frappe.db.exists("CRM Opportunity History", {"opportunity": name, "field": "opportunity_owner"}))
        update_strategy_opportunity(name, {"owner": self.target}, self.opportunity["modified"])
        row = frappe.get_doc("CRM Opportunity History", {"opportunity": name, "field": "opportunity_owner"})
        self.assertEqual((row.from_owner, row.to_owner), (self.renamed, self.target))

    def test_rename_and_source_email_reuse_reject_stale_request_then_retry_uses_renamed_identity(self):
        self.stale_source_edit(merge=False)

    def test_merge_and_source_email_reuse_reject_stale_request_then_retry_uses_destination_identity(self):
        self.stale_source_edit(merge=True)

    def test_target_email_reuse_cannot_inherit_the_old_requests_identity_check(self):
        name = self.opportunity["id"]
        with self.secondary_connection():
            frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            old_creation = frappe.db.get_value("User", self.target, "creation")
            with self.primary_connection():
                rename_doc("User", self.target, self.target_renamed, force=True,
                           ignore_permissions=True, rebuild_search=False)
                self._user(self.target, "CRM Sales")
                self.assertNotEqual(frappe.db.get_value("User", self.target, "creation"), old_creation)
                frappe.db.commit()
            with self.assertRaises(CrmApiException) as stale:
                update_strategy_opportunity(name, {"owner": self.target}, self.opportunity["modified"])
            self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
            frappe.db.rollback()
        self.assertEqual(frappe.db.get_value("CRM Opportunity", name, "opportunity_owner"), self.source)

    def held_owner_change(self, *, merge):
        if merge:
            self._user(self.renamed, "CRM Sales")
            frappe.db.commit()
        from rayher_crm.services.cockpit_identity import lock_opportunity_owners
        # Hold the real editor's identity guard before taking the parent lock.
        # A merge must wait here, before it can pass any history Link updates.
        lock_opportunity_owners(self.opportunity["id"], {"owner": self.target})

        def attempt_native_change():
            frappe.init(site=self.site)
            frappe.connect()
            try:
                frappe.set_user("Administrator")
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=1")
                native = import_module("frappe.model.rename_doc")
                # Observe the boundary while retaining the real native Link SQL.
                with patch.object(native, "update_link_field_values", wraps=native.update_link_field_values) as rewrite:
                    try:
                        rename_doc("User", self.source, self.renamed, merge=merge, force=True,
                                   ignore_permissions=True, rebuild_search=False)
                        return "unexpected success", rewrite.called
                    except Exception as exc:
                        return f"{type(exc).__name__}: {exc}", rewrite.called
            finally:
                frappe.db.rollback()
                frappe.destroy()

        with ThreadPoolExecutor(max_workers=1) as executor:
            outcome, reached_links = executor.submit(attempt_native_change).result(timeout=15)
        self.assertIn("lock wait timeout", outcome.lower())
        self.assertNotIn("deadlock", outcome.lower())
        self.assertFalse(reached_links, "User merge must wait before traversing History Links, not at its final delete")
        update_strategy_opportunity(self.opportunity["id"], {"owner": self.target}, self.opportunity["modified"])
        frappe.db.commit()
        rename_doc("User", self.source, self.renamed, merge=merge, force=True,
                   ignore_permissions=True, rebuild_search=False)
        row = frappe.get_doc("CRM Opportunity History", {"opportunity": self.opportunity["id"], "field": "opportunity_owner"})
        self.assertEqual((row.from_value, row.from_owner), (self.source, self.renamed))

    def test_native_rename_waits_for_the_owner_change_before_rewriting_history_links(self):
        self.held_owner_change(merge=False)

    def test_native_merge_waits_for_the_owner_change_before_rewriting_history_links(self):
        self.held_owner_change(merge=True)

    def test_blue_sheet_waits_for_user_identity_before_locking_the_opportunity(self):
        from rayher_crm.services import blue_sheet
        name = self.opportunity["id"]
        timeout = frappe.db.sql("SELECT @@innodb_lock_wait_timeout")[0][0]
        try:
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout=1")
            with self.secondary_connection():
                # Native User rename/merge holds this lock before visiting Links.
                frappe.db.sql("SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE", (self.source,))
                with self.primary_connection():
                    with self.assertRaises(Exception) as waiting:
                        blue_sheet.apply_suggestion(name, {"fingerprint": "pending"}, self.opportunity["modified"])
                    self.assertIn("lock wait timeout", str(waiting.exception).lower())
                # The waiting confirmation must not hold the parent lock: a
                # rename needs it next, and the reverse order would deadlock.
                frappe.db.sql("SELECT name FROM `tabCRM Opportunity` WHERE name=%s FOR UPDATE NOWAIT", (name,))
                frappe.db.rollback()
        finally:
            frappe.db.rollback()
            # Frappe's first secondary_connection leaves local.db pointing at
            # that connection. Restore the session changed above explicitly.
            self.primary.rollback()
            self.primary.sql("SET SESSION innodb_lock_wait_timeout=%s", (timeout,))
