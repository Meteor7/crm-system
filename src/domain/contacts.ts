import type { ContactDto } from '@/types/crm'
import type {
  LegacyOpportunityStakeholderDto,
  LegacyStrategyOpportunityDto,
  OpportunityStakeholderDto,
  StrategyOpportunityDto,
} from '@/types/workspaces'

const normalized = (value: string | undefined) =>
  String(value ?? '').trim().toLocaleLowerCase().replace(/\s+/g, ' ')

export function formatContactDisplayLine(contact: ContactDto) {
  return [contact.name, contact.title, contact.email, contact.phone].filter((value) => value?.trim()).join(', ')
}

function hasUniqueMatch(
  candidates: readonly ContactDto[],
  predicate: (contact: ContactDto) => boolean,
): ContactDto | undefined {
  const matches = candidates.filter(predicate)
  return matches.length === 1 ? matches[0] : undefined
}

function findLegacyContact(
  stakeholder: LegacyOpportunityStakeholderDto,
  accountContacts: readonly ContactDto[],
): ContactDto | undefined {
  if (stakeholder.contactId) {
    const linkedContact = accountContacts.find((contact) => contact.id === stakeholder.contactId)
    if (linkedContact) return linkedContact
  }

  const email = normalized(stakeholder.email)
  if (email) {
    return hasUniqueMatch(accountContacts, (contact) => normalized(contact.email) === email)
  }

  const name = normalized(stakeholder.name)
  const title = normalized(stakeholder.title)
  return hasUniqueMatch(accountContacts, (contact) =>
    normalized(contact.name) === name && normalized(contact.title) === title,
  )
}

function createMigrationContact(
  stakeholder: LegacyOpportunityStakeholderDto,
  opportunity: LegacyStrategyOpportunityDto,
  id: string,
): ContactDto {
  return {
    id,
    accountId: opportunity.accountId,
    name: stakeholder.name,
    title: stakeholder.title,
    department: '',
    email: stakeholder.email,
    relationship: 'Developing',
    owner: opportunity.owner,
    status: 'Active',
    dataQuality: 'Needs Review',
    updatedAt: '2026-07-28',
  }
}

function migrationContactId(
  stakeholder: LegacyOpportunityStakeholderDto,
  opportunity: LegacyStrategyOpportunityDto,
  contacts: readonly ContactDto[],
): string {
  const baseId = `CT-MIG-${stakeholder.id}`
  if (!contacts.some((contact) => contact.id === baseId && contact.accountId !== opportunity.accountId)) {
    return baseId
  }

  const accountScopedId = `${baseId}-${opportunity.accountId}`
  let id = accountScopedId
  let suffix = 2
  while (contacts.some((contact) => contact.id === id && contact.accountId !== opportunity.accountId)) {
    id = `${accountScopedId}-${suffix}`
    suffix += 1
  }
  return id
}

export function expandOpportunityContact(
  link: OpportunityStakeholderDto,
  contacts: readonly ContactDto[],
): OpportunityStakeholderDto {
  const contact = contacts.find((item) => item.id === link.contactId)
  return {
    ...link,
    name: contact?.name ?? '联系人已缺失',
    title: contact?.title ?? '—',
  }
}

export function migrateLegacyOpportunityContacts(
  contacts: readonly ContactDto[],
  opportunities: readonly LegacyStrategyOpportunityDto[],
): { contacts: ContactDto[]; opportunities: StrategyOpportunityDto[] } {
  const migratedContacts = structuredClone([...contacts])
  const migratedOpportunities = structuredClone(opportunities).map((opportunity) => {
    const accountContacts = () => migratedContacts.filter((contact) => contact.accountId === opportunity.accountId)
    const stakeholders = opportunity.stakeholders.map((stakeholder) => {
      const matched = findLegacyContact(stakeholder, accountContacts())
      if (matched) {
        return { ...stakeholder, contactId: matched.id }
      }

      const migrationId = migrationContactId(stakeholder, opportunity, migratedContacts)
      const migrated = migratedContacts.find((contact) =>
        contact.id === migrationId && contact.accountId === opportunity.accountId,
      )
      if (migrated) return { ...stakeholder, contactId: migrated.id }

      const created = createMigrationContact(stakeholder, opportunity, migrationId)
      migratedContacts.push(created)
      return { ...stakeholder, contactId: created.id }
    })
    return { ...opportunity, stakeholders }
  })

  return { contacts: migratedContacts, opportunities: migratedOpportunities }
}

type LegacyPrimaryBooking = {
  id: string
  accountId: string
  owner: string
  customerContact?: string
  primaryContactId?: string
}

type LegacyPrimaryDemoRequest = {
  id: string
  accountId: string
  accountName?: string
  salesOwner: string
  primaryContactId?: string
  formData?: { contactPerson?: string }
}

function migrationPrimaryContact(
  contacts: ContactDto[],
  input: {
    id: string
    accountId: string
    name: string
    owner: string
    primaryContactId?: string
    prefix: 'BKG' | 'DR'
  },
) {
  const linked = input.primaryContactId
    ? contacts.find((contact) => contact.id === input.primaryContactId && contact.accountId === input.accountId)
    : undefined
  if (linked) return linked

  const accountContacts = contacts.filter((contact) => contact.accountId === input.accountId)
  const name = input.name.trim()
  const matched = name
    ? hasUniqueMatch(accountContacts, (contact) => normalized(contact.name) === normalized(name))
    : undefined
  if (matched) return matched

  const id = `CT-${input.prefix}-${input.id}`
  const existing = contacts.find((contact) => contact.id === id && contact.accountId === input.accountId)
  if (existing) return existing
  const created: ContactDto = {
    id,
    accountId: input.accountId,
    name: name || `${input.accountId} Contact`,
    title: '',
    department: '',
    relationship: 'Developing',
    owner: input.owner,
    status: 'Active',
    dataQuality: 'Needs Review',
    updatedAt: '2026-07-28',
  }
  contacts.push(created)
  return created
}

export function migrateLegacyPrimaryContacts<
  B extends LegacyPrimaryBooking,
  D extends LegacyPrimaryDemoRequest,
>(
  contacts: readonly ContactDto[],
  bookings: readonly B[],
  demoRequests: readonly D[],
): {
  contacts: ContactDto[]
  bookings: Array<B & { primaryContactId: string }>
  demoRequests: Array<D & { primaryContactId: string }>
} {
  const migratedContacts = structuredClone([...contacts])
  const migratedBookings = structuredClone([...bookings]).map((booking) => {
    const contact = migrationPrimaryContact(migratedContacts, {
      id: booking.id,
      accountId: booking.accountId,
      name: booking.customerContact ?? '',
      owner: booking.owner,
      primaryContactId: booking.primaryContactId,
      prefix: 'BKG',
    })
    return { ...booking, primaryContactId: contact.id }
  })
  const migratedDemoRequests = structuredClone([...demoRequests]).map((request) => {
    const retainedName = (request.formData?.contactPerson ?? `${request.accountName ?? request.accountId} Demo Contact`)
      .split(',')[0]
      .trim()
    const contact = migrationPrimaryContact(migratedContacts, {
      id: request.id,
      accountId: request.accountId,
      name: retainedName,
      owner: request.salesOwner,
      primaryContactId: request.primaryContactId,
      prefix: 'DR',
    })
    return { ...request, primaryContactId: contact.id }
  })
  return { contacts: migratedContacts, bookings: migratedBookings, demoRequests: migratedDemoRequests }
}
