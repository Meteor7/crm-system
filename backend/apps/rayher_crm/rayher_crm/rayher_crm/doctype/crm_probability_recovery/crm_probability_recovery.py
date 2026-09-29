import frappe
from frappe.model.document import Document


class CRMProbabilityRecovery(Document):
    def validate(self):
        if not self.is_new() and (
            self.has_value_changed("opportunity") or self.has_value_changed("probability_change")
        ):
            frappe.throw("A recovery plan cannot be moved to another probability change")
