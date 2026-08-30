# Dashboard Demo / Wafer Test Priority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the management dashboard's owner-performance chart with the existing Demo / Wafer Test status chart and show it first without duplicating it in expanded analysis.

**Architecture:** Reuse `DashboardDto.process.evaluationByStatus` and `buildCountBreakdownOption` directly in `DashboardPage.vue`. Keep the existing three-card grid and remove the promoted evaluation chart from `processCharts`, so no data-domain or API changes are required.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, Vue Test Utils, ECharts

## Global Constraints

- Only modify `src/pages/DashboardPage.vue` and `src/pages/DashboardPage.test.ts`.
- Do not change Dashboard aggregation, Mock data, API, permissions, other pages, dependencies, or frontend ports.
- Keep exactly three primary data-dashboard charts.
- Do not duplicate “Demo / Wafer Test 状态” in expanded analysis.

---

### Task 1: Promote Demo / Wafer Test status into the primary dashboard

**Files:**
- Modify: `src/pages/DashboardPage.test.ts`
- Modify: `src/pages/DashboardPage.vue`

**Interfaces:**
- Consumes: `DashboardDto.process.evaluationByStatus: Array<{ label: string; count: number }>`
- Consumes: `buildCountBreakdownOption(data): EChartsOption`
- Produces: A three-card primary dashboard led by the Demo / Wafer Test status chart.

- [ ] **Step 1: Write the failing page test**

Add primary dashboard assertions before expanding analysis:

```ts
const primaryCards = wrapper.findAll('.decision-grid > .section-card')
expect(primaryCards).toHaveLength(3)
expect(primaryCards[0].text()).toContain('Demo / Wafer Test 状态')
expect(primaryCards[0].text()).toContain('EVALUATION')
expect(wrapper.text()).not.toContain('团队业绩与管线')
```

After expanding analysis, assert that the promoted chart appears only once:

```ts
expect(wrapper.findAll('.section-card').filter((card) => card.text().includes('Demo / Wafer Test 状态'))).toHaveLength(1)
expect(wrapper.findAll('[data-testid="chart"]')).toHaveLength(18)
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run:

```powershell
pnpm.cmd test src/pages/DashboardPage.test.ts
```

Expected: FAIL because the first primary card is still “实际 Booking 月度分布”, “团队业绩与管线” still exists, and expanded analysis still contains the evaluation chart.

- [ ] **Step 3: Implement the minimal page change**

In `DashboardPage.vue`:

- Remove the `buildOwnerPerformanceOption` import and `ownerOption` computed value.
- Add `evaluationOption`, computed from `store.data?.process.evaluationByStatus ?? []`.
- Remove the `evaluation` entry from `processCharts`.
- Replace the “团队业绩与管线” card with “Demo / Wafer Test 状态”.
- Place that card first in `.decision-grid`.
- Use `store.data.process.evaluationByStatus.length` for its populated state and “暂无 Demo / Wafer Test 状态记录” for its empty state.

- [ ] **Step 4: Run focused and static verification**

Run:

```powershell
pnpm.cmd test src/pages/DashboardPage.test.ts
pnpm.cmd run typecheck
pnpm.cmd run build
```

Expected: Dashboard tests pass, typecheck exits 0, and build exits 0.

- [ ] **Step 5: Verify the live preview**

Refresh `http://localhost:4173/`, switch to Management Viewer, and confirm:

- The first primary chart is “Demo / Wafer Test 状态”.
- The primary grid has three charts.
- “团队业绩与管线” is absent.
- Expanded analysis contains no duplicate evaluation chart.
- Browser console has no errors.
