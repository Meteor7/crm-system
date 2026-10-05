import type { ApiResponse, PageData } from '@/types/crm'

export async function readAllPages<T>(
  readPage: (page: number, pageSize: number) => Promise<ApiResponse<PageData<T>>>,
  pageSize = 200,
): Promise<T[]> {
  return (await readAllPagesWithFirst(readPage, pageSize)).items
}

/** readAllPages that also hands back the first response, for a page that shows its warnings and staleness. */
export async function readAllPagesWithFirst<T>(
  readPage: (page: number, pageSize: number) => Promise<ApiResponse<PageData<T>>>,
  pageSize = 200,
): Promise<{ items: T[]; first: ApiResponse<PageData<T>> }> {
  const items: T[] = []
  let first: ApiResponse<PageData<T>> | undefined
  let page = 1
  while (true) {
    const result = await readPage(page, pageSize)
    first ??= result
    items.push(...result.data.items)
    const total = result.meta?.total
    if (typeof total === 'number' ? items.length >= total : result.data.items.length < pageSize) break
    if (result.data.items.length === 0) break
    page += 1
  }
  return { items, first: first! }
}
