from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import create_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.dashboard import get_dashboard
from rayher_crm.services.opportunities import create_opportunity_action, create_strategy_opportunity
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture
from rayher_crm.services.sites import create_site
from rayher_crm.services.stakeholders import create_stakeholder, list_stakeholders, update_stakeholder
from rayher_crm.services.visits import create_visit


class TestStage5GDashboardStakeholders(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-dashboard-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-dashboard-other@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-dashboard-engineer@example.invalid", "CRM Engineer")

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

    def _base(self, owner: str, suffix: str, segment: str = "Frontend"):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Dashboard {suffix}", "shortName": suffix, "segment": segment,
            "tier": "A", "city": "Shanghai", "region": "East", "owner": owner,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "Shanghai", "type": "Fab",
            "process": segment, "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"dashboard-{suffix.lower()}@example.invalid", "relationship": "Developing",
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

    def test_dashboard_shape_aggregations_scope_and_query_validation(self):
        account, site, contact = self._base(self.sales, "Core")
        opened = self._opportunity(account, site, self.sales, "Dashboard Open", "Wafer Demo确认", 1000, 25)
        won = self._opportunity(account, site, self.sales, "Dashboard Won", "Won", 500, 100)
        create_opportunity_action(opened["id"], {
            "title": "Overdue action", "owner": self.sales, "due": "2026-08-01", "status": "Open",
        })
        booking_date = "2026-08-20"
        booking = create_booking({
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Inspection",
            "quantity": 1, "ddl": "2026-12-31", "amount": "500.00", "currency": "CNY", "status": "Confirmed",
            "owner": self.sales, "source": "Opportunity", "sourceOpportunityId": won["id"], "note": "",
        })
        frappe.db.set_value("CRM Booking", booking["id"], "booking_date", booking_date)
        create_visit({
            "accountId": account["id"], "primaryContactId": contact["id"], "subject": "Dashboard Visit",
            "date": "2026-08-20", "type": "Video", "owner": self.sales, "objective": "Review",
        })
        foreign_account, foreign_site, _ = self._base(self.other_sales, "Foreign")
        self._opportunity(foreign_account, foreign_site, self.other_sales, "Hidden Open", "Wafer Demo确认", 9000, 50)

        frappe.set_user(self.sales)
        result = get_dashboard({"range": "month", "segment": "Frontend"})
        self.assertRegex(result["asOf"], r"Z$")
        self.assertEqual(result["kpis"]["moneyByCurrency"], [{
            "currency": "CNY", "openPipeline": "1000.00", "weightedPipeline": "610.00",
            "confirmedBooking": "500.00", "cumulativeWon": "500.00",
        }])
        self.assertEqual(result["kpis"]["overdueActions"], 1)
        self.assertEqual(result["process"]["requirementsByStatus"], [])
        self.assertEqual(result["process"]["budgetByStatus"], [])
        self.assertEqual(result["process"]["visitsByStatus"], [{"label": "Planned", "count": 1}])
        self.assertEqual(result["bookingByMonth"][0]["label"], booking_date[:7])
        self.assertNotIn("Hidden Open", {item["title"] for item in result["weeklyActions"]})
        with self.assertRaises(CrmApiException):
            get_dashboard({"range": "decade"})

    def test_engineer_dashboard_does_not_require_visit_access(self):
        frappe.set_user(self.engineer)

        result = get_dashboard({"range": "month", "segment": "Frontend"})

        self.assertEqual(result["process"]["visitsByStatus"], [])
        self.assertEqual(result["process"]["visitsByOwner"], [])

    def test_legacy_stakeholders_reuse_standard_contact_and_preserve_fields(self):
        account, _site, _contact = self._base(self.sales, "Stakeholder")
        frappe.set_user(self.sales)
        created = create_stakeholder({
            "accountId": account["id"], "name": "Decision Person", "title": "VP",
            "department": "Operations", "role": "Decision Maker", "influence": "High",
            "relationship": "Strong", "email": "decision@example.invalid",
        })
        self.assertTrue(frappe.db.exists("Contact", created["id"]))
        self.assertFalse(frappe.db.exists("DocType", "CRM Stakeholder"))
        self.assertEqual((created["role"], created["influence"]), ("Decision Maker", "High"))
        items, total, page, page_size = list_stakeholders({"accountId": account["id"], "search": "Decision"})
        self.assertIn(created["id"], {item["id"] for item in items})
        self.assertEqual((total, page, page_size), (1, 1, 20))
        updated = update_stakeholder(created["id"], {
            "accountId": account["id"], "name": "Decision Person", "title": "VP",
            "department": "Operations", "role": "Economic Buyer", "influence": "Medium",
            "relationship": "Strong", "email": "decision@example.invalid",
        }, created["modified"])
        self.assertEqual((updated["role"], updated["influence"]), ("Economic Buyer", "Medium"))
