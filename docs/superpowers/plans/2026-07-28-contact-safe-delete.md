# Contact Safe Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Administrator-only recoverable Contact deletion, default-hide archived records, and identify migrated `Needs Review` data.

**Architecture:** Extend the existing Contact capability/API boundary with `contact:delete` and `deleteContact(id)`. Mock deletion changes only `status` and `updatedAt`; it never removes IDs or rewrites business references. The Vue list and detail pages expose the operation while keeping Archived records available through an explicit filter.

**Tech Stack:** Vue 3, TypeScript, Vue Router, Vitest, existing Mock/Frappe adapters and CRM design system.

## Global Constraints

- No physical deletion.
- Only CRM Administrator can delete.
- Preserve every Opportunity, Booking, Demo Request, Visit, reporting, and timeline reference.
- Default Contacts list excludes Archived.
- Frappe returns explicit `NOT_IMPLEMENTED`.
- Do not perform Git submission operations.

---

### Task 1: Safe Contact Delete and Data-Quality Visibility

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/domain/permissions.ts`
- Modify: `src/domain/permissions.test.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/pages/ContactsPage.vue`
- Modify: `src/pages/ContactDetailPage.vue`
- Modify: `src/pages/contacts.test.ts`

**Interfaces:**
- Produces `contact:delete`.
- Produces `CrmApi.deleteContact(id: string): Promise<ApiResponse<{ id: string; status: 'Archived' }>>`.
- Reuses `ContactDto.status`, `ContactDto.dataQuality`, and existing permission/error patterns.

- [ ] **Step 1: Write failing API and page tests**

Add assertions that:

```ts
const admin = createMockApi({ role: 'CRM Administrator', latency: 0 })
const result = await admin.deleteContact('CT-MIG-STK-OPP-003-1')
expect(result.data).toEqual({ id: 'CT-MIG-STK-OPP-003-1', status: 'Archived' })
expect((await admin.getContact('CT-MIG-STK-OPP-003-1')).data.contact.status).toBe('Archived')
```

Also verify non-admin denial, preserved related Opportunity/Booking/Demo references, repeated delete idempotence, default list exclusion, Archived filtering, Needs Review badge, delete confirmation, and hidden actions on Archived detail.

- [ ] **Step 2: Run RED**

Run:

```powershell
node_modules/.bin/vitest.CMD run --exclude .superpowers/** src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts src/pages/contacts.test.ts
```

Expected: failure because capability, API method, filter semantics, and UI action do not exist.

- [ ] **Step 3: Implement the minimal domain/API change**

Add `contact:delete` only to the Administrator profile and API contract:

```ts
deleteContact(id: string): Promise<ApiResponse<{ id: string; status: 'Archived' }>>
```

Mock implementation:

```ts
const deleteContactInternal = async (id: string) => {
  assertCapability(capabilities, 'contact:delete')
  const contact = localContacts.find((item) => item.id === id)
  if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到联系人', requestId(), false)
  contact.status = 'Archived'
  contact.updatedAt = '2026-07-28'
  await salesRepository.save(snapshot => ({ ...snapshot, contacts: localContacts }))
  return ok({ id, status: 'Archived' as const })
}
```

Do not mutate any other collection. Frappe method throws explicit `NOT_IMPLEMENTED`.

- [ ] **Step 4: Implement the minimal UI change**

- Make the default list request `contactStatus: 'Active'` unless an explicit URL/status filter is present.
- Render `Needs Review` as a visible badge in list rows and Contact 360.
- Add Administrator-only “删除联系人” on active Contact detail.
- Use the existing confirmation/modal pattern.
- After success, navigate to `/contacts` and show the refreshed active list.
- Archived detail hides edit, merge, delete, and create-business actions.

- [ ] **Step 5: Run GREEN and typecheck**

Run:

```powershell
node_modules/.bin/vitest.CMD run --exclude .superpowers/** src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts src/pages/contacts.test.ts
pnpm.cmd run typecheck
```

Expected: focused tests pass; typecheck exit code 0.

- [ ] **Step 6: Browser acceptance**

Verify `/contacts`, a `Needs Review` detail, delete confirmation, post-delete list behavior, `contactStatus=Archived`, console health, and a desktop screenshot.

- [ ] **Step 7: Report**

Record changed files, RED/GREEN evidence, browser URL, and the explicit Mock/Frappe boundary. Do not run Git add, commit, push, or PR operations.
