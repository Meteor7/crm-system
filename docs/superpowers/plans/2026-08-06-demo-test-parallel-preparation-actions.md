# Demo Test Parallel Preparation Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist two independent Demo Test preparation branches, replace the status dropdown with valid action buttons, and make concurrent Demo writes version-safe.

**Architecture:** `CRM Evaluation` stores branch state and completion audit fields. A focused preparation command updates one branch under optimistic lock and automatically marks the Evaluation Scheduled when both branches finish. Frontend domain helpers derive views/actions, while all write pages separate action errors from list errors.

**Tech Stack:** Vue 3, TypeScript, Vitest, Frappe v15, Python unittest, MariaDB, Docker Compose.

## Global Constraints

- Preserve the dirty worktree and do not modify unrelated files.
- Sales can view Demo Test; Manager and scoped Engineer keep existing write permissions.
- Every version-sensitive write sends the currently displayed `modified` value.
- Permission revocation clears sensitive data; ordinary write errors preserve loaded rows.
- No new dependency.

---

### Task 1: Define and persist preparation branch state

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/domain/evaluations.ts`
- Modify: `src/domain/evaluations.test.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_evaluation/crm_evaluation.json`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/evaluations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_evaluation_api.py`

**Interfaces:**
- Produces `EvaluationPreparationBranch = 'wafer' | 'test'`.
- Produces `complete_evaluation_preparation(name, branch, expected_modified)` and DTO fields declared in the design.

- [ ] Add failing frontend domain tests for independent branches, the two-complete gate, and view grouping.
- [ ] Add failing backend tests proving one branch does not open execution, both branches set `Scheduled`, and stale versions return `VERSION_CONFLICT`.
- [ ] Run the focused tests and confirm failures are caused by missing branch support.
- [ ] Add DocType fields, serialization, defaults, legacy fallback, and the locked service command.
- [ ] Run focused frontend and backend tests until green.

### Task 2: Expose the preparation command and protect Demo Request concurrency

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/evaluations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/demo_requests.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/demo_requests.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_demo_request_api.py`

**Interfaces:**
- `completeEvaluationPreparation(id, branch, expectedModified): Promise<ApiResponse<EvaluationDto>>`.
- `transitionDemoRequest(id, command, expectedModified)` requires the displayed record version.

- [ ] Add failing transport tests for both `expectedModified` payloads.
- [ ] Add failing Mock and Frappe tests for branch completion and stale Demo Request transitions.
- [ ] Implement contracts, adapters, API endpoints, and optimistic locking.
- [ ] Run focused API tests until green.

### Task 3: Replace the Demo Test dropdown with workflow actions

**Files:**
- Modify: `src/features/evaluations/EvaluationWorkspaceNav.vue`
- Modify: `src/features/evaluations/EvaluationWorkspace.vue`
- Modify: `src/features/evaluations/EvaluationCard.vue`
- Modify: `src/features/evaluations/EvaluationWorkspace.test.ts`
- Modify: `src/features/evaluations/EvaluationCard.test.ts`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Workspace emits `prepare(branch)`, `status(next)`, `deadline`, `run`, and `report`.
- Navigation views are `overview | wafer | preparation | execution | internal | customer`.

- [ ] Add failing component tests proving the dropdown is absent and buttons follow the approved stage matrix.
- [ ] Add failing page tests proving branch commands and status commands send current `modified`.
- [ ] Implement separate Wafer/Test views and explicit buttons.
- [ ] Preserve inline errors and permission-revocation behavior.
- [ ] Run focused component/page tests until green.

### Task 4: Synchronize timelines and repair concurrent Demo Request UI

**Files:**
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/evaluations.py`
- Modify: relevant workflow projection tests.

**Interfaces:**
- Both Mock and Frappe workflow projections expose preparation steps from persisted branch fields.
- Demo Request write conflict reloads rows and displays an inline latest-data notice.

- [ ] Add failing tests for Demo Request edit/transition versions and conflict-preserved page content.
- [ ] Add failing projection tests for one-complete and both-complete preparation timelines.
- [ ] Pass selected `modified`, separate action/list errors, and reload on `VERSION_CONFLICT`.
- [ ] Replace hard-coded Mock timeline completion with persisted state.
- [ ] Run focused workflow and permission tests until green.

### Task 5: Verify and deploy

**Files:**
- Generated: `backend/apps/rayher_crm/rayher_crm/public/crm/**`
- Generated: `backend/build/rayher_crm.zip`

- [ ] Run all frontend tests and `npm.cmd run typecheck`.
- [ ] Run focused Frappe backend API tests in the container.
- [ ] Build the Frappe frontend and verified app archive.
- [ ] Rebuild/restart the local Docker services.
- [ ] Confirm containers are healthy and deployed Demo Test assets contain the new branch actions.
- [ ] Report exact verification evidence and any remaining risks.

