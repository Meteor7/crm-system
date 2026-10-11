"""A Visit changed by another request while its meeting file is being scanned.

The scan runs before the Visit's row is locked. A second database connection stands in for the other request;
the rows it must see are committed, and taken out again by hand at the end, as test_account_name_concurrency does.
"""

from __future__ import annotations

import frappe
from frappe.database import get_db
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.visit_meetings import update_record as update_meeting_record
from rayher_crm.services.visit_meetings import upload as upload_meeting_file
from rayher_crm.services.visits import create_visit
from rayher_crm.tests.test_contact_file_api import Scanner

COMPLETE_RECORD = (
    "Meeting purpose: Discuss project\nAttendees: Customer A, Sales A\nAgenda: Introduce solution\n"
    "Summary: Requirements confirmed\nConclusion: Proceed\nFollowup: Send proposal\n"
).encode()


class TestVisitUploadConcurrency(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        # Nothing an earlier test left pending may be committed with this test's rows.
        frappe.db.rollback()
        frappe.set_user("Administrator")
        self.manager = self._user("crm-visit-race-manager@example.invalid", "CRM Manager")
        self.sales = self._user("crm-visit-race-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-visit-race-other@example.invalid", "CRM Sales")
        frappe.db.commit()
        self.committed: list[tuple[str, str]] = []

    def tearDown(self):
        frappe.set_user("Administrator")
        # The Visit's row lock is released before its row is removed.
        frappe.db.rollback()
        for doctype, name in self.committed:
            frappe.db.delete("CRM Notification Event", {"source_doctype": doctype, "source_name": name})
            if frappe.db.exists(doctype, name):
                # Permanently: a deletion that keeps a Deleted Document would commit that archive instead.
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, delete_permanently=True)
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

    def _committed_visit(self) -> str:
        suffix = frappe.generate_hash(length=8)
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"Visit race {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East", "owner": self.sales,
        })
        visit = create_visit({
            "accountId": account["id"], "primaryContactId": "", "subject": "Fab review", "date": "2026-08-20",
            "type": "On-site", "owner": self.sales, "objective": "Confirm evaluation criteria",
        })
        frappe.db.commit()
        self.committed[:0] = [("CRM Visit", visit["id"]), ("Customer", account["id"])]
        # A read opens this request's snapshot, before the other request commits.
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "visit_owner"), self.sales)
        return visit["id"]

    def _other(self):
        other = get_db(
            host=frappe.conf.db_host, port=frappe.conf.db_port, user=frappe.conf.db_user or frappe.conf.db_name,
            password=frappe.conf.db_password, cur_db_name=frappe.conf.db_name,
        )
        other.connect()
        return other

    def _committed_by_the_other_request(self, assignment: str, values: tuple) -> None:
        other = self._other()
        try:
            other.sql(f"UPDATE `tabCRM Visit` SET {assignment}, `modified` = NOW(6) WHERE `name` = %s", values)
            other.commit()
        finally:
            other.close()

    def test_a_visit_reassigned_during_the_scan_refuses_its_former_owner(self):
        visit_id = self._committed_visit()
        self._committed_by_the_other_request("`visit_owner` = %s", (self.other_sales, visit_id))
        # The snapshot still has the former owner; the row read under its lock has the new one.
        self.assertEqual(frappe.db.get_value("CRM Visit", visit_id, "visit_owner"), self.sales)
        with self.assertRaises(CrmApiException) as refused:
            upload_meeting_file(visit_id, "notes.txt", "text/plain", b"Meeting notes", scanner=Scanner())
        self.assertEqual(refused.exception.code, "SCOPE_DENIED")
        self.assertFalse(frappe.db.exists("File", {"attached_to_doctype": "CRM Visit", "attached_to_name": visit_id}))
        self.assertFalse(frappe.db.exists("CRM Visit Meeting Record", {"visit": visit_id}))

    def test_an_edit_committed_during_the_scan_is_kept_when_the_record_submits_the_visit(self):
        visit_id = self._committed_visit()
        self._committed_by_the_other_request("`next_action` = 'Bring samples'", (visit_id,))
        # The snapshot still has no next action; the row read under its lock has the Manager's.
        self.assertFalse(frappe.db.get_value("CRM Visit", visit_id, "next_action"))
        upload_meeting_file(visit_id, "minutes.txt", "text/plain", COMPLETE_RECORD, scanner=Scanner())
        # Read under the lock, as committed plus this transaction's own write: the Manager's edit survived the save
        # that submitted the Visit, which a copy from the snapshot would have written over, or failed on.
        status, next_action = frappe.db.sql(
            "SELECT `status`, `next_action` FROM `tabCRM Visit` WHERE `name` = %s FOR UPDATE", (visit_id,),
        )[0]
        self.assertEqual((status, next_action), ("Minutes Submitted", "Bring samples"))

    def test_a_record_saved_by_another_request_during_the_scan_is_replaced_by_the_upload(self):
        visit_id = self._committed_visit()
        update_meeting_record(visit_id, {"purpose": "Typed in by hand", "attendees": "Customer A"})
        frappe.db.commit()
        record = frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit_id}, ["name", "modified"], as_dict=True)
        self.committed.insert(0, ("CRM Visit Meeting Record", record.name))
        other = self._other()
        try:
            other.sql(
                "UPDATE `tabCRM Visit Meeting Record` SET `summary` = 'Added meanwhile', `modified` = NOW(6) WHERE `name` = %s",
                (record.name,),
            )
            other.commit()
        finally:
            other.close()
        # The snapshot still has the record as this request first saw it.
        self.assertEqual(frappe.db.get_value("CRM Visit Meeting Record", record.name, "modified"), record.modified)
        # An upload re-parses the file over the record, whenever it comes; one during another request's save must
        # read the record it writes over under its lock, or Frappe refuses the save as out of date.
        upload_meeting_file(visit_id, "minutes.txt", "text/plain", COMPLETE_RECORD, scanner=Scanner())
        purpose, summary, status = frappe.db.sql(
            "SELECT r.`purpose`, r.`summary`, v.`status` FROM `tabCRM Visit Meeting Record` r"
            " JOIN `tabCRM Visit` v ON v.`name` = r.`visit` WHERE r.`name` = %s FOR UPDATE", (record.name,),
        )[0]
        self.assertEqual((purpose, summary, status), ("Discuss project", "Requirements confirmed", "Minutes Submitted"))

    def _first_record_added_by_the_other_request(self, visit_id: str) -> str:
        """A first meeting record committed by a request that held the Visit's lock before this one, after this
        request's snapshot: this request's own lookup cannot find it."""

        name = f"CRM-VMR-RACE-{frappe.generate_hash(length=8)}"
        self.committed.insert(0, ("CRM Visit Meeting Record", name))
        other = self._other()
        try:
            other.sql(
                "INSERT INTO `tabCRM Visit Meeting Record` (`name`, `creation`, `modified`, `modified_by`, `owner`,"
                " `docstatus`, `idx`, `visit`, `purpose`, `parse_status`, `manually_corrected`)"
                " VALUES (%s, NOW(6), NOW(6), %s, %s, 0, 0, %s, 'Typed in meanwhile', 'Parsed', 1)",
                (name, self.manager, self.manager, visit_id),
            )
            other.commit()
        finally:
            other.close()
        self.assertIsNone(frappe.db.get_value("CRM Visit Meeting Record", {"visit": visit_id}, "name"))
        return name

    def test_a_first_record_added_during_the_scan_is_written_over_by_the_upload(self):
        visit_id = self._committed_visit()
        name = self._first_record_added_by_the_other_request(visit_id)
        logged = len(getattr(frappe.local, "message_log", ()))
        upload_meeting_file(visit_id, "minutes.txt", "text/plain", COMPLETE_RECORD, scanner=Scanner())
        # The refused insert printed nothing onto this response.
        self.assertEqual(len(getattr(frappe.local, "message_log", ())), logged)
        rows = frappe.db.sql(
            "SELECT `name`, `purpose` FROM `tabCRM Visit Meeting Record` WHERE `visit` = %s FOR UPDATE", (visit_id,),
        )
        self.assertEqual(rows, ((name, "Discuss project"),))
        self.assertEqual(frappe.db.sql("SELECT `status` FROM `tabCRM Visit` WHERE `name` = %s FOR UPDATE", (visit_id,))[0][0], "Minutes Submitted")

    def test_a_first_record_added_meanwhile_refuses_a_typed_record_as_changed(self):
        visit_id = self._committed_visit()
        name = self._first_record_added_by_the_other_request(visit_id)
        with self.assertRaises(CrmApiException) as refused:
            update_meeting_record(visit_id, {"purpose": "Typed in by hand", "attendees": "Customer A"})
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("VERSION_CONFLICT", "Meeting record was changed by another user."))
        rows = frappe.db.sql(
            "SELECT `name`, `purpose` FROM `tabCRM Visit Meeting Record` WHERE `visit` = %s FOR UPDATE", (visit_id,),
        )
        self.assertEqual(rows, ((name, "Typed in meanwhile"),))
