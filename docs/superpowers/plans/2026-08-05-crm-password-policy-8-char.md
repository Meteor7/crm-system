# CRM 8-Character Password Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the CRM account-center and Frappe password policy at 8 or more characters with at least one English letter and one digit.

**Architecture:** Keep client-side validation for immediate feedback and enforce the identical rule in the authenticated Frappe endpoint as the authoritative boundary. Preserve the existing password-change API contract and deployment topology.

**Tech Stack:** Vue 3, TypeScript, Frappe v15, Python, Docker Compose

## Global Constraints

- Do not expose or change any existing password during verification.
- Do not commit, reset, stash, clean, stop containers, or delete Docker volumes.
- Follow the user's debug-first then test instruction; do not use TDD.

---

### Task 1: Align frontend and backend validation

**Files:**
- Modify: `src/app/AppShell.vue`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/account.py`

**Interfaces:**
- Consumes: `changeCurrentUserPassword({ currentPassword, newPassword })`
- Produces: unchanged API response `{ updated: true }`

- [x] Change the frontend predicate to `length >= 8`, `/[A-Za-z]/`, and `/[0-9]/`.
- [x] Change the visible guidance and validation error to the same rule.
- [x] Change backend validation to the same three checks and retain the new-versus-current comparison.
- [x] Remove the now-unused Python `string` import.

### Task 2: Verify and deploy

**Files:**
- Modify: `docs/CRM-持续执行审计日志-2026-08-04.md`

**Interfaces:**
- Consumes: built `rayher_crm` application archive.
- Produces: updated `rayher-crm-stage1:v15-local` services with the existing database volumes.

- [x] Run `npm.cmd run typecheck` and the focused account-shell tests.
- [x] Compile the Python endpoint and run `npm.cmd run build:frappe`.
- [x] Prepare the app archive and run the frontend/package contract checks.
- [x] Rebuild and update Docker Compose without deleting volumes.
- [x] Verify HTTP ping and append a password-free audit entry.
