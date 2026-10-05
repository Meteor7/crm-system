import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { demoRequests, evaluations } from '@/api/mock-data'
import { createAppRouter } from '@/app/router'
import type { DemoRequestDto, EvaluationDto, ListQuery } from '@/types/crm'
import DemoRequestsPage from './DemoRequestsPage.vue'
import EvaluationsPage from './EvaluationsPage.vue'

// The server's answer to a list query: one page of the rows, and how many there are in all.
function paged<T>(rows: T[], query: ListQuery = {}) {
  const page = query.page ?? 1
  const pageSize = query.pageSize ?? 20
  return {
    data: { items: rows.slice((page - 1) * pageSize, page * pageSize) },
    meta: { requestId: 'req_in_progress', total: rows.length, page, pageSize },
    warnings: [],
  }
}

describe('Workspaces of what is in progress', () => {
  it('reads every Demo Request in progress once and pages it in the workspace', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    const base = demoRequests.find((item) => !['Converted', 'Cancelled'].includes(item.status))!
    const rows: DemoRequestDto[] = Array.from({ length: 12 }, (_, index) => ({ ...base, id: `DR-Q${String(index).padStart(2, '0')}`, status: index === 9 ? 'Draft' : 'Engineer Review' }))
    const list = vi.spyOn(api, 'listDemoRequests').mockImplementation(async (query) => paged(rows, query))
    const router = createAppRouter()
    await router.push('/demo-requests'); await router.isReady()
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    // One request, for what is in progress: the server leaves out what became a Demo or was cancelled.
    expect(list).toHaveBeenCalledTimes(1)
    expect(list.mock.calls[0][0]).toMatchObject({ status: 'All', inProgress: '1', page: 1, pageSize: 200 })
    // A full page, and a count and a pager that agree with it.
    expect(wrapper.findAll('[data-demo-request]')).toHaveLength(10)
    expect(wrapper.get('.row-count').text()).toBe('Demo Request · 12')
    expect(wrapper.findAll('.pagination-controls')).toHaveLength(1)
    expect(wrapper.get('.pagination-controls small').text()).toContain('12')
    await wrapper.get('[data-page-next]').trigger('click')
    expect(wrapper.findAll('[data-demo-request]')).toHaveLength(2)
    // Turning the page asks the server for nothing.
    expect(list).toHaveBeenCalledTimes(1)

    // A request created from page 2 is the newest and so the first of the list: it is selected and shown.
    const created: DemoRequestDto = { ...base, id: 'DR-NEW', status: 'Draft' }
    vi.spyOn(api, 'createDemoRequest').mockImplementation(async () => { rows.unshift(created); return { data: created, warnings: [] } })
    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    await wrapper.findComponent({ name: 'DemoRequestModal' }).vm.$emit('submit', {})
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('[data-demo-request]')).toHaveLength(10)
    expect(wrapper.get('tr.selected').attributes('data-demo-request')).toBe('DR-NEW')
    expect(wrapper.get('.row-count').text()).toBe('Demo Request · 13')

    // The user turns to page 2 and submits the request on show there. Saved, it is the first of the list, and
    // it is still the one on show: the request created before, which has the same button, does not take its place.
    await wrapper.get('[data-page-next]').trigger('click'); await flushPromises()
    expect(wrapper.get('tr.selected').attributes('data-demo-request')).toBe('DR-Q09')
    const transition = vi.spyOn(api, 'transitionDemoRequest').mockImplementation(async (id) => {
      const request: DemoRequestDto = { ...rows.find((item) => item.id === id)!, status: 'Engineer Review' }
      rows.splice(rows.findIndex((item) => item.id === id), 1); rows.unshift(request)
      return { data: { request }, warnings: [] }
    })
    await wrapper.get('[data-demo-action="DR-Q09-submit"]').trigger('click')
    await flushPromises()
    expect(transition).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('[data-demo-request]')[0].attributes('data-demo-request')).toBe('DR-Q09')
    expect(wrapper.get('tr.selected').attributes('data-demo-request')).toBe('DR-Q09')
    expect(wrapper.find('[data-demo-action="DR-NEW-submit"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('selects a Demo Request created from a view that does not show drafts', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    const base = demoRequests.find((item) => !['Converted', 'Cancelled'].includes(item.status))!
    const rows: DemoRequestDto[] = [
      ...['DR-M0', 'DR-M1', 'DR-M2'].map((id) => ({ ...base, id, status: 'Manager Approval' as const })),
      ...Array.from({ length: 12 }, (_, index) => ({ ...base, id: `DR-D${String(index).padStart(2, '0')}`, status: 'Draft' as const })),
    ]
    vi.spyOn(api, 'listDemoRequests').mockImplementation(async (query) => paged(rows, query))
    const router = createAppRouter()
    await router.push('/demo-requests'); await router.isReady()
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    await wrapper.get('[data-demo-view="manager"]').trigger('click')
    expect(wrapper.findAll('[data-demo-request]')).toHaveLength(3)
    const created: DemoRequestDto = { ...base, id: 'DR-NEW', status: 'Draft' }
    vi.spyOn(api, 'createDemoRequest').mockImplementation(async () => { rows.unshift(created); return { data: created, warnings: [] } })
    await wrapper.get('[data-testid="new-demo-request"]').trigger('click')
    await wrapper.findComponent({ name: 'DemoRequestModal' }).vm.$emit('submit', {})
    await flushPromises()
    // The approval view does not show the draft; the view that does has it selected.
    expect(wrapper.findAll('[data-demo-request]')).toHaveLength(3)
    await wrapper.get('[data-demo-view="overview"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('tr.selected').attributes('data-demo-request')).toBe('DR-NEW')
    wrapper.unmount()
  })

  it('reads every Demo Test in progress once and counts all of them in the heading', async () => {
    const api = createMockApi({ role: 'Manager', latency: 0 })
    const base = evaluations.find((item) => item.status === 'Testing')!
    const rows: EvaluationDto[] = Array.from({ length: 8 }, (_, index) => ({ ...base, id: `EVAL-Q${index}` }))
    const list = vi.spyOn(api, 'listEvaluations').mockImplementation(async (query) => paged(rows, query))
    const router = createAppRouter()
    await router.push('/evaluations'); await router.isReady()
    const wrapper = mount(EvaluationsPage, { props: { apiClient: api }, global: { plugins: [createPinia(), router] } })
    await flushPromises()

    expect(list).toHaveBeenCalledTimes(1)
    expect(list.mock.calls[0][0]).toMatchObject({ inProgress: '1', page: 1, pageSize: 200 })
    // The heading counts every Demo in progress, not the six rows of the page shown.
    expect(wrapper.get('.header-chip').text()).toBe('8 个进行中项目')
    expect(wrapper.findAll('[data-evaluation]')).toHaveLength(6)
    expect(wrapper.findAll('.pagination-controls')).toHaveLength(1)
    expect(wrapper.get('.pagination-controls small').text()).toContain('8')
    await wrapper.get('[data-page-next]').trigger('click')
    expect(wrapper.findAll('[data-evaluation]')).toHaveLength(2)
    expect(wrapper.get('.header-chip').text()).toBe('8 个进行中项目')
    expect(list).toHaveBeenCalledTimes(1)

    // A report uploaded for the Demo on show on page 2 saves it, which makes it the first of the list. It is
    // still the one on show; the Demo selected when the page opened does not take its place.
    expect(wrapper.get('tr.selected').attributes('data-evaluation')).toBe('EVAL-Q6')
    await wrapper.get('[data-report-action="EVAL-Q6"]').trigger('click')
    rows.unshift(...rows.splice(6, 1))
    await wrapper.findComponent({ name: 'TestReportUploadModal' }).vm.$emit('uploaded')
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('[data-evaluation]')[0].attributes('data-evaluation')).toBe('EVAL-Q6')
    expect(wrapper.get('tr.selected').attributes('data-evaluation')).toBe('EVAL-Q6')
    wrapper.unmount()
  })
})
