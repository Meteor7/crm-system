import type { ApiResponse, PageData } from '@/types/crm'

export async function readAllPages<T>(
  readPage: (page: number, pageSize: number) => Promise<ApiResponse<PageData<T>>>,
  pageSize = 200,
): Promise<T[]> {
  const items: T[] = []
  let page = 1
  while (true) {
    const result = await readPage(page, pageSize)
    items.push(...result.data.items)
    const total = result.meta?.total
    if (typeof total === 'number' ? items.length >= total : result.data.items.length < pageSize) break
    if (result.data.items.length === 0) break
    page += 1
  }
  return items
}
