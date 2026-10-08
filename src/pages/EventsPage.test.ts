import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { setLocale } from '@/i18n'
import type { UserRole } from '@/types/crm'
import type { EventDto } from '@/features/events/types'
import EventsPage from './EventsPage.vue'

beforeEach(() => setLocale('zh-CN'))
const event = (): EventDto => ({ id: 'event-1', modified: 'v1', title: 'Semiconductor show', owner: 'alice',
  startDate: '2026-10-10', endDate: '2026-10-12', status: 'Planned', accountId: '', opportunityId: '',
  region: '', market: '', equipment: '', note: '', completedAt: null })
const response = <T,>(data: T) => ({ data, meta: { requestId: 'events', total: 1 }, warnings: [] })
async function setup(role: UserRole = 'Manager', focus = '') {
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
  const wrapper = mount(EventsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
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

  it('does not load event records or show mutations to engineers', async () => {
    const { api, wrapper } = await setup('Engineer')
    expect(api.listEvents).not.toHaveBeenCalled()
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).toContain('仅向销售和经理开放')
    wrapper.unmount()
  })
})
