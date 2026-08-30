<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, ref, watch } from 'vue'
import { CalendarClock, ExternalLink, FileText, FlaskConical, History, Plus, UserRoundCog } from '@lucide/vue'
import type { EvaluationDto, EvaluationPreparationBranch, EvaluationStatus, Tone } from '@/types/crm'
import { evaluationGroup, evaluationPreparationStatus, evaluationStatusOptions, hasCompletedTestRun, isEvaluationPreparationComplete } from '@/domain/evaluations'
import { formatDisplayDate } from '@/domain/time'
import StatusBadge from '@/design-system/StatusBadge.vue'
import type { EvaluationView } from './EvaluationWorkspaceNav.vue'

const props = withDefaults(defineProps<{
  view: EvaluationView
  evaluations: EvaluationDto[]
  selectedId?: string
  processing?: string
  canWrite?: boolean
  canReport?: boolean
}>(), {
  selectedId: '',
  processing: '',
  canWrite: false,
  canReport: false,
})

const emit = defineEmits<{
  select: [id: string]
  'open-detail': [evaluation: EvaluationDto]
  status: [id: string, status: EvaluationStatus]
  prepare: [evaluation: EvaluationDto, branch: EvaluationPreparationBranch]
  deadline: [evaluation: EvaluationDto]
  run: [evaluation: EvaluationDto]
  report: [evaluation: EvaluationDto]
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
const selected = computed(() => scopedRows.value.find((item) => item.id === props.selectedId) ?? scopedRows.value[0] ?? null)
const nextStatus = computed(() => selected.value
  ? evaluationStatusOptions(selected.value.status).find((status) => status !== selected.value!.status && status !== 'Rejected')
  : undefined)
const selectedIsPreparation = computed(() => selected.value && evaluationGroup(selected.value.status) === 'Preparation')
const preparationComplete = computed(() => selected.value ? isEvaluationPreparationComplete(selected.value) : false)
const internalReviewBlocked = computed(() => selected.value?.status === 'Testing'
  && (!selected.value.internalReportArtifactId
    || !selected.value.externalReportArtifactId
    || !hasCompletedTestRun(selected.value)))
const showAdvance = computed(() => {
  if (!selected.value || !nextStatus.value) return false
  if (selected.value.status === 'Scheduled') return preparationComplete.value
  return ['Testing', 'Analysis', 'Internal Review', 'Customer Review'].includes(selected.value.status)
})
const advanceLabel = computed(() => (nextStatus.value ? ({
  Testing: '进入 Test Execution',
  'Internal Review': '完成 Test Execution',
  'Customer Review': '提交 Customer Review',
  Accepted: 'Accept Demo',
} as Partial<Record<EvaluationStatus, string>>)[nextStatus.value] ?? `推进至 ${nextStatus.value}` : ''))
const viewLabel = computed(() => ({
  overview: '全部 Demo Test',
  wafer: 'Wafer Preparation',
  preparation: 'Test Preparation',
  execution: 'Test Execution',
  internal: 'Internal Review',
  customer: 'Customer Review',
}[props.view]))
function displayStage(evaluation: EvaluationDto) {
  if (props.view === 'wafer') return `Wafer Preparation · ${evaluationPreparationStatus(evaluation, 'wafer')}`
  if (props.view === 'preparation') return `Test Preparation · ${evaluationPreparationStatus(evaluation, 'test')}`
  return evaluation.status
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
          客户
          <select v-model="accountId" aria-label="Evaluation 客户">
            <option value="All">全部客户</option>
            <option v-for="account in accounts" :key="account[0]" :value="account[0]">{{ account[1] }}</option>
          </select>
        </label>
        <span class="row-count">{{ viewLabel }} · {{ scopedRows.length }}</span>
      </div>

      <div class="evaluation-table-wrap">
        <table class="evaluation-table" data-evaluation-table>
          <thead>
            <tr>
              <th>Test / 项目</th>
              <th>客户</th>
              <th>来源 Request</th>
              <th>Engineer</th>
              <th>阶段</th>
              <th>计划完成</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in scopedRows"
              :key="item.id"
              :class="{ selected: selected?.id === item.id }"
              :data-evaluation="item.id"
              @click="emit('select', item.id)"
            >
              <td data-label="Test / 项目">
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
              <td data-label="客户">{{ item.accountName }}</td>
              <td data-label="来源 Request">{{ item.demoRequestId || '—' }}</td>
              <td data-label="Engineer">{{ personnelDisplayName(item.owner) }}</td>
              <td data-label="阶段"><StatusBadge :label="displayStage(item)" :tone="tone(item.status)" /></td>
              <td data-label="计划完成">{{ item.plannedEnd }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!scopedRows.length" class="empty-copy">当前分类暂无 Demo Test</p>
      </div>
    </div>

    <aside class="action-panel" data-evaluation-actions>
      <template v-if="selected">
        <span class="panel-kicker"><UserRoundCog :size="15" />相关人员操作</span>
        <b>{{ selected.id }}</b>
        <h2>{{ selected.title }}</h2>
        <p>{{ selected.accountName }}</p>

        <dl>
          <div><dt>Engineer</dt><dd>{{ personnelDisplayName(selected.owner) }}</dd></div>
          <div><dt>来源 Request</dt><dd>{{ selected.demoRequestId || '—' }}</dd></div>
          <div><dt>当前阶段</dt><dd>{{ displayStage(selected) }}</dd></div>
        </dl>

        <button
          class="secondary-button"
          type="button"
          :data-open-demo-detail="`${selected.id}-panel`"
          @click="emit('open-detail', selected)"
        >
          <ExternalLink :size="14" />查看详细信息
        </button>

        <section
          v-if="selected.status === 'Testing' && (view === 'overview' || view === 'execution')"
          class="test-report-card"
          data-test-report-card
        >
          <header><FileText :size="15" /><strong>Test Report</strong><span>{{ selected.reportStatus }}</span></header>
          <div v-if="selected.internalReportArtifact" class="report-file"><strong>Internal</strong><b>{{ selected.internalReportArtifact.fileName }}</b><small>v{{ selected.internalReportArtifact.version }} · {{ personnelDisplayName(selected.internalReportArtifact.createdBy) }} · {{ formatDisplayDate(selected.internalReportArtifact.createdAt) }}</small></div>
          <div v-if="selected.externalReportArtifact" class="report-file"><strong>External</strong><b>{{ selected.externalReportArtifact.fileName }}</b><small>v{{ selected.externalReportArtifact.version }} · {{ personnelDisplayName(selected.externalReportArtifact.createdBy) }} · {{ formatDisplayDate(selected.externalReportArtifact.createdAt) }}</small></div>
          <p v-if="!selected.internalReportArtifact || !selected.externalReportArtifact">Internal 和 External 两份报告均上传后才可进入 Internal Review。</p>
          <button
            v-if="canWrite"
            type="button"
            :class="selected.reportStatus === 'Ready' ? 'secondary-button' : 'primary-button'"
            :data-report-action="selected.id"
            :disabled="processing === selected.id"
            @click="emit('report', selected)"
          >
            <FileText :size="14" />{{ selected.reportStatus === 'Ready' ? '上传新版本' : '上传两份 Test Report' }}
          </button>
        </section>

        <button
          v-if="canWrite && selectedIsPreparation && evaluationPreparationStatus(selected, 'wafer') === 'Pending' && (view === 'overview' || view === 'wafer')"
          type="button"
          class="primary-button"
          data-complete-preparation="wafer"
          :disabled="processing === selected.id"
          @click="emit('prepare', selected, 'wafer')"
        >完成 Wafer Preparation</button>
        <button
          v-if="canWrite && selectedIsPreparation && evaluationPreparationStatus(selected, 'test') === 'Pending' && (view === 'overview' || view === 'preparation')"
          type="button"
          class="primary-button"
          data-complete-preparation="test"
          :disabled="processing === selected.id"
          @click="emit('prepare', selected, 'test')"
        >完成 Test Preparation</button>

        <button
          v-if="canWrite && selectedIsPreparation && (view === 'overview' || view === 'preparation')"
          type="button"
          class="primary-button"
          :data-set-ddl="selected.id"
          :disabled="processing === selected.id"
          @click="emit('deadline', selected)"
        >
          <CalendarClock :size="14" />设置 Test Run DDL
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
          <Plus :size="14" />新增 Test Run
        </button>
        <button
          v-if="canWrite && showAdvance"
          type="button"
          class="primary-button"
          :data-advance-status="nextStatus"
          :disabled="processing === selected.id || internalReviewBlocked"
          @click="emit('status', selected.id, nextStatus!)"
        >{{ advanceLabel }}</button>
        <p v-if="canWrite && internalReviewBlocked" class="action-hint" data-test-run-review-gate>请先上传 Internal 和 External Test Report以及完成Test Run。</p>
        <button
          v-if="canWrite && !['Accepted', 'Rejected'].includes(selected.status)"
          type="button"
          class="danger-button"
          data-reject-evaluation
          :disabled="processing === selected.id"
          @click="emit('status', selected.id, 'Rejected')"
        >Reject Demo</button>
        <div class="owner-note">
          <FlaskConical :size="14" />
          <span>操作区域只保留当前负责人可执行动作；详细测试信息请进入内页。</span>
        </div>
        <section v-if="selected.history?.length" class="evaluation-history" aria-label="Evaluation history">
          <header><History :size="14" /><strong>Tracking History</strong></header>
          <ol>
            <li v-for="event in selected.history.slice(0, 6)" :key="event.id">
              <span>{{ event.eventType }}</span>
              <strong>{{ event.summary }}</strong>
              <small>{{ personnelDisplayName(event.actor) }} · {{ formatDisplayDate(event.at) }}</small>
            </li>
          </ol>
        </section>
      </template>
      <p v-else>请先选择一条 Demo Test。</p>
    </aside>
  </section>
</template>

<style scoped>
.evaluation-workspace{display:grid;grid-template-columns:minmax(0,1fr) 248px;gap:14px;align-items:start}.workspace-main{min-width:0;display:grid;gap:12px}.toolbar{display:flex;align-items:center;gap:10px;padding:11px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.toolbar-search{display:flex;min-width:240px;flex:1;align-items:center;gap:7px;height:36px;padding:0 11px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.toolbar-search input{min-width:0;flex:1;background:transparent;border:0;outline:0;font:inherit;font-size:12px}.toolbar label{display:flex;align-items:center;gap:7px;color:var(--crm-text-muted);font-size:11px;font-weight:700}.toolbar select{height:36px;padding:0 9px;background:#fff;border:1px solid var(--crm-line-strong);border-radius:8px;font:inherit;font-size:11px}.row-count{flex:none;color:var(--crm-text-muted);font-size:11px;font-weight:700}.evaluation-table-wrap{overflow:auto;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.evaluation-table{width:100%;min-width:870px;border-collapse:collapse}.evaluation-table th,.evaluation-table td{padding:13px 12px;border-bottom:1px solid var(--crm-line);font-size:11px;text-align:left}.evaluation-table th{color:var(--crm-text-muted);background:#faf8f5;font-size:10px;letter-spacing:.02em}.evaluation-table tbody tr{cursor:pointer;transition:background .15s ease}.evaluation-table tbody tr:hover,.evaluation-table tr.selected{background:#fff8ed}.evaluation-table tr.selected{box-shadow:inset 3px 0 0 var(--crm-teal)}.evaluation-table td:first-child{min-width:190px}.evaluation-table td b,.evaluation-table td strong{display:block}.evaluation-table td b{margin-bottom:4px;color:var(--crm-teal);font-size:11px}.evaluation-table td strong{color:var(--crm-link);font-size:12px}.detail-link{display:grid;width:30px;height:30px;place-items:center;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:7px;cursor:pointer}.empty-copy{padding:42px;color:var(--crm-text-muted);text-align:center}.action-panel{position:sticky;top:16px;display:grid;align-content:start;gap:10px;padding:16px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.panel-kicker{display:flex;align-items:center;gap:7px;color:var(--crm-teal);font-size:11px;font-weight:800}.action-panel>b{color:var(--crm-teal);font-size:12px}.action-panel h2{margin:0;color:var(--crm-navy);font-size:15px;line-height:1.4}.action-panel>p{margin:0;color:var(--crm-text-muted);font-size:11px;line-height:1.5}.action-panel dl{display:grid;margin:2px 0}.action-panel dl div{display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid var(--crm-line);font-size:10px}.action-panel dt{color:var(--crm-text-muted)}.action-panel dd{margin:0;font-weight:700;text-align:right}.owner-note{display:flex;align-items:flex-start;gap:7px;margin-top:2px;padding:10px;color:var(--crm-text-muted);background:var(--crm-surface);border-radius:8px;font-size:10px;line-height:1.5}.owner-note svg{flex:none;color:var(--crm-teal)}@media(max-width:1000px){.evaluation-workspace{grid-template-columns:1fr}.action-panel{position:static}.toolbar{align-items:stretch;flex-wrap:wrap}.toolbar-search{min-width:100%}}
.evaluation-link{display:grid;gap:4px;padding:0;color:inherit;background:transparent;border:0;font:inherit;text-align:left;cursor:pointer}.evaluation-link:hover strong{color:var(--crm-link-hover);text-decoration:none}
.test-report-card{display:grid;gap:8px;padding:11px;background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:9px}.test-report-card header{display:flex;align-items:center;gap:6px;color:var(--crm-navy)}.test-report-card header span{margin-left:auto;color:var(--crm-teal);font-size:9px;font-weight:800}.report-file{display:grid;grid-template-columns:55px minmax(0,1fr);gap:3px 7px;padding:7px;background:#fff;border:1px solid var(--crm-line);border-radius:7px}.report-file strong{grid-row:1/3;color:var(--crm-teal);font-size:8px}.report-file b{overflow:hidden;color:var(--crm-navy);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.report-file small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.test-report-card small,.test-report-card p{margin:0;color:var(--crm-text-muted);font-size:9px;line-height:1.5}.test-report-card .primary-button,.test-report-card .secondary-button{width:100%}
.evaluation-history{display:grid;gap:8px;padding:10px 0;border-top:1px solid var(--crm-line);border-bottom:1px solid var(--crm-line)}.evaluation-history header{display:flex;align-items:center;gap:6px;color:var(--crm-navy);font-size:10px}.evaluation-history ol{display:grid;gap:8px;margin:0;padding:0;list-style:none}.evaluation-history li{display:grid;gap:2px}.evaluation-history li span{color:var(--crm-teal);font-size:8px;font-weight:800}.evaluation-history li strong{font-size:9px;line-height:1.4}.evaluation-history li small{color:var(--crm-text-muted);font-size:8px}
@media(max-width:839px){.toolbar{display:grid;grid-template-columns:minmax(0,1fr) auto}.toolbar-search{grid-column:1/-1;min-width:0}.row-count{align-self:center}.evaluation-table-wrap{overflow:visible;background:transparent;border:0}.evaluation-table{min-width:0;border-collapse:separate}.evaluation-table thead{display:none}.evaluation-table tbody{display:grid;gap:10px}.evaluation-table tr{display:grid;overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:11px}.evaluation-table tbody tr:hover,.evaluation-table tr.selected{background:#fff}.evaluation-table tr.selected{border-color:var(--crm-teal);box-shadow:inset 3px 0 0 var(--crm-teal)}.evaluation-table td,.evaluation-table td:first-child{display:grid;min-width:0;grid-template-columns:104px minmax(0,1fr);align-items:center;gap:10px;padding:9px 12px;font-size:12px}.evaluation-table td::before{grid-column:1;content:attr(data-label);color:var(--crm-text-muted);font-size:10px;font-weight:800}.evaluation-table td>*{grid-column:2}.evaluation-link{min-width:0}.evaluation-link strong{overflow-wrap:anywhere}.action-panel{padding:14px}}
@media(max-width:480px){.toolbar{grid-template-columns:1fr}.toolbar label{justify-content:space-between}.toolbar select{min-width:0;max-width:65%}.row-count{justify-self:start}.evaluation-table td,.evaluation-table td:first-child{grid-template-columns:88px minmax(0,1fr)}}
</style>
