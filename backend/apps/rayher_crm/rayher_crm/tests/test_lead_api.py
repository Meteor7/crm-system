from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from rayher_crm.api.v1.errors import CrmApiException
from rayher_crm.api.v1.leads import create_lead as create_lead_endpoint
from rayher_crm.services.accounts import create_account, get_account_360
from rayher_crm.services.contacts import create_contact, get_contact
from rayher_crm.services.leads import (
    ARCHIVED_LEAD_CONVERT,
    ARCHIVED_LEAD_EDIT,
    CONVERTED_LEAD_ARCHIVE,
    DUPLICATE_LEAD_EMAIL,
    MAX_ACTIVITIES,
    _duplicate_email,
    archive_lead,
    convert_lead,
    create_lead,
    get_lead,
    list_leads,
    unarchive_lead,
    update_lead,
)
from rayher_crm.services.opportunities import get_strategy_opportunity
from rayher_crm.services.opportunity_stages import QUALIFIED_OPPORTUNITY
from rayher_crm.services.sites import create_site


class TestLeadApi(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-lead-sales@example.invalid", "CRM Sales")
        self.other_sales = self._user("crm-lead-other@example.invalid", "CRM Sales")
        self.manager = self._user("crm-lead-manager@example.invalid", "CRM Manager")

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
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@", 1)[0],
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True).name

    def _input(self, name: str, owner: str | None = None, **overrides) -> dict:
        payload = {
            "name": name,
            "company": f"{name} Semiconductor",
            "title": "Process Manager",
            "phone": "13800000004",
            "email": f"{name.replace(' ', '.').lower()}@example.invalid",
            "source": "Trade Show",
            "status": "New",
            "owner": owner or frappe.session.user,
            "interest": "Advanced packaging inspection",
            "firstContactNote": "Met at exhibition",
            "nextAction": "Arrange discovery call",
            "nextActionDue": "2026-08-20",
            "activities": [],
        }
        payload.update(overrides)
        return payload

    def test_lead_create_list_update_and_endpoint_envelope(self):
        frappe.set_user(self.sales)
        created = create_lead(self._input("Lead Vertical Slice"))
        self.assertTrue(created["id"])
        self.assertEqual(created["owner"], self.sales)
        self.assertEqual(created["status"], "New")
        self.assertRegex(created["modified"], r"Z$")

        items, total, page, page_size = list_leads(
            {
                "search": "Vertical Slice",
                "status": "New",
                "source": "Trade Show",
                "owner": "All",
                "page": 1,
                "pageSize": 100000,
            }
        )
        self.assertIn(created["id"], {item["id"] for item in items})
        self.assertGreaterEqual(total, 1)
        self.assertEqual((page, page_size), (1, 200))

        with self.assertRaises(CrmApiException) as stale:
            update_lead(created["id"], self._input("Stale Lead"), "2000-01-01T00:00:00Z")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        updated = update_lead(
            created["id"],
            self._input("Lead Vertical Slice", status="Working", firstContactNote="Discovery completed"),
            created["modified"],
        )
        self.assertEqual(updated["status"], "Working")
        self.assertEqual(updated["firstContactNote"], "Discovery completed")
        self.assertNotEqual(updated["modified"], created["modified"])

        endpoint = create_lead_endpoint(self._input("Endpoint Lead"))
        self.assertEqual(endpoint["data"]["name"], "Endpoint Lead")
        self.assertRegex(endpoint["meta"]["requestId"], r"^req_[0-9a-f]{24}$")

    def test_a_next_action_with_markup_in_it_is_the_same_arrangement_when_the_form_sends_it_back(self):
        frappe.set_user(self.sales)
        # Frappe stores the next action with "<" escaped; the form sends it back as stored. The arrangement is one.
        plain_input = self._input("Escaped Timeline Lead", nextAction="Contact <sales@example.invalid>", nextActionDue="2026-08-20")
        del plain_input["activities"]
        created = create_lead(plain_input)
        self.assertEqual([item["action"] for item in created["activities"]], ["Contact <sales@example.invalid>"])
        stored = get_lead(created["id"])
        payload = self._input("Escaped Timeline Lead", nextAction=stored["nextAction"], nextActionDue="2026-08-20", title="Senior Process Manager")
        del payload["activities"]
        edited = update_lead(created["id"], payload, stored["modified"])
        self.assertEqual((edited["title"], [item["action"] for item in edited["activities"]]), ("Senior Process Manager", ["Contact <sales@example.invalid>"]))
        # Re-dated the same way: still one, with the new date.
        redated = update_lead(created["id"], {**payload, "nextActionDue": "2026-08-27"}, edited["modified"])
        self.assertEqual([(item["action"], item["dueDate"]) for item in redated["activities"]], [("Contact <sales@example.invalid>", "2026-08-27")])

        # Entity text that is no markup ("&amp;lt;") is stored as written by Frappe and must stay one arrangement
        # through any number of plain saves.
        literal = "Explain &amp;lt; in the quote"
        literal_input = self._input("Literal Timeline Lead", nextAction=literal, nextActionDue="2026-08-20")
        del literal_input["activities"]
        first = create_lead(literal_input)
        self.assertEqual(([item["action"] for item in first["activities"]], get_lead(first["id"])["nextAction"]), ([literal], literal))
        stored_literal = get_lead(first["id"])
        again = self._input("Literal Timeline Lead", nextAction=stored_literal["nextAction"], nextActionDue="2026-08-20", title="Senior Process Manager")
        del again["activities"]
        once = update_lead(first["id"], again, stored_literal["modified"])
        twice = update_lead(first["id"], {**again, "title": "Principal Process Manager"}, once["modified"])
        self.assertEqual(([item["action"] for item in twice["activities"]], twice["title"]), ([literal], "Principal Process Manager"))

        # A wrapping tag Frappe drops leaves its spaces in the Data field, which the form's next save trims: one
        # arrangement still, through a plain save, a re-dating, and a plain save at the cap.
        wrapped_input = self._input("Wrapped Timeline Lead", nextAction="<body> Call </body>", nextActionDue="2026-08-20")
        del wrapped_input["activities"]
        wrapped = create_lead(wrapped_input)
        self.assertEqual([item["action"] for item in wrapped["activities"]], ["<body> Call </body>"])
        stored_wrapped = get_lead(wrapped["id"])
        plain = self._input("Wrapped Timeline Lead", nextAction=stored_wrapped["nextAction"], nextActionDue="2026-08-20", title="Senior Process Manager")
        del plain["activities"]
        kept = update_lead(wrapped["id"], plain, stored_wrapped["modified"])
        redated_wrapped = update_lead(wrapped["id"], {**plain, "nextActionDue": "2026-08-27"}, kept["modified"])
        self.assertEqual([(item["action"], item["dueDate"]) for item in redated_wrapped["activities"]], [("<body> Call </body>", "2026-08-27")])
        full = update_lead(wrapped["id"], {**plain, "activities": [*redated_wrapped["activities"][:1], *[{"action": f"Step {index:03d}", "dueDate": "2026-08-20"} for index in range(MAX_ACTIVITIES - 2)], {"action": "<body> Call </body>", "dueDate": "2026-08-27"}]}, redated_wrapped["modified"])
        self.assertEqual(len(full["activities"]), MAX_ACTIVITIES)
        at_cap = update_lead(wrapped["id"], {**plain, "title": "Principal Process Manager"}, full["modified"])
        self.assertEqual((len(at_cap["activities"]), at_cap["title"]), (MAX_ACTIVITIES, "Principal Process Manager"))

    def test_a_lead_full_of_arrangements_refuses_another_from_the_form(self):
        frappe.set_user(self.sales)
        full = [{"action": f"Step {index:03d}", "dueDate": "2026-08-20"} for index in range(MAX_ACTIVITIES)]
        latest = f"Step {MAX_ACTIVITIES - 1:03d}"
        created = create_lead(self._input("Full Timeline Lead", nextAction=latest, nextActionDue="2026-08-20", activities=full))
        self.assertEqual(len(created["activities"]), MAX_ACTIVITIES)
        payload = self._input("Full Timeline Lead", nextAction=latest, nextActionDue="2026-08-27")
        del payload["activities"]
        # The latest re-dated by the form: not an addition, nothing dropped.
        redated = update_lead(created["id"], payload, created["modified"])
        self.assertEqual(len(redated["activities"]), MAX_ACTIVITIES)
        self.assertEqual((redated["activities"][-1]["action"], redated["activities"][-1]["dueDate"]), (latest, "2026-08-27"))
        # Another one from the form: refused, as a list of more than the cap is, rather than the first dropped unasked.
        with self.assertRaises(CrmApiException) as refused:
            update_lead(created["id"], {**payload, "nextAction": "One more"}, redated["modified"])
        self.assertEqual(refused.exception.code, "VALIDATION_ERROR")
        self.assertIn("the most it can", refused.exception.public_message)
        kept = get_lead(created["id"])
        self.assertEqual(len(kept["activities"]), MAX_ACTIVITIES)
        self.assertEqual(kept["activities"][0]["action"], "Step 000")

    def test_a_lead_keeps_its_arrangements_and_adds_to_them(self):
        frappe.set_user(self.sales)
        # The Lead form sends the next action alone: it is recorded as the first arrangement.
        plain_input = self._input("Plain Timeline Lead")
        del plain_input["activities"]
        plain = create_lead(plain_input)
        self.assertEqual(plain["activities"], [{"id": f"{plain['id']}-ACT-001", "action": "Arrange discovery call", "dueDate": "2026-08-20"}])

        first = {"id": "client-made", "action": "Call procurement", "dueDate": "2026-08-20"}
        created = create_lead(self._input("Timeline Lead", activities=[first]))
        # Kept in order, with ids of the server's own; the client's id is not taken.
        self.assertEqual(created["activities"], [{"id": f"{created['id']}-ACT-001", "action": "Call procurement", "dueDate": "2026-08-20"}])

        # A second arrangement is added, as the detail page sends them: the ones shown and the new one (F2-04 had the
        # server drop them all and keep the last next action alone).
        second = {"action": " Send quote draft ", "dueDate": "2026-08-25"}
        updated = update_lead(created["id"], self._input(
            "Timeline Lead", nextAction="Send quote draft", nextActionDue="2026-08-25", activities=[*created["activities"], second],
        ), created["modified"])
        self.assertEqual(
            [(item["id"], item["action"], item["dueDate"]) for item in updated["activities"]],
            [(f"{created['id']}-ACT-001", "Call procurement", "2026-08-20"), (f"{created['id']}-ACT-002", "Send quote draft", "2026-08-25")],
        )
        self.assertEqual((updated["nextAction"], updated["nextActionDue"]), ("Send quote draft", "2026-08-25"))
        self.assertEqual(get_lead(created["id"])["activities"], updated["activities"])
        listed = next(item for item in list_leads({"search": "Timeline Lead", "page": 1, "pageSize": 50})[0] if item["id"] == created["id"])
        self.assertEqual(listed["activities"], updated["activities"])

        # An edit that says nothing of the arrangements (the Lead form) leaves them when the next action is the latest
        # of them; one that sets another next action records it as the latest (the form, then "增添安排", lost it
        # otherwise); one that re-dates it re-dates that arrangement. An empty list clears them.
        payload = self._input("Timeline Lead", nextAction="Send quote draft", nextActionDue="2026-08-25")
        del payload["activities"]
        kept = update_lead(created["id"], payload, updated["modified"])
        self.assertEqual(kept["activities"], updated["activities"])
        moved = update_lead(created["id"], {**payload, "nextAction": "Visit the fab", "nextActionDue": "2026-09-02"}, kept["modified"])
        self.assertEqual(
            [(item["action"], item["dueDate"]) for item in moved["activities"]],
            [("Call procurement", "2026-08-20"), ("Send quote draft", "2026-08-25"), ("Visit the fab", "2026-09-02")],
        )
        redated = update_lead(created["id"], {**payload, "nextAction": "Visit the fab", "nextActionDue": "2026-09-09"}, moved["modified"])
        self.assertEqual(
            [(item["id"], item["action"], item["dueDate"]) for item in redated["activities"]][2:],
            [(f"{created['id']}-ACT-003", "Visit the fab", "2026-09-09")],
        )
        cleared = update_lead(created["id"], {**payload, "activities": []}, redated["modified"])
        self.assertEqual(cleared["activities"], [])

        # An arrangement needs an action, a real date if any, and the list stays a list.
        for bad, message in (
            ([{"dueDate": "2026-09-01"}], "action is required"),
            ([{"action": {"text": "Visit"}}], "action must be a string"),
            ([{"action": "V" * 141}], "at most 140 characters"),
            # 140 as typed, 146 as Frappe stores it ("<x>" is escaped): too long for the next-action field.
            ([{"action": "<x>" + "V" * 137}], "at most 140 characters"),
            ([{"action": "Visit", "dueDate": "2026-13-01"}], "real YYYY-MM-DD"),
            ([{"action": "Visit", "dueDate": 20260901}], "YYYY-MM-DD"),
            ({"action": "Visit"}, "must be an array"),
        ):
            with self.assertRaises(CrmApiException) as refused:
                update_lead(created["id"], {**payload, "activities": bad}, cleared["modified"])
            self.assertEqual(refused.exception.code, "VALIDATION_ERROR")
            self.assertIn(message, refused.exception.public_message)
        self.assertEqual(get_lead(created["id"])["activities"], [])
        # A date is optional: an arrangement without one is kept with an empty date.
        dated = update_lead(created["id"], {**payload, "activities": [{"action": "Visit"}]}, cleared["modified"])
        self.assertEqual(dated["activities"], [{"id": f"{created['id']}-ACT-001", "action": "Visit", "dueDate": ""}])

    def test_manager_assignment_notifies_owner_who_can_open_lead(self):
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Assigned Lead", self.other_sales))
        notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "Lead", "source_name": lead["id"],
                     "recipient_user": self.other_sales},
            fields=["category", "route"], order_by="creation desc", limit=1,
        )[0]
        self.assertEqual((notice.category, notice.route), ("Lead", f"/leads/{lead['id']}"))
        frappe.set_user(self.other_sales)
        self.assertEqual(get_lead(lead["id"])["id"], lead["id"])

    def test_lead_validation_owner_forgery_and_scope(self):
        frappe.set_user(self.other_sales)
        foreign = create_lead(self._input("Foreign Lead"))

        frappe.set_user(self.sales)
        with self.assertRaises(CrmApiException) as forged:
            create_lead(self._input("Forged Lead", self.other_sales))
        self.assertEqual(forged.exception.code, "SCOPE_DENIED")

        with self.assertRaises(CrmApiException) as denied:
            get_lead(foreign["id"])
        self.assertEqual(denied.exception.code, "SCOPE_DENIED")

        with self.assertRaises(CrmApiException) as missing_channel:
            create_lead(self._input("No Channel", phone="", email=""))
        self.assertEqual(missing_channel.exception.code, "VALIDATION_ERROR")

        with self.assertRaises(CrmApiException) as bad_date:
            create_lead(self._input("Bad Date", nextActionDue="2026-02-31"))
        self.assertEqual(bad_date.exception.code, "VALIDATION_ERROR")

        invalid_email = create_lead_endpoint(self._input("Bad Email", email="123123123123@qq"))
        self.assertEqual(frappe.local.response["http_status_code"], 422)
        self.assertEqual(invalid_email["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(invalid_email["error"]["fieldErrors"], {"email": "Invalid email"})

    def test_get_and_list_are_read_only(self):
        frappe.set_user(self.sales)
        created = create_lead(self._input("Read Only Lead"))
        modified_before = frappe.db.get_value("Lead", created["id"], "modified")

        detail = get_lead(created["id"])
        list_leads({"search": "Read Only Lead", "page": 1, "pageSize": 20})

        self.assertEqual(detail["id"], created["id"])
        self.assertEqual(frappe.db.get_value("Lead", created["id"], "modified"), modified_before)

    def _listed(self, query: dict) -> set[str]:
        return {item["id"] for item in list_leads({**query, "pageSize": 200})[0]}

    def test_only_a_manager_archives_a_lead_and_the_archive_is_reversible(self):
        frappe.set_user(self.other_sales)
        lead = create_lead(self._input("Archive Lead"))

        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):
            archive_lead(lead["id"])
        self.assertEqual(frappe.db.get_value("Lead", lead["id"], "custom_crm_archived"), 0)

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as missing:
            archive_lead("LEAD-NOBODY")
        self.assertEqual(missing.exception.code, "NOT_FOUND")
        archived = archive_lead(lead["id"])
        self.assertTrue(archived["archived"])
        self.assertEqual(archived["archivedBy"], self.manager)
        self.assertRegex(archived["archivedAt"], r"Z$")
        self.assertEqual(archived["status"], "New")
        self.assertTrue(frappe.db.exists("Lead", lead["id"]))
        # Archived again, nothing changes.
        self.assertEqual(archive_lead(lead["id"])["archivedAt"], archived["archivedAt"])

        # Out of the list unless the archive is asked for.
        self.assertNotIn(lead["id"], self._listed({}))
        self.assertNotIn(lead["id"], self._listed({"archiveState": "active"}))
        self.assertIn(lead["id"], self._listed({"archiveState": "archived"}))
        self.assertIn(lead["id"], self._listed({"archiveState": "all"}))
        with self.assertRaises(CrmApiException) as invalid:
            list_leads({"archiveState": "deleted"})
        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")

        # The archive moved the Lead's version, so a page opened before it holds an older one, and left a comment
        # on the Lead (which keeps no versions): who, and when.
        self.assertNotEqual(archived["modified"], lead["modified"])
        comments = {"reference_doctype": "Lead", "reference_name": lead["id"], "comment_type": "Info"}
        self.assertEqual(frappe.get_all("Comment", filters=comments, pluck="content"), ["Archived"])

        # Its owner still opens it, cannot edit or convert it, and does not restore it. An edit prepared on the
        # page before the archive (the older version) is refused for the archive, not for the version; one
        # with a bad payload too.
        frappe.set_user(self.other_sales)
        self.assertTrue(get_lead(lead["id"])["archived"])
        self.assertIn(lead["id"], self._listed({"archiveState": "archived"}))
        changed = self._input("Archive Lead", owner=self.other_sales, interest="Changed while archived")
        for payload, version in ((changed, archived["modified"]), (changed, lead["modified"]), ({**changed, "source": "Nowhere"}, lead["modified"])):
            with self.assertRaises(CrmApiException) as edit:
                update_lead(lead["id"], payload, version)
            self.assertEqual((edit.exception.code, edit.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_LEAD_EDIT))
        conversion = self._conversion_input(
            newAccount=self._account_input("Archived Lead Account"),
            newSite=self._site_input("Archived Lead Site"),
            newContact=self._contact_input("placeholder", "Archived Lead Contact"),
        )
        with self.assertRaises(CrmApiException) as convert:
            convert_lead(lead["id"], conversion)
        self.assertEqual((convert.exception.code, convert.exception.public_message), ("INVALID_TRANSITION", ARCHIVED_LEAD_CONVERT))
        self.assertEqual(frappe.db.get_value("Lead", lead["id"], "custom_crm_status"), "New")
        self.assertFalse(frappe.db.exists("Customer", {"customer_name": "Archived Lead Account"}))
        with self.assertRaises(frappe.PermissionError):
            unarchive_lead(lead["id"])

        frappe.set_user(self.manager)
        restored = unarchive_lead(lead["id"])
        self.assertFalse(restored["archived"])
        self.assertNotIn("archivedAt", restored)
        self.assertNotIn("archivedBy", restored)
        self.assertEqual(
            frappe.db.get_value("Lead", lead["id"], ["custom_crm_archived", "custom_crm_archived_at", "custom_crm_archived_by"]),
            (0, None, None),
        )
        self.assertIn(lead["id"], self._listed({}))
        self.assertNotIn(lead["id"], self._listed({"archiveState": "archived"}))
        self.assertEqual(frappe.get_all("Comment", filters=comments, pluck="content", order_by="creation asc"), ["Archived", "Restored from the archive"])
        # Restored again, nothing changes; and back as it was, the Lead is edited again.
        self.assertEqual(unarchive_lead(lead["id"])["modified"], restored["modified"])
        frappe.set_user(self.other_sales)
        self.assertEqual(update_lead(lead["id"], changed, restored["modified"])["interest"], "Changed while archived")

    def test_the_archive_writes_its_columns_without_the_leads_validation(self):
        """A legacy pair of Leads with one email (allowed while CRM Settings let emails repeat) is archived and
        restored all the same: a full save would refuse the duplicate email; the archive writes its columns alone."""

        frappe.set_user(self.sales)
        frappe.db.set_single_value("CRM Settings", "allow_lead_duplication_based_on_emails", 1)
        try:
            first = create_lead(self._input("Twin Email One", email="twins@example.invalid"))
            second = create_lead(self._input("Twin Email Two", email="twins@example.invalid"))
        finally:
            frappe.db.set_single_value("CRM Settings", "allow_lead_duplication_based_on_emails", 0)
        # The validation is on again: a save of either Lead is refused for the email.
        with self.assertRaises(CrmApiException) as refused:
            update_lead(first["id"], self._input("Twin Email One", email="twins@example.invalid", interest="Saved"), first["modified"])
        self.assertEqual(refused.exception.code, "CONFLICT")

        frappe.set_user(self.manager)
        archived = archive_lead(first["id"])
        self.assertTrue(archived["archived"])
        restored = unarchive_lead(first["id"])
        self.assertFalse(restored["archived"])
        self.assertEqual(frappe.db.get_value("Lead", second["id"], ["email_id", "custom_crm_archived"]), ("twins@example.invalid", 0))
        # A conversion saves the Lead too: the twin refuses it the same way, and nothing it wrote before stays.
        frappe.set_user(self.sales)
        # The message log is the process's: the earlier tests of the class left theirs in it.
        frappe.clear_messages()
        with self.assertRaises(CrmApiException) as converted:
            convert_lead(first["id"], self._conversion_input(
                newAccount=self._account_input("Twin Email Account"),
                newSite=self._site_input("Twin Email Site"),
                newContact=self._contact_input("placeholder", "Twin Email Contact"),
            ))
        self.assertEqual((converted.exception.code, converted.exception.public_message), ("CONFLICT", DUPLICATE_LEAD_EMAIL))
        self.assertFalse(frappe.local.message_log)
        self.assertEqual(frappe.db.get_value("Lead", first["id"], "custom_crm_status"), "New")
        self.assertFalse(frappe.db.exists("Customer", {"customer_name": "Twin Email Account"}))
        # Only the email's refusal is answered that way; any other duplicate is still a failure of the server.
        self.assertFalse(_duplicate_email(frappe.DuplicateEntryError("Lead", "Twin"), {"email": "twins@example.invalid"}))

    def test_an_email_an_archived_lead_holds_is_refused_to_another_lead_as_a_conflict(self):
        """ERPNext keeps a Lead's email unique over every Lead (CRM Settings), archived ones included; the
        refusal names the field instead of failing the request."""

        # The rule is CRM Settings' (off on this site, said so here, as the twin test turns it on for a moment).
        frappe.db.set_single_value("CRM Settings", "allow_lead_duplication_based_on_emails", 0)
        frappe.set_user(self.sales)
        kept = create_lead(self._input("Email Keeper Lead", email="keeper@example.invalid"))
        frappe.set_user(self.manager)
        archive_lead(kept["id"])

        frappe.set_user(self.sales)
        before = frappe.db.count("Lead")
        # The message log is the process's: the earlier tests of the class left theirs in it.
        frappe.clear_messages()
        with self.assertRaises(CrmApiException) as taken:
            create_lead(self._input("Email Taker Lead", email="keeper@example.invalid"))
        self.assertEqual(
            (taken.exception.code, taken.exception.public_message, taken.exception.field_errors),
            ("CONFLICT", DUPLICATE_LEAD_EMAIL, {"email": "Already used"}),
        )
        # The refusal's own message (ERPNext's) is cleared from the answer.
        self.assertFalse(frappe.local.message_log)
        self.assertEqual(frappe.db.count("Lead"), before)
        other = create_lead(self._input("Email Other Lead", email="other@example.invalid"))
        with self.assertRaises(CrmApiException) as retaken:
            update_lead(other["id"], self._input("Email Other Lead", email="keeper@example.invalid"), other["modified"])
        self.assertEqual(retaken.exception.code, "CONFLICT")
        self.assertEqual(frappe.db.get_value("Lead", other["id"], "email_id"), "other@example.invalid")

    def test_a_converted_lead_is_its_accounts_history_and_is_not_archived(self):
        frappe.set_user(self.sales)
        lead = create_lead(self._input("Converted Stays Lead"))
        convert_lead(lead["id"], self._conversion_input(
            newAccount=self._account_input("Converted Stays Account"),
            newSite=self._site_input("Converted Stays Site"),
            newContact=self._contact_input("placeholder", "Converted Stays Contact"),
        ))

        frappe.set_user(self.manager)
        with self.assertRaises(CrmApiException) as refused:
            archive_lead(lead["id"])
        self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", CONVERTED_LEAD_ARCHIVE))
        self.assertEqual(frappe.db.get_value("Lead", lead["id"], "custom_crm_archived"), 0)
        self.assertIn(lead["id"], self._listed({"status": "Converted"}))

    def test_a_lead_a_conversion_left_a_trace_on_is_not_archived_whatever_the_trace(self):
        # The archive reads these traces of a conversion, each enough alone: the status, the CRM's or ERPNext's own
        # (the column and the value ERPNext's Customer writes when it is made from the Lead in the Desk), each of the
        # Lead's four conversion columns, a Customer naming it as the Lead it was made from (ERPNext's own mark of a
        # conversion, its status following only when ERPNext works it out again), a deal naming it as its source, a
        # conversion in a deal's stage history (the cockpit and the board find a Lead's conversion by its column naming
        # the deal or by that history). A legacy conversion, or one repaired in the Desk, can leave any one of them
        # behind.
        frappe.set_user(self.sales)
        source = create_lead(self._input("Traced Source Lead"))
        converted = convert_lead(source["id"], self._conversion_input(
            newAccount=self._account_input("Traced Source Account"),
            newSite=self._site_input("Traced Source Site"),
            newContact=self._contact_input("placeholder", "Traced Source Contact"),
        ))
        deal = converted["opportunityId"]
        # The converted Lead keeps the deal's stage history alone: its own status and columns cleared, the deal's
        # source given to another Lead, which keeps that alone.
        columns = ("custom_crm_converted_at", "custom_crm_converted_account", "custom_crm_converted_contact", "custom_crm_converted_opportunity")
        frappe.db.set_value("Lead", source["id"], {
            "custom_crm_status": source["status"], "status": "Lead", **{column: None for column in columns},
        }, update_modified=False)
        sourced = create_lead(self._input("Traced Deal Source Lead"))
        frappe.db.set_value("CRM Opportunity", deal, "source_lead", sourced["id"], update_modified=False)
        # Each of the two keeps its one trace alone.
        self.assertEqual(frappe.db.get_value("CRM Opportunity", deal, "source_lead"), sourced["id"])
        self.assertEqual(
            frappe.db.get_value("Lead", source["id"], ["custom_crm_status", "status", *columns]),
            (source["status"], "Lead", None, None, None, None),
        )
        self.assertFalse(frappe.db.exists("Customer", {"lead_name": source["id"]}))
        self.assertTrue(frappe.db.exists("CRM Opportunity Stage History", {
            "event": "lead_converted", "reference_doctype": "Lead", "reference_name": source["id"],
        }))
        traces = {"stage history": source, "deal source": sourced}
        for label, values in (
            ("status", {"custom_crm_status": "Converted"}),
            ("ERPNext's status", {"status": "Converted"}),
            ("converted at", {"custom_crm_converted_at": frappe.utils.now_datetime()}),
            ("converted account", {"custom_crm_converted_account": converted["accountId"]}),
            ("converted contact", {"custom_crm_converted_contact": converted["contactId"]}),
            ("converted opportunity", {"custom_crm_converted_opportunity": deal}),
        ):
            lead = create_lead(self._input(f"Traced {label.title()} Lead"))
            frappe.db.set_value("Lead", lead["id"], values, update_modified=False)
            traces[label] = lead
        # A Customer given the Lead as the one it was made from after its insert: the Lead's status as it was.
        linked = create_lead(self._input("Traced Customer Link Lead"))
        frappe.db.set_value("Customer", converted["accountId"], "lead_name", linked["id"], update_modified=False)
        self.assertEqual(frappe.db.get_value("Lead", linked["id"], "status"), "Lead")
        traces["customer naming it"] = linked
        # ERPNext's status other than Converted (Interested, as ERPNext leaves a Lead whose Customer is deleted), and
        # no trace: the Lead is archived.
        untraced = create_lead(self._input("Untraced Interested Lead"))
        frappe.db.set_value("Lead", untraced["id"], "status", "Interested", update_modified=False)

        frappe.set_user(self.manager)
        for label, lead in traces.items():
            with self.subTest(trace=label):
                with self.assertRaises(CrmApiException) as refused:
                    archive_lead(lead["id"])
                self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", CONVERTED_LEAD_ARCHIVE))
                self.assertEqual(frappe.db.get_value("Lead", lead["id"], "custom_crm_archived"), 0)
        self.assertTrue(archive_lead(untraced["id"])["archived"])
        # ERPNext's own conversion in the Desk reads no archive flag: a Customer made from the archived Lead leaves it
        # archived, converted, and archiving it again changes nothing, as for any archived Lead.
        frappe.db.set_value("Customer", converted["accountId"], "lead_name", untraced["id"], update_modified=False)
        frappe.db.set_value("Lead", untraced["id"], "status", "Converted", update_modified=False)
        modified = frappe.db.get_value("Lead", untraced["id"], "modified")
        self.assertTrue(archive_lead(untraced["id"])["archived"])
        self.assertEqual(frappe.db.get_value("Lead", untraced["id"], "modified"), modified)

    def test_lead_create_fails_closed_if_erpnext_auto_contact_is_reenabled(self):
        frappe.set_user(self.sales)
        before = frappe.db.count("Contact")
        frappe.db.set_single_value("CRM Settings", "auto_creation_of_contact", 1)
        try:
            with self.assertRaises(CrmApiException) as failure:
                create_lead(self._input("Auto Contact Drift Lead"))
            self.assertEqual(failure.exception.code, "INTERNAL_ERROR")
            self.assertEqual(frappe.db.count("Contact"), before)
        finally:
            frappe.db.set_single_value("CRM Settings", "auto_creation_of_contact", 0)

    def _account_input(self, name: str) -> dict:
        return {
            "name": name,
            "shortName": name,
            "segment": "Advanced Packaging",
            "tier": "A",
            "city": "Shanghai",
            "region": "East China",
            "owner": frappe.session.user,
        }

    def _contact_input(self, account_id: str, name: str) -> dict:
        return {
            "accountId": account_id,
            "name": name,
            "title": "Process Manager",
            "department": "Process Engineering",
            "phone": "13800000005",
            "email": f"{name.replace(' ', '.').lower()}@example.invalid",
            "relationship": "Developing",
            "status": "Active",
            "owner": frappe.session.user,
        }

    def _site_input(self, name: str) -> dict:
        return {
            "name": name,
            "city": "Shanghai",
            "type": "Fab",
            "process": "Advanced Packaging",
            "status": "量产",
        }

    def _conversion_input(self, **overrides) -> dict:
        payload = {
            "opportunityTitle": "Advanced Packaging Inspection",
            "opportunityAmount": "250000.50",
            "opportunityAmountCny": "250000.50",
            "opportunityCloseDate": "2026-12-31",
            "opportunityOwner": self.sales,
            "toolType": "Inspection",
            "qualificationConfirmed": True,
            "opportunityProbabilityLevel": "pipeline",
        }
        payload.update(overrides)
        return payload

    def test_conversion_into_an_account_named_like_one_the_user_sees_asks_first(self):
        frappe.set_user(self.sales)
        existing = create_account(self._account_input("Converted Twin Account"))
        lead = create_lead(self._input("Twin Conversion Lead"))
        conversion = self._conversion_input(
            newAccount=self._account_input("Converted Twin Account"),
            newSite=self._site_input("Twin Site"),
            newContact=self._contact_input("placeholder", "Twin Contact"),
        )
        with self.assertRaises(CrmApiException) as taken:
            convert_lead(lead["id"], conversion)
        self.assertEqual((taken.exception.code, taken.exception.field_errors), ("CONFLICT", {"name": existing["id"]}))
        self.assertNotEqual(frappe.db.get_value("Lead", lead["id"], "custom_crm_status"), "Converted")

        # Confirmed as another company, the conversion creates it (ERPNext suffixes the id).
        conversion["newAccount"]["confirmDuplicate"] = True
        converted = convert_lead(lead["id"], conversion)
        self.assertFalse(converted["reusedAccount"])
        self.assertEqual(frappe.db.get_value("Lead", lead["id"], "custom_crm_status"), "Converted")

    def test_conversion_reuses_records_uses_selected_owner_and_is_idempotent(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Reuse Account"))
        site = create_site(account["id"], self._site_input("Lead Reuse Site"))
        contact_input = self._contact_input(account["id"], "Lead Reuse Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        lead = create_lead(self._input("Reusable Conversion Lead"))

        converted = convert_lead(
            lead["id"],
            self._conversion_input(accountId=account["id"], contactId=contact["id"], siteId=site["id"]),
        )

        self.assertEqual(converted["accountId"], account["id"])
        self.assertEqual(converted["contactId"], contact["id"])
        self.assertEqual(converted["lead"]["id"], lead["id"])
        self.assertTrue(converted["reusedAccount"])
        self.assertTrue(converted["reusedContact"])
        opportunity = frappe.get_doc("CRM Opportunity", converted["opportunityId"])
        self.assertEqual(opportunity.opportunity_owner, self.sales)
        self.assertEqual(opportunity.account, account["id"])
        self.assertEqual(opportunity.site, site["id"])
        self.assertEqual(opportunity.source_lead, lead["id"])
        self.assertEqual(str(opportunity.po_date), "2026-12-31")
        self.assertEqual(opportunity.stage, QUALIFIED_OPPORTUNITY)
        stage_history = frappe.get_all(
            "CRM Opportunity Stage History",
            filters={"opportunity": opportunity.name},
            fields=["to_stage", "source", "event", "reference_doctype", "reference_name"],
        )
        self.assertEqual(
            [(row.to_stage, row.source, row.event, row.reference_doctype, row.reference_name) for row in stage_history],
            [(QUALIFIED_OPPORTUNITY, "creation", "lead_converted", "Lead", lead["id"])],
        )
        self.assertEqual((opportunity.probability_level, opportunity.score), ("pipeline", 20))
        self.assertEqual(opportunity.sale_type, "New Equipment")
        self.assertEqual(opportunity.sub_region, "East China")
        self.assertEqual(opportunity.original_amount, opportunity.amount)
        history = frappe.get_all(
            "CRM Opportunity History",
            filters={"opportunity": opportunity.name},
            fields=["actor", "field", "from_value", "to_value"],
        )
        self.assertEqual(
            history,
            [{"actor": self.sales, "field": "leadConversion", "from_value": "", "to_value": lead["id"]}],
        )
        self.assertFalse(frappe.db.exists("Company", "Lead Reuse Account"))

        repeated = convert_lead(lead["id"], {"opportunityTitle": "Must Not Create Another"})
        self.assertEqual(repeated, converted)
        self.assertEqual(frappe.db.count("CRM Opportunity", {"source_lead": lead["id"]}), 1)

    def test_convert_lead_without_opportunity_amount(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Unpriced Account"))
        site = create_site(account["id"], self._site_input("Lead Unpriced Site"))
        contact_input = self._contact_input(account["id"], "Lead Unpriced Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        existing = {"accountId": account["id"], "contactId": contact["id"], "siteId": site["id"]}

        # A conversion always creates a qualified (S1) Opportunity, whose amounts may still be unknown.
        omitted = self._conversion_input(**existing)
        omitted.pop("opportunityAmount")
        omitted.pop("opportunityAmountCny")
        lead = create_lead(self._input("Unpriced Conversion Lead"))
        converted = convert_lead(lead["id"], omitted)
        opportunity = get_strategy_opportunity(converted["opportunityId"])
        self.assertEqual(
            (opportunity["stage"], opportunity["amount"], opportunity["originalAmount"], opportunity["amountCny"]),
            (QUALIFIED_OPPORTUNITY, "", "", ""),
        )
        self.assertEqual(
            tuple(frappe.db.get_value("CRM Opportunity", converted["opportunityId"], ["amount", "original_amount", "amount_cny"])),
            (0, 0, 0),
        )
        # Converting the same Lead again returns the first result and creates no second Opportunity.
        self.assertEqual(convert_lead(lead["id"], omitted), converted)
        self.assertEqual(frappe.db.count("CRM Opportunity", {"source_lead": lead["id"]}), 1)

        # Blank and exact zero mean the same. A CNY Opportunity takes its CNY amount from the amount (#87);
        # in another currency one amount entered does not require the other.
        for label, amounts, expected in (
            ("Blank", {"opportunityAmount": "", "opportunityAmountCny": ""}, ("", "", "")),
            ("Zero", {"opportunityAmount": "0", "opportunityAmountCny": "0.00"}, ("", "", "")),
            ("Priced", {"opportunityAmount": "1200.5", "opportunityAmountCny": ""}, ("1200.50", "1200.50", "1200.50")),
            ("Mismatch", {"opportunityAmount": "1200.5", "opportunityAmountCny": "99"}, ("1200.50", "1200.50", "1200.50")),
            (
                "Foreign",
                {"currency": "USD", "opportunityAmount": "1200.5", "opportunityAmountCny": ""},
                ("1200.50", "1200.50", ""),
            ),
        ):
            with self.subTest(label=label):
                lead = create_lead(self._input(f"{label} Conversion Lead"))
                converted = convert_lead(lead["id"], self._conversion_input(**existing, **amounts))
                opportunity = get_strategy_opportunity(converted["opportunityId"])
                self.assertEqual(
                    (opportunity["stage"], (opportunity["amount"], opportunity["originalAmount"], opportunity["amountCny"])),
                    (QUALIFIED_OPPORTUNITY, expected),
                )

    def test_manager_can_choose_opportunity_owner_during_conversion(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Assigned Account"))
        site = create_site(account["id"], self._site_input("Lead Assigned Site"))
        contact_input = self._contact_input(account["id"], "Lead Assigned Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        lead = create_lead(self._input("Manager Assigned Lead"))

        frappe.set_user(self.manager)
        converted = convert_lead(
            lead["id"],
            self._conversion_input(
                accountId=account["id"],
                contactId=contact["id"],
                siteId=site["id"],
                opportunityOwner=self.other_sales,
            ),
        )

        self.assertEqual(
            frappe.db.get_value("CRM Opportunity", converted["opportunityId"], "opportunity_owner"),
            self.other_sales,
        )
        # The Manager who converts sets the first level; the new owner takes it from there.
        self.assertEqual(
            [
                (row["from"], row["to"], row["actor"])
                for row in get_strategy_opportunity(converted["opportunityId"])["probabilityHistory"]
            ],
            [("", "pipeline", self.manager)],
        )

    def test_manager_conversion_gives_the_new_account_and_contact_to_the_chosen_owner(self):
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Converted Lead", self.sales))
        conversion = self._conversion_input(
            newAccount={**self._account_input("Manager Converted Account"), "owner": self.sales},
            newSite=self._site_input("Manager Converted Site"),
            newContact={**self._contact_input("placeholder", "Manager Converted Contact"), "owner": self.sales},
        )

        converted = convert_lead(lead["id"], conversion)

        self.assertEqual(frappe.db.get_value("Customer", converted["accountId"], "custom_crm_owner"), self.sales)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.sales)
        # The Sales user the Lead belongs to keeps it and reaches everything the conversion created.
        frappe.set_user(self.sales)
        self.assertEqual(get_lead(lead["id"])["status"], "Converted")
        self.assertEqual(get_account_360(converted["accountId"])["account"]["owner"], self.sales)
        self.assertEqual(get_contact(converted["contactId"])["contact"]["owner"], self.sales)
        self.assertEqual(get_strategy_opportunity(converted["opportunityId"])["owner"], self.sales)

    def test_manager_conversion_notifies_the_owner_even_when_the_record_id_is_too_long_for_a_route(self):
        # Frappe names a Contact "<name>-<Account ID>". With a long Account ID the route to the Contact
        # no longer fits the notification's route field; the conversion must not fail on that.
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Long Account " + "N" * 82))
        site = create_site(account["id"], self._site_input("Lead Long Site"))
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Long Route Lead", self.sales))
        contact_input = {**self._contact_input("placeholder", "Long Route Contact " + "C" * 11), "owner": self.sales}

        converted = convert_lead(lead["id"], self._conversion_input(
            accountId=account["id"], siteId=site["id"], newContact=contact_input,
        ))

        self.assertGreater(len(f"/contacts/{converted['contactId']}"), 140)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.sales)
        notice = frappe.get_all(
            "CRM Notification Event",
            filters={"source_doctype": "Contact", "source_name": converted["contactId"], "recipient_user": self.sales},
            fields=["title", "route"],
        )
        self.assertEqual([(row.title, row.route) for row in notice], [("Contact assigned", "/contacts")])
        self.assertEqual(get_lead(lead["id"])["status"], "Converted")

    def test_manager_conversion_that_fails_part_way_leaves_nothing_behind(self):
        engineer = self._user("crm-lead-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Rollback Lead", self.sales))
        counted = ("Customer", "Address", "Contact", "CRM Opportunity", "CRM Notification Event")
        before = {doctype: frappe.db.count(doctype) for doctype in counted}

        # The Account goes to Sales, which writes the Account and its notice; the Contact owner is then refused.
        with self.assertRaises(CrmApiException) as invalid:
            convert_lead(lead["id"], self._conversion_input(
                newAccount={**self._account_input("Manager Rollback Account"), "owner": self.sales},
                newSite=self._site_input("Manager Rollback Site"),
                newContact={**self._contact_input("placeholder", "Manager Rollback Contact"), "owner": engineer},
            ))

        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        self.assertEqual({doctype: frappe.db.count(doctype) for doctype in counted}, before)
        self.assertEqual(get_lead(lead["id"])["status"], "New")

    def test_manager_conversion_without_a_chosen_owner_keeps_the_records_with_the_manager(self):
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Own Conversion Lead", self.sales))
        account_input = self._account_input("Manager Own Conversion Account")
        contact_input = self._contact_input("placeholder", "Manager Own Conversion Contact")
        del account_input["owner"], contact_input["owner"]

        converted = convert_lead(lead["id"], self._conversion_input(
            newAccount=account_input, newSite=self._site_input("Manager Own Conversion Site"), newContact=contact_input,
        ))

        self.assertEqual(frappe.db.get_value("Customer", converted["accountId"], "custom_crm_owner"), self.manager)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.manager)

    def test_manager_conversion_refuses_an_owner_who_cannot_hold_records(self):
        engineer = self._user("crm-lead-engineer@example.invalid", "CRM Engineer")
        frappe.set_user(self.manager)
        lead = create_lead(self._input("Manager Invalid Owner Lead", self.sales))
        before = frappe.db.count("Customer")

        with self.assertRaises(CrmApiException) as invalid:
            convert_lead(lead["id"], self._conversion_input(
                newAccount={**self._account_input("Manager Invalid Owner Account"), "owner": engineer},
                newSite=self._site_input("Manager Invalid Owner Site"),
                newContact=self._contact_input("placeholder", "Manager Invalid Owner Contact"),
            ))

        self.assertEqual(invalid.exception.code, "VALIDATION_ERROR")
        self.assertEqual(frappe.db.count("Customer"), before)
        self.assertEqual(get_lead(lead["id"])["status"], "New")

    def test_sales_conversion_keeps_the_new_account_and_contact_with_the_converting_sales(self):
        frappe.set_user(self.sales)
        lead = create_lead(self._input("Sales Own Conversion Lead"))

        converted = convert_lead(lead["id"], self._conversion_input(
            newAccount={**self._account_input("Sales Own Conversion Account"), "owner": self.other_sales},
            newSite=self._site_input("Sales Own Conversion Site"),
            newContact={**self._contact_input("placeholder", "Sales Own Conversion Contact"), "owner": self.other_sales},
        ))

        self.assertEqual(frappe.db.get_value("Customer", converted["accountId"], "custom_crm_owner"), self.sales)
        self.assertEqual(frappe.db.get_value("Contact", converted["contactId"], "custom_crm_owner"), self.sales)

    def test_conversion_needs_a_probability_level_before_it_writes_anything(self):
        frappe.set_user(self.sales)
        account = create_account(self._account_input("Lead Level Account"))
        site = create_site(account["id"], self._site_input("Lead Level Site"))
        contact_input = self._contact_input(account["id"], "Lead Level Contact")
        contact_input["siteId"] = site["id"]
        contact = create_contact(contact_input)
        lead = create_lead(self._input("Level Required Lead"))
        existing = {"accountId": account["id"], "contactId": contact["id"], "siteId": site["id"]}

        with self.assertRaises(CrmApiException) as missing:
            convert_lead(lead["id"], self._conversion_input(**existing, opportunityProbabilityLevel=""))
        self.assertEqual(
            (missing.exception.code, missing.exception.field_errors),
            ("VALIDATION_ERROR", {"opportunityProbabilityLevel": "Required"}),
        )
        self.assertEqual(frappe.db.count("CRM Opportunity", {"source_lead": lead["id"]}), 0)
        self.assertEqual(get_lead(lead["id"])["status"], "New")

        converted = convert_lead(lead["id"], self._conversion_input(**existing, opportunityProbabilityLevel="upside"))
        opportunity = get_strategy_opportunity(converted["opportunityId"])
        self.assertEqual(opportunity["probabilityLevel"], "upside")
        self.assertEqual(
            [(row["from"], row["to"], row["actor"]) for row in opportunity["probabilityHistory"]],
            [("", "upside", self.sales)],
        )

    def test_conversion_can_create_account_and_contact_and_rolls_back_each_subwrite(self):
        frappe.set_user(self.sales)
        lead = create_lead(self._input("New Records Conversion Lead"))
        conversion = self._conversion_input(
            newAccount=self._account_input("Converted New Account"),
            newSite=self._site_input("Converted New Site"),
            newContact=self._contact_input("placeholder", "Converted New Contact"),
        )

        converted = convert_lead(lead["id"], conversion)
        self.assertFalse(converted["reusedAccount"])
        self.assertFalse(converted["reusedContact"])
        self.assertEqual(
            frappe.db.get_value("Lead", lead["id"], "custom_crm_status"),
            "Converted",
        )

        for stage in ("account", "site", "contact", "opportunity", "lead"):
            rollback_lead = create_lead(self._input(f"Rollback {stage} Lead"))
            before = {
                doctype: frappe.db.count(doctype)
                for doctype in ("Customer", "Address", "Contact", "CRM Opportunity")
            }

            def fail_at(current_stage: str, expected=stage):
                if current_stage == expected:
                    raise RuntimeError(f"injected after {expected}")

            with self.assertRaisesRegex(RuntimeError, f"injected after {stage}"):
                convert_lead(
                    rollback_lead["id"],
                    self._conversion_input(
                        newAccount=self._account_input(f"Rollback {stage} Account"),
                        newSite=self._site_input(f"Rollback {stage} Site"),
                        newContact=self._contact_input("placeholder", f"Rollback {stage} Contact"),
                    ),
                    failure_injector=fail_at,
                )
            self.assertEqual(
                {doctype: frappe.db.count(doctype) for doctype in before},
                before,
            )
            self.assertEqual(frappe.db.get_value("Lead", rollback_lead["id"], "custom_crm_status"), "New")

    def test_conversion_rejects_invalid_money_and_close_date_without_writes(self):
        frappe.set_user(self.sales)
        lead = create_lead(self._input("Invalid Conversion Lead"))
        before = frappe.db.count("CRM Opportunity")
        # Blank or zero is an amount not entered yet (test_convert_lead_without_opportunity_amount).
        messages = {
            "opportunityAmount": "opportunityAmount must be blank or a non-negative amount with at most two decimal places.",
            "opportunityAmountCny": "opportunityAmountCny must be positive with at most two decimal places.",
        }
        for field, invalid in (
            *(("opportunityAmount", value) for value in ("-1", "1.234", "not-money", True)),
            *(("opportunityAmountCny", value) for value in ("-1", "1.234", "not-money")),
        ):
            with self.subTest(field=field, invalid=invalid):
                with self.assertRaises(CrmApiException) as failure:
                    convert_lead(
                        lead["id"],
                        self._conversion_input(
                            **{field: invalid},
                            newAccount=self._account_input("Invalid Conversion Account"),
                            newSite=self._site_input("Invalid Conversion Site"),
                            newContact=self._contact_input("placeholder", "Invalid Conversion Contact"),
                        ),
                    )
                self.assertEqual(failure.exception.code, "VALIDATION_ERROR")
                # The API names the field that is wrong, for either amount, with the message the front end maps.
                self.assertEqual(failure.exception.field_errors, {field: "Invalid amount"})
                self.assertEqual(failure.exception.public_message, messages[field])
        with self.assertRaises(CrmApiException) as bad_date:
            convert_lead(
                lead["id"],
                self._conversion_input(
                    opportunityCloseDate="2026-02-31",
                    newAccount=self._account_input("Invalid Date Account"),
                    newSite=self._site_input("Invalid Date Site"),
                    newContact=self._contact_input("placeholder", "Invalid Date Contact"),
                ),
            )
        self.assertEqual(bad_date.exception.code, "VALIDATION_ERROR")
        unqualified = self._conversion_input(
            newAccount=self._account_input("Unqualified Conversion Account"),
            newSite=self._site_input("Unqualified Conversion Site"),
            newContact=self._contact_input("placeholder", "Unqualified Conversion Contact"),
        )
        unqualified.pop("qualificationConfirmed")
        with self.assertRaises(CrmApiException) as not_confirmed:
            convert_lead(lead["id"], unqualified)
        self.assertEqual(not_confirmed.exception.code, "VALIDATION_ERROR")
        self.assertEqual(not_confirmed.exception.field_errors, {"qualificationConfirmed": "Required"})
        self.assertEqual(frappe.db.count("CRM Opportunity"), before)


class TestLeadConversionConcurrency(FrappeTestCase):
    def test_an_archive_reads_the_status_under_the_lock_as_a_conversion_committed_it(self):
        """The archive reads the Lead under its row lock, as committed: a conversion committed after the request's
        snapshot (which has the Lead new) is seen there, and the Lead is refused as converted, nothing written."""

        users = {}
        for label, role in (("owner", "CRM Sales"), ("manager", "CRM Manager")):
            email = f"crm-lead-archive-race-{label}@example.invalid"
            if not frappe.db.exists("User", email):
                frappe.get_doc({
                    "doctype": "User", "email": email, "first_name": label, "enabled": 1,
                    "send_welcome_email": 0, "roles": [{"role": role}],
                }).insert(ignore_permissions=True)
            users[label] = email
        lead = "CRM-LEAD-RACE-" + frappe.generate_hash(length=8)
        original_user = frappe.session.user
        connection = None
        try:
            frappe.db.commit()
            connection = frappe.db._get_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO `tabLead` (name, first_name, lead_name, lead_owner, custom_crm_status, creation, modified)"
                    " VALUES (%s, 'Race', 'Race', %s, 'New', NOW(6) - INTERVAL 1 MINUTE, NOW(6) - INTERVAL 1 MINUTE)",
                    (lead, users["owner"]),
                )
            connection.commit()
            # This request's snapshot, which has the Lead new ...
            frappe.db.sql("SELECT COUNT(*) FROM `tabLead`")
            # ... converted by another request committed after it.
            with connection.cursor() as cursor:
                cursor.execute("UPDATE `tabLead` SET `custom_crm_status` = 'Converted', `modified` = NOW(6) WHERE `name` = %s", (lead,))
            connection.commit()
            self.assertEqual(frappe.db.get_value("Lead", lead, "custom_crm_status"), "New")
            frappe.set_user(users["manager"])
            with self.assertRaises(CrmApiException) as refused:
                archive_lead(lead)
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("INVALID_TRANSITION", CONVERTED_LEAD_ARCHIVE))
            self.assertEqual(frappe.db.sql("SELECT `custom_crm_archived` FROM `tabLead` WHERE `name` = %s FOR UPDATE", (lead,))[0][0], 0)
        finally:
            frappe.set_user(original_user)
            # The Lead's row lock released before the other connection removes the row.
            frappe.db.rollback()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM `tabLead` WHERE `name` = %s", (lead,))
                connection.commit()
                connection.close()

    def test_a_conversion_whose_snapshot_predates_the_lead_it_locked_is_refused_as_changed(self):
        """The scope is read as the request's snapshot has the Lead, the Lead itself under its lock as committed: a
        reassignment committed between the request's snapshot and its lock would leave the old owner deciding. Such a
        conversion is refused as changed, before it writes; its retry reads both anew and is refused the new owner's
        Lead."""

        users = []
        for label in ("before", "after"):
            email = f"crm-lead-race-{label}@example.invalid"
            if not frappe.db.exists("User", email):
                frappe.get_doc({
                    "doctype": "User", "email": email, "first_name": label, "enabled": 1,
                    "send_welcome_email": 0, "roles": [{"role": "CRM Sales"}],
                }).insert(ignore_permissions=True)
            users.append(email)
        before, after = users
        lead = "CRM-LEAD-RACE-" + frappe.generate_hash(length=8)
        original_user = frappe.session.user
        connection = None
        try:
            frappe.db.commit()
            connection = frappe.db._get_connection()
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO `tabLead` (name, first_name, lead_name, lead_owner, custom_crm_status, creation, modified)"
                    " VALUES (%s, 'Race', 'Race', %s, 'New', NOW(6) - INTERVAL 1 MINUTE, NOW(6) - INTERVAL 1 MINUTE)",
                    (lead, before),
                )
            connection.commit()
            # This request's snapshot, which has the Lead under its first owner ...
            frappe.db.sql("SELECT COUNT(*) FROM `tabLead`")
            # ... reassigned by another request committed after it.
            with connection.cursor() as cursor:
                cursor.execute("UPDATE `tabLead` SET `lead_owner` = %s, `modified` = NOW(6) WHERE `name` = %s", (after, lead))
            connection.commit()
            self.assertEqual(frappe.db.get_value("Lead", lead, "lead_owner"), before)
            frappe.set_user(before)
            with self.assertRaises(CrmApiException) as changed:
                convert_lead(lead, {})
            self.assertEqual(changed.exception.code, "VERSION_CONFLICT")
            # The retry, a request of its own, reads the Lead as its new owner has it.
            frappe.db.rollback()
            with self.assertRaises(CrmApiException) as refused:
                convert_lead(lead, {})
            self.assertEqual(refused.exception.code, "SCOPE_DENIED")
        finally:
            frappe.set_user(original_user)
            # The Lead's row lock released before the other connection removes the row.
            frappe.db.rollback()
            if connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM `tabLead` WHERE `name` = %s", (lead,))
                connection.commit()
                connection.close()
