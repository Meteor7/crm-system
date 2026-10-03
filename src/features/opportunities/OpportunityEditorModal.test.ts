import { flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/i18n'
import { describe, expect, it } from 'vitest'
import { opportunities } from '@/demo/operations-data'
import { accounts, sites } from '@/api/mock-data'
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
  it('asks for the amount in CNY once past stage 1 and flags an Opportunity that has none yet', async () => {
    const create = mount(OpportunityEditorModal, { props })
    expect(create.get('[aria-label="人民币金额"]').attributes('required')).toBeUndefined()
    expect(create.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)

    // In another currency Sales enter the amount in CNY by hand.
    const foreign = { ...legacyOpportunity('Service'), currency: 'USD' }
    const filled = mount(OpportunityEditorModal, { props: { ...props, opportunity: { ...foreign, amountCny: '32500000.00' } } })
    expect((filled.get('[aria-label="人民币金额"]').element as HTMLInputElement).value).toBe('32500000.00')
    expect(filled.get('[aria-label="人民币金额"]').attributes('readonly')).toBeUndefined()
    expect(filled.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)

    const missing = mount(OpportunityEditorModal, { props: { ...props, opportunity: { ...foreign, amountCny: '' } } })
    expect(missing.get('[aria-label="人民币金额"]').attributes('required')).toBe('')
    expect(missing.get('[data-testid="opportunity-amount-cny-missing"]').text()).toBe('这个商机还没有人民币金额，保存前请先填写。')
    await missing.get('[aria-label="人民币金额"]').setValue('1234.5')
    await missing.get('form').trigger('submit')
    expect(missing.emitted('submit')?.[0]?.[0]).toMatchObject({ amountCny: '1234.5' })

    // Saving at stage 1 does not need it, so there is nothing to flag.
    const early = mount(OpportunityEditorModal, { props: { ...props, opportunity: { ...foreign, stage: 'qualified_opportunity', amountCny: '' } } })
    expect(early.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)
  })

  it('fills the amount in CNY from the amount for a CNY Opportunity and hands it back when the currency changes', async () => {
    const wrapper = mount(OpportunityEditorModal, { props })
    const amountCny = () => wrapper.get('[aria-label="人民币金额"]')
    // A new Opportunity starts in CNY: one amount, shown twice, typed once.
    await wrapper.get('[aria-label="金额"]').setValue('120000')
    expect((amountCny().element as HTMLInputElement).value).toBe('120000')
    expect(amountCny().attributes('readonly')).toBe('')
    expect(wrapper.get('[data-testid="opportunity-amount-cny-follows"]').text()).toBe('随金额自动填写，无需另填。')

    // In another currency the mirrored figure would be wrong by the exchange rate, so it does not stay.
    await wrapper.get('[aria-label="币种"]').setValue('USD')
    expect(amountCny().attributes('readonly')).toBeUndefined()
    expect(wrapper.find('[data-testid="opportunity-amount-cny-follows"]').exists()).toBe(false)
    expect((amountCny().element as HTMLInputElement).value).toBe('')
    await amountCny().setValue('860000')
    await wrapper.get('[aria-label="金额"]').setValue('125000')
    expect((amountCny().element as HTMLInputElement).value).toBe('860000')

    // Back in CNY the amount takes over again, also when it is cleared.
    await wrapper.get('[aria-label="币种"]').setValue('CNY')
    expect((amountCny().element as HTMLInputElement).value).toBe('125000')
    await wrapper.get('[aria-label="金额"]').setValue('')
    expect((amountCny().element as HTMLInputElement).value).toBe('')
  })

  it('gives a foreign-currency Opportunity its stored amount in CNY back after a detour through CNY', async () => {
    const wrapper = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: { ...legacyOpportunity('Service'), currency: 'USD', amount: '125000.00', amountCny: '860000.00' } },
    })
    const amountCny = () => wrapper.get('[aria-label="人民币金额"]').element as HTMLInputElement
    expect(amountCny().value).toBe('860000.00')
    await wrapper.get('[aria-label="币种"]').setValue('CNY')
    expect(amountCny().value).toBe('125000.00')
    await wrapper.get('[aria-label="币种"]').setValue('USD')
    expect(amountCny().value).toBe('860000.00')

    // A figure typed but not yet saved survives the detour as well.
    await wrapper.get('[aria-label="人民币金额"]').setValue('900000')
    await wrapper.get('[aria-label="币种"]').setValue('CNY')
    await wrapper.get('[aria-label="币种"]').setValue('USD')
    expect(amountCny().value).toBe('900000')
  })

  it('never flags a CNY Opportunity for a missing amount in CNY: it follows the amount', () => {
    const legacy = mount(OpportunityEditorModal, { props: { ...props, opportunity: { ...legacyOpportunity('Service'), currency: 'CNY', amount: '5000.00', amountCny: '' } } })
    expect(legacy.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)
    expect((legacy.get('[aria-label="人民币金额"]').element as HTMLInputElement).value).toBe('5000.00')
  })
})

describe('OpportunityEditorModal Demo done waiting for the amount', () => {
  it('tells the owner that entering the amount moves the Opportunity to Demo done', async () => {
    const waiting = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: { ...legacyOpportunity('New Equipment'), stage: 'qualified_opportunity', currency: 'CNY', amount: '', originalAmount: '', amountCny: '', pendingStageAdvance: 'demo_done' } },
    })
    const note = waiting.get('[data-testid="opportunity-pending-demo-done"]')
    expect(note.text()).toBe('Demo 已完成。填写金额后，商机会自动进入 Demo 完成阶段。')
    // In another currency the amount in CNY is entered too, and the Opportunity waits for both: the note says so.
    await waiting.get('[aria-label="币种"]').setValue('USD')
    expect(note.text()).toBe('Demo 已完成。填写金额和人民币金额后，商机会自动进入 Demo 完成阶段。')
    setLocale('en-US'); await flushPromises()
    expect(note.text()).toBe('The Demo is complete. Enter the amount and the amount in CNY to move this Opportunity to Demo done.')
    setLocale('zh-CN'); await flushPromises()
    // Still stage 1: the amounts stay optional, so any other field can be saved without them.
    expect(waiting.get('[aria-label="金额"]').attributes('required')).toBeUndefined()

    const plain = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: { ...legacyOpportunity('New Equipment'), stage: 'qualified_opportunity', pendingStageAdvance: '' } },
    })
    expect(plain.find('[data-testid="opportunity-pending-demo-done"]').exists()).toBe(false)
    // Lost while waiting: the mark is kept for a reopening, but the amounts do not move a lost deal, so nothing promises it.
    const lost = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: { ...legacyOpportunity('New Equipment'), stage: 'lost', lostAtStage: 'qualified_opportunity', pendingStageAdvance: 'demo_done' } },
    })
    expect(lost.find('[data-testid="opportunity-pending-demo-done"]').exists()).toBe(false)
    expect(mount(OpportunityEditorModal, { props }).find('[data-testid="opportunity-pending-demo-done"]').exists()).toBe(false)
  })
})

describe('OpportunityEditorModal amount requirement', () => {
  it('does not mark amount fields required when creating a new Opportunity', () => {
    const wrapper = mount(OpportunityEditorModal, { props })
    expect(wrapper.get('[aria-label="金额"]').attributes('required')).toBeUndefined()
    expect(wrapper.get('[aria-label="人民币金额"]').attributes('required')).toBeUndefined()
    expect(wrapper.get('[aria-label="原始金额"]').attributes('required')).toBeUndefined()
  })

  it('marks amount fields required when editing an Opportunity past stage 1', () => {
    const wrapper = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: { ...legacyOpportunity('New Equipment'), stage: 'demo_done' } },
    })
    expect(wrapper.get('[aria-label="金额"]').attributes('required')).toBe('')
    expect(wrapper.get('[aria-label="人民币金额"]').attributes('required')).toBe('')
    // The original amount defaults to the amount, as before.
    expect(wrapper.get('[aria-label="原始金额"]').attributes('required')).toBeUndefined()
  })

  it('does not mark amount fields required when editing an Opportunity still at stage 1', () => {
    const wrapper = mount(OpportunityEditorModal, {
      props: { ...props, opportunity: { ...legacyOpportunity('New Equipment'), stage: 'qualified_opportunity' } },
    })
    expect(wrapper.get('[aria-label="金额"]').attributes('required')).toBeUndefined()
    expect(wrapper.get('[aria-label="人民币金额"]').attributes('required')).toBeUndefined()
  })

  it('treats a deal lost at stage 1 as still at stage 1, and one lost later as past it', () => {
    const lostAt = (lostAtStage: string) => mount(OpportunityEditorModal, {
      props: { ...props, opportunity: { ...legacyOpportunity('New Equipment'), stage: 'lost', lostAtStage, lostReason: 'Budget frozen' } as StrategyOpportunityDto },
    })
    const early = lostAt('qualified_opportunity')
    expect(early.get('[aria-label="金额"]').attributes('required')).toBeUndefined()
    expect(early.get('[aria-label="人民币金额"]').attributes('required')).toBeUndefined()
    expect(early.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)
    const late = lostAt('demo_done')
    expect(late.get('[aria-label="金额"]').attributes('required')).toBe('')
    expect(late.get('[aria-label="人民币金额"]').attributes('required')).toBe('')
    // A migrated loss without its stage is treated as past stage 1, as the backend does.
    expect(lostAt('').get('[aria-label="金额"]').attributes('required')).toBe('')
  })

  it('submits a new stage-1 Opportunity with all three amounts blank, never as 0', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { accounts, sitesByAccount: sites, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('早期缺陷检测机会')
    await wrapper.get('[aria-label="成功概率"]').setValue('pipeline')
    await wrapper.get('form').trigger('submit')

    const payload = wrapper.emitted('submit')?.[0]?.[0] as Record<string, unknown>
    expect(payload).toMatchObject({ title: '早期缺陷检测机会', amount: '', originalAmount: '', amountCny: '', qualificationConfirmed: true })
    expect(payload).not.toHaveProperty('stage')
  })

  it('re-opens the returned stage-1 record with its amounts not entered and saves it again unchanged', async () => {
    // The server serves amounts nobody has entered as ''.
    const returned = { ...legacyOpportunity('New Equipment'), stage: 'qualified_opportunity', amount: '', originalAmount: '', amountCny: '' } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity: returned } })
    for (const label of ['金额', '原始金额', '人民币金额']) {
      expect((wrapper.get(`[aria-label="${label}"]`).element as HTMLInputElement).value).toBe('')
    }
    expect(wrapper.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(false)

    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('仍在合格商机阶段')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ title: '仍在合格商机阶段', amount: '', originalAmount: '', amountCny: '' })

    // A supplied amount is still sent as typed.
    await wrapper.get('[aria-label="金额"]').setValue('50000.00')
    await wrapper.get('[aria-label="人民币金额"]').setValue('50000.00')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[1]?.[0]).toMatchObject({ amount: '50000.00', originalAmount: '50000.00', amountCny: '50000.00' })
  })

  it('sends the original amount blank when the amount is cleared at stage 1, not the old one beside an unknown amount', async () => {
    const priced = { ...legacyOpportunity('New Equipment'), stage: 'qualified_opportunity', amount: '100.00', originalAmount: '100.00', amountCny: '100.00' } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity: priced } })
    await wrapper.get('[aria-label="金额"]').setValue('')
    await wrapper.get('[aria-label="人民币金额"]').setValue('')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ amount: '', originalAmount: '', amountCny: '' })
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

describe('OpportunityEditorModal single sales objective', () => {
  it('starts empty for a new Opportunity and submits what is typed', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    const field = wrapper.get('[aria-label="本单目标"]')
    expect((field.element as HTMLInputElement).value).toBe('')
    await field.setValue('Win the Q4 wafer line')
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    await wrapper.get('[aria-label="成功概率"]').setValue('upside')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ singleSalesObjective: 'Win the Q4 wafer line' })
    wrapper.unmount()
  })

  it('edits the objective in a multi-line box and keeps the line breaks typed into it', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity: legacyOpportunity('New Equipment') } })
    const field = wrapper.get('[aria-label="本单目标"]')
    expect(field.element.tagName).toBe('TEXTAREA')
    // A single-line input drops the line breaks of what is typed; the multi-line box keeps them.
    await field.setValue('Line one\nLine two\nLine three')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ singleSalesObjective: 'Line one\nLine two\nLine three' })
    wrapper.unmount()
  })

  it('holds the trimmed objective to 2000 characters, counted as characters', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity: legacyOpportunity('New Equipment') } })
    const field = wrapper.get('[aria-label="本单目标"]')
    // No native maxlength: it counts the raw value in UTF-16 units, which would cut off padded or emoji text early.
    expect(field.attributes('maxlength')).toBeUndefined()
    await field.setValue('x'.repeat(2001))
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.get('[data-field-error="singleSalesObjective"]').text()).toBe('本单目标最多 2000 个字符（首尾空白不计）')
    // Editing it answers the message; blanks around exactly 2000 characters do not count.
    await field.setValue('  ' + 'x'.repeat(2000) + '  ')
    expect(wrapper.find('[data-field-error="singleSalesObjective"]').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    // An emoji is one character, however many UTF-16 units it takes.
    await field.setValue('😀'.repeat(2000))
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(2)
    await field.setValue('😀'.repeat(2001))
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(2)
    wrapper.unmount()
  })

  it('sends back a stored objective that is over the limit, and holds a changed one to it', async () => {
    const stored = 'y'.repeat(2001)
    const opportunity = { ...legacyOpportunity('New Equipment'), singleSalesObjective: stored } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
    // Only the title changes: the stored objective goes back unchanged and is not held to the limit.
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('Retitled')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ title: 'Retitled', singleSalesObjective: stored })
    expect(wrapper.find('[data-field-error="singleSalesObjective"]').exists()).toBe(false)
    // Changing it to another value over the limit is refused.
    await wrapper.get('[aria-label="本单目标"]').setValue('z'.repeat(2001))
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.find('[data-field-error="singleSalesObjective"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('holds the objective of a new Opportunity to the limit, and compares a padded stored one trimmed', async () => {
    const created = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    await created.get('[aria-label="本单目标"]').setValue('x'.repeat(2001))
    await created.get('[data-testid="qualification-confirmed"]').setValue(true)
    await created.get('[aria-label="成功概率"]').setValue('upside')
    await created.get('form').trigger('submit')
    expect(created.emitted('submit')).toBeUndefined()
    expect(created.find('[data-field-error="singleSalesObjective"]').exists()).toBe(true)
    created.unmount()

    // A stored value padded with blanks is the same objective once trimmed, as on the server.
    const padded = ' ' + 'y'.repeat(2001) + String.fromCharCode(10)
    const opportunity = { ...legacyOpportunity('New Equipment'), singleSalesObjective: padded } as StrategyOpportunityDto
    const edited = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
    await edited.get('form').trigger('submit')
    expect(edited.emitted('submit')).toHaveLength(1)
    expect(edited.find('[data-field-error="singleSalesObjective"]').exists()).toBe(false)
    edited.unmount()
  })

  it('loads the stored objective when editing and resends it with an unrelated edit', async () => {
    const opportunity = { ...legacyOpportunity('New Equipment'), singleSalesObjective: 'Revised objective' } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
    expect((wrapper.get('[aria-label="本单目标"]').element as HTMLInputElement).value).toBe('Revised objective')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ singleSalesObjective: 'Revised objective' })
    wrapper.unmount()
  })
})

describe('OpportunityEditorModal competitors', () => {
  const stored = [
    { name: 'Acme Metrology', strengths: 'Installed base at the fab', response: 'Local service team' },
    { name: '本地竞争对手', strengths: '', response: '样片测试指标领先' },
  ]
  const rowsOf = (wrapper: ReturnType<typeof mount>) => wrapper.findAll('[data-testid="competitor-row"]')
  const submitted = (wrapper: ReturnType<typeof mount>, call = 0) => (wrapper.emitted('submit')?.[call]?.[0] as { competitors?: unknown }).competitors

  it('starts without rows on a new Opportunity and submits the rows that are filled in', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, defaultOwner: 'person002@crm.example.invalid', currentUserId: 'person002@crm.example.invalid' } })
    expect(rowsOf(wrapper)).toHaveLength(0)
    expect(wrapper.get('[data-testid="opportunity-competitors"]').text()).toContain('尚未添加竞争对手。')
    // The free-text field is the notes; the rows are the competitors.
    expect(wrapper.find('[aria-label="竞争备注"]').exists()).toBe(true)

    await wrapper.get('[data-testid="add-competitor"]').trigger('click')
    await wrapper.get('[data-testid="add-competitor"]').trigger('click')
    await wrapper.get('[data-testid="add-competitor"]').trigger('click')
    expect(rowsOf(wrapper)).toHaveLength(3)
    await wrapper.get('[aria-label="竞争对手名称 1"]').setValue('  Acme Metrology ')
    await wrapper.get('[aria-label="对方优势 1"]').setValue(' Installed base at the fab ')
    await wrapper.get('[aria-label="我方应对 1"]').setValue('Local service team')
    await wrapper.get('[aria-label="竞争对手名称 3"]').setValue('Name only')
    await wrapper.get('[data-testid="qualification-confirmed"]').setValue(true)
    await wrapper.get('[aria-label="成功概率"]').setValue('upside')
    await wrapper.get('form').trigger('submit')
    // Trimmed, and the row left entirely blank is not sent.
    expect(submitted(wrapper)).toEqual([
      { name: 'Acme Metrology', strengths: 'Installed base at the fab', response: 'Local service team' },
      { name: 'Name only', strengths: '', response: '' },
    ])
    wrapper.unmount()
  })

  it('loads the stored rows, resends them with an unrelated edit, and removes one', async () => {
    const opportunity = { ...legacyOpportunity('New Equipment'), competitors: stored } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
    expect(rowsOf(wrapper)).toHaveLength(2)
    expect((wrapper.get('[aria-label="竞争对手名称 2"]').element as HTMLInputElement).value).toBe('本地竞争对手')
    expect((wrapper.get('[aria-label="我方应对 2"]').element as HTMLTextAreaElement).value).toBe('样片测试指标领先')

    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('Retitled')
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper)).toEqual(stored)
    // Editing never changes the Opportunity it was opened with.
    expect(opportunity.competitors).toEqual(stored)

    await wrapper.get('[aria-label="移除竞争对手 1"]').trigger('click')
    expect(rowsOf(wrapper)).toHaveLength(1)
    expect((wrapper.get('[aria-label="竞争对手名称 1"]').element as HTMLInputElement).value).toBe('本地竞争对手')
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper, 1)).toEqual([stored[1]])
    // Removing the last row clears the list.
    await wrapper.get('[aria-label="移除竞争对手 1"]').trigger('click')
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper, 2)).toEqual([])
    wrapper.unmount()
  })

  it('an Opportunity from before the field opens without rows and submits an empty list', async () => {
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity: legacyOpportunity('New Equipment') } })
    expect(rowsOf(wrapper)).toHaveLength(0)
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper)).toEqual([])
    wrapper.unmount()
  })

  it('asks for a name on a row that has text, and refuses a repeated name', async () => {
    const opportunity = { ...legacyOpportunity('New Equipment'), competitors: [stored[0]] } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
    await wrapper.get('[data-testid="add-competitor"]').trigger('click')
    await wrapper.get('[aria-label="对方优势 2"]').setValue('Price')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.get('[data-field-error="competitors"]').text()).toBe('请填写竞争对手名称')

    // Typing answers the message; the same name in another case is the same competitor.
    await wrapper.get('[aria-label="竞争对手名称 2"]').setValue(' acme metrology ')
    expect(wrapper.find('[data-field-error="competitors"]').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.get('[data-field-error="competitors"]').text()).toBe('同一个竞争对手只能填写一次')

    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('[data-field-error="competitors"]').text()).toBe('A competitor can be listed only once')
    expect(wrapper.get('[data-testid="add-competitor"]').text()).toBe('Add competitor')
    expect(wrapper.find('[aria-label="Competition notes"]').exists()).toBe(true)
    setLocale('zh-CN'); await flushPromises()

    // The form is never stricter than the server: names the server keeps apart (dotless ı and I) go through,
    // and so does a pair only the server's full case folding equates (ß and SS), which the server then refuses.
    for (const [first, second] of [['Irmak', 'ırmak'], ['Straße GmbH', 'STRASSE GMBH']]) {
      const before = wrapper.emitted('submit')?.length ?? 0
      await wrapper.get('[aria-label="竞争对手名称 1"]').setValue(first)
      await wrapper.get('[aria-label="竞争对手名称 2"]').setValue(second)
      await wrapper.get('form').trigger('submit')
      expect(wrapper.find('[data-field-error="competitors"]').exists()).toBe(false)
      expect(wrapper.emitted('submit')).toHaveLength(before + 1)
    }
    await wrapper.get('[aria-label="竞争对手名称 1"]').setValue(stored[0].name)
    await wrapper.get('[aria-label="竞争对手名称 2"]').setValue('Other vendor')
    await wrapper.get('form').trigger('submit')
    expect(submitted(wrapper, 2)).toEqual([stored[0], { name: 'Other vendor', strengths: 'Price', response: '' }])
    wrapper.unmount()
  })

  it('holds the name to 140 and each text to 1000 characters, counted as characters', async () => {
    const opportunity = { ...legacyOpportunity('New Equipment'), competitors: [stored[0]] } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
    const name = wrapper.get('[aria-label="竞争对手名称 1"]')
    const strengths = wrapper.get('[aria-label="对方优势 1"]')
    const response = wrapper.get('[aria-label="我方应对 1"]')
    // No native maxlength: it counts UTF-16 units, which would stop an emoji or a rare Chinese character early.
    for (const field of [name, strengths, response]) expect(field.attributes('maxlength')).toBeUndefined()

    const tooLong = '竞争对手名称最多 140 个字符，对方优势和我方应对各最多 1000 个字符'
    for (const [field, limit] of [[name, 140], [strengths, 1000], [response, 1000]] as const) {
      const before = wrapper.emitted('submit')?.length ?? 0
      await field.setValue('x'.repeat(limit + 1))
      await wrapper.get('form').trigger('submit')
      expect(wrapper.emitted('submit')?.length ?? 0).toBe(before)
      expect(wrapper.get('[data-field-error="competitors"]').text()).toBe(tooLong)
      // The limit itself is fine, blanks around it do not count, and an emoji is one character.
      await field.setValue('  ' + '😀'.repeat(limit) + '  ')
      expect(wrapper.find('[data-field-error="competitors"]').exists()).toBe(false)
      await wrapper.get('form').trigger('submit')
      expect(wrapper.emitted('submit')).toHaveLength(before + 1)
    }
    expect(submitted(wrapper, 2)).toEqual([{ name: '😀'.repeat(140), strengths: '😀'.repeat(1000), response: '😀'.repeat(1000) }])
    wrapper.unmount()
  })

  it('stops adding rows at ten competitors', async () => {
    const competitors = Array.from({ length: 9 }, (_, index) => ({ name: `Competitor ${index + 1}`, strengths: '', response: '' }))
    const opportunity = { ...legacyOpportunity('New Equipment'), competitors } as StrategyOpportunityDto
    const wrapper = mount(OpportunityEditorModal, { props: { ...props, opportunity } })
    const add = wrapper.get('[data-testid="add-competitor"]')
    expect(add.attributes('disabled')).toBeUndefined()
    await add.trigger('click')
    expect(rowsOf(wrapper)).toHaveLength(10)
    expect(add.attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="移除竞争对手 10"]').trigger('click')
    expect(add.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
})
