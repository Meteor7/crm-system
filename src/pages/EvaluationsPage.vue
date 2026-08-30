<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { FlaskConical } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import type { CreateTestRunInput, EvaluationDto, EvaluationPreparationBranch, EvaluationStatus, EvaluationStatusCommand } from '@/types/crm'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { evaluationGroup } from '@/domain/evaluations'
import { useAppStore } from '@/stores/app'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import EvaluationWorkspaceNav, { type EvaluationView } from '@/features/evaluations/EvaluationWorkspaceNav.vue'
import EvaluationWorkspace from '@/features/evaluations/EvaluationWorkspace.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import TestDeadlineModal from '@/features/evaluations/TestDeadlineModal.vue'
import TestRunModal from '@/features/evaluations/TestRunModal.vue'
import TestReportUploadModal from '@/features/evaluations/TestReportUploadModal.vue'
import ModalShell from '@/design-system/ModalShell.vue'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), {
  apiClient: () => defaultApi,
})

const app = useAppStore()
const route = useRoute()
const router = useRouter()
const rows = ref<EvaluationDto[]>([])
const total = ref(0), page = ref(1)
const pageSize = ref(6)
const loading = ref(false)
const denied = ref(false)
const error = ref('')
const requestId = ref('')
const actionError = ref('')
const actionRequestId = ref('')
const meta = ref<RequestMetaState | null>(null)
const processing = ref('')
const warnings = ref<string[]>([])
const view = ref<EvaluationView>('overview')
const selectedId = ref('')
const runTarget = ref<EvaluationDto | null>(null)
const deadlineTarget = ref<EvaluationDto | null>(null)
const reportTarget = ref<EvaluationDto | null>(null)
const rejectTarget = ref<EvaluationDto | null>(null)
const rejectReason = ref('')
const rejectError = ref('')

const canWrite = computed(() => app.can('evaluation:write'))
const canReport = computed(() => app.can('evaluation:view'))
const focusedEvaluationId = computed(() => typeof route?.query?.focus === 'string' ? route.query.focus : '')
const focusedEvaluation = computed(() => rows.value.find((item) => item.id === focusedEvaluationId.value))
const activeRows = computed(() => rows.value.filter((item) => !['Accepted', 'Rejected'].includes(item.status)))

let sequence = 0

function viewForStatus(status: EvaluationStatus): EvaluationView {
  const group = evaluationGroup(status)
  if (group === 'Preparation') return 'preparation'
  if (group === 'Test Execution') return 'execution'
  if (group === 'Internal Review') return 'internal'
  if (group === 'Customer Review') return 'customer'
  return 'overview'
}

function openDetail(evaluation: EvaluationDto) {
  if (!evaluation.demoRequestId) return
  router.push({
    name: 'demo-detail',
    params: { demoId: evaluation.demoRequestId },
    query: { from: 'evaluations' },
  })
}

async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  denied.value = false
  meta.value = null
  try {
    const focusId = focusedEvaluationId.value
    const [result, focusResult] = await Promise.all([
      props.apiClient.listEvaluations({ page: page.value, pageSize: pageSize.value }),
      focusId ? props.apiClient.getEvaluation(focusId) : Promise.resolve(null),
    ])
    if (current !== sequence) return
    rows.value = result.data.items
    total.value = result.meta?.total ?? rows.value.length
    meta.value = readRequestMeta(result)
    if (focusResult && !rows.value.some((item) => item.id === focusResult.data.id)) rows.value.push(focusResult.data)
    const focus = rows.value.find((item) => item.id === focusId)
    if (focus) {
      selectedId.value = focus.id
      view.value = viewForStatus(focus.status)
    } else if (!selectedId.value && activeRows.value[0]) {
      selectedId.value = activeRows.value[0].id
    }
  } catch (reason) {
    if (current !== sequence) return
    const mapped = mapRequestError(reason)
    error.value = mapped.message
    requestId.value = mapped.requestId
    denied.value = mapped.denied
    if (mapped.denied) rows.value = []
  } finally {
    if (current === sequence) loading.value = false
  }
}
function goPage(target: number) { page.value = target; void load() }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; void load() }

watch(focusedEvaluationId, () => { void load() })

function handleWriteError(reason: unknown) {
  warnings.value = []
  const mapped = mapRequestError(reason)
  if (mapped.denied) {
    error.value = mapped.message
    requestId.value = mapped.requestId
    denied.value = true
    rows.value = []
    runTarget.value = null
    deadlineTarget.value = null
    reportTarget.value = null
    rejectTarget.value = null
    actionError.value = ''
    actionRequestId.value = ''
    return
  }
  actionError.value = mapped.message
  actionRequestId.value = mapped.requestId
}

function clearActionError() {
  actionError.value = ''
  actionRequestId.value = ''
}

async function persistStatus(id: string, command: EvaluationStatusCommand) {
  processing.value = id
  clearActionError()
  try {
    const evaluation = rows.value.find((item) => item.id === id)
    await props.apiClient.updateEvaluationStatus(id, command, evaluation?.modified)
    selectedId.value = id
    view.value = viewForStatus(command.status)
    await load()
    return true
  } catch (reason) {
    handleWriteError(reason)
    return false
  } finally {
    processing.value = ''
  }
}

async function changeStatus(id: string, status: EvaluationStatus) {
  if (status === 'Rejected') {
    rejectTarget.value = rows.value.find((item) => item.id === id) ?? null
    rejectReason.value = ''
    rejectError.value = ''
    return
  }
  await persistStatus(id, { status })
}

async function confirmReject() {
  if (!rejectTarget.value) return
  const reason = rejectReason.value.trim()
  if (!reason) {
    rejectError.value = '请填写拒绝原因。'
    return
  }
  rejectError.value = ''
  const rejected = await persistStatus(rejectTarget.value.id, { status: 'Rejected', reason })
  if (rejected) rejectTarget.value = null
  else rejectError.value = actionError.value
}

async function completePreparation(evaluation: EvaluationDto, branch: EvaluationPreparationBranch) {
  processing.value = evaluation.id
  clearActionError()
  try {
    await props.apiClient.completeEvaluationPreparation(evaluation.id, branch, evaluation.modified ?? '')
    selectedId.value = evaluation.id
    view.value = branch === 'wafer' ? 'wafer' : 'preparation'
    await load()
  } catch (reason) {
    handleWriteError(reason)
  } finally {
    processing.value = ''
  }
}

async function addRun(input: CreateTestRunInput) {
  if (!runTarget.value) return
  processing.value = runTarget.value.id
  clearActionError()
  try {
    selectedId.value = runTarget.value.id
    await props.apiClient.addEvaluationRun(runTarget.value.id, { ...input, expectedModified: runTarget.value.modified })
    runTarget.value = null
    await load()
  } catch (reason) {
    handleWriteError(reason)
  } finally {
    processing.value = ''
  }
}

async function setDeadline(input: { testRunDeadline: string }) {
  if (!deadlineTarget.value) return
  processing.value = deadlineTarget.value.id
  warnings.value = []
  clearActionError()
  try {
    selectedId.value = deadlineTarget.value.id
    const result = await props.apiClient.setEvaluationTestRunDeadline(deadlineTarget.value.id, { ...input, expectedModified: deadlineTarget.value.modified })
    deadlineTarget.value = null
    await load()
    if (!denied.value && !error.value) warnings.value = result.warnings
  } catch (reason) {
    handleWriteError(reason)
  } finally {
    processing.value = ''
  }
}

async function reportUploaded() {
  reportTarget.value = null
  await load()
}

function clearWarnings() {
  warnings.value = []
}

onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  await load()
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="DEMO TEST"
      title="Demo Test"
      description="与 Demo Request 同步管理测试准备、执行和客户评审；完成后自动进入 Demo 档案。"
    >
      <span class="header-chip"><FlaskConical :size="15" />{{ activeRows.length }} 个进行中项目</span>
    </PageHeader>

    <div v-if="focusedEvaluation" class="handoff-notice" data-demo-test-focus role="status">
      已定位 Demo Test <strong>{{ focusedEvaluation.id }}</strong>，来源 Demo Request
      <strong>{{ focusedEvaluation.demoRequestId }}</strong>。
    </div>

    <DataNotice v-if="meta?.stale" :message="meta.message" :request-id="meta.requestId" @refresh="load" />
    <div v-if="warnings.length" class="api-warning" data-api-warning role="status">
      <span v-for="warning in warnings" :key="warning">{{ warning }}</span>
    </div>
    <div v-if="actionError" class="api-error" data-api-error role="alert">
      <span>{{ actionError }}</span>
      <small v-if="actionRequestId">Request ID · {{ actionRequestId }}</small>
    </div>

    <EvaluationWorkspaceNav v-model="view" />

    <DataState v-if="loading && !activeRows.length" type="loading" />
    <DataState v-else-if="denied" type="denied" :message="error" :request-id="requestId" />
    <DataState v-else-if="error" type="error" :message="error" :request-id="requestId" @retry="load" />
    <DataState
      v-else-if="!activeRows.length"
      type="empty"
      title="没有进行中的 Demo Test"
      message="新项目会在 Boss 批准 Demo Request 后自动进入这里。"
    />
    <EvaluationWorkspace
      v-else
      :view="view"
      :evaluations="activeRows"
      :selected-id="selectedId"
      :processing="processing"
      :can-write="canWrite"
      :can-report="canReport"
      @select="selectedId = $event"
      @open-detail="openDetail"
      @status="changeStatus"
      @prepare="completePreparation"
      @deadline="deadlineTarget = $event"
      @run="runTarget = $event"
      @report="reportTarget = $event"
      @customer-change="clearWarnings"
    />
    <PaginationControls v-if="!denied && !error && total > pageSize" :page="page" :page-size="pageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />

    <TestDeadlineModal
      v-if="deadlineTarget"
      :evaluation="deadlineTarget"
      :busy="Boolean(processing)"
      @close="deadlineTarget = null"
      @submit="setDeadline"
    />
    <TestRunModal
      v-if="runTarget"
      :evaluation="runTarget"
      :busy="Boolean(processing)"
      @close="runTarget = null"
      @submit="addRun"
    />
    <TestReportUploadModal
      v-if="reportTarget"
      :evaluation="reportTarget"
      :api-client="apiClient"
      @close="reportTarget = null"
      @uploaded="reportUploaded"
    />
    <ModalShell
      v-if="rejectTarget"
      title="Reject Demo"
      eyebrow="DEMO TEST"
      submit-label="确认拒绝"
      :busy="processing === rejectTarget.id"
      :submit-disabled="!rejectReason.trim()"
      @close="rejectTarget = null"
      @submit="confirmReject"
    >
      <p class="reject-warning">拒绝后该 Demo Test 将进入档案。请确认项目和原因，避免误操作。</p>
      <label class="reject-reason-field">
        <span>拒绝原因</span>
        <textarea v-model="rejectReason" aria-label="Demo 拒绝原因" maxlength="1000" required autofocus />
      </label>
      <p v-if="rejectError" class="reject-error" role="alert">{{ rejectError }}</p>
    </ModalShell>
  </div>
</template>

<style scoped>
.header-chip{display:flex;align-items:center;gap:6px;padding:9px 11px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:9px;font-size:9px;font-weight:700}
.handoff-notice,.api-warning,.api-error{margin-bottom:12px;padding:9px 12px;border-radius:10px;font-size:10px}.handoff-notice{color:#315f4b;background:#eaf5ef;border:1px solid #bddccb}.api-warning,.api-error{display:grid;gap:4px}.api-warning{color:#7d611f;background:var(--crm-warning-soft);border:1px solid #ecd99d}.api-error{color:#9f2d2d;background:#fff1f0;border:1px solid #efb4af}.api-error small{color:inherit;opacity:.75}
.reject-warning{margin:0 0 14px;padding:10px;color:#8b3434;background:var(--crm-danger-soft);border:1px solid #efb4af;border-radius:8px;font-size:10px;line-height:1.6}.reject-reason-field{display:grid;gap:7px}.reject-reason-field span{color:var(--crm-text-muted);font-size:10px;font-weight:800}.reject-reason-field textarea{min-height:120px;resize:vertical;padding:10px;border:1px solid var(--crm-line-strong);border-radius:8px;font:inherit;line-height:1.5}.reject-reason-field textarea:focus{border-color:var(--crm-danger);outline:0;box-shadow:0 0 0 3px rgba(182,69,69,.12)}.reject-error{margin:10px 0 0;color:var(--crm-danger);font-size:10px}
</style>
