# Demo Reset, Owner Permissions, and Request/Test Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Demo data with 10 correctly linked records, enforce real unique owners, and rebuild Demo Test with the same desktop workspace language as Demo Request.

**Architecture:** Keep `DemoSnapshot` as the single Mock source of truth. Upgrade it to v6 with an intentional Demo-domain reset, derive Request/Test/archive surfaces from the same Request/Evaluation records, and enforce owner values at both form and API boundaries. Build two Evaluation workspace components that mirror the established Demo Request page structure while retaining Test-specific actions.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vue Router, Vitest, Vue Test Utils, IndexedDB Mock repository, Vite.

## Global Constraints

- The final seed contains exactly 10 Demo Requests: 4 Request-stage, 4 active Test-stage, and 2 archived.
- The seed contains exactly 6 Evaluations: 4 active Test-stage and 2 archived.
- 演示员工14 owns exactly 5 Demo records; 演示员工15 owns exactly 5.
- Demo Staff 01 owns exactly 5 Demo records; Demo Staff 02 owns exactly 5.
- Valid engineer owners are only `演示员工14` and `演示员工15`.
- Valid sales owners are only `Demo Staff 01` and `Demo Staff 02`.
- A manager approval creates at most one Evaluation and keeps `evaluation.owner === request.engineerOwner`.
- Demo Test must use the Demo Request desktop workspace style but preserve Test-specific fields and actions.
- Lifecycle cards show no avatar, Test Run DDL, customer expected date, or other date.
- Q&A module and On Hold remain removed; Request-form question fields remain form data and do not recreate a system Q&A workflow.
- Do not add dependencies, mobile-specific work, Git branches, commits, merges, or unrelated refactors.
- Preserve unrelated dirty-worktree changes.

---

## File Map

- `src/demo/identities.ts`: expose canonical Sales and Engineer owner options.
- `src/demo/identities.test.ts`: protect exact real identity names and owner lists.
- `src/domain/demo-request-form.ts`: validate owner values in addition to required fields.
- `src/domain/demo-request-form.test.ts`: prove legacy/free-text owners are rejected.
- `src/features/demo-requests/DemoRequestForm.vue`: render Sales and Engineer owner fields as selects.
- `src/features/demo-requests/DemoRequestForm.test.ts`: prove the UI exposes only approved values.
- `src/features/demo-requests/DemoRequestModal.vue`: pass owner options, remove the `FAE Team` fallback, and render engineer review owner as a select/read-only scoped value.
- `src/api/mock-data.ts`: replace the current Demo Request and Evaluation fixtures with the ten-record batch.
- `src/demo/demo-repository.ts`: upgrade Snapshot to v6, intentionally replace v1-v5 Demo records, and validate seed invariants.
- `src/demo/demo-repository.test.ts`: test hard reset, counts, distribution, identity totals, linkage, and v6 persistence.
- `src/api/mock-adapter.ts`: use actual engineer identities for default usernames, enforce owner allowlists, and stop projecting legacy `demoProjects` into archives.
- `src/api/mock-adapter.test.ts`: protect role scoping and atomic Request-to-Test handoff using 演示员工14 and 演示员工15.
- `src/features/evaluations/EvaluationWorkspaceNav.vue`: new Test workspace navigation aligned with Demo Request.
- `src/features/evaluations/EvaluationWorkspace.vue`: new left rail, overview, stage detail, and action panel for active Evaluations.
- `src/pages/EvaluationsPage.vue`: compose the new workspace while retaining Test modals, report flow, permissions, and `focus`.
- `src/pages/delivery-workflow.test.ts`: verify the new Evaluation workspace and existing Test actions.
- `src/pages/DemoWorkflowPage.test.ts`: update seed expectations and protect lifecycle/archive counts and owner rendering.
- `src/pages/first-demo-completion.test.ts`: update the end-to-end seed IDs.
- `src/pages/permission-revocation.test.ts`: update Demo IDs and retain permission revocation behavior.

---

### Task 1: Canonical Demo Owner Options and Dropdown Validation

**Files:**
- Modify: `src/demo/identities.ts`
- Modify: `src/demo/identities.test.ts`
- Modify: `src/domain/demo-request-form.ts`
- Modify: `src/domain/demo-request-form.test.ts`
- Modify: `src/features/demo-requests/DemoRequestForm.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.test.ts`
- Modify: `src/features/demo-requests/DemoRequestModal.vue`

**Interfaces:**
- Produces: `DEMO_SALES_OWNER_OPTIONS: readonly string[]`
- Produces: `DEMO_ENGINEER_OWNER_OPTIONS: readonly string[]`
- Consumes: `DemoRequestFormData.salesContact` and `DemoRequestFormData.demoOwner`
- Produces: validation errors keyed by `salesContact` and `demoOwner`

- [ ] **Step 1: Write failing owner-list and validation tests**

Add literal expectations:

```ts
expect(DEMO_SALES_OWNER_OPTIONS).toEqual(['Demo Staff 01', 'Demo Staff 02'])
expect(DEMO_ENGINEER_OWNER_OPTIONS).toEqual(['演示员工14', '演示员工15'])

const legacy = validDemoRequestForm()
legacy.demoOwner = 'FAE Mia'
expect(validateDemoRequestFormData(legacy).demoOwner).toContain('演示员工14或演示员工15')

const unknownSales = validDemoRequestForm()
unknownSales.salesContact = 'Other Sales'
expect(validateDemoRequestFormData(unknownSales).salesContact).toContain('Demo Staff 01或Demo Staff 02')
```

Add a component test that mounts the real `DemoRequestForm`, queries `select[name="salesContact"]` and `select[name="demoOwner"]`, and asserts the literal option arrays.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
pnpm.cmd vitest run src/demo/identities.test.ts src/domain/demo-request-form.test.ts src/features/demo-requests/DemoRequestForm.test.ts
```

Expected: failure because the option exports do not exist, owner validation accepts legacy values, and the form still renders text inputs.

- [ ] **Step 3: Add canonical owner exports**

In `identities.ts`, derive stable values from the existing real identities:

```ts
export const DEMO_SALES_OWNER_OPTIONS = ['Demo Staff 01', 'Demo Staff 02'] as const
export const DEMO_ENGINEER_OWNER_OPTIONS = ['演示员工14', '演示员工15'] as const

export function isDemoSalesOwner(value: string) {
  return DEMO_SALES_OWNER_OPTIONS.some((owner) => owner === value)
}

export function isDemoEngineerOwner(value: string) {
  return DEMO_ENGINEER_OWNER_OPTIONS.some((owner) => owner === value)
}
```

- [ ] **Step 4: Enforce exact owner values in domain validation**

After required-field checks, set explicit errors when non-empty owner fields are outside the allowlists:

```ts
if (form.salesContact.trim() && !isDemoSalesOwner(form.salesContact.trim())) {
  errors.salesContact = '请选择 Demo Staff 01 或 Demo Staff 02'
}
if (form.demoOwner.trim() && !isDemoEngineerOwner(form.demoOwner.trim())) {
  errors.demoOwner = '请选择演示员工14或演示员工15'
}
```

- [ ] **Step 5: Replace owner inputs with selects**

Pass owner option props into `DemoRequestForm` and render:

```vue
<select name="salesContact" :value="draft.salesContact" required @change="setField('salesContact', $event)">
  <option value="" disabled>请选择 Sales Owner</option>
  <option v-for="owner in salesOwnerOptions" :key="owner" :value="owner">{{ owner }}</option>
</select>

<select name="demoOwner" :value="draft.demoOwner" required @change="setField('demoOwner', $event)">
  <option value="" disabled>请选择 Engineer Owner</option>
  <option v-for="owner in engineerOwnerOptions" :key="owner" :value="owner">{{ owner }}</option>
</select>
```

Use the same engineer options in the engineer-review modal, and replace the initial `FAE Team` value with the request owner or an empty value.

- [ ] **Step 6: Run focused owner tests and verify GREEN**

Run the Step 2 command. Expected: all three test files pass with no owner-option warnings.

---

### Task 2: Replace Demo Data with a Valid v6 Snapshot

**Files:**
- Modify: `src/api/mock-data.ts`
- Modify: `src/demo/demo-repository.ts`
- Replace behavior in: `src/demo/demo-repository.test.ts`

**Interfaces:**
- Produces: `DemoSnapshot.version = 6`
- Produces: `validateDemoSnapshot(snapshot: DemoSnapshot): void`
- Consumes: `demoRequests` and `evaluations` fixtures from `mock-data.ts`

- [ ] **Step 1: Write failing v6 reset and invariant tests**

Create tests that start from `seedDemoSnapshot()` or a mutated v5 snapshot and assert:

```ts
expect(migrated.version).toBe(6)
expect(migrated.demoRequests.map((item) => item.id)).toEqual([
  'DR-101', 'DR-102', 'DR-103', 'DR-104', 'DR-105',
  'DR-106', 'DR-107', 'DR-108', 'DR-109', 'DR-110',
])
expect(migrated.evaluations).toHaveLength(6)
expect(migrated.artifacts).toEqual([])
expect(migrated.demoRequests.filter((item) => item.engineerOwner === '演示员工14')).toHaveLength(5)
expect(migrated.demoRequests.filter((item) => item.engineerOwner === '演示员工15')).toHaveLength(5)
expect(migrated.demoRequests.filter((item) => item.salesOwner === 'Demo Staff 01')).toHaveLength(5)
expect(migrated.demoRequests.filter((item) => item.salesOwner === 'Demo Staff 02')).toHaveLength(5)
```

Verify every Evaluation has one Request with matching `evaluationId`/`demoRequestId` and owner. Verify DR-101–DR-104 have no Evaluation. Verify a v6 user change survives subsequent repository reads.

- [ ] **Step 2: Run repository tests and verify RED**

Run:

```powershell
pnpm.cmd vitest run src/demo/demo-repository.test.ts
```

Expected: v5 seed, old IDs, old owners, and legacy migration behavior fail the new assertions.

- [ ] **Step 3: Replace only Demo fixtures**

Define ten `DemoRequestDto` records using current customer/account/equipment fixtures:

```ts
DR-101 Engineer Review  演示员工14 Demo Staff 01
DR-102 Engineer Review  演示员工15 Demo Staff 02
DR-103 Manager Approval 演示员工14 Demo Staff 02
DR-104 Manager Approval 演示员工15 Demo Staff 01
DR-105 Converted        演示员工14 Demo Staff 01  -> EVAL-101 Requested
DR-106 Converted        演示员工15 Demo Staff 02 -> EVAL-102 Sample Received
DR-107 Converted        演示员工14 Demo Staff 02 -> EVAL-103 Testing
DR-108 Converted        演示员工15 Demo Staff 01  -> EVAL-104 Customer Review
DR-109 Converted        演示员工14 Demo Staff 01  -> EVAL-105 Accepted
DR-110 Converted        演示员工15 Demo Staff 02 -> EVAL-106 Rejected
```

Give each Request complete existing DTO fields, coherent history, tracking, form data, and customer/equipment references. Give Evaluations complete existing report fields and runs appropriate to their stages.

- [ ] **Step 4: Upgrade repository version and hard-reset old Demo snapshots**

Change the type to `1 | 2 | 3 | 4 | 5 | 6`. For any snapshot below v6, return a fresh cloned v6 seed instead of mutating old Demo records:

```ts
export function migrateDemoSnapshot(snapshot: DemoSnapshot): DemoSnapshot {
  if (snapshot.version === 6) return cloneSnapshot(snapshot)
  return seedDemoSnapshot()
}
```

This is intentionally destructive only for the Demo-domain snapshot and is authorized by the approved spec.

- [ ] **Step 5: Add snapshot invariant validation**

Validate exact counts, allowlisted owners, one-to-one links, stage/Evaluation boundary, and 5/5 owner distribution before saving an initial or migrated snapshot. Throw `Error('Invalid Demo seed: ...')` for a violated invariant.

- [ ] **Step 6: Run repository tests and verify GREEN**

Run the Step 2 command. Expected: all repository tests pass.

---

### Task 3: Fix Role Scoping, Owner Writes, and Archive Source

**Files:**
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Consumes: `isDemoSalesOwner`, `isDemoEngineerOwner`
- Consumes: `DemoRepository`
- Produces: role-scoped Request, Evaluation, lifecycle, and archive responses

- [ ] **Step 1: Write failing role and archive tests**

Add behavior tests using the real repository:

```ts
const zhou = createMockApi({ role: 'FAE / Applied Engineer', userName: '演示员工14', latency: 0 })
const sun = createMockApi({ role: 'Equipment Engineer', userName: '演示员工15', latency: 0 })

expect((await zhou.listDemoRequests({})).data.items).toHaveLength(5)
expect((await zhou.listDemoRequests({})).data.items.every((item) => item.engineerOwner === '演示员工14')).toBe(true)
expect((await sun.listDemoRequests({})).data.items).toHaveLength(5)
expect((await sun.listEvaluations({})).data.items.every((item) => item.owner === '演示员工15')).toBe(true)
expect((await admin.listDemoWorkflows()).data).toHaveLength(10)
```

Assert workflows contain only DR-101–DR-110 and no legacy `demoProjects` IDs. Assert invalid owner writes are rejected.

- [ ] **Step 2: Run adapter tests and verify RED**

Run:

```powershell
pnpm.cmd vitest run src/api/mock-adapter.test.ts
```

Expected: old default usernames/fixtures and legacy archive projection break the new assertions.

- [ ] **Step 3: Use real default engineer usernames**

Map role defaults to:

```ts
'FAE / Applied Engineer' -> '演示员工14'
'Equipment Engineer' -> '演示员工15'
```

Keep explicit `userName` authoritative.

- [ ] **Step 4: Enforce owner allowlists at create/update/review boundaries**

Before writing Demo Request owner fields:

```ts
if (!isDemoSalesOwner(formData.salesContact.trim())) throw validationError('请选择有效 Sales Owner')
if (!isDemoEngineerOwner(formData.demoOwner.trim())) throw validationError('请选择有效 Engineer Owner')
```

Before engineer approval, reject a non-allowlisted owner. Preserve the current request owner for engineer-role self-review; manager/admin reassignment still uses a valid option.

- [ ] **Step 5: Remove legacy archive projection**

Delete the `demoProjects` append path in `listDemoWorkflows`; retain only the Request/Evaluation projection. Remove the unused `demoProjects` import while leaving other `operations-data` consumers intact.

- [ ] **Step 6: Preserve atomic manager approval**

Keep the existing single `repository.transact` call. Verify it rejects duplicate approval and creates:

```ts
request.status = 'Converted'
request.evaluationId = evaluation.id
evaluation.demoRequestId = request.id
evaluation.owner = request.engineerOwner
```

- [ ] **Step 7: Run adapter tests and verify GREEN**

Run the Step 2 command. Expected: role scoping, write validation, handoff, and archive-source tests pass.

---

### Task 4: Build the Demo Test Workspace to Match Demo Request

**Files:**
- Create: `src/features/evaluations/EvaluationWorkspaceNav.vue`
- Create: `src/features/evaluations/EvaluationWorkspace.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Modify: `src/features/evaluations/EvaluationCard.test.ts` only if an obsolete board-only assertion must be removed

**Interfaces:**
- Produces: `EvaluationView = 'overview' | 'preparation' | 'execution' | 'customer'`
- `EvaluationWorkspace` props: `view`, `evaluations`, `focusedId`, `processing`, `canWrite`, `canReport`
- `EvaluationWorkspace` emits: `select`, `status`, `deadline`, `run`, `report`

- [ ] **Step 1: Write failing Evaluation workspace tests**

Mount the real `EvaluationsPage` and assert:

```ts
expect(wrapper.findAll('[data-evaluation-view]').map((node) => node.attributes('data-evaluation-view')))
  .toEqual(['overview', 'preparation', 'execution', 'customer'])
expect(wrapper.find('[data-evaluation-workspace]').exists()).toBe(true)
expect(wrapper.find('.evaluation-rail').exists()).toBe(true)
expect(wrapper.find('.evaluation-overview').exists()).toBe(true)
```

Switch to `preparation` and assert only Preparation records appear. Open deadline/run/report actions and assert the existing modals still render. Mount with `?focus=EVAL-104` and assert the selected item and notice are visible.

- [ ] **Step 2: Run page tests and verify RED**

Run:

```powershell
pnpm.cmd vitest run src/pages/delivery-workflow.test.ts
```

Expected: the page still renders the three-column `evaluation-board` and has no Test workspace navigation or rail.

- [ ] **Step 3: Add Evaluation workspace navigation**

Create a component matching the Request navigation structure with:

```ts
export type EvaluationView = 'overview' | 'preparation' | 'execution' | 'customer'
```

Labels are `Demo Test`, `Test Preparation`, `Test Execution`, and `Customer Review`.

- [ ] **Step 4: Add the Evaluation workspace**

Implement:

- Left rail: customer filter, keyword search, selected-record list.
- Overview: four count cards, table, selected-record preview.
- Stage views: top summary, Test-specific detail content, right action panel.
- Shared summary order: customer/title, source Request ID, Sales Owner, Engineer Owner, equipment, status.
- Preparation action emits `deadline`.
- Execution action emits `run`.
- Customer Review action emits `report`.
- Status select continues to use `evaluationStatusOptions`.

Use the established Request workspace CSS values and class structure without changing Request itself.

- [ ] **Step 5: Compose workspace in EvaluationsPage**

Retain:

- `listEvaluations`
- permission capabilities
- `focus` query behavior
- stale/error/denied handling
- `TestDeadlineModal`
- `TestRunModal`
- `ExternalReportModal`
- report release reload

Replace only the old board/filter rendering with `EvaluationWorkspaceNav` and `EvaluationWorkspace`.

- [ ] **Step 6: Run page tests and verify GREEN**

Run the Step 2 command. Expected: workspace, focus, action, report, and permission tests pass.

---

### Task 5: Update Lifecycle, Archive, and Cross-Module Regressions

**Files:**
- Modify: `src/pages/DemoWorkflowPage.test.ts`
- Modify: `src/pages/first-demo-completion.test.ts`
- Modify: `src/pages/permission-revocation.test.ts`
- Modify: other Demo-only test files revealed by focused failures

**Interfaces:**
- Consumes: v6 seed IDs and role-scoped API results
- Produces: protected end-to-end behavior across Request, Test, lifecycle, and archive

- [ ] **Step 1: Write/update lifecycle assertions before production adjustments**

Assert literal results:

```ts
expect(wrapper.findAll('.pipeline-card')).toHaveLength(8)
expect(archive.findAll('[data-demo-id]')).toHaveLength(2)
expect(wrapper.text()).toContain('Engineer 演示员工14')
expect(wrapper.text()).toContain('Engineer 演示员工15')
expect(wrapper.text()).not.toContain('FAE Leo')
expect(wrapper.text()).not.toContain('FAE Mia')
```

Keep the existing assertions that cards omit avatars, Test Run DDL, and customer expected date, and archive groups by customer/equipment.

- [ ] **Step 2: Run cross-module tests and verify RED**

Run:

```powershell
pnpm.cmd vitest run src/pages/DemoWorkflowPage.test.ts src/pages/first-demo-completion.test.ts src/pages/permission-revocation.test.ts
```

Expected: old IDs and old seed counts fail.

- [ ] **Step 3: Update test journeys to the new records**

Use:

- DR-101 for Engineer Review behavior.
- DR-103 for Manager Approval.
- EVAL-101 for Preparation/DDL.
- EVAL-103 for Test Execution/Test Run.
- EVAL-104 for Customer Review/report.
- DR-109 and DR-110 for archive.

Do not weaken permission, status transition, report, or artifact assertions.

- [ ] **Step 4: Make only production fixes revealed by valid failing tests**

If a lifecycle stage, archive category, detail link, or permission projection differs from the approved design, change the smallest responsible function. Do not modify unrelated CRM pages.

- [ ] **Step 5: Run cross-module tests and verify GREEN**

Run the Step 2 command. Expected: all three files pass.

---

### Task 6: Focused Regression, Typecheck, Build, and Browser Verification

**Files:**
- Modify only files directly implicated by verified failures.

**Interfaces:**
- Consumes: completed Tasks 1–5
- Produces: verified local desktop Demo behavior on port 4173

- [ ] **Step 1: Run the focused Demo suite**

```powershell
pnpm.cmd vitest run src/demo/identities.test.ts src/demo/demo-repository.test.ts src/domain/demo-request-form.test.ts src/features/demo-requests/DemoRequestForm.test.ts src/api/mock-adapter.test.ts src/pages/delivery-workflow.test.ts src/pages/DemoWorkflowPage.test.ts src/pages/first-demo-completion.test.ts src/pages/permission-revocation.test.ts
```

Expected: all focused tests pass.

- [ ] **Step 2: Run typecheck**

```powershell
pnpm.cmd typecheck
```

Expected: exit 0. If unrelated dirty-worktree failures remain, record exact files and separately prove no error originates from this task.

- [ ] **Step 3: Run production build**

```powershell
pnpm.cmd build
```

Expected: Vite production build exits 0.

- [ ] **Step 4: Verify the existing 4173 dev server**

Confirm port 4173 serves a Vite dev page with the HMR client. Start `pnpm.cmd dev:lan` only if no listener exists.

- [ ] **Step 5: Browser-check three identities**

Verify:

- Administrator sees 8 lifecycle cards and 2 archived Demo records.
- 演示员工14 sees only 5 owned records, including one Engineer Review and active Test records.
- 演示员工15 sees only 5 owned records, including one Engineer Review and active Test records.
- Demo Request owner fields are dropdowns.
- Demo Test matches Request workspace structure and actions open correctly.
- No card shows avatar, Test Run DDL, or customer expected date.
- No system Q&A or On Hold UI appears.

- [ ] **Step 6: Report exact verification evidence**

Summarize changed files, focused test counts, typecheck/build status, browser URLs, and any unrelated pre-existing failures. Do not create Git commits or merge work.
