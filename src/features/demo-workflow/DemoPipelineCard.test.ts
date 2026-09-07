import { flushPromises, mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { deriveDemoHealth } from '@/domain/demo-lifecycle'
import { setLocale } from '@/i18n'
import DemoPipelineCard from './DemoPipelineCard.vue'

it.each([
  ['2026-07-28', '2026-07-26', '', 'Customer expected date is overdue by 2 days'],
  ['2026-07-28', '2026-07-28', '', 'Customer expected date is today'],
  ['2026-07-28', '2026-07-29', '', 'Only 1 day until the customer expected date'],
  ['2026-07-28', '', '2026-07-27', 'Test run deadline is overdue by 1 day'],
  ['2026-07-23', '', '', 'No meaningful progress for 5 days'],
  ['2026-07-28', '', '', 'Progress made today'],
  ['2026-07-27', '', '', 'Progress within the last 1 day'],
  ['2026-07-26', '', '', 'Progress within the last 2 days'],
  ['2026-07-24', '', '', 'Progressing normally'],
])('localizes generated health feedback (%s / %s / %s) without changing the project', async (lastProgressAt, customerExpectedDate, testRunDeadline, english) => {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const item = (await api.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
  item.health = deriveDemoHealth({ lastProgressAt, customerExpectedDate, testRunDeadline, today: '2026-07-28' })
  const original = structuredClone(item)
  const wrapper = mount(DemoPipelineCard, { props: { item } })
  expect(wrapper.get('em').text()).toBe(item.health.reason)
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('em').text()).toBe(english)
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('open')?.[0]).toEqual([original])
  setLocale('zh-CN')
  await flushPromises()
  expect(wrapper.get('em').text()).toBe(original.health?.reason)
  expect(item).toEqual(original)
  wrapper.unmount()
})

it('keeps unrecognized health feedback and business text intact', async () => {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const item = (await api.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
  item.account = '客户名称'
  item.health = { level: 'healthy', reason: '客户提供的独立说明', daysSinceProgress: 0, daysToCustomerExpected: null }
  setLocale('en-US')
  const wrapper = mount(DemoPipelineCard, { props: { item } })
  expect(wrapper.get('em').text()).toBe(item.health.reason)
  expect(wrapper.get('strong').text()).toBe(item.account)
  wrapper.unmount()
})
