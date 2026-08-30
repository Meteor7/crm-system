from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class TestQuotationPermissionContract(unittest.TestCase):
    def test_roles_expose_quotation_only_to_manager_and_sales(self):
        source = (ROOT / "permissions" / "roles.py").read_text(encoding="utf-8")
        self.assertIn('"quotation:view"', source)
        self.assertIn('"quotation:write"', source)
        self.assertIn('"quotation:publish"', source)
        self.assertIn('"quotation:submit"', source)
        self.assertIn('"quotation:approve"', source)
        engineer = source.split('"Engineer": (', 1)[1].split('),', 1)[0]
        self.assertNotIn("quotation:", engineer)

    def test_scope_and_hooks_cover_master_and_version(self):
        scope = (ROOT / "permissions" / "scope.py").read_text(encoding="utf-8")
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")
        for doctype in ("CRM Quotation", "CRM Quotation Version", "CRM Quotation Approval"):
            self.assertIn(f'"{doctype}"', scope)
            self.assertIn(f'"{doctype}"', hooks)
        self.assertIn("quotation_owner", scope)
        self.assertIn("quotation_query", scope)
        self.assertIn("quotation_version_query", scope)


if __name__ == "__main__":
    unittest.main()
