# Boss Dashboard Subscription Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a Management Viewer to add multiple subscription rows, each containing exactly three unique dashboard charts.

**Architecture:** Upgrade browser persistence from one flat selection to a validated array of three-chart rows while migrating the existing `v1` value. Keep the chart catalog unified in `DashboardPage.vue`; the page edits a draft array of rows, renders each saved row as its own three-column grid, and filters every saved chart from expanded analysis.

**Tech Stack:** Vue 3 Composition API, TypeScript, Pinia, Vitest, Vue Test Utils, browser localStorage.

## Global Constraints

- Only `Management Viewer` receives this behavior.
- Every saved row contains exactly three charts and chart IDs are unique across all rows.
- The first row cannot be deleted; later rows can be deleted.
- Rows have no custom names; management labels them only by position.
- No new dependencies, backend endpoints, permission changes, drag sorting, or cross-device synchronization.
- Do not commit, push, stage, or upload any change to Git.

---

### Task 1: Versioned subscription-group state and migration

**Files:**
- Modify: `src/features/dashboard/dashboard-subscriptions.ts`
- Test: `src/features/dashboard/dashboard-subscriptions.test.ts`

**Interfaces:**
- Consumes: `DashboardChartId`, `DASHBOARD_CHART_IDS`, `DashboardSubscriptionStorage`.
- Produces: `DashboardSubscriptionGroups`, `DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS`, `normalizeBossDashboardSubscriptionGroups`, `readBossDashboardSubscriptionGroups`, and `writeBossDashboardSubscriptionGroups`.

- [ ] **Step 1: Write failing state tests**

Add tests asserting that:

```ts
expect(normalizeBossDashboardSubscriptionGroups([
  ['evaluation-status', 'booking-month', 'top-accounts'],
  ['region', 'tier', 'risk'],
])).toEqual([
  ['evaluation-status', 'booking-month', 'top-accounts'],
  ['region', 'tier', 'risk'],
])

expect(normalizeBossDashboardSubscriptionGroups([
  ['evaluation-status', 'booking-month', 'top-accounts'],
  ['region', 'tier', 'evaluation-status'],
])).toEqual(DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS)
```

Also assert `v2` user-scoped keys, `v1` migration, corrupt-data fallback, one-to-six rows, exactly three IDs per row, global uniqueness, and storage-write failure.

- [ ] **Step 2: Run the focused state test and verify RED**

Run:

```powershell
pnpm.cmd test src/features/dashboard/dashboard-subscriptions.test.ts
```

Expected: FAIL because the group APIs and `v2` storage behavior do not exist.

- [ ] **Step 3: Implement the minimal group model**

Implement:

```ts
export type DashboardSubscriptionGroups = DashboardChartId[][]

export const DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS: DashboardSubscriptionGroups = [
  [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS],
]
```

Validate one to six rows, three known IDs per row, and global uniqueness. Read `v2` first; only when it is absent, read the old `v1` key and wrap a valid flat list in one row. Write only `v2`.

- [ ] **Step 4: Run the focused state test and verify GREEN**

Run:

```powershell
pnpm.cmd test src/features/dashboard/dashboard-subscriptions.test.ts
```

Expected: all subscription-state tests pass.

---

### Task 2: Multi-row management and dashboard rendering

**Files:**
- Modify: `src/pages/DashboardPage.vue`
- Test: `src/pages/DashboardPage.test.ts`

**Interfaces:**
- Consumes: the group state APIs from Task 1 and the existing `visualDashboardCatalog`.
- Produces: saved subscription rows, draft rows, an active row index, add/delete/select interactions, multi-row rendering, and global expanded-area filtering.

- [ ] **Step 1: Write failing page interaction tests**

Add a Management Viewer test that performs:

```ts
await wrapper.get('[data-testid="manage-dashboard-subscriptions"]').trigger('click')
await wrapper.get('[data-testid="add-subscription-row"]').trigger('click')
expect(wrapper.findAll('[data-subscription-row-tab]')).toHaveLength(2)

await wrapper.get('[data-subscription-id="region"]').trigger('click')
await wrapper.get('[data-subscription-id="tier"]').trigger('click')
await wrapper.get('[data-subscription-id="risk"]').trigger('click')
await wrapper.get('form').trigger('submit')
```

Assert two rendered subscription rows, six cards, three cards per row, no duplicates in expanded analysis, and restoration after remount.

Add separate tests for:

- first row cannot be deleted;
- a later row can be deleted and its charts return to expanded analysis after save;
- the save button is disabled while any row has fewer than three charts;
- charts selected in another row are disabled and identify their row;
- cancel discards draft additions and deletions;
- the add button disables when fewer than three unused charts remain;
- non-management users still have no subscription entry.

- [ ] **Step 2: Run the focused page test and verify RED**

Run:

```powershell
pnpm.cmd test src/pages/DashboardPage.test.ts
```

Expected: FAIL because the page still models one flat three-chart selection.

- [ ] **Step 3: Implement minimal multi-row page state**

Replace flat saved and draft selections with:

```ts
const subscriptionGroups = ref<DashboardSubscriptionGroups>(...)
const draftSubscriptionGroups = ref<DashboardSubscriptionGroups>([])
const activeSubscriptionGroupIndex = ref(0)
```

Add pure page helpers for flattened selected IDs, active-row selection, add row, delete active row, occupancy lookup, and save validity. Clone nested arrays when opening, saving, or cancelling so draft mutations cannot leak into saved state.

- [ ] **Step 4: Implement multi-row template and styles**

Render each saved row as a separate `.decision-grid` with `data-subscription-dashboard-row`. In the modal, add positional row controls, completion counts, add-row control, and deletion for rows after the first. Reuse the existing unified catalog and responsive grid rules.

- [ ] **Step 5: Run page and state tests and verify GREEN**

Run:

```powershell
pnpm.cmd test src/pages/DashboardPage.test.ts src/features/dashboard/dashboard-subscriptions.test.ts
```

Expected: both files pass without warnings or runtime errors.

---

### Task 3: Regression, build, and rendered browser verification

**Files:**
- Verify: `src/domain/dashboard.test.ts`
- Verify: `src/design-system/ModalShell.test.ts`
- Verify: `src/pages/DashboardPage.test.ts`
- Verify: `src/features/dashboard/dashboard-subscriptions.test.ts`

**Interfaces:**
- Consumes: the completed feature from Tasks 1 and 2.
- Produces: fresh automated and rendered evidence.

- [ ] **Step 1: Run focused regression tests**

```powershell
pnpm.cmd test src/domain/dashboard.test.ts src/design-system/ModalShell.test.ts src/pages/DashboardPage.test.ts src/features/dashboard/dashboard-subscriptions.test.ts
```

Expected: all focused files pass.

- [ ] **Step 2: Run type checking and production build**

```powershell
pnpm.cmd build
```

Expected: `vue-tsc --noEmit` and Vite production build both exit successfully.

- [ ] **Step 3: Verify in the in-app browser**

Test this flow:

```text
/dashboard -> switch to Management Viewer -> open Manage Subscriptions ->
add second row -> select three unused charts -> save -> see two rows ->
expand all -> verify no duplicates -> reload -> verify persistence ->
delete second row -> save -> verify one row
```

Check page identity, meaningful DOM, no framework overlay, console errors or warnings, desktop layout, and one narrow viewport.

- [ ] **Step 4: Inspect the exact diff without changing Git state**

```powershell
git diff --check -- src/pages/DashboardPage.vue src/pages/DashboardPage.test.ts src/features/dashboard/dashboard-subscriptions.ts src/features/dashboard/dashboard-subscriptions.test.ts
git status --short
```

Expected: no whitespace errors; feature files remain only as local working-tree changes.
