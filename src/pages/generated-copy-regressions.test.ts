import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import { createMockApi } from '@/api/mock-adapter'
import { createAppRouter } from '@/app/router'
import { useAppStore } from '@/stores/app'
import { setLocale } from '@/i18n'
import AccountProfile from '@/features/accounts/AccountProfile.vue'
import ContactDetailPage from './ContactDetailPage.vue'
import VisitDetailPage from './VisitDetailPage.vue'

enableAutoUnmount(afterEach)

it('shows the completed visit relationship snapshot and explicitly labels legacy unknowns', async () => {
  const { api, global } = await context('/visits/V-001')
  const response = await api.getVisitDetail('V-001')
  response.data.status = 'Visited'
  response.data.customerKind = 'Prospect'
  vi.spyOn(api, 'getVisitDetail').mockResolvedValue(response)
  const wrapper = mount(VisitDetailPage, { props: { apiClient: api }, global })
  await flushPromises()
  expect(wrapper.get('[data-visit-customer-kind]').text()).toContain('潜在客户')
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('[data-visit-customer-kind]').text()).toContain('Prospect')
  wrapper.unmount()
  response.data.customerKind = ''
  const legacy = mount(VisitDetailPage, { props: { apiClient: api }, global })
  await flushPromises()
  expect(legacy.get('[data-visit-customer-kind]').text()).toContain('Unclassified')
})

async function context(path: string) {
  const api = createMockApi({ latency: 0, role: 'Manager' })
  const pinia = createPinia()
  const app = useAppStore(pinia)
  app.bootstrap = (await api.getBootstrap()).data
  app.activeApi = api
  const router = createAppRouter()
  await router.push(path)
  return { api, global: { plugins: [pinia, router] } }
}

it('updates generated booking units and site placeholders throughout the account profile', async () => {
  const { api, global } = await context('/accounts/ACC-001')
  const response = await api.getAccount360('ACC-001')
  response.data.bookings = [{ id: 'B-1', accountId: 'ACC-001', accountName: 'Acme', primaryContactId: 'CON-001', customerContact: 'Customer', amount: '1000.00', currency: 'CNY', status: 'Confirmed', bookingDate: '2026-09-07', owner: 'Sales', source: 'Upsell', sourceOpportunityId: '', note: '', ddl: '2026-10-01', equipment: 'Tool X', quantity: 2, title: 'Tool X · 2 台', bookingType: 'Equipment' }]
  response.data.sites[0].process = '待确认'
  vi.spyOn(api, 'getAccount360').mockResolvedValue(response)
  const original = structuredClone(response.data)
  const wrapper = mount(AccountProfile, { props: { accountId: 'ACC-001', apiClient: api }, global })
  await flushPromises()
  await wrapper.get('[data-testid="project-type-booking"]').trigger('click')
  expect(wrapper.get('[data-testid="account-project-filter"]').text()).toContain('Tool X · 2 台')
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('[data-testid="account-project-filter"]').text()).toContain('Tool X · 2 units')
  expect(wrapper.get('.project-section').text()).toContain('Tool X · 2 units')
  expect(wrapper.text()).toContain('To be confirmed')
  expect(wrapper.text()).not.toContain('待确认')
  expect(response.data).toEqual(original)
  wrapper.unmount()
})

it('translates contact timeline opportunity stages while keeping business summaries intact', async () => {
  const { api, global } = await context('/contacts/CON-001')
  const response = await api.getContact('CON-001')
  response.data.timeline = [
    { id: 'B-1', type: 'Booking', at: '2026-09-07', title: 'Tool X · 2 台', summary: 'Confirmed', href: '/booking/B-1' },
    { id: 'OP-1', type: 'Opportunity', at: '2026-09-07', title: '客户项目', summary: 'demo_done', href: '/opportunities/OP-1' },
    { id: 'V-1', type: 'Visit', at: '2026-09-07', title: '客户拜访', summary: '需求发现', href: '/visits/V-1' },
  ]
  vi.spyOn(api, 'getContact').mockResolvedValue(response)
  const wrapper = mount(ContactDetailPage, { props: { apiClient: api }, global })
  await flushPromises()
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.get('[data-timeline-id="OP-1"]').text()).toContain('Demo done')
  expect(wrapper.get('[data-timeline-id="B-1"]').text()).toContain('Tool X · 2 units')
  expect(wrapper.get('[data-timeline-id="B-1"]').text()).not.toContain('2 台')
  expect(wrapper.text()).toContain('需求发现')
  expect(wrapper.text()).toContain('客户项目')
  expect(wrapper.get('[data-timeline-id="V-1"]').text()).toContain('需求发现')
  expect(response.data.timeline.find(item => item.id === 'OP-1')?.summary).toBe('demo_done')
  wrapper.unmount()
})

it('translates the meeting parser description on an already loaded visit', async () => {
  const { api, global } = await context('/visits/V-001')
  const response = await api.getVisitDetail('V-001')
  response.data.meetingRecord = {
    id: 'MR-1', visitId: 'V-001', meetingStart: '', meetingEnd: '', purpose: '客户填写的目的', attendees: '', agenda: '', summary: '', conclusion: '', followup: '',
    parseStatus: 'NeedsManualReview', parseMessage: '部分模板字段未识别，请检查并补录。', parsedAt: '2026-09-07', manuallyCorrected: false,
  }
  vi.spyOn(api, 'getVisitDetail').mockResolvedValue(response)
  const wrapper = mount(VisitDetailPage, { props: { apiClient: api }, global })
  await flushPromises()
  expect(wrapper.text()).toContain(response.data.meetingRecord.parseMessage)
  setLocale('en-US')
  await flushPromises()
  expect(wrapper.text()).toContain('Some template fields were not recognized. Review and complete them.')
  expect(wrapper.text()).not.toContain(response.data.meetingRecord.parseMessage)
  expect(wrapper.text()).toContain('客户填写的目的')
  wrapper.unmount()
})
