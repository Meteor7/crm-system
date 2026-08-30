# Quotation Adversarial Fixes Design

## Goal

Make the Quotation workflow safe under concurrent use, keep selectors and lists complete as data grows, prevent stale preview and stale-tab feedback, enforce bounded inputs, migrate every existing reference number to the approved `PKYYYYMMDD-A<n>` format, and correct mixed-device pricing without changing the approved Word-template layout.

## Confirmed business decisions

- The initial quotation date determines the permanent reference-number date component.
- References are allocated per date as `PKYYYYMMDD-A1`, `-A2`, and so on, in initial creation order.
- A quotation may contain multiple parent devices and child accessories.
- Each parent device receives its own configuration subtotal and per-unit configuration price.
- A parent configuration subtotal equals the device line amount plus all charged child-accessory line amounts. Included accessories contribute zero.
- The parent per-unit configuration price equals its configuration subtotal divided by the parent device quantity. Accessory quantity remains the total quantity for that parent group.
- The document still retains quotation subtotal, whole-document discount, and discounted total.
- The fixed commercial terms and Word-derived header/footer/layout remain unchanged.
- Existing quotation masters, versions, statuses, owners, opportunities, and history must be preserved.

## Backend design

### Concurrency and lifecycle

Creation and new-version allocation will serialize on the relevant database state. Reference allocation will lock the quotation rows for the initial quote date before choosing the next `A<n>` suffix. New-version creation will lock the quotation master, recompute `latest_version_no`, and rely on a database unique index over `(quotation, version_no)` as a final invariant.

`discard_draft` and `record_decision` will accept `expectedModified` and use the same optimistic-lock contract already used by draft save and publish. A stale browser receives `VERSION_CONFLICT`; it never silently deletes or changes a newer version.

Version lookup, preview, and download will translate missing or foreign version IDs into stable domain errors instead of generic HTTP 500 responses. Unexpected exceptions continue to roll back the database transaction.

### Pricing and PDF context

The rules layer will return totals for each parent device group. The PDF context will expose `deviceGroups`, each containing configuration subtotal and per-unit configuration price. The template will render those values beside the relevant parent configuration and will not divide the whole quotation total by the total count of unrelated devices.

The overall subtotal and discount calculations remain unchanged. Preview and published PDF continue to use the same renderer.

### Input bounds

The service will reject more than 200 quotation lines, names or models longer than 140 characters, descriptions longer than 5,000 characters, and month values outside 1 through 120. Quantities remain positive integers. Existing exact-decimal money validation remains unchanged.

### Reference migration

An idempotent Frappe patch will:

1. Read each quotation's earliest version quote date, falling back to master creation date only when necessary.
2. Order quotations by date and creation, then allocate deterministic `PKYYYYMMDD-A<n>` values.
3. Update the master and every version in one transaction.
4. Re-render attached formal PDFs with the new header reference while preserving version number and lifecycle status.
5. Leave all quotation and version records intact and make a second execution a no-op.

The unique master `ref_no` constraint remains active throughout the migration by using temporary collision-free values inside the transaction before final allocation.

## Frontend design

### Complete selectors and lists

The detail page will page through all active contacts in batches of 200 before populating the contact picker. Account sites already arrive as an unbounded account-owned list and remain unchanged. A failure to load contacts will show a selector-specific error without discarding an already-loaded quotation detail.

The creation modal will page through all eligible Opportunities. The Quotation page will use server pagination rather than permanently showing only the first 100 rows. No keyword-search module will be added.

### Preview ordering and stale tabs

Each preview request receives a monotonically increasing sequence number. Only the latest request may replace the iframe object URL; late responses are revoked and ignored. This prevents an older PDF response from overwriting a newer edit.

When the window regains focus or the document becomes visible, a detail page with no pending local edit will refresh its current version. If local edits exist, optimistic concurrency remains authoritative and the page does not overwrite them.

### Error feedback

Conflict, validation, selector-loading, and not-found failures remain visible near the affected action. Successful saves continue to update the latest server `modified` timestamp used by later writes.

## Testing

Backend unit and Frappe integration tests will cover deterministic reference allocation, idempotent migration, compound version uniqueness, concurrent/stale lifecycle commands, mixed-device group totals, item/text/month limits, and stable not-found errors.

Frontend tests will cover paginated contact and Opportunity loading, quotation pagination, selector partial failure, out-of-order preview responses, focus refresh with and without pending edits, and propagation of `expectedModified` for discard and decision actions.

Deployment verification will include typecheck, focused Vitest suites, backend contract tests, Frappe integration tests, build, migration on the LAN database, direct database invariants, HTTP health, and browser QA of contact/site selection, editing, autosave, preview, publish/download, version history, and migrated header references.

## Non-goals

- No product/device catalog import.
- No quotation keyword search.
- No tax splitting.
- No changes to fixed Incoterm, payment terms, installation/training text, company signature, or watermark behavior.
- No deletion or reset of existing quotation data.