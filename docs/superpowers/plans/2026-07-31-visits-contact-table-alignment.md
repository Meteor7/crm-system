# Visits Contact-Style Table Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Visits card grid and status rail with the same row-oriented table presentation used by Contacts.

**Architecture:** Keep all existing Visit data loading, permissions, transitions, filters, and modal flows. Change only the `VisitsPage.vue` presentation layer and protect the new structure with a focused page integration test.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils.

## Global Constraints

- Do not change Visit API contracts, workflow states, permissions, or Mock data.
- Remove the status summary rail completely.
- Render one loaded Visit per table row.
- Preserve every existing Visit action and its current visibility condition.
- Do not add dependencies or mobile-specific behavior.

---

### Task 1: Protect the row-oriented Visit presentation

**Files:**
- Modify: `src/pages/customer-operations.test.ts`

**Interfaces:**
- Consumes: `VisitsPage`, `createMockApi({ latency: 0 })`.
- Produces: A regression test for the Contacts-style Visit table.

- [x] **Step 1: Add a failing page test**

Add a test that mounts `VisitsPage` with Pinia and the real Mock adapter, waits for loading, and asserts:

```ts
expect(wrapper.find('.status-rail').exists()).toBe(false)
expect(wrapper.find('.visit-card').exists()).toBe(false)
expect(wrapper.get('table.crm-table.visits-table').exists()).toBe(true)
expect(wrapper.findAll('table.visits-table tbody tr')).toHaveLength(2)
expect(wrapper.get('[data-visit-id="V-001"]').text()).toContain('南京 Fab Demo 前现场确认')
expect(wrapper.get('[data-visit-id="V-001"]').text()).toContain('On-site')
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```powershell
npx.cmd vitest run src/pages/customer-operations.test.ts --exclude ".superpowers/**" -t "renders Visits as one row per record"
```

Expected: FAIL because the page still renders `.status-rail` and `.visit-card` without a Visit table.

### Task 2: Replace the card grid with the Contacts-style table

**Files:**
- Modify: `src/pages/VisitsPage.vue`

**Interfaces:**
- Consumes: Existing `rows`, `statusLabel`, `statusTone`, `canWrite`, `canReview`, `open`, and `completeAction`.
- Produces: `.crm-table.visits-table` with `[data-visit-id]` rows.

- [x] **Step 1: Remove the status rail markup**

Delete the `VISIT_STATUS_ORDER` summary section from the template. Keep `VISIT_STATUS_ORDER` for the status filter options.

- [x] **Step 2: Replace Visit cards with one table**

Render these columns in order:

```text
拜访主题 | 客户 | 日期 / 方式 | 负责人 | 拜访目标 | 拜访结果 | 下一步行动 | 状态 | 操作
```

Use one `<tr :data-visit-id="visit.id">` per Visit. Keep the existing conditional buttons inside the operation cell.

- [x] **Step 3: Align styling with Contacts**

Add a bordered, rounded `.visits-card`, an overflow `.table-scroll`, a minimum-width `.visits-table`, stacked primary/secondary text, and a wrapping `.visit-actions`. Remove `.status-rail`, `.visit-list`, `.visit-card`, and `.visit-content` styles.

- [x] **Step 4: Run the focused test and verify GREEN**

Run:

```powershell
npx.cmd vitest run src/pages/customer-operations.test.ts --exclude ".superpowers/**" -t "renders Visits as one row per record"
```

Expected: PASS.

### Task 3: Regression and visual verification

**Files:**
- Verify: `src/pages/customer-operations.test.ts`
- Verify: `src/pages/delivery-workflow.test.ts`
- Verify: `src/pages/VisitsPage.vue`

**Interfaces:**
- Consumes: Completed Visit page.
- Produces: Verified row presentation without workflow regressions.

- [x] **Step 1: Run affected Visit tests**

```powershell
npx.cmd vitest run src/pages/customer-operations.test.ts src/pages/delivery-workflow.test.ts --exclude ".superpowers/**"
```

- [x] **Step 2: Run typecheck and standalone Vite build**

```powershell
npm.cmd run typecheck
.\node_modules\.bin\vite.CMD build
```

Record unrelated baseline failures separately.

- [x] **Step 3: Verify the page in the browser**

Open `http://127.0.0.1:4173/visits` after rebuilding. Confirm the status rail is absent, every Visit is a table row, filters remain visible, role-scoped buttons remain available, and there are no page console errors.

- [x] **Step 4: Check whitespace**

```powershell
git diff --check -- src/pages/VisitsPage.vue src/pages/customer-operations.test.ts
```
