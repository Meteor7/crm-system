import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api/contracts'
import { createAppRouter } from '@/app/router'
import { warningsFixture } from '@/features/cockpit/warnings.fixture'
import type { WarningHandling, WarningHandlingType } from '@/features/cockpit/types'
import { setLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'
import WarningsPage from './WarningsPage.vue'

beforeEach(() => {
  setLocale('zh-CN')
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
const meta = { requestId: 'warnings-test', generatedAt: '' }
// Shanghai calendar days from today, as the follow-up date bounds are set.
const shanghaiDay = (offset: number) => new Date(Date.parse(`${new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' })}T00:00:00Z`) + offset * 86400000).toISOString().slice(0, 10)
// What the backend returns after a save: the row's handling with the new values and version.
const savedHandling = (source: { warningType: WarningHandlingType; sourceId: string; sourceEvent: string }, extra: Partial<WarningHandling> = {}): WarningHandling => ({
  id: 'saved-handling', modified: '2026-09-24T09:00:00.000000Z', state: 'open', nextStep: null, planBy: 'manager', planAt: '2026-09-24T09:00:00Z',
  actionTaken: null, actedBy: null, actedAt: null, followUpOn: null, history: [], ...source, ...extra,
})
// attach: mount into the document, for focus checks.
async function setup(role: UserRole = 'Manager', attach = false) {
  const api = createMockApi({ role, latency: 0 })
  api.saveWarningPlan = vi.fn(async input => ({ data: savedHandling(input), warnings: [], meta }))
  api.recordWarningAction = vi.fn(async input => ({ data: savedHandling(input, { state: 'handled', actedBy: 'manager', actedAt: '2026-09-24T09:00:00Z' }), warnings: [], meta }))
  api.getWarnings = vi.fn(async () => ({ data: warningsFixture(), warnings: [], meta }))
  api.reviewOpportunityLoss = vi.fn(async () => ({ data: { id: 'loss-review-1', opportunityId: 'opp-lost-1', stageEventId: 'evt', lostAt: '', lostAtStage: 'quotation_sent', lostBy: 'alice', lostReason: 'Budget frozen for 2026', status: 'reviewed' as const, reviewNote: 'Capex frozen; revisit Q1 2027', reviewedBy: 'manager', reviewedAt: '2026-09-14T02:00:00Z', reopenedAt: null, modified: '2026-09-14T02:00:00.000000Z', history: [] }, warnings: [], meta }))
  const pinia = createPinia()
  const router = createAppRouter()
  await router.push('/warnings'); await router.isReady()
  const wrapper = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] }, attachTo: attach ? document.body : undefined })
  await flushPromises()
  return { wrapper, api, router }
}

describe('Warnings page', () => {
  it('lists the region filter as the territory tree and sends the territory that is chosen', async () => {
    const { wrapper, api } = await setup()
    const data = warningsFixture()
    data.filters = { ...data.filters, regions: ['World', 'Asia', 'China', 'East China', 'Taiwan'], regionParents: { Asia: 'World', China: 'Asia', 'East China': 'China' }, regionReady: true }
    api.getWarnings = vi.fn(async () => ({ data, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    const select = wrapper.get('select[aria-label="Region"]')
    expect(select.findAll('option').slice(1).map(option => option.element.textContent)).toEqual(['全球', '\u00a0\u00a0亚洲', '\u00a0\u00a0\u00a0\u00a0中国', '\u00a0\u00a0\u00a0\u00a0\u00a0\u00a0华东', 'Taiwan'])
    await select.setValue('China'); await flushPromises()
    expect(api.getWarnings).toHaveBeenLastCalledWith(expect.objectContaining({ region: 'China', market: 'Frontend' }))
    wrapper.unmount()
  })

  it('shows the four zones with the Review scope, owners and links to the source records', async () => {
    const { wrapper, api } = await setup()
    expect(api.getWarnings).toHaveBeenCalledWith({ period: 'week', sales: '', market: '', region: '', equipment: '' })
    const cards = wrapper.findAll('.summary-card')
    expect(cards.map(card => card.get('strong').text())).toEqual(['1', '2', '1', '2'])
    expect(cards[0].text()).toContain('¥5.6M')
    expect(cards[0].text()).toContain('更早待复盘 1')
    expect(cards[3].text()).toContain('报价即将到期 1')
    expect(cards[3].text()).not.toContain('Demo')
    const lost = wrapper.get('[data-zone="lost"]')
    expect(lost.findAll('tbody tr')).toHaveLength(2)
    expect(lost.get('[data-lost-backlog]').attributes('aria-expanded')).toBe('false')
    await lost.get('[data-lost-backlog]').trigger('click')
    expect(lost.findAll('tbody tr')).toHaveLength(3)
    expect(lost.get('[data-lost-backlog]').attributes('aria-expanded')).toBe('true')
    expect(lost.get('[data-lost-row="opp-lost-1"]').text()).toContain('待分析')
    expect(lost.get('[data-lost-row="opp-lost-2"]').text()).toContain('已复盘')
    expect(lost.get('[data-lost-row="opp-lost-2"]').text()).toContain('Report shared with management')
    expect(lost.get('[data-lost-row="opp-lost-3"]').text()).toContain('复盘逾期')
    expect(lost.get('[data-lost-row="opp-lost-1"] a').attributes('href')).toBe('/opportunities/opp-lost-1')
    expect(lost.get('.zone-note').text()).toContain('Tianhe Microelectronics（¥9.3M）')
    const overdue = wrapper.get('[data-zone="overdue"]')
    expect(overdue.get('[data-overdue-row="act-1"]').text()).toContain('Schedule wafer evaluation slot')
    expect(overdue.get('[data-overdue-row="act-1"]').text()).toContain('15 天')
    expect(overdue.get('[data-overdue-row="act-1"]').text()).toContain('商机停滞')
    expect(overdue.get('[data-overdue-row="act-2"]').text()).toContain('Bob')
    const downgrade = wrapper.get('[data-zone="downgrade"]')
    expect(downgrade.get('[data-downgrade-row="prob-1"]').text()).toContain('Committed')
    expect(downgrade.get('[data-downgrade-row="prob-1"]').text()).toContain('Propose 20/60/20 milestone plan')
    expect(downgrade.get('[data-downgrade-row="prob-1"] a').attributes('href')).toBe('/opportunities/opp-down-1?probabilityEvent=prob-1')
    const other = wrapper.get('[data-zone="other"]')
    expect(other.get('[data-alert="quotation_expiry"] a').attributes('href')).toBe('/quotations/Q-1?version=V-2')
    expect(other.findAll('li').map(li => li.attributes('data-alert'))).toEqual(['quotation_expiry', 'stage6_no_po'])
    expect(wrapper.get('.review-controls').text()).toContain('Warnings')
    // Review gets the same scope back that it hands to this page, anchor included: its default week differs.
    // Plan opens on the next week and keeps this one for the way back; Opportunities carries this week along.
    expect(wrapper.findAll('.review-controls a').map(link => link.attributes('href'))).toEqual(['/dashboard?period=week&anchor=2026-09-07', '/plan?period=week&anchor=2026-09-14&reviewAnchor=2026-09-07', '/opportunity-board?period=week&reviewAnchor=2026-09-07'])
    setLocale('en-US'); await flushPromises()
    expect(lost.get('[data-lost-row="opp-lost-3"]').text()).toContain('Post-mortem overdue')
    wrapper.unmount()
  })

  it('hands Review the scope it was opened with, and waits for the period when it has none', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getWarnings = vi.fn(async () => ({ data: warningsFixture(), warnings: [], meta }))
    const router = createAppRouter()
    await router.push('/warnings?period=month&anchor=2026-08-01&market=Frontend&equipment=Kibo'); await router.isReady()
    const scoped = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getWarnings).toHaveBeenLastCalledWith({ period: 'month', anchor: '2026-08-01', sales: '', market: 'Frontend', region: '', equipment: 'Kibo' })
    expect(scoped.get('.review-controls a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=month&anchor=2026-08-01&market=Frontend&equipment=Kibo')
    scoped.unmount()
    // Opened without an anchor, the period on show is unknown until the data is here: the tab is not a link yet.
    let first = () => {}
    api.getWarnings = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getWarnings>>>(resolve => { first = () => resolve({ data: warningsFixture(), warnings: [], meta }) }))
    await router.push('/warnings'); await router.isReady()
    const plain = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(plain.find('.review-controls a[href^="/dashboard"]').exists()).toBe(false)
    const pending = plain.get('.review-controls [aria-disabled="true"]')
    expect([pending.text(), pending.attributes('role')]).toEqual(['Review', 'link'])
    expect(pending.attributes('title')).toBe('页面加载完成后可用')
    setLocale('en-US'); await flushPromises()
    expect(pending.attributes('title')).toBe('Available once the page has loaded')
    setLocale('zh-CN'); await flushPromises()
    first(); await flushPromises()
    expect(plain.get('.review-controls a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=week&anchor=2026-09-07')
    plain.unmount()
    // An anchor that is only whitespace is no anchor (the backend trims it): the page must not hand it on.
    await router.push('/warnings?anchor=%20'); await router.isReady()
    api.getWarnings = vi.fn(async () => ({ data: warningsFixture(), warnings: [], meta }))
    const blank = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getWarnings).toHaveBeenLastCalledWith({ period: 'week', sales: '', market: '', region: '', equipment: '' })
    expect(blank.get('.review-controls a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=week&anchor=2026-09-07')
    blank.unmount()
  })

  it('asks for a period only when the date field or the link holds a whole date it can show', async () => {
    // Noon on 2026-10-04 in Shanghai.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-04T04:00:00Z'))
    try {
      const api = createMockApi({ role: 'Manager', latency: 0 })
      const getWarnings = vi.fn(async () => ({ data: warningsFixture(), warnings: [], meta }))
      api.getWarnings = getWarnings
      const router = createAppRouter()
      // The date of this link is in the future: it is not sent, and the rest of the link is kept.
      await router.push('/warnings?period=month&anchor=2026-12-01&market=Frontend'); await router.isReady()
      const wrapper = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
      await flushPromises()
      expect(getWarnings).toHaveBeenCalledTimes(1)
      expect(getWarnings).toHaveBeenCalledWith({ period: 'month', sales: '', market: 'Frontend', region: '', equipment: '' })
      expect(wrapper.find('.review-state.error').exists()).toBe(false)

      const field = wrapper.get<HTMLInputElement>('input[type="date"]')
      expect([field.attributes('min'), field.attributes('max')]).toEqual(['2000-01-01', '2026-10-04'])
      getWarnings.mockClear()
      // The year typed digit by digit, a cleared field, a date in the future: nothing is asked for.
      for (const value of ['0002-09-21', '0202-09-21', '', '2026-10-05']) {
        field.element.value = value
        await field.trigger('change')
      }
      await flushPromises()
      expect(getWarnings).not.toHaveBeenCalled()
      await field.trigger('blur')
      expect(field.element.value).toBe(warningsFixture().period.start)

      // A whole date in range is asked for, and the field stays usable while it loads.
      let finish!: () => void
      getWarnings.mockImplementationOnce(() => new Promise((resolve) => { finish = () => resolve({ data: warningsFixture(), warnings: [], meta }) }))
      field.element.value = '2025-09-21'
      await field.trigger('input'); await field.trigger('change')
      expect(getWarnings).toHaveBeenCalledTimes(1)
      expect(getWarnings.mock.calls[0]).toEqual([{ period: 'month', anchor: '2025-09-21', sales: '', market: 'Frontend', region: '', equipment: '' }])
      expect(field.attributes('disabled')).toBeUndefined()
      // What is typed while that load is pending stays in the field when its answer redraws the page.
      field.element.value = '0002-09-21'
      await field.trigger('input'); await field.trigger('change')
      finish(); await flushPromises()
      expect(getWarnings).toHaveBeenCalledTimes(1)
      expect(field.element.value).toBe('0002-09-21')
      await field.trigger('blur')
      expect(field.element.value).toBe('2025-09-21')
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })

  it('opens the earliest week from a link, stops stepping back there and gives way to 2000 for another kind of period', async () => {
    const earliest = warningsFixture()
    earliest.period = { ...earliest.period, start: '1999-12-27', end: '2000-01-02', previousAnchor: '1999-12-20', nextAnchor: '2000-01-03' }
    const api = createMockApi({ role: 'Manager', latency: 0 })
    const getWarnings = vi.fn(async () => ({ data: earliest, warnings: [], meta }))
    api.getWarnings = getWarnings
    const router = createAppRouter()
    // The link Review makes on the week that reaches into 2000.
    await router.push('/warnings?period=week&anchor=1999-12-27'); await router.isReady()
    const wrapper = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(getWarnings).toHaveBeenLastCalledWith({ period: 'week', anchor: '1999-12-27', sales: '', market: '', region: '', equipment: '' })
    expect(wrapper.find('.review-state.error').exists()).toBe(false)
    expect(wrapper.get('button[aria-label="上一期"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[aria-label="下一期"]').attributes('disabled')).toBeUndefined()

    await wrapper.findAll('.period-controls .segmented button')[1].trigger('click')
    await flushPromises()
    expect(getWarnings).toHaveBeenLastCalledWith({ period: 'month', anchor: '2000-01-01', sales: '', market: '', region: '', equipment: '' })
    wrapper.unmount()
  })

  it('hands Plan the next period and Opportunities this period with the same scope, on the Shanghai calendar', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getWarnings = vi.fn(async () => ({ data: warningsFixture(), warnings: [], meta }))
    const router = createAppRouter()
    // The date of the link is taken only when it is not in the future: the clock stands after it.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-12-15T04:00:00Z'))
    try {
      await router.push('/warnings?period=month&anchor=2026-12-10&sales=alice&region=East+China'); await router.isReady()
      const scoped = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
      await flushPromises()
      expect(api.getWarnings).toHaveBeenNthCalledWith(1, { period: 'month', anchor: '2026-12-10', sales: 'alice', market: '', region: 'East China', equipment: '' })
      expect(scoped.get('.review-controls a[href^="/plan"]').attributes('href')).toBe('/plan?period=month&anchor=2027-01-01&reviewAnchor=2026-12-10&sales=alice&region=East+China')
      expect(scoped.get('.review-controls a[href^="/opportunity-board"]').attributes('href')).toBe('/opportunity-board?period=month&reviewAnchor=2026-12-10&sales=alice&region=East+China')
      scoped.unmount()
    } finally { vi.useRealTimers() }
    // Without an anchor and before (or without) data, this page shows today's Shanghai period: 16:30 UTC on Sep 30 is Oct 1 there.
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-30T16:30:00Z'))
    try {
      api.getWarnings = vi.fn().mockRejectedValue(new Error('network down'))
      await router.push('/warnings?period=quarter')
      const failed = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
      await flushPromises()
      expect(failed.get('.review-controls a[href^="/plan"]').attributes('href')).toBe('/plan?period=quarter&anchor=2027-01-01&reviewAnchor=2026-10-01')
      expect(failed.get('.review-controls a[href^="/opportunity-board"]').attributes('href')).toBe('/opportunity-board?period=quarter&reviewAnchor=2026-10-01')
      failed.unmount()
    } finally { vi.useRealTimers() }
  })

  it('keeps the Review tab reachable after the first load fails, even with an empty error message', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getWarnings = vi.fn().mockRejectedValue(new CrmApiError('INTERNAL_ERROR', '', 'req_empty'))
    const router = createAppRouter()
    await router.push('/warnings'); await router.isReady()
    const wrapper = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(wrapper.get('.review-state.error').text()).toContain('数据请求失败，请稍后重试。')
    // No anchor is known: Review opens on its own default period (the last completed week).
    expect(wrapper.get('.review-controls a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=week')
    expect(wrapper.find('span.is-disabled').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows rows a Manager cannot act on as such, marks minimum stays and steps between periods', async () => {
    const { wrapper, api } = await setup()
    const edge = warningsFixture()
    // A review row without a version, a reopened deal, no review row at all (backfill pending) in the
    // backlog, and a stage 6 stay that is only a minimum.
    edge.lost[0] = { ...edge.lost[0], review: { ...edge.lost[0].review!, modified: null } }
    edge.lost[1] = { ...edge.lost[1], reopenedAt: '2026-09-12T02:00:00Z', reviewPending: false }
    edge.lostBacklog[0] = { ...edge.lostBacklog[0], review: null, amount: '12000000' }
    edge.stage6NoPoItems = [{ ...edge.stage6NoPoItems![0], daysAtLeast: true, enteredAt: null }]
    edge.period = { ...edge.period, previousAnchor: '2026-08-24', hasNext: false }
    let release = () => {}
    api.getWarnings = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.getWarnings>>>(resolve => { release = () => resolve({ data: edge, warnings: [], meta }) }))
    await wrapper.get('[aria-label="上一期"]').trigger('click')
    // While the period loads, the anchor it asked for already names the period to hand to Review.
    expect(wrapper.get('.review-controls a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=week&anchor=2026-08-31')
    release(); await flushPromises()
    expect(api.getWarnings).toHaveBeenLastCalledWith(expect.objectContaining({ anchor: '2026-08-31' }))
    const lost = wrapper.get('[data-zone="lost"]')
    expect(lost.get('[data-lost-row="opp-lost-1"]').text()).toContain('复盘记录待回填')
    expect(lost.find('[data-lost-row="opp-lost-1"] [data-review-open]').exists()).toBe(false)
    expect(lost.get('[data-lost-row="opp-lost-2"]').text()).toContain('已重开')
    expect(lost.find('[data-lost-row="opp-lost-2"] [data-review-edit]').exists()).toBe(false)
    // The backlog has no age limit any more, so its toggle no longer says "last 12 months".
    expect(lost.get('[data-lost-backlog]').text()).toContain('不计入预警数')
    expect(lost.get('[data-lost-backlog]').text()).not.toContain('12 个月')
    expect(lost.get('.zone-note').text()).toContain('Tianhe Microelectronics（¥9.3M）')
    await lost.get('[data-lost-backlog]').trigger('click')
    // The largest-loss caption follows the rows on show.
    expect(lost.get('.zone-note').text()).toContain('Sunrise Optoelectronics（¥12M）')
    expect(lost.get('[data-lost-row="opp-lost-3"]').text()).toContain('复盘记录待回填')
    expect(lost.find('[data-lost-row="opp-lost-3"] [data-review-open]').exists()).toBe(false)
    expect(wrapper.get('[data-alert="stage6_no_po"]').text()).toContain('≥42 天')
    expect(wrapper.get('[aria-label="下一期"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="上一期"]').trigger('click'); await flushPromises()
    expect(api.getWarnings).toHaveBeenLastCalledWith(expect.objectContaining({ anchor: '2026-08-24' }))
    wrapper.unmount()
  })

  it('lets a Manager record the post-mortem against the review row and reloads, and reports version conflicts', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').trigger('click'); await flushPromises()
    const dialog = wrapper.get('.loss-review-dialog')
    expect(dialog.attributes('open')).toBeDefined()
    expect(dialog.text()).toContain('Budget frozen for 2026')
    expect(dialog.get('[data-review-submit]').attributes('disabled')).toBeDefined()
    await dialog.get('[data-review-note]').setValue('Capex frozen; revisit Q1 2027')
    expect(dialog.find('[data-review-revert]').exists()).toBe(false)
    await dialog.get('form').trigger('submit'); await flushPromises()
    expect(api.reviewOpportunityLoss).toHaveBeenCalledWith('opp-lost-1', 'loss-review-1', { status: 'Reviewed', reviewNote: 'Capex frozen; revisit Q1 2027' }, '2026-09-04T02:00:00.000000Z')
    expect(api.getWarnings).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.loss-review-dialog').attributes('open')).toBeUndefined()

    // A reviewed loss can be edited or reverted; a stale version asks for a reload instead of overwriting.
    api.reviewOpportunityLoss = vi.fn(async () => { throw new CrmApiError('VERSION_CONFLICT', 'The record was changed by another request.', 'conflict', false) })
    await wrapper.get('[data-lost-row="opp-lost-2"] [data-review-edit]').trigger('click'); await flushPromises()
    const edit = wrapper.get('.loss-review-dialog')
    expect((edit.get('[data-review-note]').element as HTMLTextAreaElement).value).toBe('Report shared with management')
    // Reverting asks for its own reason; the conclusion is sent unchanged and cannot stand in for the reason.
    await edit.get('[data-review-revert]').trigger('click')
    expect(edit.get('[data-review-revert-confirm]').attributes('disabled')).toBeDefined()
    await edit.get('[data-revert-reason]').setValue('Customer reopened talks; redo the analysis')
    await edit.get('[data-review-revert-confirm]').trigger('click'); await flushPromises()
    expect(api.reviewOpportunityLoss).toHaveBeenCalledWith('opp-lost-2', 'loss-review-2', { status: 'Pending', reviewNote: 'Report shared with management', revertReason: 'Customer reopened talks; redo the analysis' }, '2026-09-02T08:00:00.000000Z')
    expect(edit.get('.dialog-error').text()).toContain('重新加载')
    await edit.get('[data-review-reload]').trigger('click'); await flushPromises()
    expect(api.getWarnings).toHaveBeenCalledTimes(3)
    wrapper.unmount()
  })

  it('sends non-managers away without loading warnings', async () => {
    const { wrapper, api, router } = await setup('Sales')
    expect(wrapper.find('[data-testid="warnings-page"]').exists()).toBe(false)
    expect(api.getWarnings).not.toHaveBeenCalled()
    await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/calendar'))
    wrapper.unmount()
  })

  it('edits the downgrade plan in the meeting against both versions and keeps the warning', async () => {
    const { wrapper, api } = await setup()
    api.saveProbabilityRecovery = vi.fn(async () => ({ data: { id: 'recovery-1', plan: 'New plan', modified: '2026-09-14T00:00:00.000000Z', history: [], state: 'pending' as const, actionTaken: null, actedBy: null, actedAt: null }, warnings: [], meta }))
    const row = wrapper.get('[data-downgrade-row="prob-1"]')
    expect(row.get('[data-plan-edit]').text()).toContain('Alice')
    await row.get('[data-plan-edit]').trigger('click')
    const editor = wrapper.get('[data-plan-editor]')
    expect((editor.get('[data-plan-draft]').element as HTMLTextAreaElement).value).toContain('Propose 20/60/20')
    await editor.get('[data-plan-draft]').setValue('   ')
    expect(editor.get('[data-plan-save]').attributes('disabled')).toBeDefined()
    await editor.get('[data-plan-draft]').setValue('Bank guarantee draft to CFO by Sep 16')
    await editor.get('[data-plan-save]').trigger('click'); await flushPromises()
    expect(api.saveProbabilityRecovery).toHaveBeenCalledWith('opp-down-1', 'prob-1', { plan: 'Bank guarantee draft to CFO by Sep 16', recoveryModified: '2026-09-08T02:00:00.000000Z' }, '2026-09-09T03:00:00.000000Z')
    // A quiet refresh: the page is not blanked and the editor closes.
    expect(api.getWarnings).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-plan-editor]').exists()).toBe(false)
    expect(wrapper.find('[data-zone="downgrade"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps an open plan draft through a post-mortem save and locks filters while saving', async () => {
    const { wrapper, api } = await setup()
    let finish: () => void = () => {}
    api.reviewOpportunityLoss = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.reviewOpportunityLoss>>>(resolve => { finish = () => resolve({ data: {} as never, warnings: [], meta }) }))
    await wrapper.get('[data-downgrade-row="prob-1"] [data-plan-edit]').trigger('click')
    await wrapper.get('[data-plan-draft]').setValue('Unsaved meeting draft')
    await wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').trigger('click')
    await wrapper.get('[data-review-note]').setValue('Budget frozen; revisit in Q1')
    await wrapper.get('.loss-review-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.get('select[aria-label="Sales"]').attributes('disabled')).toBeDefined()
    finish(); await flushPromises()
    expect(api.getWarnings).toHaveBeenCalledTimes(2)
    expect((wrapper.get('[data-plan-draft]').element as HTMLTextAreaElement).value).toBe('Unsaved meeting draft')
    expect(wrapper.get('select[aria-label="Sales"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('shows Manager names, action owners and unknown stall status instead of zero', async () => {
    const data = warningsFixture()
    data.names = { manager: 'Wang Yansong', fae: 'Li Jianlin' }
    data.lost[1].review!.reviewedBy = 'manager'
    data.overdue = data.overdue.map(row => ({ ...row, stalled: null, actionOwner: 'fae' }))
    const { wrapper, api } = await setup()
    api.getWarnings = vi.fn(async () => ({ data, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    expect(wrapper.get('[data-lost-row="opp-lost-2"]').text()).toContain('Wang Yansong')
    expect(wrapper.get('[data-overdue-row="act-1"]').text()).toContain('Li Jianlin')
    expect(wrapper.get('.summary-card.overdue').text()).toContain('停滞状态待核验')
    expect(wrapper.get('[data-overdue-row="act-1"]').text()).not.toContain('商机停滞')
    wrapper.unmount()
  })

  it('opens with the period and filters it was linked from', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getWarnings = vi.fn(async () => ({ data: warningsFixture(), warnings: [], meta }))
    const router = createAppRouter()
    await router.push({ path: '/warnings', query: { period: 'month', anchor: '2026-08-01', market: 'Frontend' } }); await router.isReady()
    const wrapper = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getWarnings).toHaveBeenCalledWith({ period: 'month', anchor: '2026-08-01', sales: '', market: 'Frontend', region: '', equipment: '' })
    wrapper.unmount()
  })

  it('saves a plan against the versions it was opened with, even after a refresh brings newer ones', async () => {
    const { wrapper, api } = await setup()
    api.saveProbabilityRecovery = vi.fn(async () => { throw new CrmApiError('VERSION_CONFLICT', 'changed', 'conflict', false) })
    await wrapper.get('[data-downgrade-row="prob-1"] [data-plan-edit]').trigger('click')
    await wrapper.get('[data-plan-draft]').setValue('Draft from the old plan')
    // Someone else saved a newer plan; a quiet refresh (after a post-mortem) brings its versions.
    const newer = warningsFixture()
    newer.downgrade[0] = { ...newer.downgrade[0], opportunityModified: '2026-09-15T00:00:00.000000Z', recovery: { ...newer.downgrade[0].recovery!, plan: 'Owner plan', modified: '2026-09-15T01:00:00.000000Z' } }
    api.getWarnings = vi.fn(async () => ({ data: newer, warnings: [], meta }))
    await wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').trigger('click')
    await wrapper.get('[data-review-note]').setValue('Budget frozen')
    await wrapper.get('.loss-review-dialog form').trigger('submit'); await flushPromises()
    await wrapper.get('[data-plan-save]').trigger('click'); await flushPromises()
    expect(api.saveProbabilityRecovery).toHaveBeenCalledWith('opp-down-1', 'prob-1', { plan: 'Draft from the old plan', recoveryModified: '2026-09-08T02:00:00.000000Z' }, '2026-09-09T03:00:00.000000Z')
    expect(wrapper.get('[data-plan-editor]').text()).toContain('重新加载')
    wrapper.unmount()
  })

  it('keeps the page when the refresh after a save fails, and leaves an editor whose row is gone', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-downgrade-row="prob-1"] [data-plan-edit]').trigger('click')
    expect(wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').attributes('disabled')).toBeUndefined()
    const gone = warningsFixture()
    gone.downgrade = []
    api.getWarnings = vi.fn(async () => ({ data: gone, warnings: [], meta }))
    await wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').trigger('click')
    await wrapper.get('[data-review-note]').setValue('Budget frozen')
    await wrapper.get('.loss-review-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.find('[data-plan-editor]').exists()).toBe(false)
    api.getWarnings = vi.fn(async () => { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Gateway timeout', 'timeout', true) })
    await wrapper.get('[data-lost-row="opp-lost-2"] [data-review-edit]').trigger('click')
    await wrapper.get('[data-review-note]').setValue('Report shared again')
    await wrapper.get('.loss-review-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.find('[data-refresh-error]').exists()).toBe(true)
    expect(wrapper.find('[data-zone="lost"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('opens when the signed-in Manager is already loaded, as when navigating from Review', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getWarnings = vi.fn(async () => ({ data: warningsFixture(), warnings: [], meta }))
    const pinia = createPinia()
    // In the app the shell has loaded the bootstrap before any cockpit page mounts.
    await useAppStore(pinia).loadBootstrap(api)
    const router = createAppRouter()
    await router.push('/warnings'); await router.isReady()
    const wrapper = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    expect(api.getWarnings).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-zone="lost"]').exists()).toBe(true)
    // The warning-handling state is declared before the immediate load, so its editors render too.
    expect(wrapper.findAll('[data-step-edit]')).toHaveLength(4)
    expect(wrapper.find('[data-action-open]').exists()).toBe(true)
    expect(wrapper.find('[data-settings-open]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('lists expiring quotes and stage 6 deals without a PO under other alerts, with one empty state when neither applies', async () => {
    const { wrapper, api } = await setup()
    const other = () => wrapper.get('[data-zone="other"]')
    const otherValue = () => wrapper.findAll('.summary-card')[3].get('strong').text()
    const s6 = other().get('[data-alert="stage6_no_po"]')
    expect(s6.text()).toContain('第 6 阶段未收到 PO 已 42 天')
    expect(s6.text()).toContain('Huaxin Micro · KIBO 4895C line validation')
    expect(s6.text()).toContain('¥18.5M')
    expect(s6.get('a').attributes('href')).toContain('opp-s6-1')
    expect(other().find('[data-alert="quotation_expiry"]').exists()).toBe(true)
    expect(other().find('[data-alert-empty]').exists()).toBe(false)
    expect(other().get('.zone-note').text()).toContain('第 6 阶段 30 天')
    expect(otherValue()).toBe('2')
    expect(wrapper.findAll('.summary-card')[3].get('small').text()).toContain('第 6 阶段超期无 PO 1')

    const empty = warningsFixture()
    empty.quotationExpiryItems = []
    empty.stage6NoPoItems = []
    empty.stage6NoPoHandledItems = []
    empty.warnings = empty.warnings.map(w => ['quotation_expiry', 'stage6_no_po'].includes(w.key) ? { ...w, count: { state: 'ready' as const, value: 0 } } : w)
    api.getWarnings = vi.fn(async () => ({ data: empty, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    expect(other().get('[data-alert-empty]').text()).toContain('没有即将到期的报价，也没有第 6 阶段超期未收到 PO 的商机')
    expect(otherValue()).toBe('0')
    // Handled stage 6 deals still exist: none is waiting, rather than none at all.
    const handledOnly = { ...empty, stage6NoPoHandledItems: warningsFixture().stage6NoPoHandledItems }
    api.getWarnings = vi.fn(async () => ({ data: handledOnly, warnings: [], meta }))
    await wrapper.get('select[aria-label="Sales"]').setValue('alice'); await flushPromises()
    expect(other().get('[data-alert-empty]').text()).toBe('没有即将到期的报价，暂无待处理的第 6 阶段超期商机')

    // One insufficient count makes the zone total insufficient, never a partial sum.
    const unknown = warningsFixture()
    unknown.warnings = unknown.warnings.map(w => w.key === 'stage6_no_po' ? { ...w, count: { state: 'insufficient' as const, value: null } } : w)
    api.getWarnings = vi.fn(async () => ({ data: unknown, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue(''); await flushPromises()
    expect(otherValue()).toBe('数据不足')

    // Unknown and empty: the note and the list never read as "none".
    const unknownEmpty = warningsFixture()
    unknownEmpty.quotationExpiryItems = []
    unknownEmpty.stage6NoPoItems = []
    unknownEmpty.warnings = unknownEmpty.warnings.map(w => w.key === 'quotation_expiry' ? { ...w, count: { state: 'ready' as const, value: 0 } }
      : w.key === 'stage6_no_po' ? { ...w, count: { state: 'insufficient' as const, value: null } } : w)
    api.getWarnings = vi.fn(async () => ({ data: unknownEmpty, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    expect(wrapper.findAll('.summary-card')[3].get('small').text()).toContain('第 6 阶段超期无 PO 数据不足')
    expect(other().get('[data-alert-empty]').text()).toBe('提醒数据不足，列表为空不代表没有提醒')

    // A ready count without a value is as unknown as an insufficient one.
    const noValue = warningsFixture()
    noValue.quotationExpiryItems = []
    noValue.stage6NoPoItems = []
    noValue.warnings = noValue.warnings.map(w => w.key === 'quotation_expiry' ? { ...w, count: { state: 'ready' as const, value: null } }
      : w.key === 'stage6_no_po' ? { ...w, count: { state: 'ready' as const, value: 0 } } : w)
    api.getWarnings = vi.fn(async () => ({ data: noValue, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue(''); await flushPromises()
    expect(otherValue()).toBe('数据不足')
    expect(other().get('[data-alert-empty]').text()).toBe('提醒数据不足，列表为空不代表没有提醒')

    // A backend without the stage 6 alert: quotes only, no stage 6 wording.
    const older = warningsFixture()
    older.quotationExpiryItems = []
    older.warnings = older.warnings.filter(w => w.key !== 'stage6_no_po').map(w => w.key === 'quotation_expiry' ? { ...w, count: { state: 'ready' as const, value: 0 } } : w)
    delete older.stage6NoPo
    delete older.stage6NoPoItems
    api.getWarnings = vi.fn(async () => ({ data: older, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    expect(otherValue()).toBe('0')
    expect(other().get('[data-alert-empty]').text()).toBe('没有即将到期的报价')
    expect(other().text()).not.toContain('第 6 阶段')
    expect(wrapper.findAll('.summary-card')[3].text()).not.toContain('第 6 阶段')
    wrapper.unmount()
  })

  it('edits the next step on overdue, quotation and stage 6 rows against the handling version and keeps every row', async () => {
    const { wrapper, api } = await setup()
    const overdue = () => wrapper.get('[data-overdue-row="act-1"]')
    expect(overdue().get('[data-step-edit]').text()).toContain('FAE confirms the slot with the fab on Friday')
    expect(overdue().get('[data-step-edit]').text()).toContain('Alice')
    // Plan updates and actions taken read differently in the history.
    expect(overdue().get('[data-step-history] [data-kind="PlanUpdated"]').text()).toContain('计划更新')
    expect(wrapper.get('[data-alert="stage6_no_po"] [data-step-history] [data-kind="ActionRecorded"]').text()).toContain('已采取行动')
    // A stage 6 row back after its follow-up date shows the previous action; overdue and quotation rows cannot record one.
    expect(wrapper.get('[data-alert="stage6_no_po"] [data-last-action]').text()).toContain('Customer finance promised the PO by Sep 10')
    expect(wrapper.find('[data-zone="overdue"] [data-action-open]').exists()).toBe(false)
    expect(wrapper.find('[data-alert="quotation_expiry"] [data-action-open]').exists()).toBe(false)

    await overdue().get('[data-step-edit]').trigger('click')
    expect((overdue().get('[data-step-draft]').element as HTMLTextAreaElement).value).toBe('FAE confirms the slot with the fab on Friday')
    // One editor at a time.
    expect(wrapper.get('[data-overdue-row="act-2"] [data-step-edit]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-alert="stage6_no_po"] [data-action-open]').attributes('disabled')).toBeDefined()
    await overdue().get('[data-step-draft]').setValue('   ')
    expect(overdue().get('[data-step-save]').attributes('disabled')).toBeDefined()
    await overdue().get('[data-step-draft]').setValue(' FAE books the slot today ')
    await overdue().get('[data-step-save]').trigger('click'); await flushPromises()
    expect(api.saveWarningPlan).toHaveBeenCalledWith({ warningType: 'overdue', sourceId: 'act-1', sourceEvent: '2026-08-29', nextStep: 'FAE books the slot today' }, '2026-09-10T02:00:00.000000Z')
    expect(api.getWarnings).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-step-editor]').exists()).toBe(false)
    expect(wrapper.find('[data-overdue-row="act-1"]').exists()).toBe(true)

    // A first next step: no handling record yet, so no version.
    await wrapper.get('[data-alert="quotation_expiry"] [data-step-edit]').trigger('click')
    await wrapper.get('[data-alert="quotation_expiry"] [data-step-draft]').setValue('Re-price with the 2027 list')
    await wrapper.get('[data-alert="quotation_expiry"] [data-step-save]').trigger('click'); await flushPromises()
    expect(api.saveWarningPlan).toHaveBeenLastCalledWith({ warningType: 'quotation_expiry', sourceId: 'Q-1', sourceEvent: 'V-2', nextStep: 'Re-price with the 2027 list' }, null)

    await wrapper.get('[data-alert="stage6_no_po"] [data-step-edit]').trigger('click')
    await wrapper.get('[data-alert="stage6_no_po"] [data-step-draft]').setValue('Chase the buyer after the audit')
    await wrapper.get('[data-alert="stage6_no_po"] [data-step-save]').trigger('click'); await flushPromises()
    expect(api.saveWarningPlan).toHaveBeenLastCalledWith({ warningType: 'stage6_no_po', sourceId: 'opp-s6-1', sourceEvent: 's6-entry-1', nextStep: 'Chase the buyer after the audit' }, '2026-08-20T03:00:00.000000Z')
    expect(api.getWarnings).toHaveBeenCalledTimes(4)
    expect(wrapper.get('[data-zone="other"]').findAll('[data-alert]').map(item => item.attributes('data-alert'))).toEqual(['quotation_expiry', 'stage6_no_po'])
    wrapper.unmount()
  })

  it('saves a next step against the version it was opened with and offers a reload on a version conflict', async () => {
    const { wrapper, api } = await setup()
    api.saveWarningPlan = vi.fn(async () => { throw new CrmApiError('VERSION_CONFLICT', 'changed', 'conflict', false) })
    await wrapper.get('[data-overdue-row="act-1"] [data-step-edit]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('Draft from the old next step')
    // Someone else saved a newer next step; a quiet refresh (after a post-mortem) brings its version, the draft stays.
    const newer = warningsFixture()
    newer.overdue[0] = { ...newer.overdue[0], handling: { ...newer.overdue[0].handling!, nextStep: 'Owner next step', modified: '2026-09-15T00:00:00.000000Z' } }
    api.getWarnings = vi.fn(async () => ({ data: newer, warnings: [], meta }))
    await wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').trigger('click')
    await wrapper.get('[data-review-note]').setValue('Budget frozen')
    await wrapper.get('.loss-review-dialog form').trigger('submit'); await flushPromises()
    expect((wrapper.get('[data-step-draft]').element as HTMLTextAreaElement).value).toBe('Draft from the old next step')
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(api.saveWarningPlan).toHaveBeenCalledWith({ warningType: 'overdue', sourceId: 'act-1', sourceEvent: '2026-08-29', nextStep: 'Draft from the old next step' }, '2026-09-10T02:00:00.000000Z')
    expect(wrapper.get('[data-step-editor]').text()).toContain('已被他人修改，请刷新后重试')
    await wrapper.get('[data-step-reload]').trigger('click'); await flushPromises()
    expect(api.getWarnings).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-step-editor]').exists()).toBe(false)
    expect(wrapper.get('[data-overdue-row="act-1"]').text()).toContain('Owner next step')
    wrapper.unmount()
  })

  it('shows field errors, and refreshes quietly and says so when the alert is gone before the save', async () => {
    const { wrapper, api } = await setup()
    api.recordWarningAction = vi.fn(async () => { throw new CrmApiError('VALIDATION_ERROR', 'Invalid input.', 'invalid', false, { followUpOn: 'Follow-up date must be after today.' }) })
    await wrapper.get('[data-alert="stage6_no_po"] [data-action-open]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('Called the buyer')
    await wrapper.get('[data-follow-up]').setValue(shanghaiDay(7))
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    // Field errors read in the page language, chosen by field.
    expect(wrapper.get('[data-step-editor="action"]').text()).toContain('请选择明天至一年内的复核日期')
    expect(wrapper.get('[data-step-editor="action"]').text()).not.toContain('Follow-up date must be after today.')
    expect(wrapper.find('[data-step-reload]').exists()).toBe(false)
    api.recordWarningAction = vi.fn(async () => { throw new CrmApiError('INVALID_TRANSITION', 'The warning is no longer open.', 'gone', false) })
    const gone = warningsFixture()
    gone.stage6NoPoItems = []
    api.getWarnings = vi.fn(async () => ({ data: gone, warnings: [], meta }))
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(api.getWarnings).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-step-editor]').exists()).toBe(false)
    expect(wrapper.find('[data-alert="stage6_no_po"]').exists()).toBe(false)
    expect(wrapper.get('[data-handling-notice]').text()).toContain('页面已刷新')
    expect(wrapper.find('[data-zone="lost"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('records the action taken on a stage 6 row only with a follow-up date, locks the filters while saving and lists it as handled', async () => {
    const { wrapper, api } = await setup()
    let finish: () => void = () => {}
    api.recordWarningAction = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.recordWarningAction>>>(resolve => { finish = () => resolve({ data: savedHandling({ warningType: 'stage6_no_po', sourceId: 'opp-s6-1', sourceEvent: 's6-entry-1' }, { state: 'handled', actionTaken: 'GM call with the buyer; PO promised', followUpOn: shanghaiDay(14) }), warnings: [], meta }) }))
    await wrapper.get('[data-alert="stage6_no_po"] [data-action-open]').trigger('click')
    const form = () => wrapper.get('[data-step-editor="action"]')
    expect((form().get('[data-step-draft]').element as HTMLTextAreaElement).value).toBe('')
    const date = form().get('[data-follow-up]')
    expect(date.attributes('min')).toBe(shanghaiDay(1))
    expect(date.attributes('max')).toBe(shanghaiDay(365))
    await form().get('[data-step-draft]').setValue('GM call with the buyer; PO promised')
    expect(form().get('[data-step-save]').attributes('disabled')).toBeDefined()
    // A missing or out-of-range date says why Save is disabled.
    expect(form().get('[data-date-hint]').text()).toBe('请选择明天至一年内的日期')
    for (const outside of [shanghaiDay(0), shanghaiDay(366)]) {
      await date.setValue(outside)
      expect(form().get('[data-step-save]').attributes('disabled')).toBeDefined()
      expect(form().find('[data-date-hint]').exists()).toBe(true)
    }
    await date.setValue(shanghaiDay(14))
    expect(form().get('[data-step-save]').attributes('disabled')).toBeUndefined()
    expect(form().find('[data-date-hint]').exists()).toBe(false)
    // The backend moves the row to the handled list; it is no longer counted.
    const after = warningsFixture()
    const moved = after.stage6NoPoItems![0]
    moved.handling = { ...moved.handling!, state: 'handled', actionTaken: 'GM call with the buyer; PO promised', actedBy: 'alice', actedAt: '2026-09-24T02:00:00Z', followUpOn: shanghaiDay(14) }
    after.stage6NoPoItems = []
    after.stage6NoPoHandledItems = [moved, ...after.stage6NoPoHandledItems!]
    after.warnings = after.warnings.map(w => w.key === 'stage6_no_po' ? { ...w, count: { state: 'ready' as const, value: 0 } } : w)
    api.getWarnings = vi.fn(async () => ({ data: after, warnings: [], meta }))
    await form().get('[data-step-save]').trigger('click'); await flushPromises()
    expect(api.recordWarningAction).toHaveBeenCalledWith({ warningType: 'stage6_no_po', sourceId: 'opp-s6-1', sourceEvent: 's6-entry-1', actionTaken: 'GM call with the buyer; PO promised', followUpOn: shanghaiDay(14) }, '2026-08-20T03:00:00.000000Z')
    expect(wrapper.get('select[aria-label="Sales"]').attributes('disabled')).toBeDefined()
    finish(); await flushPromises()
    expect(wrapper.get('select[aria-label="Sales"]').attributes('disabled')).toBeUndefined()
    expect(api.getWarnings).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-alert="stage6_no_po"]').exists()).toBe(false)
    expect(wrapper.get('[data-s6-handled-toggle]').text()).toContain('已处理 (2)')
    await wrapper.get('[data-s6-handled-toggle]').trigger('click')
    expect(wrapper.get('[data-s6-handled-row="opp-s6-1"]').text()).toContain('GM call with the buyer; PO promised')
    expect(wrapper.get('[data-zone="other"] .zone-count').text()).toBe('1')
    wrapper.unmount()
  })

  it('keeps handled stage 6 rows in a collapsed list that is never counted', async () => {
    const { wrapper } = await setup()
    const other = wrapper.get('[data-zone="other"]')
    const toggle = other.get('[data-s6-handled-toggle]')
    expect(toggle.text()).toContain('已处理 (1)')
    expect(toggle.text()).toContain('不计入预警数')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(other.find('[data-s6-handled]').exists()).toBe(false)
    expect(other.get('.zone-count').text()).toBe('2')
    expect(wrapper.findAll('.summary-card')[3].get('strong').text()).toBe('2')
    await toggle.trigger('click')
    const row = other.get('[data-s6-handled-row="opp-s6-2"]')
    expect(row.text()).toContain('GM call with the buyer; PO expected next week')
    expect(row.text()).toContain('Bob')
    expect(row.text()).toContain('复核')
    expect(row.find('[data-step-edit]').exists()).toBe(false)
    expect(other.findAll('[data-alert]').map(item => item.attributes('data-alert'))).toEqual(['quotation_expiry', 'stage6_no_po'])
    wrapper.unmount()
  })

  it('edits the thresholds in a dialog from the other-alerts zone, validates each day range and reloads the counts', async () => {
    const { wrapper, api } = await setup()
    const named = warningsFixture()
    named.names = { manager: 'Wang Yansong' }
    api.getWarnings = vi.fn(async () => ({ data: named, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    const current = { quoteExpiryDays: 14, stage6NoPoDays: 30, sources: { quoteExpiryDays: 'settings' as const, stage6NoPoDays: 'default' as const }, modified: '2026-09-20T02:00:00.000000Z', modifiedBy: 'manager', modifiedByName: '王艳松' }
    api.getCockpitSettings = vi.fn(async () => ({ data: current, warnings: [], meta }))
    api.saveCockpitSettings = vi.fn(async () => ({ data: { ...current, quoteExpiryDays: 21 }, warnings: [], meta }))
    // The masthead keeps its measured layout: the button lives in the zone header.
    expect(wrapper.find('.review-masthead [data-settings-open]').exists()).toBe(false)
    await wrapper.get('[data-zone="other"] .panel-heading [data-settings-open]').trigger('click'); await flushPromises()
    const dialog = wrapper.get('.settings-dialog')
    expect(dialog.attributes('open')).toBeDefined()
    expect(api.getCockpitSettings).toHaveBeenCalledTimes(1)
    const quote = () => dialog.get('[data-setting="quoteExpiryDays"]')
    expect((quote().element as HTMLInputElement).value).toBe('14')
    expect(dialog.get('[data-setting-source="quoteExpiryDays"]').text()).toContain('已保存设置')
    expect(dialog.get('[data-setting-source="stage6NoPoDays"]').text()).toContain('默认值')
    expect(dialog.get('[data-settings-modified]').text()).toContain('王艳松')
    // Quotes take 0–365 (0: only quotes expiring on the reference date); stage 6 takes 1–365.
    for (const bad of ['-1', '366', '14.5', '']) {
      await quote().setValue(bad)
      expect(dialog.get('[data-settings-save]').attributes('disabled')).toBeDefined()
      expect(dialog.get('[data-setting-invalid]').text()).toContain('0–365')
    }
    await dialog.get('[data-setting="stage6NoPoDays"]').setValue('0')
    expect(dialog.get('[data-setting-source="stage6NoPoDays"] [data-setting-invalid]').text()).toContain('1–365')
    await dialog.get('[data-setting="stage6NoPoDays"]').setValue('30')
    await quote().setValue('0')
    expect(dialog.find('[data-setting-invalid]').exists()).toBe(false)
    await dialog.get('form').trigger('submit'); await flushPromises()
    expect(api.saveCockpitSettings).toHaveBeenCalledWith({ quoteExpiryDays: 0, stage6NoPoDays: 30 }, '2026-09-20T02:00:00.000000Z')
    expect(dialog.attributes('open')).toBeUndefined()
    expect(api.getWarnings).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-zone="lost"]').exists()).toBe(true)

    // Someone saved first: the dialog says so and reloads the settings.
    api.saveCockpitSettings = vi.fn(async () => { throw new CrmApiError('VERSION_CONFLICT', 'changed', 'conflict', false) })
    await wrapper.get('[data-settings-open]').trigger('click'); await flushPromises()
    await wrapper.get('.settings-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.get('.settings-dialog .dialog-error').text()).toContain('已被他人修改，请刷新后重试')
    // A rejected value reads in the page language, not the backend's text.
    api.saveCockpitSettings = vi.fn(async () => { throw new CrmApiError('VALIDATION_ERROR', 'Invalid input.', 'invalid', false, { quoteExpiryDays: 'Must be between 0 and 365.' }) })
    await wrapper.get('.settings-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.get('.settings-dialog .dialog-error').text()).toBe('报价到期提醒天数须为 0–365 的整数')
    api.saveCockpitSettings = vi.fn(async () => { throw new CrmApiError('VERSION_CONFLICT', 'changed', 'conflict', false) })
    await wrapper.get('.settings-dialog form').trigger('submit'); await flushPromises()
    await wrapper.get('[data-settings-reload]').trigger('click'); await flushPromises()
    expect(api.getCockpitSettings).toHaveBeenCalledTimes(3)
    expect(wrapper.find('.settings-dialog .dialog-error').exists()).toBe(false)
    wrapper.unmount()
  })

  it('hides the next-step editors and the thresholds button for a backend without warning handling', async () => {
    const old = warningsFixture()
    for (const row of [...old.overdue, ...old.quotationExpiryItems, ...old.stage6NoPoItems!]) delete row.handling
    delete old.stage6NoPoHandledItems
    const { wrapper, api } = await setup()
    api.getWarnings = vi.fn(async () => ({ data: old, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    expect(wrapper.find('[data-alert="stage6_no_po"]').exists()).toBe(true)
    expect(wrapper.find('[data-step-edit]').exists()).toBe(false)
    expect(wrapper.find('[data-action-open]').exists()).toBe(false)
    expect(wrapper.find('[data-settings-open]').exists()).toBe(false)
    expect(wrapper.find('[data-s6-handled-toggle]').exists()).toBe(false)
    expect(wrapper.get('[data-zone="overdue"] thead').text()).not.toContain('下一步')
    expect(wrapper.get('[data-zone="other"] .zone-note').text()).not.toContain('下一步')
    wrapper.unmount()
  })

  it('keeps one inline editor per page and disables every save while another save runs', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-downgrade-row="prob-1"] [data-plan-edit]').trigger('click')
    // A plan draft locks every next-step and action button, and the other way round.
    const stepButtons = wrapper.findAll('[data-step-edit], [data-action-open]')
    expect(stepButtons.length).toBeGreaterThan(0)
    expect(stepButtons.every(button => button.attributes('disabled') !== undefined)).toBe(true)
    await wrapper.get('[data-plan-editor] .plan-editor-foot button').trigger('click')
    await wrapper.get('[data-overdue-row="act-2"] [data-step-edit]').trigger('click')
    expect(wrapper.get('[data-downgrade-row="prob-1"] [data-plan-edit]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-step-draft]').setValue('Counter-proposal to the buyer by Friday')
    expect(wrapper.get('[data-step-save]').attributes('disabled')).toBeUndefined()
    // While a post-mortem save runs, the open next step cannot save: one save's reload would drop the other's result.
    let finish: () => void = () => {}
    api.reviewOpportunityLoss = vi.fn(() => new Promise<Awaited<ReturnType<typeof api.reviewOpportunityLoss>>>(resolve => { finish = () => resolve({ data: {} as never, warnings: [], meta }) }))
    await wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').trigger('click')
    await wrapper.get('[data-review-note]').setValue('Budget frozen')
    await wrapper.get('.loss-review-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[data-step-save]').attributes('disabled')).toBeDefined()
    finish(); await flushPromises()
    expect(wrapper.get('[data-step-save]').attributes('disabled')).toBeUndefined()
    expect((wrapper.get('[data-step-draft]').element as HTMLTextAreaElement).value).toBe('Counter-proposal to the buyer by Friday')
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(api.saveWarningPlan).toHaveBeenCalledWith({ warningType: 'overdue', sourceId: 'act-2', sourceEvent: '2026-09-01', nextStep: 'Counter-proposal to the buyer by Friday' }, null)
    wrapper.unmount()
  })

  it('corrects the action and follow-up date of a handled stage 6 row against its version', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-s6-handled-toggle]').trigger('click')
    const row = () => wrapper.get('[data-s6-handled-row="opp-s6-2"]')
    await row().get('[data-action-edit]').trigger('click')
    expect((row().get('[data-step-draft]').element as HTMLTextAreaElement).value).toBe('GM call with the buyer; PO expected next week')
    expect((row().get('[data-follow-up]').element as HTMLInputElement).value).toBe('2026-09-30')
    await row().get('[data-follow-up]').setValue(shanghaiDay(10))
    await row().get('[data-step-save]').trigger('click'); await flushPromises()
    expect(api.recordWarningAction).toHaveBeenCalledWith({ warningType: 'stage6_no_po', sourceId: 'opp-s6-2', sourceEvent: 's6-entry-2', actionTaken: 'GM call with the buyer; PO expected next week', followUpOn: shanghaiDay(10) }, '2026-09-12T03:00:00.000000Z')
    expect(api.getWarnings).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-step-editor]').exists()).toBe(false)
    expect(row().find('[data-action-edit]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('says an open draft was not saved when a refresh removes its row', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-overdue-row="act-1"] [data-step-edit]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('Unsaved next step')
    const gone = warningsFixture()
    gone.overdue = gone.overdue.slice(1)
    api.getWarnings = vi.fn(async () => ({ data: gone, warnings: [], meta }))
    await wrapper.get('[data-lost-row="opp-lost-1"] [data-review-open]').trigger('click')
    await wrapper.get('[data-review-note]').setValue('Budget frozen')
    await wrapper.get('.loss-review-dialog form').trigger('submit'); await flushPromises()
    expect(wrapper.find('[data-step-editor]').exists()).toBe(false)
    expect(wrapper.get('[data-handling-notice]').text()).toContain('草稿未保存')
    wrapper.unmount()
  })

  it('keeps the saved version when the reload fails, and never claims a save or a refresh that did not happen', async () => {
    const { wrapper, api } = await setup()
    api.getWarnings = vi.fn(async () => { throw new CrmApiError('BACKEND_NOT_CONNECTED', 'Gateway timeout', 'timeout', true) })
    await wrapper.get('[data-overdue-row="act-2"] [data-step-edit]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('Counter-proposal by Friday')
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-refresh-error]').text()).toContain('已保存，但页面刷新失败')
    // The saved next step and its new version are on the row although the reload failed.
    expect(wrapper.get('[data-overdue-row="act-2"]').text()).toContain('Counter-proposal by Friday')
    let finish: () => void = () => {}
    api.saveWarningPlan = vi.fn(input => new Promise<Awaited<ReturnType<typeof api.saveWarningPlan>>>(resolve => { finish = () => resolve({ data: savedHandling(input), warnings: [], meta }) }))
    await wrapper.get('[data-overdue-row="act-2"] [data-step-edit]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('Counter-proposal by Monday')
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(api.saveWarningPlan).toHaveBeenCalledWith({ warningType: 'overdue', sourceId: 'act-2', sourceEvent: '2026-09-01', nextStep: 'Counter-proposal by Monday' }, '2026-09-24T09:00:00.000000Z')
    // No manual refresh while a save runs.
    expect(wrapper.get('[data-refresh-error] button').attributes('disabled')).toBeDefined()
    finish(); await flushPromises()
    // The alert is gone and the reload fails too: nothing was saved and nothing was refreshed.
    api.recordWarningAction = vi.fn(async () => { throw new CrmApiError('INVALID_TRANSITION', 'The warning is no longer open.', 'gone', false) })
    await wrapper.get('[data-alert="stage6_no_po"] [data-action-open]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('Called the buyer')
    await wrapper.get('[data-follow-up]').setValue(shanghaiDay(7))
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-handling-notice]').text()).toContain('草稿未保存')
    expect(wrapper.get('[data-handling-notice]').text()).not.toContain('页面已刷新')
    expect(wrapper.get('[data-refresh-error]').text()).toContain('页面刷新失败')
    expect(wrapper.get('[data-refresh-error]').text()).not.toContain('已保存')
    wrapper.unmount()
  })

  it('checks the follow-up date again at save time, after the Shanghai day has turned', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-24T10:00:00+08:00'))
    try {
      const { wrapper, api } = await setup()
      await wrapper.get('[data-alert="stage6_no_po"] [data-action-open]').trigger('click')
      await wrapper.get('[data-step-draft]').setValue('Called the buyer')
      await wrapper.get('[data-follow-up]').setValue('2026-09-25')
      expect(wrapper.get('[data-step-save]').attributes('disabled')).toBeUndefined()
      vi.setSystemTime(new Date('2026-09-25T00:30:00+08:00'))
      await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
      expect(api.recordWarningAction).not.toHaveBeenCalled()
      expect(wrapper.get('[data-follow-up]').attributes('min')).toBe('2026-09-26')
      expect(wrapper.get('[data-date-hint]').text()).toBe('请选择明天至一年内的日期')
      wrapper.unmount()
    } finally { vi.useRealTimers() }
  })

  it('moves focus into an opened editor and back to its button after cancel or save, and back to the thresholds button', async () => {
    const { wrapper, api } = await setup('Manager', true)
    const stepEdit = () => wrapper.get('[data-overdue-row="act-1"] [data-step-edit]').element
    await wrapper.get('[data-overdue-row="act-1"] [data-step-edit]').trigger('click'); await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[data-step-draft]').element)
    await wrapper.get('[data-step-editor] .step-editor-foot button').trigger('click'); await flushPromises()
    expect(document.activeElement).toBe(stepEdit())
    await wrapper.get('[data-overdue-row="act-1"] [data-step-edit]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('FAE books the slot today')
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(document.activeElement).toBe(stepEdit())
    await wrapper.get('[data-downgrade-row="prob-1"] [data-plan-edit]').trigger('click'); await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[data-plan-draft]').element)
    await wrapper.get('[data-plan-editor] .plan-editor-foot button').trigger('click'); await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[data-downgrade-row="prob-1"] [data-plan-edit]').element)
    // A stage 6 row that moved to the collapsed handled list hands focus to its toggle.
    const after = warningsFixture()
    after.stage6NoPoHandledItems = [...after.stage6NoPoHandledItems!, { ...after.stage6NoPoItems![0], handling: { ...after.stage6NoPoItems![0].handling!, state: 'handled' } }]
    after.stage6NoPoItems = []
    api.getWarnings = vi.fn(async () => ({ data: after, warnings: [], meta }))
    await wrapper.get('[data-alert="stage6_no_po"] [data-action-open]').trigger('click')
    await wrapper.get('[data-step-draft]').setValue('Called the buyer')
    await wrapper.get('[data-follow-up]').setValue(shanghaiDay(7))
    await wrapper.get('[data-step-save]').trigger('click'); await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[data-s6-handled-toggle]').element)
    const current = { quoteExpiryDays: 14, stage6NoPoDays: 30, sources: { quoteExpiryDays: 'default' as const, stage6NoPoDays: 'default' as const }, modified: null, modifiedBy: null, modifiedByName: null }
    api.getCockpitSettings = vi.fn(async () => ({ data: current, warnings: [], meta }))
    api.saveCockpitSettings = vi.fn(async () => ({ data: current, warnings: [], meta }))
    await wrapper.get('[data-settings-open]').trigger('click'); await flushPromises()
    await wrapper.get('.settings-dialog form').trigger('submit'); await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('[data-settings-open]').element)
    wrapper.unmount()
  })

  it('filters Warnings by equipment and opens with the equipment it was linked from', async () => {
    const data = warningsFixture()
    data.filters = { ...data.filters, equipment: ['Aconca', 'Kibo'] }
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getWarnings = vi.fn(async () => ({ data, warnings: [], meta }))
    const router = createAppRouter()
    await router.push({ path: '/warnings', query: { equipment: 'Kibo' } }); await router.isReady()
    const wrapper = mount(WarningsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()
    expect(api.getWarnings).toHaveBeenLastCalledWith(expect.objectContaining({ equipment: 'Kibo' }))
    await wrapper.get('select[aria-label="Equipment"]').setValue('Aconca'); await flushPromises()
    expect(api.getWarnings).toHaveBeenLastCalledWith(expect.objectContaining({ equipment: 'Aconca' }))
    wrapper.unmount()
  })

  it('keeps an insufficient summary count on one line, with the full text as the tooltip', async () => {
    const data = warningsFixture()
    data.warnings[1] = { key: 'overdue', count: { value: null, state: 'insufficient' } }
    const { wrapper, api } = await setup()
    api.getWarnings = vi.fn(async () => ({ data, warnings: [], meta }))
    await wrapper.get('select[aria-label="Market"]').setValue('Frontend'); await flushPromises()
    const value = wrapper.get('.summary-card.overdue strong')
    expect(value.text()).toBe('数据不足')
    expect(value.classes()).toContain('text-value')
    expect(value.attributes('title')).toBe('数据不足')
    expect(wrapper.get('.summary-card.lost strong').classes()).not.toContain('text-value')
    wrapper.unmount()
  })
})
