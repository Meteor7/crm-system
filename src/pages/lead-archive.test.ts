import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import type { LeadDto, UserRole } from '@/types/crm'
import LeadListView from '@/features/leads/LeadListView.vue'
import LeadDetailPage from './LeadDetailPage.vue'

async function context(role: UserRole) {
  const api = createMockApi({ latency: 0, role, userName: role === 'Sales' ? 'Demo Staff 01' : '演示员工24' })
  const pinia = createPinia()
  const bootstrap = (await api.getBootstrap()).data
  useAppStore(pinia).bootstrap = bootstrap
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/leads', name: 'leads', component: { template: '<div />' } },
      { path: '/leads/:leadId', name: 'lead-detail', component: { template: '<div />' } },
      { path: '/opportunities', name: 'opportunities', component: { template: '<div />' } },
      { path: '/accounts', name: 'accounts', component: { template: '<div />' } },
      { path: '/accounts/:accountId', name: 'account-detail', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
    ],
  })
  return { api, pinia, router, user: bootstrap.user }
}

function archived(lead: LeadDto, by: string): LeadDto {
  return { ...lead, archived: true, archivedAt: '2026-10-07T02:30:00Z', archivedBy: by }
}

async function detail(role: UserRole, prepare?: (api: ReturnType<typeof createMockApi>, lead: LeadDto) => void) {
  const { api, pinia, router, user } = await context(role)
  const lead = (await api.listLeads({ pageSize: 1 })).data.items[0]!
  prepare?.(api, lead)
  await router.push(`/leads/${lead.id}`)
  const wrapper = mount(LeadDetailPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { api, router, user, lead, wrapper }
}

afterEach(() => vi.restoreAllMocks())

describe('Lead archive', () => {
  it('lets a Manager archive a Lead from its page, which then shows the notice and the restore button, and restore it', async () => {
    const { api, router, user, lead, wrapper } = await detail('Manager')
    const archive = vi.spyOn(api, 'archiveLead').mockResolvedValue({ data: archived(lead, user.id), warnings: [] })
    expect(wrapper.find('[data-delete-lead]').exists()).toBe(false)
    expect(wrapper.find('[data-unarchive-lead]').exists()).toBe(false)
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.get('.status-badges').text()).not.toContain('已归档')

    // The inline forms open at the time of the archive go with the edit buttons.
    await wrapper.get('[data-testid="edit-qualification"]').trigger('click')
    await wrapper.get('[data-testid="add-arrangement"]').trigger('click')
    expect(wrapper.find('[data-testid="save-qualification"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="save-arrangement"]').exists()).toBe(true)

    await wrapper.get('[data-archive-lead]').trigger('click')
    await flushPromises()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-label')).toBe('归档 Lead')
    expect(dialog.text()).toContain(lead.name)
    expect(dialog.text()).toContain('资料全部保留')
    expect(dialog.text()).not.toContain('删除')
    expect(dialog.get('[data-modal-submit]').text()).toBe('归档')
    expect(dialog.get('[data-modal-submit]').classes()).toContain('danger-action')
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(archive).toHaveBeenCalledWith(lead.id)
    expect(router.currentRoute.value.path).toBe(`/leads/${lead.id}`)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    const notice = wrapper.get('[data-archived-notice]').text()
    expect(notice).toContain('已归档')
    expect(notice).toContain(user.name)
    expect(notice).toContain('取消归档后恢复')
    expect(wrapper.get('.status-badges').text()).toContain('已归档')
    expect(wrapper.find('[data-archive-lead]').exists()).toBe(false)
    for (const action of ['edit-lead', 'convert-lead', 'edit-qualification', 'add-arrangement', 'save-qualification', 'save-arrangement']) {
      expect(wrapper.find(`[data-testid="${action}"]`).exists(), action).toBe(false)
    }

    const restore = vi.spyOn(api, 'unarchiveLead').mockResolvedValue({ data: { ...lead, archived: false }, warnings: [] })
    await wrapper.get('[data-unarchive-lead]').trigger('click')
    await flushPromises()
    expect(restore).toHaveBeenCalledWith(lead.id)
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.get('.status-badges').text()).not.toContain('已归档')
    expect(wrapper.find('[data-unarchive-lead]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-lead]').exists()).toBe(true)
    for (const action of ['edit-lead', 'convert-lead', 'edit-qualification', 'add-arrangement']) {
      expect(wrapper.find(`[data-testid="${action}"]`).exists(), action).toBe(true)
    }
  })

  it('offers the archive to nobody but a Manager, and not for a converted Lead', async () => {
    const sales = await detail('Sales')
    expect(sales.wrapper.find('[data-archive-lead]').exists()).toBe(false)
    expect(sales.wrapper.find('[data-testid="edit-lead"]').exists()).toBe(true)

    // A Sales user opening an archived Lead reads the notice, edits nothing and cannot restore it.
    const archivedForSales = await detail('Sales', (api, lead) => {
      vi.spyOn(api, 'getLead').mockResolvedValue({ data: archived(lead, 'manager@example.invalid'), warnings: [] })
    })
    expect(archivedForSales.wrapper.get('[data-archived-notice]').text()).toContain('已归档')
    expect(archivedForSales.wrapper.get('[data-archived-notice]').text()).toContain('请联系经理')
    expect(archivedForSales.wrapper.get('[data-archived-notice]').text()).not.toContain('取消归档后')
    expect(archivedForSales.wrapper.find('[data-unarchive-lead]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-archive-lead]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-testid="edit-lead"]').exists()).toBe(false)
    expect(archivedForSales.wrapper.find('[data-testid="convert-lead"]').exists()).toBe(false)

    // The status alone says converted (its columns cleared): no archive, on a page that is there.
    const converted = await detail('Manager', (api, lead) => {
      vi.spyOn(api, 'getLead').mockResolvedValue({
        data: { ...lead, status: 'Converted', convertedAt: undefined, convertedAccountId: undefined, convertedContactId: undefined, convertedOpportunityId: undefined },
        warnings: [],
      })
    })
    expect(converted.wrapper.text()).toContain(converted.lead.name)
    expect(converted.wrapper.find('[data-archive-lead]').exists()).toBe(false)
    expect(converted.wrapper.find('[data-unarchive-lead]').exists()).toBe(false)

    // A conversion's column left on a Lead whose status is not Converted (a legacy conversion): no archive either, on a
    // page that is there.
    for (const trace of [{ convertedAt: '2026-10-01T08:00:00Z' }, { convertedAccountId: 'ACC-001' }, { convertedContactId: 'CON-001' }, { convertedOpportunityId: 'OPP-001' }]) {
      const traced = await detail('Manager', (api, lead) => {
        vi.spyOn(api, 'getLead').mockResolvedValue({ data: { ...lead, status: 'Qualified', ...trace }, warnings: [] })
      })
      expect(traced.wrapper.text(), JSON.stringify(trace)).toContain(traced.lead.name)
      expect(traced.wrapper.find('[data-archive-lead]').exists(), JSON.stringify(trace)).toBe(false)
    }
  })

  it('keeps the page and shows the refusal with its request id when the archive or the restore is refused', async () => {
    const { api, router, lead, wrapper } = await detail('Manager')
    vi.spyOn(api, 'archiveLead').mockRejectedValue(new CrmApiError('INVALID_TRANSITION', "A converted Lead is part of its Account's history and cannot be archived.", 'req-archive-lead', false))
    await wrapper.get('[data-archive-lead]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.get('[data-archive-error]').text()).toContain('已转换的 Lead 是客户的历史记录，不能归档。')
    expect(dialog.get('[data-archive-error]').text()).toContain('请求编号 req-archive-lead')
    // Shown in the dialog alone, not under the header as well.
    expect(wrapper.findAll('[data-archive-error]')).toHaveLength(1)
    expect(dialog.get('[data-modal-submit]').attributes('disabled')).toBeUndefined()
    expect(router.currentRoute.value.path).toBe(`/leads/${lead.id}`)
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    await dialog.get('header button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(wrapper.find('[data-archive-lead]').exists()).toBe(true)

    const archivedPage = await detail('Manager', (archivedApi, archivedLead) => {
      vi.spyOn(archivedApi, 'getLead').mockResolvedValue({ data: archived(archivedLead, 'manager@example.invalid'), warnings: [] })
      vi.spyOn(archivedApi, 'unarchiveLead').mockRejectedValue(new CrmApiError('SCOPE_DENIED', 'Lead is outside the current user scope.', 'req-restore-lead', false))
    })
    await archivedPage.wrapper.get('[data-unarchive-lead]').trigger('click')
    await flushPromises()
    expect(archivedPage.wrapper.get('[data-archive-error]').text()).toContain('req-restore-lead')
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(true)
    expect(archivedPage.wrapper.get('[data-unarchive-lead]').attributes('disabled')).toBeUndefined()

    // The error belongs to that Lead: another Lead opened in the same page starts clean.
    const another = (await archivedPage.api.listLeads({ pageSize: 2 })).data.items[1]!
    vi.spyOn(archivedPage.api, 'getLead').mockResolvedValue({ data: another, warnings: [] })
    await archivedPage.router.push(`/leads/${another.id}`)
    await flushPromises()
    expect(archivedPage.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(archivedPage.wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(archivedPage.wrapper.find('[data-archive-lead]').exists()).toBe(true)
  })

  it('drops an answer that arrives after the page moved to another Lead', async () => {
    const { api, router, user, lead, wrapper } = await detail('Manager')
    const other = (await api.listLeads({ pageSize: 2 })).data.items.find((item) => item.id !== lead.id)!
    // One resolver per archive sent: the first Lead's, then the other's.
    const pending: Array<{ settle: (value: { data: LeadDto; warnings: never[] }) => void; fail: (reason: unknown) => void }> = []
    vi.spyOn(api, 'archiveLead').mockImplementation(() => new Promise((resolve, reject) => { pending.push({ settle: resolve, fail: reject }) }))
    await wrapper.get('[data-archive-lead]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()

    // The page moves on while the archive is out: the other Lead's button is free at once, before any answer.
    vi.spyOn(api, 'getLead').mockResolvedValue({ data: other, warnings: [] })
    await router.push(`/leads/${other.id}`)
    await flushPromises()
    expect(wrapper.text()).toContain(other.name)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-archive-lead]').attributes('disabled')).toBeUndefined()
    // The other Lead's own archive goes out; the first Lead's answer lands meanwhile and is for the Lead before:
    // it changes nothing here, the other Lead's request still holds the dialog.
    await wrapper.get('[data-archive-lead]').trigger('click')
    await flushPromises()
    await wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(pending).toHaveLength(2)
    pending[0]!.settle({ data: archived(lead, user.id), warnings: [] })
    await flushPromises()
    expect(wrapper.text()).toContain(other.name)
    expect(wrapper.text()).not.toContain(lead.name)
    expect(wrapper.find('[data-archived-notice]').exists()).toBe(false)
    expect(wrapper.get('[role="dialog"] [data-modal-submit]').attributes('disabled')).toBeDefined()
    pending[1]!.settle({ data: archived(other, user.id), warnings: [] })
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('[data-archived-notice]').text()).toContain('已归档')
    expect(wrapper.find('[data-unarchive-lead]').exists()).toBe(true)

    // The same for a refusal that arrives late.
    const again = await detail('Manager')
    let fail!: (reason: unknown) => void
    vi.spyOn(again.api, 'archiveLead').mockImplementation(() => new Promise((_resolve, reject) => { fail = reject }))
    await again.wrapper.get('[data-archive-lead]').trigger('click')
    await flushPromises()
    await again.wrapper.get('[role="dialog"] form').trigger('submit')
    await flushPromises()
    vi.spyOn(again.api, 'getLead').mockResolvedValue({ data: other, warnings: [] })
    await again.router.push(`/leads/${other.id}`)
    await flushPromises()
    fail(new CrmApiError('INVALID_TRANSITION', "A converted Lead is part of its Account's history and cannot be archived.", 'req-late', false))
    await flushPromises()
    expect(again.wrapper.find('[data-archive-error]').exists()).toBe(false)
    expect(again.wrapper.text()).toContain(other.name)
    expect(again.wrapper.get('[data-archive-lead]').attributes('disabled')).toBeUndefined()
  })

  it('lists active Leads by default, the archived ones through the filter, marked and without an edit button', async () => {
    const { api, pinia, router } = await context('Manager')
    const [first, second] = (await api.listLeads({ pageSize: 2 })).data.items
    const archivedSecond = archived(second!, 'manager@example.invalid')
    const list = vi.spyOn(api, 'listLeads').mockImplementation(async (query) => {
      const items = query.archiveState === 'archived' ? [archivedSecond] : query.archiveState === 'all' ? [first!, archivedSecond] : [first!]
      return { data: { items }, meta: { requestId: 'req-list', page: 1, pageSize: 12, total: items.length }, warnings: [] }
    })
    await router.push('/leads')
    const wrapper = mount(LeadListView, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active' }))
    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(1)
    expect(wrapper.find('[data-lead-archived]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="edit-lead"]')).toHaveLength(1)

    await wrapper.get('[aria-label="归档状态"]').setValue('archived')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'archived', page: 1 }))
    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(1)
    expect(wrapper.find(`[data-lead-id="${second!.id}"]`).exists()).toBe(true)
    expect(wrapper.get('[data-lead-archived]').text()).toBe('已归档')
    expect(wrapper.find('[data-testid="edit-lead"]').exists()).toBe(false)

    await wrapper.get('[aria-label="归档状态"]').setValue('all')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'all' }))
    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(2)
    expect(wrapper.findAll('[data-lead-archived]')).toHaveLength(1)

    await wrapper.get('.reset-button').trigger('click')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ archiveState: 'active' }))
    expect((wrapper.get('[aria-label="归档状态"]').element as HTMLSelectElement).value).toBe('active')
    expect(wrapper.findAll('[data-lead-id]')).toHaveLength(1)
  })
})
