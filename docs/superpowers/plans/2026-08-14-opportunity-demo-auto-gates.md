# Opportunity Demo Auto Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Demo Request、Demo Test 与 Opportunity 组成不可手工越过的自动状态机，并把阶段回退限制为 Manager 专用动作；完成后审查并修复新增链路及全项目前端 P0/P1。

**Architecture:** Opportunity 仍是阶段真源，但两个中间门禁只接受后端业务事件推进。Demo Request 保存强制 Opportunity 外键；Request Manager Approval 和 Evaluation Accepted 在原事务中调用内部阶段函数。普通 Opportunity 更新不接受自动门禁转换；回退使用独立 Manager-only API。Opportunity 不新增 Demo 链路展示组件。

**Tech Stack:** Frappe/Python/MariaDB、Vue 3/TypeScript、Pinia、Vitest、Docker Compose Bench tests。

## Global Constraints

- 使用当前 `codex/crm-consolidated-update` 工作区，不覆盖或清理既有未提交改动。
- 所有行为变更严格执行 Red → Green → Refactor；每个测试必须先因缺失行为稳定失败。
- 不处理需要主动伪造 Frappe 通用 REST 请求的鉴权绕过。
- 不在 Opportunity 页面新增 Demo Request/Test 展示板块。
- 所有写入后检查 TipRay 文件头、NUL 字节和 UTF-8 可读性。

---

### Task 1: 后端自动门禁和强制关联

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_demo_request_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_evaluation_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_opportunity_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/opportunities.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/demo_requests.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/evaluations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_demo_request/crm_demo_request.json`

**Interfaces:**
- Produces: `advance_opportunity_for_demo_event(opportunity_id, event)`，其中事件为 `request_created`、`request_approved`、`evaluation_accepted`。
- Invariant: Request 创建只允许 Opportunity 处于 `需求发现`/`技术确认`；成功后至少为 `技术确认`。
- Invariant: Request Converted 只把 `技术确认` 推到 `Demo验证`；Evaluation Accepted 只把 `Demo验证` 推到 `预算审批`。

- [ ] **Step 1: 写 Request 强关联和创建自动推进失败测试**

  在 `test_demo_request_api.py` 增加：缺少 `opportunityId` 返回 `VALIDATION_ERROR`；跨 Account 返回 `LINK_MISMATCH`；从 `需求发现` 创建后 DB 阶段为 `技术确认` 且历史只新增一次；在故障注入点失败时 Request、历史和阶段全部回滚。

- [ ] **Step 2: 运行 Request 测试确认 RED**

  Run: `docker compose --env-file backend/test.env.example -f backend/compose.yaml exec -T backend bench --site rayher-crm.test run-tests --app rayher_crm --module rayher_crm.tests.test_demo_request_api`

  Expected: 新增断言因 `opportunityId` 仍可缺失或 Opportunity 仍停留在 `需求发现` 而失败。

- [ ] **Step 3: 最小实现 Request 关联和事务推进**

  `_validate_opportunity` 对空值抛 `CrmApiException("VALIDATION_ERROR", ..., field_errors={"opportunityId": "Required"})`；在 Request 创建 savepoint 内锁定并复核 Opportunity 的 Account/阶段、插入 Request/History、调用内部事件函数；异常回滚。

- [ ] **Step 4: 运行 Request 模块确认 GREEN**

  Run: 同 Step 2；Expected: 该模块 0 failure/error。

- [ ] **Step 5: 写 Request Approved 和 Evaluation Accepted 自动推进失败测试**

  断言 Manager Approval 成功后 Opportunity 为 `Demo验证`；审批故障注入后仍为 `技术确认`；Evaluation 到 `Accepted` 后为 `预算审批`；Rejected 不推进；重复终态不重复写阶段历史；异常落后阶段返回 409/`VERSION_CONFLICT` 或稳定业务冲突且整笔不写。

- [ ] **Step 6: 运行两个模块确认 RED**

  Run: Demo Request 与 Evaluation 两个模块；Expected: 自动推进断言失败。

- [ ] **Step 7: 在现有 savepoint 内接入两个事件**

  Manager Approval 创建 Evaluation 后、保存 Request 前推进到 `Demo验证`；Evaluation 将状态保存为 `Accepted` 的同一 try/savepoint 内推进到 `预算审批`。自动函数只能按事件映射前进，不接受客户端目标阶段，不回退后续阶段，不修改 `Lost`。

- [ ] **Step 8: 运行三个后端模块确认 GREEN**

  Run: Opportunity、Demo Request、Evaluation 模块；Expected: 0 failure/error。

### Task 2: Manager-only 回退与普通更新封锁

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/roles.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/opportunities.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/opportunities.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_roles.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_opportunity_api.py`

**Interfaces:**
- Produces: `rollback_opportunity_stage(name, target_stage, reason, expected_modified)`。
- Produces endpoint: `rayher_crm.api.v1.opportunities.rollback_opportunity_stage`。
- Permission: capability `deal:rollback` 仅 Manager。

- [ ] **Step 1: 写权限和状态转换失败测试**

  普通 update 对 `需求发现→技术确认`、`技术确认→Demo验证`、`Demo验证→预算审批` 和任何后退均返回 `INVALID_TRANSITION`；预算审批之后仍只允许顺序前进；Sales/Engineer 回退返回 403；Manager 缺 reason、向前或同阶段返回 422；合法回退成功并写 `stageRollback` 历史，`to` 中包含目标阶段和原因；旧 expectedModified 返回 409。

- [ ] **Step 2: 运行 Opportunity/roles 测试确认 RED**

  Expected: 自动阶段仍可普通推进，且回退接口不存在。

- [ ] **Step 3: 实现 capability、服务和 endpoint**

  `deal:rollback` 加入 Manager 能力集合和前后端类型；普通 update 显式拒绝涉及前三个自动边；回退锁内重检、只允许更早阶段、保存阶段和重新计算概率，以 `field=stageRollback`、`from_value=旧阶段`、`to_value=<目标阶段> | <reason>` 记录历史。

- [ ] **Step 4: 运行 Opportunity/roles 测试确认 GREEN**

### Task 3: 前端/Mock 契约封堵

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/domain/permissions.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/features/demo-requests/DemoRequestModal.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.test.ts`
- Modify: `src/features/opportunities/OpportunityEditorModal.vue`
- Modify: `src/features/opportunities/OpportunityEditorModal.test.ts`
- Create: `src/features/opportunities/OpportunityRollbackModal.vue`
- Modify: `src/pages/OpportunityDetailPage.vue`
- Modify: `src/pages/opportunity-detail.test.ts`

**Interfaces:**
- `CreateDemoRequestInput.opportunityId: string`。
- `CrmApi.rollbackOpportunityStage(id, { targetStage, reason }, expectedModified)`。

- [ ] **Step 1: 写前端失败测试**

  Demo Request 新建表单没有 Opportunity 时不提交并显示字段错误；切换 Account 清空无效商机；payload 必含 Opportunity。Opportunity 编辑器不渲染阶段 select。三个自动阶段不渲染推进按钮。Manager 有回退按钮，Sales/Engineer 无；原因空白不能提交。Frappe adapter 路由和 Mock 的权限/状态行为一致。

- [ ] **Step 2: 运行相关 Vitest 确认 RED**

  Run: `pnpm vitest run src/features/demo-requests/DemoRequestForm.test.ts src/features/opportunities/OpportunityEditorModal.test.ts src/pages/opportunity-detail.test.ts src/api/frappe-adapter.test.ts src/api/mock-adapter.test.ts`

- [ ] **Step 3: 最小实现 UI 和 adapters**

  Demo Request 页面加载当前用户可见 Opportunities，并传入 Modal；Modal 按 Account 过滤 `需求发现`/`技术确认`，edit 时保留当前关联值。编辑器只读呈现阶段。详情页对前三阶段完全隐藏普通推进；Manager 回退使用独立 Modal/API，失败保持原数据并显示 Request ID。Mock 在 Request 创建/审批/Evaluation Accepted 时执行同一事件映射。

- [ ] **Step 4: 运行相关 Vitest 确认 GREEN**

### Task 4: 新增链路和全项目前端对抗性审查

**Files:**
- Update findings in: `docs/superpowers/plans/2026-08-13-crm-adversarial-review-remediation.md`
- Test/Fix: 仅修改经稳定复现的 P0/P1 所属页面、组件和测试。

- [ ] **Step 1: 建立路由×角色×数据边界矩阵**

  覆盖所有活动路由，重点检查无效 ID、21/201 条记录、快速切换、局部接口失败、Mutation 失败、权限按钮、空/加载/拒绝/错误互斥、跨模块 focus 精确性和新增 Demo 自动链。

- [ ] **Step 2: 对每个 P0/P1 写最小失败测试并记录根因**

  每条 finding 必须有用户可见复现、准确文件/数据流、严重度理由和能因修复回归而失败的测试；不以静态字符串断言代替行为测试。

- [ ] **Step 3: 逐条最小修复并运行邻近测试**

  不顺手重构，不处理 P2/P3，不处理通用 REST 攻击面。

- [ ] **Step 4: 更新统一执行文档状态**

  把新增链路与审查 finding 标为 `已修复/已验证/未复现`，附测试命令和证据，不写未经验证的完成声明。

### Task 5: 完整验证与完成审计

- [ ] **Step 1: TipRay 与 diff 审计**

  Run: 对全部改动文件检查 `%TSD-Header-`、NUL、UTF-8；运行 `git diff --check`；确认没有无关文件变更。

- [ ] **Step 2: 前端质量门**

  Run: `pnpm typecheck`、稳定配置下全量 `pnpm vitest run`、`pnpm build`。

- [ ] **Step 3: 后端质量门**

  Run: `backend/tests/run-backend-tests.ps1` 或等价 JUnit wrapper；确认任意 failure/error 使外层非零。

- [ ] **Step 4: 真实 `.test` HTTP 场景**

  用唯一 run ID 创建 Opportunity→Request→Evaluation→Accepted，断言三个阶段；分别验证 Manager/Sales/Engineer 回退权限；finally 精确清理并断言零残留。

- [ ] **Step 5: 浏览器验收**

  使用 Browser 插件检查 Demo Request 强制商机、自动阶段、无手工自动门禁按钮、Manager 回退、角色按钮隐藏、无相关 console error；桌面和移动视口各一次。

- [ ] **Step 6: 逐项对照目标和两个计划文档**

  对每项标记证据强度；只在全部显式要求均有当前证据时完成目标。
