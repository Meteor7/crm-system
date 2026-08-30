# Opportunity Sale Type Select Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Opportunity 的销售类型改为后端枚举一致的固定英文下拉框，并兼容旧前端值。

**Architecture:** 在现有 `OpportunityEditorModal.vue` 内集中声明三个合法选项和一个初始化归一化函数。表单继续提交原有 `saleType: string`，不改变 API、后端或数据库。

**Tech Stack:** Vue 3、TypeScript、Vue Test Utils、Vitest、Vite、Frappe frontend build、Docker Compose

## Global Constraints

- 仅修改 Opportunity 新增/编辑共用弹窗及其聚焦测试。
- 选项精确为 `New Equipment`、`Repeat Order`、`Service`。
- `New Tool` 映射为 `New Equipment`；`Capacity Expansion` 映射为 `Repeat Order`。
- 新建或空值默认使用 `New Equipment`。
- 不修改 API payload、Frappe 后端枚举、DocType 或数据库。
- 按用户要求先实施再测试，不 commit、reset、stash 或 clean，不删除 Docker volumes。

---

### Task 1: 固定 Sale Type 下拉框

**Files:**
- Modify: `src/features/opportunities/OpportunityEditorModal.vue`
- Create: `src/features/opportunities/OpportunityEditorModal.test.ts`

**Interfaces:**
- Consumes: `StrategyOpportunityDto.saleType: string`、`CreateStrategyOpportunityInput.saleType: string`
- Produces: `normalizeSaleType(value?: string): string` 和仅提交合法英文枚举的 `select`

- [x] **Step 1: 添加枚举和旧值归一化**

  在组件脚本中定义：

  ```ts
  const SALE_TYPE_OPTIONS = ['New Equipment', 'Repeat Order', 'Service'] as const

  function normalizeSaleType(value?: string) {
    if (value === 'New Tool') return 'New Equipment'
    if (value === 'Capacity Expansion') return 'Repeat Order'
    return SALE_TYPE_OPTIONS.includes(value as typeof SALE_TYPE_OPTIONS[number]) ? value! : 'New Equipment'
  }
  ```

  使用 `normalizeSaleType(props.opportunity?.saleType)` 初始化 `form.saleType`。

- [x] **Step 2: 将自由输入改为下拉框**

  使用以下模板替换销售类型文本框：

  ```vue
  <select v-model="form.saleType" aria-label="Opportunity 销售类型">
    <option v-for="saleType in SALE_TYPE_OPTIONS" :key="saleType" :value="saleType">{{ saleType }}</option>
  </select>
  ```

- [x] **Step 3: 增加聚焦测试**

  新建组件测试，断言新建默认值与三个精确选项，并分别挂载 `saleType` 为 `New Tool`、`Capacity Expansion` 和 `Service` 的编辑数据，验证初始化选中值为 `New Equipment`、`Repeat Order` 和 `Service`。

- [x] **Step 4: 运行聚焦测试**

  Run: `pnpm.cmd test src/features/opportunities/OpportunityEditorModal.test.ts src/pages/opportunity-strategy-operations.test.ts`

  Expected: 目标测试全部通过。

- [x] **Step 5: 运行 Frappe 生产构建并刷新受控 App ZIP**

  Run: `pnpm.cmd run build:frappe`

  Run: `powershell -ExecutionPolicy Bypass -File backend/scripts/prepare-app-build-context.ps1`

  Expected: TypeScript 检查和 Frappe 模式构建通过，受控 ZIP 逐项完整性复验通过。

- [x] **Step 6: 刷新本地 Docker 前端并检查健康状态**

  Run: `docker compose -p rayher-crm-stage1-local -f backend/compose.yaml up -d --build frontend`

  Run: `docker compose -p rayher-crm-stage1-local -f backend/compose.yaml ps`

  Expected: frontend、backend 与 db 保持健康，`http://127.0.0.1:2224/crm` 返回 HTTP 200。
