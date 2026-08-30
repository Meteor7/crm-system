# CRM Frontend Baseline Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不回退已批准的 Demo 独立详情页、三角色模型、统一 Sales Repository 和收件人隔离行为的前提下，将现有前端恢复到 `70/70` 测试文件、`473/473` 测试、类型检查和生产构建全部通过。

**Architecture:** 本计划只处理总路线中的“子项目 0：恢复现有前端基线”。按权威设计裁决陈旧测试，保留当前实现；仅在新工作区缺少稳定测试钩子时增加无业务影响的属性。DOCX 作为二进制契约资产修复为 ZIP Store 格式，不修改生成器去接受不兼容格式。完成后才允许开始 Stage 1 A2/A4/A5 契约预埋。

**Tech Stack:** Vue 3.5、TypeScript 5.9、Pinia 4、Vue Router 5、Vitest 4、Vue Test Utils 2、Vite 8、Python 标准库 `zipfile`（仅用于一次性重打包 DOCX）。

## Global Constraints

- 权威依据依次为：`docs/superpowers/specs/2026-08-04-crm-backend-delivery-roadmap-design.md`、`docs/superpowers/specs/2026-07-31-demo-module-alignment-and-comments-design.md`、`docs/superpowers/specs/2026-08-03-three-role-personnel-contract-design.md`。
- 不加入 A2、A4、A5 字段或注释，不开始 Frappe/Docker 实现。
- 不恢复 Demo 列表页内嵌详情；所有项目链接继续进入 `/demo-workflow/:demoId`。
- 不恢复已删除的 `On Hold`，不恢复旧 Boss/Administrator 角色，不取消通知收件人隔离。
- 不使用 `skip`、`.only`、删除测试、放宽 DOCX 断言或单纯延长测试超时制造绿灯。
- 当前工作区包含大量用户改动；禁止 reset、stash、checkout 覆盖和无关格式化。
- 本子项目不创建分支、不 commit；完成后由用户决定何时统一提交。
- 每个任务先运行指定失败测试确认红灯，再作最小修改，再运行同一测试确认绿灯。

## File Map

**Binary asset**

- Modify: `public/templates/demo-request-form-v2.docx` — 保留包内文件内容和公司 Logo，仅将所有 ZIP entry 重打包为 Store。

**Stable UI test hooks**

- Modify: `src/features/demo-requests/DemoRequestWorkspace.vue` — 给右侧动作按钮补回基于 Request ID 的稳定 `data-demo-action`。
- Modify: `src/features/evaluations/EvaluationWorkspace.vue` — 给右侧状态选择框增加稳定且可访问的 `aria-label`。

**Contract/data expectation tests**

- Modify: `src/domain/contacts.test.ts` — 迁移终态版本改为当前 Sales snapshot v5。
- Modify: `src/features/accounts/customer-report-model.test.ts` — 从实际 Opportunities sheet 验证概率，并断言当前统一数据源中的 next action。
- Modify: `src/features/accounts/AccountDrawer.test.ts` — 断言当前 ACC-001 的真实项目选项数量与内容。
- Modify: `src/app/AppShell.test.ts` — 断言 Manager 看不到发给 Sales 的未读通知，并隔离纯品牌测试的异步路由负载。

**Demo navigation/workspace tests**

- Modify: `src/pages/DemoWorkflowPage.test.ts` — 点击行后断言独立详情路由，不再寻找列表内嵌详情。
- Modify: `src/pages/seven-page-workspace.test.ts` — 将敏感字段和项目切换断言移到 `DemoDetailPage`/真实路由上下文。
- Modify: `src/pages/first-demo-completion.test.ts` — 按 Request/Test 新工作区及 Internal Review 节点校正完成度断言。
- Modify: `src/pages/delivery-workflow.test.ts` — 使用表格行和右侧动作面板执行 Request/Test 流程，接受 Internal Review 新节点。
- Modify: `src/pages/permission-revocation.test.ts` — 在新工作区动作位置触发权限撤销，并通过独立详情路由验证字段投影。

---

### Task 1: Repair the DOCX package without weakening its binary contract

**Files:**

- Modify: `public/templates/demo-request-form-v2.docx`
- Verify: `src/features/demo-requests/demo-request-docx.test.ts`
- Verify: `src/features/evaluations/demo-test-report-pdf.test.ts`

**Step 1: Reproduce the package-format failures**

Run:

```powershell
pnpm test src/features/demo-requests/demo-request-docx.test.ts src/features/evaluations/demo-test-report-pdf.test.ts --reporter=verbose --maxWorkers=1
```

Expected: exactly five failures rooted in `Word 模板必须使用未压缩 ZIP Store 格式` or `Expected stored ZIP entry`.

**Step 2: Inspect the source package before rewriting it**

Run:

```powershell
python -c "import zipfile; p=r'public/templates/demo-request-form-v2.docx'; z=zipfile.ZipFile(p); print(len(z.infolist())); print(sorted(set(i.compress_type for i in z.infolist()))); print([i.filename for i in z.infolist() if 'media/' in i.filename])"
```

Expected: at least one compression method is not `0`, and a company Logo entry exists under `word/media/`.

**Step 3: Repack every entry as ZIP_STORED into a validated temporary file**

Run this exact PowerShell sequence from the repository root:

```powershell
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path 'public/templates/demo-request-form-v2.docx').Path
$temporary = Join-Path (Split-Path $source) 'demo-request-form-v2.store.tmp.docx'
if (Test-Path -LiteralPath $temporary) { throw "Unexpected temporary file already exists: $temporary" }
python -c "import sys,zipfile; s,t=sys.argv[1:3]; src=zipfile.ZipFile(s,'r'); dst=zipfile.ZipFile(t,'w',compression=zipfile.ZIP_STORED,allowZip64=True); [(setattr(i,'compress_type',zipfile.ZIP_STORED), dst.writestr(i,src.read(i.filename),compress_type=zipfile.ZIP_STORED)) for i in src.infolist()]; dst.close(); src.close()" $source $temporary
python -c "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); infos=z.infolist(); assert infos and all(i.compress_type==zipfile.ZIP_STORED for i in infos); assert any(i.filename.startswith('word/media/') for i in infos); assert z.testzip() is None; print(len(infos))" $temporary
Move-Item -LiteralPath $temporary -Destination $source -Force
```

Expected: validation prints the entry count; overwrite occurs only after all entries are Store, a media entry exists, and CRC validation passes.

**Step 4: Verify the binary boundary**

Run:

```powershell
pnpm test src/features/demo-requests/demo-request-docx.test.ts src/features/evaluations/demo-test-report-pdf.test.ts --reporter=verbose --maxWorkers=1
```

Expected: `10 passed`; do not edit either test or `demo-request-docx.ts`.

### Task 2: Align migration, Customer 360, and notification tests with current contracts

**Files:**

- Modify: `src/domain/contacts.test.ts`
- Modify: `src/features/accounts/customer-report-model.test.ts`
- Modify: `src/features/accounts/AccountDrawer.test.ts`
- Modify: `src/app/AppShell.test.ts`

**Step 1: Lock the current failures**

Run:

```powershell
pnpm test src/domain/contacts.test.ts src/features/accounts/customer-report-model.test.ts src/features/accounts/AccountDrawer.test.ts src/app/AppShell.test.ts --reporter=verbose --maxWorkers=1
```

Expected: failures identify snapshot version `5` vs stale `4`, current project options `2` vs stale `3`, missing removed OPP-002 action, Demo-sheet-only percentage lookup, and Manager unread count `3` vs stale `4`.

**Step 2: Update the snapshot terminal-version assertion**

In `src/domain/contacts.test.ts`, change only:

```ts
expect(migrated).toMatchObject({ version: 5 })
```

Keep the contact migration and repository equality assertions unchanged.

**Step 3: Make report tests verify the intended type contract against current data**

In `src/features/accounts/customer-report-model.test.ts`:

- Collect style `7` cells from all sheets, not only the Demo sheet, because the current ACC-001 evaluation has no completed fractional run while its Opportunity probability is fractional.
- Keep the numeric/date/contact-count assertions.
- Replace stale `确认数据接口` (removed OPP-002) with the current ACC-001 Opportunity next action returned by `detail.opportunities[0].nextAction`.

Use this shape:

```ts
const percentageCells = spec.sheets
  .flatMap((sheet) => sheet.rows.flat())
  .filter((cell) => cell?.s === 7)

expect(actionValues).toContain(detail.opportunities[0].nextAction)
```

Also keep the assertion that an `商机 / Opportunity` action exists, so the test cannot pass using only Requirement actions.

**Step 4: Assert Customer 360 options from the canonical response**

In `src/features/accounts/AccountDrawer.test.ts`, keep the explicit selection of `opportunity:OPP-001`, but replace the hard-coded `3` option count with assertions that the options are exactly:

```ts
expect(projectFilter.findAll('option').map((option) => option.attributes('value'))).toEqual([
  'all',
  'opportunity:OPP-001',
])
```

Do not re-add OPP-002 to `mock-data.ts`; Customer 360 now reads the unified Sales Repository.

**Step 5: Preserve notification privacy in the AppShell test**

In `src/app/AppShell.test.ts`, after saving an action owned by `Demo Staff 01`, assert:

```ts
expect(notifications.items[0]).toMatchObject({
  title: '新增推进 Action',
  recipient: 'Demo Staff 01',
})
expect(notifications.visibleItems).not.toContainEqual(notifications.items[0])
expect(wrapper.get('[data-testid="notification-button"]').text()).toContain('3')
```

The mounted identity is Manager, so changing the count to `4` would reintroduce the P0 recipient-isolation bug.

For the pure brand test, create and pre-bootstrap a Pinia store and stub `RouterView` so it does not load the Dashboard route in parallel test runs:

```ts
const pinia = createPinia()
useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
const wrapper = mount(AppShell, {
  global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } },
})
```

Do not increase Vitest timeouts.

**Step 6: Verify the focused contracts**

Run the Step 1 command again.

Expected: `30 passed` in these four files, including the recipient-isolation assertion.

### Task 3: Convert Demo archive tests to dedicated-route assertions

**Files:**

- Modify: `src/pages/DemoWorkflowPage.test.ts`
- Modify: `src/pages/seven-page-workspace.test.ts`
- Verify: `src/pages/DemoDetailPage.test.ts`

**Step 1: Reproduce the route/inline-detail mismatch**

Run:

```powershell
pnpm test src/pages/DemoWorkflowPage.test.ts src/pages/seven-page-workspace.test.ts src/pages/DemoDetailPage.test.ts --reporter=verbose --maxWorkers=1
```

Expected: failures look for `[data-testid="selected-demo"]` or sensitive fields inside `DemoWorkflowPage`, while dedicated-detail tests pass.

**Step 2: Give every DemoWorkflowPage test a real router**

Use `createAppRouter()`, push the list route with the required `surface` query, await `router.isReady()`, and mount with `[pinia, router]`. After clicking a project card/row, assert:

```ts
expect(router.currentRoute.value).toMatchObject({
  name: 'demo-detail',
  params: { demoId: 'DR-108' },
})
expect(router.currentRoute.value.query.from).toBe('demo-workflow')
```

For project and lifecycle views, additionally assert that the outgoing `surface` query is preserved. Remove only assertions that require inline `selected-demo` rendering.

**Step 3: Move sensitive-data assertions to the detail page boundary**

In `src/pages/seven-page-workspace.test.ts`:

- Keep the archive page test responsible for navigation and absence of leaked inline detail.
- Mount `DemoDetailPage` through `/demo-workflow/DR-108` for Manager and through the equivalent visible record for Sales/Engineer.
- Assert Manager sees the contact, wafer-sample, and test-run sections on the detail page.
- Assert role-scoped API data determines what Sales/Engineer see; do not assert old Boss/Administrator names.
- For switching evidence, navigate from `/demo-workflow/DR-107` to `/demo-workflow/DR-108`, await route/render completion, then assert the selected project title and `CUSTOMER05-R01` on the detail page.

**Step 4: Verify route and detail ownership**

Run the Step 1 command again.

Expected: all three files pass; no Vue warnings for missing `router` or `route` injection.

### Task 4: Restore stable Request workspace actions and update delivery tests

**Files:**

- Modify: `src/features/demo-requests/DemoRequestWorkspace.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Modify: `src/pages/permission-revocation.test.ts`

**Step 1: Add stable hooks to the approved right-side action panel**

Add these bindings without changing visibility or click handlers:

```vue
:data-demo-action="`${selected.id}-submit`"
:data-demo-action="`${selected.id}-edit`"
:data-demo-action="`${selected.id}-cancel`"
:data-demo-action="`${selected.id}-review`"
```

Apply `review` to both Engineer and Manager approval buttons because the selected status makes them mutually exclusive. Keep `data-demo-download` unchanged.

**Step 2: Select rows through the table before operating**

In both page test files, replace obsolete `[data-request-select="DR-101"]` interactions with:

```ts
await wrapper.get('[data-demo-request="DR-101"]').trigger('click')
await wrapper.get('[data-demo-action="DR-101-submit"]').trigger('click')
```

For Engineer and Manager paths, select the visible row in that stage and then use `DR-xxx-review` from `[data-demo-request-actions]`. Continue asserting API state after each transition; do not reduce workflow coverage to button existence.

**Step 3: Retain modal-field coverage in its new location**

For “Sales DRF engineering inputs” and returned-request correction tests:

- Select the table row.
- Trigger the right-panel Engineer review or Edit action.
- Assert and fill the existing modal fields there.
- Submit and assert repository/API state changed.

Do not expect detailed DRF fields to render in the list table; the approved design removes detailed data from list pages.

**Step 4: Verify Request transitions and revocation**

Run:

```powershell
pnpm test src/features/demo-requests/DemoRequestWorkspace.test.ts src/pages/delivery-workflow.test.ts src/pages/permission-revocation.test.ts --reporter=verbose --maxWorkers=1
```

Expected: Request submission, correction, cancellation, engineering review, Manager approval, Word generation, and mid-transition permission revocation pass using the table + action-panel UI.

### Task 5: Align Demo Test workflow coverage with Internal Review and the action panel

**Files:**

- Modify: `src/features/evaluations/EvaluationWorkspace.vue`
- Modify: `src/pages/delivery-workflow.test.ts`
- Modify: `src/pages/permission-revocation.test.ts`
- Modify: `src/pages/first-demo-completion.test.ts`

**Step 1: Restore an accessible stable selector for status changes**

In `src/features/evaluations/EvaluationWorkspace.vue`, add:

```vue
<select
  aria-label="Evaluation 状态"
  :value="selected.status"
  ...
>
```

Do not move the selector back into the table row.

**Step 2: Update status-change tests to target the selected action panel**

Replace row-nested status queries with:

```ts
await wrapper.get('[data-evaluation="EVAL-103"]').trigger('click')
await wrapper.get('[data-evaluation-actions] [aria-label="Evaluation 状态"]').setValue('Internal Review')
```

Keep assertions against `updateEvaluationStatus`, permission-revocation clearing, and reloaded API state.

**Step 3: Accept the approved five-view navigation**

Where tests expect four Evaluation views or four Test Run columns, update exact arrays/counts to include `internal` / `Internal Review` between execution and customer review:

```ts
expect(views).toEqual(['overview', 'preparation', 'execution', 'internal', 'customer'])
```

Do not bring back `On Hold`.

**Step 4: Preserve end-to-end Test Run and artifact assertions**

Use `[data-add-run="EVAL-103"]`, `[data-set-ddl]`, and `[data-report-action]` from the right action panel. After each modal submission, continue verifying:

- measured Test Run values are returned by the API;
- DDL warning persists;
- External Report is limited to Customer Review;
- released Artifact metadata is identical in Demo Test and the dedicated Demo detail page.

Update `first-demo-completion.test.ts` only for the approved table/action-panel surfaces and Internal Review stage. Keep its cross-workspace completion assertions.

**Step 5: Verify the complete Demo delivery cluster**

Run:

```powershell
pnpm test src/features/evaluations/EvaluationWorkspace.test.ts src/pages/first-demo-completion.test.ts src/pages/delivery-workflow.test.ts src/pages/permission-revocation.test.ts --reporter=verbose --maxWorkers=1
```

Expected: all tests pass with no missing-selector failures and no weakened API-state assertions.

### Task 6: Run the full gate and check order independence

**Files:**

- Verify all modified files

**Step 1: Run type checking**

Run:

```powershell
pnpm typecheck
```

Expected: exit code `0`, no TypeScript errors.

**Step 2: Run the normal full suite**

Run:

```powershell
pnpm test
```

Expected: `70 passed` test files and `473 passed` tests.

**Step 3: Run the previously failing cluster serially**

Run:

```powershell
pnpm test src/domain/contacts.test.ts src/features/demo-requests/demo-request-docx.test.ts src/features/evaluations/demo-test-report-pdf.test.ts src/features/accounts/customer-report-model.test.ts src/features/accounts/AccountDrawer.test.ts src/pages/DemoWorkflowPage.test.ts src/pages/first-demo-completion.test.ts src/pages/delivery-workflow.test.ts src/pages/seven-page-workspace.test.ts src/pages/permission-revocation.test.ts src/app/AppShell.test.ts --maxWorkers=1
```

Expected: all listed files pass serially. This catches hidden shared-state and router-injection dependencies that a parallel full run can mask.

**Step 4: Build the production bundle**

Run:

```powershell
pnpm build
```

Expected: `vue-tsc --noEmit` and `vite build` both succeed.

**Step 5: Check patch hygiene without touching unrelated changes**

Run:

```powershell
git diff --check -- public/templates/demo-request-form-v2.docx src/domain/contacts.test.ts src/features/accounts/customer-report-model.test.ts src/features/accounts/AccountDrawer.test.ts src/app/AppShell.test.ts src/features/demo-requests/DemoRequestWorkspace.vue src/features/evaluations/EvaluationWorkspace.vue src/pages/DemoWorkflowPage.test.ts src/pages/first-demo-completion.test.ts src/pages/delivery-workflow.test.ts src/pages/seven-page-workspace.test.ts src/pages/permission-revocation.test.ts
```

Expected: no new whitespace errors. Do not clean or stage unrelated dirty files.

**Step 6: Enforce the next-stage gate**

Record the four verification outputs in the execution handoff. Stage 1 may begin only when all of these are true:

```text
pnpm typecheck   -> 0 errors
pnpm test        -> 70 files passed, 473 tests passed
pnpm build       -> success
git diff --check -> no new whitespace errors in scoped files
```

If any count differs, stop and diagnose; do not start A2/A4/A5 or Docker work.
