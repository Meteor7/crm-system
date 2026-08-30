from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.setup.money_schema import MONEY_COLUMNS, enforce_money_column_contract


class TestMoneySchema(FrappeTestCase):
    def test_money_columns_are_physically_decimal_20_2(self):
        enforce_money_column_contract()

        rows = frappe.db.sql(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE()",
            as_dict=True,
        )
        types = {(row.TABLE_NAME, row.COLUMN_NAME): row.COLUMN_TYPE.lower() for row in rows}

        for key in MONEY_COLUMNS:
            self.assertEqual(types[key], "decimal(20,2)")
