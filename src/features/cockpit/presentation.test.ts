import { describe, expect, it } from 'vitest'
import { createFrappeApi } from '@/api/frappe-adapter'
import { metricText, monotoneCurvePath, nextMonday, nextPeriodStart, targetStart } from './presentation'

describe('Review business API and presentation', () => {
  it('distinguishes zero, no target, unavailable and inapplicable', () => {
    expect(metricText({ value: 0, state: 'ready' }, 'zh-CN')).toBe('0')
    expect(metricText({ value: null, state: 'not_set' }, 'zh-CN')).toBe('未设置')
    expect(metricText({ value: null, state: 'insufficient' }, 'en-US')).toBe('Insufficient data')
    expect(metricText({ value: null, state: 'not_applicable' }, 'en-US')).toBe('N/A')
    expect(targetStart('2026-09-07', 'quarter')).toBe('2026-07-01')
    expect(targetStart('2026-09-07', 'month')).toBe('2026-09-01')
    expect(nextMonday(new Date('2026-09-14T00:00:00+08:00'))).toBe('2026-09-21')
  })
  it('opens Plan on the period after today for every granularity, on the Shanghai calendar', () => {
    const tuesday = new Date('2026-09-22T10:00:00+08:00')
    expect(nextPeriodStart('week', tuesday)).toBe('2026-09-28')
    expect(nextPeriodStart('month', tuesday)).toBe('2026-10-01')
    expect(nextPeriodStart('quarter', tuesday)).toBe('2026-10-01')
    expect(nextPeriodStart('year', tuesday)).toBe('2027-01-01')
    // Next Monday falling in the next month must not change which month comes next.
    expect(nextPeriodStart('month', new Date('2026-09-29T10:00:00+08:00'))).toBe('2026-10-01')
    const december = new Date('2026-12-15T10:00:00+08:00')
    expect(nextPeriodStart('month', december)).toBe('2027-01-01')
    expect(nextPeriodStart('quarter', december)).toBe('2027-01-01')
    // 17:00 UTC on Sep 30 is already Oct 1 in Shanghai.
    expect(nextPeriodStart('month', new Date('2026-09-30T17:00:00Z'))).toBe('2026-11-01')
    expect(nextPeriodStart('quarter', new Date('2026-09-30T17:00:00Z'))).toBe('2027-01-01')
  })
  it('uses only cockpit business methods with POST CSRF and target version', async () => {
    const requests: { url: string; init?: RequestInit }[] = []
    const api = createFrappeApi({ csrfToken: () => 'test-csrf', fetchImpl: async (url, init) => {
      requests.push({ url: String(url), init })
      return new Response(JSON.stringify({ message: { data: {}, meta: { requestId: 'test' }, warnings: [] } }), { headers: { 'Content-Type': 'application/json' } })
    } })
    await api.getReview({ period: 'week', sales: 'alice', region: 'East China' })
    await api.getReviewDetails({ metric: 'downgrade', page: 2, pageSize: 20 })
    await api.saveReviewTarget({ sales: 'alice', metric: 'visits', period: 'week', anchor: '2026-09-07', value: '4' }, 'version')
    expect(requests[0].url).toContain('/api/method/rayher_crm.api.v1.cockpit.get_review?')
    expect(requests[1].url).toContain('cockpit.get_details?metric=downgrade')
    expect(requests[2].url).toBe('/api/method/rayher_crm.api.v1.cockpit.save_target')
    expect(requests[2].init?.method).toBe('POST')
    expect(new Headers(requests[2].init?.headers).get('X-Frappe-CSRF-Token')).toBe('test-csrf')
    expect(String(requests[2].init?.body)).toContain('expectedModified')
  })
})

describe('Cumulative order curve', () => {
  it('keeps a flat tail flat and draws a straight line between two points', () => {
    expect(monotoneCurvePath([{ x: 0, y: 100 }, { x: 10, y: 50 }])).toBe('M0.0 100.0L10.0 50.0')
    expect(monotoneCurvePath([{ x: 0, y: 100 }, { x: 10, y: 50 }, { x: 20, y: 50 }]))
      .toBe('M0.0 100.0C3.3 75.0 6.7 50.0 10.0 50.0C13.3 50.0 16.7 50.0 20.0 50.0')
  })

  it('never leaves the band between two neighbouring points', () => {
    const path = monotoneCurvePath([{ x: 0, y: 190 }, { x: 10, y: 30 }, { x: 100, y: 20 }, { x: 120, y: 20 }])
    const start = path.match(/^M([\d.-]+) ([\d.-]+)/)!
    let from = { x: Number(start[1]), y: Number(start[2]) }
    const curves = [...path.matchAll(/C([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+)/g)]
    expect(curves).toHaveLength(3)
    for (const curve of curves) {
      const [c1x, c1y, c2x, c2y, x, y] = curve.slice(1).map(Number)
      const cubic = (t: number, a: number, b: number, c: number, d: number) =>
        (1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
      for (const t of [.1, .25, .5, .75, .9]) {
        expect(cubic(t, from.x, c1x, c2x, x)).toBeGreaterThanOrEqual(from.x - .05)
        expect(cubic(t, from.x, c1x, c2x, x)).toBeLessThanOrEqual(x + .05)
        expect(cubic(t, from.y, c1y, c2y, y)).toBeGreaterThanOrEqual(Math.min(from.y, y) - .05)
        expect(cubic(t, from.y, c1y, c2y, y)).toBeLessThanOrEqual(Math.max(from.y, y) + .05)
      }
      from = { x, y }
    }
    expect(from).toEqual({ x: 120, y: 20 })
  })

  it('drops unusable points, keeps the last value at a repeated position and never draws a stray dot', () => {
    expect(monotoneCurvePath([])).toBe('')
    expect(monotoneCurvePath([{ x: 45, y: 190 }])).toBe('M45.0 190.0')
    expect(monotoneCurvePath([{ x: NaN, y: 10 }, { x: 0, y: 190 }, { x: 10, y: Infinity }, { x: 20, y: 30 }]))
      .toBe('M0.0 190.0L20.0 30.0')
    expect(monotoneCurvePath([{ x: 0, y: 190 }, { x: 10, y: 90 }, { x: 10, y: 30 }]))
      .toBe('M0.0 190.0L10.0 30.0')
  })
})
