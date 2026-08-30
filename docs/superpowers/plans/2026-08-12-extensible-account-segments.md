# Extensible Account Segments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Sales to add a custom customer business segment from the dropdown and make the new segment available globally in customer entry and matching filters.

**Architecture:** Add one account-segment list operation to the `CrmApi` boundary. Frappe stores the canonical options on Customer `custom_crm_segment`; Mock API keeps an equivalent in-memory set. A reusable Vue selector handles the last-row custom option, while pages load the canonical list and pass it into customer create/edit and Lead conversion forms.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils, Frappe/Python, MariaDB.

## Global Constraints

- Preserve `Frontend` and `Advanced Packaging` and all existing customer values.
- Do not add a segment-management page or segment rename/delete/merge behavior.
- Trim outer whitespace, reject blank values, and deduplicate by exact trimmed text.
- Account read permission controls list access; account write permission controls registration through create/update.
- Do not add dependencies or refactor unrelated code.
- Target files already contain unrelated user changes; never stage or commit an entire modified target file without reviewing the exact diff.

---

### Task 1: Frappe canonical segment registry

**Files:**
- Modify: `backend/apps/rayher_crm/rayher_crm/services/accounts.py`
- Modify: `backend/apps/rayher_crm/rayher_crm/api/v1/accounts.py`
- Test: `backend/apps/rayher_crm/rayher_crm/tests/test_account_contact_api.py`

**Interfaces:**
- Produces: `list_account_segments() -> list[str]`
- Produces: private `_normalize_account_segment(value: Any) -> str`
- Produces: private `_register_account_segment(segment: str) -> None`
- API endpoint: `GET accounts.list_account_segments` returning `success_response(list[str])`

- [ ] **Step 1: Write failing Frappe service tests**

Add tests that create an account with `segment: "  Power Semiconductor  "`, assert the serialized customer value is `Power Semiconductor`, assert `list_account_segments()` contains it once, create a second account with the trimmed name, and assert the list still contains it once. Add a blank-segment case asserting `CrmApiException.code == "VALIDATION_ERROR"`.

- [ ] **Step 2: Run the focused backend test and verify RED**

Run: `docker compose exec -T backend bench --site crm.localhost run-tests --app rayher_crm --module rayher_crm.tests.test_account_contact_api`

Expected: FAIL because `list_account_segments` is missing and custom segments are rejected by `ACCOUNT_SEGMENTS`.

- [ ] **Step 3: Implement the minimal canonical registry**

Replace fixed-choice segment validation with `required_text({"segment": payload.get("segment")}, "segment")`. Read normalized non-empty lines from the `Custom Field` row for `Customer.custom_crm_segment`, falling back to the two defaults. When registering a missing segment, lock that Custom Field row with `SELECT ... FOR UPDATE`, append exactly once using `frappe.db.set_value(..., update_modified=False)`, and clear Customer metadata cache. Register before Customer insert/save so the Select field accepts the value; on exceptions clear the same cache before re-raising.

Expose the read operation through the whitelisted API endpoint.

- [ ] **Step 4: Run the focused backend test and verify GREEN**

Run the command from Step 2.

Expected: PASS with custom persistence, trimming, blank rejection, and idempotent registration covered.

### Task 2: TypeScript API and adapters

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Test: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Changes: `AccountSummaryDto['segment']` from a two-value union to `string`
- Produces: `CrmApi.listAccountSegments(): Promise<ApiResponse<string[]>>`
- Frappe mapping: `listAccountSegments: 'accounts.list_account_segments'`

- [ ] **Step 1: Write failing adapter tests**

Extend the exact `FRAPPE_METHODS` expectation with `listAccountSegments`, then call the method and assert a GET request to `/api/method/rayher_crm.api.v1.accounts.list_account_segments` returns `['Frontend', 'Advanced Packaging']`.

In `mock-adapter.test.ts`, create `Power Semiconductor`, assert `listAccountSegments().data` contains it once, update another account with `" Power Semiconductor "`, and assert the stored value is trimmed and the global list remains deduplicated. Assert whitespace-only segment rejects with `VALIDATION_ERROR`.

- [ ] **Step 2: Run adapter tests and verify RED**

Run: `pnpm test -- src/api/frappe-adapter.test.ts src/api/mock-adapter.test.ts`

Expected: FAIL because the new API method does not exist and the account segment type is fixed.

- [ ] **Step 3: Implement minimal adapter behavior**

Add the interface method and Frappe GET mapping. In `createMockApi`, initialize a `Set<string>` from the two defaults plus current account segments; normalize and register on create/update; return `response([...localAccountSegments])` from `listAccountSegments`. Include segment in required non-blank validation and store only the trimmed value.

- [ ] **Step 4: Run adapter tests and verify GREEN**

Run the command from Step 2.

Expected: both files PASS.

### Task 3: Reusable custom segment selector

**Files:**
- Create: `src/features/accounts/AccountSegmentSelect.vue`
- Test: `src/features/accounts/AccountSegmentSelect.test.ts`

**Interfaces:**
- Props: `modelValue: string`, `segments: string[]`, `ariaLabel: string`, optional `required?: boolean`
- Emits: `update:modelValue(value: string)`
- Constant internal sentinel: `__custom_account_segment__`

- [ ] **Step 1: Write failing component tests**

Mount with the two defaults and assert the last option is `＋自定义领域`. Select the sentinel and assert an input labelled `${ariaLabel}自定义` appears and updates the v-model to `Power Semiconductor`. Switch back to `Frontend` and assert the input disappears and the value changes. Assert the custom input is `required` when the component is required.

- [ ] **Step 2: Run the component test and verify RED**

Run: `pnpm test -- src/features/accounts/AccountSegmentSelect.test.ts`

Expected: FAIL because the component is missing.

- [ ] **Step 3: Implement the minimal selector**

Render one `<select>` with deduplicated trimmed options followed by the sentinel. Track whether the current value is custom; when selected, emit an empty value and render a text input bound to `modelValue`. If a saved custom value is not in `segments`, keep the selector in custom mode so existing data remains editable.

- [ ] **Step 4: Run the component test and verify GREEN**

Run the command from Step 2.

Expected: PASS.

### Task 4: Customer list, create, and edit integration

**Files:**
- Modify: `src/pages/AccountsPage.vue`
- Modify: `src/pages/AccountDetailPage.vue`
- Test: `src/pages/mvp-workflow.test.ts`
- Test: `src/pages/opportunity-strategy-operations.test.ts`

**Interfaces:**
- Consumes: `CrmApi.listAccountSegments()` and `AccountSegmentSelect`
- Local page state: `segments = ref(['Frontend', 'Advanced Packaging'])`

- [ ] **Step 1: Write failing page tests**

For AccountsPage, open the new-account modal, select custom, enter `Power Semiconductor`, submit valid required fields, reopen the modal, and assert `Power Semiconductor` is now a normal option. Also assert the page filter includes it and selecting it returns the created account.

For AccountDetailPage, open edit and assert the reusable selector renders the globally loaded options and submits a custom value through `updateAccount`.

- [ ] **Step 2: Run focused page tests and verify RED**

Run: `pnpm test -- src/pages/mvp-workflow.test.ts src/pages/opportunity-strategy-operations.test.ts`

Expected: FAIL because pages still hard-code two options.

- [ ] **Step 3: Integrate the API and selector**

Load segments alongside page data with the existing request-error handling. Render the filter from `segments`. Replace create/edit hard-coded selects with `AccountSegmentSelect`. After a successful create/update, merge the saved segment into local options immediately so it is available without a full reload.

- [ ] **Step 4: Run focused page tests and verify GREEN**

Run the command from Step 2.

Expected: PASS.

### Task 5: Lead conversion integration

**Files:**
- Modify: `src/pages/LeadDetailPage.vue`
- Modify: `src/features/leads/LeadConvertModal.vue`
- Test: `src/pages/leads.test.ts`

**Interfaces:**
- `LeadConvertModal` gains required prop `segments: string[]`
- Consumes: `AccountSegmentSelect` for `newAccount.segment`

- [ ] **Step 1: Write the failing conversion test**

Open Lead conversion, choose the custom option, enter `Power Semiconductor`, submit, and assert the emitted `LeadConversionInput.newAccount.segment` equals the custom value. Mount the detail page with Mock API and assert the loaded global options are passed to the modal.

- [ ] **Step 2: Run the located Lead test and verify RED**

Run: `pnpm test -- src/pages/leads.test.ts`

Expected: FAIL because the modal still has a fixed select and no `segments` prop.

- [ ] **Step 3: Implement Lead integration**

Load `listAccountSegments()` in LeadDetailPage with its existing account/contact/site bootstrap. Pass the result into LeadConvertModal and replace the fixed segment select with `AccountSegmentSelect`.

- [ ] **Step 4: Run the located Lead test and verify GREEN**

Run the command from Step 2.

Expected: PASS.

### Task 6: Regression and completion audit

**Files:**
- Review only all files changed by Tasks 1-5.

- [ ] **Step 1: Run all focused frontend tests**

Run: `pnpm test -- src/features/accounts/AccountSegmentSelect.test.ts src/api/frappe-adapter.test.ts src/api/mock-adapter.test.ts src/pages/mvp-workflow.test.ts src/pages/opportunity-strategy-operations.test.ts src/pages/leads.test.ts`

Expected: all PASS with zero failures.

- [ ] **Step 2: Run full frontend verification**

Run: `pnpm test`

Run: `pnpm build`

Expected: both exit 0.

- [ ] **Step 3: Run focused backend verification**

Run: `docker compose exec -T backend bench --site crm.localhost run-tests --app rayher_crm --module rayher_crm.tests.test_account_contact_api`

Expected: PASS.

- [ ] **Step 4: Audit requirements against evidence**

Confirm from tests and source that: the custom entry is last; blank values fail; new values persist globally; create, edit, Lead conversion, and list filtering use the same registry; existing values remain; duplicates are impossible under normal and repeated requests.

- [ ] **Step 5: Review exact diffs without staging unrelated work**

Run: `git diff -- backend/apps/rayher_crm/rayher_crm/services/accounts.py backend/apps/rayher_crm/rayher_crm/api/v1/accounts.py backend/apps/rayher_crm/rayher_crm/tests/test_account_contact_api.py src/types/crm.ts src/api/contracts.ts src/api/frappe-adapter.ts src/api/frappe-adapter.test.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts src/features/accounts/AccountSegmentSelect.vue src/features/accounts/AccountSegmentSelect.test.ts src/pages/AccountsPage.vue src/pages/AccountDetailPage.vue src/pages/mvp-workflow.test.ts src/pages/opportunity-strategy-operations.test.ts src/pages/LeadDetailPage.vue src/features/leads/LeadConvertModal.vue src/pages/leads.test.ts` and verify every changed hunk maps to this feature. Do not stage or commit pre-existing changes.
