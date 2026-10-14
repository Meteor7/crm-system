import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api/contracts'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import { planFixture, planDetailsFixture } from '@/features/cockpit/plan.fixture'
import { setLocale } from '@/i18n'
import type { UserRole } from '@/types/crm'
import PlanPage from './PlanPage.vue'
import apiSample from '../../docs/plan/api-sample.json'
import type { PlanDto, PlanDetails } from '@/features/cockpit/plan-types'
const response = <T,>(data: T) => ({ data, warnings: [], meta: { requestId: 'plan-test', generatedAt: '' } })
beforeEach(() => setLocale('zh-CN'))
async function setup(role: UserRole = 'Manager', plan = planFixture(), details = planDetailsFixture()) {
  const api = createMockApi({ role, latency: 0 })
  api.getPlan = vi.fn(async () => response(plan))
  api.getPlanDetails = vi.fn(async () => response(details))
  const pinia = createPinia(), router = createAppRouter()
  await router.push('/plan'); await router.isReady()
  const wrapper = mount(PlanPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { api, wrapper, router, app: useAppStore(pinia) }
}
describe('Plan business interface', () => {
  it('shows equipment counts as plain text and filters through the top controls', async () => {
    const data = planFixture()
    data.filters.equipment = ['Aconca']
    data.equipmentGroups = [{ id: 'unclassified', name: null, activities: { value: 0, state: 'ready' }, po: { value: 3, state: 'ready' }, poAmounts: [], poAmountIncomplete: true }]
    const { wrapper, api } = await setup('Manager', data)
    const summary = wrapper.get('[data-equipment-summary]')
    expect(summary.text()).toContain('未分类')
    expect(summary.text()).toContain('部分金额数据不足')
    expect(summary.find('button, a, input').exists()).toBe(false)
    const cells = summary.findAll('tbody td')
    expect(cells[0]!.text()).toBe('0')
    expect(cells[1]!.text()).toBe('3')
    const requests = vi.mocked(api.getPlanDetails).mock.calls.length
    await cells[0]!.trigger('click'); await cells[1]!.trigger('click'); await flushPromises()
    expect(api.getPlanDetails).toHaveBeenCalledTimes(requests)
    await wrapper.get('select[aria-label="Equipment"]').setValue('Aconca'); await flushPromises()
    expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ equipment: 'Aconca' }))
    expect(api.getPlanDetails).toHaveBeenLastCalledWith(expect.objectContaining({ equipment: 'Aconca', includeOverdue: false }))
    wrapper.unmount()
  })
  it('shows quote amounts only on quotes and PO amounts only on PO', async () => {
    const plan = planFixture()
    plan.quoteAmounts = [{ currency: 'CNY', value: '125000.00' }]
    plan.quoteAmountIncomplete = false
    const { wrapper } = await setup('Manager', plan)
    expect(wrapper.get('.kpi.quotes').text()).toContain('CNY 125,000')
    expect(wrapper.get('.kpi.quotes').text()).not.toContain('6,800,000')
    expect(wrapper.get('.kpi.po').text()).toContain('CNY 6,800,000')
    expect(wrapper.get('.kpi.followups').text()).not.toContain('CNY')
    expect(wrapper.get('.kpi.events').text()).not.toContain('CNY')
    wrapper.unmount()
  })

  it('opens carried-over quotation work with original dates and source links', async () => {
    const plan = planFixture()
    plan.otherDemos = { state: 'ready', value: 0 }
    plan.quotationCarryover = { state: 'ready', value: 1 }
    const details = planDetailsFixture()
    const { wrapper, api } = await setup('Manager', plan, details)
    api.getPlanDetails = vi.fn(async () => response({ ...details, total: 1, items: [{
      id: 'followup-1', quotationId: 'quote-1', title: 'Confirm quote', kind: 'followups' as const, date: '2026-09-01',
      accountId: 'customer-1', customer: 'Customer', salesOwner: 'alice', market: null, status: 'Open', carryover: true,
    }] }))
    await wrapper.get('select[aria-label="Activity type"]').setValue('quotation_carryover'); await flushPromises()
    expect(api.getPlanDetails).toHaveBeenCalledWith(expect.objectContaining({ metric: 'quotation_carryover' }))
    expect(wrapper.get('.agenda-item.followups').attributes('href')).toContain('/quotations/quote-1')
    expect(wrapper.findAll('.agenda-day')).toHaveLength(1)
    expect(wrapper.get('.agenda-item.followups').text()).toContain('Confirm quote')
    wrapper.unmount()
  })
  it('shows scheduled metrics, CNY estimates and seven days without carryover', async () => {
    const { wrapper, router } = await setup()
    expect(wrapper.findAll('.kpi')).toHaveLength(7)
    expect(wrapper.findAll('.agenda-day:not(.carryover)')).toHaveLength(7)
    expect(wrapper.find('.carryover').exists()).toBe(false)
    expect(wrapper.find('.overdue-link').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('往期未完成')
    expect(wrapper.findAll('.agenda-day h3').at(-1)!.text()).toContain('周日')
    expect(wrapper.get('.kpi.po').text()).toContain('CNY 6,800,000')
    expect(wrapper.get('.kpi.po').text()).not.toContain('USD')
    expect(wrapper.get('.kpi.po').text()).toContain('部分金额数据不足')
    expect(wrapper.text()).toContain('展会活动')
    expect(wrapper.text()).toContain('待发报价')
    expect(wrapper.text()).not.toMatch(/团队目标|内部会议/)
    // The equipment filter uses the Opportunities board catalog (#18).
    expect(wrapper.find('select[aria-label="Equipment"]').exists()).toBe(true)
    expect(router.currentRoute.value.meta.navigationPath).toBe('/dashboard')
    expect(wrapper.get('.agenda-item.tests').attributes('href')).toContain('focus=eval-1')
    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('.kpi.po').text()).toContain('Expected PO this period')
    wrapper.unmount()
  })
  it('keeps active Demos without a date or outside the period below the seven days', async () => {
    const details = planDetailsFixture()
    const test = details.items.find(row => row.kind === 'tests')!
    details.items.push(
      { ...test, id: 'undated-demo', title: 'Undated Demo', date: null },
      { ...test, id: 'old-demo', title: 'Earlier Demo', date: '2026-09-01' },
      { ...test, id: 'future-demo', title: 'Later Demo', date: '2026-10-01' },
    )
    const { wrapper } = await setup('Manager', planFixture(), details)
    expect(wrapper.findAll('.agenda-day:not(.outside-period)')).toHaveLength(7)
    const extra = wrapper.get('.agenda-day.outside-period')
    expect(extra.get('h3').text()).toContain('待排期／进行中')
    expect(extra.findAll('.agenda-item.tests')).toHaveLength(3)
    expect(extra.text()).toContain('尚未排期')
    expect(extra.text()).toContain('测试截止：2026-09-01')
    expect(extra.text()).toContain('测试截止：2026-10-01')
    expect(extra.text()).not.toContain('Invalid Date')
    expect(wrapper.get('.kpi.tests').text()).toContain('两项准备完成，尚未进入内部审核')
    for (const locale of ['zh-CN', 'en-US'] as const) {
      setLocale(locale); await flushPromises()
      for (const grouping of ['day', 'sales', 'market']) {
        await wrapper.get('select[aria-label="Group by"]').setValue(grouping); await flushPromises()
        const rows = wrapper.findAll('.agenda-item.tests')
        expect(rows).toHaveLength(4)
        const scheduledLabel = locale === 'en-US' ? 'Demos scheduled this period' : '本期安排 Demo'
        const otherLabel = locale === 'en-US' ? 'Other ongoing Demos' : '其他进行中 Demo'
        for (const row of rows) {
          const scheduled = row.get('strong').text() === test.title
          expect(row.text()).toContain(scheduled ? scheduledLabel : otherLabel)
          expect(row.text()).not.toContain(scheduled ? otherLabel : scheduledLabel)
        }
        expect(wrapper.get('.kpi.tests strong').text()).toBe('1')
        if (grouping !== 'day') expect(wrapper.find('.outside-period').exists()).toBe(false)
        expect(wrapper.text()).toContain(locale === 'en-US' ? 'Date not set' : '尚未排期')
      }
    }
    expect(wrapper.get('.kpi.tests').text()).toContain('Preparation complete, before Internal Review')
    wrapper.unmount()
  })
  it('renders the captured backend response, incomplete CNY amounts and hides carryover', async () => {
    const { wrapper, api } = await setup('Manager', apiSample.get_plan as PlanDto, apiSample['get_plan_details (metric=all, sales filter)'] as PlanDetails)
    expect(wrapper.get('.kpi.po strong').text()).toBe('9')
    expect(wrapper.get('.kpi.po').text()).toContain('CNY 400,000')
    expect(wrapper.get('.kpi.po').text()).toContain('部分金额数据不足')
    expect(wrapper.text()).not.toContain('2026-11-27')
    expect(wrapper.find('.carryover').exists()).toBe(false)
    expect(api.getPlanDetails).toHaveBeenCalledWith(expect.objectContaining({ anchor: '2026-12-01', pageSize: 50, includeOverdue: false }))
    wrapper.unmount()
  })
  it('labels unassigned sales and preserves an engineer owner outside the sales filter in both languages', async () => {
    const plan = planFixture(), details = planDetailsFixture()
    plan.sales[0] = { ...plan.sales[0], id: null, name: '' }
    const action = details.items.find(row => row.id === 'action-1')!
    action.salesOwner = null; action.actionOwner = 'engineer@example.invalid'
    const { wrapper } = await setup('Manager', plan, details)
    expect(wrapper.get('.sales-panel tbody th').text()).toBe('未分配')
    const actionRow = wrapper.findAll('.agenda-item.actions').find(row => row.text().includes(action.title))!
    expect(actionRow.text()).toContain('未分配')
    expect(actionRow.text()).toContain('执行人 · engineer@example.invalid')
    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('.sales-panel tbody th').text()).toBe('Unassigned')
    expect(actionRow.text()).toContain('Assigned to · engineer@example.invalid')
    wrapper.unmount()
  })
  it('prefers an engineer name supplied by the API and falls back for an empty name', async () => {
    const details = planDetailsFixture()
    const action = details.items.find(row => row.id === 'action-1')!
    action.actionOwner = 'engineer@example.invalid'; action.actionOwnerName = '王工程师'
    const { wrapper, api } = await setup('Manager', planFixture(), details)
    const actionRow = () => wrapper.findAll('.agenda-item.actions').find(row => row.text().includes(action.title))!
    expect(actionRow().text()).toContain('执行人 · 王工程师')
    expect(actionRow().text()).not.toContain('engineer@example.invalid')
    setLocale('en-US'); await flushPromises()
    expect(actionRow().text()).toContain('Assigned to · 王工程师')
    api.getPlanDetails = vi.fn(async () => response({ ...details, items: [{ ...action, actionOwnerName: '  ' }] }))
    await wrapper.get('.kpi.actions').trigger('click'); await flushPromises()
    expect(actionRow().text()).toContain('Assigned to · engineer@example.invalid')
    wrapper.unmount()
  })
  it('explains missing dates across Plan metrics in both languages without exposing unknown reason codes', async () => {
    const plan = planFixture()
    const missing = { value: null, state: 'insufficient' as const, reason: 'missing_date' }
    plan.summary.visits = missing; plan.sales[0].visits = missing
    plan.markets[0].activities = missing; plan.overdue = missing
    plan.summary.tests = { ...missing, reason: 'unknown_reason' }
    const { wrapper } = await setup('Manager', plan)
    const selectors = ['.kpi.visits strong', '.sales-panel tbody td', '.market-list article b']
    for (const selector of selectors) expect(wrapper.get(selector).text()).toContain('数据不足：部分记录未填写日期')
    expect(wrapper.get('.kpi.tests strong').text()).toBe('数据不足')
    expect(wrapper.text()).not.toMatch(/missing_date|unknown_reason/)
    setLocale('en-US'); await flushPromises()
    for (const selector of selectors) expect(wrapper.get(selector).text()).toContain('Insufficient data: some records have no date')
    expect(wrapper.get('.kpi.tests strong').text()).toBe('Insufficient data')
    wrapper.unmount()
  })
  it('lists the region filter as the territory tree and sends the territory that is chosen', async () => {
    const plan = planFixture()
    plan.filters = { ...plan.filters, regions: ['World', 'Asia', 'China', 'East China', 'Taiwan'], regionParents: { Asia: 'World', China: 'Asia', 'East China': 'China' }, regionReady: true }
    const { api, wrapper } = await setup('Manager', plan)
    const select = wrapper.get('select[aria-label="Region"]')
    expect(select.findAll('option').slice(1).map(option => option.element.textContent)).toEqual(['全球', '\u00a0\u00a0亚洲', '\u00a0\u00a0\u00a0\u00a0中国', '\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0华东', 'Taiwan'])
    await select.setValue('China'); await flushPromises()
    expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ region: 'China' }))
    wrapper.unmount()
  })
  it('passes filters, the server period anchor and pagination to the same business detail endpoint', async () => {
    const { api, wrapper } = await setup()
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    await wrapper.get('select[aria-label="Region"]').setValue('East China'); await flushPromises()
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    await wrapper.get('.kpi.po').trigger('click'); await flushPromises()
    expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ sales: 'alice', region: 'East China', market: 'Frontend' }))
    expect(api.getPlanDetails).toHaveBeenLastCalledWith(expect.objectContaining({ sales: 'alice', region: 'East China', market: 'Frontend', anchor: '2026-09-21', metric: 'po', page: 1, pageSize: 50 }))
    api.getPlanDetails = vi.fn(async q => response({ ...planDetailsFixture(), total: 61, page: q.page }))
    await wrapper.get('select[aria-label="Activity type"]').setValue('all'); await flushPromises()
    await wrapper.get('button[aria-label="下一页"]').trigger('click'); await flushPromises()
    expect(api.getPlanDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'all', page: 2, includeOverdue: false }))
    await wrapper.get('button[aria-label="下一周期"]').trigger('click'); await flushPromises()
    expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ anchor: '2026-09-28' }))
    wrapper.unmount()
  })
  it('switching to month, quarter or year opens the next period, not the current one', async () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-22T10:00:00+08:00'))
    try {
      const { api, wrapper } = await setup()
      const periodButton = (text: string) => wrapper.findAll('.segmented button').find(button => button.text() === text)!
      for (const [text, anchor] of [['月', '2026-10-01'], ['季度', '2026-10-01'], ['年', '2027-01-01'], ['周', '2026-09-28']]) {
        await periodButton(text).trigger('click'); await flushPromises()
        expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ anchor }))
      }
      // Clicking the active granularity keeps wherever the manager has paged to.
      await wrapper.get('button[aria-label="下一周期"]').trigger('click'); await flushPromises()
      const calls = vi.mocked(api.getPlan).mock.calls.length
      await periodButton('周').trigger('click'); await flushPromises()
      expect(api.getPlan).toHaveBeenCalledTimes(calls)
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })
  it.each(['Sales', 'Engineer'] as UserRole[])('does not request Plan for %s', async role => {
    const { wrapper, api, router } = await setup(role)
    expect(api.getPlan).not.toHaveBeenCalled()
    expect(api.getPlanDetails).not.toHaveBeenCalled()
    expect(wrapper.find('.plan-page').exists()).toBe(false)
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/calendar'))
    wrapper.unmount()
  })
  it('asks for a period only when the date field or the link holds a whole date in range', async () => {
    const { wrapper, api } = await setup()
    const getPlan = vi.mocked(api.getPlan)
    const field = wrapper.get<HTMLInputElement>('input[type="date"]')
    const shown = field.element.value
    expect([field.attributes('min'), field.attributes('max')]).toEqual(['2000-01-01', '2099-12-31'])
    getPlan.mockClear()
    // A cleared field, the year typed digit by digit, a mistyped year: nothing is asked for and nothing fails.
    for (const value of ['', '0002-09-21', '0202-09-21', '9999-01-01']) {
      field.element.value = value
      await field.trigger('change')
    }
    await flushPromises()
    expect(getPlan).not.toHaveBeenCalled()
    expect(wrapper.find('.error-banner').exists()).toBe(false)
    await field.trigger('blur')
    expect(field.element.value).toBe(shown)
    // Plan looks ahead: a date years from now is asked for.
    let finish!: () => void
    getPlan.mockImplementationOnce(() => new Promise((resolve) => { finish = () => resolve(response(planFixture())) }))
    field.element.value = '2031-05-05'
    await field.trigger('input'); await field.trigger('change')
    expect(getPlan).toHaveBeenCalledTimes(1)
    expect(getPlan.mock.calls[0][0]).toMatchObject({ anchor: '2031-05-05' })
    // What is typed while that load is pending stays in the field when its answer redraws the page.
    field.element.value = '0002-05-05'
    await field.trigger('input'); await field.trigger('change')
    finish(); await flushPromises()
    expect(getPlan).toHaveBeenCalledTimes(1)
    expect(field.element.value).toBe('0002-05-05')
    await field.trigger('blur')
    expect(field.element.value).toBe('2031-05-05')

    // The period that reaches into 2000 is the earliest: there is no stepping back from it.
    expect(wrapper.get('button[aria-label="上一周期"]').attributes('disabled')).toBeUndefined()
    const earliest = planFixture()
    earliest.period = { ...earliest.period, start: '1999-12-27', end: '2000-01-02', previousAnchor: '1999-12-20', nextAnchor: '2000-01-03' }
    getPlan.mockResolvedValueOnce(response(earliest))
    field.element.value = '2000-01-01'
    await field.trigger('input'); await field.trigger('change'); await field.trigger('blur')
    await flushPromises()
    expect(wrapper.get('button[aria-label="上一周期"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="下一周期"]').attributes('disabled')).toBeUndefined()
    // The details of that period are asked with its first day, which lies in 1999.
    expect(vi.mocked(api.getPlanDetails).mock.calls.at(-1)![0]).toMatchObject({ anchor: '1999-12-27' })
    // Review and Warnings are handed that earliest period, not the one before it, which they could not show.
    expect(wrapper.get('a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=week&anchor=1999-12-27')
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week&anchor=1999-12-27')
    wrapper.unmount()

    // A link with a date out of range opens on the period after today, like a link without a date.
    const fresh = await setup()
    const defaultAnchor = vi.mocked(fresh.api.getPlan).mock.calls[0][0].anchor
    fresh.wrapper.unmount()
    for (const anchor of ['0002-09-21', '1999-12-26', '9999-01-01']) {
      const linked = createMockApi({ role: 'Manager', latency: 0 })
      linked.getPlan = vi.fn(async () => response(planFixture()))
      linked.getPlanDetails = vi.fn(async () => response(planDetailsFixture()))
      const router = createAppRouter()
      await router.push(`/plan?period=week&anchor=${anchor}`); await router.isReady()
      const opened = mount(PlanPage, { props: { apiClient: linked }, global: { plugins: [createPinia(), router] } })
      await flushPromises()
      expect(vi.mocked(linked.getPlan).mock.calls[0][0]).toMatchObject({ period: 'week', anchor: defaultAnchor })
      opened.unmount()
    }
    // The first day of the week that reaches into 2000 is a date of 1999, and is taken.
    const earliestLink = createMockApi({ role: 'Manager', latency: 0 })
    earliestLink.getPlan = vi.fn(async () => response(planFixture()))
    earliestLink.getPlanDetails = vi.fn(async () => response(planDetailsFixture()))
    const earliestRouter = createAppRouter()
    await earliestRouter.push('/plan?period=week&anchor=1999-12-27'); await earliestRouter.isReady()
    const earliestPage = mount(PlanPage, { props: { apiClient: earliestLink }, global: { plugins: [createPinia(), earliestRouter] } })
    await flushPromises()
    expect(vi.mocked(earliestLink.getPlan).mock.calls[0][0]).toMatchObject({ period: 'week', anchor: '1999-12-27' })
    earliestPage.unmount()
  })

  it('suggests a server without Plan only when the failure is not about the period asked for', async () => {
    const { wrapper, api } = await setup()
    const hint = '若当前服务器尚未启用 Plan'
    vi.mocked(api.getPlan).mockRejectedValueOnce(new CrmApiError('VALIDATION_ERROR', 'Invalid Plan period or anchor.', 'req-plan', false))
    await wrapper.get('button[aria-label="刷新"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('.error-banner').text()).toContain('无法显示这个周期，请重新选择日期。')
    expect(wrapper.get('.error-banner').text()).not.toContain(hint)
    vi.mocked(api.getPlan).mockRejectedValueOnce(new CrmApiError('INTERNAL_ERROR', 'The request could not be completed.', 'req-plan', true))
    await wrapper.get('.error-banner button').trigger('click')
    await flushPromises()
    expect(wrapper.get('.error-banner').text()).toContain(hint)
    wrapper.unmount()
  })

  it('does not replace the latest filter results with a stale response', async () => {
    const { wrapper, api } = await setup()
    let resolve!: (value: Awaited<ReturnType<typeof api.getPlan>>) => void
    api.getPlan = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getPlan>>>(r => { resolve = r }))
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    api.getPlan = vi.fn(async () => response({ ...planFixture(), summary: { ...planFixture().summary, visits: { value: 9, state: 'ready' as const } } }))
    await wrapper.get('select[aria-label="Sales"]').setValue('bob'); await flushPromises()
    resolve(response(planFixture())); await flushPromises()
    expect(wrapper.get('.kpi.visits strong').text()).toBe('9')
    wrapper.unmount()
  })
  it('clears data on permission loss and ignores an in-flight detail response', async () => {
    const { wrapper, api, app } = await setup()
    let resolve!: (value: Awaited<ReturnType<typeof api.getPlanDetails>>) => void
    api.getPlanDetails = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getPlanDetails>>>(r => { resolve = r }))
    await wrapper.get('.kpi.po').trigger('click'); await flushPromises()
    app.bootstrap!.user.role = 'Sales'; await flushPromises()
    resolve(response(planDetailsFixture())); await flushPromises()
    expect(wrapper.find('.plan-page').exists()).toBe(false)
    wrapper.unmount()
  })
  it('shows an API failure without fabricated zeros and lets the user retry', async () => {
    const { wrapper, api } = await setup()
    api.getPlan = vi.fn(async () => { throw new Error('Plan API unavailable') })
    await wrapper.get('button[aria-label="刷新"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Plan API unavailable')
    expect(wrapper.get('.kpi.visits strong').text()).toBe('—')
    expect(wrapper.find('.agenda-item').exists()).toBe(false)
    expect(wrapper.find('.market-panel').exists()).toBe(true)
    api.getPlan = vi.fn(async () => response(planFixture()))
    await wrapper.get('.error-banner button').trigger('click'); await flushPromises()
    expect(wrapper.find('.error-banner').exists()).toBe(false)
    expect(wrapper.get('.kpi.visits strong').text()).toBe('2')
    wrapper.unmount()
  })

  it('filters Plan by equipment and reports planned records without an opportunity', async () => {
    const plan = planFixture()
    plan.filters = { ...plan.filters, equipment: ['Aconca', 'Kibo'] }
    plan.equipmentUnclassified = { visits: 3, tests: 1 }
    const { wrapper, api } = await setup('Manager', plan)
    await wrapper.get('select[aria-label="Equipment"]').setValue('Aconca'); await flushPromises()
    expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ equipment: 'Aconca' }))
    expect(wrapper.get('[data-unclassified]').text()).toContain('3 条拜访 · 1 个 Demo 测试')
    wrapper.unmount()
  })

  it('sends the exact equipment spelling and counts unlinked records in English', async () => {
    setLocale('en-US')
    const plan = planFixture()
    plan.filters = { ...plan.filters, equipment: ['Kibo  4895C'] }
    plan.equipmentUnclassified = { visits: 1, tests: 2 }
    const { wrapper, api } = await setup('Manager', plan)
    await wrapper.get('select[aria-label="Equipment"]').setValue('Kibo  4895C'); await flushPromises()
    expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ equipment: 'Kibo  4895C' }))
    expect(wrapper.get('[data-unclassified]').text()).toContain('1 visit · 2 Demo tests')
    wrapper.unmount()
  })

  it('resets region, sales, market and equipment together and keeps the period', async () => {
    const { api, wrapper } = await setup()
    const reset = wrapper.get('[data-testid="plan-filter-reset"]')
    expect(reset.attributes('disabled')).toBeDefined()
    await wrapper.get('select[aria-label="Region"]').setValue('East China')
    await wrapper.get('select[aria-label="Sales"]').setValue('alice')
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend')
    await wrapper.get('select[aria-label="Equipment"]').setValue('Kibo  4895C'); await flushPromises()
    expect(reset.attributes('disabled')).toBeUndefined()
    const anchor = vi.mocked(api.getPlan).mock.lastCall![0].anchor
    await reset.trigger('click'); await flushPromises()
    expect(vi.mocked(api.getPlan).mock.lastCall![0]).toMatchObject({ period: 'week', anchor, region: '', sales: '', market: '', equipment: '' })
    expect((wrapper.get('select[aria-label="Sales"]').element as HTMLSelectElement).value).toBe('')
    expect((wrapper.get('select[aria-label="Equipment"]').element as HTMLSelectElement).value).toBe('')
    expect(reset.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  async function open(path: string, configure?: (api: ReturnType<typeof createMockApi>) => void) {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getPlan = vi.fn(async () => response(planFixture()))
    api.getPlanDetails = vi.fn(async () => response(planDetailsFixture()))
    configure?.(api)
    const router = createAppRouter()
    await router.push(path); await router.isReady()
    const wrapper = mount(PlanPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    const href = (path: string) => wrapper.get(`.view-tabs a[href^="${path}"]`).attributes('href')
    return { api, wrapper, href }
  }

  it('keeps a direct Plan Q4 link on Q4 and returns to the preceding Review quarter with the same scope', async () => {
    const { api, wrapper, href } = await open('/plan?region=East+China&sales=alice&market=Frontend&equipment=Aconca&period=quarter&anchor=2026-10-01')
    expect(api.getPlan).toHaveBeenNthCalledWith(1, { period: 'quarter', anchor: '2026-10-01', sales: 'alice', region: 'East China', market: 'Frontend', equipment: 'Aconca' })
    expect(href('/dashboard')).toBe('/dashboard?period=quarter&anchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Aconca')
    expect(href('/warnings')).toBe('/warnings?period=quarter&anchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Aconca')
    expect(href('/opportunity-board')).toBe('/opportunity-board?period=quarter&reviewAnchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Aconca')
    // Changing a filter here goes along on the way back.
    await wrapper.get('select[aria-label="Market"]').setValue(''); await flushPromises()
    expect(href('/dashboard')).toBe('/dashboard?period=quarter&anchor=2026-07-01&sales=alice&region=East+China&equipment=Aconca')
    wrapper.unmount()
  })

  it('advances a Review anchor exactly once across the year and restores it on the way back', async () => {
    // After the periods involved, so Review's "not started yet" limit does not apply to them.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2027-03-01T10:00:00+08:00'))
    try {
      const { api, wrapper, href } = await open('/plan?period=month&reviewAnchor=2026-12-15&sales=alice')
      expect(api.getPlan).toHaveBeenNthCalledWith(1, { period: 'month', anchor: '2027-01-01', sales: 'alice', region: '', market: '', equipment: '' })
      expect(href('/dashboard')).toBe('/dashboard?period=month&anchor=2026-12-15&sales=alice')
      // Paging Plan on moves the Review period with it.
      await wrapper.get('input[aria-label="周期日期"]').setValue('2027-02-01'); await flushPromises()
      expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'month', anchor: '2027-02-01' }))
      expect(href('/dashboard')).toBe('/dashboard?period=month&anchor=2027-01-01&sales=alice')
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })

  it('never links Review, Warnings or Opportunities to a period that has not started when Plan is paged ahead', async () => {
    // Wednesday 2026-09-30: Plan opens on the week of 2026-10-05; Review and Warnings refuse a future period.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-30T10:00:00+08:00'))
    try {
      const { api, wrapper, href } = await open('/plan?sales=alice')
      expect(api.getPlan).toHaveBeenNthCalledWith(1, { period: 'week', anchor: '2026-10-05', sales: 'alice', region: '', market: '', equipment: '' })
      expect(href('/dashboard')).toBe('/dashboard?period=week&anchor=2026-09-28&sales=alice')
      await wrapper.get('input[aria-label="周期日期"]').setValue('2026-10-12'); await flushPromises()
      expect(api.getPlan).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'week', anchor: '2026-10-12' }))
      expect(href('/dashboard')).toBe('/dashboard?period=week&anchor=2026-09-28&sales=alice')
      expect(href('/warnings')).toBe('/warnings?period=week&anchor=2026-09-28&sales=alice')
      expect(href('/opportunity-board')).toBe('/opportunity-board?period=week&reviewAnchor=2026-09-28&sales=alice')
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })

  it('opens without context on the next Shanghai week and links back to the current one, even when Plan fails to load', async () => {
    // Sunday 16:30 UTC is already Monday 2026-10-05 in Shanghai.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-04T16:30:00Z'))
    try {
      const { api, wrapper, href } = await open('/plan', api => { api.getPlan = vi.fn().mockRejectedValue(new Error('Plan API unavailable')) })
      expect(api.getPlan).toHaveBeenNthCalledWith(1, { period: 'week', anchor: '2026-10-12', sales: '', region: '', market: '', equipment: '' })
      expect(wrapper.get('[role="alert"]').text()).toContain('Plan API unavailable')
      expect(href('/dashboard')).toBe('/dashboard?period=week&anchor=2026-10-05')
      expect(href('/opportunity-board')).toBe('/opportunity-board?period=week&reviewAnchor=2026-10-05')
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })
})
