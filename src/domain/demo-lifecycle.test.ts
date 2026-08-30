import { describe, expect, it } from 'vitest'
import { deriveDemoHealth, mapDemoLifecycleStage } from './demo-lifecycle'

describe('Demo lifecycle stage mapping', () => {
  it.each([
    ['Engineer Review', undefined, 'Engineer Review'],
    ['Engineer Returned', undefined, 'Engineer Review'],
    ['Manager Approval', undefined, 'Manager Approval'],
    ['Manager Rejected', undefined, 'Manager Approval'],
    ['Converted', 'Requested', 'Test Preparation'],
    ['Converted', 'Scope Confirmed', 'Test Preparation'],
    ['Converted', 'Sample Received', 'Test Preparation'],
    ['Converted', 'Scheduled', 'Test Preparation'],
    ['Converted', 'Testing', 'Test Execution'],
    ['Converted', 'Analysis', 'Internal Review'],
    ['Converted', 'Internal Review', 'Internal Review'],
    ['Converted', 'Customer Review', 'Customer Review'],
  ] as const)('maps %s / %s to %s', (requestStatus, evaluationStatus, expected) => {
    expect(mapDemoLifecycleStage(requestStatus, evaluationStatus)).toBe(expected)
  })

  it.each([
    ['Draft', undefined],
    ['Cancelled', undefined],
    ['Converted', 'Accepted'],
    ['Converted', 'Rejected'],
  ] as const)('excludes inactive %s / %s records', (requestStatus, evaluationStatus) => {
    expect(mapDemoLifecycleStage(requestStatus, evaluationStatus)).toBeNull()
  })
})

describe('Demo health derivation', () => {
  const today = '2026-07-28'

  it('marks a customer expectation exactly 7 natural days away as critical', () => {
    expect(deriveDemoHealth({
      lastProgressAt: '2026-07-28T09:00:00+08:00',
      customerExpectedDate: '2026-08-04',
      testRunDeadline: '',
      today,
    })).toMatchObject({
      level: 'critical',
      reason: '距客户预期仅 7 天',
      daysToCustomerExpected: 7,
    })
  })

  it('keeps an 8-day customer expectation healthy when progress is recent', () => {
    expect(deriveDemoHealth({
      lastProgressAt: '2026-07-27T23:30:00+08:00',
      customerExpectedDate: '2026-08-05',
      testRunDeadline: '',
      today,
    })).toMatchObject({
      level: 'healthy',
      daysSinceProgress: 1,
      daysToCustomerExpected: 8,
    })
  })

  it('marks exactly 5 natural days without progress as stalled', () => {
    expect(deriveDemoHealth({
      lastProgressAt: '2026-07-23T08:00:00+08:00',
      customerExpectedDate: '2026-08-20',
      testRunDeadline: '',
      today,
    })).toMatchObject({
      level: 'stalled',
      reason: '已连续 5 天无有效进展',
      daysSinceProgress: 5,
    })
  })

  it('keeps 4 natural days without progress healthy', () => {
    expect(deriveDemoHealth({
      lastProgressAt: '2026-07-24T08:00:00+08:00',
      customerExpectedDate: '2026-08-20',
      testRunDeadline: '',
      today,
    })).toMatchObject({
      level: 'healthy',
      daysSinceProgress: 4,
    })
  })

  it('gives customer time risk priority over stalled progress', () => {
    expect(deriveDemoHealth({
      lastProgressAt: '2026-07-01T08:00:00+08:00',
      customerExpectedDate: '2026-07-30',
      testRunDeadline: '',
      today,
    })).toMatchObject({
      level: 'critical',
      reason: '距客户预期仅 2 天',
    })
  })

  it('marks an overdue Test Run DDL as critical', () => {
    expect(deriveDemoHealth({
      lastProgressAt: '2026-07-28T08:00:00+08:00',
      customerExpectedDate: '',
      testRunDeadline: '2026-07-27',
      today,
    })).toMatchObject({
      level: 'critical',
      reason: 'Test Run DDL 已逾期 1 天',
    })
  })

  it('uses Asia/Shanghai natural days across a UTC date boundary', () => {
    expect(deriveDemoHealth({
      lastProgressAt: '2026-07-23T16:30:00Z',
      customerExpectedDate: '2026-08-20',
      testRunDeadline: '',
      today: '2026-07-28T00:30:00+08:00',
    })).toMatchObject({
      level: 'healthy',
      daysSinceProgress: 4,
    })
  })
})
