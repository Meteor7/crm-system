<script setup lang="ts">
import { personnelDisplayName } from '@/demo/personnel'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Banknote, BellRing, BriefcaseBusiness, CalendarDays, CircleDollarSign, Scale, UserRound } from '@lucide/vue'
import type { EChartsOption } from 'echarts'
import { api as defaultApi, type CrmApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { useDashboardStore } from '@/stores/dashboard'
import PageHeader from '@/design-system/PageHeader.vue'
import KpiCard from '@/design-system/KpiCard.vue'
import SectionCard from '@/design-system/SectionCard.vue'
import StatusBadge from '@/design-system/StatusBadge.vue'
import DataState from '@/design-system/DataState.vue'
import DataNotice from '@/design-system/DataNotice.vue'
import ModalShell from '@/design-system/ModalShell.vue'
import CrmChart from '@/charts/CrmChart.vue'
import {
  DASHBOARD_CHART_IDS,
  DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS,
  readBossDashboardSubscriptionGroups,
  writeBossDashboardSubscriptionGroups,
  type DashboardChartId,
  type DashboardSubscriptionGroups,
  type DashboardSubscriptionStorage,
} from '@/features/dashboard/dashboard-subscriptions'
import {
  buildAccountContributionOption,
  buildBookingOption,
  buildCountBreakdownOption,
  buildValueDistributionOption,
} from '@/charts/options'
import { formatMoney } from '@/domain/money'
import { formatDisplayDate } from '@/domain/time'
import { readAllPages } from '@/features/shared/read-all-pages'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const store = useDashboardStore()
const app = useAppStore()
const router = useRouter()
const showMoreAnalysis = ref(false)
type ReminderType = '拜访' | '客户预期' | 'Demo Test DDL' | 'Booking DDL' | '行动截止'
interface DeadlineReminder {
  id: string
  type: ReminderType
  date: string
  title: string
  account: string
  owner: string
  detail: string
  path: string
  demoRequestId?: string
  evaluationId?: string
}
const reminderLoading = ref(false)
const reminderError = ref('')
const reminders = ref<DeadlineReminder[]>([])
const selectedScheduleId = ref('')
type DashboardChartGroup = 'core' | 'customer' | 'process'
interface DashboardChartItem {
  id: DashboardChartId
  group: DashboardChartGroup
  title: string
  eyebrow: string
  description: string
  option: EChartsOption
  hasData: boolean
  emptyTitle: string
  label: string
}
interface ProcessDashboardChart {
  key: DashboardChartId
  title: string
  eyebrow: string
  rows: unknown[]
  option: EChartsOption
  label: string
}
const subscriptionGroups = ref<DashboardSubscriptionGroups>(
  DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS.map((group) => [...group]),
)
const draftSubscriptionGroups = ref<DashboardSubscriptionGroups>([])
const activeSubscriptionGroupIndex = ref(0)
const subscriptionOpen = ref(false)
const subscriptionStorageWarning = ref('')

const managementView = computed(() => app.bootstrap?.user.role === 'Manager')
const activeCurrency = computed(() => store.data?.kpis.moneyByCurrency[0]?.currency ?? 'CNY')
const activeMoney = computed(() => store.data?.kpis.moneyByCurrency.find((item) => item.currency === activeCurrency.value))
const bookingOption = computed(() => buildBookingOption((store.data?.bookingByMonth ?? []).filter((item) => item.currency === activeCurrency.value).map((item) => ({ ...item, amount: Number(item.amount) }))))
const evaluationOption = computed(() => buildCountBreakdownOption(store.data?.process.evaluationByStatus ?? []))
const accountOption = computed(() => buildAccountContributionOption((store.data?.topAccounts ?? []).filter((item) => item.currency === activeCurrency.value).slice(0, 6).map((item) => ({ label: item.accountName, pipeline: Number(item.pipeline), booking: Number(item.booking) }))))
const regionOption = computed(() => buildValueDistributionOption((store.data?.regionDistribution ?? []).filter((item) => item.currency === activeCurrency.value).map((item) => ({ ...item, pipeline: Number(item.pipeline), booking: Number(item.booking) }))))
const tierOption = computed(() => buildCountBreakdownOption(store.data?.tierDistribution ?? []))
const riskOption = computed(() => buildCountBreakdownOption(store.data?.riskDistribution ?? []))

const processCharts = computed<ProcessDashboardChart[]>(() => {
  const process = store.data?.process
  return [
    { key: 'requirements', title: 'Requirement Status', eyebrow: 'REQUIREMENTS', rows: process?.requirementsByStatus ?? [], option: buildBookingOption(process?.requirementsByStatus ?? []), label: 'Purchase requirement status and budget value' },
    { key: 'budget', title: 'Budget Status', eyebrow: 'BUDGET', rows: process?.budgetByStatus ?? [], option: buildBookingOption(process?.budgetByStatus ?? []), label: 'Budget status and requirement value' },
    { key: 'actions', title: 'Action Sources', eyebrow: 'OPEN ACTIONS', rows: process?.actionsBySource ?? [], option: buildCountBreakdownOption(process?.actionsBySource ?? []), label: 'Open actions by source' },
    { key: 'action-timeliness', title: 'Action Timeliness', eyebrow: 'ACTION TIMELINESS', rows: process?.actionsByTimeliness ?? [], option: buildCountBreakdownOption(process?.actionsByTimeliness ?? []), label: 'Open actions by due status' },
    { key: 'demo', title: 'Demo Request Status', eyebrow: 'DEMO REQUEST', rows: process?.demoByStatus ?? [], option: buildCountBreakdownOption(process?.demoByStatus ?? []), label: 'Demo Requests by status' },
    { key: 'demo-priority', title: 'Demo Priority', eyebrow: 'DEMO PRIORITY', rows: process?.demoByPriority ?? [], option: buildCountBreakdownOption(process?.demoByPriority ?? []), label: 'Demo Requests by priority' },
    { key: 'evaluation-runs', title: 'Test Run Results', eyebrow: 'TEST RUNS', rows: process?.evaluationRunResults ?? [], option: buildCountBreakdownOption(process?.evaluationRunResults ?? []), label: 'Test run plans and results' },
    { key: 'visits', title: 'Visit Status', eyebrow: 'VISITS', rows: process?.visitsByStatus ?? [], option: buildCountBreakdownOption(process?.visitsByStatus ?? []), label: 'Customer visits by status' },
    { key: 'visit-owner', title: 'Visit Owners', eyebrow: 'VISIT OWNER', rows: process?.visitsByOwner ?? [], option: buildCountBreakdownOption(process?.visitsByOwner ?? []), label: 'Customer visits by owner' },
  ]
})

const dashboardGroupMeta: Record<DashboardChartGroup, { eyebrow: string; title: string; description: string }> = {
  core: { eyebrow: 'CORE ANALYSIS', title: 'Commercial Performance', description: 'Demo, Booking, and key-account performance.' },
  customer: { eyebrow: 'CUSTOMER ANALYSIS', title: 'Account Mix & Risk', description: 'Review account distribution by region, tier, and risk.' },
  process: { eyebrow: 'PROCESS ANALYSIS', title: 'Process & Execution', description: 'Charts use current requirements, actions, demos, evaluations, and visit records.' },
}

const visualDashboardCatalog = computed<DashboardChartItem[]>(() => [
  {
    id: 'evaluation-status',
    group: 'core',
    title: 'Demo / Wafer Test 状态',
    eyebrow: 'EVALUATION',
    description: '按当前 Demo 与 Wafer Test 记录汇总各执行状态。',
    option: evaluationOption.value,
    hasData: Boolean(store.data?.process.evaluationByStatus.length),
    emptyTitle: '暂无 Demo / Wafer Test 状态记录',
    label: 'Demo 与 Wafer Test 状态分布图',
  },
  {
    id: 'booking-month',
    group: 'core',
    title: '实际 Booking 月度分布',
    eyebrow: 'BOOKING BY MONTH',
    description: '仅使用 Confirmed Booking 的真实 bookingDate，不补造趋势。',
    option: bookingOption.value,
    hasData: Boolean(store.data?.bookingByMonth.length),
    emptyTitle: '暂无 Confirmed Booking',
    label: '实际 Booking 月度金额图',
  },
  {
    id: 'top-accounts',
    group: 'core',
    title: '重点客户金额贡献',
    eyebrow: 'TOP ACCOUNTS',
    description: '按客户汇总开放 Pipeline 与 Confirmed Booking。',
    option: accountOption.value,
    hasData: Boolean(store.data?.topAccounts.length),
    emptyTitle: '暂无客户金额记录',
    label: '重点客户金额贡献图',
  },
  {
    id: 'region',
    group: 'customer',
    title: '区域分布',
    eyebrow: 'REGION',
    description: '按区域查看客户 Pipeline 与 Booking 金额。',
    option: regionOption.value,
    hasData: Boolean(store.data?.regionDistribution.length),
    emptyTitle: '暂无区域金额',
    label: '区域金额分布图',
  },
  {
    id: 'tier',
    group: 'customer',
    title: '客户等级',
    eyebrow: 'TIER',
    description: '查看当前客户等级数量构成。',
    option: tierOption.value,
    hasData: Boolean(store.data?.tierDistribution.length),
    emptyTitle: '暂无客户等级',
    label: '客户等级数量图',
  },
  {
    id: 'risk',
    group: 'customer',
    title: '客户风险',
    eyebrow: 'RISK',
    description: '查看当前客户风险数量构成。',
    option: riskOption.value,
    hasData: Boolean(store.data?.riskDistribution.length),
    emptyTitle: '暂无客户风险',
    label: '客户风险数量图',
  },
  ...processCharts.value.map((chart) => ({
    id: chart.key,
    group: 'process' as const,
    title: chart.title,
    eyebrow: chart.eyebrow,
    description: chart.label,
    option: chart.option,
    hasData: chart.rows.length > 0,
    emptyTitle: `${chart.title}暂无记录`,
    label: chart.label,
  })),
])

const subscribedDashboardGroups = computed(() => {
  const catalog = new Map(visualDashboardCatalog.value.map((chart) => [chart.id, chart]))
  return subscriptionGroups.value.map((group) => group.flatMap((id) => {
    const chart = catalog.get(id)
    return chart ? [chart] : []
  }))
})

const subscribedDashboardCount = computed(() => subscriptionGroups.value.flat().length)

const unsubscribedDashboardGroups = computed(() => {
  const selected = new Set(subscriptionGroups.value.flat())
  return (['core', 'customer', 'process'] as const)
    .map((group) => ({
      id: group,
      ...dashboardGroupMeta[group],
      charts: visualDashboardCatalog.value.filter((chart) => chart.group === group && !selected.has(chart.id)),
    }))
    .filter((group) => group.charts.length > 0)
})

const subscriptionCatalogGroups = computed(() => (['core', 'customer', 'process'] as const).map((group) => ({
  id: group,
  ...dashboardGroupMeta[group],
  charts: visualDashboardCatalog.value.filter((chart) => chart.group === group),
})))

const activeDraftSubscriptionGroup = computed(() =>
  draftSubscriptionGroups.value[activeSubscriptionGroupIndex.value] ?? [],
)

const draftSubscriptionGroupsValid = computed(() => {
  if (draftSubscriptionGroups.value.length < 1) return false
  if (!draftSubscriptionGroups.value.every((group) => group.length === 3)) return false
  const ids = draftSubscriptionGroups.value.flat()
  return new Set(ids).size === ids.length
})

const canAddSubscriptionGroup = computed(() =>
  draftSubscriptionGroups.value.length < Math.floor(DASHBOARD_CHART_IDS.length / 3)
  && DASHBOARD_CHART_IDS.length - draftSubscriptionGroups.value.flat().length >= 3,
)

function browserStorage(): DashboardSubscriptionStorage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

function subscriptionUserId() {
  return app.bootstrap?.user.id || 'management-viewer'
}

function cloneSubscriptionGroups(groups: DashboardSubscriptionGroups): DashboardSubscriptionGroups {
  return groups.map((group) => [...group])
}

function openSubscriptionManager() {
  draftSubscriptionGroups.value = cloneSubscriptionGroups(subscriptionGroups.value)
  activeSubscriptionGroupIndex.value = 0
  subscriptionOpen.value = true
}

function draftSubscriptionOwner(id: DashboardChartId) {
  return draftSubscriptionGroups.value.findIndex((group) => group.includes(id))
}

function isDraftSubscriptionOptionDisabled(id: DashboardChartId) {
  const owner = draftSubscriptionOwner(id)
  if (owner >= 0) return owner !== activeSubscriptionGroupIndex.value
  return activeDraftSubscriptionGroup.value.length >= 3
}

function draftSubscriptionOptionLabel(id: DashboardChartId) {
  const owner = draftSubscriptionOwner(id)
  if (owner === activeSubscriptionGroupIndex.value) return '已订阅'
  if (owner >= 0) return `第 ${owner + 1} 排已订阅`
  return '选择'
}

function toggleDraftSubscription(id: DashboardChartId) {
  const activeGroup = activeDraftSubscriptionGroup.value
  const index = activeGroup.indexOf(id)
  if (index >= 0) {
    activeGroup.splice(index, 1)
    return
  }
  if (draftSubscriptionOwner(id) < 0 && activeGroup.length < 3) activeGroup.push(id)
}

function addSubscriptionGroup() {
  if (!canAddSubscriptionGroup.value) return
  draftSubscriptionGroups.value.push([])
  activeSubscriptionGroupIndex.value = draftSubscriptionGroups.value.length - 1
}

function deleteActiveSubscriptionGroup() {
  if (activeSubscriptionGroupIndex.value === 0) return
  draftSubscriptionGroups.value.splice(activeSubscriptionGroupIndex.value, 1)
  activeSubscriptionGroupIndex.value = Math.min(
    activeSubscriptionGroupIndex.value,
    draftSubscriptionGroups.value.length - 1,
  )
}

function saveSubscriptions() {
  if (!draftSubscriptionGroupsValid.value) return
  subscriptionGroups.value = cloneSubscriptionGroups(draftSubscriptionGroups.value)
  const saved = writeBossDashboardSubscriptionGroups(
    browserStorage(),
    subscriptionUserId(),
    subscriptionGroups.value,
  )
  subscriptionStorageWarning.value = saved ? '' : '当前浏览器无法保存订阅；本次页面选择仍然有效。'
  subscriptionOpen.value = false
}

function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
function addDays(date: Date, amount: number) {
  const next = new Date(date)
  next.setDate(next.getDate() + amount)
  return next
}
function daysUntil(date: string) {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const target = new Date(`${date}T00:00:00`)
  return Math.round((target.getTime() - start.getTime()) / 86400000)
}
function dueLabel(date: string) {
  const days = daysUntil(date)
  return days === 0 ? '今天到期' : `剩余 ${days} 天`
}
const reminderWindow = computed(() => {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  return `${dateKey(start)} — ${dateKey(addDays(start, 15))}`
})
const teamSchedule = computed(() => reminders.value
  .filter((item) => item.type !== '行动截止')
  .slice(0, 5))
const selectedTeamSchedule = computed(() => teamSchedule.value.find((item) => item.id === selectedScheduleId.value) ?? teamSchedule.value[0])
const relatedScheduleItems = computed(() => {
  const selected = selectedTeamSchedule.value
  if (!selected) return []
  if (!selected.demoRequestId) return [selected]
  return reminders.value
    .filter((item) => item.demoRequestId === selected.demoRequestId && ['客户预期', 'Demo Test DDL'].includes(item.type))
    .sort((a, b) => {
      const order = (item: DeadlineReminder) => item.type === '客户预期' ? 0 : 1
      return order(a) - order(b)
    })
})
const demoTimingRelation = computed(() => {
  const request = relatedScheduleItems.value.find((item) => item.type === '客户预期')
  const test = relatedScheduleItems.value.find((item) => item.type === 'Demo Test DDL')
  if (!request || !test) return ''
  const gap = daysUntil(test.date) - daysUntil(request.date)
  if (gap === 0) return 'Test DDL 与客户预期同日对齐'
  return gap < 0 ? `Test DDL 提前客户预期 ${Math.abs(gap)} 天` : `Test DDL 晚于客户预期 ${gap} 天`
})
const scheduleCounts = computed(() => [
  { type: '拜访', label: 'Sales 拜访', count: reminders.value.filter((item) => item.type === '拜访').length },
  { type: '客户预期', label: '客户预期', count: reminders.value.filter((item) => item.type === '客户预期').length },
  { type: 'Demo Test DDL', label: 'Test DDL', count: reminders.value.filter((item) => item.type === 'Demo Test DDL').length },
  { type: 'Booking DDL', label: 'Booking DDL', count: reminders.value.filter((item) => item.type === 'Booking DDL').length },
])

async function loadReminders() {
  reminderLoading.value = true
  reminderError.value = ''
  try {
    const visitsRequest = app.can('visit:view')
      ? readAllPages((page, pageSize) => props.apiClient.listVisits({ page, pageSize }))
      : Promise.resolve([])
    const [visits, requests, evaluations, pipeline] = await Promise.all([
      visitsRequest,
      readAllPages((page, pageSize) => props.apiClient.listDemoRequests({ page, pageSize })),
      readAllPages((page, pageSize) => props.apiClient.listEvaluations({ page, pageSize })),
      props.apiClient.listPipeline({}),
    ])
    const rows: DeadlineReminder[] = [
      ...visits.map((item) => ({
        id: `visit-${item.id}`, type: '拜访' as const, date: item.date, title: item.subject,
        account: item.accountName, owner: item.owner, detail: item.objective, path: '/visits',
      })),
      ...requests.filter((item) => item.status !== 'Cancelled').map((item) => ({
        id: `request-${item.id}`, type: '客户预期' as const, date: item.customerExpectedDate || item.targetDate,
        title: `${item.id} · ${item.title}`, account: item.accountName, owner: item.salesOwner,
        detail: item.requestedEquipment, path: '/demo-requests', demoRequestId: item.id,
      })),
      ...evaluations.filter((item) => item.testRunDeadline).map((item) => {
        const linkedRequest = requests.find((request) =>
          request.id === item.demoRequestId ||
          Boolean(item.requirementId && request.requirementId === item.requirementId))
        return {
          id: `test-${item.id}`, type: 'Demo Test DDL' as const, date: item.testRunDeadline,
          title: `${item.id} · ${item.title}`, account: item.accountName, owner: item.owner,
          detail: item.criteria || 'Demo Test 截止提醒', path: '/evaluations',
          demoRequestId: item.demoRequestId || linkedRequest?.id, evaluationId: item.id,
        }
      }),
      ...pipeline.data.bookings.filter((item) => item.status !== 'Cancelled' && item.ddl).map((item) => ({
        id: `booking-${item.id}`, type: 'Booking DDL' as const, date: item.ddl,
        title: `${item.id} · ${item.equipment}`, account: item.accountName, owner: item.owner,
        detail: `${item.quantity} 台 · ${item.status}`, path: '/booking',
      })),
      ...(store.data?.weeklyActions ?? []).filter((item) => item.status !== 'Completed').map((item) => ({
        id: `action-${item.id}`, type: '行动截止' as const, date: item.due,
        title: item.title, account: item.accountId, owner: item.owner,
        detail: item.sourceType, path: '/requirements',
      })),
    ]
    reminders.value = rows
      .filter((item) => {
        const days = daysUntil(item.date)
        return days >= 0 && (managementView.value || days <= 15)
      })
      .sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title))
  } catch (reason) {
    reminderError.value = reason instanceof Error ? reason.message : '提醒数据加载失败'
  } finally {
    reminderLoading.value = false
  }
}
async function load() {
  await store.load(props.apiClient, 'quarter')
  if (store.data) await loadReminders()
}
onMounted(async () => {
  await app.loadBootstrap(props.apiClient)
  if (managementView.value) {
    subscriptionGroups.value = readBossDashboardSubscriptionGroups(browserStorage(), subscriptionUserId())
  }
  await load()
})
</script>

<template>
  <div class="dashboard-page dashboard-readable-type">
    <PageHeader
      :eyebrow="managementView ? 'MANAGEMENT INFORMATION CENTER' : 'REMINDER CENTER'"
      title="信息中心"
      :description="managementView ? 'Boss 可查阅公司经营数据看板；指标来自商机、Booking、客户、需求、Demo 和拜访记录。' : '仅展示当前权限范围内未来 15 天即将到期的业务活动，不展示公司经营看板。'"
      :updated-at="store.data?.asOf"
    >
      <StatusBadge v-if="managementView" label="管理者权限 · 公司季度 · 只读" tone="info" />
      <StatusBadge v-else label="个人提醒 · 未来 15 天" tone="neutral" />
    </PageHeader>

    <DataState v-if="store.loading && !store.data" type="loading" />
    <DataState v-else-if="store.denied" type="denied" :message="store.error" :request-id="store.requestId" />
    <DataState v-else-if="store.error" type="error" :message="store.error" :request-id="store.requestId" data-testid="retry-dashboard" @retry="load" />

    <template v-else-if="store.data">
      <DataNotice v-if="store.stale" :message="store.staleMessage" :request-id="store.requestId" @refresh="load" />
      <p v-if="managementView" class="source-note">数据口径：开放 Pipeline 排除 Won / Lost；加权值按商机金额 × 赢率；Booking 仅统计 Confirmed；累计成交取 Won 商机。</p>

      <section v-if="managementView" class="kpi-grid" aria-label="关键经营指标">
        <KpiCard class="kpi-value-pipeline" label="Open Pipeline" :value="formatMoney(activeMoney?.openPipeline ?? '0.00', activeCurrency)" detail="当前币种未关闭商机金额" :icon="BriefcaseBusiness" tone="navy" />
        <KpiCard class="kpi-value-weighted" label="Weighted Pipeline" :value="formatMoney(activeMoney?.weightedPipeline ?? '0.00', activeCurrency)" detail="当前币种开放商机按赢率加权" :icon="Scale" tone="teal" />
        <KpiCard class="kpi-value-booking" label="Confirmed Booking" :value="formatMoney(activeMoney?.confirmedBooking ?? '0.00', activeCurrency)" detail="当前币种真实 Booking" :icon="Banknote" tone="lime" />
        <KpiCard class="kpi-value-won" label="累计 Closed Won" :value="formatMoney(activeMoney?.cumulativeWon ?? '0.00', activeCurrency)" detail="当前币种已成交商机总额" :icon="CircleDollarSign" tone="amber" />
      </section>

      <template v-if="managementView">
        <section class="management-primary-grid">
          <SectionCard title="重点事项与执行提醒" eyebrow="TEAM CALENDAR" description="按日期汇总全员 Calendar 中的拜访、客户预期、Demo Test 与 Booking 截止安排。">
            <template #action><button class="text-button" type="button" @click="router.push('/calendar')">查看完整日历 →</button></template>
            <DataState v-if="reminderLoading" type="loading" />
            <DataState v-else-if="reminderError" type="error" :message="reminderError" @retry="loadReminders" />
            <div v-else-if="teamSchedule.length" class="team-schedule-list" aria-label="全员近期安排">
              <button v-for="item in teamSchedule" :key="item.id" type="button" :class="{ active: selectedTeamSchedule?.id === item.id }" @click="selectedScheduleId = item.id">
                <time>{{ formatDisplayDate(item.date) }}</time>
                <span class="schedule-owner">{{ personnelDisplayName(item.owner).slice(0, 1) }}</span>
                <div>
                  <p><b class="schedule-type" :class="{ request: item.type === '客户预期', test: item.type === 'Demo Test DDL', booking: item.type === 'Booking DDL' }">{{ item.type }}</b><strong>{{ item.title }}</strong></p>
                  <small>{{ item.account }} · {{ item.detail }}</small>
                </div>
                <span class="schedule-person"><UserRound :size="12" />{{ personnelDisplayName(item.owner) }}</span>
              </button>
            </div>
            <DataState v-else type="empty" title="暂无后续全员安排" message="Calendar 上游模块新增日期后会自动显示在这里。" />
            <footer class="schedule-footer">
              <span><CalendarDays :size="13" />即日起 · 与 Calendar 同步</span>
              <b>显示最近 {{ teamSchedule.length }} 项</b>
            </footer>
          </SectionCard>

          <SectionCard title="相关事项速览" eyebrow="RELATED SCHEDULE" description="联动展示同一 Demo 项目的客户预期与 Test DDL。">
            <div v-if="selectedTeamSchedule" class="schedule-snapshot">
              <header>
                <time>{{ formatDisplayDate(selectedTeamSchedule.date) }}</time>
                <div><b class="schedule-type" :class="{ request: selectedTeamSchedule.type === '客户预期', test: selectedTeamSchedule.type === 'Demo Test DDL', booking: selectedTeamSchedule.type === 'Booking DDL' }">{{ selectedTeamSchedule.type }}</b></div>
              </header>
              <div class="snapshot-body">
                <strong>{{ selectedTeamSchedule.account }}</strong>
                <p v-if="demoTimingRelation" class="relation-summary"><CalendarDays :size="13" />{{ demoTimingRelation }}</p>
                <p v-else>{{ selectedTeamSchedule.title }}</p>
                <div class="relation-timeline">
                  <article v-for="(item, index) in relatedScheduleItems" :key="item.id" :class="{ linked: relatedScheduleItems.length > 1 }">
                    <span class="relation-node">{{ index + 1 }}</span>
                    <div>
                      <header><b>{{ item.type }}</b><time>{{ formatDisplayDate(item.date) }}</time></header>
                      <strong>{{ item.title }}</strong>
                      <small><UserRound :size="11" />{{ personnelDisplayName(item.owner) }} · {{ item.detail }}</small>
                    </div>
                    <button type="button" @click="router.push(item.path)">查看</button>
                  </article>
                </div>
              </div>
              <footer class="snapshot-counts">
                <div v-for="item in scheduleCounts" :key="item.type"><strong>{{ item.count }}</strong><span>{{ item.label }}</span></div>
              </footer>
            </div>
            <DataState v-else type="empty" title="暂无安排可预览" />
          </SectionCard>
        </section>

        <section class="subscription-section" data-dashboard-subscriptions>
          <header class="subscription-heading">
            <div><span>MY SUBSCRIPTIONS</span><h2>我的订阅看板</h2><p>每排展示 3 张最关注的可视化看板；其余内容保留在下方“展开全部”。</p></div>
            <button data-testid="manage-dashboard-subscriptions" type="button" @click="openSubscriptionManager">管理订阅 · {{ subscribedDashboardCount }} 张</button>
          </header>
          <p v-if="subscriptionStorageWarning" class="subscription-storage-warning" role="status">{{ subscriptionStorageWarning }}</p>
          <div
            v-for="(charts, rowIndex) in subscribedDashboardGroups"
            :key="rowIndex"
            class="decision-grid"
            data-subscription-dashboard-row
            :data-subscription-row-index="rowIndex"
          >
            <SectionCard
              v-for="chart in charts"
              :key="chart.id"
              class="dashboard-dataset-card"
              :title="chart.title"
              :eyebrow="chart.eyebrow"
              :description="chart.description"
              data-subscribed-dashboard
              :data-dashboard-id="chart.id"
            >
              <CrmChart v-if="chart.hasData" :option="chart.option" :height="230" :label="chart.label" />
              <DataState v-else type="empty" :title="chart.emptyTitle" />
            </SectionCard>
          </div>
        </section>

        <section class="more-analysis-shell">
          <button
            class="more-analysis-toggle"
            data-testid="toggle-more-analysis"
            type="button"
            :aria-expanded="showMoreAnalysis"
            @click="showMoreAnalysis = !showMoreAnalysis"
          >
            <span><b>{{ showMoreAnalysis ? '收起更多分析' : '查看更多分析' }}</b><small>客户 / 流程 / 执行</small></span>
            <span class="toggle-state">{{ showMoreAnalysis ? '收起' : '展开全部' }} <b aria-hidden="true">{{ showMoreAnalysis ? '↑' : '↓' }}</b></span>
          </button>

          <div v-if="showMoreAnalysis" class="expanded-analysis">
            <template v-for="group in unsubscribedDashboardGroups" :key="group.id">
              <div class="analysis-heading"><div><span>{{ group.eyebrow }}</span><h2>{{ group.title }}</h2></div><p>{{ group.description }}</p></div>
              <section :class="group.id === 'process' ? 'process-grid' : 'dimension-grid'">
                <SectionCard
                  v-for="chart in group.charts"
                  :key="chart.id"
                  class="dashboard-dataset-card"
                  :title="chart.title"
                  :eyebrow="chart.eyebrow"
                  :description="chart.group === 'core' ? chart.description : undefined"
                  data-expanded-dashboard
                  :data-dashboard-id="chart.id"
                >
                  <CrmChart v-if="chart.hasData" :option="chart.option" :height="230" :label="chart.label" />
                  <DataState v-else type="empty" :title="chart.emptyTitle" message="这里不会用推测数据补齐。" />
                </SectionCard>
              </section>
            </template>
          </div>
        </section>

        <ModalShell
          v-if="subscriptionOpen"
          class="dashboard-subscription-modal"
          title="管理订阅看板"
          eyebrow="BOSS DASHBOARD"
          wide
          :submit-disabled="!draftSubscriptionGroupsValid"
          submit-label="保存订阅"
          @close="subscriptionOpen = false"
          @submit="saveSubscriptions"
        >
          <div class="subscription-manager">
            <div class="subscription-row-manager">
              <div class="subscription-row-tabs" aria-label="订阅排">
                <button
                  v-for="(group, rowIndex) in draftSubscriptionGroups"
                  :key="rowIndex"
                  type="button"
                  data-subscription-row-tab
                  :data-subscription-row-index="rowIndex"
                  :class="{ active: activeSubscriptionGroupIndex === rowIndex }"
                  :aria-pressed="activeSubscriptionGroupIndex === rowIndex"
                  @click="activeSubscriptionGroupIndex = rowIndex"
                >
                  <span>第 {{ rowIndex + 1 }} 排</span>
                  <b :class="{ complete: group.length === 3 }">{{ group.length }}/3</b>
                </button>
                <button
                  type="button"
                  class="add-subscription-row"
                  data-testid="add-subscription-row"
                  :disabled="!canAddSubscriptionGroup"
                  @click="addSubscriptionGroup"
                >
                  ＋ 增加一排
                </button>
              </div>
              <button
                v-if="activeSubscriptionGroupIndex > 0"
                type="button"
                class="delete-subscription-row"
                data-testid="delete-subscription-row"
                @click="deleteActiveSubscriptionGroup"
              >
                删除此排
              </button>
            </div>
            <div class="subscription-manager-summary">
              <div><strong>为第 {{ activeSubscriptionGroupIndex + 1 }} 排选择 3 张看板</strong><p>其他排已使用的看板不能重复选择；设置仅保存在当前浏览器。</p></div>
              <b :class="{ complete: activeDraftSubscriptionGroup.length === 3 }">{{ activeDraftSubscriptionGroup.length }}/3</b>
            </div>
            <section v-for="group in subscriptionCatalogGroups" :key="group.id" class="subscription-group">
              <header><span>{{ group.eyebrow }}</span><h3>{{ group.title }}</h3></header>
              <div class="subscription-options">
                <button
                  v-for="chart in group.charts"
                  :key="chart.id"
                  type="button"
                  class="subscription-option"
                  :class="{ selected: activeDraftSubscriptionGroup.includes(chart.id) }"
                  data-subscription-option
                  :data-subscription-id="chart.id"
                  :aria-pressed="activeDraftSubscriptionGroup.includes(chart.id)"
                  :disabled="isDraftSubscriptionOptionDisabled(chart.id)"
                  @click="toggleDraftSubscription(chart.id)"
                >
                  <span>{{ chart.eyebrow }}</span>
                  <strong>{{ chart.title }}</strong>
                  <small>{{ chart.description }}</small>
                  <b>{{ draftSubscriptionOptionLabel(chart.id) }}</b>
                </button>
              </div>
            </section>
          </div>
        </ModalShell>
      </template>

      <section v-else class="reminder-center" aria-label="未来15天提醒中心">
        <header>
          <div><span class="reminder-icon"><BellRing :size="18" /></span><div><h2>未来 15 天提醒</h2><p>{{ reminderWindow }} · 共 {{ reminders.length }} 项</p></div></div>
          <button type="button" @click="router.push('/calendar')"><CalendarDays :size="14" />打开 Calendar</button>
        </header>
        <DataState v-if="reminderLoading" type="loading" />
        <DataState v-else-if="reminderError" type="error" :message="reminderError" @retry="loadReminders" />
        <div v-else-if="reminders.length" class="reminder-list">
          <button v-for="item in reminders" :key="item.id" type="button" :data-reminder-id="item.id" @click="router.push(item.path)">
            <time>{{ formatDisplayDate(item.date) }}</time>
            <i />
            <div><span class="reminder-type">{{ item.type }}</span><strong>{{ item.title }}</strong><small>{{ item.account }} · {{ item.detail }}</small></div>
            <p><UserRound :size="13" />{{ personnelDisplayName(item.owner) }}</p>
          </button>
        </div>
        <DataState v-else type="empty" title="未来 15 天暂无即将到期活动" message="新的拜访、客户预期或 Demo Test DDL 会自动同步到这里。" />
      </section>

    </template>

    <DataState v-else type="empty" title="经营数据还没有记录" message="记录建立后会自动汇总到这里。" />
  </div>
</template>

<style scoped>
.dashboard-readable-type { font-size: 15px; }
.dashboard-readable-type :deep(.page-eyebrow) { font-size: 11px; }
.dashboard-readable-type :deep(.page-header p) { font-size: 14px; }
.dashboard-readable-type :deep(.page-header small) { font-size: 11px; }
.dashboard-readable-type :deep(.kpi-card h3) { font-size: 13px; }
.dashboard-readable-type :deep(.kpi-card p) { font-size: 11px; }
.dashboard-readable-type :deep(.section-card > header span) { font-size: 10px; }
.dashboard-readable-type :deep(.section-card h2) { font-size: 16px; }
.dashboard-readable-type :deep(.section-card > header p) { font-size: 12px; line-height: 1.45; }
.kpi-grid :deep(.kpi-card.kpi-value-pipeline > strong) { color: #FE9900; }
.kpi-grid :deep(.kpi-card.kpi-value-weighted > strong) { color: #0D9488; }
.kpi-grid :deep(.kpi-card.kpi-value-booking > strong) { color: #6366F1; }
.kpi-grid :deep(.kpi-card.kpi-value-won > strong) { color: var(--crm-navy); }
.source-note { margin: -4px 0 14px; padding: 9px 12px; color: #557076; background: #f4f8f7; border: 1px solid var(--crm-line); border-radius: 9px; font-size: 11px; }
.dashboard-dataset-card { height: 100%; }
.dashboard-dataset-card :deep(.section-body) { display: grid; grid-template-rows: auto minmax(0, 1fr); }
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.management-primary-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(290px, 1fr); gap: 14px; margin-bottom: 14px; }
.team-schedule-list { display: grid; }
.team-schedule-list > button { display: grid; grid-template-columns: 68px 34px minmax(0, 1fr) 116px; align-items: center; gap: 10px; min-height: 59px; padding: 8px 2px; color: inherit; background: #fff; border: 0; border-bottom: 1px solid var(--crm-line); text-align: left; cursor: pointer; }
.team-schedule-list > button:hover { background: #FFFBF5; }
.team-schedule-list > button.active { margin: 0 -8px; padding-right: 8px; padding-left: 8px; background: #FFF8ED; box-shadow: inset 3px 0 0 var(--crm-teal); }
.team-schedule-list time { display: grid; gap: 3px; color: var(--crm-navy); }
.team-schedule-list time strong { font-size: 13px; }
.team-schedule-list time span { color: var(--crm-warning); font-size: 9px; font-weight: 800; }
.schedule-owner { display: grid; width: 30px; height: 30px; place-items: center; color: var(--crm-teal); background: var(--crm-teal-soft); border-radius: 9px; font-size: 11px; font-weight: 900; }
.team-schedule-list > button > div { display: grid; min-width: 0; gap: 4px; }
.team-schedule-list p { display: flex; min-width: 0; align-items: center; gap: 7px; margin: 0; }
.team-schedule-list p strong { overflow: hidden; color: var(--crm-navy); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.team-schedule-list small { overflow: hidden; color: var(--crm-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.schedule-type { flex: none; padding: 3px 6px; color: var(--crm-teal); background: var(--crm-teal-soft); border-radius: 5px; font-size: 9px; }
.schedule-type.request { color: #8a651d; background: var(--crm-warning-soft); }
.schedule-type.test { color: var(--crm-navy); background: #edf1f5; }
.schedule-type.booking { color: var(--crm-positive-ink); background: #eff4d7; }
.schedule-person { display: flex; align-items: center; justify-content: flex-end; gap: 5px; color: var(--crm-text-muted); font-size: 10px; white-space: nowrap; }
.schedule-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 11px; color: var(--crm-text-muted); font-size: 10px; }
.schedule-footer span { display: flex; align-items: center; gap: 6px; }
.schedule-footer b { color: var(--crm-teal); }
.schedule-snapshot { display: grid; gap: 12px; }
.schedule-snapshot > header { display: flex; align-items: center; gap: 12px; padding: 13px; background: linear-gradient(135deg, var(--crm-navy), #174d5d); border-radius: 11px; }
.schedule-snapshot > header time { display: grid; min-width: 55px; height: 55px; place-content: center; color: #fff; background: rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.15); border-radius: 10px; text-align: center; }
.schedule-snapshot > header time strong { font-size: 19px; line-height: 1; }.schedule-snapshot > header time span { margin-top: 4px; color: #bdd4d9; font-size: 10px; }
.schedule-snapshot > header > div { display: grid; gap: 7px; }.schedule-snapshot > header > div > span { color: #d5e4e7; font-size: 11px; font-weight: 700; }
.snapshot-body { display: grid; gap: 7px; padding: 2px 2px 0; }
.snapshot-body > strong { color: var(--crm-navy); font-size: 14px; line-height: 1.45; }.snapshot-body > p { margin: 0; color: var(--crm-teal); font-size: 11px; font-weight: 800; }
.relation-summary { display: flex; align-items: center; gap: 6px; padding: 8px 9px; color: #8a651d!important; background: var(--crm-warning-soft); border-radius: 7px; }
.relation-timeline { display: grid; margin-top: 3px; }
.relation-timeline article { position: relative; display: grid; grid-template-columns: 24px minmax(0,1fr) auto; align-items: center; gap: 8px; padding: 10px 0; border-top: 1px solid var(--crm-line); }
.relation-timeline article.linked:not(:last-child)::after { position: absolute; bottom: -8px; left: 11px; z-index: 0; width: 1px; height: 16px; background: var(--crm-teal); content: ""; }
.relation-node { z-index: 1; display: grid; width: 23px; height: 23px; place-items:center; color:#fff; background:var(--crm-teal); border:3px solid var(--crm-teal-soft); border-radius:50%; font-size:9px; font-weight:900; }
.relation-timeline article > div { display: grid; min-width:0; gap:4px; }
.relation-timeline article header { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.relation-timeline article header b { color:var(--crm-teal); font-size:10px; }.relation-timeline article header time { color:var(--crm-navy); font-size:10px; font-weight:800; }
.relation-timeline article > div > strong { overflow:hidden; color:var(--crm-navy); font-size:10px; text-overflow:ellipsis; white-space:nowrap; }
.relation-timeline article small { display:flex; align-items:center; gap:4px; color:var(--crm-text-muted); font-size:9px; line-height:1.4; }
.relation-timeline article > button { padding:5px 7px; color:var(--crm-teal); background:#fff; border:1px solid var(--crm-line); border-radius:6px; font-size:9px; font-weight:800; cursor:pointer; }
.snapshot-counts { display: grid; grid-template-columns: repeat(4,1fr); gap: 1px; overflow: hidden; background: var(--crm-line); border: 1px solid var(--crm-line); border-radius: 9px; }
.snapshot-counts div { display: grid; gap: 3px; padding: 9px 5px; background:#fff; text-align:center; }.snapshot-counts strong { color: var(--crm-navy); font-size: 16px; }.snapshot-counts span { color: var(--crm-text-muted); font-size: 9px; }
.subscription-section { margin-bottom: 14px; }
.subscription-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin: 0 2px 10px; }
.subscription-heading span { color: var(--crm-teal); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.subscription-heading h2 { margin: 3px 0 0; color: var(--crm-navy); font-size: 18px; }
.subscription-heading p { margin: 4px 0 0; color: var(--crm-text-muted); font-size: 11px; }
.subscription-heading button { flex: none; min-height: 36px; padding: 0 13px; color: var(--crm-teal); background: #fff; border: 1px solid #a9c9c5; border-radius: 9px; font-size: 11px; font-weight: 800; cursor: pointer; }
.subscription-heading button:hover { color: #fff; background: var(--crm-teal); border-color: var(--crm-teal); }
.subscription-storage-warning { margin: 0 0 10px; padding: 9px 12px; color: #8a651d; background: var(--crm-warning-soft); border: 1px solid #ead8ad; border-radius: 8px; font-size: 10px; }
.decision-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 14px; }
.subscription-manager { display: grid; gap: 20px; }
.subscription-row-manager { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.subscription-row-tabs { display: flex; flex: 1; flex-wrap: wrap; gap: 8px; }
.subscription-row-tabs > button { display: inline-flex; min-height: 38px; align-items: center; gap: 9px; padding: 7px 10px; color: var(--crm-text-muted); background: #fff; border: 1px solid var(--crm-line); border-radius: 9px; font-size: 10px; font-weight: 800; cursor: pointer; }
.subscription-row-tabs > button:hover:not(:disabled) { border-color: #8ebbb5; background: #f9fcfb; }
.subscription-row-tabs > button.active { color: var(--crm-navy); background: var(--crm-teal-soft); border-color: var(--crm-teal); box-shadow: inset 3px 0 0 var(--crm-teal); }
.subscription-row-tabs > button:disabled { cursor: not-allowed; opacity: .48; }
.subscription-row-tabs b { min-width: 32px; padding: 4px 6px; color: #8a651d; background: var(--crm-warning-soft); border-radius: 6px; font-size: 9px; text-align: center; }
.subscription-row-tabs b.complete { color: var(--crm-positive-ink); background: var(--crm-positive-soft); }
.subscription-row-tabs .add-subscription-row { color: var(--crm-teal); border-style: dashed; }
.delete-subscription-row { flex: none; min-height: 38px; padding: 0 11px; color: var(--crm-danger); background: #fff; border: 1px solid #e2b9b5; border-radius: 9px; font-size: 10px; font-weight: 800; cursor: pointer; }
.delete-subscription-row:hover { background: var(--crm-danger-soft); }
.subscription-manager-summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; background: var(--crm-surface-muted); border: 1px solid var(--crm-line); border-radius: 11px; }
.subscription-manager-summary strong { color: var(--crm-navy); font-size: 14px; }
.subscription-manager-summary p { margin: 4px 0 0; color: var(--crm-text-muted); font-size: 10px; }
.subscription-manager-summary > b { display: grid; width: 46px; height: 46px; place-items: center; color: #8a651d; background: var(--crm-warning-soft); border-radius: 12px; font-size: 15px; }
.subscription-manager-summary > b.complete { color: var(--crm-positive-ink); background: var(--crm-positive-soft); }
.subscription-group { display: grid; gap: 9px; }
.subscription-group > header span { color: var(--crm-teal); font-size: 8px; font-weight: 800; letter-spacing: .12em; }
.subscription-group > header h3 { margin: 3px 0 0; color: var(--crm-navy); font-size: 14px; }
.subscription-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }
.subscription-option { position: relative; display: grid; min-height: 112px; align-content: start; gap: 6px; padding: 13px 14px; color: inherit; background: #fff; border: 1px solid var(--crm-line); border-radius: 10px; text-align: left; cursor: pointer; }
.subscription-option:hover:not(:disabled) { border-color: #8ebbb5; background: #f9fcfb; }
.subscription-option.selected { background: var(--crm-teal-soft); border-color: var(--crm-teal); box-shadow: inset 3px 0 0 var(--crm-teal); }
.subscription-option:disabled { cursor: not-allowed; opacity: .48; }
.subscription-option > span { color: var(--crm-teal); font-size: 8px; font-weight: 800; letter-spacing: .08em; }
.subscription-option > strong { padding-right: 88px; color: var(--crm-navy); font-size: 12px; }
.subscription-option > small { color: var(--crm-text-muted); font-size: 9px; line-height: 1.45; }
.subscription-option > b { position: absolute; top: 12px; right: 12px; padding: 3px 6px; color: var(--crm-text-muted); background: var(--crm-surface-muted); border-radius: 5px; font-size: 8px; }
.subscription-option.selected > b { color: var(--crm-positive-ink); background: var(--crm-positive-soft); }
.dashboard-page :deep(.dashboard-subscription-modal) { position: fixed; }
.more-analysis-shell { margin-bottom: 14px; }
.more-analysis-toggle { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 18px; padding: 14px 18px; color: var(--crm-navy); background: var(--crm-surface-raised); border: 1px solid var(--crm-line); border-radius: var(--crm-radius-md); box-shadow: 0 1px 1px rgba(31,35,41,.02); cursor: pointer; font: inherit; text-align: left; }
.more-analysis-toggle:hover { border-color: #a9c9c5; background: #fbfdfc; }
.more-analysis-toggle > span:first-child { display: grid; gap: 3px; }
.more-analysis-toggle b { font-size: 14px; }
.more-analysis-toggle small { color: var(--crm-text-muted); font-size: 11px; }
.toggle-state { color: var(--crm-teal); font-size: 12px; font-weight: 700; white-space: nowrap; }
.toggle-state b { display: inline-grid; width: 24px; height: 24px; margin-left: 7px; place-items: center; color: var(--crm-brand-ink); background: var(--crm-teal); border-radius: 999px; }
.expanded-analysis { padding-top: 16px; }
.analysis-heading { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin: 4px 2px 10px; }
.analysis-heading span { color: var(--crm-teal); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.analysis-heading h2 { margin: 3px 0 0; color: var(--crm-navy); font-size: 18px; }
.analysis-heading p { margin: 0; color: var(--crm-text-muted); font-size: 12px; }
.dimension-grid, .process-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.process-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.text-button { color: var(--crm-teal); background: transparent; border: 0; font-size: 12px; font-weight: 700; cursor: pointer; }
.reminder-center{overflow:hidden;background:#fff;border:1px solid var(--crm-line);border-radius:14px;box-shadow:0 6px 22px rgba(31,35,41,.04)}.reminder-center>header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:17px 18px;border-bottom:1px solid var(--crm-line)}.reminder-center>header>div{display:flex;align-items:center;gap:11px}.reminder-icon{display:grid;width:38px;height:38px;place-items:center;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:11px}.reminder-center h2{margin:0;color:var(--crm-navy);font-size:16px}.reminder-center header p{margin:4px 0 0;color:var(--crm-text-muted);font-size:10px}.reminder-center>header>button{display:inline-flex;height:34px;align-items:center;gap:6px;padding:0 11px;color:var(--crm-teal);background:#fff;border:1px solid var(--crm-line);border-radius:8px;font-size:10px;font-weight:800;cursor:pointer}.reminder-list{display:grid}.reminder-list>button{display:grid;grid-template-columns:82px 8px minmax(0,1fr) 150px;align-items:center;gap:13px;min-height:78px;padding:11px 18px;background:#fff;border:0;border-bottom:1px solid var(--crm-line);text-align:left;cursor:pointer}.reminder-list>button:last-child{border-bottom:0}.reminder-list>button:hover{background:#FFFBF5}.reminder-list time{display:grid;gap:4px;color:var(--crm-navy)}.reminder-list time strong{font-size:15px}.reminder-list time span{color:var(--crm-warning);font-size:10px;font-weight:800}.reminder-list>button>i{width:8px;height:8px;background:var(--crm-teal);border:2px solid #d7eeea;border-radius:50%}.reminder-list>button>div{display:grid;gap:4px}.reminder-type{width:fit-content;padding:3px 6px;color:var(--crm-teal);background:var(--crm-teal-soft);border-radius:5px;font-size:9px;font-weight:800}.reminder-list>button>div>strong{color:var(--crm-text);font-size:12px}.reminder-list>button small{color:var(--crm-text-muted);font-size:10px}.reminder-list>button>p{display:flex;align-items:center;justify-content:flex-end;gap:6px;margin:0;color:var(--crm-text-muted);font-size:10px}
@media (max-width: 1450px) { .management-primary-grid { grid-template-columns: minmax(0, 1.7fr) minmax(270px, 1fr); } .dimension-grid, .process-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 1180px) { .management-primary-grid, .decision-grid { grid-template-columns: 1fr; } .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 760px) { .dimension-grid, .process-grid, .kpi-grid { grid-template-columns: 1fr; } .subscription-heading, .subscription-row-manager { align-items: flex-start; flex-direction: column; }.subscription-row-tabs{width:100%}.subscription-options{grid-template-columns:repeat(2,minmax(0,1fr))}.analysis-heading { display: block; } .analysis-heading p { margin-top: 5px; }.team-schedule-list>button{grid-template-columns:60px 32px 1fr}.schedule-person{grid-column:3;justify-content:flex-start}.reminder-center>header{align-items:flex-start;flex-direction:column}.reminder-list>button{grid-template-columns:66px 8px 1fr}.reminder-list>button>p{grid-column:3;justify-content:flex-start} }
@media (max-width: 560px) { .subscription-options { grid-template-columns: 1fr; } }
</style>
