# Opportunity Purchase Intent Slider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Opportunity purchase-intent numeric field with a horizontal slider whose right side displays only the current integer value.

**Architecture:** Keep the existing `intentScore` form field and probability computed property unchanged. Replace only the editor control markup and add component-scoped layout and range styles; verify behavior through the existing Opportunities page test.

**Tech Stack:** Vue 3, TypeScript, native HTML range input, Vitest, Vue Test Utils.

## Global Constraints

- Range is 0–100 with step 1.
- The slider's right side displays only the current value, such as `74`.
- Do not display `/100` or additional low/high labels.
- Preserve the existing probability formula, API input, and persistence behavior.
- Do not add dependencies or modify Leads, permissions, or Frappe backend behavior.

---

### Task 1: Replace the purchase-intent number input with a slider

**Files:**
- Modify: `src/features/opportunities/OpportunityEditorModal.vue`
- Test: `src/pages/leads-opportunities.test.ts`

**Interfaces:**
- Consumes: `form.intentScore: number | undefined` and the existing `calculatedProbability` computed value.
- Produces: an accessible `input[type="range"]` bound through `v-model.number`, plus a visible current-value output.

- [ ] **Step 1: Write the failing interaction test**

Update the existing new-Opportunity modal test to locate the purchase-intent control by its accessible name and assert:

```ts
expect(intent.attributes('type')).toBe('range')
expect(intent.attributes('min')).toBe('0')
expect(intent.attributes('max')).toBe('100')
expect(intent.attributes('step')).toBe('1')
expect(wrapper.get('[data-testid="opportunity-intent-value"]').text()).toBe('50')
```

After setting the control to `80`, assert the displayed value is `80` and the calculated probability remains `41%` at the default stage.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
.\node_modules\.bin\vitest.cmd run src\pages\leads-opportunities.test.ts --exclude ".superpowers/**"
```

Expected: FAIL because the current control is `type="number"` and the value-output test id does not exist.

- [ ] **Step 3: Implement the minimal slider markup**

Replace the numeric input with:

```vue
<label class="intent-field">
  <span>购买意愿</span>
  <div class="intent-slider-row">
    <input
      v-model.number="form.intentScore"
      aria-label="Opportunity 购买意愿"
      type="range"
      min="0"
      max="100"
      step="1"
    />
    <output data-testid="opportunity-intent-value">{{ form.intentScore }}</output>
  </div>
</label>
```

Add component-scoped styles that keep the slider horizontal and reserve a compact fixed-width value column on the right.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the focused command from Step 2. Expected: all tests in `leads-opportunities.test.ts` pass.

- [ ] **Step 5: Run proportional verification**

Run:

```powershell
.\node_modules\.bin\vitest.cmd run src\domain\opportunity-probability.test.ts src\api\mock-adapter.test.ts src\pages\leads-opportunities.test.ts src\pages\opportunity-detail.test.ts --exclude ".superpowers/**"
pnpm.cmd typecheck
pnpm.cmd build
```

Expected: all focused tests pass, then typecheck and build exit with code 0.

- [ ] **Step 6: Inspect the rendered modal**

Open the Opportunities view, launch the new-Opportunity modal, and verify the slider is horizontal, the right side contains only the current number, and moving it updates both the number and calculated probability.

No commit is included because the shared worktree already contains unrelated staged and unstaged user changes.
