import frappe
from frappe.model.document import Document


class CRMOpportunityLossReview(Document):
    def validate(self):
        if not self.is_new() and (
            self.has_value_changed("opportunity") or self.has_value_changed("stage_event")
        ):
            frappe.throw("A loss review cannot be moved to another lost event")
