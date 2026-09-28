from frappe.model.document import Document


class CRMOpportunityStageHistory(Document):
    """Each stage change is kept as an append-only row; rollbacks add rows instead of editing."""

    def validate(self):
        if not self.is_new():
            import frappe

            frappe.throw("CRM Opportunity Stage History is immutable")

    def on_trash(self):
        import frappe

        frappe.throw("CRM Opportunity Stage History is immutable")
