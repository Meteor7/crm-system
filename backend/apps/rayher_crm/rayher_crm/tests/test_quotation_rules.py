from __future__ import annotations

import unittest

from rayher_crm.services.quotation_rules import QuotationRuleError, calculate_totals, validate_payment_terms


class TestQuotationRules(unittest.TestCase):
    def test_calculates_devices_and_only_charged_accessories(self):
        result = calculate_totals([
            {"lineType": "Device", "lineKey": "device-1", "quantity": 2, "unitPrice": "100.00"},
            {"lineType": "Accessory", "parentDeviceKey": "device-1", "pricingMode": "Included", "quantity": 5, "unitPrice": "9.00"},
            {"lineType": "Accessory", "parentDeviceKey": "device-1", "pricingMode": "Charged", "quantity": 3, "unitPrice": "10.00"},
        ], discount_type="Percentage", discount_value="10")
        self.assertEqual(result, {
            "subtotal": "230.00", "discountAmount": "23.00", "total": "207.00",
            "deviceGroups": [{
                "lineKey": "device-1", "quantity": 2,
                "configurationSubtotal": "230.00", "configurationUnitTotal": "115.00",
            }],
        })

    def test_calculates_each_parent_configuration_without_whole_document_average(self):
        result = calculate_totals([
            {"lineType": "Device", "lineKey": "device-1", "quantity": 2, "unitPrice": "10000.00"},
            {"lineType": "Accessory", "parentDeviceKey": "device-1", "pricingMode": "Charged", "quantity": 1, "unitPrice": "5000.00"},
            {"lineType": "Accessory", "parentDeviceKey": "device-1", "pricingMode": "Included", "quantity": 9, "unitPrice": "999.00"},
            {"lineType": "Device", "lineKey": "device-2", "quantity": 1, "unitPrice": "20000.00"},
        ], discount_type="None", discount_value="0")
        self.assertEqual(result["subtotal"], "45000.00")
        self.assertEqual(result["deviceGroups"], [
            {"lineKey": "device-1", "quantity": 2, "configurationSubtotal": "25000.00", "configurationUnitTotal": "12500.00"},
            {"lineKey": "device-2", "quantity": 1, "configurationSubtotal": "20000.00", "configurationUnitTotal": "20000.00"},
        ])

    def test_rejects_fractional_device_and_included_accessory_quantities(self):
        cases = [
            [{"lineType": "Device", "lineKey": "device-1", "quantity": "1.5", "unitPrice": "100.00"}],
            [
                {"lineType": "Device", "lineKey": "device-1", "quantity": 1, "unitPrice": "100.00"},
                {"lineType": "Accessory", "parentDeviceKey": "device-1", "pricingMode": "Included", "quantity": "2.5", "unitPrice": "0.00"},
            ],
        ]
        for items in cases:
            with self.subTest(items=items), self.assertRaisesRegex(QuotationRuleError, "whole number"):
                calculate_totals(items, discount_type="None", discount_value="0")

    def test_fixed_discount_cannot_exceed_subtotal(self):
        with self.assertRaisesRegex(QuotationRuleError, "exceed"):
            calculate_totals(
                [{"lineType": "Device", "lineKey": "device-1", "quantity": 1, "unitPrice": "100.00"}],
                discount_type="Fixed Amount", discount_value="100.01",
            )

    def test_rejects_non_cny_or_invalid_line_hierarchy(self):
        with self.assertRaisesRegex(QuotationRuleError, "CNY"):
            calculate_totals([], discount_type="None", discount_value="0", currency="USD")
        with self.assertRaisesRegex(QuotationRuleError, "parent"):
            calculate_totals([
                {"lineType": "Accessory", "parentDeviceKey": "missing", "pricingMode": "Charged", "quantity": 1, "unitPrice": "1.00"},
            ], discount_type="None", discount_value="0")

    def test_system_groups_are_zero_value_and_accessories_stay_under_the_same_device(self):
        items = [
            {"lineType": "Device", "lineKey": "device-1", "quantity": 1, "unitPrice": "100.00"},
            {"lineType": "System", "lineKey": "system-1", "parentDeviceKey": "device-1", "quantity": 999, "unitPrice": "999.00"},
            {"lineType": "Accessory", "lineKey": "accessory-1", "parentDeviceKey": "device-1", "parentSystemKey": "system-1", "pricingMode": "Charged", "quantity": 2, "unitPrice": "10.00"},
        ]
        result = calculate_totals(items, discount_type="None", discount_value="0")
        self.assertEqual(result["subtotal"], "120.00")
        with self.assertRaisesRegex(QuotationRuleError, "same parent device"):
            calculate_totals([
                *items,
                {"lineType": "Device", "lineKey": "device-2", "quantity": 1, "unitPrice": "1.00"},
                {"lineType": "Accessory", "lineKey": "wrong", "parentDeviceKey": "device-2", "parentSystemKey": "system-1", "pricingMode": "Included", "quantity": 1, "unitPrice": "0"},
            ], discount_type="None", discount_value="0")
    def test_payment_terms_must_equal_100_only_when_publishing(self):
        terms = [{"percentage": "30"}, {"percentage": "30"}, {"percentage": "30"}, {"percentage": "10"}]
        self.assertIsNone(validate_payment_terms(terms, publishing=True))
        self.assertIsNone(validate_payment_terms([{"percentage": "30"}], publishing=False))
        with self.assertRaisesRegex(QuotationRuleError, "100"):
            validate_payment_terms([{"percentage": "30"}], publishing=True)


if __name__ == "__main__":
    unittest.main()