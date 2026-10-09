import type { CrmApi } from '@/api'
import { readAllPages } from '@/features/shared/read-all-pages'
import type { ContactSummaryDto } from '@/types/crm'

/**
 * The active Contacts of an Account the pickers do not list (an archived Account and its Contacts are out of every
 * picker), read by its id, so that a correction of a record under it keeps its own Contact; none for a listed one.
 */
export async function ownAccountContacts(
  apiClient: CrmApi,
  listedAccountIds: Iterable<string>,
  accountId: string | undefined,
): Promise<ContactSummaryDto[]> {
  if (!accountId || new Set(listedAccountIds).has(accountId)) return []
  return readAllPages((page, pageSize) => apiClient.listContacts({ accountId, contactStatus: 'Active', page, pageSize }))
}

/** The Contacts read for the pickers, with those among `more` they do not have added. */
export function withContacts(contacts: ContactSummaryDto[], more: ContactSummaryDto[]): ContactSummaryDto[] {
  const known = new Set(contacts.map((contact) => contact.id))
  return [...contacts, ...more.filter((contact) => !known.has(contact.id))]
}

/** The Contacts an editor offers for a record under this Account: those read for the pickers and its own. */
export async function contactsWithOwnAccount(
  apiClient: CrmApi,
  contacts: ContactSummaryDto[],
  listedAccountIds: Iterable<string>,
  accountId: string | undefined,
): Promise<ContactSummaryDto[]> {
  return withContacts(contacts, await ownAccountContacts(apiClient, listedAccountIds, accountId))
}
