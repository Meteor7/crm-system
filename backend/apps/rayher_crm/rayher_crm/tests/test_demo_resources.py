from datetime import datetime
from hashlib import sha256
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import demo_resources as service
from rayher_crm.services.evaluations import terminate_evaluation, update_evaluation_status
from rayher_crm.tests.test_evaluation_api import TestEvaluationApi


class TestDemoResources(FrappeTestCase):
    _user = TestEvaluationApi._user
    _approved_source = TestEvaluationApi._approved_source

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self._user("resource-manager@example.invalid", "CRM Manager")
        self.sales = self._user("resource-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("resource-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._user("resource-other-engineer@example.invalid", "CRM Engineer")
        self.account, self.request = self._approved_source("Resource" + frappe.generate_hash(length=6), self.sales, self.engineer)
        self.evaluation = self.request["evaluationId"]
        frappe.set_user(self.manager)
        self.resource = service.save_resource(self.resource_input())

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def resource_input(self, **overrides):
        return {"code": "Machine-" + frappe.generate_hash(length=6), "title": "Demo machine", "platform": "Inspection",
                "maintainer": self.engineer, "enabled": True, **overrides}

    def block_input(self, **overrides):
        return {"start": "2030-10-01T11:00:00+08:00", "end": "2030-10-01T13:00:00+08:00", "reason": "Maintenance", "status": "Active", **overrides}

    def schedule_input(self, **overrides):
        return {"resourceId": self.resource["id"], "start": "2030-10-01T10:00:00+08:00", "end": "2030-10-01T12:00:00+08:00", **overrides}

    def test_catalogue_authority_current_maintainer_cas_and_native_denial(self):
        doc = frappe.get_doc(service.RESOURCE, self.resource["id"])
        self.assertFalse(frappe.has_permission(service.RESOURCE, "read", doc=doc))
        self.assertFalse(frappe.has_permission(service.RESOURCE, "write", doc=doc))
        with self.assertRaises(CrmApiException):
            service.save_resource(self.resource_input(code=self.resource["code"]))
        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException):
            service.save_resource(self.resource_input())
        block = service.save_unavailability(self.resource["id"], self.block_input())
        edited = service.save_unavailability(self.resource["id"], self.block_input(reason="More detail"), block["id"], block["modified"])
        with self.assertRaises(CrmApiException) as stale:
            service.save_unavailability(self.resource["id"], self.block_input(), block["id"], block["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        frappe.set_user(self.other_engineer)
        with self.assertRaises(CrmApiException) as denied:
            service.save_unavailability(self.resource["id"], self.block_input(), edited["id"], edited["modified"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        frappe.set_user(self.sales)
        self.assertTrue(service.get_catalogue()["resources"])
        with self.assertRaises(frappe.PermissionError):
            service.save_unavailability(self.resource["id"], self.block_input())

    def test_overlaps_history_recovery_reschedule_and_notification_deduplication(self):
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 10, 1, 8)):
            frappe.set_user(self.engineer)
            initial = service.get_schedule(self.evaluation)
            self.assertEqual(initial["state"], "unknown")
            scheduled = service.save_schedule(self.evaluation, self.schedule_input(), initial["modified"])
            self.assertEqual(scheduled["state"], "available")
            block = service.save_unavailability(self.resource["id"], self.block_input())
            affected = service.get_schedule(self.evaluation)
            self.assertEqual((affected["state"], len(affected["history"])), ("blocked", 1))
            notices = frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Evaluation", "source_name": self.evaluation})
            self.assertGreater(notices, 0)
            block = service.save_unavailability(self.resource["id"], self.block_input(reason="Updated maintenance note"), block["id"], block["modified"])
            service.capture_impacts()
            self.assertEqual(frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Evaluation", "source_name": self.evaluation}), notices)
            resolved = service.save_unavailability(self.resource["id"], self.block_input(status="Resolved"), block["id"], block["modified"])
            current = service.get_schedule(self.evaluation)
            self.assertEqual(current["state"], "available")
            self.assertFalse(current["history"][0]["current"])
            service.save_unavailability(self.resource["id"], self.block_input(), block["id"], resolved["modified"])
            self.assertEqual(len(service.get_schedule(self.evaluation)["history"]), 2)
            moved = service.save_schedule(self.evaluation, self.schedule_input(start="2030-10-01T13:00:00+08:00", end="2030-10-01T14:00:00+08:00"), current["modified"])
            self.assertEqual(moved["state"], "available")
            self.assertTrue(all(not row["current"] for row in moved["history"]))
            self.assertTrue(frappe.db.exists("CRM Evaluation History", {"evaluation": self.evaluation, "event_type": "Resource Schedule"}))
            terminate_evaluation(self.evaluation, {"reason": "Cancelled test"}, moved["modified"])
            self.assertEqual(service.get_schedule(self.evaluation)["state"], "inactive")

    def test_source_scope_device_identity_unknown_and_stale_schedule(self):
        second = service.save_resource(self.resource_input())
        service.save_unavailability(second["id"], self.block_input())
        frappe.set_user(self.engineer)
        initial = service.get_schedule(self.evaluation)
        saved = service.save_schedule(self.evaluation, self.schedule_input(), initial["modified"])
        self.assertEqual(saved["state"], "available")
        with self.assertRaises(CrmApiException) as stale:
            service.save_schedule(self.evaluation, self.schedule_input(resourceId="", start=None, end=None), initial["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        for value in ({"start": "2030-10-01T10:00:00"}, {"end": "2030-10-01T09:00:00+08:00"}, {"start": "0001-01-01T10:00:00+08:00"}):
            with self.subTest(value=value), self.assertRaises(CrmApiException):
                service.save_schedule(self.evaluation, self.schedule_input(**value), saved["modified"])
        frappe.set_user(self.other_engineer)
        with self.assertRaises(CrmApiException):
            service.get_schedule(self.evaluation)
        frappe.set_user(self.sales)
        self.assertFalse(service.get_schedule(self.evaluation)["canWrite"])
        with self.assertRaises(frappe.PermissionError):
            service.save_schedule(self.evaluation, self.schedule_input(), saved["modified"])
        frappe.set_user(self.manager)
        result = service.warning_summary({})
        self.assertNotIn(self.evaluation, {row["id"] for row in result["items"]})
        cleared = service.save_schedule(self.evaluation, self.schedule_input(resourceId="", start=None, end=None), saved["modified"])
        self.assertEqual(cleared["state"], "unknown")
        self.assertIn(self.evaluation, {row["id"] for row in service.warning_summary({})["items"]})
        self.assertNotIn(self.evaluation, {row["id"] for row in service.warning_summary({"market": "Other"})["items"]})

    def test_retest_clears_old_booking_and_keeps_impact_history(self):
        scheduled = service.save_schedule(self.evaluation, self.schedule_input(), service.get_schedule(self.evaluation)["modified"])
        service.save_unavailability(self.resource["id"], self.block_input())
        # The status transition itself is exercised; reports are unrelated to resource assignment.
        frappe.db.set_value("CRM Evaluation", self.evaluation, {
            "status": "Customer Review", "wafer_preparation_status": "Completed", "test_preparation_status": "Completed",
        })
        current = service.get_schedule(self.evaluation)
        self.assertEqual(current["state"], "inactive")
        update_evaluation_status(self.evaluation, {"status": "Testing", "customerComment": "Run a new sample"}, current["modified"])
        retest = service.get_schedule(self.evaluation)
        self.assertEqual((retest["resourceId"], retest["start"], retest["end"], retest["state"]), ("", None, None, "unknown"))
        self.assertTrue(retest["history"])
        self.assertTrue(all(not row["current"] for row in retest["history"]))
        self.assertTrue(frappe.db.exists("CRM Evaluation History", {"evaluation": self.evaluation, "event_type": "Resource Schedule", "summary": ["like", "Cleared round%"]}))

    def test_native_user_permission_restricts_details_and_warning_rows(self):
        second_account, _ = self._approved_source("ResourceOther" + frappe.generate_hash(length=6), self.sales, self.engineer)
        frappe.set_user("Administrator")
        frappe.get_doc({"doctype": "User Permission", "user": self.manager, "allow": "Customer", "for_value": second_account, "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
        frappe.clear_cache(user=self.manager)
        frappe.set_user(self.manager)
        self.assertNotIn(self.evaluation, {row["id"] for row in service.warning_summary({})["items"]})
        with self.assertRaises(CrmApiException) as denied:
            service.get_schedule(self.evaluation)
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

    def test_disabled_resource_allows_rescheduling_but_not_new_assignment(self):
        saved = service.save_schedule(self.evaluation, self.schedule_input(), service.get_schedule(self.evaluation)["modified"])
        service.save_resource(self.resource_input(code=self.resource["code"], enabled=False), self.resource["id"], self.resource["modified"])
        moved = service.save_schedule(self.evaluation, self.schedule_input(start="2030-10-01T13:00:00+08:00", end="2030-10-01T14:00:00+08:00"), saved["modified"])
        self.assertEqual(moved["resourceId"], self.resource["id"])
        cleared = service.save_schedule(self.evaluation, self.schedule_input(resourceId="", start=None, end=None), moved["modified"])
        with self.assertRaises(CrmApiException) as denied:
            service.save_schedule(self.evaluation, self.schedule_input(), cleared["modified"])
        self.assertEqual(denied.exception.code, "VALIDATION_ERROR")

    def test_warning_sources_exclude_terminal_evaluations_before_enrichment(self):
        _, archived_request = self._approved_source("Archived" + frappe.generate_hash(length=6), self.sales, self.engineer)
        archived = archived_request["evaluationId"]
        frappe.db.set_value("CRM Evaluation", archived, {"status": "Accepted", "demo_resource": self.resource["id"]})
        frappe.set_user(self.manager)
        with patch.object(service, "enriched", wraps=service.enriched) as enrich:
            summary = service.warning_summary({})
        loaded = {row["name"] for call in enrich.call_args_list for row in call.args[0]}
        self.assertIn(self.evaluation, loaded)
        self.assertNotIn(archived, loaded)
        self.assertIn(self.evaluation, {row["id"] for row in summary["items"]})
        self.assertNotIn(archived, {row["id"] for row in summary["items"]})
        self.assertEqual(service.get_schedule(archived)["state"], "inactive")

    def test_enrichment_batches_linked_facts_and_preserves_cancellation(self):
        _, cancelled_request = self._approved_source("Cancelled" + frappe.generate_hash(length=6), self.sales, self.engineer)
        cancelled = cancelled_request["evaluationId"]
        cancelled_source = frappe.db.get_value("CRM Evaluation", cancelled, "demo_request")
        frappe.db.set_value("CRM Demo Request", cancelled_source, "status", "Cancelled")
        inputs = frappe.get_all("CRM Evaluation", filters={"name": ["in", [self.evaluation, cancelled]]}, fields=service.EVALUATION_FIELDS.split())
        # The same linked records across a large result still take only three
        # source batches, rather than three lookups for every returned row.
        with patch("frappe.get_all", wraps=frappe.get_all) as read:
            rows = service.enriched(inputs * 100)
        linked_reads = [call for call in read.call_args_list if call.args and call.args[0] in {"CRM Demo Request", "Customer", "CRM Opportunity"}]
        self.assertEqual(len(linked_reads), 3)
        active = next(row for row in rows if row["name"] == self.evaluation)
        self.assertEqual((active["owner"], active["region"], active["market"]), (self.sales, "East China", "Frontend"))
        self.assertTrue(active["equipment"])
        inactive = next(row for row in rows if row["name"] == cancelled)
        self.assertEqual(service.resource_state(inactive, [], datetime(2030, 10, 1))["state"], "inactive")
        customer_call = next(call for call in linked_reads if call.args[0] == "Customer")
        self.assertEqual(customer_call.kwargs["filters"]["name"][1], [self.account])

    def test_capture_locks_active_sources_without_locking_archived_schedules(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        names = ["CRM-EVAL-RESOURCE-LOCK-" + frappe.generate_hash(length=10) for _ in range(2)]
        connection = frappe.db._get_connection()
        try:
            # Only these raw isolated rows are committed by the second connection;
            # the ordinary account/request fixtures stay in this test's rollback.
            with connection.cursor() as cursor:
                for name, status in zip(names, ("Accepted", "Testing")):
                    cursor.execute("INSERT INTO `tabCRM Evaluation` (name, status, demo_resource) VALUES (%s,%s,%s)",
                                   (name, status, self.resource["id"]))
            connection.commit()
            service.capture_impacts()
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM `tabCRM Evaluation` WHERE name=%s FOR UPDATE NOWAIT", (names[0],))
                self.assertEqual(cursor.fetchone()[0], names[0])
                with self.assertRaises(Exception) as held:
                    cursor.execute("SELECT name FROM `tabCRM Evaluation` WHERE name=%s FOR UPDATE NOWAIT", (names[1],))
                self.assertEqual(held.exception.args[0], 1205)
        finally:
            frappe.db.rollback()
            connection.rollback()
            with connection.cursor() as cursor:
                for name in names:
                    cursor.execute("DELETE FROM `tabCRM Evaluation` WHERE name=%s", (name,))
            connection.commit()
            connection.close()

    def test_status_entrypoints_hold_catalogue_before_the_evaluation_lock(self):
        from rayher_crm.services import evaluations

        class ReachedEvaluationLock(Exception):
            pass

        self.assertTrue(frappe.local.site.endswith(".test"))
        # setUp creates a resource and already holds the mutex. Release those
        # uncommitted fixtures so each real entrypoint must acquire it itself.
        frappe.db.rollback()
        connection = frappe.db._get_connection()
        lock_sql = "SELECT name FROM `tabDocType` WHERE name=%s FOR UPDATE NOWAIT"

        def reached_parent(*args, **kwargs):
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as held:
                    cursor.execute(lock_sql, (service.RESOURCE,))
                self.assertEqual(held.exception.args[0], 1205)
            raise ReachedEvaluationLock()

        try:
            # Access checks are covered by the lifecycle tests. Stop exactly at
            # the parent-lock boundary, after exercising the real mutex SQL.
            with patch.object(evaluations, "assert_capability"), patch.object(evaluations, "_require_evaluation"), patch.object(evaluations, "lock_document", side_effect=reached_parent):
                operations = (
                    lambda: evaluations.update_evaluation_status("unused", {"status": "Testing"}, "unused"),
                    lambda: evaluations.terminate_evaluation("unused", {"reason": "Stopped"}, "unused"),
                    lambda: evaluations.complete_evaluation_preparation("unused", "wafer", "unused"),
                )
                for operation in operations:
                    with self.assertRaises(ReachedEvaluationLock):
                        operation()
                    frappe.db.rollback()
                    connection.rollback()
                    with connection.cursor() as cursor:
                        cursor.execute(lock_sql, (service.RESOURCE,))
                        self.assertEqual(cursor.fetchone()[0], service.RESOURCE)
                    connection.rollback()
        finally:
            frappe.db.rollback()
            connection.rollback()
            connection.close()

    def test_capture_dedupes_committed_rows_outside_its_repeatable_read_snapshot(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        now = datetime(2030, 10, 1, 8)
        with patch("frappe.utils.now_datetime", return_value=now):
            # Prepare sources without save_schedule's locking history response:
            # that response locks the empty impact range until this transaction
            # ends, preventing the second connection from seeding a prior capture.
            # Schedule writes themselves are covered by the lifecycle tests above.
            frappe.db.set_value("CRM Evaluation", self.evaluation, {
                "demo_resource": self.resource["id"], "resource_start": datetime(2030, 10, 1, 10),
                "resource_end": datetime(2030, 10, 1, 12), "resource_revision": 1,
            })
            with patch.object(service, "capture_impacts"):
                service.save_unavailability(self.resource["id"], self.block_input())
            impact = service.get_schedule(self.evaluation)["impacts"][0]
            recipients = {self.manager, self.sales, self.engineer}
            keys = {user: sha256(f"demo-resource:{impact['key']}:{user}".encode()).hexdigest() for user in recipients}
            # Establish the read view, then use a second MariaDB connection to
            # commit the rows a preceding capture would have written. The source
            # fixtures remain uncommitted, so this test never commits shared data.
            self.assertFalse(frappe.db.exists(service.IMPACT, impact["key"]))
            self.assertFalse(frappe.db.exists("CRM Notification Event", {"dedupe_key": keys[self.manager]}))
            connection = frappe.db._get_connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("INSERT INTO `tabCRM Demo Resource Impact` (name, impact_key, evaluation, resource, unavailability, detected_at, snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                   (impact["key"], impact["key"], self.evaluation, self.resource["id"], impact["unavailabilityId"], now, frappe.as_json(impact)))
                    for user, key in keys.items():
                        cursor.execute("INSERT INTO `tabCRM Notification Event` (name, dedupe_key, recipient_user, source_doctype, source_name) VALUES (%s,%s,%s,'CRM Evaluation',%s)",
                                       (key, key, user, self.evaluation))
                connection.commit()
                self.assertFalse(frappe.db.exists(service.IMPACT, impact["key"]))
                self.assertFalse(frappe.db.exists("CRM Notification Event", {"dedupe_key": keys[self.manager]}))
                with patch.object(service, "active_crm_users", return_value={self.manager}), patch.object(service, "notify_if_reachable") as notify:
                    service.capture_impacts()
                    notify.assert_not_called()
                # A write response must expose current committed impact history,
                # even though its transaction still has the earlier read view.
                refreshed = service.get_schedule(self.evaluation, for_update=True)
                self.assertEqual(refreshed["history"][0]["id"], impact["key"])
            finally:
                frappe.db.rollback()
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM `tabCRM Demo Resource Impact` WHERE name=%s", (impact["key"],))
                    for key in keys.values():
                        cursor.execute("DELETE FROM `tabCRM Notification Event` WHERE name=%s", (key,))
                connection.commit()
                connection.close()
