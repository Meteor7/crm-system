# Opportunities Salesforce Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Salesforce-structured Opportunities list and Path detail page in the Planck CRM Demo, with unified Leads, Opportunities, and Booking search fields.

**Architecture:** Add a focused Opportunity list component for the combined workspace and reuse the current Opportunity strategy page as the dedicated record-detail surface. Route identity selects the record, while existing Mock API mutations continue to own create, edit, stage, stakeholder, and action persistence.

**Tech Stack:** Vue 3 Composition API, Vue Router, Pinia, TypeScript, Vitest, scoped CSS, existing design-system components, and Lucide icons already installed in the repository.

## Global Constraints

- Module label stays exactly `Leads&Opportunities`.
- Leads and Opportunities use a vertical switch, not a horizontal Sales navigation bar.
- Booking remains an independent left-navigation module.
- Salesforce is an information-architecture reference; Planck colors, typography, and components remain authoritative.
- Existing opportunity strategy data and actions must not be removed.
- No new dependency is allowed.
- Frappe mutations remain `NOT_IMPLEMENTED`.

---

### Task 1: Shared compact search control

**Files:**
- Modify: `src/design-system/workspace.css`
- Modify: `src/features/leads/LeadListView.vue`
- Modify: `src/pages/BookingPage.vue`
- Test: `src/pages/leads.test.ts`
- Test: `src/pages/booking.test.ts`

**Interfaces:**
- Produces: reusable `.crm-search-control` class for a label containing a search icon and input.
- Consumes: existing `--crm-*` design tokens.

- [ ] **Step 1: Add failing rendered-style contract assertions**

Assert that the Leads and Booking search wrappers use `crm-search-control` and their inputs keep the current accessible names.

- [ ] **Step 2: Run the focused tests and verify the new assertions fail**

Run:

```powershell
& '.\node_modules\.bin\vitest.CMD' run src/pages/leads.test.ts src/pages/booking.test.ts --exclude '.superpowers/**'
```

Expected: failure because the shared class is not rendered.

- [ ] **Step 3: Add the shared search class and apply it**

Define height, surface, border, radius, placeholder, hover, focus-within, icon, and responsive behavior in `workspace.css`. Replace the two page-specific search wrappers with the shared class and remove only the redundant Booking search-wrapper declarations.

- [ ] **Step 4: Re-run the focused tests**

Expected: both test files pass.

### Task 2: Opportunity list view and route

**Files:**
- Create: `src/features/opportunities/OpportunityListView.vue`
- Modify: `src/pages/LeadsOpportunitiesPage.vue`
- Modify: `src/app/router.ts`
- Test: `src/pages/leads-opportunities.test.ts`
- Test: `src/app/router-sales.test.ts`

**Interfaces:**
- Consumes: `CrmApi.listStrategyOpportunities`, `CrmApi.createStrategyOpportunity`, `OpportunityEditorModal`.
- Produces: navigation to route name `opportunity-detail` with `opportunityId`.

- [ ] **Step 1: Write failing list and route tests**

Cover list heading, shared search class, Stage / Forecast / Owner filters, table columns, name navigation, create action, and `/opportunities/:opportunityId` route metadata.

- [ ] **Step 2: Run focused tests and verify failure**

```powershell
& '.\node_modules\.bin\vitest.CMD' run src/pages/leads-opportunities.test.ts src/app/router-sales.test.ts --exclude '.superpowers/**'
```

- [ ] **Step 3: Implement the list**

Load the existing strategy opportunities, filter them locally, render loading/error/empty states, render the Salesforce-structured table, reuse the existing editor modal, and route newly created or selected records to the detail page.

- [ ] **Step 4: Replace the embedded strategy dashboard**

Render `OpportunityListView` in the Opportunities branch of `LeadsOpportunitiesPage`.

- [ ] **Step 5: Add the detail route**

Add:

```ts
{
  path: '/opportunities/:opportunityId',
  name: 'opportunity-detail',
  component: () => import('@/pages/OpportunityStrategyPage.vue'),
  meta: { navigationPath: '/leads-opportunities' },
}
```

- [ ] **Step 6: Re-run the focused tests**

Expected: list and route tests pass.

### Task 3: Salesforce Path Opportunity detail

**Files:**
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/pages/opportunity-strategy-operations.test.ts`
- Test: `src/pages/opportunity-detail.test.ts`

**Interfaces:**
- Consumes: route param `opportunityId`, existing `StrategyOpportunityDto`, existing update/stakeholder/action APIs.
- Produces: dedicated record detail with functional stage advancement.

- [ ] **Step 1: Write failing detail tests**

Assert record selection from the route, the six Path stages, active/completed states, the three-column content groups, back link, edit action, new Action action, and stage advancement through `updateStrategyOpportunity`.

- [ ] **Step 2: Run the detail tests and verify failure**

```powershell
& '.\node_modules\.bin\vitest.CMD' run src/pages/opportunity-detail.test.ts src/pages/opportunity-strategy-operations.test.ts --exclude '.superpowers/**'
```

- [ ] **Step 3: Implement route-based selection and Path state**

Select from `route.params.opportunityId`, compute stage index and terminal state, and update to the next stage through the current API before reloading the selected record.

- [ ] **Step 4: Recompose the detail template**

Build the record header, horizontally scrollable Path, About/Status cards, Action Plan, Change History, Commercial Forecast, Buying Influence, and strategy evidence cards. Keep current editor and contact flows.

- [ ] **Step 5: Add responsive styles**

Use three columns on wide screens, two columns at tablet width where appropriate, and a single column on narrow screens. Keep tables and Path scrolling within their own containers.

- [ ] **Step 6: Re-run detail and regression tests**

Expected: both test files pass.

### Task 4: Final verification

**Files:**
- Verify only; no source changes unless a directly related regression is found.

- [ ] **Step 1: Run focused sales tests**

```powershell
& '.\node_modules\.bin\vitest.CMD' run src/pages/leads.test.ts src/pages/leads-opportunities.test.ts src/pages/opportunity-detail.test.ts src/pages/opportunity-strategy-operations.test.ts src/pages/booking.test.ts src/app/router-sales.test.ts src/api/mock-adapter.test.ts --exclude '.superpowers/**' --maxWorkers=1
```

- [ ] **Step 2: Run typecheck**

```powershell
pnpm.cmd typecheck
```

- [ ] **Step 3: Run production build**

```powershell
pnpm.cmd build
```

- [ ] **Step 4: Run whitespace validation**

```powershell
git diff --check
```

- [ ] **Step 5: Browser QA**

Validate:

1. `/leads-opportunities?view=opportunities` renders the Opportunity list.
2. Search and one select filter change the table.
3. Clicking a name opens `/opportunities/:opportunityId`.
4. Path, About, Status, activity, commercial, stakeholder, and evidence areas render.
5. One stage advancement updates visible state.
6. Leads and Booking use the same search style.
7. Desktop and 768px viewports have no page-level horizontal overflow.
8. Browser error log is empty.
