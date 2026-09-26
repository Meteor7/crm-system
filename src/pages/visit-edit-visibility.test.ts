import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CrmApiError } from '@/api'
import { createMockApi } from '@/api/mock-adapter'
import { createMemorySalesRepository } from '@/demo/sales-repository'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'
import VisitsPage from './VisitsPage.vue'
import VisitDetailPage from './VisitDetailPage.vue'

async function context(role: UserRole, path: string, salesRepository = createMemorySalesRepository()) {
  const api = createMockApi({ latency: 0, role, userName: role === 'Sales' ? 'Demo Staff 01' : '演示员工24', salesRepository })
  const pinia = createPinia()
  useAppStore(pinia).bootstrap = (await api.getBootstrap()).data
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/visits', name: 'visits', component: { template: '<div />' } },
      { path: '/visits/:visitId', name: 'visit-detail', component: { template: '<div />' } },
      { path: '/contacts/:contactId', name: 'contact-detail', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  return { api, pinia, router }
}

afterEach(() => vi.restoreAllMocks())

const subjectDraft = (wrapper: ReturnType<typeof mount>) =>
  (wrapper.get('[aria-label="拜访主题"]').element as HTMLInputElement).value

const plannedVisit = { accountId: 'ACC-001', subject: '原定拜访', date: '2026-07-21', type: 'Video' as const, owner: 'person002@crm.example.invalid', objective: '确认样片' }

function conflictOnce(api: ReturnType<typeof createMockApi>) {
  vi.spyOn(api, 'updateVisit').mockRejectedValueOnce(
    new CrmApiError('VERSION_CONFLICT', '拜访记录已被其他用户修改', 'req-visit-conflict', false),
  )
}

describe('Visit editing for rescheduled customers', () => {
  it('shows the edit button to Sales on unreviewed Visits only and saves through updateVisit', async () => {
    const sales = await context('Sales', '/visits')
    const planned = await sales.api.createVisit({ accountId: 'ACC-001', subject: '原定拜访', date: '2026-07-21', type: 'Video', owner: 'person002@crm.example.invalid', objective: '确认样片' })
    const updateSpy = vi.spyOn(sales.api, 'updateVisit')
    const wrapper = mount(VisitsPage, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()

    expect(wrapper.find(`[data-edit-visit="${planned.data.id}"]`).exists()).toBe(true)
    // V-001 is Manager Reviewed in the seed data and must stay frozen.
    expect(wrapper.find('[data-edit-visit="V-001"]').exists()).toBe(false)

    await wrapper.get(`[data-edit-visit="${planned.data.id}"]`).trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="拜访日期"]').setValue('2026-07-28')
    await wrapper.get('[aria-label="拜访主题"]').setValue('改期后拜访')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(updateSpy).toHaveBeenCalledWith(planned.data.id, { subject: '改期后拜访', date: '2026-07-28', type: 'Video', owner: 'person002@crm.example.invalid', objective: '确认样片' }, planned.data.modified)
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.get(`[data-visit-id="${planned.data.id}"]`).text()).toContain('改期后拜访')
  })

  it('keeps the list draft on screen when another tab saved the visit first', async () => {
    const salesRepository = createMemorySalesRepository()
    const seed = await context('Sales', '/visits', salesRepository)
    const planned = await seed.api.createVisit(plannedVisit)
    const sales = await context('Sales', '/visits', salesRepository)
    const wrapper = mount(VisitsPage, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()

    await wrapper.get(`[data-edit-visit="${planned.data.id}"]`).trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="拜访主题"]').setValue('我的改期草稿')

    // A colleague saves the same visit first, so this editor holds a stale version token.
    conflictOnce(sales.api)
    await seed.api.updateVisit(planned.data.id, { ...plannedVisit, subject: '同事改的主题' })
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('已被其他人修改')
    expect(subjectDraft(wrapper)).toBe('我的改期草稿')

    // Reloading is the user's call: only then does the colleague's version replace the draft.
    await wrapper.get('[data-reload-visit]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(subjectDraft(wrapper)).toBe('同事改的主题')
  })

  it('re-fetches by id when the conflicting visit has left the current list', async () => {
    const salesRepository = createMemorySalesRepository()
    const seed = await context('Sales', '/visits', salesRepository)
    const planned = await seed.api.createVisit(plannedVisit)
    const sales = await context('Sales', '/visits', salesRepository)
    const wrapper = mount(VisitsPage, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()

    await wrapper.get(`[data-edit-visit="${planned.data.id}"]`).trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="拜访主题"]').setValue('我的改期草稿')

    conflictOnce(sales.api)
    await seed.api.updateVisit(planned.data.id, { ...plannedVisit, subject: '同事改的主题' })
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(subjectDraft(wrapper)).toBe('我的改期草稿')

    // The colleague's save moved the visit out of this page's filter, so the
    // refreshed list cannot supply it. Falling back to the stale object would
    // keep the old version token and every later save would conflict again.
    const listVisits = sales.api.listVisits.bind(sales.api)
    vi.spyOn(sales.api, 'listVisits').mockImplementationOnce(async (query) => {
      const response = await listVisits(query)
      return { ...response, data: { ...response.data, items: [] } }
    })
    const getVisit = vi.spyOn(sales.api, 'getVisit')

    await wrapper.get('[data-reload-visit]').trigger('click')
    await flushPromises()

    expect(getVisit).toHaveBeenCalledWith(planned.data.id)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(subjectDraft(wrapper)).toBe('同事改的主题')
  })

  it('keeps a colleague visit read-only for the Sales user who only owns its action', async () => {
    const salesRepository = createMemorySalesRepository()
    // Bella owns the visit; Alex was only given its next action, which is what lets him see it.
    const template = salesRepository.snapshot.visits.find((item) => item.id === 'V-003')!
    salesRepository.snapshot.visits.push({
      ...template, id: 'V-ACTION', accountId: 'ACC-001', status: 'Planned',
      owner: 'person005@crm.example.invalid', nextAction: '带样片到现场', actionOwner: 'person002@crm.example.invalid', actionDone: false,
    })
    const sales = await context('Sales', '/visits', salesRepository)
    const wrapper = mount(VisitsPage, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()

    expect(wrapper.find('[data-visit-id="V-ACTION"]').exists()).toBe(true)
    expect(wrapper.find('[data-edit-visit="V-ACTION"]').exists()).toBe(false)
    // The backend refuses it too: naming himself owner would take the visit from Bella.
    await expect(sales.api.updateVisit('V-ACTION', {
      subject: '接管拜访', date: '2026-07-22', type: 'On-site', owner: 'person002@crm.example.invalid', objective: template.objective,
    })).rejects.toMatchObject({ code: 'SCOPE_DENIED' })

    const detail = await context('Sales', '/visits/V-ACTION', salesRepository)
    const page = mount(VisitDetailPage, { props: { apiClient: detail.api }, global: { plugins: [detail.pinia, detail.router] } })
    await flushPromises()
    expect(page.text()).toContain(template.subject)
    expect(page.find('[data-edit-visit]').exists()).toBe(false)
    // The meeting record belongs to the visit too: a complete one would submit Bella's visit for review.
    expect(page.find('.upload-record-button').exists()).toBe(false)
    expect(page.find('[data-edit-record]').exists()).toBe(false)
    await expect(sales.api.updateVisitMeetingRecord('V-ACTION', {
      meetingStart: '', meetingEnd: '', purpose: '复核', attendees: '客户 A', agenda: '议程', summary: '摘要', conclusion: '推进', followup: '发方案',
    })).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
    await expect(sales.api.submitVisitRecord('V-ACTION', {
      fileName: 'minutes.txt', mimeType: 'text/plain', size: 16, blob: new Blob(['purpose: 复核']),
    })).rejects.toMatchObject({ code: 'SCOPE_DENIED' })
  })

  it('hides the edit button from Engineers, who never hold visit:write', async () => {
    const engineer = await context('Engineer', '/visits')
    const wrapper = mount(VisitsPage, { props: { apiClient: engineer.api }, global: { plugins: [engineer.pinia, engineer.router] } })
    await flushPromises()

    expect(wrapper.find('[data-edit-visit]').exists()).toBe(false)
  })

  it('offers editing on the detail page and refreshes the header after saving', async () => {
    const salesRepository = createMemorySalesRepository()
    const seed = await context('Sales', '/visits', salesRepository)
    const planned = await seed.api.createVisit({ accountId: 'ACC-001', subject: '原定拜访', date: '2026-07-21', type: 'Video', owner: 'person002@crm.example.invalid', objective: '确认样片' })

    const sales = await context('Sales', `/visits/${planned.data.id}`, salesRepository)
    const updateSpy = vi.spyOn(sales.api, 'updateVisit')
    const wrapper = mount(VisitDetailPage, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()

    await wrapper.get('[data-edit-visit]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="拜访主题"]').setValue('改期后拜访')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(updateSpy).toHaveBeenCalledWith(planned.data.id, expect.objectContaining({ subject: '改期后拜访', date: '2026-07-21' }), planned.data.modified)
    expect(wrapper.text()).toContain('改期后拜访')

    const manager = await context('Manager', '/visits/V-001', salesRepository)
    const reviewed = mount(VisitDetailPage, { props: { apiClient: manager.api }, global: { plugins: [manager.pinia, manager.router] } })
    await flushPromises()
    expect(reviewed.find('[data-edit-visit]').exists()).toBe(false)
  })

  it('keeps the detail draft on screen when another tab saved the visit first', async () => {
    const salesRepository = createMemorySalesRepository()
    const seed = await context('Sales', '/visits', salesRepository)
    const planned = await seed.api.createVisit(plannedVisit)

    const sales = await context('Sales', `/visits/${planned.data.id}`, salesRepository)
    const wrapper = mount(VisitDetailPage, { props: { apiClient: sales.api }, global: { plugins: [sales.pinia, sales.router] } })
    await flushPromises()

    await wrapper.get('[data-edit-visit]').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="拜访主题"]').setValue('我的改期草稿')

    conflictOnce(sales.api)
    await seed.api.updateVisit(planned.data.id, { ...plannedVisit, subject: '同事改的主题' })
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('已被其他人修改')
    expect(wrapper.get('[role="alert"]').text()).toContain('req-visit-conflict')
    expect(subjectDraft(wrapper)).toBe('我的改期草稿')

    await wrapper.get('[data-reload-visit]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(subjectDraft(wrapper)).toBe('同事改的主题')

    // The reloaded version token is current, so the next save goes through.
    await wrapper.get('[aria-label="拜访主题"]').setValue('改期后拜访')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('改期后拜访')
  })
})
