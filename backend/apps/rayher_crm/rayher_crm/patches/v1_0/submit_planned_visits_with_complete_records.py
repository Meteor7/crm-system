"""Submit visits whose record was already complete for Manager review.

Saving a complete visit record now submits the visit straight away. Visits whose
record was completed before that rule existed are still Planned (or Visited) and
would never reach Manager review without re-saving, so move them once. Visits
with an incomplete or missing record are left untouched.

Like the live path in `visit_meetings._mark_record_submitted`, an empty outcome
or next action is filled from the record's conclusion and the first line of its
follow-up, so a migrated visit is not left with a blank outcome column.
`modified_by` is stamped so the move is attributable, and the Managers get the
same reminder the live transition sends -- a visit that appears in their queue
silently is one nobody reviews.
"""

import frappe

REQUIRED_FIELDS = ("purpose", "attendees", "agenda", "summary", "conclusion", "followup")
# MariaDB's bare TRIM() strips spaces only. The live check is Python `strip()`,
# which also strips tabs, newlines and carriage returns -- so a record holding
# nothing but a newline would be migrated here and then refused by `review_visit`
# as incomplete. Fold those characters away before trimming to match.
_BLANK = "REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(r.`{field}`, {empty}), CHAR(9), {empty}), CHAR(10), {empty}), CHAR(13), {empty}), CHAR(11), {empty})"


def execute():
    if not frappe.db.table_exists("CRM Visit") or not frappe.db.table_exists("CRM Visit Meeting Record"):
        return
    empty = "''"
    complete = " AND ".join(
        f"TRIM({_BLANK.format(field=field, empty=empty)}) <> {empty}" for field in REQUIRED_FIELDS
    )
    names = [
        row[0] for row in frappe.db.sql(
            f"""
            SELECT v.`name`
            FROM `tabCRM Visit` v
            JOIN `tabCRM Visit Meeting Record` r ON r.`visit` = v.`name`
            WHERE v.`status` IN ('Planned', 'Visited') AND {complete}
            """
        )
    ]
    if not names:
        return
    from frappe.utils import now

    from rayher_crm.services.visit_meetings import (
        RECORD_REQUIRED_FIELDS,
        _notify_managers_of_submission,
        next_action_from_followup,
        outcome_from_conclusion,
    )

    submitted = []
    for name in names:
        record = frappe.db.get_value(
            "CRM Visit Meeting Record", {"visit": name}, list(RECORD_REQUIRED_FIELDS), as_dict=True,
        )
        # The SQL above is only a coarse filter. Python's strip() -- the rule the live
        # path and review_visit apply -- also drops form feeds, NBSP and ideographic
        # spaces, and a record that is blank by that rule stays where it is.
        if not all(str(record.get(field) or "").strip() for field in RECORD_REQUIRED_FIELDS):
            continue
        # Filled in Python with the live path's own rules: SQL TRIM() only strips
        # spaces, and copying a whole follow-up or conclusion into the narrower visit
        # columns fails in MariaDB's strict mode.
        visit = frappe.db.get_value("CRM Visit", name, ["outcome", "next_action"], as_dict=True)
        values = {"status": "Minutes Submitted", "modified": now(), "modified_by": "Administrator"}
        if not str(visit.outcome or "").strip():
            values["outcome"] = outcome_from_conclusion(record.conclusion)
        if not str(visit.next_action or "").strip():
            values["next_action"] = next_action_from_followup(record.followup)
        # A visit whose data the columns cannot hold must not stop the migration. It
        # stays as it was, and the Error Log names it for somebody to look at.
        savepoint = f"crm_submit_visit_{frappe.generate_hash(length=8)}"
        frappe.db.savepoint(savepoint)
        try:
            frappe.db.set_value("CRM Visit", name, values, update_modified=False)
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(title=f"Visit {name} was not submitted for Manager review")
            continue
        submitted.append(name)
    # The live transition reminds the Managers; a visit that lands in their queue
    # without one is invisible until somebody goes looking for it.
    for name in submitted:
        _notify_managers_of_submission(frappe.get_doc("CRM Visit", name))
