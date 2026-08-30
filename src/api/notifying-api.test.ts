import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'
import { createNotifyingApi } from './notifying-api'
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

    await expect(api.updateStrategyOpportunity('OPP-006', { stage: 'Won' })).rejects.toBeTruthy()
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
