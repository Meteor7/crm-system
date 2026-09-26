import frappe
from frappe.model.document import Document


class CRMTestRun(Document):
    """The round marker is owned by the evaluation service, not by the caller.

    `_has_completed_test_run` gates the Internal Review transition on a run
    completed in the evaluation's *current* round. If `test_round` were an
    ordinary writable field, a CRM Engineer or CRM Manager could re-tag a
    historical round-1 run through the standard document API and pass the
    retest gate without running the retest, corrupting the round history.
    So the round is stamped from the parent on insert and frozen afterwards.
    """

    def before_insert(self):
        self.test_round = _current_round(self.evaluation)

    def validate(self):
        if self.is_new():
            return
        if self.has_value_changed("test_round"):
            frappe.throw("CRM Test Run round is assigned on creation and cannot be changed")
        if self.has_value_changed("evaluation"):
            frappe.throw("CRM Test Run cannot be moved to another Evaluation")


def _current_round(evaluation: str | None) -> int:
    if not evaluation:
        frappe.throw("CRM Test Run requires an Evaluation")
    current = frappe.db.get_value("CRM Evaluation", evaluation, "test_round")
    if current is None:
        frappe.throw(f"CRM Evaluation {evaluation} does not exist")
    return int(current or 1)
