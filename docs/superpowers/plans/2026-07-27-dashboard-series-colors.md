# Dashboard Series Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved orange, teal, and indigo mapping to management Dashboard data series.

**Architecture:** Define the three semantic colors once inside `src/charts/options.ts` and reuse them across relevant ECharts option builders. Extend the existing option-builder test to assert actual rendered series colors.

**Tech Stack:** TypeScript, ECharts, Vitest

## Global Constraints

- Pipeline is `#FE9900`.
- Weighted Pipeline is `#0D9488`.
- Booking is `#6366F1`.
- Do not change global positive/success colors.
- Do not change chart data or structure.

---

### Task 1: Apply semantic Dashboard chart colors

**Files:**
- Modify: `src/charts/options.ts`
- Test: `src/charts/options.test.ts`

**Interfaces:**
- Consumes: existing Dashboard DTO series data
- Produces: ECharts series with approved `itemStyle.color` values

- [x] **Step 1: Write a failing color-mapping test**

Assert owner performance colors equal `['#FE9900', '#0D9488', '#6366F1']`, booking-only color equals `#6366F1`, and Pipeline/Booking comparison colors equal `['#FE9900', '#6366F1']`.

- [x] **Step 2: Verify the new assertions fail**

Run: `npm.cmd test -- src/charts/options.test.ts`

Expected: FAIL because the current series use charcoal, brand orange, and green.

- [x] **Step 3: Implement the approved mapping**

```ts
const DASHBOARD_SERIES_COLORS = {
  pipeline: '#FE9900',
  weightedPipeline: '#0D9488',
  booking: '#6366F1',
} as const
```

Use these values in funnel, owner performance, booking-only, value distribution, account contribution, Pipeline mix, and count chart builders.

- [x] **Step 4: Verify code and rendered output**

Run:

```powershell
npm.cmd test -- src/charts/options.test.ts
npm.cmd run typecheck
npm.cmd run build
```

Reload `http://localhost:4173/` in management view and verify the chart legends and bars use the approved colors with no relevant console errors.
