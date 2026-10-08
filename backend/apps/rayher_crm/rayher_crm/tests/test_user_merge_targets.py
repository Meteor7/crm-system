"""Native identity maintenance cannot create ambiguous target business keys."""
import frappe
from frappe.model.rename_doc import rename_doc
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services import cockpit
from rayher_crm.services.common import to_iso_timestamp
from rayher_crm.tests import test_opportunity_relations as relation_fixtures


class TestUserMergeTargets(FrappeTestCase):
    _user = relation_fixtures.TestOpportunityRelations._user

    def setUp(self):
        super().setUp()
        self.assertTrue(frappe.local.site.endswith(".test"))
        self.original_user = frappe.session.user
        self.primary = frappe.local.db
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=10)
        self.source = self._user(f"merge-target-{token}-source@example.invalid", "CRM Sales")
        self.destination = self._user(f"merge-target-{token}-destination@example.invalid", "CRM Sales")
        self.targets = []
        self.addCleanup(self.remove_fixtures)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def remove_fixtures(self):
        frappe.local.db = self.primary
        frappe.db.rollback()
        frappe.set_user("Administrator")
        for name in self.targets:
            frappe.db.delete("Version", {"ref_doctype": cockpit.TARGET, "docname": name})
            frappe.db.delete(cockpit.TARGET, {"name": name})
        for user in (self.source, self.destination):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)

    def target(self, owner, metric="visits", anchor="2030-09-02", value="5"):
        row = cockpit.save_target({"sales": owner, "metric": metric, "period": "week", "anchor": anchor, "value": value})
        self.targets.append(row["id"])
        return row

    def merge(self):
        return rename_doc("User", self.source, self.destination, merge=True, force=True,
                          ignore_permissions=True, rebuild_search=False)

    def test_native_merge_rejects_colliding_target_keys_and_preserves_records(self):
        first = self.target(self.source)
        second = self.target(self.destination, value="7")
        frappe.db.set_value(cockpit.TARGET, first["id"],
                            {"sales_owner": self.source.upper(), "target_scope": ""}, update_modified=False)
        with self.assertRaisesRegex(frappe.ValidationError, "conflicting cockpit targets"):
            self.merge()
        self.assertTrue(frappe.db.exists("User", self.source))
        self.assertEqual(frappe.db.get_value(cockpit.TARGET, first["id"], "sales_owner"), self.source.upper())
        self.assertEqual(frappe.db.get_value(cockpit.TARGET, second["id"], "sales_owner"), self.destination)
        self.assertEqual(str(frappe.db.get_value(cockpit.TARGET, first["id"], "target_value")), "5.00")
        self.assertEqual(str(frappe.db.get_value(cockpit.TARGET, second["id"], "target_value")), "7.00")

    def test_noncolliding_native_merge_keeps_all_target_ids_and_audit(self):
        first = self.target(self.source)
        second = self.target(self.destination, anchor="2030-09-09")
        updated = cockpit.save_target({"sales": self.source, "metric": "visits", "period": "week",
                                       "anchor": "2030-09-02", "value": "6"}, first["modified"])
        audit = frappe.get_all("Version", filters={"ref_doctype": cockpit.TARGET, "docname": first["id"]}, fields=["name", "data"])
        self.assertTrue(audit)
        self.merge()
        for row in (first, second):
            self.assertEqual(frappe.db.get_value(cockpit.TARGET, row["id"], "sales_owner"), self.destination)
        self.assertEqual(str(frappe.db.get_value(cockpit.TARGET, first["id"], "target_value")), "6.00")
        self.assertEqual(to_iso_timestamp(frappe.db.get_value(cockpit.TARGET, first["id"], "modified")), updated["modified"])
        self.assertEqual(frappe.get_all("Version", filters={"ref_doctype": cockpit.TARGET, "docname": first["id"]}, fields=["name", "data"]), audit)

    def test_merge_checks_targets_committed_after_its_repeatable_read_snapshot(self):
        first = self.target(self.source)
        frappe.db.commit()
        with self.secondary_connection():
            frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self.assertFalse(frappe.db.exists(cockpit.TARGET, {"sales_owner": self.destination}))
            with self.primary_connection():
                second = self.target(self.destination, value="9")
                frappe.db.commit()
            with self.assertRaisesRegex(frappe.ValidationError, "conflicting cockpit targets"):
                self.merge()
            frappe.db.rollback()
        self.assertEqual(frappe.db.get_value(cockpit.TARGET, first["id"], "sales_owner"), self.source)
        self.assertEqual(frappe.db.get_value(cockpit.TARGET, second["id"], "sales_owner"), self.destination)

    def test_identity_merge_preserves_historical_target_for_disabled_destination(self):
        first = self.target(self.source)
        frappe.db.set_value("User", self.destination, "enabled", 0)
        frappe.clear_cache(user=self.destination)
        self.merge()
        record = next(row for row in cockpit.target_rows() if row["id"] == first["id"])
        self.assertEqual((record["sales"], record["value"]), (self.destination, "5.00"))
        self.assertNotIn(self.destination, cockpit.targetable_sales())
