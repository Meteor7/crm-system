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
import OpportunityBoardPage from './OpportunityBoardPage.vue'
const response = <T,>(data: T) => ({ data, warnings: [], meta: { requestId: 'board-test' } })
const mounted: VueWrapper[] = []
beforeEach(() => {
  setLocale('zh-CN')
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { mounted.splice(0).forEach(w => w.unmount()); vi.useRealTimers() })
async function setup(role: UserRole = 'Manager', configure?: (api: ReturnType<typeof createMockApi>) => void) {
  const api = createMockApi({ role, latency: 0 })
  api.getOpportunityFilters = vi.fn(async () => response(boardFiltersFixture()))
  api.queryOpportunities = vi.fn(async () => boardResultFixture())
  api.listOpportunityQueries = vi.fn(async () => response({ items: [] }))
  api.saveOpportunityQuery = vi.fn(async input => response({ id: 'saved-1', modified: '2026-09-22T00:00:00Z', ...input }))
  api.deleteOpportunityQuery = vi.fn(async id => response({ id, status: 'Deleted' as const }))
  configure?.(api)
  const pinia = createPinia(), router = createAppRouter()
  await router.push('/opportunity-board'); await router.isReady()
  const wrapper = mount(OpportunityBoardPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  mounted.push(wrapper); await flushPromises()
  return { wrapper, api, app: useAppStore(pinia), router }
}
async function settle() { await new Promise(resolve => setTimeout(resolve, 340)); await flushPromises() }
describe('Opportunities board', () => {
  it.each<UserRole>(['Manager', 'Sales', 'Engineer'])('renders real HTTP rows and full-result summary for %s', async role => {
    const { wrapper, api } = await setup(role)
    const result = boardResultFixture()
    expect(wrapper.findAll('[data-opportunity]')).toHaveLength(result.data.items.length)
    expect(wrapper.get('.board-total').text()).toContain(String(result.data.summary.count))
    expect(api.queryOpportunities).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 25, conditions: [] }))
    expect(wrapper.find('a[href="/dashboard"]').exists()).toBe(role === 'Manager')
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
    await wrapper.get('.board-dialog form').trigger('submit'); await flushPromises()
    expect(api.saveOpportunityQuery).toHaveBeenCalledWith(expect.objectContaining({ name: '<x> Demo', definition: expect.not.objectContaining({ page: expect.anything() }) }), undefined, undefined)
    expect(wrapper.find('x').exists()).toBe(false)
    expect(wrapper.get('[data-saved-select]').text()).toContain('<x> Demo')
    await wrapper.get('[data-update-query]').trigger('click')
    await wrapper.get('[data-query-name]').setValue('Renamed')
    await wrapper.get('.board-dialog form').trigger('submit'); await flushPromises()
    expect(api.saveOpportunityQuery).toHaveBeenLastCalledWith(expect.objectContaining({ name: 'Renamed' }), 'saved-1', '2026-09-22T00:00:00Z')
    await wrapper.get('[data-delete-query]').trigger('click')
    await wrapper.findAll('.board-dialog form')[1].trigger('submit'); await flushPromises()
    expect(api.deleteOpportunityQuery).toHaveBeenCalledWith('saved-1', '2026-09-22T00:00:00Z')
    expect(wrapper.get('[data-saved-select]').text()).not.toContain('Renamed')
  })
  it('keeps the save dialog open on version conflict', async () => {
    const { wrapper } = await setup('Manager', api => {
      api.saveOpportunityQuery = vi.fn(async () => { throw new CrmApiError('VERSION_CONFLICT', 'Changed', 'test') })
    })
    await wrapper.get('[data-save-new]').trigger('click'); await wrapper.get('[data-query-name]').setValue('Demo')
    await wrapper.get('.board-dialog form').trigger('submit'); await flushPromises()
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

