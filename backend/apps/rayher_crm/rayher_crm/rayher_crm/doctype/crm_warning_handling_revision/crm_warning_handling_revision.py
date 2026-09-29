import frappe
from frappe.model.document import Document


class CRMWarningHandlingRevision(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw("Warning handling revisions are immutable")

    def on_trash(self):
        frappe.throw("Warning handling revisions are immutable")
