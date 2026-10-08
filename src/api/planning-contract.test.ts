import { describe, expect, it, vi } from 'vitest'
import { createFrappeApi } from './frappe-adapter'

describe('Planning source API contracts', () => {
  it('roundtrips quotation source IDs and concurrency tokens without flattening nested input', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ message: { data: {}, warnings: [], meta: { requestId: 'planning' } } }), { headers: { 'Content-Type': 'application/json' } }))
    const api = createFrappeApi({ fetchImpl: fetchMock })
    await api.getQuotationPlanning('quote-1')
    await api.saveQuotationSchedule('quote-1', { plannedSendDate: null }, 'q-v1')
    await api.saveQuotationFollowUp('quote-1', { title: 'Confirm', due: '2026-10-12', status: 'Done', note: '' }, 'followup-1', 'q-v2')
    await api.saveEvent({ title: 'Show', owner: 'alice', startDate: '2026-10-12', endDate: '2026-10-14', status: 'Planned',
      accountId: '', opportunityId: '', region: '', market: '', equipment: '', note: '' }, 'event-1', 'e-v1')
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][]
    expect(String(calls[0]![0])).toContain('quotation_planning.get_planning?quotationId=quote-1')
    const bodies = calls.slice(1).map(call => new URLSearchParams(String(call[1].body)))
    expect(JSON.parse(bodies[0]!.get('input')!)).toEqual({ plannedSendDate: null })
    expect(bodies[0]!.get('expectedModified')).toBe('q-v1')
    expect([bodies[1]!.get('quotationId'), bodies[1]!.get('id'), bodies[1]!.get('expectedModified')]).toEqual(['quote-1', 'followup-1', 'q-v2'])
    expect([bodies[2]!.get('id'), bodies[2]!.get('expectedModified')]).toEqual(['event-1', 'e-v1'])
    expect(JSON.parse(bodies[2]!.get('input')!).title).toBe('Show')
  })
})
