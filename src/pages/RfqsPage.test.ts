import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createMockApi } from '@/api/mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { setLocale } from '@/i18n'
import RfqsPage from './RfqsPage.vue'

describe('RfqsPage', () => {
  beforeEach(() => { setActivePinia(createPinia()); setLocale('zh-CN') })
  afterEach(() => setLocale('zh-CN'))

  it('localizes RFQ status options while keeping backend enum values and loaded data stable', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const read = vi.spyOn(api, 'listRfqs')
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/rfqs', name: 'rfqs', component: RfqsPage }] })
    await router.push('/rfqs'); await router.isReady()
    const wrapper = mount(RfqsPage, { props: { apiClient: api }, global: { plugins: [router] } })
    await flushPromises()
    const status = wrapper.get('.toolbar select')
    expect(status.findAll('option').map((option) => option.text())).toEqual(['全部状态', '工程师评审', '经理审批', '销售修订', '已批准'])
    setLocale('en-US')
    await flushPromises()
    expect(status.findAll('option').map((option) => option.text())).toEqual(['All statuses', 'Engineer review', 'Manager approval', 'Sales revision', 'Approved'])
    expect(status.findAll('option')[1]!.attributes('value')).toBe('Engineer Review')
    expect(read).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('lets Sales create one RFQ from the project list', async () => {
    const repository = createMemorySalesRepository()
    repository.snapshot.opportunities[0].stage = 'customer_budget_approved'
    const api = createMockApi({ latency: 0, role: 'Sales', userId: 'person002@crm.example.invalid', salesRepository: repository })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/rfqs', name: 'rfqs', component: RfqsPage },
        { path: '/rfqs/:rfqId', name: 'rfq-detail', component: { template: '<div />' } },
      ],
    })
    await router.push('/rfqs')
    await router.isReady()
    const wrapper = mount(RfqsPage, { props: { apiClient: api }, global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="new-rfq"]').exists()).toBe(true)
    await wrapper.get('[data-testid="new-rfq"]').trigger('click')
    await flushPromises()
    const selects = wrapper.findAll('.create-form select')
    const opportunityOption = selects[0].findAll('option').find((option) => option.attributes('value'))!
    await selects[0].setValue(opportunityOption.attributes('value'))
    await selects[1].setValue('person077@crm.example.invalid')
    const fileInput = wrapper.get('.create-form input[type="file"]')
    const file = new File(['%PDF-1.7 mock'], 'customer-rfq.pdf', { type: 'application/pdf' })
    Object.defineProperty(fileInput.element, 'files', { value: [file], configurable: true })
    await fileInput.trigger('change')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('rfq-detail')
    const result = await api.listRfqs({ page: 1, pageSize: 50 })
    expect(result.data.items).toHaveLength(1)
    expect(result.data.items[0]).toMatchObject({ status: 'Engineer Review', fileName: 'customer-rfq.pdf' })
  })

  it('asks for confirmation before uploading a TipRay-protected file', async () => {
    const repository = createMemorySalesRepository()
    repository.snapshot.opportunities[0].stage = 'customer_budget_approved'
    const api = createMockApi({ latency: 0, role: 'Sales', userId: 'person002@crm.example.invalid', salesRepository: repository })
    const createSpy = vi.spyOn(api, 'createRfq')
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/rfqs', name: 'rfqs', component: RfqsPage },
        { path: '/rfqs/:rfqId', name: 'rfq-detail', component: { template: '<div />' } },
      ],
    })
    await router.push('/rfqs')
    await router.isReady()
    const wrapper = mount(RfqsPage, { props: { apiClient: api }, global: { plugins: [router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-rfq"]').trigger('click')
    await flushPromises()
    const selects = wrapper.findAll('.create-form select')
    const opportunityOption = selects[0].findAll('option').find((option) => option.attributes('value'))!
    await selects[0].setValue(opportunityOption.attributes('value'))
    await selects[1].setValue('person077@crm.example.invalid')
    const fileInput = wrapper.get('.create-form input[type="file"]')
    const protectedFile = new File(['%TSD-Header-###%encrypted'], 'protected-rfq.pdf', { type: 'application/pdf' })
    Object.defineProperty(fileInput.element, 'files', { value: [protectedFile], configurable: true })
    await fileInput.trigger('change')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledWith('天锐绿盾加密文件无法生成在线预览，但下载后仍可正常浏览，确定上传吗？')
    expect(createSpy).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('rfqs')

    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(createSpy).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.name).toBe('rfq-detail')
    confirmSpy.mockRestore()
  })

  it('sends status and owner filters to the paginated RFQ query', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const listRfqs = vi.spyOn(api, 'listRfqs')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/rfqs', name: 'rfqs', component: RfqsPage },
        { path: '/rfqs/:rfqId', name: 'rfq-detail', component: { template: '<div />' } },
      ],
    })
    await router.push('/rfqs')
    await router.isReady()
    const wrapper = mount(RfqsPage, { props: { apiClient: api }, global: { plugins: [router] } })
    await flushPromises()

    await wrapper.get('[aria-label="RFQ 状态"]').setValue('Approved')
    await wrapper.get('[aria-label="RFQ 负责人"]').setValue('person002@crm.example.invalid')
    await flushPromises()

    expect(listRfqs).toHaveBeenLastCalledWith({
      opportunityId: '', status: 'Approved', owner: 'person002@crm.example.invalid', page: 1, pageSize: 50,
    })
  })
})
