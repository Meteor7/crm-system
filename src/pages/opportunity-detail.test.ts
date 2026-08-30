import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import OpportunityDetailPage from './OpportunityDetailPage.vue'

function requireOpportunityVersion(api: ReturnType<typeof createMockApi>) {
  const modified = '2026-08-05T10:00:00.000000Z'
  const listStrategyOpportunities = api.listStrategyOpportunities.bind(api)
  const getStrategyOpportunity = api.getStrategyOpportunity.bind(api)
  const updateStrategyOpportunity = api.updateStrategyOpportunity.bind(api)
  api.listStrategyOpportunities = async (query) => {
    const result = await listStrategyOpportunities(query)
    return {
      ...result,
      data: {
        ...result.data,
        items: result.data.items.map((item) => ({ ...item, modified })),
      },
    }
  }
  api.getStrategyOpportunity = async (id) => {
    const result = await getStrategyOpportunity(id)
    return { ...result, data: { ...result.data, modified } }
  }
  api.updateStrategyOpportunity = async (id, input, expectedModified) => {
    if (expectedModified !== modified) {
      throw new CrmApiError('VALIDATION_ERROR', 'expectedModified is required.', 'req_opportunity_version')
    }
    return updateStrategyOpportunity(id, input, expectedModified)
  }
  return api
}

async function context(opportunityId = 'OPP-001', requireVersion = false, role: 'Manager' | 'Sales' | 'Engineer' = 'Manager') {
  const api = createMockApi({ latency: 0, role })
  if (requireVersion) requireOpportunityVersion(api)
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createAppRouter()
  await router.push(`/opportunities/${opportunityId}`)
  await router.isReady()
  return { api, pinia, router }
}

describe('Opportunity detail', () => {
  it('shows Not Found without rendering or mutating an unrelated opportunity', async () => {
    const { api, pinia, router } = await context('OPP-NOT-FOUND')
    ;(api as unknown as { getStrategyOpportunity: (id: string) => Promise<never> }).getStrategyOpportunity = async () => {
      throw new CrmApiError('NOT_FOUND', 'Opportunity was not found.', 'req_opportunity_not_found')
    }
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('未找到指定 Opportunity。')
    expect(wrapper.find('[data-testid="selected-opportunity"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-opportunity"]').exists()).toBe(false)
  })

  it('loads the route opportunity directly even when it is absent from the first list page', async () => {
    const { api, pinia, router } = await context('OPP-003')
    const all = await api.listStrategyOpportunities({ pageSize: 200 })
    const target = all.data.items.find((item) => item.id === 'OPP-003')!
    const unrelated = all.data.items.find((item) => item.id !== target.id)!
    api.listStrategyOpportunities = async () => ({
      data: { items: [unrelated] },
      meta: { requestId: 'req_first_page', page: 1, pageSize: 1, total: 201 },
      warnings: [],
    })
    ;(api as unknown as { getStrategyOpportunity: (id: string) => Promise<{ data: typeof target; meta: { requestId: string } }> }).getStrategyOpportunity = async () => ({
      data: target,
      meta: { requestId: 'req_opportunity_detail' },
    })

    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="selected-opportunity"]').exists()).toBe(true)
    expect(wrapper.get('h1').text()).toBe(target.title)
    expect(wrapper.text()).not.toContain(unrelated.title)
  })

  it('does not let an older route request overwrite the latest opportunity', async () => {
    const { api, pinia, router } = await context('OPP-001')
    const all = await api.listStrategyOpportunities({ pageSize: 200 })
    const first = all.data.items.find((item) => item.id === 'OPP-001')!
    const latest = all.data.items.find((item) => item.id === 'OPP-003')!
    const pending = new Map<string, (value: { data: typeof first; meta: { requestId: string }; warnings: [] }) => void>()
    api.getStrategyOpportunity = (id) => new Promise((resolve) => pending.set(id, resolve))

    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()
    await router.push('/opportunities/OPP-003')
    await flushPromises()

    pending.get('OPP-003')!({ data: latest, meta: { requestId: 'req_latest' }, warnings: [] })
    await flushPromises()
    pending.get('OPP-001')!({ data: first, meta: { requestId: 'req_old' }, warnings: [] })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe(latest.title)
    expect(wrapper.text()).not.toContain(first.title)
  })

  it('selects the route record and renders a Salesforce-style Path', async () => {
    const { api, pinia, router } = await context('OPP-001')
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('南京缺陷检测设备 2 台')
    expect(wrapper.findAll('[data-stage-path]')).toHaveLength(8)
    expect(wrapper.get('[data-stage-path="Wafer Demo确认"]').classes()).toContain('is-current')
    expect(wrapper.get('[data-stage-path="需求发现"]').classes()).toContain('is-complete')
    expect(wrapper.get('[data-testid="back-opportunities"]').attributes('href')).toContain('/opportunities')
  })

  it('preserves the existing strategy capabilities in the recomposed detail', async () => {
    const { api, pinia, router } = await context('OPP-003')
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('About')
    expect(wrapper.text()).toContain('Status')
    expect(wrapper.text()).toContain('Action Plan')
    expect(wrapper.text()).not.toContain('Change History')
    expect(wrapper.text()).toContain('Commercial Forecast')
    expect(wrapper.text()).toContain('Buying Influence')
    expect(wrapper.text()).toContain('Strength')
    expect(wrapper.text()).toContain('Red Flag')
    expect(wrapper.text()).toContain('Information Needed')
    expect(wrapper.get('[data-testid="opportunity-probability"]').text()).toBe('88%')
    expect(wrapper.get('[data-testid="opportunity-intent"]').text()).toBe('86/100')
    expect(wrapper.get('[data-testid="opportunity-probability-explanation"]').text()).toContain('阶段基础概率 90% × 60% + 购买意愿 86 × 40%')
  })

  it('does not expose manual advancement for automatic Demo gate stages', async () => {
    const { api, pinia, router } = await context('OPP-001', true)
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="advance-opportunity-stage"]').exists()).toBe(false)
    expect((await api.getStrategyOpportunity('OPP-001')).data.stage).toBe('Wafer Demo确认')
  })

  it('keeps sequential manual advancement after budget approval', async () => {
    const { api, pinia, router } = await context('OPP-003', true)
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="advance-opportunity-stage"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-stage-path="Won"]').classes()).toContain('is-current')
    const saved = (await api.listStrategyOpportunities()).data.items.find((item) => item.id === 'OPP-003')
    expect(saved?.stage).toBe('Won')
    expect(saved?.probability).toBe(100)
  })

  it('shows rollback only to Manager', async () => {
    const managerContext = await context('OPP-001', false, 'Manager')
    const manager = mount(OpportunityDetailPage, {
      props: { apiClient: managerContext.api },
      global: { plugins: [managerContext.pinia, managerContext.router] },
    })
    await flushPromises()
    expect(manager.find('[data-testid="rollback-opportunity-stage"]').exists()).toBe(true)

    manager.unmount()
    const salesContext = await context('OPP-001', false, 'Sales')
    const sales = mount(OpportunityDetailPage, {
      props: { apiClient: salesContext.api },
      global: { plugins: [salesContext.pinia, salesContext.router] },
    })
    await flushPromises()
    expect(sales.find('[data-testid="rollback-opportunity-stage"]').exists()).toBe(false)
  })

  it('requires a rollback reason before calling the Manager-only API', async () => {
    const { api, pinia, router } = await context('OPP-001', false, 'Manager')
    const rollbackOpportunityStage = vi.fn().mockResolvedValue(await api.getStrategyOpportunity('OPP-001'))
    api.rollbackOpportunityStage = rollbackOpportunityStage
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="rollback-opportunity-stage"]').trigger('click')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    expect(rollbackOpportunityStage).not.toHaveBeenCalled()
    expect(wrapper.find('[data-field-error="rollbackReason"]').exists()).toBe(true)

    await wrapper.get('[aria-label="阶段回退原因"]').setValue('客户要求重新做Wafer Demo确认')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(rollbackOpportunityStage).toHaveBeenCalledWith(
      'OPP-001',
      { targetStage: '需求发现', reason: '客户要求重新做Wafer Demo确认' },
      undefined,
    )
  })

  it('edits an opportunity with its latest modified version', async () => {
    const { api, pinia, router } = await context('OPP-001', true)
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="edit-opportunity"]').trigger('click')
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('已更新的 Opportunity')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('已更新的 Opportunity')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('creates one Booking from a Won Opportunity and keeps the source link visible', async () => {
    const { api, pinia, router } = await context('OPP-003')
    await api.updateStrategyOpportunity('OPP-003', { stage: 'Won' })
    const primaryContact = (await api.listContacts({ accountId: 'ACC-002', pageSize: 100 })).data.items[0]
    const wrapper = mount(OpportunityDetailPage, {
      props: { apiClient: api },
      global: { plugins: [pinia, router] },
    })
    await flushPromises()

    await wrapper.get('[data-testid="create-booking-from-opportunity"]').trigger('click')

    expect((wrapper.get('[aria-label="Booking 来源 Opportunity"]').element as HTMLSelectElement).value).toBe('OPP-003')
    expect((wrapper.get('[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(primaryContact.id)
    expect((wrapper.get('[aria-label="Booking 金额"]').element as HTMLInputElement).value).toBe('32500000.00')

    await wrapper.get('[data-testid="create-contact"]').trigger('click')
    await wrapper.get('[aria-label="联系人姓名"]').setValue('Opportunity Booking 联系人')
    await wrapper.get('[aria-label="联系人职位"]').setValue('Procurement Manager')
    await wrapper.get('[aria-label="联系人部门"]').setValue('Procurement')
    await wrapper.get('[role="dialog"][aria-label="新增联系人"]').get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    const createdContact = (await api.listContacts({ search: 'Opportunity Booking 联系人', page: 1, pageSize: 10 })).data.items[0]
    expect((wrapper.get('[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(createdContact.id)

    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    const booking = (await api.listPipeline({})).data.bookings.find((item) => item.sourceOpportunityId === 'OPP-003')
    expect(booking).toMatchObject({
      accountId: 'ACC-002',
      primaryContactId: createdContact.id,
      amount: '32500000.00',
      status: 'Pending',
    })
    expect(wrapper.get('[data-testid="opportunity-booking-link"]').text()).toContain(booking!.id)
    expect(wrapper.find('[data-testid="create-booking-from-opportunity"]').exists()).toBe(false)
  })
})
