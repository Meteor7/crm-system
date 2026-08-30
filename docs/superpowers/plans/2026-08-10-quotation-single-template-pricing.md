# Quotation Single Template and Pricing Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make quotation price and discount editing reliable, restrict commercial editing to three month values, and render preview and published PDF from the same Word-aligned server template.

**Architecture:** Frappe remains the authority for validation, normalized values, and template rendering. `get_quotation` and every successful save return `previewHtml` rendered from the same Jinja template that `publish_version` converts to PDF; the Vue page displays that server HTML in a sandboxed iframe. Fixed commercial wording is defined by the backend/template, while only delivery, warranty, and validity months cross the writable API boundary.

**Tech Stack:** Vue 3, TypeScript, Vitest, Frappe/Python, MariaDB DocTypes, Jinja, wkhtmltopdf, Docker Compose.

## Global Constraints

- `Format.doc` is the visual and wording authority.
- Every page header shows `Ref. No.: PKYYYYMMDD-A1`; the date and sequence come from the initial quotation only.
- Only delivery months, warranty months, and validity months are editable commercial values.
- Incoterm, Payment Terms, Installation & Training, Documentation, Packing, and company signature wording are fixed.
- QTY remains a positive whole number.
- Prices are tax-inclusive exact decimals; tax is not split.
- Preview and published PDF use the same Jinja template and context.
- Preserve existing quotations and unrelated dirty-worktree changes.
- Use TipRay-safe trusted writers only; never use Write/Edit/NotebookEdit/apply_patch.

---

### Task 1: Reproduce and lock the price/discount regression

**Files:**
- Modify: `src/pages/QuotationDetailPage.test.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`

**Interfaces:**
- Consumes: existing `QuotationEditor`, autosave queue, `save_draft`.
- Produces: failing behavior tests for unit price, discount selection, persistence, and normalized response values.

- [ ] **Step 1: Add a frontend failing test**

Add a test that changes the device price to `123.45`, chooses Percentage using the user-facing discount control, enters `10`, waits for autosave, and asserts the editor/preview receives `subtotal=123.45`, `discountAmount=12.35`, and `total=111.10`. The production mutation caught is a missing change event, stale autosave payload, or stale server response.

- [ ] **Step 2: Run the frontend test and verify RED**

Run:

`npm.cmd test -- --run src/pages/QuotationDetailPage.test.ts`

Expected: FAIL because the current native discount control and local preview contract do not expose the required reliable interaction/server preview behavior.

- [ ] **Step 3: Add a Frappe integration failing test**

Extend `test_save_draft_persists_exact_money_contacts_and_sites` with literal assertions after saving `unitPrice="123.45"`, `discountType="Percentage"`, and `discountValue="10"`:

```python
self.assertEqual(saved["version"]["subtotal"], "123.45")
self.assertEqual(saved["version"]["discountValue"], "10.00")
self.assertEqual(saved["version"]["discountAmount"], "12.35")
self.assertEqual(saved["version"]["total"], "111.10")
```

Add a second save using `Fixed Amount` and assert the selected type and total survive a fresh `get_quotation`.

- [ ] **Step 4: Run the Frappe test and capture the actual failure boundary**

Run the quotation API test inside the deployed Frappe container with `allow_tests=1`, then restore `allow_tests=0`. Treat textual `FAILED` or `ERROR` as failure even if Bench exits 0. Record whether failure occurs in UI payload creation, service validation, database save, or serialization.

- [ ] **Step 5: Commit the regression tests**

```bash
git add src/pages/QuotationDetailPage.test.ts backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py
git commit -m "test: cover quotation price and discount persistence"
```

### Task 2: Reduce the writable commercial contract to three month values

**Files:**
- Modify: `src/features/quotations/types.ts`
- Modify: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_quotation_version/crm_quotation_version.json`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_schema.py`

**Interfaces:**
- Produces: `QuotationDraftInput.validityMonths: number`; persisted `validity_months`; server-derived `validUntil`.
- Keeps: read-only version snapshots and existing fixed-term database columns for compatibility.

- [ ] **Step 1: Write failing schema and service tests**

Assert the DocType contains required Int field `validity_months` with default `1`. Save `quoteDate="2026-08-10"` and `validityMonths=2`; assert `validUntil="2026-10-10"`, `deliveryMonths=4`, and `warrantyMonths=12`. Assert incoming attempts to change Incoterm or payment terms do not alter fixed output.

- [ ] **Step 2: Run backend tests and verify RED**

Run:

`python -m unittest backend/apps/rayher_crm/rayher_crm/tests/test_quotation_schema.py backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py -v`

Expected: schema and API assertions fail because `validity_months` does not exist and `validUntil` is client-controlled.

- [ ] **Step 3: Implement the minimal backend contract**

Add `validity_months` to the DocType. In `_validated_values`, validate all three month values as positive integers, compute `valid_until = add_months(quote_date, validity_months)`, and ignore client-provided fixed-term fields. Use exact backend constants for the four payment rows and fixed legacy columns. Add `validityMonths` to serialization and version-copy payloads.

- [ ] **Step 4: Narrow the TypeScript draft input**

Define writable fields as contact, site, quote date, validity months, items, discount type/value, delivery months, and warranty months. Keep `validUntil` as a read-only `QuotationVersionDto` field.

- [ ] **Step 5: Run focused backend tests and verify GREEN**

Run the schema, quotation rules, backend contract, and quotation API suites. Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/features/quotations/types.ts backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_quotation_version/crm_quotation_version.json backend/apps/rayher_crm/rayher_crm/services/quotations.py backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py backend/apps/rayher_crm/rayher_crm/tests/test_quotation_schema.py
git commit -m "feat: constrain quotation commercial inputs"
```

### Task 3: Make one server template serve preview and PDF

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/templates/quotation/quotation.html`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py`

**Interfaces:**
- Produces: `render_quotation_html(master, version) -> str`; `QuotationDetailDto.previewHtml: string`.
- Consumes: the same `_pdf_context` for draft preview and PDF release.

- [ ] **Step 1: Write a failing rendered-output test**

Create a draft with two devices and an accessory. Assert `previewHtml` contains the literal header `Ref. No.: PK...`, customer/ATTN data, item hierarchy, exact four payment terms, exact six fixed training/documentation/packing lines, `4月内(标准交期)`, `12个月自发货日起维保`, `报价有效期2个月`, company name, and quote date.

- [ ] **Step 2: Verify RED**

Run the quotation API and backend contract tests. Expected: FAIL because detail responses have no `previewHtml` and the current template differs from `Format.doc`.

- [ ] **Step 3: Implement the shared renderer**

Add one public-in-module `render_quotation_html` that calls `frappe.render_template` with `_pdf_context`. Add its result only for the selected version in `get_quotation`. Change `_release_pdf` to call this same function; no second HTML builder is allowed.

- [ ] **Step 4: Rebuild the Jinja template to match Format.doc**

Implement an A4 template with a fixed repeating page header, right-aligned `Ref. No.:`, Word-aligned party block, item columns, tax-inclusive price note, fixed terms, and signature/date. Escape all data through Jinja defaults and do not include scripts.

- [ ] **Step 5: Verify GREEN and PDF generation**

Run focused backend tests and a real publish integration. Confirm HTML assertions pass and wkhtmltopdf returns a non-empty PDF.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/rayher_crm/rayher_crm/templates/quotation/quotation.html backend/apps/rayher_crm/rayher_crm/services/quotations.py backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py
git commit -m "feat: share quotation preview and PDF template"
```

### Task 4: Replace fragile pricing controls and fixed-term editor

**Files:**
- Modify: `src/features/quotations/QuotationEditor.vue`
- Modify: `src/features/quotations/QuotationPreview.vue`
- Modify: `src/pages/QuotationDetailPage.vue`
- Modify: `src/pages/QuotationDetailPage.test.ts`

**Interfaces:**
- Consumes: `QuotationDetailDto.previewHtml`, narrowed `QuotationDraftInput`.
- Produces: explicit discount buttons and sandboxed server-template preview.

- [ ] **Step 1: Add failing component behavior assertions**

Assert three discount buttons exist; selecting Percentage enables the value input; selecting None resets it to `0.00`. Assert only delivery, warranty, and validity month controls are editable in the commercial area. Assert preview iframe `srcdoc` equals the last successful server `previewHtml`.

- [ ] **Step 2: Verify RED**

Run `npm.cmd test -- --run src/pages/QuotationDetailPage.test.ts`. Expected: FAIL on missing controls and preview contract.

- [ ] **Step 3: Implement explicit controlled pricing actions**

Replace the native discount select with three buttons. `setDiscountType` updates the model, resets None to `0.00`, emits one changed event, and never relies on bubbled native select events. Give unit-price and discount inputs explicit labels and input handlers so a price edit always increments the autosave revision.

- [ ] **Step 4: Simplify commercial inputs and preview**

Remove direct editing of valid-until date, Incoterm, payment rows, delivery/warranty start text, installation, training, documentation, and packing. Show only three positive integer month fields. Make `QuotationPreview.vue` render a sandboxed iframe from server HTML, with no local quotation layout.

- [ ] **Step 5: Verify GREEN**

Run the focused page test and quotation API contract test. Expected: all pass and the saved payload contains only writable fields.

- [ ] **Step 6: Commit**

```bash
git add src/features/quotations/QuotationEditor.vue src/features/quotations/QuotationPreview.vue src/features/quotations/types.ts src/pages/QuotationDetailPage.vue src/pages/QuotationDetailPage.test.ts
git commit -m "fix: make quotation pricing controls persist"
```

### Task 5: Protect save consistency and legacy quotations

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`
- Modify only if test proves necessary: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Modify only if test proves necessary: `backend/apps/rayher_crm/rayher_crm/api/v1/errors.py`

**Interfaces:**
- Consumes: optimistic-lock token and existing unexpected-exception rollback.
- Produces: no partial write and deterministic legacy defaults.

- [ ] **Step 1: Add integration tests**

Force serialization/rendering failure after validation and assert the transaction is rolled back. Load existing versions with missing `validity_months` and assert a safe value derived from quote date/valid-until, falling back to one month only when dates are not an exact natural-month interval.

- [ ] **Step 2: Verify RED or existing protection**

Run the integration tests. If rollback already passes, retain the test without changing `errors.py`. If legacy serialization fails, implement only the normalization necessary in `quotations.py`.

- [ ] **Step 3: Run all quotation backend tests**

Expected: no failure, no database reset, and no deletion of existing quotation records.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py backend/apps/rayher_crm/rayher_crm/services/quotations.py backend/apps/rayher_crm/rayher_crm/api/v1/errors.py
git commit -m "test: protect quotation save consistency"
```

### Task 6: Build, deploy, and execute full QA

**Files:**
- Verify only: frontend, backend, Docker runtime, existing quotation data.

**Interfaces:**
- Produces: LAN deployment at `http://203.0.113.10:2224/crm`.

- [ ] **Step 1: Run final automated verification**

Run all frontend tests, all local quotation/backend contract tests, and the real Frappe quotation integration suite. Reject textual `FAILED` or `ERROR`.

- [ ] **Step 2: Build and deploy**

Run `npm.cmd run build:frappe`, prepare the app build context, then `docker compose --env-file backend/.env.lan -f backend/compose.yaml build` and `up -d`.

- [ ] **Step 3: Migrate schema safely**

Run Frappe migrate against the existing site. Do not reset, truncate, delete, or backfill existing quotation data destructively.

- [ ] **Step 4: Browser QA every writable function**

Using the authenticated LAN session, select contact and site, change device and charged-accessory prices, test None/Percentage/Fixed Amount, change all three month values, reload after each save, create a new version, preview, publish, and download PDF. Restore temporary test edits where practical.

- [ ] **Step 5: Compare preview and PDF**

Verify identical reference header, customer/ATTN block, item order, totals, fixed terms, three generated clauses, company name, and date. For a multi-page quotation, confirm the reference number repeats in every page header.

- [ ] **Step 6: Runtime health checks**

Confirm backend/frontend healthy, LAN HTTP 200, `allow_tests=0`, existing quotations preserved, and browser console has no errors.

- [ ] **Step 7: Final handoff**

Report changed behavior, automated test counts, real QA evidence, deployment URL, and any residual risk.
