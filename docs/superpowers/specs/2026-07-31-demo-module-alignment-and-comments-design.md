# Demo Module Alignment and Comments Design

## Goal

Unify Demo Archive, Demo Request, and Demo Test around one project-detail experience; add persistent project comments; align Request and Test list layouts with the Contacts module; and insert `Internal Review` before `Customer Review` throughout the Demo workflow.

## Scope and constraints

- Work only in the existing Vue 3, TypeScript, and Mock adapter surface.
- Do not add dependencies or change the application shell.
- Preserve existing role checks and Request/Test operations.
- Keep customer, Sales, Engineer, status, search, handoff, document, Test Run, and report behavior.
- Frappe Comment persistence remains explicitly unsupported; its adapter returns `NOT_IMPLEMENTED`.
- Existing Mock IndexedDB snapshots must remain readable. New comment storage is initialized without resetting unrelated Demo data.

## Recommended architecture

### Unified Demo project detail

Add a dedicated route:

`/demo-workflow/:demoId`

All project links from the project-cycle board, lifecycle board, Demo Archive, Demo Request, and Demo Test route to this page. Request and Test records resolve to the shared Demo Request ID so every module opens the same project record.

The existing query-based detail URL remains compatible by redirecting or forwarding to the dedicated route. The list surface and filters remain in `/demo-workflow`.

### Detail page composition

The page follows the approved high-fidelity reference while using the current CRM design tokens:

1. Back navigation and breadcrumb.
2. Project title and customer.
3. Summary fields: current status, Sales owner, Engineer owner, and creation date.
4. Full-width project timeline.
5. Two primary tabs:
   - `Information`
   - `Comment`

`Information` contains:

- Demo Request snapshot
- wafer/sample details
- Demo Test runs and results
- artifacts
- project conclusion
- participant summary

`Comment` contains:

- a required comment composer
- chronological collaboration feed
- author name, role, and timestamp
- seeded historical comments and newly published comments
- an empty state when no comments are available

The Comment tab implements plain project comments only. Replies, reactions, attachments, and active `@mention` notification behavior are outside this scope.

### Comment data and API

Add a `DemoCommentDto` with:

- `id`
- `demoRequestId`
- `author`
- `role`
- `body`
- `createdAt`

Extend the Mock Demo snapshot with optional `comments` storage so existing version-6 snapshots remain readable. Seed representative comments for one project and initialize missing comment arrays lazily.

Extend `CrmApi` with:

- `listDemoComments(demoRequestId)`
- `addDemoComment(demoRequestId, { body })`

Mock behavior:

- trim the body
- reject empty comments with `VALIDATION_ERROR`
- verify the Demo Request is visible to the active role
- use the active bootstrap user as author
- persist through the shared Demo repository
- return comments newest first

Frappe behavior:

- return `NOT_IMPLEMENTED` with a clear Demo Comment message

### Demo Request alignment

Replace the current left rail plus inline detail workspace with:

- Contacts-style filter bar
- summary table
- clickable Request ID/project name
- fixed right operation panel for the selected row

The table shows only summary fields:

- Request ID and project
- customer
- Sales
- Engineer
- status
- target date
- updated date

The right panel retains current actions:

- submit
- edit
- cancel
- engineer review
- manager approval
- DOCX generation

Detailed Request fields are removed from the list page and shown only on the unified Demo detail page.

### Demo Test alignment

Replace the current left rail plus inline detail workspace with:

- Contacts-style filter bar
- summary table
- clickable Test ID/project name
- fixed right operation panel for the selected row

The table shows:

- Test ID and project
- customer
- source Request
- Engineer
- stage
- planned completion
- latest run status

The right panel retains:

- status transition
- Test Run DDL
- Test Run creation
- Internal Review progression
- External Report in Customer Review

Detailed Test fields and metrics appear only on the unified Demo detail page.

## Internal Review workflow

Insert `Internal Review` between `Test Execution` and `Customer Review`.

The active Evaluation flow becomes:

1. Requested
2. Scope Confirmed
3. Sample Received
4. Scheduled
5. Testing
6. Internal Review
7. Customer Review
8. Accepted or Rejected

`Analysis` remains a legacy-compatible status and maps to `Internal Review`.

Synchronize the new stage across:

- `EvaluationStatus`
- `DemoLifecycleStage`
- Evaluation grouping and transition options
- Mock transition validation
- Demo Test navigation and summary counts
- project-cycle timeline
- lifecycle pipeline columns
- detail-page timeline
- workflow approvals
- related tests and seeded data

External Report remains available only in `Customer Review`.

## Timeline structure

The detail timeline preserves the circuit-style parallel preparation gate:

- `Sales Preparation`
- `Engineer Review`
- `Manager Approval`
- `Wafer & Test Preparation`
  - `Wafer Preparation`
  - `Test Preparation`
- `Test Execution`
- `Internal Review`
- `Customer Review`

The preparation gate opens only when both preparation branches are complete.

## Navigation behavior

- Project-cycle and lifecycle rows route to the unified detail page.
- Demo Archive entries route to the unified detail page instead of rendering a second inline detail column.
- Request and Test project links route to the same detail page using the Demo Request ID.
- Back navigation returns to the originating module when a return route is supplied; otherwise it returns to Demo Archive.
- Existing Request-to-Test focus links remain supported.

## Error and empty states

- Detail load failure uses the existing `DataState` error pattern.
- A missing project displays “未找到 Demo 项目” and a back action.
- Comment submission shows an inline error without clearing the draft.
- Empty Request/Test tables use existing empty-state styling.
- An unavailable Frappe Comment API presents the adapter message; it does not imply the comment was saved.

## Testing

Use test-driven development for each behavior:

1. Domain tests for `Internal Review` mapping and transitions.
2. Mock repository/API tests for comment persistence, validation, and role-scoped visibility.
3. Router/page tests for dedicated project detail navigation.
4. Detail-page tests for `Information` and `Comment`, publishing, and timeline rendering.
5. Request workspace tests for Contacts-style table, detail link, and retained actions.
6. Evaluation workspace tests for Contacts-style table, detail link, retained actions, and Internal Review.
7. Existing workflow/handoff/report tests to prevent regressions.
8. Production Vite build.
9. Browser verification at the active local preview.

## Acceptance criteria

- Every visible Demo project opens a dedicated detail page.
- The detail page has working `Information` and `Comment` tabs.
- A non-empty Comment persists in Mock storage and reappears after reload.
- Demo Request and Demo Test use table-based layouts matching Contacts while retaining right-side operation panels.
- Request/Test detailed data is not expanded on list pages.
- `Internal Review` appears between Test Execution and Customer Review in every relevant module.
- External Report remains restricted to Customer Review.
- The circuit-style preparation branch remains visible on the detail timeline.
- Existing Request approval to Test handoff remains functional.
