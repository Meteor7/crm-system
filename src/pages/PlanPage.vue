<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight, RefreshCw } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { labels, metricText, nextPeriodStart } from '@/features/cockpit/presentation'
import RegionSelect from '@/features/cockpit/RegionSelect.vue'
import { cockpitRoute, pickScope, planStart, readCockpitQuery, reviewAnchorForPlan, type CockpitContext } from '@/features/cockpit/scope'
import type { Metric, PeriodKind, ReviewDto } from '@/features/cockpit/types'
import type { PlanDto, PlanDetails, PlanItem, PlanKind, PlanMetric, PlanMoney, PlanQuery } from '@/features/cockpit/plan-types'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const brandIconUrl = `${import.meta.env.BASE_URL}brand/planck-icon.png`
const app = useAppStore(), router = useRouter()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const label = (key: string) => labels[key]?.[locale.value === 'en-US' ? 1 : 0] ?? key
const kindLabel = (kind: Exclude<PlanMetric, 'overdue'>) => ({ all: copy('All plans', '全部计划'), visits: copy('Customer visits planned', '计划拜访'), tests: copy('Demo tests in Plan', '计划测试'), actions: copy('Actions due', '到期行动'), po: copy('Expected PO this period', '本期预计 PO') })[kind]
const kinds: PlanKind[] = ['visits', 'tests', 'actions', 'po']
const periods: PeriodKind[] = ['week', 'month', 'quarter', 'year']
const route = useRoute()
// Opened from Review, Warnings or Opportunities with their scope and Review period (see cockpit/scope.ts):
// an explicit anchor already names the Plan period; a Review anchor alone is advanced once to the next period.
const incoming = readCockpitQuery(route.query)
const query = reactive<PlanQuery>({ ...planStart(incoming), ...incoming.scope })
// The way back restores the originating Review period while Plan still shows the period right after it.
const context = computed<CockpitContext>(() => ({ ...pickScope(query), period: query.period,
  reviewAnchor: reviewAnchorForPlan(query.period, query.anchor, incoming.reviewAnchor) }))
const reviewRoute = computed(() => cockpitRoute('review', context.value))
const warningsRoute = computed(() => cockpitRoute('warnings', context.value))
const boardRoute = computed(() => cockpitRoute('board', context.value))
const manager = computed(() => app.bootstrap?.user.role === 'Manager')
const data = ref<PlanDto | null>(null), items = ref<PlanDetails | null>(null)
const filters = ref<ReviewDto['filters']>({ sales: [], markets: [], regions: [], regionReady: false, equipment: [] })
const loading = ref(false), itemLoading = ref(false)
const error = useLocaleMessage(), itemError = useLocaleMessage()
const metric = ref<Exclude<PlanMetric, 'overdue'>>('all'), groupBy = ref<'day' | 'sales' | 'market'>('day')
const page = ref(1)
const agendaRoot = ref<HTMLElement | null>(null)
let cardObserver: ResizeObserver | undefined
watch([items, groupBy, locale], () => {
  cardObserver?.disconnect()
  const root = agendaRoot.value
  if (!root) return
  const contents = [...root.querySelectorAll<HTMLElement>('.agenda-item-content')]
  const sizeCards = () => {
    const height = Math.max(0, ...contents.map(content => {
      const style = getComputedStyle(content.parentElement!)
      return content.getBoundingClientRect().height + parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
        + parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth)
    }))
    root.style.setProperty('--agenda-card-height', `${Math.ceil(height)}px`)
  }
  if (typeof ResizeObserver !== 'undefined') {
    cardObserver = new ResizeObserver(sizeCards)
    contents.forEach(content => cardObserver!.observe(content))
  }
  sizeCards()
}, { flush: 'post' })
let revision = 0, detailRevision = 0
const fmt = (m?: Metric) => m?.state === 'insufficient' && m.reason === 'missing_date'
  ? copy('Insufficient data: some records have no date', '数据不足：部分记录未填写日期')
  : m ? metricText(m, locale.value) : '—'
const ownerName = (id?: string | null) => filters.value.sales.find(p => p.id === id)?.name || id || copy('Unassigned', '未分配')
const moneyText = (amounts: PlanMoney[], incomplete: boolean) => [
  ...amounts.map(m => `${m.currency} ${Number(m.value).toLocaleString(locale.value, { maximumFractionDigits: 2 })}`),
  ...(incomplete ? [copy('Some amounts unavailable', '部分金额数据不足')] : []),
].join(' · ') || '—'
const rowMoney = (row: PlanItem) => row.amount != null && row.currency ? moneyText([{ value: row.amount, currency: row.currency }], false) : copy('Amount unavailable', '金额数据不足')
const dateLabel = (date: string) => new Date(`${date}T00:00:00Z`).toLocaleDateString(locale.value, { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })
const maxMarket = computed(() => Math.max(1, ...data.value?.markets.map(m => Number(m.activities.value ?? 0)) ?? []))
function sourceRoute(row: PlanItem) {
  if (row.kind === 'visits') return { path: `/visits/${encodeURIComponent(row.id)}` }
  if (row.kind === 'tests') return { path: '/evaluations', query: { focus: row.evaluationId } }
  return { path: `/opportunities/${encodeURIComponent(row.opportunityId ?? row.id)}` }
}
const outsidePeriod = (row: PlanItem) => row.kind === 'tests' && (!row.date || !!data.value && (row.date < data.value.period.start || row.date > data.value.period.end))
const groups = computed(() => {
  const result = new Map<string, { key: string; title: string; rows: PlanItem[]; outsidePeriod?: boolean }>()
  const add = (key: string, title: string) => { if (!result.has(key)) result.set(key, { key, title, rows: [] }) }
  if (groupBy.value === 'day' && data.value?.period.kind === 'week') {
    const start = new Date(`${data.value.period.start}T00:00:00Z`)
    for (let i = 0; i < 7; i++) { const date = new Date(start); date.setUTCDate(start.getUTCDate() + i); const key = date.toISOString().slice(0, 10); add(key, dateLabel(key)) }
  }
  for (const row of items.value?.items ?? []) {
    if (row.carryover) continue
    const extra = groupBy.value === 'day' && outsidePeriod(row)
    const key = extra ? 'unscheduled' : groupBy.value === 'day' ? row.date! : groupBy.value === 'sales' ? row.salesOwner ?? '' : row.market ?? ''
    const title = extra ? copy('Unscheduled / in progress', '待排期／进行中') : groupBy.value === 'day' ? dateLabel(row.date!) : groupBy.value === 'sales' ? ownerName(row.salesOwner) : row.market || copy('Market unavailable', '市场未填写')
    add(key, title); result.get(key)!.rows.push(row)
    if (extra) result.get(key)!.outsidePeriod = true
  }
  return [...result.values()].sort((a, b) => groupBy.value === 'day' ? a.key.localeCompare(b.key) : 0)
})
async function loadItems() {
  const id = ++detailRevision
  items.value = null; itemError.value = ''; itemLoading.value = false
  if (!manager.value || !data.value) return
  itemLoading.value = true
  try {
    const response = await props.apiClient.getPlanDetails({ ...query, anchor: data.value.period.start, metric: metric.value, page: page.value, pageSize: 50, includeOverdue: false })
    if (id === detailRevision && manager.value) items.value = response.data
  } catch (reason) { if (id === detailRevision) itemError.value = requestErrorMessage(reason) }
  finally { if (id === detailRevision) itemLoading.value = false }
}
async function load() {
  const id = ++revision
  detailRevision++; data.value = null; items.value = null; error.value = ''; itemError.value = ''; itemLoading.value = false
  if (!manager.value) { loading.value = false; return }
  loading.value = true
  try {
    const response = await props.apiClient.getPlan({ ...query })
    if (id !== revision || !manager.value) return
    data.value = response.data; filters.value = response.data.filters; page.value = 1
    void loadItems()
  } catch (reason) { if (id === revision) error.value = requestErrorMessage(reason) }
  finally { if (id === revision) loading.value = false }
}
function selectPeriod(value: PeriodKind) {
  if (query.period === value) return
  query.period = value; query.anchor = nextPeriodStart(value)
}
function resetFilters() { query.region = ''; query.sales = ''; query.market = ''; query.equipment = '' }
function selectMetric(value: Exclude<PlanMetric, 'overdue'>) { metric.value = value; page.value = 1; void loadItems() }
function changePage(value: number) { page.value = value; void loadItems() }
watch(() => [app.bootstrap?.user.role, app.identityRevision, query.period, query.anchor, query.sales, query.region, query.market, query.equipment], () => {
  if (app.bootstrap && !manager.value) {
    revision++; detailRevision++; data.value = null; items.value = null
    filters.value = { sales: [], markets: [], regions: [], regionReady: false, equipment: [] }
    void router.replace('/calendar')
  } else if (manager.value) void load()
}, { immediate: true })
onMounted(() => app.loadBootstrap(props.apiClient))
onBeforeUnmount(() => { revision++; detailRevision++; cardObserver?.disconnect() })
</script>

<template>
  <div v-if="manager" class="plan-page" data-testid="plan-page" :aria-busy="loading">
    <div class="plan-masthead">
      <div class="plan-header-art" aria-hidden="true"><img :src="brandIconUrl" alt="" width="512" height="512" draggable="false" /></div>
    <header class="plan-heading">
      <div><h1>Plan <span>· {{ copy('Upcoming activity', '周期计划') }}</span></h1><p>{{ data ? `${data.period.start} — ${data.period.end}` : query.anchor }}</p></div>
      <p class="heading-note">{{ copy('Period activities and active Demo tests', '所选周期活动与当前计划测试') }}<small>{{ copy('Tests follow the current stage; other activity follows the selected period', '测试按当前阶段统计；其他活动按所选周期') }}</small></p>
    </header>
    <nav class="plan-controls" :aria-label="copy('Plan filters', '计划筛选')">
      <div class="view-tabs"><RouterLink :to="reviewRoute">Review</RouterLink><strong aria-current="page">Plan</strong><RouterLink :to="warningsRoute">Warnings</RouterLink><RouterLink :to="boardRoute">Opportunities</RouterLink></div>
      <label><span class="filter-name">{{ copy('Region', '区域') }}</span><RegionSelect v-model="query.region" :regions="filters.regions" :parents="filters.regionParents" :disabled="!filters.regionReady" :all-label="copy('All regions', '全部区域')" /></label>
      <label><span class="filter-name">{{ copy('Sales', '销售') }}</span><select v-model="query.sales" aria-label="Sales"><option value="">{{ copy('All sales reps', '全部销售') }}</option><option v-for="person in filters.sales" :key="person.id" :value="person.id">{{ person.name }}</option></select></label>
      <label><span class="filter-name">{{ copy('Market', '市场') }}</span><select v-model="query.market" aria-label="Market"><option value="">{{ copy('All markets', '全部市场') }}</option><option v-for="market in filters.markets" :key="market" :value="market">{{ market }}</option></select></label>
      <label><span class="filter-name">{{ copy('Equipment', '设备') }}</span><select v-model="query.equipment" aria-label="Equipment"><option value="">{{ copy('All equipment', '全部设备') }}</option><option v-for="equipment in filters.equipment ?? []" :key="equipment" :value="equipment">{{ equipment }}</option></select></label>
      <button type="button" class="filter-reset" data-testid="plan-filter-reset" :disabled="!query.region && !query.sales && !query.market && !query.equipment" @click="resetFilters">{{ copy('Reset filters', '重置筛选') }}</button>
      <div class="period-controls"><div class="segmented"><button v-for="period in periods" :key="period" :aria-pressed="query.period === period" @click="selectPeriod(period)">{{ label(period) }}</button></div><button :disabled="!data || loading" :aria-label="copy('Previous period', '上一周期')" @click="query.anchor = data!.period.previousAnchor"><ChevronLeft :size="15" /></button><input v-model="query.anchor" type="date" :aria-label="copy('Period date', '周期日期')" /><button :disabled="!data || loading" :aria-label="copy('Next period', '下一周期')" @click="query.anchor = data!.period.nextAnchor"><ChevronRight :size="15" /></button><button :disabled="loading" :aria-label="copy('Refresh', '刷新')" @click="load"><RefreshCw :size="14" /></button></div>
    </nav>
    </div>
    <div v-if="error" class="error-banner" role="alert"><strong>{{ copy('Plan could not be loaded', '暂时无法读取计划') }}</strong><p>{{ error }}</p><p>{{ copy('If Plan has not been enabled on this server, its business APIs need to be deployed first.', '若当前服务器尚未启用 Plan，需要先部署对应业务接口。') }}</p><button @click="load">{{ copy('Retry', '重试') }}</button></div>
    <section class="plan-kpis" :aria-label="copy('Period summary', '周期概览')">
      <button v-for="kind in kinds" :key="kind" :class="['kpi', kind, { selected: metric === kind }]" :disabled="!data || loading" :aria-pressed="metric === kind" @click="selectMetric(kind)">
        <span>{{ kindLabel(kind) }}</span><strong :class="{ unavailable: data?.summary[kind].state !== 'ready' }">{{ loading ? '…' : fmt(data?.summary[kind]) }}</strong>
        <small v-if="kind === 'visits'">{{ copy('Visits with a planned date', '按已安排的拜访日期') }}</small><small v-else-if="kind === 'tests'">{{ copy('Preparation complete, before Internal Review', '两项准备完成，尚未进入内部审核') }}</small><small v-else-if="kind === 'actions'">{{ copy('Incomplete actions due in this period', '本期到期且尚未完成的行动') }}</small><small v-else>{{ data ? moneyText(data.poAmounts, data.poAmountIncomplete) : copy('Opportunity estimates', '商机预计金额') }}</small>
      </button>
    </section>
    <div class="plan-grid">
      <div class="plan-brand-art" aria-hidden="true"><img :src="brandIconUrl" alt="" width="512" height="512" draggable="false" /></div>
      <section class="panel agenda-panel" :aria-busy="itemLoading">
        <header class="panel-heading"><div><h2>{{ copy('Agenda', '计划日程') }}</h2><p>{{ copy('Period schedule and Demo tests before Internal Review', '本期日程及尚未进入内部审核的 Demo 测试') }}</p><p v-if="data?.equipmentUnclassified && (data.equipmentUnclassified.visits || data.equipmentUnclassified.tests)" data-unclassified>{{ copy('Not linked to an opportunity, so not counted under this equipment:', '未关联商机、不计入该设备：') }} {{ data.equipmentUnclassified.visits }} {{ copy(data.equipmentUnclassified.visits === 1 ? 'visit' : 'visits', '条拜访') }} · {{ data.equipmentUnclassified.tests }} {{ copy(data.equipmentUnclassified.tests === 1 ? 'Demo test' : 'Demo tests', '个 Demo 测试') }}</p></div><div class="agenda-tools"><label>{{ copy('Activity', '类型') }}<select :value="metric" aria-label="Activity type" :disabled="!data" @change="selectMetric(($event.target as HTMLSelectElement).value as Exclude<PlanMetric, 'overdue'>)"><option v-for="key in ['all', ...kinds] as Exclude<PlanMetric, 'overdue'>[]" :key="key" :value="key">{{ kindLabel(key) }}</option></select></label><label>{{ copy('Group by', '分组') }}<select v-model="groupBy" aria-label="Group by"><option value="day">{{ copy('Day', '日期') }}</option><option value="sales">{{ copy('Sales', '销售') }}</option><option value="market">{{ copy('Market', '市场') }}</option></select></label></div></header>

        <p v-if="itemLoading || loading" class="empty-state" role="status">{{ copy('Loading plans…', '正在读取计划…') }}</p>
        <div v-else-if="itemError" class="empty-state" role="alert"><p>{{ itemError }}</p><button @click="loadItems">{{ copy('Retry', '重试') }}</button></div>
        <div v-else-if="items && groups.length" ref="agendaRoot" class="agenda-scroll"><div class="agenda-columns" :class="{ weekly: groupBy === 'day' && data?.period.kind === 'week' }"><section v-for="group in groups" :key="group.key" class="agenda-day" :class="{ 'outside-period': group.outsidePeriod }"><h3><span>{{ group.title }}</span><b>{{ group.rows.length }}</b></h3><RouterLink v-for="row in group.rows" :key="`${row.kind}:${row.id}`" :to="sourceRoute(row)" :class="['agenda-item', row.kind]"><div class="agenda-item-content"><strong>{{ row.title }}</strong><span>{{ row.customer }}</span><small>{{ kindLabel(row.kind) }} · {{ ownerName(row.salesOwner) }}</small><small v-if="row.kind === 'actions'">{{ copy('Assigned to', '执行人') }} · {{ row.actionOwnerName?.trim() || ownerName(row.actionOwner) }}</small><small v-if="row.kind === 'tests'">{{ row.status === 'Testing' ? copy('Testing', '测试中') : copy('Ready to test', '准备就绪') }}</small><small v-if="groupBy !== 'day' || outsidePeriod(row)">{{ row.date ? (row.kind === 'tests' ? copy('Test deadline: ', '测试截止：') : '') + row.date : copy('Date not set', '尚未排期') }}</small><small v-if="row.market">{{ row.market }}</small><small v-if="row.kind === 'po'">{{ rowMoney(row) }}</small></div></RouterLink><p v-if="!group.rows.length" class="empty-day">{{ copy('No items on this page', '本页无安排') }}</p></section></div></div>
        <p v-else class="empty-state">{{ data ? copy('No matching plans', '暂无符合条件的计划') : copy('Waiting for plan data', '等待读取计划数据') }}</p>
        <footer class="agenda-footer"><div class="legend"><span v-for="kind in kinds" :key="kind" :class="kind">{{ kindLabel(kind) }}</span></div><div v-if="items" class="pagination"><span>{{ items.total }} {{ copy('items · grouped on this page', '条 · 按本页记录分组') }}</span><button :disabled="itemLoading || items.page <= 1" :aria-label="copy('Previous page', '上一页')" @click="changePage(items.page - 1)"><ChevronLeft :size="14" /></button><span>{{ items.page }}</span><button :disabled="itemLoading || items.page * items.pageSize >= items.total" :aria-label="copy('Next page', '下一页')" @click="changePage(items.page + 1)"><ChevronRight :size="14" /></button></div></footer>
      </section>

        <section class="panel sales-panel"><header class="panel-heading"><div><h2>{{ copy('Planned activity by sales rep', '销售计划汇总') }}</h2><p>{{ copy('Period activity, active Demo tests and expected PO', '本期活动、当前计划测试与预计 PO') }}</p></div></header><div class="table-scroll"><table class="cockpit-sales-table"><thead><tr><th>{{ copy('Sales rep', '销售') }}</th><th>{{ copy('Visits', '拜访') }}</th><th>{{ copy('Tests', '测试') }}</th><th>{{ copy('Actions', '行动') }}</th><th>{{ copy('Expected PO', '预计 PO') }}</th></tr></thead><tbody><tr v-for="person in data?.sales ?? []" :key="person.id ?? 'unassigned'"><th>{{ person.name || ownerName(person.id) }}</th><td>{{ fmt(person.visits) }}</td><td>{{ fmt(person.tests) }}</td><td>{{ fmt(person.actions) }}</td><td><strong>{{ fmt(person.po) }}</strong><small>{{ moneyText(person.poAmounts, person.poAmountIncomplete) }}</small></td></tr></tbody></table></div><p v-if="!data?.sales.length" class="empty-state">{{ data ? copy('No scheduled activity', '暂无计划记录') : '—' }}</p></section>
        <section class="panel po-panel"><header class="panel-heading"><div><h2>{{ kindLabel('po') }}</h2><p>{{ copy('Expected PO date recorded on the opportunity', '按商机已填写的预计 PO 日期') }}</p></div><button :disabled="!data" class="text-link" @click="selectMetric('po')">{{ copy('View all', '查看全部') }}</button></header><div class="table-scroll"><table><thead><tr><th>{{ copy('Customer / Opportunity', '客户 / 商机') }}</th><th>{{ copy('Estimate', '预计金额') }}</th><th>{{ copy('Probability', '概率') }}</th><th>{{ copy('Expected date', '预计日期') }}</th></tr></thead><tbody><tr v-for="row in data?.expectedPO.items ?? []" :key="row.id"><td><RouterLink :to="sourceRoute(row)"><strong>{{ row.customer }}</strong><small>{{ row.title }}</small></RouterLink><small>{{ ownerName(row.salesOwner) }}</small></td><td>{{ rowMoney(row) }}</td><td><span v-if="row.probabilityLevel" class="probability" :class="row.probabilityLevel">{{ label(row.probabilityLevel) }}</span><span v-else>—</span></td><td>{{ row.date }}</td></tr></tbody></table></div><p v-if="!data?.expectedPO.items.length" class="empty-state">{{ data ? copy('No expected PO in this period', '本期暂无预计 PO') : '—' }}</p><footer class="panel-note">{{ copy('Unweighted opportunity estimates; excludes PO already received and lost opportunities.', '金额为未加权商机预计值；不含已收到 PO 或已丢单的商机。') }}</footer></section>
      <section class="panel market-panel"><header class="panel-heading"><div><h2>{{ copy('By market', '按市场汇总') }}</h2><p>{{ copy('Planned activity · expected PO estimates', '计划活动数 · 预计 PO 金额') }}</p></div></header><div v-if="data?.markets.length" class="market-list"><article v-for="market in data.markets" :key="market.name ?? 'unknown'"><div><strong>{{ market.name || copy('Market unavailable', '市场未填写') }}</strong><b>{{ fmt(market.activities) }}</b></div><div class="bar-track"><span v-if="market.activities.state === 'ready'" :style="{ width: `${Number(market.activities.value) / maxMarket * 100}%` }"></span></div><p>{{ fmt(market.po) }} {{ copy('expected PO', '个预计 PO') }}</p><small>{{ moneyText(market.poAmounts, market.poAmountIncomplete) }}</small></article></div><p v-else class="empty-state">{{ data ? copy('No market activity', '暂无市场计划记录') : '—' }}</p><footer class="panel-note">{{ copy('Activity = period visits + active Demo tests + period actions. Expected PO is counted separately.', '活动数为本期拜访、当前计划测试及本期行动之和；预计 PO 单独统计。') }}</footer></section>
    </div>
    <footer class="plan-footer"><strong>QIHENG DEMO</strong><span>{{ copy('Shanghai time · current planning status', '上海时区 · 当前排期状态') }}<template v-if="data"> · {{ copy('Updated', '更新于') }} {{ new Date(data.asOf).toLocaleString(locale, { timeZone: 'Asia/Shanghai' }) }}</template></span></footer>
  </div>
</template>

<style scoped src="@/features/cockpit/plan.css"></style>

<style scoped src="@/features/cockpit/sales-table.css"></style>
