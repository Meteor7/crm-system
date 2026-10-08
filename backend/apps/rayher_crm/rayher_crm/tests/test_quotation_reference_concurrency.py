"""A Quotation's reference is allocated without locking the Quotations of its date.

A second database connection stands in for another request writing one of the date's Quotations. What either
connection writes is rolled back: nothing here is committed.
"""
from __future__ import annotations

import frappe
from frappe.database import get_db
from frappe.tests.utils import FrappeTestCase

from rayher_crm.services.quotations import _next_ref_no

# Seconds a statement waits for a row lock here: a wait means the allocation took a lock it must not.
LOCK_WAIT = 2


class TestQuotationReferenceConcurrency(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.lock_wait = frappe.db.sql("SELECT @@SESSION.innodb_lock_wait_timeout")[0][0]
        frappe.db.sql("SET SESSION innodb_lock_wait_timeout = %s", (LOCK_WAIT,))
        self.other = get_db(
            host=frappe.conf.db_host, port=frappe.conf.db_port, user=frappe.conf.db_user or frappe.conf.db_name,
            password=frappe.conf.db_password, cur_db_name=frappe.conf.db_name,
        )
        self.other.connect()
        self.other.sql("SET SESSION innodb_lock_wait_timeout = %s", (LOCK_WAIT,))

    def tearDown(self):
        self.other.rollback()
        self.other.close()
        frappe.db.rollback()
        frappe.db.sql("SET SESSION innodb_lock_wait_timeout = %s", (self.lock_wait,))
        super().tearDown()

    def _write_quotation(self, name: str, ref_no: str) -> None:
        """The other request inserts a Quotation, and holds its row until it ends."""

        self.other.sql("INSERT INTO `tabCRM Quotation` (`name`, `ref_no`) VALUES (%s, %s)", (name, ref_no))

    def test_an_allocation_does_not_wait_for_a_writer_of_a_quotation_of_its_date(self):
        # A writer holds the row of one of the date's Quotations, and may be waiting for a row the creation holds
        # (its Opportunity's): an allocation that waited for the writer could close a cycle with it.
        self._write_quotation("crm-test-reference-held", "PK29970707-A5")

        self.assertTrue(_next_ref_no("2997-07-07").startswith("PK29970707-A"))

    def test_the_first_allocation_of_a_date_leaves_its_references_free_to_write(self):
        # The first two creations of a date would both take the gap of its references, then each wait to insert
        # into the other's: the allocation takes no gap, so another request writes a reference of the date meanwhile.
        self.assertEqual(_next_ref_no("2997-08-08"), "PK29970808-A1")

        self._write_quotation("crm-test-reference-written", "PK29970808-A2")
