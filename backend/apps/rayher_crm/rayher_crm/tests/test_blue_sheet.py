import json
from copy import deepcopy
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.patches.v1_0.backfill_blue_sheet_flags import execute as backfill
from rayher_crm.services import blue_sheet, opportunities
from rayher_crm.tests.test_blue_sheet_rules import sample_rules
from rayher_crm.tests.test_opportunity_relations import TestOpportunityRelations


class TestBlueSheet(FrappeTestCase):
    _user = TestOpportunityRelations._user
    _records = TestOpportunityRelations._records
    _stakeholder_input = TestOpportunityRelations._stakeholder_input

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("blue-sheet-sales@example.invalid", "CRM Sales")
        self.other = self._user("blue-sheet-other@example.invalid", "CRM Sales")
        self.manager = self._user("blue-sheet-manager@example.invalid", "CRM Manager")
        self.engineer = self._user("blue-sheet-engineer@example.invalid", "CRM Engineer")
        self.account, self.opportunity, self.contact = self._records(self.sales, "BlueSheet" + frappe.generate_hash(length=8))
        self.name = self.opportunity["id"]
        self.stakeholder = opportunities.create_opportunity_stakeholder(self.name, self._stakeholder_input(self.contact["id"], role="Economic Buyer"))

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user(self.original_user)
        super().tearDown()

    def current(self):
        return opportunities.get_strategy_opportunity(self.name)

    def save(self, items, version=None):
        return blue_sheet.save_flags(self.name, {"items": items}, version or self.current()["modified"])

    def test_flag_lifecycle_audit_legacy_editor_and_stale_version(self):
        created = self.save([{"text": "No budget evidence", "severity": "High", "status": "Open"}])
        flag = created["redFlagRecords"][0]
        self.assertEqual(created["redFlags"], [flag["text"]])
        self.assertEqual(flag["updatedBy"], self.sales)
        resolved = self.save([{key: ("Resolved" if key == "status" else flag[key]) for key in ("id", "text", "severity", "status")}])
        roundtrip = opportunities.update_strategy_opportunity(self.name, {"title": "Changed title", "redFlags": resolved["redFlags"]}, resolved["modified"])
        self.assertEqual(roundtrip["redFlagRecords"], resolved["redFlagRecords"])
        self.assertEqual(roundtrip["redFlagRecords"][0]["id"], flag["id"])
        with self.assertRaises(CrmApiException) as stale:
            self.save([], created["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        deleted = self.save([])
        self.assertEqual((deleted["redFlags"], deleted["redFlagRecords"]), ([], []))
        self.assertEqual(len([row for row in deleted["history"] if row["field"] == "red_flag_records"]), 3)

    def test_legacy_backfill_preserves_duplicates_long_text_and_unknown_metadata(self):
        texts = ["旧风险" * 1500, "旧风险" * 1500]
        frappe.db.set_value("CRM Opportunity", self.name, {"red_flags": json.dumps(texts), "red_flag_records": None})
        before = self.current()
        backfill()
        after = self.current()
        backfill()
        self.assertEqual(after["modified"], before["modified"])
        self.assertEqual(after["redFlagRecords"], self.current()["redFlagRecords"])
        self.assertEqual([row["text"] for row in after["redFlagRecords"]], texts)
        self.assertEqual(len({row["id"] for row in after["redFlagRecords"]}), 2)
        self.assertTrue(all(row["severity"] == "" and row["updatedAt"] is None and row["updatedBy"] is None for row in after["redFlagRecords"]))

    def test_current_warnings_follow_resolution_deletion_and_permissions(self):
        current = self.save([{"text": "Risk", "severity": "", "status": "Open"}])
        def warnings():
            return blue_sheet.warning_rows([{"name": self.name}], [{"name": self.account["id"], "customer_name": "Account"}], {})
        rows = warnings()
        self.assertEqual([(row["eventId"], row["redFlagSeverity"]) for row in rows], [(current["redFlagRecords"][0]["id"], "")])
        self.assertEqual(rows, warnings())
        row = current["redFlagRecords"][0]
        self.save([{key: ("Resolved" if key == "status" else row[key]) for key in ("id", "text", "severity", "status")}])
        self.assertEqual(warnings(), [])
        self.save([{key: row[key] for key in ("id", "text", "severity", "status")}])
        frappe.set_user(self.other)
        self.assertEqual(warnings(), [])
        with self.assertRaises(CrmApiException):
            blue_sheet.save_flags(self.name, {"items": []}, current["modified"])
        frappe.set_user(self.sales)
        self.save([])
        self.assertEqual(warnings(), [])

    def test_unconfigured_assessment_never_changes_probability_or_exposes_engineer_facts(self):
        with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": None}):
            result = blue_sheet.get_assessment(self.name)
            self.assertEqual((result["state"], result["suggestedLevel"]), ("unconfigured", None))
            with self.assertRaises(CrmApiException):
                blue_sheet.apply_suggestion(self.name, {"fingerprint": result["fingerprint"]}, result["opportunityModified"])
        self.assertEqual(self.current()["probabilityLevel"], "pipeline")
        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as denied:
            blue_sheet.get_assessment(self.name)
        self.assertEqual(denied.exception.code, "PERMISSION_DENIED")
        frappe.set_user(self.sales)
        frappe.db.set_value("CRM Opportunity", self.name, "stage", "po_received")
        with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": sample_rules()}):
            closed = blue_sheet.get_assessment(self.name)
            self.assertEqual((closed["state"], closed["suggestedLevel"], closed["canApply"]), ("closed", None, False))
            with self.assertRaises(CrmApiException):
                blue_sheet.apply_suggestion(self.name, {"fingerprint": closed["fingerprint"]}, closed["opportunityModified"])

    def test_suggestion_confirmation_uses_existing_downgrade_and_audit_workflow(self):
        config = sample_rules()
        with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": config}):
            result = blue_sheet.get_assessment(self.name)
            self.assertEqual(result["suggestedLevel"], "upside")
            self.assertEqual(self.current()["probabilityLevel"], "pipeline")
            updated = blue_sheet.apply_suggestion(self.name, {"fingerprint": result["fingerprint"]}, result["opportunityModified"])
            self.assertEqual(updated["probabilityLevel"], "upside")
            config["rules"][0]["level"] = "low_probability"
            down = blue_sheet.get_assessment(self.name)
            with self.assertRaises(CrmApiException):
                blue_sheet.apply_suggestion(self.name, {"fingerprint": down["fingerprint"]}, down["opportunityModified"])
            updated = blue_sheet.apply_suggestion(self.name, {"fingerprint": down["fingerprint"], "probabilityReason": "Budget withdrawn", "probabilityActionPlan": "Meet the economic buyer"}, down["opportunityModified"])
            self.assertEqual(updated["probabilityLevel"], "low_probability")
            self.assertEqual(updated["probabilityHistory"][0]["reason"], "Budget withdrawn")
            self.assertEqual(updated["probabilityHistory"][0]["recovery"]["plan"], "Meet the economic buyer")
            self.assertEqual(len([row for row in updated["history"] if row["field"] == "blueSheetSuggestion"]), 2)

    def test_an_archived_opportunity_takes_no_red_flag_and_no_suggestion_until_the_restore(self):
        from rayher_crm.services.opportunity_archive import ARCHIVED_OPPORTUNITY_EDIT
        with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": sample_rules()}):
            self.assertTrue(blue_sheet.get_assessment(self.name)["canApply"])
            frappe.set_user(self.manager)
            opportunities.archive_strategy_opportunity(self.name)
            frappe.set_user(self.sales)
            archived = self.current()
            assessment = blue_sheet.get_assessment(self.name)
            self.assertFalse(assessment["canApply"])
            for attempt in (
                lambda: self.save([{"text": "No budget evidence", "severity": "High", "status": "Open"}], archived["modified"]),
                lambda: blue_sheet.apply_suggestion(self.name, {"fingerprint": assessment["fingerprint"]}, archived["modified"]),
            ):
                with self.assertRaises(CrmApiException) as refused:
                    attempt()
                self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_OPPORTUNITY_EDIT))
            current = self.current()
            self.assertEqual(
                (current["redFlagRecords"], current["probabilityLevel"], current["modified"]),
                (archived["redFlagRecords"], archived["probabilityLevel"], archived["modified"]),
            )
            frappe.set_user(self.manager)
            opportunities.unarchive_strategy_opportunity(self.name)
            frappe.set_user(self.sales)
            self.assertTrue(blue_sheet.get_assessment(self.name)["canApply"])

    def test_old_suggestion_rejects_changed_stakeholders_rules_and_owner(self):
        config = sample_rules()
        with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": config}):
            old = blue_sheet.get_assessment(self.name)
            changed = deepcopy(config)
            changed["version"] = "test-v2"
            with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": changed}):
                with self.assertRaises(CrmApiException) as stale:
                    blue_sheet.apply_suggestion(self.name, {"fingerprint": old["fingerprint"]}, old["opportunityModified"])
                self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
            opportunities.update_opportunity_stakeholder(self.name, self.stakeholder["id"], self._stakeholder_input(self.contact["id"], role="Economic Buyer", stance="Against"))
            with self.assertRaises(CrmApiException) as stale:
                blue_sheet.apply_suggestion(self.name, {"fingerprint": old["fingerprint"]}, old["opportunityModified"])
            self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
            frappe.set_user(self.manager)
            current = blue_sheet.get_assessment(self.name)
            self.assertFalse(current["canApply"])
            with self.assertRaises(CrmApiException):
                blue_sheet.apply_suggestion(self.name, {"fingerprint": current["fingerprint"]}, current["opportunityModified"])

    def test_legacy_create_and_update_enforce_red_flag_limits(self):
        before = self.current()
        payload = opportunities._current_input(frappe.get_doc("CRM Opportunity", self.name))
        payload["qualificationConfirmed"] = True
        for texts in (["new"] * 201, ["x" * 4001]):
            with self.subTest(size=len(texts)):
                with self.assertRaises(CrmApiException) as create_error:
                    opportunities.create_strategy_opportunity({**payload, "redFlags": texts})
                self.assertEqual(create_error.exception.code, "VALIDATION_ERROR")
                self.assertIn("redFlags", create_error.exception.field_errors)
                with self.assertRaises(CrmApiException) as update_error:
                    opportunities.update_strategy_opportunity(self.name, {"redFlags": texts}, before["modified"])
                self.assertEqual(update_error.exception.code, "VALIDATION_ERROR")
                self.assertEqual(self.current()["redFlagRecords"], before["redFlagRecords"])
                self.assertEqual(self.current()["modified"], before["modified"])

    def test_unrelated_edits_and_probability_confirmation_preserve_exact_red_flag_text_and_state(self):
        text = "  Budget pending\nBuyer follow-up  "
        saved = self.save([{"text": text, "severity": "High", "status": "Resolved"}])
        records = saved["redFlagRecords"]
        for payload in ({"title": "Unrelated change"}, {"redFlags": [text]}):
            updated = opportunities.update_strategy_opportunity(self.name, payload, self.current()["modified"])
            self.assertEqual(updated["redFlagRecords"], records)
            self.assertEqual(updated["redFlags"], [text])
        with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": sample_rules()}):
            assessment = blue_sheet.get_assessment(self.name)
            self.assertEqual(assessment["suggestedLevel"], "upside")
            updated = blue_sheet.apply_suggestion(self.name, {"fingerprint": assessment["fingerprint"]}, assessment["opportunityModified"])
        self.assertEqual(updated["probabilityLevel"], "upside")
        self.assertEqual(updated["redFlagRecords"], records)
        self.assertEqual(blue_sheet.warning_rows([{"name": self.name}], [{"name": self.account["id"], "customer_name": "Account"}], {}), [])

    def test_same_role_and_stance_contact_rebind_invalidates_suggestion(self):
        from rayher_crm.services.contacts import create_contact
        contact = create_contact({"accountId": self.account["id"], "name": "Replacement buyer", "title": "Director",
            "department": "Engineering", "phone": "13800000002", "email": "replacement@example.invalid",
            "relationship": "Developing", "owner": self.sales, "status": "Active"})
        with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": sample_rules()}):
            before = blue_sheet.get_assessment(self.name)
            opportunities.update_opportunity_stakeholder(self.name, self.stakeholder["id"],
                self._stakeholder_input(contact["id"], role="Economic Buyer"))
            after = blue_sheet.get_assessment(self.name)
            self.assertEqual(after["opportunityModified"], before["opportunityModified"])
            self.assertEqual(after["facts"], before["facts"])
            self.assertNotEqual(after["fingerprint"], before["fingerprint"])
            with self.assertRaises(CrmApiException) as stale:
                blue_sheet.apply_suggestion(self.name, {"fingerprint": before["fingerprint"]}, before["opportunityModified"])
            self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

    def test_committed_customer_visibility_revocation_rejects_both_editors_and_suggestion(self):
        from rayher_crm.permissions.scope import OPPORTUNITY_SCOPED_CHILD_DOCTYPES
        self.assertTrue(frappe.local.site.endswith(".test"))
        site = frappe.db.get_value("CRM Opportunity", self.name, "site")
        frappe.db.set_value("Customer", self.account["id"], {"custom_crm_owner": self.other, "custom_crm_visibility": "Public"})
        frappe.db.commit()
        connection = frappe.db._get_connection()
        require = opportunities._require_opportunity

        def revoke_after_initial_read(name, *args, **kwargs):
            doc = require(name, *args, **kwargs)
            with connection.cursor() as cursor:
                cursor.execute("UPDATE `tabCustomer` SET custom_crm_visibility='Private' WHERE name=%s", (self.account["id"],))
            connection.commit()
            return doc

        try:
            self.assertEqual(frappe.db.sql("SELECT @@tx_isolation")[0][0], "REPEATABLE-READ")
            for path in ("flags", "legacy", "suggestion"):
                with self.subTest(path=path):
                    frappe.db.rollback()
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE `tabCustomer` SET custom_crm_visibility='Public' WHERE name=%s", (self.account["id"],))
                    connection.commit()
                    with patch.dict(frappe.conf, {"crm_blue_sheet_probability_rules": sample_rules()}):
                        assessment = blue_sheet.get_assessment(self.name)
                        with patch.object(opportunities, "_require_opportunity", side_effect=revoke_after_initial_read):
                            with self.assertRaises(CrmApiException) as denied:
                                if path == "flags":
                                    blue_sheet.save_flags(self.name, {"items": []}, assessment["opportunityModified"])
                                elif path == "legacy":
                                    opportunities.update_strategy_opportunity(self.name, {"redFlags": ["Denied"]}, assessment["opportunityModified"])
                                else:
                                    blue_sheet.apply_suggestion(self.name, {"fingerprint": assessment["fingerprint"]}, assessment["opportunityModified"])
                        self.assertEqual(denied.exception.code, "SCOPE_DENIED")
        finally:
            frappe.db.rollback()
            connection.close()
            frappe.set_user("Administrator")
            fixture_refs = {"CRM Opportunity": [self.name], "Contact": [self.contact["id"]],
                            "Address": [site], "Customer": [self.account["id"]]}
            # These are standalone Link records, not Frappe child rows. Deleting
            # the parent with force=True does not cascade to their history.
            for doctype in OPPORTUNITY_SCOPED_CHILD_DOCTYPES:
                fixture_refs[doctype] = frappe.get_all(doctype, filters={"opportunity": self.name}, pluck="name")
                frappe.db.delete(doctype, {"opportunity": self.name})
            for doctype, names in fixture_refs.items():
                if names:
                    frappe.db.delete("Version", {"ref_doctype": doctype, "docname": ["in", names]})
                    frappe.db.delete("CRM Notification Event", {"source_doctype": doctype, "source_name": ["in", names]})
            frappe.delete_doc("CRM Opportunity", self.name, ignore_permissions=True, force=True)
            frappe.delete_doc("Contact", self.contact["id"], ignore_permissions=True, force=True)
            frappe.delete_doc("Address", site, ignore_permissions=True, force=True)
            frappe.delete_doc("Customer", self.account["id"], ignore_permissions=True, force=True)
            with patch("frappe.enqueue"):
                frappe.db.commit()
            for doctype, names in fixture_refs.items():
                for name in names:
                    self.assertIsNone(frappe.db.get_value(doctype, name, "name", for_update=True), (doctype, name))

    def test_stakeholder_current_read_uses_index_and_does_not_lock_other_opportunity_rows(self):
        self.assertTrue(frappe.local.site.endswith(".test"))
        suffix = frappe.generate_hash(length=16)
        ids = ["blue-lock-" + suffix + str(i) for i in range(3)]
        parents = ["blue-parent-" + suffix + str(i) for i in range(3)]
        connection = frappe.db._get_connection()
        try:
            # Raw, isolated child fixtures need no committed shared test data.
            with connection.cursor() as cursor:
                for identity, parent in zip(ids, parents):
                    cursor.execute("""INSERT INTO `tabCRM Opportunity Stakeholder`
                        (name, opportunity, contact, role, stance, archived, modified)
                        VALUES (%s,%s,'test-contact','Economic Buyer','Support',0,NOW(6))""", (identity, parent))
            connection.commit()
            plan = frappe.db.sql("EXPLAIN " + blue_sheet.STAKEHOLDER_QUERY + " FOR UPDATE", (parents[1],), as_dict=True)
            self.assertEqual(plan[0]["key"], blue_sheet.OPPORTUNITY_STAKEHOLDER_INDEX)
            doc = frappe._dict(name=parents[1], modified=frappe.utils.now_datetime(), opportunity_owner=self.sales,
                stage="qualified_opportunity", probability_level="pipeline", red_flags="[]", red_flag_records="[]")
            assessment = blue_sheet._assessment(doc, current=True)
            self.assertEqual(assessment["facts"]["coveredRoles"], ["Economic Buyer"])
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION innodb_lock_wait_timeout=1")
                for identity in (ids[0], ids[2]):
                    cursor.execute("SELECT name FROM `tabCRM Opportunity Stakeholder` WHERE name=%s FOR UPDATE NOWAIT", (identity,))
                    cursor.execute("UPDATE `tabCRM Opportunity Stakeholder` SET stance='Neutral' WHERE name=%s", (identity,))
                with self.assertRaises(Exception) as locked:
                    cursor.execute("SELECT name FROM `tabCRM Opportunity Stakeholder` WHERE name=%s FOR UPDATE NOWAIT", (ids[1],))
                self.assertEqual(locked.exception.args[0], 1205)
        finally:
            frappe.db.rollback()
            connection.rollback()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM `tabCRM Opportunity Stakeholder` WHERE name IN (%s,%s,%s)", tuple(ids))
            connection.commit()
            connection.close()
