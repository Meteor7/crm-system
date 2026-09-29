import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { useAppStore } from '@/stores/app'
import { setLocale } from '@/i18n'
import OpportunityDetailPage from './OpportunityDetailPage.vue'

type MockOptions = NonNullable<Parameters<typeof createMockApi>[0]>

function requireOpportunityVersion(api: ReturnType<typeof createMockApi>) {
  const updateStrategyOpportunity = api.updateStrategyOpportunity.bind(api)
  api.updateStrategyOpportunity = async (id, input, expectedModified) => {
    if (!expectedModified) {
      throw new CrmApiError('VALIDATION_ERROR', 'expectedModified is required.', 'req_opportunity_version')
    }
    return updateStrategyOpportunity(id, input, expectedModified)
  }
  return api
}

async function context(
  opportunityId = 'OPP-001',
  requireVersion = false,
  role: 'Manager' | 'Sales' | 'Engineer' = 'Manager',
  options: Omit<MockOptions, 'latency' | 'role'> = {},
) {
  const api = createMockApi({ latency: 0, role, ...options })
  if (requireVersion) requireOpportunityVersion(api)
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createAppRouter()
  await router.push(`/opportunities/${opportunityId}`)
  await router.isReady()
  return { api, pinia, router }
}

function mountPage({ api, pinia, router }: Awaited<ReturnType<typeof context>>) {
  return mount(OpportunityDetailPage, {
    props: { apiClient: api },
    global: { plugins: [pinia, router] },
  })
}

describe('Opportunity detail', () => {
  afterEach(() => setLocale('zh-CN'))

  it('shows Not Found without rendering or mutating an unrelated opportunity', async () => {
    const setup = await context('OPP-NOT-FOUND')
    ;(setup.api as unknown as { getStrategyOpportunity: (id: string) => Promise<never> }).getStrategyOpportunity = async () => {
      throw new CrmApiError('NOT_FOUND', 'Opportunity was not found.', 'req_opportunity_not_found')
    }
    const wrapper = mountPage(setup)
    await flushPromises()

    expect(wrapper.text()).toContain('未找到指定 Opportunity。')
    expect(wrapper.find('[data-testid="selected-opportunity"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-opportunity"]').exists()).toBe(false)
  })

  it('loads the route opportunity directly even when it is absent from the first list page', async () => {
    const setup = await context('OPP-003')
    const { api } = setup
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

    const wrapper = mountPage(setup)
    await flushPromises()

    expect(wrapper.find('[data-testid="selected-opportunity"]').exists()).toBe(true)
    expect(wrapper.get('h1').text()).toBe(target.title)
    expect(wrapper.text()).not.toContain(unrelated.title)
  })

  it('does not let an older route request overwrite the latest opportunity', async () => {
    const setup = await context('OPP-001')
    const { api, router } = setup
    const all = await api.listStrategyOpportunities({ pageSize: 200 })
    const first = all.data.items.find((item) => item.id === 'OPP-001')!
    const latest = all.data.items.find((item) => item.id === 'OPP-003')!
    const pending = new Map<string, (value: { data: typeof first; meta: { requestId: string }; warnings: [] }) => void>()
    api.getStrategyOpportunity = (id) => new Promise((resolve) => pending.set(id, resolve))

    const wrapper = mountPage(setup)
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

  it('selects the route record and renders the seven-milestone path', async () => {
    const wrapper = mountPage(await context('OPP-001'))
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('南京缺陷检测设备 2 台')
    expect(wrapper.findAll('[data-stage-path]').map((segment) => segment.attributes('data-stage-path'))).toEqual([
      'qualified_opportunity', 'demo_done', 'customer_budget_approved', 'rfq_validated', 'quotation_sent', 'internal_validation', 'po_received',
    ])
    expect(wrapper.get('[data-stage-path="qualified_opportunity"]').classes()).toContain('is-current')
    expect(wrapper.get('[data-stage-path="demo_done"]').classes()).toContain('is-upcoming')
    expect(wrapper.get('[data-stage-path="internal_validation"]').classes()).toContain('is-optional')
    expect(wrapper.get('[data-stage-path="internal_validation"] [data-stage-marker="optional"]').text()).toBe('可选')
    expect(wrapper.get('[data-testid="opportunity-stage"]').text()).toBe('合格商机')
    expect(wrapper.get('[data-testid="back-opportunities"]').attributes('href')).toContain('/opportunities')
    expect(wrapper.get('[data-testid="blue-sheet-title"]').text()).toBe('战略分析')
    const detailGrid = wrapper.get('[data-testid="selected-opportunity"]')
    expect(Array.from(detailGrid.element.children).map((child) => child.className)).toEqual([
      'detail-column detail-left',
      'opportunity-strategy-shell',
    ])
    const strategyGrid = wrapper.get('[data-testid="blue-sheet"] .strategy-shell-grid')
    expect(Array.from(strategyGrid.element.children).map((child) => child.className)).toEqual([
      'detail-column detail-center',
      'detail-column detail-right',
    ])
  })

  it('keeps Site-restricted Opportunities readable without exposing invalid main-record actions', async () => {
    const setup = await context('OPP-001', false, 'Sales')
    const getStrategyOpportunity = setup.api.getStrategyOpportunity.bind(setup.api)
    setup.api.getStrategyOpportunity = async (id) => {
      const result = await getStrategyOpportunity(id)
      return {
        ...result,
        data: { ...result.data, siteId: '', site: '', siteRestricted: true, stage: 'quotation_sent' as const },
      }
    }

    const wrapper = mountPage(setup)
    await flushPromises()

    expect(wrapper.text()).toContain('仅客户负责人可见')
    expect(wrapper.find('[data-testid="edit-opportunity"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="mark-opportunity-lost"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="confirm-po"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="request-internal-validation"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="new-opportunity-action"]').exists()).toBe(true)
  })

  it('preserves the existing strategy capabilities in the recomposed detail', async () => {
    setLocale('en-US')
    const wrapper = mountPage(await context('OPP-003'))
    await flushPromises()

    expect(wrapper.text()).toContain('About')
    expect(wrapper.text()).toContain('Status')
    expect(wrapper.text()).toContain('Action plan')
    expect(wrapper.text()).not.toContain('Change History')
    expect(wrapper.text()).toContain('Commercial forecast')
    expect(wrapper.text()).toContain('Buying influence')
    expect(wrapper.text()).toContain('Strength')
    expect(wrapper.text()).toContain('Red flag')
    expect(wrapper.text()).toContain('Information needed')
    expect(wrapper.get('[data-testid="opportunity-stage"]').text()).toBe('Quotation sent')
    expect(wrapper.get('[data-testid="opportunity-probability-level"]').text()).toBe('Committed')
    expect(wrapper.get('[data-testid="opportunity-intent"]').text()).toBe('86/100')
    expect(wrapper.find('[data-testid="opportunity-probability"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="opportunity-probability-explanation"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Forecast category')
    expect(wrapper.text()).not.toContain('Win probability')
    expect(wrapper.text()).toContain('Success probability history')
    const history = wrapper.findAll('[data-probability-history-id]')
    expect(history).toHaveLength(2)
    expect(history[0]!.text()).toContain('Upside → Committed')
    expect(history[0]!.text()).toContain('Demo Staff 01')
    expect(history[0]!.text()).toContain('2026-07-16 17:20')
    expect(history[1]!.text()).toContain('Pending sales confirmation → Upside')
    setLocale('zh-CN')
    await flushPromises()
    expect(wrapper.get('[data-testid="opportunity-probability-level"]').text()).toBe('确定')
    expect(wrapper.findAll('[data-probability-history-id]')[0]!.text()).toContain('有望 → 确定')
  })

  it('shows the structured stage history with declared business dates on the optional internal validation stage', async () => {
    const wrapper = mountPage(await context('OPP-008'))
    await flushPromises()

    const rows = wrapper.findAll('[data-stage-history-id]')
    expect(rows.map((row) => row.attributes('data-stage-history-event'))).toEqual([
      'internal_validation_approved', 'quotation_published', 'rfq_approved', 'budget_confirmed', 'demo_customer_review', 'created',
    ])
    expect(rows[0]!.text()).toContain('报价已发 → 内部生产审批')
    expect(rows[0]!.text()).toContain('演示员工24')
    expect(rows[0]!.text()).toContain('2026-07-20 09:00')
    expect(wrapper.get('[data-stage-history-id="OSH-OPP-008-3"] [data-stage-history-reached]').text()).toBe('实际到达 2026-07-06 · 销售填写日期')
    expect(rows[5]!.find('[data-stage-history-reached]').exists()).toBe(false)
    expect(wrapper.get('[data-stage-path="internal_validation"]').classes()).toEqual(expect.arrayContaining(['is-current', 'is-optional']))
    expect(wrapper.get('[data-testid="opportunity-budget-approved-on"]').text()).toBe('2026-07-06')
    expect(wrapper.get('[data-testid="opportunity-booking-link"]').text()).toContain('BKG-003')
    expect(wrapper.get('[data-testid="internal-validation-panel"]').attributes('data-validation-status')).toBe('approved')
    expect(wrapper.find('[data-testid="request-internal-validation"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="confirm-po"]').exists()).toBe(true)
  })

  it('marks internal validation skipped when the PO was confirmed straight from quotation sent', async () => {
    const wrapper = mountPage(await context('OPP-006'))
    await flushPromises()

    expect(wrapper.get('[data-stage-path="internal_validation"]').classes()).toContain('is-skipped')
    expect(wrapper.get('[data-stage-path="internal_validation"] [data-stage-marker="skipped"]').text()).toBe('已跳过')
    expect(wrapper.get('[data-stage-path="po_received"]').classes()).toContain('is-current')
    expect(wrapper.find('[data-testid="mark-opportunity-lost"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="replace-booking"]').exists()).toBe(false)
  })

  it('leaves the Demo gate stages to the Demo workflow', async () => {
    const setup = await context('OPP-001', true)
    const wrapper = mountPage(setup)
    await flushPromises()

    for (const action of ['confirm-budget-approved', 'request-internal-validation', 'confirm-po', 'replace-booking']) {
      expect(wrapper.find(`[data-testid="${action}"]`).exists()).toBe(false)
    }
    expect((await setup.api.getStrategyOpportunity('OPP-001')).data.stage).toBe('qualified_opportunity')
  })

  it('confirms the customer budget at Demo done with the date the customer approved it', async () => {
    const salesRepository = createMemorySalesRepository()
    salesRepository.snapshot.opportunities.find((item) => item.id === 'OPP-001')!.stage = 'demo_done'
    const setup = await context('OPP-001', false, 'Sales', { salesRepository })
    const confirmBudgetApproved = vi.spyOn(setup.api, 'confirmBudgetApproved')
    const version = (await setup.api.getStrategyOpportunity('OPP-001')).data.modified
    const wrapper = mountPage(setup)
    await flushPromises()

    expect(wrapper.find('[data-testid="confirm-po"]').exists()).toBe(false)
    await wrapper.get('[data-testid="confirm-budget-approved"]').trigger('click')
    await wrapper.get('[aria-label="预算批准日期"]').setValue('2026-07-06')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(confirmBudgetApproved).toHaveBeenCalledWith('OPP-001', { approvedOn: '2026-07-06' }, version)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="opportunity-stage"]').text()).toBe('客户预算批准')
    expect(wrapper.get('[data-testid="opportunity-budget-approved-on"]').text()).toBe('2026-07-06')
    expect(wrapper.get('[data-stage-history-id] [data-stage-history-reached]').text()).toBe('实际到达 2026-07-06 · 销售填写日期')
    expect(wrapper.find('[data-testid="confirm-budget-approved"]').exists()).toBe(false)
  })

  it('requests internal validation at quotation sent and lets another Manager approve it into a Pending Booking', async () => {
    const salesRepository = createMemorySalesRepository()
    const sales = await context('OPP-003', false, 'Sales', { salesRepository })
    const requestInternalValidation = vi.spyOn(sales.api, 'requestInternalValidation')
    const version = (await sales.api.getStrategyOpportunity('OPP-003')).data.modified
    const salesPage = mountPage(sales)
    await flushPromises()

    await salesPage.get('[data-testid="request-internal-validation"]').trigger('click')
    await flushPromises()
    expect((salesPage.get('[aria-label="预计 PO 日期"]').element as HTMLInputElement).value).toBe('2026-09-18')
    expect((salesPage.get('[aria-label="Booking 金额"]').element as HTMLInputElement).value).toBe('32500000.00')
    await salesPage.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    expect(requestInternalValidation).not.toHaveBeenCalled()
    expect(salesPage.get('[data-field-error="reason"]').text()).toBe('请填写申请理由')

    await salesPage.get('[aria-label="申请理由"]').setValue('客户扩产窗口紧，需要提前锁定产能')
    await salesPage.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(requestInternalValidation).toHaveBeenCalledWith('OPP-003', expect.objectContaining({
      reason: '客户扩产窗口紧，需要提前锁定产能',
      expectedPoDate: '2026-09-18',
      booking: expect.objectContaining({ owner: 'person002@crm.example.invalid', amount: '32500000.00', currency: 'CNY' }),
    }), version)
    expect(salesPage.get('[data-testid="internal-validation-panel"]').attributes('data-validation-status')).toBe('pending')
    expect(salesPage.find('[data-testid="approve-internal-validation"]').exists()).toBe(false)
    expect(salesPage.find('[data-testid="request-internal-validation"]').exists()).toBe(false)
    salesPage.unmount()

    const manager = await context('OPP-003', false, 'Manager', { salesRepository })
    const managerPage = mountPage(manager)
    await flushPromises()
    await managerPage.get('[data-testid="reject-internal-validation"]').trigger('click')
    expect(managerPage.get('[data-field-error="comment"]').text()).toBe('驳回时必须填写审批意见')
    await managerPage.get('[data-testid="approve-internal-validation"]').trigger('click')
    await flushPromises()

    expect(managerPage.get('[data-testid="opportunity-stage"]').text()).toBe('内部生产审批')
    expect(managerPage.get('[data-testid="internal-validation-panel"]').attributes('data-validation-status')).toBe('approved')
    const booking = (await manager.api.getStrategyOpportunity('OPP-003')).data.liveBooking!
    expect(booking.status).toBe('Pending')
    expect(managerPage.get('[data-testid="opportunity-booking-link"]').text()).toContain(booking.id)
    expect(managerPage.get('[data-stage-path="internal_validation"]').classes()).toContain('is-current')
    expect(booking.modified).toBeTruthy()

    // The PO form keeps the current Pending Booking details and sends its own optimistic-lock token.
    const confirmPo = vi.spyOn(manager.api, 'confirmPo')
    await managerPage.get('[data-testid="confirm-po"]').trigger('click')
    await flushPromises()
    await managerPage.get('[aria-label="实际 PO 日期"]').setValue('2026-07-15')
    await managerPage.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(confirmPo).toHaveBeenCalledTimes(1)
    expect(confirmPo.mock.calls[0].slice(0, 2)).toEqual(['OPP-003', {
      booking: expect.objectContaining({
        primaryContactId: booking.primaryContactId,
        amount: booking.amount,
        owner: 'person002@crm.example.invalid',
        note: booking.note,
      }),
      expectedBookingModified: booking.modified,
      actualPoDate: '2026-07-15',
    }])
    expect(managerPage.get('[data-testid="opportunity-stage"]').text()).toBe('收到 PO')
  })

  it('confirms the PO at quotation sent into a Confirmed Booking and links it from the Opportunity', async () => {
    const setup = await context('OPP-003')
    const wrapper = mountPage(setup)
    await flushPromises()

    expect(wrapper.find('[data-testid="create-booking-from-opportunity"]').exists()).toBe(false)
    await wrapper.get('[data-testid="confirm-po"]').trigger('click')
    expect(wrapper.get('[data-testid="po-confirmation-hint"]').text()).toBe('确认后生成 Confirmed Booking，商机进入“收到 PO”阶段。')
    expect((wrapper.get('[aria-label="Booking 金额"]').element as HTMLInputElement).value).toBe('32500000.00')

    await wrapper.get('[data-testid="create-contact"]').trigger('click')
    await wrapper.get('[aria-label="联系人姓名"]').setValue('Opportunity Booking 联系人')
    await wrapper.get('[aria-label="联系人职位"]').setValue('Procurement Manager')
    await wrapper.get('[aria-label="联系人部门"]').setValue('Procurement')
    await wrapper.get('[role="dialog"][aria-label="新增联系人"]').get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    const createdContact = (await setup.api.listContacts({ search: 'Opportunity Booking 联系人', page: 1, pageSize: 10 })).data.items[0]!
    expect((wrapper.get('[aria-label="选择联系人"]').element as HTMLSelectElement).value).toBe(createdContact.id)

    // The actual PO date starts blank: neither today nor the expected PO date is the date on the PO.
    expect((wrapper.get('[aria-label="实际 PO 日期"]').element as HTMLInputElement).value).toBe('')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-field-error="actualPoDate"]').text()).toBe('请填写实际 PO 日期')
    expect((await setup.api.getStrategyOpportunity('OPP-003')).data.stage).toBe('quotation_sent')

    await wrapper.get('[aria-label="实际 PO 日期"]').setValue('2026-07-15')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()

    const opportunity = (await setup.api.getStrategyOpportunity('OPP-003')).data
    expect(opportunity).toMatchObject({ stage: 'po_received', liveBooking: { status: 'Confirmed', amount: '32500000.00' } })
    const booking = (await setup.api.listBookings({ pageSize: 100 })).data.items.find((item) => item.id === opportunity.liveBooking!.id)!
    expect(booking).toMatchObject({
      accountId: 'ACC-002', primaryContactId: createdContact.id, source: 'Opportunity', sourceOpportunityId: 'OPP-003',
      actualPoDate: '2026-07-15', actualPoDateSource: 'po_confirmation',
    })
    expect(wrapper.get('[data-testid="opportunity-booking-link"]').text()).toContain(booking.id)
    expect(wrapper.get('[data-stage-path="internal_validation"]').classes()).toContain('is-skipped')
    expect(wrapper.find('[data-testid="confirm-po"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="replace-booking"]').exists()).toBe(false)
  })

  it('offers a replacement Booking at PO received once the Booking was cancelled by hand', async () => {
    const setup = await context('OPP-006')
    const current = (await setup.api.listBookings({ pageSize: 100 })).data.items.find((item) => item.id === 'BKG-001')!
    await setup.api.updateBooking('BKG-001', { ...current, status: 'Cancelled' } as never)
    const confirmPo = vi.spyOn(setup.api, 'confirmPo')
    const version = (await setup.api.getStrategyOpportunity('OPP-006')).data.modified
    const wrapper = mountPage(setup)
    await flushPromises()

    expect(wrapper.find('[data-testid="opportunity-booking-link"]').exists()).toBe(false)
    await wrapper.get('[data-testid="replace-booking"]').trigger('click')
    expect(wrapper.get('[data-testid="po-confirmation-hint"]').text()).toBe('原 Booking 已取消。补录的 Booking 为 Confirmed，商机阶段保持不变。')
    await wrapper.get('[aria-label="实际 PO 日期"]').setValue('2026-07-15')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(confirmPo).toHaveBeenCalledWith(
      'OPP-006', { booking: expect.objectContaining({ owner: 'person005@crm.example.invalid' }), actualPoDate: '2026-07-15' }, version,
    )
    expect(wrapper.get('[data-testid="opportunity-stage"]').text()).toBe('收到 PO')
    expect(wrapper.get('[data-testid="opportunity-booking-link"]').text()).toContain('BKG-')
    expect(wrapper.find('[data-testid="replace-booking"]').exists()).toBe(false)
  })

  it('marks an open Opportunity lost with a reason and shows where it was lost', async () => {
    const setup = await context('OPP-001')
    const markOpportunityLost = vi.spyOn(setup.api, 'markOpportunityLost')
    const version = (await setup.api.getStrategyOpportunity('OPP-001')).data.modified
    const wrapper = mountPage(setup)
    await flushPromises()

    await wrapper.get('[data-testid="mark-opportunity-lost"]').trigger('click')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    expect(markOpportunityLost).not.toHaveBeenCalled()
    expect(wrapper.get('[role="dialog"] .form-error').text()).toBe('请填写丢单原因')

    await wrapper.get('[aria-label="丢单原因"]').setValue('客户预算冻结')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(markOpportunityLost).toHaveBeenCalledWith('OPP-001', { lostReason: '客户预算冻结' }, version)
    expect(wrapper.get('[data-testid="opportunity-stage"]').text()).toBe('丢单')
    expect(wrapper.get('[data-testid="opportunity-lost-outcome"]').text()).toBe('丢单')
    expect(wrapper.get('[data-testid="lost-at-stage"]').text()).toBe('合格商机')
    expect(wrapper.get('[data-stage-path="qualified_opportunity"]').classes()).toContain('is-lost')
    expect(wrapper.get('[data-stage-path="qualified_opportunity"] [data-stage-marker="lost"]').text()).toBe('在此丢单')
    expect(wrapper.find('[data-testid="mark-opportunity-lost"]').exists()).toBe(false)
  })

  it('blocks marking lost while the Opportunity has a live Booking', async () => {
    const wrapper = mountPage(await context('OPP-008'))
    await flushPromises()

    await wrapper.get('[data-testid="mark-opportunity-lost"]').trigger('click')
    expect(wrapper.get('[data-testid="lost-blocked-by-booking"]').text()).toBe('该商机有未取消的 Booking，请先取消 Booking 再标记丢单。')
    expect(wrapper.get('[role="dialog"] [data-modal-submit]').attributes('disabled')).toBeDefined()
  })

  it('lets only the Opportunity owner change the success probability and shows each recorded change', async () => {
    const ownerContext = await context('OPP-001', false, 'Sales')
    const owner = mountPage(ownerContext)
    await flushPromises()

    expect(owner.get('[data-testid="opportunity-probability-level"]').text()).toBe('有望')
    expect(owner.findAll('[data-probability-history-id]')).toHaveLength(1)
    await owner.get('[data-testid="edit-opportunity"]').trigger('click')
    const level = owner.get('[aria-label="成功概率"]')
    expect((level.element as HTMLSelectElement).disabled).toBe(false)
    await level.setValue('committed')
    await owner.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(owner.get('[data-testid="opportunity-probability-level"]').text()).toBe('确定')
    const entries = owner.findAll('[data-probability-history-id]')
    expect(entries).toHaveLength(2)
    expect(entries[0]!.text()).toContain('有望 → 确定')
    expect(entries[0]!.text()).toContain('Demo Staff 01')
    expect(entries[1]!.text()).toContain('待销售确认 → 有望')
    owner.unmount()

    const manager = mountPage(await context('OPP-001', false, 'Manager'))
    await flushPromises()

    await manager.get('[data-testid="edit-opportunity"]').trigger('click')
    expect((manager.get('[aria-label="成功概率"]').element as HTMLSelectElement).disabled).toBe(true)
    expect(manager.get('[data-testid="opportunity-probability-level-owner-only"]').text()).toBe('仅商机负责人可设置成功概率')
  })

  it('shows rollback only to Manager and only when an earlier milestone exists', async () => {
    const manager = mountPage(await context('OPP-003', false, 'Manager'))
    await flushPromises()
    expect(manager.find('[data-testid="rollback-opportunity-stage"]').exists()).toBe(true)
    manager.unmount()

    const firstStage = mountPage(await context('OPP-001', false, 'Manager'))
    await flushPromises()
    expect(firstStage.find('[data-testid="rollback-opportunity-stage"]').exists()).toBe(false)
    firstStage.unmount()

    const sales = mountPage(await context('OPP-003', false, 'Sales'))
    await flushPromises()
    expect(sales.find('[data-testid="rollback-opportunity-stage"]').exists()).toBe(false)
  })

  it('offers only earlier milestones and requires a rollback reason before calling the Manager-only API', async () => {
    const setup = await context('OPP-003', false, 'Manager')
    const rollbackOpportunityStage = vi.fn().mockResolvedValue(await setup.api.getStrategyOpportunity('OPP-003'))
    setup.api.rollbackOpportunityStage = rollbackOpportunityStage
    const version = (await setup.api.getStrategyOpportunity('OPP-003')).data.modified
    const wrapper = mountPage(setup)
    await flushPromises()

    await wrapper.get('[data-testid="rollback-opportunity-stage"]').trigger('click')
    const target = wrapper.get('[aria-label="阶段回退目标"]')
    expect(target.findAll('option').map((option) => option.attributes('value'))).toEqual([
      'qualified_opportunity', 'demo_done', 'customer_budget_approved', 'rfq_validated',
    ])
    expect((target.element as HTMLSelectElement).value).toBe('rfq_validated')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    expect(rollbackOpportunityStage).not.toHaveBeenCalled()
    expect(wrapper.find('[data-field-error="rollbackReason"]').exists()).toBe(true)

    await target.setValue('demo_done')
    await wrapper.get('[aria-label="阶段回退原因"]').setValue('客户要求重新做 Demo')
    await wrapper.get('[role="dialog"] [data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(rollbackOpportunityStage).toHaveBeenCalledWith(
      'OPP-003',
      { targetStage: 'demo_done', reason: '客户要求重新做 Demo' },
      version,
    )
  })

  it('explains when a live Booking withholds the rollback targets', async () => {
    const wrapper = mountPage(await context('OPP-006', false, 'Manager'))
    await flushPromises()

    await wrapper.get('[data-testid="rollback-opportunity-stage"]').trigger('click')
    expect(wrapper.get('[data-rollback-blocker="live_booking"]').text()).toBe('该商机有未取消的 Booking，请先取消 Booking，才能回退到报价已发或更早的阶段。')
    expect(wrapper.get('[aria-label="阶段回退目标"]').findAll('option')).toHaveLength(0)
    expect(wrapper.get('[role="dialog"] [data-modal-submit]').attributes('disabled')).toBeDefined()
  })

  it('edits an opportunity with its latest modified version', async () => {
    const wrapper = mountPage(await context('OPP-001', true))
    await flushPromises()

    await wrapper.get('[data-testid="edit-opportunity"]').trigger('click')
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('已更新的 Opportunity')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('已更新的 Opportunity')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('shows the amount in CNY, and asks for it before an edit when it is missing', async () => {
    const filled = mountPage(await context('OPP-001'))
    await flushPromises()
    expect(filled.get('[data-testid="opportunity-amount-cny"]').text()).toBe('CNY 16,800,000.00')

    const cached = structuredClone(createMemorySalesRepository().snapshot)
    const foreign = cached.opportunities.find((item) => item.id === 'OPP-001')!
    foreign.currency = 'USD'
    delete (foreign as { amountCny?: string }).amountCny
    const wrapper = mountPage(await context('OPP-001', false, 'Manager', { salesRepository: createMemorySalesRepository(cached) }))
    await flushPromises()
    expect(wrapper.get('[data-testid="opportunity-amount-cny"]').text()).toBe('待补填')

    await wrapper.get('[data-testid="edit-opportunity"]').trigger('click')
    expect(wrapper.find('[data-testid="opportunity-amount-cny-missing"]').exists()).toBe(true)
    await wrapper.get('[aria-label="Opportunity 名称"]').setValue('改名但没填人民币金额')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('请填写人民币金额。')

    await wrapper.get('[aria-label="人民币金额"]').setValue('118000')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="opportunity-amount-cny"]').text()).toBe('CNY 118,000.00')
  })
})
