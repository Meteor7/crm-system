"""The daily CRM jobs must be registered with Frappe's scheduler, and nothing may pause it.

A new Frappe site starts with the scheduler disabled. Every environment created before 2026-09-22
(staging included) stayed that way, so the DDL reminders and quotation expiry never ran once.
``compose.yaml``'s install-app step now enables it on every start. Whether it is enabled cannot be
asserted here: ``bench run-tests`` disables the scheduler for the duration of the run and restores
it afterwards (frappe/test_runner.py), so ``run-backend-tests.ps1`` checks ``bench scheduler status``
before starting the run instead.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm import hooks

DAILY_JOBS = tuple(hooks.scheduler_events["daily"])


class TestSchedulerContract(FrappeTestCase):
    def test_nothing_in_site_config_pauses_the_scheduler(self):
        for key in ("disable_scheduler", "pause_scheduler", "maintenance_mode"):
            self.assertFalse(frappe.conf.get(key), f"site_config.json sets {key}; the daily CRM jobs {DAILY_JOBS} would not run")

    def test_every_daily_crm_job_is_registered_and_not_stopped(self):
        self.assertEqual(DAILY_JOBS, (
            "rayher_crm.services.quotations.expire_quotations",
            "rayher_crm.services.ddl_reminders.send_ddl_reminders",
            "rayher_crm.services.warning_notifications.send_warning_notifications",
        ))
        for method in DAILY_JOBS:
            rows = frappe.get_all(
                "Scheduled Job Type", filters={"method": method}, fields=["name", "frequency", "stopped"],
            )
            self.assertEqual(len(rows), 1, f"{method} is not registered as a Scheduled Job Type; run bench migrate")
            self.assertEqual((rows[0].frequency, rows[0].stopped), ("Daily", 0), method)
