from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import (
    create_opportunity_action,
    create_opportunity_stakeholder,
    create_strategy_opportunity,
    delete_opportunity_action,
    delete_opportunity_stakeholder,
    update_opportunity_action,
    update_opportunity_stakeholder,
)
from rayher_crm.services.opportunity_stages import QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site


class TestOpportunityRelations(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-relations-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-relations-other@example.invalid", "CRM Sales")
        self.manager = self._user("crm-relations-manager@example.invalid", "CRM Manager")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
            user.enabled = 1
            if role not in {row.role for row in user.roles}:
                user.append("roles", {"role": role})
                user.save(ignore_permissions=True)
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _records(self, owner: str, suffix: str):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Relations {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": owner,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "上海", "type": "Fab",
            "process": "Frontend", "status": "量产",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Opportunity",
            "owner": owner, "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": 100000,
            "probability": 20, "intentScore": 20, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY",
            "originalAmount": 100000, "amountCny": 100000, "qualificationConfirmed": True,
        })
        contact = create_contact({
            "accountId": account["id"], "name": f"{suffix} Contact", "title": "Director",
            "department": "Engineering", "phone": "13800000002",
            "email": f"{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": owner, "status": "Active",
        })
        return account, opportunity, contact

    def _stakeholder_input(self, contact_id: str, **overrides):
        payload = {
            "contactId": contact_id, "role": "Decision Maker", "influence": "High",
            "stance": "Support", "coverage": "Monthly", "isCoach": True,
            "winResult": "Budget approved", "opportunityNotes": "Confirm FAT attendees",
        }
        payload.update(overrides)
        return payload

    def _action_input(self, **overrides):
        payload = {
            "title": "Confirm technical scope", "owner": self.sales,
            "due": "2026-09-01", "status": "Open",
        }
        payload.update(overrides)
        return payload

    def test_stakeholder_lifecycle_uses_server_id_soft_archive_and_history(self):
        _, opportunity, contact = self._records(self.sales, "Stakeholder")
        created = create_opportunity_stakeholder(
            opportunity["id"], self._stakeholder_input(contact["id"])
        )
        self.assertNotEqual(created["id"], "client-id")
        self.assertEqual((created["name"], created["title"]), ("Stakeholder Contact", "Director"))
        self.assertEqual(create_strategy_opportunity.__module__, "rayher_crm.services.opportunities")

        updated = update_opportunity_stakeholder(
            opportunity["id"], created["id"], self._stakeholder_input(contact["id"], stance="Neutral")
        )
        self.assertEqual(updated["stance"], "Neutral")
        self.assertEqual(delete_opportunity_stakeholder(opportunity["id"], created["id"]), {"id": created["id"]})
        self.assertEqual(frappe.db.get_value("CRM Opportunity Stakeholder", created["id"], "archived"), 1)

        from rayher_crm.services.opportunities import serialize_opportunity

        serialized = serialize_opportunity(frappe.get_doc("CRM Opportunity", opportunity["id"]))
        self.assertEqual(serialized["stakeholders"], [])
        deleted = [row for row in serialized["history"] if row["field"] == "stakeholderDeleted"]
        self.assertEqual([(row["actor"], row["to"]) for row in deleted], [(self.sales, created["id"])])
        with self.assertRaises(CrmApiException) as archived:
            update_opportunity_stakeholder(
                opportunity["id"], created["id"], self._stakeholder_input(contact["id"])
            )
        self.assertEqual(archived.exception.code, "NOT_FOUND")

    def test_stakeholder_rejects_duplicates_foreign_inactive_and_out_of_scope(self):
        _, opportunity, contact = self._records(self.sales, "StakeholderValidation")
        _, foreign_opportunity, foreign_contact = self._records(self.other_sales, "ForeignStakeholder")
        frappe.set_user(self.sales)
        create_opportunity_stakeholder(opportunity["id"], self._stakeholder_input(contact["id"]))

        with self.assertRaises(CrmApiException) as duplicate:
            create_opportunity_stakeholder(opportunity["id"], self._stakeholder_input(contact["id"]))
        self.assertEqual(duplicate.exception.code, "CONFLICT")
        with self.assertRaises(CrmApiException) as mismatch:
            create_opportunity_stakeholder(opportunity["id"], self._stakeholder_input(foreign_contact["id"]))
        self.assertEqual(mismatch.exception.code, "CONFLICT")

        frappe.set_user("Administrator")
        frappe.db.set_value("Contact", contact["id"], "custom_crm_status", "Left Company")
        frappe.set_user(self.sales)
        delete_opportunity_stakeholder(
            opportunity["id"],
            frappe.db.get_value("CRM Opportunity Stakeholder", {"opportunity": opportunity["id"]}, "name"),
        )
        with self.assertRaises(CrmApiException) as inactive:
            create_opportunity_stakeholder(opportunity["id"], self._stakeholder_input(contact["id"]))
        self.assertEqual(inactive.exception.code, "VALIDATION_ERROR")

        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException) as denied:
            create_opportunity_stakeholder(opportunity["id"], self._stakeholder_input(foreign_contact["id"]))
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        self.assertTrue(foreign_opportunity["id"])

    def test_action_validation_owner_lock_update_soft_archive_and_history(self):
        _, opportunity, _ = self._records(self.sales, "Action")
        with self.assertRaises(CrmApiException) as client_id:
            create_opportunity_action(opportunity["id"], self._action_input(id="client-id"))
        self.assertEqual(client_id.exception.code, "VALIDATION_ERROR")
        for overrides in ({"title": ""}, {"due": "2026-02-30"}, {"status": "Pending"}):
            with self.subTest(overrides=overrides), self.assertRaises(CrmApiException) as invalid:
                create_opportunity_action(opportunity["id"], self._action_input(**overrides))
            self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as forged:
            create_opportunity_action(opportunity["id"], self._action_input(owner=self.other_sales))
        self.assertEqual(forged.exception.code, "SCOPE_DENIED")

        created = create_opportunity_action(opportunity["id"], self._action_input())
        updated = update_opportunity_action(
            opportunity["id"], created["id"], self._action_input(status="Done")
        )
        self.assertEqual(updated["status"], "Done")
        self.assertEqual(delete_opportunity_action(opportunity["id"], created["id"]), {"id": created["id"]})
        self.assertEqual(frappe.db.get_value("CRM Opportunity Action", created["id"], "archived"), 1)

        from rayher_crm.services.opportunities import serialize_opportunity

        serialized = serialize_opportunity(frappe.get_doc("CRM Opportunity", opportunity["id"]))
        self.assertEqual(serialized["actions"], [])
        deleted = [row for row in serialized["history"] if row["field"] == "actionDeleted"]
        self.assertEqual([(row["actor"], row["to"]) for row in deleted], [(self.sales, created["id"])])
        with self.assertRaises(CrmApiException) as archived:
            update_opportunity_action(opportunity["id"], created["id"], self._action_input())
        self.assertEqual(archived.exception.code, "NOT_FOUND")

    def test_action_notification_requires_reachable_owner_and_preserves_snapshots(self):
        _, opportunity, _ = self._records(self.sales, "ActionNotification")
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as inaccessible:
            create_opportunity_action(
                opportunity["id"], self._action_input(owner=self.other_sales),
            )
        self.assertEqual(
            inaccessible.exception.code, "VALIDATION_ERROR",
        )
        self.assertIn("access to this Opportunity", inaccessible.exception.public_message)

        created = create_opportunity_action(
            opportunity["id"], self._action_input(owner=self.sales),
        )
        notification = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Opportunity Action", "source_name": created["id"]},
            fields=["recipient_user", "category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (notification.recipient_user, notification.category, notification.route),
            (self.sales, "Action", f"/opportunities/{opportunity['id']}"),
        )
        frappe.set_user(self.sales)
        from rayher_crm.services.opportunities import get_strategy_opportunity, serialize_opportunity

        self.assertEqual(get_strategy_opportunity(opportunity["id"])["id"], opportunity["id"])
        frappe.set_user(self.manager)
        updated = update_opportunity_action(
            opportunity["id"], created["id"],
            self._action_input(owner=self.sales, status="Done", due="2026-09-02"),
        )
        serialized = serialize_opportunity(frappe.get_doc("CRM Opportunity", opportunity["id"]))
        history = [row for row in serialized["history"] if row["field"] == "actionUpdated"][-1]
        self.assertEqual(json.loads(history["from"]), created)
        self.assertEqual(json.loads(history["to"]), updated)

    def test_action_remark_round_trips_updates_and_clears(self):
        from rayher_crm.services.opportunities import get_strategy_opportunity

        _, opportunity, _ = self._records(self.sales, "ActionRemark")
        remark = "Line one" + chr(10) + "第二行"
        created = create_opportunity_action(opportunity["id"], self._action_input(remark=remark))
        self.assertEqual(created["remark"], remark)
        # An update that omits the remark must not silently drop it.
        updated = update_opportunity_action(opportunity["id"], created["id"], self._action_input(status="Done"))
        self.assertEqual(updated["remark"], created["remark"])
        self.assertEqual(get_strategy_opportunity(opportunity["id"])["actions"][0]["remark"], created["remark"])
        cleared = update_opportunity_action(opportunity["id"], created["id"], self._action_input(remark=""))
        self.assertEqual(cleared["remark"], "")
        with self.assertRaises(CrmApiException):
            create_opportunity_action(opportunity["id"], self._action_input(remark="x" * 10001))
