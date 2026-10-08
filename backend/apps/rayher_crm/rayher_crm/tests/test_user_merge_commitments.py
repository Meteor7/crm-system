"""Native User merges preserve commitment uniqueness without losing history."""
import frappe
from frappe.model.rename_doc import rename_doc
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services import plan_commitments as service
from rayher_crm.tests import test_opportunity_relations as relation_fixtures


class TestUserMergeCommitments(FrappeTestCase):
    _user = relation_fixtures.TestOpportunityRelations._user

    def setUp(self):
        super().setUp()
        self.assertTrue(frappe.local.site.endswith(".test"))
        self.original_user = frappe.session.user
        self.primary = frappe.local.db
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=10)
        self.source = self._user(f"merge-commit-{token}-source@example.invalid", "CRM Sales")
        self.destination = self._user(f"merge-commit-{token}-destination@example.invalid", "CRM Sales")
        self.records = []
        self.addCleanup(self.remove_fixtures)

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def remove_fixtures(self):
        frappe.local.db = self.primary
        frappe.db.rollback()
        frappe.set_user("Administrator")
        for name in self.records:
            frappe.db.delete("Version", {"ref_doctype": service.DOCTYPE, "docname": name})
            frappe.db.delete(service.DOCTYPE, {"name": name})
        for user in (self.source, self.destination):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.original_user)

    def commitment(self, owner, metric="visits", anchor="2030-09-02", value="5", expected=None):
        row = service.save({"sales": owner, "metric": metric, "period": "week", "anchor": anchor,
                            "value": value, "note": "Preserved meeting promise"}, expected)
        if row["id"] not in self.records:
            self.records.append(row["id"])
        return row

    def merge(self):
        return rename_doc("User", self.source, self.destination, merge=True, force=True,
                          ignore_permissions=True, rebuild_search=False)

    def audit(self, name):
        return frappe.get_all("Version", filters={"ref_doctype": service.DOCTYPE, "docname": name},
                              fields=["name", "data"], order_by="name")

    def test_native_merge_rejects_colliding_keys_without_changing_records_or_audit(self):
        first = self.commitment(self.source)
        first = self.commitment(self.source, value="6", expected=first["modified"])
        second = self.commitment(self.destination, value="9")
        frappe.db.set_value(service.DOCTYPE, first["id"], "sales_owner", self.source.upper(), update_modified=False)
        audit = self.audit(first["id"])
        self.assertTrue(audit)
        with self.assertRaisesRegex(frappe.ValidationError, "conflicting plan commitments"):
            self.merge()
        self.assertTrue(frappe.db.exists("User", self.source))
        for row, owner in ((first, self.source.upper()), (second, self.destination)):
            actual = frappe.get_doc(service.DOCTYPE, row["id"])
            self.assertEqual((actual.sales_owner, str(actual.commitment_value), actual.note),
                             (owner, row["value"], row["note"]))
            self.assertEqual(service.to_iso_timestamp(actual.modified), row["modified"])
        self.assertEqual(self.audit(first["id"]), audit)

    def test_noncolliding_native_merge_keeps_record_ids_and_audit(self):
        first = self.commitment(self.source)
        first = self.commitment(self.source, value="6", expected=first["modified"])
        second = self.commitment(self.destination, metric="events")
        third = self.commitment(self.destination, anchor="2030-09-09")
        audit = self.audit(first["id"])
        self.assertTrue(audit)
        self.merge()
        for row in (first, second, third):
            actual = frappe.get_doc(service.DOCTYPE, row["id"])
            self.assertEqual((actual.sales_owner, str(actual.commitment_value)), (self.destination, row["value"]))
            self.assertEqual(service.to_iso_timestamp(actual.modified), row["modified"])
        self.assertEqual(self.audit(first["id"]), audit)
        retried = self.commitment(self.destination, value="7", expected=first["modified"])
        self.assertEqual(retried["id"], first["id"])

    def test_merge_checks_commitments_committed_after_its_repeatable_read_snapshot(self):
        first = self.commitment(self.source)
        frappe.db.commit()
        with self.secondary_connection():
            frappe.db.sql("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self.assertFalse(frappe.db.exists(service.DOCTYPE, {"sales_owner": self.destination}))
            with self.primary_connection():
                second = self.commitment(self.destination, value="9")
                frappe.db.commit()
            with self.assertRaisesRegex(frappe.ValidationError, "conflicting plan commitments"):
                self.merge()
            frappe.db.rollback()
        self.assertEqual(frappe.db.get_value(service.DOCTYPE, first["id"], "sales_owner"), self.source)
        self.assertEqual(frappe.db.get_value(service.DOCTYPE, second["id"], "sales_owner"), self.destination)

    def test_noncolliding_merge_preserves_historical_commitment_for_disabled_destination(self):
        first = self.commitment(self.source)
        frappe.db.set_value("User", self.destination, "enabled", 0)
        frappe.clear_cache(user=self.destination)
        self.merge()
        self.assertEqual(frappe.db.get_value(service.DOCTYPE, first["id"], "sales_owner"), self.destination)
        self.assertEqual(str(frappe.db.get_value(service.DOCTYPE, first["id"], "commitment_value")), "5")
