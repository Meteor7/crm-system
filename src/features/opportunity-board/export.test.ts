import { describe, expect, it, vi } from 'vitest'
import { boardResultFixture } from './fixtures'
import { defaultDefinition, toQuery } from './model'
import { boardWorkbook, readBoardExport } from './export'
import { buildXlsxFile } from '@/features/accounts/xlsx-writer'
describe('full-result board export', () => {
  function page(n: number, id: string) {
    const result = boardResultFixture()
    result.meta = { ...result.meta!, page: n, pageSize: 1, total: 2 }
    result.data.items = [{ ...result.data.items[0], id }]
    result.data.summary.count = 2
    return result
  }
  it('reads every page using the identical filters', async () => {
    const queryOpportunities = vi.fn().mockResolvedValueOnce(page(1, 'a')).mockResolvedValueOnce(page(2, 'b'))
    const result = await readBoardExport({ queryOpportunities }, toQuery(defaultDefinition()))
    expect(result.items.map(r => r.id)).toEqual(['a', 'b'])
    expect(queryOpportunities.mock.calls.map(c => c[0].page)).toEqual([1, 2])
    expect(queryOpportunities.mock.calls[1][0].pageSize).toBe(200)
  })
  it.each(['total', 'summary', 'duplicate', 'day'])('refuses a changing export: %s', async kind => {
    const first = page(1, 'a'), second = page(2, 'b')
    if (kind === 'total') second.meta!.total = 3
    if (kind === 'summary') second.data.summary.knownAmountCny = '123'
    if (kind === 'duplicate') second.data.items[0].id = 'a'
    if (kind === 'day') second.data.asOf = '2030-01-01T00:00:00Z'
    const queryOpportunities = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    await expect(readBoardExport({ queryOpportunities }, toQuery(defaultDefinition()))).rejects.toThrow('EXPORT_CHANGED')
  })
  it('cancels when the user identity changes', async () => {
    const queryOpportunities = vi.fn(async () => page(1, 'a'))
    await expect(readBoardExport({ queryOpportunities }, toQuery(defaultDefinition()), () => true)).rejects.toThrow('EXPORT_CANCELLED')
    expect(queryOpportunities).not.toHaveBeenCalled()
  })
  it('keeps only selected columns, isolates group sheets, writes amounts as numbers and escapes workbook names / formula-like data', () => {
    const result = boardResultFixture().data
    const template = result.items[0]
    result.items = [
      { ...template, id: 'a', equipment: 'A/B', customerName: '=HYPERLINK("bad")', amountCny: null },
      { ...template, id: 'b', equipment: ('A' + String.fromCharCode(92) + 'B'), amountCny: '1234.50' },
    ]
    result.groups = ['A/B', ('A' + String.fromCharCode(92) + 'B')].map(key => ({ key, label: key, count: 1, knownAmountCny: '0.00', missingAmountCount: 1 }))
    const workbook = boardWorkbook(result, ['customerName', 'amountCny'], 'equipment', 'en-US')
    expect(workbook.sheets.map(s => s.name)).toEqual(['A B', 'A B (2)'])
    expect(workbook.sheets[0].rows[1][1].v).toBe('')
    expect(workbook.sheets[1].rows[1][1]).toEqual({ v: 1234.5, s: 16 })
    const xml = new TextDecoder().decode(buildXlsxFile(workbook))
    expect(xml).toContain('=HYPERLINK(&quot;bad&quot;)')
    expect(xml).not.toContain('<f>')
    // A number cell, not text, so Excel can sum the column.
    expect(xml).toContain('<c r="B2" s="16"><v>1234.5</v></c>')
    expect(xml).not.toContain('>1234.50<')
    expect(workbook.sheets[0].rows).toHaveLength(2)
  })

  it.each(['', '0.00'])('exports an amount not entered yet (%j) as a dash and an empty CNY cell, never as 0', (amount) => {
    const result = boardResultFixture().data
    result.items = [
      { ...result.items[0], id: 'unknown', stage: 'qualified_opportunity', amount, currency: 'USD', amountCny: null },
      { ...result.items[0], id: 'known', amount: '1234.50', currency: 'USD', amountCny: '8765.40' },
    ]
    const workbook = boardWorkbook(result, ['amount', 'amountCny'], null, 'en-US')
    expect(workbook.sheets[0].rows[1]).toEqual([{ v: '—', s: 5 }, { v: '', s: 16 }])
    expect(workbook.sheets[0].rows[2]).toEqual([{ v: 'USD 1234.50', s: 5 }, { v: 8765.4, s: 16 }])
  })

  it('writes CNY amounts as numbers and drops characters XML forbids', () => {
    const result = boardResultFixture().data
    result.items = [{ ...result.items[0], id: 'a', customerName: 'A\u000bB\u0000C', amountCny: '1234567.89' }]
    const workbook = boardWorkbook(result, ['customerName', 'amountCny'], null, 'en-US')
    expect(workbook.sheets[0].rows[1][1]).toEqual({ v: 1234567.89, s: 16 })
    const xml = new TextDecoder().decode(buildXlsxFile(workbook))
    expect(xml).toContain('<v>1234567.89</v>')
    expect(xml).toContain('ABC')
    expect(xml).not.toContain('A\u000bB')
  })
})

