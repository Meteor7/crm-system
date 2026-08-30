import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { initializePersonnelDirectory, PERSONNEL } from '@/demo/personnel'
import type { DemoWorkflowDto } from '@/types/workspaces'
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
