from __future__ import annotations

import frappe
from frappe.permissions import get_doctypes_with_read
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.bootstrap import _personnel_directory
from rayher_crm.api import search as crm_search
from rayher_crm.permissions.scope import CONDITION_DOCTYPES
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contact_files import download_contact_file, list_contact_files, upload_contact_files
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.sites import create_site
from rayher_crm.setup.controlled_documents import ACONCA_DOCUMENT_ID
from rayher_crm.tests._controlled_document_fixtures import install_test_controlled_documents
from rayher_crm.tests.test_contact_file_api import pdf


class Scanner:
    def scan(self, content: bytes) -> bool:
        return True


class TestNativeLists(FrappeTestCase):
    """What /api/resource/File and /api/resource/User list to a CRM user."""

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.owner = self._user("crm-native-list-owner@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-native-list-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-native-list-engineer@example.invalid", "CRM Engineer")
        self.manager = self._user("crm-native-list-manager@example.invalid", "CRM Manager")
        self.system_manager = self._user("crm-native-list-admin@example.invalid", "System Manager")
        # An ERPNext user who is not a CRM user, and one who is both.
        self.erp_user = self._user("crm-native-list-erp@example.invalid", "Sales User")
        self.dual_user = self._user("crm-native-list-dual@example.invalid", "CRM Sales")
        dual = frappe.get_doc("User", self.dual_user)
        if "Sales User" not in {row.role for row in dual.roles}:
            dual.append("roles", {"role": "Sales User"})
            dual.save(ignore_permissions=True)
        frappe.set_user(self.owner)
        suffix = frappe.generate_hash(length=12)
        self.account = create_account({
            "name": f"Native List Account {suffix}", "shortName": "Native", "segment": "Frontend", "tier": "A",
            "city": "Shanghai", "region": "East", "owner": self.owner, "visibility": "Private",
        })
        self.contact = create_contact({
            "accountId": self.account["id"], "name": f"Native List Contact {suffix}", "title": "Director",
            "department": "Engineering", "phone": "13800000001", "email": "native.list@example.invalid",
            "relationship": "Developing", "owner": self.owner, "status": "Active",
        })
        self.upload = pdf("native-list-roadmap.pdf", marker=frappe.generate_hash(length=12))
        self.contact_file = upload_contact_files(
            self.contact["id"],
            [self.upload],
            scanner=Scanner(),
        )[0]

    def tearDown(self):
        frappe.set_user(self.original_user)
        frappe.clear_cache()
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _file(self, name: str, **fields) -> str:
        return frappe.get_doc({
            "doctype": "File", "file_name": name, "is_private": 1, "content": name.encode(), **fields,
        }).insert(ignore_permissions=True).name

    def _listed_files(self, user: str) -> list[dict]:
        frappe.set_user(user)
        return frappe.get_list(
            "File", fields=["name", "file_name", "attached_to_doctype", "attached_to_name"], limit_page_length=0,
        )

    def test_private_file_list_combines_scoped_service_and_ordinary_parent_rules(self):
        frappe.set_user("Administrator")
        crm_file = frappe.db.get_value("CRM Contact File", self.contact_file["id"], "private_file")
        self.assertEqual(
            frappe.db.get_value("File", crm_file, ["attached_to_doctype", "is_private"]), ("CRM Contact File", 1),
        )
        # Ordinary Desk attachments and a valid controlled-document service file.
        frappe.set_user(self.owner)
        site = create_site(self.account["id"], {"name": "Native List Fab", "city": "Shanghai", "type": "Fab", "process": "Frontend", "status": "量产"})
        frappe.set_user("Administrator")
        on_customer = self._file("native-list-on-customer.txt", attached_to_doctype="Customer", attached_to_name=self.account["id"])
        on_site = self._file("native-list-on-site.txt", attached_to_doctype="Address", attached_to_name=site["id"])
        install_test_controlled_documents()
        on_document = frappe.db.get_value("CRM Controlled Document", ACONCA_DOCUMENT_ID, "private_file")
        on_contact = self._file("native-list-on-contact.txt", attached_to_doctype="Contact", attached_to_name=self.contact["id"])
        on_lead = self._file("native-list-on-lead.txt", attached_to_doctype="Lead", attached_to_name="legacy-lead")
        self.assertNotIn("CRM Controlled Document", CONDITION_DOCTYPES)
        hidden_files = {on_customer, on_site, on_document, on_contact, on_lead}
        crm_files = {crm_file, *hidden_files}
        attached_to = {"CRM Contact File", "Customer", "Address", "CRM Controlled Document"}

        # Ordinary CRM parent attachments stay hidden even from an in-scope owner.
        # The service-backed Contact file keeps its current-scope native read path.
        for user in (self.other_sales, self.engineer, self.owner, self.manager):
            with self.subTest(user=user):
                listed = {row.name for row in self._listed_files(user)}
                self.assertTrue(attached_to.issubset(get_doctypes_with_read()))
                self.assertFalse(hidden_files & listed)
                self.assertEqual(crm_file in listed, user in (self.owner, self.manager))
                expected = [crm_file] if user in (self.owner, self.manager) else []
                self.assertEqual(frappe.get_list("File", filters={"name": ["in", sorted(crm_files)]}, pluck="name"), expected)
        # Nor does a user of the ERP who is not a CRM user, or a System Manager.
        for user in (self.erp_user, self.system_manager):
            with self.subTest(user=user):
                self.assertFalse(crm_files.intersection(row.name for row in self._listed_files(user)))
        self.assertTrue(crm_files.issubset(row.name for row in self._listed_files("Administrator")))

        # Link search cannot skip the filter by asking to ignore user permissions.
        frappe.set_user(self.other_sales)
        for ignore in (0, 1, "1"):
            with self.subTest(ignore=ignore):
                self.assertNotIn(crm_file, str(crm_search.search_widget(
                    "File", "native-list", searchfield="file_name", ignore_user_permissions=ignore,
                )))

        # The CRM's own endpoint still hands the file to whoever is in scope.
        frappe.set_user(self.owner)
        self.assertEqual([row["id"] for row in list_contact_files(self.contact["id"])], [self.contact_file["id"]])
        self.assertEqual(download_contact_file(self.contact_file["id"])["content"], self.upload["content"])

    def test_file_list_keeps_what_frappe_lists_outside_the_crm(self):
        # A user's own unattached upload, a file on a DocType the CRM does not own, and a file on an
        # Address that is not a CRM site: ordinary ERP data.
        frappe.set_user(self.other_sales)
        own_upload = self._file("native-list-own-upload.txt")
        frappe.set_user("Administrator")
        on_todo = self._file("native-list-on-todo.txt", attached_to_doctype="ToDo", attached_to_name="any")
        erp_address = frappe.get_doc({
            "doctype": "Address", "address_title": "Native List Supplier", "address_type": "Billing",
            "address_line1": "1 Supplier Road", "city": "Shanghai", "country": "China",
        }).insert(ignore_permissions=True).name
        on_erp_address = self._file("native-list-on-erp-address.txt", attached_to_doctype="Address", attached_to_name=erp_address)

        listed = {row.name for row in self._listed_files(self.other_sales)}
        self.assertIn(own_upload, listed)
        self.assertEqual(on_todo in listed, "ToDo" in get_doctypes_with_read())
        self.assertNotIn(own_upload, {row.name for row in self._listed_files(self.engineer)})

        listed = {row.name for row in self._listed_files(self.erp_user)}
        self.assertIn("Address", get_doctypes_with_read())
        self.assertIn(on_erp_address, listed)

    def test_user_list_shows_a_crm_user_only_themselves(self):
        frappe.set_user("Administrator")
        frappe.db.set_value("User", self.owner, {"last_ip": "203.0.113.7", "last_login": "2026-10-01 08:00:00"})
        everyone = {self.owner, self.other_sales, self.engineer, self.manager, self.system_manager}

        # A Sales user and an Engineer, and a Sales user who also holds an ERP role.
        for user in (self.other_sales, self.engineer, self.dual_user):
            with self.subTest(user=user):
                frappe.set_user(user)
                rows = frappe.get_list("User", fields=["name", "last_ip", "last_login"], limit_page_length=0)
                self.assertEqual([row.name for row in rows], [user])
                self.assertEqual(frappe.get_list("User", filters={"name": self.owner}, fields=["last_ip"]), [])
                self.assertEqual(frappe.db.count("User", {"name": ["in", sorted(everyone)]}), 5)
                self.assertEqual(len(frappe.get_list("User", filters={"name": ["in", sorted(everyone - {user})]})), 0)
                for ignore in (0, 1):
                    self.assertNotIn(self.owner, str(crm_search.search_widget(
                        "User", "crm-native-list", ignore_user_permissions=ignore,
                    )))

        # An address may contain %. It is compared as it is, in the list and in link search.
        frappe.set_user("Administrator")
        percent = self._user("crm-native-list%sales@example.invalid", "CRM Sales")
        self._user("crm-native-list%%sales@example.invalid", "CRM Sales")
        frappe.set_user(percent)
        self.assertEqual(frappe.get_list("User", pluck="name", limit_page_length=0), [percent])
        found = str(crm_search.search_widget("User", "crm-native-list", ignore_user_permissions=1))
        self.assertIn(percent, found)
        self.assertNotIn("crm-native-list%%sales@example.invalid", found)
        self.assertNotIn(self.owner, found)

        # A Manager assigns Engineers to Accounts in the Desk form of the assignment, and finds them
        # in its link field.
        frappe.set_user(self.manager)
        self.assertTrue(frappe.has_permission("CRM Account Engineer Assignment", "create"))
        self.assertEqual(frappe.get_meta("CRM Account Engineer Assignment").get_field("engineer").options, "User")
        self.assertIn(self.engineer, str(crm_search.search_link("User", "crm-native-list-engineer", reference_doctype="CRM Account Engineer Assignment")))
        self.assertIn(self.engineer, str(crm_search.search_widget("User", "crm-native-list-engineer", reference_doctype="CRM Account Engineer Assignment")))

        # Whoever administers the system keeps the whole list, and so do a Manager and a user of the
        # ERP who is not a CRM user: the CRM does not narrow what it does not own.
        for user in (self.system_manager, "Administrator", self.manager, self.erp_user):
            with self.subTest(user=user):
                frappe.set_user(user)
                rows = frappe.get_list("User", filters={"name": ["in", sorted(everyone)]}, fields=["name", "last_ip"], limit_page_length=0)
                self.assertEqual({row.name for row in rows}, everyone)
                self.assertEqual({row.last_ip for row in rows if row.name == self.owner}, {"203.0.113.7"})

        # The people the CRM shows come from its own directory, which is not narrowed.
        frappe.set_user(self.other_sales)
        directory = {person["id"] for person in _personnel_directory()}
        self.assertTrue({self.owner, self.other_sales, self.engineer, self.manager}.issubset(directory))

    def test_user_child_tables_show_a_crm_user_only_their_own_rows(self):
        """Frappe lists a child table on the parent's DocType-level read alone, which every desk user has
        for User (select, and the self-share). Without their own hook, Has Role and the other User child
        tables handed a Sales user every user's address and roles (#219)."""
        from frappe.client import get_list as client_get_list

        frappe.set_user("Administrator")
        everyone = {self.owner, self.other_sales, self.engineer, self.manager, self.system_manager}

        def child(doctype, parent, parentfield, **values):
            row = frappe.get_doc({"doctype": doctype, "parent": parent, "parenttype": "User", "parentfield": parentfield, **values})
            row.name = frappe.generate_hash(length=10)
            row.db_insert()
            return row.name

        owner_rows = {
            "DefaultValue": child("DefaultValue", self.owner, "defaults", defkey="company", defvalue="QIHENG Demo"),
            "User Email": child("User Email", self.owner, "user_emails", email_account="Native List Mailbox", email_id=self.owner),
            "User Social Login": child("User Social Login", self.owner, "social_logins", provider="frappe", username="native-list-owner"),
            "Block Module": child("Block Module", self.owner, "block_modules", module="Rayher CRM"),
        }
        own_default = child("DefaultValue", self.other_sales, "defaults", defkey="company", defvalue="QIHENG Demo")
        # A system default belongs to no user.
        frappe.defaults.set_global_default("crm_native_list_probe", frappe.generate_hash(length=8))

        def listed(doctype, *fields):
            return client_get_list(doctype, parent="User", fields=["name", "parent", "parenttype", *fields], limit_page_length=0)

        for user, role in ((self.other_sales, "CRM Sales"), (self.engineer, "CRM Engineer"), (self.dual_user, "CRM Sales")):
            with self.subTest(user=user):
                frappe.set_user(user)
                roles = listed("Has Role", "role")
                self.assertEqual({row["parent"] for row in roles if row["parenttype"] == "User"}, {user})
                self.assertIn(role, {row["role"] for row in roles})
                self.assertFalse((everyone - {user}) & {row["parent"] for row in roles})
                defaults = listed("DefaultValue", "defkey")
                self.assertEqual({row["name"] for row in defaults}, {own_default} if user == self.other_sales else set())
                # Frappe gives each user a social login row of their own; nobody else's row is listed.
                for doctype in ("User Email", "User Social Login", "Block Module"):
                    self.assertLessEqual({row["parent"] for row in listed(doctype)}, {user})

        # A Manager, a user of the ERP who is not a CRM user and a System Manager keep Frappe's list of
        # other users' rows; the system defaults are nobody's row.
        for user in (self.manager, self.erp_user, self.system_manager):
            with self.subTest(user=user):
                frappe.set_user(user)
                self.assertTrue(everyone <= {row["parent"] for row in listed("Has Role", "role")})
                defaults = listed("DefaultValue", "defkey")
                self.assertTrue({own_default, owner_rows["DefaultValue"]} <= {row["name"] for row in defaults})
                self.assertNotIn("__default", {row["parent"] for row in defaults})
                for doctype, name in owner_rows.items():
                    self.assertIn(name, {row["name"] for row in listed(doctype)})
        frappe.set_user("Administrator")
        self.assertIn("__default", {row["parent"] for row in listed("DefaultValue")})

    def test_public_ordinary_crm_attachments_remain_listed_and_searchable(self):
        frappe.set_user(self.owner)
        site = create_site(self.account["id"], {"name": "Public Native Fab", "city": "Shanghai", "type": "Fab", "process": "Frontend", "status": "量产"})
        frappe.set_user("Administrator")
        prefix = f"native-public-{frappe.generate_hash(length=10)}"
        public_files = {
            self._file(f"{prefix}-{doctype}.txt", is_private=0,
                       attached_to_doctype=doctype, attached_to_name=name)
            for doctype, name in (("Customer", self.account["id"]), ("Contact", self.contact["id"]),
                                 ("Lead", "legacy-lead"), ("Address", site["id"]))
        }
        # Other methods deliberately add native User Permissions to shared
        # fixtures. Use fresh identities to test Frappe's default public policy.
        for role in ("CRM Sales", "CRM Engineer", "CRM Manager", "Sales User"):
            with self.subTest(role=role):
                frappe.set_user("Administrator")
                user = self._user(f"native-public-{frappe.generate_hash(length=12)}@example.invalid", role)
                frappe.set_user(user)
                self.assertEqual(set(frappe.get_list("File", filters={"name": ["in", sorted(public_files)]}, pluck="name")), public_files)
                found = str(crm_search.search_widget("File", prefix, searchfield="file_name", ignore_user_permissions=1))
                for name in public_files:
                    self.assertIn(name, found)

    def test_ambiguous_crm_manager_roles_restrict_lists_and_foreign_shares(self):
        from rayher_crm.permissions.native_lists import reconcile_user_shares

        for additional_role in ("CRM Sales", "CRM Engineer"):
            with self.subTest(role=additional_role):
                frappe.set_user("Administrator")
                user = self._user(f"native-ambiguous-{frappe.generate_hash(length=12)}@example.invalid", "CRM Manager")
                doc = frappe.get_doc("User", user)
                doc.append("roles", {"role": "Sales User"})
                doc.save(ignore_permissions=True)
                old_grant = self._share("User", self.owner, user).name
                frappe.set_user(user)
                self.assertTrue(frappe.get_list("User", filters={"name": self.owner}))

                frappe.set_user("Administrator")
                doc.append("roles", {"role": additional_role})
                doc.save(ignore_permissions=True)
                self.assertFalse(frappe.db.exists("DocShare", old_grant))
                with self.assertRaises(frappe.PermissionError):
                    self._share("User", self.owner, user)
                frappe.set_user(user)
                self.assertEqual(frappe.get_list("User", pluck="name", limit_page_length=0), [user])

                frappe.set_user("Administrator")
                frappe.get_doc({"doctype": "User Permission", "user": user,
                                "allow": "User", "for_value": user}).insert(ignore_permissions=True)
                legacy = self._legacy_share("User", self.owner, user)
                reconcile_user_shares()
                self.assertFalse(frappe.db.exists("DocShare", legacy))
                self.assertTrue(frappe.db.exists("DocShare", {"share_doctype": "User", "share_name": user, "user": user}))
                frappe.set_user(user)
                self.assertEqual(frappe.get_list("User", pluck="name", limit_page_length=0), [user])

                # System Manager remains an explicit administrative exception.
                frappe.set_user("Administrator")
                doc.reload()
                doc.append("roles", {"role": "System Manager"})
                doc.save(ignore_permissions=True)
                self.assertTrue(self._share("User", self.owner, user))

    def test_both_hooks_are_registered_and_link_search_keeps_them(self):
        hooks = frappe.get_hooks("permission_query_conditions")
        self.assertEqual(hooks["File"], ["frappe.core.doctype.file.file.get_permission_query_conditions", "rayher_crm.services.managed_file_access.file_query"])
        self.assertEqual(hooks["User"][-1], "rayher_crm.permissions.native_lists.user_query")
        self.assertEqual(hooks["User"], ["frappe.core.doctype.user.user.get_permission_query_conditions", "rayher_crm.permissions.native_lists.user_query"])
        frappe.set_user(self.other_sales)
        # Exercise the public wrapper with an explicit query and a bypass flag.
        for search in (crm_search.search_widget, crm_search.search_link):
            self.assertNotIn(self.owner, str(search(
                "User", "crm-native-list-owner", query="frappe.core.doctype.user.user.user_query",
                ignore_user_permissions=1,
            )))

    def _share(self, doctype, name, user=None, everyone=0):
        from frappe.share import add_docshare

        return add_docshare(doctype, name, user=user, everyone=everyone, read=1,
                            flags={"ignore_share_permission": True})

    def _legacy_share(self, doctype, name, user=None, everyone=0):
        # Historical rows are installed directly to exercise the migration boundary.
        share = frappe.get_doc({
            "doctype": "DocShare", "name": frappe.generate_hash(length=12),
            "share_doctype": doctype, "share_name": name, "user": user,
            "everyone": everyone, "read": 1,
        })
        share.db_insert()
        return share.name

    def test_user_shares_keep_self_and_exempt_users_but_cannot_override_own_row(self):
        frappe.set_user("Administrator")
        for user in (self.other_sales, self.engineer, self.dual_user):
            with self.subTest(user=user), self.assertRaises(frappe.PermissionError):
                self._share("User", self.owner, user)
        with self.assertRaises(frappe.PermissionError):
            self._share("User", self.owner, everyone=1)
        for user in (self.manager, self.erp_user, self.system_manager, "Administrator"):
            self.assertTrue(self._share("User", self.owner, user))
        self.assertTrue(self._share("User", self.other_sales, self.other_sales))

    def test_migration_removes_foreign_user_shares_that_bypass_native_user_permissions(self):
        from rayher_crm.permissions.scope import install_crm_doc_permissions

        frappe.set_user("Administrator")
        frappe.get_doc({"doctype": "User Permission", "user": self.other_sales,
                        "allow": "User", "for_value": self.other_sales}).insert(ignore_permissions=True)
        foreign = self._legacy_share("User", self.owner, self.other_sales)
        everyone = self._legacy_share("User", self.engineer, everyone=1)
        erp = self._share("User", self.owner, self.erp_user).name
        own = frappe.db.get_value("DocShare", {"share_doctype": "User", "share_name": self.other_sales, "user": self.other_sales})
        frappe.set_user(self.other_sales)
        self.assertIn(self.owner, frappe.get_list("User", pluck="name"))
        frappe.set_user("Administrator")
        install_crm_doc_permissions()
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", foreign))
        self.assertFalse(frappe.db.exists("DocShare", everyone))
        self.assertTrue(frappe.db.exists("DocShare", erp))
        self.assertTrue(frappe.db.exists("DocShare", own))
        frappe.set_user(self.other_sales)
        self.assertEqual(frappe.get_list("User", pluck="name"), [self.other_sales])

    def test_user_role_transitions_revoke_foreign_shares_including_removed_exemptions(self):
        frappe.set_user("Administrator")
        for user, removed in ((self.erp_user, None), (self.manager, "CRM Manager"), (self.system_manager, "System Manager")):
            with self.subTest(user=user):
                share = self._share("User", self.owner, user).name
                doc = frappe.get_doc("User", user)
                original_roles = [row.role for row in doc.roles]
                try:
                    doc.append("roles", {"role": "CRM Sales"})
                    if removed:
                        doc.set("roles", [row for row in doc.roles if row.role != removed])
                    doc.save(ignore_permissions=True)
                    self.assertFalse(frappe.db.exists("DocShare", share))
                    self.assertTrue(frappe.db.exists("DocShare", {"share_doctype": "User", "share_name": user, "user": user}))
                finally:
                    doc.reload()
                    doc.set("roles", [{"role": role} for role in original_roles])
                    doc.save(ignore_permissions=True)

    def test_private_crm_file_shares_are_blocked_and_legacy_bypasses_are_removed(self):
        from rayher_crm.permissions.scope import install_crm_doc_permissions

        frappe.set_user("Administrator")
        target = self._file("native-list-share-target.txt", attached_to_doctype="Customer", attached_to_name=self.account["id"])
        ordinary = self._file("native-list-share-ordinary.txt")
        for user in (self.other_sales, self.owner, self.manager, self.erp_user):
            with self.subTest(user=user), self.assertRaises(frappe.PermissionError):
                self._share("File", target, user)
        with self.assertRaises(frappe.PermissionError):
            self._share("File", target, everyone=1)
        erp = self._share("File", ordinary, self.erp_user).name
        frappe.get_doc({"doctype": "User Permission", "user": self.other_sales,
                        "allow": "File", "for_value": ordinary}).insert(ignore_permissions=True)
        legacy = self._legacy_share("File", target, self.other_sales)
        frappe.set_user(self.other_sales)
        self.assertIn(target, frappe.get_list("File", pluck="name"))
        frappe.set_user("Administrator")
        install_crm_doc_permissions()
        self.assertFalse(frappe.db.exists("DocShare", legacy))
        self.assertTrue(frappe.db.exists("DocShare", erp))
        frappe.set_user(self.other_sales)
        self.assertNotIn(target, frappe.get_list("File", pluck="name"))

    def test_file_reparent_and_address_promotion_revoke_old_file_shares(self):
        frappe.set_user("Administrator")
        ordinary = self._file("native-list-reparent.txt")
        share = self._share("File", ordinary, self.other_sales).name
        doc = frappe.get_doc("File", ordinary)
        doc.attached_to_doctype = "Customer"
        doc.attached_to_name = self.account["id"]
        doc.save(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("DocShare", share))

        address = frappe.get_doc({
            "doctype": "Address", "address_title": "Native promotion", "address_type": "Billing",
            "address_line1": "1 Supplier Road", "city": "Shanghai", "country": "China",
        }).insert(ignore_permissions=True)
        file = self._file("native-list-promoted-site.txt", attached_to_doctype="Address", attached_to_name=address.name)
        share = self._share("File", file, self.erp_user).name
        address.append("links", {"link_doctype": "Customer", "link_name": self.account["id"]})
        address.save(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("DocShare", share))
        with self.assertRaises(frappe.PermissionError):
            self._share("File", file, self.erp_user)

    def test_customer_promotion_revokes_shares_of_its_address_files(self):
        frappe.set_user("Administrator")
        customer = frappe.get_doc({
            "doctype": "Customer", "customer_name": f"Native ERP {frappe.generate_hash(length=12)}",
            "customer_type": "Company", "customer_group": "CRM Customers",
            "territory": "CRM Territory", "custom_crm_owner": "Administrator",
        }).insert(ignore_permissions=True)
        frappe.db.set_value("Customer", customer.name, "customer_group", None, update_modified=False)
        address = frappe.get_doc({
            "doctype": "Address", "address_title": "Native ERP site", "address_type": "Billing",
            "address_line1": "1 Supplier Road", "city": "Shanghai", "country": "China",
            "links": [{"link_doctype": "Customer", "link_name": customer.name}],
        }).insert(ignore_permissions=True)
        file = self._file("native-list-customer-promotion.txt", attached_to_doctype="Address", attached_to_name=address.name)
        share = self._share("File", file, self.erp_user).name
        customer.reload()
        customer.customer_group = "CRM Customers"
        customer.save(ignore_permissions=True)
        self.assertFalse(frappe.db.exists("DocShare", share))

    def test_privatizing_a_deduplicated_sibling_revokes_only_crm_parent_shares(self):
        frappe.set_user("Administrator")
        content = frappe.generate_hash(length=40).encode()
        target = self._file("native-list-public-customer.txt", content=content, is_private=0,
                            attached_to_doctype="Customer", attached_to_name=self.account["id"])
        other = self._file("native-list-public-other.txt", content=content, is_private=0)
        target_doc = frappe.get_doc("File", target)
        other_doc = frappe.get_doc("File", other)
        self.assertEqual(target_doc.file_url, other_doc.file_url)
        crm_share = self._share("File", target, self.other_sales).name
        erp_share = self._share("File", other, self.erp_user).name
        frappe.get_doc({"doctype": "User Permission", "user": self.other_sales,
                        "allow": "File", "for_value": other}).insert(ignore_permissions=True)
        other_doc.is_private = 1
        other_doc.save(ignore_permissions=True)
        target_doc.reload()
        self.assertEqual(target_doc.is_private, 1)
        self.assertFalse(frappe.db.exists("DocShare", crm_share))
        self.assertTrue(frappe.db.exists("DocShare", erp_share))
        frappe.set_user(self.other_sales)
        self.assertEqual(frappe.get_list("File", filters={"name": target}, pluck="name"), [])


class TestNativeShareConcurrency(FrappeTestCase):
    def test_existing_share_edits_retry_when_file_or_recipient_is_locked(self):
        """Existing DocShare.save locks its grant before the boundary hook runs."""
        from frappe.share import add_docshare

        self.assertTrue(frappe.local.site.endswith(".test"))
        original_user = frappe.session.user
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=12)
        recipient = frappe.get_doc({
            "doctype": "User", "email": f"native-share-race-{suffix}@example.invalid",
            "first_name": "Native sharing concurrency", "send_welcome_email": 0,
            "roles": [{"role": "Sales User"}],
        }).insert(ignore_permissions=True).name
        file = frappe.get_doc({
            "doctype": "File", "file_name": f"native-share-race-{suffix}.txt",
            "content": suffix, "is_private": 1,
        }).insert(ignore_permissions=True).name
        file_share = add_docshare("File", file, user=recipient, read=1,
                                 flags={"ignore_share_permission": True}).name
        user_share = add_docshare("User", "Administrator", user=recipient, read=1,
                                 flags={"ignore_share_permission": True}).name
        primary = frappe.local.db
        primary.commit()
        try:
            with self.secondary_connection():
                frappe.db.sql("SET SESSION innodb_lock_wait_timeout=1")
                frappe.db.rollback()
            frappe.local.db = primary
            for doctype, name, share in (("File", file, file_share), ("User", recipient, user_share)):
                with self.subTest(doctype=doctype):
                    frappe.db.sql(f"SELECT name FROM `tab{doctype}` WHERE name=%s FOR UPDATE", (name,))
                    with self.secondary_connection():
                        grant = frappe.get_doc("DocShare", share)
                        grant.write = 1
                        with self.assertRaisesRegex(frappe.PermissionError, "Please retry"):
                            grant.save(ignore_permissions=True)
                        frappe.db.rollback()
                    primary.rollback()
                    with self.secondary_connection():
                        grant = frappe.get_doc("DocShare", share)
                        grant.write = 1
                        grant.save(ignore_permissions=True)
                        frappe.db.commit()
                    self.assertEqual(frappe.db.get_value("DocShare", share, "write"), 1)
                    primary.rollback()
        finally:
            if self._secondary_connection:
                self._secondary_connection.rollback()
            frappe.local.db = primary
            primary.rollback()
            frappe.db.delete("DocShare", {"name": ("in", (file_share, user_share))})
            frappe.delete_doc("File", file, ignore_permissions=True)
            frappe.delete_doc("User", recipient, ignore_permissions=True)
            primary.commit()
            frappe.set_user(original_user)
            frappe.clear_cache()
