# Installed Tool Edit Permissions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add role-scoped Installed Tool master-data editing for administrators, Boss, and assigned engineers.

**Architecture:** Add a dedicated capability and typed update command. The Mock adapter enforces capability, account scope, engineer ownership, site ownership, and Serial uniqueness before mutating the shared Sales Repository; the page uses the same rules to expose a focused edit modal.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, Mock/Frappe adapters.

## Global Constraints

- Sales users remain read-only in Installed Tools.
- Boss has the same Installed Tool editing scope as CRM Administrator.
- Lifecycle milestones and documents are outside this change.
- Frappe editing remains `NOT_IMPLEMENTED`.

---

### Task 1: Capability and API contract

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/domain/permissions.ts`
- Modify: `src/api/contracts.ts`
- Test: `src/domain/permissions.test.ts`

- [x] Add failing role capability assertions.
- [x] Add `installed_tool:write`, `UpdateInstalledToolInput`, and `updateInstalledTool`.
- [x] Run permission tests and confirm they pass.

### Task 2: Mock and Frappe adapters

**Files:**
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`

- [x] Add failing tests for administrator/Boss success, assigned-engineer scope, Sales denial, duplicate Serial, and invalid Site.
- [x] Implement validation and one-save Mock mutation.
- [x] Add and verify the Frappe `NOT_IMPLEMENTED` boundary.

### Task 3: Edit modal and page entry

**Files:**
- Create: `src/features/installed-tools/InstalledToolEditorModal.vue`
- Modify: `src/pages/InstalledToolsPage.vue`
- Modify: `src/pages/seven-page-workspace.test.ts`

- [x] Add failing UI tests for Boss, assigned engineer, and Sales visibility.
- [x] Add the edit modal and save/reload flow.
- [x] Keep engineer reassignment enabled only for administrator and Boss.
- [x] Run focused page tests.

### Task 4: Verification

- [x] Run all affected tests.
- [x] Run standalone Vite build and record unrelated TypeScript baseline failures separately.
- [x] Verify administrator, Boss, engineer, and Sales behavior in the browser.
- [x] Run `git diff --check` for changed files.
