# Demo Lifecycle and Archive Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Demo Request hand off directly to Demo Test, move terminal Demo Tests into classified history archives, migrate old browser data, and remove the legacy Nanjing Fab report link.

**Architecture:** Keep one IndexedDB-backed Demo Repository and derive all three pages from it. Add an in-place snapshot migration, apply lifecycle filtering only in the relevant workspaces, and classify archive DTOs from the linked Evaluation terminal state.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, IndexedDB, Vite

## Global Constraints

- Modify only the current Vue / Mock Demo; do not add or change a Frappe backend.
- `Accepted` and `Rejected` are the only completed Demo Test states.
- Preserve existing IndexedDB user data and Artifact Blobs during migration.
- Do not restore the legacy `reportLink`; keep the formal External Report PDF workflow.
- Keep existing role and account-scope filtering.

---

### Task 1: Version and migrate the shared Demo snapshot

**Files:**
- Modify: `src/demo/demo-repository.ts`
- Test: `src/demo/demo-repository.test.ts`

**Interfaces:**
- Consumes: stored snapshot version 1 with `demoRequests`, `evaluations`, and `artifacts`.
- Produces: `migrateDemoSnapshot(snapshot): DemoSnapshot` and version 2 snapshots with bidirectional Request/Evaluation links.

- [ ] **Step 1: Write the failing migration test**

Add a test that stores a version 1 snapshot with an Evaluation missing `demoRequestId`, a Request missing `evaluationId`, existing Q&A/Artifact Blob, and a legacy `reportLink`. Assert that `repository.read()` returns version 2, links both records, removes `reportLink`, preserves Q&A, and preserves Blob content.

- [ ] **Step 2: Run the migration test and verify RED**

Run: `pnpm.cmd exec vitest run src/demo/demo-repository.test.ts`

Expected: FAIL because an existing snapshot is returned unchanged as version 1.

- [ ] **Step 3: Implement the minimal migration**

Change `DemoSnapshot.version` to `2`, accept version 1 storage input, and migrate on `ensure()` before returning. Link by existing `request.evaluationId` first, otherwise by a unique `accountId + requirementId` match. Backfill the reciprocal ID, add missing submit history to non-Draft requests, delete legacy `reportLink`, save the migrated snapshot, and never clear arrays or Blobs.

- [ ] **Step 4: Run the repository test and verify GREEN**

Run: `pnpm.cmd exec vitest run src/demo/demo-repository.test.ts`

Expected: all repository tests pass.

---

### Task 2: Make Request and Test pages show only active work

**Files:**
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Test: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: complete API lists including terminal records.
- Produces: page-local `activeRequests` and `activeEvaluations` projections.

- [ ] **Step 1: Write failing page tests**

Add assertions that Demo Request has no completed column and renders neither `Converted` nor `Cancelled`; Demo Test has no `Closed` column and renders neither `Accepted` nor `Rejected`, while retaining `Customer Review`.

- [ ] **Step 2: Run the page tests and verify RED**

Run: `pnpm.cmd exec vitest run src/pages/delivery-workflow.test.ts`

Expected: FAIL because both pages currently render terminal buckets.

- [ ] **Step 3: Implement the minimal projections**

In `DemoRequestsPage.vue`, add:

```ts
const activeRows = computed(() => rows.value.filter((item) => !['Converted', 'Cancelled'].includes(item.status)))
```

Remove the completed bucket and terminal status filter options. Use `activeRows` for totals, owners, result count, bucket counts, and cards.

In `EvaluationsPage.vue`, add:

```ts
const activeRows = computed(() => rows.value.filter((item) => !['Accepted', 'Rejected'].includes(item.status)))
```

Remove `Closed` from `groups` and use `activeRows` for header count, accounts, empty state, and group rows.

- [ ] **Step 4: Run the page tests and verify GREEN**

Run: `pnpm.cmd exec vitest run src/pages/delivery-workflow.test.ts`

Expected: all delivery workflow tests pass.

---

### Task 3: Classify all non-cancelled Demo archives

**Files:**
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Test: `src/api/mock-adapter.test.ts`
- Test: `src/pages/seven-page-workspace.test.ts`

**Interfaces:**
- Produces: `DemoWorkflowDto.archiveCategory: 'In Progress' | 'Completed'`.
- Classification: linked Evaluation `Accepted` or `Rejected` means `Completed`; every other non-cancelled Request means `In Progress`.

- [ ] **Step 1: Write failing API and UI tests**

Assert that CRM Administrator archive results include every non-cancelled Request, Management Viewer still excludes Draft, cancelled records are absent, and terminal Evaluations are classified as completed. Assert that the archive page renders “进行中的 Demo” and “已完成历史归档” sections.

- [ ] **Step 2: Run the archive tests and verify RED**

Run: `pnpm.cmd exec vitest run src/api/mock-adapter.test.ts src/pages/seven-page-workspace.test.ts`

Expected: FAIL because `listDemoWorkflows()` filters all records through `wasDemoRequestSubmitted` and has no category.

- [ ] **Step 3: Implement archive inclusion and classification**

Replace the global submitted filter with:

```ts
.filter((request) => request.status !== 'Cancelled')
.filter((request) => role !== 'Management Viewer' || wasDemoRequestSubmitted(request))
```

Set `archiveCategory` from the linked Evaluation status. In `DemoWorkflowPage.vue`, compute the two category arrays and render separate labeled lists while preserving the selected archive detail view.

Keep the existing current-released-report checks in `canReadDemoArtifact`; they already permit scoped members to download the current released PDF in `Customer Review`, `Accepted`, or `Rejected` states.

- [ ] **Step 4: Run the archive tests and verify GREEN**

Run: `pnpm.cmd exec vitest run src/api/mock-adapter.test.ts src/pages/seven-page-workspace.test.ts`

Expected: all targeted archive tests pass.

---

### Task 4: Remove the legacy Nanjing Fab report interface

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/api/mock-data.ts`
- Modify: `src/features/evaluations/EvaluationCard.vue`
- Test: `src/features/evaluations/EvaluationCard.test.ts`

**Interfaces:**
- Removes: `EvaluationDto.reportLink` and the external anchor rendered from it.
- Preserves: the `External Report` button and formal PDF modal workflow.

- [ ] **Step 1: Write the failing card test**

Mount a Nanjing Fab Evaluation containing a legacy `reportLink` through a test-only widened object. Assert there is no anchor labeled `Report`, while `[data-report-action]` remains available for an authorized user.

- [ ] **Step 2: Run the card test and verify RED**

Run: `pnpm.cmd exec vitest run src/features/evaluations/EvaluationCard.test.ts`

Expected: FAIL because the old external anchor is rendered.

- [ ] **Step 3: Remove the legacy interface**

Remove `reportLink` from `EvaluationDto`, remove the Nanjing Fab seed URL, and remove `Link2`, `safeExternalUrl`, `reportUrl`, and the legacy `<a>` from `EvaluationCard.vue`.

- [ ] **Step 4: Run the card test and verify GREEN**

Run: `pnpm.cmd exec vitest run src/features/evaluations/EvaluationCard.test.ts`

Expected: all EvaluationCard tests pass.

---

### Task 5: Verify and publish the revised LAN preview

**Files:**
- No source files beyond Tasks 1-4.

**Interfaces:**
- Produces: rebuilt `dist` and LAN preview at `http://203.0.113.10:4173/`.

- [ ] **Step 1: Run focused regression tests**

Run:

```powershell
pnpm.cmd exec vitest run src/demo/demo-repository.test.ts src/api/mock-adapter.test.ts src/pages/delivery-workflow.test.ts src/pages/seven-page-workspace.test.ts src/features/evaluations/EvaluationCard.test.ts
```

Expected: zero failed tests.

- [ ] **Step 2: Run typecheck and build**

Run:

```powershell
pnpm.cmd typecheck
pnpm.cmd build
```

Expected: both commands exit 0.

- [ ] **Step 3: Restart and smoke-check the LAN preview**

Start `pnpm.cmd preview:lan` in the background, verify HTTP 200 from `http://127.0.0.1:4173/` and `http://203.0.113.10:4173/`, then confirm the three Demo workspaces render their new categories without a visible alert.
