import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { setLocale } from '@/i18n'
import { useAppStore } from '@/stores/app'
import type { CrmApi } from '@/api'
import type { UserRole } from '@/types/crm'
import type { EventDto } from '@/features/events/types'
import EventsPage from './EventsPage.vue'

beforeEach(() => setLocale('zh-CN'))
const event = (): EventDto => ({ id: 'event-1', modified: 'v1', title: 'Semiconductor show', owner: 'alice',
  startDate: '2026-10-10', endDate: '2026-10-12', status: 'Planned', accountId: '', opportunityId: '',
  region: '', market: '', equipment: '', note: '', completedAt: null })
const response = <T,>(data: T) => ({ data, meta: { requestId: 'events', total: 1 }, warnings: [] })
const eventPage = (items: EventDto[], total: number) => ({ ...response({ items }), meta: { requestId: 'events', total } })
const firstPage = () => Array.from({ length: 20 }, (_, index) => ({ ...event(), id: `event-${index + 1}` }))
async function setup(role: UserRole = 'Manager', focus = '', preload = false) {
  const api = createMockApi({ role, latency: 0 })
  api.listEvents = vi.fn(async () => response({ items: [event()] }))
  api.getEvent = vi.fn(async () => response(event()))
  api.saveEvent = vi.fn(async () => response(event()))
  api.listAccounts = vi.fn(async () => response({ items: [] }))
  api.listStrategyOpportunities = vi.fn(async () => response({ items: [] }))
  api.listAccountRegions = vi.fn(async () => response(['East China']))
  api.listAccountSegments = vi.fn(async () => response(['Frontend']))
  api.listEquipmentTypes = vi.fn(async () => response(['Inspection']))
  const router = createAppRouter()
  await router.push({ path: '/events', query: focus ? { focus } : {} }); await router.isReady()
  const pinia = createPinia()
  // The real shell has loaded the user before a page mounts, so its immediate watcher loads during setup.
  if (preload) await useAppStore(pinia).loadBootstrap(api)
  const wrapper = mount(EventsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  await flushPromises()
  return { api, wrapper, router }
}

describe('Events', () => {
  it('opens a focused event and sends only editable inputs with its CAS version', async () => {
    const { api, wrapper } = await setup('Manager', 'event-1')
    expect(api.getEvent).toHaveBeenCalledWith('event-1')
    await wrapper.get('[data-testid="event-title"]').setValue('Updated show')
    await wrapper.get('.editor form').trigger('submit'); await flushPromises()
    expect(api.saveEvent).toHaveBeenCalledWith({ title: 'Updated show', owner: 'alice', startDate: '2026-10-10', endDate: '2026-10-12',
      status: 'Planned', accountId: '', opportunityId: '', region: '', market: '', equipment: '', note: '' }, 'event-1', 'v1')
    expect(wrapper.find('.editor').exists()).toBe(false)
    wrapper.unmount()
  })

  it('retains an unsuccessful draft until explicit reload and follows focus changes', async () => {
    const { api, wrapper, router } = await setup('Manager', 'event-1')
    api.saveEvent = vi.fn().mockRejectedValue(new Error('Event changed'))
    await wrapper.get('[data-testid="event-title"]').setValue('Keep my notes')
    await wrapper.get('.editor form').trigger('submit'); await flushPromises()
    expect(wrapper.get('.editor [role=alert]').text()).toContain('Event changed')
    expect((wrapper.get('[data-testid="event-title"]').element as HTMLInputElement).value).toBe('Keep my notes')
    expect(api.getEvent).toHaveBeenCalledTimes(1)
    await wrapper.get('.editor [role=alert] button').trigger('click'); await flushPromises()
    expect(api.getEvent).toHaveBeenCalledTimes(2)
    expect((wrapper.get('[data-testid="event-title"]').element as HTMLInputElement).value).toBe('Semiconductor show')
    await router.push({ path: '/events', query: { focus: 'event-2' } }); await flushPromises()
    expect(api.getEvent).toHaveBeenLastCalledWith('event-2')
    wrapper.unmount()
  })

  it('lists events in the shared table with status badges when the shell has already loaded the user', async () => {
    const { api, wrapper } = await setup('Manager', '', true)
    expect(api.listEvents).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.page-header h1').text()).toBe('活动管理')
    const row = wrapper.get('.events-table tbody tr[data-event-id="event-1"]')
    expect(row.text()).toContain('Semiconductor show')
    expect(row.get('.status-badge').text()).toBe('计划中')
    await row.get('.record-button').trigger('click'); await flushPromises()
    expect(wrapper.findAll('.editor :required')).toHaveLength(4)
    expect(wrapper.findAll('.editor [data-required-mark]')).toHaveLength(4)
    wrapper.unmount()
  })

  it('does not load event records or show mutations to engineers', async () => {
    const { api, wrapper } = await setup('Engineer')
    expect(api.listEvents).not.toHaveBeenCalled()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('仅向销售和经理开放')
    wrapper.unmount()
  })

  it('refetches the previous page after editing the only match on the last filtered page', async () => {
    const { api, wrapper } = await setup('Manager', '', true)
    const remaining = firstPage()
    const last = { ...event(), id: 'event-21' }
    api.listEvents = vi.fn()
      .mockResolvedValueOnce(eventPage(remaining, 21))
      .mockResolvedValueOnce(eventPage([last], 21))
      .mockResolvedValueOnce(eventPage([], 20))
      .mockResolvedValueOnce(eventPage(remaining, 20))
    await wrapper.get('.search-control input').setValue('Semiconductor')
    await wrapper.get('.search-control').trigger('submit'); await flushPromises()
    await wrapper.get('[data-page-next]').trigger('click'); await flushPromises()
    await wrapper.get('[data-event-id="event-21"] .record-button').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="event-title"]').setValue('Renamed conference')
    await wrapper.get('.editor form').trigger('submit'); await flushPromises()

    expect(api.listEvents).toHaveBeenNthCalledWith(3, { page: 2, pageSize: 20, search: 'Semiconductor' })
    expect(api.listEvents).toHaveBeenNthCalledWith(4, { page: 1, pageSize: 20, search: 'Semiconductor' })
    expect(wrapper.findAll('.events-table tbody tr')).toHaveLength(20)
    expect(wrapper.find('[data-event-id="event-21"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('当前范围暂无活动')
    wrapper.unmount()
  })

  it('keeps the page-size selector and its original 20 option after all events fit the larger size', async () => {
    const { api, wrapper } = await setup('Manager', '', true)
    const all = [...firstPage(), { ...event(), id: 'event-21' }]
    api.listEvents = vi.fn()
      .mockResolvedValueOnce(eventPage(all.slice(0, 20), 21))
      .mockResolvedValueOnce(eventPage(all, 21))
      .mockResolvedValueOnce(eventPage(all.slice(0, 20), 21))
    await wrapper.get('.search-control').trigger('submit'); await flushPromises()
    await wrapper.get('.pagination-controls select').setValue('50'); await flushPromises()

    expect(wrapper.findAll('.events-table tbody tr')).toHaveLength(21)
    const size = wrapper.get('.pagination-controls select')
    expect((size.element as HTMLSelectElement).value).toBe('50')
    expect(size.findAll('option').map(option => option.attributes('value'))).toContain('20')
    await size.setValue('20'); await flushPromises()
    expect(api.listEvents).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, search: '' })
    expect(wrapper.findAll('.events-table tbody tr')).toHaveLength(20)
    expect(wrapper.get('[data-page-next]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('ignores a corrective page response after a newer search reset has completed', async () => {
    const { api, wrapper } = await setup('Manager', '', true)
    const remaining = firstPage(), last = { ...event(), id: 'event-21' }
    let resolveCorrection!: (value: Awaited<ReturnType<CrmApi['listEvents']>>) => void
    const correction = new Promise<Awaited<ReturnType<CrmApi['listEvents']>>>(resolve => { resolveCorrection = resolve })
    api.listEvents = vi.fn()
      .mockResolvedValueOnce(eventPage(remaining, 21))
      .mockResolvedValueOnce(eventPage([last], 21))
      .mockResolvedValueOnce(eventPage([], 20))
      .mockReturnValueOnce(correction)
      .mockResolvedValueOnce(eventPage([{ ...event(), id: 'event-new', title: 'New scope event' }], 1))
    await wrapper.get('.search-control input').setValue('Semiconductor')
    await wrapper.get('.search-control').trigger('submit'); await flushPromises()
    await wrapper.get('[data-page-next]').trigger('click'); await flushPromises()
    await wrapper.get('[data-event-id="event-21"] .record-button').trigger('click'); await flushPromises()
    await wrapper.get('.editor form').trigger('submit'); await flushPromises()
    expect(api.listEvents).toHaveBeenNthCalledWith(4, { page: 1, pageSize: 20, search: 'Semiconductor' })

    await wrapper.get('.reset-button').trigger('click'); await flushPromises()
    resolveCorrection(eventPage(remaining, 20)); await flushPromises()
    expect(api.listEvents).toHaveBeenCalledTimes(5)
    expect(api.listEvents).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, search: '' })
    expect(wrapper.findAll('.events-table tbody tr')).toHaveLength(1)
    expect(wrapper.get('[data-event-id="event-new"]').text()).toContain('New scope event')
    expect(wrapper.get('[data-page-next]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('lets an empty filtered list restore the original page size after choosing a larger size', async () => {
    const { api, wrapper } = await setup('Manager', '', true)
    api.listEvents = vi.fn()
      .mockResolvedValueOnce(eventPage([event()], 1))
      .mockResolvedValueOnce(eventPage([], 0))
      .mockResolvedValueOnce(eventPage([], 0))
    await wrapper.get('.pagination-controls select').setValue('50'); await flushPromises()
    await wrapper.get('.search-control input').setValue('No matching event')
    await wrapper.get('.search-control').trigger('submit'); await flushPromises()

    expect(wrapper.text()).toContain('当前范围暂无活动')
    expect(wrapper.find('.events-table').exists()).toBe(false)
    await wrapper.get('.pagination-controls select').setValue('20'); await flushPromises()
    expect(api.listEvents).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, search: 'No matching event' })
    expect(wrapper.find('.pagination-controls').exists()).toBe(false)
    wrapper.unmount()
  })
})
