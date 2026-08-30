import type { AccountSummaryDto, BookingDto, ContactDto, LeadDto, SiteDto, VisitDto } from '@/types/crm'
import { STRATEGY_OPPORTUNITY_STAGES, type InstalledToolDto, type LegacyStrategyOpportunityDto, type StrategyOpportunityDto, type StrategyOpportunityStage } from '@/types/workspaces'
import { accounts, bookings, contacts, sites, visits } from '@/api/mock-data'
import { installedTools as installedToolSeeds, opportunities } from '@/demo/operations-data'
import { leads } from '@/demo/leads-data'
import { migrateLegacyOpportunityContacts, migrateLegacyPrimaryContacts } from '@/domain/contacts'
import { normalizeMoney } from '@/domain/money'
import { migrateLegacyUserId, migrateOptionalLegacyUserId } from './identity-migration'

const STORAGE_KEY = 'semicrm:sales-workspace:v1'
const RETIRED_LOCAL_CONTACT_NAMES = new Set([
  '王志远',
  '陈珂',
  '赵昕',
  '李敏',
  '周楠',
  '顾晓',
  '马会东',
  '孙强',
  '钱宇',
  '演示员工20',
  '演示员工17',
  '示例企业040有限公司 Demo Contact',
  '示例企业003有限公司 Demo Contact',
  '示例企业027有限公司 Demo Contact',
  '示例企业045有限公司 Demo Contact',
  '示例企业018有限公司 Demo Contact',
])

export function isRetiredLocalContact(contact: Pick<ContactDto, 'name' | 'dataQuality'>) {
  return contact.dataQuality === 'Needs Review' && RETIRED_LOCAL_CONTACT_NAMES.has(contact.name.trim())
}

export type LegacyBookingDto = Omit<BookingDto, 'primaryContactId' | 'source' | 'bookingType'> & {
  primaryContactId?: string
  source?: BookingDto['source']
  bookingType?: 'Equipment' | 'Service' | 'Renewal' | 'Maintenance'
  directSource?: string
  directReason?: string
}

export interface SalesSnapshotV1 {
  version: 1
  bookings: LegacyBookingDto[]
  visits: VisitDto[]
  opportunities: LegacyStrategyOpportunityDto[]
}

export interface SalesSnapshotV2 {
  version: 2
  contacts: ContactDto[]
  bookings: LegacyBookingDto[]
  visits: VisitDto[]
  opportunities: StrategyOpportunityDto[]
}

export interface SalesSnapshotV3 {
  version: 3
  contacts: ContactDto[]
  bookings: LegacyBookingDto[]
  visits: VisitDto[]
  opportunities: StrategyOpportunityDto[]
}

export interface SalesSnapshotV4 {
  version: 4
  leads: LeadDto[]
  contacts: ContactDto[]
  bookings: LegacyBookingDto[]
  visits: VisitDto[]
  opportunities: StrategyOpportunityDto[]
}

export interface SalesSnapshot {
  version: 5
  accounts: AccountSummaryDto[]
  sites: Record<string, SiteDto[]>
  leads: LeadDto[]
  contacts: ContactDto[]
  bookings: BookingDto[]
  installedTools: InstalledToolDto[]
  visits: VisitDto[]
  opportunities: StrategyOpportunityDto[]
}

export interface SalesRepository {
  snapshot: SalesSnapshot
  save(): void
}

function migrateSalesIdentityReferences(snapshot: SalesSnapshot): SalesSnapshot {
  const migrated = structuredClone(snapshot)
  migrated.accounts.forEach((item) => { item.owner = migrateLegacyUserId(item.owner, 'account.owner') })
  migrated.leads.forEach((item) => { item.owner = migrateLegacyUserId(item.owner, 'lead.owner') })
  migrated.contacts.forEach((item) => { item.owner = migrateLegacyUserId(item.owner, 'contact.owner') })
  migrated.bookings.forEach((item) => { item.owner = migrateLegacyUserId(item.owner, 'booking.owner') })
  migrated.visits.forEach((item) => {
    item.owner = migrateLegacyUserId(item.owner, 'visit.owner')
    item.actionOwner = migrateOptionalLegacyUserId(item.actionOwner, 'visit.actionOwner') ?? ''
  })
  migrated.installedTools.forEach((item) => {
    item.salesOwner = migrateLegacyUserId(item.salesOwner, 'installedTool.salesOwner')
    item.engineerOwner = migrateLegacyUserId(item.engineerOwner, 'installedTool.engineerOwner')
  })
  migrated.opportunities.forEach((item) => {
    item.owner = migrateLegacyUserId(item.owner, 'opportunity.owner')
    item.history.forEach((entry) => { entry.actor = migrateLegacyUserId(entry.actor, 'opportunity.history.actor') })
    item.actions.forEach((action) => { action.owner = migrateLegacyUserId(action.owner, 'opportunity.action.owner') })
  })
  return migrated
}

function normalizeBooking(booking: LegacyBookingDto | BookingDto): BookingDto {
  return {
    ...booking,
    amount: normalizeMoney(String(booking.amount)),
    currency: booking.currency || 'CNY',
    primaryContactId: booking.primaryContactId ?? '',
    source: booking.source ?? (booking.sourceOpportunityId ? 'Opportunity' : 'Upsell'),
    bookingType: booking.bookingType === 'Service' ? 'Service' : 'Equipment',
  }
}

function normalizeOpportunity(opportunity: StrategyOpportunityDto): StrategyOpportunityDto {
  const legacyStages: Record<string, StrategyOpportunityStage> = {
    'Demo验证': 'Wafer Demo确认',
    'Demo 验证': 'Wafer Demo确认',
    '技术确认': '设备规格确认',
  }
  const stage = STRATEGY_OPPORTUNITY_STAGES.includes(opportunity.stage)
    ? opportunity.stage
    : legacyStages[String(opportunity.stage)] ?? '需求发现'
  return {
    ...opportunity,
    stage,
    amount: normalizeMoney(String(opportunity.amount)),
    originalAmount: normalizeMoney(String(opportunity.originalAmount)),
  }
}

function seededInstalledTools(): InstalledToolDto[] {
  const salesOwners = ['Demo Staff 02', 'Demo Staff 01', 'Demo Staff 02']
  const engineerOwners = ['演示员工14', '演示员工15', '演示员工15']
  return structuredClone(installedToolSeeds).map((tool, index) => ({
    id: tool.id,
    accountId: tool.accountId,
    siteId: tool.siteId,
    serial: tool.serial,
    model: tool.model,
    account: tool.account,
    site: tool.site,
    location: tool.location,
    status: tool.status,
    software: tool.software,
    firmware: '待确认',
    warrantyEnd: tool.warrantyEnd,
    completeness: tool.health,
    sourceBookingId: '',
    sourceOpportunityId: tool.sourceOpportunityId,
    salesOwner: salesOwners[index],
    engineerOwner: engineerOwners[index],
    salesOrder: tool.salesOrder,
    contract: tool.contract,
    warrantyStart: tool.warrantyStart,
    serviceContract: tool.serviceContract,
    pmCycle: tool.pmCycle,
    lastService: tool.lastService,
    operatingSystem: tool.operatingSystem,
    configuration: tool.configuration,
    ownershipType: tool.ownershipType,
    milestones: tool.milestones,
    documents: tool.documents,
  }))
}

function seededOpportunities(): StrategyOpportunityDto[] {
  return structuredClone(opportunities).map((opportunity) => ({
    ...opportunity,
    amount: normalizeMoney(String(opportunity.amount)),
    originalAmount: normalizeMoney(String(opportunity.originalAmount)),
    stakeholders: opportunity.stakeholders.map((stakeholder, index) => ({
      ...stakeholder,
      id: stakeholder.id ?? `STK-${opportunity.id}-${index + 1}`,
    })),
    actions: opportunity.actions.map((action, index) => ({
      ...action,
      id: action.id ?? `ACT-${opportunity.id}-${index + 1}`,
    })),
  })) as StrategyOpportunityDto[]
}

function restoreBookingSourceOpportunities(snapshot: SalesSnapshot): SalesSnapshot {
  const restored = structuredClone(snapshot)
  const canonical = seededOpportunities()
  for (const booking of restored.bookings) {
    if (!booking.sourceOpportunityId || restored.opportunities.some((item) => item.id === booking.sourceOpportunityId)) continue
    const source = canonical.find((item) =>
      item.id === booking.sourceOpportunityId &&
      item.accountId === booking.accountId &&
      item.stage === 'Won',
    )
    if (source) restored.opportunities.push(source)
  }
  return restored
}

function restoreCanonicalSites(snapshot: SalesSnapshot): SalesSnapshot {
  const restored = structuredClone(snapshot)
  for (const [accountId, canonicalSites] of Object.entries(sites)) {
    const existing = restored.sites[accountId] ?? []
    const existingIds = new Set(existing.map((site) => site.id))
    restored.sites[accountId] = [
      ...existing,
      ...structuredClone(canonicalSites.filter((site) => !existingIds.has(site.id))),
    ]
  }
  return restored
}

function removeRetiredLocalContacts(snapshot: SalesSnapshot): SalesSnapshot {
  snapshot = restoreCanonicalSites(restoreBookingSourceOpportunities(snapshot))
  const storedTools = (snapshot as SalesSnapshot & { installedTools?: InstalledToolDto[] }).installedTools
  snapshot = { ...snapshot, installedTools: storedTools?.length ? structuredClone(storedTools) : seededInstalledTools() }
  const normalizedBookings = snapshot.bookings.map(normalizeBooking)
  const normalizedSnapshot = {
    ...snapshot,
    bookings: normalizedBookings,
    opportunities: snapshot.opportunities.map(normalizeOpportunity),
  }
  const deletedContacts = snapshot.contacts.filter((contact) =>
    isRetiredLocalContact(contact),
  )
  const deletedIds = new Set(deletedContacts.map((contact) => contact.id))
  const retainedContacts = snapshot.contacts.filter((contact) => !deletedIds.has(contact.id))
  const hasBrokenBookingLink = normalizedBookings.some((booking) =>
    !retainedContacts.some((contact) => contact.id === booking.primaryContactId),
  )
  const hasLegacyBooking = snapshot.bookings.some((booking) => !booking.source)
  if (!deletedContacts.length && !hasBrokenBookingLink && !hasLegacyBooking) return normalizedSnapshot
  const replacementFor = (accountId: string, name: string) =>
    retainedContacts.find((contact) =>
      contact.accountId === accountId &&
      contact.status === 'Active' &&
      contact.name.trim().toLocaleLowerCase() === name.trim().toLocaleLowerCase(),
    ) ?? retainedContacts.find((contact) => contact.accountId === accountId && contact.status === 'Active')

  return {
    ...normalizedSnapshot,
    contacts: retainedContacts.map((contact) => {
      if (!deletedIds.has(contact.reportsToContactId ?? '') && !deletedIds.has(contact.reportsTo ?? '')) return contact
      const cleaned = { ...contact }
      delete cleaned.reportsToContactId
      delete cleaned.reportsTo
      return cleaned
    }),
    bookings: normalizedBookings.map((booking) => {
      if (!deletedIds.has(booking.primaryContactId) && retainedContacts.some((contact) => contact.id === booking.primaryContactId)) return booking
      const deleted = deletedContacts.find((contact) => contact.id === booking.primaryContactId)
      const replacement = replacementFor(booking.accountId, deleted?.name ?? booking.customerContact)
      return {
        ...booking,
        primaryContactId: replacement?.id ?? '',
        customerContact: replacement?.name ?? booking.customerContact,
      }
    }),
    opportunities: snapshot.opportunities.map((opportunity) => ({
      ...opportunity,
      stakeholders: opportunity.stakeholders.filter((stakeholder) => !deletedIds.has(stakeholder.contactId)),
    })),
  }
}

function restoreConvertedAccounts(snapshot: SalesSnapshot): SalesSnapshot {
  const restored = structuredClone(snapshot)
  const accountIds = new Set(restored.accounts.map((account) => account.id))
  restored.leads.filter((lead) =>
    lead.status === 'Converted' &&
    Boolean(lead.convertedAccountId) &&
    !accountIds.has(lead.convertedAccountId!),
  ).forEach((lead) => {
    const accountId = lead.convertedAccountId!
    const opportunity = restored.opportunities.find((item) =>
      item.id === lead.convertedOpportunityId || item.accountId === accountId,
    )
    const siteId = opportunity?.siteId ||
      restored.contacts.find((contact) => contact.accountId === accountId)?.siteId ||
      `${accountId}-SITE-01`
    restored.accounts.push({
      id: accountId,
      name: lead.company,
      shortName: lead.company.replace(/[（(].*$/, '').slice(0, 12),
      segment: 'Frontend',
      tier: 'B',
      city: '待补全',
      region: opportunity?.subRegion || 'China',
      owner: lead.owner,
      pipelineAmount: 0,
      intentScore: opportunity?.score ?? 50,
      stakeholderCount: restored.contacts.filter((contact) => contact.accountId === accountId).length,
      siteCount: 1,
      requirementCount: 0,
      completeness: 45,
      risk: '关注',
      nextAction: lead.nextAction || '补齐客户档案',
      nextActionDue: lead.nextActionDue,
      updatedAt: lead.updatedAt,
    })
    restored.sites[accountId] = [{
      id: siteId,
      name: opportunity?.site || `${lead.company} Main Site`,
      city: '待补全',
      type: 'Fab',
      process: '待确认',
      status: '规划中',
    }]
    accountIds.add(accountId)
  })
  return restored
}

function legacySeed(): SalesSnapshotV1 {
  return {
    version: 1,
    bookings: structuredClone(bookings),
    visits: structuredClone(visits),
    opportunities: seededOpportunities() as LegacyStrategyOpportunityDto[],
  }
}

export function migrateSalesSnapshot(snapshot: SalesSnapshotV1 | SalesSnapshotV2 | SalesSnapshotV3 | SalesSnapshotV4 | SalesSnapshot): SalesSnapshot {
  if (snapshot.version === 5) return migrateSalesIdentityReferences(removeRetiredLocalContacts(restoreConvertedAccounts(snapshot)))
  if (snapshot.version === 4) {
    return migrateSalesIdentityReferences(removeRetiredLocalContacts(restoreConvertedAccounts({
      ...structuredClone(snapshot),
      version: 5,
      accounts: structuredClone(accounts),
      sites: structuredClone(sites),
      installedTools: seededInstalledTools(),
      bookings: snapshot.bookings.map(normalizeBooking),
    })))
  }
  if (snapshot.version === 3) {
    return migrateSalesIdentityReferences(removeRetiredLocalContacts({
      ...structuredClone(snapshot),
      version: 5,
      accounts: structuredClone(accounts),
      sites: structuredClone(sites),
      leads: structuredClone(leads),
      installedTools: seededInstalledTools(),
      bookings: snapshot.bookings.map(normalizeBooking),
    }))
  }
  const opportunityMigration = snapshot.version === 1
    ? migrateLegacyOpportunityContacts(contacts, snapshot.opportunities)
    : { contacts: snapshot.contacts, opportunities: snapshot.opportunities }
  const primaryMigration = migrateLegacyPrimaryContacts(opportunityMigration.contacts, snapshot.bookings, [])
  return migrateSalesIdentityReferences(removeRetiredLocalContacts({
    version: 5,
    accounts: structuredClone(accounts),
    sites: structuredClone(sites),
    leads: structuredClone(leads),
    contacts: primaryMigration.contacts,
    bookings: primaryMigration.bookings.map(normalizeBooking),
    installedTools: seededInstalledTools(),
    visits: structuredClone(snapshot.visits),
    opportunities: opportunityMigration.opportunities,
  }))
}

function seed(): SalesSnapshot {
  return migrateSalesSnapshot(legacySeed())
}

export function createMemorySalesRepository(snapshot: SalesSnapshotV1 | SalesSnapshotV2 | SalesSnapshotV3 | SalesSnapshotV4 | SalesSnapshot = seed()): SalesRepository {
  return { snapshot: migrateSalesSnapshot(snapshot), save() {} }
}

let sharedRepository: SalesRepository | undefined

function isStoredSalesSnapshot(value: unknown): value is SalesSnapshotV1 | SalesSnapshotV2 | SalesSnapshotV3 | SalesSnapshotV4 | SalesSnapshot {
  if (!value || typeof value !== 'object') return false
  const snapshot = value as { version?: number; accounts?: unknown; sites?: unknown; leads?: unknown; bookings?: unknown; visits?: unknown; opportunities?: unknown }
  return (snapshot.version === 1 || snapshot.version === 2 || snapshot.version === 3 || snapshot.version === 4 || snapshot.version === 5)
    && (snapshot.version < 4 || Array.isArray(snapshot.leads))
    && (snapshot.version !== 5 || (Array.isArray(snapshot.accounts) && Boolean(snapshot.sites) && typeof snapshot.sites === 'object'))
    && Array.isArray(snapshot.bookings)
    && Array.isArray(snapshot.visits)
    && Array.isArray(snapshot.opportunities)
}

export function getSharedSalesRepository(): SalesRepository {
  if (sharedRepository) return sharedRepository
  let snapshot = seed()
  let migratedFromLegacy = false
  if (typeof window !== 'undefined') {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY)
      const parsed = stored ? JSON.parse(stored) as unknown : null
      if (isStoredSalesSnapshot(parsed)) {
        const migrated = migrateSalesSnapshot(parsed)
        migratedFromLegacy = JSON.stringify(migrated) !== JSON.stringify(parsed)
        snapshot = migrated
      }
    } catch {
      // Invalid demo cache falls back to the checked-in seed.
    }
  }
  sharedRepository = {
    snapshot,
    save() {
      if (typeof window === 'undefined') return
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot))
    },
  }
  if (migratedFromLegacy) sharedRepository.save()
  return sharedRepository
}
