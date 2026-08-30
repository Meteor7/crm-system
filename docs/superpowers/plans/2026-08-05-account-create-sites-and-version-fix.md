# Account Create Sites and Version Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix optimistic-lock metadata when editing an Account and allow optional zero-to-many Site records to be created from the new Account modal without duplicating the Account on retry.

**Architecture:** Keep the existing `CrmApi` contract and create the Account first, then create Site records with the returned Account ID. Store the created Account ID and the count of successfully persisted Site drafts in page-local state so a partial Site failure retries only remaining Site records.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vitest, Vue Test Utils, existing `CrmApi`, Vite Frappe build, Docker Compose.

## Global Constraints

- Site entry is optional and supports zero or more records.
- Reuse the existing Site fields: `name`, `city`, `type`, `process`, and `status`.
- Do not add a backend bulk endpoint or new dependency.
- Do not modify Contact, Lead conversion, or unrelated modules.
- Preserve all unrelated worktree changes.

---

### Task 1: Account detail optimistic-lock regression

**Files:**
- Modify: `src/pages/AccountDetailPage.vue`
- Test: `src/pages/account-booking-details.test.ts`

**Interfaces:**
- Consumes: `CrmApi.updateAccount(id, input, expectedModified?)` and `Account360Dto.account.modified`.
- Produces: `saveAccount()` passes the loaded Account version as the third API argument.

- [ ] **Step 1: Add a failing request-argument assertion**

Load an Account fixture with `modified = '2026-08-05 08:50:00.000000'`, spy on `updateAccount`, submit the edit modal, and assert:

```ts
expect(updateAccount).toHaveBeenCalledWith('ACC-002', expect.any(Object), expectedModified)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
$env:TEMP=(Resolve-Path .codex-test-tmp); $env:TMP=$env:TEMP
npm.cmd test -- --run src/pages/account-booking-details.test.ts
```

Expected: the assertion fails because `updateAccount` receives only two arguments.

- [ ] **Step 3: Pass the loaded version**

Use the loaded Account detail in `saveAccount()`:

```ts
await props.apiClient.updateAccount(
  accountId.value,
  accountForm.value,
  accountDetail.value?.account.modified,
)
```

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run the Task 1 command again. Expected: 2 tests pass.

---

### Task 2: Optional Site drafts in new Account flow

**Files:**
- Modify: `src/pages/AccountsPage.vue`
- Test: `src/pages/opportunity-strategy-operations.test.ts`

**Interfaces:**
- Consumes: `CrmApi.createAccount(input)` and `CrmApi.createAccountSite(accountId, Omit<SiteDto, 'id'>)`.
- Produces: `newSiteDrafts`, `addNewSiteDraft()`, `removeNewSiteDraft(index)`, and resumable `createAccount()` sequencing.

- [ ] **Step 1: Write failing success-flow tests**

Extend the existing “creates a customer” test to spy on both API methods, add two Site drafts through `[data-add-site]`, fill inputs identified by stable aria labels, submit, and assert both calls use the created Account ID:

```ts
expect(createAccountSite).toHaveBeenNthCalledWith(1, createdAccountId, {
  name: '上海一厂',
  city: '上海',
  type: '晶圆制造',
  process: '28nm',
  status: '量产',
})
```

Also retain a no-Site assertion proving the existing Account-only flow makes zero `createAccountSite` calls.

- [ ] **Step 2: Write a failing partial-retry test**

Make the first `createAccountSite` call succeed and the second reject once. Submit twice and assert `createAccount` is called once while the already-created first Site is not submitted again.

- [ ] **Step 3: Run the focused tests and confirm RED**

Run:

```powershell
$env:TEMP=(Resolve-Path .codex-test-tmp); $env:TMP=$env:TEMP
npm.cmd test -- --run src/pages/opportunity-strategy-operations.test.ts
```

Expected: Site controls or API sequencing assertions fail before implementation.

- [ ] **Step 4: Add Site draft state and modal controls**

Add `SiteDto` typing and page-local state:

```ts
type NewSiteDraft = Omit<SiteDto, 'id'> & { clientId: string }
const newSiteDrafts = ref<NewSiteDraft[]>([])
const createdAccountId = ref('')
const persistedSiteCount = ref(0)
```

Reset all three values in `openAccountModal()`. Render the same Site editor fields and status options used by `AccountDetailPage.vue`; default a new draft city from `accountForm.city`.

- [ ] **Step 5: Implement resumable Account/Site persistence**

In `createAccount()`, call `createAccount` only when `createdAccountId` is empty. Loop from `persistedSiteCount` to the end, incrementing it after each successful `createAccountSite`. On partial failure, keep the modal open and show `客户已创建，但厂区保存失败：${message}`. On full success, clear state, close, reload, and navigate.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run the Task 2 command again. Expected: all tests in the file pass.

---

### Task 3: Integrated verification and local deployment

**Files:**
- Verify: `src/pages/AccountDetailPage.vue`
- Verify: `src/pages/AccountsPage.vue`
- Generate: `backend/apps/rayher_crm/rayher_crm/public/crm/**`
- Generate: `backend/app-build/rayher_crm.zip`

**Interfaces:**
- Consumes: verified source and existing build/deployment scripts.
- Produces: updated local Docker CRM frontend.

- [ ] **Step 1: Run focused regression tests**

```powershell
$env:TEMP=(Resolve-Path .codex-test-tmp); $env:TMP=$env:TEMP
npm.cmd test -- --run src/pages/account-booking-details.test.ts src/pages/opportunity-strategy-operations.test.ts
```

- [ ] **Step 2: Run typecheck and Frappe build**

```powershell
npm.cmd run typecheck
npm.cmd run build:frappe
```

- [ ] **Step 3: Prepare app build context**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File backend\scripts\prepare-app-build-context.ps1
```

- [ ] **Step 4: Rebuild and restart the local backend**

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml build backend
docker compose --env-file backend/.env.example -f backend/compose.yaml up -d
```

- [ ] **Step 5: Verify runtime health**

```powershell
docker compose --env-file backend/.env.example -f backend/compose.yaml ps
Invoke-RestMethod http://127.0.0.1:8080/api/method/ping
```

Expected: backend is healthy and ping returns a successful response.
