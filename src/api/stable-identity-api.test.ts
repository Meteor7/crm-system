import { describe, expect, it } from 'vitest'
import { CrmApiError } from './contracts'
import { createMockApi } from './mock-adapter'

describe('Mock API stable identity boundary', () => {
  it('returns the explicit active Frappe User id in Bootstrap', async () => {
    const api = createMockApi({
      latency: 0,
      role: 'Sales',
      userId: 'person002@crm.example.invalid',
      userName: 'Demo Staff 01',
    })
    expect((await api.getBootstrap()).data.user).toMatchObject({
      id: 'person002@crm.example.invalid',
      name: 'Demo Staff 01',
      role: 'Sales',
    })
  })

  it('exposes stable owner ids from repository-backed records', async () => {
    const api = createMockApi({ latency: 0 })
    const accounts = await api.listAccounts({ pageSize: 100 })
    expect(accounts.data.items.length).toBeGreaterThan(0)
    expect(accounts.data.items.every((item) => item.owner.endsWith('@crm.example.invalid'))).toBe(true)
    expect(accounts.data.items.some((item) => item.owner === 'Demo Staff 01')).toBe(false)
  })

  it('rejects a display name at the write boundary', async () => {
    const api = createMockApi({ latency: 0 })
    await expect(api.createAccount({
      name: 'Stable ID account', shortName: 'STABLE', segment: 'Frontend', tier: 'A',
      city: '上海', region: '华东', owner: 'Demo Staff 01',
    })).rejects.toBeInstanceOf(CrmApiError)
  })
})
