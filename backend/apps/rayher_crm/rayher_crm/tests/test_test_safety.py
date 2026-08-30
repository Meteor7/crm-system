from __future__ import annotations

import unittest

from rayher_crm.tests.safety import assert_dedicated_test_site


class TestTestSafety(unittest.TestCase):
    def test_operational_or_unmarked_site_is_rejected(self):
        for marker in (None, False, 0, "false", "0"):
            with self.subTest(marker=marker), self.assertRaisesRegex(
                RuntimeError,
                "dedicated CRM test site",
            ):
                assert_dedicated_test_site(marker, "rayher-crm.localhost")

    def test_explicit_dedicated_test_site_is_allowed(self):
        for marker in (True, 1, "true", "1"):
            with self.subTest(marker=marker):
                assert_dedicated_test_site(marker, "rayher-crm.test")

    def test_operational_site_name_is_rejected_even_with_marker(self):
        with self.assertRaisesRegex(RuntimeError, "dedicated CRM test site"):
            assert_dedicated_test_site(True, "rayher-crm.localhost")
