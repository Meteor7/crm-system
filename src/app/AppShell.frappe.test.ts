import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createAppRouter } from './router'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import { useNotificationStore } from '@/stores/notifications'

vi.mock('@/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/api')>(),
  usingMock: false,
  notificationDelivery: 'server',
}))

describe('AppShell in Frappe mode', () => {
  it('does not show a local database status card', async () => {
    const { default: AppShell } = await import('./AppShell.vue')
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const wrapper = mount(AppShell, {
      global: {
        plugins: [createPinia(), router],
        stubs: { RouterView: true, CrmChart: { template: '<div />' } },
      },
    })

    expect(wrapper.text()).not.toContain('本地数据库已连接')
    expect(wrapper.text()).not.toContain('Frappe / ERPNext v15')
    expect(wrapper.find('.sidebar-note').exists()).toBe(false)
  }, 15_000)

  it('keeps a failed notification unread and shows the request error without closing the panel', async () => {
    const { default: AppShell } = await import('./AppShell.vue')
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    const apiClient = createMockApi({ latency: 0, role: 'Sales', userId: 'sales@example.invalid' })
    app.bootstrap = (await apiClient.getBootstrap()).data
    const serverNotification = { id: 'CRM-NOT-FAIL', category: 'Action' as const, title: '待办', message: '仍未读', route: '/dashboard', recipientId: 'sales@example.invalid', actorId: 'manager@example.invalid', createdAt: '2026-08-13', read: false }
    app.activeApi = {
      ...apiClient,
      listNotifications: vi.fn().mockImplementation(async (query) => ({
        data: { items: query?.unreadOnly ? [serverNotification] : [serverNotification] },
        meta: { requestId: 'req-notifications', page: 1, pageSize: query?.pageSize ?? 50, total: 1 },
        warnings: [],
      })),
      markNotificationRead: vi.fn().mockRejectedValue(new Error('REQ-NOTIFY-READ: server unavailable')),
    }
    const notifications = useNotificationStore(pinia)
    notifications.setActiveRecipient('sales@example.invalid')
    notifications.replaceAll([serverNotification])
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })

    await wrapper.get('[data-testid="notification-button"]').trigger('click')
    await wrapper.get('[data-notification-id="CRM-NOT-FAIL"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="notification-center"]').exists()).toBe(true)
    expect(wrapper.get('[data-notification-error]').text()).toContain('REQ-NOTIFY-READ')
    expect(notifications.items[0]?.read).toBe(false)
  })
})
