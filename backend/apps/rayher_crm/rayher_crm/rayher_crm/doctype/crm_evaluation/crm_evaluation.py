import frappe
from frappe.model.document import Document

# Set by the evaluation service when a customer retest opens the next round.
# Flags live only on the in-memory document, so they cannot be supplied
# through the REST API or the Desk form.
OPEN_RETEST_ROUND_FLAG = "crm_open_retest_round"


class CRMEvaluation(Document):
    """The current round is owned by the evaluation service.

    ``read_only`` on ``test_round`` only hides the field in the form, and the
    DocPerms in ``permissions/scope.py`` are not the last line of defence either:
    every write that matters goes through the service with
    ``ignore_permissions=True``. Without a controller rule, anything writing the
    document could set the round back to 1 after a retest opened round 2 and let
    ``_has_completed_test_run`` accept the old completed round-1 run, advancing
    without performing the retest. Every evaluation therefore starts at round 1,
    and the round may only move forward by one, and only when the service opens
    a retest.
    """

    def before_insert(self):
        self.test_round = 1

    def validate(self):
        if self.is_new():
            return
        if not self.has_value_changed("test_round"):
            return
        old_round = int(self.get_doc_before_save().test_round or 1)
        new_round = int(self.test_round or 1)
        if self.flags.get(OPEN_RETEST_ROUND_FLAG) and new_round == old_round + 1:
            return
        frappe.throw(
            "CRM Evaluation test round is advanced only by a customer retest and cannot be edited"
        )
