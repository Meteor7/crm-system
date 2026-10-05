from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.permissions.scope import conditions_for_doctype


class TestStage5FSchema(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_private_file_metadata_doctypes_have_exact_server_owned_fields(self):
        contact_file = frappe.get_meta("CRM Contact File")
        artifact = frappe.get_meta("CRM Demo Artifact")

        self.assertEqual(contact_file.autoname, "format:CRM-CF-{#####}")
        self.assertEqual(artifact.autoname, "format:CRM-ART-{#####}")
        self.assertEqual((contact_file.get_field("contact").fieldtype, contact_file.get_field("contact").options), ("Link", "Contact"))
        self.assertEqual((contact_file.get_field("account").fieldtype, contact_file.get_field("account").options), ("Link", "Customer"))
        self.assertEqual((contact_file.get_field("private_file").fieldtype, contact_file.get_field("private_file").options), ("Link", "File"))
        self.assertTrue(contact_file.get_field("private_file").unique)
        self.assertEqual((contact_file.get_field("uploaded_by").fieldtype, contact_file.get_field("uploaded_by").options), ("Link", "User"))
        self.assertEqual(contact_file.get_field("uploaded_at").fieldtype, "Datetime")
        self.assertEqual(contact_file.get_field("size_bytes").fieldtype, "Int")
        self.assertEqual(contact_file.get_field("content_hash").fieldtype, "Data")

        self.assertEqual((artifact.get_field("demo_request").fieldtype, artifact.get_field("demo_request").options), ("Link", "CRM Demo Request"))
        self.assertEqual((artifact.get_field("evaluation").fieldtype, artifact.get_field("evaluation").options), ("Link", "CRM Evaluation"))
        self.assertEqual((artifact.get_field("private_file").fieldtype, artifact.get_field("private_file").options), ("Link", "File"))
        self.assertTrue(artifact.get_field("private_file").unique)
        self.assertEqual(
            artifact.get_field("artifact_type").options,
            "Demo Request DOCX\nTest Report\nCustomer Report",
        )
        self.assertEqual(artifact.get_field("visibility").options, "Internal\nCustomer Review")
        self.assertEqual(artifact.get_field("artifact_version").fieldtype, "Int")
        self.assertEqual(artifact.get_field("test_round").fieldtype, "Int")
        test_run = frappe.get_meta("CRM Test Run")
        self.assertEqual((test_run.get_field("test_round").fieldtype, test_run.get_field("test_round").default), ("Int", "1"))
        self.assertEqual((artifact.get_field("created_by_user").fieldtype, artifact.get_field("created_by_user").options), ("Link", "User"))
        self.assertEqual(artifact.get_field("canonical_hash").fieldtype, "Data")

    def test_access_audit_and_notification_are_server_named_and_append_safe(self):
        audit = frappe.get_meta("CRM File Access Audit")
        notification = frappe.get_meta("CRM Notification Event")

        self.assertEqual(audit.autoname, "hash")
        self.assertEqual((audit.get_field("actor").fieldtype, audit.get_field("actor").options), ("Link", "User"))
        self.assertEqual(audit.get_field("outcome").options, "Allowed\nDenied")
        self.assertEqual(audit.get_field("at").fieldtype, "Datetime")
        audit_permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in audit.permissions}
        self.assertIn(("CRM Manager", 1, 0, 0, 0), audit_permissions)

        self.assertEqual(notification.autoname, "format:CRM-NOT-{#####}")
        self.assertEqual((notification.get_field("actor").fieldtype, notification.get_field("actor").options), ("Link", "User"))
        self.assertEqual((notification.get_field("recipient_user").fieldtype, notification.get_field("recipient_user").options), ("Link", "User"))
        self.assertEqual(notification.get_field("created_at").fieldtype, "Datetime")
        self.assertEqual(notification.get_field("read_at").fieldtype, "Datetime")
        self.assertEqual((notification.get_field("source_name").fieldtype, notification.get_field("source_name").options), ("Dynamic Link", "source_doctype"))
        notification_permissions = {(row.role, row.read, row.write, row.create, row.delete) for row in notification.permissions}
        self.assertIn(("CRM Sales", 1, 0, 0, 0), notification_permissions)
        self.assertIn(("CRM Engineer", 1, 0, 0, 0), notification_permissions)

    def test_artifact_composite_unique_index_exists(self):
        rows = frappe.db.sql(
            """
            SELECT `INDEX_NAME` AS `index_name`, GROUP_CONCAT(`COLUMN_NAME` ORDER BY `SEQ_IN_INDEX`) AS `columns`
            FROM `information_schema`.`STATISTICS`
            WHERE `TABLE_SCHEMA` = DATABASE() AND `TABLE_NAME` = 'tabCRM Demo Artifact'
              AND `NON_UNIQUE` = 0
            GROUP BY `INDEX_NAME`
            """,
            as_dict=True,
        )
        indexes = {row.index_name: row.columns for row in rows}
        self.assertEqual(indexes.get("unique_evaluation_artifact_version"), "evaluation,artifact_type,artifact_version,visibility")

    def test_file_content_hash_index_survives_file_schema_sync(self):
        from frappe.database.mariadb.schema import MariaDBTable
        from rayher_crm.patches.v1_0 import add_file_content_hash_index
        from rayher_crm.setup.indexes import install_stage5f_indexes

        # Fresh installs and migrations create the index with these flags set,
        # when core add_index does not declare it on the DocField.
        for entry_point, flag in (
            (install_stage5f_indexes, "in_install"),
            (add_file_content_hash_index.execute, "in_migrate"),
        ):
            with self.subTest(entry_point=entry_point.__module__):
                frappe.db.delete("Property Setter", {
                    "doc_type": "File", "field_name": "content_hash", "property": "search_index",
                })
                frappe.clear_cache(doctype="File")
                previous = frappe.flags.get(flag)
                frappe.flags[flag] = True
                try:
                    entry_point()
                finally:
                    frappe.flags[flag] = previous
                self.assertTrue(frappe.db.has_index("tabFile", add_file_content_hash_index.INDEX_NAME))
                # frappe.db.updatedb("File") runs this plan after any Custom
                # Field, Customize Form or core File DocType change. Build it
                # without executing DDL.
                table = MariaDBTable("File")
                table.setup_table_columns()
                for column in table.columns.values():
                    column.build_for_alter_table(table.current_columns.get(column.fieldname.lower()))
                self.assertNotIn("content_hash", {column.fieldname for column in table.drop_index})
                self.assertEqual(f"{table.columns['content_hash'].fieldname}_index",
                    add_file_content_hash_index.INDEX_NAME)

    def test_stage5f_scope_is_fail_closed_and_recipient_specific(self):
        sales = "stage5f-schema-sales@example.invalid"
        manager = "stage5f-schema-manager@example.invalid"
        if not frappe.db.exists("User", sales):
            frappe.get_doc({
                "doctype": "User", "email": sales, "first_name": "Stage5F Schema Sales",
                "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "CRM Sales"}],
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("User", manager):
            frappe.get_doc({
                "doctype": "User", "email": manager, "first_name": "Stage5F Schema Manager",
                "enabled": 1, "send_welcome_email": 0, "roles": [{"role": "CRM Manager"}],
            }).insert(ignore_permissions=True)
        self.assertIn("tabCRM Contact File", conditions_for_doctype("CRM Contact File", sales))
        self.assertIn("tabCRM Demo Artifact", conditions_for_doctype("CRM Demo Artifact", sales))
        self.assertIn("recipient_user", conditions_for_doctype("CRM Notification Event", sales))
        self.assertNotEqual(conditions_for_doctype("CRM Notification Event", sales), "1=1")
        self.assertIn(manager, conditions_for_doctype("CRM Notification Event", manager))
        self.assertNotEqual(conditions_for_doctype("CRM Notification Event", manager), "1=1")
        self.assertEqual(conditions_for_doctype("CRM Notification Event", "Guest"), "1=0")
