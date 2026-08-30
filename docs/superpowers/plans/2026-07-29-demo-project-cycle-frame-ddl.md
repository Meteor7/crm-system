# Demo Project Cycle Frame and DDL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one visual outer frame around the existing Demo Request and Demo Test sections, and show each project's customer-expected DDL on its project-cycle card.

**Architecture:** Keep the three existing `data-project-cycle-section` sections and their selection/risk behavior unchanged. Add a wrapper only around the first two sections, render a small DDL row from `DemoWorkflowDto.customerExpectedDate` on every project card, and apply the approved green/orange/gray status tones with red overriding them for urgent work.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils, scoped CSS.

## Global Constraints

- Keep Demo Request and Demo Test as independent sections; the new wrapper is visual grouping only.
- Keep the completed section outside the active wrapper.
- DDL means customer expected date and renders as `待确认` when no valid value exists.
- Use green for normal Demo Request, theme orange for normal Demo Test, gray for completed projects, and red with an explicit `加急` label for urgent projects.
- Preserve the existing `customerExpectedDate <= 7 days` urgent rule and completed-project exemption.
- Modify only the Vue/Mock implementation; do not alter Frappe adapters, DocTypes, routing, or archive-detail behavior.
- Do not create a git commit because the worktree already contains extensive user-owned changes and the user did not request a commit.

---

### Task 1: Lock the wrapper and DDL behavior with a page test

**Files:**
- Modify: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: `data-project-cycle-board`, `data-project-cycle-section`, and project-card `data-project-id` selectors.
- Produces: regression assertions for `[data-active-demo-frame]` and `[data-customer-expected-ddl]`.

- [ ] **Step 1: Write the failing test**

```ts
const activeFrame = wrapper.get('[data-active-demo-frame]')
expect(activeFrame.findAll('[data-project-cycle-section]')).toHaveLength(2)
expect(activeFrame.find('[data-project-cycle-section="request"]').exists()).toBe(true)
expect(activeFrame.find('[data-project-cycle-section="test"]').exists()).toBe(true)
expect(activeFrame.find('[data-project-cycle-section="completed"]').exists()).toBe(false)
expect(wrapper.get('[data-project-cycle-section="completed"]').element.parentElement).not.toBe(activeFrame.element)

expect(wrapper.get('[data-project-id="DR-101"] [data-customer-expected-ddl]').text())
  .toMatch(/^DDL：\d{4}-\d{2}-\d{2}$/)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts`

Expected: FAIL because the outer-frame and DDL selectors do not exist.

- [ ] **Step 3: Keep the test scoped**

Confirm the test does not require changes to the lifecycle board, archive-detail route, or domain risk helpers.

### Task 2: Add the visual frame and customer-expected DDL row

**Files:**
- Modify: `src/features/demo-workflow/DemoProjectCycleBoard.vue`
- Modify: `src/features/demo-workflow/DemoProjectTimeline.vue`
- Test: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: `DemoWorkflowDto.customerExpectedDate?: string`.
- Produces: `formatCustomerExpectedDate(value?: string): string`, `[data-active-demo-frame]`, and `[data-customer-expected-ddl]`.

- [ ] **Step 1: Add the minimum date formatter**

```ts
function formatCustomerExpectedDate(value?: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(value ?? '')
  return match?.[1] ?? '待确认'
}
```

- [ ] **Step 2: Wrap only the active sections**

Render the existing Request and Test sections inside:

```vue
<div class="active-demo-frame" data-active-demo-frame>
  <!-- unchanged request and test sections -->
</div>
```

Render the existing completed section after the wrapper, outside it.

- [ ] **Step 3: Render DDL on every project card**

```vue
<span class="project-ddl" data-customer-expected-ddl>
  DDL：{{ formatCustomerExpectedDate(item.customerExpectedDate) }}
</span>
```

- [ ] **Step 4: Style the wrapper and DDL without changing section tones**

Add a neutral outer border, light background, and spacing around the two existing active sections. Apply green Request, orange Test, gray completed, and red urgent tones to sections, cards, and timelines.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts`

Expected: PASS.

### Task 3: Verify the visible workflow

**Files:**
- Verify: `src/features/demo-workflow/DemoProjectCycleBoard.vue`
- Verify: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: the completed Vue implementation.
- Produces: test, build, and browser evidence.

- [ ] **Step 1: Run project-cycle domain and page tests**

Run: `pnpm.cmd test src/domain/demo-project-cycle.test.ts src/pages/DemoWorkflowPage.test.ts`

Expected: PASS.

- [ ] **Step 2: Build the application**

Run: `pnpm.cmd build`

Expected: PASS with no TypeScript or Vite build error.

- [ ] **Step 3: Inspect the rendered project-cycle board**

Open the local Demo workflow project-cycle surface and verify:

- Request and Test retain their own headers, lists, timelines, and detail buttons.
- One neutral outer frame surrounds both active sections.
- Completed sits outside that frame.
- Every visible card shows a customer-expected DDL.
- Existing urgent red state still wins over normal tone.

- [ ] **Step 4: Review the focused diff**

Run: `git diff -- src/features/demo-workflow/DemoProjectCycleBoard.vue src/pages/DemoWorkflowPage.test.ts docs/superpowers/plans/2026-07-29-demo-project-cycle-frame-ddl.md`

Expected: only the requested wrapper, DDL, regression test, and plan are present.
