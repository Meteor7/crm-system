import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createAppRouter } from './router'
import { CrmApiError, type CrmApi } from '@/api/contracts'
import { ClientRequestError } from '@/api/request-state'
import { localeMessage } from '@/i18n'
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
  it('signs out from the account centre and goes to the login page', async () => {
    const { default: AppShell } = await import('./AppShell.vue')
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    app.bootstrap = (await apiClient.getBootstrap()).data
    const signOut = vi.fn(async () => {})
    app.activeApi = { ...apiClient, signOut, listNotifications: vi.fn(async () => ({ data: { items: [] }, meta: { requestId: 'req-notifications', page: 1, pageSize: 50, total: 0 }, warnings: [] })) }
    const assign = vi.fn(), replace = vi.fn(), reload = vi.fn()
    vi.stubGlobal('location', { pathname: '/assets/rayher_crm/crm/index.html', search: '', hash: '#/dashboard', assign, replace, reload })
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })
    await flushPromises()

    await wrapper.get('[data-testid="account-center-button"]').trigger('click')
    const button = wrapper.get('[data-testid="sign-out"]')
    expect(button.text()).toContain('退出登录')

    // Brought back whole from the back-forward cache while still signed in: the page keeps what it has.
    expect(sessionStorage.getItem('rayher-crm:session-user')).toBe(app.bootstrap!.user.id)
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(reload).not.toHaveBeenCalled()
    // Brought back after a later page of the tab signed in as someone else (or signed out): it loads anew.
    sessionStorage.setItem('rayher-crm:session-user', 'someone.else@example.invalid')
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(reload).toHaveBeenCalledTimes(1)
    reload.mockClear()
    sessionStorage.setItem('rayher-crm:session-user', app.bootstrap!.user.id)

    // While the server is asked, the shell reads no notifications (a read answered after the logout would write the
    // session back); the page coming to the front reads them otherwise.
    const listNotifications = app.activeApi.listNotifications as ReturnType<typeof vi.fn>
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    const readsBefore = listNotifications.mock.calls.length
    expect(readsBefore).toBeGreaterThan(0)
    let fail: (reason: unknown) => void = () => undefined
    signOut.mockImplementationOnce(() => new Promise<void>((_resolve, reject) => { fail = reject }))
    await button.trigger('click')
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(listNotifications.mock.calls.length).toBe(readsBefore)
    fail(new CrmApiError('INTERNAL_ERROR', '', 'req_sign_out_held', true))
    await flushPromises()
    expect(replace).not.toHaveBeenCalled()

    // Refused by the server: still signed in, the account centre says so and the page stays.
    signOut.mockRejectedValueOnce(new CrmApiError('INTERNAL_ERROR', '', 'req_sign_out', true))
    await button.trigger('click')
    await flushPromises()
    expect(signOut).toHaveBeenCalledTimes(2)
    expect(replace).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="account-center"] [role="alert"]').text()).toContain('退出登录失败')

    // What the server said comes after it: a Frappe status without a message of its own, as the transport reads it,
    // or the server's own message.
    signOut.mockRejectedValueOnce(new ClientRequestError('VALIDATION_ERROR', localeMessage('Bad request.', '请求无效。'), 'req_sign_out_400'))
    await wrapper.get('[data-testid="sign-out"]').trigger('click')
    await flushPromises()
    expect(replace).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="account-center"] [role="alert"]').text()).toBe('退出登录失败，请重试。 请求无效。')
    signOut.mockRejectedValueOnce(new CrmApiError('INTERNAL_ERROR', 'Session store unavailable.', 'req_sign_out_msg', true))
    await wrapper.get('[data-testid="sign-out"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="account-center"] [role="alert"]').text()).toBe('退出登录失败，请重试。 Session store unavailable.')

    // Signed out: nothing of the account stays in the page, and the page leaves history for the login page.
    await wrapper.get('[data-testid="sign-out"]').trigger('click')
    await flushPromises()
    expect(signOut).toHaveBeenCalledTimes(5)
    expect(app.bootstrap).toBeNull()
    expect(replace).toHaveBeenCalledWith('/login')
    // Nothing of the account stays on the page while the login page is on its way: the route content, the bell
    // with its notifications and the account centre are gone.
    expect(wrapper.find('main.route-content').exists()).toBe(false)
    expect(wrapper.find('[data-testid="notification-button"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="account-center-button"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="session-ended"]').exists()).toBe(true)
    expect(assign).not.toHaveBeenCalled()

    // Brought back whole from the browser's back-forward cache (the next user pressing "back"), the page loads anew;
    // the tab holds no account now, so an earlier page of the tab brought back would too.
    expect(sessionStorage.getItem('rayher-crm:session-user')).toBe('')
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(reload).toHaveBeenCalledTimes(1)
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: false }))
    expect(reload).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it('does not let a bootstrap answered after the sign-out bring the account back', async () => {
    const { default: AppShell } = await import('./AppShell.vue')
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const account = (await apiClient.getBootstrap()).data
    // The page's own bootstrap read (the one its mount starts) is still out when the user signs out.
    type Booted = Awaited<ReturnType<CrmApi['getBootstrap']>>
    let answer: (value: Booted) => void = () => undefined
    const getBootstrap = vi.fn(() => new Promise<Booted>((resolve) => { answer = resolve }))
    app.activeApi = { ...apiClient, getBootstrap, signOut: vi.fn(async () => {}), listNotifications: vi.fn(async () => ({ data: { items: [] }, meta: { requestId: 'req-notifications', page: 1, pageSize: 50, total: 0 }, warnings: [] })) }
    const replace = vi.fn()
    vi.stubGlobal('location', { pathname: '/assets/rayher_crm/crm/index.html', search: '', hash: '#/dashboard', assign: vi.fn(), replace, reload: vi.fn() })
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })
    await flushPromises()
    expect(getBootstrap).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="account-center-button"]').trigger('click')
    await wrapper.get('[data-testid="sign-out"]').trigger('click')
    await flushPromises()
    expect(replace).toHaveBeenCalledTimes(1)
    expect(app.bootstrap).toBeNull()
    expect(sessionStorage.getItem('rayher-crm:session-user')).toBe('')

    // The bootstrap answered after the sign-out: the account does not come back, and the tab records none.
    answer({ data: account, meta: { requestId: 'req-late-bootstrap' }, warnings: [] } as unknown as Booted)
    await flushPromises()
    expect(app.bootstrap).toBeNull()
    expect(sessionStorage.getItem('rayher-crm:session-user')).toBe('')
    wrapper.unmount()
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it('checks a page brought back before its account was known against the tab when the account arrives', async () => {
    const { default: AppShell } = await import('./AppShell.vue')
    type Booted = Awaited<ReturnType<CrmApi['getBootstrap']>>
    const apiClient = createMockApi({ latency: 0, role: 'Sales' })
    const account = (await apiClient.getBootstrap()).data
    const shell = async () => {
      const router = createAppRouter()
      await router.push('/dashboard')
      await router.isReady()
      const pinia = createPinia()
      const app = useAppStore(pinia)
      let answer: (value: Booted) => void = () => undefined
      app.activeApi = { ...apiClient, getBootstrap: vi.fn(() => new Promise<Booted>((resolve) => { answer = resolve })), listNotifications: vi.fn(async () => ({ data: { items: [] }, meta: { requestId: 'req-notifications', page: 1, pageSize: 50, total: 0 }, warnings: [] })) }
      const reload = vi.fn()
      vi.stubGlobal('location', { pathname: '/assets/rayher_crm/crm/index.html', search: '', hash: '#/dashboard', assign: vi.fn(), replace: vi.fn(), reload })
      const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })
      await flushPromises()
      return { app, wrapper, reload, answer: (value: Booted) => answer(value) }
    }
    const booted = { data: account, meta: { requestId: 'req-bootstrap' }, warnings: [] } as unknown as Booted

    // Brought back while its bootstrap is still out: nothing to compare yet, no reload (a draft stays). The tab
    // holds the same account when the bootstrap arrives: the page is current, and records it.
    const same = await shell()
    sessionStorage.setItem('rayher-crm:session-user', account.user.id)
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    expect(same.reload).not.toHaveBeenCalled()
    same.answer(booted)
    await flushPromises()
    expect(same.reload).not.toHaveBeenCalled()
    expect(same.app.bootstrap?.user.id).toBe(account.user.id)
    expect(sessionStorage.getItem('rayher-crm:session-user')).toBe(account.user.id)
    same.wrapper.unmount()
    vi.unstubAllGlobals()

    // A later page of the tab signed out before the bootstrap arrived: the page is stale, and loads anew.
    const stale = await shell()
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }))
    sessionStorage.setItem('rayher-crm:session-user', '')
    stale.answer(booted)
    await flushPromises()
    expect(stale.reload).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem('rayher-crm:session-user')).toBe('')
    stale.wrapper.unmount()
    vi.unstubAllGlobals()

    // Loaded afresh (not brought back) in a tab whose last page was someone else's: the page's own bootstrap is
    // what the tab holds now.
    const fresh = await shell()
    sessionStorage.setItem('rayher-crm:session-user', 'someone.else@example.invalid')
    fresh.answer(booted)
    await flushPromises()
    expect(fresh.reload).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('rayher-crm:session-user')).toBe(account.user.id)
    fresh.wrapper.unmount()
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

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
