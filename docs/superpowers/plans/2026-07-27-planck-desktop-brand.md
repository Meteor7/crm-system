# PLANCK Desktop Brand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the desktop sidebar's temporary QIHENG Demo identity with the approved horizontal QIHENG DEMO logo.

**Architecture:** Store the approved PNG under `public/brand` so Vite serves it from a stable root-relative URL. Keep the change inside `AppShell.vue`, replacing only the brand markup and its obsolete CSS. Lock the behavior with the existing AppShell component test.

**Tech Stack:** Vue 3, Vite, Vitest, Vue Test Utils, scoped CSS

## Global Constraints

- Desktop sidebar only; no mobile header redesign.
- Use `planck-logo-standard.png`.
- Do not add a dependency.
- Do not place the company logo inside business cards.
- Preserve navigation and service behavior.

---

### Task 1: Replace the sidebar brand cluster

**Files:**
- Create: `public/brand/planck-logo-standard.png`
- Modify: `src/app/AppShell.vue`
- Test: `src/app/AppShell.test.ts`

**Interfaces:**
- Consumes: Vite's public asset URL `/brand/planck-logo-standard.png`
- Produces: `[data-testid="planck-logo"]` with accessible name `QIHENG DEMO`

- [x] **Step 1: Write the failing test**

```ts
it('uses the approved QIHENG DEMO logo without the retired QIHENG Demo label', async () => {
  const logo = wrapper.get('[data-testid="planck-logo"]')
  expect(logo.attributes('src')).toBe('/brand/planck-logo-standard.png')
  expect(logo.attributes('alt')).toBe('QIHENG DEMO')
  expect(wrapper.text()).not.toContain('QIHENG Demo')
  expect(wrapper.text()).not.toContain('客户经营系统')
})
```

- [x] **Step 2: Run the test to verify it fails**

Run: `npm.cmd test -- src/app/AppShell.test.ts`

Expected: FAIL because `[data-testid="planck-logo"]` does not exist.

- [x] **Step 3: Add the approved asset and minimal markup**

```vue
<img
  class="brand-logo"
  data-testid="planck-logo"
  src="/brand/planck-logo-standard.png"
  alt="QIHENG DEMO"
/>
```

Remove only the superseded `.brand-mark` and brand-text rules, then size `.brand-logo` to fit the existing sidebar.

- [x] **Step 4: Verify the implementation**

Run:

```powershell
npm.cmd test -- src/app/AppShell.test.ts
npm.cmd run typecheck
npm.cmd run build
```

Expected: all commands exit with code `0`.

- [x] **Step 5: Verify the rendered desktop page**

Reload `http://localhost:4173/` and confirm the logo is visible, proportional, unclipped, and the page has no relevant console errors.
