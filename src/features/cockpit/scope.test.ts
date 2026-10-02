import { describe, expect, it } from 'vitest'
import { nextPeriodStart } from './presentation'
import {
  cockpitRoute, defaultReviewAnchor, fromBoardScope, nextPeriodAfter, periodStartOf, planStart, previousPeriodBefore,
  readCockpitQuery, reviewAnchorForPlan, shanghaiDate, toBoardScope, type CockpitContext,
} from './scope'

const scope = { sales: 'alice', region: 'East China', market: 'Frontend', equipment: 'Kibo 4895C' }
const q3: CockpitContext = { ...scope, period: 'quarter', reviewAnchor: '2026-07-01' }

describe('Cockpit period arithmetic', () => {
  it('finds the first day of the period that contains a business date', () => {
    expect(periodStartOf('week', '2026-10-01')).toBe('2026-09-28')
    expect(periodStartOf('month', '2026-10-31')).toBe('2026-10-01')
    expect(periodStartOf('quarter', '2026-08-15')).toBe('2026-07-01')
    expect(periodStartOf('year', '2026-08-15')).toBe('2026-01-01')
    for (const invalid of ['', '2026-02-30', '2026-9-1', 'next week']) expect(periodStartOf('week', invalid)).toBe('')
  })

  it('rolls quarters, months and years over into the next and previous year', () => {
    expect(nextPeriodAfter('quarter', '2026-07-01')).toBe('2026-10-01')
    expect(nextPeriodAfter('quarter', '2026-11-15')).toBe('2027-01-01')
    expect(previousPeriodBefore('quarter', '2027-01-01')).toBe('2026-10-01')
    expect(previousPeriodBefore('quarter', '2026-10-01')).toBe('2026-07-01')
    expect(nextPeriodAfter('month', '2026-12-31')).toBe('2027-01-01')
    expect(previousPeriodBefore('month', '2027-01-01')).toBe('2026-12-01')
    expect(previousPeriodBefore('month', '2026-03-31')).toBe('2026-02-01')
    expect(nextPeriodAfter('year', '2026-03-01')).toBe('2027-01-01')
    expect(previousPeriodBefore('year', '2027-01-01')).toBe('2026-01-01')
  })

  it('keeps ISO weeks across the year boundary', () => {
    // 2026 has 53 ISO weeks: week 53 runs Monday 2026-12-28 to Sunday 2027-01-03.
    expect(periodStartOf('week', '2027-01-01')).toBe('2026-12-28')
    expect(nextPeriodAfter('week', '2026-12-28')).toBe('2027-01-04')
    expect(nextPeriodAfter('week', '2027-01-03')).toBe('2027-01-04')
    expect(previousPeriodBefore('week', '2027-01-04')).toBe('2026-12-28')
    expect(previousPeriodBefore('week', '2027-01-06')).toBe('2026-12-28')
  })

  it('reads today and Review\'s default week on the Shanghai calendar, never the UTC date', () => {
    // 17:00 UTC on Sep 30 is already Oct 1 in Shanghai.
    expect(shanghaiDate(new Date('2026-09-30T17:00:00Z'))).toBe('2026-10-01')
    expect(shanghaiDate(new Date('2026-09-30T15:59:00Z'))).toBe('2026-09-30')
    // Sunday 2026-10-04 in UTC is Monday 2026-10-05 in Shanghai: Review's default is the Monday of the week before.
    expect(defaultReviewAnchor(new Date('2026-10-04T16:30:00Z'))).toBe('2026-09-28')
    expect(defaultReviewAnchor(new Date('2026-10-04T15:30:00Z'))).toBe('2026-09-21')
    // The same Shanghai rule as the existing next-period helper.
    for (const now of [new Date('2026-09-30T17:00:00Z'), new Date('2026-12-31T20:00:00Z'), new Date('2026-09-22T10:00:00+08:00')]) {
      for (const period of ['week', 'month', 'quarter', 'year'] as const) expect(nextPeriodAfter(period, shanghaiDate(now))).toBe(nextPeriodStart(period, now))
    }
  })
})

describe('Cockpit navigation context', () => {
  const NOW = new Date('2026-09-30T10:00:00+08:00')
  // Well after the Plan periods below, so the "not yet started" limit never applies to them.
  const LATER = new Date('2027-03-01T10:00:00+08:00')
  it('hands the Review period to Plan as the next period and restores it on the way back', () => {
    const plan = cockpitRoute('plan', q3)
    expect(plan).toEqual({ path: '/plan', query: { period: 'quarter', anchor: '2026-10-01', reviewAnchor: '2026-07-01', sales: 'alice', market: 'Frontend', region: 'East China', equipment: 'Kibo 4895C' } })
    const incoming = readCockpitQuery(plan.query)
    const start = planStart(incoming, NOW)
    expect(start).toEqual({ period: 'quarter', anchor: '2026-10-01' })
    const back = cockpitRoute('review', { ...incoming.scope, period: start.period, reviewAnchor: reviewAnchorForPlan(start.period, start.anchor, incoming.reviewAnchor, NOW) })
    expect(back).toEqual({ path: '/dashboard', query: { period: 'quarter', anchor: '2026-07-01', sales: 'alice', market: 'Frontend', region: 'East China', equipment: 'Kibo 4895C' } })
    expect(cockpitRoute('warnings', q3).path).toBe('/warnings')
    expect(cockpitRoute('warnings', q3).query).toEqual(back.query)
  })

  it('carries the Review period through Opportunities without an anchor of its own', () => {
    const board = cockpitRoute('board', q3)
    expect(board).toEqual({ path: '/opportunity-board', query: { period: 'quarter', reviewAnchor: '2026-07-01', sales: 'alice', market: 'Frontend', region: 'East China', equipment: 'Kibo 4895C' } })
    const incoming = readCockpitQuery(board.query)
    expect(incoming).toMatchObject({ period: 'quarter', anchor: '', reviewAnchor: '2026-07-01' })
    expect(toBoardScope(incoming.scope)).toEqual({ sales: ['alice'], regions: ['East China'], markets: ['Frontend'], equipment: ['Kibo 4895C'] })
    const outgoing = fromBoardScope(toBoardScope(incoming.scope))
    expect(outgoing.blocked).toEqual([])
    expect(cockpitRoute('plan', { ...outgoing.scope, period: incoming.period!, reviewAnchor: incoming.reviewAnchor }).query).toMatchObject({ period: 'quarter', anchor: '2026-10-01', reviewAnchor: '2026-07-01', region: 'East China' })
  })

  it('never advances a direct Plan link a second time and derives its Review period with the same rules', () => {
    const direct = readCockpitQuery({ period: 'quarter', anchor: '2026-10-01', region: 'East China' })
    const start = planStart(direct, NOW)
    expect(start).toEqual({ period: 'quarter', anchor: '2026-10-01' })
    expect(reviewAnchorForPlan(start.period, start.anchor, direct.reviewAnchor, NOW)).toBe('2026-07-01')
    // A week anchor in the middle of the Plan week still returns to the whole preceding ISO week.
    expect(reviewAnchorForPlan('week', '2027-01-06', '', LATER)).toBe('2026-12-28')
    // An anchor-less Plan link opens the period after today (Shanghai) and returns to the current one.
    const now = new Date('2026-10-04T16:30:00Z')
    const bare = planStart(readCockpitQuery({}), now)
    expect(bare).toEqual({ period: 'week', anchor: '2026-10-12' })
    expect(reviewAnchorForPlan(bare.period, bare.anchor, '', now)).toBe('2026-10-05')
    // A Review context without a Plan anchor is advanced exactly once.
    expect(planStart(readCockpitQuery({ period: 'month', reviewAnchor: '2026-12-15' }), now)).toEqual({ period: 'month', anchor: '2027-01-01' })
  })

  it('keeps the originating Review anchor only while Plan still shows the period right after it', () => {
    expect(reviewAnchorForPlan('quarter', '2026-10-01', '2026-08-15', LATER)).toBe('2026-08-15')
    expect(reviewAnchorForPlan('quarter', '2026-11-20', '2026-08-15', LATER)).toBe('2026-08-15')
    // Paged to the next Plan quarter, or switched granularity: the Review period follows Plan.
    expect(reviewAnchorForPlan('quarter', '2027-01-01', '2026-08-15', LATER)).toBe('2026-10-01')
    expect(reviewAnchorForPlan('month', '2026-10-01', '2026-08-15', LATER)).toBe('2026-09-01')
    // An unusable Plan anchor (a cleared date field) keeps the Review anchor or omits it.
    expect(reviewAnchorForPlan('week', '', '2026-09-21', LATER)).toBe('2026-09-21')
    expect(reviewAnchorForPlan('week', '', '', LATER)).toBe('')
    // ...but never one that has not started yet (an old bookmark or a hand-edited link).
    expect(reviewAnchorForPlan('week', '', '2026-12-14', NOW)).toBe('')
    expect(reviewAnchorForPlan('week', '', 'next', NOW)).toBe('')
  })

  it('never hands Review or Warnings a period that has not started yet (the backend refuses it)', () => {
    // Wednesday 2026-09-30 (Shanghai): Plan defaults to the week of 2026-10-05; paging on to 2026-10-12 must not
    // send Review to the week of 2026-10-05, which starts in the future.
    expect(reviewAnchorForPlan('week', '2026-10-05', '', NOW)).toBe('2026-09-28')
    expect(reviewAnchorForPlan('week', '2026-10-12', '', NOW)).toBe('2026-09-28')
    expect(reviewAnchorForPlan('week', '2026-10-12', '2026-09-28', NOW)).toBe('2026-09-28')
    expect(reviewAnchorForPlan('month', '2026-11-01', '2026-09-01', NOW)).toBe('2026-09-01')
    expect(reviewAnchorForPlan('quarter', '2027-01-01', '', NOW)).toBe('2026-07-01')
    expect(reviewAnchorForPlan('year', '2028-01-01', '', NOW)).toBe('2026-01-01')
    // A date inside the current period is kept as it is, not rounded down to the period start.
    expect(reviewAnchorForPlan('month', '2026-10-01', '2026-09-15', NOW)).toBe('2026-09-15')
    expect(reviewAnchorForPlan('week', '2026-10-05', '2026-09-30', NOW)).toBe('2026-09-30')
    // The route built from it stays queryable for every tab that goes back.
    const ahead = planStart(readCockpitQuery({ period: 'quarter', anchor: '2027-01-01' }), NOW)
    const reviewAnchor = reviewAnchorForPlan(ahead.period, ahead.anchor, '', NOW)
    expect(cockpitRoute('review', { ...readCockpitQuery({}).scope, period: 'quarter', reviewAnchor }).query.anchor).toBe('2026-07-01')
    expect(cockpitRoute('board', { ...readCockpitQuery({}).scope, period: 'quarter', reviewAnchor }).query.reviewAnchor).toBe('2026-07-01')
  })

  it('falls back to the derived Plan period when the anchor in the URL is not a business date', () => {
    expect(planStart(readCockpitQuery({ anchor: '2026-02-30' }), NOW)).toEqual({ period: 'week', anchor: '2026-10-05' })
    expect(planStart(readCockpitQuery({ anchor: 'next' }), NOW)).toEqual({ period: 'week', anchor: '2026-10-05' })
    expect(planStart(readCockpitQuery({ anchor: 'next', reviewAnchor: '2026-09-21' }), NOW)).toEqual({ period: 'week', anchor: '2026-09-28' })
  })

  it('leaves out empty scope and unknown periods and anchors', () => {
    const none: CockpitContext = { sales: '', region: '', market: '', equipment: '', period: 'week', reviewAnchor: '' }
    expect(cockpitRoute('review', none)).toEqual({ path: '/dashboard', query: { period: 'week' } })
    expect(cockpitRoute('plan', none)).toEqual({ path: '/plan', query: { period: 'week' } })
    expect(cockpitRoute('board', none)).toEqual({ path: '/opportunity-board', query: { period: 'week' } })
    // Review and Warnings hand an anchor on for the backend to validate; Plan cannot derive from a malformed one.
    expect(cockpitRoute('warnings', { ...none, reviewAnchor: 'not-a-date' }).query).toEqual({ period: 'week', anchor: 'not-a-date' })
    expect(cockpitRoute('plan', { ...none, reviewAnchor: 'not-a-date' }).query).toEqual({ period: 'week' })
    expect(readCockpitQuery({ period: 'day', anchor: ' ', sales: ['a', 'b'], region: '  East China ', reviewAnchor: '2026-07-01' }))
      .toEqual({ scope: { sales: '', region: 'East China', market: '', equipment: '' }, period: null, anchor: '', reviewAnchor: '2026-07-01' })
  })

  it('reports Board dimensions that hold more than one value instead of widening them', () => {
    expect(fromBoardScope({ sales: [], regions: ['East China', 'South China'], markets: ['Frontend'], equipment: ['A', 'B'] }))
      .toEqual({ scope: { sales: '', region: '', market: 'Frontend', equipment: '' }, blocked: ['region', 'equipment'] })
    expect(fromBoardScope({ sales: ['alice'], regions: [], markets: [], equipment: [] }))
      .toEqual({ scope: { sales: 'alice', region: '', market: '', equipment: '' }, blocked: [] })
    expect(toBoardScope({ sales: '', region: '', market: '', equipment: '' })).toEqual({ sales: [], regions: [], markets: [], equipment: [] })
  })
})
