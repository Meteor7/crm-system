import { describe, expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'

describe('personnel scope and cross-page synchronization', () => {
  it('shares customer context with other Sales, Manager, and assigned Engineer', async () => {
    const salesRepository = createMemorySalesRepository()
    const alex = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 01', salesRepository })

    const createdAccount = (await alex.createAccount({
      name: 'Sync Test Semiconductor',
      shortName: 'Sync Test',
      segment: 'Frontend',
      tier: 'A',
      city: 'Shanghai',
      region: 'East China',
      owner: 'person002@crm.example.invalid',
    })).data
    const createdContact = (await alex.createContact({
      accountId: createdAccount.id,
      name: 'Sync Contact',
      title: 'Process Manager',
      department: 'Engineering',
      relationship: 'Developing',
      owner: 'person002@crm.example.invalid',
      status: 'Active',
    })).data
    await alex.createVisit({
      accountId: createdAccount.id,
      primaryContactId: createdContact.id,
      subject: 'Sync Visit',
      date: '2026-08-03',
      type: 'On-site',
      owner: 'person002@crm.example.invalid',
      objective: 'Verify synchronized customer context',
    })
    await alex.createBooking({
      accountId: createdAccount.id,
      primaryContactId: createdContact.id,
      equipment: 'Sync Tool',
      quantity: 1,
      ddl: '2026-10-01',
      amount: '1000000.00',
      currency: 'CNY',
      status: 'Pending',
      owner: 'person002@crm.example.invalid',
      source: 'Upsell',
      sourceOpportunityId: '',
      note: 'Cross-page synchronization test',
    })

    const manager = createMockApi({ latency: 0, role: 'Manager', userName: '\u6f14\u793a\u5458\u5de524', salesRepository })
    const bella = createMockApi({ latency: 0, role: 'Sales', userName: 'Demo Staff 02', salesRepository })
    const engineer = createMockApi({
      latency: 0,
      role: 'Engineer',
      userName: '\u6f14\u793a\u5458\u5de514',
      assignedAccountIds: [createdAccount.id],
      salesRepository,
    })

    expect((await manager.listAccounts({ pageSize: 100 })).data.items).toContainEqual(
      expect.objectContaining({ id: createdAccount.id, stakeholderCount: 1 }),
    )
    expect((await engineer.listAccounts({ pageSize: 100 })).data.items).toContainEqual(
      expect.objectContaining({ id: createdAccount.id }),
    )
    expect((await bella.listAccounts({ pageSize: 100 })).data.items).not.toContainEqual(
      expect.objectContaining({ id: createdAccount.id }),
    )

    const beforeRename = (await manager.getAccount360(createdAccount.id)).data
    expect(beforeRename.contacts).toContainEqual(expect.objectContaining({ id: createdContact.id }))
    expect(beforeRename.visits).toContainEqual(expect.objectContaining({ subject: 'Sync Visit' }))
    expect(beforeRename.bookings).toContainEqual(expect.objectContaining({ equipment: 'Sync Tool' }))

    await manager.updateAccount(createdAccount.id, {
      name: 'Sync Test Semiconductor Renamed',
      shortName: 'Sync Test',
      segment: 'Frontend',
      tier: 'A',
      city: 'Shanghai',
      region: 'East China',
      owner: 'person002@crm.example.invalid',
    }, createdAccount.modified)

    const afterRename = (await manager.getAccount360(createdAccount.id)).data
    expect(afterRename.account.name).toBe('Sync Test Semiconductor Renamed')
    expect(afterRename.visits).toContainEqual(expect.objectContaining({ accountName: 'Sync Test Semiconductor Renamed' }))
    expect(afterRename.bookings).toContainEqual(expect.objectContaining({ accountName: 'Sync Test Semiconductor Renamed' }))
  })
})
