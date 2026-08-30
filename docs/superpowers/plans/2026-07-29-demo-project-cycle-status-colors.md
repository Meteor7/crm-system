# Demo Project Cycle Status Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the last 100 days of completed Demo records newest-first and apply orange, red, and green status colors consistently across the project-cycle board.

**Architecture:** Keep completion-date selection and time-window logic in `src/domain/demo-project-cycle.ts`. Let `DemoProjectCycleBoard.vue` consume the sorted domain result and derive the selected section tone, while `DemoProjectTimeline.vue` renders the matching timeline tone.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils

## Global Constraints

- Active normal projects use the CRM orange style.
- Active projects with customer expectation at or below 7 days use the red style.
- Completed projects use green and never use red risk styling.
- Completed records are limited to the last 100 days inclusive and sorted newest-first.
- Reuse existing Demo workflow data and detail routes.
- Do not modify Frappe or add dependencies.

---

### Task 1: Completion window and ordering

**Files:**
- Modify: `src/domain/demo-project-cycle.test.ts`
- Modify: `src/domain/demo-project-cycle.ts`

**Interfaces:**
- Produces: `recentCompletedProjects(items: DemoWorkflowDto[], today?: string): DemoWorkflowDto[]`

- [ ] Add a failing domain test with completed dates `2026-07-20`, `2026-07-28`, and `2026-04-19`, using `2026-07-29` as today. Expect only the first two IDs in `2026-07-28`, `2026-07-20` order.
- [ ] Run `.\node_modules\.bin\vitest.cmd run src\domain\demo-project-cycle.test.ts --exclude ".superpowers/**"` and verify the ordering assertion fails.
- [ ] Implement one completion-date resolver and `recentCompletedProjects`, filtering ages from 0 through 100 and sorting descending by the resolved date.
- [ ] Run the focused domain test and verify it passes.

### Task 2: Board copy and status tones

**Files:**
- Modify: `src/pages/DemoWorkflowPage.test.ts`
- Modify: `src/features/demo-workflow/DemoProjectCycleBoard.vue`
- Modify: `src/features/demo-workflow/DemoProjectTimeline.vue`

**Interfaces:**
- Consumes: `recentCompletedProjects`.
- Produces: section classes `is-active`, `is-critical`, and `is-completed`; project classes `is-normal-project`, `is-customer-risk`, and `is-completed-project`; timeline tones `default`, `critical`, and `complete`.

- [ ] Add failing page assertions for “过去100天已完成 Demo”, orange normal cards, red urgent cards, and a red Test section after selecting `DR-107`.
- [ ] Run `.\node_modules\.bin\vitest.cmd run src\pages\DemoWorkflowPage.test.ts --exclude ".superpowers/**"` and verify the new class/copy assertions fail.
- [ ] Change the completed copy and use `recentCompletedProjects` for the completed list and metric.
- [ ] Apply orange styles to active sections and normal active cards; apply red styles to urgent cards and the selected urgent section; preserve green completed styles.
- [ ] Pass `critical` to `DemoProjectTimeline` for the selected urgent project and add the red timeline rules.
- [ ] Run the focused page test and verify it passes.

### Task 3: Verification

**Files:**
- Test: `src/pages/DemoWorkflowPage.test.ts`
- Test: `src/domain/demo-project-cycle.test.ts`
- Test: existing Demo workflow regression files

- [ ] Run the five related Demo workflow test files and verify zero failures.
- [ ] Run `pnpm.cmd build` and verify type checking and Vite build succeed.
- [ ] Inspect the rendered project board: normal Request/Test orange, `DR-107` red with red timeline, completed green, and completed records ordered newest-first.
