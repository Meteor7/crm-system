# Browser Session Cookie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Frappe's `sid` a browser-session Cookie so closing the browser process removes client authentication while refreshes in the same browser session remain authenticated.

**Architecture:** A small `rayher_crm.security.session_cookie` module mutates only the pending `sid` Cookie options during Frappe's `after_request` phase, before the framework flushes cookies. The pure mutation helper is tested without Frappe; the registered Hook delegates to it and preserves all security flags and server-side session behavior.

**Tech Stack:** Python 3.11, Frappe v15 request hooks and CookieManager, stdlib unittest/Frappe test runner, PowerShell package contract, Docker Compose.

## Global Constraints

- Do not modify Frappe or ERPNext framework source.
- Do not read, print, log, or persist any password, Token, Cookie value, or session identifier.
- Preserve `HttpOnly`, `SameSite=Lax`, and HTTPS `Secure`; change only `sid.max_age` and `sid.expires` to `None`.
- Preserve the server-side `session_expiry=170:00`, standard logout behavior, refresh behavior, and all non-`sid` cookies.
- Do not update other Stage work, B1, Ubuntu Staging, or unrelated code.
- Do not commit, reset, stash, clean, stop containers, or delete Docker volumes.

---

### Task 1: Session Cookie Mutation and Hook Registration

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/security/__init__.py`
- Create: `backend/apps/rayher_crm/rayher_crm/security/session_cookie.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_session_cookie.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/hooks.py`

**Interfaces:**
- Produces: `make_sid_cookie_session_only(cookie_manager: object) -> None`
- Produces: `enforce_browser_session_cookie(response: object | None = None, request: object | None = None) -> None`
- Registers: `after_request = ["rayher_crm.security.session_cookie.enforce_browser_session_cookie"]`

- [ ] **Step 1: Write the failing pure behavior test**

Create a stdlib `unittest.TestCase` that constructs a fake manager with a real `cookies` dictionary. Assert that a pending `sid` with literal `max_age=612000` and a literal expiry becomes `None` for those two fields, while `httponly`, `samesite`, `secure`, the Cookie value, and an unrelated Cookie remain unchanged. Add separate tests proving missing and malformed `sid` values are no-ops.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:PYTHONPATH = 'backend/apps/rayher_crm'
python -m unittest rayher_crm.tests.test_session_cookie -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rayher_crm.security'`; this proves the new behavior does not exist.

- [ ] **Step 3: Implement the minimal pure helper and Frappe Hook**

Implement `make_sid_cookie_session_only` with defensive `getattr`/mapping checks. If and only if `cookies["sid"]` is a mutable mapping, assign `None` to `max_age` and `expires`. Implement the Hook with a function-local `import frappe`, retrieve `frappe.local.cookie_manager` safely, and delegate to the helper. Register that Hook in `hooks.py`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same unittest command and require all three tests to pass without warnings.

- [ ] **Step 5: Run the package contract**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File backend/tests/app-package-contract.ps1
```

Expected: `App package contract passed.`

### Task 2: Packaged Frappe and Runtime Verification

**Files:**
- Modify: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Generated: `backend/build/rayher_crm.zip`
- Generated: `backend/apps/rayher_crm/rayher_crm/public/crm/**`

**Interfaces:**
- Consumes: registered `after_request` Hook from Task 1.
- Produces: local Docker runtime whose `sid` response Cookie has no persistence attributes.

- [ ] **Step 1: Build the Frappe frontend and verified app archive**

Run `npm.cmd run build:frappe`, then `powershell -ExecutionPolicy Bypass -File backend/scripts/prepare-app-build-context.ps1`. Require success and no protected wrapper in the archive.

- [ ] **Step 2: Rebuild only the application image and recreate application services**

Run the existing `docker compose -f backend/compose.yaml build` and `docker compose -f backend/compose.yaml up -d` workflow. Do not run `down`, stop database/Redis/ClamAV, or remove volumes.

- [ ] **Step 3: Run the packaged backend regression**

Temporarily set `allow_tests=true`, run `bench --site rayher-crm.localhost run-tests --app rayher_crm`, and restore `allow_tests=false` in a `finally` block. Require zero failures.

- [ ] **Step 4: Verify the real Cookie boundary without exposing its value**

Inside the packaged Frappe test environment, construct a pending `sid` through the real `CookieManager`, invoke the registered Hook through Frappe's hook loader, flush to a Werkzeug response, and assert programmatically that the `sid` header contains `HttpOnly` and `SameSite=Lax` but not `Max-Age` or `Expires`. Output only boolean assertions/counts, never the header or Cookie value.

- [ ] **Step 5: Run complete local regressions**

Run TypeScript typecheck, all 524+ Vitest tests, Frappe production build, container health inspection, and unauthenticated HTTP ping. Require `allow_tests=false` after testing.

- [ ] **Step 6: Update and synchronize the audit record**

Append the selected design, exact changed files, RED/GREEN evidence, packaged backend results, Cookie attribute booleans, container health, test-switch restoration, and the browser session-restoration limitation to the repository audit log. Copy it to `C:\Users\PlanckSemicon\Desktop\CRM-持续执行审计日志-2026-08-04.md` and require matching SHA-256 hashes.

- [ ] **Step 7: Stop further Stage work**

Record that no other Stage, B1, or Ubuntu Staging work was performed, leave Git changes uncommitted, and pause after reporting the verified result.

### Task 3: Controlled Document Watermark Service and Binary API

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/controlled_documents.py`
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/controlled_documents.py`
- Create: `backend/apps/rayher_crm/rayher_crm/tests/test_controlled_document_delivery.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/read_only_views.py`

**Interfaces:**
- Produces: `render_controlled_document(document_id: str, action: Literal["preview", "download"]) -> dict[str, object]`
- Produces GET endpoints `preview_document(documentId: str)` and `download_document(documentId: str)` returning raw PDF responses.

- [ ] **Step 1: Write failing service tests**

Create Frappe tests that use the installed Mushi private PDF and assert authorized Manager/Sales delivery, watermarked PDF text on every page, unique access IDs, source/output byte inequality, audit actions, denied Guest access, and fail-closed behavior for an invalid private-file association.

- [ ] **Step 2: Run the focused backend test and verify RED**

Package only the failing test into the local app image or test source context and run `bench --site rayher-crm.localhost run-tests --app rayher_crm --module rayher_crm.tests.test_controlled_document_delivery`. Require failure because the delivery service/module is missing.

- [ ] **Step 3: Implement minimal secure delivery**

Load only `CRM Controlled Document` and its linked private File, enforce server identity/capability/status/access, generate per-request audit ID and Shanghai timestamp, build a repeated diagonal overlay with Frappe `get_pdf`, merge it on every source page with `pypdf`, record append-only access audit, and return bytes plus sanitized filename and access ID. Never return source bytes on any failure.

- [ ] **Step 4: Add raw API wrappers and verify GREEN**

Set Frappe response type, filename, display-content-as attachment flag, no-store headers and generated bytes in two thin whitelisted GET wrappers. Run the focused test and require all cases to pass.

### Task 4: Controlled Document Frontend Preview and Download

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/pages/DocumentCenterPage.vue`
- Modify: `src/pages/DocumentCenterPage.test.ts`

**Interfaces:**
- Adds `CrmApi.previewControlledDocument(documentId: string): Promise<BinaryDownload>`.
- Adds `CrmApi.downloadControlledDocument(documentId: string): Promise<BinaryDownload>`.

- [ ] **Step 1: Write failing adapter and page tests**

Assert exact raw GET method routing and binary response parsing. Mount a Frappe-mode page with a complete fake `CrmApi`, assert Manager sees the library, preview Blob becomes an object URL in the real PDF element, download invokes the binary method and `downloadBlob`, errors are visible, and URLs are revoked on switch/unmount. Retain the existing Mock Manager approval assertion.

- [ ] **Step 2: Run focused Vitest and verify RED**

Run `npm.cmd run test -- --run src/api/frappe-adapter.test.ts src/pages/DocumentCenterPage.test.ts`. Require failure on missing methods/real preview behavior.

- [ ] **Step 3: Implement minimal adapter and UI behavior**

Add endpoint mappings and binary methods, keep mock methods explicit, replace the Frappe schematic preview with authenticated Blob preview, connect download to `downloadBlob`, manage object URL lifecycle, and gate Manager approval workspace with `usingMock`.

- [ ] **Step 4: Run focused Vitest and verify GREEN**

Run the same focused test command and require zero failures, then run typecheck.

### Task 5: Combined Package, Runtime, and Audit Closure

**Files:**
- Modify: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Generated: verified app archive and Frappe frontend assets.

- [ ] **Step 1: Build one combined verified archive and update application containers**

Run production Frappe build, build-context verification, Compose build and `up -d`; do not run `down` or alter volumes.

- [ ] **Step 2: Run all backend and frontend regressions**

Require backend Frappe suite, full Vitest, typecheck, package/frontend contracts, PDF watermark probe, Cookie attribute probe, container health and HTTP ping to pass; restore `allow_tests=false` in `finally`.

- [ ] **Step 3: Record and synchronize evidence**

Append exact RED/GREEN evidence, changed boundaries, generated PDF assertions without values, Cookie attribute booleans, tests, health, limitations and no-destructive-action statement to the repository audit log. Synchronize the desktop copy and verify matching SHA-256.
