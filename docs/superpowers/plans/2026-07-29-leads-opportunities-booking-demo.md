# Leads&Opportunities and Booking Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a stable Mock Demo where Leads and Opportunities share one `Leads&Opportunities` workspace, Lead qualification converts into Account/Contact/Opportunity exactly once, and Booking is an independent crash-safe module.

**Architecture:** Extend the existing versioned sales repository with Lead records and conversion metadata. Expose Lead reads/writes/conversion through the existing `CrmApi`, keep Frappe mutations explicitly unsupported, and reuse the current opportunity workspace in embedded mode rather than rebuilding its deep features. Build Booking as an isolated route whose own list load is independent from optional reference-data loads.

**Tech Stack:** Vue 3, TypeScript, Vite, Pinia, Element Plus, Vitest, Vue Test Utils, existing Mock/Frappe adapters and localStorage repository.

## Global Constraints

- Keep the exact user-facing name `Leads&Opportunities`; do not introduce “Sales 工作区”.
- Preserve unrelated user changes in the dirty worktree and do not add dependencies.
- Treat Lead as separate from Contact until conversion.
- Allow conversion only from `Qualified`; conversion must be idempotent and record created/reused entities.
- Preserve the existing Opportunity edit, stakeholder, action, commercial forecast, history, strengths, red flags, and information-needed behavior.
- Equipment Booking must come from a Won Opportunity. Renewal/Maintenance may be created directly only with a source and reason.
- Frappe Lead/Booking mutations remain `NOT_IMPLEMENTED`; this delivery is a Mock Demo.
- Write a failing test before each production change and run it to observe the expected failure.

---

## Task 1: Add the Lead domain and versioned persistence

**Files:**

- Modify: `src/types/crm.ts`
- Modify: `src/demo/sales-repository.ts`
- Modify: `src/demo/sales-repository.test.ts`
- Create: `src/demo/leads-data.ts`

- [ ] Add a failing repository migration test proving that a version 3 snapshot migrates to version 4 with seeded Leads and preserves contacts, opportunities, bookings, and visits.
- [ ] Add a failing repository test proving Lead conversion metadata survives repository save/load cloning and that an already-converted Lead remains converted.
- [ ] Run `pnpm.cmd test -- src/demo/sales-repository.test.ts` and confirm the failure is caused by missing Lead/version-4 behavior.
- [ ] Define `LeadStatus`, `LeadSource`, `LeadDto`, `LeadInput`, `LeadConversionInput`, and `LeadConversionResult` in `src/types/crm.ts`.
- [ ] Add realistic semiconductor Lead seeds in `src/demo/leads-data.ts`, including at least one Lead for each important demo status and one `Qualified` Lead ready to convert.
- [ ] Add `SalesSnapshotV4` with `leads`, migrate versions 1–3 to version 4, keep legacy contact/bookings/opportunity migrations intact, validate stored v4 snapshots, and retain the existing localStorage key for a seamless demo migration.
- [ ] Run `pnpm.cmd test -- src/demo/sales-repository.test.ts` and confirm it passes.

## Task 2: Implement Lead API operations and idempotent conversion

**Files:**

- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`

- [ ] Add failing Mock adapter tests for Lead list filtering by search/status/owner/source and account scope.
- [ ] Add failing Mock adapter tests for Lead detail, create/update validation, and permission enforcement.
- [ ] Add failing conversion tests proving:
  - non-Qualified Leads are rejected;
  - a Qualified Lead creates or reuses Account and Contact;
  - conversion creates a Strategy Opportunity linked by conversion metadata;
  - a second conversion call returns the original result without creating duplicates.
- [ ] Run `pnpm.cmd test -- src/api/mock-adapter.test.ts` and confirm failures are caused by missing Lead API methods.
- [ ] Extend `CrmApi` with `listLeads`, `getLead`, `saveLead`, and `convertLead`.
- [ ] Implement Mock list/detail/save with `deal:view` and `deal:write`, trim/validate required fields, and persist through the shared sales repository.
- [ ] Implement conversion as one atomic in-memory operation: validate status, resolve/create Account, resolve/create active Contact, create Strategy Opportunity, mark the Lead Converted, store conversion IDs/timestamp, save once, and return the same recorded result on retries.
- [ ] Add Frappe read/write methods that explicitly reject with `NOT_IMPLEMENTED` so the adapter satisfies the contract without implying backend delivery.
- [ ] Run:
  - `pnpm.cmd test -- src/api/mock-adapter.test.ts`
  - `pnpm.cmd test -- src/api/frappe-adapter.test.ts`

## Task 3: Build Lead list and Contact-style Lead detail

**Files:**

- Create: `src/features/leads/LeadEditorModal.vue`
- Create: `src/features/leads/LeadConvertModal.vue`
- Create: `src/features/leads/LeadListView.vue`
- Create: `src/pages/LeadDetailPage.vue`
- Create: `src/pages/leads.test.ts`
- Reference without changing its data model: `src/pages/ContactDetailPage.vue`
- Modify only shared workspace styles when necessary: `src/design-system/workspace.css`

- [ ] Add failing page tests for list loading, search/status/source filters, empty/error/denied states, opening `/leads/:leadId`, and role-aware create/edit controls.
- [ ] Add failing detail tests proving the page renders Lead identity, company, title, phone, email, source, status, owner, first-contact notes, timeline, and safely handles optional reference failures.
- [ ] Add failing conversion UI tests proving the Convert action is only visible for writable Qualified Leads and successful conversion shows links/IDs for Account, Contact, and Opportunity.
- [ ] Run `pnpm.cmd test -- src/pages/leads.test.ts` and confirm the tests fail for missing components.
- [ ] Build `LeadListView.vue` with Salesforce-inspired density adapted to the existing PLANCK design system: compact toolbar, filters, table, status badges, row navigation, and clear loading/empty/error states.
- [ ] Build `LeadEditorModal.vue` for the approved core fields without turning a Lead into a Contact prematurely.
- [ ] Build `LeadDetailPage.vue` by reusing the visual skeleton and card rhythm of Contact detail while loading Lead-specific data through `getLead`.
- [ ] Build `LeadConvertModal.vue` with account reuse/create choice, contact reuse/create choice, opportunity name, amount, target close date, owner, and conversion result summary.
- [ ] Run `pnpm.cmd test -- src/pages/leads.test.ts` and confirm it passes.

## Task 4: Create the combined Leads&Opportunities workspace while preserving Opportunity depth

**Files:**

- Create: `src/pages/LeadsOpportunitiesPage.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/pages/opportunity-strategy-operations.test.ts`
- Create: `src/pages/leads-opportunities.test.ts`

- [ ] Add a failing workspace test proving the visible title is `Leads&Opportunities`, the initial tab is Leads, and the user can switch to Opportunities without a horizontal Sales navigation bar.
- [ ] Add a failing compatibility test proving query `view=opportunities` opens the Opportunity tab and existing opportunity filters/create query behavior still works.
- [ ] Add a failing Opportunity regression test for edit, stakeholder, action, commercial forecast, history, strengths, red flags, and information-needed content in embedded mode.
- [ ] Run the two focused test files and confirm the expected failures.
- [ ] Add an `embedded` prop to `OpportunityStrategyPage.vue`; in embedded mode hide only its retired outer title/navigation shell and keep all existing Opportunity data loads, dialogs, and deep detail content.
- [ ] Remove Booking mode switching and Booking-only loading/dialog wiring from the embedded Opportunity experience; retain only compatibility behavior needed for legacy query redirects.
- [ ] Build `LeadsOpportunitiesPage.vue` as the single vertical page shell with a compact Leads/Opportunities segmented switch, rendering `LeadListView` or embedded `OpportunityStrategyPage`.
- [ ] Keep tab state in the route query so links and browser back/forward remain deterministic.
- [ ] Run:
  - `pnpm.cmd test -- src/pages/leads-opportunities.test.ts`
  - `pnpm.cmd test -- src/pages/opportunity-strategy-operations.test.ts`

## Task 5: Split Booking into a crash-safe independent module

**Files:**

- Create: `src/pages/BookingPage.vue`
- Modify: `src/features/opportunities/BookingEditorModal.vue`
- Create: `src/pages/booking.test.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/api/mock-adapter.ts`

- [ ] Add failing Booking page tests proving the module renders independently when accounts, contacts, sites, or opportunities fail to load.
- [ ] Add failing tests for loading, empty, permission-denied, malformed relation, and Booking API error states; none may crash the component.
- [ ] Add failing policy tests proving Equipment bookings require a Won source Opportunity, while Renewal/Maintenance require `directSource` and `directReason` when no opportunity is selected.
- [ ] Run `pnpm.cmd test -- src/pages/booking.test.ts src/api/mock-adapter.test.ts` and confirm the expected failures.
- [ ] Add `bookingType: 'Equipment' | 'Renewal' | 'Maintenance'`, `directSource`, and `directReason` to Booking DTO/input, with a repository migration defaulting legacy rows to Equipment.
- [ ] Enforce the source policy in the Mock adapter and ensure optional relationship expansion never dereferences missing Account, Contact, or Opportunity records.
- [ ] Update `BookingEditorModal.vue` so Won Opportunity selection prefills account/contact/equipment/amount when available; direct bookings reveal and require source/reason fields.
- [ ] Build `BookingPage.vue` with an independent title, summary cards, filters, list, modal, and per-resource `Promise.allSettled` loading so reference failures degrade individual controls instead of taking down the page.
- [ ] Run `pnpm.cmd test -- src/pages/booking.test.ts src/api/mock-adapter.test.ts` and confirm it passes.

## Task 6: Wire navigation, routes, compatibility redirects, and shell tests

**Files:**

- Modify: `src/app/navigation.ts`
- Modify: `src/app/router.ts`
- Modify: `src/app/AppShell.test.ts`
- Modify: `src/pages/seven-page-workspace.test.ts`
- Modify: any Contact relation links in `src/api/mock-adapter.ts`

- [ ] Update failing shell/router tests first to require `Leads&Opportunities` at `/leads-opportunities` and separate `Booking` at `/booking`.
- [ ] Add failing route tests for `/leads/:leadId` keeping the `Leads&Opportunities` navigation item active.
- [ ] Add failing compatibility tests for:
  - `/pipeline` → `/leads-opportunities?view=opportunities`;
  - `/opportunity-strategy` → `/leads-opportunities?view=opportunities`;
  - `/opportunities-booking?view=bookings` → `/booking`;
  - other `/opportunities-booking` entries → `/leads-opportunities?view=opportunities`.
- [ ] Run focused shell and workspace tests and confirm failures reflect the old routes/labels.
- [ ] Update the Sales navigation group to show `Leads&Opportunities` and `Booking` as sibling vertical navigation items with existing capability rules.
- [ ] Add the new lazy routes, navigation metadata, and query-preserving legacy redirects.
- [ ] Update Contact related-record links to the new destinations.
- [ ] Run:
  - `pnpm.cmd test -- src/app/AppShell.test.ts`
  - `pnpm.cmd test -- src/pages/seven-page-workspace.test.ts`
  - `pnpm.cmd test -- src/pages/contacts.test.ts`

## Task 7: Integrated verification and visual acceptance

**Files:**

- Modify only if a verified regression requires it: `src/design-system/workspace.css`, `src/design-system/base.css`

- [ ] Run focused feature tests:
  - `pnpm.cmd test -- src/demo/sales-repository.test.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts`
  - `pnpm.cmd test -- src/pages/leads.test.ts src/pages/leads-opportunities.test.ts src/pages/opportunity-strategy-operations.test.ts src/pages/booking.test.ts`
  - `pnpm.cmd test -- src/app/AppShell.test.ts src/pages/seven-page-workspace.test.ts src/pages/contacts.test.ts`
- [ ] Run `pnpm.cmd typecheck`.
- [ ] Run `pnpm.cmd build`.
- [ ] Start the existing Vite development server and inspect at desktop and narrow widths in the browser.
- [ ] Verify these visible workflows end to end:
  - create/edit/filter a Lead;
  - open Contact-style Lead detail;
  - qualify and convert a Lead once, then retry without duplicates;
  - switch to Opportunities and use its existing deep controls;
  - open Booking independently;
  - create a Won-Opportunity Equipment Booking;
  - create a direct Renewal/Maintenance Booking with source/reason;
  - simulate missing/failed reference data and confirm Booking does not crash.
- [ ] Confirm there is no “Sales 工作区” text and no page-level horizontal Sales navigation.
- [ ] Review `git diff --check` and `git diff --stat`, ensuring only task-related files changed.

