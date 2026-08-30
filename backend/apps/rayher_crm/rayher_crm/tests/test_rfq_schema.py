from __future__ import annotations

import json
import unittest
from pathlib import Path


DOCTYPE_ROOT = Path(__file__).parents[1] / "rayher_crm" / "doctype"


def schema(name: str) -> dict:
    folder = name.replace(" ", "_").lower()
    return json.loads((DOCTYPE_ROOT / folder / f"{folder}.json").read_text(encoding="utf-8"))


class TestRfqSchema(unittest.TestCase):
    def test_master_is_unique_per_opportunity(self):
        fields = {row["fieldname"]: row for row in schema("CRM RFQ")["fields"]}
        self.assertEqual(fields["opportunity"]["options"], "CRM Opportunity")
        self.assertEqual(fields["opportunity"]["unique"], 1)
        self.assertEqual(fields["status"]["options"], "Engineer Review\nManager Approval\nSales Revision\nApproved")
        self.assertEqual(fields["current_version"]["options"], "CRM RFQ Version")

    def test_versions_own_files_and_decisions(self):
        fields = {row["fieldname"]: row for row in schema("CRM RFQ Version")["fields"]}
        self.assertEqual(fields["rfq"]["options"], "CRM RFQ")
        self.assertEqual(fields["original_file"]["options"], "File")
        self.assertEqual(fields["preview_file"]["options"], "File")
        self.assertEqual(fields["manager_decision"]["options"], "\nApproved\nReturned")


if __name__ == "__main__":
    unittest.main()
