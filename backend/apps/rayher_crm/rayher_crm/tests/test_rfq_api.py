from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string
from pypdf import PdfWriter

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.opportunities import create_strategy_opportunity, get_strategy_opportunity, rollback_opportunity_stage, update_strategy_opportunity
from rayher_crm.services.rfqs import (
    create_rfq,
    download_rfq_file,
    get_rfq,
    list_rfqs,
    preview_rfq_file,
    review_rfq,
    revise_rfq,
    submit_engineer_comment,
)
from rayher_crm.services.sites import create_site
from rayher_crm.services.file_security import TIPRAY_HEADER


class CleanScanner:
    def scan(self, content: bytes) -> bool:
        return True


def pdf_part(name: str = "customer-rfq.pdf") -> dict:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    return {"file_name": name, "mime_type": "application/pdf", "content": output.getvalue()}


class TestRfqApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-rfq-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-rfq-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-rfq-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._user("crm-rfq-other-engineer@example.invalid", "CRM Engineer")
        self.manager = self._user("crm-rfq-manager@example.invalid", "CRM Manager")

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

    def _opportunity(self):
        suffix = random_string(6)
        frappe.set_user(self.sales)
        account = create_account({
            "name": f"RFQ Customer {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East China", "owner": self.sales,
        })
        site = create_site(account["id"], {
            "name": f"RFQ Site {suffix}", "city": "Shanghai", "type": "Fab",
            "process": "Frontend", "status": "\u91cf\u4ea7",
        })
        return create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": f"RFQ Project {suffix}",
            "owner": self.sales, "stage": "需求发现", "forecast": "Pipeline", "amount": "100000.00",
            "probability": 20, "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": "100000.00", "paymentMilestones": [], "strengths": [],
            "redFlags": [], "informationNeeded": [],
        })

    def test_complete_workflow_scope_revision_and_opportunity_gate(self):
        opportunity = self._opportunity()
        frappe.db.set_value("CRM Opportunity", opportunity["id"], {"stage": "设备规格确认", "probability": 75})
        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer, "note": "Customer RFQ"},
            pdf_part(), CleanScanner(),
        )
        self.assertEqual((created["status"], created["latestVersion"]), ("Engineer Review", 1))
        assigned = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "recipient_user": self.engineer,
                     "title": "RFQ requires Engineer review"},
            fields=["category", "route", "source_doctype"],
        )[0]
        self.assertEqual(
            (assigned.category, assigned.route, assigned.source_doctype),
            ("RFQ", f"/rfqs/{created['id']}", "CRM RFQ"),
        )
        with self.assertRaises(CrmApiException) as duplicate:
            create_rfq({"opportunityId": opportunity["id"], "engineerId": self.engineer}, pdf_part("duplicate.pdf"), CleanScanner())
        self.assertEqual(duplicate.exception.code, "CONFLICT")

        sales_rows, _, _, _ = list_rfqs({"page": 1, "pageSize": 20})
        self.assertEqual([row["id"] for row in sales_rows], [created["id"]])
        frappe.set_user(self.other_sales)
        self.assertEqual(list_rfqs({"page": 1, "pageSize": 20})[0], [])
        frappe.set_user(self.engineer)
        self.assertEqual([row["id"] for row in list_rfqs({"page": 1, "pageSize": 20})[0]], [created["id"]])
        self.assertEqual(preview_rfq_file(created["id"])["mime_type"], "application/pdf")
        with self.assertRaises(frappe.PermissionError):
            download_rfq_file(created["id"])
        frappe.set_user(self.other_engineer)
        self.assertEqual(list_rfqs({"page": 1, "pageSize": 20})[0], [])

        frappe.set_user(self.sales)
        frappe.db.set_value("CRM Opportunity", opportunity["id"], {"stage": "设备规格确认", "probability": 75})
        specified = get_strategy_opportunity(opportunity["id"])
        with self.assertRaises(CrmApiException) as required:
            update_strategy_opportunity(opportunity["id"], {"stage": "报价"}, specified["modified"])
        self.assertEqual(required.exception.code, "INVALID_TRANSITION")

        frappe.set_user(self.engineer)
        commented = submit_engineer_comment(created["id"], "Specification is feasible.", created["modified"])
        self.assertEqual(commented["status"], "Manager Approval")
        manager_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "recipient_user": self.manager,
                     "title": "RFQ requires Manager approval"},
            fields=["category", "route"],
        )[0]
        self.assertEqual((manager_notice.category, manager_notice.route), ("RFQ", f"/rfqs/{created['id']}"))
        frappe.set_user(self.manager)
        self.assertEqual(get_rfq(created["id"])["id"], created["id"])
        with self.assertRaises(CrmApiException) as reason_required:
            review_rfq(created["id"], "Returned", "", commented["modified"])
        self.assertEqual(reason_required.exception.code, "VALIDATION_ERROR")
        returned = review_rfq(created["id"], "Returned", "Please use revision two.", commented["modified"])
        returned_notices = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "title": "RFQ Returned"},
            pluck="recipient_user",
        )
        self.assertEqual(set(returned_notices), {self.sales, self.engineer})

        frappe.set_user(self.manager)
        revised = revise_rfq(created["id"], pdf_part("customer-rfq-r2.pdf"), returned["modified"], CleanScanner())
        self.assertEqual((revised["status"], len(revised["versions"])), ("Engineer Review", 2))
        self.assertEqual(revised["currentVersion"]["engineerComment"], "")
        self.assertEqual(revised["versions"][1]["engineerComment"], "Specification is feasible.")

        frappe.set_user(self.engineer)
        recommmented = submit_engineer_comment(created["id"], "Revision two confirmed.", revised["modified"])
        frappe.set_user(self.manager)
        approved = review_rfq(created["id"], "Approved", "", recommmented["modified"])
        self.assertEqual(approved["status"], "Approved")
        approved_notices = frappe.get_all(
            "CRM Notification Event",
            filters={"source_name": created["id"], "title": "RFQ Approved"},
            pluck="recipient_user",
        )
        self.assertEqual(set(approved_notices), {self.sales, self.engineer})
        self.assertEqual(download_rfq_file(created["id"])["file_name"], "customer-rfq-r2.pdf")
        with self.assertRaises(CrmApiException) as decided:
            review_rfq(created["id"], "Approved", "Again", approved["modified"])
        self.assertEqual(decided.exception.code, "INVALID_TRANSITION")

        self.assertEqual(frappe.db.get_value("CRM Opportunity", opportunity["id"], "stage"), "报价")
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as locked:
            revise_rfq(created["id"], pdf_part("late.pdf"), approved["modified"], CleanScanner())
        self.assertEqual(locked.exception.code, "INVALID_TRANSITION")
        latest = get_strategy_opportunity(opportunity["id"])
        with self.assertRaises(CrmApiException) as manual:
            update_strategy_opportunity(opportunity["id"], {"stage": "采购流程"}, latest["modified"])
        self.assertEqual(manual.exception.code, "INVALID_TRANSITION")

        frappe.set_user(self.manager)
        rollback_reason = "Customer changed the equipment specification."
        rolled_back = rollback_opportunity_stage(
            opportunity["id"], "设备规格确认", rollback_reason, latest["modified"],
        )
        self.assertEqual(rolled_back["stage"], "设备规格确认")
        reopened = get_rfq(created["id"])
        self.assertEqual(reopened["status"], "Sales Revision")
        self.assertEqual(reopened["currentVersion"]["status"], "Returned")
        self.assertEqual(reopened["currentVersion"]["managerComment"], rollback_reason)

        revised_after_rollback = revise_rfq(
            created["id"], pdf_part("rollback-revision.pdf"), reopened["modified"], CleanScanner(),
        )
        self.assertEqual(revised_after_rollback["status"], "Engineer Review")
        self.assertEqual(revised_after_rollback["currentVersion"]["uploadedBy"], self.manager)

    def test_manager_can_upload_an_initial_rfq_for_the_opportunity_owner(self):
        opportunity = self._opportunity()
        frappe.db.set_value("CRM Opportunity", opportunity["id"], {"stage": "设备规格确认", "probability": 75})
        frappe.set_user(self.manager)

        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer, "note": "Manager upload"},
            pdf_part("manager-upload.pdf"),
            CleanScanner(),
        )

        self.assertEqual(created["salesOwner"], self.sales)
        self.assertEqual(created["currentVersion"]["uploadedBy"], self.manager)

    def test_failed_preview_generation_rolls_back_create(self):
        opportunity = self._opportunity()
        before = frappe.db.count("CRM RFQ")
        with patch("rayher_crm.services.rfqs._preview", side_effect=CrmApiException("VALIDATION_ERROR", "conversion failed")):
            with self.assertRaises(CrmApiException):
                create_rfq(
                    {"opportunityId": opportunity["id"], "engineerId": self.engineer},
                    pdf_part(), CleanScanner(),
                )
        self.assertEqual(frappe.db.count("CRM RFQ"), before)

    def test_tipray_file_can_be_created_and_downloaded_without_preview(self):
        opportunity = self._opportunity()
        frappe.db.set_value("CRM Opportunity", opportunity["id"], {"stage": "设备规格确认", "probability": 75})
        before = frappe.db.count("CRM RFQ")
        content = TIPRAY_HEADER + bytes(range(256))

        created = create_rfq(
            {"opportunityId": opportunity["id"], "engineerId": self.engineer},
            {
                "file_name": "protected-rfq.pdf",
                "mime_type": "application/pdf",
                "content": content,
            },
            CleanScanner(),
        )

        self.assertEqual(frappe.db.count("CRM RFQ"), before + 1)
        version = frappe.get_doc("CRM RFQ Version", created["currentVersionId"])
        stored = frappe.get_doc("File", version.original_file)
        self.assertTrue(stored.file_name.startswith("tipray-"))
        self.assertTrue(stored.file_name.endswith(".bin"))
        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as protected:
            preview_rfq_file(created["id"])
        self.assertEqual(protected.exception.code, "VALIDATION_ERROR")
        self.assertIn("cannot be previewed online", str(protected.exception))
        frappe.set_user(self.sales)
        downloaded = download_rfq_file(created["id"])
        self.assertEqual(downloaded["file_name"], "protected-rfq.pdf")
        self.assertEqual(downloaded["mime_type"], "application/pdf")
        self.assertEqual(downloaded["content"], content)
