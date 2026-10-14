import { afterEach, describe, expect, it } from 'vitest'
import { createPinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import ApprovalsDemoPage from '../../../previews/approvals/ApprovalsDemoPage.vue'
import ApprovalActionDemoPage from '../../../previews/approvals/ApprovalActionDemoPage.vue'
import { demoViewer } from '../../../previews/approvals/demo-fixtures'

let wrapper: VueWrapper | undefined
afterEach(() => { wrapper?.unmount(); wrapper = undefined })
describe('Standalone approval preview navigation', () => {
  it('opens the matching approval screen directly, records a view, and denies foreign or mismatched records', async () => {
    const pinia = createPinia(), app = useAppStore(pinia), viewer = demoViewer('Manager')
    app.bootstrap = { user: { id: viewer.id, name: viewer.name, initials: '王', role: viewer.role, team: 'Preview' }, capabilities: [...viewer.capabilities], version: 'approvals-ui-preview' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: ApprovalsDemoPage },
      ...['/demo-requests', '/quotations/:quotationId', '/opportunities/:opportunityId', '/visits', '/rfqs/:rfqId', '/document-center', '/evaluations'].map(path => ({ path, component: ApprovalActionDemoPage })),
    ] })
    await router.push({ path: '/', query: { role: 'Manager' } })
    await router.isReady()
    wrapper = mount({ template: '<RouterView />' }, { global: { plugins: [pinia, router] } })
    await wrapper.get('[data-approval-id="CRM-DR-04182"] [data-open-approval]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/demo-requests')
    expect(router.currentRoute.value.query).toMatchObject({ focus: 'CRM-DR-04182', mode: 'manager', approval: 'CRM-DR-04182' })
    expect(wrapper.get('.decision-panel').text()).toContain('经理审批')
    expect(wrapper.get('.submit-decision').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    await wrapper.get('.back-to-inbox').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-approval-id]').map(row => row.attributes('data-approval-id'))).toEqual([
      'PK20261012-A03', 'DOC-REQ-00216', 'CRM-DR-04182', 'CRM-OPP-03276', 'CRM-VIS-02641', 'CRM-RFQ-01037',
    ])
    expect(wrapper.get('[data-approval-id="CRM-DR-04182"]').find('[aria-label="未查看"]').exists()).toBe(false)
    await wrapper.get('[data-approval-id="PK20261012-A03"] [data-open-approval]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/quotations/CRM-QTN-04103')
    expect(wrapper.get('.request-materials').text()).toContain('PK20261012-A03')
    await router.push({ path: '/demo-requests', query: { role: 'Engineer', approval: 'CRM-DR-04182', focus: 'CRM-DR-04182', mode: 'manager' } })
    await flushPromises()
    expect(wrapper.find('.decision-panel').exists()).toBe(false)
    expect(wrapper.text()).toContain('当前没有可处理的事项')
    expect(wrapper.text()).not.toContain('CRM-DR-04182')
    await router.push({ path: '/document-center', query: { role: 'Manager', approval: 'DOC-REQ-00216', workspace: 'approvals', request: 'wrong-record' } })
    await flushPromises()
    expect(wrapper.find('.decision-panel').exists()).toBe(false)
    await router.push({ path: '/', query: { role: 'Engineer' } })
    await flushPromises()
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(4)
    await wrapper.get('[data-approval-id="CRM-EVAL-02945"] [data-open-approval]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/evaluations')
    expect(router.currentRoute.value.query.focus).toBe('CRM-EVAL-02945')
    expect(wrapper.get('.decision-panel').text()).toContain('测试结果内部审核')
  })
})
