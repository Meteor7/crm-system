import frappe
from frappe.model.document import Document


class CRMVisitMeetingRecord(Document):
    """A visit's meeting record is changed only through the visit record service.

    The service checks what the DocPerms cannot: that the visit is in scope, that
    its owner or a Manager is writing (not a colleague who only holds its action),
    and that the Manager has not reviewed it yet -- and a complete record then
    submits the visit for review. The service writes with ``ignore_permissions``;
    a write or delete through the standard document API (REST, Desk, import) does
    not, and is refused. The DocPerms installed by ``install_crm_doc_permissions``
    grant no write or delete either, and scope reads to the visit; this rule is the
    second line behind them, so a widened DocPerm cannot reopen the document API.
    """

    def validate(self):
        if not self.flags.ignore_permissions:
            frappe.throw(
                "CRM Visit Meeting Records are changed only through the Visit record service",
                frappe.PermissionError,
            )

    def on_trash(self):
        # Nothing in the service deletes a record; deleting one through the document
        # API would leave a submitted or reviewed visit without its minutes.
        if not self.flags.ignore_permissions:
            frappe.throw(
                "CRM Visit Meeting Records cannot be deleted through the document API",
                frappe.PermissionError,
            )
