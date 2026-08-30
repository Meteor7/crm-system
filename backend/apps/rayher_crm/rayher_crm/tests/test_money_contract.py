from __future__ import annotations

import unittest

from rayher_crm.services.money import (
    MoneyValidationError,
    aggregate_by_currency,
    decimal_string,
    weighted_decimal_string,
)


class TestMoneyContract(unittest.TestCase):
    def test_decimal_string_preserves_decimal_20_2_without_float_round_trip(self):
        self.assertEqual(decimal_string("999999999999999999.99"), "999999999999999999.99")
        self.assertEqual(decimal_string("0"), "0.00")

    def test_decimal_string_rejects_excess_scale_and_precision(self):
        for value in ("1.001", "1000000000000000000.00", "NaN", True):
            with self.subTest(value=value), self.assertRaises(MoneyValidationError):
                decimal_string(value)

    def test_aggregate_by_currency_never_mixes_currency_buckets(self):
        rows = [
            {"currency": "CNY", "amount": "9007199254740992.01"},
            {"currency": "CNY", "amount": "0.02"},
            {"currency": "USD", "amount": "9007199254740992.01"},
        ]
        self.assertEqual(
            aggregate_by_currency(rows),
            [
                {"currency": "CNY", "amount": "9007199254740992.03"},
                {"currency": "USD", "amount": "9007199254740992.01"},
            ],
        )

    def test_weighted_decimal_uses_decimal_half_up_rounding(self):
        self.assertEqual(weighted_decimal_string("0.05", 50), "0.03")


if __name__ == "__main__":
    unittest.main()
