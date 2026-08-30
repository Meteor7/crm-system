import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import LeadsOpportunitiesPage from './LeadsOpportunitiesPage.vue'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

async function context(initial = '/leads-opportunities') {
  const api = createMockApi({ latency: 0 })
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
    expect(wrapper.text()).toContain('Close Date')
    const priorityOpportunity = wrapper.get('[data-opportunity-id="OPP-003"]')
    expect(priorityOpportunity.get('[data-opportunity-probability]').text()).toContain('88%')
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

  it('edits purchase intent and previews the calculated probability instead of accepting a manual win rate', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    await wrapper.get('[data-testid="new-opportunity"]').trigger('click')

    expect(wrapper.find('[aria-label="Opportunity 赢率"]').exists()).toBe(false)
    const intent = wrapper.get('[aria-label="Opportunity 购买意愿"]')
    expect(intent.attributes('type')).toBe('range')
    expect(intent.attributes('min')).toBe('0')
    expect(intent.attributes('max')).toBe('100')
    expect(intent.attributes('step')).toBe('1')
    expect(wrapper.get('[data-testid="opportunity-intent-value"]').text()).toBe('50')
    expect(wrapper.get('[data-testid="calculated-opportunity-probability"]').text()).toContain('29%')

    await intent.setValue(80)
    expect(wrapper.get('[data-testid="opportunity-intent-value"]').text()).toBe('80')
    expect(wrapper.get('[data-testid="calculated-opportunity-probability"]').text()).toContain('41%')

    expect(wrapper.find('[aria-label="Opportunity 阶段"]').exists()).toBe(false)
    expect(wrapper.get('.readonly-stage').text()).toContain('需求发现')
    expect(wrapper.get('[data-testid="calculated-opportunity-probability"]').text()).toContain('41%')
  })

  it('filters the Opportunity list by stage without a page search box', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(wrapper.find('[aria-label="搜索 Opportunity"]').exists()).toBe(false)
    await wrapper.get('[aria-label="Opportunity Stage 筛选"]').setValue('采购流程')
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(1)
    expect(wrapper.text()).toContain('HBM AOI 扩线项目')

    await wrapper.get('[aria-label="Opportunity Stage 筛选"]').setValue('Wafer Demo确认')
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(1)
    expect(wrapper.find('[data-opportunity-id="OPP-001"]').exists()).toBe(true)
  })

  it('keeps the latest Opportunity filter when an older request finishes last', async () => {
    const { api, pinia, router } = await context('/leads-opportunities?view=opportunities')
    const wrapper = mount(LeadsOpportunitiesPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    const olderResult = await api.listStrategyOpportunities({ status: '采购流程', page: 1, pageSize: 12 })
    const latestResult = await api.listStrategyOpportunities({ status: 'Wafer Demo确认', page: 1, pageSize: 12 })
    const older = deferred<typeof olderResult>()
    const latest = deferred<typeof latestResult>()
    vi.spyOn(api, 'listStrategyOpportunities')
      .mockImplementationOnce(() => older.promise)
      .mockImplementationOnce(() => latest.promise)

    await wrapper.get('[aria-label="Opportunity Stage 筛选"]').setValue('采购流程')
    await wrapper.get('[aria-label="Opportunity Stage 筛选"]').setValue('Wafer Demo确认')
    latest.resolve(latestResult)
    await flushPromises()
    expect(wrapper.find('[data-opportunity-id="OPP-001"]').exists()).toBe(true)

    older.resolve(olderResult)
    await flushPromises()
    expect(wrapper.find('[data-opportunity-id="OPP-001"]').exists()).toBe(true)
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
    expect(wrapper.get('[data-opportunity-stage="采购流程"]').find('[data-opportunity-id="OPP-003"]').exists()).toBe(true)
    expect(wrapper.get('[data-opportunity-stage="报价"]').text()).toContain('0 条')
    expect(wrapper.get('[data-opportunity-board-link="OPP-003"]').text()).toContain('HBM AOI 扩线项目')

    await wrapper.get('[aria-label="Opportunity Stage 筛选"]').setValue('Wafer Demo确认')
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(1)
    expect(wrapper.get('[data-opportunity-stage="Wafer Demo确认"]').find('[data-opportunity-id="OPP-001"]').exists()).toBe(true)

    await wrapper.get('[data-opportunity-board-link="OPP-001"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/opportunities/OPP-001')
  })
})
