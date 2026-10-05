"""Install provenance before other post-sync work can create managed Files."""
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from rayher_crm.setup.custom_fields import CRM_CUSTOM_FIELDS


def execute():
    create_custom_fields({"File": CRM_CUSTOM_FIELDS["File"]}, update=True)
