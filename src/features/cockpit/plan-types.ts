import type { Metric, PeriodKind, ReviewDto, ReviewQuery } from './types'

// Plan contract, implemented by cockpit.get_plan / get_plan_details; decisions are recorded in docs/plan/backend-handoff.md.
export type PlanKind = 'visits' | 'tests' | 'actions' | 'po'
export type PlanMetric = PlanKind | 'all' | 'overdue'
export interface PlanQuery extends ReviewQuery { period: PeriodKind; anchor: string }
export interface PlanDetailQuery extends PlanQuery { metric: PlanMetric; page: number; pageSize: number; includeOverdue?: boolean }
// Always CNY: the amount_cny Sales entered on the Opportunity, as in Review. Never converted, never the original currency.
export interface PlanMoney { currency: string; value: string }
export interface PlanItem {
  id: string
  kind: PlanKind
  title: string
  accountId: string
  customer: string
  // Test Demo deadlines can be unset; they still belong to Plan.
  date: string | null
  salesOwner: string | null
  actionOwner?: string | null
  actionOwnerName?: string | null
  market: string | null
  status: string
  carryover: boolean
  opportunityId?: string
  evaluationId?: string
  amount?: string | null
  currency?: string | null
  probabilityLevel?: 'low_probability' | 'pipeline' | 'upside' | 'committed' | null
}
export interface PlanDetails {
  items: PlanItem[]; total: number; page: number; pageSize: number; asOf: string
}
export interface PlanDto {
  period: { kind: PeriodKind; start: string; end: string; previousAnchor: string; nextAnchor: string }
  asOf: string
  filters: ReviewDto['filters']
  // Only under an equipment filter: planned visits and active Demo tests with no opportunity, left out.
  equipmentUnclassified?: { visits: number; tests: number } | null
  summary: Record<PlanKind, Metric>
  overdue: Metric
  poAmounts: PlanMoney[]
  poAmountIncomplete: boolean
  sales: { id: string | null; name: string; visits: Metric; tests: Metric; actions: Metric; po: Metric; poAmounts: PlanMoney[]; poAmountIncomplete: boolean }[]
  markets: { name: string | null; activities: Metric; po: Metric; poAmounts: PlanMoney[]; poAmountIncomplete: boolean }[]
  expectedPO: { items: PlanItem[]; total: number }
}
