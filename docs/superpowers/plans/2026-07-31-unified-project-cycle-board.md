# Unified Project Cycle Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three project-cycle sections with one continuous project table whose rows pair fixed project information with a full milestone timeline and place completed projects last.

**Architecture:** Keep filtering and route state in their existing components. `DemoProjectCycleBoard.vue` will derive one ordered list and render one clickable row per project; `DemoProjectTimeline.vue` will continue to own milestone rendering and expose a row-friendly context-hiding prop.

**Tech Stack:** Vue 3 Composition API, TypeScript, scoped CSS, Vitest, Vue Test Utils.

## Global Constraints

- Keep the existing Mock/Vue data boundary.
- Do not add dependencies or backend fields.
- Preserve all existing search, filter, URL query, and archive-detail behavior.
- Render project name, current-stage owner, DDL, and all six existing milestones on every row.
- Append recent completed projects to the bottom and do not render section headers.

---

### Task 1: Lock the continuous-row behavior with tests

**Files:**
- Modify: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: existing `[data-project-cycle-board]`, `[data-project-id]`, and `[data-project-timeline]` hooks.
- Produces: assertions for `[data-project-cycle-table]`, `[data-project-cycle-row]`, `[data-current-stage-owner]`, and row-level archive navigation.

- [ ] **Step 1: Replace section-oriented assertions with row-oriented assertions**

Assert that the project surface has one table, no `[data-project-cycle-section]` elements, 10 rows, one timeline per row, six milestone labels in an active row, and completed rows at the end:

```ts
const rows = wrapper.findAll('[data-project-cycle-row]')
expect(wrapper.findAll('[data-project-cycle-table]')).toHaveLength(1)
expect(wrapper.findAll('[data-project-cycle-section]')).toHaveLength(0)
expect(rows).toHaveLength(10)
expect(wrapper.findAll('[data-project-cycle-row] [data-project-timeline]')).toHaveLength(10)
expect(rows.slice(-2).every((row) => row.classes().includes('is-completed-project'))).toBe(true)
expect(wrapper.get('[data-project-id="DR-101"] [data-current-stage-owner]').text()).not.toBe('')
```

- [ ] **Step 2: Update color and navigation tests**

Keep row tone assertions for Request, Test, urgent, and completed records. Replace the selected-project flow with a direct row click:

```ts
await wrapper.get('[data-project-id="DR-104"]').trigger('click')
await flushPromises()
expect(router.currentRoute.value.query).toMatchObject({
  surface: 'project',
  view: 'detail',
  focus: 'DR-104',
})
```

- [ ] **Step 3: Run the focused test and verify it fails**

Run:

```powershell
pnpm.cmd test src/pages/DemoWorkflowPage.test.ts
```

Expected: the new continuous-table assertions fail because the current component still renders three sections and only three selected timelines.

### Task 2: Render the unified project rows

**Files:**
- Modify: `src/features/demo-workflow/DemoProjectCycleBoard.vue`
- Modify: `src/features/demo-workflow/DemoProjectTimeline.vue`

**Interfaces:**
- Consumes: `recentCompletedProjects(items)`, `demoProjectCycleGroup(item)`, `isCustomerExpectedRisk(item)`, and `buildDemoProjectTimeline(item)`.
- Produces: `orderedItems`, `currentStageOwner(item)`, row-level tone classes, and a `hide-context` timeline prop.

- [ ] **Step 1: Replace grouped selection state with one ordered list**

Derive filtered active and completed records without reactive selected IDs:

```ts
const orderedItems = computed(() => [
  ...filtered.value.filter((item) => item.archiveCategory !== 'Completed'),
  ...filtered.value.filter((item) => item.archiveCategory === 'Completed'),
])

function currentStageOwner(item: DemoWorkflowDto): string {
  return buildDemoProjectTimeline(item).find((step) => step.state === 'Current')?.actor
    || item.engineerOwner
    || '待确认'
}
```

- [ ] **Step 2: Render one table and one row per project**

Use one `[data-project-cycle-table]` container with a header and `v-for="item in orderedItems"`. Each `[data-project-cycle-row]` must contain the three left-side fields and:

```vue
<DemoProjectTimeline
  :item="item"
  hide-context
  scope="full"
  :tone="item.archiveCategory === 'Completed'
    ? 'complete'
    : isCustomerExpectedRisk(item)
      ? 'critical'
      : demoProjectCycleGroup(item)"
/>
```

Make the row a `button` or provide equivalent keyboard behavior, and emit `open` with that row's item.

- [ ] **Step 3: Add the row-friendly timeline prop**

Extend timeline props with `hideContext?: boolean`, hide `.timeline-context` with `v-if="!hideContext"`, and keep the six existing milestone columns and tone classes unchanged.

- [ ] **Step 4: Replace the three-section CSS with a stable table grid**

Use one grid template for both header and rows:

```css
.project-table-header,
.project-cycle-row {
  display: grid;
  grid-template-columns: minmax(220px, 1.35fr) minmax(130px, .7fr) 110px minmax(760px, 3.6fr);
}
```

Add a top separator to the first completed row, retain urgent red and completed gray visual semantics, and allow horizontal overflow on the table shell.

- [ ] **Step 5: Run the focused tests**

Run:

```powershell
pnpm.cmd test src/pages/DemoWorkflowPage.test.ts src/domain/demo-project-cycle.test.ts
```

Expected: all focused tests pass.

### Task 3: Verify packaging and browser behavior

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: the completed Vue implementation.
- Produces: test, build, and browser evidence.

- [ ] **Step 1: Run the Vite bundle**

Run:

```powershell
& '.\node_modules\.bin\vite.CMD' build
```

Expected: Vite exits with code 0.

- [ ] **Step 2: Inspect the project surface in the browser**

Verify the project surface shows one continuous table, active rows first, completed rows last, one six-node timeline per row, working filters, row click navigation, and no console errors.

- [ ] **Step 3: Review the final diff**

Run:

```powershell
git diff -- src/features/demo-workflow/DemoProjectCycleBoard.vue src/features/demo-workflow/DemoProjectTimeline.vue src/pages/DemoWorkflowPage.test.ts
```

Confirm that no unrelated page, Mock data, adapter, or business logic changed.
