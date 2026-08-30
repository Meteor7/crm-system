# System Date-Only Display And Opportunity Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全系统可见时间统一为 `YYYY-MM-DD`，并让 Opportunity 看板八个阶段保持单行、`Lost` 位于最右侧。

**Architecture:** 扩展现有 `src/domain/time.ts`，集中提供只影响展示的 `formatDisplayDate()`；各页面在模板渲染边界调用它，原始 DTO 和排序值保持不变。Opportunity 看板只修正 CSS 为八列和匹配的最小宽度。

**Tech Stack:** Vue 3、TypeScript、Vitest、Vue Test Utils、Vite、Frappe frontend build、PowerShell verified ZIP、Docker Compose

## Global Constraints

- 所有用户可见时间显示为 `YYYY-MM-DD`，不显示时分秒。
- 后端、数据库、API DTO、排序值、审计键和 `modified` 保留完整精度。
- 不修改日历月视图中的单独日号、业务时长文案或相对期限说明。
- Opportunity 看板顺序不变，只改为八列单行横向滚动。
- 不修改接口、权限、业务状态或数据库。
- 按用户要求先实施再测试；不 commit、reset、stash、clean，不删除 Docker volumes。

---

### Task 1: 统一日期展示工具

**Files:**
- Modify: `src/domain/time.ts`
- Modify: `src/domain/time.test.ts`

**Interfaces:**
- Consumes: `value: string | null | undefined`、可选 `now: Date`
- Produces: `formatDisplayDate(value, now?): string`

- [ ] **Step 1: 实现日期格式化规则**

  保留 `shanghaiDate()`、`shanghaiTimestamp()` 和 `addIsoDateDays()`；新增纯展示函数，依次识别空值、`YYYY-MM-DD`、带时分但无时区的日期、带时区时间、今天/昨天/刚刚/当前待办、`M月D日`、`M-D` 和 `N 天前`。无法识别文本原样返回。

- [ ] **Step 2: 扩展日期工具测试**

  使用固定 `now = new Date('2026-08-05T04:00:00Z')`，断言 ISO 时区转换、日期直通、日期时间截断、相对日期、月日、短日期、空值和未知文本。

### Task 2: 接入所有可见时间表面

**Files:**
- Modify: `src/app/AppShell.vue`
- Modify: `src/design-system/PageHeader.vue`
- Modify: `src/features/accounts/AccountDrawer.vue`
- Modify: `src/features/contacts/ContactFilesCard.vue`
- Modify: `src/features/dashboard/AccountHealthList.vue`
- Modify: `src/features/demo-requests/DemoRequestCard.vue`
- Modify: `src/features/demo-requests/DemoRequestWorkspace.vue`
- Modify: `src/features/demo-workflow/DemoArchiveDetail.vue`
- Modify: `src/features/demo-workflow/DemoCommentPanel.vue`
- Modify: `src/features/demo-workflow/DemoProjectTimeline.vue`
- Modify: `src/features/leads/LeadListView.vue`
- Modify: `src/features/opportunities/OpportunityListView.vue`
- Modify: `src/pages/AccountsPage.vue`
- Modify: `src/pages/BookingDetailPage.vue`
- Modify: `src/pages/BookingPage.vue`
- Modify: `src/pages/ContactDetailPage.vue`
- Modify: `src/pages/ContactsPage.vue`
- Modify: `src/pages/DashboardPage.vue`
- Modify: `src/pages/DocumentCenterPage.vue`
- Modify: `src/pages/InstalledToolsPage.vue`
- Modify: `src/pages/LeadDetailPage.vue`
- Modify: `src/pages/OpportunityDetailPage.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/pages/PipelinePage.vue`
- Modify: `src/pages/RequirementsPage.vue`
- Modify: `src/pages/ServiceCalendarPage.vue`
- Modify: `src/pages/VisitsPage.vue`

**Interfaces:**
- Consumes: Task 1 的 `formatDisplayDate()`
- Produces: 所有已知列表、详情、通知、历史、评论、文件、审批和业务日期的统一可见格式

- [ ] **Step 1: 替换直接时间戳展示**

  在每个文件中导入 `formatDisplayDate`，仅包裹显示表达式。保留原始值用于 `key`、排序、逾期判断和 API 调用。

- [ ] **Step 2: 移除局部时分格式化**

  删除联系人文件的 `formatTime()` 和 Demo 评论的 `slice(0, 16).replace('T', ' ')`，改用统一函数。Document Center 的静态 `YYYY-MM-DD HH:mm` 示例也通过统一函数显示。

- [ ] **Step 3: 统一 Dashboard 日期节点**

  将 Dashboard 中拆分显示月日/年份的时间节点改为单个 `formatDisplayDate(item.date)`；保留逾期状态计算，但不再以相对时间代替日期。

- [ ] **Step 4: 运行源码审计**

  使用 `rg` 搜索模板中直接展示 `createdAt`、`updatedAt`、`uploadedAt`、`submittedAt`、历史 `.at` 以及 `slice(0, 16)`；逐项确认仅内部键或已格式化显示保留。

### Task 3: Opportunity 八列看板

**Files:**
- Modify: `src/features/opportunities/OpportunityListView.vue`
- Modify: `src/pages/leads-opportunities.test.ts`

**Interfaces:**
- Consumes: 现有 `OPPORTUNITY_STAGES` 八阶段顺序
- Produces: `repeat(8, minmax(210px, 1fr))` 单行网格，最小宽度 `1690px`

- [ ] **Step 1: 修正看板 CSS**

  将七列网格改为八列，将容器最小宽度从 `1540px` 调整为 `1690px`；保留外层 `overflow-x:auto`。

- [ ] **Step 2: 增加看板顺序断言**

  在现有 Leads/Opportunities 页面测试中断言八个阶段全部渲染，`Lost` 是最后一个 `data-opportunity-stage`，源码或计算样式使用八列。

### Task 4: 验证与本地部署

**Files:**
- Generated: `backend/apps/rayher_crm/rayher_crm/public/crm/**`
- Generated: `backend/build/rayher_crm.zip`

- [ ] **Step 1: 运行聚焦测试**

  Run: `pnpm.cmd test src/domain/time.test.ts src/pages/leads-opportunities.test.ts src/pages/opportunity-strategy-operations.test.ts src/features/demo-requests/DemoRequestForm.test.ts src/pages/DocumentCenterPage.test.ts`

  Expected: 目标测试全部通过。

- [ ] **Step 2: 运行 Frappe 构建和受控打包**

  Run: `pnpm.cmd run build:frappe`

  Run: `powershell -ExecutionPolicy Bypass -File backend/scripts/prepare-app-build-context.ps1`

  Expected: TypeScript、Vite 和 ZIP 逐项完整性复验通过。

- [ ] **Step 3: 重建并刷新应用服务**

  Run: `docker compose -p rayher-crm-stage1-local -f backend/compose.yaml build frontend`

  Run: `docker compose -p rayher-crm-stage1-local -f backend/compose.yaml up -d --no-deps --force-recreate backend websocket frontend`

  Expected: 不触发已知 Aconca PPTX 迁移钩子，不停止数据库/Redis/ClamAV，不删除 volumes。

- [ ] **Step 4: 最终验证**

  重新运行聚焦测试，检查宿主机与容器静态资源哈希一致、frontend/backend/db 健康、`/crm` HTTP 200。完整测试集单独报告范围外基线失败。
