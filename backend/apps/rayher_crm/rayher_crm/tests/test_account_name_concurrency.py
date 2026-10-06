"""Two requests naming Accounts the same way, and two merges that would close a reporting loop between them.

A second database connection stands in for the other request. The rows it must see are committed, and taken
out again by hand at the end: the rollback of the suite does not reach them.
"""
from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.database import get_db
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import accounts as account_service
from rayher_crm.services import contacts as contact_service
from rayher_crm.services.accounts import create_account, update_account
from rayher_crm.services.contacts import create_contact, merge_contacts


class TestAccountNameConcurrency(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        # Nothing an earlier test left pending may be committed with this test's rows.
        frappe.db.rollback()
        frappe.set_user("Administrator")
        self.sales = self._user("crm-account-name-sales@example.invalid", "CRM Sales")
        frappe.db.commit()
        self.committed_accounts: list[str] = []
        self.committed_contacts: list[str] = []

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for name in self.committed_contacts:
            if frappe.db.exists("Contact", name):
                frappe.delete_doc("Contact", name, ignore_permissions=True, force=True)
        for name in self.committed_accounts:
            frappe.db.delete("CRM Notification Event", {"source_doctype": "Customer", "source_name": name})
            if frappe.db.exists("Customer", name):
                frappe.delete_doc("Customer", name, ignore_permissions=True, force=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _account_input(self, name: str) -> dict:
        return {"name": name, "shortName": name[:8], "segment": "Frontend", "tier": "A", "city": "上海",
                "region": "华东", "owner": self.sales}

    def _contact_input(self, account_id: str, name: str, **overrides) -> dict:
        return {"accountId": account_id, "name": name, "title": "Engineer", "department": "R&D",
                "phone": "13800000002", "email": f"{name.replace(' ', '.').lower()}@example.invalid",
                "relationship": "Developing", "owner": self.sales, "status": "Active", **overrides}

    def _other(self):
        other = get_db(
            host=frappe.conf.db_host, port=frappe.conf.db_port, user=frappe.conf.db_user or frappe.conf.db_name,
            password=frappe.conf.db_password, cur_db_name=frappe.conf.db_name,
        )
        other.connect()
        return other

    def _committed(self, account: dict, contacts: list[dict] = ()) -> None:
        frappe.db.commit()
        self.committed_accounts.append(account["id"])
        self.committed_contacts.extend(contact["id"] for contact in contacts)

    def test_an_account_named_by_another_request_since_the_snapshot_is_seen(self):
        frappe.set_user(self.sales)
        first = create_account(self._account_input("Name Race Co"))
        self._committed(first)
        # A read opens this request's snapshot; the other request then renames its Account to the name this
        # request is about to use, and commits.
        frappe.db.get_value("Customer", first["id"], "customer_name")
        other = self._other()
        try:
            other.sql("UPDATE `tabCustomer` SET `customer_name` = 'Name Race Twin' WHERE `name` = %s", (first["id"],))
            other.commit()
            self.assertEqual(frappe.db.get_value("Customer", first["id"], "customer_name"), "Name Race Co")
            with self.assertRaises(CrmApiException) as taken:
                create_account(self._account_input("name race twin"))
            self.assertEqual((taken.exception.code, taken.exception.field_errors), ("CONFLICT", {"name": first["id"]}))
            # The snapshot still calls that Account "Name Race Co": a create of that name is refused for it too,
            # as the check believes either view, until a request with a fresh snapshot asks.
            with self.assertRaises(CrmApiException):
                create_account(self._account_input("Name Race Co"))
            frappe.db.commit()
            self.assertEqual(create_account(self._account_input("Name Race Co"))["name"], "Name Race Co")
        finally:
            other.close()

    def test_two_requests_naming_an_account_the_same_way_take_turns(self):
        frappe.set_user(self.sales)
        other = self._other()
        try:
            # The other request holds the name (it is creating "Name Turn Co" and has not committed yet).
            name_key = account_service._name_key("name turn co")
            self.assertEqual(other.sql("SELECT GET_LOCK(%s, 1)", (name_key,))[0][0], 1)
            with patch.object(account_service, "NAME_LOCK_TIMEOUT", 1):
                with self.assertRaises(CrmApiException) as busy:
                    create_account(self._account_input("Name Turn Co"))
            self.assertEqual(
                (busy.exception.code, busy.exception.public_message),
                ("CONFLICT", "Another request is naming an Account like this; try again."),
            )
            other.sql("SELECT RELEASE_LOCK(%s)", (name_key,))
            # Released: the name is free, and this request holds it to its commit.
            created = create_account(self._account_input("Name Turn Co"))
            self.assertEqual(created["name"], "Name Turn Co")
            self.assertEqual(other.sql("SELECT IS_USED_LOCK(%s) IS NOT NULL", (name_key,))[0][0], 1)
            self._committed(created)
            self.assertEqual(other.sql("SELECT IS_USED_LOCK(%s) IS NOT NULL", (name_key,))[0][0], 0)
            # A rename to a name in use waits its turn the same way.
            with patch.object(account_service, "NAME_LOCK_TIMEOUT", 1):
                self.assertEqual(other.sql("SELECT GET_LOCK(%s, 1)", (name_key,))[0][0], 1)
                renamed = create_account(self._account_input("Name Turn Other"))
                self.committed_accounts.append(renamed["id"])
                with self.assertRaises(CrmApiException) as waits:
                    update_account(renamed["id"], self._account_input("Name Turn Co"), renamed["modified"])
                self.assertEqual(waits.exception.code, "CONFLICT")
                other.sql("SELECT RELEASE_LOCK(%s)", (name_key,))
        finally:
            other.close()

    def test_two_spellings_the_database_calls_one_name_take_one_lock(self):
        # The comparison runs under the column's collation (case, accents, the width of a character aside); the
        # lock is keyed the same way, or two requests naming "Example（中国）" and "example(中国)" would not meet.
        frappe.set_user(self.sales)
        other = self._other()
        try:
            key_of = {spelling: account_service._name_key(spelling.strip().lower()) for spelling in ("Example（中国）", "example(中国)")}
            self.assertEqual(key_of["Example（中国）"], key_of["example(中国)"])
            self.assertNotEqual(key_of["example(中国)"], account_service._name_key("example (china)"))
            self.assertEqual(other.sql("SELECT GET_LOCK(%s, 1)", (key_of["example(中国)"],))[0][0], 1)
            with patch.object(account_service, "NAME_LOCK_TIMEOUT", 1):
                with self.assertRaises(CrmApiException) as busy:
                    create_account(self._account_input("Example（中国）"))
            self.assertEqual(busy.exception.code, "CONFLICT")
            other.sql("SELECT RELEASE_LOCK(%s)", (key_of["example(中国)"],))
        finally:
            other.close()

    def test_the_merges_of_one_account_take_turns(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Merge Turn Co"))
        a = create_contact(self._contact_input(account["id"], "Merge Turn A"))
        b = create_contact(self._contact_input(account["id"], "Merge Turn B"))
        self._committed(account, [a, b])
        frappe.set_user("Administrator")
        other = self._other()
        wait = frappe.db.sql("SELECT @@innodb_lock_wait_timeout")[0][0]
        try:
            # Another merge of this Account holds its row: this one waits for it (a lock wait timeout of one
            # second shows it) instead of reading lines the other has not committed.
            other.sql("SELECT `name` FROM `tabCustomer` WHERE `name` = %s FOR UPDATE", (account["id"],))
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout = 1")
            with self.assertRaises(frappe.QueryTimeoutError):
                merge_contacts(a["id"], b["id"])
            self.assertEqual(frappe.db.get_value("Contact", b["id"], "custom_crm_status"), "Active")
        finally:
            frappe.db.sql("SET SESSION innodb_lock_wait_timeout = %s", (wait,))
            other.rollback()
            other.close()

    def test_the_walk_up_the_survivors_line_reads_what_was_committed_meanwhile(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Merge Walk Co"))
        top = create_contact(self._contact_input(account["id"], "Merge Walk Top"))
        survivor = create_contact(self._contact_input(account["id"], "Merge Walk S", reportsToContactId=top["id"]))
        duplicate = create_contact(self._contact_input(account["id"], "Merge Walk D"))
        report = create_contact(self._contact_input(account["id"], "Merge Walk R", reportsToContactId=duplicate["id"]))
        self._committed(account, [top, survivor, duplicate, report])
        frappe.set_user("Administrator")
        frappe.db.get_value("Contact", top["id"], "custom_crm_reports_to")

        # Before this merge takes its locks, another request makes the Top report to R and commits. Merging D into S
        # makes R report to S; the walk up from S (S -> Top -> R -> S) sees the Top's new line only as committed.
        other = self._other()
        lock_pair = contact_service._lock_contact_pair

        def other_edit_first(first: str, second: str):
            other.sql("UPDATE `tabContact` SET `custom_crm_reports_to` = %s WHERE `name` = %s", (report["id"], top["id"]))
            other.commit()
            return lock_pair(first, second)

        try:
            with patch.object(contact_service, "_lock_contact_pair", side_effect=other_edit_first):
                with self.assertRaises(CrmApiException) as loop:
                    merge_contacts(survivor["id"], duplicate["id"])
            self.assertEqual(loop.exception.code, "VALIDATION_ERROR")
            frappe.db.rollback()
            self.assertEqual(other.sql("SELECT `custom_crm_reports_to` FROM `tabContact` WHERE `name` = %s", (report["id"],))[0][0], duplicate["id"])
        finally:
            other.close()

    def test_a_merge_whose_pair_was_merged_the_other_way_meanwhile_is_refused(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Merge Both Ways Co"))
        s = create_contact(self._contact_input(account["id"], "Merge Both Ways S"))
        d = create_contact(self._contact_input(account["id"], "Merge Both Ways D"))
        self._committed(account, [s, d])
        frappe.set_user("Administrator")
        frappe.db.get_value("Contact", s["id"], "custom_crm_status")

        # Two users merge the pair, each their way. The other's merge (S into D) is committed while this one (D
        # into S) waits for its locks: read again under them, S is merged already, and this merge changes nothing
        # (both archived, each merged into the other, otherwise).
        other = self._other()
        lock_pair = contact_service._lock_contact_pair

        def other_merge_first(first: str, second: str):
            other.sql(
                "UPDATE `tabContact` SET `custom_crm_status` = 'Archived', `custom_crm_merged_into` = %s, `modified` = NOW(6) WHERE `name` = %s",
                (d["id"], s["id"]),
            )
            other.commit()
            return lock_pair(first, second)

        try:
            with patch.object(contact_service, "_lock_contact_pair", side_effect=other_merge_first):
                with self.assertRaises(CrmApiException) as refused:
                    merge_contacts(s["id"], d["id"])
            self.assertEqual(refused.exception.code, "CONFLICT")
            frappe.db.rollback()
            rows = dict(other.sql("SELECT `name`, `custom_crm_merged_into` FROM `tabContact` WHERE `name` IN (%s, %s)", (s["id"], d["id"])))
            self.assertEqual(rows[s["id"]], d["id"])
            self.assertFalse(rows[d["id"]])
            self.assertEqual(other.sql("SELECT `custom_crm_status` FROM `tabContact` WHERE `name` = %s", (d["id"],))[0][0], "Active")
        finally:
            other.close()

    def test_a_merge_whose_duplicate_moved_to_another_account_meanwhile_is_refused(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Merge Moved Co"))
        elsewhere = create_account(self._account_input("Merge Moved Elsewhere"))
        s = create_contact(self._contact_input(account["id"], "Merge Moved S"))
        d = create_contact(self._contact_input(account["id"], "Merge Moved D"))
        self._committed(account, [s, d])
        self._committed(elsewhere)
        frappe.set_user("Administrator")

        # An edit moves D to another Account, and is committed, while this merge (D into S) waits for its locks:
        # read again under them, D is the other Account's, and the Contacts of two Accounts are not merged.
        other = self._other()
        lock_pair = contact_service._lock_contact_pair

        def other_edit_first(first: str, second: str):
            other.sql(
                "UPDATE `tabDynamic Link` SET `link_name` = %s WHERE `parenttype` = 'Contact' AND `parent` = %s AND `link_doctype` = 'Customer'",
                (elsewhere["id"], d["id"]),
            )
            other.sql("UPDATE `tabContact` SET `modified` = NOW(6) WHERE `name` = %s", (d["id"],))
            other.commit()
            return lock_pair(first, second)

        try:
            with patch.object(contact_service, "_lock_contact_pair", side_effect=other_edit_first):
                with self.assertRaises(CrmApiException) as refused:
                    merge_contacts(s["id"], d["id"])
            self.assertEqual(
                (refused.exception.code, refused.exception.public_message),
                ("CONFLICT", "Contacts from different accounts cannot be merged."),
            )
            frappe.db.rollback()
            status, merged_into = other.sql(
                "SELECT `custom_crm_status`, `custom_crm_merged_into` FROM `tabContact` WHERE `name` = %s", (d["id"],),
            )[0]
            self.assertEqual(status, "Active")
            self.assertFalse(merged_into)
            self.assertEqual(
                other.sql(
                    "SELECT `link_name` FROM `tabDynamic Link` WHERE `parenttype` = 'Contact' AND `parent` = %s AND `link_doctype` = 'Customer'",
                    (d["id"],),
                ),
                ((elsewhere["id"],),),
            )
        finally:
            other.close()

    def test_a_merge_whose_duplicate_was_archived_meanwhile_is_refused(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Merge Archived Co"))
        s = create_contact(self._contact_input(account["id"], "Merge Archived S"))
        d = create_contact(self._contact_input(account["id"], "Merge Archived D"))
        self._committed(account, [s, d])
        frappe.set_user("Administrator")

        # D is archived (deleted from the page), and that committed, while this merge waits for its locks: read
        # again under them, D is archived, and goes into no merge.
        other = self._other()
        lock_pair = contact_service._lock_contact_pair

        def other_archive_first(first: str, second: str):
            other.sql(
                "UPDATE `tabContact` SET `custom_crm_status` = 'Archived', `modified` = NOW(6) WHERE `name` = %s", (d["id"],),
            )
            other.commit()
            return lock_pair(first, second)

        try:
            with patch.object(contact_service, "_lock_contact_pair", side_effect=other_archive_first):
                with self.assertRaises(CrmApiException) as refused:
                    merge_contacts(s["id"], d["id"])
            self.assertEqual(refused.exception.code, "CONFLICT")
            frappe.db.rollback()
            rows = other.sql(
                "SELECT `name`, `custom_crm_status`, `custom_crm_merged_into` FROM `tabContact` WHERE `name` IN (%s, %s)",
                (s["id"], d["id"]),
            )
            self.assertEqual({row[0]: row[1] for row in rows}, {s["id"]: "Active", d["id"]: "Archived"})
            self.assertFalse(any(row[2] for row in rows))
        finally:
            other.close()

    def test_the_duplicates_direct_reports_are_read_as_committed_meanwhile(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Merge Reports Co"))
        t = create_contact(self._contact_input(account["id"], "Merge Reports T"))
        g = create_contact(self._contact_input(account["id"], "Merge Reports G"))
        s = create_contact(self._contact_input(account["id"], "Merge Reports S"))
        b = create_contact(self._contact_input(account["id"], "Merge Reports B", reportsToContactId=g["id"]))
        self._committed(account, [t, g, s, b])
        frappe.set_user("Administrator")

        # B reports to G in this request's snapshot. Another merge (B into S), committed while this one (G into T)
        # waits for its locks, archived B and cleared B's line: B is nobody's direct report now, and this merge
        # leaves B's line alone instead of making B report to T as the snapshot would have it.
        other = self._other()
        lock_pair = contact_service._lock_contact_pair

        def other_merge_first(first: str, second: str):
            other.sql(
                "UPDATE `tabContact` SET `custom_crm_status` = 'Archived', `custom_crm_merged_into` = %s, "
                "`custom_crm_reports_to` = NULL, `modified` = NOW(6) WHERE `name` = %s",
                (s["id"], b["id"]),
            )
            other.commit()
            return lock_pair(first, second)

        try:
            with patch.object(contact_service, "_lock_contact_pair", side_effect=other_merge_first):
                merge_contacts(t["id"], g["id"])
            frappe.db.commit()
            rows = dict(other.sql(
                "SELECT `name`, `custom_crm_reports_to` FROM `tabContact` WHERE `name` IN (%s, %s)", (g["id"], b["id"]),
            ))
            self.assertIsNone(rows[b["id"]])
            self.assertIsNone(rows[g["id"]])
            self.assertEqual(other.sql("SELECT `custom_crm_merged_into` FROM `tabContact` WHERE `name` = %s", (g["id"],))[0][0], t["id"])
        finally:
            other.close()

    def test_two_merges_cannot_close_a_reporting_loop_between_them(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Merge Race Co"))
        a = create_contact(self._contact_input(account["id"], "Merge Race A"))
        b = create_contact(self._contact_input(account["id"], "Merge Race B", reportsToContactId=a["id"]))
        c = create_contact(self._contact_input(account["id"], "Merge Race C"))
        d = create_contact(self._contact_input(account["id"], "Merge Race D", reportsToContactId=c["id"]))
        self._committed(account, [a, b, c, d])
        frappe.set_user("Administrator")
        frappe.db.get_value("Contact", c["id"], "custom_crm_reports_to")

        # A reports to B? No: B reports to A, D reports to C. This request merges A into D (D takes A's report B,
        # and A's line). Meanwhile another request merged C into B and committed: D reports to B now. Were the
        # lines read from this request's snapshot, B would be made to report to D while D reports to B.
        other = self._other()
        lock_pair = contact_service._lock_contact_pair

        def other_merge_first(first: str, second: str):
            other.sql("UPDATE `tabContact` SET `custom_crm_reports_to` = %s WHERE `name` = %s", (b["id"], d["id"]))
            other.sql("UPDATE `tabContact` SET `custom_crm_status` = 'Archived', `custom_crm_merged_into` = %s WHERE `name` = %s", (b["id"], c["id"]))
            other.commit()
            return lock_pair(first, second)

        try:
            with patch.object(contact_service, "_lock_contact_pair", side_effect=other_merge_first):
                with self.assertRaises(CrmApiException) as loop:
                    merge_contacts(d["id"], a["id"])
            self.assertEqual(loop.exception.code, "VALIDATION_ERROR")
            frappe.db.rollback()
            lines = dict(other.sql("SELECT `name`, `custom_crm_reports_to` FROM `tabContact` WHERE `name` IN (%s, %s, %s)", (a["id"], b["id"], d["id"])))
            self.assertEqual(lines, {a["id"]: None, b["id"]: a["id"], d["id"]: b["id"]})
            self.assertEqual(other.sql("SELECT `custom_crm_status` FROM `tabContact` WHERE `name` = %s", (a["id"],))[0][0], "Active")
        finally:
            other.close()
