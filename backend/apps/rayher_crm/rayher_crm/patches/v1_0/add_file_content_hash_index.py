"""Index File content hashes used by managed-blob runtime guards."""

import frappe


INDEX_NAME = "content_hash_index"


def ensure_index() -> None:
    """Create the index and declare it on File.content_hash.

    Runtime queries name this index in ``FORCE INDEX``. A schema sync of File
    (Custom Field, Customize Form or a core File DocType update) drops every
    single-column index its DocField does not declare, and core ``add_index``
    only records ``search_index`` outside install and migrate. With the
    declaration a sync keeps the index, or recreates it as
    ``<fieldname>_index``, which is ``INDEX_NAME``.
    """
    # Runtime guards import INDEX_NAME from this module; keep them light.
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    declared = frappe.db.get_value(
        "Property Setter",
        {"doc_type": "File", "field_name": "content_hash", "property": "search_index"},
        "value",
    )
    if str(declared or "") != "1":
        make_property_setter(
            "File", "content_hash", "search_index", "1", "Check",
            validate_fields_for_doctype=False,
        )
    frappe.db.add_index("File", ["content_hash"], INDEX_NAME)


def execute() -> None:
    ensure_index()
