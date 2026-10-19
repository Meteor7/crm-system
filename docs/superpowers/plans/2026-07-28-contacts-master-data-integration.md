# Contacts Master Data Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing stakeholder capability into a Contacts master-data module with an independent detail subpage and Contact-ID links across Opportunity, Booking, Demo Request, and Visit workflows.

**Architecture:** Keep one customer-scoped Contact master collection in the API adapter. Opportunity stores a Contact-ID relationship with opportunity-only buying fields; Booking and Demo Request store one primary Contact ID; Visit stores multiple Contact-ID participants. Vue pages consume expanded read DTOs, but every write contract uses IDs so changing a contact updates all related views.

**Tech Stack:** Vue 3.5, TypeScript 5.9, Vue Router 5, Pinia 4, Vitest 4, Vue Test Utils, existing CRM design-system components, Mock/Frappe adapter contract.

## Global Constraints

- Use `/contacts` for the list and `/contacts/:contactId` for the independent detail subpage; do not use a drawer for Contact details.
- Keep the current navy, warm-white, teal, and amber CRM design system; do not copy the Salesforce shell.
- One Contact has one current `accountId` and an optional same-account `siteId`.
- Opportunity supports multiple Contacts; Visit supports multiple participants; Booking and Demo Request each use one primary Contact.
- All business writes use Contact IDs; name/title/phone/email are expanded read fields or generated-document snapshots.
- Opportunity buying role, influence, attitude, coach flag, coverage evidence, win result, and notes never overwrite Contact master fields.
- Existing Opportunity stakeholders migrate without data loss; ambiguous matches remain separate and receive `Needs Review`.
- Mock success is not formal Frappe completion. Unsupported Frappe writes return explicit `NOT_IMPLEMENTED`.
- No Campaign, mass email, label management, Cases, file upload, or CSV import in this feature.
- Before every task, run `git status --short` and re-read every target file. If another worker changed a target after this plan was written, patch the newest version and never restore or overwrite their work.
- Stage and commit only the files named by the current task; never use `git reset --hard`, `git checkout --`, or whole-tree cleanup.
- Use `pnpm.cmd` on Windows.

---

### Task 1: Contact Domain Types and Idempotent Legacy Migration

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/api/mock-data.ts`
- Modify: `src/demo/operations-data.ts`
- Modify: `src/demo/sales-repository.ts`
- Create: `src/domain/contacts.ts`
- Create: `src/domain/contacts.test.ts`
- Modify: `src/domain/stakeholders.ts`
- Modify: `src/domain/stakeholders.test.ts`

**Interfaces:**
- Produces:
  - `ContactStatus`, `ContactDataQuality`, `ContactDto`, `ContactSummaryDto`, `ContactInput`
  - `ContactListQuery`, `ContactTimelineItemDto`, `ContactDetailDto`
  - `VisitParticipantDto`
  - `OpportunityStakeholderDto.contactId`
  - `OpportunityStakeholderInput` without editable `name` or `title`
  - `LegacyStrategyOpportunityDto` for migration inputs and version-1 cached data
  - `migrateLegacyOpportunityContacts(contacts, opportunities)`
  - `expandOpportunityContact(link, contacts)`
- Consumes: existing `AccountSummaryDto`, `SiteDto`, `StrategyOpportunityDto`, `VisitDto`, `DemoRequestDto`, and `BookingDto`.

- [ ] **Step 1: Write failing migration and reporting-line tests**

Add tests that prove exact matching, unmatched creation, ambiguity handling, idempotence, customer isolation, and the renamed reporting field:

```ts
import { describe, expect, it } from 'vitest'
import { migrateLegacyOpportunityContacts } from './contacts'
import type { ContactDto } from '@/types/crm'
import type { LegacyStrategyOpportunityDto } from '@/types/workspaces'

describe('contact master migration', () => {
  it('reuses a unique same-account contact and creates an id-based relationship', () => {
    const contacts: ContactDto[] = [{
      id: 'CT-001', accountId: 'ACC-001', name: '王志远', title: '设备副总经理',
      department: '制造运营', relationship: 'Strong', owner: 'Demo Staff 01',
      status: 'Active', dataQuality: 'Complete', updatedAt: '2026-07-28',
    }]
    const opportunities = [{
      id: 'OPP-001', accountId: 'ACC-001',
      stakeholders: [{
        id: 'STK-001', name: '王志远', title: '设备副总经理',
        role: 'Economic Buyer', influence: 'High', stance: 'Neutral',
        coverage: 'Manager relationship',
      }],
    }] as LegacyStrategyOpportunityDto[]

    const migrated = migrateLegacyOpportunityContacts(contacts, opportunities)

    expect(migrated.contacts).toHaveLength(1)
    expect(migrated.opportunities[0].stakeholders[0]).toMatchObject({
      contactId: 'CT-001',
      role: 'Economic Buyer',
      influence: 'High',
    })
  })

  it('creates one Needs Review contact for an unmatched stakeholder and stays idempotent', () => {
    const first = migrateLegacyOpportunityContacts([], [{
      id: 'OPP-007', accountId: 'ACC-005',
      stakeholders: [{
        id: 'STK-007', name: '马会东', title: '封装事业部总经理',
        role: 'Economic Buyer', influence: 'High', stance: 'Neutral',
        coverage: 'No direct access',
      }],
    }] as LegacyStrategyOpportunityDto[])
    const second = migrateLegacyOpportunityContacts(first.contacts, first.opportunities)

    expect(first.contacts[0]).toMatchObject({
      accountId: 'ACC-005',
      name: '马会东',
      dataQuality: 'Needs Review',
    })
    expect(second.contacts).toEqual(first.contacts)
    expect(second.opportunities).toEqual(first.opportunities)
  })
})
```

Update `src/domain/stakeholders.test.ts` to use `reportsToContactId` and verify that cross-account parents are rejected.

- [ ] **Step 2: Run the domain tests and verify RED**

Run:

```powershell
pnpm.cmd exec vitest run src/domain/contacts.test.ts src/domain/stakeholders.test.ts
```

Expected: FAIL because Contact master fields, migration functions, and `reportsToContactId` do not exist.

- [ ] **Step 3: Define the exact Contact and relationship types**

In `src/types/crm.ts`, replace the customer-level buying fields with master-data fields and add read models:

```ts
export type ContactStatus = 'Active' | 'Left Company' | 'Archived'
export type ContactDataQuality = 'Complete' | 'Needs Review'

export interface ContactDto {
  id: string
  accountId: string
  siteId?: string
  name: string
  title: string
  department: string
  phone?: string
  email?: string
  reportsToContactId?: string
  relationship: 'Strong' | 'Developing' | 'Weak'
  owner: string
  status: ContactStatus
  dataQuality: ContactDataQuality
  mergedIntoContactId?: string
  updatedAt: string
}

export interface ContactSummaryDto extends ContactDto {
  accountName: string
  accountShortName: string
  siteName?: string
  opportunityRoles: string[]
}

export interface ContactInput extends Omit<ContactDto, 'id' | 'dataQuality' | 'updatedAt'> {
  id?: string
}

export interface ContactListQuery extends ListQuery {
  siteId?: string
  contactId?: string
  contactStatus?: ContactStatus | 'All'
}

export interface VisitParticipantDto {
  contactId: string
  isPrimary: boolean
  meetingRole?: string
}
```

In `src/types/workspaces.ts`, make Opportunity input ID-based while keeping expanded read labels:

```ts
export interface OpportunityStakeholderDto {
  id: string
  contactId: string
  name: string
  title: string
  role: string
  influence: string
  stance: string
  coverage: string
  isCoach?: boolean
  winResult?: string
  opportunityNotes?: string
}

export type OpportunityStakeholderInput =
  Omit<OpportunityStakeholderDto, 'id' | 'name' | 'title'> & { id?: string }

export interface LegacyOpportunityStakeholderDto
  extends Omit<OpportunityStakeholderDto, 'contactId'> {
  contactId?: string
}

export interface LegacyStrategyOpportunityDto
  extends Omit<StrategyOpportunityDto, 'stakeholders'> {
  stakeholders: LegacyOpportunityStakeholderDto[]
}
```

- Keep the existing deprecated `StakeholderInput` as a separate compatibility interface until Task 3 redirects the old page. It maps into `ContactInput` in Task 2 and must not be used by new UI.
- Add optional deprecated `role`, `influence`, and `reportsTo` read fields only if required to keep the old unused page compiling between tasks; remove their usage in Task 3.
- Change `Account360Dto.contacts` to `ContactSummaryDto[]`.

- [ ] **Step 4: Implement deterministic migration and Contact expansion**

Create `src/domain/contacts.ts` with normalized comparison and stable IDs derived from the legacy stakeholder ID:

```ts
const normalized = (value: string | undefined) =>
  String(value ?? '').trim().toLocaleLowerCase().replace(/\s+/g, ' ')

export function expandOpportunityContact(
  link: OpportunityStakeholderDto,
  contacts: readonly ContactDto[],
): OpportunityStakeholderDto {
  const contact = contacts.find((item) => item.id === link.contactId)
  return {
    ...link,
    name: contact?.name ?? '联系人已缺失',
    title: contact?.title ?? '—',
  }
}
```

`migrateLegacyOpportunityContacts` accepts `LegacyStrategyOpportunityDto[]` and must:

1. Check an existing `contactId` first.
2. Match only inside `opportunity.accountId`.
3. Prefer unique normalized email when a legacy email exists.
4. Otherwise use normalized `name + title`.
5. Create `CT-MIG-<stakeholderId>` when no unique match exists.
6. Set `dataQuality: 'Needs Review'` for created or ambiguous records.
7. Return cloned inputs and produce the same result when called twice.

- [ ] **Step 5: Flatten the existing contact seed and add master fields**

Change `src/api/mock-data.ts` from `Record<string, ContactDto[]>` to a single `ContactDto[]`. Preserve existing IDs and names, add their `accountId`, owner inherited from the matching account, `Active`, relationship, and `updatedAt`.

Do not invent phone, email, site, or reporting relationships where the seed does not provide them.

Add optional `contactId` to the raw `StrategyOpportunity.stakeholders` seed shape in `src/demo/operations-data.ts`.

Upgrade the sales repository explicitly:

```ts
interface SalesSnapshotV1 {
  version: 1
  bookings: BookingDto[]
  visits: VisitDto[]
  opportunities: LegacyStrategyOpportunityDto[]
}

export interface SalesSnapshot {
  version: 2
  contacts: ContactDto[]
  bookings: BookingDto[]
  visits: VisitDto[]
  opportunities: StrategyOpportunityDto[]
}
```

Implement `migrateSalesSnapshot(snapshot)` in `src/demo/sales-repository.ts`. For version 1 it starts from the checked-in Contact seed, runs `migrateLegacyOpportunityContacts`, returns version 2, and is idempotent for version 2. `seed()` also runs the same normalization. `getSharedSalesRepository` accepts version 1 or 2 JSON, saves the migrated version 2 snapshot, and never keeps Contacts in a second adapter-local collection.

Do not write expanded Contact names back as an independently editable input; Opportunity writes still persist Contact ID plus opportunity-only fields.

- [ ] **Step 6: Run the domain tests and verify GREEN**

Run:

```powershell
pnpm.cmd exec vitest run src/domain/contacts.test.ts src/domain/stakeholders.test.ts
```

Expected: PASS for matching, unmatched preservation, idempotence, customer isolation, and cycle prevention.

- [ ] **Step 7: Commit the domain unit**

```powershell
git add -- src/types/crm.ts src/types/workspaces.ts src/api/mock-data.ts src/demo/operations-data.ts src/demo/sales-repository.ts src/domain/contacts.ts src/domain/contacts.test.ts src/domain/stakeholders.ts src/domain/stakeholders.test.ts
git -c user.name=Codex -c user.email=codex@local commit -m "feat: add contact master domain"
```

---

### Task 2: Contact Permissions, API Contract, Mock Storage, and Frappe Boundary

**Files:**
- Modify: `src/domain/permissions.ts`
- Modify: `src/domain/permissions.test.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/api/frappe-adapter.test.ts`
- Modify: `src/types/crm.ts`

**Interfaces:**
- Consumes: Contact types and migration functions from Task 1.
- Produces:
  - capabilities `contact:view`, `contact:write`, `contact:merge`
  - `CrmApi.listContacts`, `getContact`, `saveContact`, `mergeContacts`
  - `ContactDetailDto`
  - backward-compatible `listStakeholders`/`saveStakeholder` wrappers used only until UI migration finishes.

- [ ] **Step 1: Write failing permission and API tests**

Add focused assertions:

```ts
it('lists role-visible contacts and writes within the sales account scope', async () => {
  const api = createMockApi({ role: 'Sales User', latency: 0 })
  const listed = await api.listContacts({ accountId: 'ACC-001' })
  expect(listed.data.items.every((item) => item.accountId === 'ACC-001')).toBe(true)

  const created = await api.saveContact({
    accountId: 'ACC-001',
    name: '许工',
    title: '设备经理',
    department: '设备工程',
    relationship: 'Developing',
    owner: 'Demo Staff 01',
    status: 'Active',
  })
  expect((await api.getContact(created.data.id)).data.contact.name).toBe('许工')
})

it('rejects a Contact site or reporting parent from another account', async () => {
  const api = createMockApi({ role: 'CRM Administrator', latency: 0 })
  await expect(api.saveContact({
    accountId: 'ACC-001',
    siteId: 'SITE-005',
    name: '跨客户联系人',
    title: '经理',
    department: '采购',
    relationship: 'Developing',
    owner: 'Demo Staff 01',
    status: 'Active',
  })).rejects.toMatchObject({ code: 'CONTACT_ACCOUNT_MISMATCH' })
})
```

Add permission tests proving Management Viewer is read-only and engineering roles do not receive `contact:view` for the standalone module.

Add an Administrator-only merge test:

```ts
it('merges a duplicate by rewriting every Contact-ID reference', async () => {
  const api = createMockApi({ role: 'CRM Administrator', latency: 0 })
  const duplicate = await api.saveContact({
    accountId: 'ACC-001',
    name: '王志远（重复）',
    title: '设备副总经理',
    department: '制造运营',
    relationship: 'Developing',
    owner: 'Demo Staff 01',
    status: 'Active',
  })
  await api.mergeContacts({ survivorId: 'CON-001', duplicateId: duplicate.data.id })

  const archived = (await api.getContact(duplicate.data.id)).data.contact
  expect(archived).toMatchObject({
    status: 'Archived',
    mergedIntoContactId: 'CON-001',
  })
})
```

- [ ] **Step 2: Run focused API tests and verify RED**

Run:

```powershell
pnpm.cmd exec vitest run src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts
```

Expected: FAIL because Contact capabilities and API methods are absent.

- [ ] **Step 3: Add Contact capabilities without breaking legacy callers**

Extend `Capability` and role profiles:

```ts
| 'contact:view' | 'contact:write' | 'contact:merge'
```

Grant:

- Administrator: all three.
- Sales Manager: `contact:view`, `contact:write`.
- Sales User: `contact:view`, `contact:write`.
- Management Viewer: `contact:view`.
- Engineering roles: none of the standalone Contact capabilities.

Keep `stakeholder:view` and `stakeholder:write` temporarily in the union and existing profiles so unrelated tests do not fail before the old page is redirected. No new page may consume the legacy capabilities.

- [ ] **Step 4: Add exact CrmApi methods and detail DTO**

In `src/types/crm.ts`:

```ts
export interface ContactTimelineItemDto {
  id: string
  at: string
  type: 'Opportunity' | 'Visit' | 'Demo Request' | 'Booking'
  title: string
  summary: string
  href: string
}

export interface ContactDetailDto {
  contact: ContactSummaryDto
  reportsTo?: ContactSummaryDto
  directReports: ContactSummaryDto[]
  opportunities: Array<{ id: string; title: string; stage: string; role: string; href: string }>
  visits: Array<{ id: string; subject: string; date: string; href: string }>
  demoRequests: Array<{ id: string; title: string; status: string; href: string }>
  bookings: Array<{ id: string; title: string; status: string; href: string }>
  timeline: ContactTimelineItemDto[]
}
```

In `src/api/contracts.ts`:

```ts
listContacts(query: ContactListQuery): Promise<ApiResponse<PageData<ContactSummaryDto>>>
getContact(id: string): Promise<ApiResponse<ContactDetailDto>>
saveContact(input: ContactInput): Promise<ApiResponse<ContactSummaryDto>>
mergeContacts(input: {
  survivorId: string
  duplicateId: string
}): Promise<ApiResponse<ContactSummaryDto>>
```

- [ ] **Step 5: Normalize Contact storage and implement Mock API operations**

At `createMockApi` initialization:

```ts
const localContacts = salesRepository.snapshot.contacts
const localStrategyOpportunities = salesRepository.snapshot.opportunities
```

The repository migration from Task 1 guarantees both arrays are normalized before the adapter receives them.

Add helpers:

```ts
function contactsForAccount(accountId: string) {
  return localContacts.filter((contact) => contact.accountId === accountId)
}

function contactSummary(contact: ContactDto): ContactSummaryDto {
  const account = currentAccounts().find((item) => item.id === contact.accountId)
  const site = (localSites[contact.accountId] ?? []).find((item) => item.id === contact.siteId)
  const opportunityRoles = localStrategyOpportunities.flatMap((opportunity) =>
    opportunity.stakeholders
      .filter((link) => link.contactId === contact.id)
      .map((link) => link.role),
  )
  return {
    ...contact,
    accountName: account?.name ?? '客户已缺失',
    accountShortName: account?.shortName ?? '—',
    ...(site ? { siteName: site.name } : {}),
    opportunityRoles: [...new Set(opportunityRoles)],
  }
}
```

`listContacts` must apply visibility before search and filters. `saveContact` must validate account scope, same-account site, same-account reporting parent, active values, and reporting cycles. `getContact` must aggregate by Contact ID and sort timeline descending.

`mergeContacts` requires `contact:merge`, rejects cross-account pairs, and rejects a merge when both Contacts already occur in the same Opportunity with `CONTACT_MERGE_CONFLICT`. In this task it rewrites Opportunity links and reporting relationships from `duplicateId` to `survivorId`, then marks the duplicate `Archived` with `mergedIntoContactId`. Tasks 5 and 6 extend the same method for Booking/Demo primary IDs and Visit participants as those fields are introduced. It never hard-deletes the duplicate.

Implement `listContactsInternal` and `saveContactInternal` as local functions before returning the `CrmApi` object, then keep compatibility wrappers without recursively calling the object under construction:

```ts
const listContactsInternal = async (query: ContactListQuery) => {
  // visibility, search, filters, summary expansion
}

const saveContactInternal = async (input: ContactInput) => {
  // scope and relationship validation, create/update, summary expansion
}

return {
  listContacts: listContactsInternal,
  saveContact: saveContactInternal,
  listStakeholders: listContactsInternal,
  saveStakeholder: (input) => saveContactInternal(mapLegacyStakeholderInput(input)),
  // existing API methods
}
```

These wrappers must not create a second collection.

- [ ] **Step 6: Make Frappe support explicit**

Map `getAccount360` contacts into the new master shape using the account ID already known to the method. For standalone methods return:

```ts
listContacts: () => Promise.reject(
  new CrmApiError('NOT_IMPLEMENTED', 'Frappe Contacts 列表接口尚未接入。', 'local-contract'),
),
getContact: () => Promise.reject(
  new CrmApiError('NOT_IMPLEMENTED', 'Frappe Contact 详情聚合接口尚未接入。', 'local-contract'),
),
saveContact: () => Promise.reject(
  new CrmApiError('NOT_IMPLEMENTED', 'Frappe Contact 写接口尚未接入。', 'local-contract'),
),
mergeContacts: () => Promise.reject(
  new CrmApiError('NOT_IMPLEMENTED', 'Frappe Contact 合并接口尚未接入。', 'local-contract'),
),
```

Do not fall back to Mock or local browser storage.

- [ ] **Step 7: Run focused API tests and verify GREEN**

Run:

```powershell
pnpm.cmd exec vitest run src/domain/permissions.test.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts
```

Expected: PASS for Contact scope, write validation, aggregation, permission denial, and explicit Frappe boundaries.

- [ ] **Step 8: Commit the API unit**

```powershell
git add -- src/domain/permissions.ts src/domain/permissions.test.ts src/api/contracts.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.ts src/api/frappe-adapter.test.ts src/types/crm.ts
git -c user.name=Codex -c user.email=codex@local commit -m "feat: add contacts api contract"
```

---

### Task 3: Contacts List, Independent Detail Subpage, and Contact Form

**Files:**
- Create: `src/pages/ContactsPage.vue`
- Create: `src/pages/ContactDetailPage.vue`
- Create: `src/features/contacts/ContactModal.vue`
- Create: `src/features/contacts/ContactPicker.vue`
- Create: `src/features/contacts/ContactMergeModal.vue`
- Create: `src/pages/contacts.test.ts`
- Modify: `src/app/router.ts`
- Modify: `src/app/navigation.ts`
- Modify: `src/app/AppShell.test.ts`
- Modify: `src/pages/customer-operations.test.ts`

**Interfaces:**
- Consumes: `CrmApi.listContacts`, `getContact`, `saveContact`, Contact DTOs, `PageHeader`, `FilterBar`, `DataState`, `StatusBadge`, and `ModalShell`.
- Produces:
  - `/contacts`
  - `/contacts/:contactId`
  - `/stakeholders` redirect
  - reusable `ContactPicker` and `ContactModal` used by Tasks 4–6.
  - Administrator-only duplicate merge action from the Contact data-quality panel.

- [ ] **Step 1: Write failing route, list, detail, and form tests**

Create `src/pages/contacts.test.ts`:

```ts
it('opens an independent detail route instead of a drawer', async () => {
  const router = createAppRouter()
  await router.push('/contacts')
  const wrapper = mount(ContactsPage, {
    props: { apiClient: createMockApi({ latency: 0 }) },
    global: { plugins: [createPinia(), router] },
  })
  await flushPromises()

  await wrapper.get('[data-contact-id="CON-001"]').trigger('click')
  await flushPromises()

  expect(router.currentRoute.value.path).toBe('/contacts/CON-001')
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})

it('renders related business links on the Contact detail subpage', async () => {
  const router = createAppRouter()
  await router.push('/contacts/CON-001')
  const wrapper = mount(ContactDetailPage, {
    props: { apiClient: createMockApi({ latency: 0 }) },
    global: { plugins: [createPinia(), router] },
  })
  await flushPromises()

  expect(wrapper.get('[data-related="opportunities"]').attributes('href')).toContain('contactId=CON-001')
  expect(wrapper.get('[data-related="visits"]').attributes('href')).toContain('contactId=CON-001')
})
```

Add tests for search, account/status filters, empty/error/denied states, Contact edit, same-account site options, and `/stakeholders` redirect.

Add a detail-page test proving only an Administrator sees “合并重复联系人”, selects a same-account candidate, and is redirected to the survivor Contact after a successful merge.

- [ ] **Step 2: Run page tests and verify RED**

Run:

```powershell
pnpm.cmd exec vitest run src/pages/contacts.test.ts src/app/AppShell.test.ts src/pages/customer-operations.test.ts
```

Expected: FAIL because the routes, navigation item, pages, and components do not exist.

- [ ] **Step 3: Add routes and navigation**

In `src/app/router.ts`:

```ts
{ path: '/contacts', name: 'contacts', component: () => import('@/pages/ContactsPage.vue') },
{ path: '/contacts/:contactId', name: 'contact-detail', component: () => import('@/pages/ContactDetailPage.vue') },
{ path: '/stakeholders', redirect: '/contacts' },
```

In `src/app/navigation.ts`, import `ContactRound` and add the Sales item directly after Accounts:

```ts
{ key: 'contacts', label: '联系人', path: '/contacts', icon: ContactRound, capabilities: ['contact:view'] }
```

- [ ] **Step 4: Implement the reusable Contact form and picker**

`ContactModal.vue` accepts:

```ts
defineProps<{
  contact?: ContactDto | null
  accounts: AccountSummaryDto[]
  sites: SiteDto[]
  contacts: ContactSummaryDto[]
  fixedAccountId?: string
  busy?: boolean
}>()

defineEmits<{
  close: []
  submit: [payload: ContactInput]
}>()
```

It renders name, account, site, title, department, phone, email, reports-to, relationship, owner, and status. When `fixedAccountId` is present, the account field is disabled.

`ContactPicker.vue` accepts all accessible contacts plus `accountId`, filters to Active Contacts in that account, displays `name · title`, and emits `create` when the user clicks “快速新增联系人”.

`ContactMergeModal.vue` lists same-account Contacts except the current record and emits:

```ts
defineEmits<{
  close: []
  submit: [payload: { survivorId: string; duplicateId: string }]
}>()
```

The current Contact is the default survivor. The modal explains that all business links move to the survivor and the duplicate becomes Archived.

- [ ] **Step 5: Implement the Contacts list**

`ContactsPage.vue` must:

- load bootstrap, accounts, and contacts;
- read initial `accountId`, `contactStatus`, and `search` query values;
- expose name, customer, site, title/department, phone, email, owner, status, updated date;
- route row/name click with:

```ts
await router.push({ name: 'contact-detail', params: { contactId: contact.id } })
```

- open `ContactModal` only for create/edit;
- never render Contact details in the modal;
- reload the list after saving while preserving filters.

- [ ] **Step 6: Implement the independent Contact detail page**

`ContactDetailPage.vue` must read `route.params.contactId`, call `getContact`, and render:

```vue
<RouterLink :to="{ name: 'contacts' }">返回联系人列表</RouterLink>
<RouterLink :to="{ name: 'accounts', query: { accountId: detail.contact.accountId } }">
  {{ detail.contact.accountName }}
</RouterLink>
<RouterLink
  v-if="detail.contact.reportsToContactId"
  :to="{ name: 'contact-detail', params: { contactId: detail.contact.reportsToContactId } }"
>
  {{ detail.reportsTo?.name }}
</RouterLink>
```

Use a responsive three-column page for Contact data/organization, activity timeline, and related business. Related `RouterLink`s use the protocol defined in the design spec. Header actions use:

```ts
router.push({ name: 'opportunities-booking', query: {
  view: 'opportunities',
  create: '1',
  accountId: detail.contact.accountId,
  contactId: detail.contact.id,
}})
```

and equivalent Visit prefilling.

The data-quality panel renders the merge action only when `app.can('contact:merge')`. On success it reloads the survivor detail; on `CONTACT_MERGE_CONFLICT` it shows the API message without changing either Contact.

- [ ] **Step 7: Run page tests and verify GREEN**

Run:

```powershell
pnpm.cmd exec vitest run src/pages/contacts.test.ts src/app/AppShell.test.ts src/pages/customer-operations.test.ts
```

Expected: PASS for navigation, independent route, list filtering, detail links, form validation, and permission states.

- [ ] **Step 8: Commit the Contacts UI unit**

```powershell
git add -- src/pages/ContactsPage.vue src/pages/ContactDetailPage.vue src/features/contacts/ContactModal.vue src/features/contacts/ContactPicker.vue src/features/contacts/ContactMergeModal.vue src/pages/contacts.test.ts src/app/router.ts src/app/navigation.ts src/app/AppShell.test.ts src/pages/customer-operations.test.ts
git -c user.name=Codex -c user.email=codex@local commit -m "feat: add contacts list and detail pages"
```

---

### Task 4: Opportunity Contact-ID Relationships and Contact Deep Links

**Files:**
- Modify: `src/features/opportunities/StakeholderEditorModal.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/pages/opportunity-strategy-operations.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/demo/sales-repository.ts`
- Modify: `src/types/workspaces.ts`

**Interfaces:**
- Consumes: `ContactPicker`, `ContactModal`, Contact API, `OpportunityStakeholderInput.contactId`.
- Produces: ID-only Opportunity relationship writes, master-expanded names/titles, `contactId` route filtering, and Contact detail links.

- [ ] **Step 1: Write failing API and Opportunity page tests**

Add API proof that a master edit updates Opportunity display:

```ts
it('expands Opportunity people from the Contact master after edits', async () => {
  const api = createMockApi({ role: 'CRM Administrator', latency: 0 })
  const opportunity = (await api.listStrategyOpportunities()).data[0]
  const person = opportunity.stakeholders[0]
  const contact = (await api.getContact(person.contactId)).data.contact

  await api.saveContact({
    id: contact.id,
    accountId: contact.accountId,
    ...(contact.siteId ? { siteId: contact.siteId } : {}),
    name: '王志远（更新）',
    title: contact.title,
    department: contact.department,
    ...(contact.phone ? { phone: contact.phone } : {}),
    ...(contact.email ? { email: contact.email } : {}),
    ...(contact.reportsToContactId ? { reportsToContactId: contact.reportsToContactId } : {}),
    relationship: contact.relationship,
    owner: contact.owner,
    status: contact.status,
  })
  const refreshed = (await api.listStrategyOpportunities()).data
    .find((item) => item.id === opportunity.id)!

  expect(refreshed.stakeholders.find((item) => item.contactId === person.contactId)?.name)
    .toBe('王志远（更新）')
})
```

Update the page operation test to select an existing Contact ID, add opportunity-only fields, click the name, and assert navigation to `/contacts/<id>`.

- [ ] **Step 2: Run Opportunity tests and verify RED**

Run:

```powershell
pnpm.cmd exec vitest run src/pages/opportunity-strategy-operations.test.ts src/api/mock-adapter.test.ts
```

Expected: FAIL because Opportunity inputs still edit independent names and titles.

- [ ] **Step 3: Make Mock Opportunity writes ID-only**

`saveOpportunityStakeholder` must:

1. Resolve `input.contactId`.
2. Reject missing Contacts with `CONTACT_NOT_FOUND`.
3. Reject Contacts from another account with `CONTACT_ACCOUNT_MISMATCH`.
4. Reject inactive Contacts with `CONTACT_INACTIVE`.
5. Reject duplicate `(opportunityId, contactId)` with `DUPLICATE_OPPORTUNITY_CONTACT`.
6. Persist opportunity-only fields and expand name/title from Contact master before returning.

`deleteOpportunityStakeholder` removes only the Opportunity link; it never deletes the Contact.

- [ ] **Step 4: Convert the Opportunity editor into a Contact selector**

Replace editable name/title inputs with `ContactPicker`. The form contains:

```ts
{
  id: stakeholder?.id,
  contactId: stakeholder?.contactId ?? '',
  role: stakeholder?.role ?? 'Influencer',
  influence: stakeholder?.influence ?? 'Medium',
  stance: stakeholder?.stance ?? 'Neutral',
  coverage: stakeholder?.coverage ?? '待建立覆盖',
  isCoach: stakeholder?.isCoach ?? false,
  winResult: stakeholder?.winResult ?? '',
  opportunityNotes: stakeholder?.opportunityNotes ?? '',
}
```

The picker receives Contacts for `selected.accountId`. “快速新增联系人” opens `ContactModal` with `fixedAccountId`; saving selects the new ID and returns to the Opportunity form.

- [ ] **Step 5: Add Opportunity links and query-driven filtering/prefill**

In the table:

```vue
<RouterLink :to="{ name: 'contact-detail', params: { contactId: person.contactId } }">
  {{ person.name }}
</RouterLink>
```

Read:

- `route.query.contactId` to filter Opportunities containing that Contact;
- `route.query.accountId` to preselect the customer for creation;
- `route.query.create === '1'` to open the creation modal once;
- `route.query.view` to select Opportunity or Booking.

Clear the one-shot `create` query with `router.replace` after opening so refresh does not reopen the modal.

- [ ] **Step 6: Run Opportunity tests and verify GREEN**

Run:

```powershell
pnpm.cmd exec vitest run src/pages/opportunity-strategy-operations.test.ts src/api/mock-adapter.test.ts
```

Expected: PASS for ID-only writes, master expansion, quick create, duplicate protection, detail navigation, and query filters.

- [ ] **Step 7: Commit the Opportunity unit**

```powershell
git add -- src/features/opportunities/StakeholderEditorModal.vue src/pages/OpportunityStrategyPage.vue src/pages/opportunity-strategy-operations.test.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts src/demo/sales-repository.ts src/types/workspaces.ts
git -c user.name=Codex -c user.email=codex@local commit -m "feat: link opportunities to contact master"
```

---

### Task 5: Booking and Demo Request Primary Contacts

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/api/mock-data.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/domain/contacts.ts`
- Modify: `src/domain/contacts.test.ts`
- Modify: `src/demo/sales-repository.ts`
- Modify: `src/features/opportunities/BookingEditorModal.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.vue`
- Modify: `src/features/demo-requests/DemoRequestModal.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.test.ts`
- Modify: `src/domain/demo-request-form.ts`
- Modify: `src/domain/demo-request-form.test.ts`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Modify: `src/features/demo-requests/demo-request-docx.ts`
- Modify: `src/features/demo-requests/demo-request-docx.test.ts`

**Interfaces:**
- Consumes: Contact API, `ContactPicker`, `ContactModal`.
- Produces:
  - `BookingDto.primaryContactId`
  - `UpsertBookingInput.primaryContactId`
  - `DemoRequestDto.primaryContactId`
  - `CreateDemoRequestInput.primaryContactId`
  - read-only compatibility display values `customerContact` and `formData.contactPerson`.
  - `migrateLegacyPrimaryContacts(contacts, bookings, demoRequests)` for existing text-only records.

- [ ] **Step 1: Write failing Booking and Demo tests**

Add:

```ts
it('stores Booking primary Contact by ID and derives the display name', async () => {
  const api = createMockApi({ role: 'CRM Administrator', latency: 0 })
  const contact = (await api.listContacts({ accountId: 'ACC-001' })).data.items[0]
  const created = await api.createBooking({
    accountId: 'ACC-001',
    primaryContactId: contact.id,
    equipment: 'FastScan 1200',
    quantity: 1,
    ddl: '2026-09-30',
    amount: 1000000,
    status: 'Pending',
    owner: 'Demo Staff 01',
    sourceOpportunityId: 'OPP-001',
    note: '',
  })
  expect(created.data).toMatchObject({
    primaryContactId: contact.id,
    customerContact: contact.name,
  })
})
```

Update Demo form tests so `contactPerson` is no longer a free-text input and selection writes `primaryContactId`. Keep DOCX tests proving the selected Contact’s display line is generated.

Add migration proof:

```ts
it('converts legacy Booking text into one stable Needs Review Contact', () => {
  const first = migrateLegacyPrimaryContacts([], [{
    id: 'BKG-001',
    accountId: 'ACC-006',
    customerContact: '演示员工20',
    owner: 'Demo Staff 02',
  }], [])
  const second = migrateLegacyPrimaryContacts(first.contacts, first.bookings, first.demoRequests)

  expect(first.contacts[0]).toMatchObject({
    id: 'CT-BKG-BKG-001',
    accountId: 'ACC-006',
    name: '演示员工20',
    dataQuality: 'Needs Review',
  })
  expect(first.bookings[0].primaryContactId).toBe(first.contacts[0].id)
  expect(second).toEqual(first)
})
```

- [ ] **Step 2: Run focused Booking/Demo tests and verify RED**

Run:

```powershell
pnpm.cmd exec vitest run src/api/mock-adapter.test.ts src/features/demo-requests/DemoRequestForm.test.ts src/domain/demo-request-form.test.ts src/features/demo-requests/demo-request-docx.test.ts src/pages/delivery-workflow.test.ts
```

Expected: FAIL because Booking and Demo Request still accept free-text customer names.

- [ ] **Step 3: Add primary Contact IDs and compatibility display fields**

Change Booking input:

```ts
export interface UpsertBookingInput {
  accountId: string
  primaryContactId: string
  equipment: string
  quantity: number
  ddl: string
  amount: number
  status: BookingDto['status']
  owner: string
  sourceOpportunityId: string
  note: string
}
```

`BookingDto` keeps `customerContact` only as a read response field derived by the adapter.

Add `primaryContactId` to `CreateDemoRequestInput` and `DemoRequestDto`. Keep `formData.contactPerson` as a generated compatibility snapshot for the current DOCX pipeline; UI code must never expose it as a free-text editor.

Define repository-only legacy shapes with optional `primaryContactId` so version-1 localStorage can be read, then normalize them before returning runtime DTOs. New API inputs always require the ID.

- [ ] **Step 4: Validate and derive contacts inside the Mock adapter**

Create `migrateLegacyPrimaryContacts` in `src/domain/contacts.ts`:

- Existing valid `primaryContactId` wins.
- Match text only inside the record’s account.
- For Booking, match normalized `customerContact` to Contact name; otherwise create `CT-BKG-<bookingId>`.
- For Demo Request, use the first comma-separated segment of `contactPerson` only as the retained name; otherwise create `CT-DR-<demoRequestId>`.
- Created records use the business owner, `Needs Review`, `Active`, blank title/department, and no invented phone/email/site.
- A second run returns an identical result.

Extend `migrateSalesSnapshot` to version 3:

- version 1 first receives the Task-1 Opportunity/Contact normalization;
- version 2 then runs `migrateLegacyPrimaryContacts` for Bookings;
- version 3 is returned unchanged;
- `SalesSnapshot.bookings` in version 3 always has `primaryContactId`.

For Demo Requests, add an adapter-local `ensureDemoPrimaryContacts()` promise. On its first call it reads the Demo repository, runs the same migration against `salesRepository.snapshot.contacts`, writes normalized Demo Requests through `repository.transact`, writes Contacts through `salesRepository.save`, and then resolves. Call it before `listContacts`, `getContact`, `listDemoRequests`, create/update Demo Request, and any Contact-detail aggregation. Concurrent callers share the same promise so they cannot create duplicate Contacts.

Create one shared validation helper:

```ts
function assertActiveContactForAccount(contactId: string, accountId: string) {
  const contact = localContacts.find((item) => item.id === contactId)
  if (!contact) throw new CrmApiError('CONTACT_NOT_FOUND', '未找到联系人', requestId(), false)
  if (contact.accountId !== accountId) {
    throw new CrmApiError('CONTACT_ACCOUNT_MISMATCH', '联系人不属于当前客户', requestId(), false)
  }
  if (contact.status !== 'Active') {
    throw new CrmApiError('CONTACT_INACTIVE', '离职或归档联系人不能新增业务关联', requestId(), false)
  }
  return contact
}
```

Use it in Booking and Demo Request create/update. When returning DTOs, derive `customerContact` and `formData.contactPerson` from the selected Contact.

Extend `mergeContacts` so `primaryContactId === duplicateId` becomes `survivorId` in every Booking and Demo Request. Add an API assertion that both related collections appear under the survivor after merge.

- [ ] **Step 5: Replace free-text inputs with ContactPicker and quick create**

`BookingEditorModal` receives `contacts` and emits `create-contact`. If account changes:

```ts
watch(() => form.value.accountId, () => {
  if (!contacts.some((item) =>
    item.id === form.value.primaryContactId &&
    item.accountId === form.value.accountId &&
    item.status === 'Active'
  )) form.value.primaryContactId = ''
})
```

`DemoRequestForm` renders `ContactPicker` using the selected account and writes `primaryContactId`. The parent owns `ContactModal`; after save it updates the Contact collection and selects the new ID.

- [ ] **Step 6: Add Contact query filters and Contact links**

- Booking tab reads `route.query.contactId` and shows only matching `primaryContactId`.
- Demo Requests page reads the same query and filters records.
- Booking and Demo Request displays wrap the Contact name in a `RouterLink` to `contact-detail`.
- A Contact detail `view=bookings` or Demo link must land on a filtered result, not an unfiltered page.

- [ ] **Step 7: Run focused Booking/Demo tests and verify GREEN**

Run:

```powershell
pnpm.cmd exec vitest run src/api/mock-adapter.test.ts src/features/demo-requests/DemoRequestForm.test.ts src/domain/demo-request-form.test.ts src/features/demo-requests/demo-request-docx.test.ts src/pages/delivery-workflow.test.ts
```

Expected: PASS for ID persistence, derived display values, quick create, account change clearing, route filtering, and DOCX contact snapshots.

- [ ] **Step 8: Commit the Booking/Demo unit**

```powershell
git add -- src/types/crm.ts src/api/mock-data.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts src/domain/contacts.ts src/domain/contacts.test.ts src/demo/sales-repository.ts src/features/opportunities/BookingEditorModal.vue src/pages/OpportunityStrategyPage.vue src/features/demo-requests/DemoRequestForm.vue src/features/demo-requests/DemoRequestModal.vue src/features/demo-requests/DemoRequestForm.test.ts src/domain/demo-request-form.ts src/domain/demo-request-form.test.ts src/pages/DemoRequestsPage.vue src/pages/delivery-workflow.test.ts src/features/demo-requests/demo-request-docx.ts src/features/demo-requests/demo-request-docx.test.ts
git -c user.name=Codex -c user.email=codex@local commit -m "feat: link booking and demos to contacts"
```

---

### Task 6: Visit Participants, Contact Prefill, and Contact Timeline

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/domain/visits.ts`
- Modify: `src/domain/visits.test.ts`
- Modify: `src/features/visits/VisitModal.vue`
- Modify: `src/pages/VisitsPage.vue`
- Modify: `src/pages/customer-operations.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/demo/sales-repository.ts`

**Interfaces:**
- Consumes: `VisitParticipantDto`, Contact API, `ContactPicker`, `ContactModal`.
- Produces: multi-Contact Visit participants, one primary participant, `/visits?contactId=` filtering, and Contact detail visit timeline entries.

- [ ] **Step 1: Write failing Visit participant tests**

Add domain tests:

```ts
it('allows several participants but only one primary Contact', () => {
  expect(() => validateVisitParticipants([
    { contactId: 'CT-001', isPrimary: true },
    { contactId: 'CT-002', isPrimary: true },
  ])).toThrowError(/只能有一位主要联系人/)
})

it('rejects a participant outside the Visit account', async () => {
  const api = createMockApi({ role: 'CRM Administrator', latency: 0 })
  await expect(api.createVisit({
    accountId: 'ACC-001',
    subject: '现场交流',
    date: '2026-07-30',
    type: 'On-site',
    owner: 'Demo Staff 01',
    objective: '确认样片计划',
    participants: [{ contactId: 'CT-OTHER', isPrimary: true }],
  })).rejects.toMatchObject({ code: 'CONTACT_ACCOUNT_MISMATCH' })
})
```

Add page tests for query prefill and multi-select.

- [ ] **Step 2: Run Visit tests and verify RED**

Run:

```powershell
pnpm.cmd exec vitest run src/domain/visits.test.ts src/pages/customer-operations.test.ts src/api/mock-adapter.test.ts
```

Expected: FAIL because Visit has no participant model.

- [ ] **Step 3: Add participant fields and exact validation**

Add `participants: VisitParticipantDto[]` to `VisitDto` and `CreateVisitInput`. Existing seed Visits receive `participants: []`.

In `src/domain/visits.ts`:

```ts
export function validateVisitParticipants(participants: readonly VisitParticipantDto[]) {
  const ids = participants.map((item) => item.contactId)
  if (new Set(ids).size !== ids.length) throw new Error('同一联系人不能重复添加')
  if (participants.filter((item) => item.isPrimary).length > 1) {
    throw new Error('一次拜访只能有一位主要联系人')
  }
}
```

Adapter validation additionally resolves every Contact and checks the Visit account.

Extend `mergeContacts` so Visit participants using `duplicateId` become `survivorId`; deduplicate the participant array and preserve `isPrimary: true` when either merged participant was primary.

- [ ] **Step 4: Implement Visit participant UI and quick create**

`VisitModal` receives all accessible Contacts. Render same-account Active Contacts as selectable chips or a multi-select list, with a radio/checkbox for one primary participant and an optional meeting role.

When the account changes, clear participants outside the new account. `create-contact` opens a fixed-account Contact form and adds the saved Contact as a participant.

- [ ] **Step 5: Add query filter, prefill, and Contact links**

`VisitsPage` reads:

- `contactId` to filter rows whose `participants` contain the Contact;
- `accountId` to prefill create;
- `create=1` to open the modal once;
- `primaryContactId` to preselect the Contact.

Visit cards/table rows link participant names to `/contacts/:contactId`.

- [ ] **Step 6: Extend Contact detail aggregation**

`getContact` includes Visit records where any participant has the Contact ID and produces timeline links:

```ts
{
  id: `visit:${visit.id}`,
  at: visit.date,
  type: 'Visit',
  title: visit.subject,
  summary: visit.outcome || visit.objective,
  href: `/visits?contactId=${contact.id}`,
}
```

- [ ] **Step 7: Run Visit tests and verify GREEN**

Run:

```powershell
pnpm.cmd exec vitest run src/domain/visits.test.ts src/pages/customer-operations.test.ts src/api/mock-adapter.test.ts
```

Expected: PASS for multi-participant validation, account scope, quick create, route prefill/filtering, and Contact timeline aggregation.

- [ ] **Step 8: Commit the Visit unit**

```powershell
git add -- src/types/crm.ts src/domain/visits.ts src/domain/visits.test.ts src/features/visits/VisitModal.vue src/pages/VisitsPage.vue src/pages/customer-operations.test.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts src/demo/sales-repository.ts
git -c user.name=Codex -c user.email=codex@local commit -m "feat: link visit participants to contacts"
```

---

### Task 7: Account 360, Customer Report, and Cross-Module Route Integrity

**Files:**
- Modify: `src/pages/AccountsPage.vue`
- Modify: `src/features/accounts/AccountProfile.vue`
- Modify: `src/features/accounts/AccountDrawer.vue`
- Modify: `src/features/accounts/customer-report-model.ts`
- Modify: `src/features/accounts/customer-report-model.test.ts`
- Modify: `src/features/accounts/AccountDrawer.test.ts`
- Modify: `src/pages/customer-operations.test.ts`
- Modify: `src/app/router.ts`
- Create: `src/pages/contact-deep-links.test.ts`

**Interfaces:**
- Consumes: Contact routes, Contact summaries, Opportunity role expansion, query protocols from Tasks 3–6.
- Produces: Account/site selection deep links, Contact detail links from Account 360, Contact-aware customer report, and end-to-end route assertions.

- [ ] **Step 1: Write failing deep-link and Account 360 tests**

Create `src/pages/contact-deep-links.test.ts`:

```ts
it('opens the requested account and keeps the site focus from a Contact link', async () => {
  const router = createAppRouter()
  await router.push('/accounts?accountId=ACC-001&siteId=SITE-001')
  const wrapper = mount(AccountsPage, {
    props: { apiClient: createMockApi({ latency: 0 }) },
    global: { plugins: [createPinia(), router] },
  })
  await flushPromises()

  expect(wrapper.get('[data-selected-account]').attributes('data-selected-account')).toBe('ACC-001')
  expect(wrapper.get('[data-site-id="SITE-001"]').classes()).toContain('focused')
})

it('links Account 360 Contact names to independent Contact subpages', async () => {
  const wrapper = mount(AccountProfile, {
    props: { accountId: 'ACC-001', apiClient: createMockApi({ latency: 0 }) },
    global: { plugins: [createPinia(), createAppRouter()] },
  })
  await flushPromises()

  expect(wrapper.get('[data-contact-id="CON-001"]').attributes('href')).toBe('/contacts/CON-001')
})
```

Update customer report tests to assert opportunity roles come from `opportunityRoles`, not removed Contact master `role`.

- [ ] **Step 2: Run account/deep-link tests and verify RED**

Run:

```powershell
pnpm.cmd exec vitest run src/pages/contact-deep-links.test.ts src/features/accounts/AccountDrawer.test.ts src/features/accounts/customer-report-model.test.ts src/pages/customer-operations.test.ts
```

Expected: FAIL because Accounts does not honor query focus and report code still reads master buying fields.

- [ ] **Step 3: Honor account and site query parameters**

`AccountsPage` reads `accountId` after accounts load, selects it only when role-visible, and passes `siteId` to `AccountProfile`. Invalid IDs show a non-sensitive warning and fall back to the first visible account.

`AccountProfile` adds `data-site-id` and a `focused` class to the selected site without changing the rest of the Account 360 layout.

- [ ] **Step 4: Link Contact names from customer views**

Replace plain Contact names in `AccountProfile` and the legacy `AccountDrawer` with:

```vue
<RouterLink
  :data-contact-id="contact.id"
  :to="{ name: 'contact-detail', params: { contactId: contact.id } }"
>
  {{ contact.name }} · {{ contact.title }}
</RouterLink>
```

Use master status, phone/email, and `opportunityRoles` in the display. Keep organization relationship resolution by `reportsToContactId`.

- [ ] **Step 5: Update customer report semantics**

The Economic Buyer risk becomes:

```ts
if (!detail.contacts.some((contact) =>
  contact.opportunityRoles.includes('Economic Buyer')
)) {
  risks.push({
    level: '关注 / Watch',
    title: '经济决策人尚未识别 / Economic Buyer Not Identified',
    source: 'Opportunity Contact',
    reason: '当前客户的商机关联中没有 Economic Buyer',
    owner: detail.account.owner,
    action: '在相关 Opportunity 中关联预算最终批准人',
  })
}
```

The People sheet columns become ID, name, account/site, title, department, phone, email, relationship, reports-to, status, owner, and opportunity roles.

- [ ] **Step 6: Add full route-integrity assertions**

The deep-link test must cover:

- `/contacts/:id` → account/site;
- `/contacts/:id` → Opportunity filter;
- `/contacts/:id` → Booking filter;
- `/contacts/:id` → Demo Request filter;
- `/contacts/:id` → Visit filter;
- Opportunity/Booking/Demo/Visit Contact name → `/contacts/:id`;
- invalid or unauthorized Contact ID → denied/not-found state with no unrelated customer text.

- [ ] **Step 7: Run account/deep-link tests and verify GREEN**

Run:

```powershell
pnpm.cmd exec vitest run src/pages/contact-deep-links.test.ts src/features/accounts/AccountDrawer.test.ts src/features/accounts/customer-report-model.test.ts src/pages/customer-operations.test.ts
```

Expected: PASS for every route direction, account/site focus, report semantics, and denial isolation.

- [ ] **Step 8: Commit the cross-module unit**

```powershell
git add -- src/pages/AccountsPage.vue src/features/accounts/AccountProfile.vue src/features/accounts/AccountDrawer.vue src/features/accounts/customer-report-model.ts src/features/accounts/customer-report-model.test.ts src/features/accounts/AccountDrawer.test.ts src/pages/customer-operations.test.ts src/app/router.ts src/pages/contact-deep-links.test.ts
git -c user.name=Codex -c user.email=codex@local commit -m "feat: connect contacts across customer workflows"
```

---

### Task 8: User Documentation, Focused Regression, Build, and Browser Acceptance

**Files:**
- Modify: `docs/crm-user-operation-manual.md`
- Modify: `README.md` only if its route/module summary exists and is now inaccurate.
- Test: all files named in Tasks 1–7.

**Interfaces:**
- Consumes: the completed Contacts feature.
- Produces: role-aware user guidance and final verification evidence.

- [ ] **Step 1: Update the user manual**

Add a Contacts section documenting:

- navigation and list filters;
- independent detail subpage;
- new/edit Contact fields;
- one-customer/optional-site rule;
- Opportunity buying fields versus Contact master fields;
- quick create from Opportunity, Booking, Demo Request, and Visit;
- Contact detail related links;
- Left Company/Archived behavior;
- role permissions;
- Mock versus Frappe boundary.

Update old “关键人” language where it describes the standalone module. Keep “机会关键人关系” only for the Opportunity-specific association.

- [ ] **Step 2: Run the complete focused Contacts regression**

Run:

```powershell
pnpm.cmd exec vitest run src/domain/contacts.test.ts src/domain/stakeholders.test.ts src/domain/permissions.test.ts src/domain/visits.test.ts src/domain/demo-request-form.test.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.test.ts src/pages/contacts.test.ts src/pages/contact-deep-links.test.ts src/pages/opportunity-strategy-operations.test.ts src/pages/customer-operations.test.ts src/pages/delivery-workflow.test.ts src/app/AppShell.test.ts src/features/accounts/AccountDrawer.test.ts src/features/accounts/customer-report-model.test.ts src/features/demo-requests/DemoRequestForm.test.ts src/features/demo-requests/demo-request-docx.test.ts
```

Expected: all listed tests PASS.

- [ ] **Step 3: Run typecheck**

Run:

```powershell
pnpm.cmd run typecheck
```

Expected: exit code 0 with no TypeScript errors.

- [ ] **Step 4: Run the production build**

Run:

```powershell
pnpm.cmd run build
```

Expected: exit code 0 and a fresh `dist` output.

- [ ] **Step 5: Run the broader test suite without hiding unrelated failures**

Run:

```powershell
pnpm.cmd test
```

Expected: either all tests pass, or any pre-existing unrelated failures are listed separately with exact file/test names. No Contact-related test may fail.

- [ ] **Step 6: Perform browser acceptance**

Start the current source server:

```powershell
pnpm.cmd run dev
```

Verify at desktop and narrow viewport:

1. Sales navigation opens Contacts.
2. Search/filter/new/edit Contact work.
3. Clicking a Contact opens `/contacts/:id`, not a dialog or drawer.
4. Customer, site, and reports-to links work.
5. Opportunity, Booking, Demo Request, and Visit links land on filtered records.
6. Quick create in each business form creates one Contact and automatically selects it.
7. Editing the Contact name updates Opportunity and other read views.
8. Management Viewer is read-only.
9. Sales User sees only own account scope.
10. Engineering roles do not see the standalone Contacts navigation.
11. Invalid or inaccessible Contact IDs do not leak other customer data.

Capture screenshots of the Contacts list and independent detail subpage for handoff.

- [ ] **Step 7: Commit documentation and any final test-only corrections**

```powershell
git add -- docs/crm-user-operation-manual.md README.md
git -c user.name=Codex -c user.email=codex@local commit -m "docs: add contacts workflow guidance"
```

If `README.md` was not changed, omit it from `git add`.

- [ ] **Step 8: Final completion audit**

Compare the current implementation against all 8 completion criteria in:

```text
docs/superpowers/specs/2026-07-28-contacts-master-data-integration-design.md
```

For each criterion, record the exact test, page, route, or build output that proves it. Do not mark completion from absence of errors alone.
