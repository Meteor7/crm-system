import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'

describe('Visit record workflow', () => {
  it('marks a Visit complete when its record is submitted', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', salesRepository })
    const created = await sales.createVisit({
      accountId: 'ACC-001', subject: 'Record submission', date: '2026-08-20', type: 'On-site',
      owner: 'person002@crm.example.invalid', objective: 'Confirm customer requirements',
    })
    await sales.updateVisitMeetingRecord(created.data.id, {
      meetingStart: '', meetingEnd: '', purpose: 'Review', attendees: 'Customer',
      agenda: 'Confirm scope', summary: 'Draft', conclusion: 'Proceed', followup: 'Send plan',
    })
    expect((await sales.getVisit(created.data.id)).data.status).toBe('Planned')
    salesRepository.snapshot.visits.find((item) => item.id === created.data.id)!.status = 'Visited'
    const content = 'Meeting Purpose: Review\nAgenda: Confirm scope'
    const submitted = await sales.submitVisitRecord(created.data.id, {
      blob: new Blob([content], { type: 'text/plain' }),
      fileName: 'visit-record.txt', mimeType: 'text/plain', size: content.length,
    })

    expect(submitted.data.status).toBe('Minutes Submitted')
    expect(submitted.data.attachments).toHaveLength(1)
  })
})
