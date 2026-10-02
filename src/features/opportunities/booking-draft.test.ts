import { describe, expect, it } from 'vitest'
import type { ContactSummaryDto } from '@/types/crm'
import type { BookingDraft, OpportunityInternalValidationDto } from '@/types/workspaces'
import { opportunityBookingDraft, validateBookingDraft } from './booking-draft'

const contacts = [
  { id: 'C-OLD', accountId: 'A-1', status: 'Active' },
  { id: 'C-NEW', accountId: 'A-1', status: 'Active' },
] as ContactSummaryDto[]

const requested: BookingDraft = {
  primaryContactId: 'C-OLD', equipment: 'Inspection 3000', quantity: 1, ddl: '2027-03-31',
  amount: '880000.00', currency: 'CNY', owner: 'person002@crm.example.invalid', note: 'PO 4500012345',
}

const approval: OpportunityInternalValidationDto = {
  id: 'IV-1', attemptNo: 1, status: 'approved', reason: 'Long lead time', expectedPoDate: '2026-11-30', booking: requested,
  requestedBy: 'person002@crm.example.invalid', requestedAt: '2026-09-01T00:00:00Z', decidedBy: 'manager', decidedAt: '2026-09-02T00:00:00Z',
  decisionComment: '', bookingId: 'BK-1', cancelledBy: '', cancelledAt: '', cancelReason: '',
}

const opportunity: Parameters<typeof opportunityBookingDraft>[0] = {
  accountId: 'A-1', title: 'Fab expansion', toolType: 'Inspection', amount: '880000.00', currency: 'CNY', poDate: '2026-12-31',
  internalValidation: approval, liveBooking: null,
}

describe('opportunityBookingDraft', () => {
  it('prefers the contact and note of the Pending Booking over the approved request draft', () => {
    const draft = opportunityBookingDraft({
      ...opportunity,
      liveBooking: {
        id: 'BK-1', status: 'Pending', primaryContactId: 'C-NEW', equipment: 'Inspection 3000', quantity: 2,
        ddl: '2027-04-30', amount: '900000.00', currency: 'CNY', owner: 'person002@crm.example.invalid', note: 'Ship to the new fab',
      },
    }, contacts, 'manager')
    expect(draft).toMatchObject({ primaryContactId: 'C-NEW', quantity: 2, ddl: '2027-04-30', amount: '900000.00', note: 'Ship to the new fab' })
  })

  it('falls back to the request draft when the live Booking hides its details or has none', () => {
    const hidden = opportunityBookingDraft({ ...opportunity, liveBooking: { id: 'BK-1', status: 'Pending' } }, contacts, 'manager')
    expect(hidden).toMatchObject({ primaryContactId: 'C-OLD', quantity: 1, ddl: '2027-03-31', note: 'PO 4500012345' })
    expect(opportunityBookingDraft(opportunity, contacts, 'manager')).toMatchObject({ primaryContactId: 'C-OLD', note: 'PO 4500012345' })
  })

  it('ignores a live Booking contact that is no longer active on the account', () => {
    const draft = opportunityBookingDraft({
      ...opportunity,
      liveBooking: { id: 'BK-1', status: 'Pending', primaryContactId: 'C-GONE', note: '' },
    }, contacts, 'manager')
    expect(draft).toMatchObject({ primaryContactId: 'C-OLD', note: '' })
  })

  it('leaves the amount empty for Sales to enter when the Opportunity has none yet, never 0', () => {
    const draft = opportunityBookingDraft({ ...opportunity, internalValidation: null, amount: '', amountCny: '' }, contacts, 'manager')
    expect(draft).toMatchObject({ amount: '', amountCny: '' })
    expect(validateBookingDraft(draft).amount).toBeDefined()
  })
})
