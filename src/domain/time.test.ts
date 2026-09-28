import { describe, expect, it } from 'vitest'
import { addIsoDateDays, formatDisplayDate, formatDisplayDateTime, shanghaiDate, shanghaiTimestamp } from './time'

describe('Shanghai business clock', () => {
  it('derives one consistent Shanghai date and timestamp from the same instant', () => {
    const instant = new Date('2026-08-02T16:30:45.000Z')

    expect(shanghaiDate(instant)).toBe('2026-08-03')
    expect(shanghaiTimestamp(instant)).toBe('2026-08-03T00:30:45+08:00')
  })

  it('adds calendar days without depending on the workstation timezone', () => {
    expect(addIsoDateDays('2026-08-03', 1)).toBe('2026-08-04')
  })

  it('formats every supported display value as a date without time precision', () => {
    const now = new Date('2026-08-05T04:00:00Z')

    expect(formatDisplayDate('2026-08-05', now)).toBe('2026-08-05')
    expect(formatDisplayDate('2026-08-05 18:30:45', now)).toBe('2026-08-05')
    expect(formatDisplayDate('2026-08-04T18:30:45Z', now)).toBe('2026-08-05')
    expect(formatDisplayDate('今天 09:42', now)).toBe('2026-08-05')
    expect(formatDisplayDate('刚刚', now)).toBe('2026-08-05')
    expect(formatDisplayDate('当前待办', now)).toBe('2026-08-05')
    expect(formatDisplayDate('昨天 17:20', now)).toBe('2026-08-04')
    expect(formatDisplayDate('2 天前', now)).toBe('2026-08-03')
    expect(formatDisplayDate('7月15日', now)).toBe('2026-07-15')
    expect(formatDisplayDate('07-22', now)).toBe('2026-07-22')
    expect(formatDisplayDate('', now)).toBe('—')
    expect(formatDisplayDate('待排期', now)).toBe('待排期')
  })

  it('formats audit timestamps as a Shanghai date and minute', () => {
    expect(formatDisplayDateTime('2026-07-16T09:20:00Z')).toBe('2026-07-16 17:20')
    expect(formatDisplayDateTime('2026-07-16T16:05:30.000Z')).toBe('2026-07-17 00:05')
    expect(formatDisplayDateTime('2026-07-16 09:20')).toBe('2026-07-16 09:20')
    expect(formatDisplayDateTime('2026-07-16')).toBe('2026-07-16')
    expect(formatDisplayDateTime('')).toBe('—')
  })
})
