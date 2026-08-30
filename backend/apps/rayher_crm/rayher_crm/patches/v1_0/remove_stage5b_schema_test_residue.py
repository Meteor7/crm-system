from __future__ import annotations

import frappe


RESERVED_CUSTOMER = "Stage 5B Schema Customer"
RESERVED_ENGINEER = "crm-stage5b-schema-engineer@example.invalid"


def execute() -> None:
    assignments = frappe.get_all(
        "CRM Account Engineer Assignment",
        filters={"customer": RESERVED_CUSTOMER, "engineer": RESERVED_ENGINEER},
        pluck="name",
    )
    for name in assignments:
        frappe.delete_doc(
            "CRM Account Engineer Assignment",
            name,
            ignore_permissions=True,
            force=True,
        )

    if frappe.db.exists("Customer", RESERVED_CUSTOMER):
        frappe.delete_doc(
            "Customer",
            RESERVED_CUSTOMER,
            ignore_permissions=True,
            force=True,
        )

    if frappe.db.exists("User", RESERVED_ENGINEER):
        frappe.delete_doc(
            "User",
            RESERVED_ENGINEER,
            ignore_permissions=True,
            force=True,
        )
