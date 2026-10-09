<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, ref, watch } from 'vue'
import { CalendarClock, ExternalLink, FileText, FlaskConical, History, OctagonX, Plus, UserRoundCog } from '@lucide/vue'
import type { EvaluationDto, EvaluationPreparationBranch, EvaluationStatus, TestRunDto, Tone } from '@/types/crm'
import TestRunList from './TestRunList.vue'
import type { TestRunAction } from './test-run-actions'
import { canRetestEvaluation, canTerminateEvaluation, evaluationGroup, evaluationPreparationStatus, evaluationStatusOptions, hasCompletedTestRun, isEvaluationPreparationComplete, isTerminatedDemo } from '@/domain/evaluations'
import { formatDisplayDate } from '@/domain/time'
import StatusBadge from '@/design-system/StatusBadge.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import { usePagedSelection } from '@/features/shared/paged-selection'
import type { EvaluationView } from './EvaluationWorkspaceNav.vue'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{
  view: EvaluationView
  evaluations: EvaluationDto[]
  selectedId?: string
  processing?: string
  canWrite?: boolean
  canCustomerReview?: boolean
  canReport?: boolean
}>(), {
  selectedId: '',
  processing: '',
  canWrite: false,
  canCustomerReview: false,
  canReport: false,
})
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const statusLabel: Record<string, string> = {
  Requested: '已申请', 'Scope Confirmed': '范围已确认', 'Sample Received': '样品已收到', Scheduled: '已排期',
  Testing: '测试中', Analysis: '分析中', 'Internal Review': '内部评审', 'Customer Review': '客户评审', Accepted: '已接受', Rejected: '已拒绝',
}
const preparationLabel: Record<string, string> = { Pending: '待完成', Completed: '已完成' }
const eventLabel: Record<string, string> = { Created: '已创建', Status: '状态变更', Preparation: '准备完成', 'Test Run': '测试运行', Deadline: '截止日期', Report: '测试报告' }

const emit = defineEmits<{
  select: [id: string]
  'open-detail': [evaluation: EvaluationDto]
  status: [id: string, status: EvaluationStatus]
  prepare: [evaluation: EvaluationDto, branch: EvaluationPreparationBranch]
  deadline: [evaluation: EvaluationDto]
  run: [evaluation: EvaluationDto]
  'manage-run': [evaluation: EvaluationDto, run: TestRunDto, action: TestRunAction]
  report: [evaluation: EvaluationDto]
  'customer-report': [evaluation: EvaluationDto]
  retest: [evaluation: EvaluationDto]
  terminate: [evaluation: EvaluationDto]
  'customer-change': []
}>()

const accountId = ref('All')
const accounts = computed(() => [...new Map(props.evaluations.map((item) => [item.accountId, item.accountName])).entries()])
const stageRows = computed(() => {
  const group = props.view === 'wafer' || props.view === 'preparation'
    ? 'Preparation'
    : props.view === 'execution'
      ? 'Test Execution'
      : props.view === 'internal'
        ? 'Internal Review'
        : props.view === 'customer'
          ? 'Customer Review'
          : ''
  return group ? props.evaluations.filter((item) => evaluationGroup(item.status) === group) : props.evaluations
})
const scopedRows = computed(() => {
  return stageRows.value.filter((item) => accountId.value === 'All' || item.accountId === accountId.value)
})
// `evaluations` is everything in progress. A view is paged here, after it is filtered, so every page is full and
// the count is the view's own.
const { page, pageSize, openingPageSize, pagedRows, selected, paged, turnTo } = usePagedSelection({
  rows: scopedRows,
  selectedId: () => props.selectedId,
  narrowedBy: () => `${props.view}\n${accountId.value}`,
  pageSize: 6,
  select: (id) => emit('select', id),
})
const nextStatus = computed(() => selected.value
  ? evaluationStatusOptions(selected.value.status).find((status) => status !== selected.value!.status && status !== 'Rejected')
  : undefined)
const selectedIsPreparation = computed(() => selected.value && evaluationGroup(selected.value.status) === 'Preparation')
const preparationComplete = computed(() => selected.value ? isEvaluationPreparationComplete(selected.value) : false)
const reportsMissing = computed(() => !selected.value?.internalReportArtifactId || !selected.value?.externalReportArtifactId)
const runMissing = computed(() => !!selected.value && !hasCompletedTestRun(selected.value))
const internalReviewBlocked = computed(() => selected.value?.status === 'Testing'
  && (reportsMissing.value || runMissing.value))
// Say which half of the gate is still open. After a retest the card keeps showing the
// earlier rounds' completed runs, so "complete a Test Run" alone reads as already done.
const internalReviewHint = computed(() => {
  const round = selected.value?.testRound ?? 1
  if (reportsMissing.value && runMissing.value) {
    return copy(`Upload both Test Reports and complete a Test Run in round ${round} first.`, `请先上传 Internal 和 External Test Report，并完成第 ${round} 轮 Test Run。`)
  }
  if (runMissing.value) {
    return copy(`Complete a Test Run in round ${round} first. Runs from earlier rounds do not count.`, `请先完成第 ${round} 轮 Test Run，之前轮次的 Test Run 不计入。`)
  }
  return copy('Upload both Test Reports first.', '请先上传 Internal 和 External Test Report。')
})
const inCustomerReview = computed(() => selected.value?.status === 'Customer Review'
  && (props.view === 'overview' || props.view === 'customer'))
const roundLabel = (round: number) => copy(`Round ${round}`, `第 ${round} 轮`)
// Customer Review closes with a comment (archive or retest); a reviewer without
// evaluation:write may take that one step, the other transitions stay with canWrite.
const canCloseCustomerReview = computed(() => props.canCustomerReview && selected.value?.status === 'Customer Review')
const showAdvance = computed(() => {
  if (!selected.value || !nextStatus.value) return false
  if (selected.value.status === 'Scheduled') return preparationComplete.value
  return ['Testing', 'Analysis', 'Internal Review', 'Customer Review'].includes(selected.value.status)
})
const advanceLabel = computed(() => {
  if (!nextStatus.value) return ''
  const labels = locale.value === 'en-US'
    ? { Testing: 'Enter Test Execution', 'Internal Review': 'Complete Test Execution', 'Customer Review': 'Submit Customer Review', Accepted: 'Customer Comment' }
    : { Testing: '进入 Test Execution', 'Internal Review': '完成 Test Execution', 'Customer Review': '提交 Customer Review', Accepted: 'Customer Comment' }
  return labels[nextStatus.value as keyof typeof labels] ?? (locale.value === 'en-US' ? `Advance to ${nextStatus.value}` : `推进至 ${nextStatus.value}`)
})
const viewLabel = computed(() => (locale.value === 'en-US' ? ({
  overview: 'All Demo Tests', wafer: 'Wafer Preparation', preparation: 'Test Preparation', execution: 'Test Execution', internal: 'Internal Review', customer: 'Customer Review',
}[props.view]) : ({
  overview: '全部 Demo Test', wafer: 'Wafer Preparation', preparation: 'Test Preparation', execution: 'Test Execution', internal: 'Internal Review', customer: 'Customer Review',
}[props.view])))
function displayStage(evaluation: EvaluationDto) {
  // A historical Rejected record without a reason keeps its original label.
  if (isTerminatedDemo(evaluation)) return t('evaluations.terminated')
  if (props.view === 'wafer') return `${copy('Wafer Preparation', 'Wafer 准备')} · ${copy(evaluationPreparationStatus(evaluation, 'wafer'), preparationLabel[evaluationPreparationStatus(evaluation, 'wafer')] || evaluationPreparationStatus(evaluation, 'wafer'))}`
  if (props.view === 'preparation') return `${copy('Test Preparation', '测试准备')} · ${copy(evaluationPreparationStatus(evaluation, 'test'), preparationLabel[evaluationPreparationStatus(evaluation, 'test')] || evaluationPreparationStatus(evaluation, 'test'))}`
  return copy(evaluation.status, statusLabel[evaluation.status] || evaluation.status)
}
function reportStatusLabel(status: EvaluationDto['reportStatus']) {
  return copy(status, status === 'Ready' ? '已就绪' : '未就绪')
}
function historyEventLabel(type: string) {
  return copy(type, eventLabel[type] || type)
}
const tone = (status: EvaluationStatus): Tone => status === 'Accepted'
  ? 'positive'
  : status === 'Rejected'
    ? 'danger'
    : ['Internal Review', 'Customer Review'].includes(status)
      ? 'warning'
      : 'info'

watch(accountId, () => emit('customer-change'))
</script>

<template>
  <section class="evaluation-workspace" :data-evaluation-workspace="view">
    <div class="workspace-main">
      <div class="toolbar">
        <label>
          {{ locale === 'en-US' ? 'Account' : '客户' }}
          <select v-model="accountId" :aria-label="locale === 'en-US' ? 'Evaluation account' : 'Evaluation 客户'">
            <option value="All">{{ locale === 'en-US' ? 'All accounts' : '全部客户' }}</option>
            <option v-for="account in accounts" :key="account[0]" :value="account[0]">{{ account[1] }}</option>
          </select>
        </label>
        <span class="row-count">{{ viewLabel }} · {{ scopedRows.length }}</span>
      </div>

      <div class="evaluation-table-wrap">
        <table class="evaluation-table" data-evaluation-table>
          <thead>
            <tr>
              <th>{{ locale === 'en-US' ? 'Test / Project' : 'Test / 项目' }}</th>
              <th>{{ locale === 'en-US' ? 'Account' : '客户' }}</th>
              <th>{{ locale === 'en-US' ? 'Source request' : '来源 Request' }}</th>
              <th>Engineer</th>
              <th>{{ locale === 'en-US' ? 'Stage' : '阶段' }}</th>
              <th>{{ locale === 'en-US' ? 'Planned completion' : '计划完成' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in pagedRows"
              :key="item.id"
              :class="{ selected: selected?.id === item.id }"
              :data-evaluation="item.id"
              @click="emit('select', item.id)"
            >
              <td :data-label="locale === 'en-US' ? 'Test / Project' : 'Test / 项目'">
                <button
                  class="evaluation-link record-name-link"
                  type="button"
                  :data-open-demo-detail="item.id"
                  @click.stop="emit('open-detail', item)"
                >
                  <b>{{ item.id }}</b>
                  <strong>{{ item.title }}</strong>
                </button>
              </td>
              <td :data-label="locale === 'en-US' ? 'Account' : '客户'">{{ item.accountName }}</td>
              <td :data-label="locale === 'en-US' ? 'Source request' : '来源 Request'">{{ item.demoRequestId || '—' }}</td>
              <td data-label="Engineer">{{ personnelDisplayName(item.owner) }}</td>
              <td :data-label="locale === 'en-US' ? 'Stage' : '阶段'"><StatusBadge :label="displayStage(item)" :tone="tone(item.status)" /></td>
              <td :data-label="locale === 'en-US' ? 'Planned completion' : '计划完成'">{{ item.plannedEnd }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!scopedRows.length" class="empty-copy">{{ locale === 'en-US' ? 'No Demo Tests in this view' : '当前分类暂无 Demo Test' }}</p>
        <PaginationControls v-if="paged" :page="page" :page-size="pageSize" :opening-page-size="openingPageSize" :total="scopedRows.length" @change="turnTo" @page-size-change="pageSize = $event" />
      </div>
      <TestRunList v-if="selected" :evaluation="selected" :can-write="canWrite" :busy="Boolean(processing)" @action="(run, action) => emit('manage-run', selected!, run, action)" />
    </div>

    <aside class="action-panel" data-evaluation-actions>
      <template v-if="selected">
        <span class="panel-kicker"><UserRoundCog :size="15" />{{ locale === 'en-US' ? 'Owner actions' : '相关人员操作' }}</span>
        <b>{{ selected.id }}</b>
        <h2>{{ selected.title }}</h2>
        <p>{{ selected.accountName }}</p>

        <dl>
          <div><dt>Engineer</dt><dd>{{ personnelDisplayName(selected.owner) }}</dd></div>
          <div><dt>{{ locale === 'en-US' ? 'Source request' : '来源 Request' }}</dt><dd>{{ selected.demoRequestId || '—' }}</dd></div>
          <div><dt>{{ locale === 'en-US' ? 'Current stage' : '当前阶段' }}</dt><dd>{{ displayStage(selected) }}</dd></div>
          <div v-if="isTerminatedDemo(selected)" data-termination-reason><dt>{{ t('evaluations.terminateReason') }}</dt><dd>{{ selected.terminationReason }}</dd></div>
        </dl>

        <button
          class="secondary-button"
          type="button"
          :data-open-demo-detail="`${selected.id}-panel`"
          @click="emit('open-detail', selected)"
        >
          <ExternalLink :size="14" />{{ locale === 'en-US' ? 'View details' : '查看详细信息' }}
        </button>

        <section
          v-if="selected.status === 'Testing' && (view === 'overview' || view === 'execution')"
          class="test-report-card"
          data-test-report-card
        >
           <header><FileText :size="15" /><strong>{{ copy('Test Report', '测试报告') }}</strong><span>{{ reportStatusLabel(selected.reportStatus) }}</span></header>
           <div v-if="selected.internalReportArtifact" class="report-file"><strong>{{ copy('Internal', '内部') }}</strong><b>{{ selected.internalReportArtifact.fileName }}</b><small>{{ roundLabel(selected.internalReportArtifact.round ?? selected.testRound) }} · v{{ selected.internalReportArtifact.version }} · {{ personnelDisplayName(selected.internalReportArtifact.createdBy) }} · {{ formatDisplayDate(selected.internalReportArtifact.createdAt) }}</small></div>
           <div v-if="selected.externalReportArtifact" class="report-file"><strong>{{ copy('External', '外部') }}</strong><b>{{ selected.externalReportArtifact.fileName }}</b><small>{{ roundLabel(selected.externalReportArtifact.round ?? selected.testRound) }} · v{{ selected.externalReportArtifact.version }} · {{ personnelDisplayName(selected.externalReportArtifact.createdBy) }} · {{ formatDisplayDate(selected.externalReportArtifact.createdAt) }}</small></div>
          <p v-if="!selected.internalReportArtifact || !selected.externalReportArtifact">{{ locale === 'en-US' ? 'Upload both Internal and External reports before entering Internal Review.' : 'Internal 和 External 两份报告均上传后才可进入 Internal Review。' }}</p>
          <button
            v-if="canWrite"
            type="button"
            :class="selected.reportStatus === 'Ready' ? 'secondary-button' : 'primary-button'"
            :data-report-action="selected.id"
            :disabled="processing === selected.id"
            @click="emit('report', selected)"
          >
            <FileText :size="14" />{{ selected.reportStatus === 'Ready' ? (locale === 'en-US' ? 'Upload new version' : '上传新版本') : (locale === 'en-US' ? 'Upload both Test Reports' : '上传两份 Test Report') }}
          </button>
        </section>

        <button
          v-if="canWrite && selectedIsPreparation && evaluationPreparationStatus(selected, 'wafer') === 'Pending' && (view === 'overview' || view === 'wafer')"
          type="button"
          class="primary-button"
          data-complete-preparation="wafer"
          :disabled="processing === selected.id"
          @click="emit('prepare', selected, 'wafer')"
        >{{ locale === 'en-US' ? 'Complete Wafer Preparation' : '完成 Wafer Preparation' }}</button>
        <button
          v-if="canWrite && selectedIsPreparation && evaluationPreparationStatus(selected, 'test') === 'Pending' && (view === 'overview' || view === 'preparation')"
          type="button"
          class="primary-button"
          data-complete-preparation="test"
          :disabled="processing === selected.id"
          @click="emit('prepare', selected, 'test')"
        >{{ locale === 'en-US' ? 'Complete Test Preparation' : '完成 Test Preparation' }}</button>

        <button
          v-if="canWrite && ((selectedIsPreparation && (view === 'overview' || view === 'preparation')) || (selected.status === 'Testing' && (view === 'overview' || view === 'execution')))"
          type="button"
          class="primary-button"
          :data-set-ddl="selected.id"
          :disabled="processing === selected.id"
          @click="emit('deadline', selected)"
        >
          <CalendarClock :size="14" />{{ locale === 'en-US' ? 'Set Test Run DDL' : '设置 Test Run DDL' }}
        </button>
        <button
          v-if="canWrite && selected.status === 'Testing' && (view === 'overview' || view === 'execution')"
          type="button"
          class="secondary-button"
          data-add-test-run
          :data-add-run="selected.id"
          :disabled="processing === selected.id"
          @click="emit('run', selected)"
        >
          <Plus :size="14" />{{ locale === 'en-US' ? 'New Test Run' : '新增 Test Run' }}
        </button>
        <button
          v-if="(canWrite || canCloseCustomerReview) && showAdvance"
          type="button"
          class="primary-button"
          :data-advance-status="nextStatus"
          :disabled="processing === selected.id || internalReviewBlocked"
          @click="emit('status', selected.id, nextStatus!)"
        >{{ advanceLabel }}</button>
        <p v-if="canWrite && internalReviewBlocked" class="action-hint" data-test-run-review-gate>{{ internalReviewHint }}</p>
        <section v-if="inCustomerReview" class="customer-report-card" data-customer-report-card>
          <header><FileText :size="15" /><strong>{{ copy('Customer Report', 'Customer 报告') }}</strong><span>{{ roundLabel(selected.testRound) }}</span></header>
          <div v-if="selected.customerReportArtifact" class="report-file"><b>{{ selected.customerReportArtifact.fileName }}</b><small>v{{ selected.customerReportArtifact.version }} · {{ personnelDisplayName(selected.customerReportArtifact.createdBy) }} · {{ formatDisplayDate(selected.customerReportArtifact.createdAt) }}</small></div>
          <p v-else>{{ copy('No customer report uploaded for this round yet.', '本轮尚未上传 Customer 报告。') }}</p>
          <button
            v-if="canCloseCustomerReview"
            type="button"
            class="secondary-button"
            :data-customer-report-action="selected.id"
            :disabled="processing === selected.id"
            @click="emit('customer-report', selected)"
          >
            <FileText :size="14" />{{ copy('Upload Customer Report', '上传 Customer Report') }}
          </button>
        </section>
        <button
          v-if="canCloseCustomerReview && inCustomerReview && canRetestEvaluation(selected.status)"
          type="button"
          class="secondary-button"
          :data-retest-evaluation="selected.id"
          :disabled="processing === selected.id"
          @click="emit('retest', selected)"
        >
          <History :size="14" />{{ copy('Retest', '申请 Retest') }}
        </button>
        <button
          v-if="canWrite && canTerminateEvaluation(selected.status)"
          type="button"
          class="danger-button"
          :data-testid="`terminate-evaluation-${selected.id}`"
          :disabled="processing === selected.id"
          @click="emit('terminate', selected)"
        >
          <OctagonX :size="14" />{{ t('evaluations.terminateTitle') }}
        </button>
        <div class="owner-note">
          <FlaskConical :size="14" />
          <span>{{ locale === 'en-US' ? 'Only the current owner can act here. Open the detail view for full test information.' : '操作区域只保留当前负责人可执行动作；详细测试信息请进入内页。' }}</span>
        </div>
        <section v-if="selected.history?.length" class="evaluation-history" :aria-label="locale === 'en-US' ? 'Evaluation history' : '评估历史记录'">
          <header><History :size="14" /><strong>{{ locale === 'en-US' ? 'Tracking history' : '操作历史' }}</strong></header>
          <ol>
            <li v-for="event in selected.history.slice(0, 6)" :key="event.id">
               <span>{{ historyEventLabel(event.eventType) }}</span>
              <strong>{{ event.summary }}</strong>
              <small>{{ personnelDisplayName(event.actor) }} · {{ formatDisplayDate(event.at) }}</small>
            </li>
          </ol>
        </section>
      </template>
      <p v-else>{{ locale === 'en-US' ? 'Select a Demo Test first.' : '请先选择一条 Demo Test。' }}</p>
    </aside>
  </section>
</template>

<style scoped>
.evaluation-workspace{display:grid;grid-template-columns:minmax(0,1fr) 248px;gap:14px;align-items:start}.workspace-main{min-width:0;display:grid;gap:12px}.toolbar{display:flex;align-items:center;gap:10px;padding:11px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.toolbar-search{display:flex;min-width:240px;flex:1;align-items:center;gap:7px;height:36px;padding:0 11px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.toolbar-search input{min-width:0;flex:1;background:transparent;border:0;outline:0;font:inherit;font-size:12px}.toolbar label{display:flex;align-items:center;gap:7px;color:var(--crm-text-muted);font-size:11px;font-weight:700}.toolbar select{height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line-strong);border-radius:8px;font:inherit;font-size:11px}.row-count{flex:none;color:var(--crm-text-muted);font-size:11px;font-weight:700}.evaluation-table-wrap{overflow:auto;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.evaluation-table{width:100%;min-width:870px;border-collapse:collapse}.evaluation-table th,.evaluation-table td{padding:13px 12px;border-bottom:1px solid var(--crm-line);font-size:11px;text-align:left}.evaluation-table th{color:var(--crm-text-muted);background:#faf8f5;font-size:10px;letter-spacing:.02em}.evaluation-table tbody tr{cursor:pointer;transition:background .15s ease}.evaluation-table tbody tr:hover,.evaluation-table tr.selected{background:#fff8ed}.evaluation-table tr.selected{box-shadow:inset 3px 0 0 var(--crm-teal)}.evaluation-table td:first-child{min-width:190px}.evaluation-table td b,.evaluation-table td strong{display:block}.evaluation-table td b{margin-bottom:4px;color:var(--crm-teal);font-size:11px}.evaluation-table td strong{color:var(--crm-link);font-size:12px}.detail-link{display:grid;width:30px;height:30px;place-items:center;color:var(--crm-link);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}.empty-copy{padding:42px;color:var(--crm-text-muted);text-align:center}.action-panel{position:sticky;top:16px;display:grid;align-content:start;gap:10px;padding:16px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.panel-kicker{display:flex;align-items:center;gap:7px;color:var(--crm-teal);font-size:11px;font-weight:800}.action-panel>b{color:var(--crm-teal);font-size:12px}.action-panel h2{margin:0;color:var(--crm-navy);font-size:15px;line-height:1.4}.action-panel>p{margin:0;color:var(--crm-text-muted);font-size:11px;line-height:1.5}.action-panel dl{display:grid;margin:2px 0}.action-panel dl div{display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid var(--crm-line);font-size:10px}.action-panel dt{color:var(--crm-text-muted)}.action-panel dd{margin:0;font-weight:700;text-align:right}.owner-note{display:flex;align-items:flex-start;gap:7px;margin-top:2px;padding:10px;color:var(--crm-text-muted);background:var(--crm-surface);border-radius:8px;font-size:10px;line-height:1.5}.owner-note svg{flex:none;color:var(--crm-teal)}@media(max-width:1000px){.evaluation-workspace{grid-template-columns:1fr}.action-panel{position:static}.toolbar{align-items:stretch;flex-wrap:wrap}.toolbar-search{min-width:100%}}
.evaluation-link{display:grid;gap:4px;padding:0;color:inherit;background:transparent;border:0;font:inherit;text-align:left;cursor:pointer}.evaluation-link:hover strong{color:var(--crm-link-hover);text-decoration:none}
.test-report-card,.customer-report-card{display:grid;gap:8px;padding:11px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:9px}.test-report-card header,.customer-report-card header{display:flex;align-items:center;gap:6px;color:var(--crm-navy)}.test-report-card header span,.customer-report-card header span{margin-left:auto;color:var(--crm-teal);font-size:9px;font-weight:800}.report-file{display:grid;grid-template-columns:55px minmax(0,1fr);gap:3px 7px;padding:7px;background:#fff;border:1px solid var(--crm-line);border-radius:7px}.report-file strong{grid-row:1/3;color:var(--crm-teal);font-size:8px}.report-file b{overflow:hidden;color:var(--crm-navy);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.report-file small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.test-report-card small,.test-report-card p,.customer-report-card small,.customer-report-card p{margin:0;color:var(--crm-text-muted);font-size:9px;line-height:1.5}.test-report-card .primary-button,.test-report-card .secondary-button,.customer-report-card .secondary-button{width:100%}
.evaluation-history{display:grid;gap:8px;padding:10px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line)}.evaluation-history header{display:flex;align-items:center;gap:6px;color:var(--crm-navy);font-size:10px}.evaluation-history ol{display:grid;gap:8px;margin:0;padding:0;list-style:none}.evaluation-history li{display:grid;gap:2px}.evaluation-history li span{color:var(--crm-teal);font-size:8px;font-weight:800}.evaluation-history li strong{font-size:9px;line-height:1.4}.evaluation-history li small{color:var(--crm-text-muted);font-size:8px}
@media(max-width:839px){.toolbar{display:grid;grid-template-columns:minmax(0,1fr) auto}.toolbar-search{grid-column:1/-1;min-width:0}.row-count{align-self:center}.evaluation-table-wrap{overflow:visible;background:transparent;border:0}.evaluation-table{min-width:0;border-collapse:separate}.evaluation-table thead{display:none}.evaluation-table tbody{display:grid;gap:10px}.evaluation-table tr{display:grid;overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:11px}.evaluation-table tbody tr:hover,.evaluation-table tr.selected{background:#fff}.evaluation-table tr.selected{border-color:var(--crm-teal);box-shadow:inset 3px 0 0 var(--crm-teal)}.evaluation-table td,.evaluation-table td:first-child{display:grid;min-width:0;grid-template-columns:104px minmax(0,1fr);align-items:center;gap:10px;padding:9px 12px;font-size:12px}.evaluation-table td::before{grid-column:1;content:attr(data-label);color:var(--crm-text-muted);font-size:10px;font-weight:800}.evaluation-table td>*{grid-column:2}.evaluation-link{min-width:0}.evaluation-link strong{overflow-wrap:anywhere}.action-panel{padding:14px}}
@media(max-width:480px){.toolbar{grid-template-columns:1fr}.toolbar label{justify-content:space-between}.toolbar select{min-width:0;max-width:65%}.row-count{justify-self:start}.evaluation-table td,.evaluation-table td:first-child{grid-template-columns:88px minmax(0,1fr)}}
</style>
