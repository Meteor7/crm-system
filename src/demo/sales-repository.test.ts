import { describe, expect, it } from 'vitest'
import { createMemorySalesRepository, migrateSalesSnapshot } from './sales-repository'
import { createMockApi } from '@/api/mock-adapter'

describe('sales repository Contact cleanup', () => {
  it('keeps every Equipment Booking linked to a Won Opportunity for the same Account', () => {
    const snapshot = createMemorySalesRepository().snapshot

    for (const booking of snapshot.bookings.filter((item) => item.source === 'Opportunity')) {
      expect(snapshot.opportunities.find((item) =>
        item.id === booking.sourceOpportunityId &&
        item.accountId === booking.accountId &&
        item.stage === 'Won',
      )).toBeDefined()
    }
  })

  it('physically removes retired Needs Review Contacts and keeps Bookings on valid master Contacts', () => {
    const snapshot = createMemorySalesRepository().snapshot
    const retiredNames = ['王志远', '陈珂', '赵昕', '李敏', '周楠', '顾晓', '马会东', '孙强', '钱宇']

    expect(snapshot.contacts.filter((contact) => contact.dataQuality === 'Needs Review' && retiredNames.includes(contact.name))).toHaveLength(0)
    expect(snapshot.opportunities.flatMap((opportunity) => opportunity.stakeholders)).toHaveLength(0)
    expect(snapshot.bookings.find((booking) => booking.id === 'BKG-001')?.primaryContactId).toBe('CON-009')
    expect(snapshot.bookings.find((booking) => booking.id === 'BKG-002')?.primaryContactId).toBe('CON-006')
  })

  it('migrates the current version-3 snapshot to version 5 with seeded Accounts, Sites, and Leads', () => {
    const current = createMemorySalesRepository().snapshot
    const legacy = {
      version: 3 as const,
      contacts: structuredClone(current.contacts),
      bookings: structuredClone(current.bookings),
      visits: structuredClone(current.visits),
      opportunities: structuredClone(current.opportunities),
    }

    const migrated = migrateSalesSnapshot(legacy)

    expect(migrated.version).toBe(5)
    expect(migrated.accounts.length).toBeGreaterThanOrEqual(7)
    expect(Object.keys(migrated.sites).length).toBeGreaterThan(0)
    expect(migrated.leads.length).toBeGreaterThanOrEqual(6)
    expect(migrated.contacts).toEqual(legacy.contacts)
    expect(migrated.opportunities).toEqual(legacy.opportunities)
    expect(migrated.bookings).toEqual(legacy.bookings)
    expect(migrated.visits).toEqual(legacy.visits)
  })

  it('preserves a converted Lead and its conversion links in a memory repository', () => {
    const snapshot = createMemorySalesRepository().snapshot
    const qualified = snapshot.leads.find((lead) => lead.status === 'Qualified')

    expect(qualified).toBeDefined()
    qualified!.status = 'Converted'
    qualified!.convertedAt = '2026-07-29 10:30'
    qualified!.convertedAccountId = 'ACC-001'
    qualified!.convertedContactId = 'CON-001'
    qualified!.convertedOpportunityId = 'OPP-900'

    const restored = createMemorySalesRepository(snapshot).snapshot
    const converted = restored.leads.find((lead) => lead.id === qualified!.id)

    expect(converted).toMatchObject({
      status: 'Converted',
      convertedAt: '2026-07-29 10:30',
      convertedAccountId: 'ACC-001',
      convertedContactId: 'CON-001',
      convertedOpportunityId: 'OPP-900',
    })
  })

  it('restores canonical customer Sites missing from an existing version-5 cache', () => {
    const current = createMemorySalesRepository().snapshot
    const cached = structuredClone(current)
    delete cached.sites['ACC-006']
    cached.sites['ACC-003'] = []

    const migrated = migrateSalesSnapshot(cached)

    expect(migrated.sites['ACC-006']).toContainEqual(expect.objectContaining({ id: 'SITE-006', name: '演示员工27' }))
    expect(migrated.sites['ACC-003']).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'SITE-007' }),
      expect.objectContaining({ id: 'SITE-008' }),
    ]))
  })

  it('normalizes numeric Opportunity money from a version-5 cache before Dashboard aggregation', async () => {
    const cached = structuredClone(createMemorySalesRepository().snapshot)
    const staleOpportunity = cached.opportunities[0] as unknown as { amount: number; originalAmount: number; stage: string }
    staleOpportunity.amount = 9800000
    staleOpportunity.originalAmount = 9800000
    staleOpportunity.stage = 'Demo 验证'

    const repository = createMemorySalesRepository(cached)
    const opportunity = repository.snapshot.opportunities[0]

    expect(opportunity.amount).toBe('9800000.00')
    expect(opportunity.originalAmount).toBe('9800000.00')
    expect(opportunity.stage).toBe('Wafer Demo确认')
    await expect(createMockApi({ latency: 0, salesRepository: repository }).getDashboard({ range: 'quarter' }))
      .resolves.toBeDefined()
  })

  it('keeps Opportunity normalization when the cache also triggers retired Contact cleanup', () => {
    const cached = structuredClone(createMemorySalesRepository().snapshot)
    const staleOpportunity = cached.opportunities[0] as unknown as { forecast: string; amount: number; stage: string }
    staleOpportunity.forecast = 'Upside'
    staleOpportunity.amount = 9800000
    staleOpportunity.stage = 'Demo 验证'
    cached.contacts.push({
      ...structuredClone(cached.contacts[0]!),
      id: 'CON-RETIRED',
      name: '王志远',
      dataQuality: 'Needs Review',
    })

    const opportunity = createMemorySalesRepository(cached).snapshot.opportunities[0]!

    expect(opportunity.forecast).toBe('Best Case')
    expect(opportunity.amount).toBe('9800000.00')
    expect(opportunity.stage).toBe('Wafer Demo确认')
  })

  it('reconstructs a missing converted Account and Site when migrating a version-4 cache', () => {
    const current = createMemorySalesRepository().snapshot
    const convertedLead = structuredClone(current.leads.find((lead) => lead.id === 'LEAD-002')!)
    Object.assign(convertedLead, {
      status: 'Converted',
      convertedAt: '2026-07-30T10:30:00+08:00',
      convertedAccountId: 'ACC-008',
      convertedContactId: 'CON-900',
      convertedOpportunityId: 'OPP-900',
    })
    const legacy = {
      version: 4 as const,
      leads: current.leads.map((lead) => lead.id === convertedLead.id ? convertedLead : structuredClone(lead)),
      contacts: [
        ...structuredClone(current.contacts),
        {
          id: 'CON-900',
          accountId: 'ACC-008',
          siteId: 'ACC-008-SITE-01',
          name: convertedLead.name,
          title: convertedLead.title,
          department: '待确认',
          phone: convertedLead.phone,
          email: convertedLead.email,
          relationship: 'Developing' as const,
          owner: convertedLead.owner,
          status: 'Active' as const,
          dataQuality: 'Complete' as const,
          updatedAt: '2026-07-30',
        },
      ],
      bookings: structuredClone(current.bookings),
      visits: structuredClone(current.visits),
      opportunities: [
        ...structuredClone(current.opportunities),
        {
          ...structuredClone(current.opportunities[0]!),
          id: 'OPP-900',
          sourceLeadId: convertedLead.id,
          accountId: 'ACC-008',
          siteId: 'ACC-008-SITE-01',
          account: convertedLead.company,
          site: `${convertedLead.company} Main Site`,
        },
      ],
    }

    const migrated = migrateSalesSnapshot(legacy)

    expect(migrated.accounts).toContainEqual(expect.objectContaining({
      id: 'ACC-008',
      name: convertedLead.company,
      owner: convertedLead.owner,
    }))
    expect(migrated.sites['ACC-008']).toContainEqual(expect.objectContaining({
      id: 'ACC-008-SITE-01',
      name: `${convertedLead.company} Main Site`,
    }))
  })
})
