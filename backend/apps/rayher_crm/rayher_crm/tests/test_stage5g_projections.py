from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.bookings import create_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.opportunities import create_opportunity_action, create_strategy_opportunity
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture
from rayher_crm.services.pipeline import PIPELINE_READ_LIMIT, _read_all_pages, list_pipeline
from rayher_crm.services.sites import create_site
from rayher_crm.services.visits import create_visit, update_visit


class TestStage5GProjections(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-projection-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-projection-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-projection-engineer@example.invalid", "CRM Engineer")

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

    def test_pipeline_reader_fetches_beyond_first_bounded_page(self):
        source = [{"id": index} for index in range(PIPELINE_READ_LIMIT + 5)]
        queries = []

        def read_page(query):
            queries.append(query)
            start = (query["page"] - 1) * query["pageSize"]
            return source[start:start + query["pageSize"]], len(source), query["page"], query["pageSize"]

        self.assertEqual(_read_all_pages(read_page), source)
        self.assertEqual(queries, [
            {"page": 1, "pageSize": PIPELINE_READ_LIMIT},
            {"page": 2, "pageSize": PIPELINE_READ_LIMIT},
        ])

    def _base(self, owner: str, suffix: str):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Projection {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "Shanghai", "region": "East", "owner": owner,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "Shanghai", "type": "Fab",
            "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"projection-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": owner, "status": "Active",
        })
        return account, site, contact

    def _opportunity(self, account: dict, site: dict, owner: str, title: str, stage: str, amount: int, probability: int):
        opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": title,
            "owner": owner, "stage": "需求发现", "forecast": "Pipeline",
            "amount": amount, "probability": probability, "intentScore": 70,
            "poDate": "2026-12-31", "toolType": "Inspection", "saleType": "New Equipment",
            "subRegion": "East", "currency": "CNY", "originalAmount": amount,
        })
        changes = {"forecast": "Closed"} if stage == "Won" else None
        return advance_opportunity_fixture(opportunity, stage, changes)

    def _demo_and_evaluation(self, account: dict, contact: dict, opportunity: dict):
        request = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": account["id"], "primary_contact": contact["id"],
            "opportunity": opportunity["id"], "sales_owner": self.sales, "created_by_user": self.sales,
            "title": "Projection Demo", "objective": "Validate", "requested_equipment": "Inspection",
            "sample_type": "Wafer", "sample_quantity": 1, "target_date": "2026-09-01",
            "customer_expected_date": "2026-09-05", "priority": "High", "acceptance_criteria": "Pass",
            "status": "Draft", "engineer_owner": self.engineer, "form_data": {},
        }).insert(ignore_permissions=True)
        evaluation = frappe.get_doc({
            "doctype": "CRM Evaluation", "account": account["id"], "demo_request": request.name,
            "title": "Projection Evaluation", "status": "Requested", "evaluation_owner": self.engineer,
            "planned_end": "2026-09-10", "acceptance": "Pending", "report_status": "Not Ready",
        }).insert(ignore_permissions=True)
        return request, evaluation

    def test_pipeline_projects_canonical_rows_totals_and_scope(self):
        account, site, contact = self._base(self.sales, "Core")
        open_opportunity = self._opportunity(account, site, self.sales, "Open Projection", "Wafer Demo确认", 1000, 25)
        won = self._opportunity(account, site, self.sales, "Won Projection", "Won", 500, 100)
        action = create_opportunity_action(open_opportunity["id"], {
            "title": "Call customer", "owner": self.sales, "due": "2026-08-30", "status": "Open",
        })
        booking = create_booking({
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Inspection",
            "quantity": 1, "ddl": "2026-12-31", "amount": "500.00", "currency": "CNY", "status": "Confirmed",
            "owner": self.sales, "source": "Opportunity", "sourceOpportunityId": won["id"], "note": "",
        })
        foreign_account, foreign_site, _ = self._base(self.other_sales, "Foreign")
        self._opportunity(foreign_account, foreign_site, self.other_sales, "Hidden Projection", "Wafer Demo确认", 9999, 50)

        frappe.set_user(self.sales)
        result = list_pipeline({"accountId": account["id"]})
        self.assertEqual({item["id"] for item in result["opportunities"]}, {open_opportunity["id"], won["id"]})
        projected = next(item for item in result["opportunities"] if item["id"] == open_opportunity["id"])
        self.assertEqual(projected["accountName"], account["name"])
        self.assertEqual(projected["intentScore"], 70)
        self.assertEqual(projected["budgetStatus"], "Unknown")
        self.assertEqual((projected["nextAction"], projected["due"]), (action["title"], "2026-08-30"))
        self.assertEqual([item["id"] for item in result["bookings"]], [booking["id"]])
        self.assertEqual(result["totals"], [{"currency": "CNY", "openPipeline": "1000.00", "weightedPipeline": "610.00", "confirmedBooking": "500.00"}])
        self.assertNotIn("Hidden Projection", {item["title"] for item in list_pipeline({})["opportunities"]})

    def test_account_360_expands_scoped_canonical_rows_without_get_writes(self):
        account, site, contact = self._base(self.sales, "Detail")
        opportunity = self._opportunity(account, site, self.sales, "Detail Projection", "Won", 500, 100)
        action = create_opportunity_action(opportunity["id"], {
            "title": "Prepare delivery", "owner": self.sales, "due": "2026-08-31", "status": "Open",
        })
        booking = create_booking({
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Inspection",
            "quantity": 1, "ddl": "2026-12-31", "amount": "500.00", "currency": "CNY", "status": "Confirmed",
            "owner": self.sales, "source": "Opportunity", "sourceOpportunityId": opportunity["id"], "note": "",
        })
        visit = create_visit({
            "accountId": account["id"], "primaryContactId": contact["id"], "subject": "Detail Visit",
            "date": "2026-08-22", "type": "Video", "owner": self.sales, "objective": "Review",
        })
        visit = update_visit(visit["id"], {
            "type": "advance", "status": "Visited", "outcome": "Review completed",
        }, visit["modified"])
        request, evaluation = self._demo_and_evaluation(account, contact, opportunity)
        before = {
            "account": frappe.db.get_value("Customer", account["id"], "modified"),
            "opportunity": frappe.db.get_value("CRM Opportunity", opportunity["id"], "modified"),
            "visit": frappe.db.get_value("CRM Visit", visit["id"], "modified"),
        }

        detail = get_account_360(account["id"])
        self.assertIn(booking["id"], {item["id"] for item in detail["bookings"]})
        self.assertIn(request.name, {item["id"] for item in detail["demoRequests"]})
        self.assertIn(evaluation.name, {item["id"] for item in detail["evaluations"]})
        self.assertIn(visit["id"], {item["id"] for item in detail["visits"]})
        self.assertIn(action["id"], {item["id"] for item in detail["actions"]})
        self.assertEqual(detail["requirements"], [])
        self.assertEqual(detail["contracts"], [])
        self.assertEqual(detail["summary"]["activeDemos"], 1)
        self.assertEqual(detail["summary"]["lastVisit"], "2026-08-22")
        after = {
            "account": frappe.db.get_value("Customer", account["id"], "modified"),
            "opportunity": frappe.db.get_value("CRM Opportunity", opportunity["id"], "modified"),
            "visit": frappe.db.get_value("CRM Visit", visit["id"], "modified"),
        }
        self.assertEqual(after, before)
