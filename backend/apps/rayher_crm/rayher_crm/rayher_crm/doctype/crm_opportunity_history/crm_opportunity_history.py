from frappe.model.document import Document


class CRMOpportunityHistory(Document):
    def before_insert(self):
        from rayher_crm.services.cockpit_identity import capture_owner_identity

        capture_owner_identity(self)
