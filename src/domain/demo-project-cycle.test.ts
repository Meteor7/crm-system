import { describe, expect, it } from 'vitest'
import type { DemoWorkflowDto } from '@/types/workspaces'
import {
  buildDemoProjectTimeline,
  demoProjectCycleGroup,
  isCustomerExpectedRisk,
  isRecentCompletedProject,
  preparationGateState,
  recentCompletedProjects,
  recentTerminatedProjects,
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

  it.each([false, true])('uses only the current retest round for timeline dates (new run: %s)', (hasCurrentRun) => {
    const firstRun = {
      id: 'RUN-1', date: '2026-09-01', lot: 'Round 1', round: 1,
      wafers: 1, status: 'Completed' as const, summary: '',
      capture: null, falsePositive: null, wph: null,
    }
    const runs = [firstRun]
    if (hasCurrentRun) runs.push({ ...firstRun, id: 'RUN-2', date: '2026-09-18', round: 2 })
    const item = workflow({
      stage: 'Test Execution', testRound: 2,
      evaluation: { id: 'EVAL-1', status: 'Testing', owner: 'Engineer', testRunDeadline: '', runs },
    })

    const timeline = buildDemoProjectTimeline(item)
    expect(timeline.find(step => step.key === 'test-execution')).toMatchObject({
      state: 'Current', date: hasCurrentRun ? '2026-09-18' : undefined,
    })
    expect(timeline.find(step => step.key === 'internal-review')).toMatchObject({
      state: 'Waiting', date: hasCurrentRun ? '2026-09-18' : undefined,
    })
    expect(item.evaluation?.runs[0]).toEqual(firstRun)
    expect(item.evaluation?.runs).toHaveLength(hasCurrentRun ? 2 : 1)
  })

  describe('terminated Demos', () => {
    const tracking = (lastProgressAt: string) => ({
      lastProgressAt, lastProgressSummary: 'Demo Test terminated: Customer paused the project', lastProgressActor: 'Engineer',
      nextAction: '', nextActionOwner: '', nextActionDue: '',
    })
    const evaluation = (status: string) => ({
      id: 'EVAL-1', status, owner: 'Engineer', testRunDeadline: '',
      waferPreparationStatus: 'Completed' as const, testPreparationStatus: 'Pending' as const, runs: [],
    })
    // What list_demo_workflows returns for each archived outcome, minus the server timeline.
    const archived = (status: string, terminationReason = '', overrides: Partial<DemoWorkflowDto> = {}) => workflow({
      status, terminationReason, archiveCategory: 'Completed', stage: undefined,
      evaluation: evaluation(status), customerExpectedDate: '2026-07-10', tracking: tracking('2026-07-20T08:00:00Z'), ...overrides,
    })
    const terminated = (overrides: Partial<DemoWorkflowDto> = {}) => archived('Rejected', 'Customer paused the project', overrides)

    it('groups a terminated Demo on its own while historical Rejected and Accepted stay completed', () => {
      expect(demoProjectCycleGroup(terminated())).toBe('terminated')
      expect(demoProjectCycleGroup(archived('Rejected'))).toBe('completed')
      expect(demoProjectCycleGroup(archived('Accepted'))).toBe('completed')
    })

    it('never counts a terminated Demo as completed but lists recent terminations newest first', () => {
      const withCustomerReview = (item: DemoWorkflowDto) => ({
        ...item, projectTimeline: [{ key: 'customer-review', label: 'Customer Review', state: 'Done' as const, date: '2026-07-20' }],
      })
      const items = [
        withCustomerReview(terminated({ id: 'DR-TERMINATED-OLDER', tracking: tracking('2026-07-01T08:00:00Z') })),
        withCustomerReview(terminated({ id: 'DR-TERMINATED-EXPIRED', tracking: tracking('2026-04-19T08:00:00Z') })),
        withCustomerReview(terminated({ id: 'DR-TERMINATED-NEWEST', tracking: tracking('2026-07-25T08:00:00Z') })),
        withCustomerReview(archived('Rejected', '', { id: 'DR-HISTORICAL' })),
        withCustomerReview(archived('Accepted', '', { id: 'DR-ACCEPTED' })),
      ]

      expect(items.filter((item) => isRecentCompletedProject(item, '2026-07-29')).map((item) => item.id))
        .toEqual(['DR-HISTORICAL', 'DR-ACCEPTED'])
      expect(recentCompletedProjects(items, '2026-07-29').map((item) => item.id)).toEqual(['DR-HISTORICAL', 'DR-ACCEPTED'])
      expect(recentTerminatedProjects(items, '2026-07-29').map((item) => item.id))
        .toEqual(['DR-TERMINATED-NEWEST', 'DR-TERMINATED-OLDER'])
    })

    it('builds a fallback timeline that stops where the terminated Demo stopped', () => {
      const timeline = buildDemoProjectTimeline(terminated())

      expect(timeline.map((step) => [step.key, step.state])).toEqual([
        ['sales-preparation', 'Done'],
        ['engineer-review', 'Done'],
        ['manager-approval', 'Done'],
        ['wafer-preparation', 'Done'],
        ['test-preparation', 'Waiting'],
        ['test-execution', 'Waiting'],
        ['internal-review', 'Waiting'],
        ['customer-review', 'Waiting'],
      ])
      // The customer review was never reached, so it gets no date.
      expect(timeline.at(-1)?.date).toBeUndefined()
    })

    it('keeps the fallback timeline of historical Rejected and Accepted Demos fully done', () => {
      for (const status of ['Rejected', 'Accepted']) {
        const timeline = buildDemoProjectTimeline(archived(status))
        expect(timeline.every((step) => step.state === 'Done'), status).toBe(true)
        expect(timeline.at(-1)?.date, status).toBe('2026-07-10')
      }
    })

    it('shows the server timeline of a terminated Demo as given', () => {
      const projectTimeline = [
        { key: 'sales-preparation', label: 'Sales Preparation', state: 'Done' as const, date: '2026-06-01' },
        { key: 'engineer-review', label: 'Engineer Review', state: 'Done' as const },
        { key: 'manager-approval', label: 'Manager Approval', state: 'Done' as const },
        { key: 'wafer-preparation', label: 'Wafer Preparation', state: 'Waiting' as const },
        { key: 'test-preparation', label: 'Test Preparation', state: 'Waiting' as const },
        { key: 'test-execution', label: 'Test Execution', state: 'Waiting' as const },
        { key: 'internal-review', label: 'Internal Review', state: 'Waiting' as const },
        { key: 'customer-review', label: 'Customer Review', state: 'Waiting' as const, date: '' },
      ]
      expect(buildDemoProjectTimeline(terminated({ projectTimeline }))).toEqual(projectTimeline)
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
