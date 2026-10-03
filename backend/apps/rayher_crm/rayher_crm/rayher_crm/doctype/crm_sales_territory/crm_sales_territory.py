import frappe
from frappe.model.document import Document

from rayher_crm.services.territory_tree import ancestors


class CRMSalesTerritory(Document):
    def validate(self):
        self.territory_name = (self.territory_name or "").strip()
        if not self.parent_territory:
            return
        parents = dict(frappe.get_all(
            self.doctype, filters={"parent_territory": ["is", "set"]}, fields=["name", "parent_territory"],
            as_list=True, limit_page_length=0,
        ))
        if self.parent_territory == self.name or self.name in ancestors(self.parent_territory, parents):
            frappe.throw("A territory cannot be its own parent or sit below itself.")
