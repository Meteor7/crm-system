import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import type { CrmApi } from '@/api'
import { useAppStore } from '@/stores/app'
import BookingPage from './BookingPage.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

async function context(api: CrmApi = createMockApi({ latency: 0 })) {
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/booking', name: 'booking', component: BookingPage },
      { path: '/booking/:bookingId', name: 'booking-detail', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
      { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: { template: '<div />' } },
    ],
  })
  await router.push('/booking')
  return { api, pinia, router }
}

describe('Booking page', () => {
  it('renders as an independent module with existing Booking records', async () => {
    const { api, pinia, router } = await context()
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('Booking')
    expect(wrapper.find('[data-testid="booking-search"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-booking-id]')).toHaveLength(3)
    expect(wrapper.get('[data-booking-source="OPP-006"]').attributes('href')).toBe('/opportunities/OPP-006')
    expect(wrapper.get('[data-booking-source="OPP-008"]').attributes('href')).toBe('/opportunities/OPP-008')
    expect(wrapper.text()).toContain('FastScan 1200')
    expect(wrapper.text()).toContain('Service Expansion Kit')
    expect(wrapper.get('select[aria-label="来源"]').text()).toContain('Opportunity')
    expect(wrapper.get('select[aria-label="来源"]').text()).toContain('客户增购')
  })

  it('lists confirmed Bookings still missing their actual PO date', async () => {
    const { api, pinia, router } = await context()
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('[data-booking-actual-po-date="BKG-002"]').text()).toBe('实际 PO 日期 待补录')
    await wrapper.get('[data-testid="actual-po-date-filter"]').setValue('missing')
    await flushPromises()

    expect(wrapper.findAll('[data-booking-id]').map((row) => row.attributes('data-booking-id'))).toEqual(['BKG-002'])
    expect(router.currentRoute.value.query.actualPoDate).toBe('missing')
  })

  it('keeps Booking visible when optional account or contact references fail', async () => {
    const base = createMockApi({ latency: 0 })
    const degraded: CrmApi = {
      ...base,
      listAccounts: async () => { throw new Error('account references offline') },
      listContacts: async () => { throw new Error('contact references offline') },
    }
    const { pinia, router } = await context(degraded)
    const wrapper = mount(BookingPage, { props: { apiClient: degraded }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.findAll('[data-booking-id]')).toHaveLength(3)
    expect(wrapper.text()).toContain('参考数据暂时不可用')
    expect(wrapper.find('[data-testid="booking-crash"]').exists()).toBe(false)
  })

  it('opens the Booking detail page from the Booking name', async () => {
    const { api, pinia, router } = await context()
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-open-booking-detail="BKG-001"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('booking-detail')
    expect(router.currentRoute.value.params.bookingId).toBe('BKG-001')
  })

  it('renders a retryable state instead of crashing when the Booking list fails', async () => {
    const base = createMockApi({ latency: 0 })
    const failing: CrmApi = { ...base, listBookings: async () => { throw new Error('booking list offline') } }
    const { pinia, router } = await context(failing)
    const wrapper = mount(BookingPage, { props: { apiClient: failing }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('booking list offline')
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('keeps the latest Booking filter when an older request finishes last', async () => {
    const { api, pinia, router } = await context()
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    const olderResult = await api.listBookings({ source: 'Upsell', page: 1, pageSize: 10 })
    const latestResult = await api.listBookings({ source: 'Opportunity', page: 1, pageSize: 10 })
    const older = deferred<typeof olderResult>()
    const latest = deferred<typeof latestResult>()
    vi.spyOn(api, 'listBookings')
      .mockImplementationOnce(() => older.promise)
      .mockImplementationOnce(() => latest.promise)

    await wrapper.get('[aria-label="来源"]').setValue('Upsell')
    await wrapper.get('[aria-label="来源"]').setValue('Opportunity')
    latest.resolve(latestResult)
    await flushPromises()
    expect(wrapper.findAll('[data-booking-id]').map((row) => row.attributes('data-booking-id')))
      .toEqual(latestResult.data.items.map((item) => item.id))

    older.resolve(olderResult)
    await flushPromises()
    expect(wrapper.findAll('[data-booking-id]').map((row) => row.attributes('data-booking-id')))
      .toEqual(latestResult.data.items.map((item) => item.id))
  })

  it('creates new Bookings only as Upsell because Opportunity Bookings come from the Opportunity workflow', async () => {
    const { api, pinia, router } = await context()
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-booking"]').trigger('click')
    const source = wrapper.get('select[aria-label="Booking 来源"]')
    expect(source.findAll('option').map((option) => option.text())).toEqual(['客户增购'])
    expect(source.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('新增 Booking 仅支持客户增购')
    expect(wrapper.find('input[aria-label="Booking 直接来源"]').exists()).toBe(false)
    expect(wrapper.find('input[aria-label="Booking 直接创建原因"]').exists()).toBe(false)
  })

  it('quick creates and selects a Contact inside the Booking form', async () => {
    const { api, pinia, router } = await context()
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-booking"]').trigger('click')
    await wrapper.get('[data-testid="create-contact"]').trigger('click')
    await wrapper.get('[aria-label="联系人姓名"]').setValue('Booking 快速联系人')
    await wrapper.get('[aria-label="联系人职位"]').setValue('Equipment Manager')
    await wrapper.get('[aria-label="联系人部门"]').setValue('Equipment')
    await wrapper.findAll('[data-modal-submit]').at(-1)!.trigger('submit')
    await flushPromises()

    const created = (await api.listContacts({ search: 'Booking 快速联系人', page: 1, pageSize: 10 })).data.items[0]
    expect((wrapper.get('[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(created.id)
  })

  it('converts a confirmed Booking and retains it as a completed archive row', async () => {
    const api = createMockApi({ latency: 0 })
    const version = '2026-08-06T02:00:00.000Z'
    const listBookings = api.listBookings.bind(api)
    api.listBookings = async (query) => {
      const result = await listBookings(query)
      result.data.items = result.data.items.map((booking) => ({ ...booking, modified: version }))
      return result
    }
    const { pinia, router } = await context(api)
    const convert = vi.spyOn(api, 'convertBookingToInstalledTool')
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="convert-BKG-001"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('转入 Installed Tool')
    expect(wrapper.get('select[aria-label="负责工程师"]').text()).toContain('演示员工14 · FAE')
    expect(wrapper.get('select[aria-label="负责工程师"]').text()).toContain('演示员工15 · 工程师')
    expect((wrapper.get('select[aria-label="客户厂区"]').element as HTMLSelectElement).value).toBe('SITE-006')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(convert).toHaveBeenCalledWith('BKG-001', expect.any(Object), version)

    const archived = wrapper.get('[data-booking-id="BKG-001"]')
    expect(archived.text()).toContain('已完成')
    expect(archived.text()).toContain('TOOL-004')
    expect(archived.find('[data-testid="convert-BKG-001"]').exists()).toBe(false)
  })
})
