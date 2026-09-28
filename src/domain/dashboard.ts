import type {
  AccountSummaryDto,
  ActionDto,
  BookingDto,
  DashboardDto,
  DemoRequestDto,
  EvaluationDto,
  RequirementDto,
} from '@/types/crm'
import { addMoney, type DecimalAmount } from '@/domain/money'
import { OPEN_OPPORTUNITY_STAGES, isOpenOpportunityStage } from '@/domain/opportunity-stages'

interface VisitStatusLike { status: string; owner: string }
interface DashboardOpportunityLike {
  id: string
  accountId: string
  stage: string
  amount: DecimalAmount
  currency: string
  owner: string
}

export interface ManagementDashboardInput {
  asOf: string
  accounts: AccountSummaryDto[]
  actions: ActionDto[]
  bookings: BookingDto[]
  demoRequests: DemoRequestDto[]
  evaluations: EvaluationDto[]
  opportunities: DashboardOpportunityLike[]
  requirements: RequirementDto[]
  visits?: VisitStatusLike[]
}

const sumMoney = <T>(rows: T[], read: (row: T) => DecimalAmount) => addMoney(rows.map(read))

function countBy<T>(rows: T[], read: (row: T) => string) {
  const counts = new Map<string, number>()
  rows.forEach((row) => counts.set(read(row), (counts.get(read(row)) ?? 0) + 1))
  return [...counts].map(([label, count]) => ({ label, count }))
}

function amountBy<T>(rows: T[], readLabel: (row: T) => string, readAmount: (row: T) => number) {
  const totals = new Map<string, { count: number; amount: number }>()
  rows.forEach((row) => {
    const label = readLabel(row)
    const current = totals.get(label) ?? { count: 0, amount: 0 }
    totals.set(label, { count: current.count + 1, amount: current.amount + readAmount(row) })
  })
  return [...totals].map(([label, value]) => ({ label, count: value.count, amount: Math.round(value.amount) }))
}

export function buildManagementDashboard(input: ManagementDashboardInput): DashboardDto {
  // PO received is the won outcome; the open pipeline and the funnel count only the six open milestones.
  const isWon = (stage: string) => stage === 'po_received'
  const open = input.opportunities.filter((item) => isOpenOpportunityStage(item.stage))
  const confirmed = input.bookings.filter((item) => item.status === 'Confirmed')
  const accountById = new Map(input.accounts.map((account) => [account.id, account]))
  const currencies = [...new Set([...input.opportunities, ...input.bookings].map((item) => item.currency))].sort()
  const moneyByCurrency = currencies.map((currency) => {
    const currencyOpen = open.filter((item) => item.currency === currency)
    return {
      currency,
      openPipeline: sumMoney(currencyOpen, (item) => item.amount),
      confirmedBooking: sumMoney(confirmed.filter((item) => item.currency === currency), (item) => item.amount),
      cumulativeWon: sumMoney(input.opportunities.filter((item) => item.currency === currency && isWon(item.stage)), (item) => item.amount),
    }
  })

  const funnel = OPEN_OPPORTUNITY_STAGES.flatMap((stage) => {
    const rows = open.filter((item) => item.stage === stage)
    return [...new Set(rows.map((item) => item.currency))].sort().map((currency) => {
      const currencyRows = rows.filter((item) => item.currency === currency)
      return { stage, currency, amount: sumMoney(currencyRows, (item) => item.amount), count: currencyRows.length }
    })
  })

  const ownerNames = [...new Set([...open.map((item) => item.owner), ...confirmed.map((item) => item.owner)])].sort()
  const ownerPerformance = ownerNames.flatMap((owner) => {
    const rows = [...open, ...confirmed].filter((item) => item.owner === owner)
    return [...new Set(rows.map((item) => item.currency))].sort().map((currency) => {
      const ownerOpen = open.filter((item) => item.owner === owner && item.currency === currency)
      return { owner, currency, pipeline: sumMoney(ownerOpen, (item) => item.amount), booking: sumMoney(confirmed.filter((item) => item.owner === owner && item.currency === currency), (item) => item.amount) }
    })
  })

  const accountIds = [...new Set([...open.map((item) => item.accountId), ...confirmed.map((item) => item.accountId)])]
  const topAccounts = accountIds.flatMap((accountId) => {
    const rows = [...open, ...confirmed].filter((item) => item.accountId === accountId)
    return [...new Set(rows.map((item) => item.currency))].sort().map((currency) => ({
      accountId, accountName: accountById.get(accountId)?.name ?? accountId, currency,
      pipeline: sumMoney(open.filter((item) => item.accountId === accountId && item.currency === currency), (item) => item.amount),
      booking: sumMoney(confirmed.filter((item) => item.accountId === accountId && item.currency === currency), (item) => item.amount),
    }))
  }).sort((a, b) => a.accountName.localeCompare(b.accountName) || a.currency.localeCompare(b.currency))

  const mix = (read: (account: AccountSummaryDto) => string) => [...new Set(input.accounts.map(read))].flatMap((label) => {
    const ids = new Set(input.accounts.filter((account) => read(account) === label).map((account) => account.id))
    const rows = [...open, ...confirmed].filter((item) => ids.has(item.accountId))
    return [...new Set(rows.map((item) => item.currency))].sort().map((currency) => ({
      label, currency,
      pipeline: sumMoney(open.filter((item) => ids.has(item.accountId) && item.currency === currency), (item) => item.amount),
      booking: sumMoney(confirmed.filter((item) => ids.has(item.accountId) && item.currency === currency), (item) => item.amount),
    }))
  })

  const bookingByMonth = [...new Set(confirmed.map((item) => `${item.bookingDate.slice(0, 7)}|${item.currency}`))].sort().map((key) => {
    const [label, currency] = key.split('|')
    const rows = confirmed.filter((item) => item.bookingDate.startsWith(label) && item.currency === currency)
    return { label, currency, amount: sumMoney(rows, (item) => item.amount), count: rows.length }
  })

  const today = input.asOf.slice(0, 10)
  return {
    asOf: input.asOf,
    kpis: {
      moneyByCurrency,
      overdueActions: input.actions.filter((item) => item.status === 'Open' && item.due < today).length,
      pendingDemoRequests: input.demoRequests.filter((item) => ['Engineer Review', 'Manager Approval'].includes(item.status)).length,
      activeEvaluations: input.evaluations.filter((item) => !['Accepted', 'Rejected'].includes(item.status)).length,
    },
    funnel,
    bookingByMonth,
    ownerPerformance,
    topAccounts,
    segmentDistribution: mix((account) => account.segment),
    regionDistribution: mix((account) => account.region),
    tierDistribution: countBy(input.accounts, (item) => item.tier),
    riskDistribution: countBy(input.accounts, (item) => item.risk),
    process: {
      requirementsByStatus: amountBy(input.requirements, (item) => item.status, (item) => item.budgetAmount),
      budgetByStatus: amountBy(input.requirements, (item) => item.budgetStatus, (item) => item.budgetAmount),
      actionsBySource: countBy(input.actions.filter((item) => item.status === 'Open'), (item) => item.sourceType),
      actionsByTimeliness: countBy(input.actions.filter((item) => item.status === 'Open'), (item) => item.due < today ? '已逾期' : '未逾期'),
      demoByStatus: countBy(input.demoRequests, (item) => item.status),
      demoByPriority: countBy(input.demoRequests, (item) => item.priority),
      evaluationByStatus: countBy(input.evaluations, (item) => item.status),
      evaluationRunResults: countBy(input.evaluations.flatMap((item) => item.runs), (item) => item.status),
      visitsByStatus: countBy(input.visits ?? [], (item) => item.status),
      visitsByOwner: countBy(input.visits ?? [], (item) => item.owner),
    },
    attentionAccounts: input.accounts.filter((item) => item.risk !== '稳健').map((account) => ({
      ...account,
      pipelineAmount: 0,
    })).sort((a, b) => a.name.localeCompare(b.name)).slice(0, 4),
    weeklyActions: input.actions.filter((item) => item.status === 'Open').sort((a, b) => a.due.localeCompare(b.due)).slice(0, 5),
    deliveryAlerts: [
      ...input.demoRequests.filter((item) => item.status === 'Manager Approval').map((item) => ({ id: item.id, type: 'Demo Request' as const, title: item.title, detail: `${item.accountName} · 等待经理审批`, tone: 'warning' as const })),
    ].slice(0, 4),
    completeness: [
      { label: '客户基础档案', value: input.accounts.filter((item) => item.completeness >= 80).length, total: input.accounts.length },
      { label: '关键人关系', value: input.accounts.filter((item) => item.stakeholderCount > 0).length, total: input.accounts.length },
      { label: '采购需求字段', value: input.requirements.filter((item) => item.completeness >= 80).length, total: input.requirements.length },
      { label: 'Next Action', value: input.requirements.filter((item) => item.nextAction).length, total: input.requirements.length },
    ],
  }
}
