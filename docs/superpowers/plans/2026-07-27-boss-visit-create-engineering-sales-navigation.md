# Boss Visit Creation and Engineering Sales Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Boss create planned visits without granting broader visit writes, and hide the Sales navigation group from FAE and Equipment Engineer identities.

**Architecture:** Introduce a dedicated `visit:create` capability and use it at both the Visits page and Mock API boundary while leaving `visit:write` and `visit:review` unchanged. Add group-level hidden roles to the navigation model and make both sidebar rendering and identity-switch redirects consume the same visible group list.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, Vue Test Utils

## Global Constraints

- Boss receives only `visit:create`, not `visit:write` or `visit:review`.
- FAE and Equipment Engineer keep their existing read capabilities; only the Sales navigation group is hidden.
- Do not implement Frappe Visit writes.
- Do not change unrelated role, Demo, customer, or dashboard behavior.

---

### Task 1: Add the dedicated visit creation capability

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/domain/permissions.ts`
- Test: `src/domain/permissions.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Test: `src/api/mock-adapter.test.ts`
- Modify: `src/pages/VisitsPage.vue`
- Test: `src/pages/customer-operations.test.ts`

**Interfaces:**
- Produces: `Capability` value `visit:create`.
- Consumes: `app.can('visit:create')` in `VisitsPage.vue`.
- Consumes: `assertCapability(capabilities, 'visit:create')` in `createMockApi().createVisit`.

- [ ] **Step 1: Write failing permission, API, and page tests**

Add assertions proving that Management Viewer has only visit creation:

```ts
expect(ROLE_PROFILES['Management Viewer'].capabilities).toContain('visit:create')
expect(ROLE_PROFILES['Management Viewer'].capabilities).not.toContain('visit:write')
expect(ROLE_PROFILES['Management Viewer'].capabilities).not.toContain('visit:review')
```

Change the Mock API test to create a real Boss visit and still reject an update:

```ts
const management = createMockApi({ latency: 0, role: 'Management Viewer', userName: '演示经理01' })
await expect(management.createVisit({
  accountId: 'ACC-001',
  subject: 'Boss 客户沟通',
  date: '2026-07-21',
  type: 'Phone',
  owner: 'Demo Staff 01',
  objective: '确认客户决策时间',
})).resolves.toMatchObject({ data: { status: 'Planned', subject: 'Boss 客户沟通' } })
await expect(management.updateVisit('V-001', { type: 'complete_action' }))
  .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
```

Update the management page test to assert the create button exists while existing visit action buttons remain absent.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pnpm.cmd test src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/pages/customer-operations.test.ts
```

Expected: FAIL because `visit:create` does not exist, Boss create is denied, and the page hides the create button.

- [ ] **Step 3: Implement the minimal capability split**

- Add `visit:create` to `Capability`.
- Add it to administrator, management, sales manager, and sales user capabilities.
- Make `createVisit` require `visit:create`.
- Add `canCreate` to `VisitsPage.vue` and use it only for the “新建拜访” button.
- Leave all existing visit mutation buttons controlled by `canWrite` or `canReview`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
pnpm.cmd test src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/pages/customer-operations.test.ts
```

Expected: all focused tests pass.

---

### Task 2: Hide Sales navigation from engineering identities

**Files:**
- Modify: `src/app/navigation.ts`
- Modify: `src/app/AppShell.vue`
- Test: `src/app/AppShell.test.ts`

**Interfaces:**
- Produces: `NavigationGroup.hiddenRoles?: UserRole[]`.
- Consumes: the authenticated role in `visibleNavigation`.

- [ ] **Step 1: Write the failing AppShell test**

Update the equipment identity-switch test:

```ts
expect(wrapper.text()).not.toContain('Sales 模块')
expect(wrapper.find('[data-route="accounts"]').exists()).toBe(false)
expect(wrapper.find('[data-route="opportunities-booking"]').exists()).toBe(false)
expect(wrapper.find('[data-route="visits"]').exists()).toBe(false)
expect(wrapper.find('[data-route="demo-workflow"]').exists()).toBe(true)
```

Add equivalent assertions for the FAE identity.

- [ ] **Step 2: Run the AppShell test and verify RED**

Run:

```powershell
pnpm.cmd test src/app/AppShell.test.ts
```

Expected: FAIL because both engineering identities still render Sales navigation entries.

- [ ] **Step 3: Implement group-level role hiding**

- Add `hiddenRoles?: UserRole[]` to `NavigationGroup`.
- Set the Sales group hidden roles to `FAE / Applied Engineer` and `Equipment Engineer`.
- Filter hidden groups before filtering items by capabilities.
- Reuse `visibleNavigation` when calculating identity-switch redirect paths.

- [ ] **Step 4: Run focused and static verification**

Run:

```powershell
pnpm.cmd test src/app/AppShell.test.ts src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/pages/customer-operations.test.ts
pnpm.cmd run typecheck
pnpm.cmd run build
```

Expected: focused tests, typecheck, and build all pass.

- [ ] **Step 5: Verify the current preview**

At `http://localhost:4173/`:

- Switch to 演示经理01, open “拜访与 Action”, create a planned visit, and confirm no edit/action buttons are available.
- Switch to FAE and Equipment Engineer separately and confirm “Sales 模块” is absent while “Demo 与验证” remains.
- Confirm the browser console has no errors.
