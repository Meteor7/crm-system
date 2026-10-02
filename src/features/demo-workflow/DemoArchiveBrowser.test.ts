import { flushPromises, mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { setLocale } from '@/i18n'
import DemoArchiveBrowser from './DemoArchiveBrowser.vue'

it('keeps the stored Rejected filter with an honest combined label while each card names its meaning', async () => {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const seed = (await api.listDemoWorkflows({ page: 1, pageSize: 1 })).data.items[0]
  const archived = { ...seed, archiveCategory: 'Completed' as const }
  const items = [
    { ...archived, id: 'DR-TERMINATED', status: 'Rejected', terminationReason: 'Customer paused the project' },
    { ...archived, id: 'DR-REJECTED', status: 'Rejected', terminationReason: '' },
    { ...archived, id: 'DR-ACCEPTED', status: 'Accepted' },
  ]
  const props = { items, result: 'Rejected' as const, salesOwner: 'all', engineerOwner: 'all', groupBy: 'customer' as const, selectedId: '' }
  const wrapper = mount(DemoArchiveBrowser, { props })
  const options = () => wrapper.get('[aria-label="归档结果"], [aria-label="Archive result"]').findAll('option').map((option) => [option.attributes('value'), option.text()])
  const cards = () => wrapper.findAll('[data-demo-id]').map((card) => [card.attributes('data-demo-id'), card.get('.archive-card-head i').text()])

  expect(options()).toEqual([['all', '全部'], ['Accepted', '已接受'], ['Rejected', '已终止 / 已拒绝']])
  expect(cards()).toEqual(expect.arrayContaining([['DR-TERMINATED', '已终止'], ['DR-REJECTED', '已拒绝']]))
  expect(cards()).toHaveLength(2)
  setLocale('en-US')
  await flushPromises()
  expect(options()).toEqual([['all', 'All'], ['Accepted', 'Accepted'], ['Rejected', 'Terminated / rejected']])

  await wrapper.setProps({ result: 'Accepted' })
  expect(cards()).toEqual([['DR-ACCEPTED', 'Accepted']])
  await wrapper.get('select').setValue('Rejected')
  expect(wrapper.emitted('update:result')?.at(-1)).toEqual(['Rejected'])
  wrapper.unmount()
})
