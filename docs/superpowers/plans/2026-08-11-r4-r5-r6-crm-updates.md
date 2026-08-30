# CRM R4–R6 Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Manager-global Sales CRUD, uploaded Demo Test Reports with an Article archive, and a shared-style Installed Tools pipeline board.

**Architecture:** Preserve the existing three-role and Frappe DocType model. Tighten row scope and add narrow delete commands for R4; reuse `CRM Demo Artifact` as the secured file aggregate and gate the existing `Testing` state for R5; extract visual pipeline primitives into the design system and adapt both Demo and Installed Tools for R6.

**Tech Stack:** Vue 3, TypeScript, Vitest, Pinia, Frappe/Python, PowerShell HTTP acceptance tests.

## Global Constraints

- Implement in R4 → R5 → R6 order.
- New feature components stay under `src/features/<feature>/`; cross-feature components stay under `src/design-system/`.
- New visual values use `src/design-system/tokens.css`; do not introduce dependencies.
- Enforce permissions in both frontend visibility and backend capability/scope checks.
- Preserve Sales own-data and Engineer assigned-data boundaries.
- Uploads allow PDF, DOCX, XLSX, CSV, TXT, PNG, JPEG up to 10 MiB; reject executables, macros, MIME mismatches, and scanner failures.
- Preserve unrelated working-tree changes, especially the quotation feature.
- Use the machine's trusted plaintext recovery step after every `apply_patch` write before staging or verification.

---

### Task 1: R4 row-scope correction

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_scope.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/scope.py`
- Modify: `src/domain/permissions.test.ts`
- Modify: `src/domain/permissions.ts`

**Interfaces:**
- Consumes: `conditions_for_doctype(doctype: str, user: str | None) -> str`
- Produces: Manager `1=1`; Sales Customer condition on `custom_crm_owner`; unchanged Engineer assignment condition.

- [ ] Add a backend test that creates Manager, two Sales users, two owned Customers, and asserts Manager sees both while each Sales user sees only their own Customer.
- [ ] Run the focused scope test and verify it fails because `_customer_condition` currently returns `1=1` for Sales.
- [ ] Change `_customer_condition` so only Manager is global and Sales emits ``table.`custom_crm_owner` = escaped_user``.
- [ ] Add/adjust frontend permission assertions so Manager contains every capability exposed to Sales plus Manager-only delete/review capabilities, while Sales and Engineer profiles remain restricted.
- [ ] Run `test_scope.py` and `src/domain/permissions.test.ts` to green.

### Task 2: R4 Manager-only delete contracts

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/accounts.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/leads.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/opportunities.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/bookings.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/visits.py`
- Modify: corresponding service and backend API test files.

**Interfaces:**
- Produces frontend methods `deleteAccount`, `deleteLead`, `deleteStrategyOpportunity`, `deleteBooking`, and `deleteVisit`, each returning `ApiResponse<{ id: string; status: 'Deleted' }>`.
- Produces backend service functions with the same resource names in snake_case and Manager-only behavior.

- [ ] Add adapter contract tests proving each method posts the stable id to its named Frappe method.
- [ ] Add backend tests for each resource: Manager deletes another Sales owner's record; Sales receives permission denied before any delete; referenced documents return a conflict without partial mutation.
- [ ] Run each focused test and observe the missing-method failures.
- [ ] Add a shared service helper that requires `resolve_crm_role() == "Manager"`, verifies read scope, calls `frappe.delete_doc`, and maps link conflicts to `CrmApiException("CONFLICT", ...)`.
- [ ] Add the five whitelisted POST endpoints and frontend/mock implementations.
- [ ] Run focused adapter and backend API tests to green.

### Task 3: R4 frontend delete visibility

**Files:**
- Modify: `src/pages/AccountsPage.vue`
- Modify: `src/pages/LeadDetailPage.vue`
- Modify: `src/pages/OpportunityDetailPage.vue`
- Modify: `src/pages/BookingDetailPage.vue`
- Modify: `src/pages/VisitsPage.vue`
- Modify: their existing page tests.

**Interfaces:**
- Consumes the five delete methods from Task 2 and current bootstrap role/capabilities.
- Produces Manager-only confirmation/delete actions and existing list/detail refresh behavior.

- [ ] Add page tests that mount as Manager and Sales, assert only Manager sees the delete control, perform deletion, and observe the record disappear or route return.
- [ ] Run focused page tests and verify selector/method failures.
- [ ] Add minimal delete buttons using existing button/error patterns; do not add bulk deletion or cascade UI.
- [ ] Run the page tests and the existing Sales routing/permission tests to green.

### Task 4: R5 secure report file detection

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/file_security.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_demo_artifact_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_stage5f_schema.py`

**Interfaces:**
- Extends `detect_mime(content: bytes, file_name: str | None = None) -> str | None` and `validate_and_scan(...) -> str` for XLSX, CSV, and TXT while retaining existing formats.

- [ ] Add literal fixtures for safe XLSX ZIP structure, UTF-8 CSV/TXT, and invalid macro/NUL/mismatched MIME cases.
- [ ] Run focused security tests and verify new safe formats fail as unsupported.
- [ ] Add XLSX package checks (`[Content_Types].xml`, `xl/workbook.xml`, no `vbaProject.bin`) and bounded text detection; keep filename, size, extension, MIME, and scanner checks fail-closed.
- [ ] Run focused tests to green and confirm old PDF/DOCX/image cases still pass.

### Task 5: R5 backend upload transaction and workflow gate

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_demo_artifact/crm_demo_artifact.json`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/demo_artifacts.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/demo_reports.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/evaluations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/evaluations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_demo_report_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_evaluation_api.py`

**Interfaces:**
- `release_demo_test_report(evaluation_id, upload, scanner=None) -> dict` accepts multipart bytes.
- New artifacts write type `Test Report`; reads accept legacy `External Demo Test Report PDF`.
- `Testing -> Internal Review` requires completed run and valid `report_artifact_id`.

- [ ] Add tests for Engineer/Manager upload in scope, Sales denial, arbitrary allowed MIME, version increment, transaction rollback, and transition blocked before upload.
- [ ] Run tests and observe failures from the current fixed-PDF generator and old gate.
- [ ] Replace the report-generation write path with secured private-file/artifact insertion and atomic Evaluation updates; remove PDF-only watermark transformation for non-PDF files.
- [ ] Update the API endpoint to read exactly one multipart file up to `MAX_FILE_BYTES + 1`.
- [ ] Gate `Testing -> Internal Review` on a completed run plus an existing linked Test Report artifact.
- [ ] Run focused backend tests to green.

### Task 6: R5 frontend upload flow

**Files:**
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/types/crm.ts`
- Create: `src/features/evaluations/TestReportUploadModal.vue`
- Create: `src/features/evaluations/TestReportUploadModal.test.ts`
- Modify: `src/features/evaluations/EvaluationWorkspace.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: related evaluation tests.

**Interfaces:**
- Keeps `releaseDemoTestReport(id, file)` but sends multipart in both adapters.
- `DemoArtifactType` includes `Test Report` and the legacy PDF type for reads.

- [ ] Add modal tests for accepted input metadata, empty/oversize/unsupported file rejection, busy state, and emitted `MultipartFilePart`.
- [ ] Add workspace/page tests proving upload appears during Testing after a completed run and advance remains disabled until `reportArtifactId` exists.
- [ ] Run focused tests and observe missing component/incorrect Frappe transport failures.
- [ ] Implement the upload modal and replace the fixed-report builder/configure/release UI path.
- [ ] Make Frappe adapter submit `id` and `file` in one `FormData`; make Mock persist the same semantics.
- [ ] Run evaluation, adapter, and mock tests to green.

### Task 7: R5 Article module

**Files:**
- Create: `src/features/demo-workflow/DemoArticleCard.vue`
- Create: `src/features/demo-workflow/DemoArticleCard.test.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/features/demo-workflow/DemoArchiveDetail.vue`
- Modify: `src/pages/DemoDetailPage.vue`
- Modify: `src/pages/DemoDetailPage.test.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/evaluations.py`

**Interfaces:**
- Consumes artifact metadata including `mimeType`, `createdBy`, `createdAt`.
- Emits `preview(id)` and `download(id)`.

- [ ] Add component tests for Test Report and Demo Request Form grouping, metadata, two independent empty states, preview eligibility, and download emission.
- [ ] Run tests and observe missing component failures.
- [ ] Implement `DemoArticleCard` with `SectionCard`; replace the old ungrouped Artifacts section.
- [ ] Extend workflow serialization with complete artifact metadata and legacy type normalization.
- [ ] Implement preview via object URL for PDF/images/text and download fallback for office formats; revoke object URLs after use.
- [ ] Run component and Demo detail tests to green.

### Task 8: R6 shared pipeline primitives

**Files:**
- Modify: `src/design-system/tokens.css`
- Create: `src/design-system/PipelineBoard.vue`
- Create: `src/design-system/PipelineStageColumn.vue`
- Create: `src/design-system/PipelineCard.vue`
- Modify: `src/features/demo-workflow/DemoPipelineBoard.vue`
- Modify: `src/features/demo-workflow/DemoStageColumn.vue`
- Modify: `src/features/demo-workflow/DemoPipelineCard.vue`
- Modify: `src/features/demo-workflow/DemoPipelineBoard.test.ts`

**Interfaces:**
- `PipelineBoard` accepts ordered `{ key, label, count }[]` stages and exposes a stage slot.
- `PipelineStageColumn` accepts label/count/empty copy and exposes a default card slot.
- `PipelineCard` accepts tone/title/summary/meta/reason and emits `open`.

- [ ] Extend Demo board tests to assert shared components preserve six columns, counts, scroll containment, card open behavior, and empty state.
- [ ] Run tests and confirm they fail before extraction.
- [ ] Add only needed board tokens and implement the three design-system components.
- [ ] Adapt Demo wrappers without changing domain filtering or emitted values.
- [ ] Run Demo board and token tests to green.

### Task 9: R6 Installed Tools board

**Files:**
- Create: `src/features/installed-tools/InstalledToolPipelineBoard.vue`
- Create: `src/features/installed-tools/InstalledToolPipelineBoard.test.ts`
- Modify: `src/pages/InstalledToolsPage.vue`

**Interfaces:**
- Accepts `items: InstalledToolDto[]` and `selectedId?: string`; emits `select(item)`.
- Stage order: FAT, Shipment, Installation, SAT, Warranty.

- [ ] Add literal fixture tests for Current stage, first Waiting fallback, all-Done final stage, progress text, selection, filtering-independent empty columns, and all-empty board.
- [ ] Run the required test and observe the missing component failure.
- [ ] Implement deterministic grouping from `milestones`, render shared pipeline primitives, and display customer/serial/model/Engineer/progress.
- [ ] Mount the board after the existing filter panel and bind selection to current detail/editor state.
- [ ] Run the required test and related Installed Tool page/build tests to green.

### Task 10: Acceptance scripts, matrix, and completion audit

**Files:**
- Modify: `backend/tests/http-stage5d-booking-installed-tool-acceptance.ps1`
- Modify: `backend/tests/http-stage5e-demo-evaluation-acceptance.ps1`
- Modify: `backend/tests/http-stage5f-files-reports-notifications-acceptance.ps1`
- Modify: `C:/Users/PlanckSemicon/Desktop/CRM功能权限可见性矩阵-2026-08-04.md`

**Interfaces:**
- Stage5d asserts milestone data supports board grouping.
- Stage5e asserts Test Execution cannot advance before upload and can after upload.
- Stage5f uploads at least PDF plus one non-PDF allowed format and lists both Article types.

- [ ] Update the three scripts with cleanup-safe test data and literal assertions for the new contracts.
- [ ] Update the permission matrix operations, scope, quick-reference, and change log.
- [ ] Run focused Vitest with workspace-local TEMP/TMP, `pnpm typecheck`, focused backend tests, then stage5d/5e/5f against the available Frappe runtime.
- [ ] Run broader affected frontend and backend suites; inspect `git diff --check`, encrypted-file prefixes, and `git status` for unrelated changes.
- [ ] Audit every R4/R5/R6 requirement against code and test evidence; document any environment-only manual acceptance item.
