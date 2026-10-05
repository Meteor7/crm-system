from __future__ import annotations

import io
from unittest.mock import patch

import frappe
import pymysql
from frappe.model.naming import validate_name
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from rayher_crm.api.v1.accounts import create_account as create_account_endpoint
from rayher_crm.api.v1.accounts import create_account_site as create_site_endpoint
from rayher_crm.api.v1.contacts import create_contact as create_contact_endpoint
from rayher_crm.api.v1.errors import (
    EMAIL_ADDRESS_MESSAGE,
    NAME_CHARACTERS_MESSAGE,
    PHONE_NUMBER_MESSAGE,
    VALUE_TOO_LONG_MESSAGE,
    CrmApiException,
    api_endpoint,
    input_error,
)
from rayher_crm.services import visit_meetings
from rayher_crm.services.accounts import create_account
from rayher_crm.services.contact_files import upload_contact_files
from rayher_crm.services.contacts import create_contact
from rayher_crm.services.file_security import PDF_SCRIPT_MESSAGE, PDF_UNREADABLE_MESSAGE, validate_and_scan
from rayher_crm.services.visits import create_visit

FAILURE_LOG = {"method": "Rayher CRM API failure"}
TOO_LONG_LOG = {"method": "Rayher CRM value too long on save"}
PDF = "application/pdf"


class Scanner:
    def scan(self, content: bytes) -> bool:
        return True


def pdf_bytes(*, script: str | None = None, password: str | None = None) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    if script:
        # A script that runs when the page opens: the form Frappe's check recognises.
        action = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject(script)})
        page[NameObject("/AA")] = DictionaryObject({NameObject("/O"): action})
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class TestInputErrors(FrappeTestCase):
    """A value Frappe refuses on save is the user's to correct: 422 with a message, not a 500."""

    def setUp(self):
        super().setUp()
        self.original_user = frappe.session.user
        frappe.set_user("Administrator")
        self.sales = self._user("crm-input-errors-sales@example.invalid", "CRM Sales")
        frappe.set_user(self.sales)
        self.account = create_account(self._account("Input Errors Account"))
        self.contact = create_contact(self._contact("Input Errors Contact"))

    def tearDown(self):
        frappe.set_user(self.original_user)
        super().tearDown()

    def _user(self, email: str, role: str) -> str:
        if frappe.db.exists("User", email):
            return email
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": email.split("@", 1)[0],
            "enabled": 1, "send_welcome_email": 0, "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def _account(self, name: str, **overrides) -> dict:
        return {
            "name": name, "shortName": name[:8], "segment": "Frontend", "tier": "A",
            "city": "Shanghai", "region": "East", "owner": self.sales, **overrides,
        }

    def _contact(self, name: str, **overrides) -> dict:
        return {
            "accountId": self.account["id"] if hasattr(self, "account") else "", "name": name, "title": "Director",
            "department": "Engineering", "phone": "13800000002", "email": "input.errors@example.invalid",
            "relationship": "Developing", "owner": self.sales, "status": "Active", **overrides,
        }

    def _refused(self, endpoint, *arguments, too_long: bool = False) -> dict:
        frappe.local.response.pop("http_status_code", None)
        failures, too_long_before = frappe.db.count("Error Log", FAILURE_LOG), frappe.db.count("Error Log", TOO_LONG_LOG)
        # The endpoint rolls the request back. Under test the request's transaction is the test's own,
        # fixtures included, so that one call is counted here and not carried out.
        rollback, request_rollbacks = frappe.db.rollback, []

        def counted(*, save_point=None):
            return rollback(save_point=save_point) if save_point else request_rollbacks.append(True)

        with patch.object(frappe.db, "rollback", side_effect=counted):
            response = endpoint(*arguments)
        self.assertEqual(len(request_rollbacks), 1)
        self.assertIsNone(response["data"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertIs(response["error"]["retryable"], False)
        self.assertEqual(frappe.local.response["http_status_code"], 422)
        # It is the user's input, so it is not recorded as a failure of the server. A value that is
        # too long is still logged under a name of its own: a service may have put it together.
        self.assertEqual(frappe.db.count("Error Log", FAILURE_LOG), failures)
        self.assertEqual(frappe.db.count("Error Log", TOO_LONG_LOG), too_long_before + int(too_long))
        return response["error"]

    def test_account_values_frappe_refuses_say_which_field_and_why(self):
        accounts = frappe.db.count("Customer")
        cases = (
            (self._account("N" * 141), "Customer Name is too long: at most 140 characters.", True),
            (self._account("Input Errors Short", shortName="S" * 300), "CRM Short Name is too long: at most 140 characters.", True),
            (self._account("Input Errors City", city="C" * 300), "CRM City is too long: at most 140 characters.", True),
            (self._account("Input Errors <b>x</b>"), NAME_CHARACTERS_MESSAGE, False),
            (self._account("Input Errors > other"), NAME_CHARACTERS_MESSAGE, False),
        )
        for payload, message, too_long in cases:
            with self.subTest(message=message, name=payload["name"][:24]):
                self.assertEqual(self._refused(create_account_endpoint, payload, too_long=too_long)["message"], message)
        # Nothing of a refused request stays behind.
        self.assertEqual(frappe.db.count("Customer"), accounts)

        # The longest name that fits is still accepted.
        accepted = create_account_endpoint(self._account("M" * 140))
        self.assertEqual(accepted["data"]["name"], "M" * 140)

    def test_contact_values_frappe_refuses_say_which_field_and_why(self):
        contacts = frappe.db.count("Contact")
        phones = (
            "021-62881234 ext 801", "021-62881234转801", "13800000003/13800000014", "abc", "1" * 30, "０２１６２８８１２３４",
        )
        cases = [(self._contact(f"Input Errors Phone {index}", phone=phone), PHONE_NUMBER_MESSAGE) for index, phone in enumerate(phones)]
        cases = [(payload, message, False) for payload, message in cases] + [
            (self._contact("Input Errors Email", email="abc"), EMAIL_ADDRESS_MESSAGE, False),
            (self._contact("Input Errors Title", title="T" * 300), "Designation is too long: at most 140 characters.", True),
            (self._contact("Input Errors Department", department="D" * 300), "Department is too long: at most 140 characters.", True),
        ]
        for payload, message, too_long in cases:
            with self.subTest(message=message, phone=payload["phone"], name=payload["name"][:24]):
                self.assertEqual(self._refused(create_contact_endpoint, payload, too_long=too_long)["message"], message)
        self.assertEqual(frappe.db.count("Contact"), contacts)

    def _contact_refusal(self, payload: dict) -> tuple:
        frappe.local.response.pop("http_status_code", None)
        error = create_contact_endpoint(payload)["error"]
        return error["code"], error["message"], error["fieldErrors"], frappe.local.response["http_status_code"]

    def test_a_new_contacts_name_is_held_to_the_document_name_frappe_gives_it(self):
        # Frappe names a Contact "<name>-<Account>" in a document name of 140 characters, and appends a
        # number when that name is taken. With this Account's name of 20 the name may have 119, though
        # its own column holds 140.
        self.assertEqual(len(self.account["id"]), 20)
        self.assertEqual(self._contact_refusal(self._contact("X" * 120)), (
            "VALIDATION_ERROR", "name is too long: at most 119 characters for a Contact of this Account.", {"name": "Too long"}, 422,
        ))
        self.assertEqual(self._contact_refusal(self._contact("X" * 300)), (
            "VALIDATION_ERROR", "name is too long: at most 119 characters for a Contact of this Account.", {"name": "Too long"}, 422,
        ))
        # The limit named is one that works.
        self.assertEqual(create_contact_endpoint(self._contact("X" * 119))["data"]["name"], "X" * 119)
        # A second Contact of that name needs the number, "-1": two characters less are left.
        self.assertEqual(self._contact_refusal(self._contact("X" * 119)), (
            "VALIDATION_ERROR", "name is too long: at most 117 characters for a Contact of this Account.", {"name": "Too long"}, 422,
        ))

        # No room is kept for a number that is not needed: with an Account name of 135, "Li" makes a
        # document name of 138, and a second "Li" one of exactly 140.
        long_account = create_account(self._account("L" * 135))
        for _ in range(2):
            saved = create_contact_endpoint(self._contact("Li", accountId=long_account["id"]))
            self.assertEqual(saved["data"]["name"], "Li")
        self.assertEqual(
            sorted(len(name) for name in frappe.get_all("Contact", filters={"name": ["like", f"Li-{long_account['id']}%"]}, pluck="name")),
            [138, 140],
        )
        # An Account name of 139 leaves no room for any name.
        full_account = create_account(self._account("F" * 139))
        self.assertEqual(self._contact_refusal(self._contact("Li", accountId=full_account["id"])), (
            "VALIDATION_ERROR", "A Contact cannot be added to this Account: the Account's name is too long.", {"accountId": "Too long"}, 422,
        ))

        # What Frappe accepts as a phone number is still accepted, an extension included.
        for index, phone in enumerate(("021-62881234-801", "+86 138 0013 8000", "(021) 6288 1234", "021-62881234,801")):
            with self.subTest(phone=phone):
                accepted = create_contact_endpoint(self._contact(f"Input Errors Accepted {index}", phone=phone))
                self.assertEqual(accepted["data"]["phone"], phone)

    def test_other_failures_are_still_reported_as_failures_of_the_server(self):
        # A name error that is not about < or >, a duplicate, and any other validation error are not
        # known to be the user's input.
        with self.assertRaises(frappe.NameError) as reserved:
            validate_name("Customer", "Customer")
        for error in (
            reserved.exception, frappe.DuplicateEntryError("Customer", "Input Errors Account"),
            frappe.ValidationError("Unexpected"), frappe.MandatoryError("customer_name"), ValueError("Unexpected"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertIsNone(input_error(error))

        @api_endpoint
        def fails():
            frappe.get_doc({"doctype": "ToDo", "description": "Input errors: rolled back"}).insert(ignore_permissions=True)
            frappe.throw("Unexpected")

        failures = frappe.db.count("Error Log", FAILURE_LOG)
        response = fails()
        self.assertEqual((response["error"]["code"], response["error"]["retryable"]), ("INTERNAL_ERROR", True))
        self.assertEqual(response["error"]["message"], "The request could not be completed.")
        self.assertEqual(frappe.local.response["http_status_code"], 500)
        self.assertEqual(frappe.db.count("Error Log", FAILURE_LOG), failures + 1)
        self.assertFalse(frappe.db.exists("ToDo", {"description": "Input errors: rolled back"}))

    def test_a_document_name_the_database_cannot_hold_is_refused_and_logged(self):
        # A Site is named "<name>-<type>". Frappe does not measure a document name; the database does.
        site = {"name": "S" * 140, "city": "Shanghai", "type": "Fab", "process": "Frontend", "status": "量产"}
        sites = frappe.db.count("Address")
        refused = self._refused(create_site_endpoint, self.account["id"], site, too_long=True)
        self.assertEqual(refused["message"], VALUE_TOO_LONG_MESSAGE)
        self.assertEqual(frappe.db.count("Address"), sites)

        refused = input_error(pymysql.err.DataError(1406, "Data too long for column 'name' at row 1"))
        self.assertEqual((refused.code, refused.public_message), ("VALIDATION_ERROR", VALUE_TOO_LONG_MESSAGE))
        # Other data errors are not about length.
        self.assertIsNone(input_error(pymysql.err.DataError(1264, "Out of range value for column 'x' at row 1")))

    def test_a_length_error_without_its_field_still_reads_as_the_users_input(self):
        # Raised outside a document save: no field and no limit are known.
        refused = input_error(frappe.CharacterLengthExceededError("too long"))
        self.assertEqual((refused.code, refused.public_message), ("VALIDATION_ERROR", VALUE_TOO_LONG_MESSAGE))

        @api_endpoint
        def writes_then_fails():
            frappe.get_doc({"doctype": "ToDo", "description": "Input errors: refused"}).insert(ignore_permissions=True)
            raise frappe.CharacterLengthExceededError("too long")

        response = writes_then_fails()
        self.assertEqual(response["error"]["message"], VALUE_TOO_LONG_MESSAGE)
        self.assertEqual(frappe.local.response["http_status_code"], 422)
        # A refusal half-way through a save leaves nothing behind either.
        self.assertFalse(frappe.db.exists("ToDo", {"description": "Input errors: refused"}))

    def test_a_pdf_frappe_cannot_store_is_refused_with_a_message_of_its_own(self):
        broken = b"%PDF-1.4\n%broken\n1 0 obj\n<< /Type /Catalog >>\n"
        cases = ((broken, PDF_UNREADABLE_MESSAGE), (pdf_bytes(script="app.alert('x');"), PDF_SCRIPT_MESSAGE))
        for content, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(CrmApiException) as refused:
                    validate_and_scan("report.pdf", PDF, content, Scanner())
                self.assertEqual((refused.exception.code, refused.exception.public_message), ("VALIDATION_ERROR", message))
        # A sound PDF passes, and so does one with a password, which Frappe stores unopened.
        for content in (pdf_bytes(), pdf_bytes(password="secret")):
            self.assertEqual(validate_and_scan("report.pdf", PDF, content, Scanner()), PDF)

        # The upload paths that used to answer 500: a Visit record and a Contact file.
        visit = create_visit({
            "accountId": self.account["id"], "primaryContactId": self.contact["id"], "subject": "Input errors visit",
            "date": "2026-08-20", "type": "On-site", "owner": self.sales, "objective": "Confirm criteria",
        })
        files = frappe.db.count("File")
        with self.assertRaises(CrmApiException) as visit_record:
            visit_meetings.upload(visit["id"], "record.pdf", PDF, broken, scanner=Scanner())
        with self.assertRaises(CrmApiException) as contact_file:
            upload_contact_files(self.contact["id"], [{"file_name": "spec.pdf", "mime_type": PDF, "content": broken}], scanner=Scanner())
        for refused in (visit_record, contact_file):
            self.assertEqual((refused.exception.code, refused.exception.public_message), ("VALIDATION_ERROR", PDF_UNREADABLE_MESSAGE))
        self.assertEqual(frappe.db.count("File"), files)
        self.assertFalse(frappe.db.exists("CRM Visit Meeting Record", {"visit": visit["id"]}))
