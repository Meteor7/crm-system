import { createPinia, setActivePinia } from 'pinia'
import { markRaw } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { useNotificationStore } from './notifications'
import { useAppStore } from './app'
import { createMockApi } from '@/api/mock-adapter'

describe('notification store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts empty and keeps unread count in sync after a real event arrives', () => {
    const store = useNotificationStore()

    expect(store.items).toHaveLength(0)
    expect(store.unreadCount).toBe(0)
    store.add({
      category: 'Requirement',
      title: '真实待办',
      message: '由当前运行时数据产生',
      route: '/requirements',
    })
    expect(store.unreadCount).toBe(1)

    store.markRead(store.items[0].id)
    expect(store.unreadCount).toBe(0)

    store.markAllRead()
    expect(store.unreadCount).toBe(0)
  })

  it('receives progression events from the app store active API', async () => {
    const app = useAppStore()
    const notifications = useNotificationStore()
    app.activeApi = markRaw(createMockApi({ latency: 0 }))
    await app.loadBootstrap(app.activeApi)

    await app.activeApi.createOpportunityAction('OPP-001', {
      title: 'Store 边界验证',
      owner: 'person002@crm.example.invalid',
      due: '2026-08-08',
      status: 'Open',
    })

    expect(notifications.items[0].title).toBe('新增推进 Action')
  })

  it('keeps targeted notifications private from managers and protects recipient read state', () => {
    const store = useNotificationStore()
    store.add({
      category: 'Action',
      title: 'Assigned action',
      message: 'Follow up',
      route: '/opportunities/OPP-001',
      recipientId: 'person002@crm.example.invalid',
    })

    store.setActiveRecipient('person002@crm.example.invalid', 'Sales')
    expect(store.visibleItems.some((item) => item.title === 'Assigned action')).toBe(true)
    store.setActiveRecipient('person005@crm.example.invalid', 'Sales')
    expect(store.visibleItems.some((item) => item.title === 'Assigned action')).toBe(false)
    store.setActiveRecipient('person073@crm.example.invalid', 'Manager')
    expect(store.visibleItems.some((item) => item.title === 'Assigned action')).toBe(false)

    const targeted = store.items.find((item) => item.title === 'Assigned action')
    expect(targeted?.read).toBe(false)
    store.markRead(targeted!.id)
    store.markAllRead()
    expect(targeted?.read).toBe(false)

    store.setActiveRecipient('person002@crm.example.invalid', 'Sales')
    expect(store.visibleItems.some((item) => item.title === 'Assigned action')).toBe(true)
    expect(store.unreadCount).toBeGreaterThan(0)
  })

  it('uses the server unread total and appends notification history without duplicates', () => {
    const store = useNotificationStore()
    const first = { id: 'CRM-NOT-1', category: 'Action' as const, title: 'First', message: 'One', route: '/dashboard', recipientId: 'sales@example.invalid', actorId: 'manager@example.invalid', createdAt: '2026-08-18', read: false }
    const second = { ...first, id: 'CRM-NOT-2', title: 'Second', read: true }
    store.setActiveRecipient('sales@example.invalid')
    store.replaceAll([first], 75, 12)
    expect(store.unreadCount).toBe(12)
    expect(store.serverTotal).toBe(75)

    store.appendPage([first, second], 75)
    expect(store.items.map((item) => item.id)).toEqual(['CRM-NOT-1', 'CRM-NOT-2'])
    store.markRead('CRM-NOT-1')
    expect(store.unreadCount).toBe(11)
    store.markAllRead()
    expect(store.unreadCount).toBe(0)
  })
})
