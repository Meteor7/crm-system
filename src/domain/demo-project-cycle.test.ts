import { describe, expect, it } from 'vitest'
import type { DemoWorkflowDto } from '@/types/workspaces'
import {
  buildDemoProjectTimeline,
  demoProjectCycleGroup,
  isCustomerExpectedRisk,
  isRecentCompletedProject,
  preparationGateState,
  recentCompletedProjects,
} from './demo-project-cycle'

function workflow(overrides: Partial<DemoWorkflowDto>): DemoWorkflowDto {
  return {
    id: 'DR-TEST',
    accountId: 'ACC-001',
    siteId: 'SITE-001',
    opportunityId: 'OPP-001',
    title: 'Demo project',
    account: 'Test customer',
    opportunity: 'Test opportunity',
    salesOwner: 'Sales',
    engineerOwner: 'Engineer',
    equipment: 'Inspection Tool',
    owner: 'Engineer',
    status: 'Engineer Review',
    archiveCategory: 'In Progress',
    stage: 'Engineer Review',
    health: {
      level: 'healthy',
      reason: '正常推进',
      daysSinceProgress: 1,
      daysToCustomerExpected: 12,
    },
    conclusion: { status: 'Pending' },
    approvals: [
      { label: 'Sales 提交', actor: 'Sales', status: 'Done' },
      { label: 'FAE Review', actor: 'Engineer', status: 'Current' },
      { label: 'Boss Approval', actor: '', status: 'Waiting' },
      { label: 'Customer Review', actor: '', status: 'Waiting' },
    ],
    executions: [],
    wafers: [],
    testRuns: [],
    ...overrides,
  }
}

describe('Demo project-cycle mapping', () => {
  it.each([
    ['Engineer Review', 'In Progress', 'request'],
    ['Manager Approval', 'In Progress', 'request'],
    ['Test Preparation', 'In Progress', 'test'],
    ['Test Execution', 'In Progress', 'test'],
    ['Internal Review', 'In Progress', 'test'],
    ['Customer Review', 'In Progress', 'test'],
    [undefined, 'Completed', 'completed'],
  ] as const)('maps %s / %s to %s', (stage, archiveCategory, expected) => {
    expect(demoProjectCycleGroup(workflow({ stage, archiveCategory }))).toBe(expected)
  })

  it('marks customer expectations at seven days or less as project risk', () => {
    expect(isCustomerExpectedRisk(workflow({
      health: {
        level: 'critical',
        reason: '距客户预期仅 7 天',
        daysSinceProgress: 1,
        daysToCustomerExpected: 7,
      },
    }))).toBe(true)
    expect(isCustomerExpectedRisk(workflow({
      health: {
        level: 'healthy',
        reason: '正常推进',
        daysSinceProgress: 1,
        daysToCustomerExpected: 8,
      },
    }))).toBe(false)
  })

  it('does not flag completed projects even when their customer date is overdue', () => {
    expect(isCustomerExpectedRisk(workflow({
      archiveCategory: 'Completed',
      stage: undefined,
      health: {
        level: 'critical',
        reason: '客户预期已逾期 6 天',
        daysSinceProgress: 6,
        daysToCustomerExpected: -6,
      },
    }))).toBe(false)
  })

  it('keeps completed archives from the last 100 days and excludes older records', () => {
    const completed = (date: string) => workflow({
      archiveCategory: 'Completed',
      stage: undefined,
      projectTimeline: [
        { key: 'customer-review', label: 'Customer Review', state: 'Done', date },
      ],
    })

    expect(isRecentCompletedProject(completed('2026-04-20'), '2026-07-29')).toBe(true)
    expect(isRecentCompletedProject(completed('2026-04-19'), '2026-07-29')).toBe(false)
  })

  it('sorts completed archives from the last 100 days newest first', () => {
    const completed = (id: string, date: string) => workflow({
      id,
      archiveCategory: 'Completed',
      stage: undefined,
      projectTimeline: [
        { key: 'customer-review', label: 'Customer Review', state: 'Done', date },
      ],
    })

    expect(recentCompletedProjects([
      completed('DR-OLDER', '2026-07-20'),
      completed('DR-EXPIRED', '2026-04-19'),
      completed('DR-NEWEST', '2026-07-28'),
    ], '2026-07-29').map((item) => item.id)).toEqual([
      'DR-NEWEST',
      'DR-OLDER',
    ])
  })

  it('builds eight milestones with Internal Review before Customer Review', () => {
    expect(buildDemoProjectTimeline(workflow({ stage: 'Manager Approval' }))).toEqual([
      expect.objectContaining({ label: 'Sales Preparation', state: 'Done' }),
      expect.objectContaining({ label: 'Engineer Review', state: 'Done' }),
      expect.objectContaining({ label: 'Manager Approval', state: 'Current' }),
      expect.objectContaining({ key: 'wafer-preparation', label: 'Wafer Preparation', state: 'Waiting' }),
      expect.objectContaining({ label: 'Test Preparation', state: 'Waiting' }),
      expect.objectContaining({ label: 'Test Execution', state: 'Waiting' }),
      expect.objectContaining({ label: 'Internal Review', state: 'Waiting' }),
      expect.objectContaining({ label: 'Customer Review', state: 'Waiting' }),
    ])
  })

  it('adds wafer preparation to legacy saved timelines without changing their preparation state', () => {
    const timeline = buildDemoProjectTimeline(workflow({
      projectTimeline: [
        { key: 'sales-preparation', label: 'Sales Preparation', state: 'Done' },
        {
          key: 'test-preparation',
          label: 'Test Preparation',
          state: 'Current',
          date: '2026-07-31',
          actor: 'Engineer',
        },
        { key: 'test-execution', label: 'Test Execution', state: 'Waiting' },
      ],
    }))

    expect(timeline.map((step) => step.key)).toEqual([
      'sales-preparation',
      'wafer-preparation',
      'test-preparation',
      'test-execution',
    ])
    expect(timeline[1]).toEqual({
      key: 'wafer-preparation',
      label: 'Wafer Preparation',
      state: 'Current',
      date: '2026-07-31',
      actor: 'Engineer',
    })
  })

  it('opens the preparation gate only after both parallel branches are done', () => {
    expect(preparationGateState([
      { key: 'wafer-preparation', label: 'Wafer Preparation', state: 'Done' },
      { key: 'test-preparation', label: 'Test Preparation', state: 'Waiting' },
    ])).toBe('Current')
    expect(preparationGateState([
      { key: 'wafer-preparation', label: 'Wafer Preparation', state: 'Done' },
      { key: 'test-preparation', label: 'Test Preparation', state: 'Done' },
    ])).toBe('Done')
  })
})
