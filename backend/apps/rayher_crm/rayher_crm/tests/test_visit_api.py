from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.sites import create_site
from rayher_crm.services.visit_meetings import update_record as update_meeting_record
from rayher_crm.services.visits import create_visit, delete_visit, get_visit, list_visits, update_visit

class TestVisitApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.manager = self._user("crm-visit-manager@example.invalid", "CRM Manager")
        self.sales = self._user("crm-visit-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-visit-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-visit-engineer@example.invalid", "CRM Engineer")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _records(self, owner: str, suffix: str):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Visit {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East", "owner": owner,
        })
        contact = create_contact({
            "accountId": account["id"], "name": f"{suffix} Contact", "title": "Director",
            "department": "Engineering", "phone": "13800000002",
            "email": f"visit-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": owner, "status": "Active",
        })
        return account, contact

    def _meeting_record(self, visit_id: str):
        return frappe.get_doc({
            "doctype": "CRM Visit Meeting Record", "visit": visit_id,
            "purpose": "Discuss project", "attendees": "Customer A\nSales A",
            "agenda": "Introduce solution", "summary": "Requirements confirmed",
            "conclusion": "Proceed", "followup": "Send proposal",
            "parse_status": "Parsed", "parse_message": "Test record", "manually_corrected": 1,
        }).insert(ignore_permissions=True)

    def _input(self, account: dict, contact: dict | None, owner: str, **overrides):
        payload = {
            "accountId": account["id"], "primaryContactId": contact["id"] if contact else "",
            "subject": "Fab review", "date": "2026-08-20", "type": "On-site",
            "owner": owner, "objective": "Confirm evaluation criteria",
        }
        payload.update(overrides)
        return payload

    def test_create_list_filters_scope_and_cas(self):
        account, contact = self._records(self.sales, "Core")
        foreign_account, foreign_contact = self._records(self.other_sales, "Foreign")
        foreign_visit = create_visit(self._input(foreign_account, foreign_contact, self.other_sales))
        frappe.set_user(self.sales)

        with self.assertRaises(CrmApiException) as forged:
            create_visit(self._input(account, contact, self.other_sales))
        self.assertEqual(forged.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as mismatch:
            create_visit(self._input(account, foreign_contact, self.sales))
        self.assertEqual(mismatch.exception.code, "CONFLICT")

        site = create_site(account["id"], {
            "name": "Core Fab", "city": "Shanghai", "type": "Fab",
            "process": "CIS", "status": "量产",
        })
        opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": "CIS defect inspection",
            "owner": self.sales, "stage": "需求发现", "forecast": "Pipeline", "amount": "4860000",
            "probability": 20, "intentScore": 35, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East", "currency": "CNY",
            "originalAmount": "4860000", "paymentMilestones": [], "strengths": [],
            "redFlags": [], "informationNeeded": [],
        })
        created = create_visit(self._input(account, contact, self.sales, opportunityId=opportunity["id"]))
        self.assertRegex(created["id"], r"^CRM-VIS-\d{5}$")
        self.assertEqual(created["accountName"], account["name"])
        self.assertEqual(created["owner"], self.sales)
        self.assertEqual(created["status"], "Planned")
        self.assertEqual(created["opportunityId"], opportunity["id"])
        self.assertEqual(frappe.db.get_value("CRM Visit", created["id"], "opportunity"), opportunity["id"])
        self.assertRegex(created["modified"], r"Z$")
        self.assertEqual(frappe.db.get_value("CRM Visit", created["id"], "created_by_user"), self.sales)
        self.assertEqual(get_visit(created["id"])["id"], created["id"])
        with self.assertRaises(CrmApiException) as outside_scope:
            get_visit(foreign_visit["id"])
        self.assertEqual(outside_scope.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as missing:
            get_visit("CRM-VIS-NOT-FOUND")
        self.assertEqual(missing.exception.code, "NOT_FOUND")

        items, total, page, page_size = list_visits({
            "search": "Fab", "accountId": account["id"], "contactId": contact["id"],
            "status": "Planned", "owner": self.sales, "dateFrom": "2026-08-01",
            "dateTo": "2026-08-31", "page": "1", "pageSize": "10",
        })
        self.assertEqual([item["id"] for item in items], [created["id"]])
        self.assertEqual((total, page, page_size), (1, 1, 10))

        with self.assertRaises(CrmApiException) as stale:
            update_visit(created["id"], {"type": "edit", "subject": "Stale"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        updated = update_visit(created["id"], {"type": "edit", "subject": "Updated fab review"}, created["modified"])
        self.assertEqual(updated["subject"], "Updated fab review")

        frappe.set_user(self.other_sales)
        self.assertNotIn(created["id"], {item["id"] for item in list_visits({})[0]})
        self.assertTrue(foreign_account["id"])

    def test_state_machine_requires_complete_meeting_record_and_locks_after_review(self):
        account, contact = self._records(self.sales, "Flow")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))

        with self.assertRaises(CrmApiException) as no_outcome:
            update_visit(visit["id"], {"type": "advance", "status": "Visited"}, visit["modified"])
        self.assertEqual(no_outcome.exception.code, "INVALID_TRANSITION")
        visited = update_visit(visit["id"], {
            "type": "advance", "status": "Visited", "outcome": "Criteria confirmed",
        }, visit["modified"])
        with self.assertRaises(CrmApiException) as no_minutes:
            update_visit(visit["id"], {"type": "advance", "status": "Minutes Submitted"}, visited["modified"])
        self.assertEqual(no_minutes.exception.code, "INVALID_TRANSITION")
        self._meeting_record(visit["id"])
        minutes = update_visit(visit["id"], {"type": "advance", "status": "Minutes Submitted"}, visited["modified"])
        assigned = update_visit(visit["id"], {
            "type": "edit", "nextAction": "Prepare plan", "actionOwner": self.sales, "due": "2026-08-25",
        }, minutes["modified"])
        notification = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Visit", "source_name": visit["id"], "title": "Visit action assigned"},
            fields=["recipient_user", "route"],
        )
        self.assertEqual(len(notification), 1)
        self.assertEqual(notification[0].recipient_user, self.sales)
        self.assertEqual(notification[0].route, f"/visits?focus={visit['id']}")

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            update_visit(visit["id"], {"type": "advance", "status": "Manager Reviewed"}, assigned["modified"])
        frappe.set_user(self.manager)
        reviewed = update_visit(visit["id"], {"type": "advance", "status": "Manager Reviewed"}, assigned["modified"])
        with self.assertRaises(CrmApiException) as locked:
            update_visit(visit["id"], {"type": "edit", "subject": "Too late"}, reviewed["modified"])
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")

    def test_existing_meeting_record_requires_current_modified_token(self):
        account, contact = self._records(self.sales, "MeetingCAS")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        payload = {
            "meetingStart": "2026-08-20T10:00", "meetingEnd": "2026-08-20T11:00",
            "purpose": "Review", "attendees": "Customer A", "agenda": "Agenda",
            "summary": "Summary", "conclusion": "Proceed", "followup": "Send plan",
        }

        created = update_meeting_record(visit["id"], payload)
        self.assertTrue(created["modified"])
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Planned")
        visited = update_visit(visit["id"], {
            "type": "advance", "status": "Visited", "outcome": "Review completed",
        }, visit["modified"])
        submitted = update_meeting_record(
            visit["id"], {**payload, "summary": "Submitted"}, created["modified"],
        )
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Minutes Submitted")
        self.assertEqual(visited["status"], "Visited")

        with self.assertRaises(CrmApiException) as missing:
            update_meeting_record(visit["id"], {**payload, "summary": "Missing token"})
        self.assertEqual(missing.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as stale:
            update_meeting_record(visit["id"], {**payload, "summary": "Stale"}, "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        updated = update_meeting_record(visit["id"], {**payload, "summary": "Current"}, submitted["modified"])
        self.assertEqual(updated["summary"], "Current")

    def test_notification_is_in_same_savepoint_as_visit_update(self):
        account, contact = self._records(self.sales, "Atomic")
        frappe.set_user(self.sales)
        visit = create_visit(self._input(account, contact, self.sales))
        visited = update_visit(visit["id"], {
            "type": "advance", "status": "Visited", "outcome": "Done",
        }, visit["modified"])
        self._meeting_record(visit["id"])
        minutes = update_visit(visit["id"], {"type": "advance", "status": "Minutes Submitted"}, visited["modified"])
        before = frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Visit", "source_name": visit["id"]})

        def fail_after_notification(stage: str) -> None:
            if stage == "after_notification_insert":
                raise RuntimeError("injected visit notification failure")

        frappe.set_user(self.manager)
        with self.assertRaisesRegex(RuntimeError, "injected visit notification failure"):
            update_visit(visit["id"], {"type": "advance", "status": "Manager Reviewed"}, minutes["modified"], failure_injector=fail_after_notification)
        self.assertEqual(frappe.db.get_value("CRM Visit", visit["id"], "status"), "Minutes Submitted")
        self.assertEqual(
            frappe.db.count("CRM Notification Event", {"source_doctype": "CRM Visit", "source_name": visit["id"]}),
            before,
        )

    def test_only_manager_can_delete_visit(self):
        account, contact = self._records(self.other_sales, "Delete")
        visit = create_visit(self._input(account, contact, self.other_sales))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            delete_visit(visit["id"])
        self.assertTrue(frappe.db.exists("CRM Visit", visit["id"]))

        frappe.set_user(self.manager)
        self.assertEqual(delete_visit(visit["id"]), {"id": visit["id"], "status": "Deleted"})
        self.assertFalse(frappe.db.exists("CRM Visit", visit["id"]))
