# CRM Three-Role Personnel Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the Mock Demo permission model to Manager, Sales, and Engineer, make one personnel directory authoritative, replace free-text owner assignment with role-filtered selects, and verify cross-module synchronization.

**Architecture:** `src/demo/personnel.ts` owns personnel identities, role membership, assignment metadata, option filtering, and owner validation. `src/domain/permissions.ts` owns the three capability profiles while `src/api/mock-adapter.ts` enforces both capability and row scope at the write boundary. Vue forms consume the same personnel helpers so UI options and API validation cannot drift.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, Vue Test Utils, Mock adapter, browser localStorage, IndexedDB.

## Global Constraints

- Frontend Mock Demo only; do not connect Frappe or a production database.
- Preserve current DTO owner fields as person names for compatibility.
- Do not delete existing business data or reset unrelated local settings.
- Keep the current dirty worktree intact; do not commit, stage, push, or reformat unrelated files.
- Write failing tests before each production behavior change.

---

### Task 1: Authoritative personnel and three-role contracts

**Files:**
- Create: `src/demo/personnel.ts`
- Create: `src/demo/personnel.test.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/demo/identities.ts`
- Modify: `src/demo/identities.test.ts`
- Modify: `src/domain/permissions.ts`
- Modify: `src/domain/permissions.test.ts`

**Interfaces:**
- Produces: `UserRole = 'Manager' | 'Sales' | 'Engineer'`
- Produces: `PERSONNEL`, `personnelForRole(role)`, `personnelForRoles(roles)`, `isPersonnelName(value)`, `assertPersonnelRole(value, roles)`
- Produces: `DEMO_IDENTITIES` as a compatibility export backed by `PERSONNEL`
- Produces: `ROLE_PROFILES` with Manager/all, Sales/own, Engineer/assigned scopes

- [ ] **Step 1: Write failing personnel and permission tests**

```ts
expect(PERSONNEL.map((person) => [person.name, person.role])).toEqual([
  ['演示员工24', 'Manager'], ['演示经理01', 'Manager'], ['Demo Staff 06', 'Manager'],
  ['Demo Staff 01', 'Sales'], ['Demo Staff 02', 'Sales'],
  ['演示员工14', 'Engineer'], ['演示员工15', 'Engineer'],
])
expect(new Set(PERSONNEL.map((person) => person.name)).size).toBe(PERSONNEL.length)
expect(Object.keys(ROLE_PROFILES)).toEqual(['Manager', 'Sales', 'Engineer'])
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `pnpm.cmd test src/demo/personnel.test.ts src/demo/identities.test.ts src/domain/permissions.test.ts`

Expected: fail because `PERSONNEL` and three-role `UserRole` do not exist.

- [ ] **Step 3: Implement the personnel directory and role profiles**

```ts
export interface PersonnelIdentity {
  id: string
  name: string
  initials: string
  role: UserRole
  team: string
  teamOwners: string[]
  assignedAccountIds: string[]
}

export const PERSONNEL: PersonnelIdentity[] = [
  { id: 'administrator', name: '演示员工24', initials: '林', role: 'Manager', team: 'CRM Operations', teamOwners: ['Demo Staff 01', 'Demo Staff 02'], assignedAccountIds: [] },
  { id: 'management', name: '演示经理01', initials: '赵', role: 'Manager', team: '管理层', teamOwners: ['Demo Staff 01', 'Demo Staff 02'], assignedAccountIds: [] },
  { id: 'sales-manager', name: 'Demo Staff 06', initials: 'GL', role: 'Manager', team: '大中华区销售', teamOwners: ['Demo Staff 01', 'Demo Staff 02'], assignedAccountIds: [] },
  { id: 'sales-user', name: 'Demo Staff 01', initials: 'AC', role: 'Sales', team: '华东销售', teamOwners: ['Demo Staff 01'], assignedAccountIds: [] },
  { id: 'sales-bella', name: 'Demo Staff 02', initials: 'BW', role: 'Sales', team: '华东销售', teamOwners: ['Demo Staff 02'], assignedAccountIds: [] },
  { id: 'fae', name: '演示员工14', initials: '周', role: 'Engineer', team: '应用工程', teamOwners: [], assignedAccountIds: ['ACC-001', 'ACC-003', 'ACC-006'] },
  { id: 'equipment-engineer', name: '演示员工15', initials: '孙', role: 'Engineer', team: '设备验证工程', teamOwners: [], assignedAccountIds: ['ACC-001', 'ACC-005', 'ACC-006'] },
]
```

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `pnpm.cmd test src/demo/personnel.test.ts src/demo/identities.test.ts src/domain/permissions.test.ts`

Expected: all tests pass.

---

### Task 2: Mock API scope and owner validation

**Files:**
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/notifying-api.test.ts`
- Modify: `src/app/AppShell.vue`
- Modify: `src/app/AppShell.test.ts`
- Modify: `src/app/navigation.ts`
- Modify: role-specific page tests that no longer compile after the role union change

**Interfaces:**
- Consumes: `PersonnelIdentity`, `assertPersonnelRole`, and three `ROLE_PROFILES`
- Produces: `createMockApi({ role, userName, teamOwners, assignedAccountIds })` with Manager/all, Sales/own, Engineer/assigned behavior
- Produces: owner validation errors with code `INVALID_OWNER`

- [ ] **Step 1: Write failing API contract tests**

```ts
await expect(manager.listAccounts({})).resolves.toMatchObject({ data: { items: expect.any(Array) } })
expect((await sales.listAccounts({})).data.items.every((item) => item.owner === 'Demo Staff 01')).toBe(true)
expect((await engineer.listAccounts({})).data.items.every((item) => ['ACC-001', 'ACC-003'].includes(item.id))).toBe(true)
await expect(sales.createAccount({ ...input, owner: '演示员工14' })).rejects.toMatchObject({ code: 'INVALID_OWNER' })
await expect(engineer.transitionDemoRequest(id, { type: 'engineer_approve', engineerOwner: 'Demo Staff 01', ...review })).rejects.toMatchObject({ code: 'INVALID_OWNER' })
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `pnpm.cmd test src/api/mock-adapter.test.ts src/api/notifying-api.test.ts src/app/AppShell.test.ts`

Expected: fail on old role names and missing write-boundary owner validation.

- [ ] **Step 3: Replace legacy role branches and validate every mutable owner field**

Apply the role predicates:

```ts
const isManager = role === 'Manager'
const isSales = role === 'Sales'
const isEngineer = role === 'Engineer'
```

Before writes, validate customer/sales fields against `Sales`, engineering fields against `Engineer`, and action-owner fields against `['Sales', 'Engineer']`. Validate account scope independently of UI controls.

- [ ] **Step 4: Update identity switching and navigation role checks**

The identity menu must list all seven people, show their three category labels, recreate the API on switch, and refresh requirement notifications from the new identity API.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `pnpm.cmd test src/api/mock-adapter.test.ts src/api/notifying-api.test.ts src/app/AppShell.test.ts src/stores/app.test.ts`

Expected: all focused tests pass.

---

### Task 3: Shared personnel select and owner assignment forms

**Files:**
- Create: `src/design-system/PersonnelSelect.vue`
- Create: `src/design-system/PersonnelSelect.test.ts`
- Modify: `src/pages/AccountsPage.vue`
- Modify: `src/pages/AccountDetailPage.vue`
- Modify: `src/features/contacts/ContactModal.vue`
- Modify: `src/features/leads/LeadEditorModal.vue`
- Modify: `src/features/leads/LeadConvertModal.vue`
- Modify: `src/features/opportunities/OpportunityEditorModal.vue`
- Modify: `src/features/opportunities/BookingEditorModal.vue`
- Modify: `src/features/opportunities/ActionEditorModal.vue`
- Modify: `src/features/visits/VisitModal.vue`
- Modify: existing Installed Tool and Demo Request owner selects to consume the shared directory
- Modify: corresponding component/page tests

**Interfaces:**
- Consumes: `personnelForRole(role)` and `personnelForRoles(roles)`
- Produces: `<PersonnelSelect v-model roles label aria-label disabled required />`
- Emits: `update:modelValue` with an exact personnel name

- [ ] **Step 1: Write failing component and form tests**

```ts
expect(wrapper.find('input[aria-label="客户负责人"]').exists()).toBe(false)
expect(wrapper.get('select[aria-label="客户负责人"]').text()).toContain('Demo Staff 01')
expect(wrapper.get('select[aria-label="客户负责人"]').text()).toContain('Demo Staff 02')
expect(wrapper.get('select[aria-label="客户负责人"]').text()).not.toContain('演示员工14')
```

Add equivalent assertions for contacts, leads, conversion account/contact/opportunity owner, bookings, opportunities, actions, visit owner, visit action owner, Demo engineer, and Installed Tool engineer.

- [ ] **Step 2: Run the form tests and confirm RED**

Run: `pnpm.cmd test src/design-system/PersonnelSelect.test.ts src/features/visits/VisitModal.test.ts src/pages/customer-operations.test.ts src/pages/leads.test.ts src/pages/booking.test.ts`

Expected: fail because owner fields are still text inputs or the shared component is absent.

- [ ] **Step 3: Implement `PersonnelSelect`**

```vue
<select :value="modelValue" :aria-label="ariaLabel" @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
  <option value="" disabled>{{ placeholder }}</option>
  <option v-for="person in options" :key="person.id" :value="person.name">
    {{ person.name }} · {{ person.role }}
  </option>
</select>
```

If an existing value is outside the directory, render a disabled `历史未映射` option so the record remains readable but cannot be re-saved without a valid selection.

- [ ] **Step 4: Replace every mutable free-text owner field**

Use `roles="Sales"` for sales-owned records, `roles="Engineer"` for engineering records, and `:roles="['Sales', 'Engineer']"` for visit follow-up actions. Keep filters unchanged because they derive from stored data rather than assign new owners.

- [ ] **Step 5: Run form tests and confirm GREEN**

Run: `pnpm.cmd test src/design-system/PersonnelSelect.test.ts src/features/visits/VisitModal.test.ts src/pages/customer-operations.test.ts src/pages/leads.test.ts src/pages/booking.test.ts src/features/create-form-required-markers.test.ts`

Expected: all focused tests pass.

---

### Task 4: Cross-module synchronization regression and adversarial review

**Files:**
- Create: `src/domain/personnel-sync.test.ts`
- Modify only defects proven by failing tests in files already in scope

**Interfaces:**
- Consumes: public `CrmApi` methods and existing repositories
- Produces: regression evidence for role switch, foreign-key visibility, owner mutation, and notification refresh

- [ ] **Step 1: Write end-to-end Mock synchronization tests**

Cover `Lead -> Account -> Contact -> Opportunity -> Booking`, `Demo Request -> Evaluation -> Installed Tool`, identity switching, and list/detail/Dashboard/notification refresh. Assert both foreign keys and owner visibility.

- [ ] **Step 2: Run synchronization tests and confirm RED for every discovered defect**

Run: `pnpm.cmd test src/domain/personnel-sync.test.ts src/pages/delivery-workflow.test.ts src/pages/permission-revocation.test.ts`

Expected: any failure must name the mismatched record, owner, or scope; do not weaken assertions to accommodate stale behavior.

- [ ] **Step 3: Apply only test-proven synchronization repairs**

Repair the smallest shared data boundary responsible for each failure. Do not add Frappe code and do not reset browser data unrelated to the affected record.

- [ ] **Step 4: Re-run synchronization and permission suites**

Run: `pnpm.cmd test src/domain/personnel-sync.test.ts src/pages/delivery-workflow.test.ts src/pages/permission-revocation.test.ts src/pages/seven-page-workspace.test.ts`

Expected: all focused tests pass.

---

### Task 5: Contract inventory, desktop report, and final verification

**Files:**
- Create outside repository after approval: `C:\Users\PlanckSemicon\Desktop\CRM-Mock-Demo-接口权限与数据同步审查-2026-08-03.md`

**Interfaces:**
- Consumes: `src/api/contracts.ts`, `src/domain/permissions.ts`, `src/demo/personnel.ts`, repository implementations, test evidence, and final audit findings
- Produces: Markdown tables for API contract, role permission, personnel mapping, owner fields, synchronization boundaries, audit findings, and remaining risks

- [ ] **Step 1: Inventory every `CrmApi` method and implementation status**

Classify each method as Mock implemented, Mock local-persistence boundary, Frappe disabled, input owner validation, capability, scope, and downstream views refreshed.

- [ ] **Step 2: Write the desktop Markdown report**

The report must contain these exact table groups: personnel mapping, capability matrix, API contracts, mutable owner fields, before/after synchronization flow, storage ownership, adversarial findings, verification commands, and remaining Stage prerequisites.

- [ ] **Step 3: Run fresh verification**

Run:

```powershell
pnpm.cmd test
pnpm.cmd typecheck
pnpm.cmd build
git diff --check
```

Report exact counts and separate unrelated pre-existing failures from failures introduced by this implementation.

- [ ] **Step 4: Inspect the final diff and report scope**

Confirm no Frappe requests were reintroduced, no free-text mutable owner input remains, the desktop report exists, and no unrelated dirty-worktree files were modified by this implementation.
