import { describe, expect, it } from 'vitest'
import type { AccountSiteDto } from '@/types/crm'
import { sitesByAccountId, sitesInAccountOrder } from './account-sites'

const site = (id: string, accountId: string): AccountSiteDto => ({
  id, accountId, name: id, city: '上海', type: 'Fab', process: 'Frontend', status: '量产',
})

describe('account sites', () => {
  const accounts = [{ id: 'ACC-B' }, { id: 'ACC-A' }, { id: 'ACC-EMPTY' }]
  const sites = [site('S1', 'ACC-A'), site('S2', 'ACC-B'), site('S3', 'ACC-A'), site('S4', 'ACC-NOT-LISTED')]

  it('groups the Sites under each listed Account and gives an Account without Sites an empty list', () => {
    const grouped = sitesByAccountId(accounts, sites)

    expect(Object.keys(grouped)).toEqual(['ACC-B', 'ACC-A', 'ACC-EMPTY'])
    expect(grouped['ACC-A']!.map((item) => item.id)).toEqual(['S1', 'S3'])
    expect(grouped['ACC-B']).toEqual([{ id: 'S2', name: 'S2', city: '上海', type: 'Fab', process: 'Frontend', status: '量产' }])
    expect(grouped['ACC-EMPTY']).toEqual([])
  })

  it('lists the Sites in the order of the Accounts and leaves out an Account that is not listed', () => {
    expect(sitesInAccountOrder(accounts, sites).map((item) => `${item.accountId}/${item.id}`))
      .toEqual(['ACC-B/S2', 'ACC-A/S1', 'ACC-A/S3'])
  })
})
