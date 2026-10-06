"""Warnings handling (#27): next steps, S6 actions, Manager thresholds and the daily notices."""
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import cockpit, cockpit_settings, warning_handling, warning_notifications
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.sites import create_site
from rayher_crm.services.warning_notifications import send_warning_notifications
from rayher_crm.setup import indexes
from rayher_crm.tests import test_quotation_api

NOW = datetime(2030, 3, 13, 12)
COVERAGE = {"crm_cockpit_history_complete_from": {k: "2000-01-01" for k in ("stage", "fields", "actions", "po", "probability")}}


class TestWarningHandling(FrappeTestCase):
    # The quotation fixtures, bound to this class (inheriting would rerun every quotation test).
    _opportunity = test_quotation_api.TestQuotationApi._opportunity
    _ready_quotation = test_quotation_api.TestQuotationApi._ready_quotation
    _publish = test_quotation_api.TestQuotationApi._publish

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("sales", "CRM Sales")
        self.other_sales = self._user("other-sales", "CRM Sales")
        self.manager = self._user("manager", "CRM Manager")
        self._reset_settings()
        frappe.set_user(self.sales)
        account = create_account({"name": f"Warn {frappe.generate_hash(length=8)}", "shortName": "Warn", "segment": "Frontend",
                                  "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        site = create_site(account["id"], {"name": "Warn Fab", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产"})
        self.opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": "Warn inspection", "owner": self.sales,
            "amount": "100.00", "amountCny": "100.00", "poDate": "2030-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "probabilityLevel": "committed", "qualificationConfirmed": True,
        })
        frappe.set_user(self.manager)
        self.patches = [patch("frappe.utils.now_datetime", return_value=NOW), patch.dict(frappe.conf, {**COVERAGE, "crm_cockpit_stage6_no_po_days": 30})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        frappe.set_user("Administrator")
        self._reset_settings()
        frappe.set_user(self.original_user)
        super().tearDown()

    def _reset_settings(self):
        frappe.db.delete("Singles", {"doctype": cockpit_settings.SETTINGS})
        frappe.clear_document_cache(cockpit_settings.SETTINGS, cockpit_settings.SETTINGS)

    def _user(self, label, role):
        email = label if "@" in label else f"crm-warning-handling-{label}@example.invalid"
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": label.split("@")[0], "enabled": 1,
                            "send_welcome_email": 0, "roles": [{"role": role}]}).insert(ignore_permissions=True)
        return email

    def _action(self, due, owner=None):
        return frappe.get_doc({"doctype": "CRM Opportunity Action", "opportunity": self.opportunity["id"], "title": "Send revised layout",
                               "action_owner": owner or self.sales, "due": due, "status": "Open"}).insert(ignore_permissions=True).name

    def _to_stage6(self, days):
        entered = NOW - timedelta(days=days)
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "stage", "internal_validation", update_modified=False)
        return frappe.get_doc({"doctype": "CRM Opportunity Stage History", "opportunity": self.opportunity["id"], "from_stage": "quotation_sent",
                               "to_stage": "internal_validation", "source": "approval", "event": "internal_validation_approved",
                               "actor": self.manager, "recorded_at": entered, "reached_at": entered,
                               "reached_at_basis": "recorded"}).insert(ignore_permissions=True).name

    def _warnings(self, anchor="2030-03-13"):
        return cockpit.get_warnings({"period": "week", "anchor": anchor})

    def _mine(self, rows):
        return [r for r in rows if r["id"] == self.opportunity["id"]]

    def _count(self, result, key):
        return next(w["count"]["value"] for w in result["warnings"] if w["key"] == key)

    def _code(self, call):
        with self.assertRaises(CrmApiException) as raised:
            call()
        return raised.exception.code

    def test_next_step_is_audited_and_never_clears_an_overdue_action(self):
        action = self._action("2030-03-01")
        before = self._warnings()
        row = next(r for r in before["overdue"] if r["actionId"] == action)
        self.assertEqual((row["handling"]["id"], row["handling"]["sourceEvent"], row["handling"]["state"]), (None, "2030-03-01", "open"))
        source = {k: row["handling"][k] for k in ("warningType", "sourceId", "sourceEvent")}
        saved = warning_handling.save_plan({**source, "nextStep": "  Call the fab manager on Friday  "}, None)
        self.assertEqual((saved["nextStep"], saved["planBy"], saved["state"]), ("Call the fab manager on Friday", self.manager, "open"))
        self.assertEqual([h["kind"] for h in saved["history"]], ["PlanUpdated"])
        after = self._warnings()
        row = next(r for r in after["overdue"] if r["actionId"] == action)
        self.assertEqual(row["handling"]["nextStep"], "Call the fab manager on Friday")
        self.assertEqual(self._count(after, "overdue"), self._count(before, "overdue"))
        self.assertIn(self.manager, after["names"])
        # A retried identical save returns the record; a different one needs the version it was based on.
        again = warning_handling.save_plan({**source, "nextStep": "Call the fab manager on Friday"}, None)
        self.assertEqual((again["modified"], len(again["history"])), (saved["modified"], 1))
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "Other"}, None)), "VERSION_CONFLICT")
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "Other"}, "2000-01-01T00:00:00Z")), "VERSION_CONFLICT")
        edited = warning_handling.save_plan({**source, "nextStep": "Visit on Monday"}, saved["modified"])
        self.assertEqual([h["nextStep"] for h in edited["history"]], ["Visit on Monday", "Call the fab manager on Friday"])
        # Overdue actions clear only through the action itself.
        self.assertEqual(self._code(lambda: warning_handling.record_action(
            {**source, "actionTaken": "Called", "followUpOn": "2030-03-20"}, edited["modified"])), "INVALID_TRANSITION")
        # Rescheduled into the past again: a new warning with an empty record; the old one cannot be written.
        frappe.db.set_value("CRM Opportunity Action", action, "due", "2030-03-05")
        row = next(r for r in self._warnings()["overdue"] if r["actionId"] == action)
        self.assertEqual((row["handling"]["id"], row["handling"]["sourceEvent"]), (None, "2030-03-05"))
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "Late"}, edited["modified"])), "INVALID_TRANSITION")
        for bad in ("", "   ", "x" * 2001, None):
            with self.subTest(bad=bad):
                self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "sourceEvent": "2030-03-05", "nextStep": bad}, None)), "VALIDATION_ERROR")
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "warningType": "downgrade", "nextStep": "x"}, None)), "VALIDATION_ERROR")
        frappe.set_user(self.sales)
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "sourceEvent": "2030-03-05", "nextStep": "x"}, None)), "PERMISSION_DENIED")

    def test_stage6_action_clears_the_deal_until_its_follow_up_day(self):
        entry = self._to_stage6(45)
        before = self._warnings()
        row = self._mine(before["stage6NoPoItems"])[0]
        self.assertEqual((row["handling"]["sourceEvent"], row["handling"]["state"], row["daysInStage"]), (entry, "open", 45))
        source = {k: row["handling"][k] for k in ("warningType", "sourceId", "sourceEvent")}
        for follow_up in ("2030-03-13", "2030-03-01", "2031-03-14", "someday", None):
            with self.subTest(follow_up=follow_up):
                self.assertEqual(self._code(lambda: warning_handling.record_action(
                    {**source, "actionTaken": "Asked purchasing for the PO date", "followUpOn": follow_up}, None)), "VALIDATION_ERROR")
        planned = warning_handling.save_plan({**source, "nextStep": "Chase purchasing"}, None)
        self.assertEqual(self._mine(self._warnings()["stage6NoPoItems"])[0]["handling"]["state"], "open")
        acted = warning_handling.record_action({**source, "actionTaken": "Asked purchasing for the PO date", "followUpOn": "2030-03-20"}, planned["modified"])
        self.assertEqual((acted["state"], acted["actedBy"], acted["followUpOn"], acted["nextStep"]), ("handled", self.manager, "2030-03-20", "Chase purchasing"))
        self.assertEqual([h["kind"] for h in acted["history"]], ["ActionRecorded", "PlanUpdated"])
        after = self._warnings()
        self.assertEqual(self._mine(after["stage6NoPoItems"]), [])
        self.assertEqual(self._mine(after["stage6NoPoHandledItems"])[0]["handling"]["actionTaken"], "Asked purchasing for the PO date")
        self.assertEqual(self._count(after, "stage6_no_po"), self._count(before, "stage6_no_po") - 1)
        # The Review banner reads the same count.
        review = cockpit.get_review({"period": "week", "anchor": "2030-03-13"})
        self.assertEqual(self._count(review, "stage6_no_po"), self._count(after, "stage6_no_po"))
        # On the follow-up day the deal is back, showing what was done.
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 3, 20, 9)):
            back = self._mine(self._warnings("2030-03-20")["stage6NoPoItems"])[0]["handling"]
        self.assertEqual((back["state"], back["actionTaken"]), ("open", "Asked purchasing for the PO date"))
        # Leaving S6 ends the warning: nothing can be recorded on it any more.
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "stage", "po_received", update_modified=False)
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "x"}, acted["modified"])), "INVALID_TRANSITION")

    def test_manager_thresholds_override_site_config_and_are_audited(self):
        frappe.conf.crm_cockpit_stage6_no_po_days = None
        settings = cockpit_settings.get_settings()
        self.assertEqual((settings["quoteExpiryDays"], settings["stage6NoPoDays"], settings["modified"]), (14, 56, None))
        self.assertEqual(settings["sources"], {"quoteExpiryDays": "default", "stage6NoPoDays": "default"})
        with patch.dict(frappe.conf, {"crm_cockpit_stage6_no_po_days": 40, "crm_cockpit_quote_expiry_days": "bad"}):
            fallback = cockpit_settings.get_settings()
            self.assertEqual((fallback["stage6NoPoDays"], fallback["sources"]["stage6NoPoDays"]), (40, "site_config"))
            self.assertEqual((fallback["quoteExpiryDays"], fallback["sources"]["quoteExpiryDays"]), (14, "default"))
        # Installing or migrating the DocType leaves a row with both Ints at 0 and a modified time:
        # it reads as never saved, and the first save needs no version.
        frappe.db.sql("INSERT INTO `tabSingles` (`doctype`, `field`, `value`) VALUES (%s, 'quote_expiry_days', '0'), (%s, 'stage6_no_po_days', '0'),"
                      " (%s, 'modified', '2026-09-24 17:07:24.983428'), (%s, 'modified_by', 'Administrator')", (cockpit_settings.SETTINGS,) * 4)
        installed = cockpit_settings.get_settings()
        self.assertEqual((installed["quoteExpiryDays"], installed["stage6NoPoDays"], installed["modified"], installed["modifiedBy"]), (14, 56, None, None))
        self.assertEqual(installed["sources"], {"quoteExpiryDays": "default", "stage6NoPoDays": "default"})
        self.assertEqual(self._warnings()["quotationExpiry"]["thresholdDays"], 14)
        for bad in (366, -1, "7.5", "x", None, True, 7.0, "²"):
            with self.subTest(bad=bad):
                self.assertEqual(self._code(lambda: cockpit_settings.save_settings({"quoteExpiryDays": bad, "stage6NoPoDays": 30}, None)), "VALIDATION_ERROR")
        self.assertEqual(self._code(lambda: cockpit_settings.save_settings({"quoteExpiryDays": 14, "stage6NoPoDays": 0}, None)), "VALIDATION_ERROR")
        frappe.conf.crm_cockpit_stage6_no_po_days = 30
        self.assertEqual(cockpit_settings.get_settings()["sources"]["stage6NoPoDays"], "site_config")
        self._to_stage6(45)
        self.assertEqual(len(self._mine(self._warnings()["stage6NoPoItems"])), 1)
        with patch.dict(frappe.conf, {"crm_cockpit_stage6_no_po_days": 20}):
            saved = cockpit_settings.save_settings({"quoteExpiryDays": 10, "stage6NoPoDays": 50}, None)
            self.assertEqual((saved["quoteExpiryDays"], saved["stage6NoPoDays"], saved["modifiedBy"]), (10, 50, self.manager))
            self.assertEqual(saved["sources"], {"quoteExpiryDays": "settings", "stage6NoPoDays": "settings"})
            # Saved settings win over site config, at once.
            result = self._warnings()
            self.assertEqual((result["stage6NoPo"]["thresholdDays"], result["quotationExpiry"]["thresholdDays"]), (50, 10))
            self.assertEqual(self._mine(result["stage6NoPoItems"]), [])
        self.assertEqual(cockpit_settings.save_settings({"quoteExpiryDays": 10, "stage6NoPoDays": 50}, None)["modified"], saved["modified"])
        self.assertEqual(self._code(lambda: cockpit_settings.save_settings({"quoteExpiryDays": 12, "stage6NoPoDays": 50}, None)), "VERSION_CONFLICT")
        changed = cockpit_settings.save_settings({"quoteExpiryDays": "0", "stage6NoPoDays": 50}, saved["modified"])
        # 0 is a real quotation threshold (only quotes expiring today), not "unset".
        self.assertEqual((changed["quoteExpiryDays"], changed["sources"]["quoteExpiryDays"], changed["modifiedByName"]), (0, "settings", "manager"))
        # Every save leaves a Version row (who changed which threshold); the test runner itself skips them.
        self.assertTrue(frappe.get_meta(cockpit_settings.SETTINGS).track_changes)
        frappe.set_user(self.sales)
        self.assertEqual(self._code(cockpit_settings.get_settings), "PERMISSION_DENIED")
        self.assertEqual(self._code(lambda: cockpit_settings.save_settings({"quoteExpiryDays": 5, "stage6NoPoDays": 5}, changed["modified"])), "PERMISSION_DENIED")

    def test_threshold_increase_rejects_stale_action_without_suppressing_future_warning(self):
        entry = self._to_stage6(45)
        self.assertEqual(len(self._mine(self._warnings()["stage6NoPoItems"])), 1)
        cockpit_settings.save_settings({"quoteExpiryDays": 14, "stage6NoPoDays": 60}, None)
        source = {"warningType": "stage6_no_po", "sourceId": self.opportunity["id"], "sourceEvent": entry}
        self.assertEqual(self._code(lambda: warning_handling.record_action(
            {**source, "actionTaken": "Old page", "followUpOn": "2031-03-13"})), "INVALID_TRANSITION")
        self.assertFalse(frappe.db.exists(warning_handling.HANDLING, {"source_id": self.opportunity["id"]}))
        with patch("frappe.utils.now_datetime", return_value=NOW + timedelta(days=15)):
            row = self._mine(self._warnings("2030-03-28")["stage6NoPoItems"])[0]
            self.assertEqual((row["daysInStage"], row["handling"]["state"]), (60, "open"))

    def test_stage6_action_preserves_unknown_and_lower_bound_history_semantics(self):
        entry = self._to_stage6(45)
        source = {"warningType": "stage6_no_po", "sourceId": self.opportunity["id"], "sourceEvent": entry,
                  "actionTaken": "Call purchasing", "followUpOn": "2030-03-20"}
        with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {}}):
            self.assertEqual(self._code(lambda: warning_handling.record_action(source)), "INVALID_TRANSITION")
        frappe.db.set_value("CRM Opportunity Stage History", entry, "reached_at_basis", "upper_bound")
        with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {"stage": "2030-03-03"}}):
            self.assertEqual(self._code(lambda: warning_handling.record_action(source)), "INVALID_TRANSITION")
        with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {"stage": "2030-02-10"}}):
            self.assertEqual(warning_handling.record_action(source)["state"], "handled")

    def _notices(self, user, source_name):
        return frappe.get_all("CRM Notification Event", filters={"recipient_user": user, "source_name": source_name},
                              fields=["title", "route", "category"])

    def _postpone(self, new_date):
        from rayher_crm.services.opportunities import _append_history
        previous = frappe.db.get_value("CRM Opportunity", self.opportunity["id"], "po_date")
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "po_date", new_date)
        _append_history(self.opportunity["id"], "po_date", previous, new_date)
        event = frappe.db.get_value("CRM Opportunity History", {
            "opportunity": self.opportunity["id"], "field": "po_date", "to_value": new_date,
        }, "name")
        # now_datetime is frozen for handling/follow-up assertions; give audited
        # changes a deterministic order rather than depending on random hash names.
        sequence = frappe.db.count("CRM Opportunity History", {"opportunity": self.opportunity["id"], "field": "po_date"})
        frappe.db.set_value("CRM Opportunity History", event, "at", NOW - timedelta(seconds=60 - sequence))
        return event

    def test_postponement_plan_action_version_new_instance_and_recovery(self):
        event = self._postpone("2031-01-01")
        source = {"warningType": "close_date_slip", "sourceId": self.opportunity["id"], "sourceEvent": event}
        self.assertEqual(self._mine(self._warnings()["closeDateSlipItems"])[0]["eventId"], event)
        plan = warning_handling.save_plan({**source, "nextStep": "Confirm purchasing timetable"})
        retry = warning_handling.save_plan({**source, "nextStep": "Confirm purchasing timetable"})
        self.assertEqual((plan["id"], plan["modified"]), (retry["id"], retry["modified"]))
        self.assertEqual(len(self._mine(self._warnings()["closeDateSlipItems"])), 1)
        acted = warning_handling.record_action({**source, "actionTaken": "Called purchasing", "followUpOn": "2030-03-20"}, plan["modified"])
        self.assertEqual(self._mine(self._warnings()["closeDateSlipItems"]), [])
        self.assertEqual(self._mine(self._warnings()["closeDateSlipHandledItems"])[0]["handling"]["state"], "handled")
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "Stale edit"}, plan["modified"])), "VERSION_CONFLICT")
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 3, 20, 9)):
            self.assertEqual(len(self._mine(self._warnings("2030-03-20")["closeDateSlipItems"])), 1)
        # Same-quarter date edits preserve the handled identity; a new quarter does not.
        self._postpone("2031-02-01")
        self.assertEqual(self._mine(self._warnings()["closeDateSlipHandledItems"])[0]["eventId"], event)
        later = self._postpone("2031-04-01")
        row = self._mine(self._warnings()["closeDateSlipItems"])[0]
        self.assertEqual((row["eventId"], row["handling"]["state"]), (later, "open"))
        self.assertEqual(self._code(lambda: warning_handling.record_action({**source, "actionTaken": "Old event", "followUpOn": "2030-03-21"}, acted["modified"])), "INVALID_TRANSITION")
        self._postpone("2031-03-31")
        self.assertEqual(self._mine(self._warnings()["closeDateSlipItems"]), [])
        self.assertTrue(frappe.db.exists(warning_handling.HANDLING, plan["id"]))
        frappe.set_user(self.sales)
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "Not manager"})), "PERMISSION_DENIED")

    def test_postponement_notices_deduplicate_and_follow_current_source_scope(self):
        from rayher_crm.permissions.notification_scope import can_read_source
        event = self._postpone("2031-01-01")
        frappe.set_user("Administrator")
        send_warning_notifications()
        send_warning_notifications()
        self.assertEqual(len(self._notices(self.manager, event)), 1)
        self.assertEqual(len(self._notices(self.sales, event)), 1)
        self.assertEqual(self._notices(self.other_sales, event), [])
        self.assertTrue(can_read_source("CRM Opportunity History", event, self.sales))
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "opportunity_owner", self.other_sales)
        self.assertFalse(can_read_source("CRM Opportunity History", event, self.sales))
        # A foreign private customer also prevents the new owner from receiving it.
        self.assertFalse(can_read_source("CRM Opportunity History", event, self.other_sales))
        self.assertTrue(can_read_source("CRM Opportunity History", event, self.manager))
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "opportunity_owner", self.sales)
        frappe.set_user(self.manager)
        source = {"warningType": "close_date_slip", "sourceId": self.opportunity["id"], "sourceEvent": event}
        warning_handling.record_action({**source, "actionTaken": "Called", "followUpOn": "2030-03-20"})
        frappe.set_user("Administrator")
        send_warning_notifications()
        self.assertEqual(len(self._notices(self.sales, event)), 1)
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 3, 20, 9)):
            send_warning_notifications()
            send_warning_notifications()
        self.assertEqual(len(self._notices(self.sales, event)), 2)
        next_event = self._postpone("2031-04-01")
        send_warning_notifications()
        self.assertEqual(len(self._notices(self.sales, next_event)), 1)

    def test_delete_removes_slip_notices_atomically_with_the_history_source(self):
        from rayher_crm.services.opportunities import delete_strategy_opportunity
        event = self._postpone("2031-01-01")
        frappe.set_user("Administrator")
        send_warning_notifications()
        source = {"source_doctype": "CRM Opportunity History", "source_name": event}
        count = frappe.db.count("CRM Notification Event", source)
        self.assertGreater(count, 0)
        # A failed delete restores the notices and their source in the same savepoint.
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            delete_strategy_opportunity(self.opportunity["id"])
        self.assertEqual(frappe.db.count("CRM Notification Event", source), count)
        self.assertTrue(frappe.db.exists("CRM Opportunity History", event))
        frappe.set_user(self.manager)
        delete_strategy_opportunity(self.opportunity["id"])
        self.assertFalse(frappe.db.exists("CRM Opportunity", self.opportunity["id"]))
        self.assertFalse(frappe.db.exists("CRM Opportunity History", event))
        self.assertEqual(frappe.db.count("CRM Notification Event", source), 0)

    def test_each_warning_notifies_once_and_a_new_instance_notifies_again(self):
        frappe.set_user("Administrator")
        action = self._action("2030-03-11")
        unreadable = self._action("2030-03-12", owner=self.other_sales)
        old = self._action("2030-03-01")
        entry = self._to_stage6(31)
        send_warning_notifications()
        self.assertEqual([n.title for n in self._notices(self.manager, action)], ["预警：行动逾期"])
        self.assertEqual([n.route for n in self._notices(self.sales, action)], [f"/opportunities/{self.opportunity['id']}"])
        self.assertEqual([n.title for n in self._notices(self.manager, entry)], ["预警：第 6 阶段超期无 PO"])
        self.assertEqual(self._notices(self.sales, entry), [])
        # The owner of an action on an account they cannot read is not told; Managers are.
        self.assertEqual((len(self._notices(self.other_sales, unreadable)), len(self._notices(self.manager, unreadable))), (0, 1))
        # Late for longer than NOTICE_DAYS when first seen: already on the page, not announced (no first-run flood).
        self.assertEqual(self._notices(self.manager, old), [])
        send_warning_notifications()
        self.assertEqual((len(self._notices(self.manager, action)), len(self._notices(self.manager, entry))), (1, 1))
        # Rescheduled and late again: a new warning, a new notice.
        frappe.db.set_value("CRM Opportunity Action", action, "due", "2030-03-12")
        send_warning_notifications()
        self.assertEqual(len(self._notices(self.manager, action)), 2)
        # A handled S6 deal stays quiet; after its follow-up day it is announced again.
        frappe.set_user(self.manager)
        warning_handling.record_action({"warningType": "stage6_no_po", "sourceId": self.opportunity["id"], "sourceEvent": entry,
                                        "actionTaken": "Asked purchasing", "followUpOn": "2030-03-20"}, None)
        frappe.set_user("Administrator")
        send_warning_notifications()
        self.assertEqual(len(self._notices(self.manager, entry)), 1)
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 3, 20, 9)):
            send_warning_notifications()
        self.assertEqual(len(self._notices(self.manager, entry)), 2)

    def test_a_stage6_stay_known_only_as_a_minimum_is_announced_the_day_it_is_first_listed(self):
        # Entered S6 before the complete stage history: the stay counts from the history start as a minimum,
        # and the deal is first listed the day that minimum reaches the threshold (30 days).
        entry = self._to_stage6(45)
        coverage = COVERAGE["crm_cockpit_history_complete_from"]
        frappe.set_user("Administrator")
        # History from 2030-02-01: listed since 2030-03-03 already, so on the page and not announced.
        with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {**coverage, "stage": "2030-02-01"}}):
            send_warning_notifications()
        self.assertEqual(self._notices(self.manager, entry), [])
        # History from 2030-02-11: the minimum reaches 30 days today, so the deal is new on the page and announced.
        with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {**coverage, "stage": "2030-02-11"}}):
            frappe.set_user(self.manager)
            row = self._mine(self._warnings()["stage6NoPoItems"])[0]
            self.assertEqual((row["daysInStage"], row["daysAtLeast"], row["enteredAt"]), (30, True, None))
            frappe.set_user("Administrator")
            send_warning_notifications()
        self.assertEqual([n.title for n in self._notices(self.manager, entry)], ["预警：第 6 阶段超期无 PO"])

    def test_a_stage6_deal_without_any_entry_record_is_announced_the_day_it_is_first_listed(self):
        # In S6 since before the stage history: no entry row at all, so the stay counts from the history start.
        # Such a deal is "unknown" under any earlier coverage and would blank the company-wide S6 count for the
        # tests after this one (they share a transaction), so the stage is put back when this test ends.
        stage = frappe.db.get_value("CRM Opportunity", self.opportunity["id"], "stage")
        self.addCleanup(frappe.db.set_value, "CRM Opportunity", self.opportunity["id"], "stage", stage, update_modified=False)
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "stage", "internal_validation", update_modified=False)
        coverage = COVERAGE["crm_cockpit_history_complete_from"]
        frappe.set_user("Administrator")
        with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {**coverage, "stage": "2030-02-11"}}):
            send_warning_notifications()
            frappe.set_user(self.manager)
            row = self._mine(self._warnings()["stage6NoPoItems"])[0]
            self.assertEqual((row["daysInStage"], row["daysAtLeast"], row["enteredAt"], row["handling"]["sourceEvent"]),
                             (30, True, None, "before_history"))
        notices = frappe.get_all("CRM Notification Event", fields=["title", "source_doctype", "source_name"],
                                 filters={"recipient_user": self.manager, "route": f"/opportunities/{self.opportunity['id']}"})
        self.assertEqual(
            [(n.title, n.source_doctype, n.source_name) for n in notices],
            [("预警：第 6 阶段超期无 PO", "CRM Opportunity", self.opportunity["id"])],
        )

    def test_deleting_the_opportunity_removes_its_before_history_stage6_notices(self):
        from rayher_crm.services.opportunities import delete_strategy_opportunity

        stage = frappe.db.get_value("CRM Opportunity", self.opportunity["id"], "stage")
        self.addCleanup(frappe.db.set_value, "CRM Opportunity", self.opportunity["id"], "stage", stage, update_modified=False)
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "stage", "internal_validation", update_modified=False)
        coverage = COVERAGE["crm_cockpit_history_complete_from"]
        frappe.set_user("Administrator")
        with patch.dict(frappe.conf, {"crm_cockpit_history_complete_from": {**coverage, "stage": "2030-02-11"}}):
            send_warning_notifications()
        filters = {"source_doctype": "CRM Opportunity", "source_name": self.opportunity["id"]}
        notices = frappe.get_all("CRM Notification Event", filters=filters, pluck="name")
        self.assertTrue(notices)
        # The inbox copy is a Dynamic Link to its source, which would otherwise refuse the delete.
        frappe.set_user(self.manager)
        delete_strategy_opportunity(self.opportunity["id"])
        self.assertFalse(frappe.db.exists("CRM Opportunity", self.opportunity["id"]))
        self.assertEqual(frappe.db.count("CRM Notification Event", {"name": ["in", notices]}), 0)

    def test_a_bad_source_is_rejected_even_for_a_recipient_who_would_be_skipped(self):
        from rayher_crm.services.notifications import notify_if_reachable

        notice = dict(recipient="nobody@example.invalid", category="Opportunity", title="t", message="m", route="/opportunities/x")
        with self.assertRaises(CrmApiException) as raised:
            notify_if_reachable(**notice, source_doctype="CRM Opportunity", source_name="CRM-OPP-DOES-NOT-EXIST")
        self.assertEqual(raised.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException):
            notify_if_reachable(**notice, source_doctype="User", source_name="Administrator")
        # A well-formed notice to a recipient who no longer exists is the normal quiet skip.
        self.assertIsNone(notify_if_reachable(**notice, source_doctype="CRM Opportunity", source_name=self.opportunity["id"]))

    def test_a_warning_row_with_a_missing_source_is_logged_and_does_not_stop_the_batch(self):
        recipient = self.manager
        before = frappe.db.count("Error Log", {"method": "Warning notification skipped: invalid source"})
        created = warning_notifications._notify(
            [recipient], key="missing-source", category="Opportunity", title="t", message="m", route="/opportunities/x",
            source_doctype="CRM Opportunity", source_name="CRM-OPP-DOES-NOT-EXIST",
        )
        self.assertEqual(created, 0)
        self.assertEqual(frappe.db.count("Error Log", {"method": "Warning notification skipped: invalid source"}), before + 1)
        # A recipient who lost access is still a quiet skip.
        with patch.object(warning_notifications, "create_notification", side_effect=CrmApiException("SCOPE_DENIED", "gone")):
            self.assertEqual(warning_notifications._notify(
                [recipient], key="lost-access", category="Opportunity", title="t", message="m", route="/opportunities/x",
                source_doctype="CRM Opportunity", source_name=self.opportunity["id"]), 0)
        self.assertEqual(frappe.db.count("Error Log", {"method": "Warning notification skipped: invalid source"}), before + 1)

    def test_a_handled_stage6_deal_is_announced_again_when_it_reaches_a_raised_threshold(self):
        entry = self._to_stage6(31)
        frappe.set_user("Administrator")
        send_warning_notifications()
        frappe.set_user(self.manager)
        warning_handling.record_action({"warningType": "stage6_no_po", "sourceId": self.opportunity["id"], "sourceEvent": entry,
                                        "actionTaken": "Asked purchasing", "followUpOn": "2030-03-16"}, None)
        cockpit_settings.save_settings({"quoteExpiryDays": 14, "stage6NoPoDays": 50}, None)
        frappe.set_user("Administrator")
        # The follow-up day passes while the deal is under the raised threshold; it is announced the day it reaches it.
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 3, 31, 9)):
            send_warning_notifications()
        self.assertEqual(len(self._notices(self.manager, entry)), 1)
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 4, 1, 9)):
            send_warning_notifications()
        self.assertEqual(len(self._notices(self.manager, entry)), 2)

    def test_a_first_save_that_loses_the_race_is_a_version_conflict(self):
        # The parent row lock serializes two first saves of one warning, but the second one's REPEATABLE READ
        # snapshot can predate the first: it does not see the row, and its insert hits the key.
        action = self._action("2030-03-01")
        source = {"warningType": "overdue", "sourceId": action, "sourceEvent": "2030-03-01"}
        warning_handling.save_plan({**source, "nextStep": "Call"}, None)
        get_value = frappe.db.get_value
        snapshot = lambda doctype, *args, **kwargs: (None if doctype == warning_handling.HANDLING and args[1:] == ("name",)
                                                     else get_value(doctype, *args, **kwargs))
        with patch.object(frappe.db, "get_value", side_effect=snapshot):
            self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "Email"}, None)), "VERSION_CONFLICT")
        self.assertEqual(self._mine(self._warnings()["overdue"])[0]["handling"]["nextStep"], "Call")

    def test_handling_revisions_are_indexed_by_handling(self):
        # Review and Warnings read every handling's revisions; the Opportunity delete removes them per handling.
        self.assertTrue(frappe.db.has_index("tabCRM Warning Handling Revision", indexes.WARNING_HANDLING_REVISION_INDEX))

    def test_slip_history_lock_uses_opportunity_field_index(self):
        self.assertTrue(frappe.db.has_index("tabCRM Opportunity History", indexes.OPPORTUNITY_FIELD_HISTORY_INDEX))
        plan = frappe.db.sql(
            f"EXPLAIN SELECT name FROM `tabCRM Opportunity History` FORCE INDEX (`{indexes.OPPORTUNITY_FIELD_HISTORY_INDEX}`) "
            "WHERE opportunity=%s AND field='po_date' FOR UPDATE", (self.opportunity["id"],), as_dict=True,
        )
        self.assertEqual(plan[0].key, indexes.OPPORTUNITY_FIELD_HISTORY_INDEX)
        self.assertNotEqual(plan[0].type, "ALL")

    def test_a_lost_deal_awaiting_its_post_mortem_is_announced_to_managers(self):
        from rayher_crm.services.opportunities import mark_opportunity_lost

        frappe.set_user(self.sales)
        lost = mark_opportunity_lost(self.opportunity["id"], {"lostReason": "Budget frozen"}, self.opportunity["modified"])
        event = lost["stageHistory"][0]["id"]
        frappe.set_user("Administrator")
        send_warning_notifications()
        self.assertEqual([(n.title, n.category) for n in self._notices(self.manager, event)], [("预警：丢单待复盘", "Opportunity")])
        self.assertEqual(self._notices(self.sales, event), [])

    def test_expiring_quotation_takes_a_next_step_and_notifies_its_owner(self):
        frappe.set_user(self.sales)
        saved, _ = self._ready_quotation()
        published = self._publish(saved["quotation"]["id"], saved["version"]["modified"])
        quote_id, version_id = published["quotation"]["id"], published["version"]["id"]
        frappe.db.set_value("CRM Quotation Version", version_id, {"published_at": "2030-03-01 10:00:00", "valid_until": "2030-03-25"}, update_modified=False)
        frappe.set_user(self.manager)
        row = next(r for r in self._warnings()["quotationExpiryItems"] if r["id"] == quote_id)
        self.assertEqual((row["handling"]["sourceEvent"], row["handling"]["id"]), (version_id, None))
        source = {k: row["handling"][k] for k in ("warningType", "sourceId", "sourceEvent")}
        warning_handling.save_plan({**source, "nextStep": "Renew with the customer"}, None)
        row = next(r for r in self._warnings()["quotationExpiryItems"] if r["id"] == quote_id)
        self.assertEqual(row["handling"]["nextStep"], "Renew with the customer")
        self.assertEqual(self._code(lambda: warning_handling.record_action(
            {**source, "actionTaken": "Renewed", "followUpOn": "2030-03-20"}, row["handling"]["modified"])), "INVALID_TRANSITION")
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "sourceEvent": "other-version", "nextStep": "x"}, None)), "INVALID_TRANSITION")
        frappe.set_user("Administrator")
        send_warning_notifications()
        owner = frappe.db.get_value("CRM Quotation", quote_id, "quotation_owner")
        for user in {self.manager, owner}:
            notices = self._notices(user, version_id)
            self.assertEqual([(n.title, n.route, n.category) for n in notices], [("预警：报价即将到期", f"/quotations/{quote_id}", "Quotation")])

    def test_a_past_week_keys_a_stage6_deal_by_its_current_entry(self):
        first = self._to_stage6(45)
        # Rolled back and re-approved this week: last week's row is the same deal, now on its new entry.
        for when, before, after, event, source in ((datetime(2030, 3, 11, 10), "internal_validation", "quotation_sent", "rollback", "rollback"),
                                                  (datetime(2030, 3, 12, 10), "quotation_sent", "internal_validation", "internal_validation_approved", "approval")):
            row = frappe.get_doc({"doctype": "CRM Opportunity Stage History", "opportunity": self.opportunity["id"], "from_stage": before, "to_stage": after,
                                  "source": source, "event": event, "actor": self.manager, "recorded_at": when, "reached_at": when,
                                  "reached_at_basis": "recorded"}).insert(ignore_permissions=True)
        current = row.name
        past = self._mine(self._warnings("2030-03-04")["stage6NoPoItems"])[0]
        self.assertEqual((past["daysInStage"], past["handling"]["sourceEvent"]), (42, current))
        source = {k: past["handling"][k] for k in ("warningType", "sourceId", "sourceEvent")}
        self.assertEqual(warning_handling.save_plan({**source, "nextStep": "Re-approved; chase the PO"}, None)["sourceEvent"], current)
        self.assertEqual(self._code(lambda: warning_handling.record_action(
            {**source, "actionTaken": "Premature suppression", "followUpOn": "2031-03-13"})), "INVALID_TRANSITION")
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "sourceEvent": first, "nextStep": "x"}, None)), "INVALID_TRANSITION")

    def test_warnings_open_on_the_current_week_while_review_keeps_the_last_completed_one(self):
        # NOW is Wednesday 2030-03-13: the notices and the post-mortem card send a Manager here for this week.
        self.assertEqual(cockpit.get_warnings({"period": "week"})["period"]["start"], "2030-03-11")
        self.assertEqual(cockpit.get_review({"period": "week"})["period"]["start"], "2030-03-04")
        self.assertEqual(cockpit.get_warnings({"period": "week", "anchor": "2030-03-04"})["period"]["start"], "2030-03-04")

    def test_deleting_the_opportunity_removes_its_handling_rows(self):
        from rayher_crm.services.opportunities import delete_strategy_opportunity

        action = self._action("2030-03-01")
        saved = warning_handling.save_plan({"warningType": "overdue", "sourceId": action, "sourceEvent": "2030-03-01", "nextStep": "Call"}, None)
        self.assertTrue(frappe.db.exists("CRM Warning Handling", saved["id"]))
        delete_strategy_opportunity(self.opportunity["id"])
        self.assertFalse(frappe.db.exists("CRM Warning Handling", saved["id"]))
        self.assertEqual(frappe.db.count("CRM Warning Handling Revision", {"handling": saved["id"]}), 0)

    def test_a_cleared_warning_takes_no_next_step_and_follow_up_reaches_a_year(self):
        action = self._action("2030-03-01")
        source = {"warningType": "overdue", "sourceId": action, "sourceEvent": "2030-03-01"}
        for field, value in (("status", "Done"), ("archived", 1)):
            with self.subTest(field=field):
                frappe.db.set_value("CRM Opportunity Action", action, field, value)
                self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "x"}, None)), "INVALID_TRANSITION")
                frappe.db.set_value("CRM Opportunity Action", action, {"status": "Open", "archived": 0})
        frappe.db.set_value("CRM Opportunity", self.opportunity["id"], "stage", "lost", update_modified=False)
        self.assertEqual(self._code(lambda: warning_handling.save_plan({**source, "nextStep": "x"}, None)), "INVALID_TRANSITION")
        entry = self._to_stage6(45)
        acted = warning_handling.record_action({"warningType": "stage6_no_po", "sourceId": self.opportunity["id"], "sourceEvent": entry,
                                                "actionTaken": "Quarterly budget", "followUpOn": "2031-03-13"}, None)
        self.assertEqual((acted["followUpOn"], acted["state"]), ("2031-03-13", "handled"))


class TestWarningNotificationDeletionLock(FrappeTestCase):
    def test_legacy_parent_locks_are_sorted_and_deduplicated(self):
        with patch.object(
            warning_notifications,
            "_lock_current_opportunity",
            side_effect=lambda name: name != "CRM-OPP-B",
        ) as lock:
            locked = warning_notifications._lock_current_opportunities(
                ["CRM-OPP-C", "CRM-OPP-A", "CRM-OPP-C", "", None, "CRM-OPP-B"],
            )
        self.assertEqual(
            [call.args[0] for call in lock.call_args_list],
            ["CRM-OPP-A", "CRM-OPP-B", "CRM-OPP-C"],
        )
        self.assertEqual(locked, {"CRM-OPP-A", "CRM-OPP-C"})

    def test_slip_job_skips_a_parent_deleted_after_its_snapshot(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        opportunity_id = f"CRM-OPP-SLIP-RACE-{frappe.generate_hash(length=10)}"
        primary = frappe.local.db
        connection = None
        try:
            frappe.db.sql("INSERT INTO `tabCRM Opportunity` (`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`) VALUES (%s, NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0)", (opportunity_id,))
            primary.commit()
            self.assertTrue(frappe.db.exists("CRM Opportunity", opportunity_id))
            connection = primary._get_connection()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM `tabCRM Opportunity` WHERE name=%s", (opportunity_id,))
            connection.commit()
            # Ordinary reads still see the old parent in this transaction.
            self.assertTrue(frappe.db.exists("CRM Opportunity", opportunity_id))
            details = {"lost": [], "overdue": [], "quotation_expiry": [], "stage6_no_po": [], "close_date_slip": [{
                "id": opportunity_id, "eventId": "deleted-history", "at": NOW.isoformat(),
                "title": "Deleted", "customer": "Scope", "previousPoDate": "2030-03-01", "postponedPoDate": "2030-04-01",
            }]}
            with (patch.object(warning_notifications, "warning_details", return_value=details),
                  patch.object(warning_notifications, "active_crm_users", return_value={"manager"}),
                  patch.object(warning_notifications, "_can_read", return_value=True),
                  patch.object(warning_notifications, "_notify") as notify):
                warning_notifications.send_warning_notifications()
            notify.assert_not_called()
        finally:
            if connection is not None:
                connection.rollback()
                connection.close()
            frappe.local.db = primary
            primary.rollback()
            frappe.db.sql("DELETE FROM `tabCRM Opportunity` WHERE name=%s", (opportunity_id,))
            primary.commit()

    def test_every_legacy_parent_is_locked_before_the_first_notification_insert(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        opportunity_id = f"CRM-OPP-ORDER-{frappe.generate_hash(length=10)}"
        primary = frappe.local.db
        connection = None
        try:
            frappe.db.sql(
                "INSERT INTO `tabCRM Opportunity` "
                "(`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`) "
                "VALUES (%s, NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0)",
                (opportunity_id,),
            )
            primary.commit()
            connection = primary._get_connection()
            today = frappe.utils.now_datetime().date().isoformat()
            details = {
                "lost": [{
                    "id": opportunity_id, "eventId": "lost-before-stage6", "at": today,
                    "reviewPending": True, "title": "Lock order", "customer": "Scope",
                }],
                "overdue": [],
                "quotation_expiry": [],
                "stage6_no_po": [{
                    "id": opportunity_id, "daysInStage": 30, "daysAtLeast": True,
                    "title": "Lock order", "customer": "Scope",
                    "handling": {"sourceEvent": "before_history"},
                }],
            }
            checked = False

            def assert_parent_already_locked(*args, **kwargs):
                nonlocal checked
                del args, kwargs
                if not checked:
                    with connection.cursor() as cursor:
                        cursor.execute("SET SESSION innodb_lock_wait_timeout = 1")
                        with self.assertRaises(Exception) as waited:
                            cursor.execute(
                                "SELECT `name` FROM `tabCRM Opportunity` "
                                "WHERE `name` = %s FOR UPDATE",
                                (opportunity_id,),
                            )
                        self.assertEqual(waited.exception.args[0], 1205)
                    connection.rollback()
                    checked = True
                return 0

            with (
                patch.object(warning_notifications, "warning_details", return_value=details),
                patch.object(warning_notifications, "thresholds", return_value={
                    "quote_expiry_days": (7, "test"), "stage6_no_po_days": (30, "test"),
                }),
                patch.object(warning_notifications, "active_crm_users", return_value={"manager"}),
                patch.object(warning_notifications, "_can_read", return_value=True),
                patch.object(warning_notifications, "_notify", side_effect=assert_parent_already_locked),
            ):
                warning_notifications.send_warning_notifications()
                self.assertTrue(checked)
                primary.rollback()
                checked = False
                details["stage6_no_po"] = []
                details["close_date_slip"] = [{"id": opportunity_id, "eventId": "slip-after-lost", "at": today,
                    "title": "Lock order", "customer": "Scope", "previousPoDate": "2030-03-01", "postponedPoDate": "2030-04-01"}]
                warning_notifications.send_warning_notifications()
            self.assertTrue(checked)
        finally:
            try:
                if connection is not None:
                    try:
                        connection.rollback()
                    finally:
                        connection.close()
            finally:
                frappe.local.db = primary
                primary.rollback()
                frappe.db.sql("DELETE FROM `tabCRM Opportunity` WHERE `name` = %s", (opportunity_id,))
                primary.commit()

    def test_a_before_history_notice_takes_the_same_parent_lock_as_deletion(self):
        # Both paths lock the Opportunity primary-key row first. This dedicated raw
        # fixture keeps the required commit isolated from every business fixture.
        self.assertTrue(frappe.local.site.endswith(".test"))
        opportunity_id = f"CRM-OPP-LOCK-{frappe.generate_hash(length=10)}"
        primary = frappe.local.db
        connection = None
        try:
            frappe.db.sql(
                "INSERT INTO `tabCRM Opportunity` "
                "(`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`) "
                "VALUES (%s, NOW(6), NOW(6), 'Administrator', 'Administrator', 0, 0)",
                (opportunity_id,),
            )
            primary.commit()
            connection = primary._get_connection()
            self.assertTrue(warning_notifications._lock_current_opportunity(opportunity_id))
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_lock_wait_timeout = 1")
                with self.assertRaises(Exception) as waited:
                    cursor.execute(
                        "SELECT `name` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE",
                        (opportunity_id,),
                    )
                self.assertEqual(waited.exception.args[0], 1205)
            primary.rollback()
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT `name` FROM `tabCRM Opportunity` WHERE `name` = %s FOR UPDATE NOWAIT",
                    (opportunity_id,),
                )
                self.assertEqual(cursor.fetchone()[0], opportunity_id)
        finally:
            try:
                if connection is not None:
                    try:
                        connection.rollback()
                    finally:
                        connection.close()
            finally:
                frappe.local.db = primary
                primary.rollback()
                frappe.db.sql("DELETE FROM `tabCRM Opportunity` WHERE `name` = %s", (opportunity_id,))
                primary.commit()
