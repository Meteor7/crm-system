import frappe
from frappe.model.document import Document


class CRMOpportunityLossReviewRevision(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw("Loss review revisions are immutable")

    def on_trash(self):
        frappe.throw("Loss review revisions are immutable")
