import { describe, expect, it, vi } from 'vitest'
import { createFrappeApi } from './frappe-adapter'
import { createMockApi } from './mock-adapter'

const success = (data: unknown) => new Response(JSON.stringify({ message: { data, warnings: [] } }), { headers: { 'Content-Type': 'application/json' } })
describe('Status API transport', () => {
  it('sends metadata, retained IDs, version and actual bytes in one multipart request', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(success({ id: 'STATUS-1' }))
    const api = createFrappeApi({ fetchImpl, csrfToken: () => 'test-csrf' })
    const blob = new Blob(['meeting notes'], { type: 'text/plain' })
    const input = { text: 'Updated', recordId: 'STATUS-1', retainedFileIds: ['FILE-1'], expectedModified: '2026-09-21T00:00:00Z' }
    await api.saveOpportunityStatus('OPP-1', input, [{ blob, fileName: '记录.txt', mimeType: blob.type, size: blob.size }])
    const [url, request] = fetchImpl.mock.calls[0]
    expect(url).toContain('opportunity_status.save_record')
    expect(request.method).toBe('POST')
    expect(request.headers.get('X-Frappe-CSRF-Token')).toBe('test-csrf')
    expect(request.headers.has('Content-Type')).toBe(false)
    expect(request.body.get('opportunityId')).toBe('OPP-1')
    expect(JSON.parse(request.body.get('input'))).toEqual(input)
    expect(request.body.get('files').name).toBe('记录.txt')
    expect(await request.body.get('files').text()).toBe('meeting notes')
  })
  it('includes opportunity and record scope when downloading a binary attachment', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response('notes', { headers: { 'Content-Type': 'text/plain', 'Content-Disposition': 'attachment; filename="meeting.txt"' } }))
    const api = createFrappeApi({ fetchImpl })
    const result = await api.getOpportunityStatusFile('OPP-1', 'STATUS-1', 'FILE-1')
    const url = new URL(fetchImpl.mock.calls[0][0], 'http://localhost')
    expect(Object.fromEntries(url.searchParams)).toEqual({ opportunityId: 'OPP-1', recordId: 'STATUS-1', fileId: 'FILE-1' })
    expect(result.fileName).toBe('meeting.txt')
    expect(await result.blob.text()).toBe('notes')
  })
  it('rejects stale edits and foreign attachment IDs without losing saved data', async () => {
    const api = createMockApi({ latency: 0 })
    const initial = (await api.saveOpportunityStatus('OPP-001', { text: 'Initial', retainedFileIds: [] }, [])).data
    const input = { text: 'Updated', retainedFileIds: [], recordId: initial.id, expectedModified: initial.modified }
    await api.saveOpportunityStatus('OPP-001', input, [])
    await expect(api.saveOpportunityStatus('OPP-001', { ...input, text: 'Stale' }, [])).rejects.toMatchObject({ code: 'VERSION_CONFLICT' })
    await expect(api.saveOpportunityStatus('OPP-001', { text: 'New', retainedFileIds: ['foreign'] }, [])).rejects.toMatchObject({ code: 'VALIDATION_ERROR' })
    expect((await api.listOpportunityStatuses('OPP-001')).data.map(record => record.text)).toEqual(['Updated'])
  })
})
