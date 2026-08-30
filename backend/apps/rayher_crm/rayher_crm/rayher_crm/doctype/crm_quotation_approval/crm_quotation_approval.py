import frappe
from frappe.model.document import Document


class CRMQuotationApproval(Document):
    def validate(self):
        if not self.is_new() and not self.flags.get("allow_approval_decision"):
            frappe.throw("Quotation approval records are immutable.")
