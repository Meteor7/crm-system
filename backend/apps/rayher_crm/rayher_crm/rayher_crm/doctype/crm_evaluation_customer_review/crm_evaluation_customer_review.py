from frappe.model.document import Document


class CRMEvaluationCustomerReview(Document):
    """Customer Review is a record-keeping step, so each round's comment is kept
    verbatim and never edited in place."""

    def on_trash(self):
        import frappe

        frappe.throw("CRM Evaluation Customer Review is immutable")
