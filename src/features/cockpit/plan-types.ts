import type { Metric, PeriodKind, ReviewDto, ReviewQuery, TargetMetric } from './types'

// Plan contract, implemented by cockpit.get_plan / get_plan_details; decisions are recorded in docs/plan/backend-handoff.md.
export type PlanKind = 'visits' | 'tests' | 'quotes' | 'followups' | 'actions' | 'po' | 'events'
export type PlanMetric = PlanKind | 'all' | 'overdue' | 'tests_other' | 'quotation_carryover' | 'scheduled_activities'
export interface PlanQuery extends ReviewQuery { period: PeriodKind; anchor: string }
export interface PlanDetailQuery extends PlanQuery { metric: PlanMetric; page: number; pageSize: number; includeOverdue?: boolean; equipmentGroup?: string }
export type CommitmentMetric = 'visits' | 'leads' | 'tests' | 'quotes' | 'followups' | 'actions' | 'events'
export interface PlanCommitmentInput { sales: string; metric: CommitmentMetric; period: PeriodKind; anchor: string; value: string; note: string }
export interface PlanCommitment extends PlanCommitmentInput { id: string; modified: string; modifiedBy: string }
export interface CommitmentComparison { key: CommitmentMetric; scheduled: Metric; commitment: Omit<TargetMetric, 'record'> & { record: PlanCommitment | null; conflicts?: PlanCommitment[] }; target: TargetMetric }
export interface PlanCommitments { allocated: boolean; people: { id: string; name: string; canEdit: boolean; activities: CommitmentComparison[] }[]; team: CommitmentComparison[]; history: Record<string, { id: string; at: string; actor: string; changes: [string, unknown, unknown][] }[]> }
// Always CNY: the amount_cny Sales entered on the Opportunity, as in Review. Never converted, never the original currency.
export interface PlanMoney { currency: string; value: string }
export interface PlanItem {
  id: string
  kind: PlanKind
  equipmentGroup?: string
  title: string
  accountId: string
  customer: string
  // Test Demo deadlines can be unset; they still belong to Plan.
  date: string | null
  startDate?: string
  endDate?: string
  salesOwner: string | null
  actionOwner?: string | null
  actionOwnerName?: string | null
  market: string | null
  status: string
  carryover: boolean
  opportunityId?: string
  quotationId?: string
  quotationVersionId?: string
  evaluationId?: string
  amount?: string | null
  currency?: string | null
  probabilityLevel?: 'low_probability' | 'pipeline' | 'upside' | 'committed' | null
}
export interface PlanDetails {
  items: PlanItem[]; total: number; page: number; pageSize: number; asOf: string
}
export interface PlanDto {
  commitments?: PlanCommitments
  equipmentGroups?: { id: string; name: string | null; activities: Metric; po: Metric; poAmounts: PlanMoney[]; poAmountIncomplete: boolean }[]
  period: { kind: PeriodKind; start: string; end: string; previousAnchor: string; nextAnchor: string }
  asOf: string
  filters: ReviewDto['filters']
  // Only under an equipment filter: planned visits and active Demo tests with no opportunity, left out.
  equipmentUnclassified?: { visits: number; tests: number } | null
  summary: Record<'visits' | 'tests' | 'actions' | 'po', Metric> & Partial<Record<'quotes' | 'followups' | 'events', Metric>>
  otherDemos?: Metric
  quotationCarryover?: Metric
  quoteAmounts?: PlanMoney[]
  quoteAmountIncomplete?: boolean
  overdue: Metric
  poAmounts: PlanMoney[]
  poAmountIncomplete: boolean
  sales: { id: string | null; name: string; visits: Metric; tests: Metric; actions: Metric; po: Metric; quotes?: Metric; followups?: Metric; events?: Metric; poAmounts: PlanMoney[]; poAmountIncomplete: boolean }[]
  markets: { name: string | null; activities: Metric; po: Metric; poAmounts: PlanMoney[]; poAmountIncomplete: boolean }[]
  expectedPO: { items: PlanItem[]; total: number }
}
