import type { AccountSummaryDto, BookingDto, ContactDto, LeadDto, SiteDto, VisitDto } from '@/types/crm'
import type { InstalledToolDto, LegacyStrategyOpportunityDto, OpportunityInternalValidationDto, StrategyOpportunityDto } from '@/types/workspaces'
import { accounts, bookings, contacts, sites, visits } from '@/api/mock-data'
import { installedTools as installedToolSeeds, opportunities, opportunityInternalValidations } from '@/demo/operations-data'
import { leads } from '@/demo/leads-data'
import { migrateLegacyOpportunityContacts, migrateLegacyPrimaryContacts } from '@/domain/contacts'
import { normalizeMoney } from '@/domain/money'
import { normalizeStoredRegion } from '@/domain/regions'
import { isOpportunityProbabilityLevelValue } from '@/domain/opportunity-probability'
import { isOpenOpportunityStage, isOpportunityStage, type OpportunityStage } from '@/domain/opportunity-stages'
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

/** Internal validation requests kept by the browser mock; the API exposes only the latest one per Opportunity. */
export interface StoredOpportunityInternalValidation extends OpportunityInternalValidationDto {
  opportunityId: string
}

type SevenStageOpportunityFields = 'stageChangedAt' | 'budgetApprovedOn' | 'lostAtStage' | 'lostAt' | 'lostBy' | 'stageHistory' | 'internalValidation' | 'liveBooking'

/**
 * Opportunity rows cached before the seven milestone stages. They may still carry a legacy stage,
 * the retired percentage probability and forecast, and no stage history.
 */
export type CachedLegacyStrategyOpportunityDto = Omit<StrategyOpportunityDto, 'stage' | 'probabilityLevel' | 'probabilityHistory' | 'amountCny' | SevenStageOpportunityFields>
  & Partial<Pick<StrategyOpportunityDto, 'probabilityLevel' | 'probabilityHistory' | 'amountCny' | SevenStageOpportunityFields>>
  & { stage: string; probability?: number; forecast?: string }

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
  opportunities: CachedLegacyStrategyOpportunityDto[]
}

export interface SalesSnapshotV3 {
  version: 3
  contacts: ContactDto[]
  bookings: LegacyBookingDto[]
  visits: VisitDto[]
  opportunities: CachedLegacyStrategyOpportunityDto[]
}

export interface SalesSnapshotV4 {
  version: 4
  leads: LeadDto[]
  contacts: ContactDto[]
  bookings: LegacyBookingDto[]
  visits: VisitDto[]
  opportunities: CachedLegacyStrategyOpportunityDto[]
}

export interface SalesSnapshotV5 {
  version: 5
  accounts: AccountSummaryDto[]
  sites: Record<string, SiteDto[]>
  leads: LeadDto[]
  contacts: ContactDto[]
  bookings: BookingDto[]
  installedTools: InstalledToolDto[]
  visits: VisitDto[]
  opportunities: CachedLegacyStrategyOpportunityDto[]
}

/** Version 6 replaced the Opportunity percentage probability and forecast with an owner-set level and its history. */
export interface SalesSnapshotV6 {
  version: 6
  accounts: AccountSummaryDto[]
  sites: Record<string, SiteDto[]>
  leads: LeadDto[]
  contacts: ContactDto[]
  bookings: BookingDto[]
  installedTools: InstalledToolDto[]
  visits: VisitDto[]
  opportunities: CachedLegacyStrategyOpportunityDto[]
}

/** Version 7 moved Opportunities onto the seven milestone stages, with stage history and internal validation requests. */
export interface SalesSnapshot {
  version: 7
  accounts: AccountSummaryDto[]
  sites: Record<string, SiteDto[]>
  leads: LeadDto[]
  contacts: ContactDto[]
  bookings: BookingDto[]
  installedTools: InstalledToolDto[]
  visits: VisitDto[]
  opportunities: StrategyOpportunityDto[]
  internalValidations: StoredOpportunityInternalValidation[]
}

export type StoredSalesSnapshot = SalesSnapshotV1 | SalesSnapshotV2 | SalesSnapshotV3 | SalesSnapshotV4 | SalesSnapshotV5 | SalesSnapshotV6 | SalesSnapshot

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
    item.probabilityHistory.forEach((entry) => { entry.actor = migrateLegacyUserId(entry.actor, 'opportunity.probabilityHistory.actor') })
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
    // Cached before Bookings carried the date on the customer's PO.
    actualPoDate: booking.actualPoDate ?? '',
    actualPoDateSource: booking.actualPoDateSource ?? '',
    actualPoDateNote: booking.actualPoDateNote ?? '',
    // A CNY order's amount already is its CNY amount; another currency keeps what was entered, or ''.
    amountCny: (booking.currency || 'CNY') === 'CNY'
      ? normalizeMoney(String(booking.amount))
      : booking.amountCny ? normalizeMoney(String(booking.amountCny)) : '',
    amountCnyNote: booking.amountCnyNote ?? '',
  }
}

// The percentage probability and forecast are retired, and stage moves now live in the stage history,
// so their generic change-history rows are dropped together with the retired values.
const RETIRED_OPPORTUNITY_HISTORY_FIELDS = new Set(['probability', 'forecast', 'stage', 'stagerollback'])

// Stages cached before the seven milestones, including the aliases the older vocabulary had already absorbed.
const LEGACY_OPPORTUNITY_STAGES: Record<string, OpportunityStage> = {
  '需求发现': 'qualified_opportunity',
  'Wafer Demo确认': 'qualified_opportunity',
  '预算审批': 'demo_done',
  '设备规格确认': 'customer_budget_approved',
  '报价': 'rfq_validated',
  '采购流程': 'quotation_sent',
  Won: 'po_received',
  Lost: 'lost',
  'Demo验证': 'qualified_opportunity',
  'Demo 验证': 'qualified_opportunity',
  '技术确认': 'qualified_opportunity',
}

function normalizeOpportunity(opportunity: CachedLegacyStrategyOpportunityDto | StrategyOpportunityDto): StrategyOpportunityDto {
  const cachedStage = String(opportunity.stage)
  const stage: OpportunityStage = isOpportunityStage(cachedStage)
    ? cachedStage
    : LEGACY_OPPORTUNITY_STAGES[cachedStage] ?? 'qualified_opportunity'
  const { probability: _retiredProbability, forecast: _retiredForecast, ...current } = opportunity as CachedLegacyStrategyOpportunityDto
  const lost = stage === 'lost'
  return {
    ...current,
    stage,
    stageChangedAt: current.stageChangedAt ?? '',
    // Old mock snapshots need a stable optimistic-lock token, not a new value on each read.
    modified: current.modified?.trim() || '1970-01-01T00:00:00.000Z',
    budgetApprovedOn: current.budgetApprovedOn ?? '',
    // A cached loss has no record of the stage it was lost at; reopening then stops at quotation sent.
    lostAtStage: lost && isOpenOpportunityStage(current.lostAtStage) ? current.lostAtStage : '',
    lostAt: lost ? current.lostAt ?? '' : '',
    lostBy: lost ? current.lostBy ?? '' : '',
    stageHistory: Array.isArray(current.stageHistory) ? current.stageHistory : [],
    internalValidation: current.internalValidation ?? null,
    liveBooking: current.liveBooking ?? null,
    // Regions cached before the shared options may still be spelled in Chinese.
    subRegion: normalizeStoredRegion(current.subRegion ?? ''),
    probabilityLevel: isOpportunityProbabilityLevelValue(current.probabilityLevel) ? current.probabilityLevel : '',
    // Snapshots cached before downgrade reasons carry history rows without one.
    probabilityHistory: Array.isArray(current.probabilityHistory)
      ? current.probabilityHistory.map((entry) => ({ ...entry, reason: typeof entry.reason === 'string' ? entry.reason : '' }))
      : [],
    history: current.history.filter((entry) => !RETIRED_OPPORTUNITY_HISTORY_FIELDS.has(String(entry.field).toLowerCase())),
    amount: normalizeMoney(String(current.amount)),
    originalAmount: normalizeMoney(String(current.originalAmount)),
    amountCny: current.amountCny === undefined ? legacyAmountCny(current) : current.amountCny && normalizeMoney(String(current.amountCny)),
  }
}

// Cached or seeded before the CNY amount: like the backend migration, an Opportunity priced in CNY
// takes its amount and any other currency waits for Sales to enter it.
function legacyAmountCny(opportunity: { currency: string; amount: string | number }): StrategyOpportunityDto['amountCny'] {
  return opportunity.currency === 'CNY' ? normalizeMoney(String(opportunity.amount)) : ''
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
    amountCny: legacyAmountCny(opportunity),
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
      item.accountId === booking.accountId,
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

// Seeded internal validations belong to seeded records only: the Opportunity and Booking must be the seeded ones.
function restoreCanonicalInternalValidations(snapshot: SalesSnapshot): SalesSnapshot {
  const restored = structuredClone(snapshot)
  restored.internalValidations = Array.isArray(restored.internalValidations) ? restored.internalValidations : []
  const canonicalOpportunities = seededOpportunities()
  for (const validation of opportunityInternalValidations) {
    if (restored.internalValidations.some((item) => item.id === validation.id)) continue
    const canonical = canonicalOpportunities.find((item) => item.id === validation.opportunityId)
    const opportunity = restored.opportunities.find((item) => item.id === validation.opportunityId)
    if (!canonical || opportunity?.accountId !== canonical.accountId) continue
    if (validation.bookingId && !restored.bookings.some((item) =>
      item.id === validation.bookingId && item.sourceOpportunityId === validation.opportunityId,
    )) continue
    restored.internalValidations.push(structuredClone(validation))
  }
  return restored
}

function removeRetiredLocalContacts(snapshot: SalesSnapshot): SalesSnapshot {
  snapshot = restoreCanonicalInternalValidations(restoreCanonicalSites(restoreBookingSourceOpportunities(snapshot)))
  const storedTools = (snapshot as SalesSnapshot & { installedTools?: InstalledToolDto[] }).installedTools
  snapshot = { ...snapshot, installedTools: storedTools?.length ? structuredClone(storedTools) : seededInstalledTools() }
  const normalizedBookings = snapshot.bookings.map(normalizeBooking)
  const normalizedSnapshot = {
    ...snapshot,
    accounts: snapshot.accounts.map((account) => ({ ...account, region: normalizeStoredRegion(account.region ?? '') })),
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
    opportunities: normalizedSnapshot.opportunities.map((opportunity) => ({
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
      region: normalizeStoredRegion(opportunity?.subRegion ?? ''),
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

export function migrateSalesSnapshot(snapshot: StoredSalesSnapshot): SalesSnapshot {
  if (snapshot.version === 7) return migrateSalesIdentityReferences(removeRetiredLocalContacts(restoreConvertedAccounts(snapshot)))
  if (snapshot.version === 6 || snapshot.version === 5) {
    return migrateSalesIdentityReferences(removeRetiredLocalContacts(restoreConvertedAccounts({
      ...structuredClone(snapshot),
      version: 7,
      opportunities: snapshot.opportunities.map(normalizeOpportunity),
      internalValidations: [],
    })))
  }
  if (snapshot.version === 4) {
    return migrateSalesIdentityReferences(removeRetiredLocalContacts(restoreConvertedAccounts({
      ...structuredClone(snapshot),
      version: 7,
      accounts: structuredClone(accounts),
      sites: structuredClone(sites),
      installedTools: seededInstalledTools(),
      bookings: snapshot.bookings.map(normalizeBooking),
      opportunities: snapshot.opportunities.map(normalizeOpportunity),
      internalValidations: [],
    })))
  }
  if (snapshot.version === 3) {
    return migrateSalesIdentityReferences(removeRetiredLocalContacts({
      ...structuredClone(snapshot),
      version: 7,
      accounts: structuredClone(accounts),
      sites: structuredClone(sites),
      leads: structuredClone(leads),
      installedTools: seededInstalledTools(),
      bookings: snapshot.bookings.map(normalizeBooking),
      opportunities: snapshot.opportunities.map(normalizeOpportunity),
      internalValidations: [],
    }))
  }
  const opportunityMigration: { contacts: ContactDto[]; opportunities: Array<CachedLegacyStrategyOpportunityDto | StrategyOpportunityDto> } = snapshot.version === 1
    ? migrateLegacyOpportunityContacts(contacts, snapshot.opportunities)
    : { contacts: snapshot.contacts, opportunities: snapshot.opportunities }
  const primaryMigration = migrateLegacyPrimaryContacts(opportunityMigration.contacts, snapshot.bookings, [])
  return migrateSalesIdentityReferences(removeRetiredLocalContacts({
    version: 7,
    accounts: structuredClone(accounts),
    sites: structuredClone(sites),
    leads: structuredClone(leads),
    contacts: primaryMigration.contacts,
    bookings: primaryMigration.bookings.map(normalizeBooking),
    installedTools: seededInstalledTools(),
    visits: structuredClone(snapshot.visits),
    opportunities: opportunityMigration.opportunities.map(normalizeOpportunity),
    internalValidations: [],
  }))
}

function seed(): SalesSnapshot {
  return migrateSalesSnapshot(legacySeed())
}

export function createMemorySalesRepository(snapshot: StoredSalesSnapshot = seed()): SalesRepository {
  return { snapshot: migrateSalesSnapshot(snapshot), save() {} }
}

let sharedRepository: SalesRepository | undefined

function isStoredSalesSnapshot(value: unknown): value is StoredSalesSnapshot {
  if (!value || typeof value !== 'object') return false
  const snapshot = value as { version?: unknown; accounts?: unknown; sites?: unknown; leads?: unknown; bookings?: unknown; visits?: unknown; opportunities?: unknown; internalValidations?: unknown }
  const version = snapshot.version
  return typeof version === 'number' && Number.isInteger(version) && version >= 1 && version <= 7
    && (version < 4 || Array.isArray(snapshot.leads))
    && (version < 5 || (Array.isArray(snapshot.accounts) && Boolean(snapshot.sites) && typeof snapshot.sites === 'object'))
    && (version < 7 || Array.isArray(snapshot.internalValidations))
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
