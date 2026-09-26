import frappe
from frappe.model.document import Document

# Set by an upload service right before it inserts an artifact. Flags live only
# on the in-memory document, so they cannot be supplied through the REST API or
# the Desk form.
SERVICE_OWNED_ARTIFACT_FLAG = "crm_service_owned_artifact"


class CRMDemoArtifact(Document):
    """Demo artifacts are created only by the upload services.

    Demo Request forms, Test Reports and Customer Reports are uploaded through
    services that scan the file, check the workflow stage, allocate the version
    and record the real author. A row inserted any other way could claim an
    arbitrary evaluation, round, author, hash or file link and would still show
    up in the Article archive, so every insert must carry the service flag.
    """

    def before_insert(self):
        if not self.flags.get(SERVICE_OWNED_ARTIFACT_FLAG):
            frappe.throw(
                "CRM Demo Artifact records are created only through the Demo upload services",
                frappe.PermissionError,
            )

    def on_trash(self):
        frappe.throw("CRM Demo Artifact is immutable")
