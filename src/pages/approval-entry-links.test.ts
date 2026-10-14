import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createAppRouter } from '@/app/router'
import { createMockApi } from '@/api/mock-adapter'
import { useAppStore } from '@/stores/app'
import type { UserRole } from '@/types/crm'
import DemoRequestsPage from './DemoRequestsPage.vue'
import DemoRequestModal from '@/features/demo-requests/DemoRequestModal.vue'
import VisitsPage from './VisitsPage.vue'
import VisitModal from '@/features/visits/VisitModal.vue'
import DocumentCenterPage from './DocumentCenterPage.vue'

enableAutoUnmount(afterEach)
async function context(role: UserRole, path: string) {
  const api = createMockApi({ latency: 0, role }), pinia = createPinia(), router = createAppRouter()
  const app = useAppStore(pinia); app.bootstrap = (await api.getBootstrap()).data
  await router.push(path); await router.isReady()
  return { api, app, global: { plugins: [pinia, router] } }
}
describe('Existing approval entry links', () => {
  it.each(['Manager', 'Sales'] as const)('opens the specified Demo manager approval only for authorized %s', async role => {
    const { api, global } = await context(role, '/demo-requests?focus=linked-demo&mode=manager')
    const original = (await api.listDemoRequests({ page: 1, pageSize: 20 })).data.items[0]!
    const request = { ...original, id: 'linked-demo', status: 'Manager Approval' as const }
    vi.spyOn(api, 'listDemoRequests').mockResolvedValue({ data: { items: [request] }, warnings: [], meta: { requestId: 'entry-test', page: 1, pageSize: 100, total: 1 } })
    const transition = vi.spyOn(api, 'transitionDemoRequest')
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global }); await flushPromises()
    if (role === 'Manager') {
      expect(wrapper.findComponent(DemoRequestModal).props('mode')).toBe('manager')
      expect(wrapper.findComponent(DemoRequestModal).props('request')?.id).toBe('linked-demo')
    } else {
      expect(wrapper.findComponent(DemoRequestModal).exists()).toBe(false)
      expect(wrapper.text()).toContain('该事项当前已不在你的可审批范围内')
    }
    expect(transition).not.toHaveBeenCalled()
  })
  it('does not open an engineering approval assigned to another engineer', async () => {
    const { api, global } = await context('Engineer', '/demo-requests?focus=other-demo&mode=engineer')
    const original = (await api.listDemoRequests({ page: 1, pageSize: 20 })).data.items[0]!
    vi.spyOn(api, 'listDemoRequests').mockResolvedValue({ data: { items: [{ ...original, id: 'other-demo', status: 'Engineer Review', engineerOwner: 'another-engineer' }] }, warnings: [], meta: { requestId: 'entry-test', total: 1 } })
    const wrapper = mount(DemoRequestsPage, { props: { apiClient: api }, global }); await flushPromises()
    expect(wrapper.findComponent(DemoRequestModal).exists()).toBe(false)
  })
  it.each(['Manager', 'Sales'] as const)('opens the specific visit review only for authorized %s', async role => {
    const { api, global } = await context(role, '/visits?focus=linked-visit&review=1')
    const original = (await api.listVisits({ page: 1, pageSize: 20 })).data.items[0]!
    const visit = { ...original, id: 'linked-visit', status: 'Minutes Submitted' as const }
    vi.spyOn(api, 'listVisits').mockResolvedValue({ data: { items: [] }, warnings: [], meta: { requestId: 'entry-test', total: 0 } })
    vi.spyOn(api, 'getVisit').mockResolvedValue({ data: visit, warnings: [] })
    const review = vi.spyOn(api, 'reviewVisit')
    const wrapper = mount(VisitsPage, { props: { apiClient: api }, global }); await flushPromises()
    expect(wrapper.findComponent(VisitModal).exists()).toBe(role === 'Manager')
    if (role === 'Manager') expect(wrapper.findComponent(VisitModal).props('mode')).toBe('review')
    expect(review).not.toHaveBeenCalled()
  })
  it('does not substitute another document request for an unavailable linked request', async () => {
    const { api, global } = await context('Manager', '/document-center?workspace=approvals&request=missing-request')
    const wrapper = mount(DocumentCenterPage, { props: { apiClient: api }, global }); await flushPromises()
    expect(wrapper.find('[data-approval-action]').exists()).toBe(false)
  })
})
