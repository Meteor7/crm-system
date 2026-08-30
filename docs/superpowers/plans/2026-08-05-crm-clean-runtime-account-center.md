# CRM Clean Runtime and Account Center Implementation Plan

> **For agentic workers:** Execute inline in the current session. The user explicitly requested debug-first implementation instead of TDD.

**Goal:** Remove Frappe-visible Mock residue and provide a secure current-user password setting in Account Center.

**Architecture:** Keep Mock-only fixtures behind `usingMock`, hydrate notifications from the existing Frappe API, add one narrow rayher_crm password endpoint, and keep account UI in AppShell. Do not delete database rows during this implementation.

**Tech Stack:** Vue 3, Pinia, TypeScript, Frappe v15 Python API, Docker Compose.

## Global Constraints

- No password, cookie, token, or session output.
- No commit, reset, stash, clean, container stop, or volume deletion.
- Preserve unrelated dirty-worktree changes.

### Task 1: Remove Frappe-visible static queues

**Files:** `src/pages/DocumentCenterPage.vue`, `src/stores/notifications.ts`, `src/stores/app.ts`, `src/app/AppShell.vue`

- [ ] Gate approval fixtures to Mock mode and add a Manager empty state.
- [ ] Initialize notifications empty, load server notifications after bootstrap, and persist read actions through `CrmApi`.
- [ ] Remove static topbar timestamp in Frappe mode.

### Task 2: Add Account Center password Setting

**Files:** `src/app/AppShell.vue`, `src/api/contracts.ts`, `src/api/frappe-adapter.ts`, `src/api/mock-adapter.ts`, `backend/apps/rayher_crm/rayher_crm/api/v1/account.py`

- [ ] Replace initials/switch chevrons with a gear button and Account Center panel.
- [ ] Add current/new/confirm password fields with client validation and no persistence.
- [ ] Add authenticated server endpoint that verifies current password and enforces strong new passwords.

### Task 3: Verify and deploy locally

**Files:** existing focused tests and Docker build scripts only.

- [ ] Run focused tests, typecheck, and Frappe production build.
- [ ] Rebuild/recreate only the new local stack services required for the frontend/backend image.
- [ ] Verify health and the three affected surfaces in a signed-in browser session.
- [ ] Update the continuous audit log without recording credentials.
