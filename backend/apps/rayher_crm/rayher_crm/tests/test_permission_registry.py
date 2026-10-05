from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import frappe
from frappe.permissions import add_permission, update_permission_property
from frappe.tests.utils import FrappeTestCase

from rayher_crm import hooks
from rayher_crm.permissions import registry
from rayher_crm.permissions.scope import DOCPERMS_BY_DOCTYPE, install_crm_doc_permissions


class TestPermissionRegistry(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.original_user)
        frappe.clear_cache()
        super().tearDown()

    def test_migration_installed_permissions_match_registered_native_boundaries(self):
        # Check the actual migrated site before invoking the installer in this test.
        registry.validate_permission_registry()
        install_crm_doc_permissions()
        install_crm_doc_permissions()
        registry.validate_permission_registry()

    def test_new_object_requires_an_explicit_policy(self):
        documents = registry.definitions()
        documents["CRM Unreviewed Report"] = {
            "doctype": "DocType", "name": "CRM Unreviewed Report", "permissions": [],
        }
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            registry.validate_source_registry(documents=documents)

    def test_registered_app_doctype_needs_no_crm_prefix(self):
        documents = registry.definitions()
        documents["Sales Territory Plan"] = {
            "doctype": "DocType", "name": "Sales Territory Plan", "permissions": [],
        }
        policies = (
            *registry.POLICIES,
            registry.Policy("Sales Territory Plan", "service_only", "Manager territory plan", ("accounts",)),
        )
        registry.validate_source_registry(documents=documents, policies=policies)

    def test_a_second_app_module_cannot_escape_the_inventory(self):
        # Both inventories and the module-keyed DocShare guards cover one module.
        with self.assertRaisesRegex(ValueError, "single Rayher CRM module"):
            registry.validate_source_registry(modules=["Rayher CRM", "CRM Territory"])
        original_get_all = frappe.get_all

        def with_second_module(doctype, *args, **kwargs):
            rows = original_get_all(doctype, *args, **kwargs)
            return [*rows, "CRM Territory"] if doctype == "Module Def" else rows

        with patch.object(frappe, "get_all", side_effect=with_second_module):
            with self.assertRaisesRegex(ValueError, "single Rayher CRM module"):
                registry.validate_permission_registry()

    def test_changed_child_table_boundary_fails_the_gate(self):
        for name, istable in (("CRM Demo Comment", 1), ("CRM Quotation Item", 0)):
            documents = deepcopy(registry.definitions())
            documents[name]["istable"] = istable
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "child-table boundary"):
                registry.validate_source_registry(documents=documents)

    def test_fresh_install_flag_still_checks_actual_custom_permissions(self):
        original_flag = frappe.flags.in_install
        filters = {
            "parent": "CRM Demo Comment", "role": "CRM Sales", "permlevel": 0, "if_owner": 0,
        }
        original_write = frappe.db.get_value("Custom DocPerm", filters, "write")
        try:
            frappe.flags.in_install = "rayher_crm"
            registry.validate_permission_registry()
            frappe.db.set_value("Custom DocPerm", filters, "write", 1)
            with self.assertRaisesRegex(ValueError, "Installed permissions differ"):
                registry.validate_permission_registry()
        finally:
            frappe.db.set_value("Custom DocPerm", filters, "write", original_write)
            frappe.clear_cache(doctype="CRM Demo Comment")
            frappe.flags.in_install = original_flag

    def test_assignment_exception_does_not_allow_engineer_native_writes(self):
        assignment = DOCPERMS_BY_DOCTYPE["CRM Account Engineer Assignment"]
        with patch.dict(assignment, {"CRM Engineer": {"read", "write"}}):
            with patch("rayher_crm.permissions.scope.add_permission") as add_permission_row, patch(
                "rayher_crm.permissions.scope.update_permission_property"
            ) as update_permission_row:
                with self.assertRaisesRegex(ValueError, "standard document API"):
                    install_crm_doc_permissions()
                add_permission_row.assert_not_called()
                update_permission_row.assert_not_called()
            with self.assertRaisesRegex(ValueError, "Unregistered native write exception"):
                registry.validate_permission_registry(installed=False)

    def test_duplicate_policy_or_hook_keys_cannot_silently_replace_a_guard(self):
        with self.assertRaisesRegex(ValueError, "Duplicate native policy"):
            registry.policy_map((*registry.POLICIES, registry.POLICIES[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate dictionary key"):
            registry.assert_no_duplicate_keys(
                'doc_events = {"DocShare": {"validate": "scope"}, "DocShare": {"validate": "file"}}',
                "hooks.py",
            )

    def test_tuple_keys_and_list_shaped_json_cannot_break_or_bypass_the_gate(self):
        with self.assertRaisesRegex(ValueError, "Duplicate dictionary key"):
            registry.assert_no_duplicate_keys(
                'ALLOWED = {("All", 0, 1): {"write"}, ("All", 0, 1): {"write", "create"}}', "scope.py",
            )
        registry.assert_no_duplicate_keys('OK = {("All", 0, 1): 1, ("All", 0, 0): 2, name: 3}', "scope.py")
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "rayher_crm" / "doctype" / "crm_sample"
            folder.mkdir(parents=True)
            (folder / "test_records.json").write_text(json.dumps([{"doctype": "CRM Sample", "title": "x"}]), encoding="utf-8")
            (folder / "crm_sample.json").write_text(json.dumps({"doctype": "DocType", "name": "CRM Sample"}), encoding="utf-8")
            self.assertEqual(set(registry.definitions(Path(tmp))), {"CRM Sample"})

    def test_erp_owned_child_relationship_changes_do_not_abort_a_migration(self):
        from rayher_crm.permissions.scope import SCOPED_CHILD_RELATIONSHIPS

        child = "Dynamic Link"
        real = registry.installed_child_relationships

        def with_extra(extra=(), drop=()):
            def fake(name):
                found = set(real(name))
                if name == child:
                    found |= set(extra)
                    found -= set(drop)
                return found
            return fake

        # An ERP admin's Custom Field on an ERP DocType, or an ERP-owned pair that disappeared.
        erp_parent = ("Sales Order", "crm_test_links")
        registered = sorted(SCOPED_CHILD_RELATIONSHIPS[child])
        erp_registered = next(item for item in registered if frappe.db.get_value("DocType", item[0], "module") != registry.APP_MODULE)
        with patch.object(registry, "installed_child_relationships", with_extra(extra=[erp_parent], drop=[erp_registered])):
            registry.validate_permission_registry()
        # The same change on a CRM-owned DocType is this release's decision and fails the gate.
        with patch.object(registry, "installed_child_relationships", with_extra(extra=[("CRM Opportunity", "links")])):
            with self.assertRaisesRegex(ValueError, "Installed child relationships differ.*crm_owned"):
                registry.validate_permission_registry()

    def test_unregistered_site_custom_object_is_detected(self):
        original_get_all = frappe.get_all

        def with_custom_object(doctype, *args, **kwargs):
            rows = original_get_all(doctype, *args, **kwargs)
            if doctype == "DocType" and kwargs.get("filters") == {"module": "Rayher CRM"}:
                return [*rows, "CRM Unregistered Site Report"]
            return rows

        with patch.object(frappe, "get_all", side_effect=with_custom_object):
            with self.assertRaisesRegex(ValueError, "Installed CRM DocType inventory"):
                registry.validate_permission_registry()

    def test_removing_or_swapping_a_native_scope_hook_fails_the_gate(self):
        for key in ("CRM Demo Comment", "CRM Notification Event", "Address", "File"):
            for attribute in ("query_hooks", "detail_hooks"):
                values = dict(hooks.permission_query_conditions if attribute == "query_hooks" else hooks.has_permission)
                values.pop(key)
                with self.assertRaisesRegex(ValueError, "scope hook"):
                    registry.validate_source_registry(**{attribute: values})
        for key in ("Contact Email", "CRM Quotation Item"):
            query_hooks = dict(hooks.permission_query_conditions)
            query_hooks.pop(key)
            with self.assertRaisesRegex(ValueError, "scope hook"):
                registry.validate_source_registry(query_hooks=query_hooks)
            self.assertNotIn(key, hooks.has_permission)
        with patch.dict(hooks.doc_events, {"DocShare": {"validate": "rayher_crm.services.managed_file_access.protect_share"}}):
            with self.assertRaisesRegex(ValueError, "Both managed-file"):
                registry.validate_source_registry()
        for endpoint in (
            "frappe.desk.search.search_link",
            "frappe.desk.search.search_widget",
        ):
            values = dict(hooks.override_whitelisted_methods)
            values.pop(endpoint)
            with patch.object(hooks, "override_whitelisted_methods", values):
                with self.assertRaisesRegex(ValueError, "Scoped search override"):
                    registry.validate_source_registry()

    def test_removing_or_swapping_a_document_guard_fails_the_gate(self):
        # These write guards run outside the permission hooks; losing one silently
        # reopens a share, file provenance or private upload path.
        guards = (
            ("Customer", "before_save"), ("Contact", "before_save"), ("Lead", "before_save"),
            ("Address", "before_save"), ("User", "before_save"),
            ("File", "before_insert"), ("File", "before_validate"),
        )
        for doctype, event in guards:
            events = {key: value for key, value in hooks.doc_events[doctype].items() if key != event}
            for replacement in (events, {**events, event: "other_app.hooks.allow"}):
                with self.subTest(doctype=doctype, event=event, replacement=replacement), patch.dict(
                    hooks.doc_events, {doctype: replacement},
                ):
                    with self.assertRaisesRegex(ValueError, "Required document guard"):
                        registry.validate_source_registry()
        with patch.object(hooks, "delete_file_data_content", "other_app.files.delete_content"):
            with self.assertRaisesRegex(ValueError, "file content deletion"):
                registry.validate_source_registry()

    @staticmethod
    def _site_hooks(hook_name, merge):
        original = frappe.get_hooks

        def get_hooks(hook=None, default="_KEEP_DEFAULT_LIST", app_name=None):
            values = original(hook, default, app_name)
            return merge(values) if hook == hook_name and not app_name else values

        return patch.object(frappe, "get_hooks", get_hooks)

    def test_a_later_app_cannot_supersede_the_effective_crm_hooks(self):
        # Frappe merges every installed app's hooks. The last app's detail hook and
        # every "*" detail hook run first, the last class or method override wins,
        # and the first file content deletion hook wins.
        later = "later_app.permissions.allow_everything"
        search = "frappe.desk.search.search_link"
        cases = (
            ("permission_query_conditions", lambda values: {**values, "CRM Visit": [*values.get("CRM Visit", []), later]}),
            ("permission_query_conditions", lambda values: {**values, "*": [later]}),
            ("permission_query_conditions", lambda values: {**values, "File": list(reversed(values.get("File", [])))}),
            ("permission_query_conditions", lambda values: {**values, "Contact": [hooks.permission_query_conditions["Contact"]]}),
            ("has_permission", lambda values: {**values, "CRM Visit": [*values.get("CRM Visit", []), later]}),
            ("has_permission", lambda values: {**values, "*": [*values.get("*", []), later]}),
            ("override_whitelisted_methods", lambda values: {**values, search: [*values.get(search, []), later]}),
            ("override_doctype_class", lambda values: {**values, "File": [*values.get("File", []), later]}),
            ("delete_file_data_content", lambda values: ["earlier_app.files.delete_content", *values]),
        )
        for hook_name, merge in cases:
            with self.subTest(hook=hook_name, merged=merge({})), self._site_hooks(hook_name, merge):
                with self.assertRaisesRegex(ValueError, f"Effective site hook differs.*{hook_name}"):
                    registry.validate_permission_registry()

    def test_permission_query_scripts_require_explicit_review(self):
        path = "frappe.core.doctype.server_script.server_script_utils.get_server_script_map"
        for doctype in ("CRM Visit", "File", "Contact"):
            with self.subTest(doctype=doctype), patch(path, return_value={
                "permission_query": {doctype: "Unreviewed list rule"},
            }):
                with self.assertRaisesRegex(ValueError, "Unregistered Permission Query Server Script"):
                    registry.validate_site_hooks()
        # Unrelated ERP scripts remain outside this app's inventory.
        with patch(path, return_value={"permission_query": {"Sales Invoice": "ERP rule"}}):
            registry.validate_site_hooks()

    def test_restoring_a_native_write_in_json_is_detected(self):
        for permission in ("write", "import"):
            documents = deepcopy(registry.definitions())
            documents["CRM Demo Request"]["permissions"][0][permission] = 1
            with self.subTest(permission=permission), patch.object(registry, "definitions", return_value=documents):
                with self.assertRaisesRegex(ValueError, "JSON permissions exceed policy"):
                    registry.validate_permission_registry(installed=False)

    def test_installed_custom_permission_drift_is_detected_and_reconciled(self):
        for permission in ("write", "import"):
            update_permission_property("CRM Demo Comment", "CRM Sales", 0, permission, 1, validate=False)
            with self.subTest(permission=permission), self.assertRaisesRegex(
                ValueError, f"Installed permissions differ from policy: CRM Demo Comment: .*CRM Sales.*{permission}",
            ):
                registry.validate_permission_registry()
            install_crm_doc_permissions()
            registry.validate_permission_registry()

        # Assignment is an explicit Manager Desk exception. Old Custom DocPerm
        # rows must not mask the current schema or grant sharing to Engineer.
        update_permission_property("CRM Account Engineer Assignment", "CRM Manager", 0, "write", 0, validate=False)
        with self.assertRaisesRegex(ValueError, "Installed permissions differ"):
            registry.validate_permission_registry()
        install_crm_doc_permissions()
        registry.validate_permission_registry()
        manager_rows = [row for row in frappe.get_meta("CRM Account Engineer Assignment").permissions
                        if row.role == "CRM Manager" and not row.if_owner and not row.permlevel]
        self.assertEqual(len(manager_rows), 1)
        self.assertTrue(manager_rows[0].write)
        self.assertFalse(manager_rows[0].share)

        # An old Engineer share grant is drift too, and migration removes it.
        update_permission_property("CRM Account Engineer Assignment", "CRM Engineer", 0, "share", 1, validate=False)
        with self.assertRaisesRegex(ValueError, "Installed permissions differ from policy: CRM Account Engineer Assignment"):
            registry.validate_permission_registry()
        install_crm_doc_permissions()
        registry.validate_permission_registry()
        engineer_rows = [row for row in frappe.get_meta("CRM Account Engineer Assignment", cached=False).permissions
                         if row.role == "CRM Engineer" and not row.if_owner and not row.permlevel]
        self.assertEqual([(row.read, row.share) for row in engineer_rows], [(1, 0)])

    def test_shared_erp_address_grants_survive_registry_reconciliation(self):
        # A custom ERP grant is an ERP decision: the gate neither flags nor resets it.
        sales_user = {"parent": "Address", "role": "Sales User", "permlevel": 0, "if_owner": 0}
        original_delete = frappe.db.get_value("Custom DocPerm", sales_user, "delete")
        self.assertIsNotNone(original_delete)
        try:
            update_permission_property("Address", "Sales User", 0, "delete", 1, validate=False)
            frappe.clear_cache(doctype="Address")
            before = registry.permission_grants([
                row for row in frappe.get_meta("Address", cached=False).permissions
                if row.role not in registry.CRM_ROLES
            ])
            self.assertIn("delete", before[("Sales User", 0, 0)])
            install_crm_doc_permissions()
            registry.validate_permission_registry()
            after = registry.permission_grants([
                row for row in frappe.get_meta("Address", cached=False).permissions
                if row.role not in registry.CRM_ROLES
            ])
            self.assertEqual(before, after)
        finally:
            update_permission_property("Address", "Sales User", 0, "delete", original_delete, validate=False)
            frappe.clear_cache(doctype="Address")

    def test_implicit_roles_cannot_regain_native_mutations_on_shared_erp_objects(self):
        # Frappe gives every CRM user All and Guest, and every Desk user Desk User.
        added = [{"parent": "Contact", "role": role, "permlevel": 0, "if_owner": 0} for role in ("All", "Desk User")]
        try:
            add_permission("Contact", "All", 0)
            update_permission_property("Contact", "All", 0, "write", 1, validate=False)
            with self.assertRaisesRegex(ValueError, "Implicit role .*Contact.*All.*write"):
                registry.validate_permission_registry()
            # The installer strips All mutations from Customer, Contact and Lead again. The extra
            # level-0 All row that add_permission created still grants an unrestricted read/export,
            # which the gate reports as drift too; remove the row itself.
            install_crm_doc_permissions()
            with self.assertRaisesRegex(ValueError, "Implicit role .*unrestricted read.*Contact.*All"):
                registry.validate_permission_registry()
            frappe.db.delete("Custom DocPerm", added[0])
            frappe.clear_cache(doctype="Contact")
            registry.validate_permission_registry()

            add_permission("Contact", "Desk User", 0)
            update_permission_property("Contact", "Desk User", 0, "create", 1, validate=False)
            with self.assertRaisesRegex(ValueError, "Implicit role .*Contact.*Desk User.*create"):
                registry.validate_permission_registry()
            frappe.db.delete("Custom DocPerm", added[1])

            # Address keeps only Frappe's shipped owner-only All create/write row.
            update_permission_property("Address", "All", 0, "delete", 1, validate=False, if_owner=1)
            with self.assertRaisesRegex(ValueError, "Implicit role .*Address.*All.*delete"):
                registry.validate_permission_registry()
        finally:
            for filters in added:
                frappe.db.delete("Custom DocPerm", filters)
            update_permission_property("Address", "All", 0, "delete", 0, validate=False, if_owner=1)
            for doctype in ("Contact", "Address"):
                frappe.clear_cache(doctype=doctype)
        registry.validate_permission_registry()

    def test_implicit_roles_cannot_read_shared_erp_objects_without_the_owner_boundary(self):
        # Address is scoped by the CRM hooks only for CRM roles; a level-0 All read that is not
        # owner-only would open every CRM site to every signed-in user.
        added = {"parent": "Address", "role": "All", "permlevel": 0, "if_owner": 0}
        try:
            add_permission("Address", "All", 0)
            update_permission_property("Address", "All", 0, "read", 1, validate=False)
            with self.assertRaisesRegex(ValueError, "Implicit role .*unrestricted read.*Address.*All.*read"):
                registry.validate_permission_registry()
        finally:
            frappe.db.delete("Custom DocPerm", added)
            frappe.clear_cache(doctype="Address")
        # Frappe's shipped rows (owner-only All read/write/create, Lead's level-1 Desk User read) stay valid.
        registry.validate_permission_registry()

    def test_duplicate_erp_rows_on_shared_objects_are_left_to_erp(self):
        duplicate = frappe.get_doc({
            "doctype": "Custom DocPerm", "parent": "Address", "parenttype": "DocType",
            "parentfield": "permissions", "role": "Sales User", "permlevel": 0, "read": 1,
        }).insert()
        try:
            registry.validate_permission_registry()
        finally:
            frappe.db.delete("Custom DocPerm", {"name": duplicate.name})
            frappe.clear_cache(doctype="Address")
