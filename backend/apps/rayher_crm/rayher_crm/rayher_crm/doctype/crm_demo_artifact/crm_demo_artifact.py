import frappe
from frappe.model.document import Document


class CRMDemoArtifact(Document):
    def on_trash(self):
        frappe.throw("CRM Demo Artifact is immutable")
