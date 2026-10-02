import { setLocale } from '@/i18n'
import { createPinia } from 'pinia'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AppShell from './AppShell.vue'
import { createAppRouter } from './router'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import { useNotificationStore } from '@/stores/notifications'

enableAutoUnmount(afterEach)

describe('AppShell', () => {
  it('uses the approved PLANCK CRM brand without the retired RAYHER label', async () => {
    const router = createAppRouter()
    router.addRoute({ path: '/app-shell-brand-test', component: { template: '<div />' } })
    await router.push('/app-shell-brand-test')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })

    const logo = wrapper.get('[data-testid="planck-logo"]')
    expect(logo.attributes('src')).toBe('/brand/planck-logo-standard.png')
    expect(logo.attributes('alt')).toBe('PLANCK CRM')
    expect(wrapper.text()).not.toContain('RAYHER')
    expect(wrapper.text()).not.toContain('客户经营系统')
    expect(wrapper.text()).not.toContain('SEMICORE')
  })

  it('does not show the MVP mock workspace environment card', async () => {
    const router = createAppRouter()
    router.addRoute({ path: '/app-shell-environment-test', component: { template: '<div />' } })
    await router.push('/app-shell-environment-test')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })

    expect(wrapper.text()).not.toContain('MVP · Mock Workspace')
    expect(wrapper.text()).not.toContain('半导体 CRM')
  })

  it('does not expose navigation before permissions are loaded', async () => {
    const router = createAppRouter()
    router.addRoute({ path: '/app-shell-permissions-test', component: { template: '<div />' } })
    await router.push('/app-shell-permissions-test')
    await router.isReady()
    const wrapper = mount(AppShell, { global: { plugins: [createPinia(), router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })

    expect(wrapper.findAll('[data-route]')).toHaveLength(0)
    wrapper.unmount()
  })

  it('navigates to MVP routes without losing the shell', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div data-testid="chart-stub" />' } } } })
    const push = vi.spyOn(router, 'push')

    await wrapper.get('[data-route="accounts"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/accounts')
    await push.mock.results[0].value
    expect(router.currentRoute.value.path).toBe('/accounts')
    expect(wrapper.find('[data-testid="app-shell"]').exists()).toBe(true)
  }, 15_000)

  it('keeps the Contact detail subpage inside the Contacts navigation section', async () => {
    const router = createAppRouter()
    await router.push('/contacts/CON-001')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/contacts/CON-001')
    expect(wrapper.get('[data-route="contacts"]').classes()).toContain('active')
    expect(wrapper.get('[data-route="contacts"]').attributes('aria-current')).toBe('page')
  })

  it('applies standard typography outside Demo routes only', async () => {
    const router = createAppRouter()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    await router.push('/accounts')
    await router.isReady()
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    expect(wrapper.get('main.route-content').classes()).toContain('standard-typography')
    for (const path of ['/demo-workflow', '/demo-requests', '/evaluations']) {
      await router.push(path)
      await flushPromises()
      expect(wrapper.get('main.route-content').classes()).not.toContain('standard-typography')
    }
  })

  it('hands a Manager who becomes Sales the information centre instead of ejecting them', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    app.bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })
    await flushPromises()

    // DashboardHomePage loads each role's page with defineAsyncComponent. Promise
    // flushing alone does not wait for those imports, especially on a busy host.
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-testid="review-page"]').exists()).toBe(true)

    await app.switchDemoIdentity('sales-user')
    await flushPromises()
    await vi.dynamicImportSettled()
    await flushPromises()

    expect(app.bootstrap?.user.role).toBe('Sales')
    expect(wrapper.find('.dashboard-page').exists()).toBe(true)
    expect(router.currentRoute.value.path).toBe('/dashboard')
    expect(wrapper.find('[data-testid="review-page"]').exists()).toBe(false)
  }, 60_000)

  it('keeps Plan closed to Sales even though the dashboard section is theirs again', async () => {
    const router = createAppRouter()
    await router.push('/plan')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Sales' }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    await vi.waitFor(() => expect(router.currentRoute.value.path).not.toBe('/plan'), { timeout: 10_000 })
    expect(wrapper.find('[data-testid="plan-page"]').exists()).toBe(false)
  }, 20_000)

  it('names the dashboard entry for the page each role actually opens', async () => {
    for (const [role, present, absent] of [['Manager', 'review', 'dashboard'], ['Sales', 'dashboard', 'review'], ['Engineer', 'dashboard', 'review']] as const) {
      const router = createAppRouter()
      await router.push('/dashboard')
      await router.isReady()
      const pinia = createPinia()
      useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role }).getBootstrap()).data
      const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { RouterView: true, CrmChart: { template: '<div />' } } } })

      expect(wrapper.find(`[data-route="${present}"]`).exists()).toBe(true)
      expect(wrapper.find(`[data-route="${absent}"]`).exists()).toBe(false)
    }
  })

  it('opens and closes the compact navigation', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const wrapper = mount(AppShell, { global: { plugins: [createPinia(), router], stubs: { CrmChart: { template: '<div data-testid="chart-stub" />' } } } })

    await wrapper.get('[data-testid="menu-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="app-sidebar"]').classes()).toContain('is-open')

    await wrapper.get('[data-testid="nav-scrim"]').trigger('click')
    expect(wrapper.get('[data-testid="app-sidebar"]').classes()).not.toContain('is-open')
  })

  it('collapses the desktop sidebar completely and restores it from the topbar', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const wrapper = mount(AppShell, { global: { plugins: [createPinia(), router], stubs: { CrmChart: { template: '<div />' } } } })

    expect(wrapper.get('[data-testid="app-shell"]').classes()).not.toContain('is-sidebar-collapsed')
    expect(wrapper.get('[data-testid="app-sidebar"]').attributes('aria-hidden')).toBe('false')
    expect(wrapper.find('[data-testid="sidebar-expand-toggle"]').exists()).toBe(false)

    await wrapper.get('[data-testid="sidebar-collapse-toggle"]').trigger('click')

    expect(wrapper.get('[data-testid="app-shell"]').classes()).toContain('is-sidebar-collapsed')
    expect(wrapper.get('[data-testid="app-sidebar"]').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('[data-testid="sidebar-collapse-toggle"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="sidebar-expand-toggle"]').attributes('aria-expanded')).toBe('false')

    await wrapper.get('[data-testid="sidebar-expand-toggle"]').trigger('click')

    expect(wrapper.get('[data-testid="app-shell"]').classes()).not.toContain('is-sidebar-collapsed')
    expect(wrapper.get('[data-testid="app-sidebar"]').attributes('aria-hidden')).toBe('false')
    expect(wrapper.find('[data-testid="sidebar-expand-toggle"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="sidebar-collapse-toggle"]').attributes('aria-expanded')).toBe('true')
  })

  it('does not render a global search box above every page', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div data-testid="chart-stub" />' } } } })

    expect(wrapper.find('[aria-label="全局客户搜索"]').exists()).toBe(false)
  })

  it('opens an empty notification center without seeded dirty messages', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    const notifications = useNotificationStore(pinia)
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })
    expect(notifications.unreadCount).toBe(0)
    await wrapper.get('[data-testid="notification-button"]').trigger('click')
    expect(wrapper.find('[data-testid="notification-center"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="notification-center"]') .text()).toContain('暂无新消息')
  })

  it('connects successful progression API calls to the mounted message center', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    app.activeApi = createMockApi({ latency: 0 })
    const notifications = useNotificationStore(pinia)
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })
    await flushPromises()

    await app.activeApi.createOpportunityAction('OPP-001', {
      title: '串联消息中心',
      owner: 'person002@crm.example.invalid',
      due: '2026-08-08',
      status: 'Open',
    })
    await flushPromises()

    expect(notifications.items[0]).toMatchObject({
      title: '新增推进 Action',
      recipient: 'Demo Staff 01',
    })
    expect(notifications.visibleItems).not.toContainEqual(notifications.items[0])
    expect(wrapper.get('[data-testid="notification-button"]').text()).toContain('3')
  })

  it('supports a container-relative embedded mode', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const wrapper = mount(AppShell, { props: { embedded: true }, global: { plugins: [createPinia(), router], stubs: { CrmChart: { template: '<div data-testid="chart-stub" />' } } } })

    expect(wrapper.get('[data-testid="app-shell"]').classes()).toContain('is-embedded')
  })

  it('shows the unified Manager permission category', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    expect(wrapper.text()).toContain('经理')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.text()).toContain('Manager')
    wrapper.unmount()
  })

  it('exposes the P1 workspace and retains the CRM foundation', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    expect(wrapper.find('[data-route="intelligence"]').exists()).toBe(false)
    const salesLinks = wrapper.get('.nav-section:nth-of-type(2)').findAll('[data-route]')
    expect(wrapper.get('.nav-section:nth-of-type(2) > p').text()).toBe('Sales 中心')
    expect(salesLinks[0].attributes('data-route')).toBe('leads')
    expect(wrapper.get('[data-route="leads"]').text()).toContain('Leads')
    expect(wrapper.get('[data-route="opportunities"]').text()).toContain('Opportunities')
    expect(wrapper.find('[data-route="leads-opportunities"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="booking"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="demo-workflow"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="demo-workflow"]').text()).toContain('Demo 档案')
    expect(wrapper.find('[data-route="demo-requests"]').text()).toContain('Demo Request')
    expect(wrapper.find('[data-route="demo-test"]').text()).toContain('Demo Test')
    expect(wrapper.find('[data-route="installed-tools"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="document-center"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="visits"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="accounts"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="contacts"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Demo 中心')
    expect(wrapper.text()).toContain('设备与资料')
    const push = vi.spyOn(router, 'push')
    await wrapper.get('[data-route="demo-workflow"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/demo-workflow')
    await push.mock.results[0].value
    expect(router.currentRoute.value.path).toBe('/demo-workflow')
  })

  it('keeps Calendar available and hides Review from Engineers', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    app.bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    await app.switchDemoIdentity('fae')
    await flushPromises()
    await vi.waitFor(() => {
      expect(app.bootstrap?.user.name).toBe('演示员工14')
      expect(router.currentRoute.value.path).toBe('/dashboard')
      expect(wrapper.find('[data-route="calendar"]').exists()).toBe(true)
      expect(wrapper.find('[data-route="review"]').exists()).toBe(false)
    })

    expect(app.bootstrap?.user.name).toBe('演示员工14')
    expect(wrapper.find('[data-route="review"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="dashboard"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="calendar"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="procedure-run"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Sales 中心')
    expect(wrapper.find('[data-route="accounts"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="contacts"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="leads"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="opportunities"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="booking"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="visits"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="demo-workflow"]').exists()).toBe(true)
    expect(router.currentRoute.value.path).toBe('/dashboard')
  })

  it('offers an equipment engineer perspective focused on demo validation', async () => {
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    app.bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    await app.switchDemoIdentity('equipment-engineer')
    await flushPromises()

    expect(app.bootstrap?.user.role).toBe('Engineer')
    expect(wrapper.text()).not.toContain('Sales 中心')
    expect(wrapper.find('[data-route="accounts"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="contacts"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="leads"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="opportunities"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="booking"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="visits"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="demo-workflow"]').exists()).toBe(true)
    expect(router.currentRoute.value.path).toBe('/dashboard')
  })

  it('shows Calendar and removes Procedure Run from the sales user perspective', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    const app = useAppStore(pinia)
    app.bootstrap = (await createMockApi({ latency: 0 }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    await app.switchDemoIdentity('sales-user')
    await flushPromises()

    expect(wrapper.find('[data-route="dashboard"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="review"]').exists()).toBe(false)
    expect(wrapper.find('[data-route="calendar"]').exists()).toBe(true)
    expect(wrapper.find('[data-route="procedure-run"]').exists()).toBe(false)
  })

  it('does not expose mock runtime notices in the application shell', async () => {
    const router = createAppRouter()
    await router.push('/dashboard')
    await router.isReady()
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await createMockApi({ latency: 0, role: 'Manager' }).getBootstrap()).data
    const wrapper = mount(AppShell, { global: { plugins: [pinia, router], stubs: { CrmChart: { template: '<div />' } } } })

    expect(wrapper.text()).not.toContain('Mock 数据')
    expect(wrapper.text()).not.toContain('Mock Demo 权限契约')
  })
})
