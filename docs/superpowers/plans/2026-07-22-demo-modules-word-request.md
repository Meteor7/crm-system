# Demo Modules and Word Request Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the Mock Demo navigation into Demo, Demo Request, and Demo Test; add the approved Demo overview redaction; and let Sales complete every supplied Word-template field and download a populated DOCX.

**Architecture:** Keep the existing routes and Mock adapter. Add a focused Demo Request form-data object and validation module, render it through a dedicated form component, and populate a stored-copy OOXML template entirely in the browser. Demo overview redaction is a view-only projection driven by the current Mock role; Frappe backend files remain untouched.

**Tech Stack:** Vue 3.5, Pinia 4, TypeScript 5.9, Vitest 4, Vue Test Utils, browser DOMParser/XMLSerializer, OOXML ZIP Store format, Vite 8.

## Global Constraints

- Modify only the current Vue / Mock Demo. Do not modify `backend/`, Frappe APIs, DocTypes, workflow states, or production permissions.
- Do not add npm dependencies.
- Preserve the supplied `250709-Demo_Request_Form V2.docx`; add a normalized project copy and never modify the user's source file.
- Keep internal Demo Request status values unchanged; only user-visible Mock labels change to `FAE Review`.
- Keep existing Demo Test operations unchanged.
- Treat the Demo overview role filtering as a presentation-only demo boundary, not production security.
- Keep changes limited to Demo navigation, Demo overview, Demo Request form/download, associated types/data, and tests.
- The current `.git` directory is not a valid repository. Do not initialize Git; replace commit steps with tested checkpoints.

---

### Task 1: Publish the three Demo navigation entries and approved labels

**Files:**
- Modify: `src/app/navigation.ts`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: `src/demo/operations-data.ts`
- Modify: `src/app/AppShell.test.ts`
- Modify: `src/pages/seven-page-workspace.test.ts`

**Interfaces:**
- Consumes: existing routes `/demo-workflow`, `/demo-requests`, and `/evaluations` from `src/app/router.ts`.
- Produces: navigation keys `demo-workflow`, `demo-requests`, `demo-test` in that order.

- [ ] **Step 1: Write failing navigation and label tests**

Add these assertions to the existing navigation tests:

```ts
const demoGroup = navigation.find((group) => group.label === 'Demo 与验证')
expect(demoGroup?.items.map(({ key, label, path }) => ({ key, label, path }))).toEqual([
  { key: 'demo-workflow', label: 'Demo', path: '/demo-workflow' },
  { key: 'demo-requests', label: 'Demo Request', path: '/demo-requests' },
  { key: 'demo-test', label: 'Demo Test', path: '/evaluations' },
])
```

Update the complete-page expectation from `Demo Request` to `Demo`, and add assertions after mounting `EvaluationsPage` that its text contains `Demo Test` and `工程师依据 Demo Request 进行测试与分析`.

In `AppShell.test.ts`, assert all three visible links and their targets:

```ts
expect(wrapper.find('[data-route="demo-workflow"]').text()).toContain('Demo')
expect(wrapper.find('[data-route="demo-requests"]').text()).toContain('Demo Request')
expect(wrapper.find('[data-route="demo-test"]').text()).toContain('Demo Test')
```

- [ ] **Step 2: Run the focused tests and observe failure**

Run:

```powershell
pnpm.cmd test -- src/app/AppShell.test.ts src/pages/seven-page-workspace.test.ts
```

Expected: assertions fail because the Demo group contains only `Demo Request`, the overview title is still `Demo Request`, and the Evaluation page title is still `Demo / Wafer Test`.

- [ ] **Step 3: Implement the three navigation items and labels**

Change the Demo group in `src/app/navigation.ts` to:

```ts
{
  label: 'Demo 与验证',
  items: [
    { key: 'demo-workflow', label: 'Demo', path: '/demo-workflow', icon: ClipboardCheck, capabilities: ['demo_request:view', 'evaluation:view'] },
    { key: 'demo-requests', label: 'Demo Request', path: '/demo-requests', icon: FileText, capabilities: ['demo_request:view'] },
    { key: 'demo-test', label: 'Demo Test', path: '/evaluations', icon: FlaskConical, capabilities: ['evaluation:view'] },
  ],
},
```

Import `FileText` and `FlaskConical` from `@lucide/vue`.

In `DemoWorkflowPage.vue`, set the page heading to `Demo`. In `EvaluationsPage.vue`, use:

```vue
<PageHeader
  eyebrow="DEMO TEST"
  title="Demo Test"
  description="工程师依据 Demo Request 进行测试与分析；本轮保留现有演示操作。"
>
```

Replace the three Mock approval labels in `src/demo/operations-data.ts` from `Scope Review` to `FAE Review`. Do not edit `src/api/frappe-adapter.ts` or backend files.

- [ ] **Step 4: Re-run focused tests**

Run the Step 2 command.

Expected: both test files pass.

- [ ] **Step 5: Record a tested checkpoint**

Record that navigation, visible labels, and unchanged route targets pass focused tests. Do not create a Git commit because this workspace is not a valid repository.

---

### Task 2: Apply Boss-only full detail on the Demo overview

**Files:**
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/pages/seven-page-workspace.test.ts`
- Modify: `src/pages/first-demo-completion.test.ts`

**Interfaces:**
- Consumes: `useAppStore()`, `BootstrapDto.user.role`, and the injected `apiClient`.
- Produces: computed `canViewSensitive` where only `Management Viewer` and `CRM Administrator` return true.

- [ ] **Step 1: Write failing role-view tests**

Add a helper in `seven-page-workspace.test.ts`:

```ts
async function mountDemoForRole(role: UserRole) {
  const pinia = createPinia()
  const wrapper = mount(DemoWorkflowPage, {
    props: { apiClient: createMockApi({ latency: 0, role }) },
    global: { plugins: [pinia] },
  })
  await flushPromises()
  return wrapper
}
```

Import `flushPromises` and `UserRole`, then add:

```ts
it('shows complete Demo detail only to Boss and administrators', async () => {
  const management = await mountDemoForRole('Management Viewer')
  expect(management.find('[data-demo-sensitive="contact"]').exists()).toBe(true)
  expect(management.find('[data-demo-sensitive="wafer-samples"]').exists()).toBe(true)
  expect(management.find('[data-demo-sensitive="test-runs"]').exists()).toBe(true)

  const sales = await mountDemoForRole('Sales User')
  expect(sales.find('[data-demo-sensitive="contact"]').exists()).toBe(false)
  expect(sales.find('[data-demo-sensitive="wafer-samples"]').exists()).toBe(false)
  expect(sales.find('[data-demo-sensitive="test-runs"]').exists()).toBe(false)
  expect(sales.get('[data-testid="selected-demo"]').text()).toContain('Primary Tool')
  expect(sales.get('[data-testid="selected-demo"]').text()).toContain('Approval & Customer Review')
})

it('hides percentage progress from Demo cards and shows FAE Review', async () => {
  const management = await mountDemoForRole('Management Viewer')
  expect(management.find('[data-demo-progress]').exists()).toBe(false)
  expect(management.text()).toContain('FAE Review')
  expect(management.text()).not.toContain('Scope Review')
})
```

- [ ] **Step 2: Run the focused test and observe failure**

Run:

```powershell
pnpm.cmd test -- src/pages/seven-page-workspace.test.ts
```

Expected: tests fail because the page has no role-aware projection and still renders percentage progress.

- [ ] **Step 3: Load the current Mock role and gate sensitive sections**

In `DemoWorkflowPage.vue`, import and initialize the app store:

```ts
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const canViewSensitive = computed(() => ['Management Viewer', 'CRM Administrator'].includes(app.bootstrap?.user.role ?? ''))
```

Before loading workflows in `onMounted`, run:

```ts
await app.loadBootstrap(props.apiClient)
```

Keep the overview, Approval rail, and Demo Execution visible to all roles. Add `v-if="canViewSensitive"` and stable `data-demo-sensitive` attributes to these blocks:

```text
contact          -> Demo Request Brief
success-factors  -> Success Factors
wafer-samples    -> Wafer Samples
test-runs        -> Test Runs & Result
questions        -> Internal Questions and Customer Questions wrapper
conclusion       -> Demo Conclusion
```

The Demo Request Brief must move `Customer Contact`, `Other Tools`, and `Complementary Tool` inside the gated block so none of them remain in the business summary.

Replace the left card body with status, title, customer/opportunity, and owner/target only. Remove both the percentage `<b>` and `.workspace-progress` element. Do not delete `progress` from `DemoWorkflowDto` or Mock data.

- [ ] **Step 4: Update existing mounts to install Pinia**

Any test that mounts `DemoWorkflowPage` without a Pinia plugin must use `global: { plugins: [createPinia()] }`. Keep its existing API client and assertions unchanged unless the assertion targets a now-restricted section; those section assertions must use the default administrator Mock API.

- [ ] **Step 5: Run overview tests**

Run:

```powershell
pnpm.cmd test -- src/pages/seven-page-workspace.test.ts src/pages/first-demo-completion.test.ts
```

Expected: both test files pass and the sales view contains no sensitive blocks.

- [ ] **Step 6: Record a tested checkpoint**

Record the passing role matrix, retained business summary, removed progress display, and FAE Review label.

---

### Task 3: Add the complete Word-form data model and Mock validation

**Files:**
- Create: `src/domain/demo-request-form.ts`
- Create: `src/domain/demo-request-form.test.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Produces: `DemoWaferDetailDto`, `DemoRequestFormData`, `getDemoRequestFormData(request)`, `validateDemoRequestFormData(data)`, `countDemoWafers(data)`, and `deriveDemoRequestSummary(accountName, data)`.
- Consumes: existing `DemoRequestDto` legacy summary fields so old Mock fixtures and current Frappe adapter remain type-compatible.

- [ ] **Step 1: Define failing domain tests**

Create `src/domain/demo-request-form.test.ts` with these cases:

```ts
import { describe, expect, it } from 'vitest'
import {
  countDemoWafers,
  createEmptyDemoRequestFormData,
  deriveDemoRequestSummary,
  validateDemoRequestFormData,
} from './demo-request-form'

describe('Demo Request Word form', () => {
  it('requires every template field except complementary tool', () => {
    const form = createEmptyDemoRequestFormData()
    const errors = validateDemoRequestFormData(form)
    expect(errors).toMatchObject({
      contactPerson: '请填写 Contact Person',
      industry: '请填写 Industry',
      salesContact: '请填写 Sales Contact',
      wafers: '请至少填写一条 Wafer Details',
    })
    expect(errors).not.toHaveProperty('complementaryTool')
  })

  it('counts partially filled wafer rows and requires all six wafer cells', () => {
    const form = createEmptyDemoRequestFormData()
    form.wafers[0].slotId = '1'
    expect(countDemoWafers(form)).toBe(1)
    expect(validateDemoRequestFormData(form)).toHaveProperty('wafers.0.wid')
  })

  it('derives legacy card fields from the Word form', () => {
    const form = createEmptyDemoRequestFormData()
    Object.assign(form, {
      primaryTool: 'AX-9000',
      detectMeasure: 'TSV defect capture',
      material: 'Silicon / Cu',
      timing: '2026-08-20',
      keySuccessFactors: 'Capture >= 96%',
    })
    form.wafers[0] = {
      slotId: '1', wid: 'W-001', waferSpecificity: '300 mm Si', notchFlat: 'Notch up',
      doiMetrologyItems: 'TSV residue', resultFileProvided: 'KLARF',
    }
    expect(deriveDemoRequestSummary('Example Fab', form)).toEqual({
      title: 'Example Fab · AX-9000 Demo', objective: 'TSV defect capture', requestedEquipment: 'AX-9000',
      sampleType: 'Silicon / Cu', sampleQuantity: 1, targetDate: '2026-08-20',
      priority: 'High', acceptanceCriteria: 'Capture >= 96%',
    })
  })
})
```

- [ ] **Step 2: Run the domain test and observe module failure**

Run:

```powershell
pnpm.cmd test -- src/domain/demo-request-form.test.ts
```

Expected: test suite fails because `demo-request-form.ts` does not exist.

- [ ] **Step 3: Add exact TypeScript data interfaces**

Add to `src/types/crm.ts`:

```ts
export interface DemoWaferDetailDto {
  slotId: string
  wid: string
  waferSpecificity: string
  notchFlat: string
  doiMetrologyItems: string
  resultFileProvided: string
}

export interface DemoRequestFormData {
  contactPerson: string
  industry: string
  salesContact: string
  demoOwner: string
  sizeShape: string
  material: string
  specificRequest: string
  detectMeasure: string
  expectedResults: string
  otherTools: string
  primaryTool: string
  complementaryTool: string
  timing: string
  keySuccessFactors: string
  internalQuestions: string
  customerQuestions: string
  wafers: DemoWaferDetailDto[]
}
```

Add optional form/signature fields to `DemoRequestDto` so existing fixtures and Frappe mapping remain compatible:

```ts
formData?: DemoRequestFormData
preparedDate?: string
approvedDate?: string
```

Replace `CreateDemoRequestInput` with:

```ts
export interface CreateDemoRequestInput {
  accountId: string
  requirementId?: string
  opportunityId?: string
  formData: DemoRequestFormData
  submit?: boolean
}
```

- [ ] **Step 4: Implement form constants, fallback, validation, and summary derivation**

In `src/domain/demo-request-form.ts`, export this complete hint map, an empty-wafer factory, `createEmptyDemoRequestFormData(salesContact = '')`, and the functions below:

```ts
export const DEMO_REQUEST_HINTS = {
  companyName: '请输入客户公司全称',
  contactPerson: 'Name, title, email, phone',
  industry: 'e.g. Frontend Fab, Power devices, MEMS, Photonics, Advanced Packaging etc.',
  salesContact: 'Sales dept contact for this demo',
  demoOwner: 'R&D or Applications engineer responsible',
  waferCount: '根据下方 Wafer Details 自动计算',
  sizeShape: 'Diameter, thickness, warpage, notch or flat(s), shape...',
  material: 'Including crystal orientation, e.g. Si(100), GaN-on-Si, SiC 4H, etc.',
  specificRequest: 'Surface contact handling, edge exclusion, backside constraints...',
  detectMeasure: 'Defect type, typical size, density, location on wafer...',
  expectedResults: 'Pictures, dimensions, tool performance, report files...',
  otherTools: 'Competitors, tool of record, other solutions currently used',
  primaryTool: 'Tool selected based on discussion with customer',
  complementaryTool: 'To demonstrate additional capabilities or for internal learning',
  timing: 'Proposed schedule taking into account customer expectations',
  keySuccessFactors: 'What should we focus on to make sure we address the right objective?',
  internalQuestions: '请输入需要内部确认的问题',
  customerQuestions: '请输入需要客户确认的问题',
  slotId: 'Cassette slot number (1-25)',
  wid: 'Wafer identification number or lot ID',
  waferSpecificity: 'Material, crystal orientation, layer stack, coatings, thickness, diameter...',
  notchFlat: 'Notch or flat orientation and type',
  doiMetrologyItems: 'Defect type, size, density, location, layers to measure...',
  resultFileProvided: 'Wafer map, images, CSV, KLARF, report PDF...',
} as const
```

```ts
export function countDemoWafers(form: DemoRequestFormData) {
  return form.wafers.filter((wafer) => Object.values(wafer).some((value) => value.trim())).length
}

export function validateDemoRequestFormData(form: DemoRequestFormData) {
  const errors: Record<string, string> = {}
  const fields: Array<[keyof Omit<DemoRequestFormData, 'wafers' | 'complementaryTool'>, string]> = [
    ['contactPerson', 'Contact Person'], ['industry', 'Industry'], ['salesContact', 'Sales Contact'], ['demoOwner', 'Demo Owner'],
    ['sizeShape', 'Size & Shape'], ['material', 'Material (Substrate)'], ['specificRequest', 'Specific Request'],
    ['detectMeasure', 'What to Detect / Measure'], ['expectedResults', 'Expected Results'], ['otherTools', 'Other Tools'],
    ['primaryTool', 'Primary Tool'], ['timing', 'Timing'], ['keySuccessFactors', 'Key Success Factors'],
    ['internalQuestions', 'Internal Questions'], ['customerQuestions', 'Questions for Customer'],
  ]
  fields.forEach(([key, label]) => { if (!form[key].trim()) errors[key] = `请填写 ${label}` })
  const active = form.wafers.filter((wafer) => Object.values(wafer).some((value) => value.trim()))
  if (!active.length) errors.wafers = '请至少填写一条 Wafer Details'
  active.forEach((wafer, index) => {
    const waferFields: Array<[keyof DemoWaferDetailDto, string]> = [
      ['slotId', 'Slot ID'], ['wid', 'WID'], ['waferSpecificity', 'Wafer Specificity'],
      ['notchFlat', 'Notch / Flat'], ['doiMetrologyItems', 'DOI / Metrology Items'], ['resultFileProvided', 'Result File Provided'],
    ]
    waferFields.forEach(([key, label]) => { if (!wafer[key].trim()) errors[`wafers.${index}.${key}`] = `请填写 ${label}` })
  })
  return errors
}

export function deriveDemoRequestSummary(accountName: string, form: DemoRequestFormData) {
  return {
    title: `${accountName} · ${form.primaryTool.trim()} Demo`,
    objective: form.detectMeasure.trim(),
    requestedEquipment: form.primaryTool.trim(),
    sampleType: form.material.trim(),
    sampleQuantity: countDemoWafers(form),
    targetDate: form.timing.trim(),
    priority: 'High' as const,
    acceptanceCriteria: form.keySuccessFactors.trim(),
  }
}
```

`getDemoRequestFormData(request)` accepts `DemoRequestDto | null | undefined` and clones `request.formData` when present. For legacy fixtures, return these exact non-prompt values so every existing request can be edited and downloaded:

```ts
{
  contactPerson: `${request.accountName} Demo Contact`,
  industry: request.segment,
  salesContact: request.salesOwner,
  demoOwner: request.engineerOwner || 'FAE Team',
  sizeShape: '300 mm full wafer',
  material: request.sampleType || 'Silicon',
  specificRequest: request.objective,
  detectMeasure: request.objective,
  expectedResults: request.acceptanceCriteria,
  otherTools: 'Customer tool of record to be confirmed',
  primaryTool: request.requestedEquipment,
  complementaryTool: '',
  timing: request.targetDate,
  keySuccessFactors: request.acceptanceCriteria,
  internalQuestions: request.engineerComment || 'Confirm sample readiness and resource window',
  customerQuestions: 'Confirm sample delivery date and expected output format',
  wafers: [{
    slotId: '1',
    wid: `${request.id}-W01`,
    waferSpecificity: request.sampleType || 'Silicon wafer',
    notchFlat: 'Notch up',
    doiMetrologyItems: request.objective,
    resultFileProvided: 'Wafer map and report PDF',
  }],
}
```

When the request is absent, return `createEmptyDemoRequestFormData()`.

- [ ] **Step 5: Adapt Mock create/update/approval to the form object**

In `mock-adapter.ts`, validate with `validateDemoRequestFormData`, derive legacy summary fields with `deriveDemoRequestSummary`, set `salesOwner` from `input.formData.salesContact`, set `createdBy` from `userName`, and store a cloned `formData` object. Set signatures as follows:

```ts
preparedBy: userName,
preparedDate: TODAY,
approvedBy: request.approvedBy,
approvedDate: request.approvedDate,
```

On manager approval, assign:

```ts
request.approvedBy = userName
request.approvedDate = TODAY
```

When a form error exists, throw `CrmApiError('VALIDATION_ERROR', firstError, requestId(), false)`. Keep status names and transition rules unchanged.

- [ ] **Step 6: Update Mock adapter tests to use the new input**

Create a complete form with `createEmptyDemoRequestFormData('Demo Staff 01')`, fill the fourteen other required main values and one six-field wafer row, then pass `{ accountId: 'ACC-001', formData, submit: true }` to create/update calls. Assert:

```ts
expect(updated.data).toMatchObject({
  status: 'Engineer Review',
  sampleQuantity: 1,
  title: '示例企业014有限公司 · Macro Inspection X8 Demo',
  preparedBy: '演示员工24',
  preparedDate: '2026-07-17',
})
```

- [ ] **Step 7: Run domain and adapter tests**

Run:

```powershell
pnpm.cmd test -- src/domain/demo-request-form.test.ts src/api/mock-adapter.test.ts
```

Expected: both suites pass.

- [ ] **Step 8: Record a tested checkpoint**

Record the complete template model, fallback compatibility, exact validation behavior, automatic card summary, and prepared/approved signature rules.

---

### Task 4: Build the guided Sales form with gray template hints

**Files:**
- Create: `src/features/demo-requests/DemoRequestForm.vue`
- Create: `src/features/demo-requests/DemoRequestForm.test.ts`
- Modify: `src/features/demo-requests/DemoRequestModal.vue`
- Modify: `src/design-system/ModalShell.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: `DemoRequestFormData`, `DEMO_REQUEST_HINTS`, `validateDemoRequestFormData`, and `getDemoRequestFormData` from Task 3.
- Produces: `DemoRequestForm.vue` with `v-model:account-id` and `v-model="formData"`; `DemoRequestModal` accepts `current-sales-contact` and emits the new `CreateDemoRequestInput`.

- [ ] **Step 1: Write failing component tests**

Mount the form with one account and empty form data, then assert exact placeholders and behavior:

```ts
expect(wrapper.get('[name="contactPerson"]').attributes('placeholder')).toBe('Name, title, email, phone')
expect(wrapper.get('[name="industry"]').attributes('placeholder')).toContain('Frontend Fab')
expect(wrapper.get('[name="complementaryTool"]').attributes('placeholder')).toContain('additional capabilities')
expect(wrapper.get('[name="wafer-0-doiMetrologyItems"]').attributes('placeholder')).toContain('Defect type')
expect(wrapper.get('[data-wafer-count]').text()).toBe('0')

await wrapper.get('[name="wafer-0-slotId"]').setValue('1')
expect(wrapper.get('[data-wafer-count]').text()).toBe('1')
await wrapper.get('[data-add-wafer]').trigger('click')
expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(2)
await wrapper.get('[data-remove-wafer="1"]').trigger('click')
expect(wrapper.findAll('[data-wafer-row]')).toHaveLength(1)
```

Add a modal submission test proving missing values prevent the `submit` event and show `data-field-error="contactPerson"`.

- [ ] **Step 2: Run the new component test and observe failure**

Run:

```powershell
pnpm.cmd test -- src/features/demo-requests/DemoRequestForm.test.ts
```

Expected: suite fails because the component does not exist.

- [ ] **Step 3: Implement the dedicated form component**

`DemoRequestForm.vue` must render these section headings exactly:

```text
Customer Information
Owner Information
Sample Information
Demo Purpose
Our Proposal
What Will Make Us Winning
Open Questions
Wafer Details
```

Use semantic `<label>` controls with the `name` values referenced by tests. Render Company Name as the account selector with a disabled first option containing `DEMO_REQUEST_HINTS.companyName`. Render Sales Contact as a required text input defaulted from `current-sales-contact`. Use `DEMO_REQUEST_HINTS` for every other placeholder. Render `Complementary Tool (Optional)` without a required marker. Render a read-only wafer count with `data-wafer-count`. Each wafer row has six named controls, Add/Remove buttons, and field-specific errors. Gray prompt styling must be:

```css
.request-form input::placeholder,
.request-form textarea::placeholder { color:#9aa6a8; opacity:1 }
```

The component must emit cloned form data after each change so props are never mutated directly.

- [ ] **Step 4: Widen ModalShell only when requested**

Add a `wide?: boolean` prop and bind `:class="{ wide }"` on `.modal-card`. Add:

```css
.modal-card.wide { width:min(1120px,100%) }
```

Existing callers remain 680 px because `wide` defaults to false.

- [ ] **Step 5: Integrate create/edit mode in DemoRequestModal**

Use `DemoRequestForm.vue` only for create/edit. Initialize with `getDemoRequestFormData(props.request)` or `createEmptyDemoRequestFormData(props.currentSalesContact)`. On submit:

```ts
const nextErrors = validateDemoRequestFormData(formData.value)
errors.value = nextErrors
if (Object.keys(nextErrors).length) return
emit('submit', { accountId: accountId.value, formData: structuredClone(formData.value), submit: form.submit })
```

Pass `wide` to `ModalShell` for create/edit. Keep engineer and manager branches and payloads unchanged.

- [ ] **Step 6: Update delivery workflow tests**

Replace the legacy `样品数量` edit with editing one Word field and a wafer row. Verify the card updates from the derived summary and still resubmits. Add an assertion that create/edit placeholders are visible and validation prevents empty submission.

- [ ] **Step 7: Run component and workflow tests**

Run:

```powershell
pnpm.cmd test -- src/features/demo-requests/DemoRequestForm.test.ts src/pages/delivery-workflow.test.ts
```

Expected: both suites pass, including unchanged manager and Evaluation behavior.

- [ ] **Step 8: Record a tested checkpoint**

Record that all approved Word fields, exact gray hints, automatic wafer count, row controls, optional field, and blocking validation work.

---

### Task 5: Populate and download the supplied DOCX template

**Files:**
- Create: `public/templates/demo-request-form-v2.docx`
- Create: `src/features/demo-requests/demo-request-docx.ts`
- Create: `src/features/demo-requests/demo-request-docx.test.ts`
- Modify: `src/features/demo-requests/DemoRequestCard.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Produces: `buildDemoRequestDocx(request, templateBytes)`, `loadDemoRequestTemplate()`, `downloadDemoRequestDocx(request)`, and `demoRequestFileName(request)`.
- Consumes: saved `DemoRequestDto`, `getDemoRequestFormData`, and the normalized stored-ZIP template asset.

- [ ] **Step 1: Normalize the supplied template without changing OOXML content**

Use Python `zipfile` to read the supplied file and write every entry with `ZIP_STORED` to `public/templates/demo-request-form-v2.docx`. The source remains untouched. Verify the output contains 19 entries and every entry has compression method `0`.

Run the equivalent of:

```python
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

source = Path(r'C:\Users\PlanckSemicon\Documents\WXWork\1688857547843246\Cache\File\2026-07\250709-Demo_Request_Form V2.docx')
target = Path(r'C:\Users\PlanckSemicon\Desktop\semiconductor-crm\public\templates\demo-request-form-v2.docx')
target.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(source) as src, ZipFile(target, 'w', compression=ZIP_STORED) as dst:
    for item in src.infolist():
        clone = ZipInfo(item.filename, item.date_time)
        clone.external_attr = item.external_attr
        clone.comment = item.comment
        dst.writestr(clone, src.read(item.filename), compress_type=ZIP_STORED)
```

- [ ] **Step 2: Write failing structural DOCX tests**

Read the normalized asset in the test, build a document for a request containing unique values, and assert:

```ts
expect([...output.slice(0, 4)]).toEqual([0x50, 0x4b, 0x03, 0x04])
expect(files.has('word/document.xml')).toBe(true)
expect(files.has('word/header1.xml')).toBe(true)
expect(files.has('word/footer1.xml')).toBe(true)
expect(files.has('word/media/image1.png')).toBe(true)
expect(documentXml).toContain('Example Semiconductor Co.')
expect(documentXml).toContain('WAFER-026')
expect(documentXml).not.toContain('Name, title, email, phone')
expect(new DOMParser().parseFromString(documentXml, 'application/xml').querySelector('parsererror')).toBeNull()
```

Use 26 wafer rows and assert all 26 WIDs are present. Add a rejection test for a compressed or malformed template and a filename sanitization assertion.

- [ ] **Step 3: Run DOCX tests and observe module failure**

Run:

```powershell
pnpm.cmd test -- src/features/demo-requests/demo-request-docx.test.ts
```

Expected: suite fails because the DOCX module does not exist.

- [ ] **Step 4: Implement stored-ZIP reading and writing inside the DOCX module**

Implement a local-entry reader that accepts only compression method `0`, preserves all original entries, and returns `{ name, data }[]`. Implement CRC32 and ZIP Store output using the same signatures already proven by the customer XLSX writer. Reject missing `word/document.xml`, unsupported compression, invalid local headers, and malformed XML with explicit errors.

Do not refactor `xlsx-writer.ts`; keeping this small writer feature-local avoids unrelated customer-report changes.

- [ ] **Step 5: Implement deterministic Word table-cell mapping**

Parse `word/document.xml` and write these zero-based table/row/cell locations:

```ts
const MAIN_CELLS = {
  companyName: [0, 1, 1], contactPerson: [0, 2, 1], industry: [0, 3, 1],
  salesContact: [0, 6, 1], demoOwner: [0, 7, 1], waferCount: [0, 10, 1],
  sizeShape: [0, 11, 1], material: [0, 12, 1], specificRequest: [0, 13, 1],
  detectMeasure: [0, 16, 1], expectedResults: [0, 17, 1], otherTools: [0, 18, 1],
  primaryTool: [0, 21, 1], complementaryTool: [0, 22, 1], timing: [0, 23, 1],
  keySuccessFactors: [0, 26, 1], internalQuestions: [0, 29, 1], customerQuestions: [0, 30, 1],
} as const
```

Write signature cells at table 1 rows 0 and 1. Fill Wafer Details in table 2 from row 1. For row 26 and above, clone the last template data row before filling it. Clear unused original data rows. Preserve table-cell properties and replace only paragraph text runs.

- [ ] **Step 6: Implement loading, naming, Blob download, and UI wiring**

Load the asset with:

```ts
const url = new URL('templates/demo-request-form-v2.docx', document.baseURI)
const response = await fetch(url)
if (!response.ok) throw new Error('Word 模板加载失败，请重试')
return response.arrayBuffer()
```

Generate the filename `Demo_Request_<RequestID>_<Company>_<YYYY-MM-DD>.docx`, replacing Windows-invalid filename characters with `-`.

Add an always-visible card button with `data-demo-download="<id>"`. Emit a `download` event. In `DemoRequestsPage.vue`, track `downloadingId` and `downloadError`, call `downloadDemoRequestDocx`, and display exactly:

```text
Word 模板加载失败，请重试
Word 文档生成失败，请检查申请内容后重试
```

Do not clear rows or close another modal on a download failure.

- [ ] **Step 7: Add page-level download tests**

Mock `downloadDemoRequestDocx`, click `[data-demo-download="DR-001"]`, and assert the function receives the saved request. Mock rejection and assert the inline error appears while the request card remains visible. Verify a FAE Mock API and an Equipment Engineer Mock API both render the download button for scoped requests.

- [ ] **Step 8: Run DOCX and workflow tests**

Run:

```powershell
pnpm.cmd test -- src/features/demo-requests/demo-request-docx.test.ts src/pages/delivery-workflow.test.ts
```

Expected: generated DOCX structure, 26-row expansion, download wiring, and failure handling all pass.

- [ ] **Step 9: Record a tested checkpoint**

Record the normalized source-derived template checksum, structural DOCX assertions, preserved header/footer/logo, field mapping, and page-level download behavior.

---

### Task 6: Run complete regression and production build verification

**Files:**
- Modify only files already listed if verification exposes a directly related defect.

**Interfaces:**
- Consumes: all completed task outputs.
- Produces: verified Mock Demo build and an evidence-backed completion report.

- [ ] **Step 1: Run all tests**

```powershell
pnpm.cmd test
```

Expected: every Vitest suite passes with zero failed tests.

- [ ] **Step 2: Run TypeScript checking**

```powershell
pnpm.cmd typecheck
```

Expected: command exits `0` with no TypeScript errors.

- [ ] **Step 3: Run the production build**

```powershell
pnpm.cmd build
```

Expected: `vue-tsc --noEmit` and `vite build` both complete successfully.

- [ ] **Step 4: Verify scope and sensitive strings**

Run:

```powershell
rg -n "Scope Review" src/demo src/pages src/features
rg -n "data-demo-progress|workspace-progress" src/pages/DemoWorkflowPage.vue
```

Expected: no user-visible Mock Demo `Scope Review` occurrences and no Demo card progress markup. Backend and `src/api/frappe-adapter.ts` are intentionally outside this check.

- [ ] **Step 5: Verify no backend files were modified**

Compare the implementation file list against this plan. Expected: no changed path begins with `backend/`.

- [ ] **Step 6: Report completion evidence**

Report:

- the three navigation entries and routes;
- the two full-detail roles and four business-summary roles;
- the Word form field groups and gray hint behavior;
- the generated DOCX template asset and download entry;
- exact test, typecheck, and build results;
- the limitation that the permission split is Mock UI presentation only.
