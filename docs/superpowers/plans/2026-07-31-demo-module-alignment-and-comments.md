# Demo Module Alignment and Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified Demo project detail with persistent comments, Contacts-style Request/Test lists, and an `Internal Review` stage before `Customer Review`.

**Architecture:** Keep Demo Request, Evaluation, Artifact, and Comment data in the existing Mock repository and expose comments through `CrmApi`. Route every module to one `DemoDetailPage` keyed by Demo Request ID. Keep list pages summary-only and move project information into the detail page while retaining role-gated operations in right-side panels.

**Tech Stack:** Vue 3, TypeScript, Vue Router, Pinia, Vitest, Vue Test Utils, existing Mock repository and design system.

## Global Constraints

- Work only in the Vue/Mock Demo surface.
- Do not add dependencies.
- Preserve existing role checks, Request-to-Test handoff, document generation, Test Run, report release, and list filters.
- Keep existing version-6 Mock snapshots readable.
- External Report remains available only in Customer Review.
- Follow red-green-refactor for every behavior.

---

### Task 1: Add Internal Review to the workflow model

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/domain/evaluations.ts`
- Modify: `src/domain/evaluations.test.ts`
- Modify: `src/domain/demo-lifecycle.ts`
- Modify: `src/domain/demo-lifecycle.test.ts`
- Modify: `src/domain/demo-project-cycle.ts`
- Modify: `src/domain/demo-project-cycle.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-data.ts`

**Interfaces:**
- Produces: `EvaluationStatus` and `DemoLifecycleStage` containing `Internal Review`.
- Produces: project timeline step `{ key: 'internal-review', label: 'Internal Review' }`.
- Produces: transition `Testing -> Internal Review -> Customer Review`.

- [ ] Add failing domain tests asserting the new status order, lifecycle mapping, and timeline position.
- [ ] Run the focused domain tests and confirm failures mention missing `Internal Review`.
- [ ] Add the status to types, domain mappings, timeline indices, Mock timeline projection, and one seed Evaluation.
- [ ] Run focused domain and Mock adapter tests.

### Task 2: Add persistent Demo comments

**Files:**
- Modify: `src/types/workspaces.ts`
- Modify: `src/demo/demo-repository.ts`
- Modify: `src/demo/demo-repository.test.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`

**Interfaces:**
- Produces: `DemoCommentDto`.
- Produces: `CrmApi.listDemoComments(demoRequestId)`.
- Produces: `CrmApi.addDemoComment(demoRequestId, { body })`.

- [ ] Add failing repository/API tests for seeded comments, empty validation, author attribution, persistence, ordering, and missing-project rejection.
- [ ] Run focused tests and confirm failures come from missing comment APIs/storage.
- [ ] Add optional comment storage to the version-6 snapshot, seed representative comments, and implement Mock API methods.
- [ ] Add explicit Frappe `NOT_IMPLEMENTED` methods.
- [ ] Run repository, Mock adapter, and Frappe adapter tests.

### Task 3: Create the unified Demo detail page

**Files:**
- Create: `src/pages/DemoDetailPage.vue`
- Create: `src/pages/DemoDetailPage.test.ts`
- Create: `src/features/demo-workflow/DemoCommentPanel.vue`
- Modify: `src/features/demo-workflow/DemoArchiveDetail.vue`
- Modify: `src/features/demo-workflow/DemoProjectTimeline.vue`
- Modify: `src/app/router.ts`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Produces: route name `demo-detail`, path `/demo-workflow/:demoId`.
- Consumes: `listDemoWorkflows`, `listDemoComments`, and `addDemoComment`.
- Supports query `tab=information|comment` and `from`.

- [ ] Add failing router/page tests for detail navigation, Information/Comment tabs, timeline, and publishing.
- [ ] Run tests and confirm the missing route/page/API behavior fails.
- [ ] Implement the dedicated page, header, high-fidelity timeline, tabs, information layout, participants, comments, and error states.
- [ ] Change board/archive open actions to route to `demo-detail`.
- [ ] Run page and router tests.

### Task 4: Align Demo Request with Contacts

**Files:**
- Modify: `src/features/demo-requests/DemoRequestWorkspace.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Create or modify: `src/features/demo-requests/DemoRequestWorkspace.test.ts`

**Interfaces:**
- Produces: Contacts-style Request table and right operation panel.
- Emits: existing action events plus `open-detail`.

- [ ] Add failing component/page tests for table headings, detail link event, summary-only list, and retained operations.
- [ ] Run focused tests and confirm the old rail/inline detail behavior fails.
- [ ] Replace the rail and inline detail with filter bar, table, selection state, and role-gated right action panel.
- [ ] Route `open-detail` to the unified Demo detail.
- [ ] Run Request workspace and delivery workflow tests.

### Task 5: Align Demo Test and expose Internal Review

**Files:**
- Modify: `src/features/evaluations/EvaluationWorkspace.vue`
- Modify: `src/features/evaluations/EvaluationWorkspaceNav.vue`
- Modify: `src/features/evaluations/EvaluationWorkspace.test.ts`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Produces: Contacts-style Test table and right operation panel.
- Emits: existing action events plus `open-detail`.
- Produces: `internal` Evaluation view.

- [ ] Add failing tests for table headings, detail routing, right-side operations, Internal Review navigation, and status progression.
- [ ] Run focused tests and confirm failures are caused by the old layout and missing stage.
- [ ] Replace the rail/inline details with filter bar, table, selection, and operation panel.
- [ ] Add the Internal Review navigation/category and route detail links to the unified Demo detail.
- [ ] Run Evaluation and delivery workflow tests.

### Task 6: Full synchronization and verification

**Files:**
- Modify as required by failing focused tests only.

**Interfaces:**
- Verifies the complete user-visible workflow.

- [ ] Run all focused Demo domain, repository, adapter, workspace, page, permission, and delivery tests with `.superpowers/**` excluded.
- [ ] Run `vue-tsc --noEmit` if the current baseline permits; report unrelated failures separately.
- [ ] Run the direct local Vite production build.
- [ ] Refresh the local preview and verify Request, Test, project-cycle, Internal Review, detail Information, and Comment publishing in the browser.
- [ ] Inspect the final diff/status and report only task-related files.
