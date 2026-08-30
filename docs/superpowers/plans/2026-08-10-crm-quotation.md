# CRM Quotation Full-Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Sales Quotation module end-to-end with Frappe persistence, versioning, pricing, private PDF release, Opportunity linkage, and Contacts-style frontend interaction.

**Architecture:** A `CRM Quotation` aggregate indexes one Opportunity, while immutable `CRM Quotation Version` documents own item and payment child tables. A focused service layer enforces permissions, transitions, calculations and snapshotting; Vue consumes it through the existing `CrmApi`/Frappe adapter boundary.

**Tech Stack:** Vue 3, TypeScript, Vue Router, Vitest, Frappe/ERPNext, Python, MariaDB DocTypes, Frappe print/PDF APIs.

## Global Constraints

- One Opportunity has exactly one quotation aggregate.
- CNY tax-inclusive pricing only; no tax breakdown.
- Sales sees own records, Manager sees all, Engineer has no access.
- Published and historical versions are immutable.
- The frontend must reuse Contacts list/detail interaction and existing design-system components.
- Formal persistence is Frappe only; Mock is test support, never the runtime source of truth.
- Preserve all unrelated dirty-worktree changes.

---

### Task 1: Quotation schema and permission contract

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_quotation/**`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_quotation_version/**`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_quotation_item/**`
- Create: `backend/apps/rayher_crm/rayher_crm/rayher_crm/doctype/crm_quotation_payment_term/**`
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/roles.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/permissions/scope.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/hooks.py`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_schema.py`

**Interfaces:**
- Produces DocTypes and `quotation:view`, `quotation:write`, `quotation:publish` capabilities.

- [ ] Write schema tests asserting unique Opportunity/Ref No., child relationships, DocPerms and Engineer denial.
- [ ] Run the focused test and verify it fails because the quotation schema is absent.
- [ ] Add the four DocTypes plus capability and row-scope wiring.
- [ ] Run the focused test and verify it passes.

### Task 2: Pricing and lifecycle domain service

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/services/quotations.py`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_service.py`

**Interfaces:**
- Produces `list_quotations`, `get_quotation`, `create_quotation`, `save_draft`, `create_version`, `publish_version`, `record_decision`, `download_pdf`.

- [ ] Write failing tests for CNY pricing, Included accessories, discount exclusivity, 100% payment validation, one-Opportunity uniqueness, version promotion, immutability, expiry and Accepted Opportunity transition.
- [ ] Run the service test and confirm the expected missing-service failures.
- [ ] Implement validation, serialization, owner scope, snapshot copying, status transitions and deterministic totals.
- [ ] Run the service test and verify it passes.

### Task 3: API and private PDF release

**Files:**
- Create: `backend/apps/rayher_crm/rayher_crm/api/v1/quotations.py`
- Create: `backend/apps/rayher_crm/rayher_crm/templates/quotation/quotation.html`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_quotation_api.py`

**Interfaces:**
- Produces Frappe v1 endpoints matching frontend `CrmApi` methods and a private immutable PDF response.

- [ ] Write failing API tests for CRUD, autosave, publish, history, decision and binary download permission.
- [ ] Run the API test and confirm endpoints are missing.
- [ ] Implement whitelisted endpoints and server-side HTML/PDF generation from the persisted version snapshot.
- [ ] Run API tests and verify Sales/Manager success and Engineer denial.

### Task 4: Frontend API contract and quotation domain types

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/mock-adapter.ts`
- Test: `src/api/quotation-contract.test.ts`

**Interfaces:**
- Produces typed quotation DTO/input types and adapter methods for list/detail/draft/version/publish/decision/PDF.

- [ ] Write a failing adapter contract test asserting exact Frappe method names and request payloads.
- [ ] Run the test and confirm missing contract methods.
- [ ] Add types and Frappe methods; keep Mock implementation isolated to tests.
- [ ] Run the contract test and typecheck the changed boundary.

### Task 5: Contacts-style list, routes and navigation

**Files:**
- Create: `src/pages/QuotationsPage.vue`
- Create: `src/pages/QuotationsPage.test.ts`
- Modify: `src/app/router.ts`
- Modify: `src/app/navigation.ts`
- Test: `src/app/router-sales.test.ts`

**Interfaces:**
- Produces `/quotations` and `/quotations/:quotationId` routes plus Sales navigation entry.

- [ ] Write failing component/router tests for four key columns, filters, entire-row detail navigation and Engineer-hidden navigation.
- [ ] Run tests and confirm missing page/route.
- [ ] Implement the PageHeader/FilterBar/crm-table page using Contacts interaction patterns.
- [ ] Run list and router tests.

### Task 6: Detail editor, autosave preview and history

**Files:**
- Create: `src/pages/QuotationDetailPage.vue`
- Create: `src/pages/QuotationDetailPage.test.ts`
- Create: `src/features/quotations/QuotationEditor.vue`
- Create: `src/features/quotations/QuotationPreview.vue`
- Create: `src/features/quotations/QuotationHistory.vue`

**Interfaces:**
- Consumes quotation API types and endpoints.
- Produces structured device/accessory/payment/terms editing, latest-version summary, preview and historical version selection.

- [ ] Write failing tests for parent/child lines, pricing, one-second autosave, stale-response protection, publish gating, decision capture, PDF-only-after-publish and history read-only behavior.
- [ ] Run tests and confirm components are absent.
- [ ] Implement the shared detail editor using existing PageHeader, SectionCard, DataState and StatusBadge components.
- [ ] Run detail tests and typecheck.

### Task 7: Opportunity entry and end-to-end verification

**Files:**
- Modify: `src/pages/OpportunityDetailPage.vue`
- Test: `src/pages/OpportunityDetailPage.test.ts`

**Interfaces:**
- Produces New/View/Create Version entry actions into the single quotation aggregate.

- [ ] Write failing Opportunity-detail tests for quotation entry action selection.
- [ ] Run the focused test and confirm actions are absent.
- [ ] Add the narrow entry actions and route behavior.
- [ ] Run all quotation tests, backend focused tests, `pnpm typecheck`, and `pnpm build:frappe`.
- [ ] Inspect the final diff to confirm only quotation-required files and explicitly touched integration files changed.
