import { describe, expect, it, vi } from 'vitest'
import { createFrappeApi } from './frappe-adapter'
const success = (data: unknown) => new Response(JSON.stringify({ message: { data, warnings: [], meta: { requestId: 'approval-test' } } }), { headers: { 'Content-Type': 'application/json' } })
describe('Frappe pending approval contract', () => {
  it('uses the authenticated queue endpoint without sending a user, role or dashboard filter', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(success({ items: [] })), api = createFrappeApi({ fetchImpl })
    expect((await api.listPendingApprovals()).data.items).toEqual([])
    expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/method/rayher_crm.api.v1.approvals.list_pending_approvals')
    expect(fetchImpl.mock.calls[0]?.[1]).toMatchObject({ method: 'GET', credentials: 'same-origin' })
  })
  it('posts only the opaque task id when recording a view', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(success({ id: 'task-1', viewedAt: '2026-10-14' })), api = createFrappeApi({ fetchImpl })
    await api.markApprovalViewed('task-1')
    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/method/rayher_crm.api.v1.approvals.mark_approval_viewed')
    expect(Object.fromEntries(new URLSearchParams(init.body as string))).toEqual({ id: 'task-1' })
  })
})
