import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'

describe('notification API contract', () => {
  it('returns a paged server-shaped notification list and recipient-safe mutations', async () => {
    const api = createMockApi({ latency: 0 })

    const listed = await api.listNotifications({ page: 1, pageSize: 20, unreadOnly: true })
    expect(listed.data.items).toEqual([])
    expect(listed.meta).toMatchObject({ page: 1, pageSize: 20, total: 0 })
    await expect(api.markNotificationRead('CRM-NOT-00001')).rejects.toMatchObject({
      code: 'NOT_FOUND',
    })
    await expect(api.markAllNotificationsRead()).resolves.toMatchObject({ data: { updated: 0 } })
  })
})
