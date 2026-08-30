# CRM Stage 5G Read Models and Visits Implementation Plan

> **Execution rule:** Continue with test-driven development, systematic debugging and verification-before-completion. Preserve the current dirty worktree; do not commit, reset, stash or clean.

**Goal:** Close every `CrmApi` backend surface needed before the real Frappe adapter is enabled. Persist Visits in the independent CRM database, project Pipeline/Dashboard/Account360 from canonical CRM rows, preserve the approved read-only boundary for Requirements/Contracts/Controlled Documents, and keep unsupported external ingest data visibly empty rather than fabricating Mock records.

**Architecture:** `CRM Visit` is a lightweight rayher_crm DocType with SQL permission query conditions and server-owned identity. Pipeline and Dashboard are read models over Customer/CRM Opportunity/CRM Booking/CRM Demo Request/CRM Evaluation/CRM Visit; they do not create ERP transaction documents. Requirements, Contracts and Controlled Documents remain explicit read-only external-ingest views and return paginated empty datasets until a separately approved ingest source exists. The legacy Stakeholder page reuses standard Contact plus two CRM custom fields for buying role/influence; Opportunity Stakeholders remain the canonical deal-specific relationship.

## Task 1: Freeze schema and read-model policy

- [x] Write RED tests for CRM Visit DocType, naming, DocPerm, lock whitelist and Sales/Manager SQL scope.
- [x] Write RED tests that the three external-ingest views are implemented, paginated, read-only and empty without source rows.
- [x] Add Contact buying-role/influence compatibility fields without changing Opportunity Stakeholder ownership.
- [x] Migrate twice and verify no ERP Project/Task/Asset/Sales Order/Delivery Note/Quality Inspection rows are created.

## Task 2: Implement Visit workflow

- [x] Write RED create/list/filter/CAS/role/state tests, including forged owner and cross-account contact rejection.
- [x] Implement lightweight Visit service and whitelisted endpoints with date-only fields and stable User IDs.
- [x] Keep advance/edit/complete-action transitions server validated and append notification events in the same savepoint.
- [x] Add authenticated Sales/Manager HTTP acceptance and exact cleanup.

## Task 3: Implement Pipeline and Account360 projections

- [x] Write RED projection tests for canonical Opportunity/Booking fields, totals, scope and account filter.
- [x] Add list_pipeline endpoint and project Strategy Opportunity into the legacy Pipeline DTO without duplicating storage.
- [x] Expand Account360 with scoped Booking/Demo/Evaluation/Visit data; requirements/contracts remain explicit empty read models and actions project canonical Opportunity actions.
- [x] Verify list and Account360 use the same SQL scope and no GET path writes.

## Task 4: Implement Dashboard and compatibility endpoints

- [x] Write RED Dashboard shape/aggregation/scope/date tests over canonical CRM rows.
- [x] Implement Dashboard aggregation with all required keys and zero-valued external-ingest series where no source exists.
- [x] Implement Stakeholder compatibility endpoints through Contact and preserve server-owned owner/reporting validation.
- [x] Implement controlled-document access request as fail-closed validation when the read-only source contains no matching version.

## Task 5: Close Stage 5G

- [x] Rebuild image, migrate twice, run full textual App `OK`, package/Compose contracts and authenticated HTTP acceptance.
- [x] Run frontend full tests/typecheck/build while default adapter remains Mock.
- [x] Verify health, ports, temp identities, read-only GET behavior, old Docker project and all volumes untouched.
- [x] Record all choices/failures/results in repo audit and synchronize the Desktop mirror by SHA-256.

## Acceptance Gate

1. Every current `CrmApi` method has an approved backend endpoint or an explicit read-only empty-source behavior before adapter enablement.
2. Visits persist in the independent CRM database and never create ERP Project/Task/Asset/Sales documents.
3. Pipeline/Dashboard/Account360 derive from the same scoped canonical rows and GET requests are read-only.
4. No Mock seed is presented as Frappe data; Requirements/Contracts/Controlled Documents visibly remain empty until ingest is approved.
