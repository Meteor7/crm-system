import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { initializePersonnelDirectory, PERSONNEL } from '@/demo/personnel'
import type { PersonnelIdentity } from '@/demo/personnel'
import type { BookingDto, SiteDto } from '@/types/crm'
import BookingInstalledToolModal from './BookingInstalledToolModal.vue'

describe('Booking Installed Tool Frappe engineer directory', () => {
  const initialPersonnel = structuredClone(PERSONNEL)

  afterEach(() => initializePersonnelDirectory(initialPersonnel))

  it('shows assignable engineers loaded by Bootstrap after the modal module was imported', () => {
    initializePersonnelDirectory([
      {
        id: 'person011@staff.example.invalid',
        availableForAssignment: true,
        name: '演示员工224',
        initials: '李',
        role: 'Engineer',
        team: 'FSE工程师',
        teamOwners: [],
        assignedAccountIds: [],
      },
      {
        id: 'person022@staff.example.invalid',
        availableForAssignment: false,
        name: '停用工程师',
        initials: '停',
        role: 'Engineer',
        team: 'FSE工程师',
        teamOwners: [],
        assignedAccountIds: [],
      },
    ])

    const wrapper = mount(BookingInstalledToolModal, {
      props: {
        booking: {
          id: 'BKG-001',
          accountName: '测试客户',
          owner: 'sales@staff.example.invalid',
          equipment: 'Inspection 3000',
        } as BookingDto,
        sites: [{ id: 'SITE-001', name: '上海厂区', city: '上海' }] as SiteDto[],
        engineers: PERSONNEL.filter((person) => person.role === 'Engineer' && person.availableForAssignment),
      },
    })

    const options = wrapper.get('select[aria-label="负责工程师"]').findAll('option')
    expect(options.map((option) => option.attributes('value'))).toEqual([
      'person011@staff.example.invalid',
    ])
    expect(options.map((option) => option.text())).toEqual(['演示员工224 · 工程师'])
  })

  it('refreshes the dropdown when Bootstrap engineers arrive after the modal opens', async () => {
    initializePersonnelDirectory([])
    const booking = {
      id: 'BKG-001',
      accountName: '测试客户',
      owner: 'sales@staff.example.invalid',
      equipment: 'Inspection 3000',
    } as BookingDto
    const sites = [{ id: 'SITE-001', name: '上海厂区', city: '上海' }] as SiteDto[]
    const wrapper = mount(BookingInstalledToolModal, {
      props: { booking, sites, engineers: [] } as unknown as {
        booking: BookingDto
        sites: SiteDto[]
        engineers: PersonnelIdentity[]
      },
    })

    expect(wrapper.get('select[aria-label="负责工程师"]').findAll('option')).toHaveLength(0)

    await wrapper.setProps({
      engineers: [{
        id: 'person011@staff.example.invalid',
        availableForAssignment: true,
        name: '演示员工224',
        initials: '李',
        role: 'Engineer',
        team: 'FSE工程师',
        teamOwners: [],
        assignedAccountIds: [],
      }],
    } as unknown as Partial<{ engineers: PersonnelIdentity[] }>)

    expect(wrapper.get('select[aria-label="负责工程师"]').findAll('option').map((option) => option.text()))
      .toEqual(['演示员工224 · 工程师'])
  })
})
