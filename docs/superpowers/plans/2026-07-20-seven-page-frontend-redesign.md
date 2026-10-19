# QIHENG Demo Seven-Page Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 QIHENG Demo Vue 前端内交付七个相互关联、可浏览和可交互的业务页面原型。

**Architecture:** 保留现有 AppShell、设计变量和旧页面，通过新的集中式只读演示数据模块驱动七个页面。新路由使用现有 Vue Router memory history；页面只维护选择、筛选和演示状态，不改变后端 API 契约。

**Tech Stack:** Vue 3、TypeScript、Vite、Pinia、Vue Router、Lucide Vue、Vitest、Vue Test Utils

## Global Constraints

- 本轮仅实现前端七页面，不创建 Frappe、MariaDB 或 Redis 容器。
- 保留 QIHENG Demo 原配色，不套用 Salesforce 配色。
- 模拟数据不得写入 `localStorage`，不得包含真实凭据或机密文件 URL。
- 旧页面和路由保留，主导航切换到新的七页面信息架构。
- 只修改本需求直接相关的前端文件。

---

### Task 1: 七页面契约与失败测试

**Files:**
- Create: `src/pages/seven-page-workspace.test.ts`
- Modify: `src/app/router.ts`
- Modify: `src/app/navigation.ts`

**Interfaces:**
- Consumes: Vue Test Utils `mount`、现有 AppShell 路由结构
- Produces: 七个路由键与页面标题的可执行验收契约

- [ ] **Step 1: 写入七页面渲染和交互失败测试**
- [ ] **Step 2: 运行 `pnpm vitest run src/pages/seven-page-workspace.test.ts`，确认因页面尚不存在而失败**
- [ ] **Step 3: 增加七个路由和四组导航**
- [ ] **Step 4: 重新运行路由相关断言**

### Task 2: 共享数据与展示组件

**Files:**
- Create: `src/demo/operations-data.ts`
- Create: `src/features/workspace/WorkspaceMetric.vue`
- Create: `src/features/workspace/StageRail.vue`
- Create: `src/design-system/workspace.css`
- Modify: `src/main.ts`

**Interfaces:**
- Produces: `executiveMetrics`、`opportunities`、`demoProjects`、`installedTools`、`serviceAppointments`、`procedureRuns`、`controlledDocuments`

- [ ] **Step 1: 在测试中声明页面需要的稳定 ID、状态和关联字段**
- [ ] **Step 2: 运行测试确认数据模块缺失**
- [ ] **Step 3: 实现集中式演示数据和共享指标/阶段组件**
- [ ] **Step 4: 运行测试确认数据和组件契约通过**

### Task 3: 管理与销售页面

**Files:**
- Create: `src/pages/ExecutiveDashboardPage.vue`
- Create: `src/pages/OpportunityStrategyPage.vue`
- Create: `src/pages/DemoWorkflowPage.vue`

**Interfaces:**
- Consumes: Task 2 的演示数据和共享组件
- Produces: 管理驾驶舱、商机策略和 Demo 全链路页面

- [ ] **Step 1: 运行七页面测试确认三个页面仍失败**
- [ ] **Step 2: 实现管理驾驶舱的五域指标、风险和管理关注事项**
- [ ] **Step 3: 实现商机选择、关系覆盖、红旗和 Action Plan**
- [ ] **Step 4: 实现 Demo、Wafer、Test Run 和客户确认的关联视图**
- [ ] **Step 5: 运行测试确认三个页面及商机/Demo选择交互通过**

### Task 4: 设备、服务、流程与文档页面

**Files:**
- Create: `src/pages/InstalledToolsPage.vue`
- Create: `src/pages/ServiceCalendarPage.vue`
- Create: `src/pages/ProcedureRunsPage.vue`
- Create: `src/pages/DocumentCenterPage.vue`

**Interfaces:**
- Consumes: Task 2 的演示数据和共享组件
- Produces: Installed Base、人工服务排期、升级流程和受控文档目录页面

- [ ] **Step 1: 运行七页面测试确认四个页面仍失败**
- [ ] **Step 2: 实现设备选择、交付时间线、版本和质保状态**
- [ ] **Step 3: 实现周排期、负责人负载、冲突和逾期任务**
- [ ] **Step 4: 实现流程阶段门和检查项会话内切换**
- [ ] **Step 5: 实现文档分类、访问策略、Current Version和申请状态**
- [ ] **Step 6: 运行测试确认七页和关键交互全部通过**

### Task 5: 定向验证

**Files:**
- Modify only if verification finds a defect in the files above

**Interfaces:**
- Produces: 可在本地浏览器验收的七页面前端

- [ ] **Step 1: 运行 `pnpm vitest run src/pages/seven-page-workspace.test.ts src/app/AppShell.test.ts`**
- [ ] **Step 2: 运行 `pnpm typecheck`**
- [ ] **Step 3: 运行 `pnpm build`**
- [ ] **Step 4: 启动本地预览并逐页检查七个路由**
- [ ] **Step 5: 在桌面和窄屏检查导航、溢出、选择和状态反馈**

