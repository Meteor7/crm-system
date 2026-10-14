import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMockApi } from '@/api/mock-adapter'
import { CrmApiError } from '@/api/contracts'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import { setLocale } from '@/i18n'
import { boardFiltersFixture, boardResultFixture, savedQueryFixture } from '@/features/opportunity-board/fixtures'
import { defaultDefinition } from '@/features/opportunity-board/model'
import type { UserRole } from '@/types/crm'
import type { BoardResult } from '@/features/opportunity-board/types'
import { reviewFixture } from '@/features/cockpit/review.fixture'
import { planDetailsFixture, planFixture } from '@/features/cockpit/plan.fixture'
import OpportunityBoardPage from './OpportunityBoardPage.vue'
import ReviewPage from './ReviewPage.vue'
import PlanPage from './PlanPage.vue'
const response = <T,>(data: T) => ({ data, warnings: [], meta: { requestId: 'board-test' } })
const mounted: VueWrapper[] = []
beforeEach(() => {
  setLocale('zh-CN')
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { mounted.splice(0).forEach(w => w.unmount()); vi.useRealTimers() })
async function setup(role: UserRole = 'Manager', configure?: (api: ReturnType<typeof createMockApi>) => void, path = '/opportunity-board') {
  const api = createMockApi({ role, latency: 0 })
  api.getOpportunityFilters = vi.fn(async () => response(boardFiltersFixture()))
  api.queryOpportunities = vi.fn(async () => boardResultFixture())
  api.listOpportunityQueries = vi.fn(async () => response({ items: [] }))
  api.saveOpportunityQuery = vi.fn(async input => response({ id: 'saved-1', modified: '2026-09-22T00:00:00Z', ...input }))
  api.deleteOpportunityQuery = vi.fn(async id => response({ id, status: 'Deleted' as const }))
  configure?.(api)
  const pinia = createPinia(), router = createAppRouter()
  await router.push(path); await router.isReady()
  const wrapper = mount(OpportunityBoardPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  mounted.push(wrapper); await flushPromises()
  return { wrapper, api, app: useAppStore(pinia), router }
}
async function settle() { await new Promise(resolve => setTimeout(resolve, 340)); await flushPromises() }
describe('Opportunities board', () => {
  it('runs a shared query with its version and permits only saving an independent copy', async () => {
    const item = { ...savedQueryFixture(), owner: 'author@example.invalid', readOnly: true, recipients: [] }
    item.definition.scope.sales = ['alice@example.invalid', 'bob@example.invalid']
    const { wrapper, api } = await setup('Sales', api => { api.listOpportunityQueries = vi.fn(async () => response({ items: [item] })) })
    await wrapper.get('[data-saved-select]').setValue(item.id); await settle()
    expect(wrapper.get('[data-shared-readonly]').text()).toContain(item.owner)
    expect(wrapper.find('[data-update-query]').exists()).toBe(false)
    expect(wrapper.find('[data-delete-query]').exists()).toBe(false)
    expect(wrapper.find('[data-share-query]').exists()).toBe(false)
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ savedQuery: { id: item.id, modified: item.modified } }))
    await wrapper.get('[data-save-new]').trigger('click'); await wrapper.get('[data-query-name]').setValue('Independent')
    await wrapper.get('dialog[open] form').trigger('submit'); await flushPromises()
    expect(api.saveOpportunityQuery).toHaveBeenCalledWith(expect.objectContaining({ name: 'Independent',
      savedQuery: { id: item.id, modified: item.modified }, definition: expect.objectContaining({ scope: item.definition.scope }),
    }), undefined, undefined)
  })
  it('revokes recipients with the current version and reloads an updated saved query', async () => {
    const item = { ...savedQueryFixture(), readOnly: false, recipients: ['recipient@example.invalid'] }
    const { wrapper, api } = await setup('Manager', api => {
      api.listOpportunityQueries = vi.fn(async () => response({ items: [item] }))
      api.getQueryRecipients = vi.fn(async () => response({ items: [{ value: item.recipients[0], label: 'Recipient' }] }))
      api.shareOpportunityQuery = vi.fn(async (_id, recipients) => response({ ...item, recipients, modified: '2026-10-05T00:00:00Z' }))
    })
    await wrapper.get('[data-saved-select]').setValue(item.id)
    await wrapper.get('[data-share-query]').trigger('click'); await flushPromises()
    await wrapper.get('dialog[open] input[type="checkbox"]').setValue(false)
    await wrapper.get('dialog[open] form').trigger('submit'); await flushPromises()
    expect(api.shareOpportunityQuery).toHaveBeenCalledWith(item.id, [], item.modified)
    expect(wrapper.find('dialog[open]').exists()).toBe(false)
    await wrapper.get('[aria-label="刷新个人查询"]').trigger('click'); await flushPromises(); await settle()
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ savedQuery: { id: item.id, modified: item.modified } }))
  })
  it('edits nested groups and preserves their logic when saving a legacy query', async () => {
    const { wrapper, api } = await setup('Manager', api => { api.listOpportunityQueries = vi.fn(async () => response({ items: [savedQueryFixture()] })) })
    await wrapper.get('[data-saved-select]').setValue(savedQueryFixture().id)
    await wrapper.get('[data-add-group]').trigger('click')
    const group = wrapper.get('[data-group-depth="2"]')
    await group.get('[aria-label="条件字段"]').setValue('customerName')
    await group.get('[aria-label="条件值"]').setValue('Acme')
    await group.get('[data-add-nested-group]').trigger('click')
    const inner = group.get('[data-group-depth="3"]')
    expect(inner.find('[data-add-nested-group]').exists()).toBe(false)
    await inner.get('[aria-label="条件字段"]').setValue('createdAt')
    await inner.get('[aria-label="条件值"]').setValue('2026-01-01')
    await settle()
    const sent = vi.mocked(api.queryOpportunities).mock.lastCall![0]
    expect(sent.conditions.at(-1)).toEqual({ match: 'any', conditions: [
      { field: 'customerName', operator: 'contains', value: 'Acme' },
      { match: 'any', conditions: [{ field: 'createdAt', operator: 'after', value: '2026-01-01' }] },
    ] })
    await wrapper.get('[data-save-new]').trigger('click'); await flushPromises()
    await wrapper.get('[data-query-name]').setValue('Nested copy')
    await wrapper.get('dialog[open] form').trigger('submit'); await flushPromises()
    expect(vi.mocked(api.saveOpportunityQuery).mock.lastCall![0].definition.conditions).toEqual(sent.conditions)
  })
  it('only applies a carried period after selecting its business date and preserves return navigation', async () => {
    const { wrapper, api } = await setup('Manager', undefined, '/opportunity-board?period=quarter&reviewAnchor=2026-04-10')
    expect(vi.mocked(api.queryOpportunities).mock.lastCall![0]).not.toHaveProperty('periodFilter')
    expect(wrapper.text()).toContain('当前未限制日期')
    await wrapper.get('[data-period-field]').setValue('poDate'); await settle()
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ periodFilter: { field: 'poDate', kind: 'quarter', anchor: '2026-04-10' } }))
    expect(wrapper.get('[data-period-range]').text()).toContain('2026-04-01 – 2026-06-30')
    await wrapper.get('[data-query-anchor]').setValue('2031-12-31'); await settle()
    expect(wrapper.get('a[href^="/dashboard"]').attributes('href')).toContain('anchor=2026-04-10')
    await wrapper.get('[data-period-field]').setValue(''); await settle()
    expect(vi.mocked(api.queryOpportunities).mock.lastCall![0]).not.toHaveProperty('periodFilter')
  })
  it.each<UserRole>(['Manager', 'Sales', 'Engineer'])('renders real HTTP rows and full-result summary for %s', async role => {
    const { wrapper, api } = await setup(role)
    const result = boardResultFixture()
    expect(wrapper.findAll('[data-opportunity]')).toHaveLength(result.data.items.length)
    expect(wrapper.get('.board-total').text()).toContain(String(result.data.summary.count))
    expect(api.queryOpportunities).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 25, conditions: [] }))
    expect(wrapper.find('a[href^="/dashboard"]').exists()).toBe(role === 'Manager')
  })
  it('keeps missing amounts and backend stage flags distinct from zero / raw days', async () => {
    const { wrapper } = await setup('Manager', api => {
      const result = boardResultFixture()
      result.data.items = [
        { ...result.data.items[0], id: 'closed', stage: 'po_received', stageAgeDays: 99, stageUnchangedOver21Days: false, amountCny: null },
        { ...result.data.items[0], id: 'open', stageAgeDays: 22, stageUnchangedOver21Days: true },
      ]
      api.queryOpportunities = vi.fn(async () => result)
    })
    expect(wrapper.get('[data-opportunity="closed"] .col-amountCny').text()).toBe('—')
    expect(wrapper.get('[data-opportunity="closed"] .col-stageChangedAt').classes()).not.toContain('stage-warning')
    expect(wrapper.get('[data-opportunity="open"] .col-stageChangedAt').classes()).toContain('stage-warning')
    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('.board-table-note').text()).toContain('unweighted opportunity estimates')
  })
  it('does not send incomplete conditions; quick presets and OR reach the API', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-add-condition]').trigger('click'); await settle()
    expect(api.queryOpportunities).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.board-validation').text()).toContain('至少选择')
    await wrapper.get('[data-preset="stalled"]').trigger('click')
    await wrapper.get('.board-segmented button:last-child').trigger('click'); await settle()
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ match: 'any', conditions: [
      { field: 'stage', operator: 'in', value: ['demo_done'] }, { field: 'stageAgeDays', operator: 'gt', value: 21 },
    ] }))
  })
  it('ignores a superseded request even if it resolves while the next query is debouncing', async () => {
    const { wrapper, api } = await setup()
    let finish!: (value: ReturnType<typeof boardResultFixture>) => void
    vi.mocked(api.queryOpportunities).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('[data-preset="demo"]').trigger('click'); await settle()
    await wrapper.get('[data-preset="s6"]').trigger('click')
    const stale = boardResultFixture(); stale.data.items[0].customerName = 'STALE RESPONSE'
    finish(stale); await flushPromises()
    expect(wrapper.text()).not.toContain('STALE RESPONSE')
    await settle()
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ conditions: [{ field: 'stage', operator: 'in', value: ['internal_validation'] }] }))
  })
  it('lists region options as the territory tree, indented, and sends the territory that is chosen', async () => {
    const { wrapper, api } = await setup('Manager', api => {
      api.getOpportunityFilters = vi.fn(async () => response({
        ...boardFiltersFixture(), regionReady: true,
        regions: ['World', 'Asia', 'China', 'East China', 'Taiwan'].map(value => ({ value, label: value })), regionParents: { Asia: 'World', China: 'Asia', 'East China': 'China' },
      }))
    })
    const scope = wrapper.get('.scope-item')
    const options = scope.findAll('.board-options label')
    expect(options.map(option => option.text())).toEqual(['全球', '亚洲', '中国', '华东', 'Taiwan'])
    expect(options.map(option => option.get('span').attributes('style') ?? '')).toEqual(['', 'padding-left: 14px;', 'padding-left: 28px;', 'padding-left: 42px;', ''])
    await options[2].get('input').setValue(true); await settle()
    // The chosen territory reads without its indent in the closed control.
    expect(scope.get('summary').text()).toContain('中国')
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ scope: expect.objectContaining({ regions: ['China'] }) }))
  })
  it('disables unavailable regions, including restored saved-query grouping', async () => {
    const { wrapper, api } = await setup('Manager', api => {
      api.getOpportunityFilters = vi.fn(async () => response({ ...boardFiltersFixture(), regions: [], regionReady: false }))
      api.listOpportunityQueries = vi.fn(async () => response({ items: [{ ...savedQueryFixture(), id: 'old-region', definition: { ...defaultDefinition(), groupBy: 'region' as const } }] }))
    })
    expect(wrapper.get('.scope-item summary').attributes('aria-disabled')).toBe('true')
    await wrapper.get('[data-saved-select]').setValue('old-region'); await settle()
    expect(wrapper.get('.board-validation').text()).toContain('区域数据尚未就绪')
    expect(api.queryOpportunities).toHaveBeenCalledTimes(1)
  })
  it('saves literal names and updates/deletes with the saved version', async () => {
    const { wrapper, api } = await setup()
    await wrapper.get('[data-save-new]').trigger('click')
    await wrapper.get('[data-query-name]').setValue('<x> Demo')
    await wrapper.get('.board-dialog[open] form').trigger('submit'); await flushPromises()
    expect(api.saveOpportunityQuery).toHaveBeenCalledWith(expect.objectContaining({ name: '<x> Demo', definition: expect.not.objectContaining({ page: expect.anything() }) }), undefined, undefined)
    expect(wrapper.find('x').exists()).toBe(false)
    expect(wrapper.get('[data-saved-select]').text()).toContain('<x> Demo')
    await wrapper.get('[data-update-query]').trigger('click')
    await wrapper.get('[data-query-name]').setValue('Renamed')
    await wrapper.get('.board-dialog[open] form').trigger('submit'); await flushPromises()
    expect(api.saveOpportunityQuery).toHaveBeenLastCalledWith(expect.objectContaining({ name: 'Renamed' }), 'saved-1', '2026-09-22T00:00:00Z')
    await wrapper.get('[data-delete-query]').trigger('click')
    await wrapper.get('.board-dialog[open] form').trigger('submit'); await flushPromises()
    expect(api.deleteOpportunityQuery).toHaveBeenCalledWith('saved-1', '2026-09-22T00:00:00Z')
    expect(wrapper.get('[data-saved-select]').text()).not.toContain('Renamed')
  })
  it('keeps the save dialog open on version conflict', async () => {
    const { wrapper } = await setup('Manager', api => {
      api.saveOpportunityQuery = vi.fn(async () => { throw new CrmApiError('VERSION_CONFLICT', 'Changed', 'test') })
    })
    await wrapper.get('[data-save-new]').trigger('click'); await wrapper.get('[data-query-name]').setValue('Demo')
    await wrapper.get('.board-dialog[open] form').trigger('submit'); await flushPromises()
    expect(wrapper.get('dialog[open]').text()).toContain('其他位置更新')
  })
  it('uses server field errors and never leaves stale totals after query failure', async () => {
    const { wrapper, api } = await setup()
    vi.mocked(api.queryOpportunities).mockRejectedValueOnce(new CrmApiError('VALIDATION_ERROR', 'Invalid condition', 'req-error', false, { 'conditions[0].value': 'Not an allowed stage' }))
    await wrapper.get('[data-preset="demo"]').trigger('click'); await settle()
    expect(wrapper.get('[role="alert"]').text()).toContain('conditions[0].value')
    expect(wrapper.find('.board-total').exists()).toBe(false)
  })
  it('clears private rows and saved queries immediately on permission revocation', async () => {
    const { wrapper, app } = await setup()
    app.bootstrap!.capabilities = []
    await flushPromises()
    expect(wrapper.findAll('[data-opportunity]')).toHaveLength(0)
    expect(wrapper.text()).toContain('没有商机查看权限')
  })
  it('changes grouping and sorting on the server but columns only locally', async () => {
    const { wrapper, api } = await setup()
    const before = vi.mocked(api.queryOpportunities).mock.calls.length
    await wrapper.get('.board-columns input').setValue(false)
    await settle()
    expect(api.queryOpportunities).toHaveBeenCalledTimes(before)
    await wrapper.get('[data-group-by]').setValue('sales'); await settle()
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ groupBy: 'sales', page: 1 }))
  })

  it('sends the incoming single-value scope with the first query and keeps it through an identity reset', async () => {
    const { wrapper, api, app } = await setup('Manager', undefined, '/opportunity-board?period=quarter&reviewAnchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Aconca')
    const scope = { sales: ['alice'], regions: ['East China'], markets: ['Frontend'], equipment: ['Aconca'] }
    expect(api.queryOpportunities).toHaveBeenCalledTimes(1)
    expect(api.queryOpportunities).toHaveBeenNthCalledWith(1, expect.objectContaining({ scope, conditions: [] }))
    // The Review period is navigation context only: the board query itself has no period.
    expect(vi.mocked(api.queryOpportunities).mock.calls[0][0]).not.toHaveProperty('period')
    expect(vi.mocked(api.queryOpportunities).mock.calls[0][0]).not.toHaveProperty('reviewAnchor')
    const tail = 'sales=alice&market=Frontend&region=East+China&equipment=Aconca'
    expect(wrapper.get('a[href^="/dashboard"]').attributes('href')).toBe(`/dashboard?period=quarter&anchor=2026-07-01&${tail}`)
    expect(wrapper.get('a[href^="/plan"]').attributes('href')).toBe(`/plan?period=quarter&anchor=2026-10-01&reviewAnchor=2026-07-01&${tail}`)
    expect(wrapper.get('a[href^="/warnings"]').attributes('href')).toBe(`/warnings?period=quarter&anchor=2026-07-01&${tail}`)
    app.identityRevision += 1; await flushPromises()
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ scope }))
  })

  it('withholds the other tabs while a dimension holds two values, and resumes once one value or all is chosen', async () => {
    const { wrapper, api } = await setup('Manager', undefined, '/opportunity-board?period=month&reviewAnchor=2026-09-01&region=East+China')
    const region = () => wrapper.findAll('.scope-item')[0]
    const order = ['East China', 'South China', 'West China', 'North China', 'Central China']
    const regionBox = (value: string) => region().findAll('.board-options input[type="checkbox"]')[order.indexOf(value)]
    await regionBox('South China').setValue(true); await settle()
    expect(api.queryOpportunities).toHaveBeenLastCalledWith(expect.objectContaining({ scope: expect.objectContaining({ regions: ['East China', 'South China'] }) }))
    // Not an unfiltered link: the tabs are unavailable and the page says why.
    expect(wrapper.findAll('.board-navigation a').map(tab => tab.attributes('href'))).toEqual(['/approvals'])
    expect(wrapper.findAll('.board-navigation [aria-disabled="true"]').map(tab => tab.text())).toEqual(['Review', 'Plan', 'Warnings'])
    expect(wrapper.get('[data-scope-blocked]').text()).toContain('区域')
    setLocale('en-US'); await flushPromises()
    expect(wrapper.get('[data-scope-blocked]').text()).toContain('Select one value or All for Region')
    await regionBox('East China').setValue(false); await settle()
    expect(wrapper.find('[data-scope-blocked]').exists()).toBe(false)
    expect(wrapper.get('a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=month&anchor=2026-09-01&region=South+China')
    expect(wrapper.get('a[href^="/plan"]').attributes('href')).toBe('/plan?period=month&anchor=2026-10-01&reviewAnchor=2026-09-01&region=South+China')
    await regionBox('North China').setValue(true); await settle()
    expect(wrapper.findAll('.board-navigation a').map(tab => tab.attributes('href'))).toEqual(['/approvals'])
    await region().get('.board-options button').trigger('click'); await settle()
    expect(wrapper.get('a[href^="/dashboard"]').attributes('href')).toBe('/dashboard?period=month&anchor=2026-09-01')
  })

  it('keeps the navigation context when the board fails to load', async () => {
    const { wrapper } = await setup('Manager', api => { api.getOpportunityFilters = vi.fn().mockRejectedValue(new Error('network down')) }, '/opportunity-board?period=year&reviewAnchor=2026-01-01&market=Frontend')
    expect(wrapper.get('[role="alert"]').text()).toContain('network down')
    expect(wrapper.get('a[href^="/plan"]').attributes('href')).toBe('/plan?period=year&anchor=2027-01-01&reviewAnchor=2026-01-01&market=Frontend')
  })

  it('round-trips Review Q3 through Opportunities to Plan Q4 and back to Review Q3', async () => {
    const meta = { requestId: 'cockpit-test', generatedAt: '' }
    const api = createMockApi({ role: 'Manager', latency: 0 })
    api.getReview = vi.fn(async () => ({ data: reviewFixture(), warnings: [], meta }))
    api.getPlan = vi.fn(async () => ({ data: planFixture(), warnings: [], meta }))
    api.getPlanDetails = vi.fn(async () => ({ data: planDetailsFixture(), warnings: [], meta }))
    api.getOpportunityFilters = vi.fn(async () => response(boardFiltersFixture()))
    api.queryOpportunities = vi.fn(async () => boardResultFixture())
    api.listOpportunityQueries = vi.fn(async () => response({ items: [] }))
    const router = createAppRouter()
    const visit = async (component: typeof ReviewPage | typeof PlanPage | typeof OpportunityBoardPage, path: string) => {
      await router.push(path); await router.isReady()
      const wrapper = mount(component, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
      mounted.push(wrapper); await flushPromises()
      return wrapper
    }
    const scope = { sales: 'alice', market: 'Frontend', region: 'East China', equipment: 'Aconca' }
    const start = '/dashboard?period=quarter&anchor=2026-07-01&sales=alice&market=Frontend&region=East+China&equipment=Aconca'
    const review = await visit(ReviewPage, start)
    expect(api.getReview).toHaveBeenNthCalledWith(1, { period: 'quarter', anchor: '2026-07-01', ...scope })
    const board = await visit(OpportunityBoardPage, review.get('a[href^="/opportunity-board"]').attributes('href')!)
    expect(api.queryOpportunities).toHaveBeenNthCalledWith(1, expect.objectContaining({ scope: { sales: ['alice'], regions: ['East China'], markets: ['Frontend'], equipment: ['Aconca'] } }))
    const plan = await visit(PlanPage, board.get('a[href^="/plan"]').attributes('href')!)
    expect(api.getPlan).toHaveBeenNthCalledWith(1, { period: 'quarter', anchor: '2026-10-01', ...scope })
    const back = plan.get('.view-tabs a[href^="/dashboard"]').attributes('href')!
    expect(back).toBe(start)
    await visit(ReviewPage, back)
    expect(api.getReview).toHaveBeenNthCalledWith(2, { period: 'quarter', anchor: '2026-07-01', ...scope })
  })
})


it('keeps original-currency amounts display-only because the API sorts CNY only', async () => {
  const { wrapper, api } = await setup()
  const input = wrapper.findAll('.board-columns label').find(label => label.text() === '原币金额')!.get('input')
  await input.setValue(true)
  const header = wrapper.findAll('th').find(th => th.text() === '原币金额')!
  expect(header.find('button').exists()).toBe(false)
  await settle()
  expect(api.queryOpportunities).toHaveBeenCalledTimes(1)
})

