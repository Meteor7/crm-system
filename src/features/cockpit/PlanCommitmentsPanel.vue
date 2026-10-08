<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { CrmApi } from '@/api'
import { CrmApiError } from '@/api/contracts'
import { requestErrorMessage } from '@/api/request-state'
import { useI18n, useLocaleMessage } from '@/i18n'
import { formatDisplayDateTime } from '@/domain/time'
import { metricText } from './presentation'
import type { CommitmentMetric, PlanCommitment, PlanDto } from './plan-types'

const props = defineProps<{ data: PlanDto; apiClient: CrmApi }>()
const emit = defineEmits<{ saved: []; reload: []; details: [sales: string, metric: CommitmentMetric] }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const metrics: CommitmentMetric[] = ['visits', 'leads', 'tests', 'quotes', 'followups', 'actions', 'events']
const label = (key: CommitmentMetric) => ({ visits: copy('Visits', '客户沟通'), leads: copy('Qualified leads', '合格线索'), tests: copy('Completed test runs', '完成测试轮次'), quotes: copy('First quotes sent', '首次发布报价'), followups: copy('Quote follow-ups', '报价跟进'), actions: copy('Actions', '商机行动'), events: copy('Events', '展会活动') })[key]
const selected = ref<CommitmentMetric>('visits'), editing = ref<{ sales: string; name: string; record: PlanCommitment | null }>()
const value = ref(''), note = ref(''), saving = ref(false), stale = ref(false)
const error = useLocaleMessage()
let revision = 0
const rows = computed(() => (props.data.commitments?.people ?? []).map(person => ({ ...person, item: person.activities.find(row => row.key === selected.value)! })))
const team = computed(() => props.data.commitments?.team.find(row => row.key === selected.value))
const valid = computed(() => /^\d+$/.test(value.value) && Number(value.value) <= 999999999 && note.value.trim().length <= 1000)
function open(row: typeof rows.value[number]) {
  if (!row.canEdit || row.item.commitment.conflicts?.length || saving.value) return
  editing.value = { sales: row.id, name: row.name, record: row.item.commitment.record }
  value.value = row.item.commitment.record?.value ?? ''; note.value = row.item.commitment.record?.note ?? ''
  stale.value = false; error.value = ''
}
watch(() => props.data, () => { if (editing.value) { stale.value = true; error.value = copy('The plan was refreshed; close and reopen this editor.', '计划已刷新，请关闭并重新打开编辑。') } })
watch(selected, () => { editing.value = undefined; error.value = '' })
onBeforeUnmount(() => { revision++ })
async function save() {
  if (!editing.value || !valid.value || saving.value || stale.value) return
  const current = revision
  saving.value = true; error.value = ''
  try {
    await props.apiClient.savePlanCommitment({ sales: editing.value.sales, metric: selected.value, period: props.data.period.kind,
      anchor: props.data.period.start, value: value.value, note: note.value.trim() }, editing.value.record?.modified)
    if (current !== revision) return
    editing.value = undefined; emit('saved')
  } catch (reason) {
    if (current === revision) {
      error.value = requestErrorMessage(reason)
      // Transient failures keep the draft retryable. A refresh during this
      // request may already have invalidated it, which a network error must not undo.
      if (reason instanceof CrmApiError && reason.code === 'VERSION_CONFLICT') stale.value = true
    }
  }
  finally { if (current === revision) saving.value = false }
}
const names = (id: string) => props.data.filters.sales.find(person => person.id === id)?.name ?? id
const records = (row: typeof rows.value[number]) => row.item.commitment.conflicts ?? (row.item.commitment.record ? [row.item.commitment.record] : [])
</script>

<template>
  <section v-if="data.commitments" class="commitments" data-plan-commitments>
    <header><div><h2>{{ copy('Personal commitments and targets', '个人承诺与目标') }}</h2><p>{{ copy('The Manager records each rep’s promise for this period. Scheduled items update from their source records.', '经理记录各销售对本期的承诺；已安排项目随来源记录更新。') }}</p></div><label>{{ copy('Activity', '活动') }}<select v-model="selected" :disabled="saving" data-commitment-metric><option v-for="key in metrics" :key="key" :value="key">{{ label(key) }}</option></select></label></header>
    <p v-if="!data.commitments.allocated" class="note">{{ copy('Personal commitments and targets are not allocated by region, market or equipment. Clear those filters to edit or compare.', '个人承诺及目标未按地域、市场或设备分配。清除这些筛选后可编辑和比较。') }}</p>
    <p v-if="selected === 'tests'" class="note">{{ copy('Scheduled counts are Demo projects; commitments and targets count completed test runs. They are different units.', '已安排按 Demo 项目计数；承诺与目标按完成测试轮次计数，单位不同。') }}</p>
    <p v-if="selected === 'quotes'" class="note">{{ copy('Scheduled drafts may already have a published version; commitments and targets count only first publication.', '已安排草稿可能属于换版；承诺与目标只计首次发布。') }}</p>
    <p v-if="selected === 'leads'" class="note">{{ copy('Qualified leads have no scheduled record; use the commitment and target columns.', '合格线索没有对应的已安排记录，使用承诺和目标两列。') }}</p>
    <div class="table-scroll"><table><thead><tr><th>{{ copy('Sales', '销售') }}</th><th>{{ copy('Scheduled', '已安排') }}</th><th>{{ copy('Committed', '承诺') }}</th><th>{{ copy('Period target', '本期目标') }}</th><th>{{ copy('Record', '记录') }}</th></tr></thead><tbody>
      <tr v-if="team" data-commitment-team><th>{{ copy('Selected team', '当前范围合计') }}</th><td>{{ metricText(team.scheduled, locale) }}</td><td>{{ metricText(team.commitment, locale) }}<small v-if="team.commitment.missing?.length">{{ copy('Missing', '缺少') }} {{ team.commitment.missing.length }}</small></td><td>{{ metricText(team.target, locale) }}</td><td>—</td></tr>
      <tr v-for="row in rows" :key="row.id" :data-commitment-owner="row.id">
        <th>{{ row.name }}</th><td><button v-if="selected !== 'leads' && data.filters.sales.some(person => person.id === row.id)" :disabled="saving" @click="emit('details', row.id, selected)">{{ metricText(row.item.scheduled, locale) }}</button><span v-else>{{ metricText(row.item.scheduled, locale) }}</span></td>
        <td>{{ metricText(row.item.commitment, locale) }}</td><td>{{ metricText(row.item.target, locale) }}</td>
        <td>
          <p v-if="row.item.commitment.conflicts?.length" data-commitment-conflict>{{ copy('Multiple records were preserved after a user merge. Ask an administrator to reconcile the records below before editing; the total remains unknown.', '用户合并后保留了多条承诺。请管理员核对下列记录后再编辑；合计暂时无法确定。') }}</p>
          <button v-else-if="row.canEdit" :disabled="saving" data-commitment-edit @click="open(row)">{{ copy('Edit commitment', '填写承诺') }}</button>
          <div v-for="record in records(row)" :key="record.id" :data-commitment-record="record.id">
            <p v-if="row.item.commitment.conflicts?.length">{{ copy('Record', '记录') }}: {{ record.id }} · {{ copy('Count', '数量') }}: {{ record.value }}</p>
            <small>{{ names(record.modifiedBy) }} · {{ formatDisplayDateTime(record.modified) }}</small><p>{{ record.note }}</p>
            <details v-if="data.commitments.history[record.id]?.length"><summary>{{ copy('Recent changes (up to 20)', '最近修改（最多 20 条）') }}</summary><ul><li v-for="entry in data.commitments.history[record.id]" :key="entry.id">{{ names(entry.actor) }} · {{ formatDisplayDateTime(entry.at) }}<p v-for="change in entry.changes.filter(change => ['commitment_value', 'note'].includes(change[0]))" :key="change[0]">{{ change[0] === 'note' ? copy('Note', '备注') : copy('Count', '数量') }}: {{ change[1] ?? '—' }} → {{ change[2] ?? '—' }}</p></li></ul></details>
          </div>
        </td>
      </tr>
    </tbody></table></div>
    <form v-if="editing" @submit.prevent="save" data-commitment-form><h3>{{ editing.name }} · {{ label(selected) }} · {{ data.period.start }} — {{ data.period.end }}</h3><label>{{ copy('Committed count (0 is a recorded promise)', '承诺数量（0 也表示明确承诺）') }}<input v-model="value" inputmode="numeric" required :disabled="saving" data-commitment-value /></label><label>{{ copy('Meeting note', '会议备注') }}<textarea v-model="note" maxlength="1000" :disabled="saving" /></label><p v-if="error" role="alert">{{ error }} <button v-if="stale" type="button" :disabled="saving" @click="editing = undefined; emit('reload')">{{ copy('Discard draft and reload plan', '放弃草稿并重新加载计划') }}</button></p><div><button type="submit" :disabled="!valid || saving || stale">{{ copy('Save', '保存') }}</button><button type="button" :disabled="saving" @click="editing = undefined; error = ''">{{ copy('Close', '关闭') }}</button></div></form>
  </section>
</template>

<style scoped>
.commitments{border:1px solid var(--crm-line);border-radius:9px;background:white;padding:18px;margin-bottom:14px}header{display:flex;justify-content:space-between;gap:15px;align-items:start}h2{font-size:16px;margin:0}p,.note{font-size:12px;color:var(--crm-text-muted);line-height:1.5}table{width:100%;border-collapse:collapse;font-size:12px}td,th{text-align:left;padding:10px;border-bottom:1px solid var(--crm-line);vertical-align:top}.table-scroll{overflow:auto}td small{display:block;color:var(--crm-text-muted)}button,select,input,textarea{border:1px solid var(--crm-line);border-radius:5px;padding:6px;background:white}button:disabled{opacity:.5}form{padding:14px;background:var(--crm-surface-muted);display:grid;gap:10px;margin-top:12px}form label{display:grid;gap:5px;font-size:12px}form h3{font-size:13px;margin:0}form button{margin-right:8px}[role=alert]{color:var(--crm-danger)}details p{white-space:pre-wrap;overflow-wrap:anywhere}
</style>
