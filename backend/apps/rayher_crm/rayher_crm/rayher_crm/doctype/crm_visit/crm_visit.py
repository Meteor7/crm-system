import frappe
from frappe.model.document import Document


class CRMVisit(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if before and before.status != "Planned":
            # A later Account edit cannot rewrite the classification of a completed visit,
            # including legacy visits whose classification was never captured.
            self.customer_kind = before.customer_kind
            self.customer_kind_captured_at = before.customer_kind_captured_at
            self.completed_at = before.completed_at
        elif before and before.status == "Planned" and self.status != "Planned":
            kind = frappe.db.get_value("Customer", self.account, "custom_crm_customer_kind", for_update=True)
            self.customer_kind = kind if kind in {"Prospect", "Existing"} else ""
            self.customer_kind_captured_at = frappe.utils.now_datetime()
            self.completed_at = self.customer_kind_captured_at
        else:
            self.customer_kind = ""
            self.customer_kind_captured_at = None
            self.completed_at = None
