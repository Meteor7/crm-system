from frappe.model.document import Document


class CRMOpportunityInternalValidation(Document):
    """A request to start production before the PO arrives, decided by a Manager."""

    def validate(self):
        # live_opportunity carries a unique index, so at most one request per
        # Opportunity can be pending no matter which code path writes the row.
        self.live_opportunity = self.opportunity if self.status == "pending" else None
