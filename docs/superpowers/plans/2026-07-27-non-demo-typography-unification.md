# Non-Demo Typography Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply a consistent, readable desktop typography scale to every CRM route except Demo Archive, Demo Request, and Demo Test.

**Architecture:** `AppShell` marks the routed content container with `standard-typography` only for non-Demo routes. A dedicated global stylesheet applies semantic type tokens and route-scoped overrides, while the three Demo routes receive no new class and therefore retain their current computed styles.

**Tech Stack:** Vue 3, Vue Router, TypeScript, scoped and global CSS, Vitest, Vue Test Utils

## Global Constraints

- Exclude `/demo-workflow`, `/demo-requests`, and `/evaluations`.
- Keep existing information-center sizes as a lower bound.
- Target desktop layout; do not redesign mobile structure.
- Do not change colors, spacing, business logic, dependencies, or responsive layout.
- Do not use browser zoom or transforms to simulate font scaling.

---

### Task 1: Add route-level typography isolation

**Files:**
- Modify: `src/app/AppShell.vue`
- Test: `src/app/AppShell.test.ts`

**Interfaces:**
- Produces: `.route-content.standard-typography` for non-Demo routes.
- Preserves: `.route-content` without that class for the three Demo routes.

- [ ] **Step 1: Write the failing AppShell test**

Add a route-behavior test:

```ts
it('applies standard typography outside Demo routes only', async () => {
  const router = createAppRouter()
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
  await router.push('/accounts')
  await router.isReady()
  const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

  expect(wrapper.get('main.route-content').classes()).toContain('standard-typography')
  for (const path of ['/demo-workflow', '/demo-requests', '/evaluations']) {
    await router.push(path)
    await flushPromises()
    expect(wrapper.get('main.route-content').classes()).not.toContain('standard-typography')
  }
})
```

- [ ] **Step 2: Run the AppShell test and verify RED**

Run:

```powershell
pnpm.cmd test src/app/AppShell.test.ts
```

Expected: FAIL because the routed content does not yet expose `standard-typography`.

- [ ] **Step 3: Implement the route class**

- Add an immutable set containing the three excluded paths.
- Add `usesStandardTypography`, derived from `route.path`.
- Bind `standard-typography` to `main.route-content`.

- [ ] **Step 4: Run the AppShell test and verify GREEN**

Run:

```powershell
pnpm.cmd test src/app/AppShell.test.ts
```

Expected: all AppShell tests pass.

---

### Task 2: Add the non-Demo semantic typography layer

**Files:**
- Create: `src/design-system/typography.css`
- Modify: `src/main.ts`
- Test: browser computed-style verification on the built preview

**Interfaces:**
- Consumes: `.route-content.standard-typography`.
- Produces:
  - `--crm-type-caption: 10px`
  - `--crm-type-secondary: 11px`
  - `--crm-type-body: 12px`
  - `--crm-type-emphasis: 13px`
  - `--crm-type-section: 16px`

- [ ] **Step 1: Add the route-scoped stylesheet**

Create `src/design-system/typography.css` with:

- The five semantic type variables.
- `12px` controls, table cells, body copy, definitions, and list copy.
- `10px` captions, eyebrows, table headers, badges, status metadata, and chart-adjacent labels.
- `11px` secondary copy and footnotes.
- `13px` emphasized list copy.
- `15–16px` card and section headings.
- Explicit information-center rules that do not reduce its existing sizes.
- No selectors outside `.route-content.standard-typography`.

- [ ] **Step 2: Import the stylesheet after existing design-system CSS**

Append:

```ts
import './design-system/typography.css'
```

after `workspace.css` in `src/main.ts`.

- [ ] **Step 3: Run static verification**

Run:

```powershell
pnpm.cmd test src/app/AppShell.test.ts src/pages/DashboardPage.test.ts src/pages/customer-operations.test.ts src/pages/first-demo-completion.test.ts
pnpm.cmd run typecheck
pnpm.cmd run build
```

Expected: route and page tests pass except any already-known unrelated baseline assertion, typecheck exits 0, and build exits 0.

- [ ] **Step 4: Verify computed styles in the built preview**

At `http://localhost:4173/`, inspect:

- Information Center
- Accounts
- Visits & Actions
- Installed Tools
- Document Center
- Demo Archive
- Demo Request
- Demo Test

For non-Demo pages, confirm primary body/control text is at least `12px`, captions are at least `10px`, section titles are `15–16px`, and no layout overflow appears. Capture representative Demo computed styles before and after navigation and confirm the three excluded routes do not have `standard-typography`.

- [ ] **Step 5: Run final verification**

Run:

```powershell
git diff --check
pnpm.cmd test
```

Report focused results separately from known unrelated full-suite failures.
