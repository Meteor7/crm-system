<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { CrmApiError, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import ModalShell from '@/design-system/ModalShell.vue'
import { personnelDisplayName } from '@/demo/personnel'
import { opportunityProbabilityLevelLabel, opportunityProbabilityLevelRank } from '@/domain/opportunity-probability'
import { formatDisplayDateTime } from '@/domain/time'
import { localeMessage, useI18n, useLocaleMessage } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { OpportunityProbabilityHistoryDto, StrategyOpportunityDto } from '@/types/workspaces'

const props = defineProps<{ opportunity: StrategyOpportunityDto; apiClient: CrmApi; highlightEventId?: string }>()
const emit = defineEmits<{ updated: [opportunity: StrategyOpportunityDto]; denied: [] }>()
const app = useAppStore()
const { locale, t } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
// An archived Opportunity (a Manager's archive, in place of a delete) takes no plan and no action until restored.
const canEdit = computed(() => app.can('deal:write') && !props.opportunity.archived
  && (app.bootstrap?.user.role === 'Manager' || props.opportunity.owner === app.bootstrap?.user.id))
const canRecord = computed(() => app.can('deal:write') && !props.opportunity.archived && props.opportunity.owner === app.bootstrap?.user.id)
const mode = ref<'plan' | 'action'>('plan')
const isAction = computed(() => mode.value === 'action')
const entries = new Map<string, HTMLElement>()
watch([() => props.highlightEventId, () => props.opportunity.id], async () => {
  await nextTick()
  const element = entries.get(props.highlightEventId ?? '')
  element?.scrollIntoView?.({ block: 'center' })
  element?.focus({ preventScroll: true })
}, { immediate: true })
const isDowngrade = (entry: OpportunityProbabilityHistoryDto) => Boolean(entry.from)
  && opportunityProbabilityLevelRank(entry.to) < opportunityProbabilityLevelRank(entry.from)
const target = ref<OpportunityProbabilityHistoryDto | null>(null)
const parentVersion = ref('')
const draft = ref('')
const busy = ref(false)
const error = useLocaleMessage()
const requestId = ref('')
const conflict = ref(false)
let operation = 0
onBeforeUnmount(() => { operation++ })

watch([() => props.opportunity.id, () => props.opportunity.owner, () => app.identityRevision, canEdit], () => {
  operation++
  target.value = null
  busy.value = false
  error.value = ''
})

function open(entry: OpportunityProbabilityHistoryDto, action = false) {
  if (!canEdit.value || busy.value || !isDowngrade(entry)) return
  if (action && (!canRecord.value || !entry.recovery || entry.recovery.state === 'handled')) return
  mode.value = action ? 'action' : 'plan'
  target.value = entry
  parentVersion.value = props.opportunity.modified ?? ''
  draft.value = action ? '' : entry.recovery?.plan ?? ''
  error.value = ''
  requestId.value = ''
  conflict.value = false
}

function close() {
  if (!busy.value) target.value = null
}

function reportError(reason: unknown) {
  const mapped = mapRequestError(reason)
  if (mapped.denied) {
    target.value = null
    emit('denied')
    return
  }
  error.value = mapped.localizedMessage ?? mapped.message
  requestId.value = mapped.requestId
  conflict.value = reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT'
}

async function save() {
  const entry = target.value
  if (!entry || busy.value || !canEdit.value || conflict.value) return
  if (isAction.value && !canRecord.value) return
  if (!draft.value.trim() || draft.value.trim().length > 4000) {
    error.value = isAction.value
      ? localeMessage('Describe the action already taken (1–4000 characters).', '请填写已经采取的行动（1–4000 字）。')
      : localeMessage('Enter a recovery plan (1–4000 characters).', '请填写补救计划（1–4000 字）。')
    return
  }
  if (!parentVersion.value) {
    error.value = localeMessage('Reload the current Opportunity before saving.', '请先重新载入当前商机。')
    conflict.value = true
    return
  }
  const request = ++operation
  const identity = app.identityRevision
  busy.value = true
  error.value = ''
  requestId.value = ''
  try {
    const result = isAction.value
      ? await props.apiClient.recordProbabilityRecoveryAction(props.opportunity.id, entry.id, {
        actionTaken: draft.value.trim(), recoveryModified: entry.recovery!.modified,
      }, parentVersion.value)
      : await props.apiClient.saveProbabilityRecovery(props.opportunity.id, entry.id, {
        plan: draft.value.trim(), recoveryModified: entry.recovery?.modified ?? null,
      }, parentVersion.value)
    if (request !== operation || identity !== app.identityRevision) return
    emit('updated', { ...props.opportunity, probabilityHistory: props.opportunity.probabilityHistory.map(row =>
      row.id === entry.id ? { ...row, recovery: result.data } : row) })
    target.value = null
  } catch (reason) {
    if (request === operation && identity === app.identityRevision) reportError(reason)
  } finally {
    if (request === operation) busy.value = false
  }
}

async function reload() {
  const entry = target.value
  if (!entry || busy.value || !canEdit.value) return
  const request = ++operation
  const identity = app.identityRevision
  busy.value = true
  try {
    const result = await props.apiClient.getStrategyOpportunity(props.opportunity.id)
    if (request !== operation || identity !== app.identityRevision) return
    emit('updated', result.data)
    const latest = result.data.probabilityHistory.find(row => row.id === entry.id)
    if (!latest || !isDowngrade(latest)) { target.value = null; return }
    if (isAction.value && (!latest.recovery || latest.recovery.state === 'handled')) { target.value = null; return }
    target.value = latest
    parentVersion.value = result.data.modified ?? ''
    draft.value = isAction.value ? '' : latest.recovery?.plan ?? ''
    error.value = ''
    requestId.value = ''
    conflict.value = false
  } catch (reason) {
    if (request === operation && identity === app.identityRevision) {
      reportError(reason)
      conflict.value = true
    }
  } finally {
    if (request === operation) busy.value = false
  }
}
</script>

<template>
  <section class="probability-panel" data-testid="opportunity-probability-history">
    <header><h2>{{ t('detail.probabilityHistory') }}</h2><span>{{ opportunity.probabilityHistory.length }}</span></header>
    <article v-for="entry in opportunity.probabilityHistory" :key="entry.id" :ref="el => { if (el) entries.set(entry.id, el as HTMLElement); else entries.delete(entry.id) }" tabindex="-1" :class="{ highlighted: entry.id === highlightEventId }" :data-probability-history-id="entry.id">
      <strong>{{ opportunityProbabilityLevelLabel(entry.from, locale) }} → {{ opportunityProbabilityLevelLabel(entry.to, locale) }}</strong>
      <p class="meta">{{ personnelDisplayName(entry.actor) }} · <time :datetime="entry.at">{{ formatDisplayDateTime(entry.at) }}</time></p>
      <template v-if="isDowngrade(entry)">
        <p><b>{{ copy('Reason', '原因') }}：</b>{{ entry.reason || copy('Not recorded', '未记录') }}</p>
        <p class="meta">{{ copy('Responsible owner', '负责人') }} · {{ personnelDisplayName(opportunity.owner) }}</p>
        <p class="plan-text" :data-recovery-plan="entry.id">{{ entry.recovery?.plan || copy('No recovery plan recorded for this historical change.', '这次历史降档尚未登记补救计划。') }}</p>
        <p :data-recovery-state="entry.id">{{ entry.recovery?.state === 'handled' ? copy('Action recorded · warning cleared', '已记录行动 · 提醒已清除') : copy('Awaiting action', '待采取行动') }}</p>
        <div v-if="entry.recovery?.state === 'handled'" class="action-record">
          <p class="plan-text">{{ entry.recovery.actionTaken }}</p>
          <p class="meta">{{ personnelDisplayName(entry.recovery.actedBy || '') }} · {{ formatDisplayDateTime(entry.recovery.actedAt || '') }}</p>
        </div>
        <button v-if="canEdit" type="button" class="secondary-button" :disabled="busy" :data-recovery-edit="entry.id" @click="open(entry)">{{ entry.recovery ? copy('Edit recovery plan', '修改补救计划') : copy('Add recovery plan', '补录补救计划') }}</button>
        <button v-if="canRecord && entry.recovery && entry.recovery.state !== 'handled'" type="button" class="secondary-button record-action" :disabled="busy" :data-recovery-act="entry.id" @click="open(entry, true)">{{ copy('Record action taken', '记录已采取行动') }}</button>
        <p v-else-if="canEdit && entry.recovery?.state !== 'handled'" class="meta">{{ copy('The current owner records the action taken after a plan is saved.', '保存计划后，由当前负责人记录已采取的行动。') }}</p>
        <details v-if="entry.recovery?.history.length" class="plan-history">
          <summary>{{ copy('Plan and action history', '计划与行动记录') }} · {{ entry.recovery.history.length }}</summary>
          <ol><li v-for="revision in entry.recovery.history" :key="revision.id">
            <p class="meta">{{ personnelDisplayName(revision.actor) }} · {{ formatDisplayDateTime(revision.at) }}</p>
            <p class="plan-text">{{ revision.plan }}</p>
            <p v-if="revision.kind === 'ActionRecorded'" class="plan-text">{{ copy('Action taken', '已采取行动') }}：{{ revision.actionTaken }}</p>
          </li></ol>
        </details>
      </template>
    </article>
    <p v-if="!opportunity.probabilityHistory.length" class="empty">{{ t('detail.noProbabilityHistory') }}</p>
    <ModalShell v-if="target" :title="isAction ? copy('Record action taken', '记录已采取行动') : copy('Recovery plan', '降档补救计划')" :busy="busy" :submit-disabled="conflict" @submit="save" @close="close">
      <fieldset :disabled="busy" class="plan-form">
        <p>{{ copy('Responsible owner', '负责人') }} · {{ personnelDisplayName(opportunity.owner) }}</p>
        <p v-if="isAction" class="plan-text">{{ target.recovery?.plan }}</p>
        <label>{{ isAction ? copy('What action have you already taken?', '已经采取了什么行动？') : copy('What will you do to recover this opportunity?', '准备采取什么措施挽回商机？') }}
          <textarea v-model="draft" required maxlength="4000" rows="6" data-recovery-draft />
        </label>
        <p>{{ isAction ? copy('This records your action and clears this downgrade warning. The audit is kept.', '保存后会记录你的实际行动并清除本次降档提醒，历史记录仍保留。') : copy('Saving a plan does not mean an action has been taken.', '保存计划不代表已经采取行动。') }}</p>
        <div v-if="error" role="alert" class="error"><p>{{ error }}</p><small v-if="requestId">Request ID · {{ requestId }}</small></div>
        <div v-if="conflict" class="reload">
          <p>{{ copy('Your draft is kept. Reloading discards it and loads the latest record.', '当前输入已保留。重新载入会放弃本次输入并获取最新记录。') }}</p>
          <button type="button" class="secondary-button" data-recovery-reload @click="reload">{{ copy('Reload and discard draft', '重新载入并放弃本次输入') }}</button>
        </div>
      </fieldset>
    </ModalShell>
  </section>
</template>

<style scoped>
.probability-panel{min-width:0;overflow:hidden;border:1px solid var(--crm-line);border-radius:12px;background:#fff}
header{display:flex;align-items:center;justify-content:space-between;padding:14px;background:#faf9f7;border-bottom:1px solid var(--crm-line)}
h2{margin:0;font-size:12px;color:var(--crm-navy)}
header span,.meta{font-size:10px;color:var(--crm-text-muted)}
article{padding:14px;border-bottom:1px solid var(--crm-line);font-size:11px;overflow-wrap:anywhere}
article:last-child{border-bottom:0}p{margin:8px 0;line-height:1.5}.plan-text{white-space:pre-wrap}
.highlighted{outline:2px solid var(--crm-teal);outline-offset:-2px;background:#f0faf8}.record-action{margin-left:8px}.action-record{padding:8px;background:#f0faf8;border-radius:8px}
.plan-history{margin-top:12px}.plan-history summary{cursor:pointer;color:var(--crm-teal)}
.plan-history ol{padding-left:18px}.plan-history li{padding:4px 0;border-top:1px solid var(--crm-line)}
.empty{padding:16px;text-align:center;font-size:11px;color:var(--crm-text-muted)}
.plan-form{display:grid;gap:12px;margin:0;padding:0;border:0;min-width:0;font-size:12px}
.plan-form label{display:grid;gap:8px}.plan-form textarea{width:100%;box-sizing:border-box;padding:10px;border:1px solid var(--crm-line);border-radius:8px;font:inherit;resize:vertical}
.error{color:var(--crm-danger)}.reload{display:grid;gap:8px}
</style>
