import frappe
from frappe.model.document import Document


class CRMFileAccessAudit(Document):
    def before_save(self):
        if not self.is_new():
            frappe.throw("CRM File Access Audit is append-only")

    def on_trash(self):
        frappe.throw("CRM File Access Audit is append-only")
