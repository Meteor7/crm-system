<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import type { CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useI18n, useLocaleMessage } from '@/i18n'
import { formatDisplayDateTime } from '@/domain/time'
import type { QuotationFollowUp, QuotationFollowUpInput, QuotationPlanning } from './types'

const props = defineProps<{ quotationId: string; quotationModified?: string; apiClient: CrmApi; canWrite: boolean }>()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const expanded = ref(false), busy = ref(false), loading = ref(false), editing = ref(false)
const data = ref<QuotationPlanning | null>(null), schedule = ref(''), editingId = ref<string>()
const error = useLocaleMessage()
const draft = reactive<QuotationFollowUpInput>({ title: '', due: '', status: 'Open', note: '' })
const scheduleDirty = computed(() => !!data.value && schedule.value !== (data.value.plannedSendDate ?? ''))
const stale = ref(false)
let refreshPending = false
let revision = 0
watch(() => props.quotationId, () => { revision++; expanded.value = false; data.value = null; editing.value = false; loading.value = false; stale.value = false; refreshPending = false; error.value = '' })
watch(() => props.quotationModified, refreshFromQuotation)
function refreshFromQuotation() {
  if (props.quotationModified === data.value?.modified) return
  if (busy.value) { refreshPending = true; return }
  if (editing.value || scheduleDirty.value) {
    stale.value = true
    error.value = copy('Quotation changed. Your edits are retained; reload before saving.', '报价已更新。输入已保留，请重新加载后再保存。')
  } else if (expanded.value) void load()
  else data.value = null
}
onBeforeUnmount(() => { revision++ })
async function load() {
  const current = ++revision
  loading.value = true; error.value = ''; editing.value = false
  try {
    const response = await props.apiClient.getQuotationPlanning(props.quotationId)
    if (current === revision) { data.value = response.data; schedule.value = response.data.plannedSendDate ?? ''; stale.value = false }
  } catch (reason) { if (current === revision) error.value = requestErrorMessage(reason) }
  finally { if (current === revision) loading.value = false }
}
async function toggle() {
  expanded.value = !expanded.value
  if (expanded.value && !data.value) await load()
}
function edit(row?: QuotationFollowUp) {
  editingId.value = row?.id
  Object.assign(draft, row ? { title: row.title, due: row.due, status: row.status, note: row.note }
    : { title: '', due: '', status: 'Open', note: '' })
  editing.value = true; error.value = ''
}
async function save(kind: 'schedule' | 'followup') {
  if (!data.value || busy.value || loading.value || stale.value || !props.canWrite) return
  busy.value = true; error.value = ''
  const current = revision, quotationId = props.quotationId, modified = data.value.modified
  try {
    const response = kind === 'schedule'
      ? await props.apiClient.saveQuotationSchedule(quotationId, { plannedSendDate: schedule.value || null }, modified)
      : await props.apiClient.saveQuotationFollowUp(quotationId, { ...draft }, editingId.value, modified)
    if (current === revision) {
      data.value = response.data
      schedule.value = response.data.plannedSendDate ?? ''
      if (kind === 'followup') editing.value = false
    }
  } catch (reason) { if (current === revision) error.value = requestErrorMessage(reason) }
  finally { busy.value = false; if (refreshPending) { refreshPending = false; refreshFromQuotation() } }
}
const statusName = (status: QuotationFollowUpInput['status']) => ({ Open: copy('Open', '待跟进'), Done: copy('Done', '已完成'), Cancelled: copy('Cancelled', '已取消') })[status]
</script>

<template>
  <section class="quotation-planning" data-testid="quotation-planning">
    <button type="button" :aria-expanded="expanded" :disabled="busy" @click="toggle">{{ copy('Send plan and follow-ups', '发送计划与报价跟进') }}</button>
    <div v-if="expanded">
      <p v-if="loading">{{ copy('Loading…', '正在加载…') }}</p>
      <p v-if="error" role="alert">{{ error }} <button type="button" :disabled="busy" @click="load">{{ copy('Discard edits and reload', '放弃修改并重新加载') }}</button></p>
      <template v-if="data && !loading">
        <form v-if="canWrite" class="send-plan" @submit.prevent="save('schedule')">
          <label>{{ copy('Planned send date (current draft)', '计划发送日期（当前草稿）') }}<input v-model="schedule" type="date" :disabled="busy || editing" /></label>
          <button type="submit" :disabled="busy || editing || stale">{{ copy('Save send plan', '保存发送计划') }}</button>
          <small>{{ copy('Clear the date to cancel. Publishing completes this plan.', '清空日期可取消计划；发布报价后自动退出待发计划。') }}</small>
        </form>
        <p v-else>{{ copy('Planned send date', '计划发送日期') }}: {{ data.plannedSendDate || '—' }}</p>
        <header><h3>{{ copy('Follow-ups', '报价跟进') }}</h3><button v-if="canWrite" type="button" :disabled="busy || editing || scheduleDirty || stale" @click="edit()">{{ copy('Add follow-up', '新增跟进') }}</button></header>
        <p>{{ copy('Follow-ups require an open published quote. Overdue items carry forward in Plan; completion is recorded when you save Done.', '可跟进开放的已发布报价。逾期项自动结转到 Plan；保存已完成时记录实际完成时间。') }}</p>
        <form v-if="editing" class="followup-form" @submit.prevent="save('followup')">
          <label>{{ copy('Title', '内容') }}<input v-model="draft.title" maxlength="140" required :disabled="busy" data-followup-title /></label>
          <label>{{ copy('Due', '到期日期') }}<input v-model="draft.due" type="date" required :disabled="busy" data-followup-due /></label>
          <label>{{ copy('Status', '状态') }}<select v-model="draft.status" :disabled="busy" data-followup-status><option v-for="status in (['Open', 'Done', 'Cancelled'] as const)" :key="status" :value="status">{{ statusName(status) }}</option></select></label>
          <label>{{ copy('Note', '备注') }}<textarea v-model="draft.note" maxlength="10000" :disabled="busy" /></label>
          <div><button type="submit" :disabled="busy || stale">{{ copy('Save follow-up', '保存跟进') }}</button><button type="button" :disabled="busy" @click="editing = false">{{ copy('Discard edit', '放弃编辑') }}</button></div>
        </form>
        <ul v-else><li v-for="row in data.followUps" :key="row.id"><div><strong>{{ row.title }}</strong><span>{{ row.due }} · {{ statusName(row.status) }}</span><small v-if="row.completedAt">{{ copy('Completed', '完成于') }} {{ formatDisplayDateTime(row.completedAt) }}</small><p v-if="row.note">{{ row.note }}</p></div><button v-if="canWrite" type="button" :disabled="busy || scheduleDirty || stale" @click="edit(row)">{{ copy('Edit', '编辑') }}</button></li></ul>
        <p v-if="!data.followUps.length && !editing">{{ copy('No follow-ups yet.', '尚未安排跟进。') }}</p>
      </template>
    </div>
  </section>
</template>

<style scoped>
.quotation-planning{padding:16px;border:1px solid var(--crm-line);border-radius:10px;background:white;font-size:12px}.quotation-planning button{cursor:pointer;padding:6px 10px;background:white;border:1px solid var(--crm-line);border-radius:6px}.quotation-planning button:disabled{opacity:.5;cursor:default}header,.send-plan,li{display:flex;justify-content:space-between;align-items:center;gap:12px}.send-plan{flex-wrap:wrap;margin:14px 0}.send-plan small{flex-basis:100%}label{display:grid;gap:6px}input,select,textarea{padding:8px;border:1px solid var(--crm-line);border-radius:5px}textarea{min-height:70px}p,small{color:var(--crm-text-muted)}ul{list-style:none;padding:0}li{padding:10px 0;border-top:1px solid var(--crm-line)}li>div{display:grid;gap:5px}li p{margin:0;white-space:pre-wrap}.followup-form{display:grid;gap:12px}.followup-form button{margin-right:8px}[role=alert]{color:var(--crm-danger)}
</style>
