import unittest
from datetime import datetime

from rayher_crm.services.demo_resource_rules import resource_state


class TestDemoResourceRules(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2030, 10, 1, 8)
        self.evaluation = {"name": "eval", "status": "Scheduled", "demo_resource": "machine-1",
                           "resource_start": "2030-10-01 10:00:00", "resource_end": "2030-10-01 12:00:00", "resource_revision": 1}
        self.block = {"name": "block", "resource": "machine-1", "status": "Active", "revision": 1,
                      "starts_at": "2030-10-01 11:00:00", "ends_at": "2030-10-01 13:00:00", "reason": "Maintenance"}

    def state(self, evaluation=None, block=None, now=None):
        return resource_state({**self.evaluation, **(evaluation or {})}, [{**self.block, **(block or {})}], now or self.now)

    def test_exact_device_and_half_open_intervals(self):
        self.assertEqual(self.state()["state"], "blocked")
        for block in ({"resource": "machine-2"}, {"starts_at": "2030-10-01 12:00:00"}, {"ends_at": "2030-10-01 10:00:00", "starts_at": "2030-10-01 09:00:00"}, {"status": "Resolved"}):
            with self.subTest(block=block):
                self.assertEqual(self.state(block=block)["state"], "available")

    def test_unknown_terminal_cancelled_and_elapsed_are_not_available(self):
        for value in ({"demo_resource": None}, {"resource_start": None}, {"resource_end": "2030-10-01 09:00:00"}):
            self.assertEqual(self.state(evaluation=value)["state"], "unknown")
        for status in ("Internal Review", "Customer Review", "Accepted", "Rejected"):
            self.assertEqual(self.state(evaluation={"status": status})["state"], "inactive")
        self.assertEqual(self.state(evaluation={"request_status": "Cancelled"})["state"], "inactive")
        self.assertEqual(self.state(now=datetime(2030, 10, 1, 12))["state"], "elapsed")
        self.assertEqual(self.state(block={"ends_at": "2030-10-01 11:30:00"}, now=datetime(2030, 10, 1, 11, 30))["state"], "available")

    def test_only_semantic_revisions_change_notification_identity(self):
        key = self.state()["impacts"][0]["key"]
        self.assertEqual(key, self.state(block={"reason": "Updated note"})["impacts"][0]["key"])
        self.assertNotEqual(key, self.state(block={"revision": 2})["impacts"][0]["key"])
        self.assertNotEqual(key, self.state(evaluation={"resource_revision": 2})["impacts"][0]["key"])
