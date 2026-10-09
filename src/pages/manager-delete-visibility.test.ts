import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'
import AccountsPage from './AccountsPage.vue'
import OpportunityDetailPage from './OpportunityDetailPage.vue'
import VisitsPage from './VisitsPage.vue'

async function context(role: UserRole, path: string) {
  const api = createMockApi({ latency: 0, role, userName: role === 'Sales' ? 'Demo Staff 01' : '演示员工24' })
  api.listQuotations = async () => ({ data: { items: [] }, warnings: [] })
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/accounts', name: 'accounts', component: { template: '<div />' } },
      { path: '/accounts/:accountId', name: 'account-detail', component: { template: '<div />' } },
      { path: '/leads', name: 'leads', component: { template: '<div />' } },
      { path: '/leads/:leadId', name: 'lead-detail', component: { template: '<div />' } },
      { path: '/opportunities', name: 'opportunities', component: { template: '<div />' } },
      { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: { template: '<div />' } },
      { path: '/opportunities/:opportunityId/documents', name: 'opportunity-documents', component: { template: '<div />' } },
      { path: '/booking', name: 'booking', component: { template: '<div />' } },
      { path: '/booking/:bookingId', name: 'booking-detail', component: { template: '<div />' } },
      { path: '/visits', name: 'visits', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
      { path: '/installed-tools', name: 'installed-tools', component: { template: '<div />' } },
      { path: '/quotations', name: 'quotations', component: { template: '<div />' } },
      { path: '/quotations/:quotationId', name: 'quotation-detail', component: { template: '<div />' } },
      { path: '/rfqs', name: 'rfqs', component: { template: '<div />' } },
      { path: '/rfqs/:rfqId', name: 'rfq-detail', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  return { api, pinia, router }
}

afterEach(() => vi.restoreAllMocks())

describe('Manager-only Sales record deletion', () => {
  it('shows Account deletion only to Manager and refreshes the list after deletion', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const manager = await context('Manager', '/accounts')
    const wrapper = mount(AccountsPage, { props: { apiClient: manager.api }, global: { plugins: [manager.pinia, manager.router] } })
    await flushPromises()
    const button = wrapper.get('[data-delete-account]')
    const id = button.attributes('data-delete-account')
    await button.trigger('click'); await flushPromises()
    expect(wrapper.find(`[data-account-id="${id}"]`).exists()).toBe(false)

    const sales = await context('Sales', '/accounts')
    const salesWrapper = mount(AccountsPage, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()
    expect(salesWrapper.find('[data-delete-account]').exists()).toBe(false)
  })

  it.each([
    ['Opportunity', OpportunityDetailPage, 'deleteStrategyOpportunity', 'data-delete-opportunity', async (api: ReturnType<typeof createMockApi>): Promise<string> => (await api.listStrategyOpportunities({ pageSize: 1 })).data.items[0].id, (id: string) => `/opportunities/${id}`],
  ] as const)('shows %s deletion only to Manager and invokes the API', async (_label, component, method, attribute, findId, pathFor) => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const manager = await context('Manager', '/')
    const id = await findId(manager.api)
    await manager.router.push(pathFor(id))
    const deleteSpy = vi.spyOn(manager.api, method)
    const wrapper = mount(component, { props: { apiClient: manager.api }, global: { plugins: [manager.pinia, manager.router] } })
    await flushPromises()
    await wrapper.get(`[${attribute}]`).trigger('click'); await flushPromises()
    expect(deleteSpy).toHaveBeenCalledWith(id)

    const sales = await context('Sales', '/')
    const salesId = await findId(sales.api)
    await sales.router.push(pathFor(salesId))
    const salesWrapper = mount(component, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()
    expect(salesWrapper.find(`[${attribute}]`).exists()).toBe(false)
  })


  it.each([
    ['Account', AccountsPage, 'deleteAccount', 'data-delete-account', 'data-account-id', async (api: ReturnType<typeof createMockApi>) => (await api.listAccounts({ pageSize: 1 })).data.items[0].id, (_id: string): string => '/accounts'],
  ] as const)('keeps the %s row and exposes the Request ID when deletion fails', async (_label, component, method, buttonAttribute, rowAttribute, findId, pathFor) => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const manager = await context('Manager', '/')
    const id = await findId(manager.api)
    await manager.router.push(pathFor(id))
    const failure = vi.fn().mockRejectedValue(new CrmApiError('CONFLICT', 'Record is still in use', 'req-delete-row'))
    Object.assign(manager.api, { [method]: failure })
    const wrapper = mount(component, { props: { apiClient: manager.api }, global: { plugins: [manager.pinia, manager.router] } })
    await flushPromises()

    const button = wrapper.get(`[${buttonAttribute}="${id}"]`)
    await button.trigger('click')
    await flushPromises()

    expect(failure).toHaveBeenCalledWith(id)
    expect(wrapper.find(`[${rowAttribute}="${id}"]`).exists()).toBe(true)
    expect(wrapper.get('[data-delete-error]').text()).toContain('Record is still in use')
    expect(wrapper.get('[data-delete-error]').text()).toContain('req-delete-row')
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it.each([
    ['Opportunity', OpportunityDetailPage, 'deleteStrategyOpportunity', 'data-delete-opportunity', async (api: ReturnType<typeof createMockApi>) => (await api.listStrategyOpportunities({ pageSize: 1 })).data.items[0].id, (id: string) => `/opportunities/${id}`],
  ] as const)('keeps the %s detail and route when deletion fails', async (_label, component, method, attribute, findId, pathFor) => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const manager = await context('Manager', '/')
    const id = await findId(manager.api)
    const path = pathFor(id)
    await manager.router.push(path)
    const failure = vi.fn().mockRejectedValue(new CrmApiError('CONFLICT', 'Record is still in use', 'req-delete-detail'))
    Object.assign(manager.api, { [method]: failure })
    const wrapper = mount(component, { props: { apiClient: manager.api }, global: { plugins: [manager.pinia, manager.router] } })
    await flushPromises()

    const button = wrapper.get(`[${attribute}]`)
    await button.trigger('click')
    await flushPromises()

    expect(failure).toHaveBeenCalledWith(id)
    expect(manager.router.currentRoute.value.fullPath).toBe(path)
    expect(wrapper.find(`[${attribute}]`).exists()).toBe(true)
    expect(wrapper.get('[data-delete-error]').text()).toContain('Record is still in use')
    expect(wrapper.get('[data-delete-error]').text()).toContain('req-delete-detail')
    expect(button.attributes('disabled')).toBeUndefined()
  })
})
