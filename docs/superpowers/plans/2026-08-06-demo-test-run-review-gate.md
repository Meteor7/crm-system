# Demo Test Run Review Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require at least one Completed Test Run before a Demo Test can move from Testing to Internal Review.

**Architecture:** Add one shared frontend predicate over `EvaluationDto.runs`, consume it in the workspace action state and Mock transition validation, and mirror the same database-backed condition in the Frappe service. Preserve the existing status command and error rendering contracts.

**Tech Stack:** Vue 3, TypeScript, Vitest, Python, Frappe v15.

## Global Constraints

- A Completed Test Run is identified by `run.status === 'Completed'`.
- Planned Test Runs do not satisfy the gate.
- Only `Testing -> Internal Review` is affected.
- Use `INVALID_TRANSITION` for rejected direct transitions.
- Do not change unrelated workflow or report rules.

---

### Task 1: Frontend Gate Predicate and Workspace Feedback

**Files:**
- Modify: `src/domain/evaluations.ts`
- Modify: `src/domain/evaluations.test.ts`
- Modify: `src/features/evaluations/EvaluationWorkspace.vue`
- Modify: `src/features/evaluations/EvaluationWorkspace.test.ts`

**Interfaces:**
- Produces: `hasCompletedTestRun(evaluation: EvaluationDto): boolean`
- Consumes: `EvaluationDto.runs` and the existing `showAdvance` action computation.

- [ ] **Step 1: Write failing tests** asserting the Testing advance action is disabled with an explanatory message when runs are empty or Planned, and enabled when one run is Completed.
- [ ] **Step 2: Run focused Vitest tests** and confirm failure because no gate exists.
- [ ] **Step 3: Implement the predicate and use it to disable only the Testing advance action.** Render the literal message `请先完成至少一条 Test Run，再进入 Internal Review` beside the action.
- [ ] **Step 4: Re-run focused tests** and confirm they pass.

### Task 2: Mock API Enforcement

**Files:**
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Consumes: `hasCompletedTestRun(evaluation)`.
- Produces: `INVALID_TRANSITION` when `command.status === 'Internal Review'` and no Completed run exists.

- [ ] **Step 1: Write a failing Mock API test** that tries `Testing -> Internal Review` with no Completed Test Run and expects `INVALID_TRANSITION`; include a successful transition after adding a complete run.
- [ ] **Step 2: Run the focused test** and confirm the first transition currently succeeds.
- [ ] **Step 3: Add the minimal transition guard** before mutating Evaluation status.
- [ ] **Step 4: Re-run the focused test** and confirm both rejection and success paths pass.

### Task 3: Frappe Service Enforcement

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/evaluations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_evaluation_api.py`

**Interfaces:**
- Consumes: `CRM Test Run.status` rows related by `evaluation`.
- Produces: `INVALID_TRANSITION` before saving `Internal Review` when no Completed row exists.

- [ ] **Step 1: Write a failing backend test** for no run, Planned run, and Completed run.
- [ ] **Step 2: Run the focused Frappe module** and confirm the no-run transition incorrectly succeeds.
- [ ] **Step 3: Add a database existence check** for one `CRM Test Run` with `evaluation = doc.name` and `status = 'Completed'` when the requested transition is `Internal Review`.
- [ ] **Step 4: Re-run the backend module** and confirm all cases pass.

### Task 4: Regression, Build, and Local Deployment

**Files:**
- Generated: `backend/apps/rayher_crm/rayher_crm/public/crm/**`

- [ ] **Step 1: Run frontend typecheck and focused tests.**
- [ ] **Step 2: Run the complete frontend Vitest suite.**
- [ ] **Step 3: Build the Frappe frontend and Docker backend image.**
- [ ] **Step 4: Restart affected containers and run the focused backend module against the rebuilt service.**
- [ ] **Step 5: Verify `/api/method/ping` and container health.**
