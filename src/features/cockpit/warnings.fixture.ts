// Synthetic records for tests and the local design preview only. Never loaded by the production runtime.
import { reviewFixture } from './review.fixture'
import type { Metric, ReviewRow, WarningHandling, WarningHandlingType, WarningsDto } from './types'

const ready = (value: number | string): Metric => ({ value, state: 'ready' })
const opportunity = (id: string, title: string, customer: string, owner: string, extra: Partial<ReviewRow> = {}): ReviewRow => ({
  id, title, accountId: `${customer}-account`, customer, owner, at: '2026-09-10T04:00:00Z', kind: 'opportunity', currency: 'CNY', ...extra,
})
const handling = (warningType: WarningHandlingType, sourceId: string, sourceEvent: string, extra: Partial<WarningHandling> = {}): WarningHandling => ({
  warningType, sourceId, sourceEvent, id: null, modified: null, state: 'open', nextStep: null, planBy: null, planAt: null,
  actionTaken: null, actedBy: null, actedAt: null, followUpOn: null, history: [], ...extra,
})

export function warningsFixture(): WarningsDto {
  const review = reviewFixture()
  return {
    period: review.period,
    filters: review.filters,
    warnings: [{ key: 'lost', count: ready(1) }, { key: 'overdue', count: ready(2) }, { key: 'downgrade', count: ready(1) }, { key: 'quotation_expiry', count: ready(1) }, { key: 'stage6_no_po', count: ready(1) }],
    quotationExpiry: { referenceDate: '2026-09-13', thresholdDays: 14 },
    stage6NoPo: { thresholdDays: 30 },
    lost: [
      opportunity('opp-lost-1', 'ACONCA front-end inspection', 'Jiangnan Photonics', 'alice', {
        stage: 'quotation_sent', amount: '5600000', reason: 'Budget frozen for 2026', at: '2026-09-04T02:00:00Z',
        review: { id: 'loss-review-1', status: 'pending', note: '', reviewedBy: null, reviewedAt: null, modified: '2026-09-04T02:00:00.000000Z' },
        reviewPending: true, reviewOverdue: false, reopenedAt: null,
      }),
      opportunity('opp-lost-2', 'NANSI advanced packaging', 'Tianhe Microelectronics', 'bob', {
        stage: 'quotation_sent', amount: '9300000', reason: 'Capex frozen for 2026, revisit Q1 2027', at: '2026-08-28T02:00:00Z',
        review: { id: 'loss-review-2', status: 'reviewed', note: 'Report shared with management', reviewedBy: 'alice', reviewedAt: '2026-09-02T08:00:00Z', modified: '2026-09-02T08:00:00.000000Z' },
        reviewPending: false, reviewOverdue: false, reopenedAt: null,
      }),
    ],
    lostBacklog: [
      opportunity('opp-lost-3', 'KIBO evaluation', 'Sunrise Optoelectronics', 'alice', {
        stage: 'demo_done', amount: '3200000', reason: 'Throughput 20% below requirement', at: '2026-07-21T02:00:00Z',
        review: { id: 'loss-review-3', status: 'pending', note: '', reviewedBy: null, reviewedAt: null, modified: '2026-07-21T02:00:00.000000Z' },
        reviewPending: true, reviewOverdue: true, reopenedAt: null,
      }),
    ],
    overdue: [
      opportunity('opp-overdue-1', 'NovaSil wafer evaluation', 'NovaSil Semiconductor', 'alice', {
        stage: 'demo_done', amount: '5500000', actionId: 'act-1', actionTitle: 'Schedule wafer evaluation slot', due: '2026-08-29', stalled: true,
        handling: handling('overdue', 'act-1', '2026-08-29', {
          id: 'handling-1', modified: '2026-09-10T02:00:00.000000Z', nextStep: 'FAE confirms the slot with the fab on Friday', planBy: 'alice', planAt: '2026-09-10T02:00:00Z',
          history: [{ kind: 'PlanUpdated', nextStep: 'FAE confirms the slot with the fab on Friday', actionTaken: null, followUpOn: null, actor: 'alice', at: '2026-09-10T02:00:00Z' }],
        }),
      }),
      opportunity('opp-overdue-2', 'Dongfang metrology', 'Dongfang Micro', 'bob', {
        stage: 'quotation_sent', amount: '4100000', actionId: 'act-2', actionTitle: 'Competitive counter-proposal', due: '2026-09-01', stalled: false,
        handling: handling('overdue', 'act-2', '2026-09-01'),
      }),
    ],
    downgrade: [
      opportunity('opp-down-1', 'Kunpeng packaging line', 'Kunpeng Advanced Pkg', 'alice', {
        stage: 'internal_validation', amount: '6800000', fromLevel: 'committed', toLevel: 'upside', eventId: 'prob-1', currentOwner: 'alice',
        reason: 'CFO now involved in payment-terms dispute',
        recovery: { plan: 'Propose 20/60/20 milestone plan with bank guarantee; GM call with CFO by Sep 12', state: 'pending',
          id: 'recovery-1', modified: '2026-09-08T02:00:00.000000Z', editedBy: 'alice', editedAt: '2026-09-08T02:00:00Z' },
        opportunityModified: '2026-09-09T03:00:00.000000Z',
      }),
    ],
    quotationExpiryItems: [{
      id: 'Q-1', title: 'Shengda Fab quotation', accountId: 'shengda', customer: 'Shengda Fab', owner: 'bob', at: '2026-09-01T02:00:00Z', kind: 'quotation',
      quotationVersionId: 'V-2', quotationVersionNo: 2, validUntil: '2026-09-20', daysToExpiry: 7, opportunityId: 'opp-quote-1',
      handling: handling('quotation_expiry', 'Q-1', 'V-2'),
    }],
    stage6NoPoItems: [opportunity('opp-s6-1', 'KIBO 4895C line validation', 'Huaxin Micro', 'alice', {
      stage: 'internal_validation', amount: '18490000', daysInStage: 42, daysAtLeast: false, enteredAt: '2026-08-01T16:00:00Z',
      // Back after its follow-up date: the previous action stays visible.
      handling: handling('stage6_no_po', 'opp-s6-1', 's6-entry-1', {
        id: 'handling-s6-1', modified: '2026-08-20T03:00:00.000000Z', actionTaken: 'Customer finance promised the PO by Sep 10', actedBy: 'alice', actedAt: '2026-08-20T03:00:00Z', followUpOn: '2026-09-10',
        history: [{ kind: 'ActionRecorded', nextStep: null, actionTaken: 'Customer finance promised the PO by Sep 10', followUpOn: '2026-09-10', actor: 'alice', at: '2026-08-20T03:00:00Z' }],
      }),
    })],
    stage6NoPoHandledItems: [opportunity('opp-s6-2', 'NANSI line validation', 'Zhongke Photonics', 'bob', {
      stage: 'internal_validation', amount: '7200000', daysInStage: 35, daysAtLeast: false, enteredAt: '2026-08-08T16:00:00Z',
      handling: handling('stage6_no_po', 'opp-s6-2', 's6-entry-2', {
        id: 'handling-s6-2', modified: '2026-09-12T03:00:00.000000Z', state: 'handled', actionTaken: 'GM call with the buyer; PO expected next week', actedBy: 'bob', actedAt: '2026-09-12T03:00:00Z', followUpOn: '2026-09-30',
        history: [{ kind: 'ActionRecorded', nextStep: null, actionTaken: 'GM call with the buyer; PO expected next week', followUpOn: '2026-09-30', actor: 'bob', at: '2026-09-12T03:00:00Z' }],
      }),
    })],
  }
}
