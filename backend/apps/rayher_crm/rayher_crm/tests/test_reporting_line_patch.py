from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.patches.v1_0 import clear_self_reporting_contacts
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contacts import create_contact, get_contact


class TestReportingLinePatch(FrappeTestCase):
    """What the old merge left behind (F1-06), as `clear_self_reporting_contacts` puts it right."""

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.account = create_account({
            "name": "Reporting Line Patch", "shortName": "RLPatch", "segment": "Frontend", "tier": "A",
            "city": "上海", "region": "华东", "owner": "Administrator",
        })["id"]

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _contact(self, name: str, reports_to: str | None = None) -> str:
        return create_contact({
            "accountId": self.account, "name": name, "title": "Director", "department": "Engineering",
            "phone": "13800000001", "email": f"{name.replace(' ', '.').lower()}@example.invalid",
            "relationship": "Developing", "owner": "Administrator", "status": "Active",
            **({"reportsToContactId": reports_to} if reports_to else {}),
        })["id"]

    def _merged_by_the_old_merge(self, duplicate: str, survivor: str) -> None:
        # The old merge archived the duplicate and kept its line; a survivor who reported to it was left
        # reporting to themselves.
        frappe.db.set_value("Contact", duplicate, {"custom_crm_status": "Archived", "custom_crm_merged_into": survivor})

    def _line(self, name: str) -> str | None:
        return frappe.db.get_value("Contact", name, "custom_crm_reports_to") or None

    def test_self_loops_take_the_merged_line_merged_contacts_lose_theirs_and_loops_are_cut(self):
        top = self._contact("Patch Top")
        # The survivor reported to the duplicate, whose own line led to the Top: the survivor's line is the Top's.
        survivor = self._contact("Patch Survivor")
        duplicate = self._contact("Patch Duplicate", top)
        self._merged_by_the_old_merge(duplicate, survivor)
        frappe.db.set_value("Contact", survivor, "custom_crm_reports_to", survivor)
        # Two duplicates merged into one survivor, with two different lines: which one the survivor reported to
        # cannot be told, and the line goes.
        other_top = self._contact("Patch Other Top")
        twice = self._contact("Patch Twice")
        for name, line in (("Patch Twice A", top), ("Patch Twice B", other_top)):
            self._merged_by_the_old_merge(self._contact(name, line), twice)
        frappe.db.set_value("Contact", twice, "custom_crm_reports_to", twice)
        # Two duplicates again, the earlier one with a line, the later one (the survivor's manager) without: the
        # line goes too, not the earlier one's.
        later = self._contact("Patch Later")
        self._merged_by_the_old_merge(self._contact("Patch Later Earlier", top), later)
        self._merged_by_the_old_merge(self._contact("Patch Later Manager"), later)
        frappe.db.set_value("Contact", later, "custom_crm_reports_to", later)
        # One duplicate without a line: the survivor had a manager without one, and keeps none.
        alone = self._contact("Patch Alone")
        self._merged_by_the_old_merge(self._contact("Patch Alone Manager"), alone)
        frappe.db.set_value("Contact", alone, "custom_crm_reports_to", alone)
        # A merged Contact with a line of its own, which kept it among its manager's direct reports.
        merged = self._contact("Patch Merged", top)
        self._merged_by_the_old_merge(merged, other_top)
        # A loop of three.
        first = self._contact("Patch Loop First")
        second = self._contact("Patch Loop Second", first)
        third = self._contact("Patch Loop Third", second)
        frappe.db.set_value("Contact", first, "custom_crm_reports_to", third)
        # A line as it should be, left alone.
        fine = self._contact("Patch Fine", top)
        # The one Contact merged into a self-reporting survivor was itself left reporting to themselves by an earlier
        # merge: the line kept on them (themselves, merged away) is no line to give the survivor.
        chain = self._contact("Patch Chain")
        earlier = self._contact("Patch Chain Earlier")
        self._merged_by_the_old_merge(earlier, chain)
        frappe.db.set_value("Contact", earlier, "custom_crm_reports_to", earlier)
        frappe.db.set_value("Contact", chain, "custom_crm_reports_to", chain)

        clear_self_reporting_contacts.execute()

        self.assertEqual(self._line(survivor), top)
        self.assertIsNone(self._line(twice))
        self.assertIsNone(self._line(later))
        self.assertIsNone(self._line(alone))
        self.assertIsNone(self._line(duplicate))
        self.assertIsNone(self._line(merged))
        loop_lines = [self._line(name) for name in (first, second, third)]
        self.assertEqual(loop_lines.count(None), 1)
        self.assertEqual(self._line(fine), top)
        self.assertIsNone(self._line(chain))
        self.assertIsNone(self._line(earlier))
        # The Top's direct reports are those who report to them and were not merged away.
        self.assertEqual(
            sorted(item["id"] for item in get_contact(top)["directReports"]), sorted([survivor, fine]),
        )
        logged = frappe.get_all(
            "Error Log", filters={"method": clear_self_reporting_contacts.LOG_TITLE}, fields=["error"],
            order_by="creation desc", limit=1,
        )
        self.assertEqual(len(logged), 1)
        for expected in (f"{survivor} -> {top}", f"{twice} (2 Contacts merged into them)", f"{later} (2 Contacts merged into them)", "had no line", f"cannot be restored: {earlier}", duplicate, merged):
            self.assertIn(expected, logged[0].error)
        self.assertIn(" -> ", logged[0].error.rsplit("Loops cut", 1)[1])

        # Run again, nothing is left to do: the lines stay, and no second log is written.
        logs_before = frappe.db.count("Error Log", {"method": clear_self_reporting_contacts.LOG_TITLE})
        clear_self_reporting_contacts.execute()
        self.assertEqual(frappe.db.count("Error Log", {"method": clear_self_reporting_contacts.LOG_TITLE}), logs_before)
        self.assertEqual(self._line(survivor), top)
        self.assertEqual([self._line(name) for name in (first, second, third)], loop_lines)
