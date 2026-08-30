import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { CrmApi } from '@/api'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import QuotationsPage from './QuotationsPage.vue'

function quotationApi(): CrmApi {
  const base = {} as CrmApi
  return {
    ...base,
    getBootstrap: vi.fn(async () => ({ data: { user: { id: 'sales@example.com', name: 'Sales', initials: 'S', role: 'Sales', team: 'Sales' }, capabilities: ['quotation:view', 'quotation:write', 'quotation:submit'], today: '2026-08-10', environment: 'Frappe' }, warnings: [] })),
    listQuotations: vi.fn(async () => ({ data: { items: [{ id: 'CRM-QTN-00001', refNo: 'PK20260810-A1', quotationType: 'Device', opportunityId: 'OPP-001', opportunityTitle: 'AOI Project', accountId: 'ACC-001', accountName: 'Planck Fab', owner: 'sales@example.com', status: 'Draft', approvalStatus: 'Not Submitted', latestVersion: 1, currentVersionId: 'CRM-QTV-00001', currentPublishedVersionId: '', modified: '2026-08-10T10:00:00+08:00' }] }, meta: { requestId: 'q', total: 1 }, warnings: [] })),
    createQuotation: vi.fn(async () => ({ data: { quotation: { id: 'CRM-QTN-00002' } }, warnings: [] })),
    listStrategyOpportunities: vi.fn(async () => ({ data: { items: [
      { id: 'OPP-001', title: 'AOI Project', account: 'Planck Fab' },
      { id: 'OPP-002', title: 'Metrology Project', account: 'Second Fab' },
    ] }, warnings: [] })),
    listAccounts: vi.fn(async () => ({ data: { items: [{ id: 'ACC-001', name: 'Planck Fab' }] }, meta: { requestId: 'a', total: 1 }, warnings: [] })),
  } as unknown as CrmApi
}

describe('QuotationsPage', () => {
  it('reuses the CRM table with four key columns and row navigation', async () => {
    const api = quotationApi(); const pinia = createPinia(); useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter(); await router.push('/quotations'); await router.isReady()
    const wrapper = mount(QuotationsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    const headers = wrapper.findAll('thead th').map((node) => node.text())
    expect(headers).toHaveLength(6)
    expect([headers[0], headers[1], headers[2], headers[4], headers[5]]).toEqual(['Name', 'Type', 'Opportunity', 'Status', 'Approval'])
    expect(wrapper.text()).toContain('PK20260810-A1')
    expect(wrapper.text()).toContain('Planck Fab')
    expect(wrapper.get('[data-quotation-id="CRM-QTN-00001"]').classes()).toContain('record-name-link')
    expect(wrapper.find('.quotation-link__mark').exists()).toBe(true)
    const push = vi.spyOn(router, 'push')
    await wrapper.get('[data-quotation-id="CRM-QTN-00001"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalled()
    await push.mock.results[0]!.value
    expect(router.currentRoute.value.path).toBe('/quotations/CRM-QTN-00001')
  })

  it('creates an Others service quotation directly for an account', async () => {
    const api = quotationApi(); const pinia = createPinia(); useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter(); await router.push('/quotations'); await router.isReady()
    const wrapper = mount(QuotationsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    await wrapper.get('[data-testid="new-quotation"]').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="quotation-type"]').setValue('Service')
    await wrapper.get('[data-testid="quotation-source"]').setValue('Others')
    await wrapper.get('[data-testid="quotation-account"]').setValue('ACC-001')
    await wrapper.get('[data-modal-submit]').trigger('submit'); await flushPromises()
    expect(api.createQuotation).toHaveBeenCalledWith({ quotationType: 'Service', accountId: 'ACC-001' })
  })

  it('removes search and manual ref number and offers only unquoted opportunities', async () => {
    const api = quotationApi();
    vi.mocked(api.listStrategyOpportunities).mockImplementation(async (query) => ({ data: { items: query?.page === 2 ? [{ id: 'OPP-002', title: 'Metrology Project', account: 'Second Fab' }] : [{ id: 'OPP-001', title: 'AOI Project', account: 'Planck Fab' }] } as never, meta: { requestId: 'o', total: 2 }, warnings: [] }))
    const pinia = createPinia(); useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter(); await router.push('/quotations'); await router.isReady()
    const wrapper = mount(QuotationsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(wrapper.find('input[type="search"]').exists()).toBe(false)
    expect(vi.mocked(api.listQuotations).mock.calls[0]?.[0]).toEqual({ status: 'All', approvalStatus: 'All', page: 1, pageSize: 10 })
    await wrapper.get('[data-testid="new-quotation"]').trigger('click')
    await flushPromises()
    expect(vi.mocked(api.listQuotations).mock.calls[1]?.[0]).toEqual({ page: 1, pageSize: 200 })
    expect(api.listStrategyOpportunities).toHaveBeenNthCalledWith(1, { page: 1, pageSize: 200 })
    expect(api.listStrategyOpportunities).toHaveBeenNthCalledWith(2, { page: 2, pageSize: 200 })
    const values = wrapper.findAll('select[required] option').map((node) => node.attributes('value'))
    expect(values).toEqual(['', 'OPP-002'])
    expect(wrapper.find('input').exists()).toBe(false)
    await wrapper.get('select[required]').setValue('OPP-002')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(api.createQuotation).toHaveBeenCalledWith({ opportunityId: 'OPP-002' })
  })

  it('navigates quotation result pages instead of truncating the first page', async () => {
    const api = quotationApi()
    vi.mocked(api.listQuotations).mockImplementation(async (query) => {
      const row = { id: query?.page === 2 ? 'CRM-QTN-00051' : 'CRM-QTN-00001', refNo: query?.page === 2 ? 'PK20260810-A51' : 'PK20260810-A1', quotationType: 'Device', opportunityId: 'OPP-001', opportunityTitle: 'AOI Project', accountId: 'ACC-001', accountName: 'Planck Fab', owner: 'sales@example.com', status: 'Draft', approvalStatus: 'Not Submitted', latestVersion: 1, currentVersionId: 'CRM-QTV-00001', currentPublishedVersionId: '', modified: '2026-08-10T10:00:00+08:00' } as const
      return { data: { items: [row] }, meta: { requestId: 'q', total: 51 }, warnings: [] }
    })
    const pinia = createPinia(); useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter(); await router.push('/quotations'); await router.isReady()
    const wrapper = mount(QuotationsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    await wrapper.get('[data-testid="quotation-next"]').trigger('click'); await flushPromises()
    expect(api.listQuotations).toHaveBeenLastCalledWith({ status: 'All', approvalStatus: 'All', page: 2, pageSize: 10 })
    expect(wrapper.text()).toContain('PK20260810-A51')
    expect(wrapper.get('[data-testid="quotation-next"]').classes()).toContain('secondary-button')
  })
})
