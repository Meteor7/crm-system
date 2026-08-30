import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import AccountsPage from './AccountsPage.vue'
import ContractsPage from './ContractsPage.vue'

describe('paginated pages', () => {
  it('reloads Contracts only once when a filter changes', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const listContracts = vi.spyOn(api, 'listContracts')
    const wrapper = mount(ContractsPage, { props: { apiClient: api }, global: { plugins: [createPinia()] } })
    await flushPromises()
    listContracts.mockClear()

    await wrapper.get('[aria-label="合同状态"]').setValue('Active')
    await flushPromises()

    expect(listContracts).toHaveBeenCalledTimes(1)
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
})
