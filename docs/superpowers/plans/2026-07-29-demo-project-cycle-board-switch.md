# Demo Project Cycle Board Implementation Plan

**Goal:** Replace the project-cycle placeholder with the approved three-section project board, reuse the existing Demo workflow records and detail route, and add the same time-chain dashboard to the shared archive detail.

**Architecture:** Keep `listDemoWorkflows()` as the single data source. Add pure project-cycle grouping and timeline derivation in the frontend domain layer, render them through reusable Vue components, and keep `view=detail&focus=<id>` as the detail URL contract for lifecycle, project-cycle, and archive surfaces.

**Tech Stack:** Vue 3, TypeScript, Vue Router, Vitest, Vue Test Utils

## Constraints

- Reuse current Demo Request / Demo Test / completed records; do not add parallel seed data.
- Keep existing lifecycle board and archive behavior intact.
- Customer-expected projects with `daysToCustomerExpected <= 7` are visibly red.
- Each of the three sections has its own “档案详情” button for the selected project.
- Project-cycle detail uses the existing detail component and URL pattern.
- Do not modify the Frappe backend or add dependencies.
- Do not commit, merge, or push Git changes.

## Task 1: Protect the new behavior with failing tests

- Update `src/pages/DemoWorkflowPage.test.ts`.
- Add tests for the three populated project sections, multi-project scroll lists, project selection, red customer-risk treatment, detail routing, and time-chain content in the shared detail.
- Run the focused test and confirm it fails because the project surface is still a placeholder.

## Task 2: Add project-cycle domain mapping

- Add `src/domain/demo-project-cycle.ts` and its focused test.
- Derive request, test, and completed groups from the existing archive category and lifecycle stage.
- Derive timeline steps and customer-risk status from existing `DemoWorkflowDto` fields.

## Task 3: Build the project-cycle board

- Add reusable `DemoProjectTimeline.vue`.
- Add `DemoProjectCycleBoard.vue` with three stacked sections, scrollable multi-project lists, selection state, risk highlighting, timeline display, and per-section detail action.
- Reuse the current search, health, Sales owner, and Engineer owner filters.

## Task 4: Reuse the existing detail route and add the dashboard

- Replace the project placeholder in `DemoWorkflowPage.vue`.
- Allow project records, including completed records, to resolve through the existing `view=detail&focus=<id>` route.
- Render the existing `DemoArchiveDetail.vue` for project-cycle detail.
- Add the reusable project time-chain dashboard to `DemoArchiveDetail.vue`.

## Task 5: Verify

- Run focused project-cycle and page tests.
- Run the complete relevant Demo workflow test set.
- Run `pnpm.cmd typecheck` and `pnpm.cmd build`.
- Open the running page, inspect all three project sections and detail navigation, capture a screenshot, and compare it with the approved prototype.
- Audit every user requirement against the visible result before completion.
