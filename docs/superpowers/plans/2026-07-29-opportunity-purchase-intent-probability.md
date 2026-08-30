# Opportunity Purchase Intent Probability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse the prototype's stage-and-purchase-intent formula throughout the CRM Opportunities module.

**Architecture:** A pure domain function owns the formula and stage aliases. The Mock API remains the write boundary: it validates purchase intent, calculates probability on read/create/update, and preserves `StrategyOpportunityDto.score` as the stored purchase-intent value. Opportunity list, detail, and editor consume the same fields and never calculate a competing value.

**Tech Stack:** Vue 3, TypeScript, Pinia, Vitest, Vue Test Utils, Vite

## Global Constraints

- Reuse `stageBase × 0.6 + purchaseIntent × 0.4` exactly for open opportunities.
- `Won` is always `100`; `Lost` is always `0`.
- Keep `StrategyOpportunityDto.score` as the stored purchase-intent value.
- Do not modify Leads, Booking, permissions, Frappe backend schemas, or unrelated modules.
- Do not add dependencies.
- Do not stage or commit automatically because the current worktree contains unrelated staged and unstaged user changes.

---

### Task 1: Extract the Probability Domain Function

**Files:**
- Create: `src/domain/opportunity-probability.test.ts`
- Create: `src/domain/opportunity-probability.ts`

**Interfaces:**
- Produces: `calculateOpportunityProbability(stage: string, purchaseIntent: number): number`
- Produces: `opportunityProbabilityExplanation(stage: string, purchaseIntent: number): string`

- [ ] **Step 1: Write the failing domain tests**

Use literal, hand-calculated expectations:

```ts
expect(calculateOpportunityProbability('需求发现', 50)).toBe(29)
expect(calculateOpportunityProbability('Demo 验证', 80)).toBe(65)
expect(calculateOpportunityProbability('采购流程', 86)).toBe(88)
expect(calculateOpportunityProbability('Won', 0)).toBe(100)
expect(calculateOpportunityProbability('Lost', 100)).toBe(0)
```

- [ ] **Step 2: Run the domain test and confirm RED**

Run:

```powershell
pnpm.cmd test -- src/domain/opportunity-probability.test.ts
```

Expected: failure because `opportunity-probability.ts` does not exist.

- [ ] **Step 3: Implement the extracted formula**

Create a stage map with prototype values and compatibility aliases:

```ts
export function calculateOpportunityProbability(stage: string, purchaseIntent: number) {
  const normalizedStage = stage.trim()
  const base = STAGE_PROBABILITIES[normalizedStage] ?? 0
  if (normalizedStage === 'Won' || normalizedStage === 'Closed Won') return 100
  if (normalizedStage === 'Lost' || normalizedStage === 'Closed Lost') return 0
  const intent = Number(purchaseIntent) || 0
  return Math.max(0, Math.min(100, Math.round(base * 0.6 + intent * 0.4)))
}
```

- [ ] **Step 4: Run the domain test and confirm GREEN**

Run:

```powershell
pnpm.cmd test -- src/domain/opportunity-probability.test.ts
```

Expected: all domain cases pass.

### Task 2: Make the Mock API the Single Calculation Boundary

**Files:**
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`

**Interfaces:**
- Consumes: `calculateOpportunityProbability(stage, purchaseIntent)`
- Adds: `CreateStrategyOpportunityInput.intentScore?: number`
- Keeps: `CreateStrategyOpportunityInput.probability?: number` as compatibility fallback

- [ ] **Step 1: Change the Mock API test expectations first**

For a new Opportunity in `需求发现` with purchase intent `35`, expect probability `23`:

```ts
expect(created.data).toMatchObject({ score: 35, probability: 23 })
```

After updating to `Demo 验证` with purchase intent `55`, expect probability `55`:

```ts
expect(updated.data).toMatchObject({ score: 55, probability: 55, stage: 'Demo 验证' })
```

Also assert existing OPP-003 is normalized from `采购流程` and score `86` to probability `88`.

- [ ] **Step 2: Run the focused API test and confirm RED**

Run:

```powershell
pnpm.cmd test -- src/api/mock-adapter.test.ts
```

Expected: the API still copies manual probability and does not produce the calculated values.

- [ ] **Step 3: Implement validation and calculation**

At Mock API initialization and on create/update:

```ts
const purchaseIntent = Number(input.intentScore ?? input.probability ?? opportunity.score)
opportunity.score = Math.round(purchaseIntent)
opportunity.probability = calculateOpportunityProbability(opportunity.stage, opportunity.score)
```

Validate `purchaseIntent` is finite and inside `0..100`. Recalculate when only the stage changes.

- [ ] **Step 4: Run domain and API tests**

Run:

```powershell
pnpm.cmd test -- src/domain/opportunity-probability.test.ts src/api/mock-adapter.test.ts
```

Expected: both files pass.

### Task 3: Expose Purchase Intent and Calculated Probability in Opportunities

**Files:**
- Modify: `src/features/opportunities/OpportunityEditorModal.vue`
- Modify: `src/features/opportunities/OpportunityListView.vue`
- Modify: `src/pages/OpportunityDetailPage.vue`
- Modify: `src/pages/leads-opportunities.test.ts`
- Modify: `src/pages/opportunity-detail.test.ts`

**Interfaces:**
- Consumes: `calculateOpportunityProbability(stage, purchaseIntent)`
- Emits: `CreateStrategyOpportunityInput` with `intentScore`

- [ ] **Step 1: Add failing rendered-behavior assertions**

Assert that:

- OPP-003 list row shows `88%` and purchase intent `86/100`.
- Opportunity detail shows `购买意愿`, `86/100`, and `88%`.
- The editor exposes `Opportunity 购买意愿`, not an editable win-rate input.
- The editor preview changes when stage or purchase intent changes.

- [ ] **Step 2: Run page tests and confirm RED**

Run:

```powershell
pnpm.cmd test -- src/pages/leads-opportunities.test.ts src/pages/opportunity-detail.test.ts
```

Expected: labels, selectors, and calculated display are absent.

- [ ] **Step 3: Implement the list, detail, and editor UI**

- Add separate list columns for amount, calculated probability, and purchase intent.
- Rename `Strategy Score` to `购买意愿`.
- Add a formula note: `阶段基础概率 60% + 购买意愿 40%`.
- Replace editable probability with editable purchase intent and a read-only calculated preview.

- [ ] **Step 4: Run focused page tests**

Run:

```powershell
pnpm.cmd test -- src/pages/leads-opportunities.test.ts src/pages/opportunity-detail.test.ts
```

Expected: all page assertions pass.

### Task 4: Full Verification and Requirement Audit

**Files:**
- Verify all modified files

- [ ] **Step 1: Run all focused tests**

```powershell
pnpm.cmd test -- src/domain/opportunity-probability.test.ts src/api/mock-adapter.test.ts src/pages/leads-opportunities.test.ts src/pages/opportunity-detail.test.ts
```

- [ ] **Step 2: Run type checking**

```powershell
pnpm.cmd typecheck
```

- [ ] **Step 3: Run the production build**

```powershell
pnpm.cmd build
```

- [ ] **Step 4: Verify the rendered Opportunities workflow**

Open the Opportunities list and OPP-003 detail. Confirm:

- OPP-003 probability is `88%`.
- Purchase intent is `86/100`.
- The formula note is visible.
- Editing intent changes calculated probability after save.
- Advancing stage recalculates probability.

- [ ] **Step 5: Audit the requested scope**

Confirm that the production diff contains only the probability domain module, Opportunity input/API behavior, and Opportunities UI/tests. Confirm that Leads, Booking, permissions, and Frappe schema files were not changed by this feature.
