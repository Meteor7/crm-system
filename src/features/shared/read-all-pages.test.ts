import { describe, expect, it, vi } from 'vitest'
import { readAllPages } from './read-all-pages'

describe('readAllPages', () => {
  it('continues until response meta.total is reached', async () => {
    const readPage = vi.fn(async (page: number, pageSize: number) => ({
      data: { items: page === 1 ? Array.from({ length: 200 }, (_, index) => index) : [200] },
      meta: { requestId: `req-${page}`, page, pageSize, total: 201 },
      warnings: [],
    }))

    const items = await readAllPages(readPage)

    expect(items).toHaveLength(201)
    expect(readPage).toHaveBeenNthCalledWith(1, 1, 200)
    expect(readPage).toHaveBeenNthCalledWith(2, 2, 200)
  })

  it('stops on a short page when legacy responses omit total', async () => {
    const readPage = vi.fn(async () => ({ data: { items: ['only'] }, warnings: [] }))
    await expect(readAllPages(readPage)).resolves.toEqual(['only'])
    expect(readPage).toHaveBeenCalledTimes(1)
  })
})
