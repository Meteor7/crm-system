# Boss Dashboard Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Boss dashboard's three fixed visualization cards with three browser-persisted subscription slots while keeping every unselected visualization in the existing expanded analysis area.

**Architecture:** Add a small pure module for subscription IDs, defaults, validation, and local-storage access. Refactor `DashboardPage.vue` to build one visualization catalog, derive subscribed and unselected groups from it, and manage exactly three selections in a modal without changing dashboard API contracts.

**Tech Stack:** Vue 3 Composition API, TypeScript, Pinia, Vitest, Vue Test Utils, existing `ModalShell`, `SectionCard`, `CrmChart`, and browser `localStorage`.

## Global Constraints

- Only `Management Viewer` receives the subscription UI.
- Keep KPI, data-source note, team schedule, related schedule, reminder center, API contracts, and dashboard aggregation unchanged.
- Maintain exactly three subscriptions; defaults are `evaluation-status`, `booking-month`, and `top-accounts`.
- Persist only in the current browser under a versioned, user-scoped key.
- Never duplicate subscribed charts in the expanded list.
- Add no dependencies.
- Preserve all unrelated dirty-worktree changes and do not commit implementation files that already contain user modifications.

---

### Task 1: Browser subscription state

**Files:**
- Create: `src/features/dashboard/dashboard-subscriptions.ts`
- Create: `src/features/dashboard/dashboard-subscriptions.test.ts`

**Interfaces:**
- Produces: `DashboardChartId`, `DASHBOARD_CHART_IDS`, `DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS`, `bossDashboardSubscriptionKey(userId)`, `normalizeBossDashboardSubscriptions(value)`, `readBossDashboardSubscriptions(storage, userId)`, and `writeBossDashboardSubscriptions(storage, userId, ids)`.
- Consumes: A minimal `DashboardSubscriptionStorage` interface with `getItem` and `setItem`.

- [ ] **Step 1: Write the failing state tests**

```ts
it('accepts exactly three unique known chart IDs', () => {
  expect(normalizeBossDashboardSubscriptions(['region', 'risk', 'contracts']))
    .toEqual(['region', 'risk', 'contracts'])
})

it.each([
  null,
  ['region', 'region', 'contracts'],
  ['region', 'risk'],
  ['region', 'risk', 'removed-chart'],
])('falls back to defaults for %j', (value) => {
  expect(normalizeBossDashboardSubscriptions(value))
    .toEqual(DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS)
})

it('returns defaults for corrupt storage and persists valid selections', () => {
  const storage = createMemoryStorage('{broken')
  expect(readBossDashboardSubscriptions(storage, 'boss@example.com'))
    .toEqual(DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS)
  expect(writeBossDashboardSubscriptions(storage, 'boss@example.com', ['region', 'risk', 'contracts'])).toBe(true)
  expect(readBossDashboardSubscriptions(storage, 'boss@example.com'))
    .toEqual(['region', 'risk', 'contracts'])
})
```

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run:

```powershell
pnpm.cmd test src/features/dashboard/dashboard-subscriptions.test.ts
```

Expected: FAIL because `dashboard-subscriptions.ts` does not exist.

- [ ] **Step 3: Implement the pure state module**

```ts
export const DASHBOARD_CHART_IDS = [
  'evaluation-status', 'booking-month', 'top-accounts',
  'region', 'tier', 'risk',
  'requirements', 'budget', 'actions', 'action-timeliness',
  'demo', 'demo-priority', 'evaluation-runs',
  'contracts', 'contract-type', 'contract-risk',
  'visits', 'visit-owner',
] as const

export type DashboardChartId = typeof DASHBOARD_CHART_IDS[number]

export const DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS: DashboardChartId[] = [
  'evaluation-status',
  'booking-month',
  'top-accounts',
]

export interface DashboardSubscriptionStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export function bossDashboardSubscriptionKey(userId: string) {
  return `semiconductor-crm:boss-dashboard-subscriptions:v1:${encodeURIComponent(userId)}`
}

export function normalizeBossDashboardSubscriptions(value: unknown): DashboardChartId[] {
  if (!Array.isArray(value) || value.length !== 3) return [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS]
  const known = new Set<string>(DASHBOARD_CHART_IDS)
  const ids = value.filter((item): item is DashboardChartId => typeof item === 'string' && known.has(item))
  if (ids.length !== 3 || new Set(ids).size !== 3) return [...DEFAULT_BOSS_DASHBOARD_SUBSCRIPTIONS]
  return ids
}
```

`readBossDashboardSubscriptions` catches `getItem` and JSON errors and returns defaults. `writeBossDashboardSubscriptions` validates before writing, catches storage errors, and returns `false` on failure.

- [ ] **Step 4: Run the focused state tests**

Run:

```powershell
pnpm.cmd test src/features/dashboard/dashboard-subscriptions.test.ts
```

Expected: PASS.

### Task 2: Three subscription slots and management modal

**Files:**
- Modify: `src/pages/DashboardPage.vue:1-316`
- Modify: `src/pages/DashboardPage.test.ts:1-89`

**Interfaces:**
- Consumes: All exports from `src/features/dashboard/dashboard-subscriptions.ts`.
- Produces: `visualDashboardCatalog`, `subscribedDashboards`, `unsubscribedDashboardGroups`, `openSubscriptionManager`, `toggleDraftSubscription`, and `saveSubscriptions` inside `DashboardPage.vue`.

- [ ] **Step 1: Add failing page tests for the approved workflow**

Add stable storage cleanup to `beforeEach`:

```ts
localStorage.clear()
```

Assert the default state and full catalog:

```ts
expect(wrapper.get('[data-dashboard-subscriptions]').text()).toContain('我的订阅看板')
expect(wrapper.findAll('[data-subscribed-dashboard]')).toHaveLength(3)
expect(wrapper.find('[data-testid="manage-dashboard-subscriptions"]').exists()).toBe(true)
```

Add a workflow test:

```ts
await wrapper.get('[data-testid="manage-dashboard-subscriptions"]').trigger('click')
expect(wrapper.get('[role="dialog"]').text()).toContain('管理订阅看板')
expect(wrapper.findAll('[data-subscription-option][aria-pressed="true"]')).toHaveLength(3)

await wrapper.get('[data-subscription-id="evaluation-status"]').trigger('click')
await wrapper.get('[data-subscription-id="region"]').trigger('click')
await wrapper.get('[data-modal-submit]').trigger('submit')
await flushPromises()

const subscribed = wrapper.findAll('[data-subscribed-dashboard]')
expect(subscribed).toHaveLength(3)
expect(subscribed.some((card) => card.text().includes('区域分布'))).toBe(true)
expect(subscribed.some((card) => card.text().includes('Demo / Wafer Test 状态'))).toBe(false)

await wrapper.get('[data-testid="toggle-more-analysis"]').trigger('click')
expect(wrapper.findAll('[data-expanded-dashboard]').filter((card) => card.text().includes('Demo / Wafer Test 状态'))).toHaveLength(1)
expect(wrapper.findAll('[data-expanded-dashboard]').filter((card) => card.text().includes('区域分布'))).toHaveLength(0)
```

Add remount persistence, invalid storage fallback, exactly-three save guard, and non-management-entry absence assertions.

- [ ] **Step 2: Run the Dashboard test and verify the new assertions fail**

Run:

```powershell
pnpm.cmd test src/pages/DashboardPage.test.ts
```

Expected: FAIL because subscription controls and data attributes do not exist.

- [ ] **Step 3: Build one visualization catalog**

Define:

```ts
type DashboardChartGroup = 'core' | 'customer' | 'process'

interface DashboardChartItem {
  id: DashboardChartId
  group: DashboardChartGroup
  title: string
  eyebrow: string
  description: string
  option: Record<string, unknown>
  hasData: boolean
  emptyTitle: string
  label: string
}
```

Build `visualDashboardCatalog` from the existing three fixed options, customer options, and `processCharts`. Preserve every current title, description, chart option, label, and empty state.

Load saved subscriptions after bootstrap identifies the Boss user:

```ts
subscriptions.value = readBossDashboardSubscriptions(window.localStorage, app.bootstrap?.user.id || 'management-viewer')
```

Derive the three cards in subscription order and group all remaining cards by their original categories.

- [ ] **Step 4: Replace fixed rendering and add the modal**

Render:

```vue
<section class="subscription-section" data-dashboard-subscriptions>
  <header class="subscription-heading">
    <div><span>MY SUBSCRIPTIONS</span><h2>我的订阅看板</h2></div>
    <button data-testid="manage-dashboard-subscriptions" type="button" @click="openSubscriptionManager">
      管理订阅 · 3/3
    </button>
  </header>
  <div class="decision-grid">
    <SectionCard v-for="chart in subscribedDashboards" :key="chart.id" data-subscribed-dashboard>
      <!-- existing CrmChart and DataState behavior -->
    </SectionCard>
  </div>
</section>
```

Use `ModalShell` with grouped option buttons. Buttons expose `data-subscription-option`, `data-subscription-id`, and `aria-pressed`. Disable unselected options when three are already selected. Pass `:busy="draftSubscriptions.length !== 3"` so the existing submit button is disabled until exactly three are selected.

On save, update in-memory subscriptions first, then call `writeBossDashboardSubscriptions`. If it returns `false`, show `当前浏览器无法保存订阅；本次页面选择仍然有效。` with `role="status"`.

- [ ] **Step 5: Render only unselected charts in “展开全部”**

Replace the hard-coded customer and process grids with grouped rendering from `unsubscribedDashboardGroups`. Hide category headings with no remaining cards. Add `data-expanded-dashboard` to each lower card so tests can prove there are no duplicates.

- [ ] **Step 6: Add scoped responsive styles**

Style only:

- `.subscription-section`
- `.subscription-heading`
- `.subscription-manager-summary`
- `.subscription-group`
- `.subscription-options`
- `.subscription-option`
- `.subscription-storage-warning`

Keep the current three-column `.decision-grid`; collapse the modal options to two columns below 760px and one column below 560px.

- [ ] **Step 7: Run the focused page and state tests**

Run:

```powershell
pnpm.cmd test src/features/dashboard/dashboard-subscriptions.test.ts src/pages/DashboardPage.test.ts
```

Expected: PASS.

### Task 3: Regression and production verification

**Files:**
- Verify only; no planned source changes.

**Interfaces:**
- Consumes: Completed subscription state module and Dashboard integration.
- Produces: Verification evidence.

- [ ] **Step 1: Run Dashboard aggregation and page regressions**

Run:

```powershell
pnpm.cmd test src/domain/dashboard.test.ts src/pages/DashboardPage.test.ts src/features/dashboard/dashboard-subscriptions.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run TypeScript validation**

Run:

```powershell
pnpm.cmd typecheck
```

Expected: exit code 0.

- [ ] **Step 3: Run the production build**

Run:

```powershell
pnpm.cmd build
```

Expected: Vue typecheck and Vite production build both complete successfully.

- [ ] **Step 4: Review the final diff**

Run:

```powershell
git diff --check
git diff -- src/features/dashboard/dashboard-subscriptions.ts src/features/dashboard/dashboard-subscriptions.test.ts src/pages/DashboardPage.vue src/pages/DashboardPage.test.ts
```

Confirm that no API contract, permission profile, KPI logic, schedule logic, or unrelated file changed.
