import { afterEach, describe, expect, it, vi } from 'vitest'
import { getContractRisk } from './contracts'

describe('contract expiry risk', () => {
  afterEach(() => vi.useRealTimers())

  it.each([
    ['2026-07-16', 'expired', '已到期'],
    ['2026-08-10', '30d', '24 天内'],
    ['2026-09-01', '60d', '46 天内'],
    ['2026-10-01', '90d', '76 天内'],
    ['2027-01-01', 'normal', '演示员工152'],
  ] as const)('classifies %s into %s', (endDate, band, label) => {
    expect(getContractRisk(endDate, '2026-07-17')).toMatchObject({ band, label })
  })

  it('uses the current Shanghai date when today is omitted', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-05T16:30:00.000Z'))

    expect(getContractRisk('2026-08-06')).toMatchObject({ days: 0, band: '30d', label: '今天到期' })
  })
})
