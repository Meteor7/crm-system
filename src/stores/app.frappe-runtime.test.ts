import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { initializePersonnelDirectory, PERSONNEL } from '@/demo/personnel'
import { useNotificationStore } from './notifications'

vi.mock('@/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api')>(),
  notificationDelivery: 'server',
  usingMock: false,
}))

describe('app Frappe runtime boundaries', () => {
  const initialPersonnel = structuredClone(PERSONNEL)
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => {
    initializePersonnelDirectory(initialPersonnel)
    delete (window as Window & { frappe?: unknown }).frappe
  })

  it('initializes personnel and notifications only from server responses', async () => {
    const { useAppStore } = await import('./app')
    const base = createMockApi({ latency: 0 })
    const bootstrap = await base.getBootstrap()
    const listRequirements = vi.fn()
    const listNotifications = vi.fn().mockResolvedValue({
      data: { items: [{
        id: 'CRM-NOT-00042', category: 'Action', title: '服务器待办', message: '仅来自当前收件人',
        route: '/opportunities/OPP-42', recipientId: 'sales@example.invalid', actorId: 'manager@example.invalid',
        createdAt: '2026-08-05T04:00:00Z', read: false,
      }] },
      meta: { requestId: 'req_notifications', page: 1, pageSize: 50, total: 1 },
      warnings: [],
    })
    const markNotificationRead = vi.fn().mockResolvedValue({ data: {}, meta: { requestId: 'req_read' }, warnings: [] })
    const markAllNotificationsRead = vi.fn().mockResolvedValue({ data: { updated: 1 }, meta: { requestId: 'req_all' }, warnings: [] })
    const api = {
      ...base,
      getBootstrap: vi.fn().mockResolvedValue({
        ...bootstrap,
        data: {
          ...bootstrap.data,
          csrfToken: 'csrf-runtime-test',
          user: { id: 'sales@example.invalid', name: '真实销售', initials: 'XS', role: 'Sales' as const, team: '销售经理' },
          personnel: [{
            id: 'sales@example.invalid', name: '真实销售', initials: 'XS', role: 'Sales' as const,
            team: '销售经理', availableForAssignment: true, teamOwners: [], assignedAccountIds: [],
          }],
        },
      }),
      listRequirements,
      listNotifications,
      markNotificationRead,
      markAllNotificationsRead,
    }

    const app = useAppStore()
    const notifications = useNotificationStore()
    await app.loadBootstrap(api)

    expect(app.bootstrap?.personnel?.map((person) => person.id)).toEqual(['sales@example.invalid'])
    expect((window as Window & { frappe?: { csrf_token?: string } }).frappe?.csrf_token).toBe('csrf-runtime-test')
    expect(listNotifications).toHaveBeenCalledWith({ page: 1, pageSize: 50 })
    expect(listRequirements).not.toHaveBeenCalled()
    expect(notifications.items.map((item) => item.id)).toEqual(['CRM-NOT-00042'])

    await app.markNotificationRead('CRM-NOT-00042')
    expect(markNotificationRead).toHaveBeenCalledWith('CRM-NOT-00042')
    expect(notifications.items[0].read).toBe(true)

    notifications.items[0].read = false
    await app.markAllNotificationsRead()
    expect(markAllNotificationsRead).toHaveBeenCalledOnce()
    expect(notifications.items[0].read).toBe(true)
  })

  it('keeps the authenticated bootstrap when notification loading fails', async () => {
    const { useAppStore } = await import('./app')
    const base = createMockApi({ latency: 0, role: 'Engineer', userId: 'person077@crm.example.invalid' })
    const bootstrap = await base.getBootstrap()
    const app = useAppStore()

    await app.loadBootstrap({
      ...base,
      getBootstrap: vi.fn().mockResolvedValue(bootstrap),
      listNotifications: vi.fn().mockRejectedValue(new Error('notification service unavailable')),
    })

    expect(app.bootstrap?.user.id).toBe('person077@crm.example.invalid')
    expect(app.bootstrap?.user.role).toBe('Engineer')
    expect(app.loading).toBe(false)
  })
  it('keeps unread state when the server rejects the mutation', async () => {
    const { useAppStore } = await import('./app')
    const app = useAppStore()
    const notifications = useNotificationStore()
    notifications.replaceAll([{
      id: 'CRM-NOT-FAIL', category: 'Action', title: '待办', message: '仍未读', route: '/dashboard',
      recipientId: 'sales@example.invalid', actorId: 'manager@example.invalid',
      createdAt: '2026-08-05T04:00:00Z', read: false,
    }])
    notifications.setActiveRecipient('sales@example.invalid')
    app.activeApi = {
      ...createMockApi({ latency: 0 }),
      markNotificationRead: vi.fn().mockRejectedValue(new Error('server unavailable')),
    }

    await expect(app.markNotificationRead('CRM-NOT-FAIL')).rejects.toThrow('server unavailable')
    expect(notifications.items[0].read).toBe(false)
  })
})
