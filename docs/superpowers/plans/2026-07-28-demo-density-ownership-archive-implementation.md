# Demo Density, Ownership, and Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a 30–40-item lifecycle board with compact independently scrolling columns, unique Sales/Engineer ownership, and a switchable Demo archive grouped by customer or equipment.

**Architecture:** Keep the existing five-stage projection and add explicit owner fields plus a focused archive grouping domain module. Split the archive browser and shared detail out of `DemoWorkflowPage.vue`, while retaining one API read and URL-backed UI state.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vue Router, Vitest, Vue Test Utils, Vite, IndexedDB-backed Mock repository.

## Global Constraints

- Do not add dependencies.
- Do not restore system Q&A or On Hold.
- Cards do not show Test Run DDL, customer expected dates, ISO dates, or avatars.
- The second surface is named `Demo 档案`, not `历史档案`.
- Archived Demo classification supports customer and equipment.
- Every Demo has one concrete Sales Owner and one concrete Engineer Owner.
- Do not stage, commit, merge, push, or create a pull request.
- Deployment target is the existing Vite HMR service bound to `0.0.0.0:4173`.

---

### Task 1: Archive and Owner Domain Contracts

**Files:**
- Modify: `src/types/workspaces.ts`
- Create: `src/domain/demo-archive.ts`
- Create: `src/domain/demo-archive.test.ts`

**Interfaces:**
- Consumes: `DemoWorkflowDto`, `DemoRequestDto`, `EvaluationDto`.
- Produces: `DemoArchiveGroupMode`, `DemoArchiveGroup`, `groupDemoArchives(items, mode)`, `isConcreteEngineerOwner(value)`.

- [ ] **Step 1: Write failing archive grouping tests**

```ts
it('groups completed demos by customer and equipment', () => {
  expect(groupDemoArchives(items, 'customer').map((group) => group.label)).toEqual(['客户 A', '客户 B'])
  expect(groupDemoArchives(items, 'equipment')[0]).toMatchObject({ label: 'AX-9000', count: 2 })
})

it('rejects empty and team placeholder engineers', () => {
  expect(isConcreteEngineerOwner('')).toBe(false)
  expect(isConcreteEngineerOwner('FAE Team')).toBe(false)
  expect(isConcreteEngineerOwner('FAE Mia')).toBe(true)
})
```

- [ ] **Step 2: Run the domain test and verify failure**

Run: `pnpm.cmd test src/domain/demo-archive.test.ts`  
Expected: FAIL because `demo-archive.ts` does not exist.

- [ ] **Step 3: Add explicit workflow owner and equipment fields**

```ts
export interface DemoWorkflowDto {
  salesOwner: string
  engineerOwner: string
  equipment: string
  // existing fields remain
}
```

- [ ] **Step 4: Implement deterministic grouping**

```ts
export type DemoArchiveGroupMode = 'customer' | 'equipment'

export function groupDemoArchives(items: DemoWorkflowDto[], mode: DemoArchiveGroupMode) {
  const groups = new Map<string, DemoWorkflowDto[]>()
  for (const item of items) {
    const label = mode === 'customer' ? item.account : item.equipment || '未指定设备'
    groups.set(label, [...(groups.get(label) ?? []), item])
  }
  return [...groups.entries()]
    .map(([label, rows]) => ({ label, count: rows.length, items: rows }))
    .sort((left, right) => left.label.localeCompare(right.label, 'zh-CN'))
}
```

- [ ] **Step 5: Run the domain test**

Run: `pnpm.cmd test src/domain/demo-archive.test.ts`  
Expected: PASS.

---

### Task 2: Persist Unique Owners and Migrate Legacy Snapshots

**Files:**
- Modify: `src/api/mock-data.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/demo/demo-repository.ts`
- Modify: `src/demo/demo-repository.test.ts`
- Modify: `src/features/demo-requests/DemoRequestForm.test.ts`

**Interfaces:**
- Consumes: `isConcreteEngineerOwner(value)`.
- Produces: Snapshot version 4 with concrete `salesOwner` and `engineerOwner`.

- [ ] **Step 1: Add failing migration and creation tests**

```ts
it('migrates team placeholders to a concrete engineer without overwriting a real owner', async () => {
  const legacy = seedDemoSnapshot()
  legacy.version = 3
  legacy.demoRequests[0].engineerOwner = ''
  legacy.demoRequests[1].engineerOwner = 'FAE Team'
  const migrated = migrateDemoSnapshot(legacy)
  expect(migrated.version).toBe(4)
  expect(migrated.demoRequests[0].engineerOwner).toBe('FAE Leo')
  expect(migrated.demoRequests[1].engineerOwner).toBe('FAE Mia')
})
```

```ts
expect(created.data.engineerOwner).toBe('FAE Mia')
expect(created.data.salesOwner).toBe('Demo Staff 01')
```

- [ ] **Step 2: Verify the tests fail**

Run: `pnpm.cmd test src/demo/demo-repository.test.ts src/api/mock-adapter.test.ts`  
Expected: FAIL on version and owner assertions.

- [ ] **Step 3: Save both owners at Request creation**

```ts
salesOwner: formData.salesContact.trim(),
engineerOwner: formData.demoOwner.trim(),
```

Remove the creation-time `engineerOwner: ''`. Boss Approval must use:

```ts
owner: request.engineerOwner,
```

- [ ] **Step 4: Implement snapshot version 4 migration**

For every Request:

```ts
const linked = migrated.evaluations.find((item) => item.demoRequestId === request.id)
if (!isConcreteEngineerOwner(request.engineerOwner)) {
  const candidates = [linked?.owner, request.formData?.demoOwner]
  request.engineerOwner = candidates.find(isConcreteEngineerOwner)
    ?? (request.segment === 'Frontend' ? 'FAE Leo' : 'FAE Mia')
}
```

Set `migrated.version = 4` and `seedDemoSnapshot().version = 4`.

- [ ] **Step 5: Preserve reassignment history**

When `engineer_approve` changes the engineer, include the transition in the history comment:

```ts
const ownerChange = request.engineerOwner === command.engineerOwner.trim()
  ? ''
  : `；Engineer ${request.engineerOwner} → ${command.engineerOwner.trim()}`
```

- [ ] **Step 6: Run repository and adapter tests**

Run: `pnpm.cmd test src/demo/demo-repository.test.ts src/api/mock-adapter.test.ts src/features/demo-requests/DemoRequestForm.test.ts`  
Expected: PASS.

---

### Task 3: Apply Role Ownership Scope and Workflow Projection

**Files:**
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/types/workspaces.ts`

**Interfaces:**
- Produces: `canAccessDemo(request, evaluation?)` and explicit `salesOwner`, `engineerOwner`, `equipment` workflow fields.

- [ ] **Step 1: Write failing role-scope tests**

```ts
expect((await sales.listDemoWorkflows()).data.every((item) => item.salesOwner === 'Demo Staff 01')).toBe(true)
expect((await fae.listDemoWorkflows()).data.every((item) => item.engineerOwner === 'FAE Leo')).toBe(true)
expect((await manager.listDemoWorkflows()).data.length).toBeGreaterThan((await sales.listDemoWorkflows()).data.length)
```

- [ ] **Step 2: Run tests and verify owner-scope failure**

Run: `pnpm.cmd test src/api/mock-adapter.test.ts`  
Expected: FAIL because Demo scope is still account-based.

- [ ] **Step 3: Add a Demo-specific scope predicate**

```ts
function canAccessDemo(request: DemoRequestDto) {
  if (profile.scope === 'all' || profile.scope === 'cross-team-readonly') return true
  if (role === 'Sales User') return request.salesOwner === userName
  if (role === 'Sales Manager') return teamOwners.has(request.salesOwner)
  if (role === 'FAE / Applied Engineer' || role === 'Equipment Engineer') {
    return request.engineerOwner === userName
  }
  return canAccessAccount(request.accountId)
}
```

Apply this predicate to Demo Request, Evaluation through linked Request, and Demo Workflow listing.

- [ ] **Step 4: Project explicit owner and equipment fields**

```ts
salesOwner: request.salesOwner,
engineerOwner: request.engineerOwner,
equipment: request.assignedEquipment || request.requestedEquipment,
owner: request.engineerOwner,
```

The Frappe adapter maps the same fields from the returned Request/Evaluation data without inventing permissions.

- [ ] **Step 5: Run Mock and Frappe adapter tests**

Run: `pnpm.cmd test src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts src/pages/permission-revocation.test.ts`  
Expected: PASS.

---

### Task 4: Make the Lifecycle Board Dense and Owner-Aware

**Files:**
- Modify: `src/features/demo-workflow/DemoPipelineCard.vue`
- Modify: `src/features/demo-workflow/DemoStageColumn.vue`
- Modify: `src/features/demo-workflow/DemoPipelineBoard.vue`
- Modify: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: explicit workflow owner and equipment fields.
- Produces: board events for search, health, Sales Owner, Engineer Owner, and card open.

- [ ] **Step 1: Write failing board tests**

```ts
expect(card.text()).toContain('Sales Demo Staff 01')
expect(card.text()).toContain('Engineer FAE Leo')
expect(card.text()).not.toMatch(/\d{4}-\d{2}-\d{2}/)
expect(wrapper.findAll('[data-demo-stage-scroll]')).toHaveLength(5)
```

Verify selecting `FAE Leo` only retains cards whose `engineerOwner` is `FAE Leo`.

- [ ] **Step 2: Run the page test and verify failure**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts`  
Expected: FAIL because only one owner and no stage-scroll marker exist.

- [ ] **Step 3: Render both owners and compact the card**

```vue
<span class="owner-line">
  Sales {{ item.salesOwner }} · Engineer {{ item.engineerOwner }}
</span>
```

Use reduced gaps and padding while keeping the health row legible.

- [ ] **Step 4: Add owner filtering and stage scroll containers**

Add `salesOwner` and `engineerOwner` props/events. Generate options from the permission-scoped `items`. Set each stage column to:

```css
.stage-column {
  max-height: clamp(520px, calc(100vh - 330px), 720px);
  overflow-y: auto;
  overscroll-behavior: contain;
}
```

- [ ] **Step 5: Run board tests**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts`  
Expected: PASS.

---

### Task 5: Add the Demo Archive Surface and Shared Detail

**Files:**
- Create: `src/features/demo-workflow/DemoArchiveBrowser.vue`
- Create: `src/features/demo-workflow/DemoArchiveGroup.vue`
- Create: `src/features/demo-workflow/DemoArchiveDetail.vue`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/pages/DemoWorkflowPage.test.ts`
- Modify: `src/pages/seven-page-workspace.test.ts`

**Interfaces:**
- Consumes: `groupDemoArchives`, permission-scoped workflow DTOs.
- Produces: URL-backed `surface=board|archive`, `groupBy=customer|equipment`, archive status and owner filters.

- [ ] **Step 1: Write failing surface and grouping tests**

```ts
await wrapper.get('[data-demo-surface="archive"]').trigger('click')
expect(router.currentRoute.value.query.surface).toBe('archive')
expect(wrapper.findAll('[data-demo-archive-group]').length).toBeGreaterThan(0)

await wrapper.get('[data-archive-group-mode="equipment"]').trigger('click')
expect(router.currentRoute.value.query.groupBy).toBe('equipment')
expect(wrapper.text()).toContain('FastScan 1200')
```

Also assert archive cards contain only `Accepted` or `Rejected`, and page text does not contain `Customer Q&A` or `On Hold`.

- [ ] **Step 2: Run page tests and verify failure**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts src/pages/seven-page-workspace.test.ts`  
Expected: FAIL because the archive surface does not exist.

- [ ] **Step 3: Extract the existing detail into `DemoArchiveDetail.vue`**

Move current Request, approval rail, Demo Test, Artifact, and Conclusion sections without changing their output. Add explicit Sales and Engineer fields to the overview.

- [ ] **Step 4: Implement grouped archive browsing**

Filter only:

```ts
items.filter((item) => item.archiveCategory === 'Completed')
```

Then apply keyword, result, Sales Owner, and Engineer Owner filters before `groupDemoArchives`.

- [ ] **Step 5: Add the two-surface segmented control**

```vue
<button data-demo-surface="board">生命周期看板</button>
<button data-demo-surface="archive">Demo 档案</button>
```

Keep `surface`, filters, `groupBy`, `view`, and `focus` in route query state. Opening and closing detail must preserve the source surface.

- [ ] **Step 6: Run page and workspace tests**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts src/pages/seven-page-workspace.test.ts src/pages/first-demo-completion.test.ts`  
Expected: All Demo assertions pass; any unrelated pre-existing Installed Tools assertion is reported separately.

---

### Task 6: Regression, Browser QA, and 4173 Deployment

**Files:**
- Modify only if verification exposes an in-scope defect.

**Interfaces:**
- Produces: verified local/LAN deliverable.

- [ ] **Step 1: Run focused regression**

Run:

```powershell
pnpm.cmd test src/domain/demo-archive.test.ts src/domain/demo-lifecycle.test.ts src/demo/demo-repository.test.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts src/pages/DemoWorkflowPage.test.ts src/pages/permission-revocation.test.ts src/pages/delivery-workflow.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run typecheck and production build**

Run: `pnpm.cmd run typecheck`  
Expected: exit 0.

Run: `pnpm.cmd run build`  
Expected: exit 0.

- [ ] **Step 3: Run full regression**

Run: `pnpm.cmd test`  
Expected: no new failures compared with the two known unrelated baseline failures: AppShell timeout and Installed Tools wording expectation.

- [ ] **Step 4: Verify the 4173 HMR server**

Confirm `0.0.0.0:4173` is listening and `http://127.0.0.1:4173/demo-workflow` returns HTTP 200 with `/@vite/client`.

- [ ] **Step 5: Browser acceptance**

Verify at desktop and narrow viewport:

- Direct URL opens Demo 档案 page.
- Lifecycle columns scroll independently with 30–40 fixture items.
- Cards show Sales and Engineer, with no dates or avatars.
- Sales and Engineer filters work.
- Demo 档案 switches between customer and equipment grouping.
- Accepted/Rejected filtering works.
- Archive detail opens and returns with state preserved.
- System Q&A and On Hold remain absent.
- Browser console has no errors or warnings.

- [ ] **Step 6: Leave the final Demo page open**

Reset temporary viewport overrides and keep `http://127.0.0.1:4173/demo-workflow` as the browser deliverable.
