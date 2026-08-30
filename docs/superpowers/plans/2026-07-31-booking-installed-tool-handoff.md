# Booking to Installed Tool Implementation Plan

**Goal:** Let Sales convert a confirmed Opportunity or Upsell Booking into one Installed Tool while keeping the Booking as a completed archive record, and replace the Installed Tools metric cards with practical filters.

**Scope:** Mock Demo behavior only. Preserve unrelated modules and return `NOT_IMPLEMENTED` from the Frappe adapter.

## Task 1: Define the domain contract

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/contracts.ts`

1. Replace Booking type choices with `Opportunity | Upsell`.
2. Add `Completed`, conversion metadata, and the conversion input/result types.
3. Extend Installed Tool records with source Booking, Sales owner, and engineer owner.
4. Run the TypeScript-aware focused tests to expose all callers that require migration.

## Task 2: Prove and implement the Mock conversion

**Files:**
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/demo/sales-repository.ts`
- Modify: `src/api/mock-data.ts`
- Modify: `src/demo/operations-data.ts`

1. Add failing tests for both Booking sources, invalid status, duplicate conversion, duplicate Serial, and persisted Installed Tool data.
2. Store Installed Tools in the shared Sales snapshot so Booking and Installed Tools use one Mock transaction boundary.
3. Normalize legacy Booking values to the two new sources.
4. Implement atomic conversion: validate, create the tool, mark Booking completed, save once.
5. Run the focused Mock adapter and repository tests.

## Task 3: Align the Frappe boundary

**Files:**
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`

1. Add a failing contract test.
2. Return an explicit `NOT_IMPLEMENTED` error for conversion.
3. Run the focused Frappe adapter test.

## Task 4: Update Booking creation and transfer UI

**Files:**
- Modify: `src/features/opportunities/BookingEditorModal.vue`
- Create: `src/features/opportunities/BookingInstalledToolModal.vue`
- Modify: `src/pages/BookingPage.vue`
- Modify: `src/pages/booking.test.ts`

1. Add failing UI tests for the Opportunity/Upsell choices and confirmed-only transfer.
2. Replace the old three Booking types with the two approved sources.
3. Add the transfer action and form for Site, engineer, Serial, model, and optional Installed Tool master data.
4. Show `Completed` and the generated Installed Tool ID in the retained Booking row.
5. Run Booking page tests.

## Task 5: Replace Installed Tools metrics with filters

**Files:**
- Modify: `src/pages/InstalledToolsPage.vue`
- Modify: `src/pages/seven-page-workspace.test.ts`

1. Add a failing page test for removed metrics and combined keyword/account/status/engineer filtering.
2. Add filter controls and reset behavior.
3. Add a fallback lifecycle profile for newly converted tools, beginning with FAT as Current.
4. Run Installed Tools page tests.

## Task 6: Verify the complete flow

1. Run all directly affected tests.
2. Run the project build and distinguish pre-existing failures from regressions.
3. Start or reuse the Demo service.
4. In the browser, create or use a confirmed Booking, convert it, verify the Booking archive state and Installed Tools filter/result.
5. Review `git diff` limited to the files in this plan and report any remaining Mock/Frappe boundary.
