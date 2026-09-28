from frappe.model.document import Document


class CRMOpportunityProbabilityHistory(Document):
    """Each probability level change is kept verbatim as an append-only audit row."""

    def validate(self):
        if not self.is_new():
            import frappe

            frappe.throw("CRM Opportunity Probability History is immutable")

    def on_trash(self):
        import frappe

        frappe.throw("CRM Opportunity Probability History is immutable")
