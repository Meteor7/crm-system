<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { CalendarPlus, Search } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { readAllPages } from '@/features/shared/read-all-pages'
import FilterBar from '@/features/shared/FilterBar.vue'
import PaginationControls from '@/features/shared/PaginationControls.vue'
import DataState from '@/design-system/DataState.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import PageHeader from '@/design-system/PageHeader.vue'
import RequiredMark from '@/design-system/RequiredMark.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import { formatDisplayDate } from '@/domain/time'
import type { EventDto, EventInput } from '@/features/events/types'
import type { AccountSummaryDto, Tone } from '@/types/crm'
import type { StrategyOpportunityDto } from '@/types/workspaces'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const app = useAppStore(), route = useRoute(), { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const openingPageSize = 20
const rows = ref<EventDto[]>([]), total = ref(0), page = ref(1), pageSize = ref(openingPageSize), search = ref('')
const showPagination = computed(() => rows.value.length > 0 || pageSize.value !== openingPageSize || page.value > 1)
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
const statusTone: Record<EventInput['status'], Tone> = { Planned: 'info', Done: 'positive', Cancelled: 'neutral' }
// The table shows where an event belongs: a customer, or the region / market / equipment it was filed under.
const scopeLabel = (row: EventDto) => row.accountId ? copy('Customer event', '客户活动') : [row.region, row.market, row.equipment].filter(Boolean).join(' · ') || copy('Standalone event', '独立活动')
let revision = 0, formRevision = 0
async function load() {
  const token = ++revision
  if (!permitted.value) return
  loading.value = true; error.value = ''
  let requestedPage = page.value
  const requestedPageSize = pageSize.value, requestedSearch = search.value
  try {
    while (token === revision) {
      const response = await props.apiClient.listEvents({ page: requestedPage, pageSize: requestedPageSize, search: requestedSearch })
      if (token !== revision) return
      const count = response.meta?.total ?? response.data.items.length
      const lastPage = Math.max(1, Math.ceil(count / requestedPageSize))
      if (requestedPage > lastPage) {
        // Editing the last matching event can remove this page; fetch the last page that still exists.
        // Keep the same revision so a newer search or identity change also supersedes this corrective read.
        requestedPage = lastPage; page.value = lastPage
        continue
      }
      rows.value = response.data.items; total.value = count
      break
    }
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
function runSearch() { page.value = 1; void load() }
function reset() { search.value = ''; runSearch() }
function goPage(target: number) { page.value = target; void load() }
function changePageSize(size: number) { pageSize.value = size; runSearch() }
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
  <div v-if="permitted" class="events-page">
    <PageHeader eyebrow="SALES EVENTS" :title="copy('Events', '活动管理')" :description="copy('Exhibitions and other sales events', '展会及其他销售活动')">
      <button v-if="app.can('event:write')" class="primary-button" type="button" data-testid="new-event" :disabled="busy || editing" @click="edit()"><CalendarPlus :size="15" />{{ copy('New event', '新建活动') }}</button>
    </PageHeader>

    <FilterBar :result-label="copy(`${total} events`, `共 ${total} 条`)" @reset="reset">
      <form class="search-control" role="search" @submit.prevent="runSearch">
        <Search :size="14" aria-hidden="true" />
        <input v-model="search" :aria-label="copy('Search events', '搜索活动')" :placeholder="copy('Search event title', '搜索活动主题')" />
        <button class="secondary-button" :disabled="loading">{{ copy('Search', '搜索') }}</button>
      </form>
    </FilterBar>

    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <DataState v-if="loading && !rows.length" type="loading" />
    <DataState v-else-if="!rows.length && !error" type="empty" :title="copy('No events', '暂无活动')" :message="copy('No events in this scope', '当前范围暂无活动')" />
    <section v-if="rows.length || showPagination" class="events-card">
      <div v-if="rows.length" class="table-scroll">
        <table class="crm-table events-table is-responsive">
          <thead><tr><th>{{ copy('Event', '活动') }}</th><th>{{ copy('Dates', '起止日期') }}</th><th>{{ copy('Sales owner', '销售负责人') }}</th><th>{{ copy('Status', '状态') }}</th><th>{{ copy('Actions', '操作') }}</th></tr></thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id" :data-event-id="row.id" :class="{ focused: row.id === route.query.focus }">
              <td class="event-title" :data-label="copy('Event', '活动')"><div><button class="record-button" type="button" :disabled="editing || busy" @click="edit(row)"><strong>{{ row.title }}</strong></button><small>{{ scopeLabel(row) }}</small></div></td>
              <td class="event-date" :data-label="copy('Dates', '起止日期')">{{ formatDisplayDate(row.startDate) }} — {{ formatDisplayDate(row.endDate) }}</td>
              <td :data-label="copy('Sales owner', '销售负责人')">{{ person(row.owner) }}</td>
              <td :data-label="copy('Status', '状态')"><StatusBadge :label="statusLabel(row.status)" :tone="statusTone[row.status]" /></td>
              <td :data-label="copy('Actions', '操作')"><button class="secondary-button" type="button" :disabled="editing || busy" @click="edit(row)">{{ copy('Open', '打开') }}</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <PaginationControls v-if="showPagination" :page="page" :page-size="pageSize" :opening-page-size="openingPageSize" :total="total" @change="goPage" @page-size-change="changePageSize" />
    </section>

    <ModalShell v-if="editing" class="editor" eyebrow="SALES EVENT" :title="selected ? copy('Edit event', '编辑活动') : copy('New event', '新建活动')" :busy="busy" :busy-label="copy('Saving…', '保存中…')" :submit-label="copy('Save event', '保存活动')" :cancel-label="copy('Cancel', '取消')" :close-label="copy('Close', '关闭')" :submit-disabled="choicesLoading || !draft.owner || !app.can('event:write')" @close="busy || cancel()" @submit="save">
      <p v-if="choicesLoading" class="modal-hint">{{ copy('Loading choices…', '正在读取选项…') }}</p>
      <fieldset class="form-grid" :disabled="busy || choicesLoading || !app.can('event:write')">
        <label class="full"><span>{{ copy('Title', '主题') }}<RequiredMark /></span><input v-model="draft.title" required maxlength="140" data-testid="event-title" /></label>
        <label><span>{{ copy('Sales owner', '销售负责人') }}<RequiredMark /></span><select v-model="draft.owner" required :disabled="app.bootstrap?.user.role === 'Sales'" @change="ownerChanged"><option value="" disabled>{{ copy('Choose sales owner', '选择销售') }}</option><option v-for="owner in owners" :key="owner.id" :value="owner.id">{{ owner.name }}</option><option v-if="draft.owner && !owners.some(owner => owner.id === draft.owner)" :value="draft.owner">{{ person(draft.owner) }}</option></select></label>
        <label>{{ copy('Status', '状态') }}<select v-model="draft.status"><option v-for="status in (['Planned', 'Done', 'Cancelled'] as const)" :key="status" :value="status">{{ statusLabel(status) }}</option></select></label>
        <label><span>{{ copy('Start date', '开始日期') }}<RequiredMark /></span><input v-model="draft.startDate" type="date" required /></label>
        <label><span>{{ copy('End date', '结束日期') }}<RequiredMark /></span><input v-model="draft.endDate" type="date" :min="draft.startDate" required /></label>
        <label :class="{ full: !draft.accountId }">{{ copy('Account (optional)', '客户（可选）') }}<select v-model="draft.accountId" @change="accountChanged"><option value="">{{ copy('Standalone event', '独立活动') }}</option><option v-for="account in accountOptions" :key="account.id" :value="account.id">{{ account.name }}</option><option v-if="draft.accountId && !accountOptions.some(account => account.id === draft.accountId)" :value="draft.accountId">{{ draft.accountId }}</option></select></label>
        <label v-if="draft.accountId">{{ copy('Opportunity (optional)', '商机（可选）') }}<select v-model="draft.opportunityId"><option value="">{{ copy('None', '未关联') }}</option><option v-for="opp in opportunityOptions" :key="opp.id" :value="opp.id">{{ opp.title }}</option><option v-if="draft.opportunityId && !opportunityOptions.some(opp => opp.id === draft.opportunityId)" :value="draft.opportunityId">{{ draft.opportunityId }}</option></select></label>
        <div v-else class="full scope-grid"><label>{{ copy('Region', '地域') }}<select v-model="draft.region"><option value="">{{ copy('Unclassified', '未分类') }}</option><option v-for="value in regions" :key="value">{{ value }}</option></select></label><label>{{ copy('Market', '市场') }}<select v-model="draft.market"><option value="">{{ copy('Unclassified', '未分类') }}</option><option v-for="value in markets" :key="value">{{ value }}</option></select></label><label>{{ copy('Equipment', '设备') }}<select v-model="draft.equipment"><option value="">{{ copy('Unclassified', '未分类') }}</option><option v-for="value in equipment" :key="value">{{ value }}</option></select></label></div>
        <label class="full">{{ copy('Notes', '备注') }}<textarea v-model="draft.note" maxlength="10000" /></label>
      </fieldset>
      <p v-if="selected?.completedAt" class="completed-at">{{ copy('Completed at', '完成于') }} {{ new Date(selected.completedAt).toLocaleString(locale, { timeZone: 'Asia/Shanghai' }) }} · {{ copy('Shanghai time', '上海时间') }}</p>
      <template v-if="formError" #feedback>
        <p class="modal-error" role="alert"><span>{{ formError }}</span><button v-if="selected" class="secondary-button" type="button" :disabled="busy" @click="reloadSelected">{{ copy('Discard edits and reload', '放弃修改并重新加载') }}</button></p>
      </template>
    </ModalShell>
  </div>
  <DataState v-else type="denied" :title="copy('No access', '无权访问')" :message="copy('Events are available to Sales and Managers.', '活动管理仅向销售和经理开放。')" />
</template>

<style scoped>
.search-control{display:flex;width:min(420px,100%);height:34px;align-items:center;gap:7px;padding:0 3px 0 10px;color:var(--crm-text-muted);background:var(--crm-surface);border:1px solid var(--crm-line);border-radius:8px}.search-control input{min-width:0;flex:1;color:var(--crm-text);background:transparent;border:0;outline:0}.search-control .secondary-button{min-height:26px;padding:0 10px;border-radius:6px}
.form-error{margin:0 0 14px;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:9px;font-weight:700}
.events-card{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px}.table-scroll{overflow:auto}.events-table{min-width:760px}.events-table tbody tr.focused{background:var(--crm-teal-soft);box-shadow:inset 3px 0 0 var(--crm-teal)}
.event-title{min-width:220px}.event-title small{display:block;margin-top:4px;color:var(--crm-text-muted)}.record-button{padding:0;color:var(--crm-link);background:transparent;border:0;cursor:pointer;text-align:left}.record-button:not(:disabled):hover{color:var(--crm-link-hover)}.record-button:disabled{cursor:default}.event-date{font-variant-numeric:tabular-nums;white-space:nowrap}.events-table .secondary-button{min-height:30px;padding:0 12px}
.modal-hint{margin:0 0 12px;color:var(--crm-text-muted)}.completed-at{margin:14px 0 0;color:var(--crm-text-muted)}
.form-grid{display:grid;min-width:0;grid-template-columns:1fr 1fr;gap:13px;margin:0;padding:0;border:0}.form-grid label{display:grid;gap:6px;color:var(--crm-text-muted);font-weight:700}.form-grid .full{grid-column:1/-1}.scope-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.form-grid input,.form-grid select,.form-grid textarea{width:100%;min-height:36px;padding:8px 10px;color:var(--crm-text);background:#fff;border:1px solid var(--crm-line);border-radius:8px;outline:0}.form-grid :is(input,select,textarea):focus{border-color:var(--crm-teal)}.form-grid :is(input,select,textarea):disabled{color:var(--crm-text-muted);background:var(--crm-surface)}.form-grid textarea{min-height:90px;resize:vertical}
.modal-error{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 10px;padding:10px 12px;color:var(--crm-danger);background:var(--crm-danger-soft);border-radius:8px;font-weight:700;line-height:1.6}.modal-error button{flex:0 0 auto}
@media(max-width:839px){.search-control{width:100%}.events-table{min-width:0}.event-title{min-width:0}.event-date{white-space:normal}}
@media(max-width:560px){.form-grid,.scope-grid{grid-template-columns:1fr}.form-grid .full{grid-column:auto}.modal-error{align-items:flex-start;flex-direction:column}}
</style>
