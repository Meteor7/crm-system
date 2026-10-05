from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.api.v1.leads import create_lead as create_lead_endpoint
from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.contacts import create_contact, get_contact
from rayher_crm.services.leads import convert_lead, create_lead, delete_lead, get_lead, list_leads, update_lead
from rayher_crm.services.opportunities import get_strategy_opportunity
from rayher_crm.services.opportunity_stages import QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site


class TestLeadApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-lead-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-lead-other@example.invalid", "CRM Sales")
        self.manager = self._user("crm-lead-manager@example.invalid", "CRM Manager")

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
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@", 1)[0],
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True).name

    def _input(self, name: str, owner: str | None = None, **overrides) -> dict:
        payload = {
            "name": name,
            "company": f"{name} Semiconductor",
            "title": "Process Manager",
            "phone": "13800000004",
            "email": f"{name.replace(' ', '.').lower()}@example.invalid",
            "source": "Trade Show",
            "status": "New",
            "owner": owner or frappe.session.user,
            "interest": "Advanced packaging inspection",
            "firstContactNote": "Met at exhibition",
            "nextAction": "Arrange discovery call",
            "nextActionDue": "2026-08-20",
            "activities": [],
        }
        payload.update(overrides)
        return payload

    def test_lead_create_list_update_and_endpoint_envelope(self):
        frappe.set_user(self.sales)
        created = create_lead(self._input("Lead Vertical Slice"))
        self.assertTrue(created["id"])
        self.assertEqual(created["owner"], self.sales)
        self.assertEqual(created["status"], "New")
        self.assertRegex(created["modified"], r"Z$")

        items, total, page, page_size = list_leads(
            {
                "search": "Vertical Slice",
                "status": "New",
                "source": "Trade Show",
                "owner": "All",
                "page": 1,
                "pageSize": 100000,
            }
        )
        self.assertIn(created["id"], {item["id"] for item in items})
        self.assertGreaterEqual(total, 1)
        self.assertEqual((page, page_size), (1, 200))

        with self.assertRaises(CrmApiException) as stale:
            update_lead(created["id"], self._input("Stale Lead"), "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        updated = update_lead(
            created["id"],
            self._input("Lead Vertical Slice", status="Working", firstContactNote="Discovery completed"),
            created["modified"],
        )
        self.assertEqual(updated["status"], "Working")
        self.assertEqual(updated["firstContactNote"], "Discovery completed")
        self.assertNotEqual(updated["modified"], created["modified"])

        endpoint = create_lead_endpoint(self._input("Endpoint Lead"))
        self.assertEqual(endpoint["data"]["name"], "Endpoint Lead")
        self.assertRegex(endpoint["meta"]["requestId"], r"^req_[0-9a-f]{24}$")

    def test_manager_assignment_notifies_owner_who_can_open_lead(self):
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Assigned Lead", self.other_sales))
        notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "Lead", "source_name": lead["id"],
                     "recipient_user": self.other_sales},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual((notice.category, notice.route), ("Lead", f"/leads/{lead['id']}"))
        frappe.set_user(self.other_sales)
        self.assertEqual(get_lead(lead["id"])["id"], lead["id"])

    def test_lead_validation_owner_forgery_and_scope(self):
        frappe.set_user(self.other_sales)
        foreign = create_lead(self._input("Foreign Lead"))

        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as forged:
            create_lead(self._input("Forged Lead", self.other_sales))
        self.assertEqual(forged.exception.code, "SCOPE_DENIED")

        with self.assertRaises(CrmApiException) as denied:
            get_lead(foreign["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

        with self.assertRaises(CrmApiException) as missing_channel:
            create_lead(self._input("No Channel", phone="", email=""))
        self.assertEqual(missing_channel.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as bad_date:
            create_lead(self._input("Bad Date", nextActionDue="2026-02-31"))
        self.assertEqual(bad_date.exception.code, "VALIDATION_ERROR")

        invalid_email = create_lead_endpoint(self._input("Bad Email", email="123123123123@qq"))
        self.assertEqual(frappe.local.response["http_status_code"], 422)
        self.assertEqual(invalid_email["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(invalid_email["error"]["fieldErrors"], {"email": "Invalid email"})

    def test_get_and_list_are_read_only(self):
        frappe.set_user(self.sales)
        created = create_lead(self._input("Read Only Lead"))
        modified_before = frappe.db.get_value("Lead", created["id"], "modified")

        detail = get_lead(created["id"])
        list_leads({"search": "Read Only Lead", "page": 1, "pageSize": 20})

        self.assertEqual(detail["id"], created["id"])
        self.assertEqual(frappe.db.get_value("Lead", created["id"], "modified"), modified_before)

    def test_only_manager_can_delete_lead(self):
        frappe.set_user(self.other_sales)
        lead = create_lead(self._input("Delete Lead"))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            delete_lead(lead["id"])
        self.assertTrue(frappe.db.exists("Lead", lead["id"]))

        frappe.set_user("Administrator")
        self.assertEqual(delete_lead(lead["id"]), {"id": lead["id"], "status": "Deleted"})
        self.assertFalse(frappe.db.exists("Lead", lead["id"]))

    def test_lead_create_fails_closed_if_erpnext_auto_contact_is_reenabled(self):
        frappe.set_user(self.sales)
        before = frappe.db.count("Contact")
        frappe.db.set_single_value("CRM Settings", "auto_creation_of_contact", 1)
        try:
            with self.assertRaises(CrmApiException) as failure:
                create_lead(self._input("Auto Contact Drift Lead"))
            self.assertEqual(failure.exception.code, "INTERNAL_ERROR")
            self.assertEqual(frappe.db.count("Contact"), before)
        finally:
            frappe.db.set_single_value("CRM Settings", "auto_creation_of_contact", 0)

    def _account_input(self, name: str) -> dict:
        return {
            "name": name,
            "shortName": name,
            "segment": "Advanced Packaging",
            "tier": "A",
            "city": "Shanghai",
            "region": "East China",
            "owner": frappe.session.user,
        }

    def _contact_input(self, account_id: str, name: str) -> dict:
        return {
            "accountId": account_id,
            "name": name,
            "title": "Process Manager",
            "department": "Process Engineering",
            "phone": "13800000005",
            "email": f"{name.replace(' ', '.').lower()}@example.invalid",
            "relationship": "Developing",
            "status": "Active",
            "owner": frappe.session.user,
        }

    def _site_input(self, name: str) -> dict:
        return {
            "name": name,
            "city": "Shanghai",
            "type": "Fab",
            "process": "Advanced Packaging",
            "status": "量产",
        }

    def _conversion_input(self, **overrides) -> dict:
        payload = {
            "opportunityTitle": "Advanced Packaging Inspection",
            "opportunityAmount": "250000.50",
            "opportunityAmountCny": "250000.50",
            "opportunityCloseDate": "2026-12-31",
            "opportunityOwner": self.sales,
            "toolType": "Inspection",
            "qualificationConfirmed": True,
            "opportunityProbabilityLevel": "pipeline",
        }
        payload.update(overrides)
        return payload

    def test_conversion_reuses_records_uses_selected_owner_and_is_idempotent(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Reuse Account"))
        site = create_site(account["id"], self._site_input("Lead Reuse Site"))
        contact_input = self._contact_input(account["id"], "Lead Reuse Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        lead = create_lead(self._input("Reusable Conversion Lead"))

        converted = convert_lead(
            lead["id"],
            self._conversion_input(accountId=account["id"], contactId=contact["id"], siteId=site["id"]),
        )

        self.assertEqual(converted["accountId"], account["id"])
        self.assertEqual(converted["contactId"], contact["id"])
        self.assertEqual(converted["lead"]["id"], lead["id"])
        self.assertTrue(converted["reusedAccount"])
        self.assertTrue(converted["reusedContact"])
        opportunity = frappe.get_doc("CRM Opportunity", converted["opportunityId"])
        self.assertEqual(opportunity.opportunity_owner, self.sales)
        self.assertEqual(opportunity.account, account["id"])
        self.assertEqual(opportunity.site, site["id"])
        self.assertEqual(opportunity.source_lead, lead["id"])
        self.assertEqual(str(opportunity.po_date), "2026-12-31")
        self.assertEqual(opportunity.stage, QUALIFIED_OPPORTUNITY)
        stage_history = frappe.get_all(
            "CRM Opportunity Stage History",
            filters={"opportunity": opportunity.name},
            fields=["to_stage", "source", "event", "reference_doctype", "reference_name"],
        )
        self.assertEqual(
            [(row.to_stage, row.source, row.event, row.reference_doctype, row.reference_name) for row in stage_history],
            [(QUALIFIED_OPPORTUNITY, "creation", "lead_converted", "Lead", lead["id"])],
        )
        self.assertEqual((opportunity.probability_level, opportunity.score), ("pipeline", 20))
        self.assertEqual(opportunity.sale_type, "New Equipment")
        self.assertEqual(opportunity.sub_region, "East China")
        self.assertEqual(opportunity.original_amount, opportunity.amount)
        history = frappe.get_all(
            "CRM Opportunity History",
            filters={"opportunity": opportunity.name},
            fields=["actor", "field", "from_value", "to_value"],
        )
        self.assertEqual(
            history,
            [{"actor": self.sales, "field": "leadConversion", "from_value": "", "to_value": lead["id"]}],
        )
        self.assertFalse(frappe.db.exists("Company", "Lead Reuse Account"))

        repeated = convert_lead(lead["id"], {"opportunityTitle": "Must Not Create Another"})
        self.assertEqual(repeated, converted)
        self.assertEqual(frappe.db.count("CRM Opportunity", {"source_lead": lead["id"]}), 1)

    def test_convert_lead_without_opportunity_amount(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Unpriced Account"))
        site = create_site(account["id"], self._site_input("Lead Unpriced Site"))
        contact_input = self._contact_input(account["id"], "Lead Unpriced Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        existing = {"accountId": account["id"], "contactId": contact["id"], "siteId": site["id"]}

        # A conversion always creates a qualified (S1) Opportunity, whose amounts may still be unknown.
        omitted = self._conversion_input(**existing)
        omitted.pop("opportunityAmount")
        omitted.pop("opportunityAmountCny")
        lead = create_lead(self._input("Unpriced Conversion Lead"))
        converted = convert_lead(lead["id"], omitted)
        opportunity = get_strategy_opportunity(converted["opportunityId"])
        self.assertEqual(
            (opportunity["stage"], opportunity["amount"], opportunity["originalAmount"], opportunity["amountCny"]),
            (QUALIFIED_OPPORTUNITY, "", "", ""),
        )
        self.assertEqual(
            tuple(frappe.db.get_value("CRM Opportunity", converted["opportunityId"], ["amount", "original_amount", "amount_cny"])),
            (0, 0, 0),
        )
        # Converting the same Lead again returns the first result and creates no second Opportunity.
        self.assertEqual(convert_lead(lead["id"], omitted), converted)
        self.assertEqual(frappe.db.count("CRM Opportunity", {"source_lead": lead["id"]}), 1)

        # Blank and exact zero mean the same. A CNY Opportunity takes its CNY amount from the amount (#87);
        # in another currency one amount entered does not require the other.
        for label, amounts, expected in (
            ("Blank", {"opportunityAmount": "", "opportunityAmountCny": ""}, ("", "", "")),
            ("Zero", {"opportunityAmount": "0", "opportunityAmountCny": "0.00"}, ("", "", "")),
            ("Priced", {"opportunityAmount": "1200.5", "opportunityAmountCny": ""}, ("1200.50", "1200.50", "1200.50")),
            ("Mismatch", {"opportunityAmount": "1200.5", "opportunityAmountCny": "99"}, ("1200.50", "1200.50", "1200.50")),
            (
                "Foreign",
                {"currency": "USD", "opportunityAmount": "1200.5", "opportunityAmountCny": ""},
                ("1200.50", "1200.50", ""),
            ),
        ):
            with self.subTest(label=label):
                lead = create_lead(self._input(f"{label} Conversion Lead"))
                converted = convert_lead(lead["id"], self._conversion_input(**existing, **amounts))
                opportunity = get_strategy_opportunity(converted["opportunityId"])
                self.assertEqual(
                    (opportunity["stage"], (opportunity["amount"], opportunity["originalAmount"], opportunity["amountCny"])),
                    (QUALIFIED_OPPORTUNITY, expected),
                )

    def test_manager_can_choose_opportunity_owner_during_conversion(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Assigned Account"))
        site = create_site(account["id"], self._site_input("Lead Assigned Site"))
        contact_input = self._contact_input(account["id"], "Lead Assigned Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        lead = create_lead(self._input("Manager Assigned Lead"))

        frappe.set_user(self.manager)
        converted = convert_lead(
            lead["id"],
            self._conversion_input(
                accountId=account["id"],
                contactId=contact["id"],
                siteId=site["id"],
                opportunityOwner=self.other_sales,
            ),
        )

        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", converted["opportunityId"], "opportunity_owner"),
            self.other_sales,
        )
        # The Manager who converts sets the first level; the new owner takes it from there.
        self.assertEqual(
            [
                (row["from"], row["to"], row["actor"])
                for row in get_strategy_opportunity(converted["opportunityId"])["probabilityHistory"]
            ],
            [("", "pipeline", self.manager)],
        )

    def test_manager_conversion_gives_the_new_account_and_contact_to_the_chosen_owner(self):
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Converted Lead", self.sales))
        conversion = self._conversion_input(
            newAccount={**self._account_input("Manager Converted Account"), "owner": self.sales},
            newSite=self._site_input("Manager Converted Site"),
            newContact={**self._contact_input("placeholder", "Manager Converted Contact"), "owner": self.sales},
        )

        converted = convert_lead(lead["id"], conversion)

        self.assertEqual(frappe.db.get_value("Customer", converted["accountId"], "custom_crm_owner"), self.sales)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.sales)
        # The Sales user the Lead belongs to keeps it and reaches everything the conversion created.
        frappe.set_user(self.sales)
        self.assertEqual(get_lead(lead["id"])["status"], "Converted")
        self.assertEqual(get_account_360(converted["accountId"])["account"]["owner"], self.sales)
        self.assertEqual(get_contact(converted["contactId"])["contact"]["owner"], self.sales)
        self.assertEqual(get_strategy_opportunity(converted["opportunityId"])["owner"], self.sales)

    def test_manager_conversion_notifies_the_owner_even_when_the_record_id_is_too_long_for_a_route(self):
        # Frappe names a Contact "<name>-<Account ID>". With a long Account ID the route to the Contact
        # no longer fits the notification's route field; the conversion must not fail on that.
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Long Account " + "N" * 82))
        site = create_site(account["id"], self._site_input("Lead Long Site"))
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Long Route Lead", self.sales))
        contact_input = {**self._contact_input("placeholder", "Long Route Contact " + "C" * 11), "owner": self.sales}

        converted = convert_lead(lead["id"], self._conversion_input(
            accountId=account["id"], siteId=site["id"], newContact=contact_input,
        ))

        self.assertGreater(len(f"/contacts/{converted['contactId']}"), 140)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.sales)
        notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "Contact", "source_name": converted["contactId"], "recipient_user": self.sales},
            fields=["title", "route"],
        )
        self.assertEqual([(row.title, row.route) for row in notice], [("Contact assigned", "/contacts")])
        self.assertEqual(get_lead(lead["id"])["status"], "Converted")

    def test_manager_conversion_that_fails_part_way_leaves_nothing_behind(self):
        engineer = self._user("crm-lead-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Rollback Lead", self.sales))
        counted = ("Customer", "Address", "Contact", "CRM Opportunity", "CRM Notification Event")
        before = {doctype: frappe.db.count(doctype) for doctype in counted}

        # The Account goes to Sales, which writes the Account and its notice; the Contact owner is then refused.
        with self.assertRaises(CrmApiException) as invalid:
            convert_lead(lead["id"], self._conversion_input(
                newAccount={**self._account_input("Manager Rollback Account"), "owner": self.sales},
                newSite=self._site_input("Manager Rollback Site"),
                newContact={**self._contact_input("placeholder", "Manager Rollback Contact"), "owner": engineer},
            ))

        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        self.assertEqual({doctype: frappe.db.count(doctype) for doctype in counted}, before)
        self.assertEqual(get_lead(lead["id"])["status"], "New")

    def test_manager_conversion_without_a_chosen_owner_keeps_the_records_with_the_manager(self):
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Own Conversion Lead", self.sales))
        account_input = self._account_input("Manager Own Conversion Account")
        contact_input = self._contact_input("placeholder", "Manager Own Conversion Contact")
        del account_input["owner"], contact_input["owner"]

        converted = convert_lead(lead["id"], self._conversion_input(
            newAccount=account_input, newSite=self._site_input("Manager Own Conversion Site"), newContact=contact_input,
        ))

        self.assertEqual(frappe.db.get_value("Customer", converted["accountId"], "custom_crm_owner"), self.manager)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.manager)

    def test_manager_conversion_refuses_an_owner_who_cannot_hold_records(self):
        engineer = self._user("crm-lead-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Invalid Owner Lead", self.sales))
        before = frappe.db.count("Customer")

        with self.assertRaises(CrmApiException) as invalid:
            convert_lead(lead["id"], self._conversion_input(
                newAccount={**self._account_input("Manager Invalid Owner Account"), "owner": engineer},
                newSite=self._site_input("Manager Invalid Owner Site"),
                newContact=self._contact_input("placeholder", "Manager Invalid Owner Contact"),
            ))

        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        self.assertEqual(frappe.db.count("Customer"), before)
        self.assertEqual(get_lead(lead["id"])["status"], "New")

    def test_sales_conversion_keeps_the_new_account_and_contact_with_the_converting_sales(self):
        frappe.set_user(self.sales)
        lead = create_lead(self._input("Sales Own Conversion Lead"))

        converted = convert_lead(lead["id"], self._conversion_input(
            newAccount={**self._account_input("Sales Own Conversion Account"), "owner": self.other_sales},
            newSite=self._site_input("Sales Own Conversion Site"),
            newContact={**self._contact_input("placeholder", "Sales Own Conversion Contact"), "owner": self.other_sales},
        ))

        self.assertEqual(frappe.db.get_value("Customer", converted["accountId"], "custom_crm_owner"), self.sales)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.sales)

    def test_conversion_needs_a_probability_level_before_it_writes_anything(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Level Account"))
        site = create_site(account["id"], self._site_input("Lead Level Site"))
        contact_input = self._contact_input(account["id"], "Lead Level Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        lead = create_lead(self._input("Level Required Lead"))
        existing = {"accountId": account["id"], "contactId": contact["id"], "siteId": site["id"]}

        with self.assertRaises(CrmApiException) as missing:
            convert_lead(lead["id"], self._conversion_input(**existing, opportunityProbabilityLevel=""))
        self.assertEqual(
            (missing.exception.code, missing.exception.field_errors),
            ("VALIDATION_ERROR", {"opportunityProbabilityLevel": "Required"}),
        )
        self.assertEqual(frappe.db.count("CRM Opportunity", {"source_lead": lead["id"]}), 0)
        self.assertEqual(get_lead(lead["id"])["status"], "New")

        converted = convert_lead(lead["id"], self._conversion_input(**existing, opportunityProbabilityLevel="upside"))
        opportunity = get_strategy_opportunity(converted["opportunityId"])
        self.assertEqual(opportunity["probabilityLevel"], "upside")
        self.assertEqual(
            [(row["from"], row["to"], row["actor"]) for row in opportunity["probabilityHistory"]],
            [("", "upside", self.sales)],
        )

    def test_conversion_can_create_account_and_contact_and_rolls_back_each_subwrite(self):
        frappe.set_user(self.sales)
        lead = create_lead(self._input("New Records Conversion Lead"))
        conversion = self._conversion_input(
            newAccount=self._account_input("Converted New Account"),
            newSite=self._site_input("Converted New Site"),
            newContact=self._contact_input("placeholder", "Converted New Contact"),
        )

        converted = convert_lead(lead["id"], conversion)
        self.assertFalse(converted["reusedAccount"])
        self.assertFalse(converted["reusedContact"])
        self.assertEqual(
            frappe.db.get_value("Lead", lead["id"], "custom_crm_status"),
            "Converted",
        )

        for stage in ("account", "site", "contact", "opportunity", "lead"):
            rollback_lead = create_lead(self._input(f"Rollback {stage} Lead"))
            before = {
                doctype: frappe.db.count(doctype)
                for doctype in ("Customer", "Address", "Contact", "CRM Opportunity")
            }

            def fail_at(current_stage: str, expected=stage):
                if current_stage == expected:
                    raise RuntimeError(f"injected after {expected}")

            with self.assertRaisesRegex(RuntimeError, f"injected after {stage}"):
                convert_lead(
                    rollback_lead["id"],
                    self._conversion_input(
                        newAccount=self._account_input(f"Rollback {stage} Account"),
                        newSite=self._site_input(f"Rollback {stage} Site"),
                        newContact=self._contact_input("placeholder", f"Rollback {stage} Contact"),
                    ),
                    failure_injector=fail_at,
                )
            self.assertEqual(
                {doctype: frappe.db.count(doctype) for doctype in before},
                before,
            )
            self.assertEqual(frappe.db.get_value("Lead", rollback_lead["id"], "custom_crm_status"), "New")

    def test_conversion_rejects_invalid_money_and_close_date_without_writes(self):
        frappe.set_user(self.sales)
        lead = create_lead(self._input("Invalid Conversion Lead"))
        before = frappe.db.count("CRM Opportunity")
        # Blank or zero is an amount not entered yet (test_convert_lead_without_opportunity_amount).
        messages = {
            "opportunityAmount": "opportunityAmount must be blank or a non-negative amount with at most two decimal places.",
            "opportunityAmountCny": "opportunityAmountCny must be positive with at most two decimal places.",
        }
        for field, invalid in (
            *(("opportunityAmount", value) for value in ("-1", "1.234", "not-money", True)),
            *(("opportunityAmountCny", value) for value in ("-1", "1.234", "not-money")),
        ):
            with self.subTest(field=field, invalid=invalid):
                with self.assertRaises(CrmApiException) as failure:
                    convert_lead(
                        lead["id"],
                        self._conversion_input(
                            **{field: invalid},
                            newAccount=self._account_input("Invalid Conversion Account"),
                            newSite=self._site_input("Invalid Conversion Site"),
                            newContact=self._contact_input("placeholder", "Invalid Conversion Contact"),
                        ),
                    )
                self.assertEqual(failure.exception.code, "VALIDATION_ERROR")
                # The API names the field that is wrong, for either amount, with the message the front end maps.
                self.assertEqual(failure.exception.field_errors, {field: "Invalid amount"})
                self.assertEqual(failure.exception.public_message, messages[field])
        with self.assertRaises(CrmApiException) as bad_date:
            convert_lead(
                lead["id"],
                self._conversion_input(
                    opportunityCloseDate="2026-02-31",
                    newAccount=self._account_input("Invalid Date Account"),
                    newSite=self._site_input("Invalid Date Site"),
                    newContact=self._contact_input("placeholder", "Invalid Date Contact"),
                ),
            )
        self.assertEqual(bad_date.exception.code, "VALIDATION_ERROR")
        unqualified = self._conversion_input(
            newAccount=self._account_input("Unqualified Conversion Account"),
            newSite=self._site_input("Unqualified Conversion Site"),
            newContact=self._contact_input("placeholder", "Unqualified Conversion Contact"),
        )
        unqualified.pop("qualificationConfirmed")
        with self.assertRaises(CrmApiException) as not_confirmed:
            convert_lead(lead["id"], unqualified)
        self.assertEqual(not_confirmed.exception.code, "VALIDATION_ERROR")
        self.assertEqual(not_confirmed.exception.field_errors, {"qualificationConfirmed": "Required"})
        self.assertEqual(frappe.db.count("CRM Opportunity"), before)
