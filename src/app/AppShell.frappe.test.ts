import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createAppRouter } from './router'
import { CrmApiError } from '@/api/contracts'
import { SESSION_EXPIRED_EVENT } from '@/api/session'
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

  it('keeps the page and offers the login page when the session ends while it is in use', async () => {
    const { default: AppShell } = await import('./AppShell.vue')
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    const apiClient = createMockApi({ latency: 0, role: 'Sales', userId: 'sales@example.invalid' })
    app.bootstrap = (await apiClient.getBootstrap()).data
    const listNotifications = vi.fn(async () => ({ data: { items: [] }, meta: { requestId: 'req-notifications', page: 1, pageSize: 50, total: 0 }, warnings: [] }))
    app.activeApi = { ...apiClient, listNotifications }
    const assign = vi.fn()
    vi.stubGlobal('location', { pathname: '/assets/rayher_crm/crm/index.html', search: '?v=819a78af9dc5', hash: '#/contacts', assign })
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })
    await flushPromises()
    expect(wrapper.find('[data-testid="session-expired"]').exists()).toBe(false)

    window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT))
    await flushPromises()

    expect(wrapper.get('[data-testid="session-expired"]').text()).toContain('登录已失效')
    expect(assign).not.toHaveBeenCalled()
    // The polling stops: the server would only refuse again.
    listNotifications.mockClear()
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(listNotifications).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="sign-in-again"]').trigger('click')
    expect(assign).toHaveBeenCalledWith(`/login?redirect-to=${encodeURIComponent('/assets/rayher_crm/crm/index.html?v=819a78af9dc5#/contacts')}`)
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('shows nobody as signed in when the current user could not be read', async () => {
    const { default: AppShell } = await import('./AppShell.vue')
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    app.activeApi = {
      ...createMockApi({ latency: 0 }),
      getBootstrap: vi.fn().mockRejectedValue(new CrmApiError('INTERNAL_ERROR', 'The request could not be completed.', 'req-bootstrap', true)),
    }
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })
    await flushPromises()

    expect(app.bootstrap).toBeNull()
    expect(wrapper.get('[data-testid="account-center-button"]').text()).toBe('')
    await wrapper.get('[data-testid="account-center-button"]').trigger('click')
    const profile = wrapper.get('.account-profile')
    expect(profile.find('strong').text()).toBe('')
    expect(profile.find('span').exists()).toBe(false)
  })
})
