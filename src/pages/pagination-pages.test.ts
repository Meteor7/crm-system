import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import { ClientRequestError } from '@/api/request-state'
import { useAppStore } from '@/stores/app'
import AccountsPage from './AccountsPage.vue'
import ContractsPage from './ContractsPage.vue'
import { localeMessage, setLocale } from '@/i18n'

describe('paginated pages', () => {
  afterEach(() => setLocale('zh-CN'))

  it('reloads Contracts only once when a filter changes', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const listContracts = vi.spyOn(api, 'listContracts')
    const wrapper = mount(ContractsPage, { props: { apiClient: api }, global: { plugins: [createPinia()] } })
    await flushPromises()
    listContracts.mockClear()

    await wrapper.get('[aria-label="演示员工116状态"]').setValue('Active')
    await flushPromises()

    expect(listContracts).toHaveBeenCalledTimes(1)
  })

  it('localizes cached contract risk and enum displays without refetching', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const listContracts = vi.spyOn(api, 'listContracts')
    const wrapper = mount(ContractsPage, { props: { apiClient: api }, global: { plugins: [createPinia()] } })
    await flushPromises()
    expect(wrapper.get('.contract-table').text()).toContain('服务演示员工116')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.get('.contract-table').text()).toContain('Service Contract')
    expect(wrapper.get('.contract-table').text()).toContain('Normal')
    expect(listContracts).toHaveBeenCalledTimes(1)
    setLocale('zh-CN')
    wrapper.unmount()
  })

  it('keeps a cached client error reactive when the contract page language changes', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const listContracts = vi.spyOn(api, 'listContracts').mockRejectedValue(new ClientRequestError(
      'BACKEND_NOT_CONNECTED',
      localeMessage('Contract service is unavailable.', '演示员工116服务暂时不可用。'),
      'contract-client-error',
    ))
    const wrapper = mount(ContractsPage, { props: { apiClient: api }, global: { plugins: [createPinia()] } })
    await flushPromises()

    expect(wrapper.text()).toContain('演示员工116服务暂时不可用。')
    setLocale('en-US')
    await flushPromises()
    expect(wrapper.text()).toContain('Contract service is unavailable.')
    expect(listContracts).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('loads the next Accounts page using response total metadata', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const source = (await api.listAccounts({ page: 1, pageSize: 10 })).data.items
    const listAccounts = vi.fn(async (query) => {
      const page = Number(query.page ?? 1)
      return {
        data: { items: [{ ...source[0]!, id: `ACC-PAGE-${page}`, shortName: `Page ${page}` }] },
        meta: { requestId: `req_page_${page}`, page, pageSize: 10, total: 45 },
        warnings: [],
      }
    })
    api.listAccounts = listAccounts
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()

    const wrapper = mount(AccountsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('第 1 / 5 页')
    expect(wrapper.text()).toContain('Page 1')

    await wrapper.get('[data-page-next]').trigger('click')
    await flushPromises()
    expect(listAccounts).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, pageSize: 10 }))
    expect(wrapper.text()).toContain('Page 2')
    expect(router.currentRoute.value.query).toMatchObject({ page: '2', pageSize: '10' })
  })

  it('says how many Opportunity amounts an Account pipeline total leaves out', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const [source] = (await api.listAccounts({ page: 1, pageSize: 10 })).data.items
    vi.spyOn(api, 'listAccounts').mockResolvedValue({
      data: { items: [
        { ...source!, id: 'ACC-PARTIAL', pipelineAmount: 100, pipelineMissingAmountCount: 1 },
        { ...source!, id: 'ACC-COMPLETE', pipelineAmount: 200, pipelineMissingAmountCount: 0 },
        { ...source!, id: 'ACC-UNKNOWN', pipelineAmount: 0, pipelineMissingAmountCount: 2 },
        { ...source!, id: 'ACC-ZERO', pipelineAmount: 0, pipelineMissingAmountCount: 0 },
      ] },
      meta: { requestId: 'req_pipeline_missing', page: 1, pageSize: 10, total: 4 },
      warnings: [],
    })
    const pinia = createPinia()
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter()
    await router.push('/accounts')
    await router.isReady()

    const wrapper = mount(AccountsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(wrapper.get('[data-account-pipeline-missing="ACC-PARTIAL"]').text()).toBe('1 条未填金额')
    expect(wrapper.find('[data-account-pipeline-missing="ACC-COMPLETE"]').exists()).toBe(false)
    // Nothing known yet reads as insufficient data, not as a ¥0 pipeline; a real zero stays ¥0.
    expect(wrapper.get('[data-account-pipeline="ACC-UNKNOWN"]').text()).toBe('数据不足')
    expect(wrapper.get('[data-account-pipeline-missing="ACC-UNKNOWN"]').text()).toBe('2 条未填金额')
    expect(wrapper.get('[data-account-pipeline="ACC-ZERO"]').text()).toBe('¥0')
    expect(wrapper.get('[data-account-pipeline="ACC-PARTIAL"]').text()).toBe('¥100')
  })
})
