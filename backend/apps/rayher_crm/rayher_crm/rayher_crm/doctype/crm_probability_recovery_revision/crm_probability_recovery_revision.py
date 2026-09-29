import frappe
from frappe.model.document import Document


class CRMProbabilityRecoveryRevision(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw("Recovery plan revisions are immutable")

    def on_trash(self):
        frappe.throw("Recovery plan revisions are immutable")
