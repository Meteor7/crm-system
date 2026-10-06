import type { DemoResourceWarnings } from '@/features/demo-resources/types'
export type PeriodKind = 'week' | 'month' | 'quarter' | 'year'
export type ActivityKey = 'visits' | 'leads' | 'tests' | 'quotes'
export interface ReviewQuery { period?: PeriodKind; anchor?: string; sales?: string; market?: string; region?: string; equipment?: string }
export interface Metric { value: number | string | null; state: 'ready' | 'insufficient' | 'not_applicable' | 'not_set'; reason?: string | null }
export interface TargetInput { sales: string; metric: ActivityKey | 'orders'; period: PeriodKind | 'weekly_default'; anchor: string; value: string }
export interface Target extends TargetInput { id: string; modified: string }
export interface TargetMetric extends Metric { record: Target | null }
export interface ReviewRow {
  id: string; title: string; accountId: string; customer: string; owner: string | null; at: string | null
  kind: 'visit' | 'lead' | 'test' | 'quotation' | 'opportunity' | 'booking'; stage?: string
  status?: string; opportunityId?: string; reason?: string | null; fromLevel?: string; toLevel?: string; eventId?: string
  actionId?: string; actionTitle?: string; due?: string; days?: number; daysAtLeast?: boolean; severity?: string
  previousPoDate?: string; postponedPoDate?: string; currentPoDate?: string; actionStatus?: string
  currentOwner?: string | null
  // Lost rows: the post-mortem state (null until the loss review row exists), whether one is still owed,
  // whether it is older than the four-week window, and when the deal reopened (no post-mortem owed).
  review?: { id: string; status: 'pending' | 'reviewed'; note: string; reviewedBy: string | null; reviewedAt: string | null; modified: string | null } | null
  reviewPending?: boolean; reviewOverdue?: boolean; reopenedAt?: string | null
  // Overdue rows on the Warnings page: the opportunity is also stalled (null when stall history is insufficient),
  // and who owns the action (the row owner stays the opportunity owner used by the filters).
  stalled?: boolean | null; actionOwner?: string | null
  quotationVersionId?: string; quotationVersionNo?: number; validUntil?: string; daysToExpiry?: number
  // Stage 6 without PO: days in internal validation (a minimum when daysAtLeast) and when it began (null when only bounded).
  daysInStage?: number; enteredAt?: string | null
  recovery?: { plan: string; state: 'pending' | 'handled'; actionTaken?: string | null; actedBy?: string | null; actedAt?: string | null
    // Warnings page only: what an in-meeting plan edit needs (plan version and last editor).
    id?: string; modified?: string; editedBy?: string | null; editedAt?: string | null } | null
  // Warnings page only: the Opportunity version a plan edit is checked against.
  opportunityModified?: string | null
  // Review opportunity amounts are CNY estimates, replayed at the row reference time.
  amount?: string | null; currency?: string | null; lastActionAt?: string | null; evaluationId?: string
  // Warnings page overdue, quotation-expiry and stage 6 rows: the Manager's next step and (stage 6 only) the action taken.
  // Missing means a backend without warning handling: the editors stay hidden.
  handling?: WarningHandling | null
}
export type WarningHandlingType = 'overdue' | 'quotation_expiry' | 'stage6_no_po' | 'close_date_slip'
export interface WarningHandlingRevision { kind: 'PlanUpdated' | 'ActionRecorded'; nextStep: string | null; actionTaken: string | null; followUpOn: string | null; actor: string; at: string }
export interface WarningHandling {
  warningType: WarningHandlingType
  // overdue: action id; quotation_expiry: quotation id; stage6_no_po: opportunity id
  sourceId: string
  // overdue: due date; quotation_expiry: version id; stage6_no_po: stage 6 entry event id or 'before_history'
  sourceEvent: string
  // null until a next step or action is first saved; modified goes back as expectedModified.
  id: string | null; modified: string | null
  // 'handled' only on stage 6 rows whose action's follow-up date (YYYY-MM-DD) is still ahead.
  state: 'open' | 'handled'
  nextStep: string | null; planBy: string | null; planAt: string | null
  actionTaken: string | null; actedBy: string | null; actedAt: string | null; followUpOn: string | null
  history: WarningHandlingRevision[]
}
export interface WarningPlanInput { warningType: WarningHandlingType; sourceId: string; sourceEvent: string; nextStep: string }
export interface WarningActionInput { warningType: 'stage6_no_po' | 'close_date_slip'; sourceId: string; sourceEvent: string; actionTaken: string; followUpOn: string }
export type CockpitSettingSource = 'settings' | 'site_config' | 'default'
export interface CockpitSettingsInput { quoteExpiryDays: number; stage6NoPoDays: number }
export interface CockpitSettings extends CockpitSettingsInput {
  sources: Record<keyof CockpitSettingsInput, CockpitSettingSource>
  // modifiedByName: the saver's display name (null for an unknown user; show the id then).
  modified: string | null; modifiedBy: string | null; modifiedByName: string | null
}
export interface ReviewDetails { items: ReviewRow[]; total: number; page: number; pageSize: number; asOf: string }
export interface StageConversions {
  start: string; end: string; verifiedFrom: string | null; complete: boolean; thresholdPercent: number
  items: { fromStage: string; toStage: string; fromCount: number; toCount: number; rate: Metric; bottleneck: boolean | null }[]
}
export interface PipelineCoverage {
  openPipeline: Metric; remainingTarget: Metric; ratio: Metric; referenceMin: number; referenceMax: number
}
export interface ReviewDto {
  demoResources?: DemoResourceWarnings
  period: { kind: PeriodKind; start: string; end: string; asOf: string; previousStart: string; previousEnd: string; complete: boolean; previousAnchor: string; nextAnchor: string; hasNext: boolean }
  // equipment: the Opportunities board catalog; a record matches through the opportunity it is linked to.
  filters: { sales: { id: string; name: string }[]; markets: string[]; regions: string[]; regionParents?: Record<string, string>; regionReady: boolean; equipment?: string[] }
  // unclassified: under an equipment filter, records in the period with no opportunity (left out, not guessed).
  activities: { key: ActivityKey; actual: Metric; previous: Metric; delta: number | null; target: TargetMetric; unclassified?: number | null }[]
  pipeline: { key: string; count: Metric; amount: Metric }[]
  conversions?: StageConversions
  pipelineCoverage?: PipelineCoverage
  warnings: { key: string; count: Metric }[]
  quotationExpiry?: { referenceDate: string; thresholdDays: number }
  stage6NoPo?: { thresholdDays: number }
  sales: { id: string; name: string; activities: Record<ActivityKey, Metric>; pipeline: Metric; poCount: Metric; orders: Metric }[]
  // series: the year's PO bookings as cumulative CNY by actual PO date; fraction is that day's share of the year, like elapsedFraction.
  orders: { actual: Metric; series?: { date: string; amount: string; cumulative: string; fraction: number }[]; count: Metric; missingDate?: Metric; missingAmount?: Metric; target: TargetMetric; planned: Metric; elapsedFraction: number }
  stalled: { count: Metric; items: ReviewRow[] }
  losses: { count: Metric; items: ReviewRow[]; reviewed?: Metric; pending?: Metric }
  targets: Target[]
}
export interface WarningsDto {
  demoResources?: DemoResourceWarnings
  period: ReviewDto['period']
  filters: ReviewDto['filters']
  warnings: ReviewDto['warnings']
  quotationExpiry: { referenceDate: string; thresholdDays: number }
  lost: ReviewRow[]
  // Unreviewed losses older than four weeks, however old: reviewable, never counted.
  lostBacklog: ReviewRow[]
  overdue: ReviewRow[]
  downgrade: ReviewRow[]
  quotationExpiryItems: ReviewRow[]
  // Deals in internal validation (S6) longer than thresholdDays without a PO, longest first.
  stage6NoPo?: { thresholdDays: number }
  stage6NoPoItems?: ReviewRow[]
  // Stage 6 rows with an action recorded and a follow-up date still ahead: listed apart, never counted.
  stage6NoPoHandledItems?: ReviewRow[]
  closeDateSlipItems?: ReviewRow[]
  closeDateSlipHandledItems?: ReviewRow[]
  // Display names for users on the page (reviewers and editors are often Managers, not in filters.sales).
  names?: Record<string, string>
}
