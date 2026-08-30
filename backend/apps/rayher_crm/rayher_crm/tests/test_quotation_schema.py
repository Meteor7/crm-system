from __future__ import annotations

import json
import unittest
from pathlib import Path


DOCTYPE_ROOT = Path(__file__).parents[1] / "rayher_crm" / "doctype"


def schema(name: str) -> dict:
    folder = name.replace(" ", "_").lower()
    return json.loads((DOCTYPE_ROOT / folder / f"{folder}.json").read_text(encoding="utf-8"))


class TestQuotationSchema(unittest.TestCase):
    def test_master_is_unique_per_opportunity_and_ref_number(self):
        fields = {row["fieldname"]: row for row in schema("CRM Quotation")["fields"]}
        self.assertEqual(fields["opportunity"]["options"], "CRM Opportunity")
        self.assertNotIn("reqd", fields["opportunity"])
        self.assertEqual(fields["opportunity"]["unique"], 1)
        self.assertEqual(fields["ref_no"]["unique"], 1)
        self.assertEqual(fields["quotation_owner"]["options"], "User")
        self.assertEqual(fields["quotation_type"]["options"], "Device\nService")
        self.assertEqual(fields["quotation_type"]["default"], "Device")

    def test_version_owns_item_and_payment_child_tables(self):
        fields = {row["fieldname"]: row for row in schema("CRM Quotation Version")["fields"]}
        self.assertEqual(fields["items"], {"fieldname": "items", "fieldtype": "Table", "label": "Items", "options": "CRM Quotation Item"})
        self.assertEqual(fields["payment_terms"]["options"], "CRM Quotation Payment Term")
        self.assertNotIn("reqd", fields["opportunity"])
        self.assertEqual(fields["quotation_type"]["options"], "Device\nService")
        self.assertEqual(fields["pdf_file"]["fieldtype"], "Attach")
        self.assertEqual(schema("CRM Quotation Item")["istable"], 1)
        self.assertEqual(schema("CRM Quotation Payment Term")["istable"], 1)

    def test_catalog_and_item_schema_support_three_levels(self):
        item_fields = {row["fieldname"]: row for row in schema("CRM Quotation Item")["fields"]}
        catalog_fields = {row["fieldname"]: row for row in schema("CRM Quotation Catalog Item")["fields"]}
        self.assertEqual(item_fields["line_type"]["options"], "Device\nSystem\nAccessory")
        self.assertEqual(item_fields["parent_system_key"]["fieldtype"], "Data")
        self.assertEqual(item_fields["catalog_item"]["options"], "CRM Quotation Catalog Item")
        self.assertEqual(catalog_fields["item_level"]["options"], "Device\nSystem\nAccessory")
        self.assertEqual(catalog_fields["parent_item"]["options"], "CRM Quotation Catalog Item")
        self.assertEqual(catalog_fields["catalog_key"]["unique"], 1)
    def test_version_persists_validity_months(self):
        fields = {row["fieldname"]: row for row in schema("CRM Quotation Version")["fields"]}
        self.assertEqual(fields["validity_months"]["fieldtype"], "Int")
        self.assertEqual(fields["validity_months"]["default"], "1")
        self.assertEqual(fields["validity_months"]["reqd"], 1)

    def test_version_has_independent_approval_state_and_immutable_attempts(self):
        version_fields = {row["fieldname"]: row for row in schema("CRM Quotation Version")["fields"]}
        approval_fields = {row["fieldname"]: row for row in schema("CRM Quotation Approval")["fields"]}
        self.assertEqual(version_fields["approval_status"]["options"], "Not Submitted\nPending\nApproved\nRejected\nNot Required")
        self.assertEqual(version_fields["current_approval"]["options"], "CRM Quotation Approval")
        self.assertEqual(approval_fields["quotation_version"]["options"], "CRM Quotation Version")
        self.assertEqual(approval_fields["status"]["options"], "Pending\nApproved\nRejected")

    def test_engineer_has_no_quotation_permissions(self):
        for doctype in ("CRM Quotation", "CRM Quotation Version", "CRM Quotation Approval"):
            roles = {row["role"] for row in schema(doctype).get("permissions", [])}
            self.assertEqual(roles, {"CRM Manager", "CRM Sales"})


if __name__ == "__main__":
    unittest.main()
