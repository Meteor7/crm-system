<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CheckCircle2, Cpu, RotateCcw } from '@lucide/vue'
import { api as defaultApi } from '@/api'
import type { CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import InstalledToolArchiveView from '@/features/installed-tools/InstalledToolArchiveView.vue'
import InstalledToolEditorModal from '@/features/installed-tools/InstalledToolEditorModal.vue'
import InstalledToolPipelineBoard from '@/features/installed-tools/InstalledToolPipelineBoard.vue'
import InstalledToolProjectCycleBoard from '@/features/installed-tools/InstalledToolProjectCycleBoard.vue'
import InstalledToolServiceModal from '@/features/installed-tools/InstalledToolServiceModal.vue'
import InstalledToolTransitionModal from '@/features/installed-tools/InstalledToolTransitionModal.vue'
import InstalledToolVersionModal from '@/features/installed-tools/InstalledToolVersionModal.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import type { BootstrapDto, SiteDto } from '@/types/crm'
import type {
  AddInstalledToolServiceRecordInput,
  AddInstalledToolVersionRecordInput,
  InstalledToolDetailDto,
  InstalledToolDto,
  TransitionInstalledToolInput,
  UpdateInstalledToolInput,
} from '@/types/workspaces'
import { personnelDisplayName } from '@/demo/personnel'

type InstalledToolSurface = 'project' | 'lifecycle' | 'detail'
type ModalKind = 'editor' | 'transition' | 'version' | 'service' | ''

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const route = useRoute() as ReturnType<typeof useRoute> | undefined
const router = useRouter() as ReturnType<typeof useRouter> | undefined

function readQuery(key: string) {
  const value = route?.query?.[key]
  return typeof value === 'string' ? value : ''
}
function parseSurface(value: string): InstalledToolSurface {
  return value === 'project' || value === 'detail' ? value : 'lifecycle'
}

const surfaces: Array<{ key: InstalledToolSurface; label: string }> = [
  { key: 'project', label: '项目周期看板' },
  { key: 'lifecycle', label: '生命周期看板' },
  { key: 'detail', label: '设备档案' },
]
const installedTools = ref<InstalledToolDto[]>([])
const total = ref(0), page = ref(1)
const pageSize = ref(10)
const selectedId = ref(readQuery('tool'))
const surface = ref<InstalledToolSurface>(parseSurface(readQuery('surface')))
const accountId = ref(readQuery('accountId') || 'All')
const status = ref(readQuery('status') || 'All')
const engineerOwner = ref(readQuery('engineer') || 'All')
const loading = ref(true)
const error = ref('')
const requestId = ref('')
const notice = ref('')
const bootstrap = ref<BootstrapDto | null>(null)
const detail = ref<InstalledToolDetailDto | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const detailRequestId = ref('')
let detailSequence = 0
const activeModal = ref<ModalKind>('')
const actionBusy = ref(false)
const actionError = ref('')
const editorSites = ref<SiteDto[]>([])
let filterTimer: ReturnType<typeof setTimeout> | undefined

function matchesFilters(item: InstalledToolDto) {
  return (accountId.value === 'All' || item.accountId === accountId.value)
    && (status.value === 'All' || item.status === status.value)
    && (engineerOwner.value === 'All' || item.engineerOwner === engineerOwner.value)
}
const filtered = computed(() => installedTools.value.filter(matchesFilters))
const archiveItems = computed<InstalledToolDto[]>(() => {
  if (surface.value !== 'detail' || detail.value?.id !== selectedId.value) return filtered.value
  if (!matchesFilters(detail.value)) return filtered.value
  if (filtered.value.some((item) => item.id === detail.value?.id)) return filtered.value
  return [detail.value, ...filtered.value]
})
const selected = computed(() => {
  const items = surface.value === 'detail' ? archiveItems.value : filtered.value
  return items.find((item) => item.id === selectedId.value)
    ?? (surface.value === 'detail' && selectedId.value ? undefined : items[0])
})
const statusOptions = computed(() => ['All', ...new Set(installedTools.value.map((item) => item.status))])
const accountOptions = computed(() => [...new Map(installedTools.value.map((item) => [item.accountId, item.account])).entries()])
const engineerOptions = computed(() => [...new Set(installedTools.value.map((item) => item.engineerOwner).filter(Boolean))])
const assignmentEngineers = computed(() => (bootstrap.value?.personnel ?? [])
  .filter((item) => item.role === 'Engineer' && (item.availableForAssignment || item.id === detail.value?.engineerOwner))
  .map((item) => ({ id: item.id, name: item.name, role: item.role })))
const serviceActionOwners = computed(() => (bootstrap.value?.personnel ?? [])
  .map((item) => ({ id: item.id, name: item.name, role: item.role })))
const formattedDetailError = computed(() => detailError.value
  ? `${detailError.value}${detailRequestId.value ? ` · Request ID: ${detailRequestId.value}` : ''}`
  : '')

async function writeRoute(mode: 'push' | 'replace' = 'push') {
  if (!router) return
  const query = {
    ...route?.query,
    surface: surface.value,
    tool: selectedId.value || undefined,
    q: undefined,
    accountId: accountId.value === 'All' ? undefined : accountId.value,
    status: status.value === 'All' ? undefined : status.value,
    engineer: engineerOwner.value === 'All' ? undefined : engineerOwner.value,
  }
  if (mode === 'replace') await router.replace({ name: 'installed-tools', query })
  else await router.push({ name: 'installed-tools', query })
}

async function loadDetail(id: string) {
  const sequence = ++detailSequence
  detail.value = null
  detailLoading.value = true
  detailError.value = ''
  detailRequestId.value = ''
  try {
    const result = await props.apiClient.getInstalledTool(id)
    if (sequence !== detailSequence || selectedId.value !== id || surface.value !== 'detail') return
    detail.value = result.data
  } catch (reason) {
    if (sequence !== detailSequence || selectedId.value !== id) return
    const mapped = mapRequestError(reason)
    detailError.value = mapped.message
    detailRequestId.value = mapped.requestId
  } finally {
    if (sequence === detailSequence) detailLoading.value = false
  }
}

async function loadList() {
  const result = await props.apiClient.listInstalledTools({ page: page.value, pageSize: pageSize.value, accountId: accountId.value, status: status.value, owner: engineerOwner.value })
  installedTools.value = result.data.items
  total.value = result.meta?.total ?? installedTools.value.length
  if (!result.data.items.some((item) => item.id === selectedId.value)
    && !(surface.value === 'detail' && selectedId.value)) {
    selectedId.value = result.data.items[0]?.id ?? ''
  }
}
async function goPage(target: number) {
  page.value = target
  await loadList()
}
async function changePageSize(value: number) {
  pageSize.value = value
  page.value = 1
  await loadList()
}
watch([accountId, status, engineerOwner], () => {
  page.value = 1
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = setTimeout(() => { void loadList(); void writeRoute('replace') }, 180)
})

async function reloadListAndDetail(id: string) {
  await loadList()
  if (selectedId.value === id && surface.value === 'detail') await loadDetail(id)
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

watch(filtered, async (items) => {
  if (items.length && !items.some((item) => item.id === selectedId.value)
    && !(surface.value === 'detail' && selectedId.value)) {
    selectedId.value = items[0].id
    if (surface.value === 'detail') await writeRoute('replace')
  }
})
watch([surface, selectedId], ([nextSurface, id], [previousSurface, previousId]) => {
  if (nextSurface === 'detail' && id && (nextSurface !== previousSurface || id !== previousId)) void loadDetail(id)
  else if (nextSurface !== 'detail') {
    detailSequence += 1
    detail.value = null
    detailLoading.value = false
  }
})
watch(
  () => [readQuery('surface'), readQuery('tool'), readQuery('accountId'), readQuery('status'), readQuery('engineer')],
  ([surfaceQuery, toolQuery, accountQuery, statusQuery, engineerQuery]) => {
    surface.value = parseSurface(surfaceQuery)
    accountId.value = accountQuery || 'All'
    status.value = statusQuery || 'All'
    engineerOwner.value = engineerQuery || 'All'
    if (toolQuery && (surface.value === 'detail' || filtered.value.some((item) => item.id === toolQuery))) selectedId.value = toolQuery
    else if (filtered.value.length && !filtered.value.some((item) => item.id === selectedId.value)) selectedId.value = filtered.value[0].id
  },
)

function showDocument(name: string) {
  notice.value = `${name} 已记录；当前接口未提供下载地址。`
  window.setTimeout(() => { notice.value = '' }, 3000)
}
function resetFilters() {
  accountId.value = 'All'
  status.value = 'All'
  engineerOwner.value = 'All'
}
function closeModal() {
  if (actionBusy.value) return
  activeModal.value = ''
  actionError.value = ''
}
function requireOperableDetail() {
  return detail.value?.id === selectedId.value && detail.value.canOperate ? detail.value : null
}
function openTransition() {
  if (!requireOperableDetail() || detail.value?.lifecycleCompleted) return
  actionError.value = ''
  activeModal.value = 'transition'
}
function openVersion() {
  if (!requireOperableDetail()) return
  actionError.value = ''
  activeModal.value = 'version'
}
function openService() {
  if (!requireOperableDetail()) return
  actionError.value = ''
  activeModal.value = 'service'
}

async function openEditor() {
  const current = requireOperableDetail()
  if (!current) return
  actionError.value = ''
  editorSites.value = []
  activeModal.value = 'editor'
  try {
    editorSites.value = (await props.apiClient.getAccount360(current.accountId)).data.sites
  } catch (reason) {
    const mapped = mapRequestError(reason)
    actionError.value = `${mapped.message} · Request ID: ${mapped.requestId}`
  }
}

function expectedModified(current: InstalledToolDetailDto) {
  if (!current.modified) throw new Error('设备版本标识缺失，请刷新档案后重试。')
  return current.modified
}
function mutationError(reason: unknown) {
  const mapped = mapRequestError(reason)
  return `${mapped.message} · Request ID: ${mapped.requestId}`
}
async function finishMutation(updated: InstalledToolDetailDto, message: string) {
  detail.value = updated
  const index = installedTools.value.findIndex((item) => item.id === updated.id)
  if (index >= 0) installedTools.value[index] = updated
  activeModal.value = ''
  notice.value = message
  window.setTimeout(() => { notice.value = '' }, 3000)
  try {
    await reloadListAndDetail(updated.id)
  } catch (reason) {
    notice.value = '操作已保存，但重新读取失败：' + mutationError(reason)
    window.setTimeout(() => { notice.value = '' }, 6000)
  }
}
async function advanceLifecycle(input: TransitionInstalledToolInput) {
  const current = requireOperableDetail()
  if (!current) return
  actionBusy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.transitionInstalledTool(current.id, input, expectedModified(current))
    await finishMutation(result.data, `${current.serial} 已推进到下一生命周期节点`)
  } catch (reason) {
    actionError.value = mutationError(reason)
  } finally {
    actionBusy.value = false
  }
}
async function addVersion(input: AddInstalledToolVersionRecordInput) {
  const current = requireOperableDetail()
  if (!current) return
  actionBusy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.addInstalledToolVersionRecord(current.id, input, expectedModified(current))
    await finishMutation(result.data, `${current.serial} 版本记录已保存`)
  } catch (reason) {
    actionError.value = mutationError(reason)
  } finally {
    actionBusy.value = false
  }
}
async function addService(input: AddInstalledToolServiceRecordInput) {
  const current = requireOperableDetail()
  if (!current) return
  actionBusy.value = true
  actionError.value = ''
  try {
    const result = await props.apiClient.addInstalledToolServiceRecord(current.id, input, expectedModified(current))
    await finishMutation(result.data, `${current.serial} 服务记录已保存`)
  } catch (reason) {
    actionError.value = mutationError(reason)
  } finally {
    actionBusy.value = false
  }
}
async function saveInstalledTool(input: UpdateInstalledToolInput) {
  const current = requireOperableDetail()
  if (!current || actionBusy.value) return
  actionBusy.value = true
  actionError.value = ''
  try {
    await props.apiClient.updateInstalledTool(current.id, input, expectedModified(current))
    activeModal.value = ''
    notice.value = current.serial + ' 设备主数据已更新'
    try {
      await reloadListAndDetail(current.id)
    } catch (reason) {
      notice.value = '主数据已保存，但重新读取失败：' + mutationError(reason)
      window.setTimeout(() => { notice.value = '' }, 6000)
    }
  } catch (reason) {
    actionError.value = mutationError(reason)
  } finally {
    actionBusy.value = false
  }
}
onMounted(async () => {
  try {
    const [bootstrapResult] = await Promise.all([props.apiClient.getBootstrap(), loadList()])
    bootstrap.value = bootstrapResult.data
    await writeRoute('replace')
    if (surface.value === 'detail' && selectedId.value) await loadDetail(selectedId.value)
  } catch (reason) {
    const mapped = mapRequestError(reason)
    error.value = mapped.message
    requestId.value = mapped.requestId
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="workspace-page" data-page="installed-tools">
    <header class="page-title-row">
      <div><span class="eyebrow">INSTALLED BASE · DELIVERY LIFECYCLE</span><h1>Installed Tools</h1><p>以 Serial Number 为设备唯一标识，追踪从工厂验收到质保服务的完整交付档案。</p></div>
      <div class="header-actions">
        <nav class="surface-switch" aria-label="Installed Tool 视图">
          <button v-for="item in surfaces" :key="item.key" type="button" :data-installed-tool-surface="item.key" :class="{ active: surface === item.key }" @click="switchSurface(item.key)">{{ item.label }}</button>
        </nav>
        <span class="context-chip"><Cpu :size="15" />{{ installedTools.length }} 台客户设备</span>
      </div>
    </header>

    <section v-if="loading" class="workspace-panel workspace-panel-body">正在读取 Installed Tool 主数据…</section>
    <section v-else-if="error" class="workspace-panel workspace-panel-body">{{ error }}<small v-if="requestId">Request ID: {{ requestId }}</small></section>
    <section v-else-if="!installedTools.length" class="workspace-panel workspace-panel-body">当前暂无 Installed Tool。</section>

    <template v-else>
      <section class="workspace-panel tool-filter-panel" aria-label="Installed Tool 筛选">
        <select v-model="accountId" aria-label="客户筛选"><option value="All">全部客户</option><option v-for="[id, name] in accountOptions" :key="id" :value="id">{{ name }}</option></select>
        <select v-model="status" aria-label="设备状态筛选"><option v-for="item in statusOptions" :key="item" :value="item">{{ item === 'All' ? '全部状态' : item }}</option></select>
        <select v-model="engineerOwner" aria-label="负责工程师筛选"><option value="All">全部工程师</option><option v-for="owner in engineerOptions" :key="owner" :value="owner">{{ personnelDisplayName(owner) }}</option></select>
        <button type="button" data-testid="reset-installed-tool-filters" @click="resetFilters"><RotateCcw :size="13" />重置条件</button>
      </section>

      <div class="tool-surface" :data-installed-tool-view="surface">
        <InstalledToolPipelineBoard v-if="surface === 'lifecycle' && filtered.length" :items="filtered" :selected-id="selected?.id" @select="openDetail" />
        <InstalledToolProjectCycleBoard v-else-if="surface === 'project' && filtered.length" :items="filtered" :selected-id="selected?.id" @select="openDetail" />
        <InstalledToolArchiveView
          v-else-if="surface === 'detail' && selectedId"
          :items="archiveItems"
          :selected-id="selectedId"
          :detail="detail"
          :detail-loading="detailLoading"
          :detail-error="formattedDetailError"
          @select="selectArchive"
          @edit="openEditor"
          @advance="openTransition"
          @version="openVersion"
          @service="openService"
          @document="showDocument"
        />
        <section v-else class="workspace-panel workspace-panel-body">没有匹配筛选条件的 Installed Tool。</section>
      </div>
      <PaginationControls v-if="total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </template>

    <InstalledToolEditorModal
      v-if="activeModal === 'editor' && detail"
      :tool="detail"
      :sites="editorSites"
      :engineers="assignmentEngineers"
      :can-reassign="detail.canReassign"
      :busy="actionBusy"
      :error="actionError"
      @close="closeModal"
      @submit="saveInstalledTool"
    />
    <InstalledToolTransitionModal
      v-if="activeModal === 'transition' && detail"
      :stage="detail.lifecycleStage ?? 'FAT'"
      :busy="actionBusy"
      :error="actionError"
      @close="closeModal"
      @submit="advanceLifecycle"
    />
    <InstalledToolVersionModal
      v-if="activeModal === 'version' && detail"
      :tool="detail"
      :busy="actionBusy"
      :error="actionError"
      @close="closeModal"
      @submit="addVersion"
    />
    <InstalledToolServiceModal
      v-if="activeModal === 'service' && detail"
      :tool="detail"
      :action-owners="serviceActionOwners"
      :busy="actionBusy"
      :error="actionError"
      @close="closeModal"
      @submit="addService"
    />
    <transition name="toast"><div v-if="notice" class="demo-toast"><CheckCircle2 :size="15" />{{ notice }}</div></transition>
  </div>
</template>

<style scoped>
.header-actions{display:flex;align-items:center;gap:10px}.surface-switch{display:grid;grid-template-columns:repeat(3,1fr);padding:3px;background:#ece9e3;border-radius:7px}.surface-switch button{height:38px;padding:0 14px;color:#686d73;background:transparent;border:0;border-radius:5px;cursor:pointer;font-size:11px;font-weight:750;white-space:nowrap}.surface-switch button.active{color:#e86600;background:#fff;box-shadow:0 1px 5px rgba(30,34,38,.08)}.tool-surface{min-width:0}.tool-filter-panel{display:grid;grid-template-columns:minmax(240px,1.5fr) repeat(3,minmax(135px,.8fr)) auto;align-items:center;gap:9px;padding:12px}.tool-filter-panel select,.tool-filter-panel input{box-sizing:border-box;width:100%;height:38px;padding:0 10px;color:var(--crm-navy);background:#fff;border:1px solid var(--crm-line);border-radius:9px;font:inherit;font-size:9px}.tool-search{display:flex;align-items:center;gap:7px;padding-left:10px;color:var(--crm-text-muted);background:#fff;border:1px solid var(--crm-line);border-radius:9px}.tool-search input{padding-left:0;border:0}.tool-filter-panel>button{display:inline-flex;height:38px;align-items:center;justify-content:center;gap:6px;padding:0 12px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:9px;font-size:9px;font-weight:800;cursor:pointer}.demo-toast{position:fixed;right:22px;bottom:22px;z-index:2300;display:flex;align-items:center;gap:8px;padding:11px 14px;color:#fff;background:var(--crm-navy);border-radius:9px;box-shadow:0 10px 35px rgba(31,35,41,.22);font-size:9px}.toast-enter-active,.toast-leave-active{transition:.2s ease}.toast-enter-from,.toast-leave-to{opacity:0;transform:translateY(8px)}@media(max-width:1100px){.page-title-row{align-items:flex-start;flex-direction:column}.header-actions{width:100%;justify-content:space-between}}@media(max-width:900px){.tool-filter-panel{grid-template-columns:1fr 1fr}}@media(max-width:760px){.header-actions{align-items:stretch;flex-direction:column}.surface-switch{width:100%}.tool-filter-panel{grid-template-columns:1fr}}
</style>
