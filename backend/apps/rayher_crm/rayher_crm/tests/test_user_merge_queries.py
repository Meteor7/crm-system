"""Saved-query access remains a set after native User identity consolidation."""
import frappe
from frappe.model.rename_doc import rename_doc
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services import opportunity_board as service
from rayher_crm.tests import test_opportunity_board_api as fixtures


class TestUserMergeQueries(FrappeTestCase):
    _user = fixtures.TestOpportunityBoardApi._user

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        token = frappe.generate_hash(length=10)
        self.users = [self._user(f"query-merge-{token}-{suffix}@example.invalid", "CRM Manager", suffix)
                      for suffix in ("owner", "source", "destination")]
        self.owner, self.source, self.destination = self.users
        frappe.set_user(self.owner)
        self.saved = service.save_opportunity_query(None, {"name": "Identity set",
            "definition": {"scope": {}, "match": "all", "conditions": [], "columns": ["customerName"]}})

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def merge(self, source, destination):
        frappe.set_user("Administrator")
        rename_doc("User", source, destination, merge=True, force=True,
                   ignore_permissions=True, rebuild_search=False)

    def current(self, owner):
        frappe.set_user(owner)
        return next(row for row in service.list_opportunity_queries()["items"] if row["id"] == self.saved["id"])

    def raw_recipients(self):
        return frappe.get_all("CRM Query Recipient", filters={"parent": self.saved["id"]}, pluck="user")

    def test_merged_recipients_are_one_effective_share_and_can_be_saved_or_revoked(self):
        self.saved = service.share_opportunity_query(self.saved["id"], [self.source, self.destination], self.saved["modified"])
        self.merge(self.source, self.destination)
        row = self.current(self.owner)
        self.assertEqual(row["recipients"], [self.destination])
        self.assertEqual(row["modified"], self.saved["modified"])
        # A read is not a hidden migration or audit rewrite. A versioned save
        # through the existing owner API materializes the same effective set.
        self.assertEqual(self.raw_recipients(), [self.destination, self.destination])
        updated = service.share_opportunity_query(row["id"], row["recipients"], row["modified"])
        self.assertEqual(self.raw_recipients(), [self.destination])
        service.share_opportunity_query(updated["id"], [], updated["modified"])
        frappe.set_user(self.destination)
        self.assertNotIn(self.saved["id"], [row["id"] for row in service.list_opportunity_queries()["items"]])

    def test_recipient_merged_into_query_owner_is_not_a_self_share(self):
        self.saved = service.share_opportunity_query(self.saved["id"], [self.source], self.saved["modified"])
        self.merge(self.source, self.owner)
        row = self.current(self.owner)
        self.assertEqual((row["owner"], row["readOnly"], row["recipients"]), (self.owner, False, []))
        updated = service.share_opportunity_query(row["id"], row["recipients"], row["modified"])
        self.assertEqual((updated["recipients"], self.raw_recipients()), ([], []))

    def test_query_owner_merged_into_recipient_retains_editing_and_private_access(self):
        self.saved = service.share_opportunity_query(self.saved["id"], [self.source], self.saved["modified"])
        self.merge(self.owner, self.source)
        row = self.current(self.source)
        self.assertEqual((row["owner"], row["readOnly"], row["recipients"]), (self.source, False, []))
        updated = service.share_opportunity_query(row["id"], row["recipients"], row["modified"])
        self.assertEqual((updated["recipients"], self.raw_recipients()), ([], []))
