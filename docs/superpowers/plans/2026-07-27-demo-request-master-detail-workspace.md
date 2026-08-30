# Demo Request Master-Detail Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Demo Request kanban with a consistent four-view master-detail workspace where Demo Request is a standalone overview and the other three views form an arrow-linked processing flow.

**Architecture:** `DemoRequestsPage` retains data loading, permissions, transitions, Word generation, and modal ownership. A focused navigation component owns the four-view selector, while a focused workspace component renders overview or stage-specific request content and emits the existing business actions back to the page.

**Tech Stack:** Vue 3, TypeScript, Vue Test Utils, Vitest, existing CRM design tokens

## Global Constraints

- `Demo Request` is an overview and is not connected to the processing flow.
- Only `Sales Preparation → Engineer Review → Manager Approval` are connected with arrows.
- Match the current Sales-module visual language and the approved overview reference.
- Preserve existing permissions, API calls, Demo Test handoff, Customer Q&A, and Word generation.
- Do not add dependencies or change mobile behavior beyond maintaining safe stacking.

---

### Task 1: Add the workspace navigation contract

**Files:**
- Create: `src/features/demo-requests/DemoRequestWorkspaceNav.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Modify: `src/pages/DemoRequestsPage.vue`

**Interfaces:**
- Consumes: `modelValue: 'overview' | 'sales' | 'engineer' | 'manager'`
- Produces: `update:modelValue`

- [ ] **Step 1: Write the failing page test**

Add a test that mounts `DemoRequestsPage`, verifies one standalone overview button and three processing buttons, confirms that arrows exist only between processing buttons, and changes the active view to `Engineer Review`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
pnpm.cmd test src/pages/delivery-workflow.test.ts
```

Expected: FAIL because the new navigation selectors do not exist.

- [ ] **Step 3: Implement the navigation**

Create a navigation component using:

```ts
export type DemoRequestView = 'overview' | 'sales' | 'engineer' | 'manager'
```

Expose buttons using `data-demo-view`, mark the current button with `aria-current="page"`, and render exactly two arrow separators inside the processing-flow group.

- [ ] **Step 4: Integrate navigation state in the page**

Add `activeView` to `DemoRequestsPage`, render the navigation below the page header, and keep `Demo Request` selected by default.

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```powershell
pnpm.cmd test src/pages/delivery-workflow.test.ts
```

Expected: the navigation test and existing delivery workflow tests pass.

---

### Task 2: Replace the kanban with the master-detail workspace

**Files:**
- Create: `src/features/demo-requests/DemoRequestWorkspace.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Test: `src/pages/permission-revocation.test.ts`

**Interfaces:**
- Consumes: filtered requests, active view, selected request ID, capability flags, processing IDs.
- Produces: `select`, `submit`, `edit`, `cancel`, `engineer`, `manager`, `download`, and `answer` events.

- [ ] **Step 1: Write the failing workspace behavior test**

Assert that:

- overview shows all four active requests;
- Sales Preparation shows only editable/returned requests;
- Engineer Review shows only `Engineer Review`;
- Manager Approval shows only `Manager Approval`;
- selecting a stage preserves the existing action selectors such as `data-demo-action="DR-004-review"`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
pnpm.cmd test src/pages/delivery-workflow.test.ts
```

Expected: FAIL because the master-detail workspace does not exist.

- [ ] **Step 3: Implement the workspace**

Render:

- overview: request list, summary strip, request table, selected preview;
- stage views: filtered request rail, selected request summary, stage-appropriate detail sections, and the existing action controls.

Preserve one `data-demo-request="<id>"` root per visible request so current tests and permissions behavior remain observable.

- [ ] **Step 4: Connect existing page actions**

Forward all workspace events to the existing page functions. Keep `DemoRequestModal` and `QuestionAnswerModal` unchanged.

- [ ] **Step 5: Run focused workflow and permission tests**

Run:

```powershell
pnpm.cmd test src/pages/delivery-workflow.test.ts src/pages/permission-revocation.test.ts
```

Expected: all focused tests pass.

---

### Task 3: Validate the rendered implementation

**Files:**
- Modify only if browser findings reveal a scoped visual defect.

**Interfaces:**
- Consumes: built production assets on port 4173.
- Produces: verified desktop Demo Request navigation and workspace.

- [ ] **Step 1: Run static verification**

```powershell
pnpm.cmd run typecheck
pnpm.cmd run build
git diff --check
```

- [ ] **Step 2: Inspect all four views at `http://localhost:4173/`**

Verify:

- Demo Request is visually standalone;
- the three process nodes contain exactly two arrows;
- every view keeps the same shell, grid, type scale, borders, radii, and orange active state;
- existing role actions remain available only where permitted;
- no desktop horizontal overflow is introduced.

- [ ] **Step 3: Run the full suite**

```powershell
pnpm.cmd test
```

Report focused results separately from already-known unrelated baseline failures.
