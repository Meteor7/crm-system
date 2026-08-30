# Demo、Wafer Test 与合同管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 撤下客户情报并实现可操作的 Demo Request 审批、Demo/Wafer Test 追踪和合同到期管理 MVP。

**Architecture:** 沿用现有 Vue 3 页面、类型化 `CrmApi` 与 Mock/Frappe 双适配器。审批和测试写操作在 Mock Adapter 内存副本中执行，页面统一消费 envelope metadata、权限和错误状态。

**Tech Stack:** Vue 3.5、TypeScript 5.9、Vite 8、Pinia 4、Vue Router memory history、Vitest、Vue Test Utils、Lucide。

## Global Constraints

- 保持 `.semicrm-app` 样式命名空间和容器相对弹层，不向 Frappe Desk body 注入组件样式。
- 不使用 localStorage 作为业务数据源。
- Demo Request 经理批准必须自动生成且只生成一个 Evaluation。
- 合同风险基准日期固定为 `2026-07-17`，分为已到期、30、60、90 天和正常。
- 原始 HTML 原型与 Word 需求文档不得修改。

---

### Task 1: 领域类型、演示数据与风险计算

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/api/mock-data.ts`
- Create: `src/domain/contracts.ts`
- Test: `src/domain/contracts.test.ts`

**Interfaces:**
- Produces: `DemoRequestDto`, `EvaluationDto`, `TestRunDto`, `ContractDto`, `DemoRequestCommand`, `EvaluationStatusCommand`。
- Produces: `getContractRisk(endDate: string, today?: string): ContractRisk`。

- [ ] **Step 1: Write the failing contract-risk test**

```ts
expect(getContractRisk('2026-07-16')).toMatchObject({ band: 'expired' })
expect(getContractRisk('2026-08-10')).toMatchObject({ band: '30d' })
expect(getContractRisk('2026-09-01')).toMatchObject({ band: '60d' })
expect(getContractRisk('2026-10-01')).toMatchObject({ band: '90d' })
expect(getContractRisk('2027-01-01')).toMatchObject({ band: 'normal' })
```

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm exec vitest run src/domain/contracts.test.ts`
Expected: FAIL because `src/domain/contracts.ts` does not exist.

- [ ] **Step 3: Add focused DTOs and calculation**

```ts
export function getContractRisk(endDate: string, today = '2026-07-17') {
  const days = Math.ceil((new Date(`${endDate}T00:00:00+08:00`).getTime() - new Date(`${today}T00:00:00+08:00`).getTime()) / 86_400_000)
  const band = days < 0 ? 'expired' : days <= 30 ? '30d' : days <= 60 ? '60d' : days <= 90 ? '90d' : 'normal'
  return { days, band, label: days < 0 ? '已到期' : band === 'normal' ? '正常' : `${days} 天内` }
}
```

- [ ] **Step 4: Add prototype-aligned Demo Request, Evaluation, Test Run and Contract fixtures**

Use current `ACC-*`, `REQ-*` and `OPP-*` IDs; include all workflow states needed by page tests.

- [ ] **Step 5: Run test to verify GREEN**

Run: `pnpm exec vitest run src/domain/contracts.test.ts`
Expected: PASS.

### Task 2: API state machines and query endpoints

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `listDemoRequests`, `createDemoRequest`, `transitionDemoRequest`。
- Produces: `listEvaluations`, `updateEvaluationStatus`, `addEvaluationRun`, `listContracts`。

- [ ] **Step 1: Write failing state-machine tests**

```ts
const submitted = await api.transitionDemoRequest('DR-001', { type: 'submit' })
expect(submitted.data.status).toBe('Engineer Review')
await expect(api.transitionDemoRequest('DR-001', { type: 'manager_approve', comment: '' })).rejects.toMatchObject({ code: 'INVALID_TRANSITION' })
```

```ts
const approved = await api.transitionDemoRequest('DR-004', { type: 'manager_approve', comment: '批准' })
expect(approved.data.request.status).toBe('Converted')
expect(approved.data.evaluation?.demoRequestId).toBe('DR-004')
await expect(api.transitionDemoRequest('DR-004', { type: 'manager_approve', comment: '再次批准' })).rejects.toMatchObject({ code: 'EVALUATION_EXISTS' })
```

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm exec vitest run src/api/mock-adapter.test.ts`
Expected: FAIL because delivery endpoints are absent.

- [ ] **Step 3: Implement transitions with validation and history**

Validate source status, required engineering fields, return/reject comments and converted idempotency before mutating cloned local state.

- [ ] **Step 4: Add Test Run aggregation test and implementation**

```ts
const result = await api.addEvaluationRun('EVAL-001', { id: 'RUN-003', date: '2026-07-17', lot: 'LOT-03', wafers: 4, capture: 97, falsePositive: 2.1, wph: 35, summary: '达标' })
expect(result.data.runs.at(-1)?.status).toBe('Completed')
expect(result.data.wafers).toBe(result.data.runs.reduce((sum, run) => sum + run.wafers, 0))
```

- [ ] **Step 5: Add contract filtering and all Frappe method mappings**

Map endpoints under `semiconductor_crm.api.delivery.*` and keep envelope validation unchanged.

- [ ] **Step 6: Run adapter tests to verify GREEN**

Run: `pnpm exec vitest run src/api/mock-adapter.test.ts`
Expected: PASS.

### Task 3: Demo Request approval center

**Files:**
- Create: `src/design-system/ModalShell.vue`
- Create: `src/features/demo-requests/DemoRequestCard.vue`
- Create: `src/features/demo-requests/DemoRequestModal.vue`
- Create: `src/pages/DemoRequestsPage.vue`
- Test: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: Demo Request API methods from Task 2.
- Produces: route page at `/demo-requests`.

- [ ] **Step 1: Write failing page workflow test**

Mount `DemoRequestsPage`, assert four board columns, submit `DR-001`, approve `DR-004`, then assert `Converted` and linked Evaluation ID are visible.

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm exec vitest run src/pages/delivery-workflow.test.ts`
Expected: FAIL because page/components do not exist.

- [ ] **Step 3: Implement summary, filters and board**

Use the four prototype buckets and render `DataState` for loading, denied, errors and no matches.

- [ ] **Step 4: Implement container-local modal forms**

Support create, engineer confirm/return, manager approve/reject. Emit typed commands only; keep API mutation outside presentation components.

- [ ] **Step 5: Run page test to verify GREEN**

Run: `pnpm exec vitest run src/pages/delivery-workflow.test.ts`
Expected: PASS.

### Task 4: Evaluation board and Test Runs

**Files:**
- Create: `src/features/evaluations/EvaluationCard.vue`
- Create: `src/features/evaluations/TestRunModal.vue`
- Create: `src/pages/EvaluationsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: Evaluation APIs from Task 2.
- Produces: route page at `/evaluations`.

- [ ] **Step 1: Extend the failing workflow test**

Assert five buckets, add a completed Test Run, verify metrics and wafer total, then filter to an absent customer and see an empty state.

- [ ] **Step 2: Run test to verify RED**

Run: `pnpm exec vitest run src/pages/delivery-workflow.test.ts`
Expected: FAIL because evaluation page is absent.

- [ ] **Step 3: Implement board, status control and Test Run modal**

Bucket statuses exactly as the spec; require hold reason/resume date for `On Hold`; preserve source Request and report URL.

- [ ] **Step 4: Run test to verify GREEN**

Run: `pnpm exec vitest run src/pages/delivery-workflow.test.ts`
Expected: PASS.

### Task 5: Contract control and product integration

**Files:**
- Create: `src/pages/ContractsPage.vue`
- Modify: `src/app/navigation.ts`
- Modify: `src/app/router.ts`
- Modify: `src/pages/DashboardPage.vue`
- Modify: `src/types/crm.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/features/accounts/AccountDrawer.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Modify: `src/app/AppShell.test.ts`

**Interfaces:**
- Consumes: Contract API and `getContractRisk`.
- Produces: `/contracts` and delivery-focused Dashboard/Account 360.

- [ ] **Step 1: Write failing integration assertions**

Assert navigation contains the three delivery routes and no `/intelligence`; assert contract risk labels and filters; assert Dashboard and Account 360 contain no “客户情报”。

- [ ] **Step 2: Run tests to verify RED**

Run: `pnpm exec vitest run src/pages/delivery-workflow.test.ts src/app/AppShell.test.ts`
Expected: FAIL while old intelligence integration remains.

- [ ] **Step 3: Add routes/navigation and contract page**

Contract table uses `.crm-table.is-responsive` with `data-label` for mobile cards and summary cards hidden after permission denial.

- [ ] **Step 4: Replace intelligence Dashboard and Account 360 content**

Use pending Demo approvals, active evaluations, held evaluations and 90-day contracts; add Demo/Evaluation/Contract Account 360 tabs.

- [ ] **Step 5: Remove intelligence runtime files and API surface**

Delete `src/pages/IntelligencePage.vue`, `src/features/intelligence/IntelligenceCard.vue` and intelligence-only tests after replacement tests are RED.

- [ ] **Step 6: Run integration tests to verify GREEN**

Run: `pnpm exec vitest run src/pages/delivery-workflow.test.ts src/app/AppShell.test.ts src/features/accounts/AccountDrawer.test.ts`
Expected: PASS.

### Task 6: Documentation and final verification

**Files:**
- Modify: `README.md`
- Modify: implementation files only if verification finds a defect.

**Interfaces:**
- Produces: verified production bundle and local preview.

- [ ] **Step 1: Update README scope and Frappe endpoint notes**

Document Demo Request, Evaluation/Test Run and Contract modules; remove customer intelligence claims.

- [ ] **Step 2: Run the full quality gate**

Run: `pnpm test`, `pnpm typecheck`, `pnpm build`
Expected: all tests pass and `dist/` is emitted without errors.

- [ ] **Step 3: Audit product removal and CSS isolation**

Run: `rg -n "客户情报|/intelligence|IntelligenceEvent" src README.md` and `rg -n "element-plus/theme|localStorage\\." src`.
Expected: no intelligence runtime references, no Element theme import and no browser storage writes.

- [ ] **Step 4: Verify local preview**

Check `/` and the built JS entry on `http://127.0.0.1:4173` return HTTP 200.

## Plan Self-Review

- Spec coverage: each removal, workflow, test run, contract risk, Dashboard and Account 360 requirement maps to a task.
- Placeholder scan: no TBD/TODO or unspecified error handling remains.
- Type consistency: page tasks consume the exact API names defined in Task 2; Evaluation creation response is shared by Demo Request and Evaluation pages.
