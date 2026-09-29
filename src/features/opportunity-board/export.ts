import type { CrmApi } from '@/api'
import type { Locale } from '@/i18n'
import type { CustomerWorkbookSpec } from '@/features/accounts/customer-report-model'
import type { BoardColumn, BoardGroup, BoardQuery, BoardResult } from './types'
import { cellText, fieldLabel, groupKey, optionLabel } from './model'

export async function readBoardExport(api: Pick<CrmApi, 'queryOpportunities'>, query: BoardQuery, cancelled: () => boolean = () => false): Promise<BoardResult> {
  let result: BoardResult | undefined, signature = '', total = 0
  const ids = new Set<string>()
  for (let page = 1; ; page++) {
    if (cancelled()) throw new Error('EXPORT_CANCELLED')
    const response = await api.queryOpportunities({ ...query, page, pageSize: 200 })
    if (cancelled()) throw new Error('EXPORT_CANCELLED')
    const currentTotal = response.meta?.total
    if (currentTotal == null || response.meta?.page !== page || !response.meta.pageSize) throw new Error('EXPORT_CHANGED')
    const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date(response.data.asOf))
    const currentSignature = JSON.stringify([currentTotal, response.data.summary, response.data.groups, day])
    if (!result) { result = { ...response.data, items: [] }; signature = currentSignature; total = currentTotal }
    if (signature !== currentSignature || (!response.data.items.length && ids.size < total)) throw new Error('EXPORT_CHANGED')
    for (const row of response.data.items) {
      if (ids.has(row.id)) throw new Error('EXPORT_CHANGED')
      ids.add(row.id); result.items.push(row)
    }
    if (ids.size > total) throw new Error('EXPORT_CHANGED')
    if (ids.size === total) return result
  }
}
export function boardWorkbook(result: BoardResult, columns: BoardColumn[], group: BoardGroup | null, locale: Locale): CustomerWorkbookSpec {
  const groups = group && result.groups.length ? result.groups : [{ key: null, label: 'Opportunities' }]
  const used = new Set<string>()
  return {
    fileName: `Opportunities_${result.asOf.slice(0, 10)}.xlsx`,
    sheets: groups.map(g => {
      const label = group && g.key != null ? optionLabel(group, g.key, g.label, locale) : g.key == null && group ? (locale === 'en-US' ? 'Not set' : '未填写') : g.label
      const base = label.replaceAll(String.fromCharCode(92), ' ').replace(/[\/:*?\[\]]/g, ' ').replace(/^'+|'+$/g, '').trim().slice(0, 31) || 'Opportunities'
      let name = base, index = 2
      while (used.has(name.toLocaleLowerCase())) { const suffix = ` (${index++})`; name = base.slice(0, 31 - suffix.length) + suffix }
      used.add(name.toLocaleLowerCase())
      const rows = group ? result.items.filter(row => groupKey(row, group) === g.key) : result.items
      return { name, columns: columns.map(c => ({ width: c === 'nextAction' || c === 'title' ? 42 : c === 'customerName' ? 30 : 23 })), merges: [], freezeRows: 1,
        rows: [columns.map(c => ({ v: fieldLabel(c, locale), s: 4 })),
          // CNY amounts are number cells (style 16, two decimals) so Excel can sum them.
          ...rows.map(row => columns.map(c => c === 'amountCny'
            ? { v: row.amountCny == null ? '' : Number(row.amountCny), s: 16 }
            : { v: cellText(row, c, locale), s: 5 }))] }
    }),
  }
}

