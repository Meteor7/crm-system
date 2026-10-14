import { afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { CrmApiError, type CrmApi } from '@/api'
import { useAppStore } from '@/stores/app'
import { demoApprovals, demoViewer } from '../../previews/approvals/demo-fixtures'
import PendingApprovalsPage from './PendingApprovalsPage.vue'

enableAutoUnmount(afterEach)
const response = (items = demoApprovals()) => ({ data: { items }, warnings: [] })
function bootstrap(role: 'Manager' | 'Sales' | 'Engineer') {
  const viewer = demoViewer(role)
  return { user: { id: viewer.id, name: viewer.name, initials: viewer.name[0]!, role, team: 'Test' }, capabilities: [...viewer.capabilities], version: 'test' }
}
async function context(role: 'Manager' | 'Sales' | 'Engineer' = 'Manager') {
  const api = { listPendingApprovals: vi.fn().mockResolvedValue(response()), markApprovalViewed: vi.fn().mockResolvedValue({ data: { id: 'viewed', viewedAt: '2026-10-14' }, warnings: [] }) } as unknown as CrmApi
  const pinia = createPinia(), app = useAppStore(pinia)
  app.bootstrap = bootstrap(role)
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/approvals', component: { template: '<div />' } }, { path: '/dashboard', component: { template: '<div />' } },
    { path: '/quotations/:id', component: { template: '<div />' } }, { path: '/demo-requests', component: { template: '<div />' } },
  ] })
  await router.push('/approvals'); await router.isReady()
  const start = () => mount(PendingApprovalsPage, { props: { apiClient: api }, global: { plugins: [pinia, router] } })
  return { api, app, router, start }
}
describe('Pending approvals page', () => {
  it('places approvals after Opportunities, shows actor-scoped unread items first and has no data filters', async () => {
    const { api, start } = await context(), wrapper = start()
    await flushPromises()
    expect(api.listPendingApprovals).toHaveBeenCalledWith()
    expect(wrapper.findAll('.approval-workspace-tabs a').map(tab => tab.text())).toEqual(['Review', 'Plan', 'Warnings', 'Opportunities', '待审批6'])
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(6)
    expect(wrapper.findAll('[data-approval-id]').slice(0, 3).map(row => row.attributes('data-approval-id'))).toEqual(['CRM-DR-04182', 'PK20261012-A03', 'DOC-REQ-00216'])
    expect(wrapper.find('input,select').exists()).toBe(false)
  })
  it.each(['Sales', 'Engineer'] as const)('places %s approvals as the second information-centre page', async role => {
    const { start } = await context(role), wrapper = start()
    await flushPromises()
    expect(wrapper.findAll('.approval-workspace-tabs a').map(tab => tab.text())).toEqual(['信息概览', `待审批${role === 'Sales' ? 2 : 4}`])
    expect(wrapper.text()).not.toContain('报价审批')
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(role === 'Sales' ? 2 : 4)
  })
  it('uses the server-selected business record and version, and only writes a read receipt', async () => {
    const { api, router, start } = await context()
    const quotation = { ...demoApprovals()[1]!, target: { path: '/quotations/CRM-QTN-04103', query: { version: 'CRM-QVER-2', approval: '1' } } }
    vi.mocked(api.listPendingApprovals).mockResolvedValue(response([quotation]))
    vi.mocked(api.markApprovalViewed).mockRejectedValue(new CrmApiError('NETWORK_ERROR', 'Receipt failed.', 'req-read'))
    const wrapper = start(); await flushPromises()
    await wrapper.get('[data-open-approval]').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/quotations/CRM-QTN-04103')
    expect(router.currentRoute.value.query).toEqual({ version: 'CRM-QVER-2', approval: '1' })
    expect(api.markApprovalViewed).toHaveBeenCalledWith(quotation.id)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
  it('discards old results immediately when the account or capabilities change', async () => {
    const { api, app, start } = await context()
    let finish!: (value: ReturnType<typeof response>) => void
    vi.mocked(api.listPendingApprovals).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = start(); await flushPromises()
    app.bootstrap = bootstrap('Engineer'); await flushPromises()
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(4)
    finish(response()); await flushPromises()
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(4)
    expect(wrapper.text()).not.toContain('报价审批')
    app.bootstrap = { ...bootstrap('Engineer'), capabilities: [] }; await flushPromises()
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(0)
  })
  it('does not reattach focus refresh after unmounting during the initial request', async () => {
    const { api, app, start } = await context()
    let finish!: (value: ReturnType<typeof response>) => void
    vi.mocked(api.listPendingApprovals).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const loadBootstrap = vi.spyOn(app, 'loadBootstrap')
    const wrapper = start(); await flushPromises()
    expect(api.listPendingApprovals).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    finish(response()); await flushPromises()
    window.dispatchEvent(new Event('focus')); await flushPromises()
    expect(loadBootstrap).toHaveBeenCalledTimes(1)
    expect(api.listPendingApprovals).toHaveBeenCalledTimes(1)
  })
  it('shows a failed request as an error and retries, rather than claiming no tasks', async () => {
    const { api, start } = await context()
    vi.mocked(api.listPendingApprovals).mockRejectedValueOnce(new CrmApiError('NETWORK_ERROR', 'Queue failed.', 'req-queue'))
    const wrapper = start(); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[data-approval-inbox]').exists()).toBe(false)
    await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises()
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(6)
  })
  it('retries the session bootstrap after its initial failure', async () => {
    const { api, app, start } = await context()
    app.bootstrap = null
    api.listRequirements = vi.fn().mockResolvedValue({ data: { items: [] }, warnings: [] })
    api.getBootstrap = vi.fn().mockRejectedValueOnce(new CrmApiError('NETWORK_ERROR', 'Bootstrap failed.', 'req-boot')).mockResolvedValue({ data: bootstrap('Manager'), warnings: [] })
    const wrapper = start(); await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(api.listPendingApprovals).not.toHaveBeenCalled()
    await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises()
    expect(api.getBootstrap).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(6)
  })
})
