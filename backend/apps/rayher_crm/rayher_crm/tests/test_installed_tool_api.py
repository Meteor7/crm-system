from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.api.v1.installed_tools import (
    add_installed_tool_service_record as add_installed_tool_service_record_endpoint,
    add_installed_tool_version_record as add_installed_tool_version_record_endpoint,
    get_installed_tool as get_installed_tool_endpoint,
    transition_installed_tool as transition_installed_tool_endpoint,
)
from rayher_crm.services.accounts import create_account
from rayher_crm.services.bookings import create_booking
from rayher_crm.services.contacts import create_contact
from rayher_crm.patches.v1_0.migrate_installed_tool_lifecycle import execute as migrate_installed_tool_lifecycle
from rayher_crm.services.installed_tools import (
    add_installed_tool_service_record,
    add_installed_tool_version_record,
    convert_booking_to_installed_tool,
    get_installed_tool,
    list_installed_tools,
    transition_installed_tool,
    update_installed_tool,
)
from rayher_crm.services.opportunities import create_strategy_opportunity
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestInstalledToolApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-tool-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-tool-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-tool-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._user("crm-tool-other-engineer@example.invalid", "CRM Engineer")

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
            user.enabled = 1
            if role not in {row.role for row in user.roles}:
                user.append("roles", {"role": role})
                user.save(ignore_permissions=True)
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _booking(self, owner: str, suffix: str, status: str = "Confirmed"):
        frappe.set_user(owner)
        account = create_account({
            "name": f"Tool {suffix}", "shortName": suffix, "segment": "Frontend",
            "tier": "A", "city": "上海", "region": "华东", "owner": owner,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Site", "city": "上海", "type": "Fab", "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"tool-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": owner, "status": "Active",
        })
        opportunity = create_strategy_opportunity({
            "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Opportunity",
            "owner": owner, "stage": "需求发现", "forecast": "Pipeline", "amount": 300000,
            "probability": 100, "intentScore": 90, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "华东", "currency": "CNY", "originalAmount": 300000,
        })
        opportunity = advance_opportunity_fixture(opportunity, "Won")
        booking = create_booking({
            "accountId": account["id"], "primaryContactId": contact["id"], "equipment": "Inspection 5000",
            "quantity": 1, "ddl": "2027-01-31", "amount": "300000.00", "currency": "CNY", "status": status,
            "owner": owner, "source": "Opportunity", "sourceOpportunityId": opportunity["id"], "note": "",
        })
        return account, site, opportunity, booking

    def _input(self, site: dict, serial: str, engineer: str | None = None, **overrides):
        payload = {
            "siteId": site["id"], "engineerOwner": engineer or self.engineer,
            "serial": serial, "model": "Model X", "location": "Fab 1",
            "salesOrder": "SO-REF", "contract": "CT-REF", "software": "1.0",
            "firmware": "2.0", "configuration": "Standard",
        }
        payload.update(overrides)
        return payload

    def _update_input(self, tool: dict, **overrides):
        payload = {
            "siteId": tool["siteId"], "serial": tool["serial"], "model": tool["model"],
            "location": tool["location"], "status": tool["status"], "engineerOwner": tool["engineerOwner"],
            "software": tool["software"], "firmware": tool["firmware"],
            "configuration": tool["configuration"], "operatingSystem": tool["operatingSystem"],
            "warrantyStart": tool["warrantyStart"], "warrantyEnd": tool["warrantyEnd"],
            "serviceContract": tool["serviceContract"], "pmCycle": tool["pmCycle"],
            "ownershipType": tool["ownershipType"], "salesOrder": tool["salesOrder"], "contract": tool["contract"],
        }
        payload.update(overrides)
        return payload

    def test_legacy_milestone_migration_is_idempotent_and_creates_minimal_history(self):
        _, site, _, booking = self._booking(self.sales, "LegacyMigration")
        legacy = [
            {"label": "FAT", "date": "2026-07-01", "state": "Done"},
            {"label": "Shipment", "date": "2026-07-15", "state": "Done"},
            {"label": "Installation", "date": "", "state": "Current"},
        ]
        frappe.set_user("Administrator")
        tool = frappe.get_doc({
            "doctype": "CRM Installed Tool", "account": booking["accountId"], "site": site["id"],
            "serial": f"LEGACY-{frappe.generate_hash(length=8)}", "model": "Legacy Model",
            "location": "Fab 1", "status": "Production", "lifecycle_stage": "FAT",
            "software": "1.0", "firmware": "2.0", "completeness": 55,
            "source_booking": booking["id"], "source_opportunity": booking["sourceOpportunityId"],
            "sales_owner": self.sales, "engineer_owner": self.engineer,
            "ownership_type": "Customer Owned", "milestones": json.dumps(legacy), "documents": "[]",
        }).insert(ignore_permissions=True)

        migrate_installed_tool_lifecycle()
        first = frappe.get_all(
            "CRM Installed Tool Lifecycle History",
            filters={"installed_tool": tool.name, "comment": "Legacy milestone migration"},
            fields=["from_stage", "to_stage", "completed_at"], order_by="completed_at asc",
        )
        migrate_installed_tool_lifecycle()
        second_count = frappe.db.count(
            "CRM Installed Tool Lifecycle History",
            {"installed_tool": tool.name, "comment": "Legacy milestone migration"},
        )

        tool.reload()
        self.assertEqual(tool.lifecycle_stage, "Installation")
        self.assertEqual(second_count, 2)
        self.assertEqual(
            [(row.from_stage, row.to_stage, str(row.completed_at)) for row in first],
            [("FAT", "Shipment", "2026-07-01"), ("Shipment", "Installation", "2026-07-15")],
        )
    def test_detail_is_real_ordered_and_exposes_server_permissions(self):
        _, site, _, booking = self._booking(self.sales, "Detail")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"DETAIL-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        tool = converted["installedTool"]
        frappe.set_user("Administrator")
        older = frappe.get_doc({
            "doctype": "CRM Installed Tool Lifecycle History", "installed_tool": tool["id"],
            "at": "2026-08-10 09:00:00", "actor": self.engineer, "from_stage": "FAT",
            "to_stage": "Shipment", "completed_at": "2026-08-10", "result": "Passed",
            "open_issues": "None", "customer_signoff": "Signed", "comment": "FAT complete", "evidence": "[]",
        }).insert(ignore_permissions=True)
        newer = frappe.get_doc({
            "doctype": "CRM Installed Tool Lifecycle History", "installed_tool": tool["id"],
            "at": "2026-08-11 09:00:00", "actor": self.engineer, "from_stage": "Shipment",
            "to_stage": "Installation", "completed_at": "2026-08-11", "result": "Delivered",
            "open_issues": "None", "customer_signoff": "Received", "comment": "Shipment complete", "evidence": "[]",
        }).insert(ignore_permissions=True)
        version = frappe.get_doc({
            "doctype": "CRM Installed Tool Version History", "installed_tool": tool["id"],
            "at": "2026-08-11 10:00:00", "actor": self.engineer, "change_date": "2026-08-11",
            "change_type": "Software", "from_value": "1.0", "to_value": "1.1",
            "reason": "Validation release", "comment": "Approved",
        }).insert(ignore_permissions=True)
        service = frappe.get_doc({
            "doctype": "CRM Installed Tool Service History", "installed_tool": tool["id"],
            "at": "2026-08-11 11:00:00", "actor": self.engineer, "service_date": "2026-08-11",
            "service_type": "Installation Support", "result": "Completed", "open_issues": "None",
        }).insert(ignore_permissions=True)

        frappe.set_user(self.sales)
        sales_detail = get_installed_tool(tool["id"])
        self.assertFalse(sales_detail["canOperate"])
        self.assertFalse(sales_detail["canReassign"])

        frappe.set_user(self.engineer)
        engineer_detail = get_installed_tool(tool["id"])
        self.assertTrue(engineer_detail["canOperate"])
        self.assertFalse(engineer_detail["canReassign"])
        self.assertEqual([row["id"] for row in engineer_detail["lifecycleHistory"]], [newer.name, older.name])
        self.assertEqual(engineer_detail["versionHistory"][0]["id"], version.name)
        self.assertEqual(engineer_detail["serviceHistory"][0]["id"], service.name)

        frappe.set_user("Administrator")
        manager_detail = get_installed_tool(tool["id"])
        self.assertTrue(manager_detail["canOperate"])
        self.assertTrue(manager_detail["canReassign"])

        frappe.set_user(self.other_engineer)
        with self.assertRaises(CrmApiException) as denied:
            get_installed_tool(tool["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

    def test_detail_endpoint_returns_stable_envelope(self):
        _, site, _, booking = self._booking(self.sales, "DetailEndpoint")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"DETAIL-API-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        frappe.set_user(self.engineer)

        response = get_installed_tool_endpoint(converted["installedTool"]["id"])

        self.assertEqual(set(response), {"data", "warnings", "meta"})
        self.assertEqual(response["warnings"], [])
        self.assertRegex(response["meta"]["requestId"], r"^req_[0-9a-f]{24}$")
        self.assertEqual(
            set(("lifecycleHistory", "versionHistory", "serviceHistory", "canOperate", "canReassign")) - set(response["data"]),
            set(),
        )
    def test_conversion_is_atomic_server_named_and_creates_no_erp_documents(self):
        _, site, opportunity, booking = self._booking(self.sales, "Atomic")
        before = {doctype: frappe.db.count(doctype) for doctype in ("Asset", "Sales Order", "Delivery Note")}
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"SERIAL-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        self.assertRegex(converted["installedTool"]["id"], r"^CRM-TOOL-\d{5}$")
        self.assertRegex(converted["installedTool"]["serial"], r"^CRM-SN-[0-9]{5}$")
        self.assertEqual(converted["booking"]["status"], "Completed")
        self.assertEqual(converted["booking"]["installedToolId"], converted["installedTool"]["id"])
        self.assertEqual(converted["installedTool"]["sourceOpportunityId"], opportunity["id"])
        assigned = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Installed Tool", "source_name": converted["installedTool"]["id"],
                     "recipient_user": self.engineer},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (assigned.category, assigned.route),
            ("InstalledTool", f"/installed-tools?surface=detail&tool={converted['installedTool']['id']}"),
        )
        frappe.set_user(self.engineer)
        self.assertEqual(get_installed_tool(converted["installedTool"]["id"])["id"], converted["installedTool"]["id"])
        frappe.set_user(self.sales)
        self.assertEqual({doctype: frappe.db.count(doctype) for doctype in before}, before)
        history = frappe.get_all("CRM Opportunity History", filters={"opportunity": opportunity["id"], "field": "bookingConverted"}, fields=["actor", "to_value"])
        self.assertEqual([(row.actor, row.to_value) for row in history], [(self.sales, converted["installedTool"]["id"])])
        with self.assertRaises(CrmApiException) as repeated:
            convert_booking_to_installed_tool(booking["id"], self._input(site, "OTHER"), converted["booking"]["modified"])
        self.assertEqual(repeated.exception.code, "CONFLICT")

        for failure_stage in ("after_tool_insert", "after_booking_update"):
            _, rollback_site, _, rollback_booking = self._booking(self.sales, f"Rollback{failure_stage}")
            before_tools = frappe.db.count("CRM Installed Tool")

            def fail_at(stage: str, expected=failure_stage):
                if stage == expected:
                    raise RuntimeError(f"injected {expected}")

            with self.assertRaisesRegex(RuntimeError, f"injected {failure_stage}"):
                convert_booking_to_installed_tool(
                    rollback_booking["id"],
                    self._input(rollback_site, f"ROLLBACK-{frappe.generate_hash(length=8)}"),
                    rollback_booking["modified"], failure_injector=fail_at,
                )
            self.assertEqual(frappe.db.count("CRM Installed Tool"), before_tools)
            self.assertEqual(frappe.db.get_value("CRM Booking", rollback_booking["id"], "status"), "Confirmed")
            self.assertFalse(frappe.db.get_value("CRM Booking", rollback_booking["id"], "installed_tool"))

    def test_conversion_validates_status_site_engineer_and_generates_unique_serial(self):
        _, site, _, pending = self._booking(self.sales, "Pending", status="Pending")
        with self.assertRaises(CrmApiException) as not_confirmed:
            convert_booking_to_installed_tool(pending["id"], self._input(site, "PENDING"), pending["modified"])
        self.assertEqual(not_confirmed.exception.code, "INVALID_TRANSITION")

        _, valid_site, _, booking = self._booking(self.sales, "Validation")
        _, foreign_site, _, _ = self._booking(self.other_sales, "Foreign")
        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as mismatch:
            convert_booking_to_installed_tool(booking["id"], self._input(foreign_site, "MISMATCH"), booking["modified"])
        self.assertEqual(mismatch.exception.code, "CONFLICT")
        with self.assertRaises(CrmApiException) as invalid_engineer:
            convert_booking_to_installed_tool(
                booking["id"], self._input(valid_site, "BAD-ENGINEER", engineer=self.sales), booking["modified"]
            )
        self.assertEqual(invalid_engineer.exception.code, "VALIDATION_ERROR")

        serial = f"UNIQUE-{frappe.generate_hash(length=8)}"
        first = convert_booking_to_installed_tool(booking["id"], self._input(valid_site, serial), booking["modified"])
        _, second_site, _, second = self._booking(self.sales, "Duplicate")
        second_result = convert_booking_to_installed_tool(second["id"], self._input(second_site, serial.lower()), second["modified"])
        self.assertRegex(first["installedTool"]["serial"], r"^CRM-SN-[0-9]{5}$")
        self.assertRegex(second_result["installedTool"]["serial"], r"^CRM-SN-[0-9]{5}$")
        self.assertNotEqual(first["installedTool"]["serial"], second_result["installedTool"]["serial"])

    def test_database_serial_race_is_returned_as_conflict(self):
        _, site, _, booking = self._booking(self.sales, "SerialRace")
        from frappe.model.document import Document
        real_insert = Document.insert

        def duplicate_at_database(document, *args, **kwargs):
            if document.doctype == "CRM Installed Tool":
                raise frappe.UniqueValidationError("duplicate serial")
            return real_insert(document, *args, **kwargs)

        with patch("frappe.model.document.Document.insert", new=duplicate_at_database):
            with self.assertRaises(CrmApiException) as conflict:
                convert_booking_to_installed_tool(
                    booking["id"], self._input(site, f"RACE-{frappe.generate_hash(length=8)}"), booking["modified"]
                )
        self.assertEqual(conflict.exception.code, "CONFLICT")
        self.assertEqual(frappe.db.get_value("CRM Booking", booking["id"], "status"), "Confirmed")

    def test_lifecycle_advances_exactly_five_steps_and_then_stops(self):
        _, site, _, booking = self._booking(self.sales, "Lifecycle")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"LIFECYCLE-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        detail = converted["installedTool"]
        frappe.set_user(self.engineer)
        expected_stages = ["Shipment", "Installation", "SAT", "Warranty", "Warranty"]
        expected_statuses = ["Shipment", "Installation", "Installation Complete", "Production", "Production"]
        previous_completeness = detail["completeness"]
        for index, (stage, status) in enumerate(zip(expected_stages, expected_statuses, strict=True), start=1):
            detail = transition_installed_tool(
                detail["id"],
                {
                    "completedAt": f"2026-08-{index:02d}",
                    "result": f"Stage {index} passed", "openIssues": "None",
                    "customerSignoff": "Signed", "comment": f"Completed stage {index}",
                    "evidence": [f"report-{index}.pdf"],
                },
                detail["modified"],
            )
            self.assertEqual(detail["lifecycleStage"], stage)
            self.assertEqual(detail["status"], status)
            self.assertGreater(detail["completeness"], previous_completeness)
            previous_completeness = detail["completeness"]

        self.assertTrue(detail["lifecycleCompleted"])
        self.assertEqual(len(detail["lifecycleHistory"]), 5)
        self.assertEqual(detail["lifecycleHistory"][0]["toStage"], "Completed")
        self.assertTrue(all(row["state"] == "Done" for row in detail["milestones"]))
        with self.assertRaises(CrmApiException) as repeated:
            transition_installed_tool(
                detail["id"],
                {"completedAt": "2026-08-10", "result": "Again", "openIssues": "None", "customerSignoff": "Signed", "comment": "Repeat", "evidence": []},
                detail["modified"],
            )
        self.assertEqual(repeated.exception.code, "INVALID_TRANSITION")

    def test_lifecycle_permission_validation_and_cas_fail_closed(self):
        _, site, _, booking = self._booking(self.sales, "LifecyclePermission")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"LIFECYCLE-PERM-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        tool = converted["installedTool"]
        valid = {
            "completedAt": "2026-08-12", "result": "Passed", "openIssues": "None",
            "customerSignoff": "Signed", "comment": "Complete", "evidence": [],
        }

        frappe.set_user(self.sales)
        sales_response = transition_installed_tool_endpoint(tool["id"], valid, tool["modified"])
        self.assertEqual(sales_response["error"]["code"], "PERMISSION_DENIED")
        frappe.set_user(self.other_engineer)
        other_response = transition_installed_tool_endpoint(tool["id"], valid, tool["modified"])
        self.assertEqual(other_response["error"]["code"], "SCOPE_DENIED")
        self.assertEqual(frappe.db.count("CRM Installed Tool Lifecycle History", {"installed_tool": tool["id"]}), 0)

        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as future_date:
            transition_installed_tool(tool["id"], {**valid, "completedAt": "2099-01-01"}, tool["modified"])
        self.assertEqual(future_date.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as malformed:
            transition_installed_tool(tool["id"], {**valid, "evidence": ["ok", 7]}, tool["modified"])
        self.assertEqual(malformed.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as missing:
            transition_installed_tool(tool["id"], {**valid, "result": ""}, tool["modified"])
        self.assertEqual(missing.exception.code, "VALIDATION_ERROR")
        advanced = transition_installed_tool(tool["id"], valid, tool["modified"])
        with self.assertRaises(CrmApiException) as non_monotonic:
            transition_installed_tool(advanced["id"], {**valid, "completedAt": "2026-08-11"}, advanced["modified"])
        self.assertEqual(non_monotonic.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as stale:
            transition_installed_tool(tool["id"], valid, tool["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        self.assertEqual(len(advanced["lifecycleHistory"]), 1)

    def test_lifecycle_history_and_snapshot_are_atomic(self):
        for failure_stage in ("after_history_insert", "after_tool_update"):
            _, site, _, booking = self._booking(self.sales, f"LifecycleRollback{failure_stage}")
            converted = convert_booking_to_installed_tool(
                booking["id"], self._input(site, f"LIFECYCLE-RB-{frappe.generate_hash(length=8)}"), booking["modified"]
            )
            tool = converted["installedTool"]
            frappe.set_user(self.engineer)

            def fail_at(stage: str, expected=failure_stage):
                if stage == expected:
                    raise RuntimeError(f"injected {expected}")

            with self.assertRaisesRegex(RuntimeError, f"injected {failure_stage}"):
                transition_installed_tool(
                    tool["id"],
                    {"completedAt": "2026-08-12", "result": "Passed", "openIssues": "None", "customerSignoff": "Signed", "comment": "Atomic", "evidence": []},
                    tool["modified"], failure_injector=fail_at,
                )
            self.assertEqual(frappe.db.get_value("CRM Installed Tool", tool["id"], "lifecycle_stage"), "FAT")
            self.assertEqual(frappe.db.count("CRM Installed Tool Lifecycle History", {"installed_tool": tool["id"]}), 0)
    def test_version_records_use_server_from_value_and_update_all_four_snapshots(self):
        _, site, _, booking = self._booking(self.sales, "VersionHistory")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"VERSION-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        detail = converted["installedTool"]
        frappe.set_user(self.engineer)
        cases = [
            ("Software", "software", "1.0", "1.1"),
            ("Firmware", "firmware", "2.0", "2.1"),
            ("Operating System", "operatingSystem", "", "Ubuntu 24.04"),
            ("Configuration", "configuration", "Standard", "High Sensitivity"),
        ]
        for index, (change_type, public_field, expected_from, to_value) in enumerate(cases, start=1):
            detail = add_installed_tool_version_record(
                detail["id"],
                {
                    "changeDate": f"2026-08-{index:02d}", "changeType": change_type,
                    "fromValue": "FORGED", "toValue": to_value,
                    "reason": "Validated change", "comment": "Approved",
                },
                detail["modified"],
            )
            self.assertEqual(detail[public_field], to_value)
            self.assertEqual(detail["versionHistory"][0]["fromValue"], expected_from)
            self.assertEqual(detail["versionHistory"][0]["toValue"], to_value)
            self.assertEqual(detail["versionHistory"][0]["actor"], self.engineer)

        with self.assertRaises(CrmApiException) as no_op:
            add_installed_tool_version_record(
                detail["id"],
                {"changeDate": "2026-08-12", "changeType": "Software", "toValue": detail["software"], "reason": "No change", "comment": ""},
                detail["modified"],
            )
        self.assertEqual(no_op.exception.code, "VALIDATION_ERROR")

    def test_service_records_update_only_allowed_snapshot_fields_and_conditionals(self):
        _, site, _, booking = self._booking(self.sales, "ServiceHistory")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"SERVICE-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        detail = converted["installedTool"]
        frappe.set_user(self.engineer)
        detail = add_installed_tool_service_record(
            detail["id"],
            {
                "serviceDate": "2026-08-10", "serviceType": "Warranty Activation",
                "result": "Activated", "openIssues": "None", "comment": "Customer confirmed",
                "warrantyStart": "2026-08-10", "warrantyEnd": "2027-08-09",
                "serviceContract": "SC-2026-01", "pmCycle": "6 months",
            },
            detail["modified"],
        )
        self.assertEqual(detail["lastService"], "2026-08-10")
        self.assertEqual(detail["warrantyStart"], "2026-08-10")
        self.assertEqual(detail["warrantyEnd"], "2027-08-09")
        self.assertEqual(detail["serviceContract"], "SC-2026-01")
        self.assertEqual(detail["pmCycle"], "6 months")
        self.assertEqual(detail["serviceHistory"][0]["serviceType"], "Warranty Activation")

        invalid_count = len(detail["serviceHistory"])
        with self.assertRaises(CrmApiException) as missing_owner:
            add_installed_tool_service_record(
                detail["id"],
                {"serviceDate": "2026-08-11", "serviceType": "Corrective Service", "result": "Partial", "openIssues": "Monitor", "nextAction": "Return visit"},
                detail["modified"],
            )
        self.assertEqual(missing_owner.exception.code, "VALIDATION_ERROR")
        self.assertEqual(frappe.db.count("CRM Installed Tool Service History", {"installed_tool": detail["id"]}), invalid_count)

        detail = add_installed_tool_service_record(
            detail["id"],
            {
                "serviceDate": "2026-08-11", "serviceType": "Corrective Service",
                "result": "Partial", "openIssues": "Monitor", "nextAction": "Return visit",
                "actionOwner": self.engineer, "due": "2026-08-20", "comment": "Parts ordered",
            },
            detail["modified"],
        )
        self.assertEqual(detail["serviceHistory"][0]["actionOwner"], self.engineer)
        self.assertEqual(detail["serviceHistory"][0]["due"], "2026-08-20")
        detail = add_installed_tool_service_record(
            detail["id"],
            {
                "serviceDate": "2026-08-01", "serviceType": "Remote Support",
                "result": "Historical record", "openIssues": "None", "comment": "Backfilled",
            },
            detail["modified"],
        )
        self.assertEqual(detail["lastService"], "2026-08-11")
        self.assertEqual(len(detail["serviceHistory"]), 3)

    def test_version_and_service_permissions_cas_endpoints_and_atomicity(self):
        _, site, _, booking = self._booking(self.sales, "AuditCommands")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"AUDIT-CMD-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        tool = converted["installedTool"]
        version_input = {"changeDate": "2026-08-12", "changeType": "Software", "toValue": "1.2", "reason": "Release", "comment": ""}
        service_input = {"serviceDate": "2026-08-12", "serviceType": "Remote Support", "result": "Resolved", "openIssues": "None", "comment": ""}

        frappe.set_user(self.sales)
        self.assertEqual(add_installed_tool_version_record_endpoint(tool["id"], version_input, tool["modified"])["error"]["code"], "PERMISSION_DENIED")
        self.assertEqual(add_installed_tool_service_record_endpoint(tool["id"], service_input, tool["modified"])["error"]["code"], "PERMISSION_DENIED")
        frappe.set_user(self.other_engineer)
        self.assertEqual(add_installed_tool_version_record_endpoint(tool["id"], version_input, tool["modified"])["error"]["code"], "SCOPE_DENIED")
        self.assertEqual(add_installed_tool_service_record_endpoint(tool["id"], service_input, tool["modified"])["error"]["code"], "SCOPE_DENIED")

        frappe.set_user("Administrator")
        version_response = add_installed_tool_version_record_endpoint(tool["id"], version_input, tool["modified"])
        self.assertRegex(version_response["meta"]["requestId"], r"^req_[0-9a-f]{24}$")
        updated = version_response["data"]
        with self.assertRaises(CrmApiException) as stale:
            add_installed_tool_service_record(updated["id"], service_input, tool["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        for command, payload, history_doctype, failure_stage in (
            (add_installed_tool_version_record, {**version_input, "changeType": "Firmware", "toValue": "2.2"}, "CRM Installed Tool Version History", "after_history_insert"),
            (add_installed_tool_service_record, service_input, "CRM Installed Tool Service History", "after_tool_update"),
        ):
            current = get_installed_tool(updated["id"])
            before = frappe.db.count(history_doctype, {"installed_tool": updated["id"]})

            def fail_at(stage: str, expected=failure_stage):
                if stage == expected:
                    raise RuntimeError(f"injected {expected}")

            with self.assertRaisesRegex(RuntimeError, f"injected {failure_stage}"):
                command(current["id"], payload, current["modified"], failure_injector=fail_at)
            self.assertEqual(frappe.db.count(history_doctype, {"installed_tool": updated["id"]}), before)
    def test_master_update_adds_critical_fields_without_bypassing_audit_commands(self):
        _, site, _, booking = self._booking(self.sales, "MasterFields")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"MASTER-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        tool = converted["installedTool"]
        frappe.set_user(self.engineer)
        updated = update_installed_tool(
            tool["id"],
            self._update_input(
                tool, operatingSystem="Ubuntu 24.04", warrantyStart="2026-08-01", warrantyEnd="2027-07-31",
                serviceContract="SC-001", pmCycle="6 months", ownershipType="Leased",
                status="FORGED", lifecycleStage="Warranty", software="FORGED", firmware="FORGED", configuration="FORGED",
            ),
            tool["modified"],
        )
        self.assertEqual(
            (updated["operatingSystem"], updated["warrantyStart"], updated["warrantyEnd"], updated["serviceContract"], updated["pmCycle"], updated["ownershipType"]),
            ("Ubuntu 24.04", "2026-08-01", "2027-07-31", "SC-001", "6 months", "Leased"),
        )
        self.assertEqual((updated["status"], updated["lifecycleStage"]), (tool["status"], "FAT"))
        self.assertEqual((updated["software"], updated["firmware"], updated["configuration"]), (tool["software"], tool["firmware"], tool["configuration"]))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            update_installed_tool(updated["id"], self._update_input(updated, location="Forbidden"), updated["modified"])
    def test_installed_tool_scope_engineer_reassignment_and_cas(self):
        _, site, _, booking = self._booking(self.sales, "Scope")
        converted = convert_booking_to_installed_tool(
            booking["id"], self._input(site, f"SCOPE-{frappe.generate_hash(length=8)}"), booking["modified"]
        )
        tool = converted["installedTool"]
        frappe.set_user(self.engineer)
        self.assertIn(tool["id"], {item["id"] for item in list_installed_tools()})
        with self.assertRaises(CrmApiException) as reassign:
            update_installed_tool(tool["id"], self._update_input(tool, engineerOwner=self.other_engineer), tool["modified"])
        self.assertEqual(reassign.exception.code, "SCOPE_DENIED")

        updated = update_installed_tool(tool["id"], self._update_input(tool, location="Fab 2", status="FORGED", lifecycleStage="Warranty", software="9.9"), tool["modified"])
        self.assertEqual(updated["location"], "Fab 2")
        self.assertEqual(updated["status"], tool["status"])
        self.assertEqual(updated["lifecycleStage"], "FAT")
        self.assertEqual(updated["software"], tool["software"])
        with self.assertRaises(CrmApiException) as stale:
            update_installed_tool(tool["id"], self._update_input(updated, location="Stale"), tool["modified"])
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        frappe.set_user("Administrator")
        reassigned = update_installed_tool(
            tool["id"], self._update_input(updated, engineerOwner=self.other_engineer), updated["modified"]
        )
        self.assertEqual(reassigned["engineerOwner"], self.other_engineer)
        assignment_history = get_installed_tool(tool["id"])["versionHistory"][0]
        self.assertEqual(
            (assignment_history["changeType"], assignment_history["fromValue"], assignment_history["toValue"]),
            ("Engineer Assignment", self.engineer, self.other_engineer),
        )
        reassignment_notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Installed Tool", "source_name": tool["id"],
                     "recipient_user": self.other_engineer},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual(
            (reassignment_notice.category, reassignment_notice.route),
            ("InstalledTool", f"/installed-tools?surface=detail&tool={tool['id']}"),
        )
        frappe.set_user(self.engineer)
        self.assertNotIn(tool["id"], {item["id"] for item in list_installed_tools()})
        frappe.set_user(self.other_engineer)
        self.assertIn(tool["id"], {item["id"] for item in list_installed_tools()})
