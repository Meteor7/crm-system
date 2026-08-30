import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { InstalledToolDto } from '@/types/workspaces'
import InstalledToolPipelineBoard from './InstalledToolPipelineBoard.vue'

const milestoneOrder = ['FAT', 'Shipment', 'Installation', 'SAT', 'Warranty'] as const

function tool(id: string, states: InstalledToolDto['milestones'][number]['state'][]): InstalledToolDto {
  return {
    id, accountId: `ACC-${id}`, siteId: `SITE-${id}`, serial: `SN-${id}`, model: 'AOI-X8',
    account: `Account ${id}`, site: 'Shanghai Fab', location: 'Bay 3', status: 'Active',
    software: '4.2.0', firmware: '8.1', warrantyEnd: '2027-08-11', completeness: 100,
    sourceBookingId: `BOOK-${id}`, sourceOpportunityId: `OPP-${id}`, salesOwner: 'Demo Staff 01',
    engineerOwner: 'Engineer Li', salesOrder: `SO-${id}`, contract: `CON-${id}`,
    warrantyStart: '2026-08-11', serviceContract: `SVC-${id}`, pmCycle: 'Quarterly',
    lastService: '2026-08-01', operatingSystem: 'Linux', configuration: 'Standard', ownershipType: 'Customer',
    milestones: milestoneOrder.map((label, index) => ({ label, date: `2026-08-${String(index + 1).padStart(2, '0')}`, state: states[index] })),
    documents: [],
  }
}

describe('InstalledToolPipelineBoard', () => {
  it('renders five ordered stages and groups Current, first Waiting, and all-Done tools deterministically', async () => {
    const current = tool('CURRENT', ['Done', 'Done', 'Current', 'Waiting', 'Waiting'])
    const waiting = tool('WAITING', ['Done', 'Waiting', 'Waiting', 'Waiting', 'Waiting'])
    const done = tool('DONE', ['Done', 'Done', 'Done', 'Done', 'Done'])
    const wrapper = mount(InstalledToolPipelineBoard, { props: { items: [current, waiting, done], selectedId: current.id } })

    expect(wrapper.findAll('[data-pipeline-board] .segment').map((node) => node.text()))
      .toEqual(['FAT0', 'Shipment1', 'Installation1', 'SAT0', 'Warranty1'])
    expect(wrapper.get('[aria-label="Shipment"]').text()).toContain('SN-WAITING')
    expect(wrapper.get('[aria-label="Installation"]').text()).toContain('SN-CURRENT')
    expect(wrapper.get('[aria-label="Warranty"]').text()).toContain('SN-DONE')
    expect(wrapper.get('[data-installed-tool-id="CURRENT"]').text()).toContain('2/5 已完成')
    expect(wrapper.get('[data-installed-tool-id="DONE"]').text()).toContain('5/5 已完成')

    const card = wrapper.get('[data-installed-tool-id="CURRENT"]')
    expect(card.classes()).toContain('selected')
    await card.trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(current)
  })

  it('keeps all five empty columns when no tools match', () => {
    const wrapper = mount(InstalledToolPipelineBoard, { props: { items: [] } })
    expect(wrapper.findAll('[data-pipeline-board] .segment')).toHaveLength(5)
    expect(wrapper.findAll('p').map((node) => node.text())).toEqual(Array(5).fill('当前阶段暂无设备'))
  })
})
