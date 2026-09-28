import type { Locale } from '@/i18n'
import type { Tone } from '@/types/crm'
import type {
  OpportunityInternalValidationDto,
  OpportunityLiveBookingDto,
  OpportunityStageHistoryDto,
} from '@/types/workspaces'

/** The seven milestones an Opportunity reaches, in order. Internal validation (S6) is optional. */
export const OPPORTUNITY_MILESTONE_STAGES = [
  'qualified_opportunity',
  'demo_done',
  'customer_budget_approved',
  'rfq_validated',
  'quotation_sent',
  'internal_validation',
  'po_received',
] as const
export type OpportunityMilestoneStage = typeof OPPORTUNITY_MILESTONE_STAGES[number]

/** Every stored stage value. `lost` closes an Opportunity and is not a funnel step. */
export const OPPORTUNITY_STAGES = [
  'qualified_opportunity',
  'demo_done',
  'customer_budget_approved',
  'rfq_validated',
  'quotation_sent',
  'internal_validation',
  'po_received',
  'lost',
] as const
export type OpportunityStage = typeof OPPORTUNITY_STAGES[number]

/** S1-S6 are still being worked; they are also the only stages an Opportunity can be lost at. */
export const OPEN_OPPORTUNITY_STAGES = [
  'qualified_opportunity',
  'demo_done',
  'customer_budget_approved',
  'rfq_validated',
  'quotation_sent',
  'internal_validation',
] as const
export type OpenOpportunityStage = typeof OPEN_OPPORTUNITY_STAGES[number]

export const OPTIONAL_OPPORTUNITY_STAGE = 'internal_validation' satisfies OpportunityMilestoneStage
export const DEMO_REQUEST_STAGES = ['qualified_opportunity', 'demo_done'] as const satisfies readonly OpportunityMilestoneStage[]
export const RFQ_CREATION_STAGE = 'customer_budget_approved' satisfies OpportunityMilestoneStage
/** Quotations are approved and published from RFQ validated through internal validation. */
export const QUOTATION_STAGES = ['rfq_validated', 'quotation_sent', 'internal_validation'] as const satisfies readonly OpportunityMilestoneStage[]
export const PO_CONFIRMABLE_STAGES = ['quotation_sent', 'internal_validation'] as const satisfies readonly OpportunityMilestoneStage[]

export const OPPORTUNITY_STAGE_HISTORY_SOURCES = ['creation', 'event', 'manual', 'approval', 'rollback', 'lost', 'migration'] as const
export type OpportunityStageHistorySource = typeof OPPORTUNITY_STAGE_HISTORY_SOURCES[number]
export const OPPORTUNITY_STAGE_HISTORY_EVENTS = [
  'created',
  'lead_converted',
  'demo_customer_review',
  'budget_confirmed',
  'rfq_approved',
  'quotation_published',
  'internal_validation_approved',
  'po_confirmed',
  'marked_lost',
  'rollback',
  'reopened',
  'migration',
] as const
export type OpportunityStageHistoryEvent = typeof OPPORTUNITY_STAGE_HISTORY_EVENTS[number]
export const OPPORTUNITY_REACHED_AT_BASES = ['recorded', 'declared', 'evidence', 'upper_bound', 'unknown'] as const
export type OpportunityReachedAtBasis = typeof OPPORTUNITY_REACHED_AT_BASES[number]
export const INTERNAL_VALIDATION_STATUSES = ['pending', 'approved', 'rejected', 'cancelled'] as const
export type InternalValidationStatus = typeof INTERNAL_VALIDATION_STATUSES[number]

const includesValue = (values: readonly string[], value: unknown) => typeof value === 'string' && values.includes(value)

export function isOpportunityStage(value: unknown): value is OpportunityStage {
  return includesValue(OPPORTUNITY_STAGES, value)
}

export function isOpportunityMilestoneStage(value: unknown): value is OpportunityMilestoneStage {
  return includesValue(OPPORTUNITY_MILESTONE_STAGES, value)
}

export function isOpenOpportunityStage(value: unknown): value is OpenOpportunityStage {
  return includesValue(OPEN_OPPORTUNITY_STAGES, value)
}

/** PO received and lost are closed: the probability level is frozen and the Opportunity leaves the open pipeline. */
export function isClosedOpportunityStage(value: unknown) {
  return value === 'po_received' || value === 'lost'
}

/** Position in the funnel from 0 (S1) to 6 (S7). Lost and unknown values have no position and return -1. */
export function opportunityStageIndex(stage: unknown) {
  return isOpportunityMilestoneStage(stage) ? OPPORTUNITY_MILESTONE_STAGES.indexOf(stage) : -1
}

export function canCreateDemoRequestAt(stage: unknown) {
  return includesValue(DEMO_REQUEST_STAGES, stage)
}

export function canCreateRfqAt(stage: unknown) {
  return stage === RFQ_CREATION_STAGE
}

export function canWorkQuotationAt(stage: unknown) {
  return includesValue(QUOTATION_STAGES, stage)
}

export function canConfirmPoAt(stage: unknown) {
  return includesValue(PO_CONFIRMABLE_STAGES, stage)
}

/**
 * Stages a Manager may roll back to, from the stage rules alone. A lost Opportunity reopens at or below the
 * stage it was lost at; without that record it stops at quotation sent, below the approval nobody can vouch for.
 */
export function opportunityRollbackTargets(stage: unknown, lostAtStage: unknown = ''): OpportunityMilestoneStage[] {
  if (stage === 'lost') {
    const ceiling = isOpenOpportunityStage(lostAtStage) ? lostAtStage : 'quotation_sent'
    return OPPORTUNITY_MILESTONE_STAGES.slice(0, opportunityStageIndex(ceiling) + 1)
  }
  const index = opportunityStageIndex(stage)
  return index > 0 ? OPPORTUNITY_MILESTONE_STAGES.slice(0, index) : []
}

export type OpportunityRollbackBlocker = 'completed_booking' | 'live_booking'

export interface OpportunityRollbackOptions {
  targets: OpportunityMilestoneStage[]
  /** Why stage-valid targets were withheld, when a Booking is the reason. */
  blocker: OpportunityRollbackBlocker | null
}

type RollbackSubject = {
  stage: string
  lostAtStage?: string
  liveBooking?: Pick<OpportunityLiveBookingDto, 'id' | 'status'> | null
  internalValidation?: Pick<OpportunityInternalValidationDto, 'status' | 'bookingId'> | null
}

/**
 * Rollback targets after the Booking rules the Opportunity DTO can show: a completed Booking blocks every
 * rollback, a live Booking blocks targets at or below quotation sent, and internal validation needs the Booking
 * an approved request created. The server re-checks the Booking history the DTO does not carry.
 */
export function opportunityRollbackOptions(opportunity: RollbackSubject): OpportunityRollbackOptions {
  const stageTargets = opportunityRollbackTargets(opportunity.stage, opportunity.lostAtStage)
  const booking = opportunity.liveBooking ?? null
  if (booking?.status === 'Completed') return { targets: [], blocker: stageTargets.length ? 'completed_booking' : null }
  const validation = opportunity.internalValidation
  const approvedBookingId = validation?.status === 'approved' ? validation.bookingId : ''
  const internalValidationAllowed = Boolean(approvedBookingId) && (!booking || booking.id === approvedBookingId)
  const targets = stageTargets.filter((target) => target === 'internal_validation' ? internalValidationAllowed : !booking)
  const blocked = stageTargets.some((target) => target !== 'internal_validation' && !targets.includes(target))
  return { targets, blocker: booking && blocked ? 'live_booking' : null }
}

type MilestoneSubject = {
  stage: string
  lostAtStage?: string
  stageHistory?: Array<Pick<OpportunityStageHistoryDto, 'event' | 'from'>>
}

/** A PO confirmed straight from quotation sent skipped the optional internal validation. */
export function isInternalValidationSkipped(opportunity: MilestoneSubject) {
  if (opportunity.stage !== 'po_received') return false
  const latestPoConfirmation = (opportunity.stageHistory ?? []).find((row) => row.event === 'po_confirmed')
  return latestPoConfirmation?.from === 'quotation_sent'
}

export type OpportunityMilestoneState = 'complete' | 'current' | 'upcoming' | 'skipped' | 'lost'

export interface OpportunityMilestoneSegment {
  stage: OpportunityMilestoneStage
  state: OpportunityMilestoneState
  optional: boolean
}

/** Display state of each of the seven milestones; a lost Opportunity marks the stage where it was lost. */
export function opportunityMilestoneSegments(opportunity: MilestoneSubject): OpportunityMilestoneSegment[] {
  const lost = opportunity.stage === 'lost'
  const lostIndex = lost ? opportunityStageIndex(opportunity.lostAtStage) : -1
  const currentIndex = opportunityStageIndex(opportunity.stage)
  const skipped = isInternalValidationSkipped(opportunity)
  return OPPORTUNITY_MILESTONE_STAGES.map((stage, index) => {
    let state: OpportunityMilestoneState
    if (lost) state = lostIndex < 0 || index > lostIndex ? 'upcoming' : index === lostIndex ? 'lost' : 'complete'
    else state = index < currentIndex ? 'complete' : index === currentIndex ? 'current' : 'upcoming'
    if (stage === OPTIONAL_OPPORTUNITY_STAGE && skipped) state = 'skipped'
    return { stage, state, optional: stage === OPTIONAL_OPPORTUNITY_STAGE }
  })
}

type LocalizedLabels<T extends string> = Record<T, Record<Locale, string>>

const STAGE_LABELS: LocalizedLabels<OpportunityStage> = {
  qualified_opportunity: { 'zh-CN': '合格商机', 'en-US': 'Qualified opportunity' },
  demo_done: { 'zh-CN': 'Demo 完成', 'en-US': 'Demo done' },
  customer_budget_approved: { 'zh-CN': '客户预算批准', 'en-US': 'Customer budget approved' },
  rfq_validated: { 'zh-CN': 'RFQ 通过', 'en-US': 'RFQ validated' },
  quotation_sent: { 'zh-CN': '报价已发', 'en-US': 'Quotation sent' },
  internal_validation: { 'zh-CN': '内部生产审批', 'en-US': 'Internal validation' },
  po_received: { 'zh-CN': '收到 PO', 'en-US': 'PO received' },
  lost: { 'zh-CN': '丢单', 'en-US': 'Lost' },
}

const STAGE_TONES: Record<OpportunityStage, Tone> = {
  qualified_opportunity: 'info',
  demo_done: 'info',
  customer_budget_approved: 'info',
  rfq_validated: 'warning',
  quotation_sent: 'warning',
  internal_validation: 'warning',
  po_received: 'positive',
  lost: 'danger',
}

const EVENT_LABELS: LocalizedLabels<OpportunityStageHistoryEvent> = {
  created: { 'zh-CN': '新建商机', 'en-US': 'Opportunity created' },
  lead_converted: { 'zh-CN': '线索转换', 'en-US': 'Lead converted' },
  demo_customer_review: { 'zh-CN': 'Demo 进入客户评审', 'en-US': 'Demo entered customer review' },
  budget_confirmed: { 'zh-CN': '确认客户预算', 'en-US': 'Customer budget confirmed' },
  rfq_approved: { 'zh-CN': 'RFQ 经理批准', 'en-US': 'RFQ approved' },
  quotation_published: { 'zh-CN': '报价发布', 'en-US': 'Quotation published' },
  internal_validation_approved: { 'zh-CN': '内部生产审批通过', 'en-US': 'Internal validation approved' },
  po_confirmed: { 'zh-CN': '确认收到 PO', 'en-US': 'PO confirmed' },
  marked_lost: { 'zh-CN': '标记丢单', 'en-US': 'Marked lost' },
  rollback: { 'zh-CN': '阶段回退', 'en-US': 'Stage rolled back' },
  reopened: { 'zh-CN': '重新打开', 'en-US': 'Reopened' },
  migration: { 'zh-CN': '数据迁移', 'en-US': 'Data migration' },
}

const EVENT_TONES: Partial<Record<OpportunityStageHistoryEvent, Tone>> = {
  po_confirmed: 'positive',
  internal_validation_approved: 'positive',
  marked_lost: 'danger',
  rollback: 'warning',
  reopened: 'warning',
  migration: 'neutral',
}

const SOURCE_LABELS: LocalizedLabels<OpportunityStageHistorySource> = {
  creation: { 'zh-CN': '新建', 'en-US': 'Creation' },
  event: { 'zh-CN': '流程事件', 'en-US': 'Workflow event' },
  manual: { 'zh-CN': '人工确认', 'en-US': 'Manual confirmation' },
  approval: { 'zh-CN': '审批', 'en-US': 'Approval' },
  rollback: { 'zh-CN': '回退', 'en-US': 'Rollback' },
  lost: { 'zh-CN': '丢单', 'en-US': 'Lost' },
  migration: { 'zh-CN': '迁移', 'en-US': 'Migration' },
}

const BASIS_LABELS: LocalizedLabels<OpportunityReachedAtBasis> = {
  recorded: { 'zh-CN': '操作记录时间', 'en-US': 'Recorded time' },
  declared: { 'zh-CN': '销售填写日期', 'en-US': 'Date declared by Sales' },
  evidence: { 'zh-CN': '迁移凭证时间', 'en-US': 'Evidence time' },
  upper_bound: { 'zh-CN': '不晚于此时间', 'en-US': 'No later than' },
  unknown: { 'zh-CN': '时间未知', 'en-US': 'Time unknown' },
}

const VALIDATION_STATUS_LABELS: LocalizedLabels<InternalValidationStatus> = {
  pending: { 'zh-CN': '待审批', 'en-US': 'Pending' },
  approved: { 'zh-CN': '已批准', 'en-US': 'Approved' },
  rejected: { 'zh-CN': '已驳回', 'en-US': 'Rejected' },
  cancelled: { 'zh-CN': '已撤销', 'en-US': 'Cancelled' },
}

const VALIDATION_STATUS_TONES: Record<InternalValidationStatus, Tone> = {
  pending: 'warning',
  approved: 'positive',
  rejected: 'danger',
  cancelled: 'neutral',
}

const labelFor = <T extends string>(labels: LocalizedLabels<T>, value: string, locale: Locale) =>
  Object.hasOwn(labels, value) ? labels[value as T][locale] : value

/** Unknown values, such as a stage from an older server, are shown as they are. */
export function opportunityStageLabel(stage: string, locale: Locale) {
  return labelFor(STAGE_LABELS, stage, locale)
}

export function opportunityStageTone(stage: string): Tone {
  return isOpportunityStage(stage) ? STAGE_TONES[stage] : 'neutral'
}

export function opportunityStageHistoryEventLabel(event: string, locale: Locale) {
  return labelFor(EVENT_LABELS, event, locale)
}

export function opportunityStageHistoryEventTone(event: string): Tone {
  return EVENT_TONES[event as OpportunityStageHistoryEvent] ?? 'info'
}

export function opportunityStageHistorySourceLabel(source: string, locale: Locale) {
  return labelFor(SOURCE_LABELS, source, locale)
}

export function opportunityReachedAtBasisLabel(basis: string, locale: Locale) {
  return labelFor(BASIS_LABELS, basis, locale)
}

/** A stage history row shows its business arrival separately when it is not simply the time it was recorded. */
export function showsSeparateReachedAt(row: Pick<OpportunityStageHistoryDto, 'reachedAt' | 'recordedAt'>) {
  return row.reachedAt !== row.recordedAt
}

export function internalValidationStatusLabel(status: string, locale: Locale) {
  return labelFor(VALIDATION_STATUS_LABELS, status, locale)
}

export function internalValidationStatusTone(status: string): Tone {
  return VALIDATION_STATUS_TONES[status as InternalValidationStatus] ?? 'neutral'
}

const CANCEL_REASON_LABELS: Record<string, Record<Locale, string>> = {
  'PO received before the internal validation was decided.': {
    'zh-CN': '审批完成前已确认收到 PO，申请自动撤销。',
    'en-US': 'The PO was received before the internal validation was decided.',
  },
  'Opportunity marked lost.': { 'zh-CN': '商机已标记丢单，申请自动撤销。', 'en-US': 'The Opportunity was marked lost.' },
}

/** Server-written cancellation reasons are recognized and localized; anything else is shown as written. */
export function internalValidationCancelReasonLabel(reason: string, locale: Locale) {
  const fixed = CANCEL_REASON_LABELS[reason]
  if (fixed) return fixed[locale]
  const rolledBack = /^Opportunity rolled back to ([a-z_]+)\.$/.exec(reason)
  if (rolledBack && isOpportunityStage(rolledBack[1])) {
    const stage = opportunityStageLabel(rolledBack[1], locale)
    return locale === 'zh-CN' ? `商机已回退到${stage}，申请自动撤销。` : `The Opportunity was rolled back to ${stage}.`
  }
  return reason
}
