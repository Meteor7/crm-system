import { describe, expect, it } from 'vitest'
import { addMoney, formatKnownTotals, formatMoney, formatSummedTotals, moneyByCurrency, unknownAmountCount } from './money'

describe('exact money contract', () => {
  it('adds decimal strings without IEEE-754 precision loss', () => {
    expect(addMoney(['9007199254740992.01', '0.02'])).toBe('9007199254740992.03')
  })

  it('isolates totals by currency', () => {
    expect(moneyByCurrency([
      { currency: 'CNY', amount: '1.01' },
      { currency: 'USD', amount: '2.02' },
      { currency: 'CNY', amount: '3.03' },
    ])).toEqual([
      { currency: 'CNY', amount: '4.04' },
      { currency: 'USD', amount: '2.02' },
    ])
  })

  it('rejects totals above DECIMAL(20,2) capacity', () => {
    expect(() => addMoney(['999999999999999999.99', '0.01'])).toThrow('DECIMAL(20,2)')
  })

  it('formats without converting the integer portion to Number', () => {
    expect(formatMoney('9007199254740992.01', 'CNY')).toBe('CNY 9,007,199,254,740,992.01')
  })

  it('shows an amount nobody has entered yet as a dash, never as 0 or an error', () => {
    expect(formatMoney('', 'CNY')).toBe('—')
  })

  it('leaves unknown amounts out of the totals and counts them instead of adding 0', () => {
    const rows = [
      { currency: 'CNY', amount: '100.00' },
      { currency: 'CNY', amount: '' },
      { currency: 'USD', amount: '' },
    ]
    expect(moneyByCurrency(rows)).toEqual([{ currency: 'CNY', amount: '100.00' }])
    expect(unknownAmountCount(rows)).toBe(2)
    expect(formatKnownTotals(rows, (count) => `${count} 条未填金额`)).toBe('CNY 100.00 · 2 条未填金额')
    expect(formatKnownTotals([{ currency: 'CNY', amount: '' }], (count) => `${count} 条未填金额`)).toBe('1 条未填金额')
    expect(formatKnownTotals([{ currency: 'CNY', amount: '100.00' }], () => 'never shown')).toBe('CNY 100.00')
    // Totals that are already added up read the same: by currency, then the amounts not entered.
    const unknownLabel = (count: number) => `${count} 条未填金额`
    expect(formatSummedTotals([{ currency: 'USD', amount: '50.00' }, { currency: 'CNY', amount: '202000.00' }], 3, unknownLabel)).toBe('CNY 202,000.00 · USD 50.00 · 3 条未填金额')
    expect(formatSummedTotals([], 2, unknownLabel)).toBe('2 条未填金额')
    expect(formatSummedTotals([], 0, unknownLabel)).toBe('')
  })

  it('formats a total that is larger than any single amount may be', () => {
    // Thirteen amounts of 80,000,000,000,000,000.00 each fit DECIMAL(20,2); what the server adds up does not.
    expect(() => formatMoney('1040000000000000000.00', 'CNY')).toThrow('DECIMAL(20,2)')
    expect(formatSummedTotals([{ currency: 'CNY', amount: '1040000000000000000.00' }], 0, () => 'never shown')).toBe('CNY 1,040,000,000,000,000,000.00')
  })
})
