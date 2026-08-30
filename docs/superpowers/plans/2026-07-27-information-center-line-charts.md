# Information Center KPI Color Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the newly added line-chart section and apply the approved four-color treatment to the Information Center KPI values.

**Architecture:** Revert only the line-chart code added in the previous iteration. Apply page-scoped semantic classes to the four existing KPI cards so shared `KpiCard` behavior and other pages remain unchanged.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils, ECharts 6.

## Global Constraints

- Keep the larger Information Center typography and five-item schedule.
- Keep the original three dashboard cards.
- Remove the new trend grid and its now-unused chart option builder.
- Apply `#FE9900`, `#0D9488`, `#6366F1`, and `var(--crm-navy)` to the four KPI values in order.
- Do not modify shared design-system defaults, other pages, data contracts, or backend behavior.
- Do not stop or restart the current Vite Preview process.
- Do not commit implementation files because they contain overlapping pre-existing user changes.

---

### Task 1: Define the rollback and KPI color contract in page tests

**Files:**
- Modify: `src/pages/DashboardPage.test.ts`

**Interfaces:**
- Produces: management view with three initial charts and no `trend-chart-grid`
- Produces: `.kpi-value-pipeline`, `.kpi-value-weighted`, `.kpi-value-booking`, `.kpi-value-won`

- [ ] **Step 1: Write the failing assertions**

In the management test, assert:

```ts
expect(wrapper.find('[data-testid="trend-chart-grid"]').exists()).toBe(false)
expect(wrapper.findAll('[data-testid="chart"]')).toHaveLength(3)
expect(wrapper.get('.kpi-value-pipeline').exists()).toBe(true)
expect(wrapper.get('.kpi-value-weighted').exists()).toBe(true)
expect(wrapper.get('.kpi-value-booking').exists()).toBe(true)
expect(wrapper.get('.kpi-value-won').exists()).toBe(true)
```

After expanding more analysis, expect 19 charts rather than 22.

- [ ] **Step 2: Verify RED**

Run:

```powershell
pnpm.cmd test src/pages/DashboardPage.test.ts
```

Expected: FAIL because the trend grid still exists and KPI semantic classes are absent.

---

### Task 2: Remove trend code and apply page-scoped KPI colors

**Files:**
- Modify: `src/pages/DashboardPage.vue`
- Modify: `src/charts/options.ts`
- Modify: `src/charts/options.test.ts`

**Interfaces:**
- Removes: `buildValueTrendOption`
- Removes: `trendCharts`
- Removes: `[data-testid="trend-chart-grid"]`
- Preserves: `.slice(0, 5)` and `dashboard-readable-type`

- [ ] **Step 1: Remove the trend option builder and its test**

Delete `TrendMetric`, `TREND_METRICS`, `buildValueTrendOption`, and the dedicated line-chart test/import. Do not alter any pre-existing chart option builder.

- [ ] **Step 2: Remove the trend grid from the page**

Delete the `buildValueTrendOption` import, `trendCharts` computed value, trend-grid template section, `.trend-chart-grid` rule, and its responsive selector.

- [ ] **Step 3: Add semantic KPI classes**

Apply:

```vue
<KpiCard class="kpi-value-pipeline" ... />
<KpiCard class="kpi-value-weighted" ... />
<KpiCard class="kpi-value-booking" ... />
<KpiCard class="kpi-value-won" ... />
```

Add page-scoped styles:

```css
.kpi-grid :deep(.kpi-card.kpi-value-pipeline > strong) { color: #FE9900; }
.kpi-grid :deep(.kpi-card.kpi-value-weighted > strong) { color: #0D9488; }
.kpi-grid :deep(.kpi-card.kpi-value-booking > strong) { color: #6366F1; }
.kpi-grid :deep(.kpi-card.kpi-value-won > strong) { color: var(--crm-navy); }
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
pnpm.cmd test src/charts/options.test.ts src/pages/DashboardPage.test.ts
```

Expected: 9 tests pass with zero failures.

---

### Task 3: Verify the listening frontend

**Files:**
- Verify only.

**Interfaces:**
- Verifies targeted tests, typecheck, build, rendered colors, chart removal, and permission boundary.

- [ ] **Step 1: Run typecheck and build**

```powershell
pnpm.cmd run typecheck
pnpm.cmd run build
```

Expected: both exit with code 0.

- [ ] **Step 2: Verify browser output on port 4173**

Reload the existing page without restarting Preview. Under Management Viewer confirm:

- five recent schedule items remain;
- the trend grid is absent;
- exactly the original three dashboard canvases are shown before expanded analysis;
- KPI computed colors are `rgb(254, 153, 0)`, `rgb(13, 148, 136)`, `rgb(99, 102, 241)`, and `rgb(183, 121, 31)`;
- browser console has zero errors.

- [ ] **Step 3: Inspect final scope**

```powershell
git diff --check -- src/pages/DashboardPage.vue src/pages/DashboardPage.test.ts src/charts/options.ts src/charts/options.test.ts
```

Confirm no other implementation files changed in this iteration.
