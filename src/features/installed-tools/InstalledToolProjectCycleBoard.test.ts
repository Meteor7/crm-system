import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { InstalledToolDto } from '@/types/workspaces'
import InstalledToolProjectCycleBoard from './InstalledToolProjectCycleBoard.vue'

const stageOrder = ['FAT', 'Shipment', 'Installation', 'SAT', 'Warranty'] as const

function tool(id: string, states: InstalledToolDto['milestones'][number]['state'][]): InstalledToolDto {
  return {
    id,
    accountId: `ACC-${id}`,
    siteId: `SITE-${id}`,
    serial: `SN-${id}`,
    model: 'AOI-X8',
    account: `Account ${id}`,
    site: 'Shanghai Fab',
    location: 'Bay 3',
    status: 'Installation',
    software: '4.2.0',
    firmware: '8.1',
    warrantyEnd: '2027-08-11',
    completeness: 80,
    sourceBookingId: `BOOK-${id}`,
    sourceOpportunityId: `OPP-${id}`,
    salesOwner: 'person002@crm.example.invalid',
    engineerOwner: 'person077@crm.example.invalid',
    salesOrder: `SO-${id}`,
    contract: `CON-${id}`,
    warrantyStart: '2026-08-11',
    serviceContract: `SVC-${id}`,
    pmCycle: 'Quarterly',
    lastService: '2026-08-01',
    operatingSystem: 'Linux',
    configuration: 'Standard',
    ownershipType: 'Customer',
    milestones: stageOrder.map((label, index) => ({
      label,
      date: `2026-08-${String(index + 1).padStart(2, '0')}`,
      state: states[index],
    })),
    documents: [],
  }
}

describe('InstalledToolProjectCycleBoard', () => {
  it('renders one row per tool with five ordered milestone states', () => {
    const item = tool('001', ['Done', 'Done', 'Current', 'Waiting', 'Waiting'])
    const wrapper = mount(InstalledToolProjectCycleBoard, { props: { items: [item], selectedId: item.id } })

    expect(wrapper.findAll('[data-installed-tool-stage-header]').map((node) => node.text()))
      .toEqual(stageOrder)
    const row = wrapper.get('[data-installed-tool-project-id="001"]')
    expect(row.classes()).toContain('selected')
    expect(row.text()).toContain('SN-001')
    expect(row.text()).toContain('Account 001')
    expect(row.text()).toContain('演示员工14')
    expect(row.findAll('[data-installed-tool-milestone]').map((node) => node.attributes('data-state')))
      .toEqual(['Done', 'Done', 'Current', 'Waiting', 'Waiting'])
    expect(row.findAll('[data-installed-tool-milestone]').map((node) => node.classes()))
      .toEqual([
        expect.arrayContaining(['is-done']),
        expect.arrayContaining(['is-done']),
        expect.arrayContaining(['is-current']),
        expect.arrayContaining(['is-waiting']),
        expect.arrayContaining(['is-waiting']),
      ])
  })

  it('emits the selected tool and renders an explicit empty state', async () => {
    const item = tool('001', ['Done', 'Current', 'Waiting', 'Waiting', 'Waiting'])
    const wrapper = mount(InstalledToolProjectCycleBoard, { props: { items: [item] } })

    await wrapper.get('[data-installed-tool-project-id="001"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(item)

    await wrapper.setProps({ items: [] })
    expect(wrapper.text()).toContain('当前筛选下暂无设备')
  })
})