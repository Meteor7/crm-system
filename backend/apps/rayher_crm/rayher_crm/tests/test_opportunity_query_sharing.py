from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import opportunity_board as service
from rayher_crm.tests.test_opportunity_board_api import TestOpportunityBoardApi


class TestOpportunityQuerySharing(FrappeTestCase):
    _user = TestOpportunityBoardApi._user
    _opportunity = TestOpportunityBoardApi._opportunity
    _as = TestOpportunityBoardApi._as

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.token = frappe.generate_hash(length=8)
        self.sales = self._user("query-share-sales@example.invalid", "CRM Sales", "Share Sales")
        self.other = self._user("query-share-other@example.invalid", "CRM Sales", "Other Sales")
        self.manager = self._user("query-share-manager@example.invalid", "CRM Manager", "Share Manager")
        self.mine = self._opportunity(self.sales, "Share Mine", "Inspection", "100.00")
        self.theirs = self._opportunity(self.other, "Share Other", "Inspection", "250.50")
        self.definition = {"scope": {}, "match": "all", "conditions": [], "columns": ["customerName", "amountCny"]}
        self.saved = self._as(self.manager, lambda: service.save_opportunity_query(None, {"name": "Shared", "definition": self.definition}))

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def query(self, saved):
        return {"savedQuery": {"id": saved["id"], "modified": saved["modified"]}}

    def test_author_only_sharing_edits_copy_and_revoke(self):
        shared = self._as(self.manager, lambda: service.share_opportunity_query(self.saved["id"], [self.sales.upper(), self.sales], self.saved["modified"]))
        self.assertEqual(shared["recipients"], [self.sales])
        audit = frappe.get_all("Version", filters={"ref_doctype": service.SAVED_QUERY, "docname": shared["id"]}, pluck="data")
        self.assertTrue(any(any(field == "recipients" and row.get("user") == self.sales for field, row in frappe.parse_json(value).get("added", [])) for value in audit))
        listed = self._as(self.sales, service.list_opportunity_queries)["items"]
        received = next(row for row in listed if row["id"] == shared["id"])
        self.assertTrue(received["readOnly"])
        self.assertEqual((received["owner"], received["recipients"]), (self.manager, []))
        for change in (lambda: service.share_opportunity_query(shared["id"], [self.other], shared["modified"]),
                       lambda: service.save_opportunity_query(shared["id"], {"name": "Overwrite", "definition": self.definition}, shared["modified"]),
                       lambda: service.delete_opportunity_query(shared["id"], shared["modified"])):
            with self.assertRaises(CrmApiException) as denied:
                self._as(self.sales, change)
            self.assertEqual(denied.exception.code, "NOT_FOUND")
        copied = self._as(self.sales, lambda: service.save_opportunity_query(None, {"name": "My copy", "definition": received["definition"]}))
        self.assertFalse(copied["readOnly"])
        self.assertEqual(copied["recipients"], [])
        self.assertNotEqual(copied["id"], shared["id"])
        self._as(self.manager, lambda: service.share_opportunity_query(shared["id"], [], shared["modified"]))
        with self.assertRaises(CrmApiException) as revoked:
            self._as(self.sales, lambda: service.export_opportunities(self.query(shared)))
        self.assertEqual(revoked.exception.code, "NOT_FOUND")
        self.assertNotIn(shared["id"], {row["id"] for row in self._as(self.sales, service.list_opportunity_queries)["items"]})
        self.assertTrue(self._as(self.sales, lambda: service.export_opportunities(self.query(copied)))["items"])
        frappe.set_user(self.sales)
        self.assertFalse(frappe.has_permission(service.SAVED_QUERY, "read", doc=frappe.get_doc(service.SAVED_QUERY, shared["id"])))

    def test_export_is_one_full_set_and_rechecks_current_scope_and_version(self):
        shared = self._as(self.manager, lambda: service.share_opportunity_query(self.saved["id"], [self.sales], self.saved["modified"]))
        query = {**self.query(shared), "page": 2, "pageSize": 1}
        with patch.object(service, "_board_context", wraps=service._board_context) as reads:
            result = self._as(self.manager, lambda: service.export_opportunities({**query, "scope": {"sales": [self.sales, self.other]}}))
        self.assertEqual(reads.call_count, 1)
        self.assertEqual({row["id"] for row in result["items"]}, {self.mine, self.theirs})
        self.assertEqual((result["summary"]["count"], result["summary"]["knownAmountCny"]), (2, "350.50"))
        own = self._as(self.sales, lambda: service.export_opportunities(query))
        self.assertEqual([row["id"] for row in own["items"]], [self.mine])
        frappe.db.set_value("CRM Opportunity", self.mine, "opportunity_owner", self.other)
        self.assertEqual(self._as(self.sales, lambda: service.export_opportunities(query))["items"], [])
        self._as(self.manager, lambda: service.save_opportunity_query(shared["id"], {"name": "Changed", "definition": self.definition}, shared["modified"]))
        with self.assertRaises(CrmApiException) as stale:
            self._as(self.sales, lambda: service.query_opportunities(query))
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        self.assertIn("savedQuery", query)  # service normalization does not mutate caller input

    def test_recipients_require_current_enabled_single_crm_role_and_cas(self):
        for recipients in ([self.manager], ["person035@example.invalid"], [True], {}, [self.sales] * 101):
            with self.subTest(recipients=recipients), self.assertRaises(CrmApiException):
                self._as(self.manager, lambda: service.share_opportunity_query(self.saved["id"], recipients, self.saved["modified"]))
        frappe.db.set_value("User", self.sales, "enabled", 0)
        with self.assertRaises(CrmApiException):
            self._as(self.manager, lambda: service.share_opportunity_query(self.saved["id"], [self.sales], self.saved["modified"]))
        self.assertNotIn(self.sales, {row["value"] for row in self._as(self.manager, service.query_recipient_options)["items"]})
        self._as(self.manager, lambda: service.share_opportunity_query(self.saved["id"], [self.other], self.saved["modified"]))
        with self.assertRaises(CrmApiException) as stale:
            self._as(self.manager, lambda: service.share_opportunity_query(self.saved["id"], [], self.saved["modified"]))
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

    def test_shared_team_predicates_and_copies_intersect_recipient_scope(self):
        definitions = (
            {**self.definition, "scope": {"sales": [self.sales, self.other]}},
            {**self.definition, "conditions": [{"match": "any", "conditions": [{"field": "sales", "operator": "in", "value": [self.sales, self.other]}]}]},
            {**self.definition, "conditions": [{"field": "sales", "operator": "not_in", "value": [self.other]}]},
        )
        for index, definition in enumerate(definitions):
            with self.subTest(index=index):
                saved = self._as(self.manager, lambda: service.save_opportunity_query(None, {"name": f"Team {index}", "definition": definition}))
                shared = self._as(self.manager, lambda: service.share_opportunity_query(saved["id"], [self.sales], saved["modified"]))
                query = {key: value for key, value in definition.items() if key != "columns"}
                with self.assertRaises(CrmApiException):
                    self._as(self.sales, lambda: service.export_opportunities(query))
                result = self._as(self.sales, lambda: service.export_opportunities({**query, **self.query(shared)}))
                self.assertEqual([row["id"] for row in result["items"]], [self.mine])
                listed, _, _, _ = self._as(self.sales, lambda: service.query_opportunities({**query, **self.query(shared)}))
                self.assertEqual([row["id"] for row in listed["items"]], [self.mine])
                with self.assertRaises(CrmApiException):
                    self._as(self.sales, lambda: service.export_opportunities({**query, **self.query(shared), "scope": {"sales": [self.manager]}}))
                copied = self._as(self.sales, lambda: service.save_opportunity_query(None, {"name": f"Copy {index}", "definition": definition, **self.query(shared)}))
                self._as(self.manager, lambda: service.share_opportunity_query(shared["id"], [], shared["modified"]))
                with self.assertRaises(CrmApiException):
                    self._as(self.sales, lambda: service.save_opportunity_query(None, {"name": f"Revoked {index}", "definition": definition, **self.query(shared)}))
                own = self._as(self.sales, lambda: service.export_opportunities({**query, **self.query(copied)}))
                self.assertEqual([row["id"] for row in own["items"]], [self.mine])
                self.assertEqual(copied["recipients"], [])

    def test_revocation_committed_after_request_snapshot_is_rechecked(self):
        # External rows avoid committing this test's unrelated Frappe fixtures.
        connection = frappe.db._get_connection()
        name = "share-race-" + self.token
        child = name + "-recipient"
        when = datetime(2030, 1, 1)
        try:
            # setup's saved-query write holds the manager's index range lock.
            # Release it before inserting external rows with that same owner.
            frappe.db.rollback()
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO `tabCRM Opportunity Saved Query` (name,creation,modified,owner,modified_by,query_owner,query_name,definition) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                               (name, when, when, self.manager, self.manager, self.manager, "Race", frappe.as_json(self.definition)))
                cursor.execute("INSERT INTO `tabCRM Query Recipient` (name,creation,modified,owner,modified_by,parent,parenttype,parentfield,idx,user) VALUES (%s,%s,%s,%s,%s,%s,%s,'recipients',1,%s)",
                               (child, when, when, self.manager, self.manager, name, service.SAVED_QUERY, self.sales))
            connection.commit()
            reference = {"savedQuery": {"id": name, "modified": service.to_iso_timestamp(when)}}
            frappe.session.user = self.sales
            service._consume_saved_reference(dict(reference))
            # Two actual connections can hold shared current-read locks together.
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_lock_wait_timeout=1")
                cursor.execute("SELECT name FROM `tabCRM Opportunity Saved Query` WHERE name=%s LOCK IN SHARE MODE", (name,))
                self.assertTrue(cursor.fetchone())
                cursor.execute("SELECT user FROM `tabCRM Query Recipient` WHERE parent=%s LOCK IN SHARE MODE", (name,))
                self.assertTrue(cursor.fetchone())
            connection.rollback()
            frappe.db.rollback()
            self.assertTrue(frappe.db.exists("CRM Query Recipient", child))
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM `tabCRM Query Recipient` WHERE name=%s", (child,))
            connection.commit()
            self.assertTrue(frappe.db.exists("CRM Query Recipient", child))
            with patch.object(service, "_require_board_access"):
                frappe.session.user = self.sales
                with self.assertRaises(CrmApiException) as revoked:
                    service.export_opportunities({"savedQuery": {"id": name, "modified": service.to_iso_timestamp(when)}})
                self.assertEqual(revoked.exception.code, "NOT_FOUND")
        finally:
            frappe.db.rollback()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM `tabCRM Query Recipient` WHERE name=%s", (child,))
                cursor.execute("DELETE FROM `tabCRM Opportunity Saved Query` WHERE name=%s", (name,))
            connection.commit()
            connection.close()

    def test_reciprocal_copies_serialize_before_locking_either_source(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        # Commit only isolated raw query rows, never the test's User/Opportunity
        # fixtures. Existing built-in users stand in for two authenticated owners;
        # access and board data are covered separately above.
        frappe.db.rollback()
        connection = frappe.db._get_connection()
        site = frappe.local.site
        when = datetime(2030, 1, 1)
        prefix = "reciprocal-" + self.token
        sources = {"Administrator": prefix + "-a", "Guest": prefix + "-b"}
        names = [prefix + "-copy-a", prefix + "-copy-b"]
        first_locked, second_attempted, second_locked, release_first = (Event() for _ in range(4))
        original_lock = service._lock_query_writes

        def controlled_lock():
            if frappe.session.user == "Guest":
                second_attempted.set()
            original_lock()
            if frappe.session.user == "Administrator":
                first_locked.set()
                if not release_first.wait(timeout=15):
                    raise AssertionError("The first copy was never released")
            else:
                second_locked.set()

        def copy(user, source, name):
            frappe.init(site=site)
            frappe.connect()
            try:
                frappe.set_user(user)
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=15")
                result = service.save_opportunity_query(None, {
                    "name": name, "definition": self.definition,
                    "savedQuery": {"id": source, "modified": service.to_iso_timestamp(when)},
                })
                frappe.db.commit()
                return result
            finally:
                frappe.db.rollback()
                frappe.destroy()

        try:
            with connection.cursor() as cursor:
                for owner, source in sources.items():
                    recipient = "Guest" if owner == "Administrator" else "Administrator"
                    cursor.execute("INSERT INTO `tabCRM Opportunity Saved Query` (name,creation,modified,owner,modified_by,query_owner,query_name,definition) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                                   (source, when, when, owner, owner, owner, source, frappe.as_json(self.definition)))
                    cursor.execute("INSERT INTO `tabCRM Query Recipient` (name,creation,modified,owner,modified_by,parent,parenttype,parentfield,idx,user) VALUES (%s,%s,%s,%s,%s,%s,%s,'recipients',1,%s)",
                                   (source + "-r", when, when, owner, owner, source, service.SAVED_QUERY, recipient))
            connection.commit()
            context = {"options": {"sales": set(sources), "equipment": [], "regions": [], "markets": [], "regionParents": {}, "regionReady": True}}
            with patch.object(service, "_require_board_access"), patch.object(service, "_board_context", side_effect=lambda **_: deepcopy(context)), patch.object(service, "_lock_query_writes", side_effect=controlled_lock):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    first = executor.submit(copy, "Administrator", sources["Guest"], names[0])
                    try:
                        self.assertTrue(first_locked.wait(timeout=10))
                        second = executor.submit(copy, "Guest", sources["Administrator"], names[1])
                        self.assertTrue(second_attempted.wait(timeout=10))
                        self.assertFalse(second_locked.wait(timeout=0.2))
                    finally:
                        release_first.set()
                    copied = [first.result(timeout=30), second.result(timeout=30)]
            self.assertTrue(second_locked.is_set())
            self.assertEqual([row["owner"] for row in copied], ["Administrator", "Guest"])
            self.assertTrue(all(not row["recipients"] and not row["readOnly"] for row in copied))
            self.assertEqual(len({row["id"] for row in copied}), 2)
        finally:
            release_first.set()
            frappe.db.rollback()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM `tabCRM Query Recipient` WHERE parent IN (%s,%s)", tuple(sources.values()))
                cursor.execute("DELETE FROM `tabCRM Opportunity Saved Query` WHERE name IN (%s,%s) OR query_name IN (%s,%s)", (*sources.values(), *names))
            connection.commit()
            connection.close()
