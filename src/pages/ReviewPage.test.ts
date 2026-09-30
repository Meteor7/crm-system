import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import { reviewFixture } from '@/features/cockpit/review.fixture'
import { monotoneCurvePath } from '@/features/cockpit/presentation'
import { setLocale } from '@/i18n'
import type { UserRole } from '@/types/crm'
import ReviewPage from './ReviewPage.vue'

beforeEach(() => {
  setLocale('zh-CN')
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
async function setup(role: UserRole = 'Manager') {
  const api = createMockApi({ role, latency: 0 })
  api.getReview = vi.fn(async () => ({ data: reviewFixture(), warnings: [], meta: { requestId: 'review-test', generatedAt: '' } }))
  api.getReviewDetails = vi.fn(async () => ({ data: { items: [], page: 1, pageSize: 20, total: 0, asOf: '' }, warnings: [], meta: { requestId: 'detail-test', generatedAt: '' } }))
  const pinia = createPinia()
  const router = createAppRouter()
  await router.push('/dashboard'); await router.isReady()
  const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, api, router, app: useAppStore(pinia) }
}
describe('Manager Review', () => {
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

  it('renders four activities and seven stages, with no team target or fabricated orders', async () => {
    const { wrapper } = await setup()
    expect(wrapper.findAll('.activity-grid article')).toHaveLength(4)
    expect(wrapper.findAll('.stage-row')).toHaveLength(7)
    expect(wrapper.get('.heading-order').text()).toContain('— / —')
    expect(wrapper.get('.target-button').text()).toBe('设置个人目标')
    expect(wrapper.get('.pipeline-panel').text()).not.toContain('S1–S6')
    expect(wrapper.find('.chart-target-button').exists()).toBe(false)
    expect(wrapper.get('.chart-owner').text()).toBe('未筛选销售')
    expect(wrapper.find('.orders-panel select').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('团队目标')
    expect(wrapper.text()).not.toContain('转化率')
    expect(wrapper.find('select[aria-label="Region"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.target-button').attributes('disabled')).toBeDefined()
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

  it('keeps the Warnings tab reachable after the first load fails', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getReview = vi.fn().mockRejectedValue(new Error('network down'))
    const router = createAppRouter()
    await router.push('/dashboard'); await router.isReady()
    const wrapper = mount(ReviewPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.find('.review-state.error').exists()).toBe(true)
    // No anchor: Warnings opens on its own default period (the current week).
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe('/warnings?period=week')
    expect(wrapper.find('span.is-disabled').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('Approved Review integration', () => {
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
    expect(wrapper.get('.target-button').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.plan-line').exists()).toBe(false)
    expect(wrapper.find('.actual-line').exists()).toBe(true)
    expect(wrapper.get('.chart-caption').text()).toContain('不按区域、市场或设备拆分')
    wrapper.unmount()
  })

  it('saves an individual target with its version and refreshes the chart', async () => {
    const { wrapper, api } = await setup()
    let amount = '40000000'
    const record = { id: 'target-1', modified: 'version-1', sales: 'alice', metric: 'orders' as const, period: 'year' as const, anchor: '2026-01-01', value: amount }
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
    await wrapper.get('.target-dialog select').setValue('orders'); await flushPromises()
    await wrapper.get('.target-dialog input[type="number"]').setValue('45000000')
    await wrapper.get('.target-dialog form').trigger('submit'); await flushPromises()
    expect(api.saveReviewTarget).toHaveBeenCalledWith({ sales: 'alice', metric: 'orders', period: 'year', anchor: '2026-01-01', value: '45000000' }, 'version-1')
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
  expect(wrapper.get('.target-button').attributes('disabled')).toBeDefined()
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
