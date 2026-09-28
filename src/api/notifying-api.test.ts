import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'
import { createNotifyingApi } from './notifying-api'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import type { NotificationInput } from '@/types/notifications'

describe('createNotifyingApi', () => {
  it('targets an assigned Action owner with a stable recipient and detail link', async () => {
    const messages: NotificationInput[] = []
    const api = createNotifyingApi(createMockApi({ latency: 0 }), (message) => messages.push(message))

    await api.createOpportunityAction('OPP-001', {
      title: 'Confirm acceptance window', owner: 'person002@crm.example.invalid', due: '2026-08-08', status: 'Open',
    })

    expect(messages.at(-1)).toMatchObject({
      category: 'Action', recipientId: 'person002@crm.example.invalid', recipient: 'Demo Staff 01', route: '/opportunities/OPP-001',
    })
  })

  it('links an assigned Booking owner directly to the Booking detail page', async () => {
    const messages: NotificationInput[] = []
    const api = createNotifyingApi(createMockApi({ latency: 0 }), (message) => messages.push(message))
    const contact = (await api.listContacts({ accountId: 'ACC-001', pageSize: 100 })).data.items[0]
    const created = await api.createBooking({
      accountId: 'ACC-001', primaryContactId: contact.id, equipment: 'Assignment test tool', quantity: 1,
      ddl: '2026-09-30', amount: '1000000.00', currency: 'CNY', status: 'Pending', owner: 'person002@crm.example.invalid', source: 'Upsell',
      sourceOpportunityId: '', note: '',
    })

    expect(messages.at(-1)).toMatchObject({
      category: 'Booking', recipientId: 'person002@crm.example.invalid', recipient: 'Demo Staff 01', route: `/booking/${created.data.id}`,
    })
  })

  it('does not publish when the underlying write fails', async () => {
    const messages: NotificationInput[] = []
    const api = createNotifyingApi(
      createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01' }),
      (message) => messages.push(message),
    )

    await expect(api.markOpportunityLost('OPP-006', { lostReason: 'Customer cancelled' })).rejects.toBeTruthy()
    expect(messages).toHaveLength(0)
  })

  it('notifies the assigned engineer after Booking handoff', async () => {
    const messages: NotificationInput[] = []
    const api = createNotifyingApi(createMockApi({ latency: 0 }), (message) => messages.push(message))
    const converted = await api.convertBookingToInstalledTool('BKG-001', {
      siteId: 'SITE-006', engineerOwner: 'person077@crm.example.invalid', serial: 'ASSIGN-TOOL-001', model: 'FastScan 1200',
      location: '', salesOrder: '', contract: '', software: '', firmware: '', configuration: '',
    })

    expect(messages.at(-1)).toMatchObject({
      category: 'InstalledTool', recipientId: 'person077@crm.example.invalid', recipient: '\u6f14\u793a\u5458\u5de514',
      route: `/installed-tools?highlight=${converted.data.installedTool.id}`,
    })
  })

  it('tells the requester when another Manager approves an internal validation', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository })
    const contact = (await sales.listContacts({ accountId: 'ACC-002', pageSize: 100 })).data.items.find((item) => item.status === 'Active')!
    const requested = await sales.requestInternalValidation('OPP-003', {
      reason: 'Lock production capacity', expectedPoDate: '2026-09-30',
      booking: { primaryContactId: contact.id, equipment: 'HBM AOI', quantity: 1, ddl: '2026-11-12', amount: '32500000.00', currency: 'CNY', owner: 'person002@crm.example.invalid', note: '' },
    })
    const messages: NotificationInput[] = []
    const manager = createNotifyingApi(createMockApi({ latency: 0, role: 'Manager', salesRepository }), (message) => messages.push(message))

    await manager.reviewInternalValidation('OPP-003', { validationId: requested.data.internalValidation!.id, decision: 'approved', comment: '' })

    expect(messages.at(-1)).toMatchObject({
      category: 'Opportunity', title: '内部生产审批已批准', recipientId: 'person002@crm.example.invalid', route: '/opportunities/OPP-003',
    })
  })

  it('links the Booking owner to the confirmed Booking when the PO is received', async () => {
    const messages: NotificationInput[] = []
    const api = createNotifyingApi(createMockApi({ latency: 0, role: 'Manager' }), (message) => messages.push(message))
    const opportunity = (await api.getStrategyOpportunity('OPP-008')).data

    await api.confirmPo('OPP-008', { booking: { ...opportunity.internalValidation!.booking } })

    expect(messages.at(-1)).toMatchObject({
      category: 'Booking', title: 'Booking 已确认', recipientId: 'person002@crm.example.invalid', route: '/booking/BKG-003',
    })
  })

  it('does not fabricate browser notifications for a server-backed Frappe adapter', async () => {
    const messages: NotificationInput[] = []
    const source = createMockApi({ latency: 0 })
    const api = createNotifyingApi(source, (message) => messages.push(message), 'server')

    expect(api).toBe(source)
    await api.createOpportunityAction('OPP-001', {
      title: 'Server event only', owner: 'person002@crm.example.invalid', due: '2026-08-08', status: 'Open',
    })
    expect(messages).toEqual([])
  })
})
