# 拜访管理角色权限实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在真实 Frappe 链路中实现拜访管理的独立角色权限：Manager 全量、Sales 仅本人、Engineer 无权限。

**Architecture:** 后端 capability、DocPerm 与 SQL 行级条件共同构成权限真源；前端 capability 只同步导航与直接路由行为。保持其他模块和 Mock 适配器不变。

**Tech Stack:** Python/Frappe、Vue 3/TypeScript、FrappeTestCase、Vitest

## Global Constraints

- 不修改 Mock 适配器及 Mock 数据。
- 不调整 Demo、Demo Test、Installed Tools 或其他 Engineer 权限。
- 不引入依赖或新的权限配置页面。
- 所有生产改动必须先有能稳定复现越权的失败测试。

---

### Task 1: 锁定后端拜访权限契约

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_visit_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_stage5g_schema.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_roles.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/roles.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/scope.py`

**Interfaces:**
- Consumes: `conditions_for_doctype("CRM Visit", user)`、`list_visits(query)`、`update_visit(...)`。
- Produces: Manager 全量、Sales 仅 `visit_owner`、Engineer 拒绝的后端契约。

- [ ] **Step 1: 写失败测试**

在角色测试中断言 Engineer capabilities 不包含 `visit:view`。在 Schema 测试中断言 Engineer 的 CRM Visit DocPerm 不可读，且查询条件为 `1=0`。在 Visit API 测试中，在同一客户下直接插入另一位 Sales 负责的拜访，并断言当前 Sales 的 `list_visits({})` 不返回它、`update_visit(...)` 返回 `SCOPE_DENIED`。

- [ ] **Step 2: 运行后端定向测试并确认 RED**

Run:

```powershell
docker compose exec backend bench --site frontend run-tests --app rayher_crm --module rayher_crm.tests.test_roles
docker compose exec backend bench --site frontend run-tests --app rayher_crm --module rayher_crm.tests.test_stage5g_schema
docker compose exec backend bench --site frontend run-tests --app rayher_crm --module rayher_crm.tests.test_visit_api
```

Expected: Engineer capability/DocPerm 断言失败，同客户异 owner 的拜访错误地出现在列表或可被更新。

- [ ] **Step 3: 实现最小后端修复**

从 `ROLE_CAPABILITIES["Engineer"]` 移除 `visit:view`；将 `VISIT_DOCPERMS["CRM Engineer"]` 设为空权限集合；将 CRM Visit 的 Sales SQL 条件改为只比较 `visit_owner`，Engineer 条件改为 `1=0`。不改其他 DocType 分支。

- [ ] **Step 4: 运行后端定向测试并确认 GREEN**

重新运行 Step 2 的三个模块，预期全部通过。

### Task 2: 同步真实前端权限契约

**Files:**
- Modify: `src/domain/permissions.test.ts`
- Modify: `src/domain/permissions.ts`

**Interfaces:**
- Consumes: `ROLE_PROFILES.Engineer.capabilities`、现有 AppShell capability 导航过滤与路由重定向。
- Produces: Engineer 前端身份不再声明 `visit:view`，无需新增页面级判断。

- [ ] **Step 1: 写失败测试**

在 `src/domain/permissions.test.ts` 断言 Engineer capabilities 不包含 `visit:view`，同时保留其现有 Demo、Evaluation、Installed Tool 能力断言。

- [ ] **Step 2: 运行前端权限测试并确认 RED**

Run:

```powershell
npm.cmd test -- src/domain/permissions.test.ts
```

Expected: FAIL，因为 Engineer 当前仍包含 `visit:view`。

- [ ] **Step 3: 实现最小前端修复**

只从 `ENGINEERING_CAPABILITIES` 移除 `visit:view`。导航组已有 `hiddenRoles: ['Engineer']`，AppShell 已按可见导航重定向，因此不新增路由代码。

- [ ] **Step 4: 运行前端权限与导航测试并确认 GREEN**

Run:

```powershell
npm.cmd test -- src/domain/permissions.test.ts src/app/AppShell.test.ts
```

Expected: PASS。

### Task 3: 回归验证

**Files:**
- Verify: 上述生产文件与测试文件。

**Interfaces:**
- Consumes: 完成后的后端和前端权限契约。
- Produces: 可交付的拜访角色隔离证据。

- [ ] **Step 1: 运行相关前端测试**

Run:

```powershell
npm.cmd test -- src/domain/permissions.test.ts src/app/AppShell.test.ts src/pages/customer-operations.test.ts
```

Expected: PASS。

- [ ] **Step 2: 运行相关后端测试**

Run Task 1 的三个 Frappe 测试模块，Expected: PASS。

- [ ] **Step 3: 静态检查改动**

Run:

```powershell
git diff --check
git diff -- backend/apps/rayher_crm/rayher_crm/permissions/roles.py backend/apps/rayher_crm/rayher_crm/permissions/scope.py backend/apps/rayher_crm/rayher_crm/tests/test_roles.py backend/apps/rayher_crm/rayher_crm/tests/test_stage5g_schema.py backend/apps/rayher_crm/rayher_crm/tests/test_visit_api.py src/domain/permissions.ts src/domain/permissions.test.ts
```

Expected: 无空白错误，且没有 Mock 或其他模块改动。
