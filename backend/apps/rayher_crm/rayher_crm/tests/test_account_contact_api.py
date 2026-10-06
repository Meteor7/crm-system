from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from rayher_crm.api.v1.accounts import create_account as create_account_endpoint
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import accounts as account_service
from rayher_crm.services.accounts import create_account, delete_account, get_account_360, list_accounts, update_account
from rayher_crm.services.contacts import (
    create_contact,
    delete_contact,
    get_contact,
    list_contacts,
    merge_contacts,
    update_contact,
    contacts_for_account,
)
from rayher_crm.services.sites import _require_site, create_site, list_account_sites, sites_for_account
from rayher_crm.services.visits import create_visit


class TestAccountContactApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-account-contact-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-account-contact-other@example.invalid", "CRM Sales")
        self.manager = self._user("crm-account-contact-manager@example.invalid", "CRM Manager")

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

    def _account_input(self, name: str, owner: str | None = None) -> dict:
        return {
            "name": name,
            "shortName": name[:8],
            "segment": "Frontend",
            "tier": "A",
            "city": "上海",
            "region": "华东",
            "owner": owner or frappe.session.user,
        }

    def _contact_input(self, account_id: str, name: str, **overrides) -> dict:
        payload = {
            "accountId": account_id,
            "name": name,
            "title": "Director",
            "department": "Engineering",
            "phone": "13800000002",
            "email": f"{name.replace(' ', '.').lower()}@example.invalid",
            "relationship": "Developing",
            "owner": frappe.session.user,
            "status": "Active",
        }
        payload.update(overrides)
        return payload

    def _site_input(self, name: str) -> dict:
        return {"name": name, "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产"}

    def test_account_create_list_update_and_endpoint_envelope(self):
        frappe.set_user(self.sales)
        created = create_account(self._account_input("Account Vertical Slice"))
        self.assertTrue(created["id"])
        self.assertEqual(created["owner"], self.sales)
        self.assertRegex(created["modified"], r"Z$")

        items, total, page, page_size = list_accounts({"search": "Vertical Slice", "page": "1", "pageSize": "100000"})
        self.assertIn(created["id"], {item["id"] for item in items})
        self.assertGreaterEqual(total, 1)
        self.assertEqual((page, page_size), (1, 200))

        with self.assertRaises(CrmApiException) as stale:
            update_account(created["id"], self._account_input("Stale Name"), "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        updated = update_account(created["id"], self._account_input("Updated Account"), created["modified"])
        self.assertEqual(updated["name"], "Updated Account")
        self.assertNotEqual(updated["modified"], created["modified"])

        public_input = self._account_input("Updated Account")
        public_input["visibility"] = "Public"
        public = update_account(created["id"], public_input, updated["modified"])
        self.assertEqual(public["visibility"], "Public")
        public_input.pop("visibility")
        preserved = update_account(created["id"], public_input, public["modified"])
        self.assertEqual(preserved["visibility"], "Public")

        def fail_after_account_update(stage: str):
            if stage == "after_account_update":
                raise RuntimeError("injected account update failure")

        with self.assertRaises(RuntimeError):
            update_account(
                created["id"],
                self._account_input("Must Roll Back"),
                preserved["modified"],
                failure_injector=fail_after_account_update,
            )
        self.assertEqual(frappe.db.get_value("Customer", created["id"], "customer_name"), "Updated Account")

        endpoint = create_account_endpoint(self._account_input("Endpoint Account"))
        self.assertEqual(endpoint["data"]["name"], "Endpoint Account")
        self.assertEqual(endpoint["warnings"], [])
        self.assertRegex(endpoint["meta"]["requestId"], r"^req_[0-9a-f]{24}$")

    def test_manager_assignments_notify_reachable_account_and_contact(self):
        frappe.set_user(self.manager)
        account = create_account(self._account_input("Assigned Account", self.sales))
        contact = create_contact(self._contact_input(
            account["id"], "Assigned Contact", owner=self.sales,
        ))
        for source_doctype, source_name, category, route in (
            ("Customer", account["id"], "Account", f"/accounts/{account['id']}"),
            ("Contact", contact["id"], "Contact", f"/contacts/{contact['id']}"),
        ):
            notice = frappe.get_all(
                "CRM Notification Event",
                filters={"source_doctype": source_doctype, "source_name": source_name,
                         "recipient_user": self.sales},
                fields=["category", "route"], order_by="creation desc", limit=1,
            )[0]
            self.assertEqual((notice.category, notice.route), (category, route))
        frappe.set_user(self.sales)
        self.assertEqual(get_account_360(account["id"])["account"]["id"], account["id"])
        self.assertEqual(get_contact(contact["id"])["contact"]["id"], contact["id"])

    def test_account_360_contacts_read_all_pages(self):
        pages = [
            ([{"id": f"CON-{index}"} for index in range(200)], 201, 1, 200),
            ([{"id": "CON-200"}], 201, 2, 200),
        ]

        with patch("rayher_crm.services.contacts.list_contacts", side_effect=pages) as list_page:
            items = contacts_for_account("ACC-PAGED")

        self.assertEqual(len(items), 201)
        self.assertEqual(list_page.call_count, 2)
        self.assertEqual(list_page.call_args_list[1].args[0]["page"], 2)

    def test_custom_account_segment_is_trimmed_registered_and_deduplicated(self):
        frappe.set_user(self.sales)
        self.addCleanup(frappe.clear_cache, doctype="Customer")

        custom_segment = "Power Semiconductor"
        first_input = self._account_input("Custom Segment Account One")
        first_input["segment"] = f"  {custom_segment}  "
        try:
            first = create_account(first_input)
        except CrmApiException as exc:
            self.fail(f"custom account segment was rejected: {exc.code}")

        self.assertEqual(first["segment"], custom_segment)
        self.assertEqual(account_service.list_account_segments().count(custom_segment), 1)

        second_input = self._account_input("Custom Segment Account Two")
        second_input["segment"] = custom_segment
        second = create_account(second_input)
        self.assertEqual(second["segment"], custom_segment)
        self.assertEqual(account_service.list_account_segments().count(custom_segment), 1)

        blank_input = self._account_input("Blank Segment Account")
        blank_input["segment"] = "   "
        with self.assertRaises(CrmApiException) as blank:
            create_account(blank_input)
        self.assertEqual(blank.exception.code, "VALIDATION_ERROR")

    def test_sales_can_read_public_accounts_but_only_owner_can_write(self):
        frappe.set_user(self.other_sales)
        foreign = create_account(self._account_input("Foreign Account"))
        foreign_site = create_site(foreign["id"], self._site_input("Foreign Account Site"))
        foreign_contact = create_contact(self._contact_input(
            foreign["id"], "Foreign Contact", siteId=foreign_site["id"],
        ))
        owner_contact = get_contact(foreign_contact["id"])["contact"]
        self.assertEqual(owner_contact["siteId"], foreign_site["id"])
        self.assertEqual(owner_contact["siteName"], "Foreign Account Site")

        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as assignment:
            create_account(self._account_input("Assigned To Other Sales", self.other_sales))
        self.assertEqual(assignment.exception.code, "SCOPE_DENIED")
        # A Private Account of someone else answers as an Account that does not exist: the id of an Account is
        # its name, and two answers would let a Sales user list the company's Accounts by trying names. The
        # same for its Contacts.
        with self.assertRaises(CrmApiException) as private:
            get_account_360(foreign["id"])
        with self.assertRaises(CrmApiException) as missing:
            get_account_360("No Such Account")
        self.assertEqual(
            (private.exception.code, private.exception.public_message),
            ("NOT_FOUND", "Account was not found, or you have no access to it."),
        )
        self.assertEqual(
            (missing.exception.code, missing.exception.public_message),
            (private.exception.code, private.exception.public_message),
        )
        with self.assertRaises(CrmApiException) as private_contact:
            get_contact(foreign_contact["id"])
        with self.assertRaises(CrmApiException) as missing_contact:
            get_contact("No Such Contact")
        # The same where a Contact or a Site is named on another record: a Quotation's ATTN, a Site by its id.
        from rayher_crm.services import quotations

        with self.assertRaises(CrmApiException) as attn:
            quotations._validate_contact(foreign_contact["id"], "Any Account")
        self.assertEqual(
            (attn.exception.code, attn.exception.public_message),
            ("NOT_FOUND", "Contact was not found, or you have no access to it."),
        )
        with self.assertRaises(CrmApiException) as private_site:
            _require_site(foreign_site["id"])
        with self.assertRaises(CrmApiException) as missing_site:
            _require_site("No Such Site-Other")
        self.assertEqual(
            (private_site.exception.code, private_site.exception.public_message),
            ("NOT_FOUND", "Site was not found, or you have no access to it."),
        )
        self.assertEqual(
            (missing_site.exception.code, missing_site.exception.public_message),
            (private_site.exception.code, private_site.exception.public_message),
        )
        self.assertEqual(
            (private_contact.exception.code, private_contact.exception.public_message),
            ("NOT_FOUND", "Contact was not found, or you have no access to it."),
        )
        self.assertEqual(
            (missing_contact.exception.code, missing_contact.exception.public_message),
            (private_contact.exception.code, private_contact.exception.public_message),
        )

        frappe.set_user(self.other_sales)
        public_input = self._account_input("Foreign Account")
        public_input["visibility"] = "Public"
        foreign = update_account(foreign["id"], public_input, foreign["modified"])
        self.assertEqual((foreign["visibility"], foreign["metricsRestricted"], foreign["siteCount"]), ("Public", False, 1))

        frappe.set_user(self.sales)
        detail = get_account_360(foreign["id"])
        self.assertEqual(detail["account"]["id"], foreign["id"])
        self.assertEqual(detail["sites"], [])
        # The zeroes the other Sales user gets are said to be no numbers (F1-11).
        self.assertEqual((detail["account"]["metricsRestricted"], detail["account"]["siteCount"]), (True, 0))
        listed = list_accounts({"accountId": foreign["id"], "page": 1, "pageSize": 10})[0]
        self.assertEqual([(row["id"], row["metricsRestricted"]) for row in listed], [(foreign["id"], True)])
        # The search finds the owner by the name the pages show, and takes `%` and `_` as letters (F1-09).
        frappe.db.set_value("User", self.other_sales, {"first_name": "Foreign Owner", "full_name": "Foreign Owner"}, update_modified=False)
        by_owner = list_accounts({"search": "Foreign Own", "page": 1, "pageSize": 50})[0]
        self.assertIn(foreign["id"], [row["id"] for row in by_owner])
        self.assertEqual(list_accounts({"search": "%", "page": 1, "pageSize": 50})[1], 0)
        self.assertEqual(list_accounts({"search": "_", "page": 1, "pageSize": 50})[1], 0)
        with self.assertRaises(CrmApiException) as site_denied:
            sites_for_account(foreign["id"])
        self.assertEqual(site_denied.exception.code, "SCOPE_DENIED")
        # A Site of the Public Account, whose Sites are its owner's, answers as one that does not exist, named
        # with its Account or without: its id carries its name.
        for account in (foreign["id"], None):
            with self.assertRaises(CrmApiException) as site_hidden:
                _require_site(foreign_site["id"], account)
            self.assertEqual(
                (site_hidden.exception.code, site_hidden.exception.public_message),
                ("NOT_FOUND", "Site was not found, or you have no access to it."),
            )
        public_contact = get_contact(foreign_contact["id"])["contact"]
        self.assertEqual(public_contact["id"], foreign_contact["id"])
        self.assertNotIn("siteId", public_contact)
        self.assertNotIn("siteName", public_contact)
        self.assertFalse(
            frappe.has_permission("Contact", "read", doc=foreign_contact["id"], user=self.sales),
        )
        self.assertEqual(
            frappe.get_list("Contact", filters={"name": foreign_contact["id"]}, pluck="name"),
            [],
        )
        with self.assertRaises(CrmApiException) as site_filter:
            list_contacts({"siteId": foreign_site["id"], "page": 1, "pageSize": 20})
        self.assertEqual(site_filter.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as account_write:
            update_account(foreign["id"], self._account_input("Sales Updated Foreign"), foreign["modified"])
        self.assertEqual(account_write.exception.code, "SCOPE_DENIED")
        with self.assertRaises(CrmApiException) as contact_write:
            update_contact(
                foreign_contact["id"],
                self._contact_input(foreign["id"], "Sales Updated Contact"),
                foreign_contact["modified"],
            )
        self.assertEqual(contact_write.exception.code, "SCOPE_DENIED")

    def test_account_sites_in_one_read_are_the_sites_of_each_account_360(self):
        engineer = self._user("crm-account-contact-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.sales)
        own = create_account(self._account_input("One Read Own"))
        own_sites = [create_site(own["id"], self._site_input(name)) for name in ("One Read Fab A", "One Read Fab B")]
        empty = create_account(self._account_input("One Read No Site"))
        frappe.set_user(self.other_sales)
        private = create_account(self._account_input("One Read Private"))
        create_site(private["id"], self._site_input("One Read Private Fab"))
        public_input = self._account_input("One Read Public")
        public_input["visibility"] = "Public"
        public = create_account(public_input)
        public_site = create_site(public["id"], self._site_input("One Read Public Fab"))
        frappe.set_user("Administrator")
        frappe.get_doc({
            "doctype": "CRM Account Engineer Assignment", "customer": public["id"], "engineer": engineer, "enabled": 1,
        }).insert(ignore_permissions=True)
        made = {own["id"], empty["id"], private["id"], public["id"]}

        def one_read():
            return [site for site in list_account_sites() if site["accountId"] in made]

        def one_by_one():
            listed = [item["id"] for item in list_accounts({"page": 1, "pageSize": 200})[0] if item["id"] in made]
            return [
                {"accountId": account, **site}
                for account in sorted(listed) for site in get_account_360(account)["sites"]
            ]

        # A Sales user reads the Sites of their own Accounts; a Public Account of someone else shares none.
        frappe.set_user(self.sales)
        self.assertEqual(
            [(site["accountId"], site["id"]) for site in one_read()],
            [(own["id"], site["id"]) for site in reversed(own_sites)],
        )
        self.assertEqual(one_read()[0], {"accountId": own["id"], **own_sites[1]})
        # An Engineer reads the Sites of the Accounts assigned to them, a Manager all of them.
        frappe.set_user(engineer)
        self.assertEqual(one_read(), [{"accountId": public["id"], **public_site}])
        frappe.set_user(self.manager)
        self.assertEqual({site["accountId"] for site in one_read()}, {own["id"], private["id"], public["id"]})
        # For a Sales user and a Manager it is what the Account 360 of each listed Account returns
        # (an Engineer has no Account 360: it needs visit:view).
        for user in (self.sales, self.other_sales, self.manager):
            frappe.set_user(user)
            self.assertEqual(one_read(), one_by_one(), user)

    def test_account_sites_in_one_read_need_the_account_capability(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            list_account_sites()

    def test_account_city_dictionary_uses_all_customer_records(self):
        frappe.set_user(self.sales)
        city_input = self._account_input("Kunshan City Account")
        city_input["city"] = "昆山"
        create_account(city_input)

        self.assertIn("昆山", account_service.list_account_cities())

    def test_only_manager_can_delete_account(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Delete Account"))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            delete_account(account["id"])
        self.assertTrue(frappe.db.exists("Customer", account["id"]))

        frappe.set_user("Administrator")
        self.assertEqual(delete_account(account["id"]), {"id": account["id"], "status": "Deleted"})
        self.assertFalse(frappe.db.exists("Customer", account["id"]))

    def test_manager_delete_maps_link_conflict_without_partial_mutation(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Referenced Account"))
        visit = create_visit({
            "accountId": account["id"], "primaryContactId": "", "subject": "Referenced visit",
            "date": "2026-08-20", "type": "On-site", "owner": self.other_sales,
            "objective": "Keep the account linked",
        })

        frappe.set_user("Administrator")
        with self.assertRaises(CrmApiException) as conflict:
            delete_account(account["id"])
        self.assertEqual(conflict.exception.code, "CONFLICT")
        self.assertTrue(frappe.db.exists("Customer", account["id"]))
        self.assertTrue(frappe.db.exists("CRM Visit", visit["id"]))

    def test_account_360_derives_contact_names_and_read_does_not_write(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Read Only 360"))
        site = create_site(account["id"], self._site_input("Read Only Site"))
        contact = create_contact(self._contact_input(account["id"], "Reader Contact"))
        archived = create_contact(self._contact_input(account["id"], "Archived Contact", status="Archived"))
        account_modified = frappe.db.get_value("Customer", account["id"], "modified")
        contact_modified = frappe.db.get_value("Contact", contact["id"], "modified")

        detail = get_account_360(account["id"])

        self.assertEqual(detail["account"]["name"], "Read Only 360")
        self.assertEqual(detail["contacts"][0]["accountName"], "Read Only 360")
        self.assertEqual({item["id"] for item in detail["contacts"]}, {contact["id"]})
        self.assertNotIn(archived["id"], {item["id"] for item in detail["contacts"]})
        self.assertEqual(detail["sites"], [{**self._site_input("Read Only Site"), "id": site["id"]}])
        self.assertEqual(detail["requirements"], [])
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "modified"), account_modified)
        self.assertEqual(frappe.db.get_value("Contact", contact["id"], "modified"), contact_modified)

    def test_contact_search_finds_the_name_the_pages_show(self):
        # A standard Frappe Contact keeps its name in first_name and last_name; the pages show them joined (F1-09).
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Full Name Search"))
        contact = create_contact(self._contact_input(account["id"], "Search Placeholder"))
        frappe.db.set_value("Contact", contact["id"], {"first_name": "John", "last_name": "Smith"}, update_modified=False)
        for search in ("John Smith", "ohn Smi", "John", "Smith"):
            with self.subTest(search=search):
                items, total, _, _ = list_contacts({"accountId": account["id"], "search": search, "page": 1, "pageSize": 20})
                self.assertEqual(([row["id"] for row in items], total), ([contact["id"]], 1))
                self.assertEqual(items[0]["name"], "John Smith")

    def test_contact_rejects_site_from_another_account(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Site Account"))
        other = create_account(self._account_input("Other Site Account"))
        foreign_site = create_site(other["id"], self._site_input("Foreign Site"))

        with self.assertRaises(CrmApiException) as mismatch:
            create_contact(self._contact_input(account["id"], "Wrong Site Contact", siteId=foreign_site["id"]))
        self.assertEqual(mismatch.exception.code, "CONFLICT")

    def test_contact_crud_optimistic_lock_and_reporting_cycle(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Contact Account"))
        parent = create_contact(self._contact_input(account["id"], "Parent Contact"))
        child = create_contact(self._contact_input(account["id"], "Child Contact", reportsToContactId=parent["id"]))

        detail = get_contact(child["id"])
        self.assertEqual(detail["contact"]["accountId"], account["id"])
        self.assertEqual(detail["reportsTo"]["id"], parent["id"])

        with self.assertRaises(CrmApiException) as cycle:
            update_contact(
                parent["id"],
                self._contact_input(account["id"], "Parent Contact", reportsToContactId=child["id"]),
                parent["modified"],
            )
        self.assertEqual(cycle.exception.code, "VALIDATION_ERROR")

        updated = update_contact(
            child["id"],
            self._contact_input(account["id"], "Child Contact Updated", reportsToContactId=parent["id"]),
            child["modified"],
        )
        self.assertEqual(updated["name"], "Child Contact Updated")

    def test_contact_list_paginates_and_public_account_is_shared_between_sales(self):
        frappe.set_user(self.sales)
        account_input = self._account_input("Scoped Contacts")
        account_input["visibility"] = "Public"
        account = create_account(account_input)
        first = create_contact(self._contact_input(account["id"], "Scoped One"))
        create_contact(self._contact_input(account["id"], "Scoped Two"))

        items, total, page, page_size = list_contacts({"accountId": account["id"], "page": 1, "pageSize": 1})
        self.assertEqual(len(items), 1)
        self.assertGreaterEqual(total, 2)
        self.assertEqual((page, page_size), (1, 1))
        self.assertEqual(items[0]["accountId"], account["id"])

        all_items, all_total, _, _ = list_contacts(
            {
                "accountId": "All",
                "siteId": "All",
                "owner": "All",
                "contactStatus": "Active",
                "page": 1,
                "pageSize": 200,
            }
        )
        self.assertIn(first["id"], {item["id"] for item in all_items})
        self.assertGreaterEqual(all_total, 2)

        frappe.set_user(self.other_sales)
        self.assertEqual(get_contact(first["id"])["contact"]["id"], first["id"])

    def test_contact_merge_and_delete_are_soft_and_transactional(self):
        frappe.set_user("Administrator")
        account = create_account(self._account_input("Merge Account", self.sales))
        survivor = create_contact(self._contact_input(account["id"], "Survivor", owner=self.sales))
        duplicate = create_contact(self._contact_input(account["id"], "Duplicate", owner=self.sales))
        report = create_contact(
            self._contact_input(account["id"], "Direct Report", owner=self.sales, reportsToContactId=duplicate["id"])
        )

        merged = merge_contacts(survivor["id"], duplicate["id"])
        self.assertEqual(merged["id"], survivor["id"])
        self.assertTrue(frappe.db.exists("Contact", duplicate["id"]))
        self.assertEqual(frappe.db.get_value("Contact", duplicate["id"], "custom_crm_status"), "Archived")
        self.assertEqual(frappe.db.get_value("Contact", duplicate["id"], "custom_crm_merged_into"), survivor["id"])
        self.assertEqual(frappe.db.get_value("Contact", report["id"], "custom_crm_reports_to"), survivor["id"])

        rollback_survivor = create_contact(self._contact_input(account["id"], "Rollback Survivor", owner=self.sales))
        rollback_duplicate = create_contact(self._contact_input(account["id"], "Rollback Duplicate", owner=self.sales))

        def fail_after_first_write():
            raise RuntimeError("injected merge failure")

        with self.assertRaises(RuntimeError):
            merge_contacts(rollback_survivor["id"], rollback_duplicate["id"], failure_injector=fail_after_first_write)
        self.assertEqual(frappe.db.get_value("Contact", rollback_duplicate["id"], "custom_crm_status"), "Active")
        self.assertIsNone(frappe.db.get_value("Contact", rollback_duplicate["id"], "custom_crm_merged_into"))

        historical_reference = create_contact(
            self._contact_input(account["id"], "Historical Reference", owner=self.sales, reportsToContactId=report["id"])
        )
        deleted = delete_contact(report["id"])
        self.assertEqual(deleted, {"id": report["id"], "status": "Deleted"})
        self.assertTrue(frappe.db.exists("Contact", report["id"]))
        self.assertEqual(frappe.db.get_value("Contact", report["id"], "custom_crm_status"), "Archived")
        self.assertEqual(
            frappe.db.get_value("Contact", historical_reference["id"], "custom_crm_reports_to"),
            report["id"],
        )

        rollback_delete = create_contact(self._contact_input(account["id"], "Rollback Delete", owner=self.sales))

        def fail_after_contact_archive(stage: str):
            if stage == "after_contact_archive":
                raise RuntimeError("injected contact delete failure")

        with self.assertRaises(RuntimeError):
            delete_contact(rollback_delete["id"], failure_injector=fail_after_contact_archive)
        self.assertEqual(frappe.db.get_value("Contact", rollback_delete["id"], "custom_crm_status"), "Active")
