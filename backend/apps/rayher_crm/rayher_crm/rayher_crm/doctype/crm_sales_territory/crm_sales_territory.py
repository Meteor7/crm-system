from frappe.model.document import Document


class CRMSalesTerritory(Document):
    def insert(self, *args, **kwargs):
        from rayher_crm.services.territory_admin import lock_catalogue
        lock_catalogue()
        return super().insert(*args, **kwargs)

    def _save(self, *args, **kwargs):
        # Keep the same catalogue-before-row order as the administration API.
        from rayher_crm.services.territory_admin import lock_catalogue
        lock_catalogue()
        return super()._save(*args, **kwargs)

    def validate(self):
        from rayher_crm.services.territory_admin import validate_territory_document
        self.territory_name = (self.territory_name or "").strip()
        validate_territory_document(self)
