<script setup lang="ts">
import { requestErrorMessage } from '@/api/request-state'
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
import { useI18n, useLocaleMessage } from '@/i18n'

const props = withDefaults(defineProps<{ apiClient?: CrmApi }>(), { apiClient: () => defaultApi })
const store = useDashboardStore()
const app = useAppStore()
const router = useRouter()
const { t, message, locale } = useI18n()
const showMoreAnalysis = ref(false)
type ReminderType = '拜访' | '客户预期' | 'Demo Test DDL' | 'Booking DDL' | '行动截止'
interface DeadlineReminder {
  id: string
  type: ReminderType
  date: string
  title: string
  account: string
  owner: string
  detail: string | ReturnType<typeof message>
  path: string
  demoRequestId?: string
  evaluationId?: string
}
const reminderLoading = ref(false)
const reminderError = useLocaleMessage()
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
type ProcessDimension = 'requirements' | 'budget' | 'actions' | 'timeliness' | 'demo' | 'priority' | 'evaluation' | 'run-results' | 'visits' | 'risk'
const PROCESS_DIMENSION_LABELS: Record<ProcessDimension, Record<string, [string, string]>> = {
  requirements: {
    '需求识别': ['需求识别', 'Need identified'], '技术确认': ['技术确认', 'Technical confirmation'], 'Demo验证': ['Demo验证', 'Demo validation'],
    '预算审批': ['预算审批', 'Budget approval'], '采购计划': ['采购计划', 'Procurement planning'], '已确认': ['已确认', 'Confirmed'],
  },
  budget: { Confirmed: ['已确认', 'Confirmed'], 'In Review': ['审核中', 'In review'], Unknown: ['未知', 'Unknown'] },
  actions: {
    Requirement: ['需求', 'Requirement'], Visit: ['拜访', 'Visit'], Deal: ['商机', 'Deal'], 'Demo Request': ['Demo Request', 'Demo request'],
    Evaluation: ['评估', 'Evaluation'], Contract: ['合同', 'Contract'],
  },
  timeliness: { '已逾期': ['已逾期', 'Overdue'], '未逾期': ['未逾期', 'On time'] },
  demo: {
    Draft: ['草稿', 'Draft'], 'Engineer Review': ['工程审核', 'Engineer review'], 'Engineer Returned': ['工程退回', 'Returned by engineering'],
    'Manager Approval': ['经理审批', 'Manager approval'], 'Manager Rejected': ['经理拒绝', 'Rejected by manager'], Converted: ['已转 Demo', 'Converted to Demo'], Cancelled: ['已取消', 'Cancelled'],
  },
  priority: { Critical: ['紧急', 'Critical'], High: ['高', 'High'], Medium: ['中', 'Medium'], Low: ['低', 'Low'] },
  evaluation: {
    Requested: ['已申请', 'Requested'], 'Scope Confirmed': ['范围已确认', 'Scope confirmed'], 'Sample Received': ['已收到样品', 'Sample received'],
    Scheduled: ['已排期', 'Scheduled'], Testing: ['测试中', 'Testing'], Analysis: ['分析中', 'Analysis'], 'Internal Review': ['内部审核', 'Internal review'],
    'Customer Review': ['客户审核', 'Customer review'], Accepted: ['已接受', 'Accepted'], Rejected: ['已拒绝', 'Rejected'],
  },
  'run-results': { Planned: ['计划中', 'Planned'], Completed: ['已完成', 'Completed'] },
  visits: {
    Planned: ['待提交拜访记录', 'Minutes pending'], Visited: ['已完成', 'Completed'], 'Minutes Submitted': ['拜访记录已提交', 'Minutes submitted'],
    'Manager Reviewed': ['管理者已审核', 'Manager reviewed'],
  },
  risk: { 稳健: ['稳健', 'Steady'], 关注: ['关注', 'Watch'], 高风险: ['高风险', 'High risk'] },
}
function processRows<T extends { label: string }>(rows: T[], dimension?: ProcessDimension) {
  if (!dimension) return rows
  const labels = PROCESS_DIMENSION_LABELS[dimension]
  const index = locale.value === 'en-US' ? 1 : 0
  return rows.map((item) => labels[item.label] ? { ...item, label: labels[item.label][index] } : item)
}
const subscriptionGroups = ref<DashboardSubscriptionGroups>(
  DEFAULT_BOSS_DASHBOARD_SUBSCRIPTION_GROUPS.map((group) => [...group]),
)
const draftSubscriptionGroups = ref<DashboardSubscriptionGroups>([])
const activeSubscriptionGroupIndex = ref(0)
const subscriptionOpen = ref(false)
const subscriptionStorageWarning = ref(false)

const managementView = computed(() => app.bootstrap?.user.role === 'Manager')
const activeCurrency = computed(() => store.data?.kpis.moneyByCurrency[0]?.currency ?? 'CNY')
const activeMoney = computed(() => store.data?.kpis.moneyByCurrency.find((item) => item.currency === activeCurrency.value))
const bookingOption = computed(() => buildBookingOption((store.data?.bookingByMonth ?? []).filter((item) => item.currency === activeCurrency.value).map((item) => ({ ...item, amount: Number(item.amount) })), locale.value))
const evaluationOption = computed(() => buildCountBreakdownOption(processRows(store.data?.process.evaluationByStatus ?? [], 'evaluation'), locale.value))
const accountOption = computed(() => buildAccountContributionOption((store.data?.topAccounts ?? []).filter((item) => item.currency === activeCurrency.value).slice(0, 6).map((item) => ({ label: item.accountName, pipeline: Number(item.pipeline), booking: Number(item.booking) })), locale.value))
const regionOption = computed(() => buildValueDistributionOption((store.data?.regionDistribution ?? []).filter((item) => item.currency === activeCurrency.value).map((item) => ({ ...item, pipeline: Number(item.pipeline), booking: Number(item.booking) })), locale.value))
const tierOption = computed(() => buildCountBreakdownOption(store.data?.tierDistribution ?? [], locale.value))
const riskOption = computed(() => buildCountBreakdownOption(processRows(store.data?.riskDistribution ?? [], 'risk'), locale.value))

const processCharts = computed<ProcessDashboardChart[]>(() => {
  const process = store.data?.process
  return [
    { key: 'requirements', title: (locale.value === 'en-US' ? 'Requirement Status' : '需求状态'), eyebrow: (locale.value === 'en-US' ? 'REQUIREMENTS' : '采购需求'), rows: process?.requirementsByStatus ?? [], option: buildBookingOption(processRows(process?.requirementsByStatus ?? [], 'requirements'), locale.value), label: (locale.value === 'en-US' ? 'Purchase requirement status and budget value' : '采购需求状态与预算金额') },
    { key: 'budget', title: (locale.value === 'en-US' ? 'Budget Status' : '预算状态'), eyebrow: (locale.value === 'en-US' ? 'BUDGET' : '预算'), rows: process?.budgetByStatus ?? [], option: buildBookingOption(processRows(process?.budgetByStatus ?? [], 'budget'), locale.value), label: (locale.value === 'en-US' ? 'Budget status and requirement value' : '预算状态与需求金额') },
    { key: 'actions', title: (locale.value === 'en-US' ? 'Action Sources' : '行动来源'), eyebrow: (locale.value === 'en-US' ? 'OPEN ACTIONS' : '待办行动'), rows: process?.actionsBySource ?? [], option: buildCountBreakdownOption(processRows(process?.actionsBySource ?? [], 'actions'), locale.value), label: (locale.value === 'en-US' ? 'Open actions by source' : '按来源统计待办行动') },
    { key: 'action-timeliness', title: (locale.value === 'en-US' ? 'Action Timeliness' : '行动时效'), eyebrow: (locale.value === 'en-US' ? 'ACTION TIMELINESS' : '行动时效'), rows: process?.actionsByTimeliness ?? [], option: buildCountBreakdownOption(processRows(process?.actionsByTimeliness ?? [], 'timeliness'), locale.value), label: (locale.value === 'en-US' ? 'Open actions by due status' : '按到期状态统计待办行动') },
    { key: 'demo', title: (locale.value === 'en-US' ? 'Demo Request Status' : 'Demo 申请状态'), eyebrow: (locale.value === 'en-US' ? 'DEMO REQUEST' : 'Demo 申请'), rows: process?.demoByStatus ?? [], option: buildCountBreakdownOption(processRows(process?.demoByStatus ?? [], 'demo'), locale.value), label: (locale.value === 'en-US' ? 'Demo Requests by status' : '按状态统计 Demo 申请') },
    { key: 'demo-priority', title: (locale.value === 'en-US' ? 'Demo Priority' : 'Demo 优先级'), eyebrow: (locale.value === 'en-US' ? 'DEMO PRIORITY' : 'Demo 优先级'), rows: process?.demoByPriority ?? [], option: buildCountBreakdownOption(processRows(process?.demoByPriority ?? [], 'priority'), locale.value), label: (locale.value === 'en-US' ? 'Demo Requests by priority' : '按优先级统计 Demo 申请') },
    { key: 'evaluation-runs', title: (locale.value === 'en-US' ? 'Test Run Results' : '测试执行结果'), eyebrow: (locale.value === 'en-US' ? 'TEST RUNS' : '测试执行'), rows: process?.evaluationRunResults ?? [], option: buildCountBreakdownOption(processRows(process?.evaluationRunResults ?? [], 'run-results'), locale.value), label: (locale.value === 'en-US' ? 'Test run plans and results' : '测试执行计划与结果') },
    { key: 'visits', title: (locale.value === 'en-US' ? 'Visit Status' : '拜访状态'), eyebrow: (locale.value === 'en-US' ? 'VISITS' : '拜访'), rows: process?.visitsByStatus ?? [], option: buildCountBreakdownOption(processRows(process?.visitsByStatus ?? [], 'visits'), locale.value), label: (locale.value === 'en-US' ? 'Customer visits by status' : '按状态统计客户拜访') },
    { key: 'visit-owner', title: (locale.value === 'en-US' ? 'Visit Owners' : '拜访负责人'), eyebrow: (locale.value === 'en-US' ? 'VISIT OWNER' : '拜访负责人'), rows: process?.visitsByOwner ?? [], option: buildCountBreakdownOption(process?.visitsByOwner ?? [], locale.value), label: (locale.value === 'en-US' ? 'Customer visits by owner' : '按负责人统计客户拜访') },
  ]
})

const dashboardGroupMeta = computed<Record<DashboardChartGroup, { eyebrow: string; title: string; description: string }>>(() => ({
  core: { eyebrow: (locale.value === 'en-US' ? 'CORE ANALYSIS' : '核心分析'), title: (locale.value === 'en-US' ? 'Commercial Performance' : '业务表现'), description: (locale.value === 'en-US' ? 'Demo, Booking, and key-account performance.' : 'Demo、订单和重点客户表现。') },
  customer: { eyebrow: (locale.value === 'en-US' ? 'CUSTOMER ANALYSIS' : '客户分析'), title: (locale.value === 'en-US' ? 'Account Mix & Risk' : '客户分布与风险'), description: (locale.value === 'en-US' ? 'Review account distribution by region, tier, and risk.' : '按区域、等级和风险查看客户分布。') },
  process: { eyebrow: (locale.value === 'en-US' ? 'PROCESS ANALYSIS' : '流程分析'), title: (locale.value === 'en-US' ? 'Process & Execution' : '流程与执行'), description: (locale.value === 'en-US' ? 'Charts use current requirements, actions, demos, evaluations, and visit records.' : '图表基于当前需求、行动、Demo、评估和拜访记录。') },
}))

const visualDashboardCatalog = computed<DashboardChartItem[]>(() => [
  {
    id: 'evaluation-status',
    group: 'core',
    title: t('dashboard.chart.evaluationTitle'),
    eyebrow: 'EVALUATION',
    description: t('dashboard.chart.evaluationDescription'),
    option: evaluationOption.value,
    hasData: Boolean(store.data?.process.evaluationByStatus.length),
    emptyTitle: t('dashboard.chart.evaluationEmpty'),
    label: t('dashboard.chart.evaluationTitle'),
  },
  {
    id: 'booking-month',
    group: 'core',
    title: t('dashboard.chart.bookingTitle'),
    eyebrow: 'BOOKING BY MONTH',
    description: t('dashboard.chart.bookingDescription'),
    option: bookingOption.value,
    hasData: Boolean(store.data?.bookingByMonth.length),
    emptyTitle: t('dashboard.chart.bookingEmpty'),
    label: t('dashboard.chart.bookingTitle'),
  },
  {
    id: 'top-accounts',
    group: 'core',
    title: t('dashboard.chart.topAccountsTitle'),
    eyebrow: 'TOP ACCOUNTS',
    description: t('dashboard.chart.topAccountsDescription'),
    option: accountOption.value,
    hasData: Boolean(store.data?.topAccounts.length),
    emptyTitle: t('dashboard.chart.topAccountsEmpty'),
    label: t('dashboard.chart.topAccountsTitle'),
  },
  {
    id: 'region',
    group: 'customer',
    title: t('dashboard.chart.regionTitle'),
    eyebrow: 'REGION',
    description: t('dashboard.chart.regionDescription'),
    option: regionOption.value,
    hasData: Boolean(store.data?.regionDistribution.length),
    emptyTitle: t('dashboard.chart.regionEmpty'),
    label: t('dashboard.chart.regionTitle'),
  },
  {
    id: 'tier',
    group: 'customer',
    title: t('dashboard.chart.tierTitle'),
    eyebrow: 'TIER',
    description: t('dashboard.chart.tierDescription'),
    option: tierOption.value,
    hasData: Boolean(store.data?.tierDistribution.length),
    emptyTitle: t('dashboard.chart.tierEmpty'),
    label: t('dashboard.chart.tierTitle'),
  },
  {
    id: 'risk',
    group: 'customer',
    title: t('dashboard.chart.riskTitle'),
    eyebrow: 'RISK',
    description: t('dashboard.chart.riskDescription'),
    option: riskOption.value,
    hasData: Boolean(store.data?.riskDistribution.length),
    emptyTitle: t('dashboard.chart.riskEmpty'),
    label: t('dashboard.chart.riskTitle'),
  },
  ...processCharts.value.map((chart) => ({
    id: chart.key,
    group: 'process' as const,
    title: chart.title,
    eyebrow: chart.eyebrow,
    description: chart.label,
    option: chart.option,
    hasData: chart.rows.length > 0,
    emptyTitle: t('dashboard.chartNoRecords', { title: chart.title }),
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
      ...dashboardGroupMeta.value[group],
      charts: visualDashboardCatalog.value.filter((chart) => chart.group === group && !selected.has(chart.id)),
    }))
    .filter((group) => group.charts.length > 0)
})

const subscriptionCatalogGroups = computed(() => (['core', 'customer', 'process'] as const).map((group) => ({
  id: group,
  ...dashboardGroupMeta.value[group],
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
  if (owner === activeSubscriptionGroupIndex.value) return t('dashboard.subscribed')
  if (owner >= 0) return t('dashboard.rowSubscribed', { row: owner + 1 })
  return t('dashboard.select')
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
  subscriptionStorageWarning.value = !saved
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
  return days === 0 ? t('dashboard.dueToday') : t('dashboard.daysRemaining', { days })
}
function reminderDetail(item: DeadlineReminder) {
  return typeof item.detail === 'string' ? item.detail : item.detail[locale.value]
}
function reminderTypeLabel(type: ReminderType) {
  if (type === '拜访') return t('dashboard.reminder.visit')
  if (type === '客户预期') return t('dashboard.reminder.customer')
  if (type === 'Demo Test DDL') return t('dashboard.reminder.test')
  if (type === 'Booking DDL') return t('dashboard.reminder.booking')
  return t('dashboard.reminder.action')
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
  if (gap === 0) return t('dashboard.demoAligned')
  return gap < 0 ? t('dashboard.demoEarly', { days: Math.abs(gap) }) : t('dashboard.demoLate', { days: gap })
})
const scheduleCounts = computed(() => [
  { type: '拜访', label: t('calendar.event.visit'), count: reminders.value.filter((item) => item.type === '拜访').length },
  { type: '客户预期', label: t('calendar.event.demoRequest'), count: reminders.value.filter((item) => item.type === '客户预期').length },
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
          detail: item.criteria || message('dashboard.demoTestDue'), path: '/evaluations',
          demoRequestId: item.demoRequestId || linkedRequest?.id, evaluationId: item.id,
        }
      }),
      ...pipeline.data.bookings.filter((item) => item.status !== 'Cancelled' && item.ddl).map((item) => ({
        id: `booking-${item.id}`, type: 'Booking DDL' as const, date: item.ddl,
        title: `${item.id} · ${item.equipment}`, account: item.accountName, owner: item.owner,
        detail: message('dashboard.quantityStatus', { quantity: item.quantity, status: item.status }), path: '/booking',
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
    reminderError.value = requestErrorMessage(reason, message('dashboard.reminderLoadFailed'))
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
      :eyebrow="managementView ? t('dashboard.managementEyebrow') : t('dashboard.reminderEyebrow')"
      :title="t('dashboard.title')"
      :description="managementView ? t('dashboard.managementDescription') : t('dashboard.reminderDescription')"
      :updated-at="store.data?.asOf"
    >
      <StatusBadge v-if="managementView" :label="t('dashboard.managerBadge')" tone="info" />
      <StatusBadge v-else :label="t('dashboard.reminderBadge')" tone="neutral" />
    </PageHeader>

    <DataState v-if="store.loading && !store.data" type="loading" />
    <DataState v-else-if="store.denied" type="denied" :message="store.error" :request-id="store.requestId" />
    <DataState v-else-if="store.error" type="error" :message="store.error" :request-id="store.requestId" data-testid="retry-dashboard" @retry="load" />

    <template v-else-if="store.data">
      <DataNotice v-if="store.stale" :message="store.staleMessage" :request-id="store.requestId" @refresh="load" />

      <p v-if="managementView" class="source-note">{{ t('dashboard.sourceNote') }}</p>

      <section v-if="managementView" class="kpi-grid" :aria-label="t('dashboard.kpiLabel')">
        <KpiCard class="kpi-value-pipeline" label="Open Pipeline" :value="formatMoney(activeMoney?.openPipeline ?? '0.00', activeCurrency)" :detail="t('dashboard.openPipelineDetail')" :icon="BriefcaseBusiness" tone="navy" />
        <KpiCard class="kpi-value-weighted" label="Weighted Pipeline" :value="formatMoney(activeMoney?.weightedPipeline ?? '0.00', activeCurrency)" :detail="t('dashboard.weightedPipelineDetail')" :icon="Scale" tone="teal" />
        <KpiCard class="kpi-value-booking" label="Confirmed Booking" :value="formatMoney(activeMoney?.confirmedBooking ?? '0.00', activeCurrency)" :detail="t('dashboard.confirmedBookingDetail')" :icon="Banknote" tone="lime" />
        <KpiCard class="kpi-value-won" :label="t('dashboard.closedWon')" :value="formatMoney(activeMoney?.cumulativeWon ?? '0.00', activeCurrency)" :detail="t('dashboard.closedWonDetail')" :icon="CircleDollarSign" tone="amber" />
      </section>

      <template v-if="managementView">
        <section class="management-primary-grid">
          <SectionCard :title="t('dashboard.teamHighlights')" eyebrow="TEAM CALENDAR" :description="t('dashboard.teamHighlightsDescription')">
            <template #action><button class="text-button" type="button" @click="router.push('/calendar')">{{ t('dashboard.viewCalendar') }}</button></template>
            <DataState v-if="reminderLoading" type="loading" />
            <DataState v-else-if="reminderError" type="error" :message="reminderError" @retry="loadReminders" />
            <div v-else-if="teamSchedule.length" class="team-schedule-list" :aria-label="t('dashboard.teamSchedule')">
              <button v-for="item in teamSchedule" :key="item.id" type="button" :class="{ active: selectedTeamSchedule?.id === item.id }" @click="selectedScheduleId = item.id">
                <time>{{ formatDisplayDate(item.date) }}</time>
                <span class="schedule-owner">{{ personnelDisplayName(item.owner).slice(0, 1) }}</span>
                <div>
                  <p><b class="schedule-type" :class="{ request: item.type === '客户预期', test: item.type === 'Demo Test DDL', booking: item.type === 'Booking DDL' }">{{ reminderTypeLabel(item.type) }}</b><strong>{{ item.title }}</strong></p>
                  <small>{{ item.account }} · {{ reminderDetail(item) }}</small>
                </div>
                <span class="schedule-person"><UserRound :size="12" />{{ personnelDisplayName(item.owner) }}</span>
              </button>
            </div>
            <DataState v-else type="empty" :title="t('dashboard.noTeamSchedule')" :message="t('dashboard.scheduleAutoSync')" />
            <footer class="schedule-footer">
              <span><CalendarDays :size="13" />{{ t('dashboard.calendarSync') }}</span>
              <b>{{ t('dashboard.showRecent', { count: teamSchedule.length }) }}</b>
            </footer>
          </SectionCard>

          <SectionCard :title="t('dashboard.relatedPreview')" eyebrow="RELATED SCHEDULE" :description="t('dashboard.relatedPreviewDescription')">
            <div v-if="selectedTeamSchedule" class="schedule-snapshot">
              <header>
                <time>{{ formatDisplayDate(selectedTeamSchedule.date) }}</time>
                <div><b class="schedule-type" :class="{ request: selectedTeamSchedule.type === '客户预期', test: selectedTeamSchedule.type === 'Demo Test DDL', booking: selectedTeamSchedule.type === 'Booking DDL' }">{{ reminderTypeLabel(selectedTeamSchedule.type) }}</b></div>
              </header>
              <div class="snapshot-body">
                <strong>{{ selectedTeamSchedule.account }}</strong>
                <p v-if="demoTimingRelation" class="relation-summary"><CalendarDays :size="13" />{{ demoTimingRelation }}</p>
                <p v-else>{{ selectedTeamSchedule.title }}</p>
                <div class="relation-timeline">
                  <article v-for="(item, index) in relatedScheduleItems" :key="item.id" :class="{ linked: relatedScheduleItems.length > 1 }">
                    <span class="relation-node">{{ index + 1 }}</span>
                    <div>
                      <header><b>{{ reminderTypeLabel(item.type) }}</b><time>{{ formatDisplayDate(item.date) }}</time></header>
                      <strong>{{ item.title }}</strong>
                      <small><UserRound :size="11" />{{ personnelDisplayName(item.owner) }} · {{ reminderDetail(item) }}</small>
                    </div>
                    <button type="button" @click="router.push(item.path)">{{ t('dashboard.view') }}</button>
                  </article>
                </div>
              </div>
              <footer class="snapshot-counts">
                <div v-for="item in scheduleCounts" :key="item.type"><strong>{{ item.count }}</strong><span>{{ item.label }}</span></div>
              </footer>
            </div>
            <DataState v-else type="empty" :title="t('dashboard.noPreview')" />
          </SectionCard>
        </section>

        <section class="subscription-section" data-dashboard-subscriptions>
          <header class="subscription-heading">
            <div><span>MY SUBSCRIPTIONS</span><h2>{{ t('dashboard.mySubscriptions') }}</h2><p>{{ t('dashboard.subscriptionDescription') }}</p></div>
            <button data-testid="manage-dashboard-subscriptions" type="button" @click="openSubscriptionManager">{{ t('dashboard.manageSubscriptions', { count: subscribedDashboardCount }) }}</button>
          </header>
          <p v-if="subscriptionStorageWarning" class="subscription-storage-warning" role="status">{{ t('dashboard.subscriptionSaveFailed') }}</p>
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
            <span><b>{{ showMoreAnalysis ? t('dashboard.collapseMore') : t('dashboard.viewMore') }}</b><small>{{ t('dashboard.customerProcessExecution') }}</small></span>
            <span class="toggle-state">{{ showMoreAnalysis ? t('dashboard.collapse') : t('dashboard.expandAll') }} <b aria-hidden="true">{{ showMoreAnalysis ? '↑' : '↓' }}</b></span>
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
                  <DataState v-else type="empty" :title="chart.emptyTitle" :message="t('dashboard.noSyntheticData')" />
                </SectionCard>
              </section>
            </template>
          </div>
        </section>

        <ModalShell
          v-if="subscriptionOpen"
          class="dashboard-subscription-modal"
          :title="t('dashboard.subscriptionModal')"
          eyebrow="BOSS DASHBOARD"
          wide
          :submit-disabled="!draftSubscriptionGroupsValid"
          :submit-label="t('dashboard.saveSubscriptions')"
          @close="subscriptionOpen = false"
          @submit="saveSubscriptions"
        >
          <div class="subscription-manager">
            <div class="subscription-row-manager">
              <div class="subscription-row-tabs" :aria-label="t('dashboard.subscriptionRows')">
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
                  <span>{{ t('dashboard.row', { row: rowIndex + 1 }) }}</span>
                  <b :class="{ complete: group.length === 3 }">{{ group.length }}/3</b>
                </button>
                <button
                  type="button"
                  class="add-subscription-row"
                  data-testid="add-subscription-row"
                  :disabled="!canAddSubscriptionGroup"
                  @click="addSubscriptionGroup"
                >
                  ＋ {{ t('dashboard.addRow') }}
                </button>
              </div>
              <button
                v-if="activeSubscriptionGroupIndex > 0"
                type="button"
                class="delete-subscription-row"
                data-testid="delete-subscription-row"
                @click="deleteActiveSubscriptionGroup"
              >
                {{ t('dashboard.deleteRow') }}
              </button>
            </div>
            <div class="subscription-manager-summary">
              <div><strong>{{ t('dashboard.chooseCharts', { row: activeSubscriptionGroupIndex + 1 }) }}</strong><p>{{ t('dashboard.noDuplicateCharts') }}</p></div>
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

      <section v-else class="reminder-center" :aria-label="t('dashboard.reminderCenter')">
        <header>
          <div><span class="reminder-icon"><BellRing :size="18" /></span><div><h2>{{ t('dashboard.next15Days') }}</h2><p>{{ reminderWindow }} · {{ t('dashboard.reminderCount', { count: reminders.length }) }}</p></div></div>
          <button type="button" @click="router.push('/calendar')"><CalendarDays :size="14" />{{ t('dashboard.openCalendar') }}</button>
        </header>
        <DataState v-if="reminderLoading" type="loading" />
        <DataState v-else-if="reminderError" type="error" :message="reminderError" @retry="loadReminders" />
        <div v-else-if="reminders.length" class="reminder-list">
          <button v-for="item in reminders" :key="item.id" type="button" :data-reminder-id="item.id" @click="router.push(item.path)">
            <time>{{ formatDisplayDate(item.date) }}</time>
            <i />
            <div><span class="reminder-type">{{ reminderTypeLabel(item.type) }}</span><strong>{{ item.title }}</strong><small>{{ item.account }} · {{ reminderDetail(item) }}</small></div>
            <p><UserRound :size="13" />{{ personnelDisplayName(item.owner) }}</p>
          </button>
        </div>
        <DataState v-else type="empty" :title="t('dashboard.noUpcoming')" :message="t('dashboard.reminderSync')" />
      </section>

    </template>

    <DataState v-else type="empty" :title="t('dashboard.noBusinessData')" :message="t('dashboard.noBusinessDataHint')" />
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
