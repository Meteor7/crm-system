# Calendar Detail Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a plain “查看详情” button to Calendar details that navigates to the exact upstream record for all four event types.

**Architecture:** Keep routing local to `ServiceCalendarPage.vue`: each normalized calendar event retains its upstream record ID, and one function converts the event type plus source ID into a Vue Router route. Extend `VisitsPage.vue` only to recognize the Calendar `focus` query and visually identify the matching row; existing Demo Test focus and detail routes are reused unchanged.

**Tech Stack:** Vue 3.5, Vue Router 5.2, TypeScript 5.9, Vitest 4, Vue Test Utils 2.

## Global Constraints

- The entry is a normal existing-style button labeled exactly `查看详情`.
- Do not add a modal, menu, special animation, new dependency, or shared routing abstraction.
- The button appears in both the standard right-side detail and the selected item inside the day agenda detail.
- Missing target records must leave the destination module usable without throwing or opening an edit form.

---

### Task 1: Calendar exact-record navigation

**Files:**
- Modify: `src/pages/seven-page-workspace.test.ts`
- Modify: `src/pages/ServiceCalendarPage.vue`

**Interfaces:**
- Consumes: existing Vue Router route names `visits`, `demo-detail`, `evaluations`, and `booking-detail`.
- Produces: `sourceId: string` on each local `CalendarEvent`, `detailRoute(event: CalendarEvent): RouteLocationRaw`, and the `查看详情` button behavior.

- [ ] **Step 1: Write the failing Calendar navigation test**

Seed one visit, Demo Request, Evaluation, and Booking on the visible day. Mount Calendar with a real memory router, click each event card and the `[data-calendar-detail]` button, and assert literal destination routes:

```ts
expect(router.currentRoute.value.fullPath).toBe(`/visits?focus=${visit.id}`)
expect(router.currentRoute.value.fullPath).toBe(`/demo-workflow/${request.id}?from=demo-requests`)
expect(router.currentRoute.value.fullPath).toBe(`/evaluations?focus=${evaluation.id}`)
expect(router.currentRoute.value.fullPath).toBe(`/booking/${booking.id}`)
```

Also open the crowded-day agenda and assert its selected item exposes the same `[data-calendar-detail]` button.

- [ ] **Step 2: Run the Calendar test and verify RED**

Run: `pnpm test src/pages/seven-page-workspace.test.ts`

Expected: FAIL because `[data-calendar-detail]` does not exist.

- [ ] **Step 3: Implement minimal Calendar routing**

Add `sourceId` while mapping each upstream DTO. Add a route resolver returning literal named routes, inject `useRouter()`, and add one method:

```ts
function openDetail(event: CalendarEvent) {
  void router.push(detailRoute(event))
}
```

Render a plain `<button class="secondary-button" type="button" data-calendar-detail @click="openDetail(selected)">查看详情</button>` after the detail text in both detail modes.

- [ ] **Step 4: Run the Calendar test and verify GREEN**

Run: `pnpm test src/pages/seven-page-workspace.test.ts`

Expected: PASS with zero failures.

- [ ] **Step 5: Commit Calendar navigation**

```bash
git add src/pages/ServiceCalendarPage.vue src/pages/seven-page-workspace.test.ts
git commit -m "feat: add calendar detail navigation"
```

### Task 2: Visit focus destination

**Files:**
- Modify: `src/pages/customer-operations.test.ts`
- Modify: `src/pages/VisitsPage.vue`

**Interfaces:**
- Consumes: `/visits?focus=<VisitDto.id>` from Task 1.
- Produces: `focusedVisitId` computed state and `.focused` styling on the matching visit row.

- [ ] **Step 1: Write the failing Visit focus test**

Mount `VisitsPage` at `/visits?focus=V-001`, wait for data, and assert:

```ts
expect(wrapper.get('[data-visit-id="V-001"]').classes()).toContain('focused')
expect(wrapper.get('[data-visit-id="V-002"]').classes()).not.toContain('focused')
expect(wrapper.find('[data-testid="visit-modal"]').exists()).toBe(false)
```

Mount once more with an unknown focus and assert the table still renders normally.

- [ ] **Step 2: Run the Visit test and verify RED**

Run: `pnpm test src/pages/customer-operations.test.ts`

Expected: FAIL because the target row lacks `focused`.

- [ ] **Step 3: Implement minimal Visit focus handling**

Read the query without changing existing filters:

```ts
const focusedVisitId = computed(() => typeof route.query.focus === 'string' ? route.query.focus : '')
```

Apply `:class="{ focused: visit.id === focusedVisitId }"` to each visit row and add a scoped background/outline rule for `.visits-table tr.focused`.

- [ ] **Step 4: Run the Visit test and verify GREEN**

Run: `pnpm test src/pages/customer-operations.test.ts`

Expected: PASS with zero failures.

- [ ] **Step 5: Commit Visit focus handling**

```bash
git add src/pages/VisitsPage.vue src/pages/customer-operations.test.ts
git commit -m "feat: focus calendar visit target"
```

### Task 3: Regression verification

**Files:**
- Verify only; no planned production changes.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: fresh evidence that the feature integrates with the existing frontend.

- [ ] **Step 1: Run focused tests together**

Run: `pnpm test src/pages/seven-page-workspace.test.ts src/pages/customer-operations.test.ts`

Expected: all tests pass with zero failures.

- [ ] **Step 2: Run the full frontend test suite**

Run: `pnpm test`

Expected: all test files and tests pass with zero failures.

- [ ] **Step 3: Run type checking**

Run: `pnpm typecheck`

Expected: exit code 0 and no TypeScript errors.

- [ ] **Step 4: Run the production build**

Run: `pnpm build`

Expected: exit code 0 and Vite emits the production bundle.
