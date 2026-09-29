import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
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
  it('shows four approved metrics, CNY estimates, seven days without carryover', async () => {
    const { wrapper, router } = await setup()
    expect(wrapper.findAll('.kpi')).toHaveLength(4)
    expect(wrapper.findAll('.agenda-day:not(.carryover)')).toHaveLength(7)
    expect(wrapper.find('.carryover').exists()).toBe(false)
    expect(wrapper.find('.overdue-link').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('往期未完成')
    expect(wrapper.findAll('.agenda-day h3').at(-1)!.text()).toContain('周日')
    expect(wrapper.get('.kpi.po').text()).toContain('CNY 6,800,000')
    expect(wrapper.get('.kpi.po').text()).not.toContain('USD')
    expect(wrapper.get('.kpi.po').text()).toContain('部分金额数据不足')
    expect(wrapper.text()).not.toMatch(/待发送报价|团队目标|展会|内部会议/)
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
    test.date = null
    details.items.push({ ...test, id: 'old-demo', date: '2026-09-01' }, { ...test, id: 'future-demo', date: '2026-10-01' })
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
    await wrapper.get('select[aria-label="Group by"]').setValue('sales'); await flushPromises()
    expect(wrapper.findAll('.agenda-item.tests')).toHaveLength(3)
    expect(wrapper.find('.outside-period').exists()).toBe(false)
    expect(wrapper.text()).toContain('尚未排期')
    setLocale('en-US'); await flushPromises()
    expect(wrapper.text()).toContain('Date not set')
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
})
