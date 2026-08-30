# Opportunity Change History Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the complete `Change History` card from Opportunity detail pages while preserving backend audit records and all other Opportunity behavior.

**Architecture:** Make a presentation-only change in `OpportunityDetailPage.vue`. Protect the requested behavior with a page-level regression test; do not change DTOs, Frappe services, DocTypes, or stored history.

**Tech Stack:** Vue 3, TypeScript, Vue Test Utils, Vitest, Vite, Frappe Docker Compose

## Global Constraints

- Only remove the Opportunity detail page `Change History` presentation.
- Keep backend history creation and existing database records unchanged.
- Preserve Opportunity editing, stage advancement, Action Plan, Commercial Forecast, and Buying Influence.
- Do not modify unrelated dirty-worktree files.

---

### Task 1: Remove the Opportunity history card

**Files:**
- Modify: `src/pages/opportunity-detail.test.ts`
- Modify: `src/pages/OpportunityDetailPage.vue`

**Interfaces:**
- Consumes: `OpportunityDetailPage` and the existing `CrmApi.listStrategyOpportunities()` response.
- Produces: An Opportunity detail page with no visible `Change History` module.

- [ ] **Step 1: Write the failing page regression**

Add this assertion to the existing detail-capabilities test after the page finishes loading:

```ts
expect(wrapper.text()).not.toContain('Change History')
```

- [ ] **Step 2: Run the regression and verify RED**

Run:

```powershell
$env:TEMP=(Resolve-Path .codex-test-tmp)
$env:TMP=$env:TEMP
npm.cmd test -- --run src/pages/opportunity-detail.test.ts -t "preserves the existing strategy capabilities"
```

Expected: FAIL because the current detail page still renders `Change History`.

- [ ] **Step 3: Remove only the history presentation**

Delete this template block from `src/pages/OpportunityDetailPage.vue`:

```vue
<section class="detail-card">
  <header><Target :size="16" /><h2>Change History</h2></header>
  <div class="history-list">
    <article v-for="entry in selected.history" :key="`${entry.at}-${entry.field}`"><time>{{ entry.at }}</time><strong>{{ entry.field }}</strong><span>{{ entry.from }} → {{ entry.to }}</span><small>{{ personnelDisplayName(entry.actor) }}</small></article>
  </div>
</section>
```

Do not remove `history` from `StrategyOpportunityDto` or change backend history writes.

- [ ] **Step 4: Verify GREEN and related Opportunity behavior**

Run:

```powershell
$env:TEMP=(Resolve-Path .codex-test-tmp)
$env:TMP=$env:TEMP
npm.cmd test -- --run src/pages/opportunity-detail.test.ts src/pages/leads-opportunities.test.ts src/pages/opportunity-strategy-operations.test.ts src/features/opportunities/OpportunityEditorModal.test.ts
```

Expected: all selected test files pass, including edit and stage-advance coverage.

- [ ] **Step 5: Check the scoped diff**

Run:

```powershell
git diff --check -- src/pages/OpportunityDetailPage.vue src/pages/opportunity-detail.test.ts
git diff -- src/pages/OpportunityDetailPage.vue src/pages/opportunity-detail.test.ts
```

Expected: only the history-card removal and the new absence assertion appear for this task.

### Task 2: Build and deploy the presentation change

**Files:**
- Generated: `backend/apps/rayher_crm/rayher_crm/public/crm/**`
- Generated: `backend/build/rayher_crm.zip`

**Interfaces:**
- Consumes: the updated Vue source from Task 1.
- Produces: the local Frappe deployment served at `http://127.0.0.1:2224`.

- [ ] **Step 1: Build Frappe frontend assets**

Run:

```powershell
node_modules\.bin\vite.CMD build --mode frappe --outDir backend/apps/rayher_crm/rayher_crm/public/crm --emptyOutDir
```

Expected: Vite exits with code 0 and emits an `OpportunityDetailPage-*.js` chunk.

- [ ] **Step 2: Prepare and build the app image**

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend\scripts\prepare-app-build-context.ps1
docker compose --env-file backend/.env.example -f backend/compose.yaml build backend
```

Expected: verified app archive and `rayher-crm-stage1:v15-local` image are produced.

- [ ] **Step 3: Start the updated services without schema migration**

Run:

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml up -d --no-deps backend frontend websocket queue-short queue-long scheduler
```

Expected: Backend and Frontend become healthy. No schema migration is required because this task changes presentation only.

- [ ] **Step 4: Verify the deployed service and asset**

Run:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:2224/api/method/ping
docker compose --env-file backend/.env.example -f backend/compose.yaml ps
```

Expected: ping returns `pong`; Backend and Frontend report healthy.

Git commit is intentionally omitted because this workspace exposes `.git` as read-only and the earlier scoped commit attempt failed with `index.lock: Permission denied`.
