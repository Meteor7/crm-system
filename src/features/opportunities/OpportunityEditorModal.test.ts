import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { opportunities } from '@/demo/operations-data'
import type { StrategyOpportunityDto } from '@/types/workspaces'
import OpportunityEditorModal from './OpportunityEditorModal.vue'

const props = {
  accounts: [],
  sitesByAccount: {},
  defaultOwner: '',
}

function legacyOpportunity(saleType: string) {
  return { ...opportunities[0], saleType } as unknown as StrategyOpportunityDto
}

describe('OpportunityEditorModal sale type', () => {
  it('never exposes Opportunity stage as an editable field', () => {
    const create = mount(OpportunityEditorModal, { props })
    const edit = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: legacyOpportunity('Service') },
    })

    expect(create.find('[aria-label="Opportunity 阶段"]').exists()).toBe(false)
    expect(edit.find('[aria-label="Opportunity 阶段"]').exists()).toBe(false)
    expect(edit.text()).toContain(opportunities[0].stage)
  })

  it('uses the backend enum as a fixed dropdown for new Opportunities', () => {
    const wrapper = mount(OpportunityEditorModal, { props })
    const select = wrapper.get('[aria-label="Opportunity 销售类型"]')

    expect(select.element.tagName).toBe('SELECT')
    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual([
      'New Equipment',
      'Repeat Order',
      'Service',
    ])
    expect((select.element as HTMLSelectElement).value).toBe('New Equipment')
  })

  it('uses Inspection Tool as a hint without pre-filling the equipment type', () => {
    const wrapper = mount(OpportunityEditorModal, { props })
    const input = wrapper.get('[aria-label="Opportunity 设备类型"]')

    expect(input.attributes('placeholder')).toBe('Inspection Tool')
    expect((input.element as HTMLInputElement).value).toBe('')
  })

  it.each([
    ['New Tool', 'New Equipment'],
    ['Capacity Expansion', 'Repeat Order'],
    ['Service', 'Service'],
  ])('normalizes %s to %s when editing', (saleType, expected) => {
    const wrapper = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: legacyOpportunity(saleType) },
    })

    expect((wrapper.get('[aria-label="Opportunity 销售类型"]').element as HTMLSelectElement).value).toBe(expected)
  })
})
