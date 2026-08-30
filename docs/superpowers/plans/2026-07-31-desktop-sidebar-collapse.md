# Desktop Sidebar Collapse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a desktop-only Codex-style fully hidden sidebar and strengthen navigation group typography.

**Architecture:** Keep all behavior inside the existing `AppShell.vue`. A non-persisted Vue `ref` controls a shell state class; CSS transitions the fixed sidebar and main content while the existing mobile drawer state remains unchanged.

**Tech Stack:** Vue 3, TypeScript, scoped CSS, Vitest, Vue Test Utils, Lucide Vue.

## Global Constraints

- Desktop sidebar is expanded by default and is not persisted across refreshes.
- Collapsed state fully hides the sidebar instead of leaving an icon rail.
- Existing route, permission, notification, identity and mobile drawer behavior must remain unchanged.
- Navigation group labels use `12px / 800`; navigation item labels use `10px / 600`.
- Do not add dependencies or refactor unrelated shell behavior.

---

### Task 1: Desktop collapse behavior and typography

**Files:**
- Modify: `src/app/AppShell.test.ts`
- Modify: `src/app/AppShell.vue`

**Interfaces:**
- Consumes: existing `AppShell` desktop layout, `mobileOpen`, and navigation rendering.
- Produces: `desktopSidebarCollapsed: Ref<boolean>`, `is-sidebar-collapsed` shell class, `sidebar-collapse-toggle` and `sidebar-expand-toggle` controls.

- [ ] **Step 1: Write the failing interaction test**

Add a test that mounts the real `AppShell`, confirms the desktop sidebar begins expanded, clicks `[data-testid="sidebar-collapse-toggle"]`, asserts the shell and sidebar carry their collapsed classes and the top-bar expand button appears, then clicks `[data-testid="sidebar-expand-toggle"]` and asserts the expanded state returns.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
.\node_modules\.bin\vitest.cmd run src/app/AppShell.test.ts -t "collapses the desktop sidebar completely" --exclude ".superpowers/**"
```

Expected: FAIL because the desktop collapse controls do not exist.

- [ ] **Step 3: Implement minimal desktop behavior**

In `AppShell.vue`, import `PanelLeftClose` and `PanelLeftOpen`, add:

```ts
const desktopSidebarCollapsed = ref(false)
```

Bind `is-sidebar-collapsed` on the shell, add a collapse button in the brand block and an expand button in the top-bar start area. Both update the ref directly. Add `aria-label`, `aria-expanded`, and the stable test IDs described above.

- [ ] **Step 4: Add scoped desktop layout and typography CSS**

Add transitions for `.app-sidebar` and `.app-main`; when the shell is collapsed, translate the sidebar by `-100%`, set `.app-main` to full width with zero left margin, and hide the in-sidebar collapse control. Explicitly set group and item label typography:

```css
.nav-section > p { font-size: 12px; font-weight: 800; }
.nav-link span { font-size: 10px; font-weight: 600; }
```

Keep the current `@media (max-width: 839px)` rules authoritative for the mobile drawer and hide desktop-only controls inside that media query.

- [ ] **Step 5: Run focused and shell regression tests**

Run:

```powershell
.\node_modules\.bin\vitest.cmd run src/app/AppShell.test.ts --exclude ".superpowers/**"
```

Expected: all `AppShell` tests pass.

- [ ] **Step 6: Verify compile, build and browser behavior**

Run:

```powershell
npm.cmd run typecheck
npm.cmd run build
```

Then inspect the local app at `http://127.0.0.1:4173`, exercise collapse and expand, and confirm the sidebar fully leaves the viewport while content expands.
