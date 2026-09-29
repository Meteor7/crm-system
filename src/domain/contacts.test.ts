import { describe, expect, it } from 'vitest'
import { expandOpportunityContact, migrateLegacyOpportunityContacts, migrateLegacyPrimaryContacts } from './contacts'
import type { ContactDto } from '@/types/crm'
import type { LegacyStrategyOpportunityDto, OpportunityStakeholderDto } from '@/types/workspaces'
import { createMemorySalesRepository, migrateSalesSnapshot, type SalesSnapshotV1 } from '@/demo/sales-repository'

const contact = (overrides: Partial<ContactDto> = {}): ContactDto => ({
  id: 'CT-001',
  accountId: 'ACC-001',
  name: 'Wang Zhiyuan',
  title: 'Equipment VP',
  department: 'Manufacturing',
  relationship: 'Strong',
  owner: 'person002@crm.example.invalid',
  status: 'Active',
  dataQuality: 'Complete',
  updatedAt: '2026-07-28',
  ...overrides,
})

const legacyOpportunity = (stakeholders: LegacyStrategyOpportunityDto['stakeholders'], accountId = 'ACC-001'): LegacyStrategyOpportunityDto => ({
  id: 'OPP-001',
  accountId,
  siteId: 'SITE-001',
  title: 'Inspection expansion',
  account: 'Example account',
  site: 'Example site',
  owner: 'person002@crm.example.invalid',
  stage: 'qualified_opportunity',
  stageChangedAt: '',
  budgetApprovedOn: '',
  lostAtStage: '',
  lostAt: '',
  lostBy: '',
  stageHistory: [],
  internalValidation: null,
  liveBooking: null,
  amount: '100.00',
  currency: 'CNY',
  probabilityLevel: '',
  probabilityHistory: [],
  poDate: '2026-12-01',
  updated: '2026-07-28',
  score: 1,
  toolType: 'Inspection',
  saleType: 'New Tool',
  subRegion: 'East',
  originalAmount: '100.00',
  amountCny: '100.00',
  shipmentDate: '2027-01-01',
  fatDate: '2026-12-01',
  paymentMilestones: [],
  competition: '',
  winReason: '',
  lostReason: '',
  history: [],
  strengths: [],
  redFlags: [],
  informationNeeded: [],
  stakeholders,
  actions: [],
})

describe('contact master migration', () => {
  it('converts legacy Booking text into one stable Needs Review Contact', () => {
    const bookings = [{
      id: 'BKG-001', accountId: 'ACC-006', accountName: 'CUSTOMER04', title: 'FastScan 1200',
      customerContact: '演示员工20', equipment: 'FastScan 1200', quantity: 1, ddl: '2026-09-30',
      amount: '1000000.00', currency: 'CNY', status: 'Pending' as const, bookingDate: '2026-07-28',
      owner: 'person005@crm.example.invalid', sourceOpportunityId: 'OPP-001', note: '',
    }]
    const first = migrateLegacyPrimaryContacts([], bookings, [])
    const second = migrateLegacyPrimaryContacts(first.contacts, first.bookings, first.demoRequests)

    expect(first.contacts[0]).toMatchObject({
      id: 'CT-BKG-BKG-001', accountId: 'ACC-006', name: '演示员工20', dataQuality: 'Needs Review',
    })
    expect(first.bookings[0].primaryContactId).toBe(first.contacts[0].id)
    expect(second).toEqual(first)
  })

  it('keeps the first Demo display segment in an account-scoped migrated Contact', () => {
    const migrated = migrateLegacyPrimaryContacts([
      contact({ id: 'CT-OTHER', accountId: 'ACC-002', name: 'Ada Liu' }),
    ], [], [{
      id: 'DR-001', accountId: 'ACC-001', accountName: 'Example Fab',
      salesOwner: 'person002@crm.example.invalid', formData: { contactPerson: 'Ada Liu, Director, ada@example.com' },
    }])

    expect(migrated.contacts.at(-1)).toMatchObject({
      id: 'CT-DR-DR-001', accountId: 'ACC-001', name: 'Ada Liu', title: '', department: '',
    })
    expect(migrated.demoRequests[0]).toMatchObject({ primaryContactId: 'CT-DR-DR-001' })
  })

  it('reuses a unique same-account contact and creates an id-based relationship', () => {
    const migrated = migrateLegacyOpportunityContacts([contact()], [legacyOpportunity([{
      id: 'STK-001', name: '  wang zhiyuan ', title: 'equipment vp', role: 'Economic Buyer',
      influence: 'High', stance: 'Neutral', coverage: 'Manager relationship',
    }])])

    expect(migrated.contacts).toHaveLength(1)
    expect(migrated.opportunities[0].stakeholders[0]).toMatchObject({
      contactId: 'CT-001',
      role: 'Economic Buyer',
      influence: 'High',
    })
  })

  it('creates one Needs Review contact for an unmatched stakeholder and stays idempotent', () => {
    const first = migrateLegacyOpportunityContacts([], [legacyOpportunity([{
      id: 'STK-007', name: 'Ma Huidong', title: 'Packaging GM', role: 'Economic Buyer',
      influence: 'High', stance: 'Neutral', coverage: 'No direct access',
    }], 'ACC-005')])
    const second = migrateLegacyOpportunityContacts(first.contacts, first.opportunities)

    expect(first.contacts[0]).toMatchObject({
      id: 'CT-MIG-STK-007',
      accountId: 'ACC-005',
      name: 'Ma Huidong',
      dataQuality: 'Needs Review',
    })
    expect(second.contacts).toEqual(first.contacts)
    expect(second.opportunities).toEqual(first.opportunities)
  })

  it('creates a Needs Review contact when same-account legacy matching is ambiguous', () => {
    const migrated = migrateLegacyOpportunityContacts([
      contact({ id: 'CT-001' }),
      contact({ id: 'CT-002' }),
    ], [legacyOpportunity([{
      id: 'STK-002', name: 'Wang Zhiyuan', title: 'Equipment VP', role: 'Influencer',
      influence: 'Medium', stance: 'Support', coverage: 'Technical sync',
    }])])

    expect(migrated.contacts).toHaveLength(3)
    expect(migrated.contacts[2]).toMatchObject({
      id: 'CT-MIG-STK-002',
      dataQuality: 'Needs Review',
    })
    expect(migrated.opportunities[0].stakeholders[0].contactId).toBe('CT-MIG-STK-002')
  })

  it('does not reuse a matching Contact from another account', () => {
    const migrated = migrateLegacyOpportunityContacts([
      contact({ accountId: 'ACC-OTHER' }),
    ], [legacyOpportunity([{
      id: 'STK-003', name: 'Wang Zhiyuan', title: 'Equipment VP', role: 'Economic Buyer',
      influence: 'High', stance: 'Neutral', coverage: 'Manager relationship',
    }])])

    expect(migrated.contacts).toHaveLength(2)
    expect(migrated.opportunities[0].stakeholders[0].contactId).toBe('CT-MIG-STK-003')
    expect(migrated.contacts[1].accountId).toBe('ACC-001')
  })

  it('keeps a valid same-account contact ID ahead of email and label matching', () => {
    const migrated = migrateLegacyOpportunityContacts([
      contact({ id: 'CT-ID', name: 'Assigned contact', title: 'VP' }),
      contact({ id: 'CT-EMAIL', name: 'Email contact', title: 'Director', email: 'person@example.com' }),
    ], [legacyOpportunity([{
      id: 'STK-ID', contactId: 'CT-ID', name: 'Email contact', title: 'Director', email: 'person@example.com',
      role: 'Champion', influence: 'High', stance: 'Support', coverage: 'Direct access',
    }])])

    expect(migrated.opportunities[0].stakeholders[0].contactId).toBe('CT-ID')
  })

  it('falls back from stale and cross-account contact IDs to same-account matching', () => {
    const contacts = [
      contact({ id: 'CT-EMAIL', email: 'person@example.com', name: 'Email contact', title: 'Director' }),
      contact({ id: 'CT-LABEL', name: 'Local contact', title: 'Manager' }),
      contact({ id: 'CT-OTHER', accountId: 'ACC-OTHER', name: 'Other account', title: 'Manager' }),
    ]
    const migrated = migrateLegacyOpportunityContacts(contacts, [legacyOpportunity([
      { id: 'STK-STALE', contactId: 'CT-MISSING', name: 'Email contact', title: 'Director', email: 'person@example.com', role: 'Champion', influence: 'High', stance: 'Support', coverage: 'Direct access' },
      { id: 'STK-CROSS', contactId: 'CT-OTHER', name: 'Local contact', title: 'Manager', role: 'Champion', influence: 'High', stance: 'Support', coverage: 'Direct access' },
    ])])

    expect(migrated.opportunities[0].stakeholders.map((item) => item.contactId)).toEqual(['CT-EMAIL', 'CT-LABEL'])
  })

  it('prefers a unique email match and preserves email on a created Contact', () => {
    const byEmail = migrateLegacyOpportunityContacts([
      contact({ id: 'CT-EMAIL', name: 'Different name', title: 'Different title', email: 'person@example.com' }),
      contact({ id: 'CT-LABEL', name: 'Legacy name', title: 'Legacy title' }),
    ], [legacyOpportunity([{
      id: 'STK-EMAIL', name: 'Legacy name', title: 'Legacy title', email: ' person@example.com ', role: 'Champion',
      influence: 'High', stance: 'Support', coverage: 'Direct access',
    }])])
    const created = migrateLegacyOpportunityContacts([], [legacyOpportunity([{
      id: 'STK-NEW-EMAIL', name: 'New contact', title: 'Director', email: 'new@example.com', role: 'Champion',
      influence: 'High', stance: 'Support', coverage: 'Direct access',
    }])])

    expect(byEmail.opportunities[0].stakeholders[0].contactId).toBe('CT-EMAIL')
    expect(created.contacts[0]).toMatchObject({ id: 'CT-MIG-STK-NEW-EMAIL', email: 'new@example.com' })
  })

  it('does not reuse another account migration ID when legacy IDs collide', () => {
    const migrated = migrateLegacyOpportunityContacts([
      contact({ id: 'CT-MIG-STK-COLLISION', accountId: 'ACC-OTHER' }),
    ], [legacyOpportunity([{
      id: 'STK-COLLISION', name: 'New contact', title: 'Director', role: 'Champion',
      influence: 'High', stance: 'Support', coverage: 'Direct access',
    }])])

    const linkedId = migrated.opportunities[0].stakeholders[0].contactId
    expect(linkedId).not.toBe('CT-MIG-STK-COLLISION')
    expect(migrated.contacts.find((item) => item.id === linkedId)).toMatchObject({ accountId: 'ACC-001' })
  })

  it('expands Contact names without allowing stale relationship labels to persist', () => {
    const expanded = expandOpportunityContact({
      id: 'STK-004', contactId: 'CT-001', name: 'Stale', title: 'Stale', role: 'Champion',
      influence: 'High', stance: 'Support', coverage: 'Weekly sync',
    } satisfies OpportunityStakeholderDto, [contact({ name: 'Current Name', title: 'Current Title' })])

    expect(expanded).toMatchObject({ name: 'Current Name', title: 'Current Title', contactId: 'CT-001' })
  })

  it('normalizes a version-1 sales snapshot before exposing the memory repository', () => {
    const snapshot: SalesSnapshotV1 = {
      version: 1,
      bookings: [],
      visits: [],
      opportunities: [legacyOpportunity([{
        id: 'STK-SNAPSHOT', name: 'Snapshot contact', title: 'Director', role: 'Champion',
        influence: 'High', stance: 'Support', coverage: 'Direct access',
      }], 'ACC-NEW')],
    }

    const migrated = migrateSalesSnapshot(snapshot)
    const repository = createMemorySalesRepository(snapshot)

    expect(migrated).toMatchObject({ version: 7 })
    expect(migrated.opportunities[0].stakeholders[0].contactId).toBe('CT-MIG-STK-SNAPSHOT')
    expect(repository.snapshot).toEqual(migrated)
  })
})
