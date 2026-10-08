from frappe.model.document import Document


class CRMTerritoryAssignment(Document):
    def lock_write_context(self):
        from rayher_crm.services.territory_admin import lock_assignment_sales, lock_catalogue
        self.flags.crm_assignment_sales_active = lock_assignment_sales(self.sales_owner)
        lock_catalogue()

    def insert(self, *args, **kwargs):
        self.lock_write_context()
        return super().insert(*args, **kwargs)

    def _save(self, *args, **kwargs):
        # Document._save locks the parent in check_if_latest, before validate.
        self.lock_write_context()
        return super()._save(*args, **kwargs)

    def validate(self):
        from rayher_crm.services.territory_admin import validate_assignment_document
        validate_assignment_document(self)
