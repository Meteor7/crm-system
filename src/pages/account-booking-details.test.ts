import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import type { CrmApi } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { useAppStore } from '@/stores/app'
import AccountDetailPage from './AccountDetailPage.vue'
import BookingDetailPage from './BookingDetailPage.vue'

async function mountRoute(
  path: string,
  component: typeof AccountDetailPage | typeof BookingDetailPage,
  apiClient: CrmApi = createMockApi({ latency: 0 }),
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/accounts', name: 'accounts', component: { template: '<div />' } },
      { path: '/accounts/:accountId', name: 'account-detail', component },
      { path: '/booking', name: 'booking', component: { template: '<div />' } },
      { path: '/booking/:bookingId', name: 'booking-detail', component },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
      { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: { template: '<div />' } },
      { path: '/installed-tools', name: 'installed-tools', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    props: { apiClient },
    global: { plugins: [createPinia(), router, ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

// Mounts the BKG-001 detail with the viewer's bootstrap, so role-gated actions render.
async function mountBookingAs(apiClient: CrmApi) {
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await apiClient.getBootstrap()).data
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/booking', name: 'booking', component: { template: '<div />' } },
      { path: '/booking/:bookingId', name: 'booking-detail', component: BookingDetailPage },
      { path: '/accounts/:accountId', name: 'account-detail', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
      { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: { template: '<div />' } },
      { path: '/installed-tools', name: 'installed-tools', component: { template: '<div />' } },
    ],
  })
  await router.push('/booking/BKG-001')
  await router.isReady()
  const wrapper = mount(BookingDetailPage, { props: { apiClient }, global: { plugins: [pinia, router, ElementPlus] } })
  await flushPromises()
  return wrapper
}

describe('Account and Booking details', () => {
  it('moves Account 360 into the Account detail route and shows related equipment', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const accountDetail = await apiClient.getAccount360('ACC-002')
    const expectedModified = accountDetail.data.account.modified
    expect(expectedModified).toBeTruthy()
    accountDetail.data.account.modified = expectedModified
    vi.spyOn(apiClient, 'getAccount360').mockResolvedValueOnce(accountDetail)
    const updateAccount = vi.spyOn(apiClient, 'updateAccount')
    const wrapper = await mountRoute('/accounts/ACC-002', AccountDetailPage, apiClient)

    expect(wrapper.get('[data-testid="account-360"]').text()).toContain('示例企业044有限公司')
    expect(wrapper.text()).not.toContain('OPEN PIPELINE')
    expect(wrapper.text()).toContain('设备关联')
    expect(wrapper.findAll('[data-account-tool]')).toHaveLength(1)
    expect(wrapper.text()).toContain('AX-9000')
    expect(wrapper.get('[data-testid="edit-account"]').text()).toContain('修改档案')

    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('修改客户档案')
    await wrapper.get('input[aria-label="客户全称"]').setValue('示例企业044科技（更新）有限责任公司')
    await wrapper.get('[aria-label="业务领域"]').setValue('__custom_account_segment__')
    await wrapper.get('[aria-label="业务领域自定义"]').setValue('Power Semiconductor')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    expect(updateAccount).toHaveBeenCalledWith(
      'ACC-002',
      expect.objectContaining({ segment: 'Power Semiconductor' }),
      expectedModified,
    )
    await vi.waitFor(() => expect(wrapper.get('[data-testid="account-360"]').text()).toContain('示例企业044科技（更新）有限责任公司'))
  })

  it('loads every installed-tool page for the routed Account instead of the global first 200', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const seed = (await apiClient.listInstalledTools({ page: 1, pageSize: 1 })).data.items[0]
    const accountId = seed.accountId
    const tools = Array.from({ length: 201 }, (_, index) => ({
      ...seed, id: `TOOL-PAGED-${index + 1}`, serial: `SERIAL-PAGED-${index + 1}`,
    }))
    const listInstalledTools = vi.spyOn(apiClient, 'listInstalledTools').mockImplementation(async (query = {}) => {
      const page = query.page ?? 1
      const pageSize = query.pageSize ?? 20
      return {
        data: { items: tools.slice((page - 1) * pageSize, page * pageSize) },
        meta: { requestId: `req-tools-${page}`, total: tools.length, page, pageSize }, warnings: [],
      }
    })

    const wrapper = await mountRoute(`/accounts/${accountId}`, AccountDetailPage, apiClient)

    expect(listInstalledTools).toHaveBeenNthCalledWith(1, { accountId, page: 1, pageSize: 200 })
    expect(listInstalledTools).toHaveBeenNthCalledWith(2, { accountId, page: 2, pageSize: 200 })
    expect(wrapper.findAll('[data-account-tool]')).toHaveLength(201)
    expect(wrapper.text()).toContain('SERIAL-PAGED-201')
  })

  it('shows Booking information and its business links on a dedicated route', async () => {
    const wrapper = await mountRoute('/booking/BKG-001', BookingDetailPage)

    expect(wrapper.get('h1').text()).toContain('FastScan 1200')
    expect(wrapper.text()).toContain('BKG-001')
    expect(wrapper.text()).toContain('示例企业027有限公司')
    expect(wrapper.text()).toContain('OPP-006')
    expect(wrapper.text()).toContain('客户 DDL')
  })

  it('lets a Manager fill in or correct the actual PO date and shows where it came from', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-20' })
    const setActualPoDate = vi.spyOn(apiClient, 'setBookingActualPoDate')
    const wrapper = await mountBookingAs(apiClient)

    expect(wrapper.get('[data-testid="booking-actual-po-date"]').text()).toContain('确认 PO 时填写')
    await wrapper.get('[data-testid="set-actual-po-date"]').trigger('click')
    await wrapper.get('[aria-label="实际 PO 日期"]').setValue('2026-07-01')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-field-error="actualPoDate"]').text()).toBe('更正已有日期时必须填写原因')
    expect(setActualPoDate).not.toHaveBeenCalled()

    await wrapper.get('[aria-label="更正原因"]').setValue('The PO scan is dated 1 July')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(setActualPoDate).toHaveBeenCalledWith('BKG-001', { actualPoDate: '2026-07-01', reason: 'The PO scan is dated 1 July' }, undefined)
    expect(wrapper.get('[data-testid="booking-actual-po-date"]').text()).toContain('经理补录 / 更正')
    expect(wrapper.get('[data-testid="booking-actual-po-date-note"]').text()).toBe('The PO scan is dated 1 July')
  })

  it('lets a Manager fill in the amount in CNY of a foreign-currency order', async () => {
    const cached = structuredClone(createMemorySalesRepository().snapshot)
    Object.assign(cached.bookings.find((item) => item.id === 'BKG-001')!, { currency: 'USD', amount: '2650000.00', amountCny: '' })
    const apiClient = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-20', salesRepository: createMemorySalesRepository(cached) })
    const setAmountCny = vi.spyOn(apiClient, 'setBookingAmountCny')
    const wrapper = await mountBookingAs(apiClient)

    expect(wrapper.get('[data-testid="booking-amount-cny"]').text()).toBe('人民币金额待补填')
    await wrapper.get('[data-testid="set-amount-cny"]').trigger('click')
    await wrapper.get('[aria-label="人民币金额"]').setValue('18800000')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(setAmountCny).toHaveBeenCalledWith('BKG-001', { amountCny: '18800000.00' }, undefined)
    expect(wrapper.get('[data-testid="booking-amount-cny"]').text()).toBe('人民币金额 CNY 18,800,000.00')
  })

  it('shows no separate CNY amount on a CNY order', async () => {
    const wrapper = await mountBookingAs(createMockApi({ latency: 0, role: 'Manager' }))

    expect(wrapper.find('[data-testid="booking-amount-cny"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="set-amount-cny"]').exists()).toBe(false)
  })

  it('edits a Booking from its detail page with the same editor as the list', async () => {
    const apiClient = createMockApi({ latency: 0, role: 'Manager', today: '2026-07-20' })
    const updateBooking = vi.spyOn(apiClient, 'updateBooking')
    const wrapper = await mountBookingAs(apiClient)

    await wrapper.get('[data-testid="edit-booking"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('编辑 Booking')
    await wrapper.get('[role="dialog"] [aria-label="备注"]').setValue('交付窗口改到九月第一周')
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    expect(updateBooking).toHaveBeenCalledWith('BKG-001', expect.objectContaining({ note: '交付窗口改到九月第一周' }), undefined)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('交付窗口改到九月第一周')
  })

  it('offers no Booking edit on a completed order', async () => {
    const cached = structuredClone(createMemorySalesRepository().snapshot)
    cached.bookings.find((item) => item.id === 'BKG-001')!.status = 'Completed'
    const wrapper = await mountBookingAs(createMockApi({ latency: 0, role: 'Manager', salesRepository: createMemorySalesRepository(cached) }))

    expect(wrapper.find('[data-testid="edit-booking"]').exists()).toBe(false)
  })

  it('keeps the actual PO date correction away from Sales', async () => {
    const wrapper = await mountBookingAs(createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 02' }))

    expect(wrapper.get('[data-testid="booking-actual-po-date"]').text()).toContain('确认 PO 时填写')
    expect(wrapper.find('[data-testid="set-actual-po-date"]').exists()).toBe(false)
  })

  it('loads a converted Booking installed tool by exact id beyond the first list page', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const pipeline = await apiClient.listPipeline({})
    const toolSummary = (await apiClient.listInstalledTools({ page: 1, pageSize: 1 })).data.items[0]
    const tool = await apiClient.getInstalledTool(toolSummary.id)
    pipeline.data.bookings[0]!.installedToolId = tool.data.id
    vi.spyOn(apiClient, 'listPipeline').mockResolvedValue(pipeline)
    vi.spyOn(apiClient, 'listInstalledTools').mockResolvedValue({
      data: { items: [] }, meta: { requestId: 'req-tools-page', total: 201, page: 1, pageSize: 200 }, warnings: [],
    })
    const getInstalledTool = vi.spyOn(apiClient, 'getInstalledTool').mockResolvedValue(tool)

    const wrapper = await mountRoute('/booking/BKG-001', BookingDetailPage, apiClient)

    expect(getInstalledTool).toHaveBeenCalledWith(tool.data.id)
    expect(wrapper.find(`[data-booking-tool="${tool.data.id}"]`).exists()).toBe(true)
    expect(wrapper.text()).toContain(tool.data.serial)
    expect(wrapper.text()).not.toContain('尚未转入 Installed Tool')
  })

  it('retries an Account update with the latest modified version after a Site failure', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const accountDetail = await apiClient.getAccount360('ACC-002')
    const initialModified = accountDetail.data.account.modified
    expect(initialModified).toBeTruthy()
    let firstUpdatedModified: string | undefined
    vi.spyOn(apiClient, 'getAccount360').mockResolvedValueOnce(accountDetail)
    const originalUpdateAccount = apiClient.updateAccount.bind(apiClient)
    const updateAccount = vi.spyOn(apiClient, 'updateAccount').mockImplementation(async (...args) => {
      const result = await originalUpdateAccount(...args)
      if (!firstUpdatedModified) firstUpdatedModified = result.data.modified
      return result
    })
    const originalCreateSite = apiClient.createAccountSite.bind(apiClient)
    vi.spyOn(apiClient, 'createAccountSite')
      .mockRejectedValueOnce(new Error('Site write failed'))
      .mockImplementation(originalCreateSite)
    const wrapper = await mountRoute('/accounts/ACC-002', AccountDetailPage, apiClient)

    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await wrapper.get('[data-add-site]').trigger('click')
    const siteInputs = wrapper.get('.site-draft:last-of-type').findAll('input')
    await siteInputs[0]!.setValue('Retry Site')
    await siteInputs[2]!.setValue('Wafer Fab')
    await siteInputs[3]!.setValue('28nm')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(updateAccount).toHaveBeenNthCalledWith(1, 'ACC-002', expect.any(Object), initialModified)
    expect(updateAccount).toHaveBeenNthCalledWith(2, 'ACC-002', expect.any(Object), firstUpdatedModified)
  })

  it('does not recreate a Site that succeeded before a later Site failed', async () => {
    const apiClient = createMockApi({ latency: 0 })
    const accountDetail = await apiClient.getAccount360('ACC-002')
    expect(accountDetail.data.account.modified).toBeTruthy()
    vi.spyOn(apiClient, 'getAccount360').mockResolvedValueOnce(accountDetail)
    const originalUpdateAccount = apiClient.updateAccount.bind(apiClient)
    vi.spyOn(apiClient, 'updateAccount').mockImplementation(async (...args) => {
      return originalUpdateAccount(...args)
    })
    const originalCreateSite = apiClient.createAccountSite.bind(apiClient)
    const createAccountSite = vi.spyOn(apiClient, 'createAccountSite')
      .mockImplementationOnce(originalCreateSite)
      .mockRejectedValueOnce(new Error('Second Site write failed'))
      .mockImplementation(originalCreateSite)
    const wrapper = await mountRoute('/accounts/ACC-002', AccountDetailPage, apiClient)

    await wrapper.get('[data-testid="edit-account"]').trigger('click')
    await wrapper.get('[data-add-site]').trigger('click')
    await wrapper.get('[data-add-site]').trigger('click')
    const siteDrafts = wrapper.findAll('.site-draft')
    const firstInputs = siteDrafts.at(-2)!.findAll('input')
    const secondInputs = siteDrafts.at(-1)!.findAll('input')
    await firstInputs[0]!.setValue('Saved Site')
    await firstInputs[2]!.setValue('Wafer Fab')
    await firstInputs[3]!.setValue('28nm')
    await secondInputs[0]!.setValue('Pending Site')
    await secondInputs[2]!.setValue('Packaging')
    await secondInputs[3]!.setValue('CoWoS')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(createAccountSite).toHaveBeenCalledTimes(3)
    expect(createAccountSite.mock.calls.map((call) => call[1].name)).toEqual([
      'Saved Site',
      'Pending Site',
      'Pending Site',
    ])
  })
})
