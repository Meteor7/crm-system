import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { demoRequests } from '@/api/mock-data'
import DemoRequestWorkspace from './DemoRequestWorkspace.vue'

describe('Demo Request workspace', () => {
  it('uses a Contacts-style summary table with a separate operation panel', async () => {
    const requests = demoRequests.filter((item) => !['Converted', 'Cancelled'].includes(item.status))
    const wrapper = mount(DemoRequestWorkspace, {
      props: {
        view: 'overview',
        requests,
        selectedId: 'DR-101',
        canCreate: true,
        canEngineer: true,
        canManager: true,
      },
    })

    expect(wrapper.get('[data-demo-request-table]').text()).toContain('Request / 项目')
    expect(wrapper.get('[data-demo-request-table]').text()).toContain('客户')
    expect(wrapper.get('[data-demo-request-table]').text()).toContain('目标日期')
    expect(wrapper.get('[data-demo-request-actions]').text()).toContain('相关人员操作')
    expect(wrapper.get('[data-demo-request-actions]').text()).toContain('工程评估')
    expect(wrapper.find('[data-demo-request-inline-detail]').exists()).toBe(false)
    expect(wrapper.find('.workspace-main').exists()).toBe(true)
    expect(wrapper.find('.toolbar').exists()).toBe(true)
    expect(wrapper.find('.toolbar-search').exists()).toBe(false)
    expect(wrapper.get('[data-demo-request-actions]').classes()).toContain('action-panel')

    await wrapper.get('[data-open-demo-detail="DR-101"]').trigger('click')
    expect(wrapper.emitted('open-detail')?.[0]?.[0]).toMatchObject({ id: 'DR-101' })
  })
})
