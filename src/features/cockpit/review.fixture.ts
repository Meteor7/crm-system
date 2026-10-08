// Synthetic records for tests and the local design preview only. Never loaded by the production runtime.
import type { ActivityKey, Metric, ReviewDto } from './types'
const ready = (value: number | string): Metric => ({ value, state: 'ready' })
const notApplicable = { value: null, state: 'not_applicable' as const, record: null }
export function reviewFixture(): ReviewDto {
  return {
    period: { kind: 'week', start: '2026-09-07', end: '2026-09-13', asOf: '2026-09-13T15:59:59Z', previousStart: '2026-08-31', previousEnd: '2026-09-06T16:00:00Z', complete: true, previousAnchor: '2026-08-31', nextAnchor: '2026-09-14', hasNext: true },
    filters: { sales: [{ id: 'alice', name: 'Alice' }, { id: 'bob', name: 'Bob' }], markets: ['Frontend', 'Advanced Packaging'], regions: [], regionReady: false },
    activities: (['visits', 'leads', 'tests', 'quotes'] as ActivityKey[]).map((key, i) => ({ key, actual: ready([12, 4, 7, 3][i]), previous: ready([10, 2, 8, 3][i]), delta: [2, 2, -1, 0][i], target: { ...notApplicable } })),
    pipeline: ['qualified_opportunity', 'demo_done', 'customer_budget_approved', 'rfq_validated', 'quotation_sent', 'internal_validation', 'po'].map((key, i) => ({ key, count: ready([14, 10, 8, 6, 5, 2, 7][i]), amount: i === 0 ? notApplicable : ready(String([0, 24000000, 18000000, 12000000, 10500000, 3200000, 9500000][i])) })),
    warnings: ['lost', 'overdue', 'downgrade'].map((key, i) => ({ key, count: ready([1, 2, 1][i]) })),
    sales: ['alice', 'bob'].map((id, i) => ({ id, name: i ? 'Bob' : 'Alice', activities: { followups: ready(0), visits: ready(6), leads: ready(2), tests: ready(i ? 3 : 4), quotes: ready(i ? 1 : 2) }, pipeline: ready('33850000'), poCount: ready(i ? 3 : 4), orders: ready(i ? '5500000' : '4000000') })),
    orders: { actual: ready('9500000'), series: [{ date: '2026-03-05', amount: '4000000', cumulative: '4000000', fraction: .18 }, { date: '2026-08-20', amount: '5500000', cumulative: '9500000', fraction: .64 }], count: ready(7), missingDate: ready(2), missingAmount: ready(0), target: notApplicable, planned: notApplicable, elapsedFraction: .7 },
    stalled: { count: ready(1), items: [{ id: 'opp-example', title: 'Inspection system evaluation', accountId: 'customer-example', customer: 'Example customer', owner: 'alice', at: '2026-09-13T15:59:59Z', kind: 'opportunity', days: 36, severity: 'high' }] },
    losses: { count: ready(1), items: [{ id: 'loss-example', eventId: 'loss-event', title: 'Metrology system', accountId: 'customer-example', customer: 'Example customer', owner: 'bob', at: '2026-09-10T04:00:00Z', kind: 'opportunity', stage: 'quotation_sent', reason: 'Customer budget deferred' }] }, targets: [],
  }
}
