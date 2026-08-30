import { describe, expect, it } from 'vitest'
import { addMoney, formatMoney, moneyByCurrency, weightedMoney } from './money'

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

  it('rounds weighted money half up at the cent boundary', () => {
    expect(weightedMoney('0.05', 50)).toBe('0.03')
  })

  it('rejects totals above DECIMAL(20,2) capacity', () => {
    expect(() => addMoney(['999999999999999999.99', '0.01'])).toThrow('DECIMAL(20,2)')
  })

  it('formats without converting the integer portion to Number', () => {
    expect(formatMoney('9007199254740992.01', 'CNY')).toBe('CNY 9,007,199,254,740,992.01')
  })
})
