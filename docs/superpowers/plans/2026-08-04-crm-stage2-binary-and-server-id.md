# CRM Stage 2 Binary Boundary and Server ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成契约 A1 与 A6 的前端/Mock 契约改造：二进制不再进入 JSON DTO，上传显式走 multipart 语义，下载返回原始文件流；所有 create/upsert 输入不再携带客户端主键。

**Architecture:** `CrmApi` 继续是 UI 与数据适配器的唯一边界。JSON DTO 仅位于 `src/types`；浏览器二进制通过 `src/api/binary-transport.ts` 的 `MultipartFilePart` / `BinaryDownload` 传递，Frappe adapter 后续只需把前者编码为 `FormData`、把响应解为后者。写接口拆成 `create*` / `update*(id, input, expectedModified?)`，Mock 负责生成 ID，组件根据是否存在被编辑记录选择方法。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vitest、现有 IndexedDB Contact File repository、浏览器 `Blob` / `FormData`。

**Execution Status:** 2026-08-04 完成；`pnpm typecheck`、73/73 测试文件、481/481 测试、`pnpm build` 与范围 `git diff --check` 全部通过。

## Global Constraints

- 权威契约为 `docs/CRM-后端数据库对接契约-2026-08-04.md`；冲突时以权威契约为准。
- 保持 Mock 与未来 Frappe Adapter 的同一 `CrmApi` 契约；不得把 Mock 成功表述为真实 HTTP/数据库已完成。
- 不引入新依赖，不改变既有角色、scope、状态机或业务校验。
- 不 reset、stash、checkout、clean 或覆盖当前脏工作区；本计划不 commit，提交由用户在更大功能完成后统一决定。
- 使用 TDD：每个行为变更先写失败测试并确认失败原因正确，再做最小实现。
- Stage 2 完整 Gate：`pnpm typecheck`、`pnpm test`（70 文件/473 测试基线，新增测试后只允许通过数增加）、`pnpm build`、范围 `git diff --check`。
- A1/A6 只标记为“契约改造完成”；真实 multipart 抓包、授权流端点、Frappe naming series 与 `legacy_id` 迁移需在后端阶段验收后才能勾选完整合规。

---

## File Structure

- Create `src/api/binary-transport.ts`: 唯一的浏览器二进制传输类型与 `FormData` 编码器，不属于 JSON DTO。
- Create `src/demo/binary-storage.ts`: Mock repository/IndexedDB 私有 Blob 存储类型，不进入公共 DTO。
- Create `src/api/binary-transport.test.ts`: 验证 multipart 字段、文件名、MIME、字节与原始下载形状。
- Modify `src/types/crm.ts`: 删除含 `Blob` 的 DTO；拆分 Contact/Lead/Test Run create/update 输入。
- Modify `src/types/workspaces.ts`: 删除 Opportunity Stakeholder/Action 输入中的可选 ID，形成 create/update 输入。
- Modify `src/api/contracts.ts`: 下载脱离 `ApiResponse`；上传使用 multipart part；拆分 create/update 方法。
- Modify `src/api/mock-adapter.ts`: Blob 仅存在于 Mock 私有存储类型；服务端式生成 ID；实现拆分后的方法。
- Modify `src/api/notifying-api.ts`: 把通知代理的 method case 对齐新方法名，保持原通知语义。
- Modify affected Vue components/pages: 调用方按 create/update 分流，并直接消费 `BinaryDownload`。
- Modify focused tests: 先冻结新契约，再迁移现有用例，不弱化权限、事务或字节断言。
- Create `docs/CRM-Frappe命名与legacy-id迁移约定-2026-08-04.md`: 固定各实体独立命名空间及旧 ID 映射边界。

---

### Task 1: Freeze A1 binary transport contract

**Files:**
- Create: `src/api/binary-transport.ts`
- Create: `src/api/binary-transport.test.ts`

**Interfaces:**
- Produces: `MultipartFilePart`, `BinaryDownload`, `appendMultipartFile(formData, fieldName, part)`.
- Produces: reusable non-JSON `MultipartFilePart` / `BinaryDownload` transport primitives for Task 2.

- [ ] **Step 1: Write failing type/transport tests**

Add tests that freeze the direct `BinaryDownload` shape and assert `appendMultipartFile` inserts a file part with preserved filename/MIME/bytes.

```ts
expectTypeOf<BinaryDownload>().toEqualTypeOf<{ blob: Blob; fileName: string; mimeType: string }>()
const form = new FormData()
appendMultipartFile(form, 'file', { blob: new Blob(['abc'], { type: 'text/plain' }), fileName: 'a.txt', mimeType: 'text/plain', size: 3 })
const file = form.get('file') as File
expect(file.name).toBe('a.txt')
expect(await file.text()).toBe('abc')
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `pnpm.cmd test src/api/binary-transport.test.ts`

Expected: FAIL because `src/api/binary-transport.ts` does not exist.

- [ ] **Step 3: Add explicit non-JSON transport types**

Create:

```ts
export interface MultipartFilePart {
  blob: Blob
  fileName: string
  mimeType: string
  size: number
}

export interface BinaryDownload {
  blob: Blob
  fileName: string
  mimeType: string
}

export function appendMultipartFile(formData: FormData, fieldName: string, part: MultipartFilePart) {
  const file = new File([part.blob], part.fileName, { type: part.mimeType })
  formData.append(fieldName, file)
}
```

`MultipartFilePart` 与 `BinaryDownload` 必须留在 `src/api`，并注释说明它们是浏览器传输对象、不得 JSON 序列化为 `ApiResponse`。

- [ ] **Step 4: Run the transport unit test**

Run: `pnpm.cmd test src/api/binary-transport.test.ts`

Expected: PASS, 2 tests.

---

### Task 2: Align Mock storage and UI with multipart/raw download semantics

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Create: `src/demo/binary-storage.ts`
- Modify: `src/demo/demo-repository.ts`
- Modify: `src/demo/contact-file-repository.ts`
- Modify: `src/demo/contact-file-repository.test.ts`
- Modify: `src/features/contacts/ContactFilesCard.vue`
- Modify: `src/pages/DemoDetailPage.vue`
- Modify: `src/pages/DemoWorkflowPage.vue`
- Modify: `src/features/evaluations/ExternalReportModal.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Test: `src/api/mock-adapter.test.ts`
- Create: `src/api/binary-api-contract.test.ts`
- Test: `src/features/evaluations/ExternalReportModal.test.ts`
- Test: `src/pages/delivery-workflow.test.ts`

**Interfaces:**
- Consumes: `MultipartFilePart`, `BinaryDownload`, `DemoArtifactUploadInput` from Task 1.
- Produces: identical file bytes and authorization behavior with no JSON-wrapped Blob.

- [ ] **Step 1: Update tests to the new observable boundary and confirm RED**

Create `binary-api-contract.test.ts` with `expectTypeOf` assertions that `getContactFile`/`getDemoArtifact` return `Promise<BinaryDownload>` and JSON metadata DTOs have no `blob`. Change download assertions from `(await api.getContactFile(id)).data.blob` and `(await api.getDemoArtifact(id)).data.blob` to the direct `.blob` result; assert filename/MIME are returned with the raw binary result. Change artifact upload calls to `{ demoRequestId, evaluationId, type, visibility, file: { blob, fileName, mimeType, size } }`, and report release calls to a single `MultipartFilePart`.

Keep all existing `SCOPE_DENIED`, `PERMISSION_DENIED`, rollback, report lock and byte-content assertions.

- [ ] **Step 2: Introduce Mock-private stored binary types**

Before changing Mock, delete `ContactFileDto` and `DemoArtifactDto` from `src/types/crm.ts`, define `DemoArtifactUploadInput` in `binary-transport.ts`, and update `CrmApi` to:

```ts
uploadContactFiles(contactId: string, files: MultipartFilePart[]): Promise<ApiResponse<ContactFileMetaDto[]>>
getContactFile(fileId: string): Promise<BinaryDownload>
saveDemoArtifact(input: DemoArtifactUploadInput): Promise<ApiResponse<DemoArtifactMetaDto>>
getDemoArtifact(id: string): Promise<BinaryDownload>
releaseDemoTestReport(id: string, file: MultipartFilePart): Promise<ApiResponse<DemoArtifactMetaDto>>
```

`DemoArtifactUploadInput` separates JSON metadata from its multipart file part:

```ts
export interface DemoArtifactUploadInput {
  demoRequestId: string
  evaluationId?: string
  type: DemoArtifactMetaDto['type']
  visibility: DemoArtifactMetaDto['visibility']
  file: MultipartFilePart
}
```

Inside `mock-adapter.ts` only:

```ts
type StoredContactFile = ContactFileMetaDto & { blob: Blob }
type StoredDemoArtifact = DemoArtifactMetaDto & { blob: Blob }
```

IndexedDB/Mock arrays may store these private types; they must never be exported through `ApiResponse`.

- [ ] **Step 3: Implement raw downloads and multipart-shaped uploads**

`getContactFile` and `getDemoArtifact` must perform the same authorization first, then return:

```ts
return { blob: stored.blob, fileName: stored.fileName, mimeType: stored.mimeType }
```

Upload methods unwrap `input.file` or each `MultipartFilePart`, validate declared size/MIME exactly as before, store the private binary object, and return metadata only.

- [ ] **Step 4: Update UI consumers**

- Contact files: pass selected `File` values as multipart parts; download via `downloadBlob(result.blob, result.fileName)`.
- Demo request DOCX: wrap the generated artifact Blob in `file` metadata before `saveDemoArtifact`.
- Demo detail/workflow: consume direct `BinaryDownload`.
- External report modal: keep released metadata in `DemoArtifactMetaDto`; load the binary only for download and never merge Blob into the metadata ref.

- [ ] **Step 5: Run focused A1 tests**

Run: `pnpm.cmd test src/api/binary-transport.test.ts src/api/binary-api-contract.test.ts src/api/mock-adapter.test.ts src/features/evaluations/ExternalReportModal.test.ts src/pages/delivery-workflow.test.ts`

Expected: PASS, including exact bytes, permissions and report lifecycle.

---

### Task 3: Split Contact, Lead and legacy Stakeholder upserts

**Files:**
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/notifying-api.ts`
- Modify: `src/features/contacts/ContactModal.vue`
- Modify: `src/features/leads/LeadEditorModal.vue`
- Modify: `src/pages/ContactsPage.vue`
- Modify: `src/pages/ContactDetailPage.vue`
- Modify: `src/features/leads/LeadListView.vue`
- Modify: `src/pages/LeadDetailPage.vue`
- Modify: `src/pages/DemoRequestsPage.vue`
- Modify: `src/pages/OpportunityDetailPage.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/pages/StakeholdersPage.vue`
- Test: `src/api/mock-adapter.test.ts`
- Test: `src/api/notifying-api.test.ts`
- Test: `src/pages/contacts.test.ts`
- Test: relevant page/component tests selected by changed callers

**Interfaces:**
- Produces: `CreateContactInput`, `UpdateContactInput`, `CreateLeadInput`, `UpdateLeadInput`, `CreateStakeholderInput`, `UpdateStakeholderInput` with no `id`.
- Produces: `createContact`, `updateContact(id, input, expectedModified?)`, `createLead`, `updateLead(id, input, expectedModified?)`, `createStakeholder`, `updateStakeholder(id, input, expectedModified?)`.

- [ ] **Step 1: Add failing contract tests**

Use `expectTypeOf` to assert none of the six input types has `id`. Add runtime tests proving create ignores any primary-key concept by generating the next Mock ID, while update receives the target ID as a separate argument and returns `*_NOT_FOUND` for an unknown ID.

- [ ] **Step 2: Replace upsert input types**

```ts
export type CreateContactInput = Omit<ContactDto, 'id' | 'dataQuality' | 'updatedAt' | 'modified'>
export type UpdateContactInput = CreateContactInput
export type CreateLeadInput = Omit<LeadDto, 'id' | 'createdAt' | 'updatedAt' | 'modified' | 'convertedAt' | 'convertedAccountId' | 'convertedContactId' | 'convertedOpportunityId' | 'convertedReusedAccount' | 'convertedReusedContact'>
export type UpdateLeadInput = CreateLeadInput
export interface CreateStakeholderInput {
  accountId: string
  name: string
  title: string
  department: string
  role: BuyingRole
  influence: 'High' | 'Medium' | 'Low'
  relationship: ContactDto['relationship']
  reportsTo?: string
  email?: string
}
export type UpdateStakeholderInput = CreateStakeholderInput
```

Remove `ContactInput`, `LeadInput`, and the optional `StakeholderInput.id`; update `LeadConversionInput.newContact` to derive from `CreateContactInput` without server-owned fields.

- [ ] **Step 3: Split Mock implementations without changing validation**

Extract shared validators/normalizers, but keep create and update control flow explicit. Create always calls `nextId`; update looks up only the separate `id` argument and preserves the existing account-move/reporting-line rules. `expectedModified` remains optional and ignored in Mock until backend integration.

- [ ] **Step 4: Update modals and pages**

Modals emit field payloads without IDs. Parent pages already know `editing?.id` and must call `update*` when present, otherwise `create*`. Do not infer update from payload content.

- [ ] **Step 5: Update notification method cases**

Map both create/update variants to the same current notification categories/routes. Do not duplicate notifications or change recipients.

- [ ] **Step 6: Run focused tests**

Run: `pnpm.cmd test src/api/mock-adapter.test.ts src/api/notifying-api.test.ts src/pages/contacts.test.ts src/domain/personnel-sync.test.ts src/stores/notifications.test.ts`

Expected: PASS with existing permission and notification counts unchanged.

---

### Task 4: Split Opportunity relation writes and remove client Test Run IDs

**Files:**
- Modify: `src/types/workspaces.ts`
- Modify: `src/types/crm.ts`
- Modify: `src/api/contracts.ts`
- Modify: `src/api/mock-adapter.ts`
- Modify: `src/api/notifying-api.ts`
- Modify: `src/features/opportunities/StakeholderEditorModal.vue`
- Modify: `src/features/opportunities/ActionEditorModal.vue`
- Modify: `src/pages/OpportunityDetailPage.vue`
- Modify: `src/pages/OpportunityStrategyPage.vue`
- Modify: `src/features/evaluations/TestRunModal.vue`
- Modify: `src/pages/EvaluationsPage.vue`
- Test: `src/api/mock-adapter.test.ts`
- Test: `src/pages/opportunity-strategy-operations.test.ts`
- Test: `src/pages/delivery-workflow.test.ts`
- Test: `src/stores/notifications.test.ts`

**Interfaces:**
- Produces: create/update methods for Opportunity Stakeholder and Action with IDs only in URL/method parameters.
- Produces: `CreateTestRunInput = Omit<TestRunDto, 'id' | 'status'>`; `addEvaluationRun` assigns the ID.

- [ ] **Step 1: Write failing ID-boundary tests**

Assert create inputs have no `id`; update methods target the separate relation ID; Test Run modal no longer renders/accepts “Run 编号”; two sequential Mock runs receive distinct server-generated IDs.

- [ ] **Step 2: Split opportunity relation types and methods**

```ts
export type CreateOpportunityStakeholderInput = Omit<OpportunityStakeholderDto, 'id' | 'name' | 'title'>
export type UpdateOpportunityStakeholderInput = CreateOpportunityStakeholderInput
export type CreateOpportunityActionInput = Omit<OpportunityActionDto, 'id'>
export type UpdateOpportunityActionInput = CreateOpportunityActionInput
```

Expose `createOpportunityStakeholder`, `updateOpportunityStakeholder(opportunityId, stakeholderId, input)`, `createOpportunityAction`, and `updateOpportunityAction(opportunityId, actionId, input)`.

- [ ] **Step 3: Generate Test Run IDs in Mock**

Remove the Run ID input from the modal and input type. In Mock use a deterministic next-ID helper scoped to the evaluation, for example `${evaluation.id}-R${NN}`, computed from existing rows and never accepted from the client. Preserve duplicate protection as a storage invariant rather than a user validation branch.

- [ ] **Step 4: Update parent pages and notification proxy**

Use `editingStakeholder?.id` / `editingAction?.id` to choose update versus create. Keep delete signatures unchanged because those IDs identify existing resources. Keep current notification recipients/routes.

- [ ] **Step 5: Run focused tests**

Run: `pnpm.cmd test src/api/mock-adapter.test.ts src/pages/opportunity-strategy-operations.test.ts src/pages/delivery-workflow.test.ts src/stores/notifications.test.ts src/api/notifying-api.test.ts`

Expected: PASS; generated IDs are unique and no create payload contains a primary key.

---

### Task 5: Freeze naming/legacy migration contract and run Stage 2 Gate

**Files:**
- Create: `docs/CRM-Frappe命名与legacy-id迁移约定-2026-08-04.md`
- Modify: `docs/CRM-后端数据库对接契约-2026-08-04.md`
- Modify: `docs/CRM-持续执行审计日志-2026-08-04.md`
- Test: all Stage 2 focused and full suites

**Interfaces:**
- Produces: backend naming contract consumed by Docker/Frappe DocType implementation.

- [ ] **Step 1: Write the naming and migration rules**

The document must freeze at least:

| Entity | Frappe primary naming | legacy field |
|---|---|---|
| Contact | `CRM-CNT-.#####` | `legacy_id` |
| Contract | `CRM-CTR-.#####` | `legacy_id` |
| Lead | `CRM-LEAD-.#####` | `legacy_id` |
| Account | `CRM-ACC-.#####` | `legacy_id` |
| Opportunity | `CRM-OPP-.#####` | `legacy_id` |
| Booking | `CRM-BKG-.#####` | `legacy_id` |
| Demo Request | `CRM-DR-.#####` | `legacy_id` |
| Evaluation | `CRM-EVAL-.#####` | `legacy_id` |
| Installed Tool | `CRM-IT-.#####` | `legacy_id` |

State that `legacy_id` is immutable after import, unique within each DocType, never used as a foreign key, and never accepted by normal create endpoints. Import scripts resolve legacy references to new Frappe names before commit; duplicate or unresolved mappings abort the transaction.

- [ ] **Step 2: Run static boundary scans**

Run:

```powershell
rg -n "blob:\s*Blob|extends .*blob|ApiResponse<.*Blob|id\?: string" src/types src/api/contracts.ts
rg -n "\b(saveContact|saveLead|saveStakeholder|saveOpportunityStakeholder|saveOpportunityAction)\b" src
```

Expected: no Blob-bearing JSON DTO, no old upsert method, and no create input with optional primary ID. Any remaining `id?: string` must be a query/reference field and documented in the audit log.

- [ ] **Step 3: Run full verification**

```powershell
pnpm.cmd typecheck
pnpm.cmd test
pnpm.cmd build
git diff --check -- src/api src/types src/features/contacts src/features/leads src/features/opportunities src/features/evaluations src/pages docs/CRM-Frappe命名与legacy-id迁移约定-2026-08-04.md docs/CRM-后端数据库对接契约-2026-08-04.md docs/CRM-持续执行审计日志-2026-08-04.md
```

Expected: 0 errors; all prior 473 tests plus new Stage 2 tests pass; build succeeds; no whitespace errors.

- [ ] **Step 4: Update contract without false compliance**

Add a checked “Stage 2 契约改造完成” sub-item to Section 5 and a version 1.2 changelog row. Keep full A1/A6 unchecked until real Frappe multipart/raw-stream and naming/legacy migration integration tests pass.

- [ ] **Step 5: Mirror the audit log to Desktop**

Copy the canonical repository audit log to `C:\Users\PlanckSemicon\Desktop\CRM-持续执行审计日志-2026-08-04.md` without writing secrets.

---

## Self-Review

- Spec coverage: A1 covers JSON DTO removal, raw downloads, multipart inputs, Mock/Frappe shared signatures and all known UI consumers. A6 covers every discovered upsert/create primary ID: Contact, Lead, legacy Stakeholder, Opportunity Stakeholder, Opportunity Action and Test Run; already-ID-free creates remain unchanged.
- Deferred backend evidence is explicit: HTTP capture, Frappe authorization stream, naming series and `legacy_id` migration cannot be truthfully verified before the backend exists, so the Go/No-Go items remain unchecked.
- Placeholder scan: implementation shapes, exact method names, focused tests and commands are specified; no unspecified error-handling step is used.
- Type consistency: raw binary returns `BinaryDownload`; JSON uploads return `ApiResponse<ContactFileMetaDto[]>` or `ApiResponse<DemoArtifactMetaDto>`; create input has no ID; update ID and optimistic-lock token are method parameters.
