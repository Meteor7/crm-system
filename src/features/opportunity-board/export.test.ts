import { describe, expect, it, vi } from 'vitest'
import { boardResultFixture } from './fixtures'
import { defaultDefinition, toQuery } from './model'
import { boardWorkbook, readBoardExport } from './export'
import { buildXlsxFile } from '@/features/accounts/xlsx-writer'

describe('full-result board export', () => {
  it('exports more than a page in one call with the exact query and saved version', async () => {
    const data = boardResultFixture().data
    data.items = Array.from({ length: 205 }, (_, index) => ({ ...data.items[0], id: `opp-${index}` }))
    data.summary.count = 205
    const exportOpportunities = vi.fn(async () => ({ data, warnings: [] }))
    const query = { ...toQuery(defaultDefinition()), savedQuery: { id: 'shared', modified: 'version' } }
    const result = await readBoardExport({ exportOpportunities }, query)
    expect(result.items).toHaveLength(205)
    expect(exportOpportunities).toHaveBeenCalledExactlyOnceWith(query)
    expect(result.asOf).toBe(data.asOf)
  })
  it.each(['missing', 'duplicate'])('refuses an invalid complete set: %s', async kind => {
    const data = boardResultFixture().data
    data.items = [{ ...data.items[0], id: 'a' }, { ...data.items[0], id: kind === 'duplicate' ? 'a' : 'b' }]
    data.summary.count = kind === 'missing' ? 3 : 2
    await expect(readBoardExport({ exportOpportunities: vi.fn(async () => ({ data, warnings: [] })) }, toQuery(defaultDefinition()))).rejects.toThrow('EXPORT_CHANGED')
  })
  it('cancels before or after a response when identity changes', async () => {
    let changed = false
    const exportOpportunities = vi.fn(async () => { changed = true; return { data: boardResultFixture().data, warnings: [] } })
    await expect(readBoardExport({ exportOpportunities }, toQuery(defaultDefinition()), () => true)).rejects.toThrow('EXPORT_CANCELLED')
    expect(exportOpportunities).not.toHaveBeenCalled()
    await expect(readBoardExport({ exportOpportunities }, toQuery(defaultDefinition()), () => changed)).rejects.toThrow('EXPORT_CANCELLED')
  })
  it('includes query metadata, selected columns, typed CNY millions, isolated groups and safe text', () => {
    const result = boardResultFixture().data
    const template = result.items[0]
    result.items = [
      { ...template, id: 'a', equipment: 'A/B', customerName: '=HYPERLINK("bad")', amountCny: null },
      { ...template, id: 'b', equipment: 'A\\B', amountCny: '1234.50' },
      { ...template, id: 'c', equipment: 'Summary', amountCny: '1.00' },
    ]
    result.groups = ['A/B', 'A\\B', 'Summary'].map(key => ({ key, label: key, count: 1, knownAmountCny: '0.00', missingAmountCount: 1 }))
    const workbook = boardWorkbook(result, ['customerName', 'amountCny'], 'equipment', 'en-US', 'Q4: My/Query', defaultDefinition())
    expect(workbook.fileName).toContain('Q4  My Query')
    expect(workbook.sheets.map(s => s.name)).toEqual(['Summary', 'A B', 'A B (2)', 'Summary (2)'])
    expect(workbook.sheets[0].rows[0][1].v).toBe('Q4: My/Query')
    expect(workbook.sheets[0].rows[4][1].v).toBe(result.summary.missingAmountCount)
    expect(workbook.sheets[1].rows[1][1].v).toBe('')
    expect(workbook.sheets[2].rows[1][1]).toEqual({ v: 0.0012345, s: 17 })
    const xml = new TextDecoder().decode(buildXlsxFile(workbook))
    expect(xml).toContain('=HYPERLINK(&quot;bad&quot;)')
    expect(xml).toContain('t="inlineStr"')
    expect(xml).not.toContain('<f>')
    expect(xml).toContain('<c r="B2" s="17"><v>0.0012345</v></c>')
    expect(xml).toContain('state="frozen"')
    expect(workbook.sheets[1].rows).toHaveLength(2)
  })
  it('preserves a large Unicode query definition within Excel cell limits', () => {
    const definition = { ...defaultDefinition(), conditions: [{ field: 'customerName' as const, operator: 'contains' as const, value: '😀'.repeat(18000) }] }
    const workbook = boardWorkbook(boardResultFixture().data, ['title'], null, 'en-US', 'Large', definition)
    const parts = workbook.sheets[0].rows.filter(row => String(row[0].v).startsWith('Scope and conditions')).map(row => String(row[1].v))
    expect(parts.length).toBeGreaterThan(1)
    expect(parts.every(part => part.length <= 32767)).toBe(true)
    expect(parts.join('')).toBe(JSON.stringify(definition))
  })
  it('writes Shanghai business dates as Excel dates and keeps unknown dates blank', () => {
    const result = boardResultFixture().data
    result.items = [{ ...result.items[0], createdAt: '2026-09-30T16:30:00Z', poDate: '2026-10-01', lastActivityAt: '2026-09-30T16:30:00Z', lastActivityIncomplete: true }]
    const workbook = boardWorkbook(result, ['createdAt', 'poDate', 'lastActivityAt'], null, 'en-US')
    const expected = (Date.UTC(2026, 9, 1) - Date.UTC(1899, 11, 30)) / 86400000
    expect(workbook.sheets[1].rows[1]).toEqual([{ v: expected, s: 12 }, { v: expected, s: 12 }, { v: '', s: 12 }])
  })
  it.each(['', '0.00'])('keeps an unentered original amount (%j) and unknown CNY distinct from zero', amount => {
    const result = boardResultFixture().data
    result.items = [{ ...result.items[0], amount, amountCny: null }]
    const workbook = boardWorkbook(result, ['amount', 'amountCny'], null, 'en-US')
    expect(workbook.sheets[1].rows[1]).toEqual([{ v: '—', s: 5 }, { v: '', s: 17 }])
  })
  it('keeps cents in the numeric value and drops XML-forbidden characters', () => {
    const result = boardResultFixture().data
    result.items = [{ ...result.items[0], customerName: 'A\u000bB\u0000C', amountCny: '1234567.89' }]
    const workbook = boardWorkbook(result, ['customerName', 'amountCny'], null, 'en-US')
    expect(workbook.sheets[1].rows[1][1]).toEqual({ v: 1.23456789, s: 17 })
    const xml = new TextDecoder().decode(buildXlsxFile(workbook))
    expect(xml).toContain('ABC')
    expect(xml).not.toContain('A\u000bB')
  })
  it.each([
    ['0.00', 0],
    ['0.01', 0.00000001],
    ['0.10', 0.0000001],
    ['1234567.89', 1.23456789],
    ['9999999999999.99', 9999999.99999999],
    ['10000000000000.01', '10000000.00000001'],
    ['90071992547409.93', '90071992.54740993'],
    ['999999999999999999.99', '999999999999.99999999'],
    ['100000000000000000.00', 100000000000],
  ] as const)('preserves exact cents for row and summary amount %s', (amount, expected) => {
    const result = boardResultFixture().data
    result.items = [{ ...result.items[0], amountCny: amount }]
    result.summary.knownAmountCny = amount
    const workbook = boardWorkbook(result, ['amountCny'], null, 'en-US')
    expect(workbook.sheets[0].rows[3][1]).toEqual({ v: expected, s: 17 })
    expect(workbook.sheets[1].rows[1][0]).toEqual({ v: expected, s: 17 })
    const xml = new TextDecoder().decode(buildXlsxFile(workbook))
    for (const address of ['B4', 'A2']) {
      expect(xml).toContain(typeof expected === 'number'
        ? `<c r="${address}" s="17"><v>${expected}</v></c>`
        : `<c r="${address}" s="17" t="inlineStr"><is><t xml:space="preserve">${expected}</t></is></c>`)
    }
  })
  it('preserves totals larger than the single-record amount limit', () => {
    const result = boardResultFixture().data
    result.summary.knownAmountCny = '1999999999999999999.98'
    const workbook = boardWorkbook(result, ['amountCny'], null, 'en-US')
    expect(workbook.sheets[0].rows[3][1].v).toBe('1999999999999.99999998')
    const xml = new TextDecoder().decode(buildXlsxFile(workbook))
    expect(xml).toContain('<c r="B4" s="17" t="inlineStr"><is><t xml:space="preserve">1999999999999.99999998</t></is></c>')
    expect(xml).toContain('Amounts exceeding Excel numeric precision are exact text in CNY millions.')
  })
  it('preserves complete Unicode code points at the filename boundary', () => {
    const queryName = 'A'.repeat(79) + '😀'
    const workbook = boardWorkbook(boardResultFixture().data, ['title'], null, 'en-US', queryName)
    expect(workbook.fileName).toBe(`Opportunities_${queryName}_${boardResultFixture().data.asOf.slice(0, 10)}.xlsx`)
  })
  it('keeps Unicode sheet names valid and unique when truncating and suffixing', () => {
    const result = boardResultFixture().data
    result.groups = ['A'.repeat(26) + '😀AAA', 'A'.repeat(26) + '😀AAAB', 'B'.repeat(30) + '😀'].map(key => ({ key, label: key, count: 0, knownAmountCny: '0.00', missingAmountCount: 0 }))
    const workbook = boardWorkbook(result, ['title'], 'equipment', 'en-US')
    expect(workbook.sheets.map(sheet => sheet.name)).toEqual(['Summary', 'A'.repeat(26) + '😀AAA', 'A'.repeat(26) + ' (2)', 'B'.repeat(30)])
    const xml = new TextDecoder().decode(buildXlsxFile(workbook))
    expect(xml).toContain(`name="${'A'.repeat(26)}😀AAA"`)
    // Inspect XML only: ZIP headers contain arbitrary non-UTF-8 checksum bytes.
    expect(xml.match(/<workbook\s[\s\S]*?<\/workbook>/)?.[0]).not.toContain('\uFFFD')
  })
})
