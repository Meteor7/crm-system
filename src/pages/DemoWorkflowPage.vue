<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi } from '@/api'
import type { CrmApi } from '@/api'
import { mapRequestError, requestErrorMessage } from '@/api/request-state'
import type { DemoArchiveGroupMode } from '@/domain/demo-archive'
import type { DemoHealthLevel } from '@/types/crm'
import type { DemoWorkflowDto } from '@/types/workspaces'
import DemoArchiveBrowser from '@/features/demo-workflow/DemoArchiveBrowser.vue'
import DemoArchiveDetail from '@/features/demo-workflow/DemoArchiveDetail.vue'
import DemoPipelineBoard from '@/features/demo-workflow/DemoPipelineBoard.vue'
import DemoProjectCycleBoard from '@/features/demo-workflow/DemoProjectCycleBoard.vue'
import { useAppStore } from '@/stores/app'
import { downloadBlob } from '@/features/shared/download-blob'
import { readAllPages } from '@/features/shared/read-all-pages'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'

type DemoSurface = 'project' | 'board' | 'archive'
type ArchiveResult = 'all' | 'Accepted' | 'Rejected'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore()
const { t, locale } = useI18n()
const route = useRoute() as ReturnType<typeof useRoute> | undefined
const router = useRouter() as ReturnType<typeof useRouter> | undefined
const archives = ref<DemoWorkflowDto[]>([])
const loading = ref(true)
const error = useLocaleMessage()
const notice = useLocaleMessage()
const artifactBusyId = ref(''), artifactError = useLocaleMessage(), artifactRequestId = ref('')
const surface = ref<DemoSurface>(parseSurface(readQuery('surface')))
const detailFocus = ref(readQuery('view') === 'detail' ? readQuery('focus') : '')
const health = ref<'all' | DemoHealthLevel>(
  ['healthy', 'stalled', 'critical'].includes(readQuery('health'))
    ? readQuery('health') as DemoHealthLevel
    : 'all',
)
const archiveResult = ref<ArchiveResult>(
  ['Accepted', 'Rejected'].includes(readQuery('result'))
    ? readQuery('result') as ArchiveResult
    : 'all',
)
const groupBy = ref<DemoArchiveGroupMode>(readQuery('groupBy') === 'equipment' ? 'equipment' : 'customer')
const customer = ref(readQuery('customer') || 'all')
const salesOwner = ref(readQuery('sales') || 'all')
const engineerOwner = ref(readQuery('engineer') || 'all')

const activeArchives = computed(() => archives.value.filter((item) => item.archiveCategory === 'In Progress' && item.stage))
const completedArchives = computed(() => archives.value.filter((item) => item.archiveCategory === 'Completed'))
const selected = computed(() => {
  const items = surface.value === 'archive'
    ? completedArchives.value
    : surface.value === 'project'
      ? archives.value
      : activeArchives.value
  return items.find((item) => item.id === detailFocus.value)
})
const isDetail = computed(() => Boolean(detailFocus.value && selected.value))

function readQuery(key: string) {
  const value = route?.query?.[key]
  return typeof value === 'string' ? value : ''
}

function parseSurface(value: string): DemoSurface {
  return value === 'project' || value === 'archive' ? value : 'board'
}

function cleanQuery(input: Record<string, string | undefined>) {
  return Object.fromEntries(Object.entries(input).filter(([, value]) => value))
}

function surfaceQuery() {
  const common = {
    customer: customer.value === 'all' ? undefined : customer.value,
    sales: salesOwner.value === 'all' ? undefined : salesOwner.value,
    engineer: engineerOwner.value === 'all' ? undefined : engineerOwner.value,
  }
  if (surface.value === 'archive') {
    return cleanQuery({
      ...common,
      surface: 'archive',
      result: archiveResult.value === 'all' ? undefined : archiveResult.value,
      groupBy: groupBy.value === 'customer' ? undefined : groupBy.value,
    })
  }
  if (surface.value === 'project') {
    return cleanQuery({
      ...common,
      surface: 'project',
      health: health.value === 'all' ? undefined : health.value,
    })
  }
  return cleanQuery({
    ...common,
    health: health.value === 'all' ? undefined : health.value,
  })
}

function currentQuery() {
  return isDetail.value
    ? { ...surfaceQuery(), view: 'detail', focus: detailFocus.value }
    : surfaceQuery()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    await app.loadBootstrap(props.apiClient)
    archives.value = await readAllPages((page, pageSize) => props.apiClient.listDemoWorkflows({ page, pageSize }))
    if (detailFocus.value && !selected.value) {
      notice.value = localeMessage(`Demo archive ${detailFocus.value} was not found. Returned to the current view.`, `未找到 Demo 档案 ${detailFocus.value}，已返回当前视图。`)
      detailFocus.value = ''
      await router?.replace({ name: 'demo-workflow', query: surfaceQuery() })
    }
  } catch (reason) {
    error.value = requestErrorMessage(reason, localeMessage('Failed to load Demo archives.', 'Demo 档案加载失败'))
  } finally {
    loading.value = false
  }
}

async function switchSurface(next: DemoSurface) {
  surface.value = next
  detailFocus.value = ''
  notice.value = ''
  await router?.push({ name: 'demo-workflow', query: surfaceQuery() })
}

async function openDetail(item: DemoWorkflowDto) {
  notice.value = ''
  await router?.push({
    name: 'demo-detail',
    params: { demoId: item.id },
    query: {
      ...surfaceQuery(),
      from: 'demo-workflow',
    },
  })
}

async function backToSurface() {
  detailFocus.value = ''
  await router?.push({ name: 'demo-workflow', query: surfaceQuery() })
}

async function updateHealth(value: 'all' | DemoHealthLevel) {
  health.value = value
  await router?.replace({ name: 'demo-workflow', query: currentQuery() })
}

async function updateArchiveResult(value: ArchiveResult) {
  archiveResult.value = value
  await router?.replace({ name: 'demo-workflow', query: currentQuery() })
}

async function updateGroupBy(value: DemoArchiveGroupMode) {
  groupBy.value = value
  await router?.replace({ name: 'demo-workflow', query: currentQuery() })
}

async function updateSalesOwner(value: string) {
  salesOwner.value = value
  await router?.replace({ name: 'demo-workflow', query: currentQuery() })
}

async function updateCustomer(value: string) {
  customer.value = value
  await router?.replace({ name: 'demo-workflow', query: currentQuery() })
}

async function updateEngineerOwner(value: string) {
  engineerOwner.value = value
  await router?.replace({ name: 'demo-workflow', query: currentQuery() })
}

async function downloadArtifact(id: string) {
  if (artifactBusyId.value) return
  artifactBusyId.value = id
  artifactError.value = ''
  artifactRequestId.value = ''
  try {
    const result = await props.apiClient.getDemoArtifact(id)
    downloadBlob(result.blob, result.fileName)
  } catch (reason) {
    const mapped = mapRequestError(reason)
    artifactError.value = mapped.localizedMessage ?? mapped.message
    artifactRequestId.value = mapped.requestId
  } finally {
    artifactBusyId.value = ''
  }
}

watch(
  () => [
    readQuery('surface'),
    readQuery('view'),
    readQuery('focus'),
    readQuery('groupBy'),
    readQuery('result'),
    readQuery('customer'),
  ],
  ([surfaceQueryValue, view, focus, groupQueryValue, resultQueryValue, customerQueryValue]) => {
    surface.value = parseSurface(surfaceQueryValue)
    detailFocus.value = view === 'detail' ? focus : ''
    groupBy.value = groupQueryValue === 'equipment' ? 'equipment' : 'customer'
    archiveResult.value = ['Accepted', 'Rejected'].includes(resultQueryValue)
      ? resultQueryValue as ArchiveResult
      : 'all'
    customer.value = customerQueryValue || 'all'
  },
)

onMounted(load)
</script>

<template>
  <div class="workspace-page demo-archive-page" data-page="demo-workflow">
    <header class="page-title-row demo-page-header">
      <div>
        <span class="eyebrow">{{ locale === 'en-US' ? 'DEMO ARCHIVE' : 'DEMO 档案' }}</span>
        <h1>{{ surface === 'project' ? t('demo.projectTitle') : t('demo.title') }}</h1>
        <p>
          {{ surface === 'project'
            ? t('demo.projectDescription')
            : surface === 'board'
              ? t('demo.boardDescription')
              : t('demo.archiveDescription') }}
        </p>
      </div>
      <div class="header-actions">
        <nav class="surface-switch" :aria-label="locale === 'en-US' ? 'Demo archive views' : 'Demo 档案视图'">
          <button
            type="button"
            data-demo-surface="project"
            :class="{ active: surface === 'project' }"
            @click="switchSurface('project')"
          >{{ t('demo.projectTab') }}</button>
          <button
            type="button"
            data-demo-surface="board"
            :class="{ active: surface === 'board' }"
            @click="switchSurface('board')"
          >{{ t('demo.boardTab') }}</button>
          <button
            type="button"
            data-demo-surface="archive"
            :class="{ active: surface === 'archive' }"
            @click="switchSurface('archive')"
          >{{ t('demo.archiveTab') }}</button>
        </nav>
        <button
          v-if="isDetail"
          class="back-button"
          data-back-to-demo-board
          data-back-to-demo-surface
          type="button"
          @click="backToSurface"
        >
          <ArrowLeft :size="16" />
          {{ surface === 'archive' ? t('demo.backArchive') : surface === 'project' ? t('demo.backProject') : t('demo.backBoard') }}
        </button>
      </div>
    </header>

    <p v-if="notice" class="board-notice" role="status">{{ notice }}</p>
    <p v-if="artifactError" class="board-notice" data-artifact-error role="alert">{{ artifactError }}<small v-if="artifactRequestId">Request ID {{ artifactRequestId }}</small></p>
    <section v-if="loading" class="workspace-panel workspace-panel-body">{{ t('demo.loading') }}</section>
    <section v-else-if="error" class="workspace-panel workspace-panel-body">
      <p>{{ error }}</p>
      <button type="button" class="secondary-button" @click="load">{{ t('demo.retry') }}</button>
    </section>
    <section v-else-if="!archives.length" class="workspace-panel workspace-panel-body">
      {{ t('demo.empty') }}
    </section>

    <DemoProjectCycleBoard
      v-else-if="surface === 'project' && !isDetail"
      :items="archives"
      :health="health"
      :customer="customer"
      :sales-owner="salesOwner"
      :engineer-owner="engineerOwner"
      @update:health="updateHealth"
      @update:customer="updateCustomer"
      @update:sales-owner="updateSalesOwner"
      @update:engineer-owner="updateEngineerOwner"
      @open="openDetail"
    />

    <DemoPipelineBoard
      v-else-if="surface === 'board' && !isDetail"
      :items="activeArchives"
      :health="health"
      :sales-owner="salesOwner"
      :engineer-owner="engineerOwner"
      @update:health="updateHealth"
      @update:sales-owner="updateSalesOwner"
      @update:engineer-owner="updateEngineerOwner"
      @open="openDetail"
    />

    <DemoArchiveDetail :api-client="apiClient"
      v-else-if="(surface === 'board' || surface === 'project') && selected"
      :item="selected"
      @download="downloadArtifact"
    />

    <div v-else-if="surface === 'archive'" class="archive-layout">
      <DemoArchiveBrowser
        :items="completedArchives"
        :result="archiveResult"
        :sales-owner="salesOwner"
        :engineer-owner="engineerOwner"
        :group-by="groupBy"
        :selected-id="detailFocus"
        @update:result="updateArchiveResult"
        @update:sales-owner="updateSalesOwner"
        @update:engineer-owner="updateEngineerOwner"
        @group-change="updateGroupBy"
        @open="openDetail"
      />
      <DemoArchiveDetail :api-client="apiClient"
        v-if="selected"
        :item="selected"
        @download="downloadArtifact"
      />
      <section v-else class="archive-placeholder">
        <strong>{{ locale === 'en-US' ? 'Select a Demo archive' : '选择一个 Demo 档案' }}</strong>
        <span>{{ locale === 'en-US' ? 'Use the groups on the left to review archived Demo customers, equipment, owners, and lifecycle records.' : '左侧分类保留已归档 Demo 的客户、设备、负责人和完整生命周期记录。' }}</span>
      </section>
    </div>
  </div>
</template>

<style scoped>
.demo-archive-page{min-width:0}.demo-page-header{min-height:92px;margin-bottom:20px}.demo-page-header h1{font-size:34px;letter-spacing:-.035em}.demo-page-header p{font-size:13px}.header-actions{display:flex;align-items:center;gap:10px}.surface-switch{display:grid;grid-template-columns:repeat(3,1fr);padding:3px;background:#ece9e3;border-radius:7px}.surface-switch button{height:38px;padding:0 14px;color:#686d73;background:transparent;border:0;border-radius:5px;cursor:pointer;font-size:11px;font-weight:750;white-space:nowrap}.surface-switch button.active{color:#e86600;background:#fff;box-shadow:0 1px 5px rgba(30,34,38,.08)}.back-button{display:flex;align-items:center;gap:7px;padding:10px 13px;color:#31363c;background:#fff;border:1px solid var(--crm-line);border-radius:7px;font-size:12px;font-weight:700;cursor:pointer}.board-notice{margin:0 0 14px;padding:10px 12px;color:#8a641d;background:var(--crm-warning-soft);border:1px solid #ecd99d;border-radius:8px;font-size:12px}.workspace-panel-body>p{margin-top:0}.archive-placeholder{display:grid;min-height:340px;place-content:center;gap:9px;padding:32px;color:#7b8086;background:#fff;border:1px dashed #d7d3cc;border-radius:8px;text-align:center}.archive-placeholder strong{color:#2b3036;font-size:14px}.archive-placeholder span{max-width:420px;font-size:11px;line-height:1.7}.archive-layout{display:grid;grid-template-columns:minmax(280px,340px) minmax(0,1fr);gap:14px;align-items:start}@media(max-width:1100px){.archive-layout{grid-template-columns:1fr}.archive-layout :deep(.archive-groups){max-height:420px}}@media(max-width:760px){.demo-page-header{align-items:flex-start;flex-direction:column}.header-actions{width:100%;align-items:stretch;flex-direction:column}.surface-switch{width:100%}.back-button{justify-content:center}}
</style>
