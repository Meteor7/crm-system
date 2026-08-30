import frappe
from frappe.model.document import Document


class CRMContactFile(Document):
    def on_trash(self):
        frappe.throw("CRM Contact File metadata is soft-deleted by the file service")
