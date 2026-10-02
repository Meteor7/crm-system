<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, SlidersHorizontal, TriangleAlert, X } from '@lucide/vue'
import { api as defaultApi, type CrmApi } from '@/api'
import { requestErrorMessage } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import { useI18n, useLocaleMessage } from '@/i18n'
import { detailRoute, labels, metricText, monotoneCurvePath, nextMonday, targetStart } from '@/features/cockpit/presentation'
import ReviewConversionPanel from '@/features/cockpit/ReviewConversionPanel.vue'
import { regionLabel } from '@/domain/regions'
import type { ActivityKey, Metric, PeriodKind, ReviewDetails, ReviewDto, ReviewQuery, TargetInput, ReviewRow } from '@/features/cockpit/types'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const brandIconUrl = `${import.meta.env.BASE_URL}brand/planck-icon.png`
const app = useAppStore()
const router = useRouter()
const route = useRoute()
const { locale } = useI18n()
const copy = (english: string, chinese: string) => locale.value === 'en-US' ? english : chinese
const label = (key: string) => key.startsWith('reached_') ? `${copy('Reached stage', '到达阶段')} · ${labels[key.slice(8)]?.[locale.value === 'en-US' ? 1 : 0] ?? copy('PO received', '已收到 PO')}` : labels[key]?.[locale.value === 'en-US' ? 1 : 0] ?? key
const fmt = (value: Metric, money = false) => metricText(value, locale.value, money)
// The strip keeps one line per the masthead height: a count that is not ready shows as a dash, with the full text in the tooltip.
const stripCount = (value: Metric) => value.state === 'ready' ? fmt(value) : '—'
const activities: ActivityKey[] = ['visits', 'leads', 'tests', 'quotes']
const periods: PeriodKind[] = ['week', 'month', 'quarter', 'year']
// Opened from Warnings with the period and filters this page handed it; the backend validates every value.
const initial = (key: string) => typeof route.query[key] === 'string' ? (route.query[key] as string).trim() : ''
const query = reactive<ReviewQuery>({
  period: periods.includes(initial('period') as PeriodKind) ? initial('period') as PeriodKind : 'week',
  ...(initial('anchor') ? { anchor: initial('anchor') } : {}),
  sales: initial('sales'), market: initial('market'), region: initial('region'), equipment: initial('equipment'),
})
const data = ref<ReviewDto | null>(null)
const filterOptions = ref<ReviewDto['filters']>({ sales: [], markets: [], regions: [], regionReady: false, equipment: [] })
const loading = ref(false)
const error = useLocaleMessage()
const manager = computed(() => app.bootstrap?.user.role === 'Manager')
const pipelineMode = ref<'count' | 'amount'>('count')
let revision = 0
let detailRevision = 0
const detailKey = ref('')
const detailData = ref<ReviewDetails | null>(null)
const detailError = useLocaleMessage()
const detailLoading = ref(false)
const detailsDialog = ref<HTMLDialogElement | null>(null)
const targetDialog = ref<HTMLDialogElement | null>(null)
const targetError = useLocaleMessage()
const saving = ref(false)
const saved = ref(false)
const target = reactive<TargetInput>({ sales: '', metric: 'visits', period: 'week', anchor: '', value: '' })
const currentTarget = computed(() => data.value?.targets.find(r => r.sales === target.sales && r.metric === target.metric && r.period === target.period && r.anchor === target.anchor))
const ownerName = (owner: string | null) => data.value?.filters.sales.find(r => r.id === owner)?.name ?? owner ?? copy('Owner unavailable', '归属数据不足')
const maxPipeline = computed(() => Math.max(1, ...data.value?.pipeline.map(row => Number(row[pipelineMode.value].value ?? 0)) ?? []))
const periodTitle = computed(() => data.value ? `${data.value.period.start} — ${data.value.period.end}` : '')
// The orders card shows the salesperson chosen in the filter bar; it has no selector of its own.
const chartSales = computed(() => query.sales ?? '')
const chartSource = data
const annualTarget = computed(() => chartSource.value?.orders.target.state === 'ready' ? Number(chartSource.value.orders.target.value) : null)
const actualTotal = computed(() => chartSource.value?.orders.actual.state === 'ready' && chartSales.value ? Number(chartSource.value.orders.actual.value) : null)
const chartMaximum = computed(() => Math.max(1, annualTarget.value ?? 0, actualTotal.value ?? 0))
const chartX = (fraction: number) => 45 + fraction * 440
const chartY = (value: number) => 190 - value / chartMaximum.value * 160
// Cumulative order intake: the curve starts at zero, passes through every actual PO date and
// runs flat from the last order to the as-of line.
const actualPath = computed(() => {
  if (actualTotal.value === null || !chartSource.value) return ''
  const orders = chartSource.value.orders
  const points = [{ x: 0, y: 0 }, ...(orders.series ?? []).map(point => ({ x: Number(point.fraction), y: Number(point.cumulative) }))]
  const elapsed = orders.elapsedFraction ?? 0
  if (elapsed > points[points.length - 1].x) points.push({ x: elapsed, y: actualTotal.value })
  return monotoneCurvePath(points.map(point => ({ x: chartX(point.x), y: chartY(point.y) })))
})
const planPath = computed(() => annualTarget.value === null ? '' : `M45 190L485 ${chartY(annualTarget.value).toFixed(1)}`)
const monthLabels = computed(() => Array.from({ length: 12 }, (_, month) => new Date(Date.UTC(2026, month, 1)).toLocaleDateString(locale.value, { month: 'short', timeZone: 'UTC' })))
const curveHover = ref<{ x: number; y: number; amount: number; kind: 'actual' | 'plan' } | null>(null)
const hoverMonth = computed(() => {
  if (!curveHover.value || !chartSource.value) return ''
  const year = Number(new Date(chartSource.value.period.asOf).toLocaleDateString('en-US', { year: 'numeric', timeZone: 'Asia/Shanghai' }))
  const start = Date.UTC(year, 0, 1), days = (Date.UTC(year + 1, 0, 1) - start) / 86400000
  // API fractions count through the end of each business date; round away SVG sampling noise.
  const day = Math.max(0, Math.min(days - 1, Math.round((curveHover.value.x - 45) / 440 * days) - 1))
  return new Date(start + day * 86400000).toLocaleDateString(locale.value, { year: 'numeric', month: 'short', timeZone: 'UTC' })
})
function showCurveAmount(event: PointerEvent, kind: 'actual' | 'plan') {
  const path = event.currentTarget as SVGPathElement
  const matrix = path.getScreenCTM(), svg = path.ownerSVGElement
  if (!matrix || !svg) return
  const pointer = svg.createSVGPoint()
  pointer.x = event.clientX; pointer.y = event.clientY
  const x = pointer.matrixTransform(matrix.inverse()).x
  let low = 0, high = path.getTotalLength()
  if (!high) { curveHover.value = null; return }
  // Read the rendered curve so the amount agrees with its height, including smooth segments.
  for (let i = 0; i < 18; i++) {
    const middle = (low + high) / 2
    if (path.getPointAtLength(middle).x < x) low = middle
    else high = middle
  }
  const point = path.getPointAtLength((low + high) / 2)
  curveHover.value = { x: point.x, y: point.y, kind,
    amount: Math.round(Math.max(0, (190 - point.y) / 160 * chartMaximum.value)) }
}
watch([actualPath, planPath, chartMaximum], () => { curveHover.value = null })
const periodHeading = computed(() => {
  if (!data.value) return copy('Sales review', '销售经营看板')
  const d = new Date(`${data.value.period.start}T00:00:00Z`), year = d.getUTCFullYear()
  if (data.value.period.kind === 'year') return String(year)
  if (data.value.period.kind === 'quarter') return `${year} · Q${Math.floor(d.getUTCMonth() / 3) + 1}`
  if (data.value.period.kind === 'month') return d.toLocaleDateString(locale.value, { year: 'numeric', month: 'long', timeZone: 'UTC' })
  d.setUTCDate(d.getUTCDate() + 3 - (d.getUTCDay() + 6) % 7)
  const week = Math.ceil(((d.getTime() - Date.UTC(d.getUTCFullYear(), 0, 1)) / 86400000 + 1) / 7)
  return `${copy('Week', '第')} ${week}${copy('', '周')}`
})
const millions = (value: number) => `¥${(value / 1000000).toLocaleString(locale.value, { maximumFractionDigits: 2 })}M`
const compactMoney = (m: Metric) => m.state === 'ready' && m.value !== null ? millions(Number(m.value)) : fmt(m, true)
const orderSummary = computed(() => {
  const orders = chartSource.value?.orders
  if (!orders || !chartSales.value) return copy('Actual YTD / annual target', '实际年累计 / 年度目标')
  if (orders.actual.state !== 'ready') {
    const missing = orders.missingAmount?.state === 'ready' && Number(orders.missingAmount.value) > 0 ? `（${orders.missingAmount.value} ${copy('bookings without a CNY amount', '张订单缺人民币金额')}）` : ''
    return `${copy('Actual amount', '实际金额')}：${fmt(orders.actual)}${missing}`
  }
  if (orders.target.state !== 'ready') return `${copy('Annual target', '年度目标')}：${fmt(orders.target)}`
  const actual = Number(orders.actual.value), annual = Number(orders.target.value)
  const attainment = annual > 0 ? `${(actual / annual * 100).toLocaleString(locale.value, { maximumFractionDigits: 1 })}%` : '—'
  const gap = orders.planned.state === 'ready' ? actual - Number(orders.planned.value) : null
  return `${copy('Attainment', '达成率')} ${attainment}${gap === null ? '' : ` · ${copy('vs plan to date', '较计划')} ${gap < 0 ? '−' : '+'}${millions(Math.abs(gap))}`}`
})
// The header carries actual / target / attainment; the chart footer repeats it only where the header is hidden.
const chartCaption = computed(() => chartSource.value && chartSales.value && (query.region || query.market || query.equipment)
  ? copy('Individual targets are not allocated by region, market or equipment', '个人目标不按区域、市场或设备拆分') : '')
function rowAmount(row: ReviewRow) {
  if (row.stage === 'qualified_opportunity') return copy('No value yet', '仅计数量')
  if (row.amount == null || !row.currency) return copy('Insufficient data', '数据不足')
  return `${row.currency} ${Number(row.amount).toLocaleString(locale.value, { maximumFractionDigits: 2 })}`
}
function changePeriod(period: PeriodKind) { query.period = period }

const dateText = (value: string | null | undefined) => value ? new Date(value).toLocaleDateString(locale.value, { timeZone: 'Asia/Shanghai' }) : '—'
// Warnings gets this page's period and filters, so its counts match this banner. The anchor goes along
// whenever it is known (an anchor asked for, or the data), because without one Warnings shows the current
// week while this page shows the last completed one. Until then there is nothing to hand over, so the tab
// is not a link yet; after a failed load it links without an anchor, and Warnings opens the same kind of
// period on its own default date (for a week, the current one).
const warningsRoute = computed(() => ({ path: '/warnings', query: Object.fromEntries(Object.entries({ ...query, anchor: query.anchor || data.value?.period.start }).filter(([, value]) => value)) as Record<string, string> }))
// Post-mortem state of a loss row; empty for rows from a backend without loss reviews.
function lossStatus(row: ReviewRow): { text: string; tone: string } | null {
  if (row.reopenedAt) return { text: copy('Reopened', '已重开'), tone: 'muted' }
  if (row.review?.status === 'reviewed') return { text: copy('Post-mortem done', '已复盘'), tone: 'done' }
  if (row.reviewPending) return row.reviewOverdue ? { text: copy('Post-mortem overdue', '复盘逾期'), tone: 'danger' } : { text: copy('Post-mortem pending', '待复盘'), tone: 'warn' }
  return null
}

async function load() {
  const id = ++revision
  detailRevision++
  targetDialog.value?.close()
  detailsDialog.value?.close()
  detailKey.value = ''
  detailData.value = null
  data.value = null
  if (!manager.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await props.apiClient.getReview({ ...query })
    if (id === revision && manager.value) { data.value = result.data; filterOptions.value = result.data.filters }
  } catch (reason) {
    if (id === revision) error.value = requestErrorMessage(reason)
  } finally {
    if (id === revision) loading.value = false
  }
}
watch(() => [app.bootstrap?.user.role, app.identityRevision, query.period, query.anchor, query.sales, query.market, query.region, query.equipment], () => {
  if (app.bootstrap && !manager.value) {
    revision++; detailRevision++; data.value = null; filterOptions.value = { sales: [], markets: [], regions: [], regionReady: false, equipment: [] }
    detailsDialog.value?.close(); targetDialog.value?.close()
    void router.replace('/calendar')
  } else if (manager.value) void load()
}, { immediate: true })
onMounted(() => app.loadBootstrap(props.apiClient))
onBeforeUnmount(() => { revision++; detailRevision++ })
function step(next: boolean) {
  if (data.value) query.anchor = next ? data.value.period.nextAnchor : data.value.period.previousAnchor
}
async function details(key: string, page = 1) {
  const id = ++detailRevision
  detailKey.value = key
  detailData.value = null
  detailError.value = ''
  detailLoading.value = true
  await nextTick()
  if (id !== detailRevision || !manager.value) return
  if (!detailsDialog.value?.open) detailsDialog.value?.showModal()
  try {
    const result = await props.apiClient.getReviewDetails({ ...query, metric: key, page, pageSize: 20 })
    if (id === detailRevision && manager.value) detailData.value = result.data
  } catch (reason) {
    if (id === detailRevision) detailError.value = requestErrorMessage(reason)
  } finally {
    if (id === detailRevision) detailLoading.value = false
  }
}
function editTargets() {
  if (!query.sales || !data.value || query.market || query.region || query.equipment) return
  target.sales = query.sales
  target.metric = 'visits'
  target.period = data.value.period.kind
  target.anchor = data.value.period.start
  target.value = currentTarget.value?.value ?? ''
  targetError.value = ''; saved.value = false
  targetDialog.value?.showModal()
}
watch(() => [target.metric, target.period, target.anchor], () => {
  target.value = currentTarget.value?.value ?? ''
  saved.value = false
})
function targetPeriodChanged() {
  if (!data.value) return
  if (target.metric === 'orders') target.period = 'year'
  target.anchor = target.period === 'weekly_default' ? nextMonday() : targetStart(data.value.period.start, target.period)
}
async function saveTarget() {
  if (saving.value) return
  const requestRevision = revision
  saving.value = true; targetError.value = ''; saved.value = false
  try {
    const result = await props.apiClient.saveReviewTarget({ ...target, value: String(target.value) }, currentTarget.value?.modified)
    if (!manager.value || requestRevision !== revision) return
    if (data.value) data.value.targets = [...data.value.targets.filter(row => row.id !== result.data.id), result.data]
    const refreshed = await props.apiClient.getReview({ ...query })
    if (manager.value && requestRevision === revision) { data.value = refreshed.data; saved.value = true }
  } catch (reason) { if (manager.value && requestRevision === revision) targetError.value = requestErrorMessage(reason) }
  finally { saving.value = false }
}
</script>

<template>
  <div v-if="manager" class="review-page" data-testid="review-page" :aria-busy="loading">
    <div class="review-masthead">
      <div class="review-header-art" aria-hidden="true"><img :src="brandIconUrl" alt="" width="512" height="512" draggable="false" /></div>
    <header class="review-heading">
      <div class="identity"><h1>{{ periodHeading }}</h1><p>{{ periodTitle || '—' }}</p></div>
      <section class="warning-strip" :aria-label="copy('Warning summary', '预警摘要')"><span class="alert-icon"><TriangleAlert :size="22" /></span><div class="strip-body"><strong>{{ copy('Warnings · attention required', '预警 · 本期需关注') }}</strong><div class="warning-links"><button v-for="warning in data?.warnings" :key="warning.key" :title="warning.count.state === 'ready' ? undefined : `${fmt(warning.count)} · ${label(warning.key)}`" :aria-label="warning.count.state === 'ready' ? undefined : `${fmt(warning.count)} · ${label(warning.key)}`" @click="details(warning.key)">{{ stripCount(warning.count) }} {{ label(warning.key) }}<ChevronRight :size="12" /></button><span v-if="!data">—</span></div><button v-if="data" class="strip-history" data-downgrade-history @click="details('downgrade_history')">{{ copy('Downgrade history', '本期降档记录') }}<ChevronRight :size="12" /></button></div></section>
      <div class="heading-order"><span>{{ copy('Individual annual orders · CNY', '个人年度订单 · CNY') }}</span><strong>{{ chartSource && chartSales ? fmt(chartSource.orders.actual, true) : '—' }} / {{ chartSource && chartSales ? fmt(chartSource.orders.target, true) : '—' }}</strong><small>{{ chartSales ? ownerName(chartSales) : copy('No sales rep selected', '未筛选销售') }}</small><small class="order-summary" :title="orderSummary">{{ orderSummary }}</small></div>
    </header>
    <nav class="review-controls" :aria-label="copy('Review filters', '看板筛选')">
      <strong class="review-tab">Review</strong><RouterLink class="plan-tab" to="/plan">Plan</RouterLink><RouterLink v-if="data || query.anchor || error" class="plan-tab" :to="warningsRoute">Warnings</RouterLink><span v-else class="plan-tab is-disabled" role="link" aria-disabled="true" :title="copy('Available once the page has loaded', '页面加载完成后可用')">Warnings</span><RouterLink class="plan-tab" to="/opportunity-board">Opportunities</RouterLink>
      <label><span class="filter-name">{{ copy('Region', '区域') }}</span><select v-model="query.region" :disabled="loading || !filterOptions.regionReady" aria-label="Region"><option value="">{{ filterOptions.regionReady ? copy('All regions', '全部区域') : copy('Region migration pending', '区域待迁移') }}</option><option v-for="region in filterOptions.regions" :key="region" :value="region">{{ regionLabel(region, locale) }}</option></select></label>
      <label><span class="filter-name">{{ copy('Sales', '销售') }}</span><select v-model="query.sales" :disabled="loading" aria-label="Sales"><option value="">{{ copy('All sales', '全部销售') }}</option><option v-for="person in filterOptions.sales" :key="person.id" :value="person.id">{{ person.name }}</option></select></label>
      <label><span class="filter-name">{{ copy('Market', '市场') }}</span><select v-model="query.market" :disabled="loading" aria-label="Market"><option value="">{{ copy('All markets', '全部市场') }}</option><option v-for="market in filterOptions.markets" :key="market" :value="market">{{ market }}</option></select></label>
      <label><span class="filter-name">{{ copy('Equipment', '设备') }}</span><select v-model="query.equipment" :disabled="loading" aria-label="Equipment"><option value="">{{ copy('All equipment', '全部设备') }}</option><option v-for="equipment in filterOptions.equipment ?? []" :key="equipment" :value="equipment">{{ equipment }}</option></select></label>
      <div class="period-controls"><div class="segmented" :aria-label="copy('Period', '统计周期')"><button v-for="period in periods" :key="period" :aria-pressed="query.period === period" :class="{ active: query.period === period }" :disabled="loading" @click="changePeriod(period)">{{ label(period) }}</button></div><button :disabled="loading || !data" :aria-label="copy('Previous period', '上一期')" @click="step(false)"><ChevronLeft :size="16" /></button><input :value="query.anchor || data?.period.start" @change="query.anchor = ($event.target as HTMLInputElement).value" type="date" :aria-label="copy('Reference date', '参考日期')" :disabled="loading" /><button :disabled="loading || !data?.period.hasNext" :aria-label="copy('Next period', '下一期')" @click="step(true)"><ChevronRight :size="16" /></button></div>
      <button class="target-button" :disabled="!query.sales || loading || !!query.market || !!query.region || !!query.equipment" @click="editTargets()"><SlidersHorizontal :size="15" />{{ copy('Set individual targets', '设置个人目标') }}</button>
    </nav>
    </div>
    <div v-if="loading" class="review-state" role="status">{{ copy('Loading review…', '正在读取经营数据…') }}</div>
    <div v-else-if="error" class="review-state error" role="alert"><p>{{ error }}</p><button @click="load">{{ copy('Retry', '重新加载') }}</button></div>
    <template v-else-if="data">
      <section class="activity-panel panel"><div class="panel-heading"><h2>{{ copy('Period activity', '周期活动') }}</h2><span>{{ data.period.complete ? copy('vs previous complete period', '与上一完整周期比较') : copy('vs equal elapsed time in previous period', '与上期相同进度比较') }}</span></div><div class="activity-grid"><article v-for="item in data.activities" :key="item.key"><button class="activity-label" @click="details(item.key)">{{ label(item.key) }}</button><div class="activity-numbers"><button class="activity-value" :class="{ unavailable: item.actual.state !== 'ready' }" @click="details(item.key)">{{ fmt(item.actual) }}</button><span v-if="query.sales" class="activity-target">/ {{ fmt(item.target) }} {{ copy('target', '目标') }}</span></div><div class="activity-foot"><span v-if="item.delta !== null" :class="item.delta > 0 ? 'positive' : item.delta < 0 ? 'negative' : ''"><ArrowUp v-if="item.delta > 0" :size="12" /><ArrowDown v-if="item.delta < 0" :size="12" />{{ Math.abs(item.delta) }} {{ copy('vs prior', '较上期') }}</span><span v-else>{{ copy('Comparison unavailable', '对比数据不足') }}</span><span v-if="item.unclassified" class="unclassified-note" data-unclassified>{{ item.unclassified }} {{ copy('without an opportunity, not counted', '条未关联商机，未计入') }}</span></div></article></div></section>
      <div class="review-grid">
        <div class="review-brand-art" aria-hidden="true">
          <div class="review-watermark"><img :src="brandIconUrl" alt="" width="512" height="512" draggable="false" /></div>
        </div>
        <section class="panel pipeline-panel"><div class="panel-heading"><h2>{{ copy('Pipeline by stage', '商机阶段分布') }}</h2><div class="segmented"><button :aria-pressed="pipelineMode === 'count'" :class="{ active: pipelineMode === 'count' }" @click="pipelineMode = 'count'">{{ copy('Deals', '数量') }}</button><button :aria-pressed="pipelineMode === 'amount'" :class="{ active: pipelineMode === 'amount' }" @click="pipelineMode = 'amount'">{{ copy('Value', '金额') }}</button></div></div>
          <div class="stage-list"><button v-for="(row, index) in data.pipeline" :key="row.key" class="stage-row" :class="{ 'po-stage': row.key === 'po' }" @click="details(row.key)"><div class="stage-label"><b>{{ index + 1 }}. {{ label(row.key) }}</b><small v-if="row.key === 'internal_validation'">{{ copy('Optional · production before PO', '可选 · PO 前提前生产') }}</small></div><div class="stage-track"><span v-if="row[pipelineMode].state === 'ready'" :style="{ width: `${Number(row[pipelineMode].value) / maxPipeline * 100}%` }"></span></div><div class="stage-value"><strong :class="{ unavailable: row[pipelineMode].state !== 'ready' }">{{ pipelineMode === 'count' ? fmt(row.count) : row.key === 'qualified_opportunity' ? copy('No value yet', '仅计数量') : compactMoney(row.amount) }}<span v-if="pipelineMode === 'count' && row.count.state === 'ready'"> {{ copy('deals', '个') }}</span></strong><small v-if="pipelineMode === 'count'">{{ row.key === 'qualified_opportunity' ? copy('No value yet', '仅计数量') : compactMoney(row.amount) }}</small><small v-else>{{ fmt(row.count) }}<template v-if="row.count.state === 'ready'"> {{ copy('deals', '个') }}</template></small></div></button></div>
          <p class="panel-note po-missing"><button class="text-link" :disabled="data.orders.missingDate?.state !== 'ready'" @click="details('po_missing_date')">{{ label('po_missing_date') }} · {{ data.orders.missingDate ? fmt(data.orders.missingDate) : copy('Insufficient data', '数据不足') }} →</button><button class="text-link" :disabled="data.orders.missingAmount?.state !== 'ready'" @click="details('po_missing_amount')">{{ label('po_missing_amount') }} · {{ data.orders.missingAmount ? fmt(data.orders.missingAmount) : copy('Insufficient data', '数据不足') }} →</button></p>
        </section>
        <div class="middle-column">
          <section class="panel orders-panel"><div class="panel-heading"><div><h2>{{ copy('Orders vs individual annual target', '订单与个人年度目标') }}</h2><p>{{ copy('Calendar-day plan · CNY million', '按自然年天数计划 · 百万元') }}</p></div><span class="chart-owner">{{ chartSales ? ownerName(chartSales) : copy('No sales rep selected', '未筛选销售') }}</span></div>
            <div class="chart-frame"><svg viewBox="0 0 500 230" role="img" :aria-label="copy('Individual annual plan and cumulative actual orders', '个人年度计划与实际累计订单')"><g v-for="tick in [0, 1, 2, 3, 4]" :key="tick"><path class="grid-line" :d="`M45 ${190 - tick * 40}H485`"/><text x="36" :y="194 - tick * 40" text-anchor="end">{{ annualTarget !== null || actualTotal !== null ? (chartMaximum * tick / 4 / 1000000).toLocaleString(locale, { maximumFractionDigits: 2 }) : '—' }}</text></g><text v-for="(month, index) in monthLabels" :key="month" :x="45 + index * 40" y="212" text-anchor="middle">{{ month }}</text><template v-if="chartSales && (annualTarget !== null || actualTotal !== null)"><path v-if="planPath" class="plan-area" :d="`${planPath}V190Z`"/><path v-if="planPath" class="plan-line" :d="planPath"/><path v-if="actualPath" class="actual-line" :d="actualPath"/><path class="now-line" :d="`M${45 + (chartSource?.orders.elapsedFraction ?? 0) * 440} 20V190`"/><text class="now-label" :x="45 + (chartSource?.orders.elapsedFraction ?? 0) * 440" y="14" text-anchor="middle">{{ copy('as of', '截至') }}</text><path v-if="planPath" class="curve-hit plan-hit" :d="planPath" @pointermove="showCurveAmount($event, 'plan')" @pointerleave="curveHover = null"/><path v-if="actualPath" class="curve-hit actual-hit" :d="actualPath" @pointermove="showCurveAmount($event, 'actual')" @pointerleave="curveHover = null"/><g v-if="curveHover" class="curve-hover"><path class="hover-guide" :d="`M45 ${curveHover.y}H${curveHover.x}`"/><circle :cx="curveHover.x" :cy="curveHover.y" r="3.5"/><g :transform="`translate(${Math.min(339, Math.max(45, curveHover.x - 73))},${Math.max(22, curveHover.y - 48)})`" role="tooltip"><rect width="146" height="39" rx="5"/><text class="hover-month" x="8" y="14">{{ hoverMonth }} · {{ curveHover.kind === 'actual' ? copy('Actual curve', '实际曲线') : copy('Target curve', '目标曲线') }}</text><text class="hover-amount" x="8" y="30">≈ {{ fmt({ state: 'ready', value: curveHover.amount }, true) }}</text></g></g></template></svg><div v-if="!chartSales" class="chart-message">{{ copy('Filter by a sales rep above to see the individual annual plan', '在上方筛选销售后显示个人年度计划') }}</div></div>
            <footer class="order-footer"><span class="chart-legend"><i class="swatch actual"></i>{{ copy('Actual cumulative', '实际累计') }}<i class="swatch plan"></i>{{ copy('Calendar-day plan', '按天计划') }}</span><span class="chart-summary">{{ chartSales ? orderSummary : '' }}</span><span class="chart-caption">{{ chartCaption }}</span></footer>
          </section>
          <section class="panel sales-panel"><div class="panel-heading"><div><h2>{{ copy('By sales rep', '销售表现') }}</h2><p>{{ copy('Period activity and open pipeline per account manager', '所选周期各销售的活动与在途商机') }}</p></div></div><div class="table-scroll"><table class="cockpit-sales-table"><thead><tr><th>{{ copy('Rep', '销售') }}</th><th v-for="key in activities" :key="key">{{ ({ visits: copy('Visits', '沟通'), leads: copy('Leads', '线索'), tests: copy('Tests', '测试'), quotes: copy('Quotes', '报价') })[key] }}</th><th>Pipeline</th><th>{{ copy('PO YTD · CNY', 'PO 年累计 · CNY') }}</th></tr></thead><tbody><tr v-for="rep in data.sales" :key="rep.id"><th><button class="text-link" @click="query.sales = rep.id">{{ rep.name }}</button></th><td v-for="key in activities" :key="key">{{ fmt(rep.activities[key]) }}</td><td>{{ compactMoney(rep.pipeline) }}</td><td class="positive rep-orders">{{ compactMoney(rep.orders) }}<small v-if="rep.poCount.state === 'ready'">{{ fmt(rep.poCount) }} {{ copy(Number(rep.poCount.value) === 1 ? 'PO' : 'POs', '单') }}</small></td></tr></tbody></table></div><p v-if="!data.sales.length" class="empty-list">{{ copy('No matching sales records', '没有匹配的销售记录') }}</p></section>
        </div>
        <div class="right-column">
          <section class="panel stalled-panel"><div class="panel-heading"><div><h2>{{ copy('Stalled opportunities', '停滞商机') }}</h2><p>{{ copy('No substantive Action update · 21 days warning / 35 days escalation', '行动计划久未实质更新 · 21 天提醒 / 35 天升级') }}</p></div></div><div class="table-scroll"><table><thead><tr><th>{{ copy('Customer', '客户') }}</th><th>{{ copy('Stage', '阶段') }}</th><th>{{ copy('Estimate', '估算金额') }}</th><th>{{ copy('Idle', '停滞') }}</th><th>{{ copy('Owner', '销售') }}</th></tr></thead><tbody><tr v-for="row in data.stalled.items" :key="row.id"><td><RouterLink :to="detailRoute(row)"><strong>{{ row.customer }}</strong><small>{{ row.title }}</small></RouterLink></td><td>{{ label(row.stage ?? '') || '—' }}</td><td class="numeric">{{ rowAmount(row) }}</td><td :class="row.severity === 'high' ? 'negative idle' : 'idle'">{{ row.days == null ? '—' : `${row.daysAtLeast ? '≥' : ''}${row.days}` }} {{ copy('d', '天') }}</td><td>{{ ownerName(row.owner) }}</td></tr></tbody></table></div><p v-if="!data.stalled.items.length" class="empty-list">{{ data.stalled.count.state === 'ready' ? copy('No stalled action plans', '没有久未更新的行动计划') : copy('Action history coverage needs verification', '行动历史覆盖范围待核验') }}</p><footer class="list-footer"><span>{{ fmt(data.stalled.count) }}</span><button class="text-link" @click="details('stalled')">{{ copy('View details', '查看明细') }} →</button></footer></section>
          <section class="panel losses-panel"><div class="panel-heading"><div><h2>{{ label('losses') }}</h2><p>{{ copy('Recorded reasons · original entries, without classification', '记录中的原始原因，不做原因分类') }}</p></div></div><p v-if="data.losses.count.state !== 'ready'" class="list-intro">{{ copy('Historical completeness unverified', '历史完整性待核验') }}</p><ul v-if="data.losses.items.length" class="record-list loss-list"><li v-for="(row, index) in data.losses.items" :key="row.eventId ?? `${row.id}:${index}`"><RouterLink :to="detailRoute(row)"><strong>{{ row.customer }}</strong><p>{{ row.reason || copy('Reason not recorded', '未记录原因') }}<em v-if="lossStatus(row)" class="loss-status" :class="lossStatus(row)!.tone" data-loss-status>{{ lossStatus(row)!.text }}</em></p><span>{{ row.title }} · {{ ownerName(row.owner) }} · {{ dateText(row.at) }} · {{ label(row.stage ?? '') }}</span></RouterLink><span class="loss-value" :title="copy('CNY opportunity estimate at loss', '丢单时商机人民币金额')">{{ rowAmount(row) }}</span></li></ul><p v-else class="empty-list">{{ data.losses.count.state === 'ready' ? copy('No losses in the last 12 months', '近 12 个月无丢单') : copy('No verified loss events available', '暂无可核验的丢单事件') }}</p><footer class="list-footer"><span>{{ fmt(data.losses.count) }} · {{ copy('recorded losses', '丢单记录') }}<template v-if="data.losses.reviewed && data.losses.pending"> · {{ copy('reviewed', '已复盘') }} {{ fmt(data.losses.reviewed) }} · {{ copy('pending', '待复盘') }} {{ fmt(data.losses.pending) }}</template></span><button class="text-link" @click="details('losses')">{{ copy('View records', '查看记录') }} →</button></footer></section>
        </div>
      </div>
      <ReviewConversionPanel v-if="data.conversions || data.pipelineCoverage" :conversions="data.conversions" :coverage="data.pipelineCoverage" @details="details" />
      <footer class="review-footer"><strong>QIHENG DEMO CONFIDENTIAL</strong><span>{{ copy('Shanghai timezone · Missing data is not zero · Region and market use the customer master', '上海时区 · 数据不足不计为零 · 区域与市场取客户主档') }}</span></footer>
    </template>
    <dialog ref="detailsDialog" class="review-dialog detail-dialog" :aria-label="label(detailKey)" @cancel="detailRevision++"><header><div><p class="eyebrow">REVIEW</p><h2>{{ label(detailKey) }}</h2></div><button :aria-label="copy('Close', '关闭')" @click="detailsDialog?.close()"><X :size="20" /></button></header><p v-if="detailKey === 'po'" class="dialog-note">{{ copy('Current Confirmed / Completed opportunity bookings, by actual PO date and current opportunity owner; a CNY order counts its amount, another currency its entered CNY amount.', '当前已确认或已完成的商机订单，按实际 PO 日期统计，归属当前商机负责人；人民币订单取订单金额，外币订单取填写的人民币金额。') }}</p><p v-else-if="detailKey === 'po_missing_date'" class="dialog-note">{{ copy('Actual PO date missing; no year assumed. Open the booking to backfill the date.', '实际 PO 日期待补录，不推测所属年份。打开订单详情可补录。') }}</p><p v-else-if="detailKey === 'po_missing_amount'" class="dialog-note">{{ copy('Foreign-currency bookings without a CNY amount; the YTD amount stays unavailable until a Manager backfills them from the booking page.', '外币订单还没有人民币金额，年累计金额在经理补录前显示数据不足。打开订单详情可补录。') }}</p><p v-else-if="detailKey === 'stage6_no_po'" class="dialog-note">{{ copy('Deals in internal validation (stage 6) for at least', '在内部验证（第 6 阶段）已停留至少') }} {{ data?.stage6NoPo?.thresholdDays ?? 30 }} {{ copy('days without a PO, counted to the period cutoff (now for the current period). A deal that has since received its PO or left stage 6 is cleared; ≥ means the exact entry date is unknown (before the complete history).', '天仍未收到 PO 的商机，天数算到本期截止时（进行中的周期算到现在）。之后已收到 PO 或已离开第 6 阶段（推进、退回或关闭）的商机不再提醒；≥ 表示进入该阶段的确切日期未知（早于完整历史记录）。') }}</p><p v-else-if="detailKey === 'quotation_expiry'" class="dialog-note">{{ copy('Latest published versions still open now, expiring within', '当前仍有效的最新已发布报价，到期日位于') }} {{ data?.quotationExpiry?.referenceDate ?? '—' }} {{ copy('plus', '之后') }} {{ data?.quotationExpiry?.thresholdDays ?? 14 }} {{ copy('days (inclusive). Accepted, rejected, replaced, expired and closed-deal quotes are excluded. Counts are quotations; open a record to view the listed version.', '天内（含当天及末日）。已接受、拒绝、换版、过期或商机已结束的报价不再提醒。按报价单计数，点击打开列出的版本。') }}</p><p v-else-if="['downgrade', 'downgrade_history'].includes(detailKey)" class="dialog-note">{{ copy('Downgrades recorded in the selected period; plans, responsible owners and action status are current. Only the current owner can record an action and clear a warning. Editing the plan does not clear it. The pending count is unique opportunities; the list shows each downgrade.', '展示所选周期内的降档，计划、当前负责人及处理状态为最新情况。只有当前负责人记录已采取行动才会清除提醒，修改计划不会清除。待处理数按商机去重，明细逐次显示降档。') }}</p><p v-else-if="detailKey.startsWith('reached_')" class="dialog-note">{{ copy('Recorded arrivals during', '已记录的阶段到达时间位于') }} {{ data?.conversions?.start }} — {{ data?.conversions?.end }}{{ copy('. Each opportunity appears once per stage, using its latest arrival in this window. Missing or approximate history is excluded; with incomplete coverage these are samples, not a complete total.', '。每个阶段按商机去重，显示窗口内最近一次到达时间；缺失或仅有估算的历史不计入。历史不完整时，这些仅为样本，不是完整总量。') }}</p><p v-else class="dialog-note">{{ copy('Recorded details; when coverage is insufficient these records are not a complete total.', '已记录明细；数据不足时，这些记录不代表完整总量。') }}</p><p v-if="detailLoading" role="status">{{ copy('Loading…', '加载中…') }}</p><p v-else-if="detailError" role="alert">{{ detailError }} <button @click="details(detailKey)">{{ copy('Retry', '重试') }}</button></p><template v-else-if="detailData"><div class="table-scroll"><table><thead><tr><th>{{ copy('Record / Customer', '记录 / 客户') }}</th><th>{{ copy('Sales', '销售') }}</th><th>{{ ['po', 'po_missing_date', 'po_missing_amount'].includes(detailKey) ? copy('Actual PO date', '实际 PO 日期') : detailKey === 'quotation_expiry' ? copy('Valid until', '有效期至') : copy('Date', '日期') }}</th><th>{{ copy('Details', '详情') }}</th></tr></thead><tbody><tr v-for="(row, index) in detailData.items" :key="`${row.eventId ?? row.actionId ?? row.id}:${index}`"><td><RouterLink :to="detailRoute(row)" @click="detailsDialog?.close()">{{ row.title }}</RouterLink><small>{{ row.customer }}</small></td><td>{{ ownerName(row.owner) }}</td><td>{{ row.kind === 'booking' && !row.at ? copy('To backfill', '待补录') : dateText(row.at) }}</td><td><span v-if="row.quotationVersionId" data-quotation-expiry>V{{ row.quotationVersionNo }} · {{ row.daysToExpiry === 0 ? copy('Due on reference date', '截止日当天到期') : `${row.daysToExpiry} ${copy('days after reference date', '天后到期（相对所选截止日）')}` }}<br /></span><span v-if="row.kind === 'booking'">{{ row.status === 'Completed' ? copy('Completed', '已完成') : copy('Confirmed', '已确认') }} · {{ row.amount != null ? rowAmount(row) : copy('CNY amount to backfill', '人民币金额待补录') }}<br /></span><span v-if="row.fromLevel">{{ label(row.fromLevel) }} → {{ label(row.toLevel ?? '') }}<br /></span><span v-if="row.actionTitle">{{ row.actionTitle }} · {{ row.due }}<br /></span><span v-if="row.stage">{{ label(row.stage) }}<br /></span><span v-if="row.days">{{ row.daysAtLeast ? '≥' : '' }}{{ row.days }} {{ copy('days since update', '天未更新') }}<br /></span><span v-if="row.daysInStage != null">{{ row.daysAtLeast ? '≥' : '' }}{{ row.daysInStage }} {{ copy('days in stage 6 without a PO', '天在第 6 阶段未收到 PO') }}<br /></span><span v-if="row.kind === 'opportunity' && row.currency === 'CNY'">{{ rowAmount(row) }}<br /></span><span v-if="['lost', 'losses', 'downgrade', 'downgrade_history'].includes(detailKey)">{{ row.reason || copy('Reason not recorded', '未记录原因') }}</span><span v-if="['lost', 'losses'].includes(detailKey) && lossStatus(row)" class="loss-status" :class="lossStatus(row)!.tone" data-loss-status>{{ lossStatus(row)!.text }}</span><div v-if="row.fromLevel" class="downgrade-detail"><p>{{ copy('Current owner', '当前负责人') }} · {{ ownerName(row.currentOwner ?? row.owner) }}</p><p class="recovery-text">{{ copy('Recovery plan', '补救计划') }}：{{ row.recovery?.plan || copy('Not recorded; the owner or Manager can add it.', '尚未记录，可由负责人或经理补录。') }}</p><template v-if="row.recovery?.state === 'handled'"><p>{{ copy('Action recorded · warning cleared', '已记录行动 · 提醒已清除') }}</p><p class="recovery-text">{{ row.recovery.actionTaken }}</p><small>{{ ownerName(row.recovery.actedBy ?? null) }} · {{ dateText(row.recovery.actedAt) }}</small></template><p v-else>{{ copy('Awaiting action from the current owner', '待当前负责人采取行动') }}</p><RouterLink :to="detailRoute(row)" @click="detailsDialog?.close()">{{ copy('Open plan and action history', '查看计划及行动记录') }}</RouterLink></div></td></tr></tbody></table></div><p v-if="!detailData.items.length">{{ copy('No matching recorded events', '没有匹配的已记录事件') }}</p><footer class="dialog-pagination"><span>{{ detailData.total }} {{ copy('records', '条记录') }}</span><button :disabled="detailData.page <= 1" @click="details(detailKey, detailData.page - 1)">{{ copy('Previous', '上一页') }}</button><span>{{ detailData.page }}</span><button :disabled="detailData.page * detailData.pageSize >= detailData.total" @click="details(detailKey, detailData.page + 1)">{{ copy('Next', '下一页') }}</button></footer></template></dialog>
    <dialog ref="targetDialog" class="review-dialog target-dialog" :aria-label="copy('Individual targets', '个人目标')" @cancel="saving && $event.preventDefault()"><header><div><p class="eyebrow">{{ ownerName(target.sales) }}</p><h2>{{ copy('Individual targets', '个人目标') }}</h2></div><button :disabled="saving" :aria-label="copy('Close', '关闭')" @click="targetDialog?.close()"><X :size="20" /></button></header><form @submit.prevent="saveTarget"><label>{{ copy('Metric', '指标') }}<select v-model="target.metric" :disabled="saving" @change="targetPeriodChanged"><option v-for="key in [...activities, 'orders']" :key="key" :value="key">{{ label(key) }}</option></select></label><label>{{ copy('Target period', '目标周期') }}<select v-model="target.period" :disabled="saving || target.metric === 'orders'" @change="targetPeriodChanged"><option v-for="kind in [...periods, 'weekly_default']" :key="kind" :value="kind">{{ label(kind) }}</option></select></label><label>{{ target.period === 'weekly_default' ? copy('Effective Monday', '生效周一') : copy('Period start date', '周期开始日期') }}<input v-model="target.anchor" type="date" required :disabled="saving" /></label><label>{{ target.metric === 'orders' ? copy('Annual amount (CNY)', '年度金额（CNY）') : copy('Target count', '目标数量') }}<input v-model="target.value" type="number" min="0" :step="target.metric === 'orders' ? '0.01' : '1'" required :disabled="saving" /></label><p class="dialog-note">{{ copy('Weekly defaults take effect on a future Monday. Monthly, quarterly and annual activity goals are set independently. Zero is a target; blank means not set.', '默认周目标从未来周一生效；月、季度和年活动目标单独设置。0 表示零目标，空值表示尚未设置。') }}</p><p v-if="targetError" class="negative" role="alert">{{ targetError }}</p><p v-if="saved" class="positive" role="status">{{ copy('Target saved', '目标已保存') }}</p><footer><button type="button" :disabled="saving" @click="targetDialog?.close()">{{ copy('Close', '关闭') }}</button><button type="submit" class="save-target" :disabled="saving">{{ saving ? copy('Saving…', '保存中…') : copy('Save individual target', '保存个人目标') }}</button></footer></form></dialog>
  </div>
</template>

<style scoped>
:global(.route-content:has(.review-page)){max-width:2000px;padding:20px 24px}
.review-page{font-variant-numeric:tabular-nums;color:var(--crm-text);container-type:inline-size;font-size:13px}.review-page *{box-sizing:border-box}.review-page button,.review-page select,.review-page input{font:inherit;color:inherit}.review-page button{cursor:pointer}.review-page button:disabled,.review-page select:disabled{opacity:.5;cursor:default}.review-page button:focus-visible,.review-page select:focus-visible,.review-page input:focus-visible{outline:2px solid var(--crm-brand);outline-offset:3px}
.review-heading{display:grid;grid-template-columns:1.05fr 2fr .93fr;gap:24px;align-items:start;min-height:88px;margin-bottom:16px}.eyebrow{color:var(--crm-text-muted);font-size:11px;margin:0 0 8px}.identity h1{font-size:28px;letter-spacing:-.6px;margin:0;line-height:1.15}.identity>p:last-child{margin:5px 0 0;color:var(--crm-text-muted)}.heading-order{display:grid;gap:4px;font-size:12px}.heading-order span,.heading-order small{color:var(--crm-text-muted)}.heading-order small{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.heading-order strong{font-size:14px}.warning-strip{display:flex;align-items:center;gap:14px;min-height:66px;background:var(--crm-danger-soft);border:1px solid #e6b4ae;border-radius:9px;padding:12px 15px}.alert-icon{display:grid;place-items:center;width:34px;height:34px;flex-shrink:0;border-radius:50%;background:var(--crm-danger);color:white}.warning-strip strong{font-size:14px}.warning-links{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:4px}.warning-links button{display:flex;align-items:center;border:0;padding:0;background:none;color:var(--crm-text-muted);text-align:left}.strip-body{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:'title history' 'links links';column-gap:12px;min-width:0}.strip-body>strong{grid-area:title}.strip-body>.warning-links{grid-area:links}.strip-history{grid-area:history;display:flex;align-items:center;align-self:center;border:0;padding:0;background:none;color:var(--crm-text-muted);white-space:nowrap}
.review-controls{position:relative;display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:0}.plan-tab{padding:7px 16px;border:1px solid var(--crm-line);border-radius:5px;background:white;color:var(--crm-text);text-decoration:none}.plan-tab:hover{background:var(--crm-surface-muted)}.plan-tab.is-disabled{color:var(--crm-text-muted);background:var(--crm-surface-muted);cursor:default}.review-tab{background:var(--crm-navy);color:white;padding:7px 16px;border-radius:5px}.review-controls label{display:flex;gap:6px;align-items:center;background:white;border:1px solid var(--crm-line);border-radius:6px;padding:5px 8px;white-space:nowrap;color:var(--crm-text-muted)}.review-controls select{border:0;background:transparent;max-width:135px;min-width:0;font-weight:600}.review-page input,.target-dialog select{border:1px solid var(--crm-line);border-radius:5px;background:white;padding:5px 7px;min-width:0}.period-controls{display:flex;gap:4px;align-items:center;margin-left:auto}.period-controls>button,.target-button{display:inline-flex;align-items:center;justify-content:center;gap:5px;border:1px solid var(--crm-line);background:white;border-radius:5px;min-height:31px}.period-controls input{width:125px}.target-button{padding:5px 12px;background:var(--crm-brand);border-color:var(--crm-brand);color:var(--crm-brand-ink);font-weight:650}.segmented{display:flex;flex-shrink:0;border:1px solid var(--crm-line);border-radius:6px;overflow:hidden}.segmented button{background:white;border:0;padding:6px 10px;font-weight:600}.segmented button.active{background:var(--crm-brand);color:var(--crm-brand-ink)}
.panel{min-width:0;background:white;border:1px solid var(--crm-line);border-radius:10px;overflow:hidden}.panel-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:16px 18px 10px;flex-shrink:0}.panel h2{margin:0;line-height:1.25;letter-spacing:-.2px;font-size:16px}.panel-heading p,.panel-heading>span{color:var(--crm-text-muted);margin:4px 0 0;font-size:12px;line-height:1.4}.activity-panel{margin-bottom:16px}.activity-grid{display:grid;grid-template-columns:repeat(4,1fr);padding:2px 18px 17px}.activity-grid article{padding:0 16px;border-right:1px solid var(--crm-line);min-width:0}.activity-grid article:last-child{border:0}.activity-label{background:none;border:0;padding:0;color:var(--crm-text-muted)!important;text-align:left}.activity-numbers{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;min-height:46px}.review-page .activity-grid .activity-value{background:none;border:0;padding:0;font-size:32px!important;line-height:1.4;font-weight:750;letter-spacing:-.5px}.review-page .activity-grid .activity-value.unavailable{font-size:18px!important}.activity-target{font-size:12px;color:var(--crm-link);font-weight:650}.activity-foot{margin-top:3px;font-size:12px;color:var(--crm-text-muted)}.activity-foot span{display:inline-flex;align-items:center;gap:3px}.activity-foot .unclassified-note{display:block;margin-top:2px;color:var(--crm-text-muted)}.positive{color:var(--crm-positive-ink)!important}.negative{color:var(--crm-danger)!important}.unavailable{color:var(--crm-text-muted);font-weight:400!important}
.review-grid{position:relative;isolation:isolate;display:grid;grid-template-columns:1.15fr 1fr 1fr;gap:16px;height:744px}.review-grid .panel{display:flex;flex-direction:column;min-height:0}.middle-column,.right-column{display:grid;min-width:0;min-height:0;gap:16px}.middle-column{grid-template-rows:minmax(300px,44fr) minmax(320px,56fr)}.right-column{grid-template-rows:minmax(320px,49fr) minmax(310px,51fr)}.stage-list{padding:4px 18px 0}.stage-row{display:grid;grid-template-columns:1.05fr 1fr .68fr;gap:12px;align-items:center;min-height:61px;width:100%;text-align:left;background:none;border:0;border-bottom:1px dashed var(--crm-line);padding:10px 0}.stage-row:last-child{border:0}.stage-label b{font-size:13px;line-height:1.35}.stage-label small{display:block;color:var(--crm-link);line-height:1.4;margin-top:4px}.stage-track{height:24px;background:var(--crm-surface-muted);border-radius:4px;overflow:hidden}.stage-track span{display:block;height:100%;background:var(--crm-brand);border-radius:4px}.stage-row:nth-child(2) .stage-track span{opacity:.86}.stage-row:nth-child(3) .stage-track span{opacity:.75}.stage-row:nth-child(4) .stage-track span{opacity:.66}.stage-row:nth-child(5) .stage-track span{opacity:.56}.stage-row:nth-child(6) .stage-track span{background:#ba8b42}.po-stage .stage-track span{background:var(--crm-positive)}.stage-value{text-align:right;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.stage-value strong{display:block;font-size:13px}.stage-value strong span{font-weight:400;font-size:11px}.stage-value small{color:var(--crm-text-muted);display:block;margin-top:3px}.stage-value .unavailable{font-size:12px}.panel-note{padding:16px 18px;margin:0;line-height:1.6}.po-missing{display:flex;flex-wrap:wrap;gap:6px 18px}

.chart-owner{max-width:120px;font-size:11px;color:var(--crm-text-muted);text-align:right;overflow-wrap:anywhere}.chart-frame{flex:1;position:relative;min-height:0;margin:0 14px}.chart-frame svg{width:100%;height:100%;display:block}.chart-frame text{fill:var(--crm-text-muted);font-size:10px}.grid-line{fill:none;stroke:var(--crm-line);stroke-width:1}.plan-area{fill:var(--crm-surface-muted);opacity:.7}.plan-line{fill:none;stroke:var(--crm-text-muted);stroke-width:1.5;stroke-dasharray:4 4}.actual-line{fill:none;stroke:var(--crm-brand);stroke-width:2.25;stroke-linejoin:round;stroke-linecap:round}.curve-hit{fill:none;stroke:transparent;stroke-width:14;pointer-events:stroke;cursor:crosshair}.curve-hover{pointer-events:none}.hover-guide{fill:none;stroke:var(--crm-text-muted);stroke-width:1;stroke-dasharray:3 3}.curve-hover circle{fill:var(--crm-surface-raised);stroke:var(--crm-brand);stroke-width:2}.curve-hover rect{fill:var(--crm-surface-raised);stroke:var(--crm-line-strong)}.chart-frame .hover-amount{fill:var(--crm-text);font-weight:700;font-size:12px}.now-line{stroke:var(--crm-link);stroke-width:1.5}.chart-frame text.now-label{fill:var(--crm-link)}.chart-message{position:absolute;inset:30% 10% 35%;display:grid;place-items:center;text-align:center;color:var(--crm-text-muted);background:#fffffff0;padding:10px;font-size:12px}.chart-empty{flex:1;display:grid;place-items:center;margin:0;padding:20px;text-align:center;color:var(--crm-text-muted)}.order-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 18px 14px;color:var(--crm-text-muted);font-size:11px}.text-link{background:none;border:0;padding:0;color:var(--crm-link)!important;text-align:left;display:inline-flex;align-items:center;gap:3px}.chart-legend{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}.swatch{display:inline-block;width:14px;border-top:2px solid var(--crm-brand);border-radius:1px}.swatch.plan{border-top:2px dashed var(--crm-text-muted);margin-left:8px}.chart-summary{display:none}.chart-caption{text-align:right}
.table-scroll{overflow:auto;min-height:0;padding:0 18px;flex:1}table{border-collapse:collapse;width:100%;font-size:12px;text-align:left}th,td{padding:13px 7px;border-bottom:1px solid var(--crm-line);vertical-align:top;font-variant-numeric:tabular-nums}th:first-child,td:first-child{padding-left:0}th:last-child,td:last-child{padding-right:0}thead th{color:var(--crm-text-muted);font-size:11px;font-weight:650;white-space:nowrap;position:sticky;top:0;background:white}tbody th{font-weight:650}td strong{display:block}td small{display:block;color:var(--crm-text-muted);line-height:1.4;margin-top:3px}td a{color:inherit;text-decoration:none}td a:hover{text-decoration:underline}tr:last-child th,tr:last-child td{border-bottom:0}.sales-panel table{min-width:420px}.sales-panel td:last-child{font-weight:700}.stalled-panel{border-color:#e9cfaf}.stalled-panel table{min-width:435px}.stalled-panel td:first-child{width:36%;min-width:120px}.stalled-panel td:nth-child(2){width:22%}.idle{color:var(--crm-link);font-weight:750}.numeric{white-space:nowrap}.panel:has(.empty-list)>.table-scroll{flex:0 0 auto}.empty-list{display:grid;place-items:center;flex:1;margin:0;padding:28px 20px;min-height:80px;color:var(--crm-text-muted);text-align:center}.losses-panel{background:#fffcf7}.record-list{padding:0 18px;margin:0;list-style:none;overflow:auto;flex:1;min-height:0}.loss-list li{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding:12px 0;border-bottom:1px solid var(--crm-line)}.loss-list li:last-child{border:0}.loss-list a{color:inherit;text-decoration:none}.loss-list a:hover strong{text-decoration:underline}.loss-list p{margin:4px 0;color:var(--crm-text-muted);line-height:1.5;overflow-wrap:anywhere}.loss-list a>span{color:var(--crm-text-muted);font-size:11px}.loss-value{font-size:11px;max-width:105px;overflow-wrap:anywhere;text-align:right}.list-footer{margin:10px 18px;padding:8px 10px;background:var(--crm-surface-muted);display:flex;justify-content:space-between;gap:12px;color:var(--crm-text-muted);font-size:11px;border-radius:5px}.list-intro{margin:0 18px 7px;color:var(--crm-text-muted)}.review-footer{display:flex;justify-content:space-between;gap:12px;padding:10px 0;font-size:10px;color:var(--crm-text-muted)}.review-footer strong{font-size:9px;letter-spacing:1px}.review-state{display:grid;place-items:center;min-height:320px;border:1px solid var(--crm-line);border-radius:10px;background:white;text-align:center}.review-state.error{color:var(--crm-danger)}
@container(max-width:1350px){.review-heading{grid-template-columns:1fr 1.5fr .9fr;gap:16px}.warning-strip>div>strong{display:none}.warning-strip{padding:10px;gap:10px}.warning-strip strong{font-size:12px}.identity h1{font-size:24px}.panel-heading{padding:14px 15px 8px}.stage-row{gap:8px;grid-template-columns:1.1fr .9fr .7fr}.stage-label b{font-size:12px}.period-controls{margin-left:0}.table-scroll{padding:0 15px}.review-grid{height:744px}}
@container(max-width:1100px){.review-heading{grid-template-columns:1fr 1.5fr}.heading-order{display:none}.chart-summary{display:inline}.review-grid{height:auto;grid-template-columns:1fr 1fr}.pipeline-panel{min-height:690px!important}.middle-column{grid-template-rows:330px 344px}.right-column{grid-column:1/-1;grid-template-columns:1fr 1fr;grid-template-rows:390px}.activity-grid article{padding:0 10px}}
@container(max-width:680px){.review-heading{grid-template-columns:1fr;gap:14px}.review-controls label{flex:1;justify-content:space-between}.review-controls select{max-width:150px}.period-controls{flex-wrap:wrap}.activity-grid{grid-template-columns:1fr 1fr;gap:20px 0;padding:6px 8px 16px}.activity-grid article:nth-child(2){border:0}.activity-panel .panel-heading>span{display:none}.review-grid{display:flex;flex-direction:column}.pipeline-panel{min-height:660px!important}.middle-column{grid-template-rows:330px 344px}.right-column{grid-template-columns:1fr;grid-template-rows:390px 390px}.review-footer{flex-wrap:wrap}.stage-row{grid-template-columns:1.1fr .8fr .7fr}.orders-panel .panel-heading{gap:6px}}
.review-dialog{border:1px solid var(--crm-line);border-radius:9px;color:var(--crm-text);padding:22px;width:min(850px,90vw);max-height:85vh;overflow:auto}.review-dialog::backdrop{background:rgba(24,27,31,.42)}.review-dialog header{display:flex;justify-content:space-between;align-items:center;gap:20px}.review-dialog h2{margin:0;font-size:20px}.review-dialog header button{border:0;background:none}.review-dialog button{border:1px solid var(--crm-line);background:white;padding:6px 10px;border-radius:4px}.dialog-note{font-size:12px;color:var(--crm-text-muted);line-height:1.6}.review-dialog td{white-space:normal;line-height:1.7}.review-dialog td small{display:block;color:var(--crm-text-muted)}.review-dialog a{color:var(--crm-link)}.dialog-pagination{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:16px}.target-dialog{max-width:470px}.target-dialog form{display:grid;gap:14px;margin-top:18px}.target-dialog label{display:grid;gap:6px;font-size:12px}.target-dialog footer{display:flex;justify-content:flex-end;gap:8px}.target-dialog button.save-target{background:var(--crm-brand);border-color:var(--crm-brand);color:var(--crm-brand-ink)}


/* Use the official crossed-orbit icon intact; only transparency fades. */
.review-masthead {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  padding: 20px;
  margin-bottom: 16px;
  border: 1px solid var(--crm-line);
  border-top: 3px solid var(--crm-brand);
  border-radius: var(--crm-radius-md);
  background: linear-gradient(120deg, #fff3df 0%, #fffaf3 48%, var(--crm-surface) 100%);
}
.review-header-art {
  position: absolute;
  z-index: -1;
  inset: 0 12px 0 auto;
  width: 300px;
  pointer-events: none;
  opacity: .12;
  mask-image: linear-gradient(90deg, transparent, #000 65%);
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 65%);
}
.review-header-art img { width: 100%; height: 100%; object-fit: contain; object-position: right center; }
.identity .eyebrow { color: var(--crm-link); font-weight: 650; line-height: 1.5; }
.identity .eyebrow::before {
  content: "";
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 8px;
  border-radius: 1px;
  background: var(--crm-brand);
  box-shadow: 5px -5px 0 -1px rgb(255 142 1 / 35%);
}
.review-tab, .plan-tab, .review-controls label, .review-page input,
.period-controls > button, .target-button, .segmented, .list-footer {
  border-radius: var(--crm-radius-sm);
}
.review-tab, .plan-tab, .review-controls label, .period-controls > button, .target-button {
  min-height: 34px;
}
.review-controls select { min-height: 22px; }
.panel { border-radius: var(--crm-radius-md); }
.review-brand-art {
  position: absolute;
  inset: 0;
  z-index: 2;
  overflow: hidden;
  pointer-events: none;
  user-select: none;
  border-radius: var(--crm-radius-md);
}
.review-watermark {
  position: absolute;
  width: min(580px, 65%);
  aspect-ratio: 1;
  right: -35px;
  bottom: -45px;
  overflow: hidden;
  opacity: .09;
  mask-image: linear-gradient(135deg, transparent 0%, #000 62%);
  -webkit-mask-image: linear-gradient(135deg, transparent 0%, #000 62%);
}
.review-watermark img { display: block; width: 100%; max-width: none; height: auto; }
@container (max-width: 680px) {
  .review-masthead { padding: 16px; }
  .review-watermark { width: 400px; max-width: 115%; right: -65px; bottom: -40px; opacity: .065; }
}
@media (forced-colors: active) {
  .review-brand-art, .review-header-art { display: none; }
}

.loss-status{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;font-size:11px;font-style:normal;font-weight:650;white-space:nowrap}.loss-status.warn{background:var(--crm-warning-soft);color:#9a5b00}.loss-status.danger{background:var(--crm-danger-soft);color:var(--crm-danger)}.loss-status.done{background:#e8f5ee;color:var(--crm-positive-ink)}.loss-status.muted{background:var(--crm-surface-muted);color:var(--crm-text-muted)}
.downgrade-detail{margin-top:8px;max-width:480px}.downgrade-detail p{margin:6px 0}.recovery-text{white-space:pre-wrap;overflow-wrap:anywhere}
/* Cockpit mastheads wrap the same way below a 1860px page (above it the widest first row, English Review with its
   target button and four 135px-capped selects, about 1810px, still fits): the period (or scope) controls take their own
   second row on Review, Plan, Warnings and Opportunities, and the filters share the first row instead of
   wrapping, so the four top cards stay the same height. */
@container(max-width:1860px){.review-controls .period-controls{flex:1 1 calc(100% - 200px);margin-left:0}.review-controls label{flex:1 1 110px;max-width:max-content;min-width:0}}
/* Below a 1200px page the filter names give way so the four first-row selects stay readable; each select keeps its aria-label. */
@container(max-width:1200px){.review-controls .filter-name{display:none}}
</style>

<style scoped src="@/features/cockpit/sales-table.css"></style>
