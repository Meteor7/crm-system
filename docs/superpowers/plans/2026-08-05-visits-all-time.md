# Visits All-Time Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the visit date-range filter so the page always requests every visit visible to the current user.

**Architecture:** Keep the existing backend date-filter capability unchanged. Simplify only `VisitsPage.vue`: omit `dateFrom` and `dateTo` from page state and API requests, then prove the request contract and visible controls through the existing page test suite.

**Tech Stack:** Vue 3, TypeScript, Vitest, Frappe v15 frontend build, Docker Compose

## Global Constraints

- Do not add an archive feature.
- Do not change the database schema, visit statuses, or backend query semantics.
- Keep search, customer, status, owner, contact-route, and role-permission filtering unchanged.
- Do not commit, reset, stash, clean, or delete Docker volumes.

---

### Task 1: Remove the Visit Date Range

**Files:**
- Modify: `src/pages/VisitsPage.vue`
- Test: `src/pages/customer-operations.test.ts`

**Interfaces:**
- Consumes: `CrmApi.listVisits(query: ListQuery)`
- Produces: visit-list requests containing `search`, `accountId`, `status`, `owner`, and `contactId`, with no `dateFrom` or `dateTo`

- [ ] **Step 1: Update the page behavior**

Remove `dateFrom` and `dateTo` refs, omit them from `listVisits`, remove date mutations from `reset()` and visit creation, and delete both date inputs from the filter bar.

- [ ] **Step 2: Add focused request and DOM assertions**

Extend the existing `VisitsPage` test to spy on `listVisits`, assert the initial query has no `dateFrom` or `dateTo`, and assert neither date input exists.

- [ ] **Step 3: Run focused frontend tests**

Run:

```powershell
$env:TEMP=(Resolve-Path '.codex-tmp\vitest-temp').Path
$env:TMP=$env:TEMP
npm.cmd test -- src/pages/customer-operations.test.ts src/features/visits/VisitModal.test.ts src/api/mock-adapter.test.ts
```

Expected: all selected suites pass.

### Task 2: Build and Deploy the Updated Frappe Frontend

**Files:**
- Modify generated assets under: `backend/apps/rayher_crm/rayher_crm/public/crm/`
- Modify generated archive: `backend/build/rayher_crm.zip`

**Interfaces:**
- Consumes: the updated Vue source and existing Docker Compose stack
- Produces: the updated local service at `http://127.0.0.1:2224`

- [ ] **Step 1: Build the Frappe frontend**

Run `npm.cmd run build:frappe` and require exit code 0.

- [ ] **Step 2: Prepare and build the app image**

Run the verified app-archive script, then `docker compose -f backend/compose.yaml -p rayher-crm-stage1-local build`.

- [ ] **Step 3: Recreate containers without deleting volumes**

Run `docker compose -f backend/compose.yaml -p rayher-crm-stage1-local up -d --force-recreate`.

- [ ] **Step 4: Verify runtime health**

Require healthy backend/frontend/database containers and HTTP 200 from `http://127.0.0.1:2224`.
