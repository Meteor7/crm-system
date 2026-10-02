import { flushPromises, mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { setLocale } from '@/i18n'
import DemoArchiveGroup from './DemoArchiveGroup.vue'
import DemoCommentPanel from './DemoCommentPanel.vue'

it('localizes archive status while emitting the original project', async () => {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const item = (await api.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
  item.status = 'Completed'
  const group = { label: item.account, count: 1, items: [item] }
  const wrapper = mount(DemoArchiveGroup, { props: { group, groupBy: 'customer', selectedId: item.id } })
  expect(wrapper.get('.archive-card-head i').text()).toBe('已完成')
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('.archive-card-head i').text()).toBe('Completed')
  await wrapper.get('.archive-card').trigger('click')
  expect(wrapper.emitted('open')?.[0]).toEqual([item])
  expect(item.status).toBe('Completed')
  wrapper.unmount()
})

it('names a terminated archive card and its reason while historical outcomes keep their labels', async () => {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const seed = (await api.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
  const items = [
    { ...seed, id: 'DR-TERMINATED', status: 'Rejected', terminationReason: '客户暂停项目' },
    { ...seed, id: 'DR-REJECTED', status: 'Rejected', terminationReason: '' },
    { ...seed, id: 'DR-ACCEPTED', status: 'Accepted' },
  ]
  const wrapper = mount(DemoArchiveGroup, { props: { group: { label: seed.account, count: 3, items }, groupBy: 'customer', selectedId: '' } })
  const card = (id: string) => wrapper.get(`[data-demo-id="${id}"]`)
  const label = (id: string) => card(id).get('.archive-card-head i').text()

  expect([label('DR-TERMINATED'), label('DR-REJECTED'), label('DR-ACCEPTED')]).toEqual(['已终止', '已拒绝', '已接受'])
  expect(card('DR-TERMINATED').get('[data-termination-reason]').text()).toContain('客户暂停项目')
  expect(card('DR-REJECTED').find('[data-termination-reason]').exists()).toBe(false)
  setLocale('en-US')
  await flushPromises()
  expect([label('DR-TERMINATED'), label('DR-REJECTED'), label('DR-ACCEPTED')]).toEqual(['Terminated', 'Rejected', 'Accepted'])
  wrapper.unmount()
})

it.each([
  ['Engineer', '工程师', 'Engineer'],
  ['Sales 提交', '销售提交', 'Sales submission'],
  ['Boss Approval', '经理审批', 'Boss Approval'],
  ['Internal Review', '内部评审', 'Internal Review'],
  ['Customer Review', '客户评审', 'Customer Review'],
])('localizes the %s role without changing comment content', async (role, chinese, english) => {
  const comment = { id: 'COMMENT-1', demoRequestId: 'DR-1', author: '中文工程师', role, body: '请保留这段原始说明', createdAt: '2026-09-01' }
  const wrapper = mount(DemoCommentPanel, { props: { comments: [comment] } })
  expect(wrapper.get('[data-demo-comment] small').text()).toBe(chinese)
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('[data-demo-comment] small').text()).toBe(english)
  expect(wrapper.text()).toContain(comment.author)
  expect(wrapper.text()).toContain(comment.body)
  expect(comment.role).toBe(role)
  wrapper.unmount()
})
