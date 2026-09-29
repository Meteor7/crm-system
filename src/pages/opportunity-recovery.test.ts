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
import ProbabilityRecoveryPanel from '@/features/opportunities/ProbabilityRecoveryPanel.vue'

async function setup(legacy = false) {
  const salesRepository = createMemorySalesRepository()
  const stored = salesRepository.snapshot.opportunities.find(row => row.id === 'OPP-001')!
  stored.probabilityLevel = 'committed'
  stored.probabilityHistory = []
  const options = { latency: 0, salesRepository, role: 'Sales' as const, userName: 'Demo Staff 01' }
  const api = createMockApi(options)
  const opportunity = (await api.updateStrategyOpportunity(stored.id, {
    probabilityLevel: 'upside', probabilityReason: 'Budget delayed', probabilityActionPlan: 'Meet procurement',
  }, stored.modified)).data
  if (legacy) stored.probabilityHistory[0]!.recovery = null
  const pinia = createPinia(), app = useAppStore(pinia)
  app.bootstrap = (await api.getBootstrap()).data
  const router = createAppRouter()
  await router.push(`/opportunities/${stored.id}`)
  await router.isReady()
  const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  const event = opportunity.probabilityHistory[0]!
  const open = async () => { await wrapper.get(`[data-recovery-edit="${event.id}"]`).trigger('click') }
  const submit = async () => { await wrapper.get('[data-modal-submit]').trigger('submit'); await flushPromises() }
  return { api, app, pinia, router, wrapper, opportunity, event, open, submit, options, stored }
}

describe('Opportunity recovery plans in the detail page', () => {
  afterEach(() => setLocale('zh-CN'))

  it('requires an actual action, clears only its warning and keeps its audit visible', async () => {
    const { wrapper, submit, event, api } = await setup()
    await wrapper.get('[data-recovery-act]').trigger('click')
    await submit()
    expect(wrapper.get('[role="alert"]').text()).toContain('请填写已经采取的行动')
    await wrapper.get('[data-recovery-draft]').setValue('已与采购开会确认预算时间')
    await submit()
    expect(wrapper.get(`[data-recovery-state="${event.id}"]`).text()).toBe('已记录行动 · 提醒已清除')
    expect(wrapper.find('[data-recovery-act]').exists()).toBe(false)
    expect(wrapper.get('.action-record').text()).toContain('已与采购开会确认预算时间')
    expect(wrapper.get('.plan-history').text()).toContain('Meet procurement')
    expect((await api.getStrategyOpportunity('OPP-001')).data.probabilityHistory[0]!.reason).toBe('Budget delayed')
    wrapper.unmount()
  })

  it('uses notification and Review deep links to highlight the exact downgrade', async () => {
    const { wrapper, router, event } = await setup()
    await router.push({ path: '/opportunities/OPP-001', query: { probabilityEvent: event.id } })
    await flushPromises()
    expect(wrapper.get(`[data-probability-history-id="${event.id}"]`).classes()).toContain('highlighted')
    wrapper.unmount()
  })

  it('reloads a concurrently handled action without overwriting or recording it twice', async () => {
    const { wrapper, submit, options, opportunity, event, api } = await setup()
    await wrapper.get('[data-recovery-act]').trigger('click')
    await wrapper.get('[data-recovery-draft]').setValue('My pending note')
    await createMockApi(options).recordProbabilityRecoveryAction(opportunity.id, event.id, {
      actionTaken: 'Already recorded in another browser', recoveryModified: event.recovery!.modified,
    }, opportunity.modified!)
    await submit()
    expect((wrapper.get('[data-recovery-draft]').element as HTMLTextAreaElement).value).toBe('My pending note')
    await wrapper.get('[data-recovery-reload]').trigger('click'); await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('.action-record').text()).toContain('Already recorded in another browser')
    expect((await api.getStrategyOpportunity(opportunity.id)).data.probabilityHistory[0]!.recovery!.history.filter(row => row.kind === 'ActionRecorded')).toHaveLength(1)
    wrapper.unmount()
  })

  it('lets a Manager edit a plan but leaves actual-action recording to the owner', async () => {
    const { wrapper, options, api, app } = await setup()
    app.bootstrap = (await createMockApi({ ...options, role: 'Manager', userName: undefined }).getBootstrap()).data
    app.identityRevision++
    await flushPromises()
    expect(wrapper.find('[data-recovery-edit]').exists()).toBe(true)
    expect(wrapper.find('[data-recovery-act]').exists()).toBe(false)
    expect((await api.getStrategyOpportunity('OPP-001')).data.probabilityHistory[0]!.recovery!.state).toBe('pending')
    wrapper.unmount()
  })

  it('edits and displays an audited plan without adding a probability change', async () => {
    const { wrapper, open, submit, api, event } = await setup()
    await open()
    expect(wrapper.get('[role="dialog"]').text()).toContain('保存计划不代表已经采取行动')
    await wrapper.get('[data-recovery-draft]').setValue('Meet the technical buyer')
    await submit()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get(`[data-recovery-plan="${event.id}"]`).text()).toBe('Meet the technical buyer')
    expect(wrapper.get('.plan-history').text()).toContain('Meet procurement')
    const current = (await api.getStrategyOpportunity('OPP-001')).data
    expect(current.probabilityHistory).toHaveLength(1)
    expect(current.probabilityHistory[0]!.recovery!.history).toHaveLength(2)
    wrapper.unmount()
  })

  it('allows explicit legacy backfill and keeps the original downgrade reason', async () => {
    const { wrapper, open, submit, api } = await setup(true)
    expect(wrapper.text()).toContain('这次历史降档尚未登记补救计划')
    await open()
    await wrapper.get('[data-recovery-draft]').setValue('Follow up tomorrow')
    await submit()
    expect((await api.getStrategyOpportunity('OPP-001')).data.probabilityHistory[0]).toMatchObject({
      reason: 'Budget delayed', recovery: { plan: 'Follow up tomorrow', history: [{ kind: 'Created' }] },
    })
    wrapper.unmount()
  })

  it('keeps a conflicting draft, reloads the real other-client edit and retries with its version', async () => {
    const { wrapper, open, submit, api, options, opportunity, event } = await setup()
    await open()
    await wrapper.get('[data-recovery-draft]').setValue('My stale draft')
    const other = createMockApi(options)
    await other.saveProbabilityRecovery(opportunity.id, event.id, {
      plan: 'Another browser edit', recoveryModified: event.recovery!.modified,
    }, opportunity.modified!)
    await submit()
    expect((wrapper.get('[data-recovery-draft]').element as HTMLTextAreaElement).value).toBe('My stale draft')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-recovery-reload]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-recovery-draft]').element as HTMLTextAreaElement).value).toBe('Another browser edit')
    await wrapper.get('[data-recovery-draft]').setValue('Reconciled plan')
    await submit()
    expect((await api.getStrategyOpportunity(opportunity.id)).data.probabilityHistory[0]!.recovery!.history.map(row => row.plan))
      .toEqual(['Reconciled plan', 'Another browser edit', 'Meet procurement'])
    wrapper.unmount()
  })

  it('keeps a failed draft and blocks saving until a failed conflict reload can succeed', async () => {
    const { wrapper, open, submit, api } = await setup()
    await open()
    await wrapper.get('[data-recovery-draft]').setValue('Unsaved text')
    vi.spyOn(api, 'saveProbabilityRecovery').mockRejectedValue(new CrmApiError('VERSION_CONFLICT', 'Reload', 'conflict-id'))
    await submit()
    vi.spyOn(api, 'getStrategyOpportunity').mockRejectedValue(new Error('offline'))
    await wrapper.get('[data-recovery-reload]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-recovery-draft]').element as HTMLTextAreaElement).value).toBe('Unsaved text')
    expect(wrapper.get('[data-modal-submit]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('prevents duplicate submissions while busy and ignores a result after an identity switch', async () => {
    const { wrapper, open, api, app, options, event } = await setup()
    let resolve!: (value: Awaited<ReturnType<typeof api.saveProbabilityRecovery>>) => void
    const pending = new Promise<Awaited<ReturnType<typeof api.saveProbabilityRecovery>>>(done => { resolve = done })
    const save = vi.spyOn(api, 'saveProbabilityRecovery').mockReturnValue(pending)
    await open()
    await wrapper.get('[data-recovery-draft]').setValue('Pending draft')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    await wrapper.get('[data-modal-submit]').trigger('submit')
    expect(save).toHaveBeenCalledTimes(1)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    app.bootstrap = (await createMockApi({ ...options, role: 'Engineer', userName: undefined }).getBootstrap()).data
    app.identityRevision++
    await flushPromises()
    resolve({ data: { ...event.recovery!, plan: 'Stale response' }, meta: { requestId: 'old-identity' }, warnings: [] })
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Stale response')
    expect(wrapper.find('[data-recovery-edit]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('clears the page if a save discovers lost access', async () => {
    const { wrapper, open, submit, api } = await setup()
    await open()
    vi.spyOn(api, 'saveProbabilityRecovery').mockRejectedValue(new CrmApiError('SCOPE_DENIED', 'No access', 'denied'))
    await submit()
    expect(wrapper.find('[data-testid="selected-opportunity"]').exists()).toBe(false)
    expect(wrapper.find('[data-recovery-edit]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('allows a public-account owner with a hidden Site to maintain the non-Site recovery plan', async () => {
    const { wrapper, pinia, opportunity, api } = await setup()
    wrapper.unmount()
    const panel = mount(ProbabilityRecoveryPanel, { props: { opportunity: { ...opportunity, siteRestricted: true, siteId: '', site: '' }, apiClient: api }, global: { plugins: [pinia] } })
    expect(panel.find('[data-recovery-edit]').exists()).toBe(true)
    setLocale('en-US')
    await panel.get('[data-recovery-edit]').trigger('click')
    expect(panel.get('[role="dialog"]').text()).toContain('Saving a plan does not mean an action has been taken.')
    panel.unmount()
  })
})
