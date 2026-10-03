import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { withAccountSites } from '@/features/accounts/mock-account-sites'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import LeadsOpportunitiesPage from './LeadsOpportunitiesPage.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

async function context(initial = '/leads-opportunities') {
  const api = await withAccountSites(createMockApi({ latency: 0 }))
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/leads-opportunities', name: 'leads-opportunities', component: LeadsOpportunitiesPage },
      { path: '/leads/:leadId', name: 'lead-detail', component: { template: '<div />' } },
      { path: '/opportunities/:opportunityId', name: 'opportunity-detail', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
    ],
  })
  await router.push(initial)
  return { api, pinia, router }
}

describe('Leads&Opportunities workspace', () => {
  it.each([
    ['leads', 'Leads', '.lead-list-view'],
    ['opportunities', 'Opportunities', '[data-testid="opportunity-list"]'],
  ] as const)('renders %s as an independent workspace', async (fixedView, title, listSelector) => {
    const { api, pinia, router } = await context()
    const wrapper = mount(LeadsOpportunitiesPage, {
      props: { apiClient: api, fixedView },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe(title)
    expect(wrapper.find('[aria-label="Leads 与 Opportunities 视图切换"]').exists()).toBe(false)
    expect(wrapper.find(listSelector).exists()).toBe(true)
  })

  it('uses the approved name and switches vertically between Leads and Opportunities', async () => {
    const { api, pinia, router } = await context()
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('Leads&Opportunities')
    expect(wrapper.find('[aria-label="Opportunities 与 Booking 子页面"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(6)

    await wrapper.get('[data-workspace-view="opportunities"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.view).toBe('opportunities')
    expect(wrapper.find('[data-testid="opportunity-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="opportunity-search"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-opportunity-id]').length).toBeGreaterThan(0)
    expect(wrapper.get('[data-testid="opportunity-number-header"]').text()).toBe('编号')
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)
    expect(wrapper.get('[data-opportunity-number="OPP-001"]').text()).toBe('OPP-001')
    expect(wrapper.text()).toContain('预计成交日期')
    const priorityOpportunity = wrapper.get('[data-opportunity-id="OPP-003"]')
    expect(priorityOpportunity.get('[data-opportunity-probability-level]').text()).toBe('确定')
    expect(priorityOpportunity.get('[data-opportunity-intent]').text()).toContain('86/100')

    await wrapper.get('[data-opportunity-link="OPP-003"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/opportunities/OPP-003')
  })

  it('opens the Opportunities view directly from the route query', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('[data-workspace-view="opportunities"]').classes()).toContain('active')
    expect(wrapper.find('[data-testid="opportunity-list"]').exists()).toBe(true)
  })

  it('keeps purchase intent editable on its own next to the required success probability', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-opportunity"]').trigger('click')

    expect(wrapper.find('[aria-label="Opportunity 赢率"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="预测分类"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="calculated-opportunity-probability"]').exists()).toBe(false)
    const intent = wrapper.get('[aria-label="购买意愿"]')
    expect(intent.attributes('type')).toBe('range')
    expect(intent.attributes('min')).toBe('0')
    expect(intent.attributes('max')).toBe('100')
    expect(intent.attributes('step')).toBe('1')
    expect(wrapper.get('[data-testid="opportunity-intent-value"]').text()).toBe('50')

    // The Manager opening this for the default Sales owner still picks its first level.
    const level = wrapper.get('[data-testid="opportunity-probability-level"]').element as HTMLSelectElement
    expect(level.disabled).toBe(false)
    expect(level.value).toBe('')

    await intent.setValue(80)
    expect(wrapper.get('[data-testid="opportunity-intent-value"]').text()).toBe('80')
    expect(level.value).toBe('')

    await wrapper.get('[data-testid="opportunity-probability-level"]').setValue('upside')
    expect(level.value).toBe('upside')
    expect(wrapper.get('[data-testid="opportunity-intent-value"]').text()).toBe('80')

    expect(wrapper.find('[aria-label="Opportunity 阶段"]').exists()).toBe(false)
    expect(wrapper.get('.readonly-stage').text()).toContain('合格商机')
    expect(wrapper.find('[data-testid="qualification-confirmed"]').exists()).toBe(true)
  })

  it('filters Opportunities by success probability, including records pending sales confirmation', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const listStrategyOpportunities = vi.spyOn(api, 'listStrategyOpportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    const filter = wrapper.get('[aria-label="全部成功概率"]')
    expect(filter.findAll('option').map((option) => option.attributes('value'))).toEqual(['All', 'low_probability', 'pipeline', 'upside', 'committed', 'pending'])
    expect(filter.findAll('option').map((option) => option.text())).toEqual(['全部成功概率', '低', '在途', '有望', '确定', '待销售确认'])
    expect(wrapper.find('[aria-label="全部 Forecast"]').exists()).toBe(false)

    await filter.setValue('committed')
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity-id]').map((row) => row.attributes('data-opportunity-id'))).toEqual(['OPP-003'])
    expect(router.currentRoute.value.query.probabilityLevel).toBe('committed')
    expect(listStrategyOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ probabilityLevel: 'committed' }))

    await filter.setValue('pending')
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity-id]').map((row) => row.attributes('data-opportunity-id')).sort()).toEqual(['OPP-006', 'OPP-007'])
    expect(wrapper.get('[data-opportunity-id="OPP-007"] [data-opportunity-probability-level]').text()).toBe('待销售确认')
  })

  it('filters the Opportunity list by stage without a page search box', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.find('[aria-label="搜索 Opportunity"]').exists()).toBe(false)
    const stage = wrapper.get('[aria-label="全部 Stage"]')
    expect(stage.findAll('option').map((option) => option.attributes('value'))).toEqual([
      'All', 'qualified_opportunity', 'demo_done', 'customer_budget_approved', 'rfq_validated', 'quotation_sent', 'internal_validation', 'po_received', 'lost',
    ])
    expect(stage.findAll('option').map((option) => option.text())).toEqual([
      '全部 Stage', '合格商机', 'Demo 完成', '客户预算批准', 'RFQ 通过', '报价已发', '内部生产审批', '收到 PO', '丢单',
    ])
    await stage.setValue('quotation_sent')
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(1)
    expect(wrapper.text()).toContain('HBM AOI 扩线项目')
    expect(router.currentRoute.value.query.status).toBe('quotation_sent')

    await stage.setValue('internal_validation')
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(1)
    expect(wrapper.find('[data-opportunity-id="OPP-008"]').exists()).toBe(true)
  })

  it('keeps the latest Opportunity filter when an older request finishes last', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    const olderResult = await api.listStrategyOpportunities({ status: 'quotation_sent', page: 1, pageSize: 12 })
    const latestResult = await api.listStrategyOpportunities({ status: 'internal_validation', page: 1, pageSize: 12 })
    const older = deferred<typeof olderResult>()
    const latest = deferred<typeof latestResult>()
    vi.spyOn(api, 'listStrategyOpportunities')
      .mockImplementationOnce(() => older.promise)
      .mockImplementationOnce(() => latest.promise)

    await wrapper.get('[aria-label="全部 Stage"]').setValue('quotation_sent')
    await wrapper.get('[aria-label="全部 Stage"]').setValue('internal_validation')
    latest.resolve(latestResult)
    await flushPromises()
    expect(wrapper.find('[data-opportunity-id="OPP-008"]').exists()).toBe(true)

    older.resolve(olderResult)
    await flushPromises()
    expect(wrapper.find('[data-opportunity-id="OPP-008"]').exists()).toBe(true)
    expect(wrapper.find('[data-opportunity-id="OPP-003"]').exists()).toBe(false)
  })

  it('switches Opportunities from the list to a board grouped by the existing Stage categories', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('[data-opportunity-layout="list"]').classes()).toContain('active')
    expect(wrapper.find('[data-testid="opportunity-board"]').exists()).toBe(false)

    await wrapper.get('[data-opportunity-layout="board"]').trigger('click')

    expect(wrapper.get('[data-opportunity-layout="board"]').classes()).toContain('active')
    expect(wrapper.find('.opportunity-table').exists()).toBe(false)
    expect(wrapper.findAll('[data-opportunity-stage]')).toHaveLength(8)
    expect(wrapper.findAll('[data-opportunity-stage]').map((column) => column.attributes('data-opportunity-stage'))).toEqual([
      'qualified_opportunity', 'demo_done', 'customer_budget_approved', 'rfq_validated', 'quotation_sent', 'internal_validation', 'po_received', 'lost',
    ])
    expect(wrapper.get('[data-opportunity-stage="quotation_sent"]').find('[data-opportunity-id="OPP-003"]').exists()).toBe(true)
    expect(wrapper.get('[data-opportunity-stage="rfq_validated"]').text()).toContain('0 条')
    expect(wrapper.get('[data-opportunity-stage="internal_validation"] [data-stage-marker="optional"]').text()).toBe('可选')
    expect(wrapper.get('[data-opportunity-stage="internal_validation"]').find('[data-opportunity-id="OPP-008"]').exists()).toBe(true)
    expect(wrapper.get('[data-opportunity-board-link="OPP-003"]').text()).toContain('HBM AOI 扩线项目')
    expect(wrapper.get('[data-opportunity-stage="quotation_sent"] [data-opportunity-board-probability-level]').text()).toBe('确定')

    await wrapper.get('[aria-label="全部 Stage"]').setValue('qualified_opportunity')
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(2)
    expect(wrapper.get('[data-opportunity-stage="qualified_opportunity"]').find('[data-opportunity-id="OPP-001"]').exists()).toBe(true)

    await wrapper.get('[data-opportunity-board-link="OPP-001"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/opportunities/OPP-001')
  })

  it('shows Opportunity amounts nobody has entered as not entered and never totals them as complete', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const [template] = (await api.listStrategyOpportunities({ page: 1, pageSize: 1 })).data.items
    const items = [
      { ...template!, id: 'OPP-KNOWN', stage: 'qualified_opportunity' as const, currency: 'CNY', amount: '100.00', originalAmount: '100.00', amountCny: '100.00' },
      { ...template!, id: 'OPP-UNKNOWN', stage: 'qualified_opportunity' as const, currency: 'CNY', amount: '', originalAmount: '', amountCny: '' },
    ]
    vi.spyOn(api, 'listStrategyOpportunities').mockResolvedValue({ data: { items }, meta: { requestId: 'req_unknown_amounts', total: 2, page: 1, pageSize: 12 }, warnings: [] })
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api, fixedView: 'opportunities' }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.get('[data-opportunity-amount="OPP-KNOWN"]').text()).toBe('CNY 100.00')
    const unknown = wrapper.get('[data-opportunity-id="OPP-UNKNOWN"]')
    expect(unknown.get('[data-opportunity-amount="OPP-UNKNOWN"]').text()).toBe('待补填')
    expect(unknown.text()).toContain('原始金额 待补填')
    expect(unknown.get('[data-opportunity-amount-cny="OPP-UNKNOWN"]').text()).toBe('人民币金额 待补填')
    expect(unknown.text()).not.toContain('0.00')

    // One order of CNY 100 and one unknown: the column shows the known total and the unknown count, not a complete CNY 100.
    await wrapper.get('[data-opportunity-layout="board"]').trigger('click')
    const column = wrapper.get('[data-opportunity-stage="qualified_opportunity"]')
    expect(column.get('header em').text()).toBe('CNY 100.00 · 1 条未填金额')
    expect(column.get('[data-opportunity-id="OPP-UNKNOWN"] dd').text()).toBe('待补填')
  })

  it('marks an Opportunity whose Demo done is waiting for the amount beside its stage in the list', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const [template] = (await api.listStrategyOpportunities({ page: 1, pageSize: 1 })).data.items
    const items = [
      { ...template!, id: 'OPP-WAITING', stage: 'qualified_opportunity' as const, currency: 'CNY', amount: '', originalAmount: '', amountCny: '', pendingStageAdvance: 'demo_done' as const },
      // In another currency the amount is there but the amount in CNY is not: the tooltip names both.
      { ...template!, id: 'OPP-WAITING-USD', stage: 'qualified_opportunity' as const, currency: 'USD', amount: '5000.00', originalAmount: '5000.00', amountCny: '', pendingStageAdvance: 'demo_done' as const },
      { ...template!, id: 'OPP-PLAIN', stage: 'qualified_opportunity' as const, pendingStageAdvance: '' as const },
      // Lost while waiting: the mark is kept for a reopening, but nothing is promised on a lost deal.
      { ...template!, id: 'OPP-LOST-WAITING', stage: 'lost' as const, lostAtStage: 'qualified_opportunity' as const, pendingStageAdvance: 'demo_done' as const },
    ]
    vi.spyOn(api, 'listStrategyOpportunities').mockResolvedValue({ data: { items }, meta: { requestId: 'req_pending_demo_done', total: 4, page: 1, pageSize: 12 }, warnings: [] })
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api, fixedView: 'opportunities' }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.find('[data-opportunity-id="OPP-LOST-WAITING"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="opportunity-pending-badge-OPP-LOST-WAITING"]').exists()).toBe(false)
    const badge = wrapper.get('[data-testid="opportunity-pending-badge-OPP-WAITING"]')
    expect([badge.text(), badge.attributes('title')]).toEqual(['待补金额', 'Demo 已完成。填写金额后，商机会自动进入 Demo 完成阶段。'])
    const foreign = wrapper.get('[data-testid="opportunity-pending-badge-OPP-WAITING-USD"]')
    expect([foreign.text(), foreign.attributes('title')]).toEqual(['待补金额', 'Demo 已完成。填写金额和人民币金额后，商机会自动进入 Demo 完成阶段。'])
    expect(wrapper.find('[data-testid="opportunity-pending-badge-OPP-PLAIN"]').exists()).toBe(false)

    // The board shows the same Opportunities as cards: the waiting one is marked there too.
    await wrapper.get('[data-opportunity-layout="board"]').trigger('click')
    expect(wrapper.get('[data-testid="opportunity-board-pending-badge-OPP-WAITING"]').text()).toBe('待补金额')
    expect(wrapper.get('[data-testid="opportunity-board-pending-badge-OPP-WAITING-USD"]').attributes('title')).toBe('Demo 已完成。填写金额和人民币金额后，商机会自动进入 Demo 完成阶段。')
    expect(wrapper.find('[data-testid="opportunity-board-pending-badge-OPP-PLAIN"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="opportunity-board-pending-badge-OPP-LOST-WAITING"]').exists()).toBe(false)
  })
})
