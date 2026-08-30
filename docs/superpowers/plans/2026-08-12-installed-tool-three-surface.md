# Installed Tool Three-Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Installed Tool 页面改造成默认展示生命周期看板、可切换项目周期看板和设备档案的三视图工作区。

**Architecture:** `InstalledToolsPage.vue` 继续负责唯一一次数据加载、共享筛选、路由查询参数和当前设备选择；现有生命周期看板保持独立，新项目周期看板只消费 `InstalledToolDto.milestones`。原页面下半部分抽取到 `InstalledToolArchiveView.vue`，通过事件调用父页面已有编辑和提示行为，不修改 API、权限或 DTO。

**Tech Stack:** Vue 3 Composition API、TypeScript 5.9、Vue Router 5、Vue Test Utils、Vitest 4、现有 CRM design-system 与 Lucide Vue。

## Global Constraints

- 默认主视图必须是 `lifecycle`。
- 三个主视图固定为 `project`、`lifecycle`、`detail`，且任一时刻只渲染一个。
- 生命周期节点固定按 FAT、Shipment、Installation、SAT、Warranty 排列。
- 两个看板和设备档案列表共用搜索、客户、状态和工程师筛选结果。
- URL 使用 `surface=lifecycle|project|detail` 和 `tool=<id>`；无效参数回退到生命周期看板和筛选结果第一台设备。
- 不修改后端接口、权限规则、`InstalledToolDto` 或 Demo 档案组件。
- 不新增 npm 依赖，不改变全局设计系统。
- 所有项目文件必须通过本机受信任明文写入通道保存，并在暂存前确认不存在 `%TSD-Header-###%`。

---

## File Map

- Create `src/features/installed-tools/InstalledToolProjectCycleBoard.vue`: 一行一台设备的五节点项目周期时间轴。
- Create `src/features/installed-tools/InstalledToolProjectCycleBoard.test.ts`: 节点顺序、状态样式、选中事件和空状态测试。
- Create `src/features/installed-tools/InstalledToolArchiveView.vue`: 现有设备台账、摘要、交付生命周期、版本配置和质保服务 UI。
- Create `src/features/installed-tools/InstalledToolArchiveView.test.ts`: 档案选择、内部页签和父级动作事件测试。
- Modify `src/pages/InstalledToolsPage.vue`: 三视图切换、共享筛选、URL 状态和两个子组件协调。
- Create `src/pages/InstalledToolsPage.test.ts`: 默认视图、互斥切换、看板进入档案和查询参数恢复测试。
- Modify `src/pages/seven-page-workspace.test.ts`: 先进入设备档案再验证原有详情、编辑和权限行为。
- Modify `src/pages/first-demo-completion.test.ts`: 先进入设备档案再验证版本与质保入口。

### Task 1: Installed Tool 项目周期看板

**Files:**
- Create: `src/features/installed-tools/InstalledToolProjectCycleBoard.vue`
- Create: `src/features/installed-tools/InstalledToolProjectCycleBoard.test.ts`

**Interfaces:**
- Consumes: `InstalledToolDto[]`，其中 `milestones: Array<{ label: string; date: string; state: 'Done' | 'Current' | 'Waiting' }>`。
- Produces: props `{ items: InstalledToolDto[]; selectedId?: string }`；emit `select: [item: InstalledToolDto]`；DOM hooks `data-installed-tool-project-board`、`data-installed-tool-project-row`、`data-installed-tool-project-id`、`data-installed-tool-milestone`。

- [ ] **Step 1: Write the failing component tests**

Create a deterministic tool factory and assert the five ordered headers, row metadata, state classes and click emission:

```ts
const stageOrder = ['FAT', 'Shipment', 'Installation', 'SAT', 'Warranty'] as const

function tool(id: string, states: InstalledToolDto['milestones'][number]['state'][]): InstalledToolDto {
  return {
    id,
    accountId: `ACC-${id}`,
    siteId: `SITE-${id}`,
    serial: `SN-${id}`,
    model: 'AOI-X8',
    account: `Account ${id}`,
    site: 'Shanghai Fab',
    location: 'Bay 3',
    status: 'Installation',
    software: '4.2.0',
    firmware: '8.1',
    warrantyEnd: '2027-08-11',
    completeness: 80,
    sourceBookingId: `BOOK-${id}`,
    sourceOpportunityId: `OPP-${id}`,
    salesOwner: 'person002@crm.example.invalid',
    engineerOwner: 'person077@crm.example.invalid',
    salesOrder: `SO-${id}`,
    contract: `CON-${id}`,
    warrantyStart: '2026-08-11',
    serviceContract: `SVC-${id}`,
    pmCycle: 'Quarterly',
    lastService: '2026-08-01',
    operatingSystem: 'Linux',
    configuration: 'Standard',
    ownershipType: 'Customer',
    milestones: stageOrder.map((label, index) => ({
      label,
      date: `2026-08-${String(index + 1).padStart(2, '0')}`,
      state: states[index],
    })),
    documents: [],
  }
}

it('renders one row per tool with five ordered milestone states', () => {
  const item = tool('001', ['Done', 'Done', 'Current', 'Waiting', 'Waiting'])
  const wrapper = mount(InstalledToolProjectCycleBoard, { props: { items: [item], selectedId: item.id } })

  expect(wrapper.findAll('[data-installed-tool-stage-header]').map((node) => node.text()))
    .toEqual(stageOrder)
  const row = wrapper.get('[data-installed-tool-project-id="001"]')
  expect(row.text()).toContain('SN-001')
  expect(row.text()).toContain('Account 001')
  expect(row.findAll('[data-installed-tool-milestone]').map((node) => node.classes()))
    .toEqual(expect.arrayContaining([
      expect.arrayContaining(['is-done']),
      expect.arrayContaining(['is-current']),
      expect.arrayContaining(['is-waiting']),
    ]))
})

it('emits the selected tool and renders an explicit empty state', async () => {
  const item = tool('001', ['Done', 'Current', 'Waiting', 'Waiting', 'Waiting'])
  const wrapper = mount(InstalledToolProjectCycleBoard, { props: { items: [item] } })
  await wrapper.get('[data-installed-tool-project-id="001"]').trigger('click')
  expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(item)
  await wrapper.setProps({ items: [] })
  expect(wrapper.text()).toContain('当前筛选下暂无设备')
})
```

- [ ] **Step 2: Run the focused test and verify red**

Run:

```powershell
pnpm test -- src/features/installed-tools/InstalledToolProjectCycleBoard.test.ts
```

Expected: FAIL because `InstalledToolProjectCycleBoard.vue` does not exist.

- [ ] **Step 3: Implement the minimal project-cycle component**

Use one stable stage constant and map each DTO milestone without generating replacement data:

```ts
const stageOrder = ['FAT', 'Shipment', 'Installation', 'SAT', 'Warranty'] as const
const emit = defineEmits<{ select: [item: InstalledToolDto] }>()
const props = withDefaults(defineProps<{ items: InstalledToolDto[]; selectedId?: string }>(), { selectedId: '' })

function milestoneFor(item: InstalledToolDto, label: string) {
  return item.milestones.find((milestone) => milestone.label === label)
}

function currentOwner(item: InstalledToolDto) {
  return personnelDisplayName(item.engineerOwner) || '待确认'
}
```

Render a horizontally scrollable table with fixed columns `设备 / 客户 / 当前阶段负责人 / 关键日期` and five timeline columns. Each milestone receives `is-done`, `is-current` or `is-waiting`; display its DTO date and use `—` only when the requested label is absent. Add visible focus and selected-row styles using existing neutral, orange, green and muted tokens.

- [ ] **Step 4: Run the focused test and typecheck**

Run:

```powershell
pnpm test -- src/features/installed-tools/InstalledToolProjectCycleBoard.test.ts
pnpm typecheck
```

Expected: both commands PASS.

- [ ] **Step 5: Commit the self-contained board**

```powershell
git add -- src/features/installed-tools/InstalledToolProjectCycleBoard.vue src/features/installed-tools/InstalledToolProjectCycleBoard.test.ts
git commit -m "feat: add installed tool project cycle board"
```

### Task 2: Extract the Equipment Archive View

**Files:**
- Create: `src/features/installed-tools/InstalledToolArchiveView.vue`
- Create: `src/features/installed-tools/InstalledToolArchiveView.test.ts`
- Modify: `src/pages/InstalledToolsPage.vue`

**Interfaces:**
- Consumes: props `{ items: InstalledToolDto[]; selectedId: string; canEdit: boolean }`.
- Produces: emits `select: [item: InstalledToolDto]`, `edit: []`, `document: [name: string]`; DOM hook `data-installed-tool-archive`.
- Parent retains `InstalledToolEditorModal`, `openEditor()`, `saveInstalledTool()`, `canEditSelected`, `canReassign` and toast state.

- [ ] **Step 1: Write the failing archive component tests**

Create a fallback-profile fixture with one current milestone. Verify the selected summary, internal tabs and parent events:

```ts
it('renders the selected archive and switches its internal sections', async () => {
  const first = tool('001', ['Done', 'Current', 'Waiting', 'Waiting', 'Waiting'])
  const second = tool('002', ['Done', 'Done', 'Current', 'Waiting', 'Waiting'])
  const wrapper = mount(InstalledToolArchiveView, {
    props: { items: [first, second], selectedId: first.id, canEdit: true },
  })

  expect(wrapper.get('[data-installed-tool-archive]').text()).toContain('SN-001')
  expect(wrapper.get('.lifecycle-step.is-current').text()).toContain('Shipment')
  await wrapper.findAll('.detail-tabs button')[1].trigger('click')
  expect(wrapper.text()).toContain('软件 / 固件 / 配置变更历史')
  await wrapper.get('[data-installed-tool-archive-id="002"]').trigger('click')
  expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(second)
  await wrapper.get('[data-testid="edit-installed-tool"]').trigger('click')
  expect(wrapper.emitted('edit')).toHaveLength(1)
})

it('hides editing and does not render stale detail for an empty result', async () => {
  const wrapper = mount(InstalledToolArchiveView, {
    props: { items: [], selectedId: 'missing', canEdit: false },
  })
  expect(wrapper.text()).toContain('没有匹配筛选条件的 Installed Tool')
  expect(wrapper.find('.tool-header').exists()).toBe(false)
  expect(wrapper.find('[data-testid="edit-installed-tool"]').exists()).toBe(false)
})
```

The test file may share its local `tool()` factory with Task 1 by copying the explicit fixture; do not add a production helper solely for tests.

- [ ] **Step 2: Run the archive test and verify red**

Run:

```powershell
pnpm test -- src/features/installed-tools/InstalledToolArchiveView.test.ts
```

Expected: FAIL because `InstalledToolArchiveView.vue` does not exist.

- [ ] **Step 3: Move the existing archive behavior into the focused component**

Move, without behavioral redesign:

- `LifecycleState`, `LifecycleRecord`, `ToolProfile`, `meanings`, `toolProfiles`, `fallbackProfile()` and `profileFor()`.
- `activeSection`, `expandedStage`, selected/profile/current-stage/completed/open-issue computed state.
- Existing `.tool-layout` through warranty/service template and its scoped CSS.

Resolve selection strictly from the supplied filtered items:

```ts
const selected = computed(() =>
  props.items.find((item) => item.id === props.selectedId) ?? props.items[0],
)
const profile = computed(() => selected.value ? profileFor(selected.value) : undefined)

watch(() => props.selectedId, () => {
  expandedStage.value = profile.value?.lifecycle.find((item) => item.state === 'Current')?.label ?? 'FAT'
  activeSection.value = 'lifecycle'
})
```

Replace local side effects with events:

```vue
<button @click="emit('select', tool)">...</button>
<button v-if="canEdit" data-testid="edit-installed-tool" @click="emit('edit')">...</button>
<button @click="emit('document', file)">...</button>
```

Temporarily render the component from `InstalledToolsPage.vue` in place of the old lower archive markup. Keep the existing lifecycle board above it until Task 3 changes mutual exclusivity; this task is only the extraction seam.

- [ ] **Step 4: Run archive and existing workspace tests**

Run:

```powershell
pnpm test -- src/features/installed-tools/InstalledToolArchiveView.test.ts src/pages/seven-page-workspace.test.ts src/pages/first-demo-completion.test.ts
pnpm typecheck
```

Expected: all commands PASS and the existing edit modal still opens from the extracted view.

- [ ] **Step 5: Commit the extraction**

```powershell
git add -- src/features/installed-tools/InstalledToolArchiveView.vue src/features/installed-tools/InstalledToolArchiveView.test.ts src/pages/InstalledToolsPage.vue
git commit -m "refactor: extract installed tool archive view"
```

### Task 3: Add Three-Surface Routing and Mutual Exclusivity

**Files:**
- Modify: `src/pages/InstalledToolsPage.vue`
- Create: `src/pages/InstalledToolsPage.test.ts`

**Interfaces:**
- Consumes: `InstalledToolPipelineBoard` emit `select`, `InstalledToolProjectCycleBoard` emit `select`, `InstalledToolArchiveView` emits `select`, `edit`, `document`.
- Produces: `type InstalledToolSurface = 'project' | 'lifecycle' | 'detail'`; route query `{ surface: InstalledToolSurface; tool?: string }`; DOM hooks `data-installed-tool-surface`, `data-installed-tool-view`.

- [ ] **Step 1: Write failing page navigation tests**

Mount with the real app router so query behavior is observable:

```ts
async function mountPage(path = '/installed-tools') {
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  const wrapper = mount(InstalledToolsPage, {
    props: { apiClient: createMockApi({ latency: 0 }) },
    global: { plugins: [createPinia(), router] },
  })
  await flushPromises()
  return { wrapper, router }
}

it('defaults to the lifecycle board and switches three views exclusively', async () => {
  const { wrapper, router } = await mountPage()
  expect(wrapper.findAll('[data-installed-tool-surface]').map((button) => button.text()))
    .toEqual(['项目周期看板', '生命周期看板', '设备档案'])
  expect(wrapper.find('[data-installed-tool-pipeline]').exists()).toBe(true)
  expect(wrapper.find('[data-installed-tool-project-board]').exists()).toBe(false)
  expect(wrapper.find('[data-installed-tool-archive]').exists()).toBe(false)

  await wrapper.get('[data-installed-tool-surface="project"]').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query.surface).toBe('project')
  expect(wrapper.find('[data-installed-tool-project-board]').exists()).toBe(true)
  expect(wrapper.find('[data-installed-tool-pipeline]').exists()).toBe(false)

  await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query.surface).toBe('detail')
  expect(wrapper.find('[data-installed-tool-archive]').exists()).toBe(true)
  expect(wrapper.find('[data-installed-tool-project-board]').exists()).toBe(false)
})

it('opens a tool archive from either board and restores route state', async () => {
  const { wrapper, router } = await mountPage('/installed-tools?surface=project')
  const projectRow = wrapper.get('[data-installed-tool-project-row]')
  const projectId = projectRow.attributes('data-installed-tool-project-id')
  await projectRow.trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.query).toMatchObject({ surface: 'detail', tool: projectId })
  expect(wrapper.get('[data-installed-tool-archive]').text()).toContain(projectId)

  const restored = await mountPage(`/installed-tools?surface=detail&tool=${projectId}`)
  expect(restored.wrapper.get('[data-installed-tool-archive]').text()).toContain(projectId)
})

it('falls back from invalid route values without stale detail', async () => {
  const { wrapper, router } = await mountPage('/installed-tools?surface=unknown&tool=missing')
  expect(wrapper.find('[data-installed-tool-pipeline]').exists()).toBe(true)
  expect(router.currentRoute.value.query.surface).toBe('lifecycle')
  expect(router.currentRoute.value.query.tool).not.toBe('missing')
})
```

Add a separate lifecycle-card assertion that clicks `[data-installed-tool-id]` and expects the same `{ surface: 'detail', tool: id }` result.

- [ ] **Step 2: Run the page test and verify red**

Run:

```powershell
pnpm test -- src/pages/InstalledToolsPage.test.ts
```

Expected: FAIL because the three view buttons and route behavior are absent.

- [ ] **Step 3: Implement surface state, route synchronization and exclusive rendering**

Add router state helpers to the page:

```ts
type InstalledToolSurface = 'project' | 'lifecycle' | 'detail'
const route = useRoute() as ReturnType<typeof useRoute> | undefined
const router = useRouter() as ReturnType<typeof useRouter> | undefined

function readQuery(key: string) {
  const value = route?.query?.[key]
  return typeof value === 'string' ? value : ''
}

function parseSurface(value: string): InstalledToolSurface {
  return value === 'project' || value === 'detail' ? value : 'lifecycle'
}

const surface = ref<InstalledToolSurface>(parseSurface(readQuery('surface')))
const selectedId = ref(readQuery('tool'))
```

Use three explicit navigation functions:

```ts
async function writeRoute(mode: 'push' | 'replace' = 'push') {
  await router?.[mode]({
    name: 'installed-tools',
    query: { surface: surface.value, tool: selectedId.value || undefined },
  })
}

async function switchSurface(next: InstalledToolSurface) {
  surface.value = next
  if (!selected.value) selectedId.value = filtered.value[0]?.id ?? ''
  await writeRoute('push')
}

async function openDetail(item: InstalledToolDto) {
  selectedId.value = item.id
  surface.value = 'detail'
  await writeRoute('push')
}

async function selectArchive(item: InstalledToolDto) {
  selectedId.value = item.id
  await writeRoute('replace')
}
```

After loading, validate `tool`; when absent or invalid, choose the first filtered item. Normalize invalid `surface` and `tool` with one `router.replace`. Watch route query values so browser back/forward restores the surface and selected equipment. Preserve the existing selected-ID correction when filters remove the selected tool and update the route only when `surface === 'detail'`.

Render the three buttons in the title action area and make the body exclusive:

```vue
<nav class="surface-switch" aria-label="Installed Tool 视图">
  <button v-for="item in surfaces" :key="item.key"
    type="button" :data-installed-tool-surface="item.key"
    :class="{ active: surface === item.key }" @click="switchSurface(item.key)">
    {{ item.label }}
  </button>
</nav>

<InstalledToolPipelineBoard
  v-if="surface === 'lifecycle' && filtered.length"
  :items="filtered" :selected-id="selected?.id" @select="openDetail"
/>
<InstalledToolProjectCycleBoard
  v-else-if="surface === 'project' && filtered.length"
  :items="filtered" :selected-id="selected?.id" @select="openDetail"
/>
<InstalledToolArchiveView
  v-else-if="surface === 'detail' && filtered.length"
  :items="filtered" :selected-id="selected?.id ?? ''" :can-edit="canEditSelected"
  @select="selectArchive" @edit="openEditor" @document="showDocument"
/>
<section v-else class="workspace-panel workspace-panel-body">没有匹配筛选条件的 Installed Tool。</section>
```

Copy the compact Demo-style `.surface-switch` styling into this page’s scoped CSS and add only the responsive header rule needed below 760px. Keep the shared filter panel visible above every selected surface.

- [ ] **Step 4: Run focused tests and typecheck**

Run:

```powershell
pnpm test -- src/pages/InstalledToolsPage.test.ts src/features/installed-tools/InstalledToolProjectCycleBoard.test.ts src/features/installed-tools/InstalledToolArchiveView.test.ts src/features/installed-tools/InstalledToolPipelineBoard.test.ts
pnpm typecheck
```

Expected: all commands PASS.

- [ ] **Step 5: Commit three-view orchestration**

```powershell
git add -- src/pages/InstalledToolsPage.vue src/pages/InstalledToolsPage.test.ts
git commit -m "feat: add installed tool three-view workspace"
```

### Task 4: Preserve Existing Installed Tool Workflows and Verify the Build

**Files:**
- Modify: `src/pages/seven-page-workspace.test.ts`
- Modify: `src/pages/first-demo-completion.test.ts`

**Interfaces:**
- Consumes: page hook `data-installed-tool-surface="detail"`.
- Produces: regression evidence that archive detail, editor permissions, filters and converted Booking data still work after defaulting to lifecycle.

- [ ] **Step 1: Update existing tests to enter Equipment Archive explicitly**

After each relevant Installed Tools mount and `flushPromises()`, enter the detail surface before assertions that target `.workspace-select-card`, `.lifecycle-step`, `.detail-tabs`, `.tool-header` or the edit button:

```ts
await wrapper.get('[data-installed-tool-surface="detail"]').trigger('click')
await flushPromises()
```

Apply this to:

- selected lifecycle and warranty state;
- combined filters and reset;
- converted Booking FAT stage;
- Manager edit/reassignment;
- Engineer assignment and disabled reassignment;
- Sales read-only edit visibility;
- first demo completion assertions for “版本与配置” and “质保与服务”.

Do not weaken any existing count, permission or update assertion.

- [ ] **Step 2: Run Installed Tool regression tests**

Run:

```powershell
pnpm test -- src/pages/InstalledToolsPage.test.ts src/pages/seven-page-workspace.test.ts src/pages/first-demo-completion.test.ts src/features/installed-tools/InstalledToolPipelineBoard.test.ts src/features/installed-tools/InstalledToolProjectCycleBoard.test.ts src/features/installed-tools/InstalledToolArchiveView.test.ts
```

Expected: all test files PASS.

- [ ] **Step 3: Run the complete static and production build verification**

Run:

```powershell
pnpm typecheck
pnpm build:frappe
```

Expected: Vue TypeScript checking succeeds and the Frappe bundle finishes without build errors.

- [ ] **Step 4: Perform browser desktop and responsive verification**

Using the existing local frontend session, verify `/installed-tools` at desktop width and approximately 760 px width:

1. Lifecycle is selected on first load and the equipment archive is absent from the same viewport.
2. Project Cycle shows one row per filtered tool and the five milestone columns in order.
3. Clicking a project row and lifecycle card opens the matching Equipment Archive.
4. Refreshing `?surface=detail&tool=<known-id>` restores the same record.
5. Search and all three dropdown filters affect lifecycle, project and archive results.
6. The three main buttons and three internal archive tabs remain visually distinct at both widths.
7. No runtime console errors occur.

Capture screenshots for the three desktop views and one narrow layout as verification artifacts; do not commit generated screenshots.

- [ ] **Step 5: Commit regression updates**

```powershell
git add -- src/pages/seven-page-workspace.test.ts src/pages/first-demo-completion.test.ts
git commit -m "test: preserve installed tool archive workflows"
```

- [ ] **Step 6: Review final diff scope**

Run:

```powershell
git status --short
git diff --stat HEAD~4..HEAD
git diff --check HEAD~4..HEAD
```

Expected: only the eight files listed in the File Map are part of this feature, `git diff --check` prints no whitespace errors, and unrelated pre-existing worktree changes remain untouched.