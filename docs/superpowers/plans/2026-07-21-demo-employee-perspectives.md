# Demo Employee Perspectives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在纯前端 Mock Demo 中增加五种员工身份切换，并立即应用对应导航、数据范围与页面权限。

**Architecture:** 使用单一 Demo identity catalog 定义员工和 Mock API 参数。App Store 持有当前活动 API 与 Bootstrap；AppShell 负责身份菜单、导航过滤和越权路由跳转，RouterView 通过 identity revision 重新挂载页面。

**Tech Stack:** Vue 3、Pinia、Vue Router、TypeScript、Vitest、Vue Test Utils

## Global Constraints

- 不创建真实账号，不接入 Frappe 登录、后端权限或数据库。
- 身份只保存在当前页面内存，刷新后恢复 CRM Administrator。
- 不使用 localStorage、Cookie 或新增依赖。
- 当前目录不是有效 Git 仓库；不初始化仓库，跳过所有提交步骤。

---

### Task 1: Demo Identity Catalog

**Files:**
- Create: `src/demo/identities.ts`
- Test: `src/demo/identities.test.ts`

**Interfaces:**
- Produces: `DemoIdentity`, `DEMO_IDENTITIES`, `getDemoIdentity(id)`

- [ ] **Step 1: Write the failing catalog test**

断言五个身份 ID 唯一，并且角色依次覆盖 CRM Administrator、Management Viewer、Sales Manager、Sales User、FAE / Applied Engineer。

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/demo/identities.test.ts --maxWorkers=1`
Expected: FAIL because `src/demo/identities.ts` does not exist.

- [ ] **Step 3: Implement the catalog**

每个身份提供 `id`、`name`、`initials`、`role`、`team`、`teamOwners`、`assignedAccountIds`，供 Mock API 和界面共同使用。

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/demo/identities.test.ts --maxWorkers=1`
Expected: PASS.

### Task 2: Store-owned Demo Session

**Files:**
- Modify: `src/stores/app.ts`
- Test: `src/stores/app.test.ts`

**Interfaces:**
- Consumes: `getDemoIdentity(id)`
- Produces: `activeApi: CrmApi`, `identityId: string`, `identityRevision: number`, `switchDemoIdentity(id): Promise<void>`

- [ ] **Step 1: Write failing store tests**

断言切换为 `sales-user` 后 Bootstrap 角色为 Sales User、用户名为 Demo Staff 01、revision 增加；切换失败时保留原身份。

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/stores/app.test.ts --maxWorkers=1`
Expected: FAIL because `switchDemoIdentity` is absent.

- [ ] **Step 3: Implement active Mock API switching**

`switchDemoIdentity()` 根据 catalog 创建 `createMockApi({ role, userName, teamOwners, assignedAccountIds })`，成功读取 Bootstrap 后原子替换 active API 与身份状态。

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/stores/app.test.ts --maxWorkers=1`
Expected: PASS.

### Task 3: AppShell Identity Switcher and Route Guard

**Files:**
- Modify: `src/app/AppShell.vue`
- Modify: `src/app/AppShell.test.ts`

**Interfaces:**
- Consumes: `DEMO_IDENTITIES`, `app.switchDemoIdentity(id)`, `app.identityRevision`
- Produces: `data-testid="identity-switcher"`, `data-identity-id`, automatic redirect to first visible navigation item

- [ ] **Step 1: Write failing interaction tests**

断言管理员可打开五项身份菜单；切换 FAE 后管理驾驶舱消失、Service Calendar 和 Procedure Run 保留，并从 `/dashboard` 自动跳到第一个允许页面；切换 Sales User 后 Procedure Run 不显示。

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/app/AppShell.test.ts --maxWorkers=1`
Expected: FAIL because identity switcher does not exist.

- [ ] **Step 3: Implement switcher and redirect**

仅在 Mock 模式启用员工按钮和菜单。切换后用 visible navigation 判断当前 path；无权时 `router.replace(firstVisible.path)`。RouterView 使用 `:key="app.identityRevision"` 强制重新读取角色范围数据。

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/app/AppShell.test.ts --maxWorkers=1`
Expected: PASS.

### Task 4: Page API Source and Verification

**Files:**
- Modify: `src/app/AppShell.vue`
- Modify only if required: pages that bypass the injected/current API

**Interfaces:**
- Consumes: `app.activeApi`
- Produces: role-scoped page remounts without backend calls

- [ ] **Step 1: Add a failing Sales User scope assertion**

挂载 Accounts 页面时使用切换后的 `app.activeApi`，断言仅展示 Demo Staff 01 负责的客户。

- [ ] **Step 2: Implement active API propagation**

通过 RouterView slot 向页面传入 `apiClient="app.activeApi"`，保持未声明该 prop 的页面兼容。

- [ ] **Step 3: Run focused verification**

Run: `pnpm test src/app/AppShell.test.ts src/stores/app.test.ts src/demo/identities.test.ts --maxWorkers=1`
Expected: all pass.

- [ ] **Step 4: Run full verification**

Run: `pnpm test --maxWorkers=1`
Expected: all tests pass.

Run: `pnpm build`
Expected: exit 0.

- [ ] **Step 5: Browser acceptance**

在 `http://127.0.0.1:4173/` 切换 Management Viewer、Sales User 和 FAE，验证导航、自动跳转、员工名称和 Mock 数据范围。
