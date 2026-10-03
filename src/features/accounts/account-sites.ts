import type { AccountSiteDto, SiteDto } from '@/types/crm'

/** The Sites of each listed Account; an Account with no readable Site gets an empty list. */
export function sitesByAccountId(accounts: Array<{ id: string }>, sites: AccountSiteDto[]): Record<string, SiteDto[]> {
  const grouped: Record<string, SiteDto[]> = Object.fromEntries(accounts.map((account) => [account.id, []]))
  for (const { accountId, ...site } of sites) grouped[accountId]?.push(site)
  return grouped
}

/** The Sites of the listed Accounts as one list, in the order of the Accounts. */
export function sitesInAccountOrder(accounts: Array<{ id: string }>, sites: AccountSiteDto[]): AccountSiteDto[] {
  const grouped = sitesByAccountId(accounts, sites)
  return accounts.flatMap((account) => grouped[account.id]!.map((site) => ({ ...site, accountId: account.id })))
}
