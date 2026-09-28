import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import type { BookingDraft } from '@/types/workspaces'

type MockApi = ReturnType<typeof createMockApi>

async function activeDraft(api: MockApi, accountId: string): Promise<BookingDraft> {
  const contact = (await api.listContacts({ accountId, pageSize: 100 })).data.items.find((item) => item.status === 'Active')!
  return {
    primaryContactId: contact.id, equipment: 'HBM AOI', quantity: 1, ddl: '2026-11-12',
    amount: '32500000.00', currency: 'CNY', owner: 'person002@crm.example.invalid', note: '',
  }
}

describe('mock Opportunity stage workflow', () => {
  it('creates an Opportunity only after the qualification is confirmed, always at Qualified opportunity', async () => {
    const manager = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-20' })
    const input = {
      accountId: 'ACC-001', siteId: 'SITE-001', title: 'Qualified only', owner: 'person002@crm.example.invalid', amount: '1000000.00',
      intentScore: 50, poDate: '2026-12-31', toolType: 'AOI', saleType: 'New Equipment', subRegion: 'East China', currency: 'CNY',
    }

    await expect(manager.createStrategyOpportunity(input))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { qualificationConfirmed: 'Required' } })
    await expect(manager.createStrategyOpportunity({ ...input, qualificationConfirmed: true, stage: 'demo_done' } as never))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'New Opportunity must start at qualified_opportunity.' })

    const created = (await manager.createStrategyOpportunity({ ...input, qualificationConfirmed: true })).data
    expect(created).toMatchObject({
      stage: 'qualified_opportunity', stageChangedAt: '2026-07-20T02:30:00.000Z', budgetApprovedOn: '', lostAtStage: '',
      internalValidation: null, liveBooking: null,
    })
    expect(created.stageHistory).toEqual([expect.objectContaining({
      from: '', to: 'qualified_opportunity', source: 'creation', event: 'created', actor: 'person029@crm.example.invalid',
    })])
  })

  it('confirms the customer budget only at Demo done with a past date and a probability level', async () => {
    const salesRepository = createMemorySalesRepository()
    for (const id of ['OPP-001', 'OPP-007']) salesRepository.snapshot.opportunities.find((item) => item.id === id)!.stage = 'demo_done'
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository, today: '2026-07-20' })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, today: '2026-07-20' })

    await expect(manager.confirmBudgetApproved('OPP-003', { approvedOn: '2026-07-06' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Budget approval is not available at quotation_sent.' })
    await expect(manager.confirmBudgetApproved('OPP-007', { approvedOn: '2026-07-06' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'Set the probability level before this step.' })
    await expect(sales.confirmBudgetApproved('OPP-001', { approvedOn: '2026-07-21' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'approvedOn cannot be in the future.' })
    await expect(sales.confirmBudgetApproved('OPP-001', { approvedOn: 'not-a-date' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'approvedOn must be a real YYYY-MM-DD date.' })

    const confirmed = (await sales.confirmBudgetApproved('OPP-001', { approvedOn: '2026-07-06' })).data
    expect(confirmed).toMatchObject({ stage: 'customer_budget_approved', budgetApprovedOn: '2026-07-06', stageChangedAt: '2026-07-05T16:00:00.000Z' })
    expect(confirmed.stageHistory[0]).toMatchObject({
      from: 'demo_done', to: 'customer_budget_approved', source: 'manual', event: 'budget_confirmed', actor: 'person002@crm.example.invalid',
      recordedAt: '2026-07-20T02:30:00.000Z', reachedAt: '2026-07-05T16:00:00.000Z', reachedAtBasis: 'declared',
    })
    await expect(sales.confirmBudgetApproved('OPP-001', { approvedOn: '2026-07-06' }, 'stale-version'))
      .rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
  })

  it('reviews an internal validation by another Manager and creates the Pending Booking on approval', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository, today: '2026-07-20' })
    const reviewer = createMockApi({ latency: 0, role: 'Manager', userId: 'person015@crm.example.invalid', salesRepository, today: '2026-07-20' })
    const booking = await activeDraft(sales, 'ACC-002')

    await expect(sales.requestInternalValidation('OPP-001', { reason: 'Too early', expectedPoDate: '2026-09-30', booking: await activeDraft(sales, 'ACC-001') }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Internal validation is not available at qualified_opportunity.' })
    await expect(sales.requestInternalValidation('OPP-003', { reason: ' ', expectedPoDate: '2026-09-30', booking }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'reason is required.' })
    await expect(sales.requestInternalValidation('OPP-003', { reason: 'Lock capacity', expectedPoDate: '2026-09-30', booking: { ...booking, owner: 'person005@crm.example.invalid' } }))
      .rejects.toMatchObject({ code: 'SCOPE_DENIED' })

    const requested = (await sales.requestInternalValidation('OPP-003', { reason: 'Lock capacity', expectedPoDate: '2026-09-30', booking })).data
    expect(requested).toMatchObject({ stage: 'quotation_sent', liveBooking: null })
    expect(requested.internalValidation).toMatchObject({ attemptNo: 1, status: 'pending', reason: 'Lock capacity', requestedBy: 'person002@crm.example.invalid', bookingId: '' })
    const validationId = requested.internalValidation!.id
    expect(requested.history[0]).toMatchObject({ field: 'internalValidationRequested', from: '', to: validationId })
    await expect(sales.requestInternalValidation('OPP-003', { reason: 'Again', expectedPoDate: '2026-09-30', booking }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'The Opportunity already has a pending internal validation.' })

    await expect(sales.reviewInternalValidation('OPP-003', { validationId, decision: 'approved', comment: '' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    await expect(reviewer.reviewInternalValidation('OPP-003', { validationId, decision: 'rejected', comment: '' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'A comment is required to reject an internal validation.' })

    const approved = (await reviewer.reviewInternalValidation('OPP-003', { validationId, decision: 'approved', comment: 'Go ahead' })).data
    expect(approved).toMatchObject({ stage: 'internal_validation', liveBooking: { status: 'Pending', equipment: 'HBM AOI', owner: 'person002@crm.example.invalid' } })
    expect(approved.internalValidation).toMatchObject({ status: 'approved', decidedBy: 'person015@crm.example.invalid', decisionComment: 'Go ahead', bookingId: approved.liveBooking!.id })
    expect(approved.stageHistory[0]).toMatchObject({
      from: 'quotation_sent', to: 'internal_validation', source: 'approval', event: 'internal_validation_approved',
      referenceDoctype: 'CRM Opportunity Internal Validation', referenceName: validationId, actor: 'person015@crm.example.invalid',
    })
    expect(approved.history[0]).toMatchObject({ field: 'internalValidationApproved', from: validationId, to: approved.liveBooking!.id })
    await expect(reviewer.reviewInternalValidation('OPP-003', { validationId, decision: 'approved', comment: '' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'The internal validation was already decided or cancelled.' })
  })

  it('keeps a Manager from reviewing their own request and leaves the stage after a rejection', async () => {
    const salesRepository = createMemorySalesRepository()
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, today: '2026-07-20' })
    const other = createMockApi({ latency: 0, role: 'Manager', userId: 'person015@crm.example.invalid', salesRepository, today: '2026-07-20' })
    const booking = await activeDraft(manager, 'ACC-002')
    const requested = (await manager.requestInternalValidation('OPP-003', { reason: 'Capacity', expectedPoDate: '2026-09-30', booking })).data
    const validationId = requested.internalValidation!.id

    await expect(manager.reviewInternalValidation('OPP-003', { validationId, decision: 'approved', comment: '' }))
      .rejects.toMatchObject({ code: 'PERMISSION_DENIED', message: 'Managers cannot review their own internal validation.' })
    await expect(other.reviewInternalValidation('OPP-003', { validationId: 'CRM-VAL-99999', decision: 'approved', comment: '' }))
      .rejects.toMatchObject({ code: 'NOT_FOUND' })

    const rejected = (await other.reviewInternalValidation('OPP-003', { validationId, decision: 'rejected', comment: 'Wait for the PO' })).data
    expect(rejected).toMatchObject({ stage: 'quotation_sent', liveBooking: null })
    expect(rejected.internalValidation).toMatchObject({ status: 'rejected', decidedBy: 'person015@crm.example.invalid', decisionComment: 'Wait for the PO' })
    expect(rejected.history[0]).toMatchObject({ field: 'internalValidationRejected', from: validationId, to: 'Wait for the PO' })

    const retried = (await manager.requestInternalValidation('OPP-003', { reason: 'Capacity again', expectedPoDate: '2026-09-30', booking })).data
    expect(retried.internalValidation).toMatchObject({ attemptNo: 2, status: 'pending' })
  })

  it('confirms the PO on the Pending Booking of an approved validation and cancels a request still pending at quotation sent', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository, today: '2026-07-20' })
    const seeded = (await sales.getStrategyOpportunity('OPP-008')).data
    expect(seeded).toMatchObject({
      stage: 'internal_validation',
      liveBooking: { id: 'BKG-003', status: 'Pending' },
      internalValidation: { id: 'CRM-VAL-00001', status: 'approved', bookingId: 'BKG-003' },
    })

    const confirmed = (await sales.confirmPo('OPP-008', { booking: { ...seeded.internalValidation!.booking, quantity: 3 } }, seeded.modified)).data
    expect(confirmed).toMatchObject({ stage: 'po_received', liveBooking: { id: 'BKG-003', status: 'Confirmed', quantity: 3 } })
    expect(confirmed.stageHistory[0]).toMatchObject({
      from: 'internal_validation', to: 'po_received', source: 'manual', event: 'po_confirmed', referenceDoctype: 'CRM Booking', referenceName: 'BKG-003',
    })
    expect(confirmed.history[0]).toMatchObject({ field: 'poConfirmed', from: '', to: 'BKG-003' })
    await expect(sales.confirmPo('OPP-008', { booking: seeded.internalValidation!.booking }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'The Opportunity already has a live Booking.' })

    const booking = await activeDraft(sales, 'ACC-002')
    await sales.requestInternalValidation('OPP-003', { reason: 'Capacity', expectedPoDate: '2026-09-30', booking })
    const direct = (await sales.confirmPo('OPP-003', { booking })).data
    expect(direct).toMatchObject({ stage: 'po_received', liveBooking: { status: 'Confirmed' } })
    expect(direct.liveBooking!.id).not.toBe('BKG-003')
    expect(direct.internalValidation).toMatchObject({
      status: 'cancelled', cancelReason: 'PO received before the internal validation was decided.', cancelledBy: 'person002@crm.example.invalid',
    })
    expect(direct.stageHistory[0]).toMatchObject({ from: 'quotation_sent', to: 'po_received', event: 'po_confirmed' })
  })

  it('replaces a Booking cancelled by hand at PO received without moving the stage', async () => {
    const salesRepository = createMemorySalesRepository()
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, today: '2026-07-20' })
    const current = (await manager.listBookings({ pageSize: 100 })).data.items.find((item) => item.id === 'BKG-001')!
    const draft: BookingDraft = {
      primaryContactId: current.primaryContactId, equipment: 'FastScan 1200', quantity: 2, ddl: '2026-08-28',
      amount: '18800000.00', currency: 'CNY', owner: 'person005@crm.example.invalid', note: '',
    }

    await expect(manager.confirmPo('OPP-006', { booking: draft }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'The Opportunity already has a live Booking.' })
    await manager.updateBooking('BKG-001', { ...current, status: 'Cancelled' } as never)

    const replaced = (await manager.confirmPo('OPP-006', { booking: draft })).data
    expect(replaced).toMatchObject({ stage: 'po_received', stageChangedAt: '2026-07-02T08:30:00Z', liveBooking: { status: 'Confirmed' } })
    expect(replaced.stageHistory).toHaveLength(2)
    expect(replaced.history[0]).toMatchObject({ field: 'bookingReplaced', from: '', to: replaced.liveBooking!.id })
  })

  it('marks an open Opportunity lost without a live Booking and reopens it at or below the stage it was lost at', async () => {
    const salesRepository = createMemorySalesRepository()
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, today: '2026-07-20' })

    await expect(manager.markOpportunityLost('OPP-006', { lostReason: 'Too late' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Marking the Opportunity lost is not available at po_received.' })
    await expect(manager.markOpportunityLost('OPP-008', { lostReason: 'Customer cancelled' }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'Cancel the Booking before marking the Opportunity lost.' })
    await expect(manager.markOpportunityLost('OPP-003', { lostReason: ' ' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'lostReason is required.' })

    const lost = (await manager.markOpportunityLost('OPP-003', { lostReason: 'Budget frozen' })).data
    expect(lost).toMatchObject({
      stage: 'lost', lostReason: 'Budget frozen', lostAtStage: 'quotation_sent', lostBy: 'person029@crm.example.invalid', lostAt: '2026-07-20T02:30:00.000Z',
    })
    expect(lost.stageHistory[0]).toMatchObject({ from: 'quotation_sent', to: 'lost', source: 'lost', event: 'marked_lost', reason: 'Budget frozen' })
    await expect(manager.updateStrategyOpportunity('OPP-003', { lostReason: '' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'Lost Reason is required for a lost Opportunity.' })

    await expect(manager.rollbackOpportunityStage('OPP-003', { targetStage: 'internal_validation', reason: 'Customer is back' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'A lost Opportunity can only reopen at or below quotation_sent.' })
    const reopened = (await manager.rollbackOpportunityStage('OPP-003', { targetStage: 'quotation_sent', reason: 'Customer is back' })).data
    expect(reopened).toMatchObject({ stage: 'quotation_sent', lostReason: '', lostAtStage: '', lostAt: '', lostBy: '' })
    expect(reopened.stageHistory[0]).toMatchObject({ from: 'lost', to: 'quotation_sent', source: 'rollback', event: 'reopened', reason: 'Customer is back' })
  })

  it('rolls back to internal validation only with the Booking its approval created and blocks rollback behind a completed Booking', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository, today: '2026-07-20' })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, today: '2026-07-20' })
    const seeded = (await sales.getStrategyOpportunity('OPP-008')).data
    await sales.confirmPo('OPP-008', { booking: seeded.internalValidation!.booking })

    await expect(manager.rollbackOpportunityStage('OPP-008', { targetStage: 'quotation_sent', reason: 'PO withdrawn' }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'Cancel the Booking before rolling the Opportunity back.' })
    const back = (await manager.rollbackOpportunityStage('OPP-008', { targetStage: 'internal_validation', reason: 'PO withdrawn' })).data
    expect(back).toMatchObject({ stage: 'internal_validation', liveBooking: { id: 'BKG-003', status: 'Pending' } })

    await expect(manager.rollbackOpportunityStage('OPP-006', { targetStage: 'internal_validation', reason: 'No approval' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'internal_validation requires the Booking created by an approved internal validation.' })
    await manager.convertBookingToInstalledTool('BKG-001', { siteId: 'SITE-006', engineerOwner: 'person077@crm.example.invalid', serial: 'IGNORED', model: 'FastScan 1200' })
    await expect(manager.rollbackOpportunityStage('OPP-006', { targetStage: 'quotation_sent', reason: 'Too late' }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'A completed Booking blocks stage rollback.' })
  })

  it('refuses stage edits and applies the probability level rules on update', async () => {
    const salesRepository = createMemorySalesRepository()
    salesRepository.snapshot.opportunities.find((item) => item.id === 'OPP-001')!.stage = 'demo_done'
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository, today: '2026-07-20' })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository, today: '2026-07-20' })

    await expect(sales.updateStrategyOpportunity('OPP-001', { stage: 'customer_budget_approved' } as never))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'Opportunity stages change only through their workflow actions.' })
    await expect(sales.updateStrategyOpportunity('OPP-001', { stage: 'demo_done', title: 'Same stage is fine' } as never))
      .resolves.toMatchObject({ data: { title: 'Same stage is fine', stage: 'demo_done' } })
    await expect(sales.updateStrategyOpportunity('OPP-001', { probabilityLevel: '' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', message: 'probabilityLevel cannot be cleared once the demo is done.' })
    await expect(sales.updateStrategyOpportunity('OPP-001', { probabilityLevel: 'committed' }))
      .resolves.toMatchObject({ data: { probabilityLevel: 'committed' } })
    await expect(manager.updateStrategyOpportunity('OPP-008', { saleType: 'Service' }))
      .rejects.toMatchObject({ code: 'CONFLICT', message: 'Account and sale type cannot change while the Opportunity has a live Booking.' })

    const seeded = (await sales.getStrategyOpportunity('OPP-008')).data
    await sales.confirmPo('OPP-008', { booking: seeded.internalValidation!.booking })
    await expect(sales.updateStrategyOpportunity('OPP-008', { probabilityLevel: 'committed' }))
      .rejects.toMatchObject({ code: 'INVALID_TRANSITION', message: 'The probability level is frozen once the PO is received or the Opportunity is lost.' })
  })
})
