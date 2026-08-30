import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { initializePersonnelDirectory, PERSONNEL } from '@/demo/personnel'
import { createEmptyDemoRequestFormData } from '@/domain/demo-request-form'
import DemoRequestForm from './DemoRequestForm.vue'

describe('Demo Request Frappe owner directory', () => {
  const initialPersonnel = structuredClone(PERSONNEL)
  afterEach(() => initializePersonnelDirectory(initialPersonnel))

  it('shows owners loaded by Bootstrap after the form module was imported', () => {
    initializePersonnelDirectory([
      {
        id: 'person064@staff.example.invalid',
        availableForAssignment: true,
        name: '演示员工201',
        initials: '严成',
        role: 'Sales',
        team: '销售经理',
        teamOwners: [],
        assignedAccountIds: [],
      },
      {
        id: 'person027@staff.example.invalid',
        availableForAssignment: true,
        name: '演示员工224',
        initials: '李建',
        role: 'Engineer',
        team: 'FSE工程师',
        teamOwners: [],
        assignedAccountIds: [],
      },
    ])

    const wrapper = mount(DemoRequestForm, {
      props: {
        modelValue: createEmptyDemoRequestFormData('person064@staff.example.invalid'),
        accountId: '',
        accounts: [],
      },
    })

    expect(wrapper.get('select[name="salesContact"]').findAll('option').map((option) => option.text())).toEqual([
      '请选择 Sales Owner',
      '演示员工201',
    ])
    expect(wrapper.get('select[name="demoOwner"]').findAll('option').map((option) => option.text())).toEqual([
      '请选择 Engineer Owner',
      '演示员工224',
    ])
  })
})
