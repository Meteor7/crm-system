# Management Dashboard and Customer Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 CRM 重构为具备真实权限边界、可追溯经营决策中心、原型式客户档案/Excel 报告、拜访管理、组织关系和对齐验证卡片的本地 MVP。

**Architecture:** 沿用 Vue 3 + TypeScript + typed `CrmApi` + Mock/Frappe 双适配器。权限、Dashboard 聚合、拜访状态机、组织树和报告模型放入纯函数领域模块；页面只消费 DTO 和发出 typed command。客户报告继续使用原型的无依赖 XLSX ZIP/XML 生成方式，避免增加运行时依赖。

**Tech Stack:** Vue 3.5、TypeScript 5.9、Vite 8、Pinia 4、Vue Router memory history、Element Plus、ECharts 6、Vitest、Vue Test Utils。

## Global Constraints

- 经营决策中心只展示现有明细能够计算的数据；禁止固定趋势数组和比例缩放金额。
- `OpportunityDto[]` 是 Pipeline 金额事实来源；不使用 `AccountSummaryDto.pipelineAmount` 汇总管理指标。
- “管理者权限”严格只读；Sales、Sales Manager、FAE 和 CRM Administrator 按角色分工。
- `capabilities` 控制界面体验，Mock API 同时执行写权限校验；Frappe API 最终由后端裁决。
- 不补造线索、配额、服务工单、成交日期或预测分类。
- 客户报告缺失且不能确定性推导的字段显示“—”。
- 不使用 localStorage，不新增表格依赖。
- 只运行本轮相关 Vitest、`vue-tsc --noEmit`、生产构建和关键页面浏览器验收；不执行全量回归。
- 当前目录不是有效 Git 仓库，无法创建 worktree 或提交；每个任务完成后以定向测试作为检查点。

## File Structure

- `src/domain/permissions.ts`：角色配置、capability 查询和 Mock 权限断言。
- `src/domain/dashboard.ts`：从业务明细生成经营决策中心 DTO。
- `src/domain/visits.ts`：拜访状态流和输入校验。
- `src/domain/stakeholders.ts`：组织树生成与循环关系校验。
- `src/features/accounts/AccountProfile.vue`：常驻客户 360 详情。
- `src/features/accounts/customer-report-model.ts`：五工作表数据模型。
- `src/features/accounts/xlsx-writer.ts`：OpenXML/ZIP 写入和下载。
- `src/pages/VisitsPage.vue`、`src/pages/StakeholdersPage.vue`：新增业务页面。
- `src/charts/options.ts`：通用可追溯条形、环形和堆叠图配置。

---

### Task 1: Role Profiles and Capability Enforcement

**Files:**
- Create: `src/domain/permissions.ts`
- Create: `src/domain/permissions.test.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/stores/app.ts`
- Modify: `src/app/navigation.ts`
- Modify: `src/app/AppShell.vue`
- Test: `src/app/AppShell.test.ts`
- Test: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `UserRole`, `Capability`, `ROLE_PROFILES`, `hasCapability(bootstrap, capability)`, `assertCapability(capabilities, capability)`.
- Produces: `createMockApi({ latency, role })` for role-specific tests.
- Consumes: existing `BootstrapDto` and `CrmApiError`.

- [ ] **Step 1: Write failing permission tests**

```ts
expect(ROLE_PROFILES['Management Viewer'].capabilities).toContain('dashboard:management')
expect(ROLE_PROFILES['Management Viewer'].capabilities).not.toContain('demo_request:manager_approve')
expect(() => assertCapability(ROLE_PROFILES['Sales User'].capabilities, 'evaluation:write'))
  .toThrowError(/无权/)
```

Add API tests that a Management Viewer can read Dashboard/Account 360 but receives `PERMISSION_DENIED` from `transitionDemoRequest`, and a FAE can perform `engineer_approve` but not `manager_approve`.

- [ ] **Step 2: Run the permission tests and verify RED**

Run: `pnpm exec vitest run src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/app/AppShell.test.ts`
Expected: FAIL because role profiles and write permission enforcement do not exist.

- [ ] **Step 3: Implement typed role profiles**

```ts
export type UserRole = 'CRM Administrator' | 'Management Viewer' | 'Sales Manager' | 'Sales User' | 'FAE / Applied Engineer'
export type Capability =
  | 'dashboard:view' | 'dashboard:management' | 'account:view' | 'account:write' | 'account_report:export'
  | 'stakeholder:view' | 'stakeholder:write' | 'requirement:view' | 'requirement:write'
  | 'deal:view' | 'deal:write' | 'visit:view' | 'visit:write' | 'visit:review'
  | 'demo_request:view' | 'demo_request:create' | 'demo_request:engineering_review' | 'demo_request:manager_approve'
  | 'evaluation:view' | 'evaluation:write' | 'contract:view' | 'system:configure'

export const ROLE_PROFILES: Record<UserRole, { label: string; scope: 'all' | 'cross-team-readonly' | 'team' | 'own' | 'assigned'; capabilities: Capability[] }> = {
  'CRM Administrator': { label: 'CRM 管理员', scope: 'all', capabilities: ALL_CAPABILITIES },
  'Management Viewer': { label: '管理者权限', scope: 'cross-team-readonly', capabilities: MANAGEMENT_READ_CAPABILITIES },
  'Sales Manager': { label: '销售经理', scope: 'team', capabilities: SALES_MANAGER_CAPABILITIES },
  'Sales User': { label: '销售人员', scope: 'own', capabilities: SALES_USER_CAPABILITIES },
  'FAE / Applied Engineer': { label: 'FAE / 应用工程师', scope: 'assigned', capabilities: FAE_CAPABILITIES },
}
```

Use the role profile in Mock bootstrap, filter navigation by each item's `capability`, and assert the correct capability before every Mock write method. Map new Frappe methods without trusting the client capability.

- [ ] **Step 4: Run permission tests and verify GREEN**

Run: `pnpm exec vitest run src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/app/AppShell.test.ts`
Expected: PASS; Management Viewer is read-only and role-specific actions are enforced.

### Task 2: Traceable Management Dashboard Aggregation

**Files:**
- Create: `src/domain/dashboard.ts`
- Create: `src/domain/dashboard.test.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/stores/dashboard.ts`
- Modify: `src/charts/options.ts`
- Modify: `src/charts/options.test.ts`
- Modify: `src/pages/DashboardPage.vue`
- Modify: `src/pages/DashboardPage.test.ts`

**Interfaces:**
- Produces: `buildManagementDashboard(input): DashboardDto`.
- Produces: `buildBarOption`, `buildDonutOption`, `buildGroupedBarOption`.
- Consumes: accounts, opportunities, bookings, requirements, actions, demoRequests, evaluations, contracts and visits.

- [ ] **Step 1: Write failing aggregation tests**

```ts
const dashboard = buildManagementDashboard(fixtures)
expect(dashboard.kpis).toMatchObject({
  openPipeline: 97_100_000,
  weightedPipeline: 69_219_000,
  confirmedBooking: 22_400_000,
  cumulativeWon: 18_800_000,
})
expect(dashboard.bookingByMonth).toEqual([
  { label: '2026-06', amount: 3_600_000, count: 1 },
  { label: '2026-07', amount: 18_800_000, count: 1 },
])
expect(JSON.stringify(dashboard)).not.toContain('rangeFactor')
```

Also assert funnel totals, owner ranking, Top customers, segment/region distributions and process status breakdowns.

- [ ] **Step 2: Run Dashboard domain tests and verify RED**

Run: `pnpm exec vitest run src/domain/dashboard.test.ts src/charts/options.test.ts src/pages/DashboardPage.test.ts`
Expected: FAIL because current Dashboard uses hard-coded trends and scaled totals.

- [ ] **Step 3: Implement pure management aggregation and chart builders**

```ts
const open = opportunities.filter(item => !['Won', 'Lost'].includes(item.stage))
const openPipeline = sum(open, item => item.amount)
const weightedPipeline = sum(open, item => item.amount * item.probability / 100)
const confirmed = bookings.filter(item => item.status === 'Confirmed')
const cumulativeWon = sum(opportunities.filter(item => item.stage === 'Won'), item => item.amount)
```

Return only record-derived arrays. Keep `DashboardQuery` for API compatibility but stop scaling snapshot values by range. The page title becomes “经营决策中心”; remove the fake period selector and fixed delta labels. Render sections for KPIs, pipeline, customer contribution and process status. Every chart gets a source/口径 description and an empty state when its array is empty.

- [ ] **Step 4: Run Dashboard tests and verify GREEN**

Run: `pnpm exec vitest run src/domain/dashboard.test.ts src/charts/options.test.ts src/pages/DashboardPage.test.ts`
Expected: PASS with the four exact KPI values and no hard-coded trend assertions.

### Task 3: Visit Domain, API and Account Linkage

**Files:**
- Create: `src/domain/visits.ts`
- Create: `src/domain/visits.test.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-data.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `VisitDto`, `CreateVisitInput`, `UpdateVisitCommand`, `VISIT_STATUS_ORDER`, `transitionVisit`.
- Adds API: `listVisits`, `createVisit`, `updateVisit`.
- Adds `visits: VisitDto[]` to `Account360Dto`.

- [ ] **Step 1: Write failing visit state tests**

```ts
expect(transitionVisit(planned, { type: 'advance', status: 'Visited', outcome: '已完成现场交流' }).status).toBe('Visited')
expect(() => transitionVisit(planned, { type: 'advance', status: 'Manager Reviewed' }))
  .toThrowError(/不能从 Planned/)
expect(transitionVisit(minutes, { type: 'complete_action' }).actionDone).toBe(true)
```

Add API tests for customer/status/owner/date filtering, create validation, management review permission and Account 360 linkage.

- [ ] **Step 2: Run visit tests and verify RED**

Run: `pnpm exec vitest run src/domain/visits.test.ts src/api/mock-adapter.test.ts`
Expected: FAIL because Visit types and endpoints are absent.

- [ ] **Step 3: Implement visit data and API**

```ts
export type VisitStatus = 'Planned' | 'Visited' | 'Minutes Submitted' | 'Manager Reviewed'
export interface VisitDto {
  id: string; accountId: string; accountName: string; segment: AccountSummaryDto['segment']
  subject: string; date: string; type: 'On-site' | 'Video' | 'Phone'
  status: VisitStatus; owner: string; objective: string; outcome: string
  nextAction: string; actionOwner: string; due: string; actionDone: boolean
}
```

Seed only visits that map to current customers from the existing prototype (`V-001` → `ACC-001`, `V-003` → `ACC-006`). Store mutations in the Mock Adapter's cloned in-memory collection and append the filtered visits to `getAccount360`.

- [ ] **Step 4: Run visit tests and verify GREEN**

Run: `pnpm exec vitest run src/domain/visits.test.ts src/api/mock-adapter.test.ts`
Expected: PASS for filtering, transition rules, review permission and Account 360 linkage.

### Task 4: Stakeholder Domain and Organization Tree

**Files:**
- Create: `src/domain/stakeholders.ts`
- Create: `src/domain/stakeholders.test.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `StakeholderInput`, `StakeholderNode`, `buildStakeholderForest`, `validateReportingLine`.
- Adds API: `listStakeholders`, `saveStakeholder`.

- [ ] **Step 1: Write failing organization tests**

```ts
expect(buildStakeholderForest(rows)[0].children[0].contact.id).toBe('CON-002')
expect(() => validateReportingLine(rows, 'CON-001', 'CON-001')).toThrowError(/不能汇报给自己/)
expect(() => validateReportingLine(rows, 'CON-001', 'CON-003')).toThrowError(/循环汇报/)
```

Add Mock API tests for Sales User write, Management Viewer write denial, edit persistence and detail-count source of truth.

- [ ] **Step 2: Run stakeholder tests and verify RED**

Run: `pnpm exec vitest run src/domain/stakeholders.test.ts src/api/mock-adapter.test.ts`
Expected: FAIL because `reportsTo`, email, organization tree and save endpoint are absent.

- [ ] **Step 3: Implement stakeholder fields and validation**

```ts
export type BuyingRole = 'Decision Maker' | 'Economic Buyer' | 'Champion' | 'Technical Champion' | 'Technical Evaluator' | 'Procurement' | 'Influencer' | 'Blocker' | 'User'
export interface ContactDto {
  id: string; name: string; title: string; department: string; role: BuyingRole
  influence: 'High' | 'Medium' | 'Low'; relationship: 'Strong' | 'Developing' | 'Weak'
  reportsTo?: string; email?: string
}
```

Do not infer reporting lines or email for existing contacts. Invalid/missing parent IDs render as roots with a data-quality flag. `getAccount360` derives stakeholder count from detailed contacts.

- [ ] **Step 4: Run stakeholder tests and verify GREEN**

Run: `pnpm exec vitest run src/domain/stakeholders.test.ts src/api/mock-adapter.test.ts`
Expected: PASS for tree generation, cycle prevention and role write rules.

### Task 5: Visit and Stakeholder Pages

**Files:**
- Create: `src/pages/VisitsPage.vue`
- Create: `src/pages/StakeholdersPage.vue`
- Create: `src/features/visits/VisitModal.vue`
- Create: `src/features/stakeholders/StakeholderModal.vue`
- Create: `src/pages/customer-operations.test.ts`
- Modify: `src/app/router.ts`
- Modify: `src/app/navigation.ts`

**Interfaces:**
- Consumes: visit/stakeholder APIs and domain functions from Tasks 3–4.
- Produces: `/visits` and `/stakeholders` routes.

- [ ] **Step 1: Write failing page tests**

```ts
expect(visits.text()).toContain('待拜访')
expect(visits.text()).toContain('管理者已审核')
expect(stakeholders.text()).toContain('组织关系图')
expect(stakeholders.text()).toContain('缺少 Economic Buyer')
```

Test filters, create visit, submit minutes, management review, add/edit stakeholder, and cycle validation feedback.

- [ ] **Step 2: Run page tests and verify RED**

Run: `pnpm exec vitest run src/pages/customer-operations.test.ts`
Expected: FAIL because routes and pages are missing.

- [ ] **Step 3: Implement pages and modals**

Visits page uses date-from/date-to/customer/status/owner filters, shows the four-step status rail and exposes only permitted actions. Stakeholder page uses left customer selection, organization tree, detail table and one add/edit modal. Reuse `DataState`, `DataNotice`, `StatusBadge`, `ModalShell` and `FilterBar`.

```ts
const canReview = computed(() => hasCapability(app.bootstrap, 'visit:review'))
const canWrite = computed(() => hasCapability(app.bootstrap, 'visit:write'))
const canEditStakeholder = computed(() => hasCapability(app.bootstrap, 'stakeholder:write'))
```

- [ ] **Step 4: Run page tests and verify GREEN**

Run: `pnpm exec vitest run src/pages/customer-operations.test.ts src/app/AppShell.test.ts`
Expected: PASS and navigation items appear only for authorized roles.

### Task 6: Prototype Account Layout and Five-Sheet Report

**Files:**
- Create: `src/features/accounts/AccountProfile.vue`
- Create: `src/features/accounts/customer-report-model.ts`
- Create: `src/features/accounts/customer-report-model.test.ts`
- Create: `src/features/accounts/xlsx-writer.ts`
- Create: `src/features/accounts/xlsx-writer.test.ts`
- Modify: `src/pages/AccountsPage.vue`
- Modify: `src/features/accounts/AccountDrawer.test.ts`

**Interfaces:**
- Produces: `buildCustomerReportModel(detail, reportDate): CustomerWorkbookSpec`.
- Produces: `buildXlsxFile(spec): Uint8Array`, `downloadCustomerReport(spec): void`.
- Consumes: `Account360Dto`, including visits and expanded contacts.

- [ ] **Step 1: Write failing account/report tests**

```ts
const spec = buildCustomerReportModel(tsmcDetail, '2026-07-17')
expect(spec.sheets.map(sheet => sheet.name)).toEqual([
  '客户全貌 Overview', '商机 Opportunities', '需求与行动 Actions',
  '关键人与拜访 People', 'Demo与合同 Demo',
])
expect(spec.fileName).toMatch(/Customer_360_2026-07-17\.xlsx$/)
expect(findCell(spec, '商机 Opportunities', 'Confirmed Booking')).toBeDefined()
expect(findCell(spec, '关键人与拜访 People', '—')).toBeDefined()
```

Test that ACC-001 Booking is 0, counts come from detail rows, probability/Run averages are numeric percentages, and a Management Viewer can export but cannot edit.

- [ ] **Step 2: Run account/report tests and verify RED**

Run: `pnpm exec vitest run src/features/accounts/customer-report-model.test.ts src/features/accounts/xlsx-writer.test.ts src/features/accounts/AccountDrawer.test.ts`
Expected: FAIL because persistent profile and report modules are absent.

- [ ] **Step 3: Implement the report model and XLSX writer**

Port the prototype's `reportCell`, adaptive widths/heights, worksheet XML, styles XML, CRC32, stored ZIP and workbook relationship generation into focused modules. Use the current customer detail, not sample values.

```ts
export interface CustomerWorkbookSpec { fileName: string; sheets: CustomerWorksheetSpec[] }
export function downloadCustomerReport(spec: CustomerWorkbookSpec) {
  const bytes = buildXlsxFile(spec)
  const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = spec.fileName
  link.click()
  URL.revokeObjectURL(url)
}
```

Missing optional commercial fields and English actions are “—”. Do not reuse the sample workbook's CUSTOMER06 values.

- [ ] **Step 4: Replace drawer with persistent split Account Profile**

Accounts page keeps its filters but renders a two-column workspace: compact customer cards on the left and `AccountProfile` on the right. `AccountProfile` loads the selected Account 360, shows all requested sections and has “导出客户报告” when `account_report:export` is present. On narrow screens use one column.

- [ ] **Step 5: Run account/report tests and verify GREEN**

Run: `pnpm exec vitest run src/features/accounts/customer-report-model.test.ts src/features/accounts/xlsx-writer.test.ts src/features/accounts/AccountDrawer.test.ts src/pages/mvp-workflow.test.ts`
Expected: PASS for five sheets, selected-customer isolation and persistent split layout.

### Task 7: Evaluation Card Alignment

**Files:**
- Modify: `src/features/evaluations/EvaluationCard.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Create: `src/features/evaluations/EvaluationCard.test.ts`

**Interfaces:**
- Consumes: existing `EvaluationDto` and emits unchanged `status`/`run` events.
- Produces: fixed card content zones and identical board card height.

- [ ] **Step 1: Write failing layout test**

```ts
expect(wrapper.get('.evaluation-card').classes()).toContain('is-aligned')
expect(wrapper.get('.runs').attributes('data-scroll-region')).toBe('runs')
expect(wrapper.get('h3').classes()).toContain('line-clamp-2')
```

- [ ] **Step 2: Run card test and verify RED**

Run: `pnpm exec vitest run src/features/evaluations/EvaluationCard.test.ts`
Expected: FAIL because aligned zones do not exist.

- [ ] **Step 3: Implement aligned card layout**

Use a fixed `grid-template-rows`, common `min-height`, two-line title clamp, fixed scrollable Runs region and bottom-pinned controls/footer. Keep all existing behavior and status semantics.

- [ ] **Step 4: Run card test and verify GREEN**

Run: `pnpm exec vitest run src/features/evaluations/EvaluationCard.test.ts src/pages/delivery-workflow.test.ts`
Expected: PASS and existing status/Test Run interactions remain intact.

### Task 8: Targeted Integration and Visual Verification

**Files:**
- Modify if required by findings: only files changed in Tasks 1–7.
- Verify: generated `.xlsx` in browser download output.

**Interfaces:**
- Consumes all previous tasks.
- Produces final local MVP and verification evidence.

- [ ] **Step 1: Run only affected tests**

Run:

```powershell
pnpm exec vitest run src/domain/permissions.test.ts src/domain/dashboard.test.ts src/domain/visits.test.ts src/domain/stakeholders.test.ts src/charts/options.test.ts src/api/mock-adapter.test.ts src/app/AppShell.test.ts src/pages/DashboardPage.test.ts src/pages/customer-operations.test.ts src/features/accounts/customer-report-model.test.ts src/features/accounts/xlsx-writer.test.ts src/features/accounts/AccountDrawer.test.ts src/features/evaluations/EvaluationCard.test.ts src/pages/delivery-workflow.test.ts src/pages/mvp-workflow.test.ts
```

Expected: all selected test files pass.

- [ ] **Step 2: Run type and build checks**

Run: `pnpm typecheck`
Expected: exit 0.

Run: `pnpm build`
Expected: exit 0 and Vite writes `dist`.

- [ ] **Step 3: Browser-verify changed pages**

Verify Management Dashboard, Accounts split layout/export, Visits filters/actions, Stakeholder tree/modals and Evaluation card alignment at desktop and narrow widths. Confirm no console errors and denied roles do not see forbidden actions.

- [ ] **Step 4: Inspect the downloaded workbook**

Re-import the downloaded XLSX with the spreadsheet inspection tool. Confirm five exact sheet names, ACC-001 has zero Confirmed Booking, missing fields use “—”, amount cells are numeric, percentage cells are decimals with percentage formats, and rendered sheets match the provided sample's hierarchy without clipped headers.

- [ ] **Step 5: Final scope audit**

Confirm no lead/quota/service/lost-reason records were added, no hard-coded sales trend remains, no localStorage usage was introduced, and only record-derived Dashboard values are shown.
