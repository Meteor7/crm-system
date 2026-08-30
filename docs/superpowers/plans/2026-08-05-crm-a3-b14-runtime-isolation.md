# CRM A3/B14 Runtime Isolation Implementation Plan

> **执行规则：** 严格 RED → GREEN → REFACTOR；每个生产改动之前必须先观察对应测试因缺少行为而失败。

**目标：** Frappe 构建使用数据库人员目录与服务器通知，彻底隔离静态 Demo 人员和通知；Mock 行为不变。

**技术方向：** 扩展 bootstrap DTO/endpoint；用 Vite exact alias 提供同形 reactive personnel runtime；App Store 按 notification delivery 初始化通知；AppShell 通过 App Store 执行 server-backed read mutations。

---

## Task 1：后端 bootstrap 人员目录

**文件：**
- 修改：`backend/apps/rayher_crm/rayher_crm/tests/test_api_foundation.py`
- 修改：`backend/apps/rayher_crm/rayher_crm/api/v1/bootstrap.py`
- 可能修改：`backend/apps/rayher_crm/rayher_crm/permissions/roles.py`

1. 写测试：enabled System User + 单 CRM role 被返回；disabled、Website User、无角色、多角色、Guest、Administrator 不返回。
2. 在当前 Docker App test 中运行该测试，确认因 `personnel` 缺失而 RED。
3. 实现最小查询/序列化，复用角色常量与 display/initials helper。
4. 重跑聚焦测试至 GREEN。

## Task 2：Frappe reactive personnel runtime

**文件：**
- 新增：`src/demo/personnel.frappe.ts`
- 新增：`src/demo/personnel.frappe.test.ts`
- 修改：`src/demo/personnel.ts`
- 修改：`src/types/crm.ts`
- 修改：`vite.config.ts`

1. 写直接模块测试：初始为空；replace 后显示名、角色过滤与 preferred ID 正确；未知 ID 原样显示。
2. 运行聚焦 Vitest，确认模块不存在/行为缺失而 RED。
3. 实现同形 reactive API；Mock 模块增加 no-op bootstrap initializer；DTO 增加 personnel。
4. 增加 exact alias，运行聚焦测试至 GREEN。

## Task 3：服务器通知初始化与已读写回

**文件：**
- 修改：`src/stores/app.test.ts`
- 修改：`src/stores/notifications.test.ts`
- 修改：`src/app/AppShell.test.ts` 或新增聚焦 Frappe 测试
- 修改：`src/stores/app.ts`
- 修改：`src/stores/notifications.ts`
- 修改：`src/app/AppShell.vue`

1. 写测试：server delivery 初始无 seed、bootstrap 后替换为服务器通知；单条/全部已读先调 API，失败保持未读。
2. 运行聚焦测试并确认 RED 原因分别为 seed 泄漏、未拉服务器、未写服务器。
3. 实现最小 Store replace/error action 与 AppShell await 调用。
4. 重跑聚焦测试至 GREEN，随后重跑现有 Mock notification tests。

## Task 4：构建泄漏 Guard

**文件：**
- 新增或修改：Frappe bundle guard 测试/脚本
- 修改：`vite.config.ts`（仅在 Guard 证明需要时）

1. 先写/扩展 Guard，断言 Frappe build 不含 `person002@crm.example.invalid`、`Demo Staff 01`、`requirement-req-006`。
2. 在未完成 alias 前运行并确认 RED。
3. 完成 alias/tree-shaking 最小调整，重新 build 并确认 Guard GREEN。

## Task 5：回归与审计

1. 运行 A3/B14 前端聚焦测试。
2. 运行 Frappe 后端聚焦测试，再运行完整 App tests。
3. 运行 `npm.cmd test -- --run`、`npm.cmd run typecheck`、默认 Mock build、Frappe build。
4. 检查 bundle 静态人员/通知 seed 泄漏。
5. 检查新 Docker 栈健康；不停止/删除任何 volume。
6. 更新 A1–B14 矩阵、权威 Gate（仅证据充分时）、持续审计日志与桌面副本。

## 停止条件

- 需要创建真实业务 User 或改变权限业务规则。
- 后端目录暴露超出已批准字段。
- 需要破坏性数据库、Git 或 Docker 操作。
- 现有 dirty worktree 与本批次目标文件发生无法安全区分的冲突。
