import { describe, expect, it } from 'vitest'
import { createMockApi } from './mock-adapter'

describe('array list pagination contract', () => {
  it('returns PageData and total metadata for every migrated list API', async () => {
    const api = createMockApi({ latency: 0, role: 'Manager' })
    const results = await Promise.all([
      api.listStrategyOpportunities({ page: 1, pageSize: 1 }),
      api.listDemoWorkflows({ page: 1, pageSize: 1 }),
      api.listDemoComments('DR-105', { page: 1, pageSize: 1 }),
      api.listInstalledTools({ page: 1, pageSize: 1 }),
      api.listControlledDocuments({ page: 1, pageSize: 1 }),
      api.listContactFiles('CON-001', { page: 1, pageSize: 1 }),
    ])

    for (const result of results) {
      expect(result.data.items.length).toBeLessThanOrEqual(1)
      expect(result.meta).toMatchObject({ page: 1, pageSize: 1 })
      expect(result.meta?.total).toEqual(expect.any(Number))
    }
  })

  it('caps pageSize at 200 and reports total before slicing', async () => {
    const result = await createMockApi({ latency: 0, role: 'Manager' })
      .listDemoWorkflows({ page: 2, pageSize: 999 })

    expect(result.data.items).toEqual([])
    expect(result.meta).toMatchObject({ page: 2, pageSize: 200, total: 10 })
  })
})
