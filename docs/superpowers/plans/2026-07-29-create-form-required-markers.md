# Create Form Required Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a red `*` beside every existing required field label in every create form.

**Architecture:** Add one presentation-only `RequiredMark` component and reuse it beside required label text. Components that serve both create and edit modes pass a boolean derived from their existing entity or mode prop, so edit views remain unchanged.

**Tech Stack:** Vue 3 SFC, TypeScript, Vitest, Vue Test Utils.

## Global Constraints

- Existing validation rules and `required` attributes remain unchanged.
- Optional fields never receive a marker.
- Shared create/edit forms display markers only in create mode.
- No new dependency, API change, data-model change, or unrelated refactor.

---

### Task 1: Required marker primitive

**Files:**
- Create: `src/design-system/RequiredMark.vue`
- Create: `src/design-system/RequiredMark.test.ts`

**Interfaces:**
- Produces: `RequiredMark` with optional `show?: boolean`, defaulting to `true`.

- [ ] **Step 1: Write the failing test**

```ts
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RequiredMark from './RequiredMark.vue'

describe('RequiredMark', () => {
  it('renders an accessibility-hidden required marker when enabled', () => {
    const wrapper = mount(RequiredMark)
    expect(wrapper.get('[data-required-mark]').text()).toBe('*')
    expect(wrapper.get('[data-required-mark]').attributes('aria-hidden')).toBe('true')
  })

  it('renders nothing when disabled', () => {
    expect(mount(RequiredMark, { props: { show: false } }).find('[data-required-mark]').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: Run the test and verify RED**

Run: `pnpm.cmd test -- src/design-system/RequiredMark.test.ts`

Expected: FAIL because `RequiredMark.vue` does not exist.

- [ ] **Step 3: Add the minimal component**

```vue
<script setup lang="ts">
withDefaults(defineProps<{ show?: boolean }>(), { show: true })
</script>

<template>
  <span v-if="show" class="required-mark" data-required-mark aria-hidden="true">*</span>
</template>

<style scoped>
.required-mark{margin-left:3px;color:var(--crm-danger);font-weight:800}
</style>
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `pnpm.cmd test -- src/design-system/RequiredMark.test.ts`

Expected: 2 tests pass.

### Task 2: Create-form integration

**Files:**
- Create: `src/features/create-form-required-markers.test.ts`
- Modify: `src/pages/AccountsPage.vue`
- Modify: `src/features/contacts/ContactModal.vue`
- Modify: `src/features/stakeholders/StakeholderModal.vue`
- Modify: `src/features/visits/VisitModal.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.vue`
- Modify: `src/features/demo-requests/DemoRequestModal.vue`
- Modify: `src/features/opportunities/OpportunityEditorModal.vue`
- Modify: `src/features/opportunities/BookingEditorModal.vue`
- Modify: `src/features/opportunities/ActionEditorModal.vue`
- Modify: `src/features/opportunities/StakeholderEditorModal.vue`
- Modify: `src/features/evaluations/TestRunModal.vue`

**Interfaces:**
- Consumes: `RequiredMark(show?: boolean)`.
- Produces: one visible `[data-required-mark]` for each required control in create mode and none in edit mode.

- [ ] **Step 1: Write focused integration tests**

Mount representative create/edit shared forms and create-only forms with literal fixtures. Assert:

```ts
expect(createWrapper.findAll('[data-required-mark]')).toHaveLength(createWrapper.findAll(':required').length)
expect(editWrapper.findAll('[data-required-mark]')).toHaveLength(0)
expect(createWrapper.find('label:has([aria-label="联系人电话"]) [data-required-mark]').exists()).toBe(false)
```

The table must cover Account, Contact, Stakeholder, Visit, Demo Request, Opportunity, Booking, Action, and Wafer Test Run create paths.

- [ ] **Step 2: Run the integration test and verify RED**

Run: `pnpm.cmd test -- src/features/create-form-required-markers.test.ts`

Expected: FAIL because the form labels do not render `[data-required-mark]`.

- [ ] **Step 3: Add minimal markers**

Import `RequiredMark` only in the affected components. Place it immediately after required label text. Use the existing mode/entity signal:

```vue
<span>姓名<RequiredMark :show="!contact" /></span>
<span>Opportunity 名称<RequiredMark :show="!opportunity" /></span>
<span>设备需求<RequiredMark :show="!booking" /></span>
<span>Action 标题<RequiredMark :show="!action" /></span>
```

For `VisitModal`, use `:show="mode === 'create'"`. For `DemoRequestForm`, add a presentation-only `showRequiredMarks?: boolean` prop and pass `:show-required-marks="mode === 'create'"` from `DemoRequestModal`. For `StakeholderEditorModal`, mark both the required Contact selection and Coverage Evidence only while `!stakeholder`. Create-only Account and Wafer Test Run markers remain enabled by default.

- [ ] **Step 4: Run the integration and primitive tests**

Run: `pnpm.cmd test -- src/design-system/RequiredMark.test.ts src/features/create-form-required-markers.test.ts`

Expected: all tests pass.

### Task 3: Regression verification

**Files:**
- Verify only; no additional production changes unless a command exposes an in-scope defect.

- [ ] **Step 1: Run affected existing tests**

Run: `pnpm.cmd test -- src/pages/customer-operations.test.ts src/pages/opportunity-strategy-operations.test.ts src/features/demo-requests/DemoRequestForm.test.ts src/features/evaluations/TestRunModal.test.ts`

Expected: all available targeted tests pass; if a listed file does not exist, run the nearest existing component/page test and report the substitution.

- [ ] **Step 2: Run type checking**

Run: `pnpm.cmd typecheck`

Expected: exit code 0.

- [ ] **Step 3: Run production build**

Run: `pnpm.cmd build`

Expected: exit code 0.

- [ ] **Step 4: Review the final diff**

Run: `git diff -- docs/superpowers/specs/2026-07-29-create-form-required-markers-design.md docs/superpowers/plans/2026-07-29-create-form-required-markers.md src/design-system/RequiredMark.vue src/design-system/RequiredMark.test.ts src/features/create-form-required-markers.test.ts src/pages/AccountsPage.vue src/features/contacts/ContactModal.vue src/features/stakeholders/StakeholderModal.vue src/features/visits/VisitModal.vue src/features/demo-requests/DemoRequestForm.vue src/features/demo-requests/DemoRequestModal.vue src/features/opportunities/OpportunityEditorModal.vue src/features/opportunities/BookingEditorModal.vue src/features/opportunities/ActionEditorModal.vue src/features/opportunities/StakeholderEditorModal.vue src/features/evaluations/TestRunModal.vue`

Expected: only required-marker presentation, tests, and the two planning documents changed.
