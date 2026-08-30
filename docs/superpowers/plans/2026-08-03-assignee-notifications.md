# Assignee Dropdown And Notification Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mutable internal-person text fields with one role-filtered dropdown and send the selected person a message-center notification linking to the affected business record.

**Architecture:** Keep the existing Mock DTO owner-name fields for compatibility, but resolve names through the authoritative personnel directory. A shared `PersonnelSelect` renders assignment options; a shared notification builder derives stable recipients and exact routes after successful writes. External customer contacts and read-only filters remain outside this flow.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, Vue Test Utils, Mock adapter.

## Global Constraints

- Preserve the dirty worktree and modify only assignee, notification, and directly related tests.
- Mock Demo only; do not claim Frappe or production persistence.
- Boss `演示经理01` must be available to Comment mentions through the personnel directory.
- Customer contacts, reporting lines, stakeholders, and filters do not create internal notifications.

---

### Task 1: Stabilize the personnel contract

**Files:**
- Modify: `src/demo/personnel.ts`
- Modify: `src/demo/identities.ts`
- Modify: `src/types/crm.ts`
- Test: `src/demo/personnel.test.ts`

**Interfaces:**
- Produces: `PERSONNEL`, `personnelForRole`, `personnelForRoles`, `personnelByName`.
- Keeps: existing owner DTO fields as names.

- [ ] Write a failing test proving all personnel names are readable, unique, and include `演示经理01`.
- [ ] Run `pnpm.cmd test src/demo/personnel.test.ts` and confirm the expected failure.
- [ ] Repair the personnel directory without widening business scope.
- [ ] Run the focused test and typecheck the affected contract.

### Task 2: Shared personnel dropdown

**Files:**
- Create: `src/design-system/PersonnelSelect.vue`
- Create: `src/design-system/PersonnelSelect.test.ts`
- Modify: customer, contact, Lead, conversion, Opportunity, Booking, Action, Visit, Demo, and Installed Tool assignment forms.

**Interfaces:**
- Consumes: `modelValue: string`, `roles: UserRole[]`, standard select attributes.
- Emits: `update:modelValue` with an exact personnel name.

- [ ] Write a failing component test for role filtering, Boss visibility when Manager is allowed, and legacy-value display.
- [ ] Run the test and confirm RED.
- [ ] Implement the minimal shared component.
- [ ] Replace every mutable internal-person free-text input; keep filters unchanged.
- [ ] Run focused form tests and confirm GREEN.

### Task 3: Targeted assignment notifications

**Files:**
- Modify: `src/types/notifications.ts`
- Modify: `src/stores/notifications.ts`
- Modify: `src/api/notifying-api.ts`
- Modify: `src/pages/DemoDetailPage.vue`
- Test: `src/api/notifying-api.test.ts`
- Test: `src/stores/notifications.test.ts`

**Interfaces:**
- Produces: notifications containing `recipientId`, `recipient`, and exact `route`.
- Routes: Account, Contact, Lead, Opportunity, Booking, Visit, Demo detail, and Installed Tool highlight.

- [ ] Write failing tests proving assignment notifications are recipient-scoped and use detail routes.
- [ ] Run the tests and confirm RED.
- [ ] Add stable-recipient filtering with backward-compatible names.
- [ ] Generate assignment notifications only after successful writes.
- [ ] Refactor Comment mentions to use the shared personnel directory and recipient identity.
- [ ] Run focused tests and confirm GREEN.

### Task 4: Verification

**Files:**
- Modify only defects proven by focused verification in files already in scope.

- [ ] Run focused assignee, notification, Demo, customer, sales-flow, visit, and Installed Tool tests.
- [ ] Run `pnpm.cmd typecheck` and separate pre-existing migration failures from new failures.
- [ ] Run `pnpm.cmd build` and `git diff --check`.
- [ ] Inspect the final diff to confirm no external-contact fields or unrelated modules changed.
