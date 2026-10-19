from __future__ import annotations

import unittest
from datetime import date, datetime

from rayher_crm.services.common import SHANGHAI_TIMEZONE
from rayher_crm.services.demo_health import derive_demo_health


TODAY = "2026-07-28"


def health(last_progress_at="2026-07-28T09:00:00+08:00", customer_expected_date="", test_run_deadline="", today=TODAY):
    return derive_demo_health(
        last_progress_at=last_progress_at, customer_expected_date=customer_expected_date,
        test_run_deadline=test_run_deadline, today=today,
    )


class TestDemoHealth(unittest.TestCase):
    def test_customer_expectation_within_seven_days_is_critical(self):
        self.assertEqual(health(customer_expected_date="2026-08-04"), {
            "level": "critical", "reason": "距客户预期仅 7 天", "daysSinceProgress": 0, "daysToCustomerExpected": 7,
        })
        self.assertEqual(health(customer_expected_date="2026-07-28")["reason"], "客户预期为今天")
        self.assertEqual(health(customer_expected_date="2026-07-04"), {
            "level": "critical", "reason": "客户预期已逾期 24 天", "daysSinceProgress": 0, "daysToCustomerExpected": -24,
        })

    def test_customer_expectation_eight_days_away_is_not_critical(self):
        self.assertEqual(health(last_progress_at="2026-07-27T23:30:00+08:00", customer_expected_date="2026-08-05"), {
            "level": "healthy", "reason": "1 天内有进展", "daysSinceProgress": 1, "daysToCustomerExpected": 8,
        })

    def test_customer_expectation_comes_before_a_stall(self):
        result = health(last_progress_at="2026-07-01T08:00:00+08:00", customer_expected_date="2026-07-30")
        self.assertEqual((result["level"], result["reason"], result["daysSinceProgress"]), ("critical", "距客户预期仅 2 天", 27))

    def test_passed_test_run_deadline_is_critical(self):
        result = health(customer_expected_date="2026-08-20", test_run_deadline="2026-07-25")
        self.assertEqual((result["level"], result["reason"]), ("critical", "Test Run DDL 已逾期 3 天"))
        self.assertEqual(health(customer_expected_date="2026-08-20", test_run_deadline=TODAY)["level"], "healthy")

    def test_five_days_without_progress_is_stalled_and_four_is_not(self):
        self.assertEqual(health(last_progress_at="2026-07-23T08:00:00+08:00", customer_expected_date="2026-08-20"), {
            "level": "stalled", "reason": "已连续 5 天无有效进展", "daysSinceProgress": 5, "daysToCustomerExpected": 23,
        })
        four = health(last_progress_at="2026-07-24T08:00:00+08:00", customer_expected_date="2026-08-20")
        self.assertEqual((four["level"], four["reason"], four["daysSinceProgress"]), ("healthy", "演示员工152推进", 4))

    def test_days_are_counted_in_shanghai_time(self):
        # 16:30 UTC on the 27th is 00:30 on the 28th in Shanghai: progress today, not yesterday.
        self.assertEqual(health(last_progress_at="2026-07-27T16:30:00Z")["reason"], "今天有进展")
        self.assertEqual(health(last_progress_at="2026-07-27T15:30:00.123456Z")["daysSinceProgress"], 1)
        # A timestamp without a zone is Shanghai time, as the CRM stores them.
        self.assertEqual(health(last_progress_at="2026-07-28 00:10:00")["daysSinceProgress"], 0)
        self.assertEqual(health(last_progress_at=datetime(2026, 7, 27, 16, 30, tzinfo=SHANGHAI_TIMEZONE))["daysSinceProgress"], 1)

    def test_dates_may_be_date_objects_and_progress_in_the_future_counts_as_today(self):
        result = health(
            last_progress_at="2026-07-29T09:00:00+08:00", customer_expected_date=date(2026, 8, 20),
            test_run_deadline=date(2026, 7, 27), today=date(2026, 7, 28),
        )
        self.assertEqual((result["level"], result["daysSinceProgress"], result["daysToCustomerExpected"]), ("critical", 0, 23))

    def test_missing_or_unreadable_values_claim_nothing(self):
        self.assertEqual(health(last_progress_at=None, customer_expected_date=None, test_run_deadline=None), {
            "level": "healthy", "reason": "演示员工152推进", "daysSinceProgress": 0, "daysToCustomerExpected": None,
        })
        self.assertEqual(health(last_progress_at="not a date", customer_expected_date="2026-13-40")["level"], "healthy")
        with self.assertRaises(ValueError):
            health(today="")
