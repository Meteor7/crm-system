import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { setLocale } from '@/i18n'
import type { DemoProjectTimelineStepDto, DemoWorkflowDto } from '@/types/workspaces'
import DemoProjectCycleBoard from './DemoProjectCycleBoard.vue'

const milestones = [
  'sales-preparation', 'engineer-review', 'manager-approval', 'wafer-preparation',
  'test-preparation', 'test-execution', 'internal-review', 'customer-review',
] as const

function timeline(doneThrough: number, customerReviewDate = ''): DemoProjectTimelineStepDto[] {
  return milestones.map((key, index) => ({
    key,
    label: key,
    state: index <= doneThrough ? 'Done' : 'Waiting',
    ...(key === 'customer-review' ? { date: customerReviewDate } : {}),
  }))
}

function archived(id: string, status: string, overrides: Partial<DemoWorkflowDto> = {}): DemoWorkflowDto {
  return {
    id,
    accountId: 'ACC-001',
    siteId: '',
    opportunityId: 'OPP-001',
    title: `${id} project`,
    account: 'Test customer',
    opportunity: 'Test opportunity',
    salesOwner: 'Sales',
    engineerOwner: 'Engineer',
    equipment: 'Inspection Tool',
    owner: 'Engineer',
    status,
    terminationReason: '',
    archiveCategory: 'Completed',
    customerExpectedDate: '2026-07-10',
    projectTimeline: timeline(7, '2026-07-20'),
    conclusion: { status: status === 'Accepted' ? 'Accepted' : 'Pending' },
    approvals: [],
    executions: [],
    wafers: [],
    testRuns: [],
    ...overrides,
  }
}

describe('DemoProjectCycleBoard', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-07-29T10:00:00+08:00'))
  })

  afterEach(() => {
    vi.useRealTimers()
    setLocale('zh-CN')
  })

  it('marks a terminated Demo with its reason and neither counts nor colours it as completed', async () => {
    const items = [
      archived('DR-ACCEPTED', 'Accepted'),
      archived('DR-HISTORICAL', 'Rejected'),
      // As the server now projects it: stopped at Test Preparation, nothing later reached.
      archived('DR-TERMINATED', 'Rejected', {
        terminationReason: 'Customer paused the project',
        projectTimeline: timeline(2),
        tracking: {
          lastProgressAt: '2026-07-25T08:00:00Z', lastProgressSummary: 'Demo Test terminated: Customer paused the project',
          lastProgressActor: 'Engineer', nextAction: '', nextActionOwner: '', nextActionDue: '',
        },
      }),
    ]
    const wrapper = mount(DemoProjectCycleBoard, {
      props: { items, health: 'all', customer: 'all', salesOwner: 'all', engineerOwner: 'all' },
    })

    expect(wrapper.findAll('.board-summary article')[2]!.get('strong').text()).toBe('2')

    const terminated = wrapper.get('[data-project-id="DR-TERMINATED"]')
    expect(terminated.classes()).toContain('is-terminated-project')
    expect(terminated.classes()).not.toContain('is-completed-project')
    expect(terminated.get('[data-terminated-marker]').text()).toBe('已终止 · Customer paused the project')
    const terminatedTimeline = terminated.get('[data-project-timeline]')
    expect(terminatedTimeline.classes()).toContain('tone-terminated')
    expect(terminatedTimeline.classes()).not.toContain('tone-complete')
    // The server timeline is shown as given: only the request steps were reached.
    expect(terminatedTimeline.findAll('.timeline-track > li.done')).toHaveLength(3)

    for (const id of ['DR-ACCEPTED', 'DR-HISTORICAL']) {
      const row = wrapper.get(`[data-project-id="${id}"]`)
      expect(row.classes(), id).toContain('is-completed-project')
      expect(row.classes(), id).not.toContain('is-terminated-project')
      expect(row.find('[data-terminated-marker]').exists(), id).toBe(false)
      expect(row.get('[data-project-timeline]').classes(), id).toContain('tone-complete')
    }

    setLocale('en-US')
    await nextTick()
    expect(wrapper.get('[data-project-id="DR-TERMINATED"] [data-terminated-marker]').text()).toBe('Terminated · Customer paused the project')
    wrapper.unmount()
  })

  it('does not name the stop node owner as the current stage owner of a terminated Demo', () => {
    // As the server projects both: the stop node stays Current, like an active stage.
    const stoppedAtExecution = timeline(4).map((step) => step.key === 'test-execution'
      ? { ...step, state: 'Current' as const, actor: 'Stage Owner' }
      : step)
    const items = [
      archived('DR-ACTIVE', 'Testing', { archiveCategory: 'In Progress', projectTimeline: stoppedAtExecution }),
      archived('DR-TERMINATED', 'Rejected', {
        terminationReason: 'Customer paused the project',
        projectTimeline: stoppedAtExecution,
        tracking: {
          lastProgressAt: '2026-07-25T08:00:00Z', lastProgressSummary: 'Demo Test terminated: Customer paused the project',
          lastProgressActor: 'Engineer', nextAction: '', nextActionOwner: '', nextActionDue: '',
        },
      }),
    ]
    const wrapper = mount(DemoProjectCycleBoard, {
      props: { items, health: 'all', customer: 'all', salesOwner: 'all', engineerOwner: 'all' },
    })

    expect(wrapper.get('[data-project-id="DR-ACTIVE"] [data-current-stage-owner]').text()).toBe('Stage Owner')
    expect(wrapper.get('[data-project-id="DR-TERMINATED"] [data-current-stage-owner]').text()).toBe('Engineer')
    wrapper.unmount()
  })

  it('leaves out a termination older than the 100-day window like an old completion', () => {
    const items = [
      archived('DR-TERMINATED-EXPIRED', 'Rejected', {
        terminationReason: 'Budget frozen',
        projectTimeline: timeline(2),
        tracking: {
          lastProgressAt: '2026-04-19T08:00:00Z', lastProgressSummary: 'Demo Test terminated: Budget frozen',
          lastProgressActor: 'Engineer', nextAction: '', nextActionOwner: '', nextActionDue: '',
        },
      }),
    ]
    const wrapper = mount(DemoProjectCycleBoard, {
      props: { items, health: 'all', customer: 'all', salesOwner: 'all', engineerOwner: 'all' },
    })

    expect(wrapper.find('[data-project-id="DR-TERMINATED-EXPIRED"]').exists()).toBe(false)
    expect(wrapper.findAll('.board-summary article')[2]!.get('strong').text()).toBe('0')
    wrapper.unmount()
  })
})
