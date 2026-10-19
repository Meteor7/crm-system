<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed } from 'vue'
import { FileText, FlaskConical, Plus } from '@lucide/vue'
import type { EvaluationDto, EvaluationPreparationBranch, EvaluationStatus, Tone } from '@/types/crm'
import { evaluationGroup, evaluationPreparationStatus, evaluationStatusOptions, isEvaluationPreparationComplete } from '@/domain/evaluations'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { useI18n } from '@/i18n'

const props = withDefaults(defineProps<{ evaluation: EvaluationDto; processing?: boolean; canWrite?: boolean; canReport?: boolean; highlighted?: boolean }>(), { canWrite: false, canReport: false, highlighted: false })
defineEmits<{ status: [id: string, status: EvaluationStatus]; prepare: [evaluation: EvaluationDto, branch: EvaluationPreparationBranch]; run: [evaluation: EvaluationDto]; deadline: [evaluation: EvaluationDto]; report: [evaluation: EvaluationDto] }>()
const { t } = useI18n()
const nextStatus = computed(() => evaluationStatusOptions(props.evaluation.status).find((status) => status !== props.evaluation.status && status !== 'Rejected'))
const isPreparation = computed(() => evaluationGroup(props.evaluation.status) === 'Preparation')
const isTestExecution = computed(() => props.evaluation.status === 'Testing')
const showAdvance = computed(() => nextStatus.value && (props.evaluation.status === 'Scheduled'
  ? isEvaluationPreparationComplete(props.evaluation)
  : ['Testing', 'Analysis', 'Internal Review', 'Customer Review'].includes(props.evaluation.status)))
const canOpenReport = computed(() => props.canWrite && props.evaluation.status === 'Testing')
const tone = (status: EvaluationStatus): Tone => status === 'Accepted' ? 'positive' : status === 'Rejected' ? 'danger' : 'info'
</script>

<template>
  <article class="evaluation-card is-aligned" :class="{ highlighted }" :data-evaluation="evaluation.id">
    <header><StatusBadge :label="evaluation.status" :tone="tone(evaluation.status)" /><small>{{ evaluation.accountName }}</small></header>
    <h3 class="line-clamp-2">{{ evaluation.title }}</h3>
    <div class="summary-zone">
      <p><FlaskConical :size="13" />{{ evaluation.wafers }} Wafers · Applied Engineer {{ personnelDisplayName(evaluation.owner) }}</p>
      <p v-if="evaluation.demoRequestId" class="source">{{ t('evaluationCard.sourceRequest') }} · {{ evaluation.demoRequestId }}</p>
      <p class="report-state">Test Report · {{ evaluation.reportStatus }}<template v-if="evaluation.reportVersion"> v{{ evaluation.reportVersion }}</template></p>
    </div>
    <div class="runs" data-scroll-region="runs"><div v-for="run in evaluation.runs.slice(-3)" :key="run.id"><strong>{{ run.id }} · {{ run.lot }} · {{ run.status }}</strong><span v-if="run.capture != null">Capture {{ run.capture }}% / FP {{ run.falsePositive }}% / {{ run.wph }} WPH</span><span v-else-if="run.status === 'Cancelled'">{{ run.summary }}</span><span v-else>{{ t('evaluationCard.waitingTest') }}</span></div></div>
    <div class="controls card-controls"><button v-if="canWrite && isPreparation && evaluationPreparationStatus(evaluation, 'wafer') === 'Pending'" data-complete-preparation="wafer" type="button" :disabled="processing" @click="$emit('prepare', evaluation, 'wafer')">{{ t('evaluationCard.completeWafer') }}</button><button v-if="canWrite && isPreparation && evaluationPreparationStatus(evaluation, 'test') === 'Pending'" data-complete-preparation="test" type="button" :disabled="processing" @click="$emit('prepare', evaluation, 'test')">{{ t('evaluationCard.completeTest') }}</button><button v-if="canWrite && isPreparation" :data-set-ddl="evaluation.id" type="button" :disabled="processing" @click="$emit('deadline', evaluation)">{{ t('evaluationCard.setDdl') }}</button><button v-if="canWrite && isTestExecution" :data-add-run="evaluation.id" type="button" :disabled="processing" @click="$emit('run', evaluation)"><Plus :size="12" />Test Run</button><button v-if="canWrite && showAdvance" :data-advance-status="nextStatus" type="button" :disabled="processing" @click="$emit('status', evaluation.id, nextStatus!)">{{ t('evaluationCard.advanceTo', { status: nextStatus || '' }) }}</button><button v-if="canWrite && !['Accepted', 'Rejected'].includes(evaluation.status)" data-reject-evaluation type="button" :disabled="processing" @click="$emit('status', evaluation.id, 'Rejected')">Reject Demo</button><button v-if="canOpenReport" :data-report-action="evaluation.id" type="button" :disabled="processing" @click="$emit('report', evaluation)"><FileText :size="12" />Test Report</button></div>
    <footer><span>{{ t('evaluationCard.completed') }} {{ evaluation.plannedEnd }}</span></footer>
  </article>
</template>

<style scoped>
.evaluation-card{display:grid;gap:9px;padding:15px;background:#fff;border:1px solid var(--crm-line);border-radius:12px}.evaluation-card.is-aligned{height:382px;grid-template-rows:22px 36px 54px 112px minmax(63px,auto) 22px;overflow:hidden}.evaluation-card.highlighted{border-color:var(--crm-teal);box-shadow:0 0 0 3px rgba(49, 89, 206,.15)}header,footer{display:flex;align-items:center;justify-content:space-between;gap:8px}header small,footer{color:var(--crm-text-muted);font-size:8px}h3{margin:0;color:var(--crm-navy);font-size:12px;line-height:1.4}.line-clamp-2{display:-webkit-box;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2}.summary-zone{display:grid;align-content:start;gap:6px;overflow:hidden}p{display:flex;align-items:center;gap:5px;margin:0;color:var(--crm-text-muted);font-size:9px}.source{color:var(--crm-teal);font-weight:700}.runs{display:grid;align-content:start;gap:5px;overflow-y:auto;padding-right:2px}.runs div{display:grid;gap:3px;padding:7px 8px;background:var(--crm-surface);border-radius:7px}.runs strong{overflow:hidden;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.runs span{color:var(--crm-text-muted);font-size:8px}.controls{display:flex;align-content:flex-start;flex-wrap:wrap;gap:5px}.controls select,.controls button,.controls a{display:flex;min-height:29px;align-items:center;gap:4px;padding:0 7px;color:var(--crm-link);background:#fff;border:1px solid var(--crm-line);border-radius:7px;font-size:8px;text-decoration:none}.controls select{flex:1;min-width:120px}.controls button{cursor:pointer}footer{align-self:end;padding-top:7px;border-top:1px dashed var(--crm-line)}
</style>
