# Demo Project Customer Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a customer dropdown that filters every section of the Demo project-cycle board and survives route/detail navigation.

**Architecture:** Store the selected customer in `DemoWorkflowPage.vue` alongside the existing search and owner filters, and synchronize it through the `customer` query parameter. Let `DemoProjectCycleBoard.vue` derive sorted unique customer options and combine the customer predicate with its existing filter predicates.

**Tech Stack:** Vue 3, TypeScript, Vue Router, Vitest, Vue Test Utils.

## Global Constraints

- Default value is `all` and label is `全部客户`.
- Customer options come from `DemoWorkflowDto.account`, are unique, and are sorted.
- The customer predicate applies to Request, Test, and recent completed projects.
- Existing DDL, colors, urgent rules, archive-detail behavior, and other Demo surfaces stay unchanged.
- No new dependency and no Frappe/backend change.
- Do not create a commit because this shared worktree contains user-owned uncommitted changes.

---

### Task 1: Add a failing customer-filter workflow test

**Files:**
- Modify: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: the rendered project-cycle board and Vue Router query state.
- Produces: regression coverage for `select[aria-label="项目客户"]` and the `customer` query parameter.

- [ ] **Step 1: Write the failing test**

```ts
it('filters every project-cycle section by customer and keeps the route query', async () => {
  const { wrapper, router } = await mountPage()
  await wrapper.get('[data-demo-surface="project"]').trigger('click')
  await flushPromises()

  const customer = wrapper.get('select[aria-label="项目客户"]')
  expect(customer.findAll('option').map((option) => option.text())).toContain('示例企业014有限公司')

  await customer.setValue('示例企业014有限公司')
  await flushPromises()

  expect(router.currentRoute.value.query.customer).toBe('示例企业014有限公司')
  expect(wrapper.findAll('[data-project-id]').every((card) => card.text().includes('示例企业014有限公司'))).toBe(true)

  await customer.setValue('all')
  await flushPromises()
  expect(router.currentRoute.value.query.customer).toBeUndefined()
})
```

- [ ] **Step 2: Verify RED**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts`

Expected: FAIL because the customer select does not exist.

### Task 2: Implement customer state, options, and filtering

**Files:**
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/features/demo-workflow/DemoProjectCycleBoard.vue`
- Test: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: `DemoWorkflowDto.account` and route query `customer`.
- Produces: `customer` prop, `update:customer` event, and `select[aria-label="项目客户"]`.

- [ ] **Step 1: Add page state and URL synchronization**

```ts
const customer = ref(readQuery('customer') || 'all')

async function updateCustomer(value: string) {
  customer.value = value
  await router?.replace({ name: 'demo-workflow', query: currentQuery() })
}
```

Include `customer` in `surfaceQuery()` only when it is not `all`, and pass it to the project-cycle board.

- [ ] **Step 2: Derive options and filter projects**

```ts
const customers = computed(() => [...new Set(props.items.map((item) => item.account))].sort())
```

Add `(props.customer === 'all' || item.account === props.customer)` to the existing `filtered` predicate.

- [ ] **Step 3: Render the customer select**

```vue
<label class="toolbar-filter">
  <span>客户</span>
  <select
    :value="customer"
    aria-label="项目客户"
    @change="emit('update:customer', ($event.target as HTMLSelectElement).value)"
  >
    <option value="all">全部客户</option>
    <option v-for="account in customers" :key="account" :value="account">{{ account }}</option>
  </select>
</label>
```

- [ ] **Step 4: Verify GREEN**

Run: `pnpm.cmd test src/pages/DemoWorkflowPage.test.ts src/domain/demo-project-cycle.test.ts`

Expected: PASS.

### Task 3: Verify compilation and focused scope

**Files:**
- Verify: `src/pages/DemoWorkflowPage.vue`
- Verify: `src/features/demo-workflow/DemoProjectCycleBoard.vue`
- Verify: `src/pages/DemoWorkflowPage.test.ts`

**Interfaces:**
- Consumes: the completed implementation.
- Produces: build and focused-diff evidence.

- [ ] **Step 1: Build**

Run: `pnpm.cmd build`

Expected: PASS.

- [ ] **Step 2: Review focused files**

Run: `git status --short -- src/pages/DemoWorkflowPage.vue src/features/demo-workflow/DemoProjectCycleBoard.vue src/pages/DemoWorkflowPage.test.ts`

Expected: only the requested page, board, and test files are in implementation scope.
