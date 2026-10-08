import type { CrmApi } from '@/api'
import type { Locale } from '@/i18n'
import type { CustomerWorkbookSpec } from '@/features/accounts/customer-report-model'
import type { BoardColumn, BoardDefinition, BoardGroup, BoardQuery, BoardResult } from './types'
import { cellText, fieldLabel, groupKey, optionLabel } from './model'

export async function readBoardExport(api: Pick<CrmApi, 'exportOpportunities'>, query: BoardQuery, cancelled: () => boolean = () => false): Promise<BoardResult> {
  if (cancelled()) throw new Error('EXPORT_CANCELLED')
  const response = await api.exportOpportunities(query)
  if (cancelled()) throw new Error('EXPORT_CANCELLED')
  const result = response.data
  if (result.items.length !== result.summary.count || new Set(result.items.map(row => row.id)).size !== result.items.length) throw new Error('EXPORT_CHANGED')
  return result
}
function dateCell(value: string | null | undefined) {
  if (!value) return { v: '', s: 12 }
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value)).map(part => [part.type, part.value]))
  return { v: (Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day)) - Date.UTC(1899, 11, 30)) / 86400000, s: 12 }
}
function amountInMillions(value: string): number | string {
  // Shift the decimal point in the source string before touching binary floats.
  // Totals can exceed the per-record DECIMAL(20,2) limit. Excel preserves only
  // 15 significant digits; keep larger exact amounts as text, including totals.
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) throw new Error('Invalid CNY amount')
  const [whole, fraction = ''] = value.split('.')
  const cents = (whole + fraction.padEnd(2, '0')).replace(/^0+/, '') || '0'
  const scaled = cents.padStart(9, '0')
  const decimals = scaled.slice(-8).replace(/0+$/, '')
  const exact = scaled.slice(0, -8) + (decimals ? `.${decimals}` : '')
  const numeric = Number(exact)
  return cents.replace(/0+$/, '').length <= 15 && Number.isFinite(numeric) ? numeric : exact
}
function sheetPrefix(value: string, limit: number) {
  // Stay within Excel's UTF-16 length limit without splitting a surrogate pair.
  return value.slice(0, limit).replace(/[\uD800-\uDBFF]$/, '')
}
export function boardWorkbook(result: BoardResult, columns: BoardColumn[], group: BoardGroup | null, locale: Locale, queryName = 'Opportunities', definition?: BoardDefinition): CustomerWorkbookSpec {
  const groups = group && result.groups.length ? result.groups : [{ key: null, label: 'Opportunities' }]
  const used = new Set<string>(['summary'])
  const say = (en: string, zh: string) => locale === 'en-US' ? en : zh
  const safeName = Array.from(queryName.replace(/[\x00-\x1f\x7f\\/:*?<>|"]/g, ' ').trim()).slice(0, 80).join('') || 'Opportunities'
  // Saved definitions may exceed Excel's 32,767-character cell limit. Preserve
  // the complete definition in numbered cells rather than silently truncating it.
  const definitionParts = (definition ? JSON.stringify(definition) : '').match(/[\s\S]{1,16000}/gu) ?? ['']
  return {
    fileName: `Opportunities_${safeName}_${result.asOf.slice(0, 10)}.xlsx`,
    sheets: [{ name: 'Summary', columns: [{ width: 30 }, { width: 95 }], merges: [], freezeRows: 1, rows: [
      [{ v: say('Query export', '查询导出'), s: 4 }, { v: queryName, s: 4 }],
      [{ v: say('As of (UTC)', '数据时间（UTC）'), s: 5 }, { v: result.asOf, s: 5 }],
      [{ v: say('Matching opportunities', '匹配商机数'), s: 5 }, { v: result.summary.count, s: 5 }],
      [{ v: say('Known amount · CNY million', '已知金额 · 人民币百万元'), s: 5 }, { v: amountInMillions(result.summary.knownAmountCny), s: 17 }],
      [{ v: say('Missing CNY amounts', '人民币金额缺失数'), s: 5 }, { v: result.summary.missingAmountCount, s: 5 }],
      ...definitionParts.map((part, index) => [{ v: say('Scope and conditions', '范围与条件') + (definitionParts.length > 1 ? ` (${index + 1}/${definitionParts.length})` : ''), s: 5 }, { v: part, s: 14 }]),
      [{ v: say('Notes', '说明'), s: 5 }, { v: say('Amounts are unweighted. Amounts exceeding Excel numeric precision are exact text in CNY millions. Unknown amounts and dates are blank. Business dates use UTC+8; last-activity dates with incomplete evidence are blank. Rows and totals come from one server read.', '金额不加权；超出 Excel 数字精度的金额以人民币百万元的精确文本保存。未知金额及日期留空。业务日期使用 UTC+8；证据不完整的最后活动日期留空。明细与汇总来自一次服务端读取。'), s: 14 }],
    ] }, ...groups.map(g => {
      const label = group && g.key != null ? optionLabel(group, g.key, g.label, locale) : g.key == null && group ? (locale === 'en-US' ? 'Not set' : '未填写') : g.label
      const base = sheetPrefix(label.replaceAll(String.fromCharCode(92), ' ').replace(/[\/:*?\[\]]/g, ' ').replace(/^'+|'+$/g, '').trim(), 31) || 'Opportunities'
      let name = base, index = 2
      while (used.has(name.toLocaleLowerCase())) { const suffix = ` (${index++})`; name = sheetPrefix(base, 31 - suffix.length) + suffix }
      used.add(name.toLocaleLowerCase())
      const rows = group ? result.items.filter(row => groupKey(row, group) === g.key) : result.items
      return { name, columns: columns.map(c => ({ width: c === 'nextAction' || c === 'title' ? 42 : c === 'customerName' ? 30 : 23 })), merges: [], freezeRows: 1,
        rows: [columns.map(c => ({ v: c === 'amountCny' ? say('Value · CNY million', '金额 · 人民币百万元') : fieldLabel(c, locale), s: 4 })),
          // Typed number/date cells; arbitrary business text remains inlineStr in the writer, never a formula.
          ...rows.map(row => columns.map(c => c === 'amountCny'
            ? { v: row.amountCny == null ? '' : amountInMillions(row.amountCny), s: 17 }
            : c === 'stageChangedAt' || c === 'createdAt' || c === 'poDate' || c === 'lastActivityAt'
              ? dateCell(c === 'lastActivityAt' && row.lastActivityIncomplete ? null : row[c])
            : { v: cellText(row, c, locale), s: 5 }))] }
    })],
  }
}

