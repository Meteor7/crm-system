from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.sites import create_site
from rayher_crm.services.opportunities import create_strategy_opportunity, get_strategy_opportunity, list_strategy_opportunities, update_strategy_opportunity
from rayher_crm.services.probability_recovery import record_action, save_plan


class TestProbabilityRecovery(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("sales", "CRM Sales")
        self.other = self._user("other", "CRM Sales")
        self.manager = self._user("manager", "CRM Manager")
        self.engineer = self._user("engineer", "CRM Engineer")
        frappe.set_user(self.sales)
        account = create_account({"name": f"Recovery {frappe.generate_hash(length=8)}", "shortName": "Recovery",
                                  "segment": "Frontend", "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        site = create_site(account["id"], {"name": "Recovery Fab", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产"})
        self.opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": "Recovery inspection", "owner": self.sales,
            "amount": "100.00", "amountCny": "100.00", "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "probabilityLevel": "committed", "qualificationConfirmed": True,
        })

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, label, role):
        email = f"crm-recovery-{label}@example.invalid"
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": label, "enabled": 1,
                            "send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
        return email

    def _lower(self):
        return update_strategy_opportunity(self.opportunity["id"], {
            "probabilityLevel": "upside", "probabilityReason": "Budget delayed", "probabilityActionPlan": "Meet procurement",
        }, self.opportunity["modified"])

    def _save(self, opportunity, event, plan, modified=None):
        return save_plan(opportunity["id"], event["id"], {
            "plan": plan, "recoveryModified": modified if modified is not None else event["recovery"]["modified"],
        }, opportunity["modified"])

    def _act(self, opportunity, event, action="Met procurement and agreed the budget date", modified=None):
        return record_action(opportunity["id"], event["id"], {
            "actionTaken": action, "recoveryModified": modified or event["recovery"]["modified"],
        }, opportunity["modified"])

    def _notice_filters(self, opportunity):
        return {"source_doctype": "CRM Opportunity Probability History",
                "route": ["like", f"/opportunities/{opportunity['id']}?probabilityEvent=%"]}

    def test_manager_can_archive_a_downgraded_opportunity_which_keeps_its_plan_and_inbox_history(self):
        from rayher_crm.services.opportunities import archive_strategy_opportunity, unarchive_strategy_opportunity
        from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_EDIT
        from rayher_crm.services.notifications import list_notifications
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        notifications = frappe.get_all("CRM Notification Event", filters=self._notice_filters(opportunity), pluck="name")
        self.assertTrue(notifications)
        frappe.set_user(self.manager)
        archived = archive_strategy_opportunity(opportunity["id"])
        self.assertTrue(frappe.db.exists("CRM Opportunity", opportunity["id"]))
        self.assertTrue(frappe.db.exists("CRM Probability Recovery", {"opportunity": opportunity["id"]}))
        self.assertEqual(frappe.db.count("CRM Notification Event", {"name": ["in", notifications]}), len(notifications))
        # The notices stay in the inbox: the record they lead to still opens, read-only.
        self.assertTrue(any(event["id"] in row["route"] for row in list_notifications(page_size=200)["items"]))
        # The plan takes no edit and no action while the Opportunity is archived.
        for call in (lambda: self._save(archived, event, "Call the CFO"), lambda: self._act(archived, event)):
            with self.assertRaises(CrmApiException) as refused:
                call()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_EDIT))
        restored = unarchive_strategy_opportunity(opportunity["id"])
        self.assertEqual(self._save(restored, event, "Call the CFO")["plan"], "Call the CFO")

    def test_plan_edit_stays_pending_and_only_owner_action_closes_this_event(self):
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        frappe.set_user(self.manager)
        edited = self._save(opportunity, event, "Revised plan")
        self.assertEqual(edited["state"], "pending")
        with self.assertRaises(CrmApiException) as denied:
            self._act(opportunity, event, modified=edited["modified"])
        self.assertEqual(denied.exception.code, "PERMISSION_DENIED")
        frappe.set_user(self.sales)
        acted = self._act(opportunity, event, modified=edited["modified"])
        self.assertEqual((acted["state"], acted["actedBy"]), ("handled", self.sales))
        self.assertTrue(acted["actedAt"])
        self.assertEqual(acted["history"][0]["kind"], "ActionRecorded")
        self.assertEqual(acted["history"][0]["plan"], "Revised plan")
        self.assertEqual(acted["history"][0]["actionTaken"], acted["actionTaken"])
        # Clarification of a plan preserves the action audit and does not reopen it.
        updated = self._save(opportunity, event, "Clarified after meeting", acted["modified"])
        self.assertEqual((updated["state"], updated["actedAt"], updated["actionTaken"]),
                         ("handled", acted["actedAt"], acted["actionTaken"]))
        again = update_strategy_opportunity(opportunity["id"], {"probabilityLevel": "pipeline", "probabilityReason": "New delay",
                                           "probabilityActionPlan": "Arrange escalation"}, opportunity["modified"])
        self.assertEqual([row["recovery"]["state"] for row in again["probabilityHistory"] if row["recovery"]], ["pending", "handled"])

    def test_action_validation_conflicts_retries_and_audit_failure_do_not_clear_warning(self):
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        for action in ("", "  ", [], "x" * 4001):
            with self.assertRaises(CrmApiException) as invalid:
                self._act(opportunity, event, action)
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        with patch("rayher_crm.services.probability_recovery._append_revision", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self._act(opportunity, event)
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["probabilityHistory"][0]["recovery"], event["recovery"])
        first = self._act(opportunity, event)
        with self.assertRaises(CrmApiException) as stale:
            self._act(opportunity, event)
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        with self.assertRaises(CrmApiException) as handled:
            self._act(opportunity, event, modified=first["modified"])
        self.assertEqual(handled.exception.code, "INVALID_TRANSITION")
        self.assertEqual(frappe.db.count("CRM Probability Recovery Revision", {"recovery": first["id"], "kind": "ActionRecorded"}), 1)

    def test_downgrade_notifications_are_manager_scoped_and_atomic(self):
        from rayher_crm.services.notifications import active_crm_users
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        notifications = frappe.get_all("CRM Notification Event", filters=self._notice_filters(opportunity),
                                       fields=["recipient_user", "actor", "route", "dedupe_key"])
        self.assertEqual({row.recipient_user for row in notifications}, set(active_crm_users("Manager")))
        self.assertTrue(all(row.actor == self.sales and event["id"] in row.route for row in notifications))
        self.assertEqual(len(notifications), len({row.dedupe_key for row in notifications}))
        with self.assertRaises(CrmApiException):
            self._lower()
        self._save(opportunity, event, "Different plan")
        self.assertEqual(frappe.db.count("CRM Notification Event", self._notice_filters(opportunity)), len(notifications))
        with patch("rayher_crm.services.probability_recovery.notify_if_reachable", side_effect=RuntimeError("notification unavailable")):
            with self.assertRaises(RuntimeError):
                update_strategy_opportunity(opportunity["id"], {"probabilityLevel": "pipeline", "probabilityReason": "New delay",
                                            "probabilityActionPlan": "Arrange escalation"}, opportunity["modified"])
        current = get_strategy_opportunity(opportunity["id"])
        self.assertEqual(current["probabilityLevel"], "upside")
        self.assertEqual(len(current["probabilityHistory"]), 2)
        self.assertEqual(frappe.db.count("CRM Probability Recovery", {"opportunity": current["id"]}), 1)

    def test_notification_candidates_must_pass_current_manager_scope(self):
        with patch("rayher_crm.services.probability_recovery.active_crm_users", return_value=[self.manager]), \
             patch("rayher_crm.services.probability_recovery.has_crm_permission", return_value=False):
            opportunity = self._lower()
        self.assertFalse(frappe.db.exists("CRM Notification Event", self._notice_filters(opportunity)))

    def test_partial_manager_delivery_failure_rolls_back_earlier_notifications(self):
        from rayher_crm.services.notifications import create_notification
        second_manager = self._user("manager-second", "CRM Manager")
        def deliver(**kwargs):
            if kwargs["recipient"] == second_manager:
                raise RuntimeError("second delivery failed")
            return create_notification(**kwargs)
        with patch("rayher_crm.services.probability_recovery.active_crm_users", return_value=[self.manager, second_manager]), \
             patch("rayher_crm.services.probability_recovery.notify_if_reachable", side_effect=deliver):
            with self.assertRaises(RuntimeError):
                self._lower()
        self.assertFalse(frappe.db.exists("CRM Notification Event", self._notice_filters(self.opportunity)))
        current = get_strategy_opportunity(self.opportunity["id"])
        self.assertEqual(current["probabilityLevel"], "committed")
        self.assertEqual(len(current["probabilityHistory"]), 1)
        self.assertFalse(frappe.db.exists("CRM Probability Recovery", {"opportunity": current["id"]}))

    def test_review_loads_actual_recovery_and_keeps_handled_history(self):
        from rayher_crm.services.cockpit import get_details
        from rayher_crm.services.notifications import list_notifications
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        query = {"period": "year", "anchor": frappe.utils.nowdate(), "sales": self.sales, "pageSize": 200}
        frappe.set_user(self.manager)
        rows = get_details({**query, "metric": "downgrade"})["items"]
        row = next(row for row in rows if row["eventId"] == event["id"])
        self.assertEqual((row["recovery"]["plan"], row["currentOwner"]), ("Meet procurement", self.sales))
        notices = list_notifications(page_size=200)
        self.assertTrue(any(event["id"] in row["route"] for row in notices["items"]))
        frappe.set_user(self.sales)
        self._act(opportunity, event)
        frappe.set_user(self.manager)
        self.assertNotIn(event["id"], {row["eventId"] for row in get_details({**query, "metric": "downgrade"})["items"]})
        historical = next(row for row in get_details({**query, "metric": "downgrade_history"})["items"] if row["eventId"] == event["id"])
        self.assertEqual(historical["recovery"]["state"], "handled")
        self.assertEqual(historical["recovery"]["actedBy"], self.sales)

    def test_upgrade_unchanged_initial_and_legacy_backfill_do_not_notify_managers(self):
        self.assertFalse(frappe.db.exists("CRM Notification Event", self._notice_filters(self.opportunity)))
        opportunity = self._lower()
        count = frappe.db.count("CRM Notification Event", self._notice_filters(opportunity))
        raised = update_strategy_opportunity(opportunity["id"], {"probabilityLevel": "committed"}, opportunity["modified"])
        update_strategy_opportunity(opportunity["id"], {"title": "Unchanged level"}, raised["modified"])
        self.assertEqual(frappe.db.count("CRM Notification Event", self._notice_filters(opportunity)), count)

    def test_downgrade_requires_plan_without_partial_writes(self):
        for value in (None, "", "  ", [], "x" * 4001):
            with self.assertRaises(CrmApiException) as error:
                update_strategy_opportunity(self.opportunity["id"], {
                    "probabilityLevel": "upside", "probabilityReason": "Budget delayed", "probabilityActionPlan": value,
                }, self.opportunity["modified"])
            self.assertEqual(error.exception.code, "VALIDATION_ERROR")
            current = get_strategy_opportunity(self.opportunity["id"])
            self.assertEqual(current["modified"], self.opportunity["modified"])
            self.assertEqual(current["probabilityLevel"], "committed")
            self.assertEqual(len(current["probabilityHistory"]), 1)
            self.assertEqual(frappe.db.count("CRM Probability Recovery", {"opportunity": current["id"]}), 0)

    def test_manager_can_edit_plan_without_rewriting_event_and_noop_does_not_append(self):
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        self.assertEqual(event["recovery"]["history"][0]["actor"], self.sales)
        frappe.set_user(self.manager)
        result = self._save(opportunity, event, "  Meet the technical buyer too  ")
        self.assertEqual(result["plan"], "Meet the technical buyer too")
        self.assertEqual([row["plan"] for row in result["history"]], ["Meet the technical buyer too", "Meet procurement"])
        self.assertEqual(result["history"][0]["actor"], self.manager)
        notice_filters = {"source_doctype": "CRM Probability Recovery Revision",
            "source_name": result["history"][0]["id"], "recipient_user": self.sales}
        self.assertEqual(frappe.db.count("CRM Notification Event", notice_filters), 1)
        self.assertNotEqual(result["modified"], event["recovery"]["modified"])
        same = self._save(opportunity, event, result["plan"], result["modified"])
        self.assertEqual(same, result)
        self.assertEqual(frappe.db.count("CRM Notification Event", notice_filters), 1)
        current = get_strategy_opportunity(opportunity["id"])["probabilityHistory"][0]
        for field in ("id", "from", "to", "reason", "actor", "at"):
            self.assertEqual(current[field], event[field])

    def test_manager_plan_notice_follows_current_owner_and_stale_retry_does_not_duplicate(self):
        from urllib.parse import quote

        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        frappe.set_user("Administrator")
        frappe.db.set_value("Customer", opportunity["accountId"], "custom_crm_visibility", "Public")
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "opportunity_owner", self.other)
        frappe.set_user(self.manager)
        current = get_strategy_opportunity(opportunity["id"])
        result = self._save(current, event, "Follow up with the new owner")
        revision = result["history"][0]["id"]
        notices = frappe.get_all("CRM Notification Event", filters={
            "source_doctype": "CRM Probability Recovery Revision", "source_name": revision,
        }, fields=["recipient_user", "route", "dedupe_key"])
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].recipient_user, self.other)
        self.assertEqual(notices[0].route,
            f"/opportunities/{quote(opportunity['id'], safe='')}?probabilityEvent={quote(event['id'], safe='')}")
        self.assertTrue(notices[0].dedupe_key)
        with self.assertRaises(CrmApiException) as stale:
            self._save(current, event, "Stale concurrent plan")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        self.assertEqual(frappe.db.count("CRM Notification Event", {
            "source_doctype": "CRM Probability Recovery Revision", "source_name": revision,
        }), 1)
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["probabilityHistory"][0]["recovery"], result)

    def test_plan_notification_failure_rolls_back_plan_and_revision_but_unreachable_owner_is_skipped(self):
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        frappe.set_user(self.manager)
        with patch("rayher_crm.services.notifications.create_notification", side_effect=RuntimeError("notification unavailable")):
            with self.assertRaises(RuntimeError):
                self._save(opportunity, event, "Should roll back")
        current = get_strategy_opportunity(opportunity["id"])["probabilityHistory"][0]["recovery"]
        self.assertEqual(current, event["recovery"])
        frappe.db.set_value("User", self.sales, "enabled", 0)
        try:
            result = self._save(opportunity, event, "Owner temporarily unavailable")
            self.assertEqual(result["plan"], "Owner temporarily unavailable")
            self.assertFalse(frappe.db.exists("CRM Notification Event", {
                "source_doctype": "CRM Probability Recovery Revision", "source_name": result["history"][0]["id"],
            }))
        finally:
            frappe.db.set_value("User", self.sales, "enabled", 1)

    def test_lists_batch_recovery_queries_and_keep_the_correct_event_mapping(self):
        first = self._lower()
        copied = frappe.copy_doc(frappe.get_doc("CRM Opportunity", first["id"]))
        copied.probability_level = "committed"
        copied.insert(ignore_permissions=True)
        second = get_strategy_opportunity(copied.name)
        second = update_strategy_opportunity(second["id"], {"probabilityLevel": "pipeline", "probabilityReason": "Second delay",
                                            "probabilityActionPlan": "Second plan"}, second["modified"])
        real_get_all = frappe.get_all
        for query in (None, {"accountId": first["accountId"], "pageSize": 100}):
            with patch("frappe.get_all", wraps=real_get_all) as reads:
                result = list_strategy_opportunities(query)
            rows = result if query is None else result[0]
            by_id = {row["id"]: row for row in rows}
            self.assertEqual(by_id[first["id"]]["probabilityHistory"][0]["recovery"]["plan"], "Meet procurement")
            self.assertEqual(by_id[second["id"]]["probabilityHistory"][0]["recovery"]["plan"], "Second plan")
            for doctype in ("CRM Probability Recovery", "CRM Probability Recovery Revision"):
                self.assertEqual(sum(call.args[0] == doctype for call in reads.call_args_list if call.args), 1)

    def test_stale_versions_and_retries_never_duplicate(self):
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        self._save(opportunity, event, "Changed plan")
        with self.assertRaises(CrmApiException) as stale:
            self._save(opportunity, event, "Stale plan")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        with self.assertRaises(CrmApiException) as retry:
            self._lower()
        self.assertEqual(retry.exception.code, "VERSION_CONFLICT")
        self.assertEqual(frappe.db.count("CRM Probability Recovery", {"opportunity": opportunity["id"]}), 1)
        self.assertEqual(frappe.db.count("CRM Probability Recovery Revision", {"opportunity": opportunity["id"]}), 2)
        with self.assertRaises(CrmApiException) as missing:
            save_plan(opportunity["id"], event["id"], {"plan": "x", "recoveryModified": event["recovery"]["modified"]}, None)
        self.assertEqual(missing.exception.code, "VALIDATION_ERROR")

    def test_legacy_plan_creation_is_explicit_and_cannot_overwrite_a_racing_creation(self):
        event = frappe.get_doc({"doctype": "CRM Opportunity Probability History", "opportunity": self.opportunity["id"],
                                "from_level": "upside", "to_level": "pipeline", "reason": "Legacy reason",
                                "actor": self.sales, "changed_at": frappe.utils.now_datetime()}).insert(ignore_permissions=True)
        current = get_strategy_opportunity(self.opportunity["id"])
        self.assertIsNone(next(row for row in current["probabilityHistory"] if row["id"] == event.name)["recovery"])
        payload = {"plan": "Recorded at review", "recoveryModified": None}
        first = save_plan(current["id"], event.name, payload, current["modified"])
        self.assertEqual(len(first["history"]), 1)
        with self.assertRaises(CrmApiException) as race:
            save_plan(current["id"], event.name, payload, current["modified"])
        self.assertEqual(race.exception.code, "VERSION_CONFLICT")

    def test_manager_legacy_plan_creation_does_not_send_an_update_notice(self):
        event = frappe.get_doc({
            "doctype": "CRM Opportunity Probability History", "opportunity": self.opportunity["id"],
            "from_level": "upside", "to_level": "pipeline", "reason": "Legacy reason",
            "actor": self.sales, "changed_at": frappe.utils.now_datetime(),
        }).insert(ignore_permissions=True)
        frappe.set_user(self.manager)
        result = save_plan(self.opportunity["id"], event.name, {
            "plan": "First recorded plan", "recoveryModified": None,
        }, self.opportunity["modified"])
        self.assertEqual(len(result["history"]), 1)
        self.assertEqual(result["history"][0]["kind"], "Created")
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM Probability Recovery Revision", "source_name": result["history"][0]["id"],
        }))

    def test_non_downgrades_cannot_get_a_plan_and_new_downgrades_keep_separate_plans(self):
        initial = self.opportunity["probabilityHistory"][0]
        with self.assertRaises(CrmApiException) as invalid:
            save_plan(self.opportunity["id"], initial["id"], {"plan": "No", "recoveryModified": None}, self.opportunity["modified"])
        self.assertEqual(invalid.exception.code, "INVALID_TRANSITION")
        first = self._lower()
        second = update_strategy_opportunity(first["id"], {"probabilityLevel": "pipeline", "probabilityReason": "Delayed again",
                                            "probabilityActionPlan": "Agree a phased delivery"}, first["modified"])
        self.assertEqual([row["recovery"]["plan"] for row in second["probabilityHistory"] if row["recovery"]],
                         ["Agree a phased delivery", "Meet procurement"])

    def test_legacy_creation_conflicts_against_a_stale_repeatable_read_snapshot(self):
        # Two real DB connections: the losing request has already read the parent
        # before the winner commits, exactly as the authorization-before-lock path does.
        from rayher_crm.permissions.scope import OPPORTUNITY_CHILD_DOCTYPES
        self.assertTrue(frappe.local.site.endswith(".test"))
        event = frappe.get_doc({"doctype": "CRM Opportunity Probability History", "opportunity": self.opportunity["id"],
                                "from_level": "upside", "to_level": "pipeline", "reason": "Legacy race",
                                "actor": self.sales, "changed_at": frappe.utils.now_datetime()}).insert(ignore_permissions=True)
        event_id, opportunity_id, version = event.name, self.opportunity["id"], self.opportunity["modified"]
        primary = frappe.local.db
        primary.commit()
        try:
            with self.secondary_connection():
                frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                self.assertEqual(get_strategy_opportunity(opportunity_id)["modified"], version)
                self.assertFalse(frappe.db.get_value("CRM Probability Recovery", {"probability_change": event_id}, "name"))
                with self.primary_connection():
                    winner = save_plan(opportunity_id, event_id, {"plan": "Winner", "recoveryModified": None}, version)
                    frappe.db.commit()
                # A normal read is still stale. The service must use a current read.
                self.assertFalse(frappe.db.get_value("CRM Probability Recovery", {"probability_change": event_id}, "name"))
                with self.assertRaises(CrmApiException) as conflict:
                    save_plan(opportunity_id, event_id, {"plan": "Loser", "recoveryModified": None}, version)
                self.assertEqual(conflict.exception.code, "VERSION_CONFLICT")
                frappe.db.rollback()
            frappe.local.db = primary
            primary.rollback()
            self.assertEqual(frappe.db.get_value("CRM Probability Recovery", winner["id"], "plan"), "Winner")
            self.assertEqual(frappe.db.count("CRM Probability Recovery Revision", {"recovery": winner["id"]}), 1)
        finally:
            frappe.local.db = primary
            primary.rollback()
            for doctype in OPPORTUNITY_CHILD_DOCTYPES:
                frappe.db.delete(doctype, {"opportunity": opportunity_id})
            frappe.db.delete("CRM Opportunity", {"name": opportunity_id})
            primary.commit()

    def test_initial_plan_and_revision_failures_roll_back_business_changes(self):
        with patch("rayher_crm.services.probability_recovery._append_revision", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self._lower()
        current = get_strategy_opportunity(self.opportunity["id"])
        self.assertEqual(current["probabilityLevel"], "committed")
        self.assertEqual(current["modified"], self.opportunity["modified"])
        self.assertEqual(len(current["probabilityHistory"]), 1)
        self.assertFalse(frappe.db.exists("CRM Probability Recovery", {"opportunity": current["id"]}))
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        with patch("rayher_crm.services.probability_recovery._append_revision", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self._save(opportunity, event, "Must not remain")
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["probabilityHistory"][0]["recovery"], event["recovery"])

    def test_other_sales_engineer_and_cross_parent_event_are_rejected(self):
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        frappe.set_user(self.other)
        with self.assertRaises(CrmApiException) as denied:
            self._save(opportunity, event, "Not authorized")
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            self._save(opportunity, event, "Not authorized")
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as missing:
            save_plan(opportunity["id"], "another-event", {"plan": "x", "recoveryModified": None}, opportunity["modified"])
        self.assertEqual(missing.exception.code, "NOT_FOUND")

    def test_generic_access_cannot_mutate_audit_or_plan(self):
        from frappe.client import set_value
        opportunity = self._lower()
        recovery = opportunity["probabilityHistory"][0]["recovery"]
        for user in (self.sales, self.manager, self.engineer):
            frappe.set_user(user)
            for doctype, name, field in (("CRM Probability Recovery", recovery["id"], "plan"),
                                         ("CRM Probability Recovery Revision", recovery["history"][0]["id"], "plan")):
                with self.assertRaises(frappe.PermissionError):
                    set_value(doctype, name, field, "Unaudited mutation")

    def test_transferred_owner_can_maintain_public_recovery_without_site_access(self):
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        frappe.db.set_value("Customer", opportunity["accountId"], "custom_crm_visibility", "Public")
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "opportunity_owner", self.other)
        frappe.set_user(self.other)
        current = get_strategy_opportunity(opportunity["id"])
        self.assertTrue(current["siteRestricted"])
        self.assertEqual(current["siteId"], "")
        result = self._save(current, event, "New owner follow-up")
        self.assertEqual(result["history"][0]["actor"], self.other)
        frappe.set_user(self.sales)
        # Transferring a Public opportunity removes the former owner's scope.
        with self.assertRaises(CrmApiException) as denied:
            self._save(current, event, "Former owner's edit", result["modified"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

    def test_private_account_guards_custom_and_native_recovery_reads(self):
        from frappe.client import get as get_document
        opportunity = self._lower()
        event = opportunity["probabilityHistory"][0]
        recovery = event["recovery"]
        frappe.db.set_value("Customer", opportunity["accountId"], "custom_crm_visibility", "Private")
        frappe.db.set_value("CRM Opportunity", opportunity["id"], "opportunity_owner", self.other)
        frappe.set_user(self.other)
        with self.assertRaises(CrmApiException) as denied:
            get_strategy_opportunity(opportunity["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException):
            self._save(opportunity, event, "Private edit")
        for doctype, name in (("CRM Probability Recovery", recovery["id"]),
                              ("CRM Probability Recovery Revision", recovery["history"][0]["id"])):
            self.assertEqual(frappe.get_list(doctype, filters={"name": name}, pluck="name"), [])
            with self.assertRaises(frappe.PermissionError):
                get_document(doctype, name)
        frappe.set_user(self.manager)
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["probabilityHistory"][0]["recovery"], recovery)
