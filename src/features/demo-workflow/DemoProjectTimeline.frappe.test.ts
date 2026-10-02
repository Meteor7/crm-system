import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { initializePersonnelDirectory, PERSONNEL } from '@/demo/personnel'
import { setLocale } from '@/i18n'
import type { DemoProjectTimelineState, DemoProjectTimelineStepDto, DemoWorkflowDto } from '@/types/workspaces'
import DemoProjectTimeline from './DemoProjectTimeline.vue'

describe('Demo project timeline Frappe personnel labels', () => {
  const initialPersonnel = structuredClone(PERSONNEL)
  afterEach(() => initializePersonnelDirectory(initialPersonnel))

  it('shows the employee name for the parallel preparation owner', () => {
    initializePersonnelDirectory([{
      id: 'person027@staff.example.invalid',
      availableForAssignment: true,
      name: '演示员工224',
      initials: '李建',
      role: 'Engineer',
      team: 'FSE工程师',
      teamOwners: [],
      assignedAccountIds: [],
    }])
    const item: DemoWorkflowDto = {
      id: 'CRM-DR-00077',
      accountId: 'ACC-001',
      siteId: '',
      opportunityId: '',
      title: 'Aconca FS Edge Demo',
      account: '示例企业014有限公司',
      opportunity: '',
      salesOwner: 'person064@staff.example.invalid',
      engineerOwner: 'person027@staff.example.invalid',
      equipment: 'Aconca FS Edge',
      owner: 'person027@staff.example.invalid',
      status: 'Requested',
      archiveCategory: 'In Progress',
      stage: 'Test Preparation',
      projectTimeline: [
        { key: 'wafer-preparation', label: 'Wafer Preparation', state: 'Current', actor: 'person027@staff.example.invalid' },
        { key: 'test-preparation', label: 'Test Preparation', state: 'Current', actor: 'person027@staff.example.invalid' },
      ],
      conclusion: { status: 'Pending' },
      approvals: [],
      executions: [],
      wafers: [],
      testRuns: [],
    }

    const wrapper = mount(DemoProjectTimeline, { props: { item } })

    expect(wrapper.get('[data-parallel-preparation]').text()).toContain('演示员工224')
    expect(wrapper.get('[data-parallel-preparation]').text()).not.toContain('person027@staff.example.invalid')
  })

  it('does not label completed milestones without legacy timestamps as pending scheduling', () => {
    const item: DemoWorkflowDto = {
      id: 'CRM-DR-00078',
      accountId: 'ACC-001',
      siteId: '',
      opportunityId: '',
      title: 'Completed milestone date fallback',
      account: 'Test account',
      opportunity: '',
      salesOwner: 'sales@example.invalid',
      engineerOwner: 'engineer@example.invalid',
      equipment: 'Inspection Tool',
      owner: 'engineer@example.invalid',
      status: 'Customer Review',
      archiveCategory: 'In Progress',
      stage: 'Customer Review',
      projectTimeline: [
        { key: 'engineer-review', label: 'Engineer Review', state: 'Done', actor: 'engineer@example.invalid' },
        { key: 'manager-approval', label: 'Manager Approval', state: 'Done', actor: 'manager@example.invalid', date: '2026-08-06T16:30:00Z' },
        { key: 'customer-review', label: 'Customer Review', state: 'Current', date: '2026-08-29' },
      ],
      conclusion: { status: 'Pending' },
      approvals: [],
      executions: [],
      wafers: [],
      testRuns: [],
    }

    const wrapper = mount(DemoProjectTimeline, { props: { item } })
    const text = wrapper.text()

    expect(text).toContain('已完成（时间未记录）')
    expect(text).toContain('2026-08-07')
    expect(text).toContain('2026-08-29')
    expect(text).not.toContain('待排期')
  })

})

describe('Demo project timeline of a terminated Demo', () => {
  afterEach(() => setLocale('zh-CN'))

  const milestones = [
    ['sales-preparation', 'Sales Preparation'], ['engineer-review', 'Engineer Review'],
    ['manager-approval', 'Manager Approval'], ['wafer-preparation', 'Wafer Preparation'],
    ['test-preparation', 'Test Preparation'], ['test-execution', 'Test Execution'],
    ['internal-review', 'Internal Review'], ['customer-review', 'Customer Review'],
  ] as const

  // The server timeline as projected for a Demo that stopped at `stop`: earlier steps Done,
  // the stop step Current, later steps Waiting and undated.
  function serverTimeline(stop: number, states: Partial<Record<string, DemoProjectTimelineState>> = {}): DemoProjectTimelineStepDto[] {
    return milestones.map(([key, label], index) => {
      const state = states[key] ?? (index < stop ? 'Done' : index === stop ? 'Current' : 'Waiting')
      return { key, label, state, actor: `${key}@example.invalid`, date: state === 'Done' ? `2026-07-0${index + 1}` : '' }
    })
  }

  function workflow(status: string, terminationReason: string, projectTimeline: DemoProjectTimelineStepDto[]): DemoWorkflowDto {
    return {
      id: 'CRM-DR-00090',
      accountId: 'ACC-001',
      siteId: '',
      opportunityId: '',
      title: 'Terminated milestone labels',
      account: 'Test account',
      opportunity: '',
      salesOwner: 'sales@example.invalid',
      engineerOwner: 'engineer@example.invalid',
      equipment: 'Inspection Tool',
      owner: 'engineer@example.invalid',
      status,
      terminationReason,
      archiveCategory: status === 'Rejected' ? 'Completed' : 'In Progress',
      projectTimeline,
      conclusion: { status: 'Pending' },
      approvals: [],
      executions: [],
      wafers: [],
      testRuns: [],
    }
  }

  const nodes = (wrapper: VueWrapper) => wrapper.findAll('.timeline-track > li')

  it('labels the stop node as stopped and later nodes as not reached', async () => {
    const wrapper = mount(DemoProjectTimeline, {
      props: { item: workflow('Rejected', 'Customer paused the project', serverTimeline(5)) },
    })
    // Groups: three request steps, the parallel preparation, Test Execution, Internal and Customer Review.
    const [stop, internal, customer] = nodes(wrapper).slice(4)

    expect(stop!.get('time').text()).toBe('止于此')
    expect(stop!.classes()).toContain('stopped')
    expect(stop!.classes()).not.toContain('current')
    expect(internal!.get('time').text()).toBe('未进行')
    expect(customer!.get('time').text()).toBe('未进行')
    expect(wrapper.text()).not.toContain('进行中')
    expect(wrapper.text()).not.toContain('待排期')
    expect(wrapper.find('li.current, .parallel-stage.current').exists()).toBe(false)

    setLocale('en-US')
    await nextTick()
    expect(stop!.get('time').text()).toBe('Stopped here')
    expect(internal!.get('time').text()).toBe('Not reached')
  })

  it('labels a stop in the parallel preparation the same way', () => {
    const wrapper = mount(DemoProjectTimeline, {
      props: { item: workflow('Rejected', 'Budget frozen', serverTimeline(3, { 'test-preparation': 'Current' })) },
    })
    const preparation = wrapper.get('[data-parallel-preparation]')

    expect(preparation.get('time').text()).toBe('止于此')
    expect(preparation.classes()).toContain('stopped')
    expect(preparation.get('[data-parallel-stage="wafer-preparation"]').classes()).toContain('stopped')
    expect(nodes(wrapper)[4]!.get('time').text()).toBe('未进行')
    expect(wrapper.text()).not.toContain('进行中')
    expect(wrapper.text()).not.toContain('待排期')
  })

  it.each([
    ['an in-progress Demo', 'Testing'],
    ['a historical rejection without a reason', 'Rejected'],
  ])('keeps the in-progress labels for %s', (_, status) => {
    const wrapper = mount(DemoProjectTimeline, { props: { item: workflow(status, '', serverTimeline(5)) } })
    const [current, internal] = nodes(wrapper).slice(4)

    expect(current!.get('time').text()).toBe('进行中')
    expect(current!.classes()).toContain('current')
    expect(internal!.get('time').text()).toBe('待排期')
    expect(wrapper.text()).not.toContain('止于此')
    expect(wrapper.text()).not.toContain('未进行')
  })
})
