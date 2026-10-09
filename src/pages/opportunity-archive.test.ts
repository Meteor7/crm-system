import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { CrmApiError } from '@/api'
import { withAccountSites } from '@/features/accounts/mock-account-sites'
import { createMockApi } from '@/api/mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'
import type { LossReviewDto, OpportunityInternalValidationDto, StrategyOpportunityDto } from '@/types/workspaces'
import OpportunityListView from '@/features/opportunities/OpportunityListView.vue'
import OpportunityDetailPage from './OpportunityDetailPage.vue'

async function context(role: UserRole, path: string) {
  const api = await withAccountSites(createMockApi({ latency: 0, role, userName: role === 'Sales' ? 'Demo Staff 01' : '演示员工24' }))
  const pinia = createPinia()
  const bootstrap = (await api.getBootstrap()).data
  useAppStore(pinia).bootstrap = bootstrap
  const router = createAppRouter()
  await router.push(path)
  await router.isReady()
  return { api, pinia, router, user: bootstrap.user }
}

function archived(opportunity: StrategyOpportunityDto, by: string): StrategyOpportunityDto {
  return { ...opportunity, archived: true, archivedAt: '2026-10-07T04:00:00Z', archivedBy: by }
}

async function detail(role: UserRole, shown?: StrategyOpportunityDto, prepare?: (api: ReturnType<typeof createMockApi>) => void) {
  const { api, pinia, router, user } = await context(role, '/opportunities/OPP-001')
  if (shown) vi.spyOn(api, 'getStrategyOpportunity').mockResolvedValue({ data: shown, warnings: [] })
  prepare?.(api)
  const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { api, router, user, wrapper }
}

// Every control that writes the Opportunity or adds a record to it.
const WRITES = ['edit-opportunity', 'new-opportunity-action', 'new-opportunity-stakeholder', 'mark-opportunity-lost', 'create-quotation-from-opportunity', 'opportunity-rfq-center-link', 'new-status']

afterEach(() => vi.restoreAllMocks())

describe('Opportunity archive', () => {
  it('lets a Manager archive an Opportunity from its page, which then is read-only with the notice and the restore, and restore it', async () => {
    const { api, router, user, wrapper } = await detail('Manager')
    const opportunity = (await api.getStrategyOpportunity('OPP-001')).data
    const archive = vi.spyOn(api, 'archiveStrategyOpportunity').mockResolvedValue({ data: archived(opportunity, user.id), warnings: [] })
    expect(wrapper.find('[data-delete-opportunity]').exists()).toBe(false)
    expect(wrapper.find('[data-unarchive-opportunity]').exists()).toBe(false)
    for (const control of ['edit-opportunity', 'new-opportunity-action', 'new-opportunity-stakeholder']) {
      expect(wrapper.find(`[data-testid="${control}"]`).exists(), control).toBe(true)
    }
    expect(wrapper.findAll('[data-action="edit"]').length).toBeGreaterThan(0)

    await wrapper.get('[data-archive-opportunity]').trigger('click')
    await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-label')).toBe('归档商机')
    expect(dialog.text()).toContain(opportunity.title)
    expect(dialog.text()).toContain('全部保留')
    expect(dialog.text()).not.toContain('删除')
    expect(dialog.get('[data-modal-submit]').text()).toBe('归档')
    expect(dialog.get('[data-modal-submit]').classes()).toContain('danger-action')
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(archive).toHaveBeenCalledWith('OPP-001')
    expect(router.currentRoute.value.path).toBe('/opportunities/OPP-001')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    const notice = wrapper.get('[data-archived-notice]').text()
    expect(notice).toContain('已归档')
    expect(notice).toContain(user.name)
    expect(notice).toContain('取消归档后恢复')
    expect(wrapper.find('[data-archive-opportunity]').exists()).toBe(false)
    for (const control of WRITES) expect(wrapper.find(`[data-testid="${control}"]`).exists(), control).toBe(false)
    expect(wrapper.findAll('.path-actions button')).toHaveLength(0)
    expect(wrapper.findAll('[data-action="edit"], [data-action="delete"]')).toHaveLength(0)
    // What is read stays: the documents link, the stakeholders and the actions.
    expect(wrapper.find('[data-testid="opportunity-documents-link"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-stakeholder-name]')).toHaveLength(opportunity.stakeholders.length)
    expect(wrapper.findAll('[data-action-title]')).toHaveLength(opportunity.actions.length)

    const restore = vi.spyOn(api, 'unarchiveStrategyOpportunity').mockResolvedValue({ data: { ...opportunity, archived: false }, warnings: [] })
    await wrapper.get('[data-unarchive-opportunity]').trigger('click')
    await flushPromises()
    expect(restore).toHaveBeenCalledWith('OPP-001')
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.find('[data-unarchive-opportunity]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-opportunity]').exists()).toBe(true)
    for (const control of ['edit-opportunity', 'new-opportunity-action', 'new-opportunity-stakeholder']) {
      expect(wrapper.find(`[data-testid="${control}"]`).exists(), control).toBe(true)
    }
  })

  it('takes the recovery plan and the action its owner records with the archive', async () => {
    // A downgrade with a plan still open, recorded by the owner (the mock lets the owner alone set the level).
    const salesRepository = createMemorySalesRepository()
    const stored = salesRepository.snapshot.opportunities.find((row) => row.id === 'OPP-001')!
    stored.probabilityLevel = 'committed'
    stored.probabilityHistory = []
    const owner = createMockApi({ latency: 0, salesRepository, role: 'Sales', userName: 'Demo Staff 01' })
    const downgraded = (await owner.updateStrategyOpportunity(stored.id, {
      probabilityLevel: 'upside', probabilityReason: 'Budget delayed', probabilityActionPlan: 'Meet procurement',
    }, stored.modified)).data
    const recovery = downgraded.probabilityHistory[0]!

    // The owner edits the plan and records the action taken while the Opportunity is active, and does neither once
    // it is archived, the plan still read.
    async function ownerPage() {
      const ownerPinia = createPinia()
      useAppStore(ownerPinia).bootstrap = (await owner.getBootstrap()).data
      const ownerRouter = createAppRouter()
      await ownerRouter.push('/opportunities/OPP-001')
      await ownerRouter.isReady()
      const page = mount(OpportunityDetailPage, { props: { apiClient: owner }, global: { plugins: [ownerPinia, ownerRouter] } })
      await flushPromises()
      return page
    }
    const active = await ownerPage()
    expect(active.find(`[data-recovery-edit="${recovery.id}"]`).exists()).toBe(true)
    expect(active.find(`[data-recovery-act="${recovery.id}"]`).exists()).toBe(true)
    active.unmount()
    const read = vi.spyOn(owner, 'getStrategyOpportunity').mockResolvedValue({ data: archived(downgraded, 'manager@example.invalid'), warnings: [] })
    const frozen = await ownerPage()
    expect(frozen.find('[data-archived-notice]').exists()).toBe(true)
    expect(frozen.find('[data-recovery-edit]').exists()).toBe(false)
    expect(frozen.find('[data-recovery-act]').exists()).toBe(false)
    expect(frozen.text()).toContain('Meet procurement')
    frozen.unmount()
    read.mockRestore()

    // A Manager's archive from the page takes the plan's edit away at once.
    const api = createMockApi({ latency: 0, salesRepository, role: 'Manager', userName: '演示员工24' })
    const pinia = createPinia()
    const user = (await api.getBootstrap()).data.user
    useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
    const router = createAppRouter()
    await router.push('/opportunities/OPP-001')
    await router.isReady()
    const wrapper = mount(OpportunityDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()
    const event = downgraded.probabilityHistory[0]!
    expect(wrapper.find(`[data-recovery-edit="${event.id}"]`).exists()).toBe(true)

    vi.spyOn(api, 'archiveStrategyOpportunity').mockResolvedValue({ data: archived(downgraded, user.id), warnings: [] })
    await wrapper.get('[data-archive-opportunity]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(true)
    expect(wrapper.find('[data-recovery-edit]').exists()).toBe(false)
    expect(wrapper.find('[data-recovery-act]').exists()).toBe(false)
    // The downgrade and its plan are still read.
    expect(wrapper.text()).toContain('Meet procurement')
  })

  it('takes every stage action, the internal validation review and the post-mortem link with the archive', async () => {
    const { api } = await context('Manager', '/opportunities/OPP-001')
    const base = (await api.getStrategyOpportunity('OPP-001')).data
    const validation: OpportunityInternalValidationDto = {
      id: 'IV-ARCHIVE', attemptNo: 1, status: 'pending', reason: 'Customer asked for an early slot', expectedPoDate: '2026-11-30',
      booking: { primaryContactId: '', equipment: '', quantity: 1, ddl: '2026-12-31', amount: '100.00', currency: 'CNY', owner: base.owner, note: '' },
      requestedBy: 'requester@example.invalid', requestedAt: '2026-10-06T08:00:00Z', decidedBy: '', decidedAt: '', decisionComment: '',
      bookingId: '', cancelledBy: '', cancelledAt: '', cancelReason: '',
    }
    const review: LossReviewDto = {
      id: 'LR-ARCHIVE', opportunityId: base.id, stageEventId: 'SE-ARCHIVE', lostAt: '2026-10-01T08:00:00Z', lostAtStage: 'quotation_sent',
      lostBy: base.owner, lostReason: 'Budget cut', status: 'pending', reviewNote: '', reviewedBy: null, reviewedAt: null, reopenedAt: null,
      modified: '2026-10-01T08:00:00Z', history: [],
    }
    // Each shape of the deal shows its controls while it is active, and none of them once it is archived.
    const shapes: Array<[StrategyOpportunityDto, string[]]> = [
      [{ ...base, stage: 'demo_done' }, ['confirm-budget-approved', 'rollback-opportunity-stage']],
      [{ ...base, stage: 'customer_budget_approved' }, ['opportunity-rfq-center-link', 'rollback-opportunity-stage']],
      [{ ...base, stage: 'rfq_validated' }, ['create-quotation-from-opportunity', 'rollback-opportunity-stage']],
      [{ ...base, stage: 'quotation_sent', saleType: 'New Equipment', internalValidation: null }, ['request-internal-validation', 'confirm-po', 'rollback-opportunity-stage']],
      [{ ...base, stage: 'quotation_sent', saleType: 'New Equipment', internalValidation: validation }, ['approve-internal-validation', 'reject-internal-validation', 'confirm-po']],
      [{ ...base, stage: 'po_received', liveBooking: null }, ['replace-booking', 'rollback-opportunity-stage']],
      [{ ...base, stage: 'lost', lostAtStage: 'quotation_sent', lossReviews: [review] }, ['[data-loss-review-link]', 'rollback-opportunity-stage']],
    ]
    const selector = (control: string) => control.startsWith('[') ? control : `[data-testid="${control}"]`
    // No Quotation of its own yet, so its creation is offered at the quotation stages.
    const noQuotation = (api: ReturnType<typeof createMockApi>) => {
      vi.spyOn(api, 'listQuotations').mockResolvedValue({ data: { items: [] }, meta: { requestId: 'req-quotations', page: 1, pageSize: 1, total: 0 }, warnings: [] })
    }
    for (const [shape, controls] of shapes) {
      const active = await detail('Manager', shape, noQuotation)
      for (const control of controls) expect(active.wrapper.find(selector(control)).exists(), `${shape.stage}: ${control}`).toBe(true)
      active.wrapper.unmount()
      const frozen = await detail('Manager', archived(shape, 'manager@example.invalid'), noQuotation)
      expect(frozen.wrapper.find('[data-archived-notice]').exists()).toBe(true)
      for (const control of controls) expect(frozen.wrapper.find(selector(control)).exists(), `${shape.stage} archived: ${control}`).toBe(false)
      expect(frozen.wrapper.find('.path-actions').exists(), `${shape.stage} archived: stage actions`).toBe(false)
      frozen.wrapper.unmount()
    }
  })

  it('offers the archive to nobody but a Manager, and shows an archived Opportunity to a Sales user read-only with a notice to ask a Manager', async () => {
    const { api } = await context('Manager', '/opportunities/OPP-001')
    const opportunity = (await api.getStrategyOpportunity('OPP-001')).data

    const sales = await detail('Sales', opportunity)
    expect(sales.wrapper.find('[data-archive-opportunity]').exists()).toBe(false)
    expect(sales.wrapper.find('[data-testid="edit-opportunity"]').exists()).toBe(true)

    const archivedForSales = await detail('Sales', archived(opportunity, 'manager@example.invalid'))
    expect(archivedForSales.wrapper.get('[data-archived-notice]').text()).toContain('请联系经理')
    expect(archivedForSales.wrapper.get('[data-archived-notice]').text()).not.toContain('取消归档后')
    expect(archivedForSales.wrapper.find('[data-unarchive-opportunity]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-archive-opportunity]').exists()).toBe(false)
    for (const control of WRITES) expect(archivedForSales.wrapper.find(`[data-testid="${control}"]`).exists(), control).toBe(false)
    expect(archivedForSales.wrapper.findAll('.path-actions button')).toHaveLength(0)
  })

  it('keeps the page and shows the refusal with its request id when the archive or the restore is refused, and clears it for another Opportunity', async () => {
    const { api, router, wrapper } = await detail('Manager')
    const opportunity = (await api.getStrategyOpportunity('OPP-001')).data
    vi.spyOn(api, 'archiveStrategyOpportunity').mockRejectedValue(new CrmApiError('INVALID_TRANSITION', 'An Opportunity with a Booking that is not cancelled cannot be archived; cancel the Booking first.', 'req-archive-opportunity', false))
    await wrapper.get('[data-archive-opportunity]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.get('[data-archive-error]').text()).toContain('商机还有未取消的 Booking，不能归档；请先取消该 Booking。')
    expect(dialog.get('[data-archive-error]').text()).toContain('请求编号 req-archive-opportunity')
    expect(wrapper.findAll('[data-archive-error]')).toHaveLength(1)
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    expect(router.currentRoute.value.path).toBe('/opportunities/OPP-001')
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    await dialog.get('header button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-opportunity"]').exists()).toBe(true)

    const archivedPage = await detail('Manager', archived(opportunity, 'manager@example.invalid'), (prepared) => {
      vi.spyOn(prepared, 'unarchiveStrategyOpportunity').mockRejectedValue(new CrmApiError('SCOPE_DENIED', 'The Opportunity is outside the current user scope.', 'req-restore-opportunity', false))
    })
    await archivedPage.wrapper.get('[data-unarchive-opportunity]').trigger('click')
    await flushPromises()
    expect(archivedPage.wrapper.get('[data-archive-error]').text()).toContain('req-restore-opportunity')
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(true)
    expect(archivedPage.wrapper.get('[data-unarchive-opportunity]').attributes('disabled')).toBeUndefined()

    // The error belongs to that Opportunity: another one opened in the same page starts clean.
    const other = (await archivedPage.api.listStrategyOpportunities({ pageSize: 2 })).data.items.find((item) => item.id !== 'OPP-001')!
    vi.spyOn(archivedPage.api, 'getStrategyOpportunity').mockResolvedValue({ data: other, warnings: [] })
    await archivedPage.router.push(`/opportunities/${other.id}`)
    await flushPromises()
    expect(archivedPage.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(archivedPage.wrapper.find('[data-archive-opportunity]').exists()).toBe(true)
  })

  it('drops the answer of an archive that arrives after the page moved on to another Opportunity', async () => {
    const { api, router, wrapper } = await detail('Manager')
    const opportunity = (await api.getStrategyOpportunity('OPP-001')).data
    const other = (await api.listStrategyOpportunities({ pageSize: 3 })).data.items.find((item) => item.id !== 'OPP-001')!
    let settle: (value: { data: StrategyOpportunityDto; warnings: never[] }) => void = () => {}
    vi.spyOn(api, 'archiveStrategyOpportunity').mockImplementation(() => new Promise((resolve) => { settle = resolve }))
    await wrapper.get('[data-archive-opportunity]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    vi.spyOn(api, 'getStrategyOpportunity').mockResolvedValue({ data: other, warnings: [] })
    await router.push(`/opportunities/${other.id}`)
    await flushPromises()
    settle({ data: archived(opportunity, 'manager@example.invalid'), warnings: [] })
    await flushPromises()
    // The answer was OPP-001's: the Opportunity shown keeps its own record and controls.
    expect(wrapper.get('h1').text()).toBe(other.title)
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-opportunity]').exists()).toBe(true)
  })

  it('drops the refusal of a restore that arrives after the page moved on to another archived Opportunity', async () => {
    const { api } = await context('Manager', '/opportunities/OPP-001')
    const opportunity = (await api.getStrategyOpportunity('OPP-001')).data
    const other = (await api.listStrategyOpportunities({ pageSize: 3 })).data.items.find((item) => item.id !== 'OPP-001')!
    let refuse: (reason: unknown) => void = () => {}
    const page = await detail('Manager', archived(opportunity, 'manager@example.invalid'), (prepared) => {
      vi.spyOn(prepared, 'unarchiveStrategyOpportunity').mockImplementation(() => new Promise((_, reject) => { refuse = reject }))
    })
    await page.wrapper.get('[data-unarchive-opportunity]').trigger('click')
    await flushPromises()

    vi.spyOn(page.api, 'getStrategyOpportunity').mockResolvedValue({ data: archived(other, 'manager@example.invalid'), warnings: [] })
    await page.router.push(`/opportunities/${other.id}`)
    await flushPromises()
    refuse(new CrmApiError('SCOPE_DENIED', 'The Opportunity is outside the current user scope.', 'req-late-restore', false))
    await flushPromises()
    // The refusal was OPP-001's restore: the archived Opportunity shown is told nothing of it.
    expect(page.wrapper.get('h1').text()).toBe(other.title)
    expect(page.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(page.wrapper.find('[data-unarchive-opportunity]').exists()).toBe(true)
  })

  it('lists active Opportunities by default, the archived ones through the filter kept in the URL, marked', async () => {
    const { api, pinia, router } = await context('Manager', '/opportunities')
    const [first, second] = (await api.listStrategyOpportunities({ pageSize: 2 })).data.items
    const archivedSecond = archived(second!, 'manager@example.invalid')
    const list = vi.spyOn(api, 'listStrategyOpportunities').mockImplementation(async (query = {}) => {
      const items = query.archiveState === 'archived' ? [archivedSecond] : query.archiveState === 'all' ? [first!, archivedSecond] : [first!]
      return { data: { items }, meta: { requestId: 'req-list', page: 1, pageSize: 12, total: items.length }, warnings: [] }
    })
    const wrapper = mount(OpportunityListView, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active' }))
    expect(wrapper.findAll('[data-opportunity-id]').map((row) => row.attributes('data-opportunity-id'))).toEqual([first!.id])
    expect(wrapper.find('[data-opportunity-archived]').exists()).toBe(false)

    await wrapper.get('[aria-label="归档状态"]').setValue('archived')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'archived', page: 1 }))
    expect(router.currentRoute.value.query.archive).toBe('archived')
    expect(wrapper.findAll('[data-opportunity-id]').map((row) => row.attributes('data-opportunity-id'))).toEqual([second!.id])
    expect(wrapper.get(`[data-opportunity-archived="${second!.id}"]`).text()).toBe('已归档')

    await wrapper.get('[aria-label="归档状态"]').setValue('all')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'all' }))
    expect(wrapper.findAll('[data-opportunity-id]')).toHaveLength(2)
    expect(wrapper.findAll('[data-opportunity-archived]')).toHaveLength(1)

    // The filter comes back from the URL, and the reset puts it back to the active ones.
    await router.push('/opportunities?archive=archived')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'archived' }))
    expect((wrapper.get('[aria-label="归档状态"]').element as HTMLSelectElement).value).toBe('archived')
    await wrapper.get('[aria-label="归档状态"]').setValue('all')
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '重置条件')!.trigger('click')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active' }))
    expect(router.currentRoute.value.query.archive).toBeUndefined()
  })

  it('marks an archived Opportunity on the board as in the list', async () => {
    const { api, pinia, router } = await context('Manager', '/opportunities?layout=board&archive=all')
    const [first, second] = (await api.listStrategyOpportunities({ pageSize: 2 })).data.items
    const archivedSecond = archived({ ...second!, stage: first!.stage }, 'manager@example.invalid')
    const list = vi.spyOn(api, 'listStrategyOpportunities').mockImplementation(async (query = {}) => {
      const items = query.archiveState === 'all' ? [first!, archivedSecond] : [first!]
      return { data: { items }, meta: { requestId: 'req-board', page: 1, pageSize: 200, total: items.length }, warnings: [] }
    })
    const wrapper = mount(OpportunityListView, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(list).toHaveBeenCalledWith(expect.objectContaining({ archiveState: 'all', stageSummary: true }))
    expect(wrapper.get(`.board-card-topline [data-opportunity-archived="${second!.id}"]`).text()).toBe('已归档')
    expect(wrapper.find(`[data-opportunity-archived="${first!.id}"]`).exists()).toBe(false)
  })
})
