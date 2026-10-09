<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { CrmApiError, type CrmApi } from '@/api'
import { mapRequestError } from '@/api/request-state'
import { useI18n, useLocaleMessage } from '@/i18n'
import { useAppStore } from '@/stores/app'
import { opportunityProbabilityLevelLabel, opportunityProbabilityLevelRank } from '@/domain/opportunity-probability'
import type { BlueSheetAssessment, BlueSheetRedFlagInput, StrategyOpportunityDto } from '@/types/workspaces'

const props = defineProps<{ opportunity: StrategyOpportunityDto; apiClient: CrmApi }>()
const emit = defineEmits<{ updated: [opportunity: StrategyOpportunityDto]; denied: [] }>()
const app = useAppStore()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
// An archived Opportunity is read-only: no red flag is edited and no suggestion confirmed until it is restored.
const canEdit = computed(() => app.can('deal:write') && props.opportunity.redFlagRecords !== undefined && !props.opportunity.archived)
const canAssess = computed(() => ['Manager', 'Sales'].includes(app.bootstrap?.user.role ?? '') && props.opportunity.redFlagRecords !== undefined)
const records = computed(() => props.opportunity.redFlagRecords ?? props.opportunity.redFlags.map((text, i) => ({ id: String(i), text, severity: '' as const, status: 'Open' as const })))
const editing = ref(false), busy = ref(false), stale = ref(false), version = ref('')
const draft = ref<BlueSheetRedFlagInput[]>([])
const assessment = ref<BlueSheetAssessment | null>(null)
const reason = ref(''), plan = ref('')
const error = useLocaleMessage()
let operation = 0
onBeforeUnmount(() => { operation++ })
watch([() => props.opportunity.id, () => props.opportunity.owner, () => app.identityRevision], () => {
  operation++; editing.value = false; busy.value = false; stale.value = false; error.value = ''; assessment.value = null; draft.value = []
})
watch(() => props.opportunity.modified, value => {
  if (editing.value && value !== version.value || assessment.value && value !== assessment.value.opportunityModified) stale.value = true
})
// Archived (the page's archive): an editor open closes, as the page's own editors do, and its save still in flight is
// answered to no one; the panel's error and stale mark go (a suggestion shown is announced as older again once the
// restore moves the deal's version).
watch(canEdit, value => {
  if (value) return
  if (editing.value) { operation++; editing.value = false; busy.value = false }
  error.value = ''; stale.value = false
})
// Each change of the deal's archive flag is counted: a confirmation or a reload made before one is answered to no one,
// its success (the deal from before it) as its failure (about that deal).
let archiveTurns = 0
watch(() => Boolean(props.opportunity.archived), () => { archiveTurns++ })
const lowering = computed(() => !!assessment.value?.suggestedLevel && !!assessment.value.currentLevel
  && opportunityProbabilityLevelRank(assessment.value.suggestedLevel) < opportunityProbabilityLevelRank(assessment.value.currentLevel))
const severityLabel = (severity: string) => ({ High: copy('High', '高'), Medium: copy('Medium', '中'), Low: copy('Low', '低') })[severity] ?? copy('Unclassified', '未分类')
function report(cause: unknown) {
  const mapped = mapRequestError(cause)
  if (mapped.denied) { assessment.value = null; editing.value = false; emit('denied'); return }
  error.value = mapped.localizedMessage ?? mapped.message
  if (cause instanceof CrmApiError && cause.code === 'VERSION_CONFLICT') stale.value = true
}
function edit() {
  if (!canEdit.value || busy.value) return
  draft.value = records.value.map(({ id, text, severity, status }) => ({ id, text, severity, status }))
  version.value = props.opportunity.modified ?? ''; editing.value = true; stale.value = false; error.value = ''; assessment.value = null
}
async function save() {
  if (!canEdit.value || !editing.value || busy.value || stale.value || !version.value) return
  const request = ++operation
  busy.value = true; error.value = ''
  try {
    const response = await props.apiClient.saveBlueSheetFlags(props.opportunity.id, { items: draft.value.map(row => ({ ...row })) }, version.value)
    if (request !== operation) return
    editing.value = false; assessment.value = null; emit('updated', response.data)
  } catch (cause) { if (request === operation) report(cause) }
  finally { if (request === operation) busy.value = false }
}
async function reload() {
  if (busy.value) return
  const request = ++operation, turns = archiveTurns
  busy.value = true; error.value = ''
  try {
    const response = await props.apiClient.getStrategyOpportunity(props.opportunity.id)
    if (request !== operation || turns !== archiveTurns) return
    editing.value = false; stale.value = false; assessment.value = null; emit('updated', response.data)
  } catch (cause) { if (request === operation && turns === archiveTurns) report(cause) }
  finally { if (request === operation) busy.value = false }
}
async function assess() {
  if (!canAssess.value || busy.value || editing.value) return
  const request = ++operation
  busy.value = true; error.value = ''; assessment.value = null; reason.value = ''; plan.value = ''
  try {
    const response = await props.apiClient.getBlueSheetAssessment(props.opportunity.id)
    if (request !== operation) return
    assessment.value = response.data; stale.value = response.data.opportunityModified !== props.opportunity.modified
  } catch (cause) { if (request === operation) report(cause) }
  finally { if (request === operation) busy.value = false }
}
async function apply() {
  const current = assessment.value
  if (!current || current.state !== 'suggested' || !current.canApply || props.opportunity.archived || busy.value || stale.value || editing.value) return
  if (lowering.value && (!reason.value.trim() || !plan.value.trim())) return
  const request = ++operation, turns = archiveTurns
  busy.value = true; error.value = ''
  try {
    const response = await props.apiClient.applyBlueSheetSuggestion(props.opportunity.id, {
      fingerprint: current.fingerprint, probabilityReason: reason.value.trim(), probabilityActionPlan: plan.value.trim(),
    }, current.opportunityModified)
    if (request !== operation) return
    // Confirmed, so before any archive or restore since took the deal's row (an archive refuses it after, as a restore's
    // new version does): the suggestion goes. Answered to no one, so does the stale mark a restore set on it (the page
    // keeps its own deal); handed back, the deal may be older than one the page took meanwhile, whose mark stays.
    assessment.value = null
    if (turns === archiveTurns) emit('updated', response.data)
    else stale.value = false
  } catch (cause) { if (request === operation && turns === archiveTurns) report(cause) }
  finally { if (request === operation) busy.value = false }
}
</script>

<template>
  <section class="blue-sheet-panel" data-testid="blue-sheet-panel">
    <header><h2>{{ copy('Red flags', '红旗') }}</h2><button v-if="canEdit && !editing" type="button" :disabled="busy" data-blue-flags-edit @click="edit">{{ copy('Edit', '编辑') }}</button></header>
    <p class="note">{{ copy('Open flags on active deals appear in Warnings. Unclassified severity stays unknown.', '进行中商机的未解决红旗同步到 Warnings；未分类严重程度保持未知。') }}</p>
    <form v-if="editing" @submit.prevent="save">
      <fieldset :disabled="busy || stale">
        <article v-for="(row, index) in draft" :key="row.id ?? `new-${index}`" class="flag-row" data-blue-flag-editor>
          <label>{{ copy('Risk', '风险内容') }}<textarea v-model="row.text" rows="2" :maxlength="Math.max(4000, records.find(item => item.id === row.id)?.text.length ?? 0)" required /></label>
          <div class="flag-controls"><label>{{ copy('Severity', '严重程度') }}<select v-model="row.severity"><option value="">{{ copy('Unclassified', '未分类') }}</option><option v-for="severity in ['Low', 'Medium', 'High']" :key="severity" :value="severity">{{ severityLabel(severity) }}</option></select></label>
            <label>{{ copy('Status', '处理状态') }}<select v-model="row.status"><option value="Open">{{ copy('Open', '未解决') }}</option><option value="Resolved">{{ copy('Resolved', '已解决') }}</option></select></label>
            <button type="button" :aria-label="copy('Remove red flag', '删除红旗')" @click="draft.splice(index, 1)">{{ copy('Remove', '删除') }}</button></div>
        </article>
        <button type="button" data-blue-flag-add :disabled="draft.length >= Math.max(200, records.length)" @click="draft.push({ text: '', severity: '', status: 'Open' })">{{ copy('Add red flag', '新增红旗') }}</button>
      </fieldset>
      <footer><button type="button" :disabled="busy" @click="editing = false">{{ copy('Cancel', '取消') }}</button><button type="submit" data-blue-flags-save :disabled="busy || stale || !version || draft.some(row => !row.text.trim())">{{ copy('Save red flags', '保存红旗') }}</button></footer>
    </form>
    <ul v-else class="flags"><li v-for="row in records" :key="row.id" :class="{ resolved: row.status === 'Resolved' }" :data-blue-flag="row.id"><span>{{ row.text }}</span><small>{{ severityLabel(row.severity) }} · {{ row.status === 'Resolved' ? copy('Resolved', '已解决') : copy('Open', '未解决') }}</small></li></ul>
    <p v-if="!editing && !records.length" class="note">{{ copy('No red flags recorded.', '尚未记录红旗。') }}</p>
    <section v-if="canAssess" class="assessment">
      <h3>{{ copy('Probability suggestion', '概率档位建议') }}</h3>
      <p class="note">{{ copy('A suggestion uses the approved rule version. Your current level changes only after you confirm.', '建议使用已确认的规则版本，销售确认后才更新当前档位。') }}</p>
      <button type="button" data-blue-assess :disabled="busy || editing" @click="assess">{{ copy('Check current facts', '检查当前依据') }}</button>
      <template v-if="assessment">
        <p v-if="assessment.state === 'unconfigured'" data-blue-unconfigured>{{ copy('Probability rules are not configured or valid. No level is recommended.', '概率规则尚未配置或配置无效，暂不推荐档位。') }}</p>
        <p v-else-if="assessment.state === 'closed'">{{ copy('This opportunity is closed; its probability level is frozen.', '商机已结束，概率档位已冻结。') }}</p>
        <p v-else-if="assessment.state === 'no_match'">{{ copy('Current facts do not match an approved rule. No level is recommended.', '当前依据未满足已确认规则，暂不推荐档位。') }}</p>
        <dl class="facts"><div><dt>{{ copy('Open / high / unclassified flags', '未解决／高严重程度／未分类红旗') }}</dt><dd>{{ assessment.facts.openRedFlags }} / {{ assessment.facts.highRedFlags }} / {{ assessment.facts.unclassifiedRedFlags }}</dd></div><div><dt>{{ copy('Opposed stakeholders', '反对的关键人') }}</dt><dd>{{ assessment.facts.opposedStakeholders }}</dd></div><div><dt>{{ copy('Covered roles', '已覆盖角色') }}</dt><dd>{{ assessment.facts.coveredRoles.join(', ') || copy('None recorded', '尚未记录') }}</dd></div></dl>
        <p v-if="assessment.ruleVersion" class="note">{{ copy('Rule version', '规则版本') }}: {{ assessment.ruleVersion }}<template v-if="assessment.ruleId"> · {{ assessment.ruleId }}</template></p>
        <template v-if="assessment.state === 'suggested' && assessment.suggestedLevel">
          <strong data-blue-suggested>{{ opportunityProbabilityLevelLabel(assessment.suggestedLevel, locale) }}</strong><p>{{ assessment.reason }}</p>
          <template v-if="assessment.canApply && !opportunity.archived && assessment.currentLevel !== assessment.suggestedLevel">
            <template v-if="lowering"><label>{{ copy('Reason for lowering the level', '降档原因') }}<textarea v-model="reason" maxlength="4000" :disabled="busy || stale" data-blue-reason /></label><label>{{ copy('Recovery action plan', '补救行动计划') }}<textarea v-model="plan" maxlength="4000" :disabled="busy || stale" data-blue-plan /></label></template>
            <button type="button" data-blue-apply :disabled="busy || stale || (lowering && (!reason.trim() || !plan.trim()))" @click="apply">{{ copy('Confirm suggested level', '确认采用建议档位') }}</button>
          </template>
          <p v-else-if="opportunity.archived" class="note" data-blue-archived>{{ copy('This opportunity is archived: no level is confirmed until a Manager restores it.', '商机已归档：经理取消归档前不能确认新档位。') }}</p>
          <p v-else-if="!stale" class="note">{{ assessment.currentLevel === assessment.suggestedLevel ? copy('The current level already matches.', '当前档位已一致。') : copy('Only the opportunity owner can confirm a new level.', '仅商机负责人可确认新档位。') }}</p>
        </template>
      </template>
    </section>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="stale && !opportunity.archived" role="alert">{{ copy('The record changed. Reload before editing or confirming.', '记录已变化，请重新加载后编辑或确认。') }}<button type="button" :disabled="busy" data-blue-reload @click="reload">{{ copy('Reload and discard draft', '重新加载并放弃草稿') }}</button></p>
  </section>
</template>

<style scoped>
.blue-sheet-panel { padding: 18px; border: 1px solid #e5e7eb; border-radius: 12px; background: #fff; }
header, .flag-controls, footer { display: flex; gap: 8px; align-items: center; justify-content: space-between; }
h2 { font-size: 15px; margin: 0; } h3 { font-size: 14px; } .note, small { color: #64748b; font-size: 12px; }
fieldset { padding: 0; border: 0; } label { display: grid; gap: 5px; font-size: 12px; margin: 8px 0; }
textarea, select { max-width: 100%; border: 1px solid #cbd5e1; border-radius: 5px; padding: 6px; font: inherit; }
button { border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; padding: 5px 9px; font-size: 12px; } button:disabled { opacity: .5; }
.flags { padding-left: 18px; } .flags li { margin: 10px 0; white-space: pre-wrap; overflow-wrap: anywhere; } small { display: block; }
.resolved { color: #64748b; } .flag-row, .assessment { border-top: 1px solid #e5e7eb; margin-top: 12px; padding-top: 8px; }
.facts { font-size: 12px; } .facts div { margin: 8px 0; } dd { margin: 4px 0; } [role=alert] { color: #b91c1c; font-size: 12px; }
</style>
