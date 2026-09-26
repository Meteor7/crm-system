import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'

describe('Visit record workflow', () => {
  it('submits a new visit for Manager review once its record is complete, and review completes it', async () => {
    const salesRepository = createMemorySalesRepository()
    // Meeting records live inside one API client, so the Manager runs the whole flow.
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository })
    const created = await manager.createVisit({
      accountId: 'ACC-001', subject: 'Record submission', date: '2026-08-20', type: 'On-site',
      owner: 'person002@crm.example.invalid', objective: 'Confirm customer requirements',
    })
    expect(created.data.status).toBe('Planned')

    // An upload that leaves required fields unrecognised keeps the visit waiting.
    const content = 'Meeting Purpose: Review\nAgenda: Confirm scope'
    const partial = await manager.submitVisitRecord(created.data.id, {
      blob: new Blob([content], { type: 'text/plain' }),
      fileName: 'visit-record.txt', mimeType: 'text/plain', size: content.length,
    })
    expect(partial.data.status).toBe('Planned')
    expect(partial.data.attachments).toHaveLength(1)

    await manager.updateVisitMeetingRecord(created.data.id, {
      meetingStart: '', meetingEnd: '', purpose: 'Review', attendees: 'Customer',
      agenda: 'Confirm scope', summary: 'Draft', conclusion: 'Proceed', followup: 'Send plan',
    })
    expect((await manager.getVisit(created.data.id)).data.status).toBe('Minutes Submitted')

    const reviewed = await manager.reviewVisit(created.data.id)
    expect(reviewed.data.status).toBe('Manager Reviewed')
  })
})
