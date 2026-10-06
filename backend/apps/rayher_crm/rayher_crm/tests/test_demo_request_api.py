from __future__ import annotations

import copy
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.demo_requests import (
    add_demo_comment,
    create_demo_request,
    get_demo_request,
    list_demo_comments,
    list_demo_requests,
    transition_demo_request,
    update_demo_request,
)
from rayher_crm.services.opportunities import create_strategy_opportunity, mark_opportunity_lost
from rayher_crm.services.opportunity_stages import CUSTOMER_BUDGET_APPROVED, DEMO_DONE, QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site
from rayher_crm.tests._opportunity_fixtures import advance_opportunity_fixture


class TestDemoRequestApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-demo-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-demo-other-sales@example.invalid", "CRM Sales")
        self.engineer = self._user("crm-demo-engineer@example.invalid", "CRM Engineer")
        self.other_engineer = self._user("crm-demo-other-engineer@example.invalid", "CRM Engineer")
        self.manager = self._user("crm-demo-manager@example.invalid", "CRM Manager")
        self.account, self.contact, self.opportunity = self._records(self.sales, "Core")
        self.foreign_account, self.foreign_contact, self.foreign_opportunity = self._records(
            self.other_sales, "Foreign",
        )

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def test_import_form_endpoint_gates_on_the_create_capability(self):
        """The form import must not depend on table create/write, which no CRM role holds."""

        from io import BytesIO

        from werkzeug.datastructures import FileStorage, MultiDict

        from rayher_crm.api.v1.demo_requests import import_form

        def call_as(user: str) -> dict:
            frappe.set_user(user)
            previous = getattr(frappe.local, "request", None)
            frappe.local.request = frappe._dict(files=MultiDict([(
                "file", FileStorage(BytesIO(b""), filename="form.pdf", content_type="application/pdf"),
            )]))
            frappe.local.response = frappe._dict()
            try:
                return import_form()
            finally:
                frappe.local.request = previous

        # Sales and Managers may create Demo Requests: the gate opens and the empty upload is
        # rejected by the parser, not by permissions.
        for user in (self.sales, self.manager):
            self.assertEqual(call_as(user)["error"]["code"], "VALIDATION_ERROR", user)
        # Engineers cannot create Demo Requests, so they are refused before any parsing.
        self.assertEqual(call_as(self.engineer)["error"]["code"], "PERMISSION_DENIED")

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

    def _records(self, owner: str, suffix: str):
        frappe.set_user(owner)
        # Every test of the class makes this Account again in the one transaction: the same name, confirmed.
        account = create_account({
            "name": f"Demo {suffix}", "shortName": suffix, "segment": "Frontend", "tier": "A",
            "city": "Shanghai", "region": "East China", "owner": owner, "confirmDuplicate": True,
        })
        site = create_site(account["id"], {
            "name": f"{suffix} Demo Site", "city": "Shanghai", "type": "Fab",
            "process": "Frontend", "status": "量产",
        })
        contact = create_contact({
            "accountId": account["id"], "siteId": site["id"], "name": f"{suffix} Demo Contact",
            "title": "Director", "department": "Engineering", "phone": "13800000002",
            "email": f"demo-{suffix.lower()}@example.invalid", "relationship": "Developing",
            "owner": owner, "status": "Active",
        })
        opportunity = create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": account["id"], "siteId": site["id"], "title": f"{suffix} Demo Opportunity",
            "owner": owner, "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": 200000,
            "probability": 40, "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": 200000, "amountCny": 200000, "qualificationConfirmed": True,
        })
        return account, contact, opportunity

    def _form(self, sales: str | None = None, engineer: str | None = None) -> dict:
        return {
            "contactPerson": "client-forged display must be ignored", "industry": "Frontend Fab",
            "salesContact": sales or self.sales, "demoOwner": engineer or self.engineer,
            "sizeShape": "300 mm", "material": "Si(100)", "specificRequest": "Edge exclusion",
            "detectMeasure": "Detect particles", "expectedResults": "Wafer map",
            "otherTools": "Tool of record", "primaryTool": "Inspection 3000", "complementaryTool": "",
            "timing": "2026-12-20", "keySuccessFactors": "Capture above 95%",
            "internalQuestions": "Confirm recipe", "customerQuestions": "Confirm sample readiness",
            "wafers": [{
                "slotId": "1", "wid": "LOT-1-W01", "waferSpecificity": "Si wafer",
                "notchFlat": "Notch up", "doiMetrologyItems": "Particles",
                "resultFileProvided": "Wafer map",
            }],
        }

    def _input(self, **overrides) -> dict:
        payload = {
            "accountId": self.account["id"], "primaryContactId": self.contact["id"],
            "opportunityId": self.opportunity["id"], "requirementId": "REQ-STABLE-1",
            "formData": self._form(), "customerExpectedDate": "2026-12-31", "submit": False,
        }
        payload.update(overrides)
        return payload

    def _new_opportunity(self, suffix: str) -> dict:
        frappe.set_user(self.sales)
        return create_strategy_opportunity({
            "probabilityLevel": "pipeline",
            "accountId": self.account["id"], "siteId": self.opportunity["siteId"],
            "title": f"Demo {suffix} Opportunity", "owner": self.sales,
            "stage": QUALIFIED_OPPORTUNITY, "forecast": "Pipeline", "amount": 200000,
            "intentScore": 70, "poDate": "2026-12-31", "toolType": "Inspection",
            "saleType": "New Equipment", "subRegion": "East China", "currency": "CNY",
            "originalAmount": 200000, "amountCny": 200000, "qualificationConfirmed": True,
        })

    def test_direct_create_submit_keeps_workflow_when_notice_is_unreachable(self):
        frappe.set_user(self.sales)
        with patch("rayher_crm.services.notifications.can_read_source", return_value=False):
            request = create_demo_request(self._input(submit=True))
        self.assertEqual(request["status"], "Engineer Review")
        self.assertEqual(frappe.db.get_value("CRM Demo Request", request["id"], "status"), "Engineer Review")
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM Demo Request", "source_name": request["id"],
        }))

    def test_direct_update_submit_keeps_workflow_when_notice_is_unreachable(self):
        frappe.set_user(self.sales)
        draft = create_demo_request(self._input())
        with patch("rayher_crm.services.notifications.can_read_source", return_value=False):
            request = update_demo_request(draft["id"], self._input(submit=True), draft["modified"])
        self.assertEqual(request["status"], "Engineer Review")
        self.assertEqual(frappe.db.get_value("CRM Demo Request", request["id"], "status"), "Engineer Review")
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_doctype": "CRM Demo Request", "source_name": request["id"],
        }))

    def test_create_draft_and_submit_are_server_owned_and_derive_contact(self):
        frappe.set_user(self.sales)
        draft = create_demo_request(self._input())
        self.assertRegex(draft["id"], r"^CRM-DR-\d{5}$")
        self.assertEqual(draft["status"], "Draft")
        self.assertEqual(draft["createdBy"], self.sales)
        self.assertEqual(draft["salesOwner"], self.sales)
        self.assertEqual(draft["engineerOwner"], self.engineer)
        self.assertEqual(draft["formData"]["contactPerson"], "Core Demo Contact, Director, demo-core@example.invalid, 13800000002")
        self.assertEqual(draft["title"], "Demo Core - Inspection 3000 Demo")
        self.assertEqual(draft["sampleQuantity"], 1)
        self.assertRegex(draft["createdAt"], r"Z$")
        self.assertRegex(draft["modified"], r"Z$")
        self.assertEqual(draft["history"][-1]["actor"], self.sales)
        self.assertEqual(draft["history"][-1]["to"], "Draft")
        # A Demo Request does not move the Opportunity; the Customer Review of its Demo Test does.
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.opportunity["id"], "stage"),
            QUALIFIED_OPPORTUNITY,
        )
        self.assertEqual(
            frappe.get_all(
                "CRM Opportunity Stage History", filters={"opportunity": self.opportunity["id"]}, pluck="event",
            ),
            ["created"],
        )

        submitted = transition_demo_request(draft["id"], {"type": "submit"})["request"]
        self.assertEqual(submitted["status"], "Engineer Review")
        self.assertEqual(submitted["feasibility"], "Pending")
        self.assertEqual(
            frappe.db.count(
                "CRM Opportunity Stage History",
                {"opportunity": self.opportunity["id"]},
            ),
            1,
        )

    def test_review_stages_notify_the_assigned_engineer_and_active_managers(self):
        frappe.set_user(self.sales)
        direct = create_demo_request(self._input(
            submit=True,
            opportunityId=self._new_opportunity("Direct notification")["id"],
        ))
        engineer_event = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Demo Request", "source_name": direct["id"]},
            fields=["recipient_user", "category", "title", "route"],
        )
        self.assertTrue(any(
            row.recipient_user == self.engineer
            and row.category == "Demo"
            and row.title == "Demo Request requires engineering review"
            and row.route == f"/demo-workflow/{direct['id']}?tab=information"
            for row in engineer_event
        ))

        draft = create_demo_request(self._input(
            opportunityId=self._new_opportunity("Transition notification")["id"],
        ))
        transition_demo_request(draft["id"], {"type": "submit"})
        self.assertTrue(frappe.db.exists("CRM Notification Event", {
            "source_name": draft["id"], "recipient_user": self.engineer,
        }))

        frappe.set_user(self.engineer)
        transition_demo_request(draft["id"], self._engineer_approval())
        self.assertTrue(frappe.db.exists("CRM Notification Event", {
            "source_name": draft["id"], "recipient_user": self.manager,
        }))

    def test_create_requires_opportunity_and_rolls_back_request_stage_and_history(self):
        frappe.set_user(self.sales)
        missing_link = self._input()
        missing_link.pop("opportunityId")
        with self.assertRaises(CrmApiException) as required:
            create_demo_request(missing_link)
        self.assertEqual(required.exception.code, "VALIDATION_ERROR")
        self.assertEqual(required.exception.field_errors, {"opportunityId": "Required"})

        before_requests = frappe.db.count("CRM Demo Request", {"account": self.account["id"]})
        before_history = frappe.db.count(
            "CRM Opportunity History", {"opportunity": self.opportunity["id"]},
        )

        def fail_after_advance(stage: str) -> None:
            if stage == "after_opportunity_advance":
                raise RuntimeError("injected create rollback")

        with self.assertRaisesRegex(RuntimeError, "injected create rollback"):
            create_demo_request(
                self._input(requirementId="REQ-CREATE-ROLLBACK"),
                failure_injector=fail_after_advance,
            )
        self.assertEqual(
            frappe.db.count("CRM Demo Request", {"account": self.account["id"]}),
            before_requests,
        )
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.opportunity["id"], "stage"),
            QUALIFIED_OPPORTUNITY,
        )
        self.assertEqual(
            frappe.db.count("CRM Opportunity History", {"opportunity": self.opportunity["id"]}),
            before_history,
        )

    def test_rejects_a_second_active_request_for_the_same_opportunity(self):
        frappe.set_user(self.sales)
        first = create_demo_request(self._input(requirementId="REQ-ACTIVE-1"))
        with self.assertRaises(CrmApiException) as duplicate:
            create_demo_request(self._input(requirementId="REQ-ACTIVE-2"))
        self.assertEqual(duplicate.exception.code, "CONFLICT")
        self.assertEqual(
            frappe.db.count("CRM Demo Request", {"opportunity": self.opportunity["id"]}),
            1,
        )

        transition_demo_request(first["id"], {"type": "cancel", "comment": "Start a replacement request"})
        replacement = create_demo_request(self._input(requirementId="REQ-ACTIVE-3"))
        self.assertNotEqual(replacement["id"], first["id"])

    def test_create_is_limited_to_qualified_and_demo_done_opportunities(self):
        demo_done = advance_opportunity_fixture(self._new_opportunity("Demo done"), DEMO_DONE)
        request = create_demo_request(self._input(requirementId="REQ-DEMO-DONE", opportunityId=demo_done["id"]))
        self.assertEqual(request["opportunityId"], demo_done["id"])
        self.assertEqual(frappe.db.get_value("CRM Opportunity", demo_done["id"], "stage"), DEMO_DONE)

        budget_approved = advance_opportunity_fixture(
            self._new_opportunity("Budget approved"), CUSTOMER_BUDGET_APPROVED,
        )
        lost = self._new_opportunity("Marked lost")
        lost = mark_opportunity_lost(lost["id"], {"lostReason": "Customer stopped the project."}, lost["modified"])
        for opportunity in (budget_approved, lost):
            with self.subTest(stage=opportunity["stage"]), self.assertRaises(CrmApiException) as blocked:
                create_demo_request(self._input(
                    requirementId=f"REQ-{opportunity['stage']}", opportunityId=opportunity["id"],
                ))
            self.assertEqual(blocked.exception.code, "INVALID_TRANSITION")
            self.assertEqual(frappe.db.count("CRM Demo Request", {"opportunity": opportunity["id"]}), 0)

    def test_a_long_tool_name_does_not_overflow_the_title_the_service_puts_together(self):
        frappe.set_user(self.sales)
        payload = self._input(requestMode="Self Test")
        payload.pop("opportunityId")
        payload.pop("primaryContactId")
        payload["formData"]["industry"] = ""
        # "Self Test - " and " Demo" around a tool name of 130 make 147: more than the title's column.
        payload["formData"]["primaryTool"] = "T" * 130
        request = create_demo_request(payload)
        stored = frappe.db.get_value("CRM Demo Request", request["id"], ["title", "requested_equipment"])
        self.assertEqual(stored, (("Self Test - " + "T" * 130 + " Demo")[:140], "T" * 130))

        # A tool name that is itself too long is refused as that field, not as the title.
        payload["formData"]["primaryTool"] = "T" * 141
        with self.assertRaises(frappe.CharacterLengthExceededError) as refused:
            create_demo_request(payload)
        self.assertIn("Requested Equipment", str(refused.exception))

    def test_self_test_requires_no_opportunity_and_preserves_opportunity_stages(self):
        frappe.set_user(self.sales)
        before_stages = frappe.get_all(
            "CRM Opportunity", fields=["name", "stage"], order_by="name asc",
        )
        payload = self._input(requestMode="Self Test")
        payload.pop("opportunityId")
        payload.pop("primaryContactId")
        payload["formData"]["industry"] = ""
        request = create_demo_request(payload)
        self.assertEqual(request["requestMode"], "Self Test")
        self.assertEqual(request["primaryContactId"], "")
        self.assertNotIn("opportunityId", request)

        edit_payload = copy.deepcopy(payload)
        edit_payload["requestMode"] = "Opportunity"
        edit_payload["opportunityId"] = self.opportunity["id"]
        with self.assertRaises(CrmApiException) as immutable_mode:
            update_demo_request(request["id"], edit_payload, request["modified"])
        self.assertEqual(immutable_mode.exception.code, "VALIDATION_ERROR")

        transition_demo_request(request["id"], {"type": "submit"})
        frappe.set_user(self.engineer)
        transition_demo_request(request["id"], self._engineer_approval())
        frappe.set_user(self.manager)
        approved = transition_demo_request(
            request["id"], {"type": "manager_approve", "comment": "Approved self test"},
        )
        self.assertEqual(approved["request"]["status"], "Converted")
        self.assertEqual(approved["request"]["requestMode"], "Self Test")
        self.assertIsNotNone(approved["evaluation"])
        after_stages = frappe.get_all(
            "CRM Opportunity", fields=["name", "stage"], order_by="name asc",
        )
        self.assertEqual(after_stages, before_stages)

    def test_links_form_dates_and_owner_ids_are_validated(self):
        frappe.set_user(self.sales)
        cases = [
            # A Contact of someone else's Private Account answers as one that does not exist.
            (self._input(primaryContactId=self.foreign_contact["id"]), "NOT_FOUND"),
            (self._input(opportunityId=self.foreign_opportunity["id"]), "VALIDATION_ERROR"),
            (self._input(customerExpectedDate="2026-02-30"), "VALIDATION_ERROR"),
            (self._input(formData={**self._form(), "timing": "next quarter"}), "VALIDATION_ERROR"),
            (self._input(formData={**self._form(), "material": ""}), "VALIDATION_ERROR"),
            (self._input(formData=self._form(sales=self.other_sales)), "SCOPE_DENIED"),
            (self._input(formData=self._form(engineer=self.other_sales)), "VALIDATION_ERROR"),
        ]
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaises(CrmApiException) as error:
                create_demo_request(payload)
            self.assertEqual(error.exception.code, code)

        frappe.db.set_value("Contact", self.contact["id"], "custom_crm_status", "Archived")
        with self.assertRaises(CrmApiException) as inactive:
            create_demo_request(self._input())
        self.assertEqual(inactive.exception.code, "VALIDATION_ERROR")

    def test_scoped_pagination_side_effect_free_reads_update_and_cas(self):
        frappe.set_user(self.sales)
        first = create_demo_request(self._input())
        second_input = self._input(requirementId="REQ-STABLE-2")
        second_input["opportunityId"] = self._new_opportunity("Pagination")["id"]
        second_input["formData"] = copy.deepcopy(second_input["formData"])
        second_input["formData"]["wafers"][0]["wid"] = "LOT-2-W01"
        second = create_demo_request(second_input)
        before = frappe.db.get_value("CRM Demo Request", first["id"], "modified")
        items, total, page, page_size = list_demo_requests({
            "accountId": self.account["id"], "page": 1, "pageSize": 1,
        })
        self.assertEqual((len(items), total, page, page_size), (1, 2, 1, 1))
        # Asked for what is in progress, the list leaves out a request that became a Demo or was cancelled,
        # and counts and pages only the rest.
        for status, expected in (("Converted", [first["id"]]), ("Cancelled", [first["id"]]), ("Engineer Review", [second["id"], first["id"]])):
            frappe.db.set_value("CRM Demo Request", second["id"], "status", status, update_modified=False)
            for flag in ("1", "true"):
                items, total, _page, _page_size = list_demo_requests({"accountId": self.account["id"], "inProgress": flag, "page": 1, "pageSize": 1})
                self.assertEqual(([item["id"] for item in items], total), (expected[:1], len(expected)))
            self.assertEqual(list_demo_requests({"accountId": self.account["id"], "inProgress": "0"})[1], 2)
            self.assertEqual(list_demo_requests({"accountId": self.account["id"]})[1], 2)
        frappe.db.set_value("CRM Demo Request", second["id"], "status", "Draft", update_modified=False)
        self.assertEqual(get_demo_request(first["id"])["id"], first["id"])
        self.assertEqual(frappe.db.get_value("CRM Demo Request", first["id"], "modified"), before)

        with self.assertRaises(CrmApiException) as stale:
            update_demo_request(first["id"], self._input(), "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        updated_input = self._input(customerExpectedDate="2027-01-15")
        updated = update_demo_request(first["id"], updated_input, first["modified"])
        self.assertEqual(updated["customerExpectedDate"], "2027-01-15")
        self.assertEqual(updated["history"][-1]["from"], "Draft")

        reassigned = self._input()
        reassigned["opportunityId"] = second_input["opportunityId"]
        with self.assertRaises(CrmApiException) as immutable_link:
            update_demo_request(first["id"], reassigned, updated["modified"])
        self.assertEqual(immutable_link.exception.code, "VALIDATION_ERROR")
        self.assertEqual(
            frappe.db.get_value("CRM Demo Request", first["id"], "opportunity"),
            first["opportunityId"],
        )

        frappe.set_user(self.other_sales)
        self.assertNotIn(first["id"], {item["id"] for item in list_demo_requests({})[0]})
        with self.assertRaises(CrmApiException) as denied:
            get_demo_request(second["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

    def test_transition_rejects_a_stale_browser_version(self):
        frappe.set_user(self.sales)
        request = create_demo_request(self._input())
        with self.assertRaises(CrmApiException) as stale:
            transition_demo_request(
                request["id"], {"type": "submit"}, "2000-01-01T00:00:00Z",
            )
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        submitted = transition_demo_request(
            request["id"], {"type": "submit"}, request["modified"],
        )["request"]
        self.assertEqual(submitted["status"], "Engineer Review")

    def test_comments_are_scoped_server_owned_ordered_and_validate_mentions(self):
        frappe.set_user(self.sales)
        request = create_demo_request(self._input())
        # A mentioned user must read the request, which its Engineer does once it is submitted.
        with self.assertRaises(CrmApiException) as unsubmitted:
            add_demo_comment(request["id"], {"body": "ping", "mentionedPersonIds": [self.engineer]})
        self.assertIn("access to this Demo Request", unsubmitted.exception.public_message)
        transition_demo_request(request["id"], {"type": "submit"})
        comment = add_demo_comment(request["id"], {
            "body": "  Please review  ",
            "mentionedPersonIds": [self.engineer, self.manager, self.engineer],
        })
        self.assertEqual(comment["author"], self.sales)
        self.assertEqual(comment["role"], "Sales")
        self.assertEqual(comment["body"], "Please review")
        self.assertEqual(comment["mentionedPersonId"], self.engineer)
        self.assertEqual(
            [person["id"] for person in comment["mentionedPeople"]],
            [self.engineer, self.manager],
        )
        self.assertRegex(comment["createdAt"], r"Z$")
        notifications = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "CRM Demo Comment", "source_name": comment["id"]},
            fields=["recipient_user", "category", "route"],
        )
        self.assertEqual({row.recipient_user for row in notifications}, {self.engineer, self.manager})
        self.assertTrue(all(row.category == "Demo" for row in notifications))
        self.assertTrue(all(row.route == f"/demo-workflow/{request['id']}?tab=comment" for row in notifications))
        frappe.set_user(self.engineer)
        self.assertEqual(get_demo_request(request["id"])["id"], request["id"])
        frappe.set_user(self.sales)

        with self.assertRaises(CrmApiException) as empty:
            add_demo_comment(request["id"], {"body": "  "})
        self.assertEqual(empty.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as invalid_user:
            add_demo_comment(request["id"], {"body": "ping", "mentionedPersonIds": ["missing@example.invalid"]})
        self.assertEqual(invalid_user.exception.code, "VALIDATION_ERROR")
        with self.assertRaises(CrmApiException) as inaccessible_user:
            add_demo_comment(request["id"], {"body": "ping", "mentionedPersonIds": [self.other_sales]})
        self.assertEqual(
            inaccessible_user.exception.code, "VALIDATION_ERROR",
        )
        self.assertIn("access to this Demo Request", inaccessible_user.exception.public_message)

        second = add_demo_comment(request["id"], {"body": "Second"})
        self.assertEqual([item["id"] for item in list_demo_comments(request["id"])], [second["id"], comment["id"]])
        frappe.set_user(self.other_sales)
        with self.assertRaises(CrmApiException) as denied:
            list_demo_comments(request["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

    def test_an_engineer_reads_a_demo_request_once_sales_have_submitted_it(self):
        frappe.set_user(self.sales)
        draft = create_demo_request(self._input())
        cancelled = create_demo_request(self._input(
            requirementId="REQ-CANCELLED-DRAFT", opportunityId=self._new_opportunity("Cancelled Draft")["id"],
        ))
        transition_demo_request(cancelled["id"], {"type": "cancel", "comment": "Not needed after all"})
        # Both name the Engineer as the demo owner; neither was ever submitted to them, so the Engineer hears
        # nothing of the cancellation either.
        self.assertEqual(frappe.db.count("CRM Notification Event", {
            "source_doctype": "CRM Demo Request", "source_name": cancelled["id"], "recipient_user": self.engineer,
        }), 0)
        frappe.set_user(self.engineer)
        listed = {item["id"] for item in list_demo_requests({})[0]}
        self.assertEqual(listed & {draft["id"], cancelled["id"]}, set())
        for name in (draft["id"], cancelled["id"]):
            with self.assertRaises(CrmApiException) as hidden:
                get_demo_request(name)
            self.assertEqual(hidden.exception.code, "SCOPE_DENIED", name)
        self.assertFalse(frappe.has_permission("CRM Demo Request", "read", doc=draft["id"], user=self.engineer))

        frappe.set_user(self.sales)
        transition_demo_request(draft["id"], {"type": "submit"})
        frappe.set_user(self.engineer)
        self.assertEqual(get_demo_request(draft["id"])["status"], "Engineer Review")
        self.assertIn(draft["id"], {item["id"] for item in list_demo_requests({})[0]})
        # Returned to Sales, the request stays with the Engineer who reviewed it, and they hear of its end.
        transition_demo_request(draft["id"], {"type": "engineer_return", "comment": "Need the wafer map"})
        self.assertEqual(get_demo_request(draft["id"])["status"], "Engineer Returned")
        frappe.set_user(self.sales)
        transition_demo_request(draft["id"], {"type": "cancel", "comment": "Customer withdrew"})
        self.assertEqual(frappe.db.count("CRM Notification Event", {
            "source_doctype": "CRM Demo Request", "source_name": draft["id"], "recipient_user": self.engineer,
            "title": "Demo Request moved to Cancelled",
        }), 1)
        frappe.set_user(self.engineer)
        self.assertEqual(get_demo_request(draft["id"])["status"], "Cancelled")

    def test_the_backfill_records_the_submission_of_requests_written_in_past_draft(self):
        from rayher_crm.patches.v1_0.backfill_demo_request_submissions import execute

        # Written in at Manager Approval, as the staging generator and a hand migration do: no submission entry.
        frappe.set_user("Administrator")
        written_in = frappe.get_doc({
            "doctype": "CRM Demo Request", "account": self.account["id"], "primary_contact": self.contact["id"],
            "opportunity": self.opportunity["id"], "sales_owner": self.sales, "created_by_user": self.sales,
            "title": "Written in at approval", "objective": "Backfill", "requested_equipment": "Inspection 3000",
            "sample_type": "Si", "sample_quantity": 1, "target_date": "2026-12-20",
            "customer_expected_date": "2026-12-31", "priority": "High", "acceptance_criteria": "Capture above 95%",
            "status": "Manager Approval", "engineer_owner": self.engineer, "form_data": {},
        }).insert(ignore_permissions=True)
        frappe.set_user(self.sales)
        draft = create_demo_request(self._input(
            requirementId="REQ-BACKFILL-DRAFT", opportunityId=self._new_opportunity("Backfill")["id"],
        ))
        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException):
            get_demo_request(written_in.name)

        frappe.set_user("Administrator")
        execute()
        execute()
        self.assertEqual(frappe.db.count(
            "CRM Demo Request History", {"demo_request": written_in.name, "to_status": "Engineer Review"},
        ), 1)
        self.assertEqual(frappe.db.count(
            "CRM Demo Request History", {"demo_request": draft["id"], "to_status": "Engineer Review"},
        ), 0)
        frappe.set_user(self.engineer)
        self.assertEqual(get_demo_request(written_in.name)["status"], "Manager Approval")

    def _engineer_approval(self, engineer: str | None = None) -> dict:
        return {
            "type": "engineer_approve", "engineerOwner": engineer or self.engineer,
            "testPlan": "Run particle recipe", "assignedEquipment": "Inspection 3000",
            "resourceWindow": "Week 48", "estimatedCompletionDate": "2026-12-20",
            "technicalRisk": "Sample contamination", "comment": "Feasible",
        }

    def test_role_state_machine_reassignment_and_history_actor(self):
        frappe.set_user(self.sales)
        request = create_demo_request(self._input(submit=True))
        with self.assertRaises(frappe.PermissionError):
            transition_demo_request(request["id"], {"type": "engineer_return", "comment": "Missing data"})

        frappe.set_user(self.engineer)
        returned = transition_demo_request(
            request["id"], {"type": "engineer_return", "comment": "Need sample map"},
        )["request"]
        self.assertEqual((returned["status"], returned["feasibility"]), ("Engineer Returned", "Need More Info"))
        self.assertEqual(returned["history"][-1]["actor"], self.engineer)

        frappe.set_user(self.sales)
        reviewed = transition_demo_request(request["id"], {"type": "submit"})["request"]
        self.assertEqual(reviewed["status"], "Engineer Review")

        frappe.set_user(self.engineer)
        with self.assertRaises(CrmApiException) as reassign:
            transition_demo_request(request["id"], self._engineer_approval(self.other_engineer))
        self.assertEqual(reassign.exception.code, "PERMISSION_DENIED")
        approved = transition_demo_request(request["id"], self._engineer_approval())["request"]
        self.assertEqual((approved["status"], approved["managerDecision"]), ("Manager Approval", "Pending"))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            transition_demo_request(request["id"], {"type": "manager_approve", "comment": "forged"})

        frappe.set_user(self.manager)
        rejected = transition_demo_request(
            request["id"], {"type": "manager_reject", "comment": "Adjust schedule"},
        )["request"]
        self.assertEqual((rejected["status"], rejected["managerDecision"]), ("Manager Rejected", "Rejected"))

        frappe.set_user(self.sales)
        transition_demo_request(request["id"], {"type": "submit"})
        frappe.set_user(self.manager)
        manager_review = transition_demo_request(
            request["id"], self._engineer_approval(self.other_engineer),
        )["request"]
        self.assertEqual(manager_review["engineerOwner"], self.other_engineer)
        result = transition_demo_request(request["id"], {"type": "manager_approve", "comment": "Approved"})
        self.assertEqual(result["request"]["status"], "Converted")
        self.assertEqual(result["request"]["approvedBy"], self.manager)
        self.assertRegex(result["evaluation"]["id"], r"^CRM-EVAL-\d{5}$")
        self.assertEqual(result["evaluation"]["owner"], self.other_engineer)
        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", self.opportunity["id"], "stage"),
            QUALIFIED_OPPORTUNITY,
        )
        with self.assertRaises(CrmApiException) as duplicate:
            transition_demo_request(request["id"], {"type": "manager_approve", "comment": "Again"})
        self.assertEqual(duplicate.exception.code, "REPORT_NOT_READY")

    def test_transition_skips_a_recipient_who_lost_source_scope(self):
        frappe.set_user(self.sales)
        request = create_demo_request(self._input(submit=True))
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Customer", self.account["id"],
            {"custom_crm_owner": self.other_sales, "custom_crm_visibility": "Private"},
        )
        frappe.set_user(self.engineer)
        returned = transition_demo_request(
            request["id"], {"type": "engineer_return", "comment": "Please update the sample map"},
        )["request"]
        self.assertEqual(returned["status"], "Engineer Returned")
        self.assertFalse(frappe.db.exists("CRM Notification Event", {
            "source_name": request["id"], "recipient_user": self.sales,
            "title": "Demo Request moved to Engineer Returned",
        }))

    def test_invalid_transitions_and_required_review_fields_do_not_partially_write(self):
        frappe.set_user(self.sales)
        draft = create_demo_request(self._input())
        before_modified = draft["modified"]
        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as invalid:
            transition_demo_request(draft["id"], {"type": "manager_reject", "comment": "No"})
        self.assertEqual(invalid.exception.code, "INVALID_TRANSITION")
        self.assertEqual(get_demo_request(draft["id"])["modified"], before_modified)

        frappe.set_user(self.sales)
        transition_demo_request(draft["id"], {"type": "submit"})
        frappe.set_user(self.engineer)
        incomplete = self._engineer_approval()
        incomplete["testPlan"] = ""
        with self.assertRaises(CrmApiException) as required:
            transition_demo_request(draft["id"], incomplete)
        self.assertEqual(required.exception.code, "VALIDATION_ERROR")
        self.assertEqual(get_demo_request(draft["id"])["status"], "Engineer Review")

    def test_manager_approval_failure_rolls_back_evaluation_request_and_history(self):
        for failure_stage in ("after_evaluation_insert", "after_request_update", "after_notification_insert"):
            frappe.set_user(self.sales)
            linked_opportunity = self._new_opportunity(failure_stage)
            request = create_demo_request(self._input(
                submit=True, requirementId=f"REQ-{failure_stage}", opportunityId=linked_opportunity["id"],
            ))
            frappe.set_user(self.engineer)
            transition_demo_request(request["id"], self._engineer_approval())
            frappe.set_user(self.manager)
            before_history = frappe.db.count("CRM Demo Request History", {"demo_request": request["id"]})
            before_notifications = frappe.db.count("CRM Notification Event", {"source_name": request["id"]})

            def fail_at(stage: str) -> None:
                if stage == failure_stage:
                    raise RuntimeError(f"injected {failure_stage}")

            with self.assertRaisesRegex(RuntimeError, f"injected {failure_stage}"):
                transition_demo_request(
                    request["id"], {"type": "manager_approve", "comment": "Approve"},
                    failure_injector=fail_at,
                )
            self.assertEqual(frappe.db.count("CRM Evaluation", {"demo_request": request["id"]}), 0)
            self.assertEqual(frappe.db.get_value("CRM Demo Request", request["id"], "status"), "Manager Approval")
            self.assertFalse(frappe.db.get_value("CRM Demo Request", request["id"], "evaluation"))
            self.assertEqual(
                frappe.db.get_value("CRM Opportunity", linked_opportunity["id"], "stage"),
                QUALIFIED_OPPORTUNITY,
            )
            self.assertEqual(
                frappe.db.count("CRM Demo Request History", {"demo_request": request["id"]}), before_history,
            )
            self.assertEqual(
                frappe.db.count("CRM Notification Event", {"source_name": request["id"]}), before_notifications,
            )
