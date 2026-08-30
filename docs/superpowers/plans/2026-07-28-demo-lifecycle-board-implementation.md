# Demo Lifecycle Board Implementation Plan

> **Agentic workers:** Codex main agent only. Subagents are not requested for this task.
>
> **Required sub-skills:** `superpowers:test-driven-development`, `superpowers:verification-before-completion`, `build-web-apps:frontend-testing-debugging`.

**Goal:** Replace the default Demo Archive surface with the approved five-stage lifecycle board, keep the existing archive detail behind card clicks, add traceable health derivation, and remove system Q&A and On Hold without changing the original Word question fields.

**Architecture:** Keep `listDemoWorkflows()` as the permission-aware archive aggregation boundary. Extend its DTO with a small tracking view model and derive stage/health in pure domain functions. Store tracking on the owning Demo Request and migrate existing snapshots to version 3. The board reads the same aggregated records as the existing detail view, so no third business-data copy is introduced.

**Tech stack:** Vue 3 composition API, TypeScript, Pinia, Vue Router, Vitest, Vue Test Utils, existing Mock Demo Repository.

## Visual reference extraction

- Reference: `docs/superpowers/specs/2026-07-28-demo-lifecycle-board-concept.png`.
- One full-width workspace with five equal lifecycle columns under a continuous orange chevron rail.
- Warm white canvas, dark existing application sidebar, thin neutral column dividers, white cards, restrained borders and shadows.
- Cards use a 3 px health rail, customer name, two-line Demo ID/title, plain-text Owner, a divider, and one health reason row.
- Test Run DDL and customer expected dates do not render on cards; they remain inputs to health derivation and remain available in detail.
- No person avatars, Q&A controls, On Hold controls, drag handles, KPI cards, or decorative imagery.
- Desktop keeps five columns visible when space allows; narrower viewports use horizontal board scrolling rather than compressing cards below readable width.

## Task 1: Lock the lifecycle and health contracts with domain tests

**Files:**

- Create: `src/domain/demo-lifecycle.test.ts`
- Create: `src/domain/demo-lifecycle.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`

**Steps:**

1. Add failing table-driven tests for all five request/evaluation stage mappings, exclusion of Draft/Cancelled/Accepted/Rejected, the exact 7-day red boundary, the exact 5-day orange boundary, red-over-orange priority, Test Run DDL overdue, and Asia/Shanghai natural-day calculation.
2. Run `pnpm.cmd test src/domain/demo-lifecycle.test.ts` and confirm failures are caused by the missing module/API.
3. Add the minimal `DemoLifecycleStage`, `DemoTrackingDto`, `DemoHealth`, `mapDemoLifecycleStage()`, and `deriveDemoHealth()` implementation.
4. Run the same test file and confirm it passes.

## Task 2: Migrate Demo data and remove retired system contracts

**Files:**

- Modify: `src/demo/demo-repository.test.ts`
- Modify: `src/demo/demo-repository.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-data.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/domain/demo-request-form.ts`
- Modify: `src/domain/demo-request-form.test.ts`
- Modify: `src/domain/demo-report.ts`
- Modify: `src/domain/demo-report.test.ts`

**Steps:**

1. Replace repository migration expectations with a failing version-3 test that removes structured `questions`, converts legacy On Hold to Scheduled, carries `holdReason` into `tracking.nextAction`, removes hold fields, creates traceable tracking defaults, and preserves Request form questions, Evaluation, Test Runs, Artifacts, Blob, and Word data.
2. Run `pnpm.cmd test src/demo/demo-repository.test.ts src/domain/demo-report.test.ts src/domain/demo-request-form.test.ts` and confirm the new expectations fail.
3. Remove `DemoQuestionDto`, `DemoRequestDto.questions`, `answerDemoQuestion`, `questionAssignment`, On Hold status, `holdReason`, and `resumeDate` from active contracts.
4. Upgrade snapshots to version 3 and seed requests with deterministic tracking data. Update progress timestamps in the same repository transactions as request transitions, Evaluation transitions, DDL writes, and Test Run writes.
5. Keep `formData.internalQuestions` and `formData.customerQuestions`, DOCX mapping, and DOCX output unchanged.
6. Remove system-Q&A report plumbing while retaining report date fields and report selection behavior.
7. Re-run the targeted tests until green.

## Task 3: Remove Q&A and On Hold UI paths

**Files:**

- Modify: `src/features/demo-requests/DemoRequestWorkspace.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Delete: `src/features/demo-requests/QuestionAnswerModal.vue`
- Modify: `src/features/evaluations/EvaluationCard.vue`
- Modify: `src/features/evaluations/EvaluationCard.test.ts`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: `src/domain/evaluations.ts`
- Modify: `src/domain/evaluations.test.ts`
- Modify: `src/domain/dashboard.ts`
- Modify: `src/features/accounts/AccountDrawer.vue`
- Modify: `src/features/accounts/AccountProfile.vue`
- Modify: `src/features/accounts/customer-report-model.ts`
- Modify relevant Q&A/On Hold assertions in `src/api/mock-adapter.test.ts`, `src/pages/delivery-workflow.test.ts`, `src/pages/permission-revocation.test.ts`, and `src/pages/first-demo-completion.test.ts`

**Steps:**

1. Change component and page tests first so they expect no Answer action, Q&A section, On Hold button, modal, status option, dashboard hold alert, or account-profile hold styling.
2. Run the targeted test files and confirm those expectations fail against the current UI.
3. Remove only the retired structured workflow and On Hold paths. Preserve the Demo Request form’s original Open Questions inputs and Word behavior.
4. Re-run the targeted tests until green.

## Task 4: Implement the image-faithful board and detail routing

**Files:**

- Create: `src/features/demo-workflow/DemoPipelineCard.vue`
- Create: `src/features/demo-workflow/DemoStageColumn.vue`
- Create: `src/features/demo-workflow/DemoPipelineBoard.vue`
- Create: `src/pages/DemoWorkflowPage.test.ts`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/types/workspaces.ts`

**Steps:**

1. Add failing page tests for the five ordered stages, stage counts, active-only records, search, health filter, no card dates, no avatars, no Q&A/On Hold, and `view=detail&focus=<id>` navigation on card click.
2. Run `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts` and confirm the failures describe the missing board behavior.
3. Extend `listDemoWorkflows()` with `stage`, `health`, and tracking fields derived from the existing Request/Evaluation pair.
4. Implement the three focused board components with the approved chevron rail, readable fixed-minimum columns, compact cards, empty stages, search, and health filter.
5. Make `/demo-workflow` default to board mode. Reuse the existing detail sections for `view=detail`; remove only its structured Customer Q&A section and provide a clear “返回看板” action.
6. Keep search/filter in route query and reject an invalid focus by returning to the board with an error notice.
7. Re-run the page test until green.

## Task 5: Verify the complete visible flow

**Files:** No planned production edits unless verification finds an in-scope defect.

**Steps:**

1. Run focused tests:

   ```powershell
   pnpm.cmd test src/domain/demo-lifecycle.test.ts src/demo/demo-repository.test.ts src/domain/evaluations.test.ts src/domain/demo-report.test.ts src/features/evaluations/EvaluationCard.test.ts src/pages/DemoWorkflowPage.test.ts src/pages/delivery-workflow.test.ts
   ```

2. Run `pnpm.cmd run typecheck`.
3. Run `pnpm.cmd run build`.
4. Run `pnpm.cmd test` and report any remaining unrelated baseline failures separately from the focused result.
5. Serve the live Vite source on port 4173 with hot updates and verify:
   - `/demo-workflow` loads as the five-stage board.
   - No framework overlay or relevant console error appears.
   - Red, orange, and green cards are readable.
   - Cards contain no Test Run DDL, customer expected date, or avatar.
   - Search and health filter work.
   - Clicking a card opens the existing detail and returning restores board context.
   - A narrower viewport scrolls horizontally without card text clipping.
6. Compare the rendered page with the high-fidelity reference and correct only material, in-scope mismatches.

