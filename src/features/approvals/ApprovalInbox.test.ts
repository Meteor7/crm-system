import { afterEach, describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { DEMO_NOW, demoApprovals, demoViewer } from '../../../previews/approvals/demo-fixtures'
import ApprovalInbox from './ApprovalInbox.vue'

let wrapper: VueWrapper | undefined
afterEach(() => { wrapper?.unmount(); wrapper = undefined })
function page() {
  wrapper = mount(ApprovalInbox, { props: { viewer: demoViewer('Manager'), items: demoApprovals(), now: DEMO_NOW }, attachTo: document.body })
  return wrapper
}
describe('Approval inbox', () => {
  it('puts unread tasks first, preserving order within each group and the input array', () => {
    const items = demoApprovals(), originalIds = items.map(item => item.id)
    wrapper = mount(ApprovalInbox, { props: { viewer: demoViewer('Manager'), items, now: DEMO_NOW } })
    expect(wrapper.findAll('[data-approval-id]').map(row => row.attributes('data-approval-id'))).toEqual([
      'CRM-DR-04182', 'PK20261012-A03', 'DOC-REQ-00216', 'CRM-OPP-03276', 'CRM-VIS-02641', 'CRM-RFQ-01037',
    ])
    expect(items.map(item => item.id)).toEqual(originalIds)
    expect(wrapper.findAll('thead th').map(cell => cell.text())).toEqual(['业务类型', '审批事项', '当前环节', '提交人', '提交时间', '操作'])
    expect(wrapper.text()).not.toMatch(/处理时效|即将到期|已超期|不可见/)
    expect(wrapper.find('input, select, .queue-tabs').exists()).toBe(false)
    expect(wrapper.find('[data-approval-id="CRM-DR-04183"]').exists()).toBe(false)
  })
  it('updates the queue and approval destination when switching identities', async () => {
    const wrapper = page()
    await wrapper.setProps({ viewer: demoViewer('Engineer') })
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(4)
    expect(wrapper.text()).not.toContain('报价审批')
    await wrapper.get('[data-open-approval]').trigger('click')
    expect(wrapper.emitted('open-source')?.[0]?.[0]).toMatchObject({ recipientId: 'preview-engineer', kind: 'demo-engineering' })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })
  it('requests direct navigation without changing business state or opening a detail drawer', async () => {
    const wrapper = page()
    await wrapper.get('[data-open-approval]').trigger('click')
    expect(wrapper.emitted('open-source')?.[0]?.[0]).toMatchObject({ id: 'CRM-DR-04182', state: 'pending' })
    expect(wrapper.findAll('[data-approval-id]')).toHaveLength(6)
    expect(document.querySelector('[aria-label="审批事项详情"]')).toBeNull()
    expect(wrapper.text()).not.toContain('查看事项')
  })
})
