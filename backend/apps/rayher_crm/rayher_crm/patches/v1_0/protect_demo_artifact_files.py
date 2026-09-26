"""Remove the native File-owner bypass from existing Demo Artifact files.

Demo Request forms, Test Reports and Customer Reports are only ever served by
``download_demo_artifact``, which checks the Evaluation / Demo Request scope and
writes an audit row. A File still owned by its uploader stays reachable through
Frappe's own owner shortcut, so anyone who uploaded one keeps access to the blob
after losing the role or the scope. The uploader is recorded on the artifact's
own ``created_by_user`` field, so nothing reads the File owner.

Rows created before re-attachment still point at a File attached to the
artifact's Evaluation or Demo Request, and ``_file_belongs_to_artifact`` serves
those too. Sweeping only ``attached_to_doctype = 'CRM Demo Artifact'`` would
leave exactly those legacy files with the uploader as owner -- the shape the
patch exists to close. Every File an artifact row points at is covered instead.
"""
import frappe


def execute():
    frappe.db.sql(
        """UPDATE `tabFile` file
             JOIN `tabCRM Demo Artifact` artifact ON artifact.`private_file` = file.`name`
              SET file.`owner` = %s
            WHERE file.`owner` != %s""",
        ("Administrator", "Administrator"),
    )
    # Also any file attached to an artifact that no row points at any more.
    frappe.db.sql(
        "UPDATE `tabFile` SET owner = %s WHERE attached_to_doctype = %s AND owner != %s",
        ("Administrator", "CRM Demo Artifact", "Administrator"),
    )
