# Opportunity Strategy Mock Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在纯前端 Mock Demo 中新增设备工程师身份，并补齐客户、Opportunity Strategy、Stakeholder、Action 的角色受控写操作闭环。

**Architecture:** 扩展现有 `CrmApi` 契约和 `createMockApi()` 会话内状态，所有写操作在 Mock Adapter 中校验 Capability 与客户范围。页面复用 `ModalShell`，路由切换共享同一个活动 API 实例，刷新后重新创建 Mock 状态。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vue Router、Vitest、Vue Test Utils、Vite。

## Global Constraints

- 只使用 `VITE_API_ADAPTER=mock`，不修改 `backend`、数据库或 Docker。
- 不引入新依赖，不增加独立编辑路由。
- ID 使用 `ACC-xxx`、`SITE-xxx`、`OPP-xxx`、`STK-xxx`、`ACT-xxx`。
- Management Viewer、FAE、Equipment Engineer 不得写客户或商机；权限必须在 Mock Adapter 层执行。
- 变更保存在当前 Mock API 实例；浏览器刷新后恢复初始数据。
- 当前目录没有有效 `.git`，各任务完成后以测试检查点替代 commit；初始化 Git 后再统一提交。

---

### Task 1: Equipment Engineer 身份与权限

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/domain/permissions.ts`
- Modify: `src/demo/identities.ts`
- Test: `src/app/AppShell.test.ts`
- Test: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `UserRole` 新成员 `'Equipment Engineer'`。
- Produces: `ROLE_PROFILES['Equipment Engineer']`，scope 为 `assigned`。

- [ ] **Step 1: 写失败测试**

在 `AppShell.test.ts` 验证身份菜单包含 `data-identity-id="equipment-engineer"`；切换后角色显示“设备工程师”。在 `mock-adapter.test.ts` 验证该角色拥有 `evaluation:write`，但 `account:write` 与 `deal:write` 均被拒绝。

- [ ] **Step 2: 运行测试确认失败**

Run: `pnpm test src/app/AppShell.test.ts src/api/mock-adapter.test.ts --maxWorkers=1`

Expected: FAIL，原因是 Equipment Engineer 尚未定义。

- [ ] **Step 3: 最小实现**

将角色联合类型扩展为：

```ts
export type UserRole =
  | 'CRM Administrator'
  | 'Management Viewer'
  | 'Sales Manager'
  | 'Sales User'
  | 'FAE / Applied Engineer'
  | 'Equipment Engineer'
```

定义能力：

```ts
const EQUIPMENT_ENGINEER_CAPABILITIES: Capability[] = [
  'account:view', 'requirement:view', 'deal:view',
  'demo_request:view', 'demo_request:engineering_review',
  'evaluation:view', 'evaluation:write',
  'service:view', 'procedure:view', 'procedure:execute',
]
```

身份预设：

```ts
{
  id: 'equipment-engineer',
  name: '演示员工15',
  initials: '孙',
  role: 'Equipment Engineer',
  team: '设备验证工程',
  teamOwners: [],
  assignedAccountIds: ['ACC-001', 'ACC-002'],
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pnpm test src/app/AppShell.test.ts src/api/mock-adapter.test.ts --maxWorkers=1`

Expected: PASS。

### Task 2: Mock 写契约与会话状态

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/demo/operations-data.ts`
- Modify: `src/api/mock-adapter.ts`
- Test: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `CreateAccountInput`。
- Produces: `CreateStrategyOpportunityInput` 与 `UpdateStrategyOpportunityInput`。
- Produces: `OpportunityStakeholderInput` 与 `OpportunityActionInput`。
- Produces: `createAccount()`、`createStrategyOpportunity()`、`updateStrategyOpportunity()`、`saveOpportunityStakeholder()`、`deleteOpportunityStakeholder()`、`saveOpportunityAction()`、`deleteOpportunityAction()`。

- [ ] **Step 1: 写失败测试**

覆盖以下行为：管理员新增客户；Sales User 新增本人客户；设备工程师被拒绝；管理员新增/编辑商机；新增、编辑、删除 Stakeholder；新增、完成、删除 Action；每次商机子项操作追加 Change History；路由级重复读取仍返回变更后的数据。

- [ ] **Step 2: 运行测试确认失败**

Run: `pnpm test src/api/mock-adapter.test.ts --maxWorkers=1`

Expected: FAIL，原因是写方法不存在。

- [ ] **Step 3: 定义输入类型与 ID**

```ts
export interface CreateAccountInput {
  name: string
  shortName: string
  segment: AccountSummaryDto['segment']
  region: string
  city: string
  owner: string
}

export interface OpportunityStakeholderInput {
  id?: string
  name: string
  title: string
  role: string
  influence: string
  stance: string
  coverage: string
}

export interface OpportunityActionInput {
  id?: string
  title: string
  owner: string
  due: string
  status: 'Open' | 'Done'
}
```

为 `StrategyOpportunityDto.stakeholders` 和 `actions` 增加必填 `id`。

- [ ] **Step 4: 实现会话级副本和权限校验**

在 `createMockApi()` 内创建：

```ts
const localAccounts = clone(accounts)
const localSites = clone(sites)
const localStrategyOpportunities = clone(strategyOpportunities)
```

客户写方法调用 `assertCapability(capabilities, 'account:write')`；商机、Stakeholder、Action 写方法调用 `assertCapability(capabilities, 'deal:write')`，并对关联客户调用 `assertAccountScope(accountId)`。

新增 ID 使用最大数字加一，不复用删除过的 ID。写入历史格式为：

```ts
{ at: '2026-07-22 10:30', actor: userName, field: 'Action', from: 'Open', to: 'Done' }
```

- [ ] **Step 5: 运行 Adapter 测试**

Run: `pnpm test src/api/mock-adapter.test.ts --maxWorkers=1`

Expected: PASS。

### Task 3: 客户档案新增 Modal

**Files:**
- Modify: `src/pages/AccountsPage.vue`
- Test: `src/pages/customer-operations.test.ts`

**Interfaces:**
- Consumes: `CrmApi.createAccount(input: CreateAccountInput)`。
- Consumes: Pinia `app.can('account:write')`。

- [ ] **Step 1: 写失败测试**

验证管理员看到 `data-testid="new-account"`，提交名称、简称、Segment、地区、城市和 Owner 后列表出现新客户；Management Viewer 与 Equipment Engineer 不显示按钮。

- [ ] **Step 2: 运行测试确认失败**

Run: `pnpm test src/pages/customer-operations.test.ts --maxWorkers=1`

Expected: FAIL，找不到新增客户按钮。

- [ ] **Step 3: 实现 Modal 与校验**

在页面使用 `useAppStore()` 和 `ModalShell`。按钮仅在：

```ts
const canWrite = computed(() => app.can('account:write'))
```

为真时显示。提交前对六个字段执行 `trim()`；空字段显示“请补齐客户必填信息”。成功后关闭 Modal、执行 `load()`，并选中新记录 ID。

- [ ] **Step 4: 运行页面测试**

Run: `pnpm test src/pages/customer-operations.test.ts --maxWorkers=1`

Expected: PASS。

### Task 4: Opportunity 新增与编辑 Modal

**Files:**
- Create: `src/features/opportunities/OpportunityEditorModal.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Test: `src/pages/opportunity-strategy-operations.test.ts`

**Interfaces:**
- Consumes: `CrmApi.createStrategyOpportunity()`、`CrmApi.updateStrategyOpportunity()`。
- Produces: Modal emits `saved: [id: string]` 与 `close: []`。

- [ ] **Step 1: 写失败测试**

验证有 `deal:write` 的身份看到 `new-opportunity` 与 `edit-opportunity`；表单拒绝空标题、负数金额和 101 Probability；有效提交后列表和指标卡更新；只读身份不显示按钮。

- [ ] **Step 2: 运行测试确认失败**

Run: `pnpm test src/pages/opportunity-strategy-operations.test.ts --maxWorkers=1`

Expected: FAIL，编辑组件和按钮尚不存在。

- [ ] **Step 3: 实现编辑组件**

组件 props：

```ts
defineProps<{
  apiClient: CrmApi
  opportunity?: StrategyOpportunityDto
  accounts: AccountSummaryDto[]
}>()
```

表单覆盖规格中的商业字段；使用 `ModalShell`；校验金额 `>= 0`、Probability 在 `0..100`、客户和 Site 为可访问主数据。

- [ ] **Step 4: 接入页面并刷新指标**

页面使用 `useAppStore()` 计算 `canWrite`。保存后重新调用 `listStrategyOpportunities()`，选中返回 ID，指标卡继续从 `opportunities` 计算，不新增第二套汇总状态。

- [ ] **Step 5: 运行页面测试**

Run: `pnpm test src/pages/opportunity-strategy-operations.test.ts --maxWorkers=1`

Expected: PASS。

### Task 5: Stakeholder 与 Action 操作闭环

**Files:**
- Create: `src/features/opportunities/StakeholderEditorModal.vue`
- Create: `src/features/opportunities/ActionEditorModal.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Test: `src/pages/opportunity-strategy-operations.test.ts`

**Interfaces:**
- Consumes: Task 2 的四个 Stakeholder/Action 写方法。
- Produces: `saved` 和 `deleted` 后由页面重新加载选中商机。

- [ ] **Step 1: 写失败测试**

验证新增/编辑/删除 Stakeholder；新增/编辑/完成/删除 Action；完成 Action 后临期指标变化；Change History 出现对应记录；只读身份没有操作列和新增按钮。

- [ ] **Step 2: 运行测试确认失败**

Run: `pnpm test src/pages/opportunity-strategy-operations.test.ts --maxWorkers=1`

Expected: FAIL，操作入口不存在。

- [ ] **Step 3: 实现 Stakeholder Modal**

字段为 Name、Title、Buying Role、Influence、Attitude、Coverage Evidence。表格操作列提供“编辑”“删除”，删除前使用页面内确认状态，不调用浏览器原生 confirm。

- [ ] **Step 4: 实现 Action Modal 与快捷完成**

字段为 Title、Owner、Due Date、Status。Action 行提供“编辑”“完成/重开”“删除”。快捷状态切换调用 `saveOpportunityAction()`，不得直接修改 DTO。

- [ ] **Step 5: 运行页面测试**

Run: `pnpm test src/pages/opportunity-strategy-operations.test.ts --maxWorkers=1`

Expected: PASS。

### Task 6: 全量回归与构建

**Files:**
- Modify only if a failing regression is directly caused by Tasks 1–5.

**Interfaces:**
- Consumes: all prior tasks。
- Produces: verified Demo build。

- [ ] **Step 1: 运行改动点测试**

Run: `pnpm test src/app/AppShell.test.ts src/api/mock-adapter.test.ts src/pages/customer-operations.test.ts src/pages/opportunity-strategy-operations.test.ts --maxWorkers=1`

Expected: all PASS。

- [ ] **Step 2: 运行全量测试**

Run: `pnpm test --maxWorkers=1`

Expected: 0 failed。

- [ ] **Step 3: 类型检查与生产构建**

Run: `pnpm build`

Expected: `vue-tsc --noEmit` 和 `vite build` exit code 0。

- [ ] **Step 4: 验证纯 Mock 运行边界**

确认 `.env.local` 为 `VITE_API_ADAPTER=mock`；确认 `backend` 未修改；启动 `127.0.0.1:4173` 后验证设备工程师切换、客户新增、商机新增、Stakeholder 和 Action 闭环。
