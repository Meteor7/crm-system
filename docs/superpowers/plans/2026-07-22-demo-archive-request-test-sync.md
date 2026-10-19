# Demo Archive, Request, and Test Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one persistent Mock Demo workflow shared by Demo 档案, Demo Request, and Demo Test, including Boss-only approval, structured Q&A, preparation DDL, synchronized artifacts, and an automatically generated external PDF with a reserved watermark hook.

**Architecture:** Keep the existing `CrmApi` boundary and replace only the Mock Demo records with a shared repository backed by IndexedDB. Derive Demo 档案 and the external report from linked Request/Evaluation/Test Run records instead of copying data between pages; enforce scope and field projection in the Mock API before Vue receives data.

**Tech Stack:** Vue 3.5, TypeScript 5.9, Pinia 4, Vitest 4, browser IndexedDB, Canvas 2D, native Blob/Object URL, existing uncompressed DOCX ZIP utilities.

## Global Constraints

- Modify only the current Vue / Mock Demo; do not change Frappe backend code, DocTypes, or production workflows.
- Do not add an npm dependency; build the PDF from Canvas JPEG pages plus a small native PDF image writer.
- Keep `public/templates/demo-request-form-v2.docx` unchanged and never put `customerExpectedDate` into the Request Word mapping.
- Only Boss (`Management Viewer`) may execute manager approval and external report release; `Sales Manager` must not have those capabilities.
- FAE and Equipment Engineer must have identical capabilities and assigned-scope behavior.
- Boss must not receive Draft Requests; CRM Administrator remains Demo-only and must show that warning in the UI.
- Sensitive field removal changes only an external-report projection/version, never the source Request, Q&A, Evaluation, or Test Run.
- The PDF generation pipeline must call `applyDemoTestReportWatermark`; the current implementation returns the unchanged bytes.
- The repository currently has an empty `.git` directory and is not recognized as Git. Do not run `git init`; commit commands below run only after Git metadata is restored.

## File Structure

**Create**

- `src/demo/demo-repository.ts` — snapshot repository, serialized transactions, seed migration, memory and IndexedDB storage.
- `src/demo/demo-repository.test.ts` — persistence, cross-instance, transaction, and Blob tests.
- `src/domain/demo-report.ts` — readiness checks and explicit external-field projection.
- `src/domain/demo-report.test.ts` — gate and sensitive-field exclusion tests.
- `src/features/demo-requests/QuestionAnswerModal.vue` — answer one assigned Customer Question.
- `src/features/evaluations/TestDeadlineModal.vue` — set Test Run DDL during Preparation.
- `src/features/evaluations/ExternalReportModal.vue` — select optional external fields, preview, release, and download.
- `src/features/evaluations/pdf-image-writer.ts` — package fixed-size JPEG pages into a valid PDF.
- `src/features/evaluations/pdf-image-writer.test.ts` — PDF signature, xref, and page-count tests.
- `src/features/evaluations/demo-test-report-pdf.ts` — Canvas report rendering, Logo extraction, file naming, and watermark Hook.
- `src/features/evaluations/demo-test-report-pdf.test.ts` — report model, Hook invocation, and output tests with injected JPEG pages.

**Modify**

- `src/types/crm.ts` — Q&A, artifact, report, deadline, and API input types.
- `src/types/workspaces.ts` — aggregate Demo archive DTO and role-projected sections.
- `src/api/contracts.ts` — Q&A, DDL, report, and artifact API methods.
- `src/api/mock-data.ts` — deterministic seed dates, structured questions, and report fields.
- `src/api/mock-adapter.ts` — repository access, permissions, transitions, field projection, artifact storage.
- `src/api/frappe-adapter.ts` — typed Mock-only stubs and `FAE Review` display mapping; no backend calls added.
- `src/domain/permissions.ts` — Boss-only approval/release and identical engineering roles.
- `src/stores/app.ts` — preserve one repository while switching Mock identities.
- `src/app/navigation.ts` — rename Demo to Demo 档案.
- `src/app/AppShell.vue` — Demo-only administrator notice.
- `src/domain/demo-request-form.ts` — split/merge Customer Question lines while preserving answers.
- `src/features/demo-requests/DemoRequestForm.vue` — clarify Open Question wording; gray guidance remains.
- `src/features/demo-requests/DemoRequestModal.vue` — collect customer expected date and Q&A assignment.
- `src/features/demo-requests/DemoRequestCard.vue` — show expected date, Q&A, Answer button, Boss wording.
- `src/features/demo-requests/demo-request-docx.ts` — return a DOCX Blob and expose template Logo extraction without mapping the expected date.
- `src/pages/DemoRequestsPage.vue` — save/download artifact and answer Q&A.
- `src/pages/DemoWorkflowPage.vue` — aggregate archive UI, Q&A/Test/Artifact sections, no probability.
- `src/pages/EvaluationsPage.vue` — five stage groups, DDL, report modal, and downloads.
- `src/features/evaluations/EvaluationCard.vue` — DDL/readiness/report actions.
- `src/features/evaluations/TestRunModal.vue` — require result summary for a Completed Run.
- Existing relevant tests under `src/api`, `src/domain`, `src/app`, `src/features`, and `src/pages`.

---

### Task 1: Lock Domain Contracts and Role Rules

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/types/workspaces.ts`
- Modify: `src/domain/permissions.ts`
- Modify: `src/domain/permissions.test.ts`
- Modify: `src/demo/identities.test.ts`

**Interfaces:**
- Produces: `DemoQuestionDto`, `DemoArtifactMetaDto`, `DemoArtifactDto`, `DemoReportSelection`, `DemoTestReportContextDto`, and the new API input types used by all later tasks.
- Produces: capabilities `demo_report:configure` and `demo_report:release`.

- [ ] **Step 1: Write failing role and contract tests**

```ts
it('reserves approval and report release for Boss', () => {
  expect(ROLE_PROFILES['Management Viewer'].capabilities).toEqual(expect.arrayContaining([
    'demo_request:manager_approve', 'demo_report:release',
  ]))
  expect(ROLE_PROFILES['Sales Manager'].capabilities).not.toContain('demo_request:manager_approve')
  expect(ROLE_PROFILES['Sales Manager'].capabilities).not.toContain('demo_report:release')
})

it('keeps FAE and Equipment Engineer capabilities identical', () => {
  expect(ROLE_PROFILES['Equipment Engineer'].capabilities)
    .toEqual(ROLE_PROFILES['FAE / Applied Engineer'].capabilities)
})
```

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `pnpm.cmd test -- src/domain/permissions.test.ts src/demo/identities.test.ts`
Expected: FAIL because Management Viewer lacks approval/release and the engineering arrays differ.

- [ ] **Step 3: Add exact shared types**

```ts
export type DemoQuestionSource = 'Customer' | 'Internal'
export type DemoQuestionAssignment = 'FAE' | 'Equipment Engineer' | 'Both'

export interface DemoQuestionDto {
  id: string
  demoRequestId: string
  source: DemoQuestionSource
  question: string
  assignedRole: DemoQuestionAssignment
  status: 'Open' | 'Answered'
  answer: string
  answeredBy?: string
  answeredAt?: string
}

export type DemoArtifactType = 'Demo Request DOCX' | 'External Demo Test Report PDF'
export interface DemoArtifactMetaDto {
  id: string
  demoRequestId: string
  evaluationId?: string
  type: DemoArtifactType
  fileName: string
  mimeType: string
  version: number
  createdBy: string
  createdAt: string
  visibility: 'Internal' | 'Customer Review'
}
export interface DemoArtifactDto extends DemoArtifactMetaDto { blob: Blob }

export type DemoReportOptionalField = 'requestIds' | 'customerExpectedDate' | 'testRunDeadline' | 'owner'
export interface DemoReportSelection {
  omittedOptionalFields: DemoReportOptionalField[]
  removalReason: string
}

export interface DemoTestReportContextDto {
  reportId: string
  request: Pick<DemoRequestDto, 'id' | 'accountName' | 'title' | 'requestedEquipment' | 'customerExpectedDate' | 'questions'>
  evaluation: Pick<EvaluationDto, 'id' | 'owner' | 'testRunDeadline' | 'runs'>
  selection: DemoReportSelection
}
```

Extend `DemoRequestDto` with `customerExpectedDate: string` and `questions: DemoQuestionDto[]`. Extend `CreateDemoRequestInput` with `customerExpectedDate: string` and `questionAssignment: DemoQuestionAssignment`. Extend `EvaluationDto` with `testRunDeadline: string`, `reportStatus: 'Not Ready' | 'Ready' | 'Released'`, `reportSelection: DemoReportSelection`, `reportArtifactId?: string`, and `reportVersion: number`.

- [ ] **Step 4: Implement the role arrays**

```ts
const ENGINEERING_CAPABILITIES: Capability[] = [
  'account:view', 'requirement:view', 'deal:view', 'visit:view', 'demo_request:view',
  'demo_request:engineering_review', 'evaluation:view', 'evaluation:write',
  'service:view', 'service:write', 'procedure:view', 'procedure:execute',
]

const MANAGEMENT_READ_CAPABILITIES: Capability[] = [
  'dashboard:view', 'dashboard:management', 'account:view', 'account_report:export',
  'stakeholder:view', 'requirement:view', 'deal:view', 'visit:view', 'demo_request:view',
  'demo_request:manager_approve', 'demo_report:release', 'evaluation:view',
  'service:view', 'procedure:view', 'contract:view',
]
```

Give Sales Manager and Sales User `demo_report:configure`, and point both FAE and Equipment Engineer profiles at copies of `ENGINEERING_CAPABILITIES`.

- [ ] **Step 5: Run focused tests and typecheck**

Run:

```powershell
pnpm.cmd test -- src/domain/permissions.test.ts src/demo/identities.test.ts
pnpm.cmd typecheck
```

Expected: both commands PASS.

- [ ] **Step 6: Commit when Git metadata is available**

```powershell
git rev-parse --is-inside-work-tree
git add src/types/crm.ts src/types/workspaces.ts src/domain/permissions.ts src/domain/permissions.test.ts src/demo/identities.test.ts
git commit -m "feat: define demo workflow roles and contracts"
```

Current expected result: `git rev-parse` fails; record the checkpoint as skipped and do not initialize Git.

### Task 2: Add the Shared Persistent Demo Repository

**Files:**
- Create: `src/demo/demo-repository.ts`
- Create: `src/demo/demo-repository.test.ts`
- Modify: `src/api/mock-data.ts`
- Modify: `src/stores/app.ts`

**Interfaces:**
- Consumes: DTOs from Task 1 and existing `demoRequests`/`evaluations` seeds.
- Produces: `DemoSnapshot`, `DemoStorage`, `DemoRepository`, `createMemoryDemoStorage`, and `getSharedDemoRepository`.

- [ ] **Step 1: Write persistence and transaction tests**

```ts
it('shares one persisted snapshot across repository clients', async () => {
  const storage = createMemoryDemoStorage()
  const first = createDemoRepository(storage, seedDemoSnapshot)
  await first.transact((draft) => { draft.demoRequests[0].customerExpectedDate = '2026-08-20' })
  const second = createDemoRepository(storage, seedDemoSnapshot)
  expect((await second.read()).demoRequests[0].customerExpectedDate).toBe('2026-08-20')
})

it('persists artifact Blobs', async () => {
  const storage = createMemoryDemoStorage()
  const repository = createDemoRepository(storage, seedDemoSnapshot)
  await repository.transact((draft) => {
    draft.artifacts.push({
      id: 'ART-001', demoRequestId: 'DR-001', evaluationId: 'EVAL-001',
      type: 'External Demo Test Report PDF', fileName: 'report.pdf', mimeType: 'application/pdf',
      blob: new Blob(['pdf']), version: 1, createdBy: '演示经理01', createdAt: '2026-07-22T10:30:00+08:00',
      visibility: 'Customer Review',
    })
  })
  expect((await repository.read()).artifacts[0].blob.size).toBe(3)
})
```

- [ ] **Step 2: Run the repository test and confirm failure**

Run: `pnpm.cmd test -- src/demo/demo-repository.test.ts`
Expected: FAIL because the repository module does not exist.

- [ ] **Step 3: Implement one versioned snapshot and serialized transactions**

```ts
export interface DemoSnapshot {
  version: 1
  demoRequests: DemoRequestDto[]
  evaluations: EvaluationDto[]
  artifacts: DemoArtifactDto[]
}

export interface DemoStorage {
  load(): Promise<DemoSnapshot | null>
  save(snapshot: DemoSnapshot): Promise<void>
}

export interface DemoRepository {
  read(): Promise<DemoSnapshot>
  transact<T>(change: (draft: DemoSnapshot) => T | Promise<T>): Promise<T>
}

export function createDemoRepository(storage: DemoStorage, seed: () => DemoSnapshot): DemoRepository {
  let queue: Promise<void> = Promise.resolve()
  const ensure = async () => {
    const existing = await storage.load()
    if (existing) return existing
    const initial = structuredClone(seed())
    await storage.save(initial)
    return initial
  }
  return {
    read: async () => structuredClone(await ensure()),
    transact: async (change) => {
      const operation = queue.then(async () => {
        const draft = await ensure()
        const result = await change(draft)
        await storage.save(draft)
        return result
      })
      queue = operation.then(() => undefined, () => undefined)
      return operation
    },
  }
}
```

Implement an IndexedDB database named `semiconductor-crm-demo`, object store `snapshots`, key `demo-workflow-v1`; store the entire structured-clone-compatible snapshot so Blob artifacts survive refresh.

- [ ] **Step 4: Seed structured Q&A and report fields**

`seedDemoSnapshot()` must clone existing Request/Evaluation seeds, split non-empty Customer Question lines, assign stable IDs `${request.id}-Q01`, and default:

```ts
{
  customerExpectedDate: request.targetDate,
  questions: buildSeedQuestions(request),
  testRunDeadline: evaluation.plannedEnd,
  reportStatus: 'Not Ready',
  reportSelection: { omittedOptionalFields: [], removalReason: '' },
  reportVersion: 0,
}
```

- [ ] **Step 5: Preserve a shared repository across identity switches**

At module scope in `src/stores/app.ts`, create one repository and pass it to every Mock API identity:

```ts
const demoRepository = getSharedDemoRepository()

const nextApi = createMockApi({
  repository: demoRepository,
  latency: 0,
  role: identity.role,
  userName: identity.name,
  teamOwners: identity.teamOwners,
  assignedAccountIds: identity.assignedAccountIds,
})
```

Tests receive isolated repositories through `createMockApi({ repository })` and must not touch browser IndexedDB.

- [ ] **Step 6: Run repository and store tests**

Run: `pnpm.cmd test -- src/demo/demo-repository.test.ts src/stores/app.test.ts`
Expected: PASS, including a new test that Sales writes a Request, switches to FAE, and reads the same Request.

- [ ] **Step 7: Commit when Git metadata is available**

```powershell
git add src/demo/demo-repository.ts src/demo/demo-repository.test.ts src/api/mock-data.ts src/stores/app.ts src/stores/app.test.ts
git commit -m "feat: persist shared demo workflow data"
```

### Task 3: Move Demo Operations Behind the Shared API Boundary

**Files:**
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`
- Modify: `src/api/frappe-adapter.ts`
- Modify: `src/domain/demo-request-form.ts`
- Modify: `src/domain/demo-request-form.test.ts`

**Interfaces:**
- Consumes: `DemoRepository` and Task 1 DTOs.
- Produces: `answerDemoQuestion`, `setEvaluationTestRunDeadline`, `configureDemoTestReport`, `getDemoTestReportContext`, `saveDemoArtifact`, `getDemoArtifact`, and `releaseDemoTestReport` on `CrmApi`.

- [ ] **Step 1: Write failing API behavior tests**

```ts
it('hides Draft requests from Boss and allows only Boss approval', async () => {
  const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
  const sales = createMockApi({ repository, latency: 0, role: 'Sales User', userName: 'Demo Staff 01' })
  const boss = createMockApi({ repository, latency: 0, role: 'Management Viewer', userName: '演示经理01' })
  const salesManager = createMockApi({ repository, latency: 0, role: 'Sales Manager' })
  expect((await boss.listDemoRequests({})).data.items.some((item) => item.status === 'Draft')).toBe(false)
  await expect(salesManager.transitionDemoRequest('DR-004', { type: 'manager_approve', comment: '越权' }))
    .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
  expect((await boss.transitionDemoRequest('DR-004', { type: 'manager_approve', comment: '批准' })).data.request.approvedBy)
    .toBe('演示经理01')
})

it('answers one assigned customer question across API clients', async () => {
  const repository = createDemoRepository(createMemoryDemoStorage(), seedDemoSnapshot)
  const fae = createMockApi({ repository, latency: 0, role: 'FAE / Applied Engineer', userName: '演示员工14', assignedAccountIds: ['ACC-001'] })
  const sales = createMockApi({ repository, latency: 0, role: 'Sales User', userName: 'Demo Staff 01' })
  const answered = await fae.answerDemoQuestion('DR-001', 'DR-001-Q01', { answer: '支持该缺陷类型。' })
  expect(answered.data).toMatchObject({ status: 'Answered', answeredBy: '演示员工14' })
  expect((await sales.listDemoRequests({})).data.items[0].questions[0].answer).toBe('支持该缺陷类型。')
})
```

- [ ] **Step 2: Add exact `CrmApi` methods**

```ts
answerDemoQuestion(requestId: string, questionId: string, input: { answer: string }): Promise<ApiResponse<DemoQuestionDto>>
setEvaluationTestRunDeadline(id: string, input: { testRunDeadline: string }): Promise<ApiResponse<EvaluationDto>>
configureDemoTestReport(id: string, selection: DemoReportSelection): Promise<ApiResponse<EvaluationDto>>
getDemoTestReportContext(id: string): Promise<ApiResponse<DemoTestReportContextDto>>
saveDemoArtifact(input: Omit<DemoArtifactDto, 'id' | 'version' | 'createdBy' | 'createdAt'>): Promise<ApiResponse<DemoArtifactMetaDto>>
getDemoArtifact(id: string): Promise<ApiResponse<DemoArtifactDto>>
releaseDemoTestReport(id: string, input: { fileName: string; blob: Blob }): Promise<ApiResponse<DemoArtifactMetaDto>>
```

The Frappe adapter returns `NOT_IMPLEMENTED` for the six writes and an empty/not-implemented result for the two reads. Do not invent backend endpoints.

- [ ] **Step 3: Replace local demo arrays with repository transactions**

For every Request/Evaluation write, use:

```ts
return repository.transact(async (snapshot) => {
  const request = snapshot.demoRequests.find((item) => item.id === id)
  if (!request) throw notFound()
  // capability, scope, transition, mutation
  return response({ request, evaluation })
})
```

`listDemoRequests` reads the repository, applies account scope, then excludes `Draft` when `role === 'Management Viewer'`. `listDemoWorkflows` excludes Draft for all archive views and derives its data from snapshot relationships instead of `demoProjects`.

- [ ] **Step 4: Enforce question, DDL, report, and artifact rules**

```ts
if (!question.answer.trim()) throw new CrmApiError('VALIDATION_ERROR', '答案不能为空', requestId(), false)
if (!/^\d{4}-\d{2}-\d{2}$/.test(testRunDeadline) || testRunDeadline < today) {
  throw new CrmApiError('VALIDATION_ERROR', 'Test Run DDL 不能早于今天', requestId(), false)
}
if (testRunDeadline > request.customerExpectedDate) warnings.push('Test Run DDL 晚于客户预期时间，请 Sales 与客户沟通')
```

Only engineering capability can answer/set DDL. Only `demo_report:configure` can save optional projection. Only `demo_report:release` can create a Released PDF Artifact. Artifact reads still require Request/Evaluation visibility.

- [ ] **Step 5: Make history actors truthful**

Replace hardcoded `Sales Manager` approval actors with `userName`, use `FAE Review` in comments, and preserve the internal `Engineer Review` enum only for compatibility.

- [ ] **Step 6: Run adapter and domain tests**

Run:

```powershell
pnpm.cmd test -- src/api/mock-adapter.test.ts src/domain/demo-request-form.test.ts
pnpm.cmd typecheck
```

Expected: both commands PASS; no Mock API test may rely on mutable module-global arrays.

- [ ] **Step 7: Commit when Git metadata is available**

```powershell
git add src/api/contracts.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts src/api/frappe-adapter.ts src/domain/demo-request-form.ts src/domain/demo-request-form.test.ts
git commit -m "feat: synchronize demo workflow through api"
```

### Task 4: Add Customer Expected Date and Trackable Q&A to Demo Request

**Files:**
- Create: `src/features/demo-requests/QuestionAnswerModal.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.vue`
- Modify: `src/features/demo-requests/DemoRequestForm.test.ts`
- Modify: `src/features/demo-requests/DemoRequestModal.vue`
- Modify: `src/features/demo-requests/DemoRequestCard.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: Request/Q&A API from Task 3.
- Produces: emitted Answer actions and expected-date input; later archive/report tasks consume persisted data.

- [ ] **Step 1: Write failing component tests**

```ts
expect(wrapper.get('[data-demo-request="DR-001"]').text()).toContain('客户预期')
expect(wrapper.get('[data-demo-request="DR-001"]').text()).toContain('Customer Q&A')
await wrapper.get('[data-answer-question="DR-001-Q01"]').trigger('click')
await wrapper.get('[aria-label="Q&A 答案"]').setValue('可通过 recipe 调整实现。')
await wrapper.get('[data-modal-submit]').trigger('click')
expect(api.answerDemoQuestion).toHaveBeenCalledWith('DR-001', 'DR-001-Q01', { answer: '可通过 recipe 调整实现。' })
```

- [ ] **Step 2: Run the page and form tests to confirm failure**

Run: `pnpm.cmd test -- src/features/demo-requests/DemoRequestForm.test.ts src/pages/delivery-workflow.test.ts`
Expected: FAIL because the date and Answer UI do not exist.

- [ ] **Step 3: Add the non-Word date input**

Place this field above `DemoRequestForm`, not inside its Word-mapped `DemoRequestFormData`:

```vue
<label class="request-meta-field">
  客户预期时间
  <input v-model="customerExpectedDate" aria-label="客户预期时间" type="date" required />
  <small>仅用于系统排期与沟通，不写入 Demo Request Word</small>
</label>
```

Beside it, add a `Q&A 分配` select bound to `questionAssignment` with `Both` as the default and options `FAE`, `Equipment Engineer`, and `Both`. Emit both values on create and edit through `CreateDemoRequestInput`.

- [ ] **Step 4: Clarify and render Q&A**

Change the Open Question label to `Customer Questions for Internal Team` and retain the gray placeholder. Render each structured Customer Question on the card with status, answer, answeredBy/answeredAt, and:

```vue
<button
  v-if="canEngineer && question.status === 'Open'"
  :data-answer-question="question.id"
  type="button"
  @click="$emit('answer', { request, question })"
>Answer</button>
```

`QuestionAnswerModal.vue` accepts one question, rejects blank text locally, and emits `{ answer: string }`.

- [ ] **Step 5: Wire page calls and rename copy**

Use `FAE Review`, `Boss Approval`, and `Boss 审批意见` in visible copy. Call `answerDemoQuestion`, reload rows after success, and leave card data visible after errors.

- [ ] **Step 6: Run Request tests**

Run: `pnpm.cmd test -- src/features/demo-requests/DemoRequestForm.test.ts src/pages/delivery-workflow.test.ts src/features/demo-requests/demo-request-docx.test.ts`
Expected: PASS; add an assertion that serialized DOCX XML does not contain the expected-date value.

- [ ] **Step 7: Commit when Git metadata is available**

```powershell
git add src/features/demo-requests src/pages/DemoRequestsPage.vue src/pages/delivery-workflow.test.ts
git commit -m "feat: add demo request expected date and qa"
```

### Task 5: Rebuild Demo as the Derived Demo 档案 View

**Files:**
- Modify: `src/app/navigation.ts`
- Modify: `src/app/AppShell.test.ts`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/pages/first-demo-completion.test.ts`
- Modify: `src/pages/permission-revocation.test.ts`
- Modify: `src/types/workspaces.ts`

**Interfaces:**
- Consumes: role-projected `listDemoWorkflows()` aggregate from Task 3.
- Produces: read-only archive sections for Request, Q&A, Test, Artifact, and conclusion.

- [ ] **Step 1: Write failing archive tests**

```ts
expect(navigation.find((group) => group.label === 'Demo 与验证')?.items[0].label).toBe('Demo 档案')
expect(wrapper.get('h1').text()).toBe('Demo 档案')
expect(wrapper.text()).toContain('Customer Q&A')
expect(wrapper.text()).toContain('Test Run DDL')
expect(wrapper.text()).toContain('External Demo Test Report')
expect(wrapper.find('[data-demo-progress]').exists()).toBe(false)
```

For a Sales role, assert sensitive fields such as customer contact, competition, internal questions, and unreleased analysis are absent from both `listDemoWorkflows().data` and rendered text.

- [ ] **Step 2: Run archive tests and confirm failure**

Run: `pnpm.cmd test -- src/app/AppShell.test.ts src/pages/first-demo-completion.test.ts src/pages/permission-revocation.test.ts`
Expected: FAIL on the old title and independent `demoProjects` data.

- [ ] **Step 3: Render the derived aggregate**

Replace the existing flat page sections with direct aggregate markup; do not introduce placeholder component names:

```vue
<section class="workspace-panel archive-overview">
  <header><h2>{{ selected.title }}</h2><span>{{ selected.status }}</span></header>
  <p>{{ selected.account }} · {{ selected.owner }} · 客户预期 {{ selected.customerExpectedDate }}</p>
</section>
<StageRail :stages="selected.approvals.map(({ label, status }) => ({ label, state: status }))" />
<section v-if="selected.request" class="workspace-panel request-snapshot">{{ selected.request.objective }}</section>
<section class="workspace-panel question-list">
  <article v-for="question in selected.questions" :key="question.id">
    <strong>{{ question.question }}</strong><span>{{ question.answer || '待回答' }}</span>
  </article>
</section>
<section v-if="selected.evaluation" class="workspace-panel test-summary">
  <strong>Test Run DDL {{ selected.evaluation.testRunDeadline || '待设置' }}</strong>
  <table><tbody><tr v-for="run in selected.evaluation.runs" :key="run.id"><td>{{ run.id }}</td><td>{{ run.lot }}</td><td>{{ run.summary }}</td></tr></tbody></table>
</section>
<section class="workspace-panel artifact-list">
  <button v-for="artifact in selected.artifacts" :key="artifact.id" @click="downloadArtifact(artifact.id)">{{ artifact.fileName }}</button>
</section>
```

Keep these sections local in `DemoWorkflowPage.vue` if they remain short; extract a component only when a section exceeds roughly 100 lines. Do not add another edit path.

- [ ] **Step 4: Show role-safe content and requested list metadata**

The left card displays `selected.id`, status, customer, owner, and `客户预期`; it must not render `progress`, a percent sign, or a progress element. Role-specific sections rely on the API projection rather than only `v-if`.

- [ ] **Step 5: Run archive tests**

Run: `pnpm.cmd test -- src/app/AppShell.test.ts src/pages/first-demo-completion.test.ts src/pages/permission-revocation.test.ts`
Expected: PASS for Boss full view, Sales business view, and assigned engineering view.

- [ ] **Step 6: Commit when Git metadata is available**

```powershell
git add src/app/navigation.ts src/app/AppShell.test.ts src/pages/DemoWorkflowPage.vue src/pages/first-demo-completion.test.ts src/pages/permission-revocation.test.ts src/types/workspaces.ts
git commit -m "feat: derive synchronized demo archive"
```

### Task 6: Refactor Demo Test Preparation and Test Run Completion

**Files:**
- Create: `src/features/evaluations/TestDeadlineModal.vue`
- Modify: `src/domain/evaluations.ts`
- Modify: `src/domain/evaluations.test.ts`
- Modify: `src/features/evaluations/EvaluationCard.vue`
- Modify: `src/features/evaluations/EvaluationCard.test.ts`
- Modify: `src/features/evaluations/TestRunModal.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: `setEvaluationTestRunDeadline` and persisted Test Runs.
- Produces: validated DDL and Completed Run data required by Task 7 report readiness.

- [ ] **Step 1: Write failing workflow and UI tests**

```ts
expect(evaluationGroup('Requested')).toBe('Preparation')
expect(evaluationGroup('Scheduled')).toBe('Test Execution')
expect(wrapper.text()).toContain('Test Run DDL')
await wrapper.get('[data-set-ddl="EVAL-001"]').trigger('click')
await wrapper.get('[aria-label="Test Run DDL"]').setValue('2026-08-01')
await wrapper.get('[data-modal-submit]').trigger('click')
expect(api.setEvaluationTestRunDeadline).toHaveBeenCalled()
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `pnpm.cmd test -- src/domain/evaluations.test.ts src/features/evaluations/EvaluationCard.test.ts src/pages/delivery-workflow.test.ts`
Expected: FAIL because the group helper and DDL action do not exist.

- [ ] **Step 3: Add display groups without replacing enums**

```ts
export type EvaluationGroup = 'Preparation' | 'Test Execution' | 'Analysis' | 'Customer Review' | 'Closed' | 'On Hold'
export function evaluationGroup(status: EvaluationStatus): EvaluationGroup {
  if (['Requested', 'Scope Confirmed', 'Sample Received'].includes(status)) return 'Preparation'
  if (['Scheduled', 'Testing'].includes(status)) return 'Test Execution'
  if (status === 'Analysis') return 'Analysis'
  if (status === 'Customer Review') return 'Customer Review'
  if (status === 'On Hold') return 'On Hold'
  return 'Closed'
}
```

Use exactly five primary columns; show On Hold in the current operational column with a warning treatment rather than adding a sixth main stage.

- [ ] **Step 4: Add the DDL modal and warning**

Only show `设置 Test Run DDL` while `evaluationGroup(status) === 'Preparation'`. The page renders API warnings when DDL exceeds customer expected date but keeps the saved value.

- [ ] **Step 5: Require a result summary for Completed Runs**

Keep a Run Planned when all metrics are null. If all metrics are present, require non-empty `summary`; the Mock API rejects a completed Run with blank summary.

- [ ] **Step 6: Run Evaluation tests**

Run: `pnpm.cmd test -- src/domain/evaluations.test.ts src/features/evaluations/EvaluationCard.test.ts src/pages/delivery-workflow.test.ts src/api/mock-adapter.test.ts`
Expected: PASS, including DDL date validation and completed-summary validation.

- [ ] **Step 7: Commit when Git metadata is available**

```powershell
git add src/domain/evaluations.ts src/domain/evaluations.test.ts src/features/evaluations src/pages/EvaluationsPage.vue src/pages/delivery-workflow.test.ts src/api/mock-adapter.test.ts
git commit -m "feat: add demo test preparation deadline"
```

### Task 7: Implement Report Readiness and External Projection

**Files:**
- Create: `src/domain/demo-report.ts`
- Create: `src/domain/demo-report.test.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/mock-adapter.test.ts`

**Interfaces:**
- Consumes: `DemoTestReportContextDto`, Q&A, Completed Runs, and `DemoReportSelection`.
- Produces: `reportReadiness(context)` and `projectExternalReport(context)`.

- [ ] **Step 1: Write failing gate and redaction tests**

```ts
const completeContext = (): DemoTestReportContextDto => ({
  reportId: 'RPT-EVAL-001-V1',
  request: {
    id: 'DR-001', accountName: '示范晶圆客户', title: '缺陷检测 Demo', requestedEquipment: 'AOI-X8',
    customerExpectedDate: '2026-08-20',
    questions: [{
      id: 'DR-001-Q01', demoRequestId: 'DR-001', source: 'Customer', question: '是否支持该缺陷？',
      assignedRole: 'Both', status: 'Answered', answer: '支持。', answeredBy: '演示员工14', answeredAt: '2026-07-22T10:30:00+08:00',
    }],
  },
  evaluation: {
    id: 'EVAL-001', owner: '演示员工14', testRunDeadline: '2026-08-01',
    runs: [{ id: 'RUN-001', date: '2026-07-30', lot: 'LOT-001', wafers: 2, status: 'Completed', capture: 98, falsePositive: 1.2, wph: 35, summary: '达到目标' }],
  },
  selection: { omittedOptionalFields: [], removalReason: '' },
})

it('blocks release until every customer question is answered and one run is complete', () => {
  const openQuestion = completeContext()
  openQuestion.request.questions[0].status = 'Open'
  openQuestion.request.questions[0].answer = ''
  expect(reportReadiness(openQuestion)).toEqual(expect.objectContaining({ ready: false }))
  const noRun = completeContext()
  noRun.evaluation.runs = []
  expect(reportReadiness(noRun).missing).toContain('至少一条 Completed Test Run')
})

it('never projects internal or audit fields', () => {
  const context = completeContext()
  const report = projectExternalReport(context, { omittedOptionalFields: ['owner'], removalReason: '客户无需' })
  expect(report).not.toHaveProperty('internalQuestions')
  expect(JSON.stringify(report)).not.toContain('answeredBy')
  expect(report.owner).toBeUndefined()
  expect(context.evaluation.owner).toBeTruthy()
})
```

- [ ] **Step 2: Run the domain test and confirm failure**

Run: `pnpm.cmd test -- src/domain/demo-report.test.ts`
Expected: FAIL because report functions do not exist.

- [ ] **Step 3: Implement deterministic readiness**

```ts
export function reportReadiness(context: DemoTestReportContextDto) {
  const missing: string[] = []
  const open = context.request.questions.filter((q) => q.source === 'Customer' && q.status !== 'Answered')
  if (open.length) missing.push(`${open.length} 条 Customer Q&A 未回答`)
  const completed = context.evaluation.runs.filter((run) => run.status === 'Completed')
  if (!completed.length) missing.push('至少一条 Completed Test Run')
  completed.forEach((run) => {
    if (!run.date || !run.id || !run.lot || !run.wafers || run.capture == null || run.falsePositive == null || run.wph == null || !run.summary.trim()) {
      missing.push(`${run.id || '未编号 Run'} 数据不完整`)
    }
  })
  return { ready: missing.length === 0, missing }
}
```

- [ ] **Step 4: Implement an explicit allow-list projection**

Return only report ID, customer, title/tool, selected optional context fields, completed Run fields, answered Customer question/answer pairs, and conclusion. Never spread source DTOs into the output. If `omittedOptionalFields` is non-empty, require a non-empty `removalReason`; the reason remains internal and is not printed in the PDF.

- [ ] **Step 5: Enforce readiness in status/release API**

Transition to `Customer Review` and `releaseDemoTestReport` both call `reportReadiness`. Recompute `reportStatus` after every Q&A answer and Test Run write. Before Customer Review, report download is unavailable. A failed release leaves `reportArtifactId`, `reportVersion`, and prior Artifact untouched.

- [ ] **Step 6: Run report and adapter tests**

Run: `pnpm.cmd test -- src/domain/demo-report.test.ts src/api/mock-adapter.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit when Git metadata is available**

```powershell
git add src/domain/demo-report.ts src/domain/demo-report.test.ts src/api/mock-adapter.ts src/api/mock-adapter.test.ts
git commit -m "feat: enforce external demo report projection"
```

### Task 8: Generate a Downloadable PDF and Synchronize Artifacts

**Files:**
- Create: `src/features/evaluations/pdf-image-writer.ts`
- Create: `src/features/evaluations/pdf-image-writer.test.ts`
- Create: `src/features/evaluations/demo-test-report-pdf.ts`
- Create: `src/features/evaluations/demo-test-report-pdf.test.ts`
- Create: `src/features/evaluations/ExternalReportModal.vue`
- Modify: `src/features/demo-requests/demo-request-docx.ts`
- Modify: `src/features/demo-requests/demo-request-docx.test.ts`
- Modify: `src/features/evaluations/EvaluationCard.vue`
- Modify: `src/features/evaluations/EvaluationCard.test.ts`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: external report projection from Task 7 and artifact APIs from Task 3.
- Produces: `buildImagePdf`, `buildDemoTestReportPdf`, `applyDemoTestReportWatermark`, and shared artifact downloads.

- [ ] **Step 1: Write failing low-level PDF tests**

```ts
it('writes one PDF page per JPEG image', () => {
  const tinyJpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9])
  const bytes = buildImagePdf([{ jpeg: tinyJpeg, width: 1240, height: 1754 }, { jpeg: tinyJpeg, width: 1240, height: 1754 }])
  const text = new TextDecoder('latin1').decode(bytes)
  expect(text.startsWith('%PDF-1.4')).toBe(true)
  expect((text.match(/\/Type \/Page\b/g) || [])).toHaveLength(2)
  expect(text).toContain('startxref')
  expect(text.endsWith('%%EOF\n')).toBe(true)
})
```

- [ ] **Step 2: Run PDF tests and confirm failure**

Run: `pnpm.cmd test -- src/features/evaluations/pdf-image-writer.test.ts src/features/evaluations/demo-test-report-pdf.test.ts`
Expected: FAIL because the PDF modules do not exist.

- [ ] **Step 3: Implement the minimal image-only PDF writer**

For each page write a `/Page`, a content stream `q 595 0 0 842 0 0 cm /ImN Do Q`, and a `/Subtype /Image` object using `/Filter /DCTDecode`. Calculate byte offsets after concatenating objects, then write an xref table and trailer. Do not convert binary JPEG bytes through a JavaScript string.

- [ ] **Step 4: Render the approved report design to Canvas**

Use 1240×1754 canvases for A4 pages. Draw the extracted `word/media/image1.png` Logo at top-left, orange rule, navy headings, teal chips, metric cards, Run table, Customer Q&A, release gate, and footer. Wrap all values with a measured-text helper; create additional pages rather than clipping long Run/Q&A lists.

Expose the Logo from the existing template parser:

```ts
export function extractDemoRequestLogo(templateBytes: Uint8Array | ArrayBuffer) {
  const entry = readStoredZip(templateBytes).find((item) => item.name === 'word/media/image1.png')
  if (!entry) throw new Error('Word 模板缺少公司 Logo')
  return entry.data
}
```

- [ ] **Step 5: Add and prove the watermark Hook**

```ts
export async function applyDemoTestReportWatermark(
  pdfBytes: Uint8Array,
  context: ReportWatermarkContext,
): Promise<Uint8Array> {
  void context
  return pdfBytes
}

export async function buildDemoTestReportPdf(
  context: DemoTestReportContextDto,
  options: {
    render?: typeof renderReportPages
    watermark?: typeof applyDemoTestReportWatermark
  } = {},
) {
  const projection = projectExternalReport(context, context.selection)
  const pages = await (options.render ?? renderReportPages)(projection)
  const pdf = buildImagePdf(pages)
  const watermarkContext: ReportWatermarkContext = {
    reportId: context.reportId,
    customerName: context.request.accountName,
    generatedBy: context.evaluation.owner,
    generatedAt: new Date().toISOString(),
  }
  return (options.watermark ?? applyDemoTestReportWatermark)(pdf, watermarkContext)
}
```

The unit test spies on or injects the Hook boundary and verifies it receives the generated PDF exactly once.

- [ ] **Step 6: Save Word and PDF as shared Artifacts**

Refactor DOCX generation to return `{ fileName, blob }`; `DemoRequestsPage` calls `saveDemoArtifact` before downloading. `ExternalReportModal`:

- lets Sales configure the optional allow-list and removal reason;
- shows gate failures before Customer Review;
- lets Boss generate, preview, and release;
- downloads the released Artifact returned by `getDemoArtifact` for all allowed roles.

Use one helper for Blob downloads:

```ts
export function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const link = Object.assign(document.createElement('a'), { href: url, download: fileName })
  link.click()
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 7: Run document, card, and page tests**

Run: `pnpm.cmd test -- src/features/evaluations/pdf-image-writer.test.ts src/features/evaluations/demo-test-report-pdf.test.ts src/features/evaluations/EvaluationCard.test.ts src/features/demo-requests/demo-request-docx.test.ts src/pages/delivery-workflow.test.ts`
Expected: PASS, including same Artifact ID/version across Demo Test and Demo 档案.

- [ ] **Step 8: Commit when Git metadata is available**

```powershell
git add src/features/evaluations src/features/demo-requests/demo-request-docx.ts src/features/demo-requests/demo-request-docx.test.ts src/pages/DemoRequestsPage.vue src/pages/EvaluationsPage.vue src/pages/DemoWorkflowPage.vue src/pages/delivery-workflow.test.ts
git commit -m "feat: generate and synchronize demo report artifacts"
```

### Task 9: Add Demo-Only Administrator Notice and Complete Regression QA

**Files:**
- Modify: `src/app/AppShell.vue`
- Modify: `src/app/AppShell.test.ts`
- Modify: any test fixture that constructs `DemoRequestDto` or `EvaluationDto`
- Verify: `output/pdf/demo-test-external-report-preview.pdf`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: complete user-visible workflow and verified LAN build.

- [ ] **Step 1: Write the failing administrator-notice test**

```ts
expect(adminWrapper.text()).toContain('CRM Administrator 仅供 Demo 演示参考，生产上线后不存在')
expect(salesWrapper.text()).not.toContain('生产上线后不存在')
```

- [ ] **Step 2: Implement the role-specific notice**

```vue
<p v-if="usingMock && user.role === 'CRM Administrator'" class="demo-admin-warning" role="note">
  CRM Administrator 仅供 Demo 演示参考，生产上线后不存在
</p>
```

- [ ] **Step 3: Run all automated verification**

Run:

```powershell
pnpm.cmd test
pnpm.cmd typecheck
pnpm.cmd build
```

Expected: all Vitest files pass, `vue-tsc` exits 0, and Vite produces `dist` without warnings that affect runtime.

- [ ] **Step 4: Rebuild the LAN preview**

Stop only the existing Vite preview process owned by this workspace, run `pnpm.cmd build`, and restart `pnpm.cmd preview:lan`. Verify `http://127.0.0.1:4173/` and `http://203.0.113.10:4173/` return HTTP 200.

- [ ] **Step 5: Perform browser role-flow QA**

Use the in-app browser to verify:

1. Sales creates a Draft with customer expected date; Boss cannot see it.
2. Sales submits; FAE and Boss can now see the Request/archive.
3. FAE answers Q&A and sets DDL; switch to Equipment Engineer and confirm identical controls.
4. Boss approves; Evaluation is created once.
5. Engineer completes a Test Run with all report metrics and summary, advances through Analysis, and enters Customer Review after the gate passes.
6. Sales omits one optional report field and records a removal reason.
7. Boss releases the Customer Review PDF and downloads it.
8. Demo 档案 and Demo Test download the same released version.
9. Refresh the browser and verify all records/files remain.

- [ ] **Step 6: Render and visually inspect the generated browser PDF**

Download the released PDF, render every page to PNG with bundled `pypdfium2`, and inspect the Logo, headings, table rows, Q&A, page breaks, footer, and absence of hidden optional fields. Compare visual direction with `output/pdf/demo-test-external-report-preview.pdf`; no overlap, cutoff, missing Logo, or blank page is acceptable.

- [ ] **Step 7: Commit when Git metadata is available**

```powershell
git add src/app/AppShell.vue src/app/AppShell.test.ts
git commit -m "test: verify synchronized demo workflow"
```

Current workspace: skip the commit if `git rev-parse --is-inside-work-tree` still fails; report the exact Git limitation without initializing or deleting `.git`.
