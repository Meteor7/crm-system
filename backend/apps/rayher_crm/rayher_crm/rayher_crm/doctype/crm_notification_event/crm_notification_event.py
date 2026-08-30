import frappe
from frappe.model.document import Document


class CRMNotificationEvent(Document):
    def before_save(self):
        if not self.is_new():
            frappe.throw("CRM Notification Event is mutated only by notification service commands")

    def on_trash(self):
        frappe.throw("CRM Notification Event cannot be deleted")
