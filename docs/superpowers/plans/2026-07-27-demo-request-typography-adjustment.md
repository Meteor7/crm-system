# Demo Request Typography Adjustment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve desktop readability in the four Demo Request workspace views without changing layout or business behavior.

**Architecture:** Keep the existing Vue component structure and update only the scoped CSS in the workspace and workspace navigation components. Verify typography through production build and the existing `4173` desktop preview.

**Tech Stack:** Vue 3, scoped CSS, Vite, Vitest, in-app Browser.

## Global Constraints

- Scope is limited to the four Demo Request workspace views.
- Auxiliary copy is `11px`.
- Table, list, field, and body copy is `12–13px`.
- Card section headings are `15px`.
- Page title, application shell, layout, spacing, controls, workflow, and other modules remain unchanged.
- No new dependencies.

---

### Task 1: Increase Workspace Typography

**Files:**
- Modify: `src/features/demo-requests/DemoRequestWorkspace.vue`
- Modify: `src/features/demo-requests/DemoRequestWorkspaceNav.vue`

**Interfaces:**
- Consumes: Existing `DemoRequestWorkspace` markup and `data-demo-*` selectors.
- Produces: The same component interface and DOM structure with larger scoped typography.

- [ ] **Step 1: Record the current visual baseline**

Run the existing `4173` preview and confirm that list metadata, table headings, DRF labels, Q&A, history, and action-panel copy are currently rendered at `9–11px`.

- [ ] **Step 2: Apply the approved CSS mapping**

Update only `font-size` declarations:

```css
/* Auxiliary copy */
font-size: 11px;

/* Body, table, list, and field copy */
font-size: 12px;
font-size: 13px;

/* Section headings */
font-size: 15px;
```

Keep layout properties, padding, width, grid definitions, colors, and component markup unchanged.

- [ ] **Step 3: Run focused workflow tests**

Run:

```powershell
pnpm.cmd test src/pages/delivery-workflow.test.ts src/pages/permission-revocation.test.ts
```

Expected: 22 tests pass.

- [ ] **Step 4: Run type and production build verification**

Run:

```powershell
pnpm.cmd run typecheck
pnpm.cmd run build
```

Expected: both commands exit with code `0`.

- [ ] **Step 5: Verify the running desktop preview**

At `http://localhost:4173/`, verify:

- Demo Request overview and Engineer Review remain readable.
- Four workspace controls and two flow arrows remain visible.
- No horizontal overflow, clipped control, framework overlay, console warning, or console error is introduced.

