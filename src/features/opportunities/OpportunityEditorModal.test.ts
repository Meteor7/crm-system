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
    expect(edit.text()).toContain('报价已发')
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

  it('offers pending plus the four success probability levels instead of a forecast or an automatic percentage', () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    const select = wrapper.get('[aria-label="成功概率"]')

    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual(['', 'low_probability', 'pipeline', 'upside', 'committed'])
    expect(select.findAll('option').map((option) => option.text())).toEqual(['待销售确认', '低', '在途', '有望', '确定'])
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(select.attributes('required')).toBeUndefined()
    expect(wrapper.find('[aria-label="预测分类"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="calculated-opportunity-probability"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="购买意愿"]').attributes('type')).toBe('range')
  })

  it('lets a creator set the level only for an Opportunity they own and sends pending otherwise', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    const select = wrapper.get('[aria-label="成功概率"]')

    expect((select.element as HTMLSelectElement).disabled).toBe(false)
    await select.setValue('upside')
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ owner: 'person002@crm.example.invalid', probabilityLevel: 'upside', qualificationConfirmed: true })

    await wrapper.get('[aria-label="负责人"]').setValue('person005@crm.example.invalid')
    expect((select.element as HTMLSelectElement).disabled).toBe(true)
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(wrapper.get('[data-testid="opportunity-probability-level-owner-only"]').text()).toBe('仅商机负责人可设置成功概率')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[1]?.[0]).toMatchObject({ owner: 'person005@crm.example.invalid', probabilityLevel: '' })
  })

  it('keeps the level read-only for everyone except the Opportunity owner when editing', async () => {
    const opportunity = { ...legacyOpportunity('Service'), owner: 'person002@crm.example.invalid', probabilityLevel: 'pipeline' } as StrategyOpportunityDto
    const manager = mount(OpportunityEditorModal, { props: { ...props, opportunity, currentUserId: 'person029@crm.example.invalid' } })
    const managerSelect = manager.get('[aria-label="成功概率"]').element as HTMLSelectElement

    expect(managerSelect.disabled).toBe(true)
    expect(managerSelect.value).toBe('pipeline')
    await manager.get('form').trigger('submit')
    expect(manager.emitted('submit')?.[0]?.[0]).not.toHaveProperty('probabilityLevel')

    const owner = mount(OpportunityEditorModal, { props: { ...props, opportunity, currentUserId: 'person002@crm.example.invalid' } })
    await owner.get('[aria-label="成功概率"]').setValue('committed')
    await owner.get('[aria-label="购买意愿"]').setValue(20)
    await owner.get('form').trigger('submit')
    expect(owner.emitted('submit')?.[0]?.[0]).toMatchObject({ probabilityLevel: 'committed', intentScore: 20 })
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


describe('OpportunityEditorModal qualification and level rules', () => {
  it('requires the customer need and budget owner confirmation before creating', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    const checkbox = wrapper.get('[data-testid="qualification-confirmed"]')

    expect(checkbox.attributes('aria-label')).toBe('已确认客户需求与预算负责人')
    expect(checkbox.attributes('required')).toBeDefined()
    expect(wrapper.get('.readonly-stage strong').text()).toBe('合格商机')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.get('[data-field-error="qualificationConfirmed"]').text()).toBe('请先确认客户需求与预算负责人')

    await checkbox.setValue(true)
    expect(wrapper.find('[data-field-error="qualificationConfirmed"]').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ qualificationConfirmed: true })
    expect(wrapper.emitted('submit')?.[0]?.[0]).not.toHaveProperty('stage')
  })

  it('does not ask for the confirmation again when editing', () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity: legacyOpportunity('Service') } })
    expect(wrapper.find('[data-testid="qualification-confirmed"]').exists()).toBe(false)
  })

  it.each(['po_received', 'lost'] as const)('freezes the level for the owner at %s', async (stage) => {
    const opportunity = { ...legacyOpportunity('New Equipment'), owner: 'person002@crm.example.invalid', probabilityLevel: 'committed', stage } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity, currentUserId: 'person002@crm.example.invalid' } })
    const select = wrapper.get('[aria-label="成功概率"]').element as HTMLSelectElement

    expect(select.disabled).toBe(true)
    expect(wrapper.get('[data-testid="opportunity-probability-level-frozen"]').text()).toBe('收到 PO 或丢单后，成功概率不可修改')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).not.toHaveProperty('probabilityLevel')
  })

  it('keeps pending selectable only before the demo is done', () => {
    const owner = { ...props, currentUserId: 'person002@crm.example.invalid' }
    const early = mount(OpportunityEditorModal, {
      props: { ...owner, opportunity: { ...legacyOpportunity('New Equipment'), owner: 'person002@crm.example.invalid', stage: 'qualified_opportunity' } as StrategyOpportunityDto },
    })
    const later = mount(OpportunityEditorModal, {
      props: { ...owner, opportunity: { ...legacyOpportunity('New Equipment'), owner: 'person002@crm.example.invalid', stage: 'demo_done' } as StrategyOpportunityDto },
    })

    expect(early.get('[aria-label="成功概率"] option[value=""]').attributes('disabled')).toBeUndefined()
    expect(later.get('[aria-label="成功概率"] option[value=""]').attributes('disabled')).toBeDefined()
    expect((later.get('[aria-label="成功概率"]').element as HTMLSelectElement).disabled).toBe(false)
  })
})

it.each([
  ['qualified_opportunity', '合格商机', 'Qualified opportunity'],
  ['demo_done', 'Demo 完成', 'Demo done'],
  ['customer_budget_approved', '客户预算批准', 'Customer budget approved'],
  ['rfq_validated', 'RFQ 通过', 'RFQ validated'],
  ['quotation_sent', '报价已发', 'Quotation sent'],
  ['internal_validation', '内部生产审批', 'Internal validation'],
  ['po_received', '收到 PO', 'PO received'],
  ['lost', '丢单', 'Lost'],
] as const)('shows the read-only %s stage in both locales and never submits a stage', async (stage, chinese, english) => {
  const opportunity = { ...legacyOpportunity('Service'), stage }
  const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
  expect(wrapper.get('.readonly-stage strong').text()).toBe(chinese)
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('.readonly-stage strong').text()).toBe(english)
  await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('submit')?.[0]?.[0]).not.toHaveProperty('stage')
  expect(wrapper.emitted('submit')?.[0]?.[0]).not.toHaveProperty('qualificationConfirmed')
  expect(opportunity.stage).toBe(stage)
  setLocale('zh-CN')
  wrapper.unmount()
})
