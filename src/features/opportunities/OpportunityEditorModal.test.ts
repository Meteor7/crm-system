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

  it('asks for one of the four success probability levels on create instead of a forecast or an automatic percentage', () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    const select = wrapper.get('[aria-label="成功概率"]')

    expect(select.findAll('option').map((option) => option.attributes('value'))).toEqual(['', 'low_probability', 'pipeline', 'upside', 'committed'])
    expect(select.findAll('option').map((option) => option.text())).toEqual(['请选择成功概率', '低', '在途', '有望', '确定'])
    // The empty entry only prompts; it cannot be chosen.
    expect(select.get('option[value=""]').attributes('disabled')).toBeDefined()
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(select.attributes('required')).toBeDefined()
    expect(wrapper.find('[aria-label="预测分类"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="calculated-opportunity-probability"]').exists()).toBe(false)
    expect(wrapper.get('[aria-label="购买意愿"]').attributes('type')).toBe('range')
  })

  it('requires a level on create and lets whoever opens the Opportunity set it for another owner', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person029@crm.example.invalid' } })
    const select = wrapper.get('[aria-label="成功概率"]')
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)

    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.get('[data-field-error="probabilityLevel"]').text()).toBe('请选择成功概率')

    // The Manager opening this for Alex still sets the first level.
    expect((select.element as HTMLSelectElement).disabled).toBe(false)
    expect(wrapper.find('[data-testid="opportunity-probability-level-owner-only"]').exists()).toBe(false)
    await select.setValue('upside')
    expect(wrapper.find('[data-field-error="probabilityLevel"]').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ owner: 'person002@crm.example.invalid', probabilityLevel: 'upside', qualificationConfirmed: true })
    expect(wrapper.emitted('submit')?.[0]?.[0]).not.toHaveProperty('probabilityReason')
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

  it('offers the equipment catalog without pre-filling a type', () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, equipmentTypes: ['Aconca', 'Drakens', 'Kibo', 'Nansi', 'Veymont', 'Probe 9'] } })
    const select = wrapper.get('select[aria-label="设备类型"]')

    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(select.findAll('option').map((option) => option.text())).toEqual(
      ['请选择设备类型', 'Aconca', 'Drakens', 'Kibo', 'Nansi', 'Veymont', 'Probe 9', '＋自定义设备类型'],
    )
  })

  it('falls back to the five presets and keeps a stored type that is not an option', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity: { ...legacyOpportunity('Service'), toolType: 'kibo  4895c' } } })
    const select = wrapper.get('select[aria-label="设备类型"]')

    expect(select.findAll('option').map((option) => option.text()).slice(0, 5)).toEqual(['Aconca', 'Drakens', 'Kibo', 'Nansi', 'Veymont'])
    expect((wrapper.get('input[aria-label="设备类型"]').element as HTMLInputElement).value).toBe('kibo  4895c')
    await select.setValue('Kibo')
    expect(wrapper.find('input[aria-label="设备类型"]').exists()).toBe(false)
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
    await wrapper.get('[aria-label="成功概率"]').setValue('pipeline')
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

  it('never lets a set level return to pending, at any stage', () => {
    const owner = { ...props, currentUserId: 'person002@crm.example.invalid' }
    const leveled = mount(OpportunityEditorModal, {
      props: { ...owner, opportunity: { ...legacyOpportunity('New Equipment'), owner: 'person002@crm.example.invalid', stage: 'qualified_opportunity', probabilityLevel: 'pipeline' } as StrategyOpportunityDto },
    })
    const older = mount(OpportunityEditorModal, {
      props: { ...owner, opportunity: { ...legacyOpportunity('New Equipment'), owner: 'person002@crm.example.invalid', stage: 'qualified_opportunity', probabilityLevel: '' } as StrategyOpportunityDto },
    })

    expect(leveled.find('[aria-label="成功概率"] option[value=""]').exists()).toBe(false)
    // An Opportunity from before the levels still shows pending, but nothing can be put back to it.
    const pending = older.get('[aria-label="成功概率"] option[value=""]')
    expect(pending.text()).toBe('待销售确认')
    expect(pending.attributes('disabled')).toBeDefined()
    expect((older.get('[aria-label="成功概率"]').element as HTMLSelectElement).value).toBe('')
  })

  it('asks the owner for a reason before lowering the level, and only then', async () => {
    const opportunity = { ...legacyOpportunity('New Equipment'), owner: 'person002@crm.example.invalid', stage: 'quotation_sent', probabilityLevel: 'upside' } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity, currentUserId: 'person002@crm.example.invalid' } })
    const select = wrapper.get('[aria-label="成功概率"]')

    await select.setValue('committed')
    expect(wrapper.find('[data-testid="opportunity-probability-reason"]').exists()).toBe(false)

    await select.setValue('pipeline')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.get('[data-field-error="probabilityReason"]').text()).toBe('降低成功概率时请填写原因')

    await wrapper.get('[data-testid="opportunity-probability-reason"]').setValue('  客户预算推迟  ')
    expect(wrapper.find('[data-field-error="probabilityReason"]').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('[data-field-error="probabilityActionPlan"]').exists()).toBe(true)
    await wrapper.get('[data-testid="opportunity-probability-plan"]').setValue('  与采购确认预算时间  ')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ probabilityLevel: 'pipeline', probabilityReason: '客户预算推迟', probabilityActionPlan: '与采购确认预算时间' })

    // Raising it back needs no reason and sends none.
    await select.setValue('committed')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[1]?.[0]).toMatchObject({ probabilityLevel: 'committed' })
    expect(wrapper.emitted('submit')?.[1]?.[0]).not.toHaveProperty('probabilityReason')
    expect(wrapper.emitted('submit')?.[1]?.[0]).not.toHaveProperty('probabilityActionPlan')
  })
})

describe('OpportunityEditorModal amount in CNY', () => {
  it('asks for the amount in CNY on every Opportunity and flags one that has none yet', async () => {
    const create = mount(OpportunityEditorModal, { props })
    expect(create.get('[aria-label="人民币金额"]').attributes('required')).toBeDefined()
    expect(create.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)

    const filled = mount(OpportunityEditorModal, { props: { ...props, opportunity: { ...legacyOpportunity('Service'), amountCny: '32500000.00' } } })
    expect((filled.get('[aria-label="人民币金额"]').element as HTMLInputElement).value).toBe('32500000.00')
    expect(filled.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)

    const missing = mount(OpportunityEditorModal, { props: { ...props, opportunity: { ...legacyOpportunity('Service'), amountCny: '' } } })
    expect(missing.get('[data-testid="opportunity-amount-cny-missing"]').text()).toBe('这个商机还没有人民币金额，保存前请先填写。')
    await missing.get('[aria-label="人民币金额"]').setValue('1234.5')
    await missing.get('form').trigger('submit')
    expect(missing.emitted('submit')?.[0]?.[0]).toMatchObject({ amountCny: '1234.5' })
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
