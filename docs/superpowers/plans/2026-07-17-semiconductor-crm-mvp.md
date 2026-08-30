# Semiconductor CRM MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, testable Vue 3 semiconductor CRM MVP that preserves the prototype's core business flow and can later mount inside a Frappe Desk Page.

**Architecture:** A Vue app uses memory routing, Pinia, Element Plus, and ECharts behind a `.semicrm-app` namespace. Pages consume stable DTOs through a `CrmApi` interface; local mode selects an in-memory Mock Adapter, while a Frappe Adapter preserves the production integration boundary.

**Tech Stack:** Vue 3, TypeScript, Vite, Pinia, Vue Router, Element Plus, Apache ECharts, Vitest, Vue Test Utils.

## Global Constraints

- Use Vue Router `createMemoryHistory` and root namespace `.semicrm-app`.
- Do not write business data to `localStorage`.
- Keep the document colors exactly: `#123B4A`, `#147C72`, `#F5F7F7`, `#B8CC5A`, `#D6A84B`.
- Every data page must support loading, empty, error, permission denied, retry, and partial/stale feedback.
- Use typed API methods and POST for state-changing calls.
- Preserve Dashboard → Account → Requirement/Deal → Intelligence action traceability.

---

### Task 1: Project foundation and design tokens

**Files:**
- Create: `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`
- Create: `src/main.ts`, `src/App.vue`, `src/app/router.ts`, `src/design-system/tokens.css`, `src/design-system/base.css`
- Test: `src/design-system/tokens.test.ts`

**Interfaces:**
- Produces: `router: Router`, CSS custom properties scoped under `.semicrm-app`.

- [ ] **Step 1: Write the failing token test**

```ts
import { describe, expect, it } from 'vitest'
import tokens from './tokens.css?raw'

describe('design tokens', () => {
  it('contains the approved brand palette under the app namespace', () => {
    expect(tokens).toContain('.semicrm-app')
    expect(tokens).toContain('#123B4A')
    expect(tokens).toContain('#147C72')
    expect(tokens).toContain('#F5F7F7')
  })
})
```

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm vitest run src/design-system/tokens.test.ts`
Expected: FAIL because `tokens.css` does not exist.

- [ ] **Step 3: Add exact dependencies and the minimal application entry**

Create fixed dependency versions in `package.json`, configure Vite/Vitest with Vue, and mount `App.vue` into `#app`. Define `--crm-navy`, `--crm-teal`, `--crm-surface`, `--crm-positive`, and `--crm-warning` only inside `.semicrm-app`.

- [ ] **Step 4: Verify GREEN**

Run: `pnpm vitest run src/design-system/tokens.test.ts`
Expected: PASS, 1 test.

### Task 2: Typed domain API and in-memory data adapter

**Files:**
- Create: `src/types/crm.ts`, `src/api/contracts.ts`, `src/api/mock-data.ts`, `src/api/mock-adapter.ts`, `src/api/frappe-adapter.ts`, `src/api/index.ts`
- Test: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `CrmApi`, `getDashboard`, `listAccounts`, `getAccount360`, `listRequirements`, `listPipeline`, `listIntelligenceEvents`, `createActionFromEvent`.

- [ ] **Step 1: Write failing behavior tests**

```ts
it('keeps confirmed booking separate from open pipeline', async () => {
  const dashboard = await api.getDashboard({ range: 'quarter' })
  expect(dashboard.data.kpis.openPipeline).not.toBe(dashboard.data.kpis.confirmedBooking)
})

it('creates one action from a reviewed intelligence event', async () => {
  const action = await api.createActionFromEvent('INT-001')
  expect(action.data.sourceEventId).toBe('INT-001')
  await expect(api.createActionFromEvent('INT-001')).rejects.toMatchObject({ code: 'ACTION_EXISTS' })
})
```

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm vitest run src/api/mock-adapter.test.ts`
Expected: FAIL because the adapter methods are missing.

- [ ] **Step 3: Implement minimal typed adapter**

Return immutable cloned DTOs, simulate a short request delay, filter/paginate list results, keep writes in module memory, and throw normalized errors with request IDs. `frappe-adapter.ts` maps the same interface to `/api/method/semiconductor_crm.api.*` without being selected in local mode.

- [ ] **Step 4: Verify GREEN**

Run: `pnpm vitest run src/api/mock-adapter.test.ts`
Expected: PASS for separation, filters, pagination, account aggregation, and duplicate-action protection.

### Task 3: AppShell, navigation, shared data states

**Files:**
- Create: `src/app/AppShell.vue`, `src/app/navigation.ts`, `src/stores/app.ts`
- Create: `src/design-system/PageHeader.vue`, `KpiCard.vue`, `StatusBadge.vue`, `DataState.vue`, `SectionCard.vue`
- Test: `src/app/AppShell.test.ts`

**Interfaces:**
- Consumes: `router`, `CrmApi.getBootstrap()`.
- Produces: desktop/mobile navigation and reusable state components.

- [ ] **Step 1: Write failing shell test**

```ts
it('navigates to the five MVP routes without losing the shell', async () => {
  const wrapper = mount(AppShell, { global: { plugins: [router, pinia] } })
  await wrapper.get('[data-route="accounts"]').trigger('click')
  expect(router.currentRoute.value.path).toBe('/accounts')
  expect(wrapper.find('[data-testid="app-shell"]').exists()).toBe(true)
})
```

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm vitest run src/app/AppShell.test.ts`
Expected: FAIL because `AppShell.vue` is missing.

- [ ] **Step 3: Implement shell and state primitives**

Create grouped navigation, collapsible mobile drawer, user/role context, page outlet, visible focus rings, consistent status labels, and `DataState` variants for loading, empty, error, denied, and stale content.

- [ ] **Step 4: Verify GREEN**

Run: `pnpm vitest run src/app/AppShell.test.ts`
Expected: PASS for navigation, active state, and mobile toggle.

### Task 4: Dashboard vertical slice and chart builders

**Files:**
- Create: `src/pages/DashboardPage.vue`, `src/stores/dashboard.ts`
- Create: `src/charts/options.ts`, `src/charts/CrmChart.vue`
- Create: `src/features/dashboard/AttentionList.vue`, `src/features/dashboard/AccountHealthList.vue`
- Test: `src/charts/options.test.ts`, `src/pages/DashboardPage.test.ts`

**Interfaces:**
- Consumes: `CrmApi.getDashboard()` and `DashboardDto`.
- Produces: `buildFunnelOption(dto)` and `buildTrendOption(dto)` pure functions.

- [ ] **Step 1: Write failing chart and page-state tests**

```ts
it('uses amount and count in the funnel tooltip', () => {
  const option = buildFunnelOption([{ stage: '技术确认', amount: 8000000, weightedAmount: 2400000, count: 3 }])
  expect(JSON.stringify(option)).toContain('weightedAmount')
  expect(JSON.stringify(option)).toContain('count')
})

it('shows a retry action when dashboard loading fails', async () => {
  const wrapper = mount(DashboardPage, { global: testGlobalsWithFailingApi() })
  await flushPromises()
  expect(wrapper.get('[data-testid="retry-dashboard"]').text()).toContain('重试')
})
```

- [ ] **Step 2: Run tests to verify RED**

Run: `pnpm vitest run src/charts/options.test.ts src/pages/DashboardPage.test.ts`
Expected: FAIL because chart builders and page are missing.

- [ ] **Step 3: Implement dashboard**

Render KPI cards for open pipeline, weighted pipeline, confirmed booking, overdue actions, high-score intelligence, and active evaluations. Add an explainable horizontal funnel, monthly trend, priority account list, weekly actions, intelligence summary, data completeness, skeleton, empty, error, denied, and stale banner.

- [ ] **Step 4: Verify GREEN**

Run: `pnpm vitest run src/charts/options.test.ts src/pages/DashboardPage.test.ts`
Expected: PASS with no Vue warnings.

### Task 5: Accounts, requirements, pipeline, and intelligence workflow

**Files:**
- Create: `src/pages/AccountsPage.vue`, `RequirementsPage.vue`, `PipelinePage.vue`, `IntelligencePage.vue`
- Create: `src/features/accounts/AccountDrawer.vue`, `src/features/shared/FilterBar.vue`, `src/features/intelligence/IntelligenceCard.vue`
- Test: `src/pages/mvp-workflow.test.ts`

**Interfaces:**
- Consumes: the list and detail methods from `CrmApi`.
- Produces: route-level list/detail views and the intelligence-to-action interaction.

- [ ] **Step 1: Write failing workflow tests**

```ts
it('opens Account 360 from a filtered customer row', async () => {
  const wrapper = mount(AccountsPage, { global: testGlobals() })
  await flushPromises()
  await wrapper.get('[data-account-id="ACC-001"]').trigger('click')
  expect(wrapper.get('[data-testid="account-360"]').text()).toContain('Site')
})

it('turns a confirmed intelligence event into one visible action', async () => {
  const wrapper = mount(IntelligencePage, { global: testGlobals() })
  await flushPromises()
  await wrapper.get('[data-event-action="INT-001"]').trigger('click')
  expect(wrapper.text()).toContain('已创建跟进任务')
})
```

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm vitest run src/pages/mvp-workflow.test.ts`
Expected: FAIL because route pages are missing.

- [ ] **Step 3: Implement the minimum complete workflow**

Use server-style query objects for search/filter/page, fixed first columns on wide tables, card fallbacks on narrow screens, Account 360 in a drawer, separate Deal and Booking totals, visible source links, and a guarded POST-like action conversion with success feedback.

- [ ] **Step 4: Verify GREEN**

Run: `pnpm vitest run src/pages/mvp-workflow.test.ts`
Expected: PASS for filtering, drawer, pipeline separation, and event action.

### Task 6: Quality gate and responsive browser verification

**Files:**
- Modify: implementation files only where checks reveal defects.

**Interfaces:**
- Consumes: production build at the local preview URL.
- Produces: verified local MVP.

- [ ] **Step 1: Run full automated checks**

Run: `pnpm typecheck && pnpm test && pnpm build`
Expected: exit code 0; all tests pass; Vite emits `dist/`.

- [ ] **Step 2: Run the local preview and inspect every route**

Open `/dashboard`, `/accounts`, `/requirements`, `/pipeline`, and `/intelligence` at 1366x768, 1440x900, 1920x1080, and 820x1180.

- [ ] **Step 3: Check behavior and visual acceptance**

Confirm no horizontal overflow, clipped text, overlapping charts, global body/Desk selector overrides, console errors, fake zero-data charts, or color-only states. Exercise account drawer, filters, retry state, navigation, and intelligence-to-action.

- [ ] **Step 4: Re-run the quality gate after any correction**

Run: `pnpm typecheck && pnpm test && pnpm build`
Expected: exit code 0 with the final source tree.
