<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api as defaultApi, type CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { readAllPages } from '@/features/shared/read-all-pages'
import type { EventDto, EventInput } from '@/features/events/types'
import type { AccountSummaryDto } from '@/types/crm'
import type { StrategyOpportunityDto } from '@/types/workspaces'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore(), route = useRoute(), { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const rows = ref<EventDto[]>([]), total = ref(0), page = ref(1), search = ref('')
const accounts = ref<AccountSummaryDto[]>([]), opportunities = ref<StrategyOpportunityDto[]>([])
const regions = ref<string[]>([]), markets = ref<string[]>([]), equipment = ref<string[]>([])
const loading = ref(false), busy = ref(false), editing = ref(false), choicesLoading = ref(false)
const selected = ref<EventDto | null>(null), error = useLocaleMessage(), formError = useLocaleMessage()
const blank = (): EventInput => ({ title: '', owner: app.bootstrap?.user.role === 'Sales' ? app.bootstrap.user.id : '', startDate: '', endDate: '', status: 'Planned', accountId: '', opportunityId: '', region: '', market: '', equipment: '', note: '' })
const draft = reactive<EventInput>(blank())
const owners = computed(() => app.bootstrap?.personnel?.filter(p => p.role === 'Sales' && p.availableForAssignment) ?? [])
const permitted = computed(() => app.can('event:view'))
const accountOptions = computed(() => accounts.value.filter(account => account.owner === draft.owner || account.visibility === 'Public'))
const opportunityOptions = computed(() => opportunities.value.filter(opp => opp.accountId === draft.accountId && opp.owner === draft.owner))
const person = (id: string) => app.bootstrap?.personnel?.find(p => p.id === id)?.name || id
const statusLabel = (status: EventInput['status']) => ({ Planned: copy('Planned', '计划中'), Done: copy('Done', '已完成'), Cancelled: copy('Cancelled', '已取消') })[status]
let revision = 0, formRevision = 0
async function load() {
  const token = ++revision
  if (!permitted.value) return
  loading.value = true; error.value = ''
  try {
    const response = await props.apiClient.listEvents({ page: page.value, pageSize: 20, search: search.value })
    if (token === revision) { rows.value = response.data.items; total.value = response.meta?.total ?? rows.value.length }
  } catch (reason) { if (token === revision) error.value = requestErrorMessage(reason) }
  finally { if (token === revision) loading.value = false }
}
async function edit(row?: EventDto) {
  const token = ++formRevision
  selected.value = row ?? null; Object.assign(draft, row ?? blank()); editing.value = true; formError.value = ''; choicesLoading.value = true
  try {
    const [customers, opps, regionOptions, marketOptions, equipmentOptions] = await Promise.all([
      readAllPages((page, pageSize) => props.apiClient.listAccounts({ page, pageSize })),
      readAllPages((page, pageSize) => props.apiClient.listStrategyOpportunities({ page, pageSize })),
      props.apiClient.listAccountRegions(), props.apiClient.listAccountSegments(), props.apiClient.listEquipmentTypes(),
    ])
    if (token === formRevision) { accounts.value = customers; opportunities.value = opps; regions.value = regionOptions.data; markets.value = marketOptions.data; equipment.value = equipmentOptions.data }
  } catch (reason) { if (token === formRevision) formError.value = requestErrorMessage(reason) }
  finally { if (token === formRevision) choicesLoading.value = false }
}
function cancel() { formRevision++; editing.value = false; choicesLoading.value = false; formError.value = '' }
function ownerChanged() { draft.accountId = ''; draft.opportunityId = '' }
function accountChanged() { draft.opportunityId = ''; draft.region = ''; draft.market = ''; draft.equipment = '' }
async function save() {
  if (busy.value || choicesLoading.value || !app.can('event:write')) return
  busy.value = true; formError.value = ''
  const token = formRevision
  // Select only editable inputs; fetched DTO ids and completion snapshots never go back as input.
  const input = Object.fromEntries(Object.keys(blank()).map(key => [key, draft[key as keyof EventInput]])) as unknown as EventInput
  try {
    await props.apiClient.saveEvent(input, selected.value?.id, selected.value?.modified)
    if (token === formRevision) { cancel(); await load() }
  } catch (reason) { if (token === formRevision) formError.value = requestErrorMessage(reason) }
  finally { busy.value = false }
}
async function reloadSelected() {
  if (!selected.value) return
  const token = formRevision; busy.value = true
  try { const result = await props.apiClient.getEvent(selected.value.id); if (token === formRevision) await edit(result.data) }
  catch (reason) { if (token === formRevision) formError.value = requestErrorMessage(reason) }
  finally { busy.value = false }
}
watch(() => [app.bootstrap?.user.id, permitted.value, route.query.focus], async () => {
  revision++; formRevision++; rows.value = []; total.value = 0; cancel(); loading.value = false
  accounts.value = []; opportunities.value = []
  if (permitted.value) {
    await load()
    if (typeof route.query.focus === 'string') {
      const token = revision
      try { const response = await props.apiClient.getEvent(route.query.focus); if (token === revision) await edit(response.data) }
      catch (reason) { if (token === revision) error.value = requestErrorMessage(reason) }
    }
  }
}, { immediate: true })
onMounted(() => app.loadBootstrap(props.apiClient))
onBeforeUnmount(() => { revision++; formRevision++ })
</script>

<template>
  <main v-if="permitted" class="events-page">
    <header><div><h1>{{ copy('Events', '活动管理') }}</h1><p>{{ copy('Exhibitions and other sales events', '展会及其他销售活动') }}</p></div><button v-if="app.can('event:write')" :disabled="busy || editing" @click="edit()">{{ copy('New event', '新建活动') }}</button></header>
    <form class="search" @submit.prevent="page = 1; load()"><input v-model="search" :aria-label="copy('Search events', '搜索活动')" /><button :disabled="loading">{{ copy('Search', '搜索') }}</button></form>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="loading">{{ copy('Loading…', '正在加载…') }}</p>
    <table v-else><thead><tr><th>{{ copy('Event', '活动') }}</th><th>{{ copy('Dates', '起止日期') }}</th><th>{{ copy('Sales owner', '销售负责人') }}</th><th>{{ copy('Status', '状态') }}</th><th></th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.title }}</td><td>{{ row.startDate }} — {{ row.endDate }}</td><td>{{ person(row.owner) }}</td><td>{{ statusLabel(row.status) }}</td><td><button :disabled="editing || busy" @click="edit(row)">{{ copy('Open', '打开') }}</button></td></tr></tbody></table>
    <p v-if="!loading && !rows.length">{{ copy('No events in this scope', '当前范围暂无活动') }}</p>
    <nav><button :disabled="page <= 1 || loading" @click="page--; load()">{{ copy('Previous', '上一页') }}</button><span>{{ page }} · {{ total }} {{ copy('events', '条') }}</span><button :disabled="page * 20 >= total || loading" @click="page++; load()">{{ copy('Next', '下一页') }}</button></nav>
    <section v-if="editing" class="editor">
      <h2>{{ selected ? copy('Edit event', '编辑活动') : copy('New event', '新建活动') }}</h2>
      <p v-if="choicesLoading">{{ copy('Loading choices…', '正在读取选项…') }}</p>
      <form @submit.prevent="save"><fieldset :disabled="busy || choicesLoading || !app.can('event:write')">
        <label>{{ copy('Title', '主题') }}<input v-model="draft.title" required maxlength="140" data-testid="event-title" /></label>
        <label>{{ copy('Sales owner', '销售负责人') }}<select v-model="draft.owner" required :disabled="app.bootstrap?.user.role === 'Sales'" @change="ownerChanged"><option value="" disabled>{{ copy('Choose sales owner', '选择销售') }}</option><option v-for="owner in owners" :key="owner.id" :value="owner.id">{{ owner.name }}</option><option v-if="draft.owner && !owners.some(owner => owner.id === draft.owner)" :value="draft.owner">{{ person(draft.owner) }}</option></select></label>
        <label>{{ copy('Start date', '开始日期') }}<input v-model="draft.startDate" type="date" required /></label><label>{{ copy('End date', '结束日期') }}<input v-model="draft.endDate" type="date" :min="draft.startDate" required /></label>
        <label>{{ copy('Status', '状态') }}<select v-model="draft.status"><option v-for="status in (['Planned', 'Done', 'Cancelled'] as const)" :key="status" :value="status">{{ statusLabel(status) }}</option></select></label>
        <label>{{ copy('Account (optional)', '客户（可选）') }}<select v-model="draft.accountId" @change="accountChanged"><option value="">{{ copy('Standalone event', '独立活动') }}</option><option v-for="account in accountOptions" :key="account.id" :value="account.id">{{ account.name }}</option><option v-if="draft.accountId && !accountOptions.some(account => account.id === draft.accountId)" :value="draft.accountId">{{ draft.accountId }}</option></select></label>
        <label v-if="draft.accountId">{{ copy('Opportunity (optional)', '商机（可选）') }}<select v-model="draft.opportunityId"><option value="">{{ copy('None', '未关联') }}</option><option v-for="opp in opportunityOptions" :key="opp.id" :value="opp.id">{{ opp.title }}</option><option v-if="draft.opportunityId && !opportunityOptions.some(opp => opp.id === draft.opportunityId)" :value="draft.opportunityId">{{ draft.opportunityId }}</option></select></label>
        <template v-else><label>{{ copy('Region', '地域') }}<select v-model="draft.region"><option value="">{{ copy('Unclassified', '未分类') }}</option><option v-for="value in regions" :key="value">{{ value }}</option></select></label><label>{{ copy('Market', '市场') }}<select v-model="draft.market"><option value="">{{ copy('Unclassified', '未分类') }}</option><option v-for="value in markets" :key="value">{{ value }}</option></select></label><label>{{ copy('Equipment', '设备') }}<select v-model="draft.equipment"><option value="">{{ copy('Unclassified', '未分类') }}</option><option v-for="value in equipment" :key="value">{{ value }}</option></select></label></template>
        <label class="note">{{ copy('Notes', '备注') }}<textarea v-model="draft.note" maxlength="10000" /></label>
      </fieldset><p v-if="selected?.completedAt">{{ copy('Completed at', '完成于') }} {{ new Date(selected.completedAt).toLocaleString(locale, { timeZone: 'Asia/Shanghai' }) }} · {{ copy('Shanghai time', '上海时间') }}</p>
      <p v-if="formError" role="alert">{{ formError }} <button v-if="selected" type="button" :disabled="busy" @click="reloadSelected">{{ copy('Discard edits and reload', '放弃修改并重新加载') }}</button></p>
      <footer><button type="button" :disabled="busy" @click="cancel">{{ copy('Cancel', '取消') }}</button><button v-if="app.can('event:write')" :disabled="busy || choicesLoading || !draft.owner">{{ busy ? copy('Saving…', '保存中…') : copy('Save event', '保存活动') }}</button></footer></form>
    </section>
  </main><p v-else>{{ copy('Events are available to Sales and Managers.', '活动管理仅向销售和经理开放。') }}</p>
</template>

<style scoped>
.events-page{padding:24px;max-width:1300px;margin:auto;color:var(--crm-text)}header,nav,footer,.search{display:flex;align-items:center;gap:12px}header{justify-content:space-between}h1{margin:0}p{color:var(--crm-text-muted)}table{width:100%;border-collapse:collapse;margin:20px 0}td,th{padding:12px;border-bottom:1px solid var(--crm-line);text-align:left}button,input,select,textarea{font:inherit;padding:8px;border:1px solid var(--crm-line);border-radius:6px;background:var(--crm-surface,#fff)}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.editor{margin-top:24px;padding:22px;background:var(--crm-surface,#fff);border:1px solid var(--crm-line);border-radius:10px}fieldset{padding:0;border:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}label{display:flex;flex-direction:column;gap:6px}.note{grid-column:1/-1}textarea{min-height:90px}footer{justify-content:flex-end;margin-top:18px}@media(max-width:700px){fieldset{grid-template-columns:1fr}table{font-size:12px}.events-page{padding:12px}}
</style>
