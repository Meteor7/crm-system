import frappe
from frappe.model.document import Document


class CRMOpportunityAction(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if self.status != "Done":
            self.completed_at = None
        elif before and before.status == "Done":
            # Editing a completion, including a legacy unknown one, is not a new event.
            self.completed_at = before.completed_at
        else:
            self.completed_at = frappe.utils.now_datetime()
