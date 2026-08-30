# 第一版纯前端 Demo 实施计划

## 范围

- 继续使用现有 Vue 3 + TypeScript + Mock 数据，不接入 Frappe 后端。
- 交付七个业务入口：Executive Dashboard、Opportunity Strategy、Demo Request、Installed Tools、Service Calendar、Procedure Run、Document Center。
- 本轮只验证数据关系、状态流转、权限可见性和管理层分析；不实现智能排程、完整 DRM 或持久化。
- 当前目录不是有效 Git 仓库，不初始化仓库、不创建 worktree，也不执行提交。

## Task 1：用测试固定第一版 Demo 边界

**Files**
- Modify: `src/pages/seven-page-workspace.test.ts`
- Create: `src/demo/operations-rules.test.ts`

1. 断言导航和路由包含 Service Calendar、Procedure Run。
2. 断言 Service 页面包含人工排期、冲突和工单状态。
3. 断言 Procedure 页面包含阶段、强制检查项、附件证据、签字与回滚门禁。
4. 断言管理驾驶舱覆盖 Sales、Demo、Service、Upgrade、Document Compliance。
5. 先运行新增测试并确认失败。

## Task 2：实现 Service Calendar

**Files**
- Create: `src/pages/ServiceCalendarPage.vue`
- Create: `src/demo/operations-rules.ts`
- Modify: `src/demo/operations-data.ts`

1. 显示本周工程师排期、客户、设备、服务类型、优先级和状态。
2. 支持按工程师筛选、选中工单、人工重新分配和状态推进。
3. 自动标记同一工程师的时间冲突，保留人工决策。

## Task 3：实现 Procedure Run

**Files**
- Create: `src/pages/ProcedureRunPage.vue`
- Modify: `src/demo/operations-rules.ts`
- Modify: `src/demo/operations-data.ts`

1. 展示升级阶段、版本、设备、客户和执行窗口。
2. 展示强制检查项、执行人、证据附件和执行状态。
3. 未完成 Mandatory MOC / Backup / Qualification 时禁止进入后续阶段。
4. 展示客户签字和回滚准备区，状态仅保存在当前页面内存。

## Task 4：补齐权限、导航与驾驶舱

**Files**
- Modify: `src/types/crm.ts`
- Modify: `src/domain/permissions.ts`
- Modify: `src/app/navigation.ts`
- Modify: `src/app/router.ts`
- Modify: `src/pages/DashboardPage.vue`

1. 新增 service / procedure 的查看与执行能力。
2. 管理者可跨团队只读；FAE 可查看和执行分配给自己的操作；销售仅查看相关设备和服务摘要。
3. 驾驶舱增加 Service、Upgrade、Document Compliance 指标和管理关注项。

## Task 5：验证

1. 运行相关 Vitest 测试。
2. 运行完整测试、TypeScript 检查和生产构建。
3. 在 `http://127.0.0.1:4173/` 逐页检查七个入口、窄屏导航和关键交互。
