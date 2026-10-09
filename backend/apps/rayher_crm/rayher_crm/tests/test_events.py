import re
from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import events
from rayher_crm.tests.test_opportunity_relations import TestOpportunityRelations


class TestEvents(FrappeTestCase):
    _user = TestOpportunityRelations._user
    _records = TestOpportunityRelations._records

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("event-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("event-other@example.invalid", "CRM Sales")
        self.manager = self._user("event-manager@example.invalid", "CRM Manager")
        self.engineer = self._user("event-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.sales)

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def payload(self, **values):
        return {"title": "Industry exhibition", "owner": self.sales, "startDate": "2030-09-20", "endDate": "2030-09-30",
                "status": "Planned", "accountId": "", "opportunityId": "", "region": "", "market": "", "equipment": "", "note": "", **values}

    def test_completion_uses_server_snapshot_and_edit_reopen_cancel_are_audited(self):
        row = events.save_event(self.payload())
        with patch("frappe.utils.now_datetime", return_value=datetime(2030, 9, 30, 16)):
            done = events.save_event(self.payload(status="Done"), row["id"], row["modified"])
        self.assertEqual(done["completedAt"], "2030-09-30T08:00:00Z")
        self.assertEqual(frappe.db.get_value(events.DOCTYPE, row["id"], "completed_owner"), self.sales)
        updated = events.save_event(self.payload(status="Done", note="Attendees recorded"), row["id"], done["modified"])
        self.assertEqual(updated["completedAt"], done["completedAt"])
        with self.assertRaises(CrmApiException) as stale:
            events.save_event(self.payload(), row["id"], done["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        reopened = events.save_event(self.payload(), row["id"], updated["modified"])
        self.assertIsNone(reopened["completedAt"])
        cancelled = events.save_event(self.payload(status="Cancelled"), row["id"], reopened["modified"])
        self.assertIsNone(cancelled["completedAt"])
        self.assertTrue(frappe.db.exists("Version", {"ref_doctype": events.DOCTYPE, "docname": row["id"]}))

    def test_scope_native_permissions_and_current_customer_revocation(self):
        account, opportunity, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        payload = self.payload(accountId=account["id"], opportunityId=opportunity["id"])
        row = events.save_event(payload)
        self.assertEqual(events.get_event(row["id"])["id"], row["id"])
        self.assertFalse(frappe.has_permission(events.DOCTYPE, "write", doc=frappe.get_doc(events.DOCTYPE, row["id"])))
        frappe.set_user(self.other_sales)
        self.assertNotIn(row["id"], [item["id"] for item in events.list_events({})[0]])
        with self.assertRaises(CrmApiException):
            events.save_event(self.payload(owner=self.other_sales), row["id"], row["modified"])
        frappe.set_user(self.engineer)
        with self.assertRaises(frappe.PermissionError):
            events.list_events({})
        frappe.set_user("Administrator")
        frappe.db.set_value("Customer", account["id"], {"custom_crm_owner": self.other_sales, "custom_crm_visibility": "Private"})
        frappe.set_user(self.sales)
        self.assertFalse(frappe.has_permission(events.DOCTYPE, "read", doc=frappe.get_doc(events.DOCTYPE, row["id"])))
        with self.assertRaises(CrmApiException):
            events.get_event(row["id"])
        with self.assertRaises(CrmApiException):
            events.save_event(payload, row["id"], row["modified"])
        frappe.set_user(self.manager)
        self.assertEqual(events.get_event(row["id"])["id"], row["id"])

    def test_an_archived_opportunity_takes_no_new_event_and_the_one_naming_it_is_kept_up(self):
        from rayher_crm.services.opportunities import archive_strategy_opportunity, unarchive_strategy_opportunity
        from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_LINK
        account, opportunity, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        linked = self.payload(accountId=account["id"], opportunityId=opportunity["id"])
        kept = events.save_event(linked)
        loose = events.save_event(self.payload(accountId=account["id"]))
        frappe.set_user(self.manager)
        archive_strategy_opportunity(opportunity["id"])
        frappe.set_user(self.sales)
        before = frappe.db.count(events.DOCTYPE)
        real_sql = frappe.db.sql
        statements: list[str] = []

        def watch(query, *args, **kwargs):
            statements.append(str(query))
            return real_sql(query, *args, **kwargs)

        # A new Event naming it, and an Event made to name it, are refused before anything is written, each reading the
        # flag under the Opportunity's row lock, as committed: every statement on the Opportunity's table that reads
        # the archive's columns or the whole row, as these paths write them, is a locking one without a subquery (which
        # would read the snapshot's, without a lock), one of them FOR UPDATE (a read served from the cache is not seen).
        for attempt in (lambda: events.save_event(linked), lambda: events.save_event(linked, loose["id"], loose["modified"])):
            statements.clear()
            with self.assertRaises(CrmApiException) as refused, patch.object(frappe.db, "sql", side_effect=watch):
                attempt()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_LINK))
            reads = [text.upper() for text in statements if re.search(r"`tabCRM Opportunity`", text, re.I)
                     and re.search(r"\barchived(?:_at|_by)?\b|(?:SELECT|,)\s*(?:`[^`]+`\.|\w+\.)?\*", text, re.I)]
            self.assertTrue(any("FOR UPDATE" in text for text in reads), statements)
            self.assertTrue(all(("FOR UPDATE" in text or "LOCK IN SHARE MODE" in text) and text.count("SELECT") == 1
                                for text in reads), reads)
        self.assertEqual(frappe.db.count(events.DOCTYPE), before)
        self.assertFalse(frappe.db.get_value(events.DOCTYPE, loose["id"], "opportunity"))
        # The Event naming it already is a record of its own, kept up as a Visit is.
        done = events.save_event({**linked, "status": "Done"}, kept["id"], kept["modified"])
        self.assertEqual((done["status"], done["opportunityId"]), ("Done", opportunity["id"]))
        frappe.set_user(self.manager)
        unarchive_strategy_opportunity(opportunity["id"])
        frappe.set_user(self.sales)
        self.assertEqual(events.save_event(linked, loose["id"], loose["modified"])["opportunityId"], opportunity["id"])

    def test_an_archived_account_takes_no_new_event_none_moved_in_or_out_and_none_planned_again(self):
        from rayher_crm.services.accounts import (
            ARCHIVED_ACCOUNT_EDIT, ARCHIVED_ACCOUNT_LINK, ARCHIVED_ACCOUNT_REOPEN, archive_account, unarchive_account,
        )
        from rayher_crm.services.opportunities import mark_opportunity_lost
        account, opportunity, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        other, _, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        frappe.set_user(self.sales)
        kept = events.save_event(self.payload(accountId=account["id"]))
        finished = events.save_event(self.payload(accountId=account["id"], status="Done"))
        cancelled = events.save_event(self.payload(accountId=account["id"], status="Cancelled"))
        dealt = events.save_event(self.payload(accountId=account["id"], opportunityId=opportunity["id"]))
        loose = events.save_event(self.payload(accountId=other["id"]))
        mark_opportunity_lost(opportunity["id"], {"lostReason": "Budget withdrawn"}, opportunity["modified"])
        frappe.set_user(self.manager)
        archive_account(account["id"])
        frappe.set_user(self.sales)
        before = frappe.db.count(events.DOCTYPE)
        for message, attempt in (
            # A new Event under it, and one moved under it.
            (ARCHIVED_ACCOUNT_LINK, lambda: events.save_event(self.payload(accountId=account["id"]))),
            (ARCHIVED_ACCOUNT_LINK, lambda: events.save_event(self.payload(accountId=account["id"]), loose["id"], loose["modified"])),
            # One of its own moved out, or given a deal (its closed one).
            (ARCHIVED_ACCOUNT_EDIT, lambda: events.save_event(self.payload(accountId=other["id"]), kept["id"], kept["modified"])),
            (ARCHIVED_ACCOUNT_EDIT, lambda: events.save_event(self.payload(accountId=account["id"], opportunityId=opportunity["id"]), kept["id"], kept["modified"])),
            # One done or cancelled, planned again.
            (ARCHIVED_ACCOUNT_REOPEN, lambda: events.save_event(self.payload(accountId=account["id"]), finished["id"], finished["modified"])),
            (ARCHIVED_ACCOUNT_REOPEN, lambda: events.save_event(self.payload(accountId=account["id"]), cancelled["id"], cancelled["modified"])),
        ):
            with self.subTest(message=message):
                with self.assertRaises(CrmApiException) as refused:
                    attempt()
                self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", message))
        self.assertEqual(frappe.db.count(events.DOCTYPE), before)
        self.assertEqual(frappe.db.get_value(events.DOCTYPE, loose["id"], "account"), other["id"])
        self.assertEqual(frappe.db.get_value(events.DOCTYPE, kept["id"], ["account", "opportunity", "status"]), (account["id"], None, "Planned"))
        # One of its own is kept up where it is, as a Visit planned before the archive is: its title, done.
        done = events.save_event(self.payload(accountId=account["id"], title="Exhibition, minutes written", status="Done"), kept["id"], kept["modified"])
        self.assertEqual((done["title"], done["status"], done["accountId"]), ("Exhibition, minutes written", "Done", account["id"]))
        # Its deal cleared: a way to keep it up once the deal's owner changed since (as assigning it to the deal's new
        # owner is).
        cleared = events.save_event(self.payload(accountId=account["id"]), dealt["id"], dealt["modified"])
        self.assertEqual((cleared["accountId"], cleared["opportunityId"]), (account["id"], ""))
        frappe.set_user(self.manager)
        unarchive_account(account["id"])
        frappe.set_user(self.sales)
        self.assertEqual(events.save_event(self.payload(accountId=account["id"]))["accountId"], account["id"])

    def test_an_archived_account_named_as_the_database_matches_it_takes_no_event(self):
        # The database matches names without regard to accents or width: a variant of an archived Account's name names
        # that Account, and the save takes the name as the database has it.
        from rayher_crm.services.accounts import ARCHIVED_ACCOUNT_LINK, archive_account, create_account
        frappe.set_user(self.sales)
        suffix = frappe.generate_hash(length=6)
        account = create_account({"name": f"Müller Event（{suffix}）", "shortName": f"Mu{suffix}", "segment": "Frontend",
                                  "tier": "A", "city": "上海", "region": "华东", "owner": self.sales})
        other, _, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        frappe.set_user(self.sales)
        loose = events.save_event(self.payload(accountId=other["id"]))
        frappe.set_user(self.manager)
        archive_account(account["id"])
        frappe.set_user(self.sales)
        variant = account["id"].replace("ü", "u").replace("（", "(").replace("）", ")")
        self.assertNotEqual(variant, account["id"])
        self.assertEqual(frappe.db.get_value("Customer", variant, "name"), account["id"])
        before = frappe.db.count(events.DOCTYPE)
        for attempt in (lambda: events.save_event(self.payload(accountId=variant)),
                        lambda: events.save_event(self.payload(accountId=variant), loose["id"], loose["modified"])):
            with self.assertRaises(CrmApiException) as refused:
                attempt()
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_ACCOUNT_LINK))
        self.assertEqual(frappe.db.count(events.DOCTYPE), before)
        self.assertEqual(frappe.db.get_value(events.DOCTYPE, loose["id"], "account"), other["id"])

    def test_an_archived_account_the_desk_keeps_from_the_user_is_not_told_archived(self):
        # Refused by the Desk's own permissions first, as it was before the archive: the Account is not shown to exist.
        from frappe.permissions import add_user_permission, remove_user_permission
        from rayher_crm.services.accounts import archive_account
        from rayher_crm.services.opportunities import mark_opportunity_lost
        allowed, _, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        hidden, deal, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        frappe.set_user(self.sales)
        mark_opportunity_lost(deal["id"], {"lostReason": "Budget withdrawn"}, deal["modified"])
        frappe.set_user(self.manager)
        archive_account(hidden["id"])
        frappe.set_user("Administrator")
        add_user_permission("Customer", allowed["id"], self.sales, ignore_permissions=True, applicable_for="CRM Event")
        frappe.clear_cache(user=self.sales)
        try:
            frappe.set_user(self.sales)
            with self.assertRaises(CrmApiException) as refused:
                events.save_event(self.payload(accountId=hidden["id"]))
            self.assertEqual(refused.exception.code, "SCOPE_DENIED")
        finally:
            frappe.set_user("Administrator")
            remove_user_permission("Customer", allowed["id"], self.sales, ignore_permissions=True)
            frappe.clear_cache(user=self.sales)

    def test_a_stale_save_assigning_an_inactive_owner_is_told_of_the_version_first(self):
        # The save's own order, whatever order its locks are taken in: the Event's scope and version, then its owner.
        inactive = self._user("event-inactive@example.invalid", "CRM Sales")
        frappe.db.set_value("User", inactive, "enabled", 0)
        frappe.set_user(self.manager)
        row = events.save_event(self.payload())
        events.save_event(self.payload(title="Industry exhibition, moved"), row["id"], row["modified"])
        with self.assertRaises(CrmApiException) as stale:
            events.save_event(self.payload(owner=inactive), row["id"], row["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

    def test_an_event_takes_the_user_the_event_its_accounts_shared_then_its_deals(self):
        account, opportunity, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        other, other_deal, _ = self._records(self.sales, "Event" + frappe.generate_hash(length=6))
        frappe.set_user(self.sales)
        row = events.save_event(self.payload(accountId=account["id"], opportunityId=opportunity["id"]))
        real_sql = frappe.db.sql
        locks: list[tuple[str, str]] = []

        def watch(query, *args, **kwargs):
            text = str(query)
            mode = "exclusive" if "FOR UPDATE" in text else "shared" if "LOCK IN SHARE MODE" in text else None
            # Every table the statement reads takes its lock: a join's rows, each of them.
            for table in re.findall(r"(?:FROM|JOIN)\s+`(tab[^`]+)`", text) if mode else ():
                locks.append((table, mode))
            return real_sql(query, *args, **kwargs)

        with patch.object(frappe.db, "sql", side_effect=watch):
            moved = events.save_event(self.payload(accountId=other["id"], opportunityId=other_deal["id"]), row["id"], row["modified"])
        self.assertEqual((moved["accountId"], moved["opportunityId"]), (other["id"], other_deal["id"]))
        # The User first (as a native rename holds it), the Event, the Accounts (shared, by one statement), the
        # Opportunities: the order the Account's archive and every writer under an Account take them in.
        first = list(dict.fromkeys(locks))
        self.assertEqual(first[:4], [
            ("tabUser", "exclusive"), ("tabCRM Event", "exclusive"), ("tabCustomer", "shared"), ("tabCRM Opportunity", "exclusive"),
        ], locks)
        self.assertNotIn(("tabCustomer", "exclusive"), locks)
        # Assigned to another owner (the Account public, its deal cleared): the owner's roles after the Event's row and
        # before the Accounts'.
        frappe.db.set_value("Customer", other["id"], "custom_crm_visibility", "Public")
        locks.clear()
        frappe.set_user(self.manager)
        with patch.object(frappe.db, "sql", side_effect=watch):
            assigned = events.save_event(self.payload(owner=self.other_sales, accountId=other["id"]), moved["id"], moved["modified"])
        self.assertEqual(assigned["owner"], self.other_sales)
        first = list(dict.fromkeys(locks))
        self.assertEqual(first[:4], [
            ("tabUser", "exclusive"), ("tabCRM Event", "exclusive"), ("tabHas Role", "exclusive"), ("tabCustomer", "shared"),
        ], locks)
        self.assertNotIn(("tabCustomer", "exclusive"), locks)

    def test_validation_pagination_and_manager_assignment(self):
        for invalid in ({"endDate": "2030-09-19"}, {"startDate": "not-a-date"}, {"status": "X"}, {"region": "not-registered"}, {"title": "a" * 141}, {"owner": self.other_sales}):
            with self.subTest(invalid=invalid), self.assertRaises(CrmApiException):
                events.save_event(self.payload(**invalid))
        frappe.set_user(self.manager)
        first = events.save_event(self.payload())
        second = events.save_event(self.payload(owner=self.other_sales))
        names = {row["id"] for row in events.list_events({"pageSize": 200})[0]}
        self.assertTrue({first["id"], second["id"]} <= names)
        rows, total, page, size = events.list_events({"page": 1, "pageSize": 1})
        self.assertEqual((len(rows), page, size), (1, 1, 1))
        self.assertGreaterEqual(total, 2)
        frappe.set_user(self.sales)
        self.assertFalse(frappe.has_permission(events.DOCTYPE, "create"))

    def test_customer_user_permissions_cover_rows_count_detail_and_proposed_links(self):
        from frappe.permissions import add_user_permission, remove_user_permission

        suffix = "EventUP" + frappe.generate_hash(length=6)
        allowed_account, _, _ = self._records(self.sales, suffix + "A")
        excluded_account, _, _ = self._records(self.sales, suffix + "B")
        allowed_input = self.payload(title=suffix, accountId=allowed_account["id"])
        excluded_input = self.payload(title=suffix, accountId=excluded_account["id"])
        allowed = events.save_event(allowed_input)
        excluded = events.save_event(excluded_input)
        for user in (self.sales, self.manager):
            with self.subTest(user=user):
                frappe.set_user("Administrator")
                add_user_permission("Customer", allowed_account["id"], user,
                                    ignore_permissions=True, applicable_for=events.DOCTYPE)
                frappe.clear_cache(user=user)
                frappe.set_user(user)
                try:
                    self.assertFalse(frappe.has_permission(events.DOCTYPE, "read", doc=frappe.get_doc(events.DOCTYPE, excluded["id"])))
                    rows, total, _, _ = events.list_events({"search": suffix})
                    self.assertEqual(([row["id"] for row in rows], total), ([allowed["id"]], 1))
                    self.assertEqual(events.get_event(allowed["id"])["id"], allowed["id"])
                    if user == self.manager:
                        from rayher_crm.services import cockpit
                        from rayher_crm.services.cockpit_plan import build_plan
                        customers = [{"name": account["id"]} for account in (allowed_account, excluded_account)]
                        plan_data = cockpit.load_plan_data(customers, [])
                        review_data = cockpit.load_data(customers, [])
                        for source in (plan_data, review_data):
                            self.assertEqual({row["name"] for row in source["events"]}, {allowed["id"]})
                        plan = build_plan(plan_data, {"period": "week", "anchor": "2030-09-23"}, datetime(2030, 9, 23))
                        self.assertEqual([row["id"] for row in plan["_details"]["events"]], [allowed["id"]])
                    for action in (
                        lambda: events.get_event(excluded["id"]),
                        lambda: events.save_event(excluded_input, excluded["id"], excluded["modified"]),
                        lambda: events.save_event(excluded_input, allowed["id"], allowed["modified"]),
                        lambda: events.save_event(excluded_input),
                    ):
                        with self.assertRaises(CrmApiException) as denied:
                            action()
                        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
                    self.assertEqual(frappe.db.count(events.DOCTYPE, {"title": suffix}), 2)
                    self.assertEqual(frappe.db.get_value(events.DOCTYPE, allowed["id"], "account"), allowed_account["id"])
                    if user == self.sales:
                        # An unrestricted manager cannot assign a new event to
                        # a sales owner whose own native link scope excludes it.
                        frappe.set_user(self.manager)
                        with self.assertRaises(CrmApiException) as denied:
                            events.save_event(excluded_input)
                        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
                        with self.assertRaises(CrmApiException) as denied:
                            events.save_event(excluded_input, allowed["id"], allowed["modified"])
                        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
                finally:
                    frappe.set_user("Administrator")
                    remove_user_permission("Customer", allowed_account["id"], user, ignore_permissions=True)
                    frappe.clear_cache(user=user)

    def test_manager_can_maintain_disabled_owner_history_but_cannot_assign_new_events(self):
        account, opportunity, _ = self._records(self.sales, "EventHistory" + frappe.generate_hash(length=6))
        payload = self.payload(accountId=account["id"], opportunityId=opportunity["id"])
        planned = events.save_event(payload)
        done = events.save_event({**payload, "status": "Done"})
        frappe.set_user("Administrator")
        frappe.db.set_value("User", self.sales, "enabled", 0)
        frappe.clear_cache(user=self.sales)
        try:
            frappe.set_user(self.manager)
            cancelled = events.save_event({**payload, "status": "Cancelled"}, planned["id"], planned["modified"])
            self.assertEqual((cancelled["status"], cancelled["owner"]), ("Cancelled", self.sales))
            edited = events.save_event({**payload, "status": "Done", "note": "History reviewed"}, done["id"], done["modified"])
            self.assertEqual(edited["completedAt"], done["completedAt"])
            self.assertEqual(frappe.db.get_value(events.DOCTYPE, done["id"], "completed_owner"), self.sales)
            with self.assertRaises(CrmApiException) as denied:
                events.save_event(payload)
            self.assertEqual(denied.exception.code, "VALIDATION_ERROR")
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_value("User", self.sales, "enabled", 1)
            frappe.clear_cache(user=self.sales)

    def test_cockpit_event_query_excludes_unrelated_accounts_before_loading_and_omits_notes(self):
        from rayher_crm.services import cockpit

        suffix = "EventScope" + frappe.generate_hash(length=6)
        allowed_account, _, _ = self._records(self.sales, suffix + "A")
        excluded_account, _, _ = self._records(self.sales, suffix + "B")
        allowed = events.save_event(self.payload(accountId=allowed_account["id"], note="n" * 10000))
        excluded = events.save_event(self.payload(accountId=excluded_account["id"], note="x" * 10000))
        standalone = events.save_event(self.payload())
        empty_link = events.save_event(self.payload())
        frappe.db.set_value(events.DOCTYPE, empty_link["id"], "account", "", update_modified=False)
        own_ids = {row["id"] for row in (allowed, excluded, standalone, empty_link)}
        frappe.set_user(self.manager)
        original_list = frappe.get_list
        database_rows = []

        def observed_list(*args, **kwargs):
            rows = original_list(*args, **kwargs)
            database_rows.extend(rows)
            return rows

        with patch.object(frappe, "get_list", side_effect=observed_list):
            rows = cockpit.event_rows({allowed_account["id"]})
        expected = {allowed["id"], standalone["id"], empty_link["id"]}
        self.assertEqual({row["name"] for row in database_rows} & own_ids, expected)
        self.assertEqual({row["name"] for row in rows} & own_ids, expected)
        self.assertTrue(all("note" not in row and "modified" not in row for row in database_rows))
        self.assertEqual({row["name"] for row in cockpit.event_rows(set())} & own_ids,
                         {standalone["id"], empty_link["id"]})

    def test_event_only_classification_survives_catalogue_reconciliation(self):
        from rayher_crm.services.equipment import list_equipment_types, register_equipment
        from rayher_crm.services.regions import list_regions, register_region, REGION_FIELD
        from rayher_crm.setup.custom_fields import _custom_fields_for_install
        from rayher_crm.setup.equipment_types import sync

        suffix = frappe.generate_hash(length=6)
        region = register_region("Event Only " + suffix)
        equipment = register_equipment("Event Tool " + suffix)
        row = events.save_event(self.payload(region=region, equipment=equipment))
        # Neither classification is present on a Customer or Opportunity.
        field = next(field for field in _custom_fields_for_install()["Customer"] if field["fieldname"] == "custom_crm_region")
        self.assertIn(region, field["options"].splitlines())
        frappe.db.set_value("Custom Field", REGION_FIELD, "options", field["options"])
        frappe.clear_cache(doctype="Customer")
        sync()
        self.assertIn(region, list_regions())
        self.assertIn(equipment, list_equipment_types())
        cancelled = events.save_event(self.payload(region=region, equipment=equipment, status="Cancelled"), row["id"], row["modified"])
        self.assertEqual(cancelled["status"], "Cancelled")

    def test_identity_merge_keeps_existing_event_maintenance_for_nonassignable_destinations(self):
        from frappe.model.rename_doc import rename_doc

        for role, enabled in (("CRM Sales", 0), ("CRM Manager", 1)):
            with self.subTest(role=role, enabled=enabled):
                frappe.set_user("Administrator")
                token = frappe.generate_hash(length=8)
                source = self._user(f"event-merge-{token}-source@example.invalid", "CRM Sales")
                destination = self._user(f"event-merge-{token}-dest@example.invalid", role)
                frappe.set_user(self.manager)
                payload = self.payload(owner=source)
                planned = events.save_event(payload)
                completed = events.save_event({**payload, "status": "Done"})
                frappe.set_user("Administrator")
                frappe.db.set_value("User", destination, "enabled", enabled)
                frappe.clear_cache(user=destination)
                rename_doc("User", source, destination, merge=True, force=True,
                           ignore_permissions=True, rebuild_search=False)
                frappe.set_user(self.manager)
                current = events.get_event(planned["id"])
                self.assertEqual(current["owner"], destination)
                cancelled = events.save_event({**payload, "owner": destination, "status": "Cancelled"},
                                              current["id"], current["modified"])
                self.assertEqual(cancelled["status"], "Cancelled")
                edited = events.save_event({**payload, "owner": destination, "status": "Done", "note": "History maintained"},
                                          completed["id"], completed["modified"])
                self.assertEqual(edited["completedAt"], completed["completedAt"])
                self.assertEqual(frappe.db.get_value(events.DOCTYPE, completed["id"], "completed_owner"), destination)
                with self.assertRaises(CrmApiException):
                    events.save_event({**payload, "owner": destination})
                frappe.set_user(self.other_sales)
                with self.assertRaises(CrmApiException) as denied:
                    events.get_event(planned["id"])
                self.assertEqual(denied.exception.code, "SCOPE_DENIED")
