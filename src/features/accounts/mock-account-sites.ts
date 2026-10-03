import { vi } from 'vitest'
import type { CrmApi } from '@/api'
import type { AccountSiteDto } from '@/types/crm'

/** Test fixture: the Sites the client's Account 360 holds for each Account it lists. */
export async function accountSitesOf(api: CrmApi): Promise<AccountSiteDto[]> {
  const accounts = (await api.listAccounts({ page: 1, pageSize: 200 })).data.items
  const details = await Promise.all(accounts.map((account) => api.getAccount360(account.id)))
  return details.flatMap((detail) => detail.data.sites.map((site) => ({ ...site, accountId: detail.data.account.id })))
}

/**
 * Stubs `listAccountSites`, which the mock client does not implement, to answer with `accountSitesOf` at the
 * time of each call. Returns the client, so it wraps `createMockApi(...)`.
 */
export async function withAccountSites<T extends CrmApi>(api: T): Promise<T> {
  vi.spyOn(api as CrmApi, 'listAccountSites').mockImplementation(async () => ({ data: await accountSitesOf(api), warnings: [] }))
  return api
}
