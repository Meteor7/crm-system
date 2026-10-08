import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api/contracts'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import { reviewFixture } from '@/features/cockpit/review.fixture'
import { planDetailsFixture, planFixture } from '@/features/cockpit/plan.fixture'
import { monotoneCurvePath } from '@/features/cockpit/presentation'
import { setLocale } from '@/i18n'
import type { UserRole } from '@/types/crm'
import ReviewPage from './ReviewPage.vue'
import PlanPage from './PlanPage.vue'

beforeEach(() => {
  setLocale('zh-CN')
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
async function setup(role: UserRole = 'Manager') {
  const api = createMockApi({ role, latency: 0 })
  api.getReview = vi.fn(async () => ({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }))
  api.getReviewTarget = vi.fn(async () => ({ data: null, warnings: [], meta: { requestId: 'target-test' } }))
  api.getReviewDetails = vi.fn(async () => ({ data: { items: [], page: 1, pageSize: 20, total: 0, asOf: '' }, warnings: [], meta: { requestId: 'detail-test', generatedAt: '' } }))
  const pinia = createPinia()
  const router = createAppRouter()
  await router.push('/dashboard'); await router.isReady()
  const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, api, router, app: useAppStore(pinia) }
}
describe('Manager Review', () => {
  it('shows visit snapshots, incomplete quote value and completed follow-ups with matching details', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    const ready = (value: number | string) => ({ state: 'ready' as const, value })
    data.activities[0].customerKinds = [
      { key: 'existing', actual: ready(7), previous: ready(6), delta: 1 },
      { key: 'prospect', actual: ready(3), previous: ready(3), delta: 0 },
      { key: 'unclassified', actual: ready(2), previous: ready(1), delta: 1 },
    ]
    data.activities.find(row => row.key === 'quotes')!.quoteAmount = { actual: { state: 'insufficient', value: null }, previous: ready('1000000'), delta: null, known: '1500000', missing: 1, previousKnown: '1000000', previousMissing: 0 }
    data.activities.push({ key: 'followups', actual: ready(2), previous: ready(1), delta: 1, target: { value: 3, state: 'ready', record: null } })
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'breakdowns' } }))
    api.getReviewDetails = vi.fn(async q => ({ data: { items: [{ id: 'followup-1', quotationId: 'quote-1', quotationVersionId: 'version-1', kind: 'followup' as const, title: 'Call buyer', customer: 'Customer', owner: 'alice', at: '2026-09-10', accountId: 'c' }], page: 1, pageSize: 20, total: 1, asOf: '' }, warnings: [], meta: { requestId: q.metric } }))
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    expect(wrapper.findAll('.activity-grid article')).toHaveLength(5)
    const breakdown = wrapper.get('[data-visit-classification]')
    expect(breakdown.text()).toContain('按拜访完成时保存')
    expect(breakdown.text()).toContain('未分类')
    await breakdown.findAll('button')[2].trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'visits_unclassified' }))
    const quote = wrapper.get('[data-quote-amount]')
    expect(quote.text()).toContain('数据不足')
    expect(quote.text()).toContain('¥1.5M')
    expect(quote.text()).toContain('1 份报价缺少人民币快照')
    await wrapper.findAll('.activity-grid article').find(row => row.text().includes('报价跟进'))!.get('button').trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'followups' }))
    expect(wrapper.get('.detail-dialog tbody a').attributes('href')).toContain('/quotations/quote-1')
    expect(wrapper.get('.detail-dialog tbody a').attributes('href')).toContain('version=version-1')
    wrapper.unmount()
  })

  it('shows confirmed loss categories and opens their exact filtered records', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    data.losses.completionPercent = { value: '66.67', state: 'ready' }
    data.losses.categories = ['Price', 'pending', 'unclassified'].map(key => ({ key, count: { state: 'ready', value: 1 } }))
    data.stalled.thresholdDays = 12; data.stalled.escalationDays = 20
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'loss-categories' } }))
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    expect(wrapper.get('[data-loss-breakdown]').text()).toContain('66.7%')
    expect(wrapper.get('[data-loss-breakdown]').text()).toContain('已复盘，分类待补全')
    expect(wrapper.get('.stalled-panel').text()).toContain('12 天提醒 / 20 天升级')
    await wrapper.get('[data-loss-breakdown] button').trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'loss_reason:Price' }))
    expect(wrapper.get('.detail-dialog h2').text()).toBe('价格')
    wrapper.unmount()
  })
  it('keeps historical owners visible while excluding them from new target assignments', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    data.targetOptions = { territories: [], teamMembers: ['alice'] }
    data.activities[0].target = { state: 'insufficient', value: null, record: null, scope: 'sales',
      sources: [{ member: 'bob', state: 'insufficient', value: null, record: null, assignable: false }] }
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'roster' } }))
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    expect(wrapper.get('[data-target-sources]').text()).toContain('保留实际活动，无法分配新目标')
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="target-sales"]').findAll('option').map(option => option.attributes('value'))).toEqual(['', 'alice'])
    expect(wrapper.text()).toContain('Bob')
    wrapper.unmount()
  })
  it('shows incomplete team and region target sources without inventing a total or plan line', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    data.activities[0].target = { state: 'insufficient', value: null, record: null, scope: 'sales', missing: ['bob'],
      sources: [{ member: 'alice', state: 'ready', value: '0', record: null }, { member: 'bob', state: 'not_set', value: null, record: null }] }
    data.orders.target = { state: 'insufficient', value: null, record: null, scope: 'territory', missing: ['West China'],
      sources: [{ member: 'East China', state: 'ready', value: '1500000', record: null }, { member: 'West China', state: 'not_set', value: null, record: null }] }
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'target-sources' } }))
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    const sources = wrapper.get('.activity-grid [data-target-sources]')
    expect(sources.get('summary').text()).toContain('1 / 2')
    expect(sources.findAll('li').map(row => row.text())).toEqual(['Alice0', 'Bob未设置'])
    expect(wrapper.get('.activity-target').text()).toContain('数据不足')
    expect(wrapper.get('.annual-target-sources').text()).toContain('West China')
    expect(wrapper.find('.plan-line').exists()).toBe(false)
    expect(wrapper.find('.actual-line').exists()).toBe(true)
    expect(wrapper.get('.heading-order').text()).toContain('数据不足')
    wrapper.unmount()
  })

  it('edits the as-of year leaf target across a New Year week and clears the sales identity', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    data.period = { ...data.period, start: '2025-12-29', end: '2026-01-04', asOf: '2026-01-04T15:59:59Z' }
    const record = { id: 'region-target', modified: 'region-v1', scope: 'territory' as const, territory: 'East China',
      sales: '', metric: 'orders' as const, period: 'year' as const, anchor: '2026-01-01', value: '1500000' }
    data.targetOptions = { territories: ['East China'], teamMembers: ['alice', 'bob'] }
    data.targets = [record]
    api.getReviewTarget = vi.fn(async () => ({ data: record, warnings: [], meta: { requestId: 'target-test' } }))
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'region-target' } }))
    api.saveReviewTarget = vi.fn(async input => ({ data: { ...record, ...input, modified: 'region-v2' }, warnings: [], meta: { requestId: 'saved' } }))
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="target-scope"]').setValue('territory')
    await wrapper.get('[data-testid="target-territory"]').setValue('East China'); await flushPromises()
    expect(wrapper.get('[data-testid="target-territory"] option[value="East China"]').text()).toBe('华东')
    expect(wrapper.get('[data-testid="target-metric"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="target-period"]').attributes('disabled')).toBeDefined()
    expect((wrapper.get('.target-dialog input[type="number"]').element as HTMLInputElement).value).toBe('1500000')
    await wrapper.get('.target-dialog input[type="number"]').setValue('2000000')
    await wrapper.get('.target-dialog form').trigger('submit'); await flushPromises()
    expect(api.saveReviewTarget).toHaveBeenCalledWith({ sales: '', scope: 'territory', territory: 'East China', metric: 'orders',
      period: 'year', anchor: '2026-01-01', value: '2000000' }, 'region-v1')
    expect(wrapper.get('.target-dialog').text()).toContain('目标已保存')
    wrapper.unmount()
  })

  it('opens current Demo resource warnings instead of an unsupported historic drilldown', async () => {
    const { wrapper, api, router } = await setup()
    const data = reviewFixture()
    data.warnings.push({ key: 'demo_resources', count: { value: 1, state: 'insufficient', reason: 'missing_resource_schedule' } })
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'resources', generatedAt: '' } }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    const button = wrapper.findAll('.warning-links button').find(row => row.text().includes('Demo 设备风险'))!
    await button.trigger('click'); await flushPromises()
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/warnings'))
    expect(api.getReviewDetails).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('asks for a period only when the date field holds a whole date it can show', async () => {
    // Noon on 2026-10-04 in Shanghai.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-04T04:00:00Z'))
    try {
      const { wrapper, api } = await setup()
      const getReview = vi.mocked(api.getReview)
      const field = wrapper.get<HTMLInputElement>('input[type="date"]')
      expect([field.attributes('min'), field.attributes('max')]).toEqual(['2000-01-01', '2026-10-04'])
      expect(field.element.value).toBe(reviewFixture().period.start)
      getReview.mockClear()

      // The year typed digit by digit, a cleared field, a date in the future: nothing is asked for.
      for (const value of ['0002-09-21', '0020-09-21', '0202-09-21', '', '2026-10-05', '2026-12-01']) {
        field.element.value = value
        await field.trigger('change')
      }
      await flushPromises()
      expect(getReview).not.toHaveBeenCalled()
      expect(wrapper.find('.review-state.error').exists()).toBe(false)
      // Leaving the field puts the date on show back.
      await field.trigger('blur')
      expect(field.element.value).toBe(reviewFixture().period.start)

      // A whole date in range is asked for, and the field stays usable while it loads: disabling it took the
      // focus away after the first digit.
      let finish!: () => void
      getReview.mockImplementationOnce(() => new Promise((resolve) => {
        finish = () => resolve({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } })
      }))
      field.element.value = '2025-09-21'
      await field.trigger('input'); await field.trigger('change')
      expect(getReview).toHaveBeenCalledTimes(1)
      expect(getReview.mock.calls[0][0]).toMatchObject({ period: 'week', anchor: '2025-09-21' })
      expect(field.attributes('disabled')).toBeUndefined()
      expect(field.element.value).toBe('2025-09-21')
      // The user types on while that load is pending. Its answer redraws the page and must leave what is being
      // typed in the field; leaving the field then puts the date on show back.
      await field.trigger('focus')
      field.element.value = '0002-09-21'
      await field.trigger('input'); await field.trigger('change')
      finish(); await flushPromises()
      expect(getReview).toHaveBeenCalledTimes(1)
      expect(field.element.value).toBe('0002-09-21')
      await field.trigger('blur')
      expect(field.element.value).toBe('2025-09-21')
      // Today itself is the last date taken.
      field.element.value = '2026-10-04'
      await field.trigger('change')
      expect(getReview.mock.calls.at(-1)![0]).toMatchObject({ anchor: '2026-10-04' })
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })

  it('keeps the earliest week through its links and gives way to 2000 when the kind of period changes', async () => {
    const earliest = reviewFixture()
    earliest.period = { ...earliest.period, start: '1999-12-27', end: '2000-01-02', previousAnchor: '1999-12-20', nextAnchor: '2000-01-03', hasNext: true }
    const api = createMockApi({ role: 'Manager', latency: 0 })
    const getReview = vi.fn(async () => ({ data: earliest, warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }))
    api.getReview = getReview
    const router = createAppRouter()
    // The first day of the week that reaches into 2000, as "previous period" and the other cockpit pages give it.
    await router.push('/dashboard?period=week&anchor=1999-12-27'); await router.isReady()
    const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(getReview).toHaveBeenLastCalledWith({ period: 'week', anchor: '1999-12-27', sales: '', market: '', region: '', equipment: '' })
    expect(wrapper.find('.review-state.error').exists()).toBe(false)
    // Warnings and Plan are handed that same week.
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week&anchor=1999-12-27')
    expect(wrapper.get('a[href^="/plan"]').attributes('href')).toBe('/plan?period=week&anchor=2000-01-03&reviewAnchor=1999-12-27')

    // As a month, 1999-12-27 lies in a period that ends before 2000: the month of 2000-01-01 is asked for.
    await wrapper.findAll('.period-controls .segmented button')[1].trigger('click')
    await flushPromises()
    expect(getReview).toHaveBeenLastCalledWith({ period: 'month', anchor: '2000-01-01', sales: '', market: '', region: '', equipment: '' })
    wrapper.unmount()

    // A link that names that day as a month is opened on the default period.
    await router.push('/dashboard?period=month&anchor=1999-12-27')
    const asMonth = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(getReview).toHaveBeenLastCalledWith({ period: 'month', sales: '', market: '', region: '', equipment: '' })
    asMonth.unmount()
  })

  it('leaves the date field as the user has it when the page loads behind it', async () => {
    // Opened without a date: the field is empty until the first answer. The user is already in it, and has typed
    // part of a date, which changes nothing a script can see.
    const api = createMockApi({ role: 'Manager', latency: 0 })
    let finish!: () => void
    api.getReview = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getReview>>>((resolve) => {
      finish = () => resolve({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } })
    }))
    const router = createAppRouter()
    await router.push('/dashboard'); await router.isReady()
    const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    const field = wrapper.get<HTMLInputElement>('input[type="date"]')
    expect(field.element.value).toBe('')
    await field.trigger('focus')
    finish(); await flushPromises()
    expect(field.element.value).toBe('')
    // Leaving the field shows the date of the period that was loaded.
    await field.trigger('blur')
    expect(field.element.value).toBe(reviewFixture().period.start)
    wrapper.unmount()
  })

  it('does not step back from the earliest period it can show', async () => {
    const earliest = reviewFixture()
    earliest.period = { ...earliest.period, start: '1999-12-27', end: '2000-01-02', previousAnchor: '1999-12-20', nextAnchor: '2000-01-03', hasNext: true }
    const { wrapper, api } = await setup()
    expect(wrapper.get('button[aria-label="上一期"]').attributes('disabled')).toBeUndefined()
    vi.mocked(api.getReview).mockResolvedValue({ data: earliest, warnings: [], meta: { requestId: 'review-test', generatedAt: '' } })
    const field = wrapper.get<HTMLInputElement>('input[type="date"]')
    field.element.value = '2000-01-01'
    await field.trigger('input'); await field.trigger('change'); await field.trigger('blur')
    await flushPromises()
    expect(field.element.value).toBe('2000-01-01')
    expect(wrapper.get('button[aria-label="上一期"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="下一期"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('opens on its default period when a link carries a date it cannot show', async () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-04T04:00:00Z'))
    try {
      for (const anchor of ['2026-12-01', '0002-09-21', '2026-13-40', 'next']) {
        const api = createMockApi({ role: 'Manager', latency: 0 })
        api.getReview = vi.fn(async () => ({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }))
        const router = createAppRouter()
        await router.push(`/dashboard?period=month&anchor=${anchor}&market=Frontend`); await router.isReady()
        const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
        await flushPromises()
        // No anchor is sent: the server answers with its default period, and the rest of the link is kept.
        expect(api.getReview).toHaveBeenCalledTimes(1)
        expect(api.getReview).toHaveBeenCalledWith({ period: 'month', sales: '', market: 'Frontend', region: '', equipment: '' })
        expect(wrapper.find('.review-state.error').exists()).toBe(false)
        wrapper.unmount()
      }
    } finally { vi.useRealTimers() }
  })

  it('opens with the period and filters Warnings hands back, and ignores values it does not know', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getReview = vi.fn(async () => ({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }))
    const router = createAppRouter()
    await router.push('/dashboard?period=month&anchor=2026-08-01&market=Frontend&equipment=Kibo&sales=&bogus=1'); await router.isReady()
    const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getReview).toHaveBeenNthCalledWith(1, { period: 'month', anchor: '2026-08-01', sales: '', market: 'Frontend', region: '', equipment: 'Kibo' })
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=month&anchor=2026-08-01&market=Frontend&equipment=Kibo')
    // While a reload is on its way, the anchor it asked for already names the period to hand over.
    let release = () => {}
    api.getReview = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getReview>>>(resolve => { release = () => resolve({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }) }))
    await wrapper.get('[aria-label="上一期"]').trigger('click')
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=month&anchor=2026-08-31&market=Frontend&equipment=Kibo')
    release(); await flushPromises()
    wrapper.unmount()
    // Opened without an anchor, the period on show is unknown until the data is here: the tab is not a link yet.
    let first = () => {}
    api.getReview = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getReview>>>(resolve => { first = () => resolve({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }) }))
    await router.push('/dashboard?period=day'); await router.isReady()
    const fallback = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getReview).toHaveBeenLastCalledWith({ period: 'week', sales: '', market: '', region: '', equipment: '' })
    expect(fallback.find('a[href^="/warnings"]').exists()).toBe(false)
    const pending = fallback.get('.review-controls [aria-disabled="true"]')
    expect([pending.text(), pending.attributes('role')]).toEqual(['Warnings', 'link'])
    expect(pending.attributes('title')).toBe('页面加载完成后可用')
    first(); await flushPromises()
    // Without an anchor of its own, the Warnings link carries the week on show: Warnings would otherwise open on the current one.
    expect(fallback.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week&anchor=2026-09-07')
    fallback.unmount()
    // An anchor that is only whitespace is no anchor (the backend trims it): the page must not hand it on.
    await router.push('/dashboard?anchor=%20'); await router.isReady()
    api.getReview = vi.fn(async () => ({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }))
    const blank = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getReview).toHaveBeenLastCalledWith({ period: 'week', sales: '', market: '', region: '', equipment: '' })
    expect(blank.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week&anchor=2026-09-07')
    blank.unmount()
  })

  it('round-trips Review Q3 to Plan Q4 and back to Q3 with the same scope, from the first request of each page', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    // The loaded week (2026-09-07) is stale next to the quarter asked for: the selected anchor wins.
    api.getReview = vi.fn(async () => ({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }))
    api.getPlan = vi.fn(async () => ({ data: planFixture(), warnings: [], meta: { requestId: 'plan-test', generatedAt: '' } }))
    api.getPlanDetails = vi.fn(async () => ({ data: planDetailsFixture(), warnings: [], meta: { requestId: 'plan-test', generatedAt: '' } }))
    const router = createAppRouter()
    await router.push('/dashboard?period=quarter&anchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Kibo'); await router.isReady()
    const scope = { sales: 'alice', market: 'Frontend', region: 'East China', equipment: 'Kibo' }
    const review = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getReview).toHaveBeenNthCalledWith(1, { period: 'quarter', anchor: '2026-07-01', ...scope })
    const planHref = review.get('a[href^="/plan"]').attributes('href')!
    expect(planHref).toBe('/plan?period=quarter&anchor=2026-10-01&reviewAnchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Kibo')
    expect(review.get('a[href^="/opportunity-board"]').attributes('href')).toBe('/opportunity-board?period=quarter&reviewAnchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Kibo')
    review.unmount()

    await router.push(planHref)
    const plan = mount(PlanPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getPlan).toHaveBeenNthCalledWith(1, { period: 'quarter', anchor: '2026-10-01', ...scope })
    const backHref = plan.get('.view-tabs a[href^="/dashboard"]').attributes('href')!
    expect(backHref).toBe('/dashboard?period=quarter&anchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Kibo')
    expect(plan.get('.view-tabs a[href^="/warnings"]').attributes('href')).toBe(backHref.replace('/dashboard', '/warnings'))
    plan.unmount()

    await router.push(backHref)
    const again = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getReview).toHaveBeenNthCalledWith(2, { period: 'quarter', anchor: '2026-07-01', ...scope })
    again.unmount()
  })

  it('links Plan and Opportunities to the Shanghai default period after the first load fails without filters', async () => {
    // Sunday 16:30 UTC is Monday 2026-10-05 in Shanghai: Review's default is the week of 2026-09-28, not 2026-09-21.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-04T16:30:00Z'))
    try {
      const api = createMockApi({ role: 'Manager', latency: 0 })
      api.getReview = vi.fn().mockRejectedValue(new Error('network down'))
      const router = createAppRouter()
      await router.push('/dashboard'); await router.isReady()
      const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
      await flushPromises()
      expect(wrapper.find('.review-state.error').exists()).toBe(true)
      expect(wrapper.get('a[href^="/plan"]').attributes('href')).toBe('/plan?period=week&anchor=2026-10-05&reviewAnchor=2026-09-28')
      expect(wrapper.get('a[href^="/opportunity-board"]').attributes('href')).toBe('/opportunity-board?period=week&reviewAnchor=2026-09-28')
      // Task 5: Warnings stays reachable and opens on its own default.
      expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week')
      // An ISO week that spans the new year leads to the first Plan week of the next year.
      vi.setSystemTime(new Date('2026-12-30T04:00:00Z'))
      await router.push('/dashboard?anchor=2026-12-28&region=East+China')
      const boundary = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
      await flushPromises()
      expect(boundary.get('a[href^="/plan"]').attributes('href')).toBe('/plan?period=week&anchor=2027-01-04&reviewAnchor=2026-12-28&region=East+China')
      boundary.unmount(); wrapper.unmount()
    } finally { vi.useRealTimers() }
  })

  it('marks each 12-month loss with its post-mortem state and counts reviewed and pending losses', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    const loss = data.losses.items[0]
    data.losses = { count: { state: 'ready', value: 2 }, reviewed: { state: 'ready', value: 1 }, pending: { state: 'ready', value: 1 }, items: [
      { ...loss, review: null, reviewPending: true, reviewOverdue: true, reopenedAt: null },
      { ...loss, id: 'loss-2', eventId: 'loss-event-2', reviewPending: false, reopenedAt: null,
        review: { id: 'r2', status: 'reviewed', note: 'Report shared', reviewedBy: 'alice', reviewedAt: '2026-09-11T02:00:00Z', modified: null } },
    ] }
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'losses' } }))
    await wrapper.get('select[aria-label="Sales"]').setValue('bob'); await flushPromises()
    const panel = wrapper.get('.losses-panel')
    expect(panel.findAll('[data-loss-status]').map(tag => tag.text())).toEqual(['复盘逾期', '已复盘'])
    expect(panel.get('.list-footer').text()).toContain('已复盘 1 · 待复盘 1')
    wrapper.unmount()
  })

  it('shows quotation expiry reference dates, current owners and exact formal-version links', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    data.warnings.push({ key: 'quotation_expiry', count: { state: 'ready', value: 1 } })
    data.quotationExpiry = { referenceDate: '2026-09-22', thresholdDays: 14 }
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'expiry' } }))
    api.getReviewDetails = vi.fn(async q => ({ data: { items: [{ id: 'Q-1', title: 'Quote 1', accountId: 'customer', customer: 'Customer', owner: 'bob',
      at: '2026-09-21T16:00:00Z', kind: 'quotation' as const, quotationVersionId: 'V-1', quotationVersionNo: 1, validUntil: '2026-09-22', daysToExpiry: 0 }],
      page: q.page ?? 1, pageSize: 20, total: 21, asOf: '' }, warnings: [], meta: { requestId: 'expiry-details' } }))
    await wrapper.get('select[aria-label="Sales"]').setValue('bob'); await flushPromises()
    await wrapper.findAll('.warning-strip button').find(button => button.text().includes('报价'))!.trigger('click'); await flushPromises()
    const dialog = wrapper.get('.detail-dialog')
    expect(dialog.get('.dialog-note').text()).toContain('2026-09-22')
    expect(dialog.get('.dialog-note').text()).toContain('14')
    expect(dialog.get('.dialog-note').text()).toContain('当前仍有效')
    expect(dialog.get('thead').text()).toContain('有效期至')
    expect(dialog.get('tbody').text()).toContain('Bob')
    expect(dialog.get('[data-quotation-expiry]').text()).toContain('V1 · 截止日当天到期')
    expect(dialog.get('a').attributes('href')).toBe('/quotations/Q-1?version=V-1')
    await dialog.findAll('.dialog-pagination button')[1].trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'quotation_expiry', sales: 'bob', page: 2 }))
    setLocale('en-US'); await flushPromises()
    expect(dialog.text()).toContain('Due on reference date')
    expect(dialog.get('.dialog-note').text()).toContain('Latest published versions still open now')
    wrapper.unmount()
  })

  it('opens historical conversion samples with the selected scope and paginates them', async () => {
    const { wrapper, api } = await setup()
    const data = reviewFixture()
    data.conversions = { start: '2024-09-22', end: '2026-09-22', verifiedFrom: null, complete: false, thresholdPercent: 45,
      items: [{ fromStage: 'quotation_sent', toStage: 'po_received', fromCount: 3, toCount: 1, rate: { state: 'insufficient', value: null }, bottleneck: null }] }
    api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'conversion' } }))
    api.getReviewDetails = vi.fn(async q => ({ data: { items: [{ id: 'opp', title: 'Known win', accountId: 'c', customer: 'Customer', owner: 'alice', kind: 'opportunity' as const, stage: 'po_received', at: '2026-09-01T00:00:00Z' }],
      total: 21, page: q.page ?? 1, pageSize: 20, asOf: '' }, warnings: [], meta: { requestId: 'samples' } }))
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    await wrapper.findAll('.conversion-panel tbody button')[1].trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'reached_po_received', sales: 'alice' }))
    const dialog = wrapper.get('.detail-dialog')
    expect(dialog.get('h2').text()).toContain('已收到 PO')
    expect(dialog.get('.dialog-note').text()).toContain('2024-09-22')
    expect(dialog.get('.dialog-note').text()).toContain('样本')
    expect(dialog.get('tbody a').attributes('href')).toBe('/opportunities/opp')
    expect(dialog.get('tbody').text()).not.toContain('po_received')
    await dialog.findAll('.dialog-pagination button')[1].trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'reached_po_received', sales: 'alice', page: 2 }))
    wrapper.unmount()
  })

  it('renders four activities and seven stages with the API annual scope and target state', async () => {
    const { wrapper } = await setup()
    expect(wrapper.findAll('.activity-grid article')).toHaveLength(4)
    expect(wrapper.findAll('.stage-row')).toHaveLength(7)
    expect(wrapper.get('.heading-order').text()).toContain('9,500,000 / 不适用')
    expect(wrapper.get('.target-button').text()).toBe('设置目标')
    expect(wrapper.get('.pipeline-panel').text()).not.toContain('S1–S6')
    expect(wrapper.find('.chart-target-button').exists()).toBe(false)
    expect(wrapper.get('.chart-owner').text()).toBe('全部地域')
    expect(wrapper.find('.orders-panel select').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('团队目标')
    expect(wrapper.text()).not.toContain('转化率')
    expect(wrapper.find('select[aria-label="Region"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.target-button').attributes('disabled')).toBeUndefined()
    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Week 37')
    wrapper.unmount()
  })
  it.each(['Sales', 'Engineer'] as UserRole[])('does not fetch review for %s', async role => {
    const { wrapper, api, router } = await setup(role)
    expect(api.getReview).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="review-page"]').exists()).toBe(false)
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/calendar'))
    wrapper.unmount()
  })
  it('keeps filtering and drilldowns on the business API', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    expect(api.getReview).toHaveBeenLastCalledWith(expect.objectContaining({ sales: 'alice' }))
    expect(wrapper.get('.chart-owner').text()).toBe('Alice')
    await wrapper.findAll('.activity-label')[0].trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenCalledWith(expect.objectContaining({ sales: 'alice', metric: 'visits', pageSize: 20 }))
    expect(wrapper.get('.detail-dialog').attributes('open')).toBeDefined()
    wrapper.unmount()
  })
  it('shows the PR36 downgrade reason through the cockpit business API', async () => {
    const { wrapper, api } = await setup()
    api.getReviewDetails = vi.fn(async () => ({
      data: { items: [{ id: 'opp', title: 'Opportunity', accountId: 'c', customer: 'Customer', owner: 'alice',
        at: '2026-09-08T00:00:00Z', kind: 'opportunity' as const, fromLevel: 'committed', toLevel: 'upside',
        reason: 'Customer budget reduced', eventId: 'downgrade-1' }], page: 1, pageSize: 20, total: 1, asOf: '' },
      warnings: [], meta: { requestId: 'pr36-reason', generatedAt: '' },
    }))
    await wrapper.findAll('.warning-strip button')[2].trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenCalledWith(expect.objectContaining({ metric: 'downgrade' }))
    expect(wrapper.get('.detail-dialog tbody').text()).toContain('Customer budget reduced')
    wrapper.unmount()
  })
  it('shows current plans and owners, retains handled history, and links to the exact event', async () => {
    const { wrapper, api } = await setup()
    api.getReviewDetails = vi.fn(async () => ({
      data: { items: [{ id: 'opp', title: 'Opportunity', accountId: 'c', customer: 'Customer', owner: 'alice', currentOwner: 'bob',
        at: '2026-09-08T00:00:00Z', kind: 'opportunity' as const, fromLevel: 'committed', toLevel: 'upside',
        reason: 'Budget reduced', eventId: 'downgrade-1', recovery: { state: 'handled' as const, plan: 'Meet procurement',
          actionTaken: 'Met buyer and agreed new schedule', actedBy: 'bob', actedAt: '2026-09-16T00:00:00Z' } }], page: 1, pageSize: 20, total: 1, asOf: '' },
      warnings: [], meta: { requestId: 'recovery-history' },
    }))
    await wrapper.get('[data-downgrade-history]').trigger('click'); await flushPromises()
    expect(api.getReviewDetails).toHaveBeenCalledWith(expect.objectContaining({ metric: 'downgrade_history' }))
    const dialog = wrapper.get('.detail-dialog')
    expect(dialog.text()).toContain('Meet procurement')
    expect(dialog.text()).toContain('当前负责人 · Bob')
    expect(dialog.text()).toContain('Met buyer and agreed new schedule')
    expect(dialog.text()).toContain('已记录行动 · 提醒已清除')
    expect(dialog.get('a').attributes('href')).toBe('/opportunities/opp?probabilityEvent=downgrade-1')
    expect(dialog.get('.dialog-note').text()).toContain('修改计划不会清除')
    setLocale('en-US'); await flushPromises()
    expect(dialog.text()).toContain('Action recorded · warning cleared')
    wrapper.unmount()
  })
  it('discards a response after Manager permission is revoked', async () => {
    const { wrapper, api, app } = await setup()
    let resolve: ((value: Awaited<ReturnType<typeof api.getReview>>) => void) | undefined
    api.getReview = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getReview>>>(r => { resolve = r }))
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    app.bootstrap!.user.role = 'Sales'; await flushPromises()
    resolve!({ data: reviewFixture(), warnings: [], meta: { requestId: 'late', generatedAt: '' } }); await flushPromises()
    expect(wrapper.find('[data-testid="review-page"]').exists()).toBe(false)
    wrapper.unmount()
  })

  // An error that carries no text still has to leave a message to read, and the tab stays a link either way.
  it.each([
    ['a network error', new Error('network down'), 'network down'],
    ['a service error without any message', new CrmApiError('INTERNAL_ERROR', '', 'req_empty'), '数据请求失败，请稍后重试。'],
    ['an error whose message is only blanks', new CrmApiError('INTERNAL_ERROR', '  ', 'req_blank'), '数据请求失败，请稍后重试。'],
  ])('keeps the Warnings tab reachable after the first load fails with %s', async (_name, failure, text) => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getReview = vi.fn().mockRejectedValue(failure)
    const router = createAppRouter()
    await router.push('/dashboard'); await router.isReady()
    const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.get('.review-state.error').text()).toContain(text)
    // No anchor: Warnings opens the week on its own default date, the current week.
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week')
    expect(wrapper.find('span.is-disabled').exists()).toBe(false)
    wrapper.unmount()
  })

  it('disables the Warnings tab again while a retry loads, then hands over the loaded period', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    let release = () => {}
    api.getReview = vi.fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockImplementationOnce(() => new Promise<Awaited<ReturnType<typeof api.getReview>>>(resolve => { release = () => resolve({ data: reviewFixture(), warnings: [], meta: { requestId: 'retry', generatedAt: '' } }) }))
    const router = createAppRouter()
    await router.push('/dashboard'); await router.isReady()
    const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week')
    await wrapper.get('.review-state.error button').trigger('click'); await flushPromises()
    expect(api.getReview).toHaveBeenCalledTimes(2)
    expect(wrapper.find('a[href^="/warnings"]').exists()).toBe(false)
    expect(wrapper.find('span.is-disabled').exists()).toBe(true)
    release(); await flushPromises()
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week&anchor=2026-09-07')
    wrapper.unmount()
  })
})

describe('Approved Review integration', () => {
  it('lists the region filter as the territory tree and sends the territory that is chosen', async () => {
    const { wrapper, api } = await setup()
    api.getReview = vi.fn(async () => {
      const data = reviewFixture()
      data.filters = { ...data.filters, regions: ['World', 'Asia', 'China', 'East China', 'Taiwan'], regionParents: { Asia: 'World', China: 'Asia', 'East China': 'China' }, regionReady: true }
      return { data, warnings: [], meta: { requestId: 'territories', generatedAt: '' } }
    })
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    const select = wrapper.get('select[aria-label="Region"]')
    // A territory before the ones below it, each level indented; a region outside the tree is flat.
    expect(select.findAll('option').slice(1).map(option => option.element.textContent)).toEqual(['全球', '\u00a0\u00a0亚洲', '\u00a0\u00a0\u00a0\u00a0中国', '\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0华东', 'Taiwan'])
    await select.setValue('China'); await flushPromises()
    expect(api.getReview).toHaveBeenLastCalledWith(expect.objectContaining({ region: 'China' }))
    wrapper.unmount()
  })

  it('labels preset regions in Chinese, keeps custom regions as stored and preserves API filter scope for the individual chart', async () => {
    const { wrapper, api } = await setup()
    setLocale('en-US'); await flushPromises()
    api.getReview = vi.fn(async q => {
      const data = reviewFixture()
      data.filters.regions = ['East China', 'Taiwan']; data.filters.regionReady = true
      return { data, warnings: [], meta: { requestId: 'regions', generatedAt: '' } }
    })
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    setLocale('zh-CN'); await flushPromises()
    const regionText = wrapper.get('select[aria-label="Region"]').text()
    expect(regionText).toContain('华东')
    expect(regionText).toContain('Taiwan')
    expect(regionText).not.toContain('East China')
    await wrapper.get('select[aria-label="Region"]').setValue('East China'); await flushPromises()
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    expect(api.getReview).toHaveBeenLastCalledWith(expect.objectContaining({ sales: 'alice', region: 'East China', market: 'Frontend' }))
    expect(wrapper.get('.target-button').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('.plan-line').exists()).toBe(false)
    expect(wrapper.find('.actual-line').exists()).toBe(true)
    expect(wrapper.get('.chart-caption').text()).toContain('目标未分配到当前销售、地域、市场或设备的组合范围')
    wrapper.unmount()
  })

  it('saves an individual target with its version and refreshes the chart', async () => {
    const { wrapper, api } = await setup()
    let amount = '40000000'
    const record = { id: 'target-1', modified: 'version-1', sales: 'alice', metric: 'orders' as const, period: 'year' as const, anchor: '2026-01-01', value: amount }
    api.getReviewTarget = vi.fn(async query => ({ data: query.metric === 'orders' ? record : null, warnings: [], meta: { requestId: 'target-test' } }))
    api.getReview = vi.fn(async () => {
      const data = reviewFixture()
      data.targets = [{ ...record, value: amount }]
      data.orders.target = { value: amount, state: 'ready', record: data.targets[0] }
      return { data, warnings: [], meta: { requestId: 'target', generatedAt: '' } }
    })
    api.saveReviewTarget = vi.fn(async input => {
      amount = input.value
      return { data: { ...record, ...input, modified: 'version-2' }, warnings: [], meta: { requestId: 'saved', generatedAt: '' } }
    })
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    expect(wrapper.find('.plan-line').exists()).toBe(true)
    expect(wrapper.get('.heading-order').text()).toContain('达成率 23.8%')
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="target-metric"]').setValue('orders'); await flushPromises()
    await wrapper.get('.target-dialog input[type="number"]').setValue('45000000')
    await wrapper.get('.target-dialog form').trigger('submit'); await flushPromises()
    expect(api.saveReviewTarget).toHaveBeenCalledWith({ sales: 'alice', scope: 'sales', territory: '', metric: 'orders', period: 'year', anchor: '2026-01-01', value: '45000000' }, 'version-1')
    expect(wrapper.get('.target-dialog').text()).toContain('目标已保存')
    expect(wrapper.get('.heading-order').text()).toContain('45,000,000')
    wrapper.unmount()
  })

  it('shows the CNY order amount of each rep with the PO count and never treats missing estimates as zero', async () => {
    const { wrapper, api } = await setup()
    const rows = wrapper.findAll('.sales-panel tbody tr')
    expect(rows[0].get('.rep-orders').text()).toBe('¥4M4 单')
    expect(rows[1].get('.rep-orders').text()).toBe('¥5.5M3 单')
    // A rep with an order that still lacks its CNY amount shows the gap, not a partial sum.
    const review = reviewFixture()
    review.sales[0].orders = { state: 'insufficient', value: null, reason: 'cny_amount_unavailable' }
    api.getReview = vi.fn(async () => ({ data: review, warnings: [], meta: { requestId: 'rep-orders', generatedAt: '' } }))
    await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
    expect(wrapper.findAll('.sales-panel tbody tr')[0].get('.rep-orders').text()).toBe('数据不足4 单')
    // Without PO coverage the cell says so once, not once per line.
    review.sales[0].poCount = { state: 'insufficient', value: null }
    api.getReview = vi.fn(async () => ({ data: review, warnings: [], meta: { requestId: 'rep-orders-2', generatedAt: '' } }))
    await wrapper.get('input[type="date"]').setValue('2026-09-07'); await flushPromises()
    expect(wrapper.findAll('.sales-panel tbody tr')[0].get('.rep-orders').text()).toBe('数据不足')
    expect(wrapper.get('.loss-value').text()).toBe('数据不足')
    expect(wrapper.get('.stalled-panel tbody').text()).toContain('36')
    expect(wrapper.find('.app-sidebar').exists()).toBe(false)
    wrapper.unmount()
  })

  it('preserves an edit after a target conflict instead of reporting success', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    api.saveReviewTarget = vi.fn(async () => { throw new Error('Target changed; reload before saving') })
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    await wrapper.get('.target-dialog input[type="number"]').setValue('9')
    await wrapper.get('.target-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.get('.target-dialog [role="alert"]').text()).toContain('Target changed')
    expect(wrapper.find('.target-dialog [role="status"]').exists()).toBe(false)
    expect((wrapper.get('.target-dialog input[type="number"]').element as HTMLInputElement).value).toBe('9')
    wrapper.unmount()
  })

  it('loads an arbitrary default target outside Review and retains the saved CAS after Review refresh', async () => {
    const { wrapper, api } = await setup()
    const record = { id: 'future-default', modified: 'default-v1', sales: 'alice', scope: 'sales' as const, territory: '',
      metric: 'visits' as const, period: 'weekly_default' as const, anchor: '2030-08-26', value: '6' }
    api.getReviewTarget = vi.fn(async query => ({ data: query.anchor === record.anchor ? record : null, warnings: [], meta: { requestId: 'target' } }))
    api.saveReviewTarget = vi.fn(async input => ({ data: { ...record, ...input, modified: 'default-v2' }, warnings: [], meta: { requestId: 'saved' } }))
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="target-period"]').setValue('weekly_default'); await flushPromises()
    await wrapper.get('.target-dialog input[type="date"]').setValue(record.anchor); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('.target-dialog input[type="number"]').element.value).toBe('6')
    await wrapper.get('.target-dialog input[type="number"]').setValue('8')
    await wrapper.get('.target-dialog form').trigger('submit'); await flushPromises()
    expect(api.saveReviewTarget).toHaveBeenLastCalledWith({ sales: 'alice', scope: 'sales', territory: '', metric: 'visits',
      period: 'weekly_default', anchor: record.anchor, value: '8' }, 'default-v1')
    await wrapper.get('.target-dialog input[type="number"]').setValue('9')
    await wrapper.get('.target-dialog form').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.saveReviewTarget).mock.calls[1][1]).toBe('default-v2')
    expect(api.getReviewTarget).toHaveBeenLastCalledWith({ sales: 'alice', scope: 'sales', territory: '', metric: 'visits', period: 'weekly_default', anchor: record.anchor })
    wrapper.unmount()
  })

  it('ignores earlier target responses and blocks saving until the selected key is loaded', async () => {
    const { wrapper, api } = await setup()
    const pending: Array<(value: Awaited<ReturnType<typeof api.getReviewTarget>>) => void> = []
    api.getReviewTarget = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getReviewTarget>>>(resolve => pending.push(resolve)))
    api.saveReviewTarget = vi.fn()
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    await wrapper.get('.target-dialog input[type="date"]').setValue('2030-09-02'); await flushPromises()
    expect(pending).toHaveLength(2)
    await wrapper.get('.target-dialog form').trigger('submit')
    expect(api.saveReviewTarget).not.toHaveBeenCalled()
    const response = (value: string) => ({ data: { id: value, modified: value, sales: 'alice', metric: 'visits' as const, period: 'week' as const, anchor: '2030-09-02', value }, warnings: [], meta: { requestId: value } })
    pending[1](response('7')); await flushPromises()
    pending[0](response('3')); await flushPromises()
    expect(wrapper.get<HTMLInputElement>('.target-dialog input[type="number"]').element.value).toBe('7')
    expect(wrapper.get('.save-target').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps failed lookup distinct from an unset target and recovers through retry', async () => {
    const { wrapper, api } = await setup()
    api.getReviewTarget = vi.fn().mockRejectedValueOnce(new Error('Read failed')).mockResolvedValue({ data: null, warnings: [], meta: { requestId: 'retry' } })
    api.saveReviewTarget = vi.fn()
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    expect(wrapper.get('.target-dialog [role="alert"]').text()).toContain('Read failed')
    expect(wrapper.get('.save-target').attributes('disabled')).toBeDefined()
    await wrapper.get('.target-dialog form').trigger('submit'); await flushPromises()
    expect(api.saveReviewTarget).not.toHaveBeenCalled()
    await wrapper.get('[data-target-retry]').trigger('click'); await flushPromises()
    expect(wrapper.get('.save-target').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('.target-dialog [role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('invalidates a lookup on close and after the manager identity changes', async () => {
    const { wrapper, api, app } = await setup()
    const pending: Array<(value: Awaited<ReturnType<typeof api.getReviewTarget>>) => void> = []
    api.getReviewTarget = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getReviewTarget>>>(resolve => pending.push(resolve)))
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    await wrapper.get('.target-dialog header button').trigger('click')
    await wrapper.get('.target-button').trigger('click'); await flushPromises()
    pending[0]({ data: null, warnings: [], meta: { requestId: 'closed' } }); await flushPromises()
    expect(wrapper.get('.save-target').attributes('disabled')).toBeDefined()
    app.identityRevision++
    await flushPromises()
    pending[1]({ data: null, warnings: [], meta: { requestId: 'old-identity' } }); await flushPromises()
    expect(wrapper.get('.target-dialog').attributes('open')).toBeUndefined()
    expect(wrapper.get('.save-target').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})

it('paginates the selected warning using the current business filter scope', async () => {
  const { wrapper, api } = await setup()
  api.getReviewDetails = vi.fn(async q => ({ data: { items: [], page: q.page ?? 1, pageSize: 20, total: 41, asOf: '' }, warnings: [], meta: { requestId: 'page', generatedAt: '' } }))
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  await wrapper.findAll('.warning-strip button')[1].trigger('click'); await flushPromises()
  await wrapper.findAll('.dialog-pagination button')[1].trigger('click'); await flushPromises()
  expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'overdue', sales: 'alice', page: 2, pageSize: 20 }))
  wrapper.unmount()
})

it('opens scoped PO backfill details and links to the booking', async () => {
  const { wrapper, api } = await setup()
  api.getReviewDetails = vi.fn(async () => ({
    data: { items: [{ id: 'BKG-1', title: 'BKG-1', accountId: 'c', customer: 'Customer', owner: 'alice',
      at: null, kind: 'booking' as const, status: 'Confirmed' }], page: 1, pageSize: 20, total: 1, asOf: '' },
    warnings: [], meta: { requestId: 'backfill', generatedAt: '' },
  }))
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  expect(wrapper.get('.po-missing').text()).toContain('PO 日期待补录 · 2')
  await wrapper.get('.po-missing button').trigger('click'); await flushPromises()
  expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'po_missing_date', sales: 'alice' }))
  expect(wrapper.get('.detail-dialog').text()).toContain('不推测所属年份')
  expect(wrapper.get('.detail-dialog tbody').text()).toContain('待补录')
  expect(wrapper.get('.detail-dialog tbody a').attributes('href')).toContain('/booking/BKG-1')
  wrapper.unmount()
})

it('shows actual PO dates in Shanghai and labels the current-state total', async () => {
  const { wrapper, api } = await setup()
  api.getReviewDetails = vi.fn(async () => ({
    data: { items: [{ id: 'BKG-2', title: 'BKG-2', accountId: 'c', customer: 'Customer', owner: 'alice',
      at: '2025-12-31T16:00:00Z', kind: 'booking' as const, status: 'Completed' }], page: 1, pageSize: 20, total: 1, asOf: '' },
    warnings: [], meta: { requestId: 'actual-date', generatedAt: '' },
  }))
  await wrapper.get('.po-stage').trigger('click'); await flushPromises()
  expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'po' }))
  expect(wrapper.get('.detail-dialog thead').text()).toContain('实际 PO 日期')
  expect(wrapper.get('.detail-dialog tbody').text()).toContain('2026/1/1')
  expect(wrapper.get('.detail-dialog tbody').text()).toContain('已完成')
  expect(wrapper.get('.detail-dialog').text()).toContain('归属当前商机负责人')
  expect(wrapper.get('.detail-dialog tbody').text()).toContain('人民币金额待补录')
  wrapper.unmount()
})

it('does not present unavailable backfill counts as zero', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.orders.missingDate = { value: null, state: 'insufficient' }
    return { data, warnings: [], meta: { requestId: 'old-schema', generatedAt: '' } }
  })
  await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
  expect(wrapper.get('.po-missing').text()).toContain('数据不足')
  expect(wrapper.get('.po-missing button').attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

it('shows the CNY aggregate in millions and the same CNY amount in stage details', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.pipeline[1].amount = { value: '6000000.60', state: 'ready' }
    data.sales[0].pipeline = { value: '6000000.60', state: 'ready' }
    return { data, warnings: [], meta: { requestId: 'cny', generatedAt: '' } }
  })
  api.getReviewDetails = vi.fn(async () => ({
    data: { items: [{ id: 'opp-cny', title: 'USD-priced opportunity', accountId: 'c', customer: 'Customer',
      owner: 'alice', at: '2026-09-13T15:59:59Z', kind: 'opportunity' as const, stage: 'demo_done',
      amount: '6000000.60', currency: 'CNY' }], page: 1, pageSize: 20, total: 1, asOf: '' },
    warnings: [], meta: { requestId: 'cny-details', generatedAt: '' },
  }))
  await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
  expect(wrapper.findAll('.stage-row')[1].text()).toContain('¥6M')
  expect(wrapper.findAll('.sales-panel tbody tr')[0].text()).toContain('¥6M')
  await wrapper.findAll('.stage-row')[1].trigger('click'); await flushPromises()
  expect(wrapper.get('.detail-dialog tbody').text()).toContain('CNY 6,000,000.6')
  wrapper.unmount()
})

it('shows the S7 YTD CNY amount, the actual cumulative curve and attainment from bookings', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.targets = [{ id: 'target-1', modified: 'v1', sales: 'alice', metric: 'orders', period: 'year', anchor: '2026-01-01', value: '20000000' }]
    data.orders.target = { value: '20000000', state: 'ready', record: data.targets[0] }
    data.orders.planned = { value: '14000000', state: 'ready' }
    return { data, warnings: [], meta: { requestId: 'orders', generatedAt: '' } }
  })
  api.getReviewDetails = vi.fn(async () => ({
    data: { items: [{ id: 'BKG-3', title: 'BKG-3', accountId: 'c', customer: 'Customer', owner: 'alice',
      at: '2026-03-04T16:00:00Z', kind: 'booking' as const, status: 'Confirmed', amount: '5000.25', currency: 'CNY' }], page: 1, pageSize: 20, total: 1, asOf: '' },
    warnings: [], meta: { requestId: 'po-amount', generatedAt: '' },
  }))
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  expect(wrapper.findAll('.stage-row')[6].text()).toContain('¥9.5M')
  expect(wrapper.get('.actual-line').attributes('d')).toBe(monotoneCurvePath([{ x: 45, y: 190 },
    { x: 45 + .18 * 440, y: 190 - 4 / 20 * 160 }, { x: 45 + .64 * 440, y: 190 - 9.5 / 20 * 160 }, { x: 45 + .7 * 440, y: 190 - 9.5 / 20 * 160 }]))
  expect(wrapper.get('.plan-line').attributes('d')).toBe('M45 190L485 30.0')
  expect(wrapper.get('.heading-order').text()).toContain('¥9,500,000 / ¥20,000,000')
  expect(wrapper.get('.heading-order').text()).toContain('达成率 47.5% · 较计划 −¥4.5M')
  expect(wrapper.get('.chart-caption').text()).toBe('')
  await wrapper.get('.po-stage').trigger('click'); await flushPromises()
  expect(wrapper.get('.detail-dialog tbody').text()).toContain('CNY 5,000.25')
  wrapper.unmount()
})

it('draws the actual curve without a target and says the target is not set', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.orders.target = { value: null, state: 'not_set', record: null }
    data.orders.planned = { value: null, state: 'not_set' }
    return { data, warnings: [], meta: { requestId: 'no-target', generatedAt: '' } }
  })
  await wrapper.get('select[aria-label="Sales"]').setValue('bob'); await flushPromises()
  expect(wrapper.find('.plan-line').exists()).toBe(false)
  expect(wrapper.get('.actual-line').attributes('d')).toBe(monotoneCurvePath([{ x: 45, y: 190 },
    { x: 45 + .18 * 440, y: 190 - 4 / 9.5 * 160 }, { x: 45 + .64 * 440, y: 30 }, { x: 45 + .7 * 440, y: 30 }]))
  expect(wrapper.get('.chart-caption').text()).toBe('')
  expect(wrapper.get('.chart-summary').text()).toBe('年度目标：未设置')
  expect(wrapper.get('.heading-order').text()).toContain('¥9,500,000 / 未设置')
  expect(wrapper.get('.heading-order').text()).toContain('年度目标：未设置')
  wrapper.unmount()
})

it('lists bookings without a CNY amount instead of counting them as zero', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.orders.actual = { value: null, state: 'insufficient', reason: 'booking_cny_amount_missing' }
    data.orders.series = []
    data.orders.missingAmount = { value: 3, state: 'ready' }
    data.pipeline[6].amount = { value: null, state: 'insufficient', reason: 'booking_cny_amount_missing' }
    return { data, warnings: [], meta: { requestId: 'missing-amount', generatedAt: '' } }
  })
  api.getReviewDetails = vi.fn(async () => ({
    data: { items: [{ id: 'BKG-9', title: 'BKG-9', accountId: 'c', customer: 'Customer', owner: 'alice',
      at: '2026-03-01T16:00:00Z', kind: 'booking' as const, status: 'Confirmed', amount: null, currency: 'CNY' }], page: 1, pageSize: 20, total: 1, asOf: '' },
    warnings: [], meta: { requestId: 'missing-amount-details', generatedAt: '' },
  }))
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  expect(wrapper.findAll('.stage-row')[6].text()).toContain('数据不足')
  expect(wrapper.find('.actual-line').exists()).toBe(false)
  expect(wrapper.get('.heading-order').text()).toContain('实际金额：数据不足（3 张订单缺人民币金额）')
  expect(wrapper.get('.chart-summary').text()).toBe('实际金额：数据不足（3 张订单缺人民币金额）')
  expect(wrapper.get('.po-missing').text()).toContain('人民币金额待补录 · 3')
  await wrapper.findAll('.po-missing button')[1].trigger('click'); await flushPromises()
  expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'po_missing_amount', sales: 'alice' }))
  expect(wrapper.get('.detail-dialog').text()).toContain('经理补录前')
  expect(wrapper.get('.detail-dialog tbody').text()).toContain('人民币金额待补录')
  expect(wrapper.get('.detail-dialog tbody a').attributes('href')).toContain('/booking/BKG-9')
  wrapper.unmount()
})

it('renders no NaN when an older backend omits the series, the missing count and the elapsed fraction', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    delete data.orders.series; delete data.orders.missingAmount
    ;(data.orders as { elapsedFraction?: number }).elapsedFraction = undefined
    return { data, warnings: [], meta: { requestId: 'old-backend', generatedAt: '' } }
  })
  await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  expect(wrapper.findAll('path').map(p => p.attributes('d')).join(' ')).not.toContain('NaN')
  expect(wrapper.get('.actual-line').attributes('d')).toBe('M45.0 190.0')
  expect(wrapper.findAll('.po-missing button')[1].attributes('disabled')).toBeDefined()
  wrapper.unmount()
})

it('draws a flat zero line for a year without orders', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.orders.actual = { value: '0.00', state: 'ready' }; data.orders.series = []
    data.orders.target = { value: null, state: 'not_set', record: null }; data.orders.planned = { value: null, state: 'not_set' }
    return { data, warnings: [], meta: { requestId: 'zero', generatedAt: '' } }
  })
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  expect(wrapper.get('.actual-line').attributes('d')).toBe('M45.0 190.0L353.0 190.0')
  expect(wrapper.get('.heading-order').text()).toContain('¥0 / 未设置')
  wrapper.unmount()
})

it('swaps the primary stage value with the count/amount toggle, including missing amounts and S1', async () => {
  const { wrapper, api } = await setup()
  const stages = () => wrapper.findAll('.stage-value')
  expect(stages()[1].get('strong').text().replace(/\s/g, '')).toBe('10个')
  await wrapper.findAll('.pipeline-panel .segmented button')[1].trigger('click')
  expect(stages()[1].get('strong').text()).toBe('¥24M')
  expect(stages()[1].get('small').text().replace(/\s/g, '')).toBe('10个')
  expect(stages()[0].get('strong').text()).toBe('仅计数量')
  expect(stages()[0].get('small').text().replace(/\s/g, '')).toBe('14个')
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.pipeline[1].amount = { value: null, state: 'insufficient' }
    return { data, warnings: [], meta: { requestId: 'missing-stage', generatedAt: '' } }
  })
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  expect(stages()[1].get('strong').text()).toBe('数据不足')
  expect(stages()[1].get('strong').classes()).toContain('unavailable')
  await wrapper.findAll('.pipeline-panel .segmented button')[0].trigger('click')
  expect(stages()[1].get('strong').text().replace(/\s/g, '')).toBe('10个')
  expect(stages()[1].get('small').text()).toBe('数据不足')
  wrapper.unmount()
})

it('shows the hovered curve amount and clears it on leave or a filter change', async () => {
  const { wrapper } = await setup()
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  expect(wrapper.find('.actual-node').exists()).toBe(false)
  expect(wrapper.find('[role="tooltip"]').exists()).toBe(false)
  const hit = wrapper.get('.actual-hit')
  const svg = wrapper.get('.chart-frame svg').element as SVGSVGElement
  Object.defineProperty(svg, 'createSVGPoint', { value: () => ({ x: 0, y: 0, matrixTransform() { return { x: this.x, y: this.y } } }) })
  Object.defineProperties(hit.element, {
    getScreenCTM: { value: () => ({ inverse: () => ({}) }) },
    getTotalLength: { value: () => 440 },
    getPointAtLength: { value: (length: number) => ({ x: 45 + length, y: 190 - length / 440 * 160 }) },
  })
  hit.element.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 265, clientY: 110 })); await flushPromises()
  expect(wrapper.get('[role="tooltip"]').text()).toContain('实际曲线')
  expect(wrapper.get('.hover-month').text()).toContain('2026年7月')
  setLocale('en-US'); await flushPromises()
  expect(wrapper.get('.hover-month').text()).toContain('Jul 2026')
  hit.element.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 45, clientY: 190 })); await flushPromises()
  expect(wrapper.get('.hover-month').text()).toContain('Jan 2026')
  hit.element.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 485, clientY: 30 })); await flushPromises()
  expect(wrapper.get('.hover-month').text()).toContain('Dec 2026')
  hit.element.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 265, clientY: 110 })); await flushPromises()
  const amount = Number(wrapper.get('.hover-amount').text().replace(/[^\d.]/g, ''))
  expect(Math.abs(amount - 4750000)).toBeLessThan(50)
  await hit.trigger('pointerleave')
  expect(wrapper.find('[role="tooltip"]').exists()).toBe(false)
  hit.element.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 265, clientY: 110 })); await flushPromises()
  await wrapper.get('select[aria-label="Sales"]').setValue('bob'); await flushPromises()
  expect(wrapper.find('[role="tooltip"]').exists()).toBe(false)
  wrapper.unmount()
})

it('filters by equipment, keeps targets per person and reports activity without an opportunity', async () => {
  const { wrapper, api } = await setup()
  const data = reviewFixture()
  data.filters.equipment = ['Aconca', 'Kibo']
  data.activities = data.activities.map(item => item.key === 'visits' ? { ...item, unclassified: 2 } : item)
  api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 'equipment' } }))
  await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
  await wrapper.get('select[aria-label="Equipment"]').setValue('Kibo'); await flushPromises()
  expect(api.getReview).toHaveBeenLastCalledWith(expect.objectContaining({ sales: 'alice', equipment: 'Kibo' }))
  expect(wrapper.get('.target-button').attributes('disabled')).toBeUndefined()
  expect(wrapper.get('[data-unclassified]').text()).toContain('2 条未关联商机，未计入')
  expect(wrapper.get('.chart-caption').text()).toContain('设备')
  wrapper.unmount()
})

it('shows an insufficient warning count in the strip as a dash, with the full text as the tooltip', async () => {
  const { wrapper, api } = await setup()
  api.getReview = vi.fn(async () => {
    const data = reviewFixture()
    data.warnings[0] = { key: 'lost', count: { value: null, state: 'insufficient' } }
    return { data, warnings: [], meta: { requestId: 'strip', generatedAt: '' } }
  })
  await wrapper.get('input[type="date"]').setValue('2026-09-14'); await flushPromises()
  const [lost, overdue] = wrapper.findAll('.warning-links button')
  expect(lost.text()).toContain('—')
  expect(lost.text()).not.toContain('数据不足')
  expect(lost.attributes('title')).toContain('数据不足')
  expect(lost.attributes('aria-label')).toContain('数据不足')
  expect(overdue.attributes('title')).toBeUndefined()
  wrapper.unmount()
})

it('opens stage 6 deals without a PO from the warning strip with their days in the stage', async () => {
  const { wrapper, api } = await setup()
  const data = reviewFixture()
  data.warnings.push({ key: 'stage6_no_po', count: { state: 'ready', value: 1 } })
  data.stage6NoPo = { thresholdDays: 45 }
  api.getReview = vi.fn(async () => ({ data, warnings: [], meta: { requestId: 's6' } }))
  api.getReviewDetails = vi.fn(async q => ({ data: { items: [{ id: 'opp-s6', title: 'Line validation', accountId: 'customer', customer: 'Customer', owner: 'bob',
    at: null, kind: 'opportunity' as const, stage: 'internal_validation', amount: '18490000', currency: 'CNY', daysInStage: 42, daysAtLeast: true, enteredAt: null }],
    page: q.page ?? 1, pageSize: 20, total: 1, asOf: '' }, warnings: [], meta: { requestId: 's6-details' } }))
  await wrapper.get('select[aria-label="Sales"]').setValue('bob'); await flushPromises()
  const button = wrapper.findAll('.warning-strip button').find(b => b.text().includes('第 6 阶段超期无 PO'))!
  expect(button.text()).toContain('1')
  await button.trigger('click'); await flushPromises()
  expect(api.getReviewDetails).toHaveBeenLastCalledWith(expect.objectContaining({ metric: 'stage6_no_po', sales: 'bob' }))
  const dialog = wrapper.get('.detail-dialog')
  expect(dialog.get('.dialog-note').text()).toContain('至少 45 天')
  expect(dialog.get('tbody').text()).toContain('≥42 天在第 6 阶段未收到 PO')
  expect(dialog.get('tbody').text()).not.toContain('天未更新')
  wrapper.unmount()
})
