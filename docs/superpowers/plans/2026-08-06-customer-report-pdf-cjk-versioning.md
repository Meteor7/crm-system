# Customer Report PDF CJK and Versioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate readable, polished Chinese Customer Report PDFs and safely issue corrected immutable versions.

**Architecture:** Frappe remains the canonical renderer and ignores browser PDF bytes. The runtime supplies Noto CJK, the service projects display names and structured HTML, and repeated release appends a new artifact version.

**Tech Stack:** Frappe v15, Python, wkhtmltopdf, Noto CJK, pypdf, Docker Compose, Vue 3/Vitest.

## Global Constraints

- Preserve unrelated dirty-worktree changes.
- Never trust client report bytes or overwrite an existing artifact.
- Keep current Test Run values unchanged.

---

### Task 1: Lock the contract with failing tests

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_demo_report_api.py`

**Interfaces:**
- Consumes: `release_demo_test_report(evaluation_id, client_file=None)`.
- Produces: CJK, display-name, report-section and append-only v2 regression coverage.

- [ ] Add Chinese source data and display-name assertions to the real PDF test.
- [ ] Replace the re-release conflict assertion with v2 creation and v1 preservation assertions.
- [ ] Build and run the focused test to observe failure before implementation.

### Task 2: Implement canonical CJK rendering

**Files:**
- Modify: `backend/compose.yaml`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/demo_reports.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/controlled_documents.py`

**Interfaces:**
- Produces: display-name payloads and Noto CJK-backed report/watermark PDFs.

- [ ] Install `fonts-noto-cjk` in the Frappe image.
- [ ] Resolve owner full name with login fallback.
- [ ] Render structured A4 context, performance, conclusion/readiness and integrity sections.
- [ ] Apply the same CJK font stack to controlled-copy watermarks.
- [ ] Rebuild and run focused backend tests.

### Task 3: Implement immutable corrected-version release

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/demo_reports.py`
- Modify: `src/features/evaluations/ExternalReportModal.vue`
- Modify: `src/features/evaluations/ExternalReportModal.test.ts`

**Interfaces:**
- Produces: Customer Review vN+1 release and a `Release corrected version` UI action.

- [ ] Permit a repeated release only in Customer Review with complete run data.
- [ ] Append the new artifact and keep old files/artifacts untouched.
- [ ] Add the corrected-version button label and component test.
- [ ] Run focused backend and frontend tests.

### Task 4: Verify and issue CRM-EVAL-00088 v2

**Files:**
- Output: `output/pdf/external-demo-report-CRM-EVAL-00088-v2-Controlled.pdf`

**Interfaces:**
- Produces: a verified v2 artifact while preserving v1.

- [ ] Run complete focused tests and rebuild/restart the backend.
- [ ] Release `CRM-EVAL-00088` once to create v2.
- [ ] Extract and render every output PDF page; inspect glyphs, spacing, clipping, tables and watermark.
- [ ] Confirm artifact versions 1 and 2 exist and evaluation points to v2.
