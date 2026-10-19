from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from rayher_crm.api.v1.accounts import create_account as create_account_endpoint
from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services import accounts as account_service
from rayher_crm.services import cockpit
from rayher_crm.services.accounts import (
    ACCOUNT_WITH_DEMO_REQUEST_ARCHIVE,
    ACCOUNT_WITH_DEMO_TEST_ARCHIVE,
    ACCOUNT_WITH_LIVE_BOOKING_ARCHIVE,
    ACCOUNT_WITH_OPEN_OPPORTUNITY_ARCHIVE,
    ARCHIVED_ACCOUNT_EDIT,
    ARCHIVED_ACCOUNT_LINK,
    ARCHIVED_ACCOUNT_REOPEN,
    archive_account,
    create_account,
    get_account_360,
    list_accounts,
    unarchive_account,
    update_account,
)
from rayher_crm.services import bookings as booking_service
from rayher_crm.services import opportunities as opportunity_service
from rayher_crm.services import opportunity_status
from rayher_crm.services import quotations as quotation_service
from rayher_crm.services.bookings import archive_booking, create_booking, get_booking, unarchive_booking, update_booking
from rayher_crm.services.contacts import (
    create_contact,
    delete_contact,
    get_contact,
    list_contacts,
    merge_contacts,
    update_contact,
    contacts_for_account,
)
from rayher_crm.services.demo_requests import create_demo_request
from rayher_crm.services.opportunities import (
    archive_strategy_opportunity,
    confirm_po,
    create_strategy_opportunity,
    get_strategy_opportunity,
    mark_opportunity_lost,
    request_internal_validation,
    review_internal_validation,
    rollback_opportunity_stage,
    unarchive_strategy_opportunity,
    update_strategy_opportunity,
)
from rayher_crm.services.opportunity_stages import OPEN_STAGES, QUALIFIED_OPPORTUNITY
from rayher_crm.setup import indexes
from rayher_crm.services.quotations import (
    create_quotation,
    discard_draft,
    get_quotation,
    link_quotation_opportunity,
    save_draft,
    submit_for_approval,
)
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture
from rayher_crm.services.sites import _require_site, create_site, delete_site, list_account_sites, sites_for_account, update_site
from rayher_crm.services.visits import create_visit, update_visit


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
            "phone": "13800000001",
            "email": f"{name.replace(' ', '.').lower()}@example.invalid",
            "relationship": "Developing",
            "owner": frappe.session.user,
            "status": "Active",
        }
        payload.update(overrides)
        return payload

    def _site_input(self, name: str) -> dict:
        return {"name": name, "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产"}

    def test_customer_relationship_validates_and_omitted_legacy_payload_preserves_it(self):
        frappe.set_user(self.sales)
        payload = self._account_input("Relationship Master")
        created = create_account({**payload, "customerKind": "Prospect"})
        self.assertEqual(created["customerKind"], "Prospect")
        preserved = update_account(created["id"], payload, created["modified"])
        self.assertEqual(preserved["customerKind"], "Prospect")
        updated = update_account(created["id"], {**payload, "customerKind": "Existing"}, preserved["modified"])
        self.assertEqual(updated["customerKind"], "Existing")
        with self.assertRaises(CrmApiException):
            update_account(created["id"], {**payload, "customerKind": "Invented"}, updated["modified"])
        self.assertEqual(frappe.db.get_value("Customer", created["id"], "custom_crm_customer_kind"), "Existing")
        cleared = update_account(created["id"], {**payload, "customerKind": ""}, updated["modified"])
        self.assertEqual(cleared["customerKind"], "")

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

    def _opportunity_input(self, account: dict, site: dict, owner: str, title: str) -> dict:
        return {
            "accountId": account["id"], "siteId": site["id"], "title": title, "owner": owner,
            "amount": "125000.25", "intentScore": 35, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY", "originalAmount": "125000.25",
            "amountCny": "125000.25", "qualificationConfirmed": True, "probabilityLevel": "pipeline",
            "stage": QUALIFIED_OPPORTUNITY,
        }

    def _upsell_input(self, account: dict, contact: dict, owner: str, **overrides) -> dict:
        payload = {
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Inspection 3000",
            "quantity": 1, "ddl": "2027-01-31", "amount": "20000.00", "currency": "CNY", "status": "Confirmed",
            "owner": owner, "source": "Upsell", "sourceOpportunityId": "", "note": "Spare parts",
        }
        payload.update(overrides)
        return payload

    def _visit_input(self, account: dict, owner: str, subject: str) -> dict:
        return {
            "accountId": account["id"], "primaryContactId": "", "subject": subject, "date": "2026-08-20",
            "type": "On-site", "owner": owner, "objective": "Keep the account linked",
        }

    def _account_ids(self, query: dict) -> set[str]:
        items, _, _, _ = list_accounts({"pageSize": "200", **query})
        return {item["id"] for item in items}

    def _refused(self, message: str, call, *args, **kwargs) -> None:
        with self.assertRaises(CrmApiException) as refused:
            call(*args, **kwargs)
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", message))

    def test_only_a_manager_archives_an_account_which_then_takes_no_change_and_no_new_record_and_is_restored_whole(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Archive Account"))
        # When and by whom it was archived, only while it is.
        self.assertFalse(account["archived"])
        self.assertNotIn("archivedAt", account)
        self.assertNotIn("archivedBy", account)
        site = create_site(account["id"], self._site_input("Archive Site"))
        contact = create_contact(self._contact_input(account["id"], "Archive Contact", siteId=site["id"]))
        twin = create_contact(self._contact_input(account["id"], "Archive Twin"))
        # What stays under the Account: a lost deal, an archived deal, an archived order and a planned Visit.
        lost = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Lost Deal"))
        lost = mark_opportunity_lost(lost["id"], {"lostReason": "No budget"}, lost["modified"])
        shelved = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Shelved Deal"))
        order = create_booking(self._upsell_input(account, contact, self.other_sales))
        # A cancelled order, which stays cancelled under the archived Account.
        spare = create_booking(self._upsell_input(account, contact, self.other_sales, equipment="Spare kit"))
        spare = update_booking(spare["id"], {"status": "Cancelled"}, spare["modified"])
        visit = create_visit(self._visit_input(account, self.other_sales, "Planned before the archive"))
        frappe.set_user(self.manager)
        archive_strategy_opportunity(shelved["id"])
        archive_booking(order["id"])

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            archive_account(account["id"])
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_archived"), 0)

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as missing:
            archive_account("ACC-MISSING-ARCHIVE")
        # ACCOUNT_NOT_FOUND is published as the NOT_FOUND contract code.
        self.assertEqual(missing.exception.code, "NOT_FOUND")
        archived = archive_account(account["id"])
        self.assertTrue(archived["archived"])
        self.assertEqual(archived["archivedBy"], self.manager)
        self.assertTrue(archived["archivedAt"])
        self.assertEqual(archived["name"], "Archive Account")
        self.assertNotEqual(archived["modified"], account["modified"])
        self.assertEqual(archive_account(account["id"])["modified"], archived["modified"])
        columns = frappe.db.get_value(
            "Customer", account["id"], ["custom_crm_archived", "custom_crm_archived_at", "custom_crm_archived_by"], as_dict=True,
        )
        self.assertEqual((columns.custom_crm_archived, columns.custom_crm_archived_by), (1, self.manager))
        self.assertTrue(columns.custom_crm_archived_at)
        comments = {"reference_doctype": "Customer", "reference_name": account["id"], "comment_type": "Info"}
        self.assertEqual(frappe.get_all("Comment", filters=comments, pluck="content"), ["Archived"])

        # Out of the list unless asked for, the pickers, the cockpit; its Sites and Contacts leave with it.
        self.assertNotIn(account["id"], self._account_ids({}))
        self.assertNotIn(account["id"], self._account_ids({"archiveState": "active"}))
        self.assertIn(account["id"], self._account_ids({"archiveState": "archived"}))
        self.assertIn(account["id"], self._account_ids({"archiveState": "all"}))
        with self.assertRaises(CrmApiException) as unknown:
            list_accounts({"archiveState": "gone"})
        self.assertEqual(unknown.exception.code, "VALIDATION_ERROR")
        self.assertNotIn(site["id"], {row["id"] for row in list_account_sites()})
        self.assertNotIn(contact["id"], {row["id"] for row in list_contacts({"pageSize": "200"})[0]})
        self.assertIn(contact["id"], {row["id"] for row in list_contacts({"accountId": account["id"]})[0]})
        self.assertNotIn(account["id"], {row["name"] for row in cockpit.options()[0]})
        # Still read whole, by id: the Account 360, its Sites, its Contacts (the Contact knows of the archive).
        detail = get_account_360(account["id"])
        self.assertTrue(detail["account"]["archived"])
        self.assertEqual({row["id"] for row in detail["sites"]}, {site["id"]})
        self.assertIn(contact["id"], {row["id"] for row in detail["contacts"]})
        self.assertTrue(get_contact(contact["id"])["accountArchived"])
        # The Contact page compares its reader with the Account's owner, which the Account list does not give for an
        # archived Account.
        self.assertEqual(get_contact(contact["id"])["accountOwner"], self.other_sales)
        self.assertFalse(get_contact(create_contact(self._contact_input(
            create_account(self._account_input("Archive Neighbour"))["id"], "Neighbour Contact",
        ))["id"])["accountArchived"])

        # No change to the Account, its Sites or its Contacts, with the current version, an older one or a bad payload.
        frappe.set_user(self.other_sales)
        payload = {**self._account_input("Archive Account"), "city": "苏州"}
        self._refused(ARCHIVED_ACCOUNT_EDIT, update_account, account["id"], payload, archived["modified"])
        self._refused(ARCHIVED_ACCOUNT_EDIT, update_account, account["id"], payload, account["modified"])
        self._refused(ARCHIVED_ACCOUNT_EDIT, update_account, account["id"], {}, archived["modified"])
        self._refused(ARCHIVED_ACCOUNT_LINK, create_site, account["id"], self._site_input("Archive Site Two"))
        self._refused(ARCHIVED_ACCOUNT_EDIT, update_site, account["id"], site["id"], self._site_input("Archive Site Renamed"))
        self._refused(ARCHIVED_ACCOUNT_EDIT, delete_site, account["id"], site["id"])
        self._refused(ARCHIVED_ACCOUNT_EDIT, update_contact, contact["id"], self._contact_input(account["id"], "Archive Contact Renamed"), contact["modified"])
        frappe.set_user(self.manager)
        # A Contact's archive and a merge are a Manager's (contact:delete, contact:merge).
        self._refused(ARCHIVED_ACCOUNT_EDIT, delete_contact, contact["id"])
        self._refused(ARCHIVED_ACCOUNT_EDIT, merge_contacts, contact["id"], twin["id"])
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_city"), "上海")
        self.assertEqual(frappe.db.get_value("Contact", contact["id"], "custom_crm_status"), "Active")
        self.assertEqual(frappe.db.get_value("Contact", twin["id"], "custom_crm_merged_into"), None)
        self.assertTrue(frappe.db.exists("Address", site["id"]))

        # Nothing new under it: a Contact, an Opportunity, a Booking, a Visit, a Demo Request, a Quotation; nothing
        # of another Account moved under it; none of its Contacts moved out.
        frappe.set_user(self.other_sales)
        self._refused(ARCHIVED_ACCOUNT_LINK, create_contact, self._contact_input(account["id"], "Archive Contact Late"))
        self._refused(ARCHIVED_ACCOUNT_LINK, create_strategy_opportunity, self._opportunity_input(account, site, self.other_sales, "Late Deal"))
        self._refused(ARCHIVED_ACCOUNT_LINK, create_booking, self._upsell_input(account, contact, self.other_sales))
        self._refused(ARCHIVED_ACCOUNT_LINK, create_visit, self._visit_input(account, self.other_sales, "Late visit"))
        self._refused(ARCHIVED_ACCOUNT_LINK, create_demo_request, {
            "accountId": account["id"], "primaryContactId": contact["id"], "opportunityId": lost["id"],
        })
        self._refused(ARCHIVED_ACCOUNT_LINK, create_quotation, {"opportunityId": lost["id"]})
        neighbour = create_account(self._account_input("Archive Mover"))
        neighbour_site = create_site(neighbour["id"], self._site_input("Archive Mover Site"))
        mover = create_contact(self._contact_input(neighbour["id"], "Archive Mover Contact"))
        mover_deal = create_strategy_opportunity(self._opportunity_input(neighbour, neighbour_site, self.other_sales, "Mover Deal"))
        mover_order = create_booking(self._upsell_input(neighbour, mover, self.other_sales))
        self._refused(ARCHIVED_ACCOUNT_LINK, update_contact, mover["id"], self._contact_input(account["id"], "Archive Mover Contact"), mover["modified"])
        self._refused(
            ARCHIVED_ACCOUNT_LINK, update_strategy_opportunity, mover_deal["id"],
            {"accountId": account["id"], "siteId": site["id"]}, mover_deal["modified"],
        )
        self._refused(
            ARCHIVED_ACCOUNT_LINK, update_booking, mover_order["id"],
            {"accountId": account["id"], "primaryContactId": contact["id"]}, mover_order["modified"],
        )
        self._refused(ARCHIVED_ACCOUNT_EDIT, update_contact, contact["id"], self._contact_input(neighbour["id"], "Archive Contact"), contact["modified"])
        self.assertEqual(frappe.db.count("CRM Opportunity", {"account": account["id"]}), 2)
        self.assertEqual(frappe.db.count("CRM Booking", {"account": account["id"]}), 2)
        self.assertEqual(frappe.db.count("CRM Visit", {"account": account["id"]}), 1)
        self.assertEqual(frappe.db.count("Dynamic Link", {"link_doctype": "Customer", "link_name": account["id"], "parenttype": "Contact"}), 2)

        # Nothing reopened or restored under it (a Manager's actions: a rollback, the restores); what it has goes on
        # under its own rules (the Visit happens).
        frappe.set_user(self.manager)
        self._refused(ARCHIVED_ACCOUNT_REOPEN, rollback_opportunity_stage, lost["id"], QUALIFIED_OPPORTUNITY, "Budget back", lost["modified"])
        self.assertEqual(frappe.db.get_value("CRM Opportunity", lost["id"], "stage"), lost["stage"])
        self._refused(ARCHIVED_ACCOUNT_REOPEN, unarchive_strategy_opportunity, shelved["id"])
        self._refused(ARCHIVED_ACCOUNT_REOPEN, unarchive_booking, order["id"])
        self.assertEqual(frappe.db.get_value("CRM Opportunity", shelved["id"], "archived"), 1)
        self.assertEqual(frappe.db.get_value("CRM Booking", order["id"], "archived"), 1)
        frappe.set_user(self.other_sales)
        # A cancelled order under it is not put back in progress; its details may still be corrected, and a closed
        # deal under it is edited as before.
        self._refused(ARCHIVED_ACCOUNT_REOPEN, update_booking, spare["id"], {"status": "Confirmed"}, spare["modified"])
        self._refused(ARCHIVED_ACCOUNT_REOPEN, update_booking, spare["id"], {"status": "Pending"}, spare["modified"])
        noted = update_booking(spare["id"], {"note": "Kept for the record"}, spare["modified"])
        self.assertEqual((noted["status"], noted["note"]), ("Cancelled", "Kept for the record"))
        renamed = update_strategy_opportunity(lost["id"], {"title": "Lost Deal, renamed"}, lost["modified"])
        self.assertEqual((renamed["title"], renamed["stage"]), ("Lost Deal, renamed", lost["stage"]))
        visited = update_visit(visit["id"], {"type": "advance", "status": "Visited", "outcome": "Met anyway"}, visit["modified"])
        self.assertEqual(visited["status"], "Visited")

        # Restored whole by a Manager: the columns cleared, the trace kept, the list and the writers back.
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            unarchive_account(account["id"])
        frappe.set_user(self.manager)
        restored = unarchive_account(account["id"])
        self.assertFalse(restored["archived"])
        self.assertNotIn("archivedAt", restored)
        self.assertNotIn("archivedBy", restored)
        self.assertEqual(restored["name"], "Archive Account")
        self.assertNotEqual(restored["modified"], archived["modified"])
        self.assertEqual(unarchive_account(account["id"])["modified"], restored["modified"])
        self.assertEqual(
            frappe.db.get_value("Customer", account["id"], ["custom_crm_archived", "custom_crm_archived_at", "custom_crm_archived_by"]),
            (0, None, None),
        )
        self.assertEqual(frappe.get_all("Comment", filters=comments, pluck="content", order_by="creation asc"), ["Archived", "Restored from the archive"])
        self.assertIn(account["id"], self._account_ids({}))
        self.assertNotIn(account["id"], self._account_ids({"archiveState": "archived"}))
        self.assertIn(site["id"], {row["id"] for row in list_account_sites()})
        self.assertIn(contact["id"], {row["id"] for row in list_contacts({"pageSize": "200"})[0]})
        self.assertFalse(get_contact(contact["id"])["accountArchived"])
        self.assertFalse(unarchive_strategy_opportunity(shelved["id"])["archived"])
        frappe.set_user(self.other_sales)
        self.assertEqual(update_account(account["id"], payload, restored["modified"])["city"], "苏州")
        self.assertEqual(create_contact(self._contact_input(account["id"], "Archive Contact Late"))["accountId"], account["id"])

    def test_the_archive_reads_an_accounts_rows_through_its_index(self):
        """The archive locks the rows it reads: through the Account's index, its own rows only, not the tables. The
        DocTypes declare the index, so Frappe's schema sync makes it (named as Frappe names it) and keeps it (it drops
        an index a field does not declare); there is one."""

        for doctype, query, values in (
            ("CRM Opportunity", account_service.open_opportunity_query(), ("ACC-INDEX-PLAN", *OPEN_STAGES)),
            ("CRM Booking", account_service.live_booking_query(), ("ACC-INDEX-PLAN",)),
        ):
            self.assertTrue(frappe.get_meta(doctype).get_field("account").search_index, doctype)
            columns: dict[str, list[str]] = {}
            for row in frappe.db.sql(f"SHOW INDEX FROM `tab{doctype}`", as_dict=True):
                columns.setdefault(row.Key_name, []).append(row.Column_name)
            on_account = [name for name, names in columns.items() if names == ["account"]]
            self.assertEqual(len(on_account), 1, (doctype, on_account))
            plan = frappe.db.sql(f"EXPLAIN {query}", values, as_dict=True)
            self.assertEqual(plan[0]["key"], on_account[0], query)

    def test_the_lookup_indexes_are_made_after_a_migrate_only_when_their_column_has_none(self):
        import inspect

        # On this site each column has its index: no second one (and no statement that changes the schema).
        with patch.object(frappe.db, "add_index") as add_index:
            indexes.install_lookup_indexes()
        add_index.assert_not_called()
        # On a site where Frappe's sync made none: made under the name the sync gives one.
        with patch.object(frappe.db, "get_column_index", return_value=None), patch.object(frappe.db, "add_index") as add_index:
            indexes.install_lookup_indexes()
        self.assertEqual(
            [call.args for call in add_index.call_args_list],
            [
                ("CRM Opportunity", ["account"], "account_index"), ("CRM Booking", ["account"], "account_index"),
                ("CRM Quotation Approval", ["quotation"], "quotation_index"),
            ],
        )
        # Run after every migrate (and the install), with the app's other indexes: a statement of the function's own
        # body, under no condition, with nothing before it that could leave the function.
        import ast
        import textwrap

        body = ast.parse(textwrap.dedent(inspect.getsource(indexes.install_stage5f_indexes))).body[0].body
        calls = [
            index for index, node in enumerate(body)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name) and node.value.func.id == "install_lookup_indexes"
        ]
        self.assertEqual(len(calls), 1, calls)
        self.assertFalse([node for statement in body[:calls[0]] for node in ast.walk(statement) if isinstance(node, (ast.Return, ast.Raise))])

    def test_an_account_with_an_open_opportunity_or_a_booking_in_progress_is_archived_only_once_they_are_closed(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Busy Account"))
        site = create_site(account["id"], self._site_input("Busy Site"))
        contact = create_contact(self._contact_input(account["id"], "Busy Contact"))
        deal = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Busy Deal"))

        frappe.set_user(self.manager)
        self._refused(ACCOUNT_WITH_OPEN_OPPORTUNITY_ARCHIVE, archive_account, account["id"])
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_archived"), 0)
        # An Opportunity archived on its own is not open; a Booking in progress (confirmed or pending) is.
        archive_strategy_opportunity(deal["id"])
        frappe.set_user(self.other_sales)
        order = create_booking(self._upsell_input(account, contact, self.other_sales))
        pending = create_booking(self._upsell_input(account, contact, self.other_sales, status="Pending"))
        frappe.set_user(self.manager)
        self._refused(ACCOUNT_WITH_LIVE_BOOKING_ARCHIVE, archive_account, account["id"])
        frappe.set_user(self.other_sales)
        update_booking(order["id"], {"status": "Cancelled"}, order["modified"])
        frappe.set_user(self.manager)
        self._refused(ACCOUNT_WITH_LIVE_BOOKING_ARCHIVE, archive_account, account["id"])
        frappe.set_user(self.other_sales)
        update_booking(pending["id"], {"status": "Cancelled"}, pending["modified"])
        frappe.set_user(self.manager)
        self.assertTrue(archive_account(account["id"])["archived"])
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_archived"), 1)
        self.assertEqual(frappe.db.get_value("CRM Opportunity", deal["id"], "archived"), 1)
        self.assertEqual(frappe.db.get_value("CRM Booking", order["id"], "status"), "Cancelled")

    def test_a_closed_deal_or_order_under_an_archived_account_is_neither_reopened_nor_moved_out(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Closed Account"))
        site = create_site(account["id"], self._site_input("Closed Site"))
        contact = create_contact(self._contact_input(account["id"], "Closed Contact", siteId=site["id"]))
        order_draft = {
            "primaryContactId": contact["id"], "equipment": "Inspection 3000", "quantity": 1, "ddl": "2027-01-31",
            "amount": "200000.00", "currency": "CNY", "owner": self.other_sales, "note": "PO",
        }
        # A won deal whose order was cancelled by hand (nothing open under the Account then), a lost deal, a cancelled
        # Upsell order.
        won = advance_opportunity_fixture(
            create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Won Deal")),
            "po_received", booking=order_draft,
        )
        live = get_booking(won["liveBooking"]["id"])
        update_booking(live["id"], {"status": "Cancelled"}, live["modified"])
        won = get_strategy_opportunity(won["id"])
        lost = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Lost Deal"))
        lost = mark_opportunity_lost(lost["id"], {"lostReason": "No budget"}, lost["modified"])
        spare = create_booking(self._upsell_input(account, contact, self.other_sales, equipment="Spare kit"))
        spare = update_booking(spare["id"], {"status": "Cancelled"}, spare["modified"])
        other = create_account(self._account_input("Closed Neighbour"))
        other_site = create_site(other["id"], self._site_input("Closed Neighbour Site"))
        other_contact = create_contact(self._contact_input(other["id"], "Closed Neighbour Contact"))
        frappe.set_user(self.manager)
        self.assertTrue(archive_account(account["id"])["archived"])

        # Nothing reopened under it: the won deal rolled back, a replacement order for it; nothing written.
        self._refused(ARCHIVED_ACCOUNT_REOPEN, rollback_opportunity_stage, won["id"], "quotation_sent", "Order lost", won["modified"])
        frappe.set_user(self.other_sales)
        self._refused(ARCHIVED_ACCOUNT_REOPEN, confirm_po, won["id"], {"booking": order_draft, "actualPoDate": "2026-10-01"}, won["modified"])
        self.assertEqual(frappe.db.get_value("CRM Opportunity", won["id"], "stage"), "po_received")
        self.assertEqual(frappe.db.count("CRM Booking", {"source_opportunity": won["id"]}), 1)
        # Nothing moved out (to be reopened under the other Account); nothing written.
        self._refused(
            ARCHIVED_ACCOUNT_EDIT, update_strategy_opportunity, lost["id"],
            {"accountId": other["id"], "siteId": other_site["id"]}, lost["modified"],
        )
        self._refused(
            ARCHIVED_ACCOUNT_EDIT, update_booking, spare["id"],
            {"accountId": other["id"], "primaryContactId": other_contact["id"], "status": "Confirmed"}, spare["modified"],
        )
        self.assertEqual(frappe.db.get_value("CRM Opportunity", lost["id"], "account"), account["id"])
        self.assertEqual(frappe.db.get_value("CRM Booking", spare["id"], ["account", "status"]), (account["id"], "Cancelled"))

    def test_an_account_out_of_reach_answers_a_move_as_one_that_does_not_exist_archived_or_not(self):
        frappe.set_user(self.other_sales)
        hidden = create_account(self._account_input("Hidden Archived Account"))
        frappe.set_user(self.manager)
        archive_account(hidden["id"])
        frappe.set_user(self.sales)
        own = create_account(self._account_input("Own Order Account"))
        own_contact = create_contact(self._contact_input(own["id"], "Own Order Contact"))
        order = create_booking(self._upsell_input(own, own_contact, self.sales))

        def refusal(account_id: str) -> tuple[str, str]:
            with self.assertRaises(CrmApiException) as refused:
                update_booking(order["id"], {"accountId": account_id, "primaryContactId": own_contact["id"]}, order["modified"])
            return refused.exception.code, refused.exception.public_message

        # Another user's private Account, archived, answers as one that is not there: the archive is not told.
        self.assertEqual(refusal(hidden["id"]), refusal("ACC-NOBODY-MOVE"))
        self.assertEqual(frappe.db.get_value("CRM Booking", order["id"], "account"), own["id"])

    def test_an_account_with_a_demo_request_or_a_demo_test_in_progress_is_archived_only_once_they_have_ended(self):
        engineer = self._user("crm-account-contact-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Demo Work Account"))
        site = create_site(account["id"], self._site_input("Demo Work Site"))
        # A deal lost while its Demo Request was still in review: nothing open under the Account but the demo work.
        deal = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Demo Work Deal"))
        mark_opportunity_lost(deal["id"], {"lostReason": "Moved on"}, deal["modified"])
        frappe.set_user("Administrator")
        request = frappe.get_doc({
            "doctype": "CRM Demo Request", "request_mode": "Opportunity", "account": account["id"],
            "opportunity": deal["id"], "sales_owner": self.other_sales, "created_by_user": self.other_sales,
            "title": "Demo work", "objective": "Show the recipe", "requested_equipment": "Inspection Tool",
            "sample_type": "Wafer", "sample_quantity": 1, "target_date": "2026-12-20",
            "customer_expected_date": "2026-12-15", "priority": "Medium", "acceptance_criteria": "Clean wafers",
            "status": "Engineer Review", "engineer_owner": engineer, "form_data": "{}",
        }).insert(ignore_permissions=True)
        frappe.set_user(self.manager)
        self._refused(ACCOUNT_WITH_DEMO_REQUEST_ARCHIVE, archive_account, account["id"])
        # Approved, the request has ended and its demo test runs: the archive waits for the test.
        frappe.db.set_value("CRM Demo Request", request.name, "status", "Converted")
        test = frappe.get_doc({
            "doctype": "CRM Evaluation", "demo_request": request.name, "account": account["id"], "title": "Demo work test",
            "status": "Scheduled", "evaluation_owner": engineer, "planned_end": "2026-12-20",
            "wafer_preparation_status": "Pending", "test_preparation_status": "Pending", "acceptance": "Pending",
            "report_status": "Not Ready",
        }).insert(ignore_permissions=True)
        self._refused(ACCOUNT_WITH_DEMO_TEST_ARCHIVE, archive_account, account["id"])
        self.assertEqual(frappe.db.get_value("Customer", account["id"], "custom_crm_archived"), 0)
        frappe.db.set_value("CRM Evaluation", test.name, "status", "Rejected")
        self.assertTrue(archive_account(account["id"])["archived"])

    def _demo_request(self, account_id: str, opportunity_id: str | None, engineer: str, title: str):
        frappe.set_user("Administrator")
        try:
            return frappe.get_doc({
                "doctype": "CRM Demo Request", "request_mode": "Opportunity" if opportunity_id else "Self Test",
                "account": account_id, "opportunity": opportunity_id, "sales_owner": self.other_sales,
                "created_by_user": self.other_sales, "title": title, "objective": "Show the recipe",
                "requested_equipment": "Inspection Tool", "sample_type": "Wafer", "sample_quantity": 1,
                "target_date": "2026-12-20", "customer_expected_date": "2026-12-15", "priority": "Medium",
                "acceptance_criteria": "Clean wafers", "status": "Engineer Review", "engineer_owner": engineer, "form_data": "{}",
            }).insert(ignore_permissions=True)
        finally:
            frappe.set_user(self.other_sales)

    def test_an_accounts_demo_work_is_that_of_its_deals_now_and_its_own_without_a_deal(self):
        engineer = self._user("crm-account-contact-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.other_sales)
        first = create_account(self._account_input("Demo Move From"))
        first_site = create_site(first["id"], self._site_input("Demo Move From Site"))
        second = create_account(self._account_input("Demo Move To"))
        second_site = create_site(second["id"], self._site_input("Demo Move To Site"))
        deal = create_strategy_opportunity(self._opportunity_input(first, first_site, self.other_sales, "Demo Move Deal"))
        self._demo_request(first["id"], deal["id"], engineer, "Demo of a moved deal")
        # The deal moves to the second Account (its Demo Request keeps the customer it was started for), then is lost.
        deal = update_strategy_opportunity(deal["id"], {"accountId": second["id"], "siteId": second_site["id"]}, deal["modified"])
        mark_opportunity_lost(deal["id"], {"lostReason": "Moved on"}, deal["modified"])

        frappe.set_user(self.manager)
        # The work is the second Account's now: its archive waits for it; the first one's does not.
        self._refused(ACCOUNT_WITH_DEMO_REQUEST_ARCHIVE, archive_account, second["id"])
        self.assertTrue(archive_account(first["id"])["archived"])

        # A Demo Request without a deal (a self test) is its own Account's.
        frappe.set_user(self.other_sales)
        own = create_account(self._account_input("Demo Self Test"))
        self._demo_request(own["id"], None, engineer, "Self test")
        frappe.set_user(self.manager)
        self._refused(ACCOUNT_WITH_DEMO_REQUEST_ARCHIVE, archive_account, own["id"])

    def test_a_deal_moved_to_another_account_takes_both_rows_exclusively_from_the_start(self):
        frappe.set_user(self.other_sales)
        first = create_account(self._account_input("Exclusive Move From"))
        first_site = create_site(first["id"], self._site_input("Exclusive Move From Site"))
        second = create_account(self._account_input("Exclusive Move To"))
        second_site = create_site(second["id"], self._site_input("Exclusive Move To Site"))
        deal = create_strategy_opportunity(self._opportunity_input(first, first_site, self.other_sales, "Exclusive Move Deal"))
        real_sql = frappe.db.sql
        locks: list[str] = []

        def watch(query, *args, **kwargs):
            text = str(query)
            if "`tabCustomer`" in text and ("FOR UPDATE" in text or "LOCK IN SHARE MODE" in text):
                locks.append("shared" if "LOCK IN SHARE MODE" in text else "exclusive")
            return real_sql(query, *args, **kwargs)

        with patch.object(frappe.db, "sql", side_effect=watch):
            moved = update_strategy_opportunity(deal["id"], {"accountId": second["id"], "siteId": second_site["id"]}, deal["modified"])
        self.assertEqual(moved["accountId"], second["id"])
        # The edit's write scope (opportunity_status._lock_write_scope) takes its Account's row exclusively: the move
        # takes both rows so from the start, never one shared before (two moves out of one Account would each wait for
        # the other to raise it).
        self.assertTrue(locks)
        self.assertEqual(locks[0], "exclusive", locks)
        self.assertNotIn("shared", locks)

    def test_the_accounts_locked_are_matched_as_the_database_matches_their_names(self):
        # The database matches a name without regard to accents or width as well as case: an Account named by such a
        # variant (renamed so since a caller's snapshot named it) answers with its own flag, under either lock.
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input(f"Müller Lock（{frappe.generate_hash(length=6)}）"))
        frappe.set_user(self.manager)
        archive_account(account["id"])
        variant = account["id"].replace("ü", "u").replace("（", "(").replace("）", ")")
        self.assertNotEqual(variant.casefold(), account["id"].casefold())
        self.assertEqual(account_service.lock_accounts((variant,)), {variant: True})
        self.assertEqual(account_service.lock_accounts((variant,), for_update=True), {variant: True})
        self.assertEqual(account_service.lock_accounts((account["id"].upper(),)), {account["id"].upper(): True})
        # Two spellings of the record in one call read its flag each; a name that matches no record is not archived.
        missing = f"No Such Account {frappe.generate_hash(length=6)}"
        locked = account_service.lock_accounts((account["id"], variant, missing))
        self.assertEqual(locked, {account["id"]: True, variant: True, missing: False})

    def test_a_quotation_answers_to_its_deals_account_now(self):
        frappe.set_user(self.other_sales)
        first = create_account(self._account_input("Quotation Move From"))
        first_site = create_site(first["id"], self._site_input("Quotation Move From Site"))
        second = create_account(self._account_input("Quotation Move To"))
        second_site = create_site(second["id"], self._site_input("Quotation Move To Site"))
        elsewhere = create_account(self._account_input("Quotation Move Elsewhere"))
        deal = create_strategy_opportunity(self._opportunity_input(first, first_site, self.other_sales, "Quotation Move Deal"))
        created = create_quotation({"opportunityId": deal["id"]})
        quotation_id, version = created["quotation"]["id"], created["version"]
        payload = {key: version[key] for key in ("primaryContactId", "addressId", "quoteDate", "validityMonths", "items")}
        # The deal moves to the second Account and takes its Quotation along (which keeps the customer it was
        # addressed to), then is lost.
        deal = update_strategy_opportunity(deal["id"], {"accountId": second["id"], "siteId": second_site["id"]}, deal["modified"])
        mark_opportunity_lost(deal["id"], {"lostReason": "Moved on"}, deal["modified"])

        # The first Account archived: the Quotation is not its any more, and takes its writes.
        frappe.set_user(self.manager)
        archive_account(first["id"])
        frappe.set_user(self.other_sales)
        self.assertFalse(get_quotation(quotation_id)["quotation"]["accountArchived"])
        version = save_draft(quotation_id, payload, version["modified"])["version"]
        # A first read that has the deal under an Account it has left since: refused as changed under the deal's lock.
        with patch.object(quotation_service, "_quotation_account", return_value=elsewhere["id"]):
            with self.assertRaises(CrmApiException) as changed:
                save_draft(quotation_id, payload, version["modified"])
        self.assertEqual(changed.exception.code, "VERSION_CONFLICT")
        # The second one archived: frozen with it.
        frappe.set_user(self.manager)
        archive_account(second["id"])
        frappe.set_user(self.other_sales)
        self.assertTrue(get_quotation(quotation_id)["quotation"]["accountArchived"])
        self._refused(ARCHIVED_ACCOUNT_EDIT, save_draft, quotation_id, payload, version["modified"])

    def test_no_quotation_is_linked_to_a_deal_of_an_archived_account(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Link Archived Account"))
        site = create_site(account["id"], self._site_input("Link Archived Site"))
        deal = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Link Archived Deal"))
        mark_opportunity_lost(deal["id"], {"lostReason": "No budget"}, deal["modified"])
        quotation = create_quotation({"accountId": account["id"]})
        frappe.set_user(self.manager)
        archive_account(account["id"])

        frappe.set_user(self.other_sales)
        self._refused(
            ARCHIVED_ACCOUNT_LINK, link_quotation_opportunity,
            quotation["quotation"]["id"], deal["id"], quotation["version"]["modified"],
        )
        self.assertFalse(frappe.db.get_value("CRM Quotation", quotation["quotation"]["id"], "opportunity"))

    def test_an_internal_validation_is_not_approved_into_a_booking_under_an_archived_account(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Validation Account"))
        site = create_site(account["id"], self._site_input("Validation Site"))
        contact = create_contact(self._contact_input(account["id"], "Validation Contact", siteId=site["id"]))
        deal = advance_opportunity_fixture(
            create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Validation Deal")),
            "quotation_sent",
        )
        requested = request_internal_validation(deal["id"], {
            "reason": "Long lead time", "expectedPoDate": "2026-11-30",
            "booking": {
                "primaryContactId": contact["id"], "equipment": "Inspection 3000", "quantity": 1, "ddl": "2027-03-31",
                "amount": "880000", "currency": "cny", "owner": self.other_sales, "note": "Start before the PO",
            },
        }, deal["modified"])
        # Archived under it as no archive does (an open deal holds the archive off), as a snapshot may still say it
        # is not: the approval, which makes a Booking, is refused all the same.
        frappe.db.set_value("Customer", account["id"], "custom_crm_archived", 1)
        frappe.set_user(self.manager)
        self._refused(
            ARCHIVED_ACCOUNT_LINK, review_internal_validation, deal["id"],
            {"validationId": requested["internalValidation"]["id"], "decision": "approved"}, requested["modified"],
        )
        self.assertEqual(frappe.db.count("CRM Booking", {"source_opportunity": deal["id"]}), 0)
        self.assertEqual(frappe.db.get_value("CRM Opportunity Internal Validation", requested["internalValidation"]["id"], "status"), "pending")

    def test_a_restore_of_a_record_moved_since_its_first_read_is_refused_as_changed(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Restore Move Account"))
        site = create_site(account["id"], self._site_input("Restore Move Site"))
        contact = create_contact(self._contact_input(account["id"], "Restore Move Contact"))
        other = create_account(self._account_input("Restore Move Other"))
        deal = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Restore Move Deal"))
        order = create_booking(self._upsell_input(account, contact, self.other_sales))
        frappe.set_user(self.manager)
        archive_strategy_opportunity(deal["id"])
        archive_booking(order["id"])

        for service, restore, record, doctype in (
            (opportunity_service, unarchive_strategy_opportunity, deal, "CRM Opportunity"),
            (booking_service, unarchive_booking, order, "CRM Booking"),
        ):
            real = service.require_manager_scoped_document

            def first_read(doctype, name, *args, real=real, **kwargs):
                doc = real(doctype, name, *args, **kwargs)
                if not kwargs.get("for_update"):
                    doc.account = other["id"]  # the first read still has it under the other Account
                return doc

            with self.subTest(record=record["id"]):
                with patch.object(service, "require_manager_scoped_document", side_effect=first_read):
                    with self.assertRaises(CrmApiException) as changed:
                        restore(record["id"])
                self.assertEqual(changed.exception.code, "VERSION_CONFLICT")
                self.assertEqual(frappe.db.get_value(doctype, record["id"], "archived"), 1)

    def test_every_write_of_a_quotation_of_an_archived_account_waits_for_the_restore(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Quotation Account"))
        created = create_quotation({"accountId": account["id"]})
        quotation_id, version = created["quotation"]["id"], created["version"]
        self.assertFalse(created["quotation"]["accountArchived"])
        frappe.set_user(self.manager)
        archive_account(account["id"])

        # Frozen with its Account, and said so: no draft saved or discarded, no submission.
        frappe.set_user(self.other_sales)
        self.assertTrue(get_quotation(quotation_id)["quotation"]["accountArchived"])
        payload = {key: version[key] for key in ("primaryContactId", "addressId", "quoteDate", "validityMonths", "items")}
        self._refused(ARCHIVED_ACCOUNT_EDIT, save_draft, quotation_id, payload, version["modified"])
        self._refused(ARCHIVED_ACCOUNT_EDIT, discard_draft, quotation_id, version["modified"])
        self._refused(ARCHIVED_ACCOUNT_EDIT, submit_for_approval, quotation_id, version["modified"])
        self.assertTrue(frappe.db.exists("CRM Quotation", quotation_id))

        # Restored, it takes its writes again.
        frappe.set_user(self.manager)
        unarchive_account(account["id"])
        frappe.set_user(self.other_sales)
        self.assertFalse(get_quotation(quotation_id)["quotation"]["accountArchived"])
        self.assertTrue(discard_draft(quotation_id, version["modified"])["deleted"])

    def test_the_writers_of_an_accounts_contacts_and_sites_take_its_row_exclusively_from_the_start(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Exclusive Account"))
        real_sql = frappe.db.sql
        locks: list[str] = []

        def watch(query, *args, **kwargs):
            text = str(query)
            if "`tabCustomer`" in text and ("FOR UPDATE" in text or "LOCK IN SHARE MODE" in text):
                locks.append("shared" if "LOCK IN SHARE MODE" in text else "exclusive")
            return real_sql(query, *args, **kwargs)

        leaving = create_contact(self._contact_input(account["id"], "Exclusive Leaver"))

        def delete_as_manager():
            frappe.set_user(self.manager)
            try:
                return delete_contact(leaving["id"])
            finally:
                frappe.set_user(self.other_sales)

        # The Contact's and the Address's saves take the Account's row exclusively in their hooks: it is taken so from
        # the start, never held shared first (two such writers would each wait for the other to raise it).
        for write in (
            lambda: create_contact(self._contact_input(account["id"], "Exclusive Contact")),
            lambda: create_site(account["id"], self._site_input("Exclusive Site")),
            delete_as_manager,
        ):
            locks.clear()
            with patch.object(frappe.db, "sql", side_effect=watch):
                write()
            self.assertTrue(locks)
            self.assertEqual(locks[0], "exclusive", locks)
            self.assertNotIn("shared", locks)

    def test_a_status_record_takes_the_accounts_row_before_the_opportunitys(self):
        frappe.set_user(self.other_sales)
        account = create_account(self._account_input("Status Order Account"))
        site = create_site(account["id"], self._site_input("Status Order Site"))
        deal = create_strategy_opportunity(self._opportunity_input(account, site, self.other_sales, "Status Order Deal"))
        real_sql = frappe.db.sql
        order: list[str] = []

        def watch(query, *args, **kwargs):
            text = " ".join(str(query).split())
            if "FOR UPDATE" in text:
                order.append("opportunity" if "`tabCRM Opportunity`" in text else "account" if "`tabCustomer`" in text else "other")
            return real_sql(query, *args, **kwargs)

        # The order the Account's archive takes them in (the Account, then its Opportunities), so neither waits on the
        # other in a cycle.
        with patch.object(frappe.db, "sql", side_effect=watch):
            opportunity_status._lock_write_scope(deal["id"])
        self.assertEqual(order, ["account", "opportunity"])

        # Moved to another Account since the snapshot named its Account: refused as changed, the other Account's row
        # not taken after the Opportunity's (the reverse of the archive's order).
        other = create_account(self._account_input("Status Order Other"))
        real_get_value = frappe.db.get_value

        def snapshot(doctype, *args, **kwargs):
            if doctype == "CRM Opportunity" and args[:2] == (deal["id"], "account"):
                return other["id"]
            return real_get_value(doctype, *args, **kwargs)

        order.clear()
        with patch.object(frappe.db, "get_value", side_effect=snapshot), patch.object(frappe.db, "sql", side_effect=watch):
            with self.assertRaises(CrmApiException) as changed:
                opportunity_status._lock_write_scope(deal["id"])
        self.assertEqual(changed.exception.code, "VERSION_CONFLICT")
        self.assertEqual(order, ["account", "opportunity"])

    def test_a_contact_whose_account_is_gone_still_moves_to_another(self):
        frappe.set_user(self.other_sales)
        gone = create_account(self._account_input("Gone Account"))
        mover = create_contact(self._contact_input(gone["id"], "Gone Mover"))
        target = create_account(self._account_input("Gone Target"))
        frappe.db.sql("DELETE FROM `tabCustomer` WHERE `name` = %s", (gone["id"],))
        # A Contact left naming an Account that is not there: that Account's archive flag reads as not archived (it is
        # not asked for its read scope either), so the Contact still moves to an Account, as before the Account's
        # archive. (Its own archive fails in Frappe's Contact validation, which reads every linked record, as before.)
        frappe.set_user(self.manager)
        moved = update_contact(mover["id"], self._contact_input(target["id"], "Gone Mover"), mover["modified"])
        self.assertEqual(moved["accountId"], target["id"])

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

    def test_merging_a_contact_into_their_own_report_keeps_the_line_off_itself(self):
        frappe.set_user("Administrator")
        account = create_account(self._account_input("Merge Line Account", self.sales))
        top = create_contact(self._contact_input(account["id"], "Top", owner=self.sales))
        boss = create_contact(self._contact_input(account["id"], "Boss", owner=self.sales, reportsToContactId=top["id"]))
        staff = create_contact(self._contact_input(account["id"], "Staff", owner=self.sales, reportsToContactId=boss["id"]))
        peer = create_contact(self._contact_input(account["id"], "Peer", owner=self.sales, reportsToContactId=boss["id"]))

        # The Boss is merged into their own report: the Staff takes the Boss's line (the Top), the Peer reports
        # to the Staff, and nobody reports to themselves (F1-06).
        merged = merge_contacts(staff["id"], boss["id"])
        self.assertEqual(merged.get("reportsToContactId"), top["id"])
        self.assertEqual(frappe.db.get_value("Contact", peer["id"], "custom_crm_reports_to"), staff["id"])
        self.assertEqual(frappe.db.get_value("Contact", staff["id"], "custom_crm_reports_to"), top["id"])
        # The merged Boss keeps no line of their own: the Top's direct reports are the Staff, once, not the Boss too.
        self.assertIsNone(frappe.db.get_value("Contact", boss["id"], "custom_crm_reports_to"))
        self.assertEqual([item["id"] for item in get_contact(top["id"])["directReports"]], [staff["id"]])
        # The other way round (the report merged into their Boss), the Boss does not list the merged report.
        chief = create_contact(self._contact_input(account["id"], "Chief", owner=self.sales))
        aide = create_contact(self._contact_input(account["id"], "Aide", owner=self.sales, reportsToContactId=chief["id"]))
        self.assertNotIn("reportsToContactId", merge_contacts(chief["id"], aide["id"]))
        self.assertIsNone(frappe.db.get_value("Contact", aide["id"], "custom_crm_reports_to"))
        self.assertEqual(get_contact(chief["id"])["directReports"], [])
        # A Contact merged already is merged no more, either way; nor is one merged into an archived Contact.
        for survivor_id, duplicate_id in ((aide["id"], chief["id"]), (chief["id"], aide["id"])):
            with self.assertRaises(CrmApiException) as merged_already:
                merge_contacts(survivor_id, duplicate_id)
            self.assertEqual(merged_already.exception.code, "CONFLICT")
        gone = create_contact(self._contact_input(account["id"], "Gone", owner=self.sales))
        delete_contact(gone["id"])
        with self.assertRaises(CrmApiException) as archived:
            merge_contacts(gone["id"], peer["id"])
        self.assertEqual(archived.exception.code, "CONFLICT")
        self.assertEqual(frappe.db.get_value("Contact", peer["id"], "custom_crm_status"), "Active")

        # A Boss without a line of their own leaves their report without one.
        lone = create_contact(self._contact_input(account["id"], "Lone Boss", owner=self.sales))
        junior = create_contact(self._contact_input(account["id"], "Junior", owner=self.sales, reportsToContactId=lone["id"]))
        self.assertNotIn("reportsToContactId", merge_contacts(junior["id"], lone["id"]))

        # The top of a three-deep line merged into its bottom would close a loop: refused, nothing changes.
        head = create_contact(self._contact_input(account["id"], "Line Head", owner=self.sales))
        middle = create_contact(self._contact_input(account["id"], "Line Middle", owner=self.sales, reportsToContactId=head["id"]))
        bottom = create_contact(self._contact_input(account["id"], "Line Bottom", owner=self.sales, reportsToContactId=middle["id"]))
        with self.assertRaises(CrmApiException) as loop:
            merge_contacts(bottom["id"], head["id"])
        self.assertEqual(loop.exception.code, "VALIDATION_ERROR")
        self.assertEqual(frappe.db.get_value("Contact", head["id"], "custom_crm_status"), "Active")
        self.assertEqual(frappe.db.get_value("Contact", middle["id"], "custom_crm_reports_to"), head["id"])
        self.assertEqual(frappe.db.get_value("Contact", bottom["id"], "custom_crm_reports_to"), middle["id"])
        self.assertEqual(
            frappe.db.sql("SELECT `name` FROM `tabContact` WHERE `custom_crm_reports_to` = `name`"), (),
        )

    def test_an_account_named_like_one_the_user_sees_is_refused_until_confirmed(self):
        frappe.set_user(self.sales)
        first = create_account(self._account_input("Dup Name Co"))
        # The same name in another case and spacing is refused with the ids the user may look at; confirmed as
        # another company, the Account is created (ERPNext suffixes its id). The short name, an alias that the
        # companies of a group share, is not compared.
        with self.assertRaises(CrmApiException) as taken:
            create_account(self._account_input(" dup name co "))
        self.assertEqual(
            (taken.exception.code, taken.exception.public_message, taken.exception.field_errors),
            ("CONFLICT", "An Account with this name exists already.", {"name": first["id"]}),
        )
        self.assertEqual(frappe.db.count("Customer", {"custom_crm_short_name": first["shortName"]}), 1)
        alias = create_account({**self._account_input("Dup Name Sister Co"), "shortName": first["shortName"]})
        self.assertEqual(alias["shortName"], first["shortName"])
        confirmed = create_account({**self._account_input("dup name co"), "confirmDuplicate": True})
        self.assertNotEqual(confirmed["id"], first["id"])
        self.assertEqual(confirmed["name"], "dup name co")
        with self.assertRaises(CrmApiException) as both:
            create_account(self._account_input("Dup Name Co"))
        self.assertEqual(both.exception.field_errors, {"name": ", ".join(sorted([first["id"], confirmed["id"]]))})

        # An Account out of the user's reach (someone else's Private one) is not compared: nothing tells of it.
        frappe.set_user(self.other_sales)
        create_account(self._account_input("Hidden Name Co"))
        frappe.set_user(self.sales)
        self.assertEqual(create_account(self._account_input("Hidden Name Co"))["name"], "Hidden Name Co")

        # A rename to a name in use is refused the same way until confirmed; an edit that keeps the name is not.
        other = create_account(self._account_input("Rename Me Co"))
        renamed = self._account_input("Dup Name Co")
        with self.assertRaises(CrmApiException) as rename:
            update_account(other["id"], renamed, other["modified"])
        self.assertEqual(rename.exception.code, "CONFLICT")
        updated = update_account(other["id"], {**self._account_input("Rename Me Co"), "city": "苏州"}, other["modified"])
        self.assertEqual(updated["city"], "苏州")
        confirmed_rename = update_account(other["id"], {**renamed, "confirmDuplicate": True}, updated["modified"])
        self.assertEqual(confirmed_rename["name"], "Dup Name Co")
