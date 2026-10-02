<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { FlaskConical } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import { api as defaultApi, CrmApiError, type CrmApi } from '@/api'
import type { CreateTestRunInput, EvaluationDto, EvaluationPreparationBranch, EvaluationStatus, EvaluationStatusCommand, TestRunDto } from '@/types/crm'
import { mapRequestError, readRequestMeta, type RequestMetaState } from '@/api/request-state'
import { canTerminateEvaluation, evaluationGroup } from '@/domain/evaluations'
import { useAppStore } from '@/stores/app'
import PageHeader from '@/design-system/PageHeader.vue'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import EvaluationWorkspaceNav, { type EvaluationView } from '@/features/evaluations/EvaluationWorkspaceNav.vue'
import EvaluationWorkspace from '@/features/evaluations/EvaluationWorkspace.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import TestDeadlineModal from '@/features/evaluations/TestDeadlineModal.vue'
import TestRunModal from '@/features/evaluations/TestRunModal.vue'
import TestRunActionModal from '@/features/evaluations/TestRunActionModal.vue'
import { canManageTestRun, type TestRunAction } from '@/features/evaluations/test-run-actions'
import TestReportUploadModal from '@/features/evaluations/TestReportUploadModal.vue'
import CustomerReportUploadModal from '@/features/evaluations/CustomerReportUploadModal.vue'
import CustomerCommentModal from '@/features/evaluations/CustomerCommentModal.vue'
import TerminateEvaluationModal from '@/features/evaluations/TerminateEvaluationModal.vue'
import { useI18n, useLocaleMessage, localeMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), {
  apiClient: () => defaultApi,
})

const app = useAppStore()
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const rows = ref<EvaluationDto[]>([])
const total = ref(0), page = ref(1)
const pageSize = ref(6)
const loading = ref(false)
const denied = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const actionError = useLocaleMessage()
const actionRequestId = ref('')
// The Terminate dialog's own refusal, so another action's failure never lands inside it.
const terminateError = useLocaleMessage()
const terminateRequestId = ref('')
const meta = ref<RequestMetaState | null>(null)
const processing = ref('')
const warnings = ref<string[]>([])
const view = ref<EvaluationView>('overview')
const selectedId = ref('')
const runTarget = ref<EvaluationDto | null>(null)
const runActionTarget = ref<{ evaluation: EvaluationDto; run: TestRunDto; action: TestRunAction } | null>(null)
const runActionError = useLocaleMessage()
const runActionRequestId = ref('')
const runActionConflict = ref(false)
const runActionKey = ref(0)
const deadlineTarget = ref<EvaluationDto | null>(null)
const terminateTarget = ref<EvaluationDto | null>(null)
const reportTarget = ref<EvaluationDto | null>(null)
const customerReportTarget = ref<EvaluationDto | null>(null)
const commentTarget = ref<EvaluationDto | null>(null)
const commentError = useLocaleMessage()
const commentOutcome = ref<'archive' | 'retest'>('archive')

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
    error.value = mapped.localizedMessage ?? mapped.message
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

function handleWriteError(reason: unknown, into: 'page' | 'terminate-dialog' = 'page') {
  warnings.value = []
  const mapped = mapRequestError(reason)
  if (mapped.denied) {
    error.value = mapped.localizedMessage ?? mapped.message
    requestId.value = mapped.requestId
    denied.value = true
    rows.value = []
    runTarget.value = null
    runActionTarget.value = null
    deadlineTarget.value = null
    terminateTarget.value = null
    reportTarget.value = null
    customerReportTarget.value = null
    commentTarget.value = null
    actionError.value = ''
    actionRequestId.value = ''
    clearTerminateError()
    return
  }
  if (into === 'terminate-dialog') {
    terminateError.value = mapped.localizedMessage ?? mapped.message
    terminateRequestId.value = mapped.requestId
    return
  }
  actionError.value = mapped.localizedMessage ?? mapped.message
  actionRequestId.value = mapped.requestId
}

function clearActionError() {
  actionError.value = ''
  actionRequestId.value = ''
}

function clearTerminateError() {
  terminateError.value = ''
  terminateRequestId.value = ''
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
  const evaluation = rows.value.find((item) => item.id === id) ?? null
  // Leaving Customer Review always records a comment first, whether it archives or retests.
  if (evaluation?.status === 'Customer Review') {
    commentError.value = ''
    // `submitCustomerComment` maps retest back to Testing, so preselect the
    // radio the user already chose instead of always defaulting to archive.
    commentOutcome.value = status === 'Testing' ? 'retest' : 'archive'
    commentTarget.value = evaluation
    return
  }
  await persistStatus(id, { status })
}

function openRetest(evaluation: EvaluationDto) {
  commentError.value = ''
  commentOutcome.value = 'retest'
  commentTarget.value = evaluation
}

async function submitCustomerComment(payload: { comment: string; outcome: 'archive' | 'retest' }) {
  if (!commentTarget.value) return
  commentError.value = ''
  const status: EvaluationStatus = payload.outcome === 'retest' ? 'Testing' : 'Accepted'
  const done = await persistStatus(commentTarget.value.id, { status, customerComment: payload.comment })
  if (done) commentTarget.value = null
  else commentError.value = actionError.value
}

function customerReportUploaded() {
  customerReportTarget.value = null
  void load()
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

function openRunAction(evaluation: EvaluationDto, run: TestRunDto, action: TestRunAction) {
  if (!canWrite.value || processing.value || !canManageTestRun(evaluation, run)) return
  clearActionError()
  runActionError.value = ''
  runActionRequestId.value = ''
  runActionConflict.value = false
  runActionKey.value++
  runActionTarget.value = { evaluation, run, action }
}

function closeRunAction() {
  if (processing.value) return
  runActionTarget.value = null
}

function reportRunActionError(reason: unknown) {
  const mapped = mapRequestError(reason)
  if (mapped.denied) {
    handleWriteError(reason)
    return
  }
  runActionError.value = mapped.localizedMessage ?? mapped.message
  runActionRequestId.value = mapped.requestId
  runActionConflict.value = reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT'
}

async function mutateRun(input: CreateTestRunInput | { reason: string }) {
  const target = runActionTarget.value
  if (!target || !canWrite.value || processing.value || runActionConflict.value) return
  if (!canManageTestRun(target.evaluation, target.run)) return
  if (!target.evaluation.modified) {
    runActionError.value = localeMessage('Reload the latest record before saving.', '请先重新载入最新记录再保存。')
    runActionConflict.value = true
    return
  }
  const identity = app.identityRevision
  processing.value = target.evaluation.id
  runActionError.value = ''
  runActionRequestId.value = ''
  try {
    const expectedModified = target.evaluation.modified
    const result = 'reason' in input
      ? await props.apiClient.cancelEvaluationRun(target.evaluation.id, target.run.id, { ...input, expectedModified })
      : await props.apiClient.updateEvaluationRun(target.evaluation.id, target.run.id, { ...input, expectedModified })
    if (identity !== app.identityRevision || target !== runActionTarget.value) return
    runActionTarget.value = null
    rows.value = rows.value.map(row => row.id === result.data.id ? result.data : row)
    selectedId.value = result.data.id
    await load()
  } catch (reason) {
    if (identity === app.identityRevision && target === runActionTarget.value) reportRunActionError(reason)
  } finally {
    if (identity === app.identityRevision) processing.value = ''
  }
}

async function reloadRunAction() {
  const target = runActionTarget.value
  if (!target || processing.value || !canWrite.value) return
  const identity = app.identityRevision
  processing.value = target.evaluation.id
  try {
    const { data } = await props.apiClient.getEvaluation(target.evaluation.id)
    if (identity !== app.identityRevision || target !== runActionTarget.value) return
    rows.value = rows.value.map(row => row.id === data.id ? data : row)
    const run = data.runs.find(row => row.id === target.run.id)
    if (!run || !canManageTestRun(data, run)) {
      runActionTarget.value = null
      actionError.value = localeMessage('This test run can no longer be changed. The latest record is shown.', '该测试已不能修改，页面已显示最新记录。')
      return
    }
    runActionError.value = ''
    runActionRequestId.value = ''
    runActionConflict.value = false
    runActionKey.value++
    runActionTarget.value = { ...target, evaluation: data, run }
  } catch (reason) {
    if (identity === app.identityRevision && target === runActionTarget.value) {
      reportRunActionError(reason)
      // A failed reload must not allow the stale version to be resubmitted.
      runActionConflict.value = true
    }
  } finally {
    if (identity === app.identityRevision) processing.value = ''
  }
}

watch(() => [app.identityRevision, canWrite.value], () => {
  if (runActionTarget.value) {
    runActionTarget.value = null
    runActionError.value = ''
    processing.value = ''
  }
})

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

function openTerminate(evaluation: EvaluationDto) {
  clearActionError()
  clearTerminateError()
  terminateTarget.value = evaluation
}

function closeTerminate() {
  // The dialog stays until its own request answers, so that answer cannot land on another Demo's dialog.
  if (terminateTarget.value && processing.value === terminateTarget.value.id) return
  terminateTarget.value = null
  clearTerminateError()
}

async function terminate(input: { reason: string }) {
  const target = terminateTarget.value
  if (!target) return
  processing.value = target.id
  warnings.value = []
  clearActionError()
  clearTerminateError()
  try {
    selectedId.value = target.id
    // The terminated Demo leaves the in-progress list on reload; its record stays in the Demo archive.
    await props.apiClient.terminateEvaluation(target.id, input.reason, target.modified ?? '')
    terminateTarget.value = null
    await load()
  } catch (reason) {
    handleWriteError(reason, 'terminate-dialog')
    if (reason instanceof CrmApiError && (reason.code === 'VERSION_CONFLICT' || reason.code === 'INVALID_TRANSITION')) {
      await reloadTerminateTarget(target, reason)
    }
  } finally {
    processing.value = ''
  }
}

// Retrying with a refused version can never succeed: reload and point the open dialog, which
// keeps the typed reason, at the latest record. Close it once the Demo is no longer in progress.
async function reloadTerminateTarget(target: EvaluationDto, refusal: unknown) {
  await load()
  if (terminateTarget.value !== target) return
  if (denied.value || error.value) {
    terminateTarget.value = null
    // The dialog and the typed reason are gone: say that the termination did not go through.
    if (!denied.value) handleWriteError(refusal)
    return
  }
  // The list is ordered by last change, so the changed Demo may now sit on another page: read it directly.
  let latest: EvaluationDto
  try {
    latest = (await props.apiClient.getEvaluation(target.id)).data
  } catch (reason) {
    if (terminateTarget.value !== target) return
    terminateTarget.value = null
    handleWriteError(reason)
    return
  }
  if (terminateTarget.value !== target) return
  rows.value = rows.value.map((row) => row.id === latest.id ? latest : row)
  if (canTerminateEvaluation(latest.status)) {
    terminateTarget.value = latest
    return
  }
  terminateTarget.value = null
  actionError.value = localeMessage('This Demo Test is no longer in progress. The latest record is shown.', '该 Demo Test 已不在进行中，页面已显示最新记录。')
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
      :eyebrow="t('evaluations.pageEyebrow')"
      :title="t('evaluations.pageTitle')"
      :description="t('evaluations.pageDescription')"
    >
      <span class="header-chip"><FlaskConical :size="15" />{{ t('evaluations.inProgress', { count: activeRows.length }) }}</span>
    </PageHeader>

    <div v-if="focusedEvaluation" class="handoff-notice" data-demo-test-focus role="status">
      {{ locale === 'en-US' ? 'Focused Demo Test' : '已定位 Demo Test' }} <strong>{{ focusedEvaluation.id }}</strong>{{ locale === 'en-US' ? ', from Demo Request' : '，来源 Demo Request' }}
      <strong>{{ focusedEvaluation.demoRequestId }}</strong>{{ locale === 'en-US' ? '.' : '。' }}
    </div>

    <DataNotice v-if="meta?.stale" :message="meta.localizedMessage ?? meta.message" :request-id="meta.requestId" @refresh="load" />
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
      :title="t('evaluations.emptyTitle')"
      :message="t('evaluations.emptyMessage')"
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
      @manage-run="openRunAction"
      @report="reportTarget = $event"
      @customer-report="customerReportTarget = $event"
      @retest="openRetest"
      @terminate="openTerminate"
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
    <TerminateEvaluationModal
      v-if="terminateTarget"
      :evaluation="terminateTarget"
      :busy="Boolean(processing)"
      :submit-error="terminateError"
      :request-id="terminateRequestId"
      @close="closeTerminate"
      @submit="terminate"
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
    <TestRunActionModal
      v-if="runActionTarget"
      :key="runActionKey"
      :run="runActionTarget.run"
      :action="runActionTarget.action"
      :busy="Boolean(processing)"
      :submit-error="runActionError"
      :request-id="runActionRequestId"
      :conflict="runActionConflict"
      @close="closeRunAction"
      @save="mutateRun"
      @cancel-run="reason => mutateRun({ reason })"
      @reload="reloadRunAction"
    />
    <CustomerReportUploadModal
      v-if="customerReportTarget"
      :evaluation="customerReportTarget"
      :api-client="apiClient"
      @close="customerReportTarget = null"
      @uploaded="customerReportUploaded"
    />
    <CustomerCommentModal
      v-if="commentTarget"
      :evaluation="commentTarget"
      :busy="processing === commentTarget.id"
      :submit-error="commentError"
      :default-outcome="commentOutcome"
      @close="commentTarget = null"
      @submit="submitCustomerComment"
    />
  </div>
</template>

<style scoped>
.header-chip{display:flex;align-items:center;gap:6px;padding:9px 11px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:9px;font-size:9px;font-weight:700}
.handoff-notice,.api-warning,.api-error{margin-bottom:12px;padding:9px 12px;border-radius:10px;font-size:10px}.handoff-notice{color:#315f4b;background:#eaf5ef;border:1px solid #bddccb}.api-warning,.api-error{display:grid;gap:4px}.api-warning{color:#7d611f;background:var(--crm-warning-soft);border:1px solid #ecd99d}.api-error{color:#9f2d2d;background:#fff1f0;border:1px solid #efb4af}.api-error small{color:inherit;opacity:.75}

</style>
