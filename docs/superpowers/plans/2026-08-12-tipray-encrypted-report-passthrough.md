# TipRay Encrypted Test Report Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow company-internal TipRay-encrypted Test Reports to upload and download byte-for-byte without decrypting or converting them in CRM.

**Architecture:** The browser snapshots the selected file into memory and sends those exact bytes. The backend recognizes the `%TSD-Header-###%` envelope, derives the accepted logical MIME only from the already-validated filename extension and claimed MIME pair, scans and stores the encrypted payload unchanged, and returns the same bytes through the existing private artifact download path.

**Tech Stack:** Vue 3, TypeScript, FormData, Vitest, Python, Frappe, ClamAV protocol.

## Global Constraints

- Supported logical formats remain PDF, DOCX, XLSX, CSV, TXT, PNG, and JPEG.
- The single-file limit remains 10 MiB.
- Plain files retain existing magic-byte validation.
- TipRay files must begin with `%TSD-Header-###%` and retain identical uploaded/stored bytes.
- No new route, dependency, or artifact type is introduced.

---

### Task 1: Browser multipart passthrough

**Files:**
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`

**Interfaces:**
- Consumes: `releaseDemoTestReport(id: string, file: MultipartFilePart)`.
- Produces: multipart `file` whose bytes equal `file.blob.arrayBuffer()` for both plain and TipRay inputs.

- [ ] Replace the TipRay rejection test with a failing test that calls `releaseDemoTestReport`, extracts the multipart `File`, and asserts its bytes equal the literal `%TSD-Header-###%encrypted` fixture.
- [ ] Run `vitest src/api/frappe-adapter.test.ts` and verify failure is the current `CrmApiError` rejection.
- [ ] Remove only the client-side TipRay rejection branch; retain eager `arrayBuffer()` snapshotting.
- [ ] Rerun the adapter and binary transport tests and verify they pass.

### Task 2: Backend encrypted-envelope validation and storage

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_demo_artifact_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_demo_report_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/file_security.py`

**Interfaces:**
- Consumes: `validate_and_scan(file_name, claimed_mime, content, scanner)`.
- Produces: the claimed allowed MIME for a TipRay envelope only when extension and MIME agree; passes the unchanged encrypted bytes to scanning and storage.

- [ ] Change the file-security test to expect encrypted `.pdf` bytes to return `application/pdf` and reach the scanner unchanged.
- [ ] Add an upload integration test that stores a TipRay report and reads the attached private file back byte-for-byte.
- [ ] Run both backend test modules and verify the current rejection message causes failure.
- [ ] Replace the TipRay rejection with selection of `claimed_mime` only when it is in `EXTENSION_FOR_MIME`; let the common extension/MIME and scanner logic run unchanged.
- [ ] Rerun both modules and verify pass.

### Task 3: Verification and deployment

**Files:**
- Generated: `backend/apps/rayher_crm/rayher_crm/public/crm/**`
- Generated: `backend/build/rayher_crm.zip`

**Interfaces:**
- Consumes: existing Docker Compose deployment at `backend/compose.yaml`.
- Produces: LAN CRM on `0.0.0.0:2224` with byte-preserving TipRay upload support.

- [ ] Run affected frontend tests, typecheck, and Frappe frontend build.
- [ ] Run the complete Frappe test suite.
- [ ] Build the application archive and Docker image.
- [ ] Deploy with `HTTP_BIND_ADDRESS=0.0.0.0` and `HTTP_PORT=2224`.
- [ ] Verify container health, HTTP 200, upload modal rendering, and no browser console errors.
- [ ] Confirm a TipRay fixture retains the same SHA-256 before upload and after private-file storage in the automated integration test.