import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import type { BookingDto, UserRole } from '@/types/crm'
import BookingPage from './BookingPage.vue'
import BookingDetailPage from './BookingDetailPage.vue'

async function context(role: UserRole) {
  const api = createMockApi({ latency: 0, role, userName: role === 'Sales' ? 'Demo Staff 02' : '演示员工24' })
  const pinia = createPinia()
  const bootstrap = (await api.getBootstrap()).data
  useAppStore(pinia).bootstrap = bootstrap
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/booking', name: 'booking', component: BookingPage },
      { path: '/booking/:bookingId', name: 'booking-detail', component: BookingDetailPage },
      { path: '/accounts/:accountId', name: 'account-detail', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
      { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: { template: '<div />' } },
      { path: '/installed-tools', name: 'installed-tools', component: { template: '<div />' } },
    ],
  })
  return { api, pinia, router, user: bootstrap.user }
}

function archived(booking: BookingDto, by: string): BookingDto {
  return { ...booking, archived: true, archivedAt: '2026-10-07T03:00:00Z', archivedBy: by }
}

// The Bookings of the mock, shaped for the case: a confirmed Upsell equipment order in USD (every Manager
// correction applies to it), and a confirmed Opportunity order.
async function bookings(api: ReturnType<typeof createMockApi>) {
  const items = (await api.listBookings({ pageSize: 50 })).data.items
  const upsell: BookingDto = {
    ...items.find((item) => item.source === 'Upsell')!,
    status: 'Confirmed', bookingType: 'Equipment', currency: 'USD', amount: '20000.00', amountCny: '', installedToolId: undefined,
  }
  const fromOpportunity: BookingDto = { ...items.find((item) => item.source === 'Opportunity')!, status: 'Confirmed', bookingType: 'Equipment', installedToolId: undefined }
  return { upsell, fromOpportunity }
}

async function detail(role: UserRole, booking: BookingDto | null, id = booking?.id ?? 'BKG-NOBODY', prepare?: (api: ReturnType<typeof createMockApi>) => void) {
  const { api, pinia, router, user } = await context(role)
  if (booking) vi.spyOn(api, 'getBooking').mockResolvedValue({ data: booking, warnings: [] })
  prepare?.(api)
  await router.push(`/booking/${id}`)
  await router.isReady()
  const wrapper = mount(BookingDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router, ElementPlus] } })
  await flushPromises()
  return { api, router, user, wrapper }
}

const CORRECTIONS = ['edit-booking', 'set-actual-po-date', 'set-amount-cny']

afterEach(() => vi.restoreAllMocks())

describe('Booking archive', () => {
  it('lets a Manager archive an Upsell Booking from its page, which then shows the notice and the restore, and restore it', async () => {
    const { api } = await context('Manager')
    const { upsell } = await bookings(api)
    const page = await detail('Manager', upsell)
    const archive = vi.spyOn(page.api, 'archiveBooking').mockResolvedValue({ data: archived(upsell, page.user.id), warnings: [] })
    expect(page.wrapper.find('[data-delete-booking]').exists()).toBe(false)
    expect(page.wrapper.find('[data-unarchive-booking]').exists()).toBe(false)
    for (const action of CORRECTIONS) expect(page.wrapper.find(`[data-testid="${action}"]`).exists(), action).toBe(true)

    await page.wrapper.get('[data-archive-booking]').trigger('click')
    await flushPromises()
    const dialog = page.wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-label')).toBe('归档 Booking')
    expect(dialog.text()).toContain(upsell.id)
    expect(dialog.text()).toContain('资料全部保留')
    expect(dialog.text()).not.toContain('删除')
    expect(dialog.get('[data-modal-submit]').text()).toBe('归档')
    expect(dialog.get('[data-modal-submit]').classes()).toContain('danger-action')
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(archive).toHaveBeenCalledWith(upsell.id)
    expect(page.router.currentRoute.value.path).toBe(`/booking/${upsell.id}`)
    expect(page.wrapper.find('[role="dialog"]').exists()).toBe(false)
    const notice = page.wrapper.get('[data-archived-notice]').text()
    expect(notice).toContain('已归档')
    expect(notice).toContain(page.user.name)
    expect(notice).toContain('取消归档后恢复')
    expect(page.wrapper.find('[data-archive-booking]').exists()).toBe(false)
    for (const action of CORRECTIONS) expect(page.wrapper.find(`[data-testid="${action}"]`).exists(), action).toBe(false)

    const restore = vi.spyOn(page.api, 'unarchiveBooking').mockResolvedValue({ data: { ...upsell, archived: false }, warnings: [] })
    await page.wrapper.get('[data-unarchive-booking]').trigger('click')
    await flushPromises()
    expect(restore).toHaveBeenCalledWith(upsell.id)
    expect(page.wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(page.wrapper.find('[data-unarchive-booking]').exists()).toBe(false)
    expect(page.wrapper.find('[data-archive-booking]').exists()).toBe(true)
    for (const action of CORRECTIONS) expect(page.wrapper.find(`[data-testid="${action}"]`).exists(), action).toBe(true)
  })

  it('offers the archive to nobody but a Manager, and not for an Opportunity or a completed Booking', async () => {
    const { api } = await context('Manager')
    const { upsell, fromOpportunity } = await bookings(api)

    const sales = await detail('Sales', upsell)
    expect(sales.wrapper.find('[data-archive-booking]').exists()).toBe(false)
    expect(sales.wrapper.find('[data-testid="edit-booking"]').exists()).toBe(true)

    for (const [label, booking] of [
      ['an Opportunity Booking', fromOpportunity],
      ['a completed Booking', { ...upsell, status: 'Completed' as const }],
      ['a converted Booking', { ...upsell, installedToolId: 'TOOL-001' }],
    ] as const) {
      const page = await detail('Manager', booking)
      expect(page.wrapper.find('[data-archive-booking]').exists(), label).toBe(false)
      expect(page.wrapper.find('[data-unarchive-booking]').exists(), label).toBe(false)
    }
  })

  it('reads an archived Booking by its id, tells a Sales user to ask a Manager, and says a Booking out of reach is not found', async () => {
    const { api } = await context('Manager')
    const { upsell } = await bookings(api)

    // An archived Booking is not in the pipeline; the page reads it by id and never searches the pipeline.
    const archivedForSales = await detail('Sales', archived(upsell, 'manager@example.invalid'), upsell.id, (prepared) => {
      vi.spyOn(prepared, 'listPipeline')
    })
    expect(archivedForSales.wrapper.get('[data-archived-notice]').text()).toContain('请联系经理')
    expect(archivedForSales.wrapper.get('[data-archived-notice]').text()).not.toContain('取消归档后')
    expect(archivedForSales.wrapper.text()).toContain(upsell.id)
    expect(archivedForSales.wrapper.find('[data-unarchive-booking]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-archive-booking]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-testid="edit-booking"]').exists()).toBe(false)
    expect(archivedForSales.api.listPipeline).not.toHaveBeenCalled()

    for (const [code, id] of [['BOOKING_NOT_FOUND', 'BKG-NOBODY'], ['SCOPE_DENIED', 'BKG-THEIRS']] as const) {
      const page = await detail('Manager', null, id, (prepared) => {
        vi.spyOn(prepared, 'getBooking').mockRejectedValue(new CrmApiError(code, 'Server wording', `req-${id}`, false))
      })
      expect(page.wrapper.text(), code).toContain(`未找到 Booking ${id}`)
      expect(page.wrapper.text(), code).not.toContain('Server wording')
    }
  })

  it('keeps the page and shows the refusal with its request id when the archive or the restore is refused, and clears it for another Booking', async () => {
    const { api } = await context('Manager')
    const { upsell, fromOpportunity } = await bookings(api)
    const page = await detail('Manager', upsell)
    vi.spyOn(page.api, 'archiveBooking').mockRejectedValue(new CrmApiError('BOOKING_SOURCE_INVALID', 'An Opportunity Booking cannot be archived; cancel it instead.', 'req-archive-booking', false))
    await page.wrapper.get('[data-archive-booking]').trigger('click')
    await flushPromises()
    await page.wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    const dialog = page.wrapper.get('[role="dialog"]')
    expect(dialog.get('[data-archive-error]').text()).toContain('商机来源的 Booking 不能归档，请改为取消。')
    expect(dialog.get('[data-archive-error]').text()).toContain('请求编号 req-archive-booking')
    expect(page.wrapper.findAll('[data-archive-error]')).toHaveLength(1)
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    expect(page.router.currentRoute.value.path).toBe(`/booking/${upsell.id}`)
    expect(page.wrapper.find('[data-archived-notice]').exists()).toBe(false)
    await dialog.get('header button').trigger('click')
    await flushPromises()
    expect(page.wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(page.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(page.wrapper.find('[data-archive-booking]').exists()).toBe(true)

    const archivedPage = await detail('Manager', archived(upsell, 'manager@example.invalid'), upsell.id, (prepared) => {
      vi.spyOn(prepared, 'unarchiveBooking').mockRejectedValue(new CrmApiError('SCOPE_DENIED', 'The Booking is outside the current user scope.', 'req-restore-booking', false))
    })
    await archivedPage.wrapper.get('[data-unarchive-booking]').trigger('click')
    await flushPromises()
    expect(archivedPage.wrapper.get('[data-archive-error]').text()).toContain('req-restore-booking')
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(true)
    expect(archivedPage.wrapper.get('[data-unarchive-booking]').attributes('disabled')).toBeUndefined()

    // The error belongs to that Booking: another one opened in the same page starts clean.
    vi.spyOn(archivedPage.api, 'getBooking').mockResolvedValue({ data: fromOpportunity, warnings: [] })
    await archivedPage.router.push(`/booking/${fromOpportunity.id}`)
    await flushPromises()
    expect(archivedPage.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(archivedPage.wrapper.text()).toContain(fromOpportunity.id)
  })

  it('drops an answer that arrives after the page moved to another Booking', async () => {
    const { api } = await context('Manager')
    const { upsell, fromOpportunity } = await bookings(api)
    // A second Upsell order, which the page moves on to while the first one's archive is out.
    const second: BookingDto = { ...upsell, id: `${upsell.id}-TWO` }
    const page = await detail('Manager', upsell)
    const pending: Array<{ settle: (value: { data: BookingDto; warnings: never[] }) => void }> = []
    vi.spyOn(page.api, 'archiveBooking').mockImplementation(() => new Promise((resolve) => { pending.push({ settle: resolve }) }))
    await page.wrapper.get('[data-archive-booking]').trigger('click')
    await flushPromises()
    await page.wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    // The page moves on while the archive is out: the second order's button is free at once, before any answer.
    vi.spyOn(page.api, 'getBooking').mockResolvedValue({ data: second, warnings: [] })
    await page.router.push(`/booking/${second.id}`)
    await flushPromises()
    expect(page.wrapper.text()).toContain(second.id)
    expect(page.wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(page.wrapper.get('[data-archive-booking]').attributes('disabled')).toBeUndefined()
    // The second order's own archive goes out; the first one's answer lands meanwhile and is for the order before:
    // it changes nothing here, and the second's request still holds the dialog.
    await page.wrapper.get('[data-archive-booking]').trigger('click')
    await flushPromises()
    await page.wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(pending).toHaveLength(2)
    pending[0]!.settle({ data: archived(upsell, page.user.id), warnings: [] })
    await flushPromises()
    expect(page.wrapper.text()).toContain(second.id)
    expect(page.wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(page.wrapper.get('[role="dialog"] [data-modal-submit]').attributes('disabled')).toBeDefined()
    pending[1]!.settle({ data: archived(second, page.user.id), warnings: [] })
    await flushPromises()
    expect(page.wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(page.wrapper.get('[data-archived-notice]').text()).toContain('已归档')

    // The same for a refusal that arrives late.
    let fail!: (reason: unknown) => void
    const again = await detail('Manager', upsell)
    vi.spyOn(again.api, 'archiveBooking').mockImplementation(() => new Promise((_resolve, reject) => { fail = reject }))
    await again.wrapper.get('[data-archive-booking]').trigger('click')
    await flushPromises()
    await again.wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    vi.spyOn(again.api, 'getBooking').mockResolvedValue({ data: fromOpportunity, warnings: [] })
    await again.router.push(`/booking/${fromOpportunity.id}`)
    await flushPromises()
    fail(new CrmApiError('INVALID_TRANSITION', 'An Opportunity Booking cannot be archived; cancel it instead.', 'req-late', false))
    await flushPromises()
    expect(again.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(again.wrapper.text()).toContain(fromOpportunity.id)
    expect(again.wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('reads the pipeline for the editor only when the editor opens', async () => {
    const { api } = await context('Manager')
    const { fromOpportunity } = await bookings(api)
    const page = await detail('Manager', fromOpportunity, fromOpportunity.id, (prepared) => {
      vi.spyOn(prepared, 'listPipeline')
    })
    expect(page.api.listPipeline).not.toHaveBeenCalled()
    await page.wrapper.get('[data-testid="edit-booking"]').trigger('click')
    await flushPromises()
    expect(page.api.listPipeline).toHaveBeenCalledTimes(1)
    expect(page.wrapper.find('[role="dialog"]').exists()).toBe(true)
  })

  it('lists active Bookings by default, the archived ones through the filter kept in the URL, marked and without actions', async () => {
    const { api, pinia, router } = await context('Manager')
    const { upsell, fromOpportunity } = await bookings(api)
    const archivedUpsell = archived(upsell, 'manager@example.invalid')
    // A confirmed Service order in use, and one archived: the complete-service button of the second must go.
    const service: BookingDto = { ...upsell, id: 'BKG-SERVICE', bookingType: 'Service', equipment: 'Service plan' }
    const archivedService = archived({ ...service, id: 'BKG-SERVICE-ARCHIVED' }, 'manager@example.invalid')
    const summary = (count: number) => ({ count, pendingCount: 0, confirmed: { count, totals: [] } })
    const active = [fromOpportunity, service]
    const gone = [archivedUpsell, archivedService]
    const list = vi.spyOn(api, 'listBookings').mockImplementation(async (query) => {
      const items = query.archiveState === 'archived' ? gone : query.archiveState === 'all' ? [...active, ...gone] : active
      return { data: { items, summary: summary(items.length) }, meta: { requestId: 'req-list', page: 1, pageSize: 10, total: items.length }, warnings: [] }
    })
    // Opened on the archived ones straight from the URL.
    await router.push('/booking?archive=archived')
    await router.isReady()
    const wrapper = mount(BookingPage, { props: { apiClient: api }, global: { plugins: [pinia, router, ElementPlus] } })
    await flushPromises()
    const editButtons = () => wrapper.findAll('[aria-label="编辑 Booking"]')
    const ids = () => wrapper.findAll('[data-booking-id]').map((row) => row.attributes('data-booking-id'))

    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'archived' }))
    expect((wrapper.get('[aria-label="归档状态"]').element as HTMLSelectElement).value).toBe('archived')
    expect(ids()).toEqual(gone.map((item) => item.id))
    expect(wrapper.findAll('[data-booking-archived]').map((badge) => badge.text())).toEqual(['已归档', '已归档'])
    expect(editButtons()).toHaveLength(0)
    expect(wrapper.find(`[data-testid="convert-${upsell.id}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="complete-service-${archivedService.id}"]`).exists()).toBe(false)

    await wrapper.get('[aria-label="归档状态"]').setValue('active')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active', page: 1 }))
    expect(router.currentRoute.value.query.archive).toBeUndefined()
    expect(ids()).toEqual(active.map((item) => item.id))
    expect(wrapper.find('[data-booking-archived]').exists()).toBe(false)
    // The active rows keep their buttons: the control for the archived ones.
    expect(editButtons()).toHaveLength(2)
    expect(wrapper.find(`[data-testid="convert-${fromOpportunity.id}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="complete-service-${service.id}"]`).exists()).toBe(true)

    await wrapper.get('[aria-label="归档状态"]').setValue('all')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'all' }))
    expect(router.currentRoute.value.query.archive).toBe('all')
    expect(ids()).toHaveLength(4)
    expect(wrapper.findAll('[data-booking-archived]')).toHaveLength(2)
    expect(editButtons()).toHaveLength(2)
    expect(wrapper.find(`[data-testid="convert-${fromOpportunity.id}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="convert-${upsell.id}"]`).exists()).toBe(false)
    expect(wrapper.find(`[data-testid="complete-service-${service.id}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="complete-service-${archivedService.id}"]`).exists()).toBe(false)

    // The filter follows the URL after mount as well.
    await router.push('/booking?archive=archived')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'archived' }))
    expect((wrapper.get('[aria-label="归档状态"]').element as HTMLSelectElement).value).toBe('archived')
    await router.push('/booking')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active' }))
  })
})
