# Archive instead of delete

No Sales record is removed from the database by a user (once each record's PR is in: the table below says which are). Where a Manager could delete one (a Lead, a Booking, an Opportunity, an Account), they archive it instead; the record keeps everything it holds and can be restored. What the API still removes physically carries no history of its own: a Site (an address of an Account), a Quotation draft its author discards before it is sent, and a saved board query of the user's own. (`services/visits.py` still holds a `delete_visit` that no endpoint calls; it goes with the last of these PRs.)

## The rule

- **Who.** A CRM Manager, as the delete was. Sales users and Engineers see no archive action and no restore.
- **What archiving does.** The record is marked archived, with when and by whom, by a write of those columns alone (no full save: none of the record's other validations run for a flag flip). The archive and the restore each leave a trace on the record (a comment on a Lead or a Booking, a history row on an Opportunity): who did what, and when, after the restore as well. It leaves every list (unless the list's archive filter asks for it), every picker, and the figures, warnings and reminders. It still opens at its own URL, read-only, with a notice; a Manager restores it from there. Restoring brings every field back as it was. Both move the record's `modified`, so a page opened before holds an older version and its save is refused.
- **Concurrency.** The archive and the restore read the record under its row lock (a locking read); every write on the record checks its version (`lock_document`, or Frappe's own `check_if_latest`, which the API answers as `VERSION_CONFLICT`), so an archive committed after a client read is never written over.
- **Nothing new under an archived record.** An archived record cannot be edited, converted or moved on, and no new record is created under it.
- **The list filter.** Each list has a "归档状态 / Archive state" filter: active (the default), archived, or all. Pages read the filter as `archiveState=active|archived|all`.
- **Native lists.** The lists and pickers above are the CRM's own. Frappe's own (the Desk's list and report views, its REST list, its link search) are left as they were: they put no condition on the archive and show an archived record to whoever may read it, as they show an archived Contact (a list, a report or the REST list shows it unless one filters on its archive field, CRM Archived on a Lead). Leaving archived records out of them (a condition on their list hook, which the record's own page does not read) is a product decision for later.
- **Nothing cascades except what is said below.** Records that name an archived one keep naming it.

## Per record

| Record | Archive refused when | Archived with it | State |
| --- | --- | --- | --- |
| Lead | it is converted (it is its Account's history) | — | done |
| Booking | its source is an Opportunity (cancel it instead, as the delete had it) | — | next |
| Opportunity | — | — (its own stakeholders, actions and history stay on it) | next |
| Account | it has open Opportunities, live Bookings or planned Visits | its active Contacts, restored with it | next |
| Contact | — (archived through its own page, as before) | — | as before |
| Visit | never deletable; no archive | — | — |

## Lead

- API: `leads.archive_lead(id)` and `leads.unarchive_lead(id)` (POST, Manager); `leads.list_leads` takes `archiveState`; the Lead carries `archived`, and `archivedAt` and `archivedBy` while archived.
- An archived Lead is refused an edit and a conversion (`INVALID_TRANSITION`, "a Manager can restore it from the archive"); a converted Lead is refused the archive: one whose status says so, the CRM's or ERPNext's own, or which a conversion left a trace on whatever its status (one of its conversion columns; a Customer naming it as the Lead it was made from, ERPNext's own mark of a conversion, from which ERPNext sets its status on the Customer's insert and whenever it works the Lead's status out again (the Lead's save, an ERPNext Opportunity or Quotation of its own), not when the link is given later; a deal naming it as its source; a conversion in a deal's stage history: a legacy conversion, or one repaired in the Desk, can leave the status, or any one trace, behind). ERPNext's own conversion in the Desk (a Customer made from the Lead) reads no archive flag: it is not refused for an archived Lead, which stays archived.
- Every figure and warning reads a Lead only through its conversion (its column naming a deal, or the deal's stage history), which an archived Lead has none of: Review's new qualified leads (and the targets counted on them), the board's last activity of a deal and the warnings' stagnation (a deal's last activity). Plan reads no Lead (its lead commitments are a Manager's numbers); no reminder reads a Lead.
- ERPNext keeps a Lead's email unique over every Lead (CRM Settings `allow_lead_duplication_based_on_emails` is off), archived ones included: a new Lead with the email of an archived one is refused (`CONFLICT`, "Another Lead already uses this email address."); a Manager restores the archived Lead or the user picks another email. The Lead's owner is not told of an archive (the delete did not tell them either).
- Data: custom fields `custom_crm_archived` (Check), `custom_crm_archived_at` (Datetime) and `custom_crm_archived_by` (Link User) on Lead, installed by the custom-field sync on migrate.
