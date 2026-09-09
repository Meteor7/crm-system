import { flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/i18n'
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
    const select = wrapper.get('[aria-label="销售类型"]')

    expect(select.element.tagName).toBe('SELECT')
    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual([
      'New Equipment',
      'Repeat Order',
      'Service',
    ])
    expect((select.element as HTMLSelectElement).value).toBe('New Equipment')
  })

  it('uses only forecast values accepted by the backend contract', () => {
    const wrapper = mount(OpportunityEditorModal, { props })
    const select = wrapper.get('[aria-label="预测分类"]')

    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual([
      'Pipeline',
      'Best Case',
      'Commit',
      'Closed',
    ])
  })

  it('uses Inspection Tool as a hint without pre-filling the equipment type', () => {
    const wrapper = mount(OpportunityEditorModal, { props })
    const input = wrapper.get('[aria-label="设备类型"]')

    expect(input.attributes('placeholder')).toBe('检测设备示例')
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

    expect((wrapper.get('[aria-label="销售类型"]').element as HTMLSelectElement).value).toBe(expected)
  })
})


it.each([
  ['需求发现', 'Discovery'], ['Wafer Demo确认', 'Wafer demo confirmed'], ['预算审批', 'Budget approval'],
  ['设备规格确认', 'Equipment specification'], ['报价', 'Quotation'], ['采购流程', 'Procurement'],
] as const)('translates the read-only %s stage and preserves the submitted enum', async (stage, english) => {
  const opportunity = { ...legacyOpportunity('Service'), stage }
  const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
  expect(wrapper.get('.readonly-stage strong').text()).toBe(stage)
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('.readonly-stage strong').text()).toBe(english)
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ stage })
  expect(opportunity.stage).toBe(stage)
  wrapper.unmount()
})
