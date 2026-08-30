# Quotation Adversarial Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the confirmed Quotation data-integrity, pricing, selector-completeness, stale-preview, stale-tab, reference-migration, and validation defects while preserving the approved document template and all existing records.

**Architecture:** Extend the pure quotation rules with parent-group totals, protect lifecycle writes at the service boundary, enforce a database compound invariant, and keep migration logic in an idempotent Frappe patch. Add small frontend paging and request-order helpers inside the existing pages rather than introducing dependencies.

**Tech Stack:** Python 3/Frappe v15/MariaDB, Vue 3/TypeScript, Vitest, unittest, Docker Compose.

## Global Constraints

- Preserve all existing quotation masters, versions, statuses, owners, opportunities, and history.
- Reference format is `PKYYYYMMDD-A<n>` based on the initial quotation date.
- Parent configuration unit price is `(device line amount + charged child line amounts) / device quantity`.
- Quantity remains a positive integer; money remains exact decimal input.
- Keep the approved Word-derived header, footer, fixed terms, CNY inclusive-tax behavior, and no-watermark behavior.
- Do not add quotation keyword search or catalog import.
- Use trusted command-line writers only because TipRay corrupts direct editor writes.

---

### Task 1: Parent configuration totals and bounded validation

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotation_rules.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/templates/quotation/quotation.html`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_rules.py`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`

**Interfaces:**
- `calculate_totals(...)` additionally returns `deviceGroups: list[dict[str, str]]` with `lineKey`, `configurationSubtotal`, and `configurationUnitTotal`.
- `_validated_values(...)` rejects more than 200 rows, text above schema limits, and months outside 1..120.

- [ ] Write a failing pure-rule test with two differently priced devices and charged/included accessories. Assert literal group totals and ensure the former whole-document average cannot satisfy it.
- [ ] Run `python -m unittest rayher_crm.tests.test_quotation_rules -v` and confirm the new assertion fails because `deviceGroups` is absent.
- [ ] Implement group accumulation with exact `Decimal` arithmetic and expose group totals to `_pdf_context`.
- [ ] Add failing service/API tests for 201 rows, 141-character names/models, 5,001-character descriptions, and month values 0/121.
- [ ] Implement minimal input bounds and stable validation errors.
- [ ] Update the template to render each parent group total without changing fixed sections.
- [ ] Run the focused backend suites and confirm all pass.

### Task 2: Lifecycle concurrency, lookup errors, and database invariant

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/quotations.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/setup/indexes.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_backend_contract.py`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/quotation-contract.test.ts`

**Interfaces:**
- `discard_draft(name, expected_modified)` and `record_decision(..., expected_modified)` lock the current version.
- Frontend `discardQuotationDraft(id, expectedModified)` and decision input field `expectedModified` propagate the optimistic token.
- `ensure_indexes()` creates unique index `uq_crm_quotation_version_number` on `(quotation, version_no)`.

- [ ] Write failing Frappe tests proving stale discard/decision requests return `VERSION_CONFLICT`, foreign/missing versions return domain errors, and duplicate `(quotation, version_no)` is rejected.
- [ ] Run the focused integration test and confirm expected failures.
- [ ] Lock the quotation master with `SELECT ... FOR UPDATE` before version allocation and add the compound unique index.
- [ ] Use `lock_document` for discard and decision; validate selected version ownership before `get_doc` serialization/rendering.
- [ ] Write failing frontend contract tests for `expectedModified` payloads, then update API types and adapter.
- [ ] Run backend and frontend contract suites.

### Task 3: Complete pagination and ordered preview refresh

**Files:**
- Modify: `src/pages/QuotationDetailPage.vue`
- Modify: `src/pages/QuotationDetailPage.test.ts`
- Modify: `src/pages/QuotationsPage.vue`
- Modify: `src/pages/QuotationsPage.test.ts`

**Interfaces:**
- Detail page internal `loadAllContacts(accountId)` reads pages of 200 until loaded count reaches `meta.total`.
- Creation modal internal `loadAllOpportunities()` reads all pages of 200.
- Quotation list tracks `page`, `pageSize=50`, and response `meta.total`.
- `refreshPreview` uses an incrementing token; only the latest token can replace `previewUrl`.

- [ ] Add failing component tests for two contact pages, two Opportunity pages, quotation next-page navigation, selector-only contact failure, and reversed preview response order.
- [ ] Run the focused Vitest files and confirm each new test fails for the named behavior.
- [ ] Implement paging loops, visible quotation pager, and isolated selector errors.
- [ ] Implement preview sequence protection and revoke ignored object URLs.
- [ ] Add failing tests for focus refresh with no pending edits and no refresh while edits are queued.
- [ ] Implement focus/visibility listeners with cleanup on unmount.
- [ ] Run the focused Vitest files.

### Task 4: Idempotent reference migration

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/patches/v1_0/normalize_quotation_reference_numbers.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/patches.txt`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`

**Interfaces:**
- Patch `execute()` deterministically assigns per-date suffixes, updates master and all versions, and regenerates attached formal PDFs.
- A rerun produces the same references and does not create extra quotation/version records.

- [ ] Add a failing Frappe integration test with malformed and old-format references on the same initial date; assert deterministic `-A1/-A2`, version alignment, regenerated header bytes, preserved counts, and idempotence.
- [ ] Run the integration test and confirm failure before the patch exists.
- [ ] Implement two-phase temporary/final reference assignment and formal PDF regeneration.
- [ ] Register the patch once in `patches.txt`.
- [ ] Run the integration test twice and inspect database invariants.

### Task 5: Full verification and LAN deployment

**Files:**
- No new behavior; verify all modified files and runtime state.

- [ ] Run focused Vitest Quotation suites and `npm.cmd run typecheck`.
- [ ] Run pure backend Quotation suites.
- [ ] Rebuild the Frappe asset package and Docker image.
- [ ] Run migrations and Frappe Quotation integration tests; explicitly reject output containing `FAILED` or `ERROR` even if the command exit code is zero.
- [ ] Restore `allow_tests` to `0`.
- [ ] Verify existing quotation/version counts, compound uniqueness, migrated references, formal PDF header references, and no record deletion.
- [ ] Verify Docker services healthy and LAN HTTP 200.
- [ ] Browser QA contact/site selection, integer quantity, price and discount save/echo, commercial-month save, preview order, publish/download, history, and header reference.
- [ ] Review `git diff --check` and report any remaining risk without claiming unverified success.