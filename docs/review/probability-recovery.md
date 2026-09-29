# Probability downgrade recovery (#13)

## Delivery boundaries

The first PR adds required recovery plans and editable, audited revisions. It targets
`codex/plan-integration`, which already carries the four probability levels and Review.
The second, stacked PR adds recorded actions, pending downgrade warnings, and Manager
in-app notifications. Neither PR changes #21 queries/exports or the Status ledger migration.
The second PR covers only the downgrade category of #27, not its other warning categories.

## Agreed business rules

- A downward move in `Low probability < Pipeline < Upside < Committed` requires both a
  reason and a recovery plan. Initial assignment, unchanged levels, and upgrades do not.
- The original Probability History remains immutable. Each downgrade gets a separate
  recovery plan, so a subsequent downgrade cannot overwrite an older plan or resolution.
- The current Opportunity owner is responsible. That owner and a CRM Manager with access
  may edit the plan. Changing the owner transfers responsibility; an old owner cannot edit.
- Each creation or actual text change appends the server's author, timestamp, and full plan.
  A no-op save does not create a revision. The plan is 1–4000 characters after trimming.
- Editing a plan is not evidence of action taken and does not clear a warning.
- Confirmed by the user: recipients follow existing CRM Manager permissions and delivery
  uses in-app notifications. No new approval gate or external messaging channel is added.

## Action recording and warning semantics

Only the **current Opportunity owner** may record an action already taken, including a
Manager who is that owner. Other Managers can edit plans and review the history, but cannot
attest on behalf of the owner. An action is a required 1–4000-character account of what was
done, stored with the server author/time and an immutable plan snapshot. It clears only the
linked downgrade. The endpoint rejects stale versions and repeated resolution. Historical
events must have a plan explicitly recorded before an action can be recorded. Later plan
clarifications preserve the handled state and original action. Reopening is not an API option;
a new downgrade is a new pending event.

Review uses its existing selected Shanghai week/month/quarter/year window, defaulting to the
last complete week. There is no saved last-review checkpoint. Downgrade events fall within that
window; their plans, owner and resolution are **current**, including when looking at an older
period. Both pending and handled lists follow current owner/market/region filters. The warning
count is unique opportunities with at least one pending event; details show individual events.
Missing legacy plans remain pending. The separate period history includes handled events,
so clearing a warning never erases the downgrade. This does not change lost/overdue warnings
or implement the other categories in #27.

The successful original downgrade inserts one notification for every active, unambiguous
CRM Manager who currently has Opportunity read permission, including the actor if that actor
is a Manager. Event/recipient dedupe keys are unique. Initial assignments, upgrades, no-ops,
legacy backfills, plan edits and action recording do not resend the downgrade notification.
Notifications are in the same transaction as the downgrade and initial plan; delivery insertion
failure rolls back all of them. Notification links and Review links highlight the exact event.
Inbox read/unread is independent of recovery state: clearing the warning keeps the inbox
event as history. Disabled/ambiguous users are excluded by the existing recipient resolver.

The mock adapter models plan/action validation and concurrency. Its existing notification
inbox and Review aggregation remain unavailable; server delivery and counts are verified
against the Frappe implementation, not simulated by client-only toasts.

## Concurrency, access, and migration

The parent Opportunity version and the recovery version are checked separately. Writes lock
the parent before the recovery; the original downgrade, plan, and first audit revision commit
together. A failed revision insertion rolls the business write back. Generic Frappe writes
cannot bypass this API. Native reads inherit the parent access rules, including Private
Account restrictions. A Public-account Opportunity owner with a hidden Site can maintain
the recovery plan through the custom API, without exposing the Site.

Existing probability events remain unchanged. Events without recovery records explicitly
show a missing historical plan. An authorized person can add one using an explicit null
recovery version. A competing creation conflicts instead of replacing the first plan.
Standard `bench migrate` creates the two new DocTypes; there is no fabricated historical
plan or author/time backfill. Recovery revisions are deleted before recovery records in the
explicit staging-dataset wipe order; ordinary users cannot delete the audit.

The editor keeps failed drafts. A version conflict requires an explicit reload, labeled as
discarding the local draft. Identity changes, access loss, navigation and unmount invalidate
pending UI responses. Mock storage assigns existing opportunities a stable initial version
and advances persisted versions monotonically across API instances.

## Verification

Backend tests exercise required plan validation, version conflicts and retries, legacy
creation races, audit failure rollback, immutable events, role/Private Account restrictions,
owner transfer, hidden Sites and generic-write denial. Frontend tests exercise the real
mock adapter and detail page, including two-client conflicts, draft preservation, explicit
reload/retry, busy submission, identity changes and permission loss.
