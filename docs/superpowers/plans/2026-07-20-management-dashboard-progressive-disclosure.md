# 经营决策中心渐进式分析 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将管理者首页改为“先结论、后细节”的底部收缩布局，并以真实 Open Pipeline 金额展示业务领域环形图。

**Architecture:** 不修改 Dashboard API 与领域聚合口径，继续使用 `segmentDistribution` 中由开放商机明细汇总的 `pipeline` 金额。图表层新增独立环形图配置函数；页面层只重排管理者视图，并用本地展开状态控制详细分析区。

**Tech Stack:** Vue 3、TypeScript、Pinia、ECharts 6、Vitest、Vue Test Utils

## Global Constraints

- 只使用现有业务明细，不补造季度目标、趋势或线索数据。
- 管理者权限保持只读，非管理者业务首页行为不变。
- 不引入新依赖，不修改无关页面。
- 仅运行 Dashboard 与图表相关定向测试，以及类型检查和生产构建。

---

### Task 1: Pipeline 业务结构环形图

**Files:**
- Modify: `src/charts/options.ts`
- Modify: `src/charts/CrmChart.vue`
- Test: `src/charts/options.test.ts`

**Interfaces:**
- Consumes: `DashboardDto['segmentDistribution']`
- Produces: `buildPipelineMixOption(data): EChartsOption`

- [ ] **Step 1: Write the failing test**

```ts
it('builds a pipeline-only donut with the open pipeline total', () => {
  const option = buildPipelineMixOption([
    { label: 'Frontend', pipeline: 70, booking: 20 },
    { label: 'Advanced Packaging', pipeline: 30, booking: 10 },
  ])
  const series = Array.isArray(option.series) ? option.series[0] : option.series
  expect(series).toMatchObject({ type: 'pie', radius: ['56%', '76%'] })
  expect((series as { data: unknown[] }).data).toEqual([
    { name: 'Frontend', value: 70 },
    { name: 'Advanced Packaging', value: 30 },
  ])
  expect(option.title).toMatchObject({ text: '¥0万', subtext: 'Open Pipeline' })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/charts/options.test.ts`

Expected: FAIL because `buildPipelineMixOption` is not exported.

- [ ] **Step 3: Write minimal implementation**

```ts
export function buildPipelineMixOption(data: DashboardDto['segmentDistribution']): EChartsOption {
  const total = data.reduce((sum, item) => sum + item.pipeline, 0)
  return {
    title: { text: compactMoney(total), subtext: 'Open Pipeline', left: 'center', top: '39%' },
    tooltip: { trigger: 'item', valueFormatter: (value) => compactMoney(Number(value)) },
    legend: { bottom: 0, left: 'center' },
    series: [{ type: 'pie', radius: ['56%', '76%'], center: ['50%', '45%'], data: data.map((item) => ({ name: item.label, value: item.pipeline })) }],
  }
}
```

同时在 `CrmChart.vue` 注册 `PieChart` 与 `TitleComponent`。

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/charts/options.test.ts`

Expected: PASS.

### Task 2: 管理者首页收缩布局

**Files:**
- Modify: `src/pages/DashboardPage.vue`
- Test: `src/pages/DashboardPage.test.ts`

**Interfaces:**
- Consumes: `store.data.kpis`、`store.data.segmentDistribution` 和现有分析数据
- Produces: 默认只显示五个核心图表，点击 `data-testid="toggle-more-analysis"` 后显示全部二十一个图表

- [ ] **Step 1: Write the failing test**

```ts
expect(wrapper.text()).toContain('Pipeline 业务结构')
expect(wrapper.text()).toContain('管理者待干预')
expect(wrapper.text()).toContain('查看更多分析')
expect(wrapper.findAll('[data-testid="chart"]')).toHaveLength(5)
await wrapper.get('[data-testid="toggle-more-analysis"]').trigger('click')
expect(wrapper.findAll('[data-testid="chart"]')).toHaveLength(21)
expect(wrapper.text()).toContain('收起更多分析')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/pages/DashboardPage.test.ts`

Expected: FAIL because the page still renders all charts and has no toggle.

- [ ] **Step 3: Write minimal implementation**

在 `DashboardPage.vue` 中：

```ts
const showMoreAnalysis = ref(false)
const segmentOption = computed(() => buildPipelineMixOption(store.data?.segmentDistribution ?? []))
```

首屏保留 KPI、管线漏斗、Pipeline 业务结构、管理者待干预、季度 Booking、重点客户和团队对比。客户维度、流程图、行动列表、交付提醒与完整度全部放入由按钮控制的 `v-if="showMoreAnalysis"` 区域。

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/pages/DashboardPage.test.ts`

Expected: PASS.

### Task 3: 定向验证

**Files:**
- Verify only; no planned production changes

- [ ] **Step 1: Run related tests**

Run: `pnpm test src/charts/options.test.ts src/pages/DashboardPage.test.ts`

Expected: all selected tests PASS.

- [ ] **Step 2: Run type check**

Run: `pnpm typecheck`

Expected: exit code 0.

- [ ] **Step 3: Run production build**

Run: `pnpm build`

Expected: exit code 0 and Vite emits `dist` assets.

- [ ] **Step 4: Inspect the management dashboard in the browser**

Expected: default view is compact, the donut shows real Pipeline business mix, and the bottom control expands and collapses detailed analysis without changing data.
