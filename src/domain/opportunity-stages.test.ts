import { describe, expect, it } from 'vitest'
import {
  OPEN_OPPORTUNITY_STAGES,
  OPPORTUNITY_MILESTONE_STAGES,
  OPPORTUNITY_STAGES,
  canConfirmPoAt,
  canCreateDemoRequestAt,
  canCreateRfqAt,
  canWorkQuotationAt,
  internalValidationCancelReasonLabel,
  isClosedOpportunityStage,
  isInternalValidationSkipped,
  isOpenOpportunityStage,
  isOpportunityMilestoneStage,
  isOpportunityStage,
  opportunityMilestoneSegments,
  opportunityRollbackOptions,
  opportunityRollbackTargets,
  opportunityStageIndex,
  opportunityStageLabel,
  opportunityStageTone,
  showsSeparateReachedAt,
} from './opportunity-stages'

const milestones = [
  'qualified_opportunity',
  'demo_done',
  'customer_budget_approved',
  'rfq_validated',
  'quotation_sent',
  'internal_validation',
  'po_received',
] as const

describe('opportunity stage vocabulary', () => {
  it('orders the seven milestones and keeps lost out of the funnel', () => {
    expect(OPPORTUNITY_MILESTONE_STAGES).toEqual(milestones)
    expect(OPPORTUNITY_STAGES).toEqual([...milestones, 'lost'])
    expect(OPEN_OPPORTUNITY_STAGES).toEqual(milestones.slice(0, 6))
    expect(milestones.map(opportunityStageIndex)).toEqual([0, 1, 2, 3, 4, 5, 6])
    expect(opportunityStageIndex('lost')).toBe(-1)
    expect(opportunityStageIndex('需求发现')).toBe(-1)
  })

  it('recognizes stored, open and closed stages and rejects retired names', () => {
    expect(isOpportunityStage('lost')).toBe(true)
    expect(isOpportunityMilestoneStage('lost')).toBe(false)
    expect(isOpportunityStage('Won')).toBe(false)
    expect(isOpportunityStage('设备规格确认')).toBe(false)
    expect(isOpenOpportunityStage('internal_validation')).toBe(true)
    expect(isOpenOpportunityStage('po_received')).toBe(false)
    expect(isClosedOpportunityStage('po_received')).toBe(true)
    expect(isClosedOpportunityStage('lost')).toBe(true)
    expect(isClosedOpportunityStage('quotation_sent')).toBe(false)
  })

  it('places each workflow entry at its milestones', () => {
    expect(OPPORTUNITY_STAGES.filter(canCreateDemoRequestAt)).toEqual(['qualified_opportunity', 'demo_done'])
    expect(OPPORTUNITY_STAGES.filter(canCreateRfqAt)).toEqual(['customer_budget_approved'])
    expect(OPPORTUNITY_STAGES.filter(canWorkQuotationAt)).toEqual(['rfq_validated', 'quotation_sent', 'internal_validation'])
    expect(OPPORTUNITY_STAGES.filter(canConfirmPoAt)).toEqual(['quotation_sent', 'internal_validation'])
  })

  it('labels every stage in both locales and shows unknown values as they are', () => {
    expect(OPPORTUNITY_STAGES.map((stage) => opportunityStageLabel(stage, 'zh-CN'))).toEqual([
      '合格商机', 'Demo 完成', '客户预算批准', 'RFQ 通过', '报价已发', '内部生产审批', '收到 PO', '丢单',
    ])
    expect(OPPORTUNITY_STAGES.map((stage) => opportunityStageLabel(stage, 'en-US'))).toEqual([
      'Qualified opportunity', 'Demo done', 'Customer budget approved', 'RFQ validated', 'Quotation sent', 'Internal validation', 'PO received', 'Lost',
    ])
    expect(opportunityStageLabel('采购流程', 'en-US')).toBe('采购流程')
    expect(opportunityStageLabel('toString', 'en-US')).toBe('toString')
    expect(opportunityStageTone('po_received')).toBe('positive')
    expect(opportunityStageTone('lost')).toBe('danger')
    expect(opportunityStageTone('Won')).toBe('neutral')
  })
})

describe('opportunity rollback targets', () => {
  it('offers only earlier milestones', () => {
    expect(opportunityRollbackTargets('qualified_opportunity')).toEqual([])
    expect(opportunityRollbackTargets('quotation_sent')).toEqual(milestones.slice(0, 4))
    expect(opportunityRollbackTargets('po_received')).toEqual(milestones.slice(0, 6))
    expect(opportunityRollbackTargets('Won')).toEqual([])
  })

  it('reopens a lost Opportunity at or below the stage it was lost at, or below internal validation without that record', () => {
    expect(opportunityRollbackTargets('lost', 'rfq_validated')).toEqual(milestones.slice(0, 4))
    expect(opportunityRollbackTargets('lost', 'internal_validation')).toEqual(milestones.slice(0, 6))
    expect(opportunityRollbackTargets('lost', '')).toEqual(milestones.slice(0, 5))
    expect(opportunityRollbackTargets('lost', 'po_received')).toEqual(milestones.slice(0, 5))
  })

  it('withholds every target behind a completed Booking', () => {
    expect(opportunityRollbackOptions({
      stage: 'po_received',
      liveBooking: { id: 'BKG-001', status: 'Completed' },
      internalValidation: null,
    })).toEqual({ targets: [], blocker: 'completed_booking' })
  })

  it('keeps internal validation for the Booking an approved request created and blocks the rest while it is live', () => {
    const approved = { status: 'approved' as const, bookingId: 'BKG-003' }
    expect(opportunityRollbackOptions({
      stage: 'po_received',
      liveBooking: { id: 'BKG-003', status: 'Confirmed' },
      internalValidation: approved,
    })).toEqual({ targets: ['internal_validation'], blocker: 'live_booking' })
    expect(opportunityRollbackOptions({
      stage: 'po_received',
      liveBooking: { id: 'BKG-009', status: 'Confirmed' },
      internalValidation: approved,
    })).toEqual({ targets: [], blocker: 'live_booking' })
    expect(opportunityRollbackOptions({
      stage: 'internal_validation',
      liveBooking: { id: 'BKG-003', status: 'Pending' },
      internalValidation: approved,
    })).toEqual({ targets: [], blocker: 'live_booking' })
  })

  it('offers every earlier milestone once the Booking is cancelled, and internal validation only after an approval', () => {
    expect(opportunityRollbackOptions({
      stage: 'po_received',
      liveBooking: null,
      internalValidation: { status: 'approved', bookingId: 'BKG-003' },
    })).toEqual({ targets: milestones.slice(0, 6), blocker: null })
    expect(opportunityRollbackOptions({
      stage: 'po_received',
      liveBooking: null,
      internalValidation: { status: 'cancelled', bookingId: '' },
    })).toEqual({ targets: milestones.slice(0, 5), blocker: null })
  })
})

describe('opportunity milestone display', () => {
  it('marks internal validation skipped when the PO was confirmed straight from quotation sent', () => {
    const opportunity = {
      stage: 'po_received',
      stageHistory: [
        { event: 'po_confirmed' as const, from: 'quotation_sent' as const },
        { event: 'quotation_published' as const, from: 'rfq_validated' as const },
      ],
    }
    expect(isInternalValidationSkipped(opportunity)).toBe(true)
    expect(opportunityMilestoneSegments(opportunity)).toEqual([
      { stage: 'qualified_opportunity', state: 'complete', optional: false },
      { stage: 'demo_done', state: 'complete', optional: false },
      { stage: 'customer_budget_approved', state: 'complete', optional: false },
      { stage: 'rfq_validated', state: 'complete', optional: false },
      { stage: 'quotation_sent', state: 'complete', optional: false },
      { stage: 'internal_validation', state: 'skipped', optional: true },
      { stage: 'po_received', state: 'current', optional: false },
    ])
  })

  it('uses the latest PO confirmation, so a PO confirmed after internal validation completes it', () => {
    const opportunity = {
      stage: 'po_received',
      stageHistory: [
        { event: 'po_confirmed' as const, from: 'internal_validation' as const },
        { event: 'po_confirmed' as const, from: 'quotation_sent' as const },
      ],
    }
    expect(isInternalValidationSkipped(opportunity)).toBe(false)
    expect(opportunityMilestoneSegments(opportunity)[5]).toEqual({ stage: 'internal_validation', state: 'complete', optional: true })
    expect(isInternalValidationSkipped({ stage: 'quotation_sent', stageHistory: opportunity.stageHistory.slice(1) })).toBe(false)
  })

  it('shows where a lost Opportunity was lost', () => {
    expect(opportunityMilestoneSegments({ stage: 'lost', lostAtStage: 'rfq_validated', stageHistory: [] }).map((segment) => segment.state)).toEqual([
      'complete', 'complete', 'complete', 'lost', 'upcoming', 'upcoming', 'upcoming',
    ])
    expect(opportunityMilestoneSegments({ stage: 'lost', lostAtStage: '', stageHistory: [] }).map((segment) => segment.state)).toEqual(
      new Array(7).fill('upcoming'),
    )
  })

  it('shows the business arrival only when it differs from the recorded time', () => {
    expect(showsSeparateReachedAt({ recordedAt: '2026-07-08T02:00:00Z', reachedAt: '2026-07-05T16:00:00Z' })).toBe(true)
    expect(showsSeparateReachedAt({ recordedAt: '2026-07-08T02:00:00Z', reachedAt: '2026-07-08T02:00:00Z' })).toBe(false)
    expect(showsSeparateReachedAt({ recordedAt: '2026-07-01T02:00:00Z', reachedAt: '' })).toBe(true)
  })
})

describe('internal validation cancel reasons', () => {
  it('localizes the reasons the server writes and keeps anything else as written', () => {
    expect(internalValidationCancelReasonLabel('Opportunity marked lost.', 'zh-CN')).toBe('商机已标记丢单，申请自动撤销。')
    expect(internalValidationCancelReasonLabel('PO received before the internal validation was decided.', 'en-US'))
      .toBe('The PO was received before the internal validation was decided.')
    expect(internalValidationCancelReasonLabel('Opportunity rolled back to rfq_validated.', 'zh-CN')).toBe('商机已回退到RFQ 通过，申请自动撤销。')
    expect(internalValidationCancelReasonLabel('Opportunity rolled back to rfq_validated.', 'en-US')).toBe('The Opportunity was rolled back to RFQ validated.')
    expect(internalValidationCancelReasonLabel('Customer paused the project.', 'zh-CN')).toBe('Customer paused the project.')
  })
})
