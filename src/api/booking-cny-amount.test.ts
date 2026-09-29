import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import BookingEditorModal from '@/features/opportunities/BookingEditorModal.vue'
import type { BookingDto, UpsertBookingInput } from '@/types/crm'
import { createMockApi } from './mock-adapter'

async function activeContact(api: ReturnType<typeof createMockApi>) {
  return (await api.listContacts({ accountId: 'ACC-002', pageSize: 100 })).data.items.find((item) => item.status === 'Active')!
}

function upsell(contactId: string, overrides: Partial<UpsertBookingInput> = {}): UpsertBookingInput {
  return {
    accountId: 'ACC-002', primaryContactId: contactId, equipment: 'Upgrade kit', quantity: 1, ddl: '2026-12-31',
    amount: '50000.00', currency: 'USD', status: 'Confirmed', source: 'Upsell', sourceOpportunityId: '',
    owner: 'person002@crm.example.invalid', note: '', ...overrides,
  }
}

describe('mock Booking amount in CNY', () => {
  it('asks for the CNY amount of a foreign-currency PO and keeps a CNY order on its own amount', async () => {
    const salesRepository = createMemorySalesRepository()
    const api = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', today: '2026-07-20', salesRepository })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository })
    const contact = await activeContact(api)
    const draft = {
      primaryContactId: contact.id, equipment: 'HBM AOI', quantity: 1, ddl: '2026-11-12', amount: '4200000.00',
      currency: 'USD', owner: 'person002@crm.example.invalid', note: '',
    }

    await expect(api.confirmPo('OPP-003', { booking: draft, actualPoDate: '2026-07-15' }))
      .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { amountCny: 'Required' } })
    const received = (await api.confirmPo('OPP-003', { booking: { ...draft, amountCny: '30100000' }, actualPoDate: '2026-07-15' })).data
    expect(received.liveBooking).toMatchObject({ currency: 'USD', amount: '4200000.00', amountCny: '30100000.00' })

    // Cancelling and replacing the order keeps the trail of its CNY amount and PO date.
    const first = (await api.listBookings({ pageSize: 100 })).data.items.find((item) => item.id === received.liveBooking!.id)!
    await api.updateBooking(first.id, { ...first, status: 'Cancelled' } as never)
    const replaced = (await api.confirmPo('OPP-003', { booking: { ...draft, amountCny: '29000000' }, actualPoDate: '2026-07-16' })).data
    expect(replaced.history.filter((item) => ['bookingAmountCny', 'bookingPoDate'].includes(item.field)).map((item) => [item.field, item.from, item.to]))
      .toEqual(expect.arrayContaining([['bookingAmountCny', '30100000.00', '29000000.00'], ['bookingPoDate', '2026-07-15', '2026-07-16']]))

    const cny = (await manager.listBookings({ pageSize: 100 })).data.items.find((item) => item.id === 'BKG-001')!
    expect(cny.currency).toBe('CNY')
    expect(cny.amountCny).toBe(cny.amount)
  })

  it('makes a confirmed foreign-currency Upsell carry its CNY amount, but never blocks cancelling', async () => {
    const api = createMockApi({ latency: 0, salesRepository: createMemorySalesRepository() })
    const contact = await activeContact(api)

    await expect(api.createBooking(upsell(contact.id))).rejects.toMatchObject({ fieldErrors: { amountCny: 'Required' } })
    const pending = (await api.createBooking(upsell(contact.id, { status: 'Pending' }))).data
    expect(pending.amountCny).toBe('')
    await expect(api.updateBooking(pending.id, upsell(contact.id))).rejects.toMatchObject({ fieldErrors: { amountCny: 'Required' } })

    const confirmed = (await api.updateBooking(pending.id, upsell(contact.id, { amountCny: '355000' }))).data
    expect(confirmed.amountCny).toBe('355000.00')
    const cancelled = (await api.updateBooking(pending.id, upsell(contact.id, { amountCny: '', status: 'Cancelled' }))).data
    expect(cancelled).toMatchObject({ status: 'Cancelled', amountCny: '355000.00' })
  })

  it('keeps a recorded CNY amount out of ordinary edits', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository })
    const contact = await activeContact(manager)
    const booking = (await manager.createBooking(upsell(contact.id, { amountCny: '355000' }))).data

    for (const api of [sales, manager]) {
      await expect(api.updateBooking(booking.id, upsell(contact.id, { amountCny: '1.00' })))
        .rejects.toMatchObject({ code: 'VALIDATION_ERROR', fieldErrors: { amountCny: 'Manager correction only' } })
    }
    const edited = (await sales.updateBooking(booking.id, upsell(contact.id, { amountCny: '355000', note: 'Ships in March' }))).data
    expect(edited).toMatchObject({ amountCny: '355000.00', note: 'Ships in March' })

    await manager.setBookingAmountCny(booking.id, { amountCny: '356000', reason: 'Rate on the PO' })
    const native = (await sales.updateBooking(booking.id, upsell(contact.id, { currency: 'CNY', amount: '356000.00' }))).data
    expect(native).toMatchObject({ amountCny: '356000.00', amountCnyNote: '' })

    const pending = (await sales.createBooking(upsell(contact.id, { status: 'Pending', amountCny: '300000' }))).data
    const repriced = (await sales.updateBooking(pending.id, upsell(contact.id, { status: 'Pending', amountCny: '310000' }))).data
    expect(repriced.amountCny).toBe('310000.00')
  })

  it('lets only a Manager fill in or correct the CNY amount of a confirmed foreign-currency order', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository })
    const manager = createMockApi({ latency: 0, role: 'Manager', salesRepository })
    const contact = await activeContact(manager)
    const booking = (await manager.createBooking(upsell(contact.id, { amountCny: '355000' }))).data

    await expect(sales.setBookingAmountCny(booking.id, { amountCny: '356000' })).rejects.toMatchObject({ code: 'PERMISSION_DENIED' })
    await expect(manager.setBookingAmountCny(booking.id, { amountCny: '356000' })).rejects.toMatchObject({ fieldErrors: { reason: 'Required' } })
    await expect(manager.setBookingAmountCny(booking.id, { amountCny: '355000.00', reason: 'Same' }))
      .rejects.toMatchObject({ fieldErrors: { amountCny: 'Unchanged' } })
    const corrected = (await manager.setBookingAmountCny(booking.id, { amountCny: '356000', reason: 'Rate on the PO' })).data
    expect(corrected).toMatchObject({ amountCny: '356000.00', amountCnyNote: 'Rate on the PO' })

    await expect(manager.setBookingAmountCny('BKG-001', { amountCny: '1' })).rejects.toMatchObject({ fieldErrors: { amountCny: 'CNY Booking' } })
  })
})

describe('Booking editor amount in CNY', () => {
  const props = { accounts: [], contacts: [], defaultOwner: 'person002@crm.example.invalid' }

  it('asks for the amount in CNY only when the order is in another currency', async () => {
    const foreign = { id: 'BKG-9', accountId: 'ACC-002', source: 'Upsell', status: 'Pending', currency: 'USD', amount: '50000.00', amountCny: '355000.00' } as BookingDto
    const cny = mount(BookingEditorModal, { props })
    expect(cny.find('[aria-label="人民币金额"]').exists()).toBe(false)

    await cny.get('[aria-label="币种"]').setValue('USD')
    expect(cny.get('[aria-label="人民币金额"]').attributes('required')).toBeDefined()

    const editing = mount(BookingEditorModal, { props: { ...props, booking: foreign } })
    expect((editing.get('[aria-label="人民币金额"]').element as HTMLInputElement).value).toBe('355000.00')
    await editing.get('[aria-label="人民币金额"]').setValue('356000')
    await editing.get('form').trigger('submit')
    expect(editing.emitted('submit')?.[0]?.[0]).toMatchObject({ currency: 'USD', amountCny: '356000' })
  })

  it('locks the recorded CNY amount of an order and sends it back unchanged', async () => {
    const order = { id: 'BKG-9', accountId: 'ACC-002', source: 'Upsell', status: 'Confirmed', currency: 'USD', amount: '50000.00', amountCny: '355000.00' } as BookingDto
    const editing = mount(BookingEditorModal, { props: { ...props, booking: order } })
    expect(editing.get('[aria-label="人民币金额"]').attributes('disabled')).toBeDefined()
    await editing.get('form').trigger('submit')
    expect(editing.emitted('submit')?.[0]?.[0]).toMatchObject({ amountCny: '355000.00' })

    const missing = mount(BookingEditorModal, { props: { ...props, booking: { ...order, amountCny: '' } } })
    expect(missing.get('[aria-label="人民币金额"]').attributes('disabled')).toBeUndefined()
  })
})
