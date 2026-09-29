// Synthetic data for tests and the local preview only; never used by the runtime adapter.
import type { PlanDetails, PlanDto, PlanItem } from './plan-types'
import type { Metric } from './types'
const ready = (value: number): Metric => ({ value, state: 'ready' })
export function planItemsFixture(): PlanItem[] {
  return [
    { id: 'visit-1', kind: 'visits', title: '量测方案现场沟通', accountId: 'account-1', customer: '华芯半导体（示例）', date: '2026-09-21', salesOwner: 'alice', market: 'Frontend', status: 'Planned', carryover: false },
    { id: 'visit-2', kind: 'visits', title: '新产线需求确认', accountId: 'account-2', customer: '远景封装（示例）', date: '2026-09-22', salesOwner: 'bob', market: 'Advanced Packaging', status: 'Planned', carryover: false },
    { id: 'eval-1', kind: 'tests', title: '晶圆检测测试', accountId: 'account-1', customer: '华芯半导体（示例）', date: '2026-09-23', salesOwner: 'alice', market: 'Frontend', status: 'Testing', carryover: false, evaluationId: 'eval-1' },
    { id: 'action-1', kind: 'actions', title: '确认预算审批进度', accountId: 'account-1', customer: '华芯半导体（示例）', date: '2026-09-24', salesOwner: 'alice', actionOwner: 'alice', market: 'Frontend', status: 'Open', carryover: false, opportunityId: 'opp-1' },
    { id: 'action-2', kind: 'actions', title: '补充交付计划', accountId: 'account-2', customer: '远景封装（示例）', date: '2026-09-26', salesOwner: 'bob', actionOwner: 'bob', market: 'Advanced Packaging', status: 'Open', carryover: false, opportunityId: 'opp-2' },
    { id: 'opp-1', kind: 'po', title: '前道检测系统', accountId: 'account-1', customer: '华芯半导体（示例）', date: '2026-09-25', salesOwner: 'alice', market: 'Frontend', status: 'rfq_validated', carryover: false, amount: '6800000', currency: 'CNY', probabilityLevel: 'upside' },
    { id: 'opp-2', kind: 'po', title: '先进封装量测系统', accountId: 'account-2', customer: '远景封装（示例）', date: '2026-09-27', salesOwner: 'bob', market: 'Advanced Packaging', status: 'quotation_sent', carryover: false, amount: null, currency: null, probabilityLevel: 'committed' },
    { id: 'action-old', kind: 'actions', title: '待客户确认验收条款', accountId: 'account-1', customer: '华芯半导体（示例）', date: '2026-09-18', salesOwner: 'alice', actionOwner: 'alice', market: 'Frontend', status: 'Open', carryover: true, opportunityId: 'opp-1' },
  ]
}
export function planFixture(): PlanDto {
  return {
    period: { kind: 'week', start: '2026-09-21', end: '2026-09-27', previousAnchor: '2026-09-14', nextAnchor: '2026-09-28' },
    asOf: '2026-09-18T03:00:00Z',
    filters: { sales: [{ id: 'alice', name: '演示员工151' }, { id: 'bob', name: '陈远' }], markets: ['Frontend', 'Advanced Packaging'], regions: ['East China', 'South China'], regionReady: true },
    summary: { visits: ready(2), tests: ready(1), actions: ready(2), po: ready(2) }, overdue: ready(1),
    poAmounts: [{ currency: 'CNY', value: '6800000' }], poAmountIncomplete: true,
    sales: [
      { id: 'alice', name: '演示员工151', visits: ready(1), tests: ready(1), actions: ready(1), po: ready(1), poAmounts: [{ currency: 'CNY', value: '6800000' }], poAmountIncomplete: false },
      { id: 'bob', name: '陈远', visits: ready(1), tests: ready(0), actions: ready(1), po: ready(1), poAmounts: [], poAmountIncomplete: true },
    ],
    markets: [
      { name: 'Frontend', activities: ready(3), po: ready(1), poAmounts: [{ currency: 'CNY', value: '6800000' }], poAmountIncomplete: false },
      { name: 'Advanced Packaging', activities: ready(2), po: ready(1), poAmounts: [], poAmountIncomplete: true },
    ],
    expectedPO: { items: planItemsFixture().filter(row => row.kind === 'po'), total: 2 },
  }
}
export function planDetailsFixture(): PlanDetails { return { items: planItemsFixture(), total: 8, page: 1, pageSize: 50, asOf: '2026-09-18T03:00:00Z' } }
