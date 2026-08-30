# Document Center Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing Document Center page with the approved three-state high-fidelity module while preserving the current CRM shell and API contracts.

**Architecture:** Keep the feature in `DocumentCenterPage.vue`, using the injected `CrmApi` for bootstrap, document listing, and access requests. Derive the employee workspace or approval workspace from the current role, and keep approval mutations as explicit Demo-only local state.

**Tech Stack:** Vue 3 Composition API, TypeScript, Lucide Vue, Vitest, Vue Test Utils, existing CRM design tokens.

## Global Constraints

- Modify only the Document Center page, its focused test, and the implementation spec/plan.
- Do not add dependencies or modify global role capability definitions.
- Do not expose Restricted document body content.
- Keep Version History and Download Audit inside the right detail area.
- Management Viewer is read-only.
- Preserve the injected `CrmApi` interface and existing identity-switch remount behavior.

---

### Task 1: Define employee workspace behavior with failing tests

**Files:**
- Create: `src/pages/DocumentCenterPage.test.ts`
- Modify: `src/pages/DocumentCenterPage.vue`

**Interfaces:**
- Consumes: `CrmApi.getBootstrap()`, `CrmApi.listControlledDocuments()`, `CrmApi.requestControlledDocumentAccess(versionId, reason)`.
- Produces: `[data-document-workspace]`, `[data-document-row]`, `[data-document-preview]`, and `[data-access-request-form]` UI contracts.

- [ ] Write a test mounting the page as Sales User and assert that the library contains only the three approved categories, the direct document preview is visible, and admin controls are absent.
- [ ] Run `.\node_modules\.bin\vitest.cmd run src/pages/DocumentCenterPage.test.ts --exclude ".superpowers/**"` and confirm failure because the new workspace selectors and preview do not exist.
- [ ] Add a test selecting `DOC-PRICE-26`, submitting a literal business reason, and asserting the API receives its `versionId` and the exact reason.
- [ ] Run the focused test again and confirm failure because the locked request form behavior does not exist.
- [ ] Implement document loading, role loading, search, category filtering, selection, direct preview, locked preview, reason validation, and request submission.
- [ ] Run the focused test and confirm the employee workspace cases pass.

### Task 2: Define approval and read-only behavior with failing tests

**Files:**
- Modify: `src/pages/DocumentCenterPage.test.ts`
- Modify: `src/pages/DocumentCenterPage.vue`

**Interfaces:**
- Consumes: the bootstrap role loaded in Task 1.
- Produces: `[data-approval-workspace]`, `[data-approval-action]`, `[data-management-readonly]`, version history, and download audit evidence.

- [ ] Add a CRM Administrator test asserting the queue, approval timeline, approve/reject/more-info controls, version history, and download audit are rendered.
- [ ] Add a Management Viewer test asserting the same evidence is visible while every approval action is disabled.
- [ ] Run the focused test and confirm failure because the approval workspace does not exist.
- [ ] Implement the approval queue and local Demo action state with enabled administrator controls.
- [ ] Implement the Management Viewer read-only presentation with disabled mutation controls.
- [ ] Run the focused test and confirm all Document Center tests pass.

### Task 3: Apply the approved high-fidelity visual system

**Files:**
- Modify: `src/pages/DocumentCenterPage.vue`

**Interfaces:**
- Consumes: employee and approval UI contracts from Tasks 1 and 2.
- Produces: responsive three-column layouts matching the approved Direct Access, Access Required, and Admin Review references.

- [ ] Replace the old metrics/table/detail styling with the deep-navy, warm-white, orange-accent dossier layout.
- [ ] Add selected, hover, focus-visible, disabled, locked-preview, PDF-preview, timeline, badge, and audit-table states.
- [ ] Add responsive rules for 1360px, 1100px, and 760px without changing AppShell.
- [ ] Run the focused test to ensure the visual markup did not break behavior.

### Task 4: Verify the complete implementation

**Files:**
- Verify: `src/pages/DocumentCenterPage.vue`
- Verify: `src/pages/DocumentCenterPage.test.ts`

**Interfaces:**
- Consumes: completed module.
- Produces: fresh test, typecheck, build, and browser-rendering evidence.

- [ ] Run `.\node_modules\.bin\vitest.cmd run src/pages/DocumentCenterPage.test.ts --exclude ".superpowers/**"`.
- [ ] Run `npm.cmd run typecheck`.
- [ ] Run `npm.cmd run build`.
- [ ] Start or reuse the LAN development server and inspect `/document-center` as Sales User, CRM Administrator, and Management Viewer.
- [ ] Confirm no console errors, no Restricted body leakage, and no enabled Management Viewer mutation controls.

No commit is planned because the shared worktree already contains unrelated staged and unstaged user changes.
