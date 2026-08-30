from __future__ import annotations

import json
import unittest

from rayher_crm.patches.v1_0.migrate_installed_tool_lifecycle import build_lifecycle_state
from rayher_crm.patches.v1_0.prepare_installed_tool_date_fields import normalize_legacy_date


class TestInstalledToolMigration(unittest.TestCase):
    def test_legacy_dates_keep_iso_dates_and_clear_placeholders(self):
        self.assertEqual(normalize_legacy_date("2026-08-12"), "2026-08-12")
        for value in (None, "", "Pending", "待确认", "尚未开始", "2026-99-99"):
            self.assertIsNone(normalize_legacy_date(value))

    def test_lifecycle_is_derived_from_first_incomplete_milestone(self):
        legacy = [
            {"label": "FAT", "date": "2026-07-01", "state": "Done"},
            {"label": "Shipment", "date": "2026-07-15", "state": "Done"},
            {"label": "Installation", "date": "待确认", "state": "Current"},
            {"label": "SAT", "date": "待确认", "state": "Waiting"},
            {"label": "Warranty", "date": "待确认", "state": "Waiting"},
        ]

        stage, milestones = build_lifecycle_state(json.dumps(legacy, ensure_ascii=False), "Production")

        self.assertEqual(stage, "Installation")
        self.assertEqual(
            milestones,
            [
                {"label": "FAT", "date": "2026-07-01", "state": "Done"},
                {"label": "Shipment", "date": "2026-07-15", "state": "Done"},
                {"label": "Installation", "date": "", "state": "Current"},
                {"label": "SAT", "date": "", "state": "Waiting"},
                {"label": "Warranty", "date": "", "state": "Waiting"},
            ],
        )

    def test_current_milestone_takes_priority_over_status_mapping(self):
        stage, _ = build_lifecycle_state(
            [{"label": "Shipment", "date": "", "state": "Current"}],
            "Production",
        )
        self.assertEqual(stage, "Shipment")

    def test_status_mapping_is_used_when_no_current_milestone_exists(self):
        stage, _ = build_lifecycle_state([], "Installation Complete")
        self.assertEqual(stage, "SAT")
    def test_lifecycle_normalization_is_idempotent(self):
        stage, milestones = build_lifecycle_state([])
        second_stage, second_milestones = build_lifecycle_state(milestones)
        self.assertEqual((stage, milestones), (second_stage, second_milestones))
        self.assertEqual(stage, "FAT")

    def test_completed_legacy_lifecycle_remains_completed(self):
        legacy = [
            {"label": label, "date": f"2026-07-{index:02d}", "state": "Done"}
            for index, label in enumerate(("FAT", "Shipment", "Installation", "SAT", "Warranty"), start=1)
        ]
        stage, milestones = build_lifecycle_state(legacy)
        self.assertEqual(stage, "Warranty")
        self.assertTrue(all(row["state"] == "Done" for row in milestones))